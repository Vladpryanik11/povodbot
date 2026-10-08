from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.handlers.events import EventHandler
from src.bot.handlers.settings import SettingsHandler
from src.bot.handlers.start import ConsentTexts, StartHandler
from src.db.session import get_session_factory
from src.repositories.consents import ConsentRepository
from src.repositories.directions import DirectionRepository
from src.repositories.events import EventRepository
from src.repositories.users import UserRepository
from src.services.analytics.attribution import AttributionService
from src.services.consents.service import ConsentService
from src.services.directions.service import DirectionService
from src.services.events.service import EventService
from src.services.users.service import UserService


def create_router(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    texts: ConsentTexts | None = None,
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
                response = await EventHandler(
                    EventService(EventRepository(session)),
                    DirectionService(DirectionRepository(session)),
                ).read(query.data)
        await query.answer()
        await query.message.answer(response.text, reply_markup=response.keyboard, parse_mode=None)

    return router
