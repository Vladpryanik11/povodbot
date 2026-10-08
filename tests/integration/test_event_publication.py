from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError

from src.api.admin.events import require_event_admin
from src.api.app import create_app
from src.db.session import get_async_session
from src.models.events import Event, EventStatus
from src.services.events.service import UpdateEventCommand
from tests.integration.test_start_flow import TelegramTransport, callbacks, press
from tests.unit.services.test_events import draft, service


def app_for(factory, admin=False):
    app = create_app()

    async def session_dependency():
        async with factory() as session, session.begin():
            yield session

    app.dependency_overrides[get_async_session] = session_dependency
    if admin:
        app.dependency_overrides[require_event_admin] = lambda: None
    return app


def payload(command):
    result = asdict(command)
    result["direction_id"] = str(command.direction_id)
    result["starts_at"] = command.starts_at.isoformat()
    result["ends_at"] = command.ends_at.isoformat()
    return result


async def test_api_admin_guard_and_public_projection(pg_factory):
    app = app_for(pg_factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.post("/api/admin/events", json=payload(draft()))
        assert denied.status_code == 403
        app.dependency_overrides[require_event_admin] = lambda: None
        created = await client.post("/api/admin/events", json=payload(draft()))
        assert created.status_code == 201
        event_id = created.json()["id"]
        assert (await client.get(f"/api/public/events/{event_id}")).status_code == 404
        published = await client.post(f"/api/admin/events/{event_id}/publish")
        assert published.status_code == 200
        public = (await client.get(f"/api/public/events/{event_id}")).json()
        assert set(public) == {
            "id",
            "title",
            "description",
            "cover_ref",
            "direction_id",
            "starts_at",
            "ends_at",
            "timezone",
            "address",
            "map_url",
            "capacity",
            "ticket_types",
        }
        assert set(public["ticket_types"][0]) == {
            "id",
            "name",
            "price_kopecks",
            "currency",
            "limit",
        }
        assert len((await client.get("/api/public/events")).json()) == 1
        assert (
            await client.get("/api/public/events", params={"direction_id": str(UUID(int=2))})
        ).json() == []
        assert (
            await client.patch(f"/api/admin/events/{event_id}", json={"status": "cancelled"})
        ).status_code == 200
        assert (await client.get(f"/api/public/events/{event_id}")).status_code == 404
        assert (await client.delete(f"/api/admin/events/{event_id}")).status_code == 405


@pytest.mark.parametrize("data", ["direction:bad", "event:bad", f"event:{uuid4()}", "events:all"])
async def test_bot_stale_callbacks_safe(pg_factory, data):
    from aiogram import Bot

    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await press(pg_factory, bot, data)
    assert transport.sent
    assert "events:all" in callbacks(transport) or data == "events:all"


async def test_bot_direction_event_card_survives_router_restart(pg_factory):
    from aiogram import Bot

    async with pg_factory() as session, session.begin():
        event = await service(session).create_draft(draft())
        await service(session).publish(event.id)
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await press(pg_factory, bot, "direction:00000000-0000-0000-0000-000000000001")
    assert f"event:{event.id}" in callbacks(transport)
    await press(pg_factory, bot, f"event:{event.id}")
    assert "150.00 RUB" in transport.sent[-1].text
    assert "Клуб Повод" in transport.sent[-1].text
    assert "events:all" in callbacks(transport)
    async with pg_factory() as session, session.begin():
        await service(session).update(event.id, UpdateEventCommand(status=EventStatus.CANCELLED))
    await press(pg_factory, bot, f"event:{event.id}")
    assert "недоступно" in transport.sent[-1].text


async def test_database_protects_published_history(pg_factory):
    async with pg_factory() as session, session.begin():
        event = await service(session).create_draft(draft(ticket_types=[]))
        # Isolate the event deletion trigger from ticket FK restrictions.
        stored = await session.get(Event, event.id)
        stored.status = EventStatus.CANCELLED
        stored.published_at = datetime.now(UTC)
    async with pg_factory() as session, session.begin():
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(delete(Event).where(Event.id == event.id))
        assert await session.scalar(select(Event.id).where(Event.id == event.id)) == event.id


async def test_public_hides_past_and_inactive_tickets(db_session):
    events = service(db_session)
    event = await events.create_draft(draft())
    await events.publish(event.id)
    stored = await db_session.get(Event, event.id)
    stored.starts_at = datetime.now(UTC) - timedelta(hours=1)
    stored.ends_at = datetime.now(UTC) + timedelta(hours=1)
    await db_session.flush()
    assert await events.list_public(None, None) == []


async def test_long_bot_card_preserves_details_within_telegram_limit(pg_factory):
    from aiogram import Bot

    async with pg_factory() as session, session.begin():
        event = await service(session).create_draft(draft(description="Длинное описание " * 1000))
        await service(session).publish(event.id)
    transport = TelegramTransport()
    bot = Bot("123456:TEST_TOKEN_NOT_A_REAL_SECRET", session=transport)
    await press(pg_factory, bot, f"event:{event.id}")
    assert len(transport.sent[-1].text) <= 4096
    assert "150.00 RUB" in transport.sent[-1].text
    assert "Клуб Повод" in transport.sent[-1].text


async def test_api_nullable_patch_and_invalid_inputs(pg_factory):
    app = app_for(pg_factory, admin=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        body = payload(draft(map_url="https://example.com/map", cover_ref="cover"))
        created = await client.post("/api/admin/events", json=body)
        event_id = created.json()["id"]
        patched = await client.patch(
            f"/api/admin/events/{event_id}", json={"cover_ref": None, "map_url": None}
        )
        assert patched.status_code == 200
        assert patched.json()["cover_ref"] is None and patched.json()["map_url"] is None
        for fields in [
            {"title": None},
            {"ticket_types": None},
            {"timezone": "Bad/Zone"},
            {"starts_at": "2030-01-01T00:00:00"},
            {"status": "published"},
        ]:
            assert (
                await client.patch(f"/api/admin/events/{event_id}", json=fields)
            ).status_code == 422
        assert (
            await client.get("/api/public/events", params={"from_date": "bad"})
        ).status_code == 422
