from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from scripts.link_admin_telegram import link_admin_telegram
from src.models.admin import AdminUser
from src.models.events import Event
from src.repositories.admin import AdminRepository


def new_event(**changes):
    start = datetime.now(UTC) + timedelta(days=3)
    values = {
        "title": "Кино вечером",
        "description": "Обсуждение фильма",
        "direction_id": UUID(int=1),
        "starts_at": start,
        "ends_at": start + timedelta(hours=2),
        "timezone": "Europe/Moscow",
        "address": "Клуб Повод",
        "capacity": 20,
    }
    values.update(changes)
    return Event(**values)


async def test_event_accepts_null_address_and_defaults_focus(db_session):
    event = new_event(address=None)
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    assert event.address is None
    assert event.cover_focus_x == 0.5
    assert event.cover_focus_y == 0.5
    assert event.cover_width is None
    assert event.cover_height is None
    assert event.accent_color is None


async def test_focus_server_default_applies_to_raw_insert(db_session):
    result = await db_session.execute(
        text(
            "INSERT INTO events (id, title, description, direction_id, starts_at, ends_at,"
            " timezone, capacity, status, created_at, updated_at)"
            " VALUES (gen_random_uuid(), 't', 'd', :direction, now(), now() + interval '1 hour',"
            " 'UTC', 5, 'draft', now(), now()) RETURNING cover_focus_x, cover_focus_y, address"
        ),
        {"direction": UUID(int=1)},
    )
    assert result.one() == (0.5, 0.5, None)


@pytest.mark.parametrize(
    "changes",
    [
        {"cover_focus_x": 1.5},
        {"cover_focus_y": -0.1},
        {"accent_color": "red"},
        {"accent_color": "#12345"},
    ],
)
async def test_focus_and_accent_constraints(db_session, changes):
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(new_event(**changes))
            await db_session.flush()


async def test_focus_and_accent_accept_valid_values(db_session):
    event = new_event(
        cover_focus_x=0.25, cover_focus_y=1.0, accent_color="#A1b2C3", cover_width=1080
    )
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    assert (event.cover_focus_x, event.cover_focus_y) == (0.25, 1.0)
    assert event.accent_color == "#A1b2C3"
    assert event.cover_width == 1080


async def test_link_admin_telegram(db_session):
    owner = AdminUser(login="owner", password_hash="x", role="owner")
    other = AdminUser(login="second", password_hash="x", role="administrator")
    db_session.add_all([owner, other])
    await db_session.flush()

    await link_admin_telegram(db_session, "owner", 42)

    found = await AdminRepository(db_session).user_by_telegram_id(42)
    assert found is not None
    assert found.id == owner.id
    assert await AdminRepository(db_session).user_by_telegram_id(43) is None

    with pytest.raises(LookupError):
        await link_admin_telegram(db_session, "nobody", 1)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await link_admin_telegram(db_session, "second", 42)
