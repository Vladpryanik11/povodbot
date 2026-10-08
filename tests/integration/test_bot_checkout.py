from dataclasses import dataclass

from sqlalchemy import select

from src.bot.handlers.checkout import CheckoutHandler
from src.bot.handlers.tickets import TicketHandler
from src.models.commerce import Order, OrderStatus
from src.repositories.orders import OrderRepository
from src.services.orders.service import OrderService
from src.services.payments.dtos import (
    CreatePaymentResponse,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.tickets.issuer import TicketIssuer
from tests.commerce_fixtures import catalog


@dataclass
class Gateway:
    async def create_payment(self, request):
        return CreatePaymentResponse(
            "bot-payment", "https://pay.example/bot", "NEW", request.amount_minor
        )

    async def get_status(self, provider_payment_id: str):
        return ProviderPaymentStatus(provider_payment_id, "NEW")

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        return ProviderOperationResult(provider_payment_id, "REFUNDING")


async def test_telegram_checkout_creates_reservation_and_payment_link(db_session):
    event, user = await catalog(db_session, capacity=3)
    handler = CheckoutHandler(db_session, Gateway())

    options = await handler.choose_quantity(event.ticket_types[0].id)
    callbacks = [button.callback_data for row in options.keyboard.inline_keyboard for button in row]
    assert f"quantity:{event.ticket_types[0].id}:1" in callbacks

    response = await handler.create_payment(event.ticket_types[0].id, 2, user.id)
    assert "300.00" in response.text
    assert response.keyboard.inline_keyboard[0][0].url == "https://pay.example/bot"

    order = await db_session.scalar(select(Order).where(Order.user_id == user.id))
    assert order is not None
    assert OrderStatus(order.status) == OrderStatus.PENDING_PAYMENT
    assert order.total_kopecks == 30000

    await OrderService(OrderRepository(db_session)).transition(
        order.id, "confirm_payment", "payment_confirmed"
    )
    await TicketIssuer(db_session).issue_for_paid_order(order.id)
    tickets = await TicketHandler(db_session).mine(user.id)
    assert "QR-код:" in tickets.text
