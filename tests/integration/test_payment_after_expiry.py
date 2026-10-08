from dataclasses import dataclass

import pytest
from sqlalchemy import select

from src.models.commerce import OrderStatus, Reservation, ReservationStatus
from src.models.outbox import Outbox
from src.models.payments import Payment
from src.repositories.payments import PaymentRepository
from src.services.payments.checkout import PaymentCheckoutService
from src.services.payments.dtos import (
    CreatePaymentResponse,
    PaymentWebhookDTO,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.ports import PaymentGatewayError
from src.services.payments.service import PaymentService, PaymentStateError
from src.services.reservations.service import ReservationItem
from src.workers.outbox import PaymentRefundOutboxWorker
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations


@dataclass
class FakeGateway:
    async def create_payment(self, request):
        return CreatePaymentResponse(
            "late-payment", "https://pay/late", "NEW", request.amount_minor
        )

    async def get_status(self, provider_payment_id: str):
        return ProviderPaymentStatus(provider_payment_id, "CONFIRMED", 15000)

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        return ProviderOperationResult(provider_payment_id, "REFUNDING")


@dataclass
class UnknownInitGateway(FakeGateway):
    calls: int = 0

    async def create_payment(self, request):
        self.calls += 1
        raise PaymentGatewayError("response lost after Init")


@dataclass
class RefundFailureGateway(FakeGateway):
    refund_calls: int = 0

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        self.refund_calls += 1
        raise PaymentGatewayError("response lost after Cancel")


async def test_confirmation_after_expiry_requires_reconciliation_and_releases_reservation(
    db_session,
):
    event, user = await catalog(db_session, capacity=1)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    clock = FixedClock(NOW)
    payments = PaymentService(PaymentRepository(db_session), FakeGateway(), clock)
    await payments.start(pending.order_id)
    clock.value = pending.expires_at
    result = await payments.apply_webhook(
        PaymentWebhookDTO("late-payment", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
    )
    assert result.order_status == OrderStatus.RECONCILIATION_REQUIRED
    reservation = await db_session.scalar(
        select(Reservation).where(Reservation.order_id == pending.order_id)
    )
    assert reservation is not None
    assert ReservationStatus(reservation.status) == ReservationStatus.RELEASED


async def test_unknown_init_is_persisted_and_not_retried_as_a_second_charge(db_session):
    event, user = await catalog(db_session)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    gateway = UnknownInitGateway()
    payments = PaymentService(PaymentRepository(db_session), gateway, FixedClock(NOW))
    unresolved = await payments.start(pending.order_id)
    assert unresolved.status.value == "reconciliation_required"
    with pytest.raises(PaymentStateError, match="reconciliation"):
        await payments.start(pending.order_id)
    assert gateway.calls == 1


async def test_unknown_init_can_be_bound_and_reconciled_by_operator(db_session):
    event, user = await catalog(db_session)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    gateway = UnknownInitGateway()
    payments = PaymentService(PaymentRepository(db_session), gateway, FixedClock(NOW))
    await payments.start(pending.order_id)
    payment = await PaymentRepository(db_session).by_order_for_update(pending.order_id)
    assert payment is not None
    bound = await payments.bind_provider_payment(payment.id, "recovered-provider-id")
    assert bound.provider_payment_id == "recovered-provider-id"
    reconciled = await payments.reconcile(payment.id)
    assert reconciled.status.value == "confirmed"


async def test_manual_provider_bind_rejects_amount_mismatch(db_session):
    event, user = await catalog(db_session)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    gateway = UnknownInitGateway()
    payments = PaymentService(PaymentRepository(db_session), gateway, FixedClock(NOW))
    await payments.start(pending.order_id)
    payment = await PaymentRepository(db_session).by_order_for_update(pending.order_id)
    assert payment is not None

    class MismatchedGateway(UnknownInitGateway):
        async def get_status(self, provider_payment_id: str):
            return ProviderPaymentStatus(provider_payment_id, "CONFIRMED", 1)

    payments = PaymentService(PaymentRepository(db_session), MismatchedGateway(), FixedClock(NOW))
    with pytest.raises(PaymentStateError, match="amount"):
        await payments.bind_provider_payment(payment.id, "recovered-provider-id")


async def test_refund_failure_keeps_operation_in_reconcilable_state(db_session):
    event, user = await catalog(db_session)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    gateway = RefundFailureGateway()
    payments = PaymentService(PaymentRepository(db_session), gateway, FixedClock(NOW))
    checkout = await payments.start(pending.order_id)
    await payments.apply_webhook(
        PaymentWebhookDTO("late-payment", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
    )
    result = await payments.request_refund(checkout.payment_id, "customer_request")
    assert result.status.value == "refunding"
    assert gateway.refund_calls == 0
    command = await db_session.scalar(
        select(Outbox).where(Outbox.deduplication_key == f"payment:refund:{checkout.payment_id}")
    )
    assert command is not None
    repeated = await payments.request_refund(checkout.payment_id, "customer_request")
    assert repeated.status.value == "refunding"
    assert gateway.refund_calls == 0


async def test_checkout_orchestrator_commits_intent_before_provider_call(pg_factory):
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session)
        pending = await reservations(session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
        )

    checkout = await PaymentCheckoutService(pg_factory, FakeGateway(), FixedClock(NOW)).start(
        pending.order_id
    )

    assert checkout.payment_url == "https://pay/late"
    async with pg_factory() as session, session.begin():
        payment = await session.scalar(select(Payment).where(Payment.id == checkout.payment_id))
        assert payment is not None
        assert payment.provider_payment_id == "late-payment"


async def test_refund_worker_reconciles_ambiguous_cancel_without_retrying(pg_factory):
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session)
        pending = await reservations(session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
        )
        gateway = RefundFailureGateway()
        payments = PaymentService(PaymentRepository(session), gateway, FixedClock(NOW))
        checkout = await payments.start(pending.order_id)
        await payments.apply_webhook(
            PaymentWebhookDTO("late-payment", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
        )
        await payments.request_refund(checkout.payment_id, "customer_request")

    assert await PaymentRefundOutboxWorker(pg_factory, gateway).process_pending() == 1
    assert gateway.refund_calls == 1
    assert await PaymentRefundOutboxWorker(pg_factory, gateway).process_pending() == 0
    async with pg_factory() as session, session.begin():
        payment = await session.scalar(select(Payment).where(Payment.id == checkout.payment_id))
        assert payment is not None
        assert payment.provider_status == "REFUND_UNKNOWN"
