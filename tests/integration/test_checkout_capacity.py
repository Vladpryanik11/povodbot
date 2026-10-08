from datetime import timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.models.commerce import Order, OrderEvent, OrderItem, OrderTransition, Reservation
from src.models.commerce import ReservationItem as ReservationItemRow
from src.models.events import EventStatus
from src.services.events.service import TicketTypeCommand, UpdateEventCommand
from src.services.orders.service import OrderItemInput
from src.services.reservations.service import CapacityExceeded, ReservationItem
from tests.commerce_fixtures import NOW, catalog, orders, reservations
from tests.unit.services.test_events import draft, service


async def test_checkout_snapshots_server_prices_and_exact_utc_deadline(db_session):
    event, user = await catalog(db_session, 3)
    ticket = event.ticket_types[0]
    result = await orders(db_session).create_pending(
        user.id,
        event.id,
        [OrderItemInput(ticket.id, 2)],
        NOW.astimezone(timezone(timedelta(hours=3))),
    )
    assert result.status == "pending_payment"
    assert result.expires_at == NOW + timedelta(seconds=600)
    assert result.expires_at.utcoffset() == timedelta(0)
    assert result.total_kopecks == 30000
    assert result.currency == "RUB"
    assert result.items[0].quantity == 2
    await service(db_session).update(
        event.id,
        UpdateEventCommand(ticket_types=[TicketTypeCommand("New", 99000, 3, id=ticket.id)]),
    )
    item = (await db_session.scalars(select(OrderItem))).one()
    assert (item.price_kopecks, item.currency, item.ticket_label) == (15000, "RUB", "Обычный")
    audit = (await db_session.scalars(select(OrderEvent))).one()
    assert (audit.previous_status, audit.next_status, audit.action) == (
        None,
        "pending_payment",
        "create",
    )
    assert audit.created_at == NOW


async def test_shared_event_capacity_and_per_type_ceiling(db_session):
    event, user = await catalog(
        db_session, 3, [TicketTypeCommand("A", 100, 1), TicketTypeCommand("B", 200, 3)]
    )
    a, b = sorted(event.ticket_types, key=lambda t: t.name)
    checkout = reservations(db_session)
    first = await checkout.reserve(event.id, [ReservationItem(a.id, 1)], user.id, NOW)
    assert first.order_id and first.reservation_id and len(first.items) == 1
    with pytest.raises(CapacityExceeded):
        await checkout.reserve(event.id, [ReservationItem(a.id, 1)], user.id, NOW)
    with pytest.raises(CapacityExceeded):
        await checkout.reserve(event.id, [ReservationItem(b.id, 3)], user.id, NOW)
    second = await checkout.reserve(event.id, [ReservationItem(b.id, 2)], user.id, NOW)
    assert second.order_id != first.order_id
    assert await db_session.scalar(select(func.count()).select_from(Order)) == 2


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5, 2147483648])
async def test_invalid_quantities_create_nothing(db_session, quantity):
    event, user = await catalog(db_session)
    with pytest.raises(ValueError):
        await reservations(db_session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, quantity)], user.id, NOW
        )
    assert await db_session.scalar(select(func.count()).select_from(Order)) == 0


@pytest.mark.parametrize(
    "kind", ["empty", "duplicate", "unknown", "foreign", "inactive", "naive", "overflow"]
)
async def test_invalid_carts_create_nothing(db_session, kind):
    event, user = await catalog(db_session)
    ticket = event.ticket_types[0]
    items = [ReservationItem(ticket.id, 1)]
    now = NOW
    if kind == "empty":
        items = []
    elif kind == "duplicate":
        items *= 2
    elif kind == "unknown":
        items = [ReservationItem(uuid4(), 1)]
    elif kind == "foreign":
        other = await service(db_session).create_draft(draft())
        items = [ReservationItem(other.ticket_types[0].id, 1)]
    elif kind == "inactive":
        await service(db_session).update(event.id, UpdateEventCommand(ticket_types=[]))
    elif kind == "naive":
        now = NOW.replace(tzinfo=None)
    else:
        await service(db_session).update(
            event.id,
            UpdateEventCommand(
                ticket_types=[TicketTypeCommand("Huge", 9223372036854775807, 2, id=ticket.id)]
            ),
        )
        items = [ReservationItem(ticket.id, 2)]
    with pytest.raises(ValueError):
        await reservations(db_session).reserve(event.id, items, user.id, now)
    assert await db_session.scalar(select(func.count()).select_from(Order)) == 0


@pytest.mark.parametrize("kind", ["draft", "cancelled", "started", "direction"])
async def test_checkout_rejects_unavailable_events(db_session, kind):
    event, user = await catalog(db_session)
    if kind == "draft":
        event = await service(db_session).create_draft(draft())
    elif kind == "cancelled":
        await service(db_session).update(event.id, UpdateEventCommand(status=EventStatus.CANCELLED))
    elif kind == "direction":
        from src.repositories.directions import DirectionRepository
        from src.services.directions.service import DirectionService

        await DirectionService(DirectionRepository(db_session)).set_active(UUID(int=1), False)
    now = event.starts_at if kind == "started" else NOW
    with pytest.raises(ValueError):
        await reservations(db_session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, now
        )


async def test_caller_rollback_discards_order_reservation_and_audit(pg_factory):
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session)
    async with pg_factory() as session:
        with pytest.raises(RuntimeError, match="rollback"):
            async with session.begin():
                await reservations(session).reserve(
                    event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
                )
                raise RuntimeError("rollback")
    async with pg_factory() as session:
        for model in (Order, OrderItem, Reservation, ReservationItemRow, OrderEvent):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_checkout_requires_caller_owned_transaction(pg_factory):
    async with pg_factory() as session:
        with pytest.raises(RuntimeError, match="transaction"):
            await reservations(session).reserve(
                uuid4(), [ReservationItem(uuid4(), 1)], uuid4(), NOW
            )


async def test_paid_capacity_survives_expiry_reconciliation_and_refund_request(db_session):
    event, user = await catalog(db_session, 1)
    cart = [ReservationItem(event.ticket_types[0].id, 1)]
    result = await reservations(db_session).reserve(event.id, cart, user.id, NOW)
    order_service = orders(db_session)
    paid = await order_service.transition(
        result.order_id, OrderTransition.CONFIRM_PAYMENT, "provider_confirmed"
    )
    assert paid.status == "paid"
    assert (await db_session.get(Reservation, result.reservation_id)).status == "converted"
    count = await db_session.scalar(select(func.count()).select_from(OrderEvent))
    await order_service.transition(
        result.order_id, OrderTransition.CONFIRM_PAYMENT, "provider_confirmed"
    )
    assert await db_session.scalar(select(func.count()).select_from(OrderEvent)) == count
    await order_service.transition(
        result.order_id, OrderTransition.REQUIRE_RECONCILIATION, "provider_unknown"
    )
    await order_service.transition(
        result.order_id, OrderTransition.REQUEST_REFUND, "refund_requested"
    )
    assert await reservations(db_session).release_expired(NOW + timedelta(hours=1), 10) == 0
    with pytest.raises(CapacityExceeded):
        await reservations(db_session).reserve(event.id, cart, user.id, NOW + timedelta(hours=1))
    await order_service.transition(
        result.order_id, OrderTransition.CONFIRM_REFUND, "provider_refunded"
    )
    await reservations(db_session).reserve(event.id, cart, user.id, NOW + timedelta(hours=1))
    audits = list(
        await db_session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == result.order_id)
            .order_by(OrderEvent.sequence)
        )
    )
    assert [a.next_status for a in audits] == [
        "pending_payment",
        "paid",
        "reconciliation_required",
        "refund_requested",
        "refunded",
    ]
    assert all(a.created_at.tzinfo is not None for a in audits)


@pytest.mark.parametrize(
    "action",
    [OrderTransition.FAIL_PAYMENT, OrderTransition.CANCEL, OrderTransition.REQUIRE_RECONCILIATION],
)
async def test_failed_cancelled_and_uncertain_checkout_release_capacity(db_session, action):
    event, user = await catalog(db_session, 1)
    cart = [ReservationItem(event.ticket_types[0].id, 1)]
    result = await reservations(db_session).reserve(event.id, cart, user.id, NOW)
    await orders(db_session).transition(result.order_id, action, "checkout_stopped")
    assert (await db_session.get(Reservation, result.reservation_id)).status == "released"
    await reservations(db_session).reserve(event.id, cart, user.id, NOW)


@pytest.mark.parametrize("reason", ["", "customer@example.com", "customer text", "x" * 65])
async def test_audit_rejects_arbitrary_text_before_mutation(db_session, reason):
    event, user = await catalog(db_session)
    result = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    with pytest.raises(ValueError):
        await orders(db_session).transition(result.order_id, OrderTransition.CANCEL, reason)
    assert (await db_session.get(Order, result.order_id)).status == "pending_payment"
    assert await db_session.scalar(select(func.count()).select_from(OrderEvent)) == 1


@pytest.mark.parametrize("table", ["order_events", "order_items"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
async def test_database_protects_audit_and_snapshots(db_session, table, operation):
    event, user = await catalog(db_session)
    await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    sql = f"{operation} {table}"
    if operation == "UPDATE":
        column = "reason" if table == "order_events" else "ticket_label"
        sql += f" SET {column} = 'changed'"
    elif operation == "DELETE":
        sql = f"DELETE FROM {table}"
    with pytest.raises(DBAPIError, match="immutable"):
        async with db_session.begin_nested():
            await db_session.execute(text(sql))


async def test_database_rejects_duplicate_reservation_item(db_session):
    event, user = await catalog(db_session)
    result = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    item = (await db_session.scalars(select(OrderItem))).one()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ReservationItemRow(reservation_id=result.reservation_id, order_item_id=item.id)
            )
            await db_session.flush()
