"""Guest Mini App, read-only slice: directions, the afisha and one evening (camelCase JSON).

Orders, tickets and polls come in a later phase; until then the Mini App sends guests to the bot.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.owner.schemas import OwnerOut, PosterOut, poster_out
from src.db.session import get_async_session
from src.models.base import utcnow
from src.models.events import Event
from src.repositories.directions import DirectionRepository
from src.repositories.events import EventRepository
from src.repositories.reservations import ReservationRepository

router = APIRouter(prefix="/api/app", tags=["app"])

Session = Annotated[AsyncSession, Depends(get_async_session)]

# The Mini App draws one of three direction icons; unknown slugs get the film one.
ICON_BY_SLUG = {"cinema": "film", "books": "book", "workshops": "workshop"}


class DirectionOut(OwnerOut):
    id: UUID
    title: str
    icon: str


class AttendeesOut(OwnerOut):
    count: int
    avatars: list[str]


class EventCardOut(OwnerOut):
    id: UUID
    title: str
    starts_at: datetime
    timezone: str
    address: str | None
    poster: PosterOut | None
    min_price_kopecks: int
    seats_left: int
    sold_out: bool
    direction_id: UUID
    accent_color: str | None
    attendees: AttendeesOut


class TicketOfferOut(OwnerOut):
    id: UUID
    name: str
    price_kopecks: int
    seats_left: int


class EventDetailOut(EventCardOut):
    description: str
    map_url: str | None
    ticket_types: list[TicketOfferOut]
    poll: None = None


def card_out(event: Event, sold: int) -> EventCardOut:
    active = [ticket for ticket in event.ticket_types if ticket.active]
    seats_left = max(event.capacity - sold, 0)
    return EventCardOut(
        id=event.id,
        title=event.title,
        starts_at=event.starts_at,
        timezone=event.timezone,
        address=event.address,
        poster=poster_out(
            event.cover_ref,
            event.cover_width,
            event.cover_height,
            event.cover_focus_x,
            event.cover_focus_y,
        ),
        min_price_kopecks=min((ticket.price_kopecks for ticket in active), default=0),
        seats_left=seats_left,
        sold_out=seats_left == 0,
        direction_id=event.direction_id,
        accent_color=event.accent_color,
        attendees=AttendeesOut(count=sold, avatars=[]),
    )


@router.get("/directions", response_model=list[DirectionOut])
async def directions(session: Session) -> list[DirectionOut]:
    active = await DirectionRepository(session).list_active()
    return [
        DirectionOut(id=d.id, title=d.name, icon=ICON_BY_SLUG.get(d.slug, "film")) for d in active
    ]


@router.get("/events", response_model=list[EventCardOut])
async def events(session: Session, direction_id: UUID | None = None) -> list[EventCardOut]:
    found = await EventRepository(session).list_public(direction_id, None, utcnow())
    sold = await ReservationRepository(session).occupied_by_events([e.id for e in found])
    return [card_out(e, sold.get(e.id, 0)) for e in found]


@router.get("/events/{event_id}", response_model=EventDetailOut)
async def event(event_id: UUID, session: Session) -> EventDetailOut:
    found = await EventRepository(session).list_public(None, None, utcnow(), event_id)
    if not found:
        raise HTTPException(404, "Event not found")
    item = found[0]
    by_ticket = await ReservationRepository(session).occupied_by_ticket(item.id)
    card = card_out(item, sum(by_ticket.values()))
    offers = [
        TicketOfferOut(
            id=ticket.id,
            name=ticket.name,
            price_kopecks=ticket.price_kopecks,
            # A ticket type never offers more than the evening has left.
            seats_left=min(max(ticket.limit - by_ticket.get(ticket.id, 0), 0), card.seats_left),
        )
        for ticket in item.ticket_types
        if ticket.active
    ]
    return EventDetailOut(
        **card.model_dump(),
        description=item.description,
        map_url=item.map_url,
        ticket_types=offers,
    )
