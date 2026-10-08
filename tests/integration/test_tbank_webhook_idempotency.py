from dataclasses import dataclass

from sqlalchemy import select

from src.models.commerce import OrderStatus, Reservation, ReservationStatus
from src.models.payments import Payment, PaymentStatus
from src.repositories.payments import PaymentRepository
from src.services.payments.dtos import (
    CreatePaymentResponse,
    PaymentWebhookDTO,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.service import PaymentService
from src.services.reservations.service import ReservationItem
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations


@dataclass
class FakeGateway:
    calls: int = 0

    async def create_payment(self, request):
        self.calls += 1
        return CreatePaymentResponse("payment-1", "https://pay/1", "NEW", request.amount_minor)

    async def get_status(self, provider_payment_id: str):
        return ProviderPaymentStatus(provider_payment_id, "CONFIRMED", 15000)

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        return ProviderOperationResult(provider_payment_id, "REFUNDING")


async def test_webhook_confirmation_is_idempotent_and_redirect_is_not_proof(db_session):
    event, user = await catalog(db_session, capacity=2)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    gateway = FakeGateway()
    payments = PaymentService(PaymentRepository(db_session), gateway, FixedClock(NOW))
    checkout = await payments.start(pending.order_id)
    assert checkout.payment_url == "https://pay/1"
    first = await payments.apply_webhook(
        PaymentWebhookDTO("payment-1", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
    )
    second = await payments.apply_webhook(
        PaymentWebhookDTO("payment-1", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
    )
    assert first.reason == "payment_confirmed"
    assert first.order_status == OrderStatus.PAID
    assert second.duplicate is True
    stored = await db_session.scalar(select(Payment).where(Payment.id == checkout.payment_id))
    assert stored is not None
    assert PaymentStatus(stored.status) == PaymentStatus.CONFIRMED
    assert stored.provider_payment_id == "payment-1"
    reservation = await db_session.scalar(
        select(Reservation).where(Reservation.order_id == pending.order_id)
    )
    assert reservation is not None
    assert ReservationStatus(reservation.status) == ReservationStatus.CONVERTED
    assert gateway.calls == 1


async def test_start_reuses_existing_provider_payment(db_session):
    event, user = await catalog(db_session)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    gateway = FakeGateway()
    payments = PaymentService(PaymentRepository(db_session), gateway, FixedClock(NOW))
    first = await payments.start(pending.order_id)
    second = await payments.start(pending.order_id)
    assert first.payment_id == second.payment_id
    assert gateway.calls == 1


async def test_in_progress_provider_status_does_not_trigger_refund_flow(db_session):
    event, user = await catalog(db_session, capacity=2)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    payments = PaymentService(PaymentRepository(db_session), FakeGateway(), FixedClock(NOW))
    checkout = await payments.start(pending.order_id)

    result = await payments.apply_webhook(
        PaymentWebhookDTO(
            "payment-1",
            "NEW",
            15000,
            event_id="progress-status",
            payload={"Status": "NEW"},
        )
    )

    assert result.reason == "payment_processing"
    assert result.order_status == OrderStatus.PENDING_PAYMENT
    stored = await db_session.scalar(select(Payment).where(Payment.id == checkout.payment_id))
    assert stored is not None
    assert PaymentStatus(stored.status) == PaymentStatus.PROCESSING
