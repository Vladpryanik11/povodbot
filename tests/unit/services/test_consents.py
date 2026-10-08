import pytest
from sqlalchemy import select

from src.models.identity import Consent, ConsentSource, ConsentStatus, ConsentType
from src.repositories.consents import ConsentRepository
from src.repositories.users import UserRepository
from src.services.consents.service import ConsentService
from src.services.users.service import UserService


async def test_consents_are_separate_versioned_append_only_events(db_session):
    user = await UserService(UserRepository(db_session)).upsert_telegram_user(
        1, None, None, None, None
    )
    service = ConsentService(ConsentRepository(db_session))
    assert not await service.is_active(user.id, ConsentType.MARKETING)
    first = await service.record(user.id, ConsentType.PERSONAL_DATA, "v1", ConsentSource.TELEGRAM)
    assert first.text_version == "v1"
    assert first.created_at.tzinfo is not None
    assert await service.is_active(user.id, ConsentType.PERSONAL_DATA)
    assert not await service.is_active(user.id, ConsentType.MARKETING)
    grant = await service.record(user.id, ConsentType.MARKETING, "v2", ConsentSource.TELEGRAM)
    revoked = await service.revoke(user.id, ConsentType.MARKETING, ConsentSource.TELEGRAM)
    assert grant.id != revoked.id
    assert revoked.status == ConsentStatus.REVOKED
    assert revoked.text_version == "v2"
    assert not await service.is_active(user.id, ConsentType.MARKETING)
    assert await service.is_active(user.id, ConsentType.PERSONAL_DATA)
    history = (await db_session.scalars(select(Consent).order_by(Consent.sequence))).all()
    assert len(history) == 3
    assert history[1].status == ConsentStatus.GRANTED


async def test_revoke_without_prior_consent_records_no_invented_version(db_session):
    user = await UserService(UserRepository(db_session)).upsert_telegram_user(
        1, None, None, None, None
    )
    service = ConsentService(ConsentRepository(db_session))
    event = await service.revoke(user.id, ConsentType.MARKETING, ConsentSource.TELEGRAM)
    assert event.text_version is None
    assert not await service.is_active(user.id, ConsentType.MARKETING)


async def test_empty_consent_version_rejected(db_session):
    user = await UserService(UserRepository(db_session)).upsert_telegram_user(
        1, None, None, None, None
    )
    with pytest.raises(ValueError):
        await ConsentService(ConsentRepository(db_session)).record(
            user.id, ConsentType.MARKETING, " ", ConsentSource.TELEGRAM
        )
