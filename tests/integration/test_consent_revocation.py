import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from src.models.identity import Consent, ConsentSource, ConsentType
from src.repositories.consents import ConsentRepository
from src.repositories.users import UserRepository
from src.services.consents.service import ConsentService
from src.services.users.service import UserService


async def test_revocation_survives_new_sessions_and_preserves_history(pg_factory):
    async with pg_factory() as session, session.begin():
        user = await UserService(UserRepository(session)).upsert_telegram_user(
            1, None, None, None, None
        )
        service = ConsentService(ConsentRepository(session))
        await service.record(user.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM)
        await service.revoke(user.id, ConsentType.MARKETING, ConsentSource.TELEGRAM)
    async with pg_factory() as session, session.begin():
        assert not await ConsentService(ConsentRepository(session)).is_active(
            user.id, ConsentType.MARKETING
        )
        assert len((await session.scalars(select(Consent))).all()) == 2
        # Even tied timestamps cannot undo a later revocation.
        assert (
            await session.scalar(select(Consent).order_by(Consent.sequence.desc()).limit(1))
        ).status == "revoked"


@pytest.mark.parametrize("operation", ["update", "delete", "truncate"])
async def test_database_rejects_mutating_consent_history(db_session, operation):
    user = await UserService(UserRepository(db_session)).upsert_telegram_user(
        1, None, None, None, None
    )
    await ConsentService(ConsentRepository(db_session)).record(
        user.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM
    )
    statements = {
        "update": update(Consent).values(text_version="tampered"),
        "delete": delete(Consent),
        "truncate": text("TRUNCATE consents"),
    }
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(statements[operation])


async def test_stop_command_path_revokes_marketing_even_without_prior_record(pg_factory):
    from src.bot.handlers.settings import SettingsHandler

    async with pg_factory() as session, session.begin():
        user = await UserService(UserRepository(session)).upsert_telegram_user(
            7, None, None, None, None
        )
        await SettingsHandler(ConsentRepository(session)).unsubscribe_marketing(user.id)
    async with pg_factory() as session:
        assert not await ConsentService(ConsentRepository(session)).is_active(
            user.id, ConsentType.MARKETING
        )
