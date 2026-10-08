from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.campaigns import Attribution, FunnelEvent


class FunnelEventName(StrEnum):
    START = "start"
    SHOWCASE = "showcase"
    CHECKOUT = "checkout"
    PURCHASE = "purchase"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(UTC)


class AttributionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_start(
        self, user_id: UUID, start_param: str | None, observed_at: datetime
    ) -> Attribution:
        if start_param is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", start_param):
            raise ValueError("Invalid attribution parameter")
        now = _utc(observed_at)
        row = await self.session.scalar(
            select(Attribution).where(Attribution.user_id == user_id).with_for_update()
        )
        if row is None:
            row = Attribution(
                user_id=user_id,
                first_start_param=start_param,
                latest_start_param=start_param,
                first_seen_at=now,
                latest_seen_at=now,
            )
            self.session.add(row)
        else:
            row.latest_start_param = start_param
            row.latest_seen_at = now
        await self.session.flush()
        return row

    async def record_funnel_event(
        self,
        user_id: UUID,
        event: FunnelEventName,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        occurred_at: datetime | None = None,
    ) -> FunnelEvent:
        row = FunnelEvent(
            user_id=user_id,
            event_name=event,
            source=source[:64] if source else None,
            event_metadata={
                str(key)[:64]: value
                for key, value in (metadata or {}).items()
                if isinstance(value, (str, int, float, bool)) or value is None
            },
            occurred_at=_utc(occurred_at or datetime.now(UTC)),
        )
        self.session.add(row)
        await self.session.flush()
        return row
