from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.repositories.reservations import ReservationRepository
from src.services.commerce.clock import Clock, SystemClock
from src.services.reservations.service import ReservationService


async def run_once(
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock | None = None,
    limit: int = 100,
) -> int:
    current_clock = clock or SystemClock()
    async with session_factory() as session, session.begin():
        return await ReservationService(
            ReservationRepository(session), current_clock
        ).release_expired(current_clock.now(), limit)
