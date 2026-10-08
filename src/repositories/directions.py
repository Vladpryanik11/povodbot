from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.directions import Direction


class DirectionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        slug: str,
        name: str,
        description: str | None,
        sort_order: int,
        active: bool,
    ) -> Direction:
        direction = Direction(
            slug=slug, name=name, description=description, sort_order=sort_order, active=active
        )
        self.session.add(direction)
        await self.session.flush()
        return direction

    async def list_active(self) -> list[Direction]:
        return list(
            await self.session.scalars(
                select(Direction)
                .where(Direction.active.is_(True))
                .order_by(Direction.sort_order, Direction.slug, Direction.id)
            )
        )

    async def set_active(self, direction_id: UUID, active: bool) -> Direction:
        direction = await self.session.scalar(
            select(Direction).where(Direction.id == direction_id).with_for_update()
        )
        if direction is None:
            raise LookupError("Direction not found")
        direction.active = active
        await self.session.flush()
        return direction
