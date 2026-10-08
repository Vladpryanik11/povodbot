import asyncio

from aiogram import Bot, Dispatcher

from src.bot.router import create_router
from src.core.config import get_settings


async def run() -> None:
    settings = get_settings()
    token = settings.telegram_token.get_secret_value().strip()
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN is required to run the bot")
    bot = Bot(token)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router())
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
