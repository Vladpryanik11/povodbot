"""Guests with tickets, likes, blocks and consents for broadcast tests; direct ORM inserts."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from src.models.campaigns import Campaign, CampaignDelivery, DeliveryStatus
from src.models.commerce import Order, OrderItem, OrderStatus
from src.models.events import TicketType
from src.models.favorites import Favorite
from src.models.identity import Consent, ConsentStatus, ConsentType, User
from src.models.tickets import TicketStatus, Ticket
from src.repositories.users import UserRepository
from tests.unit.services.test_events import draft, service

D1 = UUID(int=1)
D2 = UUID(int=2)


async def evening(session, direction_id: UUID = D1, **changes) -> UUID:
    event = await service(session).create_draft(draft(direction_id=direction_id, **changes))
    await service(session).publish(event.id)
    return event.id


async def paid_order(session, user: User, event_id: UUID, ticket: str | None = None) -> Order:
    kind = await session.scalar(select(TicketType).where(TicketType.event_id == event_id))
    order = Order(
        user_id=user.id,
        event_id=event_id,
        status=OrderStatus.PAID,
        total_kopecks=kind.price_kopecks,
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()
    if ticket is not None:
        item = OrderItem(
            order_id=order.id,
            ticket_type_id=kind.id,
            ticket_label=kind.name,
            quantity=1,
            price_kopecks=kind.price_kopecks,
            line_total_kopecks=kind.price_kopecks,
        )
        session.add(item)
        await session.flush()
        session.add(
            Ticket(
                order_id=order.id,
                event_id=event_id,
                ticket_type_id=kind.id,
                order_item_id=item.id,
                position=1,
                label=kind.name,
                price_kopecks=kind.price_kopecks,
                token_hash=secrets.token_hex(32),
                status=ticket,
            )
        )
        await session.flush()
    return order


async def guest(
    session,
    telegram_id: int,
    *,
    liked=(),
    going=(),
    attended=(),
    paid=(),
    blocked: bool = False,
    revoked: bool = False,
) -> User:
    user = await UserRepository(session).upsert(telegram_id, f"Гость {telegram_id}", None, None, None)
    user.is_blocked = blocked
    for event_id in liked:
        session.add(Favorite(user_id=user.id, event_id=event_id))
    for event_id in going:
        await paid_order(session, user, event_id, TicketStatus.ISSUED)
    for event_id in attended:
        await paid_order(session, user, event_id, TicketStatus.CHECKED_IN)
    for event_id in paid:
        await paid_order(session, user, event_id)
    if revoked:
        session.add(
            Consent(
                user_id=user.id,
                consent_type=ConsentType.MARKETING,
                status=ConsentStatus.REVOKED,
                source="telegram",
            )
        )
    await session.flush()
    return user


async def delivered(
    session, user: User, sent_at: datetime, status: str = DeliveryStatus.SENT
) -> CampaignDelivery:
    campaign = Campaign(title="Прошлая рассылка", body="Текст", audience={}, status="completed")
    session.add(campaign)
    await session.flush()
    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        user_id=user.id,
        telegram_id=user.telegram_id,
        idempotency_key=f"campaign:{campaign.id}:user:{user.id}",
        status=status,
        attempts=1,
        sent_at=sent_at if status == DeliveryStatus.SENT else None,
    )
    session.add(delivery)
    await session.flush()
    return delivery
