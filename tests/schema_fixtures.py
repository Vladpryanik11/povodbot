"""Real PostgreSQL schemas, migrated and isolated per test; never SQLite."""

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def pg_factory(test_engine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if test_engine.dialect.name != "postgresql":
        raise RuntimeError("Task 2 tests require disposable PostgreSQL via TEST_DATABASE_URL")
    schema = "task2_" + uuid.uuid4().hex
    async with test_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        test_engine.url,
        connect_args={"server_settings": {"search_path": schema + ",public", "timezone": "UTC"}},
        hide_parameters=True,
    )
    try:
        from alembic import command
        from alembic.config import Config

        def migrate(connection):
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with test_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest_asyncio.fixture
async def db_session(pg_factory) -> AsyncIterator[AsyncSession]:
    async with pg_factory() as session, session.begin():
        yield session
