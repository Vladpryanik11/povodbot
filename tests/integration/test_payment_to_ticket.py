from dataclasses import dataclass

from src.repositories.payments import PaymentRepository
from src.services.payments.dtos import (
    CreatePaymentResponse,
    PaymentWebhookDTO,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.service import PaymentService
from src.services.reservations.service import ReservationItem
from src.services.tickets.issuer import TicketIssuer
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations


@dataclass
class Gateway:
    async def create_payment(self, request):
        return CreatePaymentResponse("ticket-payment", "https://pay", "NEW", request.amount_minor)

    async def get_status(self, provider_payment_id: str):
        return ProviderPaymentStatus(provider_payment_id, "CONFIRMED", 15000)

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        return ProviderOperationResult(provider_payment_id, "REFUNDING")


async def test_confirmed_payment_issues_tickets_once(db_session):
    event, user = await catalog(db_session, capacity=2)
    pending = await reservations(db_session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 2)], user.id, NOW
    )
    payments = PaymentService(PaymentRepository(db_session), Gateway(), FixedClock(NOW))
    await payments.start(pending.order_id)
    await payments.apply_webhook(
        PaymentWebhookDTO("ticket-payment", "CONFIRMED", 30000, payload={"Status": "CONFIRMED"})
    )
    repeated = await TicketIssuer(db_session).issue_for_paid_order(pending.order_id)
    assert len(repeated) == 2
