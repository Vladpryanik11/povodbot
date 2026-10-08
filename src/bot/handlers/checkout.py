from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import BotResponse
from src.bot.keyboards.checkout import payment_keyboard, quantity_keyboard
from src.bot.keyboards.events import events_keyboard
from src.models.events import TicketType
from src.repositories.events import EventRepository
from src.repositories.orders import OrderRepository
from src.repositories.payments import PaymentRepository
from src.services.events.service import EventService, PublicEventDTO, PublicTicketTypeDTO
from src.services.orders.service import OrderItemInput, OrderService
from src.services.payments.ports import PaymentGateway
from src.services.payments.service import PaymentService

MAX_TICKETS_PER_ORDER = 10


class CheckoutHandler:
    def __init__(self, session: AsyncSession, gateway: PaymentGateway | None = None):
        self.session = session
        self.gateway = gateway
        self.events = EventService(EventRepository(session))

    async def _ticket(self, ticket_type_id: UUID) -> tuple[PublicEventDTO, PublicTicketTypeDTO]:
        event_id = await self.session.scalar(
            select(TicketType.event_id).where(TicketType.id == ticket_type_id)
        )
        if event_id is None:
            raise LookupError("Ticket type not found")
        event = await self.events.get_public(event_id)
        for ticket in event.ticket_types:
            if ticket.id == ticket_type_id:
                return event, ticket
        raise LookupError("Ticket type is not available")

    async def choose_quantity(self, ticket_type_id: UUID) -> BotResponse:
        event, ticket = await self._ticket(ticket_type_id)
        maximum = min(ticket.limit, MAX_TICKETS_PER_ORDER)
        return BotResponse(
            f"{event.title}\nТип билета: {ticket.name}\nВыберите количество:",
            quantity_keyboard(str(ticket.id), maximum),
        )

    async def create_payment(
        self, ticket_type_id: UUID, quantity: int, user_id: UUID
    ) -> BotResponse:
        if type(quantity) is not int or not 1 <= quantity <= MAX_TICKETS_PER_ORDER:
            raise ValueError("Invalid ticket quantity")
        if self.gateway is None:
            raise RuntimeError("Payment gateway is required to create a payment")
        event, ticket = await self._ticket(ticket_type_id)
        pending = await OrderService(OrderRepository(self.session)).create_pending(
            user_id,
            event.id,
            [OrderItemInput(ticket.id, quantity)],
            datetime.now(UTC),
        )
        checkout = await PaymentService(PaymentRepository(self.session), self.gateway).start(
            pending.order_id
        )
        if checkout.payment_url is None:
            return BotResponse(
                "Заказ создан, но платёжная ссылка пока недоступна. "
                "Мы передали заказ на ручную сверку. Обратитесь в поддержку клуба.",
                events_keyboard([event]),
            )
        rubles, kopecks = divmod(pending.total_kopecks, 100)
        return BotResponse(
            f"Заказ создан на сумму {rubles}.{kopecks:02d} ₽. Бронь действует до "
            f"{pending.expires_at.astimezone(UTC).strftime('%d.%m.%Y %H:%M UTC')}. "
            "Завершите оплату по кнопке ниже.",
            payment_keyboard(checkout.payment_url),
        )
