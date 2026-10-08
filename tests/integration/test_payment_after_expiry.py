from dataclasses import dataclass

import pytest
from sqlalchemy import select

from src.models.commerce import OrderStatus, Reservation, ReservationStatus
from src.repositories.payments import PaymentRepository
from src.services.payments.dtos import (
    CreatePaymentResponse,
    PaymentWebhookDTO,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.ports import PaymentGatewayError
from src.services.payments.service import PaymentService, PaymentStateError
from src.services.reservations.service import ReservationItem
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
    assert gateway.refund_calls == 1
    repeated = await payments.request_refund(checkout.payment_id, "customer_request")
    assert repeated.status.value == "refunding"
    assert gateway.refund_calls == 1
