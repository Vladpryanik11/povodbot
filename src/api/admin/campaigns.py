from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.dependencies import require_permission
from src.db.session import get_async_session
from src.repositories.admin import AdminRepository
from src.services.admin.permissions import AdminActor, Permission
from src.services.audit.service import AuditService
from src.services.campaigns.composer import CampaignPreviewDTO, CampaignService

router = APIRouter(prefix="/api/admin/campaigns", tags=["admin campaigns"])


class CampaignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    body: str
    audience: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: datetime | None = None


class CampaignOutput(BaseModel):
    id: UUID
    title: str
    body: str
    status: str
    audience: dict[str, Any]
    scheduled_at: datetime | None


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled_at: datetime


@router.post("", response_model=CampaignOutput, status_code=201)
async def create_campaign(
    payload: CampaignInput,
    actor: Annotated[AdminActor, Depends(require_permission(Permission.MANAGE_CAMPAIGNS))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CampaignOutput:
    try:
        result = await CampaignService(session).create_draft(
            actor.id, payload.title, payload.body, payload.audience, payload.scheduled_at
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid campaign") from exc
    await AuditService(AdminRepository(session)).record(
        actor.id, "campaign.create", "campaign", result.id
    )
    return CampaignOutput(
        id=result.id,
        title=result.title,
        body=result.body,
        status=result.status,
        audience=result.audience,
        scheduled_at=result.scheduled_at,
    )


@router.get("/{campaign_id}/preview", response_model=CampaignPreviewDTO)
async def preview_campaign(
    campaign_id: UUID,
    actor: Annotated[AdminActor, Depends(require_permission(Permission.MANAGE_CAMPAIGNS))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CampaignPreviewDTO:
    del actor
    try:
        return await CampaignService(session).preview(campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc


@router.post("/{campaign_id}/schedule", response_model=CampaignOutput)
async def schedule_campaign(
    campaign_id: UUID,
    payload: ScheduleInput,
    actor: Annotated[AdminActor, Depends(require_permission(Permission.MANAGE_CAMPAIGNS))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CampaignOutput:
    try:
        result = await CampaignService(session).schedule(campaign_id, payload.scheduled_at)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid campaign schedule") from exc
    await AuditService(AdminRepository(session)).record(
        actor.id, "campaign.schedule", "campaign", result.id
    )
    return CampaignOutput(
        id=result.id,
        title=result.title,
        body=result.body,
        status=result.status,
        audience=result.audience,
        scheduled_at=result.scheduled_at,
    )
