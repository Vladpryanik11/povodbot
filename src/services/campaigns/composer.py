from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.campaigns import Campaign, CampaignStatus
from src.services.campaigns.content import validate_body
from src.services.campaigns.launch import is_quiet
from src.services.crm.segments import SegmentService


@dataclass(frozen=True)
class CampaignDTO:
    id: UUID
    title: str
    body: str
    status: CampaignStatus
    audience: dict[str, Any]
    scheduled_at: datetime | None


@dataclass(frozen=True)
class CampaignPreviewDTO:
    campaign_id: UUID
    eligible_count: int
    sample_telegram_ids: tuple[int, ...]


def _dto(campaign: Campaign) -> CampaignDTO:
    return CampaignDTO(
        campaign.id,
        campaign.title,
        campaign.body,
        CampaignStatus(campaign.status),
        campaign.audience,
        campaign.scheduled_at,
    )


def _future_schedule(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Campaign schedule must be timezone-aware")
    normalized = value.astimezone(UTC)
    if normalized <= datetime.now(UTC):
        raise ValueError("Campaign schedule must be in the future")
    return normalized


class CampaignService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.segments = SegmentService(session)

    async def create_draft(
        self,
        actor_id: UUID,
        title: str,
        body: str,
        audience: dict[str, Any],
        scheduled_at: datetime | None = None,
    ) -> CampaignDTO:
        if not title.strip() or len(title) > 256:
            raise ValueError("Campaign title is invalid")
        if not body.strip() or len(body) > 4096:
            raise ValueError("Campaign body is invalid")
        if not isinstance(audience, dict):
            raise ValueError("Campaign audience must be an object")
        normalized_scheduled_at = (
            _future_schedule(scheduled_at) if scheduled_at is not None else None
        )
        campaign = Campaign(
            title=title.strip(),
            body=body,
            audience=audience,
            scheduled_at=normalized_scheduled_at,
            created_by=actor_id,
        )
        self.session.add(campaign)
        await self.session.flush()
        return _dto(campaign)

    async def preview(self, campaign_id: UUID) -> CampaignPreviewDTO:
        campaign = await self.session.scalar(select(Campaign).where(Campaign.id == campaign_id))
        if campaign is None:
            raise LookupError("Campaign not found")
        recipients = await self.segments.resolve(campaign.audience)
        return CampaignPreviewDTO(
            campaign.id, len(recipients), tuple(r.telegram_id for r in recipients[:10])
        )

    async def schedule(self, campaign_id: UUID, scheduled_at: datetime) -> CampaignDTO:
        normalized_scheduled_at = _future_schedule(scheduled_at)
        campaign = await self.session.scalar(
            select(Campaign).where(Campaign.id == campaign_id).with_for_update()
        )
        if campaign is None:
            raise LookupError("Campaign not found")
        if CampaignStatus(campaign.status) != CampaignStatus.DRAFT:
            raise ValueError("Only draft campaigns can be scheduled")
        if is_quiet(normalized_scheduled_at):
            raise ValueError("Campaigns are not sent in quiet hours, 22:00-10:00 MSK")
        # Sending is HTML now: a bare < or & would fail at Telegram on every try.
        validate_body(campaign.body, has_image=campaign.image.get("kind") != "none")
        campaign.scheduled_at = normalized_scheduled_at
        campaign.status = CampaignStatus.SCHEDULED
        await self.session.flush()
        return _dto(campaign)
