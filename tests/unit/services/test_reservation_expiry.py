from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from src.models.commerce import Order, OrderEvent, OrderTransition, Reservation
from src.services.orders.service import InvalidOrderTransition
from src.services.reservations.service import CapacityExceeded, ReservationItem
from src.workers.reservation_expiry import run_once
from tests.commerce_fixtures import NOW, FixedClock, catalog, orders, reservations


async def test_lazy_expiry_frees_capacity_at_inclusive_deadline(db_session):
    event, user = await catalog(db_session, 1)
    cart = [ReservationItem(event.ticket_types[0].id, 1)]
    first = await reservations(db_session).reserve(event.id, cart, user.id, NOW)
    with pytest.raises(CapacityExceeded):
        await reservations(db_session).reserve(
            event.id, cart, user.id, NOW + timedelta(seconds=599)
        )
    second = await reservations(db_session).reserve(
        event.id, cart, user.id, NOW + timedelta(seconds=600)
    )
    assert second.order_id != first.order_id
    assert (await db_session.get(Order, first.order_id)).status == "expired"
    assert (await db_session.get(Reservation, first.reservation_id)).status == "expired"
    audit = (
        await db_session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == first.order_id)
            .order_by(OrderEvent.sequence)
        )
    ).all()
    assert [a.next_status for a in audit] == ["pending_payment", "expired"]
    assert audit[-1].created_at == NOW + timedelta(seconds=600)


async def test_expiry_is_bounded_and_idempotent(db_session):
    event, user = await catalog(db_session, 3)
    cart = [ReservationItem(event.ticket_types[0].id, 1)]
    for _ in range(3):
        await reservations(db_session).reserve(event.id, cart, user.id, NOW)
    checkout = reservations(db_session)
    assert await checkout.release_expired(NOW + timedelta(seconds=599), 10) == 0
    assert await checkout.release_expired(NOW + timedelta(seconds=600), 2) == 2
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Reservation).where(Reservation.status == "active")
        )
        == 1
    )
    assert await checkout.release_expired(NOW + timedelta(seconds=600), 2) == 1
    assert await checkout.release_expired(NOW + timedelta(seconds=600), 2) == 0
    assert await db_session.scalar(select(func.count()).select_from(OrderEvent)) == 6


@pytest.mark.parametrize(
    "seconds,action", [(599, OrderTransition.EXPIRE), (600, OrderTransition.CONFIRM_PAYMENT)]
)
async def test_transitions_enforce_reservation_deadline_without_partial_mutation(
    db_session, seconds, action
):
    event, user = await catalog(db_session)
    result = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    with pytest.raises(InvalidOrderTransition):
        await orders(db_session, NOW + timedelta(seconds=seconds)).transition(
            result.order_id, action, "deadline_checked"
        )
    assert (await db_session.get(Order, result.order_id)).status == "pending_payment"
    assert (await db_session.get(Reservation, result.reservation_id)).status == "active"
    assert await db_session.scalar(select(func.count()).select_from(OrderEvent)) == 1


async def test_late_confirmation_requires_reconciliation_and_never_reclaims_seat(db_session):
    event, user = await catalog(db_session, 1)
    cart = [ReservationItem(event.ticket_types[0].id, 1)]
    result = await reservations(db_session).reserve(event.id, cart, user.id, NOW)
    await reservations(db_session).reserve(event.id, cart, user.id, NOW + timedelta(seconds=600))
    with pytest.raises(InvalidOrderTransition):
        await orders(db_session, NOW + timedelta(seconds=601)).transition(
            result.order_id, OrderTransition.CONFIRM_PAYMENT, "provider_confirmed"
        )
    reconciled = await orders(db_session).transition(
        result.order_id, OrderTransition.REQUIRE_RECONCILIATION, "late_confirmation"
    )
    assert reconciled.status == "reconciliation_required"
    assert (await db_session.get(Reservation, result.reservation_id)).status == "expired"


async def test_worker_commits_expiry_and_skips_checkout_event_lock(pg_factory):
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session, 1)
        result = await reservations(session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
        )
    clock = FixedClock(NOW + timedelta(seconds=600))
    async with pg_factory() as session, session.begin():
        await session.execute(
            text("SELECT id FROM events WHERE id = :id FOR UPDATE"), {"id": event.id}
        )
        assert await run_once(pg_factory, clock, limit=10) == 0
    assert await run_once(pg_factory, clock, limit=10) == 1
    assert await run_once(pg_factory, clock, limit=10) == 0
    async with pg_factory() as session:
        assert (await session.get(Order, result.order_id)).status == "expired"


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
async def test_expiry_rejects_invalid_batch_limits(db_session, limit):
    with pytest.raises(ValueError):
        await reservations(db_session).release_expired(NOW, limit)
