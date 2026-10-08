from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.payments import Payment, PaymentEvent


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_update(self, payment_id: UUID) -> Payment:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.id == payment_id)
            .options(selectinload(Payment.events))
            .with_for_update()
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            raise LookupError("Payment not found")
        return payment

    async def by_order_for_update(self, order_id: UUID) -> Payment | None:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
            .options(selectinload(Payment.events))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def by_provider_payment_for_update(self, provider_payment_id: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.provider_payment_id == provider_payment_id)
            .options(selectinload(Payment.events))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def event_by_key(self, key: str) -> PaymentEvent | None:
        result = await self.session.execute(
            select(PaymentEvent).where(PaymentEvent.deduplication_key == key)
        )
        return result.scalar_one_or_none()

    async def save(self) -> None:
        await self.session.flush()
