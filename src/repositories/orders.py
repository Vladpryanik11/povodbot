from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.commerce import Order, OrderEvent


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def event_id(self, order_id: UUID) -> UUID:
        event_id = await self.session.scalar(select(Order.event_id).where(Order.id == order_id))
        if event_id is None:
            raise LookupError("Order not found")
        return event_id

    async def get_for_update(self, order_id: UUID) -> Order:
        order = await self.session.scalar(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items), selectinload(Order.reservation))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if order is None:
            raise LookupError("Order not found")
        return order

    async def add_event(
        self,
        order: Order,
        previous_status: str | None,
        next_status: str,
        action: str,
        reason: str,
        created_at: datetime,
    ) -> OrderEvent:
        event = OrderEvent(
            order_id=order.id,
            previous_status=previous_status,
            next_status=next_status,
            action=action,
            reason=reason,
            created_at=created_at,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def save(self) -> None:
        await self.session.flush()
