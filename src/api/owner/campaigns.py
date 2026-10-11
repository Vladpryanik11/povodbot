"""Owner Mini App broadcasts before sending: drafts, picture, audience count and templates."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from aiogram import Bot
from fastapi import Depends, File, Query, Response, UploadFile
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.api.owner.auth import require_owner_campaigns
from src.api.owner.campaign_schemas import (
    AudienceCountOut,
    CampaignInput,
    CampaignListItem,
    CampaignOut,
    CampaignPatch,
    SaveAsTemplateInput,
    SendInput,
    TemplateInput,
    TemplateOut,
    campaign_list,
    campaign_out,
    template_out,
)
from src.api.owner.errors import OwnerApiError
from src.api.owner.posters import UPLOAD_BUSY, upload_lock
from src.api.owner.router import router
from src.core.config import get_settings
from src.db.session import get_async_session
from src.models.admin import AdminUser
from src.models.base import utcnow
from src.repositories.admin import AdminRepository
from src.services.admin.permissions import AdminActor
from src.services.audit.service import AuditService
from src.services.campaigns.audience import AudienceFilter, audience_count
from src.services.campaigns.content import CampaignFieldError
from src.services.campaigns.launch import CampaignLauncher, QuietHours, send_test
from src.services.campaigns.owner import CampaignConflict, CampaignLocked, OwnerCampaignService
from src.services.campaigns.render import CampaignNotReady
from src.services.campaigns.telegram import (
    AiogramCampaignSender,
    CampaignSender,
    RecipientBlocked,
    RetryAfter,
)
from src.services.campaigns.templates import TemplateLocked, TemplateService
from src.services.media.posters import MAX_BYTES, PosterError, store_image

CAMPAIGN_NOT_FOUND = "Рассылка не найдена"
TEMPLATE_NOT_FOUND = "Шаблон не найден"
REJECTED = "Так изменить рассылку нельзя"
BOT_BLOCKED = "Бот не может тебе написать. Открой бота и нажми «Старт»"
TELEGRAM_BUSY = "Telegram просит подождать. Попробуй через минуту"
IMAGE_MIN_SIZE = (320, 320)

Actor = Annotated[AdminActor, Depends(require_owner_campaigns)]
Session = Annotated[AsyncSession, Depends(get_async_session)]


@contextmanager
def campaign_errors(not_found: str = CAMPAIGN_NOT_FOUND) -> Iterator[None]:
    """Campaign and template service failures become the Mini App's error bodies."""
    try:
        yield
    except QuietHours as error:
        body = {"field": "at", "message": error.message}
        raise OwnerApiError(422, body | {"suggestedAt": error.suggested_at.isoformat()}) from error
    except CampaignNotReady as error:
        raise OwnerApiError(422, {"message": error.message}) from error
    except CampaignFieldError as error:
        field = to_camel(error.field)
        raise OwnerApiError(422, {"field": field, "message": error.message}) from error
    except CampaignConflict as error:
        raise OwnerApiError(409, {"message": error.message}) from error
    except CampaignLocked as error:
        raise OwnerApiError(422, {"message": error.message}) from error
    except TemplateLocked as error:
        raise OwnerApiError(403, {"message": error.message}) from error
    except LookupError as error:
        raise OwnerApiError(404, {"message": not_found}) from error
    except ValueError as error:
        raise OwnerApiError(422, {"message": REJECTED}) from error


async def audit(
    session: AsyncSession,
    actor: AdminActor,
    action: str,
    object_id: UUID,
    metadata: dict[str, object] | None = None,
) -> None:
    kind = action.split(".")[0]
    await AuditService(AdminRepository(session)).record(
        actor.id,
        f"owner.{action}",
        "campaign" if kind == "campaign" else "campaign_template",
        object_id,
        metadata,
    )


@router.get("/campaigns", response_model=list[CampaignListItem])
async def list_campaigns(
    _: Actor,
    session: Session,
    which: Annotated[Literal["draft", "scheduled", "sent"], Query(alias="filter")] = "draft",
) -> list[CampaignListItem]:
    service = OwnerCampaignService(session)
    campaigns = await service.list(which)
    counters = await service.counters([campaign.id for campaign in campaigns])
    return await campaign_list(session, campaigns, counters)


@router.post("/campaigns/audience-count", response_model=AudienceCountOut)
async def count_audience(body: AudienceFilter, _: Actor, session: Session) -> AudienceCountOut:
    count, over_limit = await audience_count(session, body.to_definition(), utcnow())
    return AudienceCountOut(count=count, over_limit=over_limit)


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: UUID, _: Actor, session: Session) -> CampaignOut:
    with campaign_errors():
        campaign = await OwnerCampaignService(session).get(campaign_id)
    return await campaign_out(session, campaign)


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(body: CampaignInput, actor: Actor, session: Session) -> CampaignOut:
    with campaign_errors():
        campaign = await OwnerCampaignService(session).create(actor.id, body.values())
    await audit(session, actor, "campaign.create", campaign.id)
    return await campaign_out(session, campaign)


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: UUID, body: CampaignPatch, actor: Actor, session: Session
) -> CampaignOut:
    with campaign_errors():
        expected = body.expected_updated_at()
        campaign = await OwnerCampaignService(session).update(campaign_id, body.values(), expected)
    await audit(session, actor, "campaign.update", campaign.id)
    return await campaign_out(session, campaign)


@router.post("/campaigns/{campaign_id}/duplicate", response_model=CampaignOut, status_code=201)
async def duplicate_campaign(campaign_id: UUID, actor: Actor, session: Session) -> CampaignOut:
    with campaign_errors():
        campaign = await OwnerCampaignService(session).duplicate(campaign_id, actor.id)
    await audit(session, actor, "campaign.duplicate", campaign.id, {"source": str(campaign_id)})
    return await campaign_out(session, campaign)


@router.post("/campaigns/{campaign_id}/image", response_model=CampaignOut)
async def upload_campaign_image(
    campaign_id: UUID, file: Annotated[UploadFile, File()], actor: Actor, session: Session
) -> CampaignOut:
    service = OwnerCampaignService(session)
    lock = upload_lock(actor.id)
    if lock.locked():
        raise OwnerApiError(429, {"message": UPLOAD_BUSY})
    async with lock:
        with campaign_errors():
            await service.ensure_editable(campaign_id)
        # One byte over the limit is enough for store_image to answer 413.
        data = await file.read(MAX_BYTES + 1)
        try:
            stored = await run_in_threadpool(
                store_image, data, get_settings().media_root, "campaigns", IMAGE_MIN_SIZE
            )
        except PosterError as error:
            raise OwnerApiError(
                error.status, {"field": "image", "message": error.message}
            ) from error
        with campaign_errors():
            campaign = await service.set_image(campaign_id, stored.key)
    await audit(session, actor, "campaign.image", campaign.id, {"key": stored.key})
    return await campaign_out(session, campaign)


@router.delete("/campaigns/{campaign_id}/image", response_model=CampaignOut)
async def clear_campaign_image(campaign_id: UUID, actor: Actor, session: Session) -> CampaignOut:
    with campaign_errors():
        campaign = await OwnerCampaignService(session).clear_image(campaign_id)
    await audit(session, actor, "campaign.image_clear", campaign.id)
    return await campaign_out(session, campaign)


async def campaign_sender() -> AsyncIterator[CampaignSender]:
    """The real Telegram sender for "send to myself"; tests replace this dependency."""
    bot = Bot(get_settings().telegram_token.get_secret_value())
    try:
        yield AiogramCampaignSender(bot)
    finally:
        await bot.session.close()


Sender = Annotated[CampaignSender, Depends(campaign_sender)]


@router.post("/campaigns/{campaign_id}/send", response_model=CampaignOut)
async def send_campaign(
    campaign_id: UUID, body: SendInput, actor: Actor, session: Session
) -> CampaignOut:
    with campaign_errors():
        campaign = await CampaignLauncher(session).send(campaign_id, body.at, utcnow())
    if body.at is None:
        await audit(session, actor, "campaign.start", campaign.id)
    else:
        await audit(session, actor, "campaign.schedule", campaign.id, {"at": body.at.isoformat()})
    return await campaign_out(session, campaign)


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignOut)
async def cancel_campaign(campaign_id: UUID, actor: Actor, session: Session) -> CampaignOut:
    with campaign_errors():
        campaign = await CampaignLauncher(session).cancel(campaign_id)
    await audit(session, actor, "campaign.cancel", campaign.id)
    return await campaign_out(session, campaign)


@router.post("/campaigns/{campaign_id}/stop", response_model=CampaignOut)
async def stop_campaign(campaign_id: UUID, actor: Actor, session: Session) -> CampaignOut:
    with campaign_errors():
        campaign = await CampaignLauncher(session).stop(campaign_id, utcnow())
    await audit(session, actor, "campaign.stop", campaign.id)
    return await campaign_out(session, campaign)


@router.post("/campaigns/{campaign_id}/test", status_code=204)
async def test_campaign(
    campaign_id: UUID, actor: Actor, session: Session, sender: Sender
) -> Response:
    admin = await session.get(AdminUser, actor.id)
    if admin is None or admin.telegram_id is None:
        raise OwnerApiError(422, {"message": BOT_BLOCKED})
    with campaign_errors():
        try:
            await send_test(session, campaign_id, admin.telegram_id, sender, get_settings())
        except RecipientBlocked as error:
            raise OwnerApiError(422, {"message": BOT_BLOCKED}) from error
        except RetryAfter as error:
            raise OwnerApiError(429, {"message": TELEGRAM_BUSY}) from error
    await audit(session, actor, "campaign.test", campaign_id)
    return Response(status_code=204)


@router.post(
    "/campaigns/{campaign_id}/save-as-template", response_model=TemplateOut, status_code=201
)
async def save_as_template(
    campaign_id: UUID, body: SaveAsTemplateInput, actor: Actor, session: Session
) -> TemplateOut:
    with campaign_errors():
        template = await TemplateService(session).from_campaign(campaign_id, actor.id, body.name)
    await audit(
        session, actor, "template.from_campaign", template.id, {"campaign": str(campaign_id)}
    )
    return template_out(template)


@router.get("/campaign-templates", response_model=list[TemplateOut])
async def list_templates(_: Actor, session: Session) -> list[TemplateOut]:
    return [template_out(template) for template in await TemplateService(session).list()]


@router.post("/campaign-templates", response_model=TemplateOut, status_code=201)
async def create_template(body: TemplateInput, actor: Actor, session: Session) -> TemplateOut:
    with campaign_errors(TEMPLATE_NOT_FOUND):
        template = await TemplateService(session).create(actor.id, body.values())
    await audit(session, actor, "template.create", template.id)
    return template_out(template)


@router.patch("/campaign-templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: UUID, body: TemplateInput, actor: Actor, session: Session
) -> TemplateOut:
    with campaign_errors(TEMPLATE_NOT_FOUND):
        template = await TemplateService(session).update(template_id, body.values())
    await audit(session, actor, "template.update", template.id)
    return template_out(template)


@router.delete("/campaign-templates/{template_id}", status_code=204)
async def delete_template(template_id: UUID, actor: Actor, session: Session) -> Response:
    with campaign_errors(TEMPLATE_NOT_FOUND):
        await TemplateService(session).delete(template_id)
    await audit(session, actor, "template.delete", template_id)
    return Response(status_code=204)
