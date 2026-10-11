from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commerce import Order, OrderStatus
from src.models.events import Event
from src.models.favorites import Favorite
from src.models.identity import Consent, ConsentStatus, ConsentType, User
from src.models.tickets import Ticket, TicketStatus

# A ticket that still lets the guest in, or already did.
VALID_TICKET = (TicketStatus.ISSUED, TicketStatus.CHECKED_IN)


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
        # No marketing record yet means "not opted out": everyone but /stop gets mail.
        statement = select(User).where(
            User.is_blocked.is_(False),
            or_(latest_status.is_(None), latest_status != ConsentStatus.REVOKED),
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
        return self._audience_filter(statement, definition, paid).order_by(User.id)

    def _audience_filter(self, statement: Any, definition: dict[str, Any], paid: Any) -> Any:
        """Owner-mode keys: event relation, direction and purchases; unknown values fail closed."""
        event = definition.get("event")
        if event is not None:
            statement = statement.where(_event_relation(UUID(str(event["id"])), event["relation"]))
        direction_id = definition.get("directionId")
        if direction_id is not None:
            in_direction = select(Event.id).where(Event.direction_id == UUID(str(direction_id)))
            statement = statement.where(
                or_(
                    exists(_tickets().where(Ticket.event_id.in_(in_direction))),
                    exists(_likes().where(Favorite.event_id.in_(in_direction))),
                )
            )
        purchases = definition.get("purchases", "any")
        if purchases == "bought":
            statement = statement.where(paid)
        elif purchases == "never":
            statement = statement.where(~paid)
        elif purchases not in ("any", None):
            raise ValueError(f"unknown purchases filter: {purchases!r}")
        return statement

    async def count(self, definition: dict[str, Any]) -> int:
        statement = self._eligible_statement(definition).with_only_columns(User.id)
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        return total or 0

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


def _tickets(*statuses: str) -> Any:
    return (
        select(Ticket.id)
        .join(Order, Order.id == Ticket.order_id)
        .where(Order.user_id == User.id, Ticket.status.in_(statuses or VALID_TICKET))
    )


def _likes() -> Any:
    return select(Favorite.event_id).where(Favorite.user_id == User.id)


def _event_relation(event_id: UUID, relation: str) -> Any:
    liked = exists(_likes().where(Favorite.event_id == event_id))
    if relation == "going":
        return exists(_tickets().where(Ticket.event_id == event_id))
    if relation == "attended":
        return exists(_tickets(TicketStatus.CHECKED_IN).where(Ticket.event_id == event_id))
    if relation == "liked":
        return liked
    if relation == "liked_not_bought":
        bought = exists(
            select(Order.id).where(
                Order.user_id == User.id,
                Order.event_id == event_id,
                Order.status == OrderStatus.PAID,
            )
        )
        return liked & ~bought
    raise ValueError(f"unknown event relation: {relation!r}")
