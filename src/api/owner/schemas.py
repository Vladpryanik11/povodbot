"""Owner API shapes: camelCase JSON for the Mini App, built from the event service DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.events import Event, EventStatus
from src.repositories.reservations import ReservationRepository
from src.services.events.service import (
    CreateEventCommand,
    EventDTO,
    EventFieldError,
    TicketTypeCommand,
    UpdateEventCommand,
)
from src.services.media.posters import poster_url

POSTER_KEY_PREFIX = "posters/"
CLEARABLE_FIELDS = frozenset({"address", "accent_color", "map_url"})
STALE_FORM = "Обнови форму и попробуй ещё раз"


class OwnerOut(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class OwnerIn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")


class PosterOut(OwnerOut):
    url: str
    focus_x: float
    focus_y: float
    width: int
    height: int


class OwnerTicketTypeOut(OwnerOut):
    id: UUID
    name: str
    price_kopecks: int
    currency: str
    limit: int
    active: bool


class OwnerEventListItem(OwnerOut):
    id: UUID
    title: str
    starts_at: datetime
    status: EventStatus
    capacity: int
    sold: int
    poster: PosterOut | None


class OwnerEventOut(OwnerOut):
    id: UUID
    title: str
    description: str
    direction_id: UUID
    starts_at: datetime
    ends_at: datetime
    timezone: str
    address: str | None
    map_url: str | None
    capacity: int
    ticket_types: list[OwnerTicketTypeOut]
    status: EventStatus
    published_at: datetime | None
    created_at: datetime
    # Opaque edit version: the exact ISO 8601 string, never rounded; the form sends it back as is.
    updated_at: str
    accent_color: str | None
    poster: PosterOut | None
    sold: int


def poster_out(
    cover_ref: str | None,
    width: int | None,
    height: int | None,
    focus_x: float,
    focus_y: float,
) -> PosterOut | None:
    if not cover_ref:
        return None
    if cover_ref.startswith(POSTER_KEY_PREFIX):
        return PosterOut(
            url=poster_url(cover_ref),
            focus_x=focus_x,
            focus_y=focus_y,
            width=width or 0,
            height=height or 0,
        )
    # Older events keep a plain image URL in cover_ref and have no stored size.
    return PosterOut(url=cover_ref, focus_x=focus_x, focus_y=focus_y, width=0, height=0)


def owner_list_item(event: Event, sold: int) -> OwnerEventListItem:
    return OwnerEventListItem(
        id=event.id,
        title=event.title,
        starts_at=event.starts_at,
        status=EventStatus(event.status),
        capacity=event.capacity,
        sold=sold,
        poster=poster_out(
            event.cover_ref,
            event.cover_width,
            event.cover_height,
            event.cover_focus_x,
            event.cover_focus_y,
        ),
    )


async def owner_event_out(session: AsyncSession, dto: EventDTO) -> OwnerEventOut:
    sold = (await ReservationRepository(session).occupied_by_events([dto.id])).get(dto.id, 0)
    return OwnerEventOut(
        id=dto.id,
        title=dto.title,
        description=dto.description,
        direction_id=dto.direction_id,
        starts_at=dto.starts_at,
        ends_at=dto.ends_at,
        timezone=dto.timezone,
        address=dto.address,
        map_url=dto.map_url,
        capacity=dto.capacity,
        ticket_types=[
            OwnerTicketTypeOut(
                id=ticket.id,
                name=ticket.name,
                price_kopecks=ticket.price_kopecks,
                currency=ticket.currency,
                limit=ticket.limit,
                active=ticket.active,
            )
            for ticket in dto.ticket_types
        ],
        status=dto.status,
        published_at=dto.published_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at.isoformat(),
        accent_color=dto.accent_color,
        poster=poster_out(
            dto.cover_ref, dto.cover_width, dto.cover_height, dto.cover_focus_x, dto.cover_focus_y
        ),
        sold=sold,
    )


class OwnerTicketTypeInput(OwnerIn):
    id: UUID | None = None
    name: str
    price_kopecks: StrictInt
    limit: StrictInt
    currency: str = "RUB"
    active: StrictBool = True

    def command(self) -> TicketTypeCommand:
        return TicketTypeCommand(**self.model_dump())


class OwnerEventInput(OwnerIn):
    title: str
    description: str
    direction_id: UUID
    starts_at: datetime
    ends_at: datetime
    timezone: str
    address: str | None = None
    capacity: StrictInt
    map_url: str | None = None
    accent_color: str | None = None
    ticket_types: list[OwnerTicketTypeInput] = []

    def command(self) -> CreateEventCommand:
        return CreateEventCommand(
            **self.model_dump(exclude={"ticket_types"}),
            ticket_types=[ticket.command() for ticket in self.ticket_types],
        )


class OwnerEventPatch(OwnerIn):
    updated_at: str
    title: str | None = None
    description: str | None = None
    direction_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = None
    address: str | None = None
    capacity: StrictInt | None = None
    map_url: str | None = None
    accent_color: str | None = None
    ticket_types: list[OwnerTicketTypeInput] | None = None

    def expected_updated_at(self) -> datetime:
        try:
            version = datetime.fromisoformat(self.updated_at)
        except ValueError:
            raise EventFieldError("updatedAt", STALE_FORM) from None
        if version.tzinfo is None:
            raise EventFieldError("updatedAt", STALE_FORM)
        return version

    def command(self) -> UpdateEventCommand:
        values = self.model_dump(exclude_unset=True, exclude={"ticket_types", "updated_at"})
        clear = frozenset(name for name, value in values.items() if value is None)
        if not clear <= CLEARABLE_FIELDS:
            raise EventFieldError(sorted(clear - CLEARABLE_FIELDS)[0], "Заполни это поле")
        if "ticket_types" in self.model_fields_set and self.ticket_types is None:
            raise EventFieldError("ticket_types", "Заполни это поле")
        return UpdateEventCommand(
            **values,
            clear_fields=clear,
            ticket_types=[ticket.command() for ticket in self.ticket_types]
            if self.ticket_types is not None
            else None,
        )
