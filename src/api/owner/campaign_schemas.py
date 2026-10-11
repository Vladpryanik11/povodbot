"""Owner API shapes for broadcasts and templates: camelCase JSON, content checked by the service."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.owner.schemas import POSTER_KEY_PREFIX, STALE_FORM, OwnerIn, OwnerOut
from src.models.campaigns import Campaign, CampaignTemplate
from src.models.events import Event
from src.services.campaigns.audience import AudienceFilter
from src.services.campaigns.content import CampaignFieldError
from src.services.media.posters import poster_url


class SendInput(OwnerIn):
    # No time means "now"; a time means "schedule for then".
    at: AwareDatetime | None = None


class CampaignInput(OwnerIn):
    title: str | None = None
    body: str | None = None
    # Shapes and copy are checked by the campaign service, which knows the field messages.
    image: dict[str, Any] | None = None
    buttons: list[Any] | None = None
    event_id: UUID | None = None
    audience: AudienceFilter | None = None

    def values(self) -> dict[str, Any]:
        values = {
            name: getattr(self, name)
            for name in self.model_fields_set
            if name != "updated_at" and (name == "event_id" or getattr(self, name) is not None)
        }
        if self.audience is not None and "audience" in values:
            values["audience"] = self.audience.to_definition()
        return values


class CampaignPatch(CampaignInput):
    updated_at: str

    def expected_updated_at(self) -> datetime:
        try:
            version = datetime.fromisoformat(self.updated_at)
        except ValueError:
            raise CampaignFieldError("updated_at", STALE_FORM) from None
        if version.tzinfo is None:
            raise CampaignFieldError("updated_at", STALE_FORM)
        return version


class ImageOut(OwnerOut):
    kind: str
    ref: str | None = None
    url: str | None = None


class CampaignOut(OwnerOut):
    id: UUID
    title: str
    body: str
    image: ImageOut
    buttons: list[dict[str, Any]]
    event_id: UUID | None
    audience: dict[str, Any]
    status: str
    scheduled_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    recipient_count: int | None
    cancel_reason: str | None
    # Opaque edit version, sent back as is.
    updated_at: str


class CampaignListItem(CampaignOut):
    delivered: int
    clicked: int


class TemplateInput(OwnerIn):
    name: str | None = None
    body: str | None = None
    image_kind: str | None = None
    buttons: list[Any] | None = None

    def values(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.model_fields_set
            if getattr(self, name) is not None
        }


class TemplateOut(OwnerOut):
    id: UUID
    name: str
    body: str
    image_kind: str
    buttons: list[dict[str, Any]]
    is_builtin: bool
    updated_at: str


class SaveAsTemplateInput(OwnerIn):
    name: str


class AudienceCountOut(OwnerOut):
    count: int
    over_limit: int


class CampaignStatsOut(OwnerOut):
    recipients: int
    delivered: int
    failed: int
    failed_reasons: dict[str, int]
    skipped_limit: int
    clicked: int
    anonymous_clicks: int
    bought: int | None


def _cover_url(cover_ref: str | None) -> str | None:
    if not cover_ref:
        return None
    return poster_url(cover_ref) if cover_ref.startswith(POSTER_KEY_PREFIX) else cover_ref


def _image_out(
    image: dict[str, Any], covers: dict[UUID, str | None], event_id: UUID | None
) -> ImageOut:
    kind = image.get("kind", "none")
    if kind == "upload":
        return ImageOut(kind=kind, ref=image["ref"], url=poster_url(image["ref"]))
    if kind == "event" and event_id is not None:
        return ImageOut(kind=kind, url=_cover_url(covers.get(event_id)))
    return ImageOut(kind=kind)


def _fields(campaign: Campaign, covers: dict[UUID, str | None]) -> dict[str, Any]:
    return {
        "id": campaign.id,
        "title": campaign.title,
        "body": campaign.body,
        "image": _image_out(campaign.image, covers, campaign.event_id),
        "buttons": campaign.buttons,
        "event_id": campaign.event_id,
        "audience": campaign.audience,
        "status": campaign.status,
        "scheduled_at": campaign.scheduled_at,
        "started_at": campaign.started_at,
        "finished_at": campaign.finished_at,
        "recipient_count": campaign.recipient_count,
        "cancel_reason": campaign.cancel_reason,
        "updated_at": campaign.updated_at.isoformat(),
    }


async def _covers(session: AsyncSession, campaigns: list[Campaign]) -> dict[UUID, str | None]:
    ids = {c.event_id for c in campaigns if c.event_id and c.image.get("kind") == "event"}
    if not ids:
        return {}
    rows = await session.execute(select(Event.id, Event.cover_ref).where(Event.id.in_(ids)))
    return {event_id: cover_ref for event_id, cover_ref in rows.all()}


async def campaign_out(session: AsyncSession, campaign: Campaign) -> CampaignOut:
    return CampaignOut(**_fields(campaign, await _covers(session, [campaign])))


async def campaign_list(
    session: AsyncSession, campaigns: list[Campaign], counters: dict[UUID, tuple[int, int]]
) -> list[CampaignListItem]:
    covers = await _covers(session, campaigns)
    return [
        CampaignListItem(
            **_fields(campaign, covers),
            delivered=counters[campaign.id][0],
            clicked=counters[campaign.id][1],
        )
        for campaign in campaigns
    ]


def template_out(template: CampaignTemplate) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        body=template.body,
        image_kind=template.image_kind,
        buttons=template.buttons,
        is_builtin=template.is_builtin,
        updated_at=template.updated_at.isoformat(),
    )
