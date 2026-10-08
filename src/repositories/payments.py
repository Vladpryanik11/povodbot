from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.payments import Payment, PaymentEvent


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_id(self, payment_id: UUID) -> Payment | None:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.id == payment_id)
            .options(selectinload(Payment.events))
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

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

    async def by_provider_payment(self, provider_payment_id: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.provider_payment_id == provider_payment_id)
            .options(selectinload(Payment.events))
            .execution_options(populate_existing=True)
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

    async def insert_payment_event_if_absent(self, event: PaymentEvent) -> bool:
        statement = (
            pg_insert(PaymentEvent)
            .values(
                id=event.id or uuid4(),
                payment_id=event.payment_id,
                provider=event.provider or "tbank",
                provider_payment_id=event.provider_payment_id,
                deduplication_key=event.deduplication_key,
                provider_status=event.provider_status,
                payload=event.payload,
                received_at=event.received_at,
                applied_at=event.applied_at,
                ignored_reason=event.ignored_reason,
            )
            .on_conflict_do_nothing(index_elements=[PaymentEvent.deduplication_key])
        )
        result = await self.session.execute(statement)
        rowcount: int = int(getattr(result, "rowcount", 0))
        return rowcount == 1

    async def save(self) -> None:
        await self.session.flush()
