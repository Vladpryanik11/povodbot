import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for key in (
        "TELEGRAM_TOKEN",
        "TBANK_TERMINAL_KEY",
        "TBANK_PASSWORD",
        "TBANK_WEBHOOK_SECRET",
        "RESERVATION_TTL_SECONDS",
        "DATABASE_URL",
        "REDIS_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")


@pytest_asyncio.fixture
async def test_engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    # Task 1 has no schema: SELECT 1 requires no persistent data or migrations.
    # CI uses disposable PostgreSQL; local foundation tests need no server.
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    engine = create_async_engine(url)
    try:
        yield engine
    finally:
        await engine.dispose()
