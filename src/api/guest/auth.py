"""Guest Mini App sign-in: the Telegram user behind initData, created on first visit."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.telegram_auth import parse_init_data
from src.models.identity import User
from src.repositories.users import UserRepository


async def get_guest_user(session: AsyncSession, authorization: str | None) -> User:
    telegram_user = parse_init_data(authorization)
    return await UserRepository(session).upsert(
        telegram_user.id,
        telegram_user.first_name,
        telegram_user.last_name,
        telegram_user.username,
        None,
    )
