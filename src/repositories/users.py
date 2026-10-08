from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import utcnow
from src.models.identity import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self,
        telegram_id: int,
        first_name: str | None,
        last_name: str | None,
        username: str | None,
        start_param: str | None,
    ) -> User:
        now = utcnow()
        statement = insert(User).values(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            first_start_param=start_param,
            last_start_param=start_param,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
        )
        upsert = statement.on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "first_name": statement.excluded.first_name,
                "last_name": statement.excluded.last_name,
                "username": statement.excluded.username,
                "last_start_param": func.coalesce(
                    statement.excluded.last_start_param, User.last_start_param
                ),
                "updated_at": now,
                "last_seen_at": now,
            },
        ).returning(User)
        result = await self.session.execute(upsert, execution_options={"populate_existing": True})
        return result.scalar_one()

    async def by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()
