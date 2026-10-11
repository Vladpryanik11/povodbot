"""The Mini App reports that a guest came in through a broadcast's «Открыть вечер» button."""

from fastapi import APIRouter, Response
from pydantic import Field
from sqlalchemy import select

from src.api.guest.favorites import Guest, Session
from src.api.owner.errors import OwnerRoute
from src.api.owner.schemas import OwnerIn
from src.models.campaigns import Campaign, CampaignClick

router = APIRouter(prefix="/api/app", tags=["app"], route_class=OwnerRoute)


class CampaignOpenIn(OwnerIn):
    campaign: str = Field(max_length=12)


@router.post("/campaign-open", status_code=204)
async def campaign_open(body: CampaignOpenIn, session: Session, user: Guest) -> Response:
    campaign = await session.scalar(select(Campaign).where(Campaign.short_code == body.campaign))
    # An unknown or stale code is not the guest's problem: the evening still opens.
    if campaign is not None:
        index = next(
            (i for i, button in enumerate(campaign.buttons) if button.get("kind") == "event"), 0
        )
        session.add(CampaignClick(campaign_id=campaign.id, user_id=user.id, button_index=index))
    return Response(status_code=204)
