"""Link an admin account to a Telegram user: python -m scripts.link_admin_telegram."""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import dispose_engine, get_session_factory
from src.repositories.admin import AdminRepository


async def link_admin_telegram(session: AsyncSession, login: str, telegram_id: int) -> None:
    admin = await AdminRepository(session).user_by_login(login)
    if admin is None:
        raise LookupError(f"No admin with login {login!r}")
    admin.telegram_id = telegram_id
    await session.flush()


async def run(login: str, telegram_id: int) -> None:
    try:
        async with get_session_factory()() as session, session.begin():
            await link_admin_telegram(session, login, telegram_id)
    finally:
        await dispose_engine()
    print(f"Linked {login} → {telegram_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", required=True)
    parser.add_argument("--telegram-id", required=True, type=int)
    args = parser.parse_args()
    asyncio.run(run(args.login, args.telegram_id))


if __name__ == "__main__":
    main()
