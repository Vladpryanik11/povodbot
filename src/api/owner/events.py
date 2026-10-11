"""Owner Mini App events: list, form, publish and unpublish."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Query
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.owner.auth import require_owner_events
from src.api.owner.errors import OwnerApiError
from src.api.owner.router import router
from src.api.owner.schemas import (
    OwnerEventInput,
    OwnerEventListItem,
    OwnerEventOut,
    OwnerEventPatch,
    owner_event_out,
    owner_list_item,
)
from src.api.public.events import event_service
from src.db.session import get_async_session
from src.models.base import utcnow
from src.repositories.admin import AdminRepository
from src.repositories.events import EventRepository
from src.repositories.reservations import ReservationRepository
from src.services.admin.permissions import AdminActor
from src.services.audit.service import AuditService
from src.services.events.service import EventConflict, EventFieldError, EventService

EVENT_NOT_FOUND = "Вечер не найден"
REJECTED = "Так изменить вечер нельзя"

Service = Annotated[EventService, Depends(event_service)]
Actor = Annotated[AdminActor, Depends(require_owner_events)]
Session = Annotated[AsyncSession, Depends(get_async_session)]


@contextmanager
def owner_errors() -> Iterator[None]:
    """Event service failures become the Mini App's error bodies."""
    try:
        yield
    except EventFieldError as error:
        # The service names form fields in snake_case; on the wire they are camelCase.
        field = to_camel(error.field)
        raise OwnerApiError(422, {"field": field, "message": error.message}) from error
    except EventConflict as error:
        raise OwnerApiError(409, {"message": error.message}) from error
    except LookupError as error:
        raise OwnerApiError(404, {"message": EVENT_NOT_FOUND}) from error
    except ValueError as error:
        raise OwnerApiError(422, {"message": REJECTED}) from error


async def audit(
    session: AsyncSession,
    actor: AdminActor,
    action: str,
    event_id: UUID,
    metadata: dict[str, object] | None = None,
) -> None:
    await AuditService(AdminRepository(session)).record(
        actor.id, f"owner.event.{action}", "event", event_id, metadata
    )


@router.get("/events", response_model=list[OwnerEventListItem])
async def list_events(
    _: Actor,
    session: Session,
    which: Annotated[Literal["all", "draft", "past"], Query(alias="filter")] = "all",
) -> list[OwnerEventListItem]:
    events = await EventRepository(session).list_for_owner(which, utcnow())
    sold = await ReservationRepository(session).occupied_by_events([event.id for event in events])
    return [owner_list_item(event, sold.get(event.id, 0)) for event in events]


@router.get("/events/{event_id}", response_model=OwnerEventOut)
async def get_event(event_id: UUID, _: Actor, events: Service, session: Session) -> OwnerEventOut:
    with owner_errors():
        dto = await events.get(event_id)
    return await owner_event_out(session, dto)


@router.post("/events", response_model=OwnerEventOut, status_code=201)
async def create_event(
    body: OwnerEventInput, actor: Actor, events: Service, session: Session
) -> OwnerEventOut:
    with owner_errors():
        dto = await events.create_draft(body.command())
    await audit(session, actor, "create", dto.id)
    return await owner_event_out(session, dto)


@router.patch("/events/{event_id}", response_model=OwnerEventOut)
async def update_event(
    event_id: UUID, body: OwnerEventPatch, actor: Actor, events: Service, session: Session
) -> OwnerEventOut:
    with owner_errors():
        expected = body.expected_updated_at()
        dto = await events.update(event_id, body.command(), expected_updated_at=expected)
    await audit(session, actor, "update", dto.id)
    return await owner_event_out(session, dto)


@router.post("/events/{event_id}/publish", response_model=OwnerEventOut)
async def publish_event(
    event_id: UUID, actor: Actor, events: Service, session: Session
) -> OwnerEventOut:
    with owner_errors():
        dto = await events.publish(event_id)
    await audit(session, actor, "publish", dto.id)
    return await owner_event_out(session, dto)


@router.post("/events/{event_id}/unpublish", response_model=OwnerEventOut)
async def unpublish_event(
    event_id: UUID, actor: Actor, events: Service, session: Session
) -> OwnerEventOut:
    with owner_errors():
        dto = await events.unpublish(event_id)
    await audit(session, actor, "unpublish", dto.id)
    return await owner_event_out(session, dto)
