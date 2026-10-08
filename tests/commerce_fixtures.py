from datetime import UTC, datetime

from src.repositories.orders import OrderRepository
from src.repositories.reservations import ReservationRepository
from src.repositories.users import UserRepository
from src.services.orders.service import OrderService
from src.services.reservations.service import ReservationService
from src.services.users.service import UserService
from tests.unit.services.test_events import draft, service

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


class FixedClock:
    def __init__(self, now):
        self.value = now

    def now(self):
        return self.value


def orders(session, now=NOW):
    return OrderService(OrderRepository(session), FixedClock(now))


def reservations(session):
    return ReservationService(ReservationRepository(session), FixedClock(NOW))


async def catalog(session, capacity=2, ticket_types=None):
    from src.services.events.service import TicketTypeCommand

    if ticket_types is None:
        ticket_types = [TicketTypeCommand("Обычный", 15000, capacity)]
    event = await service(session).create_draft(draft(capacity=capacity, ticket_types=ticket_types))
    await service(session).publish(event.id)
    user = await UserService(UserRepository(session)).upsert_telegram_user(
        100, None, None, None, None
    )
    return event, user
