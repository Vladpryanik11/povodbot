from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.identity import Consent, ConsentSource, ConsentStatus, ConsentType, User


class ConsentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_user(self, user_id: UUID) -> None:
        # Serialize grant/revoke operations for one user. Sequence then expresses
        # effective order even when timestamps tie or transactions arrive concurrently.
        user = await self.session.scalar(
            select(User.id).where(User.id == user_id).with_for_update()
        )
        if user is None:
            raise LookupError("User not found")

    async def latest(self, user_id: UUID, consent_type: ConsentType) -> Consent | None:
        result = await self.session.execute(
            select(Consent)
            .where(Consent.user_id == user_id, Consent.consent_type == consent_type)
            .order_by(Consent.sequence.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def append(
        self,
        user_id: UUID,
        consent_type: ConsentType,
        status: ConsentStatus,
        text_version: str | None,
        source: ConsentSource,
    ) -> Consent:
        event = Consent(
            user_id=user_id,
            consent_type=consent_type,
            status=status,
            text_version=text_version,
            source=source,
        )
        self.session.add(event)
        await self.session.flush()
        return event
