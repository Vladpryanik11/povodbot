import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.models.base import utcnow
from src.models.events import Event, EventStatus, TicketType
from src.repositories.events import EventRepository
from src.repositories.orders import OrderRepository
from src.repositories.reservations import ReservationRepository

ACCENT_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
CLEARABLE_FIELDS = frozenset({"cover_ref", "map_url", "address", "accent_color"})


class EventFieldError(ValueError):
    """A rule violation tied to one form field, worded for the club owner."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class EventConflict(Exception):
    """The event cannot be changed this way right now; the owner has to refresh or step back."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


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
    address: str | None
    capacity: int
    cover_ref: str | None = None
    map_url: str | None = None
    ticket_types: list[TicketTypeCommand] = field(default_factory=list)
    accent_color: str | None = None


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
    accent_color: str | None = None
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
    address: str | None
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
    address: str | None
    map_url: str | None
    capacity: int
    ticket_types: tuple[TicketTypeDTO, ...]
    status: EventStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    accent_color: str | None
    cover_focus_x: float
    cover_focus_y: float
    cover_width: int | None
    cover_height: int | None


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
        accent_color=event.accent_color,
        cover_focus_x=event.cover_focus_x,
        cover_focus_y=event.cover_focus_y,
        cover_width=event.cover_width,
        cover_height=event.cover_height,
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


def touch(event: Event) -> None:
    # updated_at is also the edit version, so it must change on every edit even on a coarse clock.
    event.updated_at = max(utcnow(), event.updated_at + timedelta(microseconds=1))


def valid_integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def focus_point(x: float, y: float) -> tuple[float, float]:
    for value in (x, y):
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
            raise EventFieldError("focus", "Точка фокуса вне фото")
    # The column keeps three decimals; round here so the returned DTO matches what is stored.
    return round(float(x), 3), round(float(y), 3)


def validate(command: CreateEventCommand) -> CreateEventCommand:
    if not command.title.strip():
        raise EventFieldError("title", "Назови вечер")
    if len(command.title) > 256:
        raise EventFieldError("title", "Название длиннее 256 символов")
    if not command.description.strip():
        raise EventFieldError("description", "Добавь пару слов о вечере")
    if len(command.description) > 100000:
        raise EventFieldError("description", "Описание слишком длинное")
    if command.address is not None and (not command.address.strip() or len(command.address) > 1024):
        raise EventFieldError("address", "Укажи адрес или выбери «Место уточняется»")
    if not valid_integer(command.capacity, 1, 2147483647):
        raise EventFieldError("capacity", "Сколько мест?")
    if not command.timezone or len(command.timezone) > 128:
        raise ValueError("Invalid IANA timezone")
    try:
        ZoneInfo(command.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Invalid IANA timezone") from exc
    for name, timestamp in (("starts_at", command.starts_at), ("ends_at", command.ends_at)):
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise EventFieldError(name, "Укажи дату и время")
    if command.ends_at.astimezone(UTC) <= command.starts_at.astimezone(UTC):
        raise EventFieldError("ends_at", "Конец должен быть позже начала")
    if command.cover_ref is not None and (
        not command.cover_ref.strip() or len(command.cover_ref) > 2048
    ):
        raise ValueError("Invalid event reference")
    if command.map_url is not None:
        url = urlsplit(command.map_url)
        if (
            not command.map_url.strip()
            or len(command.map_url) > 2048
            or url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username
            or url.password
        ):
            raise EventFieldError("map_url", "Ссылка на карту не открывается")
    if command.accent_color is not None and not ACCENT_COLOR.fullmatch(command.accent_color):
        raise EventFieldError("accent_color", "Цвет в формате #RRGGBB")
    for ticket in command.ticket_types:
        if not ticket.name.strip() or len(ticket.name) > 256:
            raise EventFieldError("ticket_types", "У билета нет названия")
        if not valid_integer(ticket.price_kopecks, 0, 9223372036854775807):
            raise EventFieldError("ticket_types", "Проверь цену билета")
        if not valid_integer(ticket.limit, 1, command.capacity if ticket.active else 2147483647):
            raise EventFieldError("ticket_types", "Проверь количество билетов")
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
            accent_color=command.accent_color,
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

    async def get(self, event_id: UUID) -> EventDTO:
        return event_dto(await self.repository.get(event_id))

    async def publish(self, event_id: UUID) -> EventDTO:
        event = await self.repository.get_for_update(event_id)
        if event.status != EventStatus.DRAFT:
            raise ValueError("Only drafts can be published")
        command = self._command(event)
        validate(command)
        if command.starts_at <= utcnow():
            raise EventFieldError("starts_at", "Вечер уже начался — поменяй дату")
        await self._publication_requirements(command)
        event.status = EventStatus.PUBLISHED
        event.published_at = utcnow()
        touch(event)
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
            event.accent_color,
        )

    async def _publication_requirements(self, command: CreateEventCommand) -> None:
        direction = await self.repository.direction(command.direction_id)
        if not direction.active:
            raise ValueError("Publication requires an active direction")
        if not any(t.active for t in command.ticket_types):
            raise EventFieldError("ticket_types", "Добавь хотя бы один билет")
        if command.cover_ref is None:
            raise EventFieldError("poster", "Без фото опубликовать нельзя")

    async def _capacity_edit_requirements(
        self, event_id: UUID, command: CreateEventCommand
    ) -> None:
        occupied = await ReservationRepository(self.repository.session).occupied_by_ticket(event_id)
        total_occupied = sum(occupied.values())
        if command.capacity < total_occupied:
            raise EventFieldError("capacity", "Уже занято больше мест")
        by_id = {ticket.id: ticket for ticket in command.ticket_types if ticket.id is not None}
        for ticket_id, quantity in occupied.items():
            candidate = by_id.get(ticket_id)
            if candidate is None or not candidate.active or candidate.limit < quantity:
                raise EventFieldError("ticket_types", "Уже продано больше билетов этого типа")

    @staticmethod
    def _require_editable(event: Event) -> None:
        if event.status in {EventStatus.CANCELLED, EventStatus.COMPLETED}:
            raise ValueError("Terminal events cannot be edited")

    async def update(
        self,
        event_id: UUID,
        command: UpdateEventCommand,
        *,
        expected_updated_at: datetime | None = None,
    ) -> EventDTO:
        event = await self.repository.get_for_update(event_id)
        if expected_updated_at is not None and event.updated_at != expected_updated_at:
            raise EventConflict("Событие уже изменили — обнови")
        self._require_editable(event)
        if not command.clear_fields <= CLEARABLE_FIELDS:
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
        touch(event)
        await self.repository.save()
        return event_dto(event)

    async def unpublish(self, event_id: UUID) -> EventDTO:
        event = await self.repository.get_for_update(event_id)
        if event.status != EventStatus.PUBLISHED:
            raise ValueError("Only published events can be unpublished")
        # Any order counts, expired ones included: a late payment can still arrive for them.
        if await OrderRepository(self.repository.session).exists_for_event(event.id):
            raise EventConflict("Уже есть брони — отменить можно будет через возвраты")
        event.status = EventStatus.DRAFT
        event.published_at = None
        touch(event)
        await self.repository.save()
        return event_dto(event)

    async def set_poster(
        self, event_id: UUID, key: str, width: int, height: int, focus_x: float, focus_y: float
    ) -> EventDTO:
        focus = focus_point(focus_x, focus_y)
        if not key.strip() or len(key) > 2048:
            raise ValueError("Invalid event reference")
        if not valid_integer(width, 1, 2147483647) or not valid_integer(height, 1, 2147483647):
            raise ValueError("Invalid poster size")
        event = await self.repository.get_for_update(event_id)
        self._require_editable(event)
        event.cover_ref = key
        event.cover_width = width
        event.cover_height = height
        event.cover_focus_x, event.cover_focus_y = focus
        touch(event)
        await self.repository.save()
        return event_dto(event)

    async def set_poster_focus(self, event_id: UUID, focus_x: float, focus_y: float) -> EventDTO:
        focus = focus_point(focus_x, focus_y)
        event = await self.repository.get_for_update(event_id)
        self._require_editable(event)
        event.cover_focus_x, event.cover_focus_y = focus
        touch(event)
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
