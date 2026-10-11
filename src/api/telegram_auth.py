"""Telegram Mini App sign-in shared by guests and the owner: `Authorization: tma <initData>`."""

from datetime import UTC, datetime, timedelta

from aiogram.utils.web_app import WebAppUser, safe_parse_webapp_init_data
from fastapi import HTTPException

from src.core.config import get_settings

AUTH_SCHEME = "tma"
MAX_AUTH_AGE = timedelta(hours=24)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Telegram sign-in required",
        headers={"WWW-Authenticate": AUTH_SCHEME},
    )


def parse_init_data(authorization: str | None) -> WebAppUser:
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
    return parsed.user
