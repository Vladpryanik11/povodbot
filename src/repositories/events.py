from datetime import date, datetime
from typing import Literal, overload
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.directions import Direction
from src.models.events import Event, EventStatus, TicketType

OWNER_LIVE_STATUSES = [EventStatus.DRAFT, EventStatus.PUBLISHED]


class EventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def direction(self, direction_id: UUID) -> Direction:
        direction = await self.session.scalar(
            select(Direction)
            .where(Direction.id == direction_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if direction is None:
            raise LookupError("Direction not found")
        return direction

    async def create(self, event: Event) -> Event:
        self.session.add(event)
        await self.session.flush()
        return event

    @overload
    async def get_for_update(
        self, event_id: UUID, *, skip_locked: Literal[False] = False
    ) -> Event: ...

    @overload
    async def get_for_update(
        self, event_id: UUID, *, skip_locked: Literal[True]
    ) -> Event | None: ...

    async def get_for_update(self, event_id: UUID, *, skip_locked: bool = False) -> Event | None:
        event = await self.session.scalar(
            select(Event)
            .where(Event.id == event_id)
            .options(selectinload(Event.ticket_types))
            .with_for_update(skip_locked=skip_locked)
            .execution_options(populate_existing=True)
        )
        if event is None and not skip_locked:
            raise LookupError("Event not found")
        return event

    async def get(self, event_id: UUID) -> Event:
        event = await self.session.scalar(
            select(Event)
            .where(Event.id == event_id)
            .options(selectinload(Event.ticket_types))
            .execution_options(populate_existing=True)
        )
        if event is None:
            raise LookupError("Event not found")
        return event

    async def save(self) -> None:
        await self.session.flush()

    async def list_for_owner(
        self, filter: Literal["all", "draft", "past"], now: datetime
    ) -> list[Event]:
        query = select(Event).execution_options(populate_existing=True)
        if filter == "past":
            query = query.where(Event.status != EventStatus.CANCELLED, Event.ends_at < now)
            query = query.order_by(Event.starts_at.desc(), Event.id)
        else:
            statuses = [EventStatus.DRAFT] if filter == "draft" else OWNER_LIVE_STATUSES
            query = query.where(Event.status.in_(statuses), Event.ends_at >= now)
            query = query.order_by(Event.starts_at, Event.id)
        return list(await self.session.scalars(query))

    async def list_public(
        self,
        direction_id: UUID | None,
        from_date: date | None,
        now: datetime,
        event_id: UUID | None = None,
    ) -> list[Event]:
        query = (
            select(Event)
            .join(Direction)
            .options(selectinload(Event.ticket_types))
            .where(
                Event.status == EventStatus.PUBLISHED,
                Direction.active.is_(True),
                Event.starts_at > now,
                Event.ticket_types.any(TicketType.active.is_(True)),
            )
            .order_by(Event.starts_at, Event.id)
            .execution_options(populate_existing=True)
        )
        if direction_id is not None:
            query = query.where(Event.direction_id == direction_id)
        if from_date is not None:
            query = query.where(
                func.date(func.timezone(Event.timezone, Event.starts_at)) >= from_date
            )
        if event_id is not None:
            query = query.where(Event.id == event_id)
        return list(await self.session.scalars(query))
