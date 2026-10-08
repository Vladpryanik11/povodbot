from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.campaigns import Campaign, CampaignDelivery, CampaignStatus, DeliveryStatus
from src.models.outbox import Outbox
from src.services.crm.segments import SegmentService


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
        self.segments = SegmentService(session)

    async def deliver(self, campaign_id: UUID, batch_size: int = 100) -> int:
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("Batch size must be between 1 and 1000")
        campaign = await self.session.scalar(
            select(Campaign).where(Campaign.id == campaign_id).with_for_update()
        )
        if campaign is None:
            raise LookupError("Campaign not found")
        if CampaignStatus(campaign.status) in {CampaignStatus.CANCELLED, CampaignStatus.COMPLETED}:
            return 0
        if CampaignStatus(campaign.status) == CampaignStatus.DRAFT:
            raise ValueError("Campaign must be scheduled before delivery")
        if campaign.scheduled_at is not None and campaign.scheduled_at > datetime.now(UTC):
            return 0
        campaign.status = CampaignStatus.RUNNING
        recipients = await self.segments.resolve(campaign.audience)
        completed_ids = set(
            await self.session.scalars(
                select(CampaignDelivery.user_id).where(
                    CampaignDelivery.campaign_id == campaign.id,
                    CampaignDelivery.status.in_([DeliveryStatus.SENT, DeliveryStatus.BLOCKED]),
                )
            )
        )
        pending_recipients = [r for r in recipients if r.user_id not in completed_ids]
        queued = 0
        for recipient in pending_recipients[:batch_size]:
            key = f"campaign:{campaign.id}:user:{recipient.user_id}"
            delivery = await self.session.scalar(
                select(CampaignDelivery)
                .where(CampaignDelivery.idempotency_key == key)
                .with_for_update()
            )
            if delivery is not None and DeliveryStatus(delivery.status) == DeliveryStatus.SENT:
                continue
            if not await self.segments.is_eligible(recipient.user_id, campaign.audience):
                if delivery is None:
                    delivery = CampaignDelivery(
                        campaign_id=campaign.id,
                        user_id=recipient.user_id,
                        telegram_id=recipient.telegram_id,
                        idempotency_key=key,
                        status=DeliveryStatus.BLOCKED,
                        attempts=0,
                    )
                    self.session.add(delivery)
                else:
                    delivery.status = DeliveryStatus.BLOCKED
                continue
            if delivery is None:
                delivery = CampaignDelivery(
                    campaign_id=campaign.id,
                    user_id=recipient.user_id,
                    telegram_id=recipient.telegram_id,
                    idempotency_key=key,
                    status=DeliveryStatus.QUEUED,
                    attempts=0,
                )
                self.session.add(delivery)
                await self.session.flush()
            outbox = await self.session.scalar(
                select(Outbox).where(Outbox.deduplication_key == key).with_for_update()
            )
            if outbox is not None:
                if outbox.processed_at is None:
                    continue
                # A failed delivery whose retry record was completed can be
                # staged again without violating the unique deduplication key.
                outbox.processed_at = None
                outbox.available_at = datetime.now(UTC)
                outbox.payload = {
                    "delivery_id": str(delivery.id),
                    "campaign_id": str(campaign.id),
                    "telegram_id": recipient.telegram_id,
                    "text": campaign.body,
                }
            else:
                self.session.add(
                    Outbox(
                        event_type="campaign.telegram_message",
                        deduplication_key=key,
                        payload={
                            "delivery_id": str(delivery.id),
                            "campaign_id": str(campaign.id),
                            "telegram_id": recipient.telegram_id,
                            "text": campaign.body,
                        },
                    )
                )
            delivery.status = DeliveryStatus.QUEUED
            delivery.error = None
            queued += 1
        await self.session.flush()
        processed = await self.session.scalar(
            select(func.count())
            .select_from(CampaignDelivery)
            .where(
                CampaignDelivery.campaign_id == campaign.id,
                CampaignDelivery.status.in_([DeliveryStatus.SENT, DeliveryStatus.BLOCKED]),
            )
        )
        if not recipients or processed == len(recipients):
            campaign.status = CampaignStatus.COMPLETED
        await self.session.flush()
        return queued
