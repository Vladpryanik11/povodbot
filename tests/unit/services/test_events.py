from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from src.models.events import EventStatus, TicketType
from src.repositories.directions import DirectionRepository
from src.repositories.events import EventRepository
from src.services.directions.service import DirectionService
from src.services.events.service import (
    CreateEventCommand,
    EventService,
    TicketTypeCommand,
    UpdateEventCommand,
)


def draft(**changes):
    start = datetime.now(UTC) + timedelta(days=3)
    return replace(
        CreateEventCommand(
            title="Кино вечером",
            description="Обсуждение фильма",
            direction_id=UUID(int=1),
            starts_at=start,
            ends_at=start + timedelta(hours=2),
            timezone="Europe/Moscow",
            address="Клуб Повод",
            capacity=20,
            cover_ref="posters/test",
            ticket_types=[TicketTypeCommand(name="Обычный", price_kopecks=15000, limit=20)],
        ),
        **changes,
    )


def service(session):
    return EventService(EventRepository(session))


async def test_draft_normalizes_utc_and_publishes(db_session):
    command = draft(starts_at=datetime.now(timezone(timedelta(hours=3))) + timedelta(days=3))
    event = await service(db_session).create_draft(command)
    assert event.status == EventStatus.DRAFT
    assert event.starts_at.utcoffset() == timedelta(0)
    assert event.published_at is None
    published = await service(db_session).publish(event.id)
    assert published.status == EventStatus.PUBLISHED
    assert published.published_at.utcoffset() == timedelta(0)
    public = await service(db_session).get_public(event.id)
    assert public.ticket_types[0].price_kopecks == 15000
    assert public.capacity == 20
    assert not hasattr(public, "published_at")
    assert not hasattr(public.ticket_types[0], "active")


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"description": ""},
        {"address": ""},
        {"capacity": 0},
        {"capacity": True},
        {"timezone": "Invalid/Zone"},
        {"starts_at": datetime(2030, 1, 1)},
        {"ends_at": datetime(2000, 1, 1, tzinfo=UTC)},
        {"map_url": "javascript:bad"},
        {"direction_id": uuid4()},
        {"ticket_types": [TicketTypeCommand(name="Bad", price_kopecks=-1, limit=10)]},
        {"ticket_types": [TicketTypeCommand(name="Bad", price_kopecks=1.5, limit=10)]},
        {"ticket_types": [TicketTypeCommand(name="Bad", price_kopecks=True, limit=10)]},
        {"ticket_types": [TicketTypeCommand(name="Bad", price_kopecks=0, limit=21)]},
        {"ticket_types": [TicketTypeCommand(name="Bad", price_kopecks=0, limit=0)]},
        {
            "ticket_types": [
                TicketTypeCommand(name="Bad", price_kopecks=0, limit=10, currency="USD")
            ]
        },
    ],
)
async def test_invalid_draft_rejected(db_session, changes):
    with pytest.raises((ValueError, LookupError)):
        await service(db_session).create_draft(draft(**changes))


@pytest.mark.parametrize(
    "tickets", [[], [TicketTypeCommand(name="Hidden", price_kopecks=0, limit=10, active=False)]]
)
async def test_publish_needs_active_tickets(db_session, tickets):
    event = await service(db_session).create_draft(draft(ticket_types=tickets))
    with pytest.raises(ValueError):
        await service(db_session).publish(event.id)


async def test_inactive_direction_blocks_publication_and_public_read(db_session):
    events = service(db_session)
    event = await events.create_draft(draft())
    directions = DirectionService(DirectionRepository(db_session))
    await directions.set_active(UUID(int=1), False)
    with pytest.raises(ValueError):
        await events.publish(event.id)
    await directions.set_active(UUID(int=1), True)
    await events.publish(event.id)
    await directions.set_active(UUID(int=1), False)
    assert await events.list_public(None, None) == []
    with pytest.raises(LookupError):
        await events.get_public(event.id)


async def test_lifecycle_and_terminal_edits(db_session):
    events = service(db_session)
    event = await events.create_draft(draft())
    with pytest.raises(ValueError):
        await events.update(event.id, UpdateEventCommand(status=EventStatus.PUBLISHED))
    await events.publish(event.id)
    with pytest.raises(ValueError):
        await events.update(event.id, UpdateEventCommand(status=EventStatus.COMPLETED))
    cancelled = await events.update(event.id, UpdateEventCommand(status=EventStatus.CANCELLED))
    assert cancelled.status == EventStatus.CANCELLED
    for command in [
        UpdateEventCommand(status=EventStatus.DRAFT),
        UpdateEventCommand(title="Changed"),
    ]:
        with pytest.raises(ValueError):
            await events.update(event.id, command)
    assert await events.list_public(None, None) == []


async def test_completion_after_end_and_past_publish_rejected(db_session):
    events = service(db_session)
    event = await events.create_draft(draft())
    await events.publish(event.id)
    start = datetime.now(UTC) - timedelta(hours=3)
    await events.update(
        event.id, UpdateEventCommand(starts_at=start, ends_at=start + timedelta(hours=2))
    )
    result = await events.update(event.id, UpdateEventCommand(status=EventStatus.COMPLETED))
    assert result.status == EventStatus.COMPLETED
    past = await events.create_draft(draft(starts_at=start, ends_at=start + timedelta(hours=2)))
    with pytest.raises(ValueError):
        await events.publish(past.id)


async def test_ticket_updates_keep_ids_and_old_dto_price(db_session):
    events = service(db_session)
    event = await events.create_draft(draft())
    ticket = event.ticket_types[0]
    updated = await events.update(
        event.id,
        UpdateEventCommand(
            ticket_types=[
                TicketTypeCommand(id=ticket.id, name=ticket.name, price_kopecks=20000, limit=20)
            ]
        ),
    )
    assert updated.ticket_types[0].id == ticket.id
    assert updated.ticket_types[0].price_kopecks == 20000
    assert ticket.price_kopecks == 15000
    with pytest.raises(ValueError):
        await events.update(
            event.id,
            UpdateEventCommand(
                ticket_types=[
                    TicketTypeCommand(id=uuid4(), name="Foreign", price_kopecks=100, limit=20)
                ]
            ),
        )
    await events.update(event.id, UpdateEventCommand(ticket_types=[]))
    persisted = await db_session.get(TicketType, ticket.id)
    assert persisted is not None and not persisted.active
    assert len(list(await db_session.scalars(select(TicketType)))) == 1


async def test_public_filters_direction_local_date_and_drafts(db_session):
    events = service(db_session)
    start = datetime(2030, 1, 1, 22, tzinfo=UTC)
    event = await events.create_draft(draft(starts_at=start, ends_at=start + timedelta(hours=2)))
    await events.create_draft(draft())
    await events.publish(event.id)
    assert [e.id for e in await events.list_public(UUID(int=1), datetime(2030, 1, 2).date())] == [
        event.id
    ]
    assert await events.list_public(UUID(int=2), None) == []
    assert await events.list_public(None, datetime(2030, 1, 3).date()) == []


async def test_dates_compare_actual_instants_during_dst_fold(db_session):
    zone = ZoneInfo("America/New_York")
    # 01:45 EDT = 05:45 UTC; 01:15 EST = 06:15 UTC: a valid 30-minute event.
    event = await service(db_session).create_draft(
        draft(
            starts_at=datetime(2030, 11, 3, 1, 45, tzinfo=zone, fold=0),
            ends_at=datetime(2030, 11, 3, 1, 15, tzinfo=zone, fold=1),
            timezone="America/New_York",
        )
    )
    assert event.starts_at == datetime(2030, 11, 3, 5, 45, tzinfo=UTC)
    assert event.ends_at == datetime(2030, 11, 3, 6, 15, tzinfo=UTC)


async def test_deactivated_types_do_not_block_later_capacity_edit(db_session):
    events = service(db_session)
    event = await events.create_draft(draft())
    await events.publish(event.id)
    await events.update(
        event.id,
        UpdateEventCommand(
            capacity=10, ticket_types=[TicketTypeCommand(name="New", price_kopecks=100, limit=10)]
        ),
    )
    updated = await events.update(event.id, UpdateEventCommand(title="New title"))
    assert updated.title == "New title"
    public = await events.get_public(event.id)
    assert len(public.ticket_types) == 1
    assert public.ticket_types[0].name == "New"
    assert len(updated.ticket_types) == 2


async def test_rejected_edit_does_not_mutate_price_or_event(db_session):
    events = service(db_session)
    event = await events.create_draft(draft())
    await events.publish(event.id)
    ticket = event.ticket_types[0]
    with pytest.raises(ValueError):
        await events.update(
            event.id,
            UpdateEventCommand(
                title="Should not persist",
                ticket_types=[
                    TicketTypeCommand(id=ticket.id, name=ticket.name, price_kopecks=100, limit=20),
                    TicketTypeCommand(id=ticket.id, name=ticket.name, price_kopecks=200, limit=20),
                ],
            ),
        )
    await db_session.flush()
    public = await events.get_public(event.id)
    assert public.title == "Кино вечером"
    assert public.ticket_types[0].price_kopecks == 15000
    with pytest.raises(ValueError):
        await events.publish(event.id)
