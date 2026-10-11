"""Create an admin account: python -m scripts.create_admin --login owner --role owner --telegram-id 123."""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import dispose_engine, get_session_factory
from src.models.admin import AdminRole, AdminUser
from src.repositories.admin import AdminRepository
from src.services.admin.auth import AdminAuthService

MIN_PASSWORD_LENGTH = 12


async def create_admin(
    session: AsyncSession,
    login: str,
    password: str,
    role: AdminRole,
    telegram_id: int | None = None,
) -> AdminUser:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters")
    user = await AdminAuthService(AdminRepository(session)).create_user(login, password, role)
    if telegram_id is not None:
        user.telegram_id = telegram_id
        await session.flush()
    return user


async def run(login: str, password: str, role: AdminRole, telegram_id: int | None) -> None:
    try:
        async with get_session_factory()() as session, session.begin():
            user = await create_admin(session, login, password, role, telegram_id)
    finally:
        await dispose_engine()
    print(f"Created {user.role} {user.login}" + (f" → {telegram_id}" if telegram_id else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", required=True)
    parser.add_argument("--role", choices=[role.value for role in AdminRole], required=True)
    parser.add_argument("--telegram-id", type=int)
    parser.add_argument(
        "--password-stdin", action="store_true", help="read the password from the first stdin line"
    )
    args = parser.parse_args()
    # The password never goes through argv, so it stays out of shell history and `ps`:
    # typed at a hidden prompt, or piped in with --password-stdin for scripted setups.
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("
")
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match")
    try:
        asyncio.run(run(args.login, password, AdminRole(args.role), args.telegram_id))
    except ValueError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
