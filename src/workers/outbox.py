from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.campaigns import Campaign, CampaignDelivery, CampaignStatus, DeliveryStatus
from src.models.outbox import Outbox
from src.models.payments import Payment
from src.repositories.payments import PaymentRepository
from src.services.crm.segments import SegmentService
from src.services.payments.dtos import PaymentWebhookDTO
from src.services.payments.ports import PaymentGateway, PaymentGatewayError
from src.services.payments.service import (
    REFUNDED_STATUSES,
    REFUNDING_STATUSES,
    PaymentService,
)

OUTBOX_LEASE = timedelta(seconds=60)
MAX_DELIVERY_ATTEMPTS = 5


@dataclass(frozen=True)
class ClaimedOutbox:
    id: UUID
    event_type: str
    payload: dict[str, Any]
    attempts: int


class _OutboxWorker:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def _claim(self, event_type: str) -> ClaimedOutbox | None:
        now = datetime.now(UTC)
        async with self.session_factory() as session, session.begin():
            event = await session.scalar(
                select(Outbox)
                .where(
                    Outbox.event_type == event_type,
                    Outbox.processed_at.is_(None),
                    Outbox.available_at <= now,
                )
                .order_by(Outbox.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                return None
            event.attempts += 1
            event.available_at = now + OUTBOX_LEASE
            await session.flush()
            return ClaimedOutbox(event.id, event.event_type, dict(event.payload), event.attempts)


class CampaignOutboxWorker(_OutboxWorker):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sender: Any,
    ) -> None:
        super().__init__(session_factory)
        self.sender = sender

    @staticmethod
    def _delivery_id(job: ClaimedOutbox) -> UUID:
        value = job.payload.get("delivery_id")
        if not isinstance(value, str):
            raise ValueError("Outbox delivery id is invalid")
        return UUID(value)

    async def _is_eligible_before_send(self, job: ClaimedOutbox) -> bool:
        async with self.session_factory() as session, session.begin():
            delivery = await session.scalar(
                select(CampaignDelivery).where(CampaignDelivery.id == self._delivery_id(job))
            )
            if delivery is None:
                return False
            campaign = await session.get(Campaign, delivery.campaign_id)
            if campaign is None or CampaignStatus(campaign.status) == CampaignStatus.CANCELLED:
                return False
            return await SegmentService(session).is_eligible(delivery.user_id, campaign.audience)

    @staticmethod
    async def _maybe_complete_campaign(session: AsyncSession, campaign: Campaign) -> None:
        if CampaignStatus(campaign.status) not in {
            CampaignStatus.SCHEDULED,
            CampaignStatus.RUNNING,
        }:
            return
        recipients = await SegmentService(session).resolve(campaign.audience)
        if not recipients:
            campaign.status = CampaignStatus.COMPLETED
            return
        terminal_ids = set(
            await session.scalars(
                select(CampaignDelivery.user_id).where(
                    CampaignDelivery.campaign_id == campaign.id,
                    CampaignDelivery.status.in_([DeliveryStatus.SENT, DeliveryStatus.BLOCKED]),
                )
            )
        )
        if all(recipient.user_id in terminal_ids for recipient in recipients):
            campaign.status = CampaignStatus.COMPLETED

    async def _finish(
        self,
        job: ClaimedOutbox,
        *,
        message_id: str | None = None,
        error: str | None = None,
        blocked: bool = False,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            delivery_id = self._delivery_id(job)
            delivery_snapshot = await session.scalar(
                select(CampaignDelivery).where(CampaignDelivery.id == delivery_id)
            )
            campaign = (
                await session.scalar(
                    select(Campaign)
                    .where(Campaign.id == delivery_snapshot.campaign_id)
                    .with_for_update()
                )
                if delivery_snapshot is not None
                else None
            )
            event = await session.scalar(
                select(Outbox).where(Outbox.id == job.id).with_for_update()
            )
            if event is None or event.processed_at is not None:
                return
            delivery = await session.scalar(
                select(CampaignDelivery).where(CampaignDelivery.id == delivery_id).with_for_update()
            )
            if delivery is None:
                event.processed_at = datetime.now(UTC)
                return
            now = datetime.now(UTC)
            if blocked:
                delivery.status = DeliveryStatus.BLOCKED
                delivery.error = "recipient_not_eligible"
                event.processed_at = now
                event.available_at = now
                if campaign is not None:
                    await self._maybe_complete_campaign(session, campaign)
                return
            if error is None:
                delivery.status = DeliveryStatus.SENT
                delivery.provider_message_id = message_id
                delivery.sent_at = now
                event.processed_at = now
                event.available_at = now
                if campaign is not None:
                    await self._maybe_complete_campaign(session, campaign)
                return
            delivery.status = DeliveryStatus.FAILED
            delivery.error = error[:512]
            if job.attempts >= MAX_DELIVERY_ATTEMPTS:
                # Stop an endlessly failing campaign from holding the whole
                # campaign in RUNNING forever; the failure remains auditable.
                delivery.status = DeliveryStatus.BLOCKED
                event.processed_at = now
                event.available_at = now
                if campaign is not None:
                    await self._maybe_complete_campaign(session, campaign)
            else:
                event.available_at = now + timedelta(seconds=min(job.attempts * 30, 300))

    async def process_pending(self, limit: int = 100) -> int:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Outbox limit must be between 1 and 1000")
        delivered = 0
        for _ in range(limit):
            job = await self._claim("campaign.telegram_message")
            if job is None:
                break
            try:
                if not await self._is_eligible_before_send(job):
                    await self._finish(job, blocked=True)
                    continue
                telegram_id = job.payload["telegram_id"]
                text = job.payload["text"]
                if not isinstance(telegram_id, int) or not isinstance(text, str):
                    raise ValueError("Outbox campaign payload is invalid")
                message_id = await self.sender.send_message(telegram_id, text)
            except Exception as exc:  # provider failures are persisted and retried
                await self._finish(job, error=str(exc))
            else:
                await self._finish(job, message_id=message_id)
                delivered += 1
        return delivered


class PaymentRefundOutboxWorker(_OutboxWorker):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: PaymentGateway,
    ) -> None:
        super().__init__(session_factory)
        self.gateway = gateway

    @staticmethod
    def _required_text(job: ClaimedOutbox, key: str) -> str:
        value = job.payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Outbox refund field {key} is invalid")
        return value

    async def _finish(self, job: ClaimedOutbox, provider_status: str, *, reconcile: bool) -> None:
        async with self.session_factory() as session, session.begin():
            event = await session.scalar(
                select(Outbox).where(Outbox.id == job.id).with_for_update()
            )
            if event is None or event.processed_at is not None:
                return
            payment_id = UUID(self._required_text(job, "payment_id"))
            payment = await session.scalar(select(Payment).where(Payment.id == payment_id))
            if payment is None:
                event.processed_at = datetime.now(UTC)
                return
            if reconcile:
                await PaymentService(PaymentRepository(session), self.gateway).apply_webhook(
                    PaymentWebhookDTO(
                        provider_payment_id=self._required_text(job, "provider_payment_id"),
                        provider_status=provider_status,
                        amount_minor=job.payload.get("amount_minor")
                        if isinstance(job.payload.get("amount_minor"), int)
                        else None,
                        event_id=f"refund-outbox:{job.id}",
                        payload={"Status": provider_status},
                    )
                )
            else:
                payment.provider_status = provider_status[:64]
            if provider_status in REFUNDED_STATUSES or provider_status in REFUNDING_STATUSES:
                event.processed_at = datetime.now(UTC)
                event.available_at = datetime.now(UTC)
            else:
                event.processed_at = datetime.now(UTC)

    async def process_pending(self, limit: int = 100) -> int:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Outbox limit must be between 1 and 1000")
        processed = 0
        for _ in range(limit):
            job = await self._claim("payment.refund")
            if job is None:
                break
            try:
                provider_payment_id = self._required_text(job, "provider_payment_id")
                amount = job.payload.get("amount_minor")
                reason = self._required_text(job, "reason")
                if type(amount) is not int or amount <= 0:
                    raise ValueError("Outbox refund amount is invalid")
                state = await self.gateway.get_status(provider_payment_id)
                status = state.provider_status.upper()
                if status not in REFUNDED_STATUSES and status not in REFUNDING_STATUSES:
                    result = await self.gateway.refund(provider_payment_id, amount, reason)
                    status = result.provider_status.upper()
                await self._finish(
                    job,
                    status,
                    reconcile=status in REFUNDED_STATUSES or status in REFUNDING_STATUSES,
                )
            except (PaymentGatewayError, ValueError, KeyError):
                # A lost/ambiguous Cancel response must be reconciled, not
                # blindly retried. T-Bank status lookup is the safe next step.
                await self._finish(job, "REFUND_UNKNOWN", reconcile=False)
            processed += 1
        return processed
