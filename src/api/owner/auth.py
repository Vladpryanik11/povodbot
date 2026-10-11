"""Owner Mini App sign-in: Telegram-signed initData in `Authorization: tma <initData>`."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.telegram_auth import parse_init_data
from src.db.session import get_async_session
from src.repositories.admin import AdminRepository
from src.services.admin.permissions import AdminActor, Permission, PermissionService


async def get_owner_actor(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> AdminActor:
    telegram_user = parse_init_data(authorization)
    admin = await AdminRepository(session).user_by_telegram_id(telegram_user.id)
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=403, detail="Admin access required")
    return AdminActor.from_model(admin)


def _require(actor: AdminActor, permission: Permission) -> AdminActor:
    try:
        PermissionService.require(actor, permission)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Insufficient admin permissions") from exc
    return actor


async def require_owner_events(
    actor: Annotated[AdminActor, Depends(get_owner_actor)],
) -> AdminActor:
    return _require(actor, Permission.MANAGE_EVENTS)


async def require_owner_campaigns(
    actor: Annotated[AdminActor, Depends(get_owner_actor)],
) -> AdminActor:
    return _require(actor, Permission.MANAGE_CAMPAIGNS)
