from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.dependencies import require_permission
from src.api.public.events import domain_result, event_service
from src.db.session import get_async_session
from src.models.events import EventStatus
from src.repositories.admin import AdminRepository
from src.services.admin.permissions import AdminActor, Permission
from src.services.audit.service import AuditService
from src.services.events.service import (
    CreateEventCommand,
    EventDTO,
    EventService,
    TicketTypeCommand,
    UpdateEventCommand,
)


async def require_event_admin(
    actor: Annotated[AdminActor, Depends(require_permission(Permission.MANAGE_EVENTS))],
) -> AdminActor:
    return actor


router = APIRouter(
    prefix="/api/admin/events",
    tags=["admin events"],
    dependencies=[Depends(require_event_admin)],
)


class TicketTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID | None = None
    name: str
    price_kopecks: StrictInt
    limit: StrictInt
    currency: str = "RUB"
    active: StrictBool = True

    def command(self) -> TicketTypeCommand:
        return TicketTypeCommand(**self.model_dump())


class CreateEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    description: str
    direction_id: UUID
    starts_at: datetime
    ends_at: datetime
    timezone: str
    address: str
    capacity: StrictInt
    cover_ref: str | None = None
    map_url: str | None = None
    ticket_types: list[TicketTypeInput] = Field(default_factory=list)

    def command(self) -> CreateEventCommand:
        return CreateEventCommand(
            **self.model_dump(exclude={"ticket_types"}),
            ticket_types=[t.command() for t in self.ticket_types],
        )


class UpdateEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    description: str | None = None
    direction_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = None
    address: str | None = None
    capacity: StrictInt | None = None
    cover_ref: str | None = None
    map_url: str | None = None
    ticket_types: list[TicketTypeInput] | None = None
    status: EventStatus | None = None

    def command(self) -> UpdateEventCommand:
        values = self.model_dump(exclude_unset=True, exclude={"ticket_types"})
        clear = frozenset(name for name, value in values.items() if value is None)
        if not clear <= {"cover_ref", "map_url"} or (
            "ticket_types" in self.model_fields_set and self.ticket_types is None
        ):
            raise HTTPException(422, "Required event fields cannot be null")
        return UpdateEventCommand(
            **values,
            clear_fields=clear,
            ticket_types=[t.command() for t in self.ticket_types]
            if self.ticket_types is not None
            else None,
        )


@router.post("", response_model=EventDTO, status_code=201)
async def create_event(
    command: CreateEventInput,
    events: Annotated[EventService, Depends(event_service)],
    actor: Annotated[AdminActor | None, Depends(require_event_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventDTO:
    result = await domain_result(events.create_draft(command.command()))
    if actor is not None:
        await AuditService(AdminRepository(session)).record(
            actor.id, "event.create", "event", result.id
        )
    return result


@router.post("/{event_id}/publish", response_model=EventDTO)
async def publish_event(
    event_id: UUID,
    events: Annotated[EventService, Depends(event_service)],
    actor: Annotated[AdminActor | None, Depends(require_event_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventDTO:
    result = await domain_result(events.publish(event_id))
    if actor is not None:
        await AuditService(AdminRepository(session)).record(
            actor.id, "event.publish", "event", result.id
        )
    return result


@router.patch("/{event_id}", response_model=EventDTO)
async def update_event(
    event_id: UUID,
    command: UpdateEventInput,
    events: Annotated[EventService, Depends(event_service)],
    actor: Annotated[AdminActor | None, Depends(require_event_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventDTO:
    result = await domain_result(events.update(event_id, command.command()))
    if actor is not None:
        await AuditService(AdminRepository(session)).record(
            actor.id, "event.update", "event", result.id
        )
    return result
