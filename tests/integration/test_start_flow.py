from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select

from src.bot.router import create_router
from src.models.identity import Consent, User


class TelegramTransport(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109 - aiogram interface
        if isinstance(method, SendMessage):
            self.sent.append(method)
            return Message(
                message_id=len(self.sent),
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        if isinstance(method, AnswerCallbackQuery):
            return True
        raise AssertionError(type(method))

    async def stream_content(self, url, **kwargs) -> AsyncGenerator[bytes, None]:
        yield b""


def message(text, username="first"):
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=42, type="private"),
        from_user=TelegramUser(id=42, is_bot=False, first_name="Анна", username=username),
        text=text,
    )


async def feed_start(factory, bot, text="/start first", username="first"):
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(factory))
    await dispatcher.feed_update(bot, Update(update_id=1, message=message(text, username)))


async def press(factory, bot, data):
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(factory))
    await dispatcher.feed_update(
        bot,
        Update(
            update_id=2,
            callback_query=CallbackQuery(
                id="callback",
                from_user=message("").from_user,
                chat_instance="test",
                message=message("prompt"),
                data=data,
            ),
        ),
    )


def callbacks(transport):
    return [
        button.callback_data
        for row in transport.sent[-1].reply_markup.inline_keyboard
        for button in row
    ]


async def test_start_asks_for_no_consent_and_greets_first_then_again(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    assert transport.sent[-1].text == (
        "Привет, Анна! Это «Повод».\n\nВсе наши вечера и билеты в приложении, открывается кнопкой."
    )
    assert callbacks(transport) == ["events:all", "tickets:mine", "support"]
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Consent)) == 0
    await feed_start(pg_factory, bot, "/start latest", "changed")
    assert transport.sent[-1].text == "Привет, Анна! Открывай, посмотри, что у нас скоро."
    async with pg_factory() as session:
        user = (await session.scalars(select(User))).one()
        assert user.username == "changed"
        assert user.first_start_param == "first"
        assert user.last_start_param == "latest"
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Consent)) == 0


async def test_old_consent_buttons_just_show_the_menu(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    for data in ("consent:personal_data:grant:draft-v1:0", "consent:marketing:revoke:x:0"):
        await press(pg_factory, bot, data)
        assert transport.sent[-1].text == "Привет, Анна! Открывай, посмотри, что у нас скоро."
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Consent)) == 0


async def test_stop_is_gone_and_gets_the_stray_text_reply(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    await feed_start(pg_factory, bot, "/stop")
    assert transport.sent[-1].text.startswith("Мы тут отвечаем только на кнопки.")
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Consent)) == 0


async def test_tickets_help_commands_and_unknown_text(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot, "/tickets")  # unknown user gets the start menu
    assert transport.sent[-1].text.startswith("Привет, Анна! Это «Повод».")
    await feed_start(pg_factory, bot, "/tickets")
    assert transport.sent[-1].text == "Билетов пока нет. Загляни в приложение, там афиша."
    assert callbacks(transport) == ["events:menu"]
    await feed_start(pg_factory, bot, "/help")
    assert "напиши нам: https://t.me/vladpryanik" in transport.sent[-1].text
    await feed_start(pg_factory, bot, "что вы делаете?")
    assert transport.sent[-1].text.startswith("Мы тут отвечаем только на кнопки.")
    assert callbacks(transport) == ["events:all", "tickets:mine", "support"]


async def test_group_start_does_not_register_profile(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(pg_factory))
    group_message = message("/start").model_copy(update={"chat": Chat(id=-99, type="group")})
    await dispatcher.feed_update(bot, Update(update_id=1, message=group_message))
    assert not transport.sent
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_overlong_start_args_get_clear_response_without_profile_write(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot, "/start " + "x" * 65)
    assert transport.sent[-1].text == "Что-то не так со ссылкой. Отправь просто /start."
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0
    await feed_start(pg_factory, bot, "/start " + "x" * 64)
    assert "Привет, Анна!" in transport.sent[-1].text
    async with pg_factory() as session:
        user = (await session.scalars(select(User))).one()
        assert user.first_start_param == "x" * 64
