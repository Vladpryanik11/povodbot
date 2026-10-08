import asyncio

import pytest
from sqlalchemy import func, select

from src.models.identity import User
from src.repositories.users import UserRepository
from src.services.users.service import UserService


async def test_start_creates_and_updates_one_crm_record(db_session):
    service = UserService(UserRepository(db_session))
    first = await service.upsert_telegram_user(5000000000, "Анна", None, "anna", "first")
    again = await service.upsert_telegram_user(5000000000, "Аня", "Иванова", "new", "last")
    assert first.id == again.id
    assert again.first_name == "Аня"
    assert again.last_name == "Иванова"
    assert again.username == "new"
    assert again.first_start_param == "first"
    assert again.last_start_param == "last"
    assert again.created_at.tzinfo is not None
    assert again.last_seen_at >= first.last_seen_at
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1


async def test_first_start_without_source_stays_unattributed(db_session):
    service = UserService(UserRepository(db_session))
    await service.upsert_telegram_user(1, None, None, None, None)
    later = await service.upsert_telegram_user(1, None, None, None, "later")
    blank = await service.upsert_telegram_user(1, None, None, None, None)
    assert later.first_start_param is None
    assert blank.last_start_param == "later"


async def test_concurrent_start_does_not_duplicate(pg_factory):
    async def start(source):
        async with pg_factory() as session, session.begin():
            return await UserService(UserRepository(session)).upsert_telegram_user(
                99, None, None, None, source
            )

    results = await asyncio.gather(start("a"), start("b"))
    assert results[0].id == results[1].id
    assert results[0].first_start_param == results[1].first_start_param
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize("telegram_id", [0, -1])
async def test_invalid_telegram_id_rejected(db_session, telegram_id):
    with pytest.raises(ValueError):
        await UserService(UserRepository(db_session)).upsert_telegram_user(
            telegram_id, None, None, None, None
        )
