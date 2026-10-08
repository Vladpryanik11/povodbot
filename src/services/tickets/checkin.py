from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tickets import Checkin, Ticket, TicketStatus
from src.repositories.tickets import TicketRepository
from src.services.tickets.issuer import TicketDTO, TicketIssuer
from src.services.tickets.qr import InvalidQrToken, QrTokenService


class InvalidTicket(ValueError):
    pass


@dataclass(frozen=True)
class CheckinResult:
    ticket: TicketDTO
    checked_at: datetime


@dataclass(frozen=True)
class TicketLookupQuery:
    ticket_id: UUID | None = None
    order_id: UUID | None = None
    event_id: UUID | None = None
    status: TicketStatus | None = None
    limit: int = 100


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(UTC)


class CheckinService:
    def __init__(self, session: AsyncSession, qr: QrTokenService | None = None) -> None:
        self.session = session
        self.qr = qr or QrTokenService()

    def _require_transaction(self) -> None:
        if not self.session.in_transaction():
            raise RuntimeError("Check-in operations require a caller-owned transaction")

    async def check(
        self,
        token: str,
        actor_id: UUID,
        now: datetime,
        event_id: UUID,
    ) -> CheckinResult:
        self._require_transaction()
        checked_at = _utc(now)
        try:
            ticket_id = self.qr.ticket_id(token)
        except InvalidQrToken as exc:
            raise InvalidTicket("Invalid QR token") from exc
        ticket = await TicketRepository(self.session).get_for_update(ticket_id)
        if not hmac.compare_digest(ticket.token_hash, self.qr.hash_token(token)):
            raise InvalidTicket("Invalid QR token")
        if ticket.event_id != event_id:
            raise InvalidTicket("Ticket belongs to another event")
        if TicketStatus(ticket.status) == TicketStatus.VOIDED:
            raise InvalidTicket("Ticket is voided")
        if TicketStatus(ticket.status) == TicketStatus.CHECKED_IN:
            raise InvalidTicket("Ticket was already checked in")
        ticket.status = TicketStatus.CHECKED_IN
        ticket.checked_in_at = checked_at
        ticket.checked_in_by = actor_id
        self.session.add(
            Checkin(
                ticket_id=ticket.id,
                actor_id=actor_id,
                event_id=ticket.event_id,
                checked_at=checked_at,
                source="qr",
            )
        )
        await self.session.flush()
        return CheckinResult(TicketIssuer(self.session, self.qr)._dto(ticket), checked_at)

    async def lookup(self, query: TicketLookupQuery) -> list[TicketDTO]:
        self._require_transaction()
        if type(query.limit) is not int or not 1 <= query.limit <= 500:
            raise ValueError("Lookup limit must be between 1 and 500")
        tickets = await TicketRepository(self.session).search(query)
        return [TicketIssuer(self.session, self.qr)._dto(ticket) for ticket in tickets]


class TicketService:
    def __init__(self, session: AsyncSession, qr: QrTokenService | None = None) -> None:
        self.session = session
        self.qr = qr or QrTokenService()

    def _require_transaction(self) -> None:
        if not self.session.in_transaction():
            raise RuntimeError("Ticket operations require a caller-owned transaction")

    async def void(self, ticket_id: UUID, reason: str, actor_id: UUID) -> TicketDTO:
        self._require_transaction()
        if not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", reason):
            raise ValueError("Void reason must be a bounded machine code")
        ticket = await TicketRepository(self.session).get_for_update(ticket_id)
        if TicketStatus(ticket.status) == TicketStatus.CHECKED_IN:
            raise InvalidTicket("Checked-in tickets cannot be voided")
        if TicketStatus(ticket.status) == TicketStatus.VOIDED:
            return TicketIssuer(self.session, self.qr)._dto(ticket)
        ticket.status = TicketStatus.VOIDED
        ticket.voided_at = _utc(datetime.now(UTC))
        ticket.void_reason = reason
        ticket.checked_in_by = actor_id
        await self.session.flush()
        return TicketIssuer(self.session, self.qr)._dto(ticket)

    async def void_for_order(self, order_id: UUID, reason: str = "payment_refunded") -> int:
        self._require_transaction()
        if not re.fullmatch(r"[a-z0-9_]{1,64}", reason):
            raise ValueError("Void reason must be a bounded machine code")
        tickets = list(
            await self.session.scalars(
                select(Ticket)
                .where(Ticket.order_id == order_id, Ticket.status == TicketStatus.ISSUED)
                .with_for_update()
            )
        )
        now = _utc(datetime.now(UTC))
        for ticket in tickets:
            ticket.status = TicketStatus.VOIDED
            ticket.voided_at = now
            ticket.void_reason = reason
        await self.session.flush()
        return len(tickets)
