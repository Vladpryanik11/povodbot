from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.models.identity import Consent, ConsentSource, ConsentStatus, ConsentType
from src.repositories.consents import ConsentRepository


@dataclass(frozen=True)
class ConsentDTO:
    id: UUID
    user_id: UUID
    consent_type: ConsentType
    status: ConsentStatus
    text_version: str | None
    source: ConsentSource
    created_at: datetime

    @classmethod
    def from_model(cls, event: Consent) -> "ConsentDTO":
        return cls(
            event.id,
            event.user_id,
            ConsentType(event.consent_type),
            ConsentStatus(event.status),
            event.text_version,
            ConsentSource(event.source),
            event.created_at,
        )


class ConsentService:
    def __init__(self, repository: ConsentRepository):
        self.repository = repository

    async def record(
        self,
        user_id: UUID,
        consent_type: ConsentType,
        text_version: str,
        source: ConsentSource,
    ) -> ConsentDTO:
        if not text_version.strip() or len(text_version) > 128:
            raise ValueError("Consent text version must contain 1 to 128 characters")
        await self.repository.lock_user(user_id)
        return ConsentDTO.from_model(
            await self.repository.append(
                user_id, consent_type, ConsentStatus.GRANTED, text_version, source
            )
        )

    async def is_active(self, user_id: UUID, consent_type: ConsentType) -> bool:
        latest = await self.repository.latest(user_id, consent_type)
        return latest is not None and latest.status == ConsentStatus.GRANTED

    async def latest(self, user_id: UUID, consent_type: ConsentType) -> ConsentDTO | None:
        event = await self.repository.latest(user_id, consent_type)
        return ConsentDTO.from_model(event) if event is not None else None

    async def revoke(
        self,
        user_id: UUID,
        consent_type: ConsentType,
        source: ConsentSource,
    ) -> ConsentDTO:
        await self.repository.lock_user(user_id)
        latest = await self.repository.latest(user_id, consent_type)
        return ConsentDTO.from_model(
            await self.repository.append(
                user_id,
                consent_type,
                ConsentStatus.REVOKED,
                latest.text_version if latest else None,
                source,
            )
        )
