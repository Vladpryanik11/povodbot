"""Owner Mini App sign-in: Telegram-signed initData in `Authorization: tma <initData>`."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_async_session
from src.repositories.admin import AdminRepository
from src.services.admin.permissions import AdminActor, Permission, PermissionService

AUTH_SCHEME = "tma"
MAX_AUTH_AGE = timedelta(hours=24)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Telegram sign-in required",
        headers={"WWW-Authenticate": AUTH_SCHEME},
    )


async def get_owner_actor(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> AdminActor:
    token = get_settings().telegram_token.get_secret_value()
    if not token:
        # An empty bot token makes the HMAC key public: nobody may sign in then.
        raise HTTPException(status_code=503, detail="Telegram sign-in is not configured")
    scheme, _, init_data = (authorization or "").partition(" ")
    init_data = init_data.strip()
    if scheme.lower() != AUTH_SCHEME or not init_data:
        raise _unauthorized()
    try:
        parsed = safe_parse_webapp_init_data(token, init_data)
    except (ValueError, TypeError):  # bad signature, malformed payload, non-ASCII hash
        raise _unauthorized() from None
    if parsed.user is None or datetime.now(UTC) - parsed.auth_date > MAX_AUTH_AGE:
        raise _unauthorized()
    admin = await AdminRepository(session).user_by_telegram_id(parsed.user.id)
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=403, detail="Admin access required")
    return AdminActor.from_model(admin)


async def require_owner_events(
    actor: Annotated[AdminActor, Depends(get_owner_actor)],
) -> AdminActor:
    try:
        PermissionService.require(actor, Permission.MANAGE_EVENTS)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Insufficient admin permissions") from exc
    return actor
