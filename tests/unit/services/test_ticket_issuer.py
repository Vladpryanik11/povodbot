import pytest

from src.services.reservations.service import ReservationItem
from src.services.tickets.issuer import TicketIssuer
from src.services.tickets.qr import QrTokenService
from tests.commerce_fixtures import NOW, catalog, orders, reservations


async def test_issuer_is_idempotent_and_creates_one_ticket_per_quantity(db_session):
    event, user = await catalog(db_session, capacity=5)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 2)], user.id, NOW
    )
    await orders(db_session).transition(pending.order_id, "confirm_payment", "payment_confirmed")
    issuer = TicketIssuer(db_session, QrTokenService("test-secret"))
    first = await issuer.issue_for_paid_order(pending.order_id)
    second = await issuer.issue_for_paid_order(pending.order_id)
    assert len(first) == len(second) == 2
    assert {ticket.id for ticket in first} == {ticket.id for ticket in second}
    assert {ticket.qr_token for ticket in first} == {ticket.qr_token for ticket in second}


async def test_unpaid_orders_cannot_issue_tickets(db_session):
    event, user = await catalog(db_session)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    with pytest.raises(ValueError):
        await TicketIssuer(db_session).issue_for_paid_order(pending.order_id)
