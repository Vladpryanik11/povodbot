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
    assert "consent:personal_data:grant:draft-v1" in callbacks(transport)
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Consent)) == 0
    await press(pg_factory, bot, "consent:personal_data:grant:draft-v1")
    assert "consent:marketing:grant:draft-v1" in callbacks(transport)
    await press(pg_factory, bot, "consent:marketing:skip:draft-v1")
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
    await press(pg_factory, bot, "consent:marketing:grant:draft-v1")
    assert "consent:marketing:revoke:draft-v1" in callbacks(transport)
    await press(pg_factory, bot, "consent:marketing:revoke:draft-v1")
    async with pg_factory() as session:
        assert not await ConsentService(ConsentRepository(session)).is_active(
            user.id, ConsentType.MARKETING
        )
        assert await session.scalar(select(func.count()).select_from(Consent)) == 4


async def test_marketing_skip_persists_refusal_after_restart(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    await press(pg_factory, bot, "consent:personal_data:grant:draft-v1")
    await press(pg_factory, bot, "consent:marketing:skip:draft-v1")
    async with pg_factory() as session:
        events = (await session.scalars(select(Consent).order_by(Consent.sequence))).all()
        assert len(events) == 2
        assert events[-1].status == "revoked"
    await feed_start(pg_factory, bot)
    assert "consent:marketing:show:draft-v1" in callbacks(transport)


async def test_stale_marketing_opt_out_works_after_personal_consent_revocation(pg_factory):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    await press(pg_factory, bot, "consent:personal_data:grant:draft-v1")
    await press(pg_factory, bot, "consent:marketing:grant:draft-v1")
    async with pg_factory() as session, session.begin():
        user = (await session.scalars(select(User))).one()
        from src.models.identity import ConsentSource

        await ConsentService(ConsentRepository(session)).revoke(
            user.id, ConsentType.PERSONAL_DATA, ConsentSource.ADMIN
        )
    await press(pg_factory, bot, "consent:marketing:revoke:obsolete")
    async with pg_factory() as session:
        assert not await ConsentService(ConsentRepository(session)).is_active(
            user.id, ConsentType.MARKETING
        )


@pytest.mark.parametrize(
    "data",
    [
        "consent:personal_data:grant:obsolete",
        "consent:marketing:grant:draft-v1",
        "consent:unknown:grant:draft-v1",
    ],
)
async def test_invalid_or_out_of_order_callbacks_do_not_grant_consent(pg_factory, data):
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await feed_start(pg_factory, bot)
    await press(pg_factory, bot, data)
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Consent)) == 0
    assert "consent:personal_data:grant:draft-v1" in callbacks(transport)


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
