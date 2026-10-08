from collections.abc import Awaitable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.repositories.events import EventRepository
from src.services.events.service import EventService, PublicEventDTO

router = APIRouter(prefix="/api/public/events", tags=["events"])


def event_service(session: Annotated[AsyncSession, Depends(get_async_session)]) -> EventService:
    return EventService(EventRepository(session))


async def domain_result[Result](operation: Awaitable[Result]) -> Result:
    try:
        return await operation
    except LookupError as exc:
        raise HTTPException(404, "Event or direction not found") from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid event data or lifecycle transition") from exc


@router.get("", response_model=list[PublicEventDTO])
async def list_events(
    events: Annotated[EventService, Depends(event_service)],
    direction_id: UUID | None = None,
    from_date: date | None = None,
) -> list[PublicEventDTO]:
    return await domain_result(events.list_public(direction_id, from_date))


@router.get("/{event_id}", response_model=PublicEventDTO)
async def get_event(
    event_id: UUID, events: Annotated[EventService, Depends(event_service)]
) -> PublicEventDTO:
    return await domain_result(events.get_public(event_id))
