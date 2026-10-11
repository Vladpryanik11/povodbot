"""Who an owner broadcast reaches: the filter the screen sends, and the weekly limit."""

from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.campaigns import CampaignDelivery, DeliveryStatus
from src.services.crm.segments import SegmentService

WEEKLY_LIMIT = 2
LIMIT_WINDOW = timedelta(days=7)
CHUNK = 10000


class _Filter(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class AudienceEvent(_Filter):
    id: UUID
    relation: Literal["going", "liked", "liked_not_bought", "attended"]


class AudienceFilter(_Filter):
    event: AudienceEvent | None = None
    direction_id: UUID | None = None
    purchases: Literal["any", "bought", "never"] = "any"

    def to_definition(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


async def limited_user_ids(session: AsyncSession, user_ids: list[UUID], now: datetime) -> set[UUID]:
    """Guests who already got the weekly maximum of broadcasts."""
    limited: set[UUID] = set()
    for start in range(0, len(user_ids), CHUNK):
        chunk = user_ids[start : start + CHUNK]
        rows = await session.scalars(
            select(CampaignDelivery.user_id)
            .where(
                CampaignDelivery.user_id.in_(chunk),
                CampaignDelivery.status == DeliveryStatus.SENT,
                CampaignDelivery.sent_at > now - LIMIT_WINDOW,
            )
            .group_by(CampaignDelivery.user_id)
            .having(func.count() >= WEEKLY_LIMIT)
        )
        limited.update(rows)
    return limited


async def audience_count(
    session: AsyncSession, definition: dict[str, Any], now: datetime
) -> tuple[int, int]:
    """(will receive, cut by the weekly limit)."""
    recipients = await SegmentService(session).resolve(definition)
    limited = await limited_user_ids(session, [r.user_id for r in recipients], now)
    return len(recipients) - len(limited), len(limited)
