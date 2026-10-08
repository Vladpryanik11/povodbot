from contextlib import asynccontextmanager

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.app import create_app
from src.db import session as database


async def test_readiness_handles_postgresql_authentication_failure(test_engine, monkeypatch):
    async def authentication_failure(*args, **kwargs):
        raise asyncpg.InvalidPasswordError("sensitive driver details")

    monkeypatch.setattr(database, "get_session_factory", lambda: async_sessionmaker(test_engine))
    # Driver authentication is an external operation; preserve the real session/dependency.
    monkeypatch.setattr(AsyncSession, "execute", authentication_failure)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert "sensitive driver details" not in response.text


async def test_failed_readiness_rolls_back_its_transaction(test_engine, monkeypatch):
    async with test_engine.begin() as connection:
        await connection.execute(text("CREATE TABLE readiness_probe (value INTEGER)"))
    execute = AsyncSession.execute

    async def interrupted_probe(session, statement, *args, **kwargs):
        await execute(session, text("INSERT INTO readiness_probe VALUES (1)"))
        raise SQLAlchemyError("interrupted probe")

    monkeypatch.setattr(database, "get_session_factory", lambda: async_sessionmaker(test_engine))
    monkeypatch.setattr(AsyncSession, "execute", interrupted_probe)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        assert (await client.get("/ready")).status_code == 503
    async with test_engine.begin() as connection:
        result = await connection.execute(text("SELECT COUNT(*) FROM readiness_probe"))
        assert result.scalar_one() == 0
        await connection.execute(text("DROP TABLE readiness_probe"))


async def test_health_returns_ok():
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_app_and_liveness_do_not_initialize_database(monkeypatch):
    def forbid_engine(*args, **kwargs):
        raise AssertionError("Liveness must not initialize the database")

    monkeypatch.setattr(database, "create_async_engine", forbid_engine)
    database.get_engine.cache_clear()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).status_code == 200


async def test_readiness_reports_unreachable_postgresql(monkeypatch):
    engine = create_async_engine(
        "postgresql+asyncpg://dummy:dummy@127.0.0.1:1/povod_test",
        connect_args={"timeout": 1},
    )
    monkeypatch.setattr(database, "get_session_factory", lambda: async_sessionmaker(engine))
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json()["dependencies"]["database"] == "unavailable"
    finally:
        await engine.dispose()


async def test_readiness_reports_database_dependency(test_engine, monkeypatch):
    monkeypatch.setattr(database, "get_session_factory", lambda: async_sessionmaker(test_engine))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "dependencies": {"database": "ok"}}


async def test_readiness_fails_when_database_unavailable(tmp_path, monkeypatch):
    # Missing parent directory causes a real driver connection failure.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'missing' / 'test.db'}")
    monkeypatch.setattr(database, "get_session_factory", lambda: async_sessionmaker(engine))
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "dependencies": {"database": "unavailable"},
        }
        assert str(tmp_path) not in response.text
    finally:
        await engine.dispose()


async def test_session_commits_success_and_rolls_back_failure(test_engine, monkeypatch):
    monkeypatch.setattr(database, "get_session_factory", lambda: async_sessionmaker(test_engine))
    async with test_engine.begin() as connection:
        await connection.execute(text("CREATE TABLE foundation_probe (value INTEGER)"))
    scope = asynccontextmanager(database.get_async_session)
    async with scope() as session:
        await session.execute(text("INSERT INTO foundation_probe VALUES (1)"))
    with pytest.raises(RuntimeError):
        async with scope() as session:
            await session.execute(text("INSERT INTO foundation_probe VALUES (2)"))
            raise RuntimeError("abort")
    async with test_engine.connect() as connection:
        result = await connection.execute(text("SELECT value FROM foundation_probe"))
        assert list(result.scalars()) == [1]
        await connection.execute(text("DROP TABLE foundation_probe"))
        await connection.commit()
