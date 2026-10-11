"""Starting a broadcast: readiness, quiet hours, the frozen recipient list, cancel and stop."""

from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.models.campaigns import (
    Campaign,
    CampaignDelivery,
    CampaignLink,
    CampaignStatus,
    DeliveryStatus,
    new_short_code,
)
from src.models.events import Event, EventStatus
from src.models.outbox import Outbox
from src.services.campaigns.audience import audience_count, limited_user_ids
from src.services.campaigns.content import CampaignFieldError, validate_body, validate_buttons
from src.services.campaigns.owner import CampaignLocked, OwnerCampaignService
from src.services.campaigns.render import RenderedMessage, render
from src.services.campaigns.telegram import CampaignSender
from src.services.crm.segments import SegmentService

# Moscow has had no daylight saving since 2014, so a fixed offset needs no tz database.
MSK = timezone(timedelta(hours=3))
QUIET_FROM = time(22, 0)
QUIET_UNTIL = time(10, 0)

PAST = "Это время уже прошло"
QUIET_AT = "С 22:00 до 10:00 не отправляем. Выбери другое время"
NIGHT = "Ночью не отправляем. Отправить в 10:00?"
NO_RECIPIENTS = "Получателей нет"
CANCEL_ONLY_SCHEDULED = "Отменить можно только запланированную рассылку"
STOP_ONLY_RUNNING = "Остановить можно только идущую рассылку"
EVENT_UNPUBLISHED = "event_unpublished"

# Spec §10: the evening was published when the draft was made and is gone by the start.
EVENT_GONE = "Вечер больше не опубликован"


class QuietHours(Exception):
    def __init__(self, suggested_at: datetime):
        super().__init__(NIGHT)
        self.message = NIGHT
        self.suggested_at = suggested_at


def is_quiet(at: datetime) -> bool:
    local = at.astimezone(MSK).time()
    return local >= QUIET_FROM or local < QUIET_UNTIL


def next_morning(at: datetime) -> datetime:
    local = at.astimezone(MSK)
    morning = datetime.combine(local.date(), QUIET_UNTIL, tzinfo=MSK)
    if local >= morning:
        morning += timedelta(days=1)
    return morning.astimezone(UTC)


def _render(
    campaign: Campaign, event: Event | None, links: dict[int, str], settings: Settings, **kw: Any
) -> RenderedMessage:
    return render(
        campaign,
        event,
        links,
        media_root=settings.media_root,
        miniapp_link=settings.miniapp_link,
        public_base_url=settings.public_base_url,
        **kw,
    )


def _check_content(campaign: Campaign) -> None:
    validate_body(campaign.body, has_image=campaign.image.get("kind") != "none")
    validate_buttons(campaign.buttons, has_event=campaign.event_id is not None)


def _unpublished(campaign: Campaign, event: Event | None) -> bool:
    if campaign.event_id is None:
        return False
    return event is None or event.status != EventStatus.PUBLISHED


class CampaignLauncher:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()
        self.campaigns = OwnerCampaignService(session)

    async def send(self, campaign_id: UUID, at: datetime | None, now: datetime) -> Campaign:
        campaign = await self.campaigns.get(campaign_id, for_update=True)
        if campaign.status != CampaignStatus.DRAFT:
            raise CampaignLocked()
        await self._check_ready(campaign, now)
        if at is None:
            if is_quiet(now):
                raise QuietHours(next_morning(now))
            await self.freeze(campaign, now)
            return campaign
        if at <= now:
            raise CampaignFieldError("at", PAST)
        if is_quiet(at):
            raise CampaignFieldError("at", QUIET_AT)
        campaign.status = CampaignStatus.SCHEDULED
        campaign.scheduled_at = at
        await self.session.flush()
        return campaign

    async def _check_ready(self, campaign: Campaign, now: datetime) -> None:
        _check_content(campaign)
        event = await self._event(campaign)
        if _unpublished(campaign, event):
            raise CampaignFieldError("event_id", EVENT_GONE)
        placeholders = {index: "x" for index in range(len(campaign.buttons))}
        _render(campaign, event, placeholders, self.settings)
        sendable, _ = await audience_count(self.session, campaign.audience, now)
        if sendable == 0:
            raise CampaignFieldError("audience", NO_RECIPIENTS)

    async def _event(self, campaign: Campaign) -> Event | None:
        if campaign.event_id is None:
            return None
        return await self.session.get(Event, campaign.event_id)

    async def freeze(self, campaign: Campaign, now: datetime) -> None:
        """Takes the recipient list once; later likes and purchases do not change it."""
        event = await self._event(campaign)
        if _unpublished(campaign, event):
            campaign.status = CampaignStatus.CANCELLED
            campaign.cancel_reason = EVENT_UNPUBLISHED
            campaign.finished_at = now
            await self.session.flush()
            return
        recipients = await SegmentService(self.session).resolve(campaign.audience)
        limited = await limited_user_ids(self.session, [r.user_id for r in recipients], now)
        rows = [
            {
                "campaign_id": campaign.id,
                "user_id": recipient.user_id,
                "telegram_id": recipient.telegram_id,
                "idempotency_key": f"campaign:{campaign.id}:user:{recipient.user_id}",
                "status": DeliveryStatus.SKIPPED_LIMIT
                if recipient.user_id in limited
                else DeliveryStatus.QUEUED,
                "attempts": 0,
            }
            for recipient in recipients
        ]
        if rows:
            await self.session.execute(insert(CampaignDelivery), rows)
        for index, button in enumerate(campaign.buttons):
            if button["kind"] == "url":
                self.session.add(
                    CampaignLink(
                        code=new_short_code(),
                        campaign_id=campaign.id,
                        button_index=index,
                        url=button["url"],
                    )
                )
        campaign.recipient_count = len(recipients)
        campaign.started_at = now
        campaign.status = CampaignStatus.RUNNING
        if len(limited) == len(recipients):
            campaign.status = CampaignStatus.COMPLETED
            campaign.finished_at = now
        await self.session.flush()

    async def cancel(self, campaign_id: UUID) -> Campaign:
        campaign = await self.campaigns.get(campaign_id, for_update=True)
        if campaign.status != CampaignStatus.SCHEDULED:
            raise CampaignLocked(CANCEL_ONLY_SCHEDULED)
        campaign.status = CampaignStatus.CANCELLED
        await self.session.flush()
        return campaign

    async def stop(self, campaign_id: UUID, now: datetime) -> Campaign:
        campaign = await self.campaigns.get(campaign_id, for_update=True)
        if campaign.status != CampaignStatus.RUNNING:
            raise CampaignLocked(STOP_ONLY_RUNNING)
        campaign.status = CampaignStatus.STOPPED
        campaign.finished_at = now
        await self.session.execute(
            update(Outbox)
            .where(
                Outbox.processed_at.is_(None),
                Outbox.deduplication_key.like(f"campaign:{campaign.id}:user:%"),
            )
            .values(processed_at=now)
        )
        await self.session.flush()
        return campaign


async def send_test(
    session: AsyncSession,
    campaign_id: UUID,
    telegram_id: int,
    sender: CampaignSender,
    settings: Settings,
) -> None:
    """The owner sees the message as guests will; nothing is counted or limited."""
    campaign = await OwnerCampaignService(session).get(campaign_id)
    _check_content(campaign)
    event = await session.get(Event, campaign.event_id) if campaign.event_id else None
    message = _render(campaign, event, {}, settings, direct_urls=True)
    await sender.send(telegram_id, message)
