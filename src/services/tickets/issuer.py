from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commerce import OrderStatus
from src.models.tickets import Ticket, TicketStatus
from src.repositories.orders import OrderRepository
from src.repositories.tickets import TicketRepository
from src.services.tickets.qr import QrTokenService


@dataclass(frozen=True)
class TicketDTO:
    id: UUID
    order_id: UUID
    event_id: UUID
    ticket_type_id: UUID
    label: str
    position: int
    price_kopecks: int
    currency: str
    status: TicketStatus
    qr_token: str
    issued_at: datetime
    checked_in_at: datetime | None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(UTC)


class TicketIssuer:
    def __init__(self, session: AsyncSession, qr: QrTokenService | None = None) -> None:
        self.session = session
        self.qr = qr or QrTokenService()

    def _require_transaction(self) -> None:
        if not self.session.in_transaction():
            raise RuntimeError("Ticket operations require a caller-owned transaction")

    def _dto(self, ticket: Ticket) -> TicketDTO:
        return TicketDTO(
            id=ticket.id,
            order_id=ticket.order_id,
            event_id=ticket.event_id,
            ticket_type_id=ticket.ticket_type_id,
            label=ticket.label,
            position=ticket.position,
            price_kopecks=ticket.price_kopecks,
            currency=ticket.currency,
            status=TicketStatus(ticket.status),
            qr_token=self.qr.generate(ticket.id),
            issued_at=ticket.issued_at,
            checked_in_at=ticket.checked_in_at,
        )

    async def issue_for_paid_order(self, order_id: UUID) -> list[TicketDTO]:
        self._require_transaction()
        order = await OrderRepository(self.session).get_for_update(order_id)
        if OrderStatus(order.status) != OrderStatus.PAID:
            raise ValueError("Tickets can be issued only for a paid order")
        existing = await TicketRepository(self.session).list_for_order(order.id)
        if existing:
            return [self._dto(ticket) for ticket in existing]

        issued_at = _utc(datetime.now(UTC))
        created: list[Ticket] = []
        for item in order.items:
            for position in range(1, item.quantity + 1):
                ticket_id = uuid4()
                token = self.qr.generate(ticket_id)
                created.append(
                    Ticket(
                        id=ticket_id,
                        order_id=order.id,
                        event_id=order.event_id,
                        ticket_type_id=item.ticket_type_id,
                        order_item_id=item.id,
                        position=position,
                        label=item.ticket_label,
                        price_kopecks=item.price_kopecks,
                        currency=item.currency,
                        token_hash=self.qr.hash_token(token),
                        status=TicketStatus.ISSUED,
                        issued_at=issued_at,
                    )
                )
        self.session.add_all(created)
        await self.session.flush()
        return [self._dto(ticket) for ticket in created]
