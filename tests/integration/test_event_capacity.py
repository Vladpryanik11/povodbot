import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.services.events.service import TicketTypeCommand, UpdateEventCommand
from tests.integration.test_event_publication import app_for, payload
from tests.unit.services.test_events import draft, service


async def test_capacity_public_read_only_and_validated_edit(pg_factory):
    app = app_for(pg_factory, admin=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        event = (await client.post("/api/admin/events", json=payload(draft()))).json()
        event_id = event["id"]
        await client.post(f"/api/admin/events/{event_id}/publish")
        assert (await client.get(f"/api/public/events/{event_id}")).json()["capacity"] == 20
        assert (
            await client.patch(f"/api/public/events/{event_id}", json={"capacity": 0})
        ).status_code == 405
        assert (
            await client.patch(f"/api/admin/events/{event_id}", json={"capacity": 10})
        ).status_code == 422
        assert (await client.get(f"/api/public/events/{event_id}")).json()["capacity"] == 20
        assert (
            await client.patch(f"/api/admin/events/{event_id}", json={"capacity": True})
        ).status_code == 422
        assert (
            await client.patch(f"/api/admin/events/{event_id}", json={"published_at": "2030-01-01"})
        ).status_code == 422


async def test_ticket_type_limits_share_event_ceiling(db_session):
    events = service(db_session)
    event = await events.create_draft(
        draft(
            ticket_types=[
                TicketTypeCommand(name="A", price_kopecks=100, limit=20),
                TicketTypeCommand(name="B", price_kopecks=200, limit=20),
            ]
        )
    )
    await events.publish(event.id)
    assert (await events.get_public(event.id)).capacity == 20
    with pytest.raises(ValueError):
        await events.update(event.id, UpdateEventCommand(capacity=19))
    assert (await events.get_public(event.id)).capacity == 20


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE events SET capacity = 0 WHERE id = :id",
        "UPDATE events SET ends_at = starts_at WHERE id = :id",
        "UPDATE events SET status = 'unknown' WHERE id = :id",
        "UPDATE ticket_types SET price_kopecks = -1 WHERE event_id = :id",
        'UPDATE ticket_types SET "limit" = 0 WHERE event_id = :id',
        "UPDATE ticket_types SET currency = 'USD' WHERE event_id = :id",
    ],
)
async def test_postgres_constraints_reject_invalid_catalog(db_session, sql):
    event = await service(db_session).create_draft(draft())
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(text(sql), {"id": event.id})
