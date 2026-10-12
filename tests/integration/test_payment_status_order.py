from sqlalchemy import func, select

from src.models.commerce import Order, OrderStatus
from src.models.payments import Payment, PaymentEvent, PaymentStatus
from src.models.tickets import Ticket
from src.repositories.payments import PaymentRepository
from src.services.payments.dtos import PaymentWebhookDTO
from src.services.payments.service import PaymentService
from src.services.reservations.service import ReservationItem
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations
from tests.integration.test_tbank_webhook_idempotency import FakeGateway


def webhook(status, event_id):
    return PaymentWebhookDTO(
        "payment-1", status, 15000, event_id=event_id, payload={"Status": status}
    )


async def started(db_session):
    event, user = await catalog(db_session, capacity=2)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    clock = FixedClock(NOW)
    payments = PaymentService(PaymentRepository(db_session), FakeGateway(), clock)
    await payments.start(pending.order_id)
    return payments, pending, clock


async def state(db_session, order_id):
    payment = await db_session.scalar(select(Payment).where(Payment.order_id == order_id))
    await db_session.refresh(payment)
    order_status = await db_session.scalar(select(Order.status).where(Order.id == order_id))
    tickets = await db_session.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.order_id == order_id)
    )
    return (
        PaymentStatus(payment.status),
        payment.provider_status,
        OrderStatus(order_status),
        tickets,
    )


async def ignored_reason(db_session, event_id):
    return await db_session.scalar(
        select(PaymentEvent.ignored_reason).where(
            PaymentEvent.deduplication_key == f"tbank:event:{event_id}"
        )
    )


async def test_authorized_after_confirmed_is_stale(db_session):
    payments, pending, _ = await started(db_session)
    await payments.apply_webhook(webhook("CONFIRMED", "e1"))
    result = await payments.apply_webhook(webhook("AUTHORIZED", "e2"))
    assert result.reason == "stale_status"
    assert await state(db_session, pending.order_id) == (
        PaymentStatus.CONFIRMED,
        "CONFIRMED",
        OrderStatus.PAID,
        1,
    )
    assert await ignored_reason(db_session, "e2") == "stale_status"


async def test_authorized_before_confirmed_still_applies(db_session):
    payments, pending, _ = await started(db_session)
    await payments.apply_webhook(webhook("AUTHORIZED", "e1"))
    result = await payments.apply_webhook(webhook("CONFIRMED", "e2"))
    assert result.reason == "payment_confirmed"
    assert await state(db_session, pending.order_id) == (
        PaymentStatus.CONFIRMED,
        "CONFIRMED",
        OrderStatus.PAID,
        1,
    )


async def test_new_after_late_payment_keeps_reconciliation(db_session):
    payments, pending, clock = await started(db_session)
    clock.value = pending.expires_at
    late = await payments.apply_webhook(webhook("CONFIRMED", "e1"))
    assert late.reason == "late_payment"
    result = await payments.apply_webhook(webhook("AUTHORIZED", "e2"))
    assert result.reason == "stale_status"
    status, provider_status, order_status, _ = await state(db_session, pending.order_id)
    assert status == PaymentStatus.RECONCILIATION_REQUIRED
    assert provider_status == "CONFIRMED"
    assert order_status == OrderStatus.RECONCILIATION_REQUIRED


async def test_refunding_after_refunded_is_stale(db_session):
    payments, pending, _ = await started(db_session)
    await payments.apply_webhook(webhook("CONFIRMED", "e1"))
    await payments.apply_webhook(webhook("REFUNDED", "e2"))
    result = await payments.apply_webhook(webhook("REFUNDING", "e3"))
    assert result.reason == "stale_status"
    status, provider_status, order_status, _ = await state(db_session, pending.order_id)
    assert status == PaymentStatus.REFUNDED
    assert provider_status == "REFUNDED"
    assert await ignored_reason(db_session, "e3") == "stale_status"


async def test_unknown_status_on_paid_order_does_not_require_reconciliation(db_session):
    payments, pending, _ = await started(db_session)
    await payments.apply_webhook(webhook("CONFIRMED", "e1"))
    result = await payments.apply_webhook(webhook("RECEIPT", "e2"))
    assert result.reason == "unknown_status"
    assert await state(db_session, pending.order_id) == (
        PaymentStatus.CONFIRMED,
        "CONFIRMED",
        OrderStatus.PAID,
        1,
    )
    assert await ignored_reason(db_session, "e2") == "unknown_status"
