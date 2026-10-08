from datetime import timedelta
from uuid import uuid4

import pytest

from src.models.tickets import TicketStatus
from src.services.reservations.service import ReservationItem
from src.services.tickets.checkin import CheckinService, InvalidTicket
from src.services.tickets.issuer import TicketIssuer
from src.services.tickets.qr import QrTokenService
from tests.commerce_fixtures import NOW, catalog, orders, reservations


async def paid_ticket(db_session):
    event, user = await catalog(db_session, capacity=2)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    await orders(db_session).transition(pending.order_id, "confirm_payment", "payment_confirmed")
    issuer = TicketIssuer(db_session, QrTokenService("test-secret"))
    ticket = (await issuer.issue_for_paid_order(pending.order_id))[0]
    return event, ticket, QrTokenService("test-secret")


async def test_checkin_consumes_ticket_once_and_rejects_tampering(db_session):
    event, ticket, qr = await paid_ticket(db_session)
    service = CheckinService(db_session, qr)
    actor = uuid4()
    result = await service.check(ticket.qr_token, actor, NOW, event.id)
    assert result.ticket.status == TicketStatus.CHECKED_IN
    with pytest.raises(InvalidTicket, match="already"):
        await service.check(ticket.qr_token, actor, NOW + timedelta(minutes=1), event.id)
    with pytest.raises(InvalidTicket):
        await service.check(ticket.qr_token[:-1] + "x", actor, NOW, event.id)


async def test_checkin_rejects_wrong_event_and_voided_ticket(db_session):
    event, ticket, qr = await paid_ticket(db_session)
    service = CheckinService(db_session, qr)
    with pytest.raises(InvalidTicket, match="another event"):
        await service.check(ticket.qr_token, uuid4(), NOW, uuid4())
    from src.services.tickets.checkin import TicketService

    await TicketService(db_session, qr).void(ticket.id, "manual_void", uuid4())
    with pytest.raises(InvalidTicket, match="voided"):
        await service.check(ticket.qr_token, uuid4(), NOW, event.id)


async def test_checkin_requires_event_scope(db_session):
    event, ticket, qr = await paid_ticket(db_session)
    with pytest.raises(InvalidTicket, match="Event is required"):
        await CheckinService(db_session, qr).check(ticket.qr_token, uuid4(), NOW, None)
