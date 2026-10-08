from uuid import UUID

from src.models.identity import ConsentSource, ConsentType
from src.repositories.consents import ConsentRepository
from src.services.consents.service import ConsentService


class SettingsHandler:
    """Consent settings boundary used by the bot's /stop and settings commands."""

    def __init__(self, repository: ConsentRepository):
        self.consents = ConsentService(repository)

    async def unsubscribe_marketing(self, user_id: UUID) -> None:
        await self.consents.revoke(user_id, ConsentType.MARKETING, ConsentSource.TELEGRAM)
