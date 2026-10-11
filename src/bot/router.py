from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot import copy
from src.bot.handlers.checkout import CheckoutHandler
from src.bot.handlers.events import EventHandler
from src.bot.handlers.start import BotResponse, StartHandler, menu_response
from src.bot.handlers.support import SupportHandler
from src.bot.handlers.tickets import TicketHandler
from src.bot.keyboards.events import events_keyboard
from src.bot.keyboards.main_menu import back_to_menu
from src.core.config import get_settings
from src.db.session import get_session_factory
from src.repositories.directions import DirectionRepository
from src.repositories.events import EventRepository
from src.repositories.users import UserRepository
from src.services.analytics.attribution import AttributionService
from src.services.directions.service import DirectionService
from src.services.events.service import EventService
from src.services.orders.service import PendingOrderDTO
from src.services.payments.checkout import PaymentCheckoutService
from src.services.payments.ports import PaymentGateway
from src.services.payments.service import PaymentStateError
from src.services.payments.tbank_client import TBankPaymentGateway
from src.services.users.service import UserService


def create_router(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    payment_gateway: PaymentGateway | None = None,
    miniapp_url: str | None = None,
    support_contact: str | None = None,
) -> Router:
    router = Router(name="onboarding")
    settings = get_settings()
    app_url = settings.miniapp_url if miniapp_url is None else miniapp_url
    contact = settings.support_contact if support_contact is None else support_contact

    def handler(session: AsyncSession) -> StartHandler:
        return StartHandler(
            UserService(UserRepository(session)),
            AttributionService(session),
            app_url,
        )

    @router.message(CommandStart(), F.chat.type == "private")
    async def start(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        if command.args is not None and len(command.args) > 64:
            await message.answer(copy.ERR_START_PARAM)
            return
        factory = session_factory or get_session_factory()
        async with factory() as session, session.begin():
            response = await handler(session).start(message.from_user, command.args)
        # Commit persisted state before telling Telegram that the action succeeded.
        await message.answer(response.text, reply_markup=response.keyboard)

    async def personal_area_response(
        session: AsyncSession, sender: TelegramUser, what: str
    ) -> BotResponse:
        user = await UserRepository(session).by_telegram_id(sender.id)
        if user is None:
            return await handler(session).start(sender, None)
        if what == "tickets":
            return await TicketHandler(session, app_url).mine(user.id)
        return BotResponse(SupportHandler(contact).answer(), back_to_menu())

    @router.message(Command("tickets"), F.chat.type == "private")
    async def tickets_command(message: Message) -> None:
        if message.from_user is None:
            return
        factory = session_factory or get_session_factory()
        async with factory() as session, session.begin():
            response = await personal_area_response(session, message.from_user, "tickets")
        await message.answer(response.text, reply_markup=response.keyboard, parse_mode=None)

    @router.message(Command("help"), F.chat.type == "private")
    async def help_command(message: Message) -> None:
        if message.from_user is None:
            return
        factory = session_factory or get_session_factory()
        async with factory() as session, session.begin():
            response = await personal_area_response(session, message.from_user, "support")
        await message.answer(response.text, reply_markup=response.keyboard, parse_mode=None)

    @router.callback_query(F.data.startswith("consent:"), F.message.chat.type == "private")
    async def legacy_consent(query: CallbackQuery) -> None:
        # Buttons from old consent prompts: nothing to record any more, just show the menu.
        if not isinstance(query.message, Message):
            await query.answer()
            return
        response = menu_response(query.from_user.first_name, app_url)
        await query.answer()
        await query.message.answer(response.text, reply_markup=response.keyboard)

    @router.callback_query(
        F.data.startswith("buy:") | F.data.startswith("quantity:"),
        F.message.chat.type == "private",
    )
    async def checkout(query: CallbackQuery) -> None:
        if not isinstance(query.message, Message) or query.data is None:
            await query.answer()
            return
        factory = session_factory or get_session_factory()
        pending_order: PendingOrderDTO | None = None
        created_gateway: TBankPaymentGateway | None = None
        async with factory() as session, session.begin():
            user = await UserRepository(session).by_telegram_id(query.from_user.id)
            if user is None:
                response = await handler(session).start(query.from_user, None)
            else:
                parts = query.data.split(":")
                try:
                    if len(parts) == 2 and parts[0] == "buy":
                        response = await CheckoutHandler(session).choose_quantity(UUID(parts[1]))
                    elif len(parts) == 3 and parts[0] == "quantity":
                        _, pending_order = await CheckoutHandler(session).create_order(
                            UUID(parts[1]), int(parts[2]), user.id
                        )
                        response = BotResponse(
                            copy.ORDER_CREATED,
                            events_keyboard([]),
                        )
                    else:
                        raise ValueError("Invalid checkout callback")
                except (LookupError, PaymentStateError, ValueError):
                    response = BotResponse(
                        copy.ERR_ORDER,
                        events_keyboard([]),
                    )
        if pending_order is not None:
            gateway = payment_gateway
            if gateway is None:
                created_gateway = _new_tbank_gateway()
                gateway = created_gateway
            try:
                checkout = await PaymentCheckoutService(factory, gateway).start(
                    pending_order.order_id
                )
                response = CheckoutHandler.payment_response(pending_order, checkout)
            except (LookupError, PaymentStateError, ValueError):
                response = BotResponse(
                    copy.ERR_PAYMENT,
                    events_keyboard([]),
                )
            finally:
                if created_gateway is not None:
                    await created_gateway.aclose()
        await query.answer()
        await query.message.answer(response.text, reply_markup=response.keyboard, parse_mode=None)

    @router.callback_query(
        (F.data == "tickets:mine") | (F.data == "support"),
        F.message.chat.type == "private",
    )
    async def personal_area(query: CallbackQuery) -> None:
        if not isinstance(query.message, Message) or query.data is None:
            await query.answer()
            return
        factory = session_factory or get_session_factory()
        async with factory() as session, session.begin():
            response = await personal_area_response(
                session, query.from_user, "tickets" if query.data == "tickets:mine" else "support"
            )
        await query.answer()
        await query.message.answer(response.text, reply_markup=response.keyboard, parse_mode=None)

    @router.callback_query(
        F.data.startswith("direction:")
        | F.data.startswith("event:")
        | F.data.startswith("events:"),
        F.message.chat.type == "private",
    )
    async def events(query: CallbackQuery) -> None:
        if not isinstance(query.message, Message) or query.data is None:
            await query.answer()
            return
        factory = session_factory or get_session_factory()
        async with factory() as session, session.begin():
            if query.data == "events:menu":
                response = handler(session).menu(query.from_user.first_name)
            else:
                user = await UserRepository(session).by_telegram_id(query.from_user.id)
                response = await EventHandler(
                    EventService(EventRepository(session)),
                    DirectionService(DirectionRepository(session)),
                    AttributionService(session),
                ).read(query.data, user.id if user is not None else None)
        await query.answer()
        await query.message.answer(response.text, reply_markup=response.keyboard, parse_mode=None)

    @router.message(F.chat.type == "private")
    async def unknown_text(message: Message) -> None:
        name = message.from_user.first_name if message.from_user else None
        menu = menu_response(name, app_url)
        await message.answer(copy.UNKNOWN_TEXT, reply_markup=menu.keyboard)

    return router


def _new_tbank_gateway() -> TBankPaymentGateway:
    settings = get_settings()
    return TBankPaymentGateway(
        settings.tbank_terminal_key,
        settings.tbank_password,
        api_token=settings.tbank_api_token,
        base_url=settings.tbank_api_base_url,
    )
