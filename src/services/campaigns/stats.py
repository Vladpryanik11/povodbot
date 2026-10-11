"""What a sent broadcast achieved: who got it, who pressed a button, who bought."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.campaigns import Campaign, CampaignClick, CampaignDelivery, DeliveryStatus
from src.models.commerce import Order, OrderEvent, OrderStatus

# A purchase counts for the broadcast within this long after it started.
PURCHASE_WINDOW = timedelta(days=7)
UNKNOWN_REASON = "unknown"


@dataclass(frozen=True)
class CampaignStats:
    recipients: int
    delivered: int
    failed: int
    failed_reasons: dict[str, int]
    skipped_limit: int
    clicked: int
    anonymous_clicks: int
    bought: int | None


async def campaign_stats(session: AsyncSession, campaign_id: UUID) -> CampaignStats:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise LookupError("Campaign not found")
    rows = await session.execute(
        select(CampaignDelivery.status, CampaignDelivery.error, func.count())
        .where(CampaignDelivery.campaign_id == campaign_id)
        .group_by(CampaignDelivery.status, CampaignDelivery.error)
    )
    by_status: dict[str, int] = {}
    failed_reasons: dict[str, int] = {}
    for status, error, count in rows.all():
        by_status[status] = by_status.get(status, 0) + count
        if status in (DeliveryStatus.FAILED, DeliveryStatus.BLOCKED):
            reason = error or UNKNOWN_REASON
            failed_reasons[reason] = failed_reasons.get(reason, 0) + count
    clicked, anonymous = (
        await session.execute(
            select(
                func.count(CampaignClick.user_id.distinct()),
                func.count().filter(CampaignClick.user_id.is_(None)),
            ).where(CampaignClick.campaign_id == campaign_id)
        )
    ).one()
    return CampaignStats(
        recipients=sum(by_status.values()),
        delivered=by_status.get(DeliveryStatus.SENT, 0),
        failed=by_status.get(DeliveryStatus.FAILED, 0) + by_status.get(DeliveryStatus.BLOCKED, 0),
        failed_reasons=failed_reasons,
        skipped_limit=by_status.get(DeliveryStatus.SKIPPED_LIMIT, 0),
        clicked=clicked,
        anonymous_clicks=anonymous,
        bought=await _bought(session, campaign),
    )


async def _bought(session: AsyncSession, campaign: Campaign) -> int | None:
    """Guests who got the message and paid for its evening within the window."""
    if campaign.event_id is None:
        return None
    if campaign.started_at is None:
        return 0
    count = await session.scalar(
        select(func.count(CampaignDelivery.user_id.distinct()))
        .join(Order, Order.user_id == CampaignDelivery.user_id)
        .join(OrderEvent, OrderEvent.order_id == Order.id)
        .where(
            CampaignDelivery.campaign_id == campaign.id,
            CampaignDelivery.status == DeliveryStatus.SENT,
            Order.event_id == campaign.event_id,
            Order.status == OrderStatus.PAID,
            OrderEvent.next_status == OrderStatus.PAID,
            OrderEvent.created_at.between(
                campaign.started_at, campaign.started_at + PURCHASE_WINDOW
            ),
        )
    )
    return count or 0
