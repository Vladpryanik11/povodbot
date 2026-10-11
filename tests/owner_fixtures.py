"""Owner Mini App helpers: locally signed Telegram initData, app and admin factories."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from uuid import UUID

import pytest
from fastapi import FastAPI

from src.api.app import create_app
from src.core.config import get_settings
from src.db.session import get_async_session
from src.models.admin import AdminUser

TOKEN = "123:test"


def sign_init_data(user_id: int, auth_date: int | None = None, token: str = TOKEN) -> str:
    """Build Telegram Mini App initData signed exactly as Telegram does it."""
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def owner_headers(user_id: int = 42, auth_date: int | None = None) -> dict[str, str]:
    return {"Authorization": f"tma {sign_init_data(user_id, auth_date)}"}


@pytest.fixture
def owner_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def owner_app(factory) -> FastAPI:
    """Application with a session per request; permission dependencies stay real."""
    app = create_app()

    async def session_dependency():
        async with factory() as session, session.begin():
            yield session

    app.dependency_overrides[get_async_session] = session_dependency
    return app


async def make_admin(
    factory, role: str = "owner", telegram_id: int = 42, is_active: bool = True
) -> UUID:
    async with factory() as session, session.begin():
        admin = AdminUser(
            login=f"{role}-{telegram_id}",
            password_hash="x",
            role=role,
            telegram_id=telegram_id,
            is_active=is_active,
        )
        session.add(admin)
        await session.flush()
        return admin.id
