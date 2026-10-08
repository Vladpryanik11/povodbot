from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.handlers.checkout import CheckoutHandler
from src.bot.handlers.events import EventHandler
from src.bot.handlers.settings import SettingsHandler
from src.bot.handlers.start import BotResponse, ConsentTexts, StartHandler
from src.bot.handlers.support import SupportHandler
from src.bot.handlers.tickets import TicketHandler
from src.bot.keyboards.events import events_keyboard
from src.core.config import get_settings
from src.db.session import get_session_factory
from src.models.identity import ConsentType
from src.repositories.consents import ConsentRepository
from src.repositories.directions import DirectionRepository
from src.repositories.events import EventRepository
from src.repositories.users import UserRepository
from src.services.analytics.attribution import AttributionService
from src.services.consents.service import ConsentService
from src.services.directions.service import DirectionService
from src.services.events.service import EventService
from src.services.payments.ports import PaymentGateway
from src.services.payments.service import PaymentStateError
from src.services.payments.tbank_client import TBankPaymentGateway
from src.services.users.service import UserService


def create_router(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    texts: ConsentTexts | None = None,
    payment_gateway: PaymentGateway | None = None,
) -> Router:
    router = Router(name="onboarding")
    consent_texts = texts or ConsentTexts.from_settings()

    def handler(session: AsyncSession) -> StartHandler:
        return StartHandler(
            UserService(UserRepository(session)),
            ConsentService(ConsentRepository(session)),
            DirectionService(DirectionRepository(session)),
            consent_texts,
            AttributionService(session),
        )

    @router.message(CommandStart(), F.chat.type == "private")
    async def start(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        if command.args is not None and len(command.args) > 64:
            await message.answer(
                "Параметр /start слишком длинный: максимум 64 символа. "
                "Отправьте /start без параметра или воспользуйтесь корректной ссылкой."
            )
            return
        factory = session_factory or get_session_factory()
        async with factory() as session, session.begin():
            response = await handler(session).start(message.from_user, command.args)
        # Commit persisted state before telling Telegram that the action succeeded.
        await message.answer(response.text, reply_markup=response.keyboard)

    @router.message(Command("stop"), F.chat.type == "private")
    async def stop(message: Message) -> None:
        if message.from_user is None:
            return
        factory = session_factory or get_session_factory()
        async with factory() as session, session.begin():
            user = await UserRepository(session).by_telegram_id(message.from_user.id)
            if user is not None:
                await SettingsHandler(ConsentRepository(session)).unsubscribe_marketing(user.id)
        await message.answer("Рекламные сообщения отключены. Вернуть их можно в настройках.")

    @router.callback_query(F.data.startswith("consent:"), F.message.chat.type == "private")
    async def consent(query: CallbackQuery) -> None:
        if not isinstance(query.message, Message) or query.data is None:
            await query.answer()
            return
        factory = session_factory or get_session_factory()
        async with factory() as session, session.begin():
            response = await handler(session).consent(query.from_user, query.data)
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
        async with factory() as session, session.begin():
            user = await UserRepository(session).by_telegram_id(query.from_user.id)
            if user is None or not await ConsentService(ConsentRepository(session)).is_active(
                user.id, ConsentType.PERSONAL_DATA
            ):
                response = await handler(session).start(query.from_user, None)
            else:
                parts = query.data.split(":")
                try:
                    if len(parts) == 2 and parts[0] == "buy":
                        response = await CheckoutHandler(session).choose_quantity(UUID(parts[1]))
                    elif len(parts) == 3 and parts[0] == "quantity":
                        created_gateway = None
                        gateway = payment_gateway
                        if gateway is None:
                            created_gateway = _new_tbank_gateway()
                            gateway = created_gateway
                        try:
                            response = await CheckoutHandler(session, gateway).create_payment(
                                UUID(parts[1]), int(parts[2]), user.id
                            )
                        finally:
                            if created_gateway is not None:
                                await created_gateway.aclose()
                    else:
                        raise ValueError("Invalid checkout callback")
                except (LookupError, PaymentStateError, ValueError):
                    response = BotResponse(
                        "Не удалось создать заказ. Откройте актуальную афишу и попробуйте ещё раз.",
                        events_keyboard([]),
                    )
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
            user = await UserRepository(session).by_telegram_id(query.from_user.id)
            if user is None:
                response = await handler(session).start(query.from_user, None)
            elif query.data == "tickets:mine":
                response = await TicketHandler(session).mine(user.id)
            else:
                response = BotResponse(SupportHandler().answer(), events_keyboard([]))
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
                response = await handler(session).start(query.from_user, None)
            else:
                user = await UserRepository(session).by_telegram_id(query.from_user.id)
                response = await EventHandler(
                    EventService(EventRepository(session)),
                    DirectionService(DirectionRepository(session)),
                    AttributionService(session),
                ).read(query.data, user.id if user is not None else None)
        await query.answer()
        await query.message.answer(response.text, reply_markup=response.keyboard, parse_mode=None)

    return router


def _new_tbank_gateway() -> TBankPaymentGateway:
    settings = get_settings()
    return TBankPaymentGateway(
        settings.tbank_terminal_key,
        settings.tbank_password,
        api_token=settings.tbank_api_token,
        base_url=settings.tbank_api_base_url,
    )
