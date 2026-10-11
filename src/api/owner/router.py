from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.owner.auth import get_owner_actor, require_owner_events
from src.api.owner.errors import OwnerRoute
from src.db.session import get_async_session
from src.repositories.directions import DirectionRepository
from src.services.admin.permissions import ROLE_PERMISSIONS, AdminActor

router = APIRouter(prefix="/api/owner", tags=["owner"], route_class=OwnerRoute)


class MeDTO(BaseModel):
    role: str
    permissions: list[str]


class DirectionOptionDTO(BaseModel):
    id: UUID
    name: str


@router.get("/me", response_model=MeDTO)
async def me(actor: Annotated[AdminActor, Depends(get_owner_actor)]) -> MeDTO:
    permissions = sorted(permission.value for permission in ROLE_PERMISSIONS[actor.role])
    return MeDTO(role=actor.role.value, permissions=permissions)


@router.get(
    "/directions",
    response_model=list[DirectionOptionDTO],
    dependencies=[Depends(require_owner_events)],
)
async def directions(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[DirectionOptionDTO]:
    active = await DirectionRepository(session).list_active()
    return [DirectionOptionDTO(id=direction.id, name=direction.name) for direction in active]
