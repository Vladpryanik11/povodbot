"""Owner-mode broadcasts before sending: drafts, edits, copies and the picture."""

from __future__ import annotations

import builtins
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.campaigns import (
    Campaign,
    CampaignClick,
    CampaignDelivery,
    CampaignStatus,
    DeliveryStatus,
)
from src.models.events import Event, EventStatus
from src.services.campaigns.audience import AudienceFilter
from src.services.campaigns.content import (
    CampaignFieldError,
    validate_body,
    validate_buttons,
    validate_image,
)

DEFAULT_TITLE = "Новая рассылка"
COPY_SUFFIX = " (копия)"
TITLE_LIMIT = 256
EMPTY_TITLE = "Напиши название рассылки"
EVENT_NOT_PUBLISHED = "Вечер не опубликован"
BAD_IMAGE = "Картинка не загрузилась. Попробуй ещё раз"
STALE = "Рассылку уже изменили в другой вкладке. Обнови страницу"
LOCKED = "Эту рассылку уже не изменить"

EDITABLE = (CampaignStatus.DRAFT, CampaignStatus.SCHEDULED)
SENT = (
    CampaignStatus.RUNNING,
    CampaignStatus.COMPLETED,
    CampaignStatus.STOPPED,
    CampaignStatus.CANCELLED,
)
FIELDS = ("title", "body", "image", "buttons", "event_id", "audience")


class CampaignConflict(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CampaignLocked(Exception):
    message = LOCKED


class OwnerCampaignService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, campaign_id: UUID, *, for_update: bool = False) -> Campaign:
        statement = select(Campaign).where(Campaign.id == campaign_id)
        if for_update:
            statement = statement.with_for_update()
        campaign = await self.session.scalar(statement)
        if campaign is None:
            raise LookupError(campaign_id)
        return campaign

    async def list(self, which: Literal["draft", "scheduled", "sent"]) -> builtins.list[Campaign]:
        statement = select(Campaign)
        if which == "draft":
            statement = statement.where(Campaign.status == CampaignStatus.DRAFT).order_by(
                Campaign.updated_at.desc()
            )
        elif which == "scheduled":
            statement = statement.where(Campaign.status == CampaignStatus.SCHEDULED).order_by(
                Campaign.scheduled_at
            )
        else:
            statement = statement.where(Campaign.status.in_(SENT)).order_by(
                func.coalesce(Campaign.started_at, Campaign.updated_at).desc()
            )
        return list(await self.session.scalars(statement.order_by(Campaign.id)))

    async def counters(self, campaign_ids: builtins.list[UUID]) -> dict[UUID, tuple[int, int]]:
        """(delivered, unique guests who clicked) per campaign."""
        delivered: dict[UUID, int] = {
            campaign_id: count
            for campaign_id, count in (
                await self.session.execute(
                    select(CampaignDelivery.campaign_id, func.count())
                    .where(
                        CampaignDelivery.campaign_id.in_(campaign_ids),
                        CampaignDelivery.status == DeliveryStatus.SENT,
                    )
                    .group_by(CampaignDelivery.campaign_id)
                )
            ).all()
        }
        clicked: dict[UUID, int] = {
            campaign_id: count
            for campaign_id, count in (
                await self.session.execute(
                    select(CampaignClick.campaign_id, func.count(CampaignClick.user_id.distinct()))
                    .where(CampaignClick.campaign_id.in_(campaign_ids))
                    .group_by(CampaignClick.campaign_id)
                )
            ).all()
        }
        return {key: (delivered.get(key, 0), clicked.get(key, 0)) for key in campaign_ids}

    async def create(self, actor_id: UUID | None, data: dict[str, Any]) -> Campaign:
        campaign = Campaign(
            title=DEFAULT_TITLE,
            body="",
            image={"kind": "none"},
            buttons=[],
            audience=AudienceFilter().to_definition(),
            status=CampaignStatus.DRAFT,
            created_by=actor_id,
        )
        await self._apply(campaign, data)
        self.session.add(campaign)
        await self.session.flush()
        return campaign

    async def update(self, campaign_id: UUID, patch: dict[str, Any], updated_at: Any) -> Campaign:
        campaign = await self._editable(campaign_id)
        if campaign.updated_at != updated_at:
            raise CampaignConflict(STALE)
        await self._apply(campaign, patch)
        await self.session.flush()
        return campaign

    async def duplicate(self, campaign_id: UUID, actor_id: UUID | None) -> Campaign:
        source = await self.get(campaign_id)
        # The picture is shared by reference: stored files are never deleted.
        copy = Campaign(
            title=(source.title[: TITLE_LIMIT - len(COPY_SUFFIX)] + COPY_SUFFIX),
            body=source.body,
            image=dict(source.image),
            buttons=list(source.buttons),
            event_id=source.event_id,
            audience=dict(source.audience),
            status=CampaignStatus.DRAFT,
            created_by=actor_id,
        )
        self.session.add(copy)
        await self.session.flush()
        return copy

    async def ensure_editable(self, campaign_id: UUID) -> None:
        await self._editable(campaign_id)

    async def set_image(self, campaign_id: UUID, key: str) -> Campaign:
        campaign = await self._editable(campaign_id)
        if campaign.body:
            validate_body(campaign.body, has_image=True)
        campaign.image = {"kind": "upload", "ref": key}
        campaign.telegram_photo_id = None
        await self.session.flush()
        return campaign

    async def clear_image(self, campaign_id: UUID) -> Campaign:
        campaign = await self._editable(campaign_id)
        campaign.image = {"kind": "none"}
        campaign.telegram_photo_id = None
        await self.session.flush()
        return campaign

    async def _editable(self, campaign_id: UUID) -> Campaign:
        campaign = await self.get(campaign_id, for_update=True)
        if campaign.status not in EDITABLE:
            raise CampaignLocked()
        return campaign

    async def _apply(self, campaign: Campaign, values: dict[str, Any]) -> None:
        """Checks the campaign as it will be after the change; a draft may keep an empty text."""
        unknown = set(values) - set(FIELDS)
        if unknown:
            raise ValueError(f"unknown campaign fields: {sorted(unknown)}")
        title = values.get("title", campaign.title)
        if not isinstance(title, str) or not title.strip():
            raise CampaignFieldError("title", EMPTY_TITLE)
        title = title.strip()[:TITLE_LIMIT]
        event_id = values.get("event_id", campaign.event_id)
        if "event_id" in values and event_id is not None:
            status = await self.session.scalar(select(Event.status).where(Event.id == event_id))
            if status != EventStatus.PUBLISHED:
                raise CampaignFieldError("event_id", EVENT_NOT_PUBLISHED)
        image = validate_image(values.get("image", campaign.image))
        if image["kind"] == "upload" and image != campaign.image:
            # A new picture arrives only through the upload route.
            raise CampaignFieldError("image", BAD_IMAGE)
        if image["kind"] == "event" and event_id is None:
            raise CampaignFieldError("image", "Сначала выбери вечер")
        buttons = validate_buttons(
            values.get("buttons", campaign.buttons), has_event=event_id is not None
        )
        body = values.get("body", campaign.body)
        if not isinstance(body, str):
            raise CampaignFieldError("body", "Напиши текст рассылки")
        if body:
            validate_body(body, has_image=image["kind"] != "none")
        if image != campaign.image or event_id != campaign.event_id:
            campaign.telegram_photo_id = None
        campaign.title = title
        campaign.event_id = event_id
        campaign.image = image
        campaign.buttons = buttons
        campaign.body = body
        if "audience" in values:
            campaign.audience = values["audience"]
