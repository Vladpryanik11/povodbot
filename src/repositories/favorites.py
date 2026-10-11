from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.events import Event, EventStatus
from src.models.favorites import Favorite


class FavoriteRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user_id: UUID, event_id: UUID) -> None:
        await self.session.execute(
            insert(Favorite)
            .values(user_id=user_id, event_id=event_id)
            .on_conflict_do_nothing(index_elements=[Favorite.user_id, Favorite.event_id])
        )

    async def remove(self, user_id: UUID, event_id: UUID) -> None:
        await self.session.execute(
            delete(Favorite).where(Favorite.user_id == user_id, Favorite.event_id == event_id)
        )

    async def list_ids(self, user_id: UUID) -> list[UUID]:
        return list(
            await self.session.scalars(
                select(Favorite.event_id)
                .where(Favorite.user_id == user_id)
                .order_by(Favorite.created_at, Favorite.event_id)
            )
        )

    async def import_ids(self, user_id: UUID, ids: list[UUID]) -> None:
        published = list(
            await self.session.scalars(
                select(Event.id).where(Event.id.in_(ids), Event.status == EventStatus.PUBLISHED)
            )
        )
        for event_id in ids:
            if event_id in published:
                await self.add(user_id, event_id)
