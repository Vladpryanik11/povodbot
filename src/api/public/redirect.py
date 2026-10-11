"""Broadcast link buttons point here, so a press is counted before the guest goes on."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.models.campaigns import CampaignClick, CampaignLink

router = APIRouter(tags=["campaigns"])


@router.get("/r/{code}", include_in_schema=False)
async def follow_link(
    code: str, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> RedirectResponse:
    link = await session.get(CampaignLink, code)
    if link is None:
        raise HTTPException(404, "Link not found")
    session.add(
        CampaignClick(campaign_id=link.campaign_id, user_id=None, button_index=link.button_index)
    )
    return RedirectResponse(link.url, status_code=302)
