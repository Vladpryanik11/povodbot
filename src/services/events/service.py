from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.models.base import utcnow
from src.models.events import Event, EventStatus, TicketType
from src.repositories.events import EventRepository
from src.repositories.reservations import ReservationRepository


@dataclass(frozen=True)
class TicketTypeCommand:
    name: str
    price_kopecks: int
    limit: int
    currency: str = "RUB"
    active: bool = True
    id: UUID | None = None


@dataclass(frozen=True)
class CreateEventCommand:
    title: str
    description: str
    direction_id: UUID
    starts_at: datetime
    ends_at: datetime
    timezone: str
    address: str
    capacity: int
    cover_ref: str | None = None
    map_url: str | None = None
    ticket_types: list[TicketTypeCommand] = field(default_factory=list)


@dataclass(frozen=True)
class UpdateEventCommand:
    title: str | None = None
    description: str | None = None
    direction_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = None
    address: str | None = None
    capacity: int | None = None
    cover_ref: str | None = None
    map_url: str | None = None
    ticket_types: list[TicketTypeCommand] | None = None
    status: EventStatus | None = None
    # Allows the HTTP PATCH boundary to distinguish omitted nullable fields from explicit null.
    clear_fields: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PublicTicketTypeDTO:
    id: UUID
    name: str
    price_kopecks: int
    currency: str
    limit: int


@dataclass(frozen=True)
class TicketTypeDTO(PublicTicketTypeDTO):
    active: bool


@dataclass(frozen=True)
class PublicEventDTO:
    id: UUID
    title: str
    description: str
    cover_ref: str | None
    direction_id: UUID
    starts_at: datetime
    ends_at: datetime
    timezone: str
    address: str
    map_url: str | None
    capacity: int
    ticket_types: tuple[PublicTicketTypeDTO, ...]


@dataclass(frozen=True)
class EventDTO:
    id: UUID
    title: str
    description: str
    cover_ref: str | None
    direction_id: UUID
    starts_at: datetime
    ends_at: datetime
    timezone: str
    address: str
    map_url: str | None
    capacity: int
    ticket_types: tuple[TicketTypeDTO, ...]
    status: EventStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


def card_fields(event: Event) -> dict[str, object]:
    return {
        name: getattr(event, name)
        for name in (
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
        )
    }


def ticket_dto(ticket: TicketType) -> TicketTypeDTO:
    return TicketTypeDTO(
        ticket.id, ticket.name, ticket.price_kopecks, ticket.currency, ticket.limit, ticket.active
    )


def event_dto(event: Event) -> EventDTO:
    return EventDTO(
        **card_fields(event),  # type: ignore[arg-type]
        ticket_types=tuple(ticket_dto(t) for t in event.ticket_types),
        status=EventStatus(event.status),
        published_at=event.published_at,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def public_dto(event: Event) -> PublicEventDTO:
    return PublicEventDTO(
        **card_fields(event),  # type: ignore[arg-type]
        ticket_types=tuple(
            PublicTicketTypeDTO(t.id, t.name, t.price_kopecks, t.currency, t.limit)
            for t in event.ticket_types
            if t.active
        ),
    )


def integer(value: int, minimum: int, maximum: int, label: str) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {label}")


def validate(command: CreateEventCommand) -> CreateEventCommand:
    for value, maximum in [
        (command.title, 256),
        (command.description, 100000),
        (command.address, 1024),
    ]:
        if not value.strip() or len(value) > maximum:
            raise ValueError("Required event text is empty or too long")
    integer(command.capacity, 1, 2147483647, "capacity")
    if not command.timezone or len(command.timezone) > 128:
        raise ValueError("Invalid IANA timezone")
    try:
        ZoneInfo(command.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Invalid IANA timezone") from exc
    for timestamp in (command.starts_at, command.ends_at):
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Event timestamps must be timezone-aware")
    if command.ends_at.astimezone(UTC) <= command.starts_at.astimezone(UTC):
        raise ValueError("Event end must follow start")
    for reference in (command.cover_ref, command.map_url):
        if reference is not None and (not reference.strip() or len(reference) > 2048):
            raise ValueError("Invalid event reference")
    if command.map_url is not None:
        url = urlsplit(command.map_url)
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            raise ValueError("Invalid map URL")
    for ticket in command.ticket_types:
        if not ticket.name.strip() or len(ticket.name) > 256:
            raise ValueError("Invalid ticket name")
        integer(ticket.price_kopecks, 0, 9223372036854775807, "price")
        integer(ticket.limit, 1, command.capacity if ticket.active else 2147483647, "ticket limit")
        if ticket.currency != "RUB" or type(ticket.active) is not bool:
            raise ValueError("Invalid ticket currency or active state")
    return command


class EventService:
    def __init__(self, repository: EventRepository):
        self.repository = repository

    async def create_draft(self, command: CreateEventCommand) -> EventDTO:
        validate(command)
        await self.repository.direction(command.direction_id)
        if any(t.id is not None for t in command.ticket_types):
            raise ValueError("New ticket types cannot specify IDs")
        event = Event(
            title=command.title,
            description=command.description,
            cover_ref=command.cover_ref,
            direction_id=command.direction_id,
            starts_at=command.starts_at.astimezone(UTC),
            ends_at=command.ends_at.astimezone(UTC),
            timezone=command.timezone,
            address=command.address,
            map_url=command.map_url,
            capacity=command.capacity,
            ticket_types=[self._new_ticket(t) for t in command.ticket_types],
        )
        return event_dto(await self.repository.create(event))

    @staticmethod
    def _new_ticket(ticket: TicketTypeCommand) -> TicketType:
        return TicketType(
            name=ticket.name,
            price_kopecks=ticket.price_kopecks,
            currency=ticket.currency,
            limit=ticket.limit,
            active=ticket.active,
        )

    async def publish(self, event_id: UUID) -> EventDTO:
        event = await self.repository.get_for_update(event_id)
        if event.status != EventStatus.DRAFT:
            raise ValueError("Only drafts can be published")
        command = self._command(event)
        validate(command)
        if command.starts_at <= utcnow():
            raise ValueError("Publication requires a future start")
        await self._publication_requirements(command)
        event.status = EventStatus.PUBLISHED
        event.published_at = utcnow()
        await self.repository.save()
        return event_dto(event)

    @staticmethod
    def _command(event: Event) -> CreateEventCommand:
        return CreateEventCommand(
            event.title,
            event.description,
            event.direction_id,
            event.starts_at,
            event.ends_at,
            event.timezone,
            event.address,
            event.capacity,
            event.cover_ref,
            event.map_url,
            [
                TicketTypeCommand(t.name, t.price_kopecks, t.limit, t.currency, t.active, t.id)
                for t in event.ticket_types
            ],
        )

    async def _publication_requirements(self, command: CreateEventCommand) -> None:
        direction = await self.repository.direction(command.direction_id)
        if not direction.active or not any(t.active for t in command.ticket_types):
            raise ValueError("Publication requires an active direction and ticket type")

    async def _capacity_edit_requirements(
        self, event_id: UUID, command: CreateEventCommand
    ) -> None:
        occupied = await ReservationRepository(self.repository.session).occupied_by_ticket(event_id)
        total_occupied = sum(occupied.values())
        if command.capacity < total_occupied:
            raise ValueError("Capacity cannot be lower than already occupied seats")
        by_id = {ticket.id: ticket for ticket in command.ticket_types if ticket.id is not None}
        for ticket_id, quantity in occupied.items():
            candidate = by_id.get(ticket_id)
            if candidate is None or not candidate.active or candidate.limit < quantity:
                raise ValueError("Ticket limit cannot be lower than already occupied seats")

    async def update(self, event_id: UUID, command: UpdateEventCommand) -> EventDTO:
        event = await self.repository.get_for_update(event_id)
        if event.status in {EventStatus.CANCELLED, EventStatus.COMPLETED}:
            raise ValueError("Terminal events cannot be edited")
        if not command.clear_fields <= {"cover_ref", "map_url"}:
            raise ValueError("Cannot clear required fields")
        status = command.status or EventStatus(event.status)
        if status != event.status:
            if event.status != EventStatus.PUBLISHED or status not in {
                EventStatus.CANCELLED,
                EventStatus.COMPLETED,
            }:
                raise ValueError("Invalid event transition; use publish for drafts")
        existing = self._command(event)
        values = {name: getattr(existing, name) for name in existing.__dataclass_fields__}
        for name in values:
            value = getattr(command, name)
            if value is not None or name in command.clear_fields:
                values[name] = value
        candidate = CreateEventCommand(**values)
        validate(candidate)
        await self.repository.direction(candidate.direction_id)
        if status == EventStatus.COMPLETED and candidate.ends_at > utcnow():
            raise ValueError("Cannot complete an event before it ends")
        if status == EventStatus.PUBLISHED:
            await self._publication_requirements(candidate)
        by_id = {t.id: t for t in event.ticket_types}
        ids = [t.id for t in candidate.ticket_types if t.id is not None]
        if len(set(ids)) != len(ids) or any(i not in by_id for i in ids):
            raise ValueError("Duplicate or foreign ticket type ID")
        await self._capacity_edit_requirements(event.id, candidate)
        # Validate the complete candidate before mutating any attached ORM state.
        for name in values:
            if name != "ticket_types":
                value = getattr(candidate, name)
                if name in {"starts_at", "ends_at"}:
                    value = value.astimezone(UTC)
                setattr(event, name, value)
        if command.ticket_types is not None:
            for ticket in event.ticket_types:
                if ticket.id not in ids:
                    ticket.active = False
            for ticket_command in command.ticket_types:
                if ticket_command.id is None:
                    event.ticket_types.append(self._new_ticket(ticket_command))
                else:
                    ticket = by_id[ticket_command.id]
                    for name in ("name", "price_kopecks", "currency", "limit", "active"):
                        setattr(ticket, name, getattr(ticket_command, name))
        event.status = status
        event.updated_at = utcnow()
        await self.repository.save()
        return event_dto(event)

    async def list_public(
        self, direction_id: UUID | None = None, from_date: date | None = None
    ) -> list[PublicEventDTO]:
        return [
            public_dto(e)
            for e in await self.repository.list_public(direction_id, from_date, utcnow())
        ]

    async def get_public(self, event_id: UUID) -> PublicEventDTO:
        events = await self.repository.list_public(None, None, utcnow(), event_id)
        if not events:
            raise LookupError("Event not found")
        return public_dto(events[0])
