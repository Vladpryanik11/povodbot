import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import Base
from src.models.directions import Direction
from src.models.outbox import Outbox


async def test_migration_matches_models_and_round_trips(pg_factory):
    async with pg_factory() as session:
        engine = session.bind
        async with engine.begin() as connection:

            def check(sync_connection):
                config = Config("alembic.ini")
                config.attributes["connection"] = sync_connection
                context = MigrationContext.configure(sync_connection)
                assert compare_metadata(context, Base.metadata) == []
                command.downgrade(config, "base")
                assert not sync_connection.dialect.has_table(sync_connection, "users")
                command.upgrade(config, "head")
                command.upgrade(config, "head")
                assert (
                    compare_metadata(MigrationContext.configure(sync_connection), Base.metadata)
                    == []
                )

            await connection.run_sync(check)
    async with pg_factory() as session:
        directions = (await session.scalars(select(Direction).order_by(Direction.sort_order))).all()
        assert [(d.slug, d.name) for d in directions] == [
            ("cinema", "Кино"),
            ("books", "Книги"),
            ("workshops", "Мастер-классы"),
        ]
        assert all(d.created_at.tzinfo is not None for d in directions)


async def test_outbox_has_jsonb_and_database_deduplication(db_session):
    db_session.add(Outbox(event_type="test", deduplication_key="one", payload={"count": 1}))
    await db_session.flush()
    event = (await db_session.scalars(select(Outbox))).one()
    assert event.payload == {"count": 1}
    assert event.available_at.tzinfo is not None
    assert event.attempts == 0
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(Outbox(event_type="test", deduplication_key="one", payload={}))
            await db_session.flush()
