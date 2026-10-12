from __future__ import annotations

from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import copy
from src.models.commerce import Order
from src.models.events import Event
from src.models.identity import User
from src.models.outbox import Outbox
from src.models.tickets import TicketStatus
from src.repositories.tickets import TicketRepository
from src.services.campaigns.render import RenderedMessage

TICKET_ISSUED_EVENT = "ticket.issued"


def _key(order_id: UUID) -> str:
    return f"ticket:issued:{order_id}"


async def enqueue_ticket_issued(session: AsyncSession, order_id: UUID) -> None:
    """Queues the guest's 'ticket issued' message in the caller's transaction, once per order."""
    existing = await session.scalar(
        select(Outbox.id).where(Outbox.deduplication_key == _key(order_id))
    )
    if existing is None:
        session.add(
            Outbox(
                event_type=TICKET_ISSUED_EVENT,
                deduplication_key=_key(order_id),
                payload={"order_id": str(order_id)},
            )
        )


async def build_ticket_issued(
    session: AsyncSession, order_id: UUID
) -> tuple[int, RenderedMessage] | None:
    """Who gets the message and what it says; None when there is nobody or nothing to tell."""
    order = await session.get(Order, order_id)
    if order is None:
        return None
    tickets = [
        ticket
        for ticket in await TicketRepository(session).list_for_order(order.id)
        if ticket.status == TicketStatus.ISSUED
    ]
    telegram_id = await session.scalar(select(User.telegram_id).where(User.id == order.user_id))
    event = await session.get(Event, order.event_id)
    if not tickets or not telegram_id or event is None:
        return None
    local = event.starts_at.astimezone(ZoneInfo(event.timezone))
    fields = {
        "title": event.title,
        "date": local.strftime("%d.%m.%Y"),
        "time": local.strftime("%H:%M"),
    }
    text = (
        copy.TICKET_ISSUED_ONE.format(**fields)
        if len(tickets) == 1
        else copy.TICKET_ISSUED_MANY.format(count=len(tickets), **fields)
    )
    return telegram_id, RenderedMessage(text=text, photo_path=None, photo_file_id=None, buttons=[])
