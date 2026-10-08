from dataclasses import dataclass

from sqlalchemy import select

from src.models.commerce import OrderStatus, Reservation, ReservationStatus
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
