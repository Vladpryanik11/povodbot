from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from src.models.commerce import Order, OrderStatus
from src.models.outbox import Outbox
from src.models.payments import Payment, PaymentStatus
from src.repositories.payments import PaymentRepository
from src.services.payments.dtos import (
    CreatePaymentResponse,
    PaymentWebhookDTO,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.ports import (
    PaymentGatewayError,
    PaymentProviderRejected,
    PaymentProviderTimeout,
)
from src.services.payments.service import PaymentService
from src.services.reservations.service import ReservationItem
from src.workers.outbox import REFUND_MAX_ATTEMPTS, PaymentRefundOutboxWorker
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations

REFUNDED = ProviderOperationResult("retry-payment", "REFUNDED")


@dataclass
class Gateway:
    """refund() answers from the queue; an empty queue means the bank is down."""

    refunds: list = field(default_factory=list)
    refund_calls: int = 0
    refunded: bool = False

    async def create_payment(self, request):
        return CreatePaymentResponse(
            "retry-payment", "https://pay/retry", "NEW", request.amount_minor
        )

    async def get_status(self, provider_payment_id: str):
        status = "REFUNDED" if self.refunded else "CONFIRMED"
        return ProviderPaymentStatus(provider_payment_id, status, 15000)

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        self.refund_calls += 1
        outcome = self.refunds.pop(0) if self.refunds else PaymentGatewayError("bank is down")
        if isinstance(outcome, Exception):
            raise outcome
        self.refunded = outcome.provider_status == "REFUNDED"
        return outcome


@dataclass
class LostResponseGateway(Gateway):
    """The bank returns the money, but its answer to Cancel never reaches us."""

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        self.refund_calls += 1
        self.refunded = True
        raise PaymentProviderTimeout("response lost after Cancel")


async def refund_requested(pg_factory, gateway):
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session)
        pending = await reservations(session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
        )
        payments = PaymentService(PaymentRepository(session), gateway, FixedClock(NOW))
        checkout = await payments.start(pending.order_id)
        await payments.apply_webhook(
            PaymentWebhookDTO("retry-payment", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
        )
        await payments.request_refund(checkout.payment_id, "customer_request")
    return checkout.payment_id, pending.order_id


async def request_refund(pg_factory, gateway, payment_id):
    async with pg_factory() as session, session.begin():
        payments = PaymentService(PaymentRepository(session), gateway, FixedClock(NOW))
        await payments.request_refund(payment_id, "operator_retry")


async def state(pg_factory, payment_id):
    async with pg_factory() as session:
        payment = await session.get(Payment, payment_id)
        order = await session.get(Order, payment.order_id)
        commands = list(
            await session.scalars(
                select(Outbox).where(Outbox.deduplication_key == f"payment:refund:{payment_id}")
            )
        )
    assert len(commands) == 1
    return payment, order, commands[0]


async def make_due(pg_factory, payment_id):
    async with pg_factory() as session, session.begin():
        await session.execute(
            update(Outbox)
            .where(Outbox.deduplication_key == f"payment:refund:{payment_id}")
            .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
        )


async def give_up(pg_factory, gateway, payment_id):
    worker = PaymentRefundOutboxWorker(pg_factory, gateway)
    for attempt in range(1, REFUND_MAX_ATTEMPTS + 1):
        assert await worker.process_pending() == 1
        _, _, command = await state(pg_factory, payment_id)
        assert (command.processed_at is None) == (attempt < REFUND_MAX_ATTEMPTS)
        await make_due(pg_factory, payment_id)


async def test_refund_retries_after_gateway_error_and_succeeds(pg_factory):
    gateway = Gateway(refunds=[PaymentGatewayError("bank is down"), REFUNDED])
    payment_id, _ = await refund_requested(pg_factory, gateway)
    worker = PaymentRefundOutboxWorker(pg_factory, gateway)

    await worker.process_pending()
    payment, _, command = await state(pg_factory, payment_id)
    assert command.processed_at is None
    assert payment.provider_status == "REFUND_RETRY"

    await make_due(pg_factory, payment_id)
    await worker.process_pending()
    payment, order, command = await state(pg_factory, payment_id)
    assert PaymentStatus(payment.status) == PaymentStatus.REFUNDED
    assert OrderStatus(order.status) == OrderStatus.REFUNDED
    assert command.processed_at is not None
    assert gateway.refund_calls == 2


async def test_refund_retry_does_not_cancel_twice_when_bank_already_refunded(pg_factory):
    gateway = LostResponseGateway()
    payment_id, _ = await refund_requested(pg_factory, gateway)
    worker = PaymentRefundOutboxWorker(pg_factory, gateway)

    await worker.process_pending()
    await make_due(pg_factory, payment_id)
    await worker.process_pending()

    payment, _, _ = await state(pg_factory, payment_id)
    assert gateway.refund_calls == 1
    assert PaymentStatus(payment.status) == PaymentStatus.REFUNDED


async def test_refund_gives_up_after_max_attempts(pg_factory):
    gateway = Gateway()
    payment_id, _ = await refund_requested(pg_factory, gateway)

    await give_up(pg_factory, gateway, payment_id)

    payment, _, command = await state(pg_factory, payment_id)
    assert command.processed_at is not None
    assert payment.provider_status == "REFUND_UNKNOWN"
    assert PaymentStatus(payment.status) == PaymentStatus.RECONCILIATION_REQUIRED
    assert gateway.refund_calls == REFUND_MAX_ATTEMPTS


async def test_rejected_refund_is_closed_for_operator(pg_factory):
    gateway = Gateway(refunds=[PaymentProviderRejected("refund rejected")])
    payment_id, _ = await refund_requested(pg_factory, gateway)

    await PaymentRefundOutboxWorker(pg_factory, gateway).process_pending()

    payment, _, command = await state(pg_factory, payment_id)
    assert command.processed_at is not None
    assert payment.provider_status == "REFUND_REJECTED"
    assert PaymentStatus(payment.status) == PaymentStatus.RECONCILIATION_REQUIRED


async def test_refund_after_give_up_can_be_requested_again(pg_factory):
    gateway = Gateway()
    payment_id, _ = await refund_requested(pg_factory, gateway)
    await give_up(pg_factory, gateway, payment_id)

    await request_refund(pg_factory, gateway, payment_id)
    payment, _, command = await state(pg_factory, payment_id)
    assert command.processed_at is None
    assert command.attempts == 0
    assert command.payload["reason"] == "operator_retry"
    assert PaymentStatus(payment.status) == PaymentStatus.REFUNDING

    gateway.refunds = [REFUNDED]
    await PaymentRefundOutboxWorker(pg_factory, gateway).process_pending()
    payment, order, _ = await state(pg_factory, payment_id)
    assert PaymentStatus(payment.status) == PaymentStatus.REFUNDED
    assert OrderStatus(order.status) == OrderStatus.REFUNDED


async def test_late_payment_can_be_refunded(pg_factory):
    gateway = Gateway(refunds=[REFUNDED])
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session)
        pending = await reservations(session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
        )
        clock = FixedClock(NOW)
        payments = PaymentService(PaymentRepository(session), gateway, clock)
        checkout = await payments.start(pending.order_id)
        clock.value = pending.expires_at
        await payments.apply_webhook(
            PaymentWebhookDTO("retry-payment", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
        )
    async with pg_factory() as session:
        payment = await session.get(Payment, checkout.payment_id)
    assert PaymentStatus(payment.status) == PaymentStatus.RECONCILIATION_REQUIRED
    assert payment.provider_status == "CONFIRMED"

    await request_refund(pg_factory, gateway, checkout.payment_id)
    await PaymentRefundOutboxWorker(pg_factory, gateway).process_pending()

    payment, order, command = await state(pg_factory, checkout.payment_id)
    assert PaymentStatus(payment.status) == PaymentStatus.REFUNDED
    assert OrderStatus(order.status) == OrderStatus.REFUNDED
    assert command.processed_at is not None
