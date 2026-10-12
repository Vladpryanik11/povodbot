from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings, get_settings
from src.models.campaigns import (
    Campaign,
    CampaignDelivery,
    CampaignLink,
    CampaignStatus,
    DeliveryStatus,
)
from src.models.events import Event
from src.models.identity import User
from src.models.outbox import Outbox
from src.models.payments import Payment, PaymentStatus
from src.repositories.payments import PaymentRepository
from src.services.campaigns.render import RenderedMessage, render
from src.services.campaigns.telegram import (
    CampaignSender,
    RecipientBlocked,
    RetryAfter,
    SentMessage,
)
from src.services.crm.segments import SegmentService
from src.services.payments.dtos import PaymentWebhookDTO
from src.services.payments.ports import (
    PaymentGateway,
    PaymentGatewayError,
    PaymentProviderRejected,
)
from src.services.payments.service import (
    REFUNDED_STATUSES,
    REFUNDING_STATUSES,
    PaymentService,
)
from src.services.tickets.delivery import TICKET_ISSUED_EVENT, build_ticket_issued
from src.workers.throttle import Throttle

OUTBOX_LEASE = timedelta(seconds=60)
MAX_DELIVERY_ATTEMPTS = 5
REFUND_MAX_ATTEMPTS = 10
# Why a queued guest got nothing from this job.
DROP = "drop"
NOT_ELIGIBLE = "recipient_not_eligible"
BOT_BLOCKED = "bot_blocked"


def refund_backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2**attempts, 3600))


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

    async def _postpone(self, job: ClaimedOutbox, seconds: float) -> None:
        """Telegram asked the bot to wait: the try does not count, no job of this kind goes out."""
        async with self.session_factory() as session, session.begin():
            event = await session.scalar(
                select(Outbox).where(Outbox.id == job.id).with_for_update()
            )
            if event is None or event.processed_at is not None:
                return
            event.attempts = max(event.attempts - 1, 0)
            until = datetime.now(UTC) + timedelta(seconds=seconds)
            event.available_at = until
            await session.execute(
                update(Outbox)
                .where(
                    Outbox.event_type == job.event_type,
                    Outbox.processed_at.is_(None),
                    Outbox.available_at < until,
                )
                .values(available_at=until)
            )


class CampaignOutboxWorker(_OutboxWorker):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sender: CampaignSender,
        *,
        settings: Settings | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        throttle: Throttle | None = None,
    ) -> None:
        super().__init__(session_factory)
        self.sender = sender
        self.settings = settings or get_settings()
        self.sleep = sleep
        self.throttle = throttle or Throttle(
            self.settings.campaign_rate_limit_per_second, sleep=sleep
        )

    @staticmethod
    def _delivery_id(job: ClaimedOutbox) -> UUID:
        value = job.payload.get("delivery_id")
        if not isinstance(value, str):
            raise ValueError("Outbox delivery id is invalid")
        return UUID(value)

    async def _prepare(self, job: ClaimedOutbox) -> RenderedMessage | str:
        """The message for this guest, or why they get nothing (DROP or NOT_ELIGIBLE)."""
        async with self.session_factory() as session, session.begin():
            delivery = await session.scalar(
                select(CampaignDelivery).where(CampaignDelivery.id == self._delivery_id(job))
            )
            if delivery is None or delivery.status != DeliveryStatus.QUEUED:
                return DROP
            campaign = await session.get(Campaign, delivery.campaign_id)
            if campaign is None or campaign.status != CampaignStatus.RUNNING:
                return DROP
            # The list was frozen at launch; only a block or a revoked consent removes a guest.
            if not await SegmentService(session).is_eligible(delivery.user_id):
                return NOT_ELIGIBLE
            event = await session.get(Event, campaign.event_id) if campaign.event_id else None
            links = await session.execute(
                select(CampaignLink.button_index, CampaignLink.code).where(
                    CampaignLink.campaign_id == campaign.id
                )
            )
            return render(
                campaign,
                event,
                {index: code for index, code in links.all()},
                media_root=self.settings.media_root,
                miniapp_link=self.settings.miniapp_link,
                public_base_url=self.settings.public_base_url,
            )

    @staticmethod
    async def _complete_if_done(session: AsyncSession, campaign: Campaign, now: datetime) -> None:
        if campaign.status != CampaignStatus.RUNNING:
            return
        await session.flush()
        queued = await session.scalar(
            select(func.count())
            .select_from(CampaignDelivery)
            .where(
                CampaignDelivery.campaign_id == campaign.id,
                CampaignDelivery.status == DeliveryStatus.QUEUED,
            )
        )
        if not queued:
            campaign.status = CampaignStatus.COMPLETED
            campaign.finished_at = now

    async def _finish(
        self,
        job: ClaimedOutbox,
        *,
        sent: SentMessage | None = None,
        blocked: str | None = None,
        error: str | None = None,
    ) -> None:
        """Records the outcome; with none given the job is dropped and the guest stays queued."""
        now = datetime.now(UTC)
        async with self.session_factory() as session, session.begin():
            delivery_id = self._delivery_id(job)
            snapshot = await session.scalar(
                select(CampaignDelivery).where(CampaignDelivery.id == delivery_id)
            )
            # The campaign row is locked first so two finishing workers agree on completion.
            campaign = (
                await session.scalar(
                    select(Campaign).where(Campaign.id == snapshot.campaign_id).with_for_update()
                )
                if snapshot is not None
                else None
            )
            event = await session.scalar(
                select(Outbox).where(Outbox.id == job.id).with_for_update()
            )
            if event is None:
                return
            delivery = await session.scalar(
                select(CampaignDelivery).where(CampaignDelivery.id == delivery_id).with_for_update()
            )
            queued = delivery is not None and delivery.status == DeliveryStatus.QUEUED
            # Stopping may close the job while its message is already on the way;
            # a message Telegram accepted is still recorded as sent.
            if event.processed_at is not None and not (sent is not None and queued):
                return
            event.available_at = now
            if delivery is None or not (sent or blocked or error):
                event.processed_at = now
                return
            delivery.attempts = job.attempts
            if error is not None:
                delivery.error = error[:512]
                if job.attempts < MAX_DELIVERY_ATTEMPTS:
                    event.available_at = now + timedelta(seconds=min(job.attempts * 30, 300))
                    return
                delivery.status = DeliveryStatus.FAILED
            elif blocked is not None:
                delivery.status = DeliveryStatus.BLOCKED
                delivery.error = blocked
                if blocked == BOT_BLOCKED:
                    await session.execute(
                        update(User).where(User.id == delivery.user_id).values(is_blocked=True)
                    )
            elif sent is not None:
                delivery.status = DeliveryStatus.SENT
                delivery.provider_message_id = sent.message_id
                delivery.sent_at = now
                delivery.error = None
                if campaign is not None and sent.photo_file_id and not campaign.telegram_photo_id:
                    campaign.telegram_photo_id = sent.photo_file_id
            event.processed_at = now
            if campaign is not None:
                await self._complete_if_done(session, campaign, now)

    async def process_pending(self, limit: int = 100) -> int:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Outbox limit must be between 1 and 1000")
        delivered = 0
        for _ in range(limit):
            job = await self._claim("campaign.telegram_message")
            if job is None:
                break
            try:
                prepared = await self._prepare(job)
                if prepared == DROP:
                    await self._finish(job)
                    continue
                if isinstance(prepared, str):
                    await self._finish(job, blocked=prepared)
                    continue
                telegram_id = job.payload["telegram_id"]
                if not isinstance(telegram_id, int):
                    raise ValueError("Outbox campaign payload is invalid")
                await self.throttle.wait()
                sent = await self.sender.send(telegram_id, prepared)
            except RetryAfter as wait:
                # The pause holds for the whole bot; this loop also releases seats
                # and refunds, so the queue waits in the database, not here.
                await self._postpone(job, wait.seconds)
                break
            except RecipientBlocked:
                await self._finish(job, blocked=BOT_BLOCKED)
            except Exception as exc:  # provider failures are persisted and retried
                await self._finish(job, error=str(exc) or type(exc).__name__)
            else:
                await self._finish(job, sent=sent)
                delivered += 1
        return delivered


class TicketIssuedOutboxWorker(_OutboxWorker):
    """Tells the guest the tickets are theirs; the tickets never depend on this message."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sender: CampaignSender,
    ) -> None:
        super().__init__(session_factory)
        self.sender = sender

    async def _close(self, job: ClaimedOutbox, *, retry: bool = False) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session, session.begin():
            event = await session.scalar(
                select(Outbox).where(Outbox.id == job.id).with_for_update()
            )
            if event is None or event.processed_at is not None:
                return
            if retry and job.attempts < MAX_DELIVERY_ATTEMPTS:
                event.available_at = now + timedelta(seconds=min(30 * 2**job.attempts, 3600))
                return
            event.available_at = now
            event.processed_at = now

    async def process_pending(self, limit: int = 100) -> int:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Outbox limit must be between 1 and 1000")
        delivered = 0
        for _ in range(limit):
            job = await self._claim(TICKET_ISSUED_EVENT)
            if job is None:
                break
            try:
                order_id = UUID(str(job.payload["order_id"]))
            except (KeyError, ValueError):
                # A broken job never gets better; closing it keeps the queue moving.
                await self._close(job)
                continue
            try:
                async with self.session_factory() as session, session.begin():
                    built = await build_ticket_issued(session, order_id)
                if built is None:
                    await self._close(job)
                    continue
                telegram_id, message = built
                await self.sender.send(telegram_id, message)
            except RetryAfter as wait:
                await self._postpone(job, wait.seconds)
                break
            except RecipientBlocked:
                await self._close(job)
            except Exception:  # provider failures are retried with backoff
                await self._close(job, retry=True)
            else:
                await self._close(job)
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

    @staticmethod
    def _payment_id(job: ClaimedOutbox) -> UUID | None:
        try:
            return UUID(str(job.payload["payment_id"]))
        except (KeyError, ValueError):
            return None

    async def _retry(self, job: ClaimedOutbox) -> None:
        """The bank did not answer; the next try starts with GetState, so it never refunds twice."""
        async with self.session_factory() as session, session.begin():
            event = await session.scalar(
                select(Outbox).where(Outbox.id == job.id).with_for_update()
            )
            if event is None or event.processed_at is not None:
                return
            event.available_at = datetime.now(UTC) + refund_backoff(job.attempts)
            payment_id = self._payment_id(job)
            payment = await session.get(Payment, payment_id) if payment_id else None
            if payment is not None and PaymentStatus(payment.status) == PaymentStatus.REFUNDING:
                payment.provider_status = "REFUND_RETRY"

    async def _finish(self, job: ClaimedOutbox, provider_status: str, *, reconcile: bool) -> None:
        """Closes the job; without a refund status from the bank the payment goes to an operator."""
        now = datetime.now(UTC)
        async with self.session_factory() as session, session.begin():
            event = await session.scalar(
                select(Outbox).where(Outbox.id == job.id).with_for_update()
            )
            if event is None or event.processed_at is not None:
                return
            event.processed_at = now
            event.available_at = now
            payment_id = self._payment_id(job)
            payment = await session.get(Payment, payment_id) if payment_id else None
            if payment is None:
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
            elif PaymentStatus(payment.status) == PaymentStatus.REFUNDING:
                # A payment refunded meanwhile by the bank's own notice is left alone.
                payment.provider_status = provider_status[:64]
                payment.status = PaymentStatus.RECONCILIATION_REQUIRED

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
            except PaymentProviderRejected:
                await self._finish(job, "REFUND_REJECTED", reconcile=False)
            except PaymentGatewayError:
                # A lost or failed Cancel is retried later; the retry asks GetState first.
                if job.attempts < REFUND_MAX_ATTEMPTS:
                    await self._retry(job)
                else:
                    await self._finish(job, "REFUND_UNKNOWN", reconcile=False)
            except (ValueError, KeyError):
                await self._finish(job, "REFUND_UNKNOWN", reconcile=False)
            processed += 1
        return processed
