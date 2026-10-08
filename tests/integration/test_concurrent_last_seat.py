import asyncio

import pytest
from sqlalchemy import func, select, text

from src.models.commerce import Order, OrderItem, Reservation
from src.models.commerce import ReservationItem as ReservationItemRow
from src.services.reservations.service import CapacityExceeded, ReservationItem
from tests.commerce_fixtures import NOW, catalog, reservations


@pytest.mark.parametrize("attempt", range(3))
async def test_independent_transactions_compete_for_last_seat(pg_factory, attempt):
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session, 1)
    ready = asyncio.Barrier(2)
    backends = []

    async def buy():
        async with pg_factory() as session, session.begin():
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            backends.append(await session.scalar(text("SELECT pg_backend_pid()")))
            await ready.wait()
            return await reservations(session).reserve(
                event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
            )

    results = await asyncio.wait_for(asyncio.gather(buy(), buy(), return_exceptions=True), 12)
    assert len(set(backends)) == 2
    assert sum(not isinstance(r, BaseException) for r in results) == 1
    assert sum(isinstance(r, CapacityExceeded) for r in results) == 1
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Order)) == 1
        occupied = await session.scalar(
            select(func.sum(OrderItem.quantity))
            .join(ReservationItemRow, ReservationItemRow.order_item_id == OrderItem.id)
            .join(Reservation, Reservation.id == ReservationItemRow.reservation_id)
            .where(Reservation.status.in_(["active", "converted"]))
        )
        assert occupied == 1
