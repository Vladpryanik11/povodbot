from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commerce import (
    OrderItem,
    Reservation,
    ReservationItem,
    ReservationStatus,
)


class ReservationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def due_event_ids(self, now: datetime) -> list[UUID]:
        result = await self.session.scalars(
            select(Reservation.event_id)
            .where(
                Reservation.status == ReservationStatus.ACTIVE,
                Reservation.expires_at <= now,
            )
            .distinct()
            .order_by(Reservation.event_id)
        )
        return list(result)

    async def due_for_event(
        self,
        event_id: UUID,
        now: datetime,
        limit: int,
        *,
        skip_locked: bool = False,
    ) -> list[Reservation]:
        query = (
            select(Reservation)
            .where(
                Reservation.event_id == event_id,
                Reservation.status == ReservationStatus.ACTIVE,
                Reservation.expires_at <= now,
            )
            .order_by(Reservation.expires_at, Reservation.id)
            .limit(limit)
            .with_for_update(skip_locked=skip_locked)
            .execution_options(populate_existing=True)
        )
        return list(await self.session.scalars(query))

    async def occupied_by_ticket(self, event_id: UUID) -> dict[UUID, int]:
        result = await self.session.execute(
            select(OrderItem.ticket_type_id, func.sum(OrderItem.quantity))
            .join(ReservationItem, ReservationItem.order_item_id == OrderItem.id)
            .join(Reservation, Reservation.id == ReservationItem.reservation_id)
            .where(
                Reservation.event_id == event_id,
                Reservation.status.in_([ReservationStatus.ACTIVE, ReservationStatus.CONVERTED]),
            )
            .group_by(OrderItem.ticket_type_id)
        )
        return {ticket_id: int(quantity) for ticket_id, quantity in result.all()}
