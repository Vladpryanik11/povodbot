"""Guest likes kept on the server: `Authorization: tma <initData>`, camelCase JSON."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.guest.auth import get_guest_user
from src.api.owner.errors import OwnerApiError, OwnerRoute
from src.api.owner.schemas import OwnerIn, OwnerOut
from src.db.session import get_async_session
from src.models.events import Event, EventStatus
from src.models.identity import User
from src.repositories.favorites import FavoriteRepository

MAX_IMPORT = 200

router = APIRouter(prefix="/api/app/favorites", tags=["app"], route_class=OwnerRoute)

Session = Annotated[AsyncSession, Depends(get_async_session)]


async def guest(
    session: Session, authorization: Annotated[str | None, Header()] = None
) -> User:
    return await get_guest_user(session, authorization)


Guest = Annotated[User, Depends(guest)]


class FavoritesOut(OwnerOut):
    event_ids: list[UUID]


class FavoritesImportIn(OwnerIn):
    event_ids: list[UUID] = Field(max_length=MAX_IMPORT)


async def _listed(session: AsyncSession, user: User) -> FavoritesOut:
    return FavoritesOut(event_ids=await FavoriteRepository(session).list_ids(user.id))


@router.get("", response_model=FavoritesOut)
async def list_favorites(session: Session, user: Guest) -> FavoritesOut:
    return await _listed(session, user)


@router.put("/{event_id}", status_code=204)
async def add_favorite(event_id: UUID, session: Session, user: Guest) -> Response:
    event = await session.get(Event, event_id)
    if event is None or EventStatus(event.status) != EventStatus.PUBLISHED:
        raise OwnerApiError(404, {"message": "Вечер не найден"})
    await FavoriteRepository(session).add(user.id, event_id)
    return Response(status_code=204)


@router.delete("/{event_id}", status_code=204)
async def remove_favorite(event_id: UUID, session: Session, user: Guest) -> Response:
    await FavoriteRepository(session).remove(user.id, event_id)
    return Response(status_code=204)


@router.post("/import", response_model=FavoritesOut)
async def import_favorites(
    payload: FavoritesImportIn, session: Session, user: Guest
) -> FavoritesOut:
    await FavoriteRepository(session).import_ids(user.id, payload.event_ids)
    return await _listed(session, user)
