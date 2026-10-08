from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commerce import Order, OrderStatus
from src.models.identity import Consent, ConsentStatus, ConsentType, User


@dataclass(frozen=True)
class UserRecipient:
    user_id: UUID
    telegram_id: int
    first_name: str | None
    username: str | None


class SegmentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _latest_marketing_status(self) -> Any:
        return (
            select(Consent.status)
            .where(
                Consent.user_id == User.id,
                Consent.consent_type == ConsentType.MARKETING,
            )
            .order_by(Consent.sequence.desc())
            .limit(1)
            .scalar_subquery()
        )

    def _eligible_statement(self, definition: dict[str, Any]) -> Any:
        latest_status = self._latest_marketing_status()
        statement = select(User).where(
            User.is_blocked.is_(False), latest_status == ConsentStatus.GRANTED
        )
        telegram_ids = definition.get("telegram_ids")
        if isinstance(telegram_ids, list) and telegram_ids:
            statement = statement.where(User.telegram_id.in_(telegram_ids[:10000]))
        exclude = definition.get("exclude_user_ids")
        if isinstance(exclude, list) and exclude:
            statement = statement.where(~User.id.in_(exclude[:10000]))
        paid = exists(
            select(Order.id).where(Order.user_id == User.id, Order.status == OrderStatus.PAID)
        )
        if definition.get("prior_purchasers") is True:
            statement = statement.where(paid)
        if definition.get("never_purchased") is True:
            statement = statement.where(~paid)
        event_id = definition.get("event_id")
        if event_id is not None:
            statement = statement.where(
                exists(
                    select(Order.id).where(
                        Order.user_id == User.id,
                        Order.event_id == event_id,
                        Order.status == OrderStatus.PAID,
                    )
                )
            )
        return statement.order_by(User.id)

    async def is_eligible(self, user_id: UUID, definition: dict[str, Any] | None = None) -> bool:
        statement = self._eligible_statement(definition or {}).where(User.id == user_id)
        return (
            await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        ) == 1

    async def resolve(self, definition: dict[str, Any]) -> list[UserRecipient]:
        users = list(await self.session.scalars(self._eligible_statement(definition)))
        return [
            UserRecipient(user.id, user.telegram_id, user.first_name, user.username)
            for user in users
        ]
