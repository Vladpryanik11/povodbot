from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import utcnow
from src.models.campaigns import Campaign, CampaignDelivery, CampaignStatus, DeliveryStatus
from src.models.outbox import Outbox
from src.services.campaigns.launch import CampaignLauncher


class TelegramSender(Protocol):
    async def send_message(self, telegram_id: int, text: str) -> str | None: ...


class CampaignDeliveryWorker:
    """Stage campaign messages in the transactional outbox.

    The sender argument remains accepted for compatibility with the first MVP
    service API, but delivery is intentionally performed by the outbox worker
    after this transaction commits.
    """

    def __init__(self, session: AsyncSession, sender: TelegramSender | None = None):
        self.session = session
        self.sender = sender

    async def deliver(
        self, campaign_id: UUID, batch_size: int = 100, now: datetime | None = None
    ) -> int:
        """Freezes a due campaign, then stages its next batch; returns how many were staged."""
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("Batch size must be between 1 and 1000")
        now = now or utcnow()
        campaign = await self.session.scalar(
            select(Campaign).where(Campaign.id == campaign_id).with_for_update()
        )
        if campaign is None:
            raise LookupError("Campaign not found")
        if campaign.status == CampaignStatus.DRAFT:
            raise ValueError("Campaign must be scheduled before delivery")
        if campaign.status == CampaignStatus.SCHEDULED:
            if campaign.scheduled_at is not None and campaign.scheduled_at > now:
                return 0
            await CampaignLauncher(self.session).freeze(campaign, now)
        if campaign.status != CampaignStatus.RUNNING:
            return 0
        deliveries = list(
            await self.session.scalars(
                select(CampaignDelivery)
                .outerjoin(Outbox, Outbox.deduplication_key == CampaignDelivery.idempotency_key)
                .where(
                    CampaignDelivery.campaign_id == campaign.id,
                    CampaignDelivery.status == DeliveryStatus.QUEUED,
                    Outbox.id.is_(None),
                )
                .order_by(CampaignDelivery.id)
                .limit(batch_size)
            )
        )
        for delivery in deliveries:
            self.session.add(
                Outbox(
                    event_type="campaign.telegram_message",
                    deduplication_key=delivery.idempotency_key,
                    payload={
                        "delivery_id": str(delivery.id),
                        "campaign_id": str(campaign.id),
                        "telegram_id": delivery.telegram_id,
                    },
                )
            )
        await self.session.flush()
        return len(deliveries)
