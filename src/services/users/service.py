from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.repositories.users import UserRepository


@dataclass(frozen=True, repr=False)
class UserDTO:
    id: UUID
    telegram_id: int
    first_name: str | None
    last_name: str | None
    username: str | None
    first_start_param: str | None
    last_start_param: str | None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def upsert_telegram_user(
        self,
        telegram_id: int,
        first_name: str | None,
        last_name: str | None,
        username: str | None,
        start_param: str | None,
    ) -> UserDTO:
        if telegram_id <= 0:
            raise ValueError("Telegram ID must be positive")
        if start_param is not None and len(start_param) > 64:
            raise ValueError("Start parameter must be at most 64 characters")
        user = await self.repository.upsert(
            telegram_id, first_name, last_name, username, start_param or None
        )
        return UserDTO(
            user.id,
            user.telegram_id,
            user.first_name,
            user.last_name,
            user.username,
            user.first_start_param,
            user.last_start_param,
            user.created_at,
            user.updated_at,
            user.last_seen_at,
        )
