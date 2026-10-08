from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select

from src.bot.router import create_router
from src.models.identity import Consent, ConsentType, User
from src.repositories.consents import ConsentRepository
from src.services.consents.service import ConsentService


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


async def test_start_and_consent_flow_survives_recreated_dispatchers(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    assert "consent:personal_data:grant:draft-v1:0" in callbacks(transport)
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Consent)) == 0
    await press(pg_factory, bot, rendered_callback(transport, "personal_data", "grant"))
    assert "consent:marketing:grant:draft-v1:0" in callbacks(transport)
    await press(pg_factory, bot, rendered_callback(transport, "marketing", "skip"))
    assert "direction:00000000-0000-0000-0000-000000000001" in callbacks(transport)
    await feed_start(pg_factory, bot, "/start latest", "changed")
    async with pg_factory() as session:
        user = (await session.scalars(select(User))).one()
        assert user.username == "changed"
        assert user.first_start_param == "first"
        assert user.last_start_param == "latest"
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        service = ConsentService(ConsentRepository(session))
        assert await service.is_active(user.id, ConsentType.PERSONAL_DATA)
        assert not await service.is_active(user.id, ConsentType.MARKETING)
    await press(pg_factory, bot, rendered_callback(transport, "marketing", "show"))
    await press(pg_factory, bot, rendered_callback(transport, "marketing", "grant"))
    await press(pg_factory, bot, rendered_callback(transport, "marketing", "revoke"))
    async with pg_factory() as session:
        assert not await ConsentService(ConsentRepository(session)).is_active(
            user.id, ConsentType.MARKETING
        )
        assert await session.scalar(select(func.count()).select_from(Consent)) == 4


async def test_marketing_skip_persists_refusal_after_restart(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    await press(pg_factory, bot, rendered_callback(transport, "personal_data", "grant"))
    await press(pg_factory, bot, rendered_callback(transport, "marketing", "skip"))
    async with pg_factory() as session:
        events = (await session.scalars(select(Consent).order_by(Consent.sequence))).all()
        assert len(events) == 2
        assert events[-1].status == "revoked"
    await feed_start(pg_factory, bot)
    assert rendered_callback(transport, "marketing", "show")


async def test_stale_marketing_opt_out_works_after_personal_consent_revocation(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    await press(pg_factory, bot, rendered_callback(transport, "personal_data", "grant"))
    await press(pg_factory, bot, rendered_callback(transport, "marketing", "grant"))
    async with pg_factory() as session, session.begin():
        user = (await session.scalars(select(User))).one()
        from src.models.identity import ConsentSource

        await ConsentService(ConsentRepository(session)).revoke(
            user.id, ConsentType.PERSONAL_DATA, ConsentSource.ADMIN
        )
    await press(pg_factory, bot, "consent:marketing:revoke:obsolete:0")
    async with pg_factory() as session:
        assert not await ConsentService(ConsentRepository(session)).is_active(
            user.id, ConsentType.MARKETING
        )


@pytest.mark.parametrize(
    "data",
    [
        "consent:personal_data:grant:obsolete",
        "consent:personal_data:grant:draft-v1",
        "consent:personal_data:grant:draft-v1:1",
        "consent:personal_data:grant:draft-v1:-1",
        "consent:personal_data:grant:draft-v1:9223372036854775808",
        "consent:personal_data:grant:draft-v1:invalid",
        "consent:marketing:grant:draft-v1:0",
        "consent:unknown:grant:draft-v1:0",
    ],
)
async def test_invalid_or_out_of_order_callbacks_do_not_grant_consent(pg_factory, data):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    await press(pg_factory, bot, data)
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Consent)) == 0
    assert "consent:personal_data:grant:draft-v1:0" in callbacks(transport)


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


def rendered_callback(transport, consent_type, action):
    prefix = f"consent:{consent_type}:{action}:"
    return next(data for data in callbacks(transport) if data.startswith(prefix))


async def test_replayed_grant_stays_revoked_and_fresh_prompt_can_reconsent(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    await press(pg_factory, bot, rendered_callback(transport, "personal_data", "grant"))
    old_grant = rendered_callback(transport, "marketing", "grant")
    await press(pg_factory, bot, old_grant)
    revoke = rendered_callback(transport, "marketing", "revoke")
    await press(pg_factory, bot, revoke)
    # press() creates a new dispatcher/router for every update.
    await press(pg_factory, bot, old_grant)
    async with pg_factory() as session:
        user = (await session.scalars(select(User))).one()
        assert not await ConsentService(ConsentRepository(session)).is_active(
            user.id, ConsentType.MARKETING
        )
        assert await session.scalar(select(func.count()).select_from(Consent)) == 3
    fresh_grant = rendered_callback(transport, "marketing", "grant")
    assert fresh_grant != old_grant
    await press(pg_factory, bot, fresh_grant)
    async with pg_factory() as session:
        assert await ConsentService(ConsentRepository(session)).is_active(
            user.id, ConsentType.MARKETING
        )
        assert await session.scalar(select(func.count()).select_from(Consent)) == 4
    # A consumed current prompt must also be single-use before any revoke.
    await press(pg_factory, bot, fresh_grant)
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Consent)) == 4


async def test_overlong_start_args_get_clear_response_without_profile_write(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot, "/start " + "x" * 65)
    assert "64" in transport.sent[-1].text
    assert "/start" in transport.sent[-1].text
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0
    await feed_start(pg_factory, bot, "/start " + "x" * 64)
    assert "consent:personal_data:grant:draft-v1:0" in callbacks(transport)
    async with pg_factory() as session:
        user = (await session.scalars(select(User))).one()
        assert user.first_start_param == "x" * 64


def test_revision_callbacks_fit_telegram_limit():
    from src.bot.keyboards.main_menu import consent_prompt

    keyboard = consent_prompt("personal_data", "v" * 16, 2**63 - 1)
    assert len(keyboard.inline_keyboard[0][0].callback_data.encode("utf-8")) <= 64
