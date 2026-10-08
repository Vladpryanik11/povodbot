import asyncio
from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import get_settings
from src.db.session import get_session_factory
from src.models.campaigns import Campaign, CampaignStatus
from src.repositories.reservations import ReservationRepository
from src.services.campaigns.delivery import CampaignDeliveryWorker
from src.services.payments.tbank_client import TBankPaymentGateway
from src.services.reservations.service import ReservationService
from src.workers.outbox import CampaignOutboxWorker, PaymentRefundOutboxWorker


class AiogramSender:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_message(self, telegram_id: int, text: str) -> str:
        message = await self.bot.send_message(telegram_id, text)
        return str(message.message_id)


async def run_once(
    session_factory: async_sessionmaker[AsyncSession],
    sender: AiogramSender,
    payment_gateway: TBankPaymentGateway,
) -> tuple[int, int]:
    async with session_factory() as session, session.begin():
        released = await ReservationService(ReservationRepository(session)).release_expired(
            datetime.now(UTC), 1_000
        )
    async with session_factory() as session, session.begin():
        campaign_ids = list(
            await session.scalars(
                select(Campaign.id).where(
                    Campaign.status.in_([CampaignStatus.SCHEDULED, CampaignStatus.RUNNING])
                )
            )
        )
        delivered = 0
        for campaign_id in campaign_ids:
            await CampaignDeliveryWorker(session).deliver(campaign_id, batch_size=100)
    delivered += await CampaignOutboxWorker(session_factory, sender).process_pending(100)
    await PaymentRefundOutboxWorker(session_factory, payment_gateway).process_pending(100)
    return released, delivered


async def run() -> None:
    settings = get_settings()
    token = settings.telegram_token.get_secret_value().strip()
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN is required to run workers")
    bot = Bot(token)
    settings = get_settings()
    payment_gateway = TBankPaymentGateway(
        settings.tbank_terminal_key,
        settings.tbank_password,
        api_token=settings.tbank_api_token,
        base_url=settings.tbank_api_base_url,
    )
    try:
        while True:
            await run_once(get_session_factory(), AiogramSender(bot), payment_gateway)
            await asyncio.sleep(1)
    finally:
        await bot.session.close()
        await payment_gateway.aclose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
