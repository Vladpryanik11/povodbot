from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from pydantic import SecretStr

from src.models.admin import AdminRole, AdminUser
from src.repositories.admin import AdminRepository
from src.services.admin.permissions import AdminActor

SESSION_TTL: Final = timedelta(hours=8)
SCRYPT_N: Final = 16_384
SCRYPT_R: Final = 8
SCRYPT_P: Final = 1


def _password_value(password: str | SecretStr) -> str:
    return password.get_secret_value() if isinstance(password, SecretStr) else password


def hash_password(password: str | SecretStr) -> str:
    value = _password_value(password)
    if not value or len(value) > 256:
        raise ValueError("Password must contain 1 to 256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(value.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    encoder = base64.urlsafe_b64encode
    return "$scrypt$16384$8$1$" + encoder(salt).decode() + "$" + encoder(digest).decode()


def verify_password(password: str | SecretStr, encoded: str) -> bool:
    try:
        parts = encoded.split("$")
        if len(parts) != 7 or parts[0] != "":
            return False
        _, algorithm, n, r, p, salt_text, digest_text = parts
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.scrypt(
            _password_value(password).encode(),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


_DUMMY_PASSWORD_HASH = hash_password("povod-auth-dummy-password")


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class AdminSessionDTO:
    token: str
    expires_at: datetime
    actor: AdminActor


class AdminAuthService:
    def __init__(self, repository: AdminRepository):
        self.repository = repository

    async def authenticate(
        self, login: str, password: str | SecretStr, now: datetime | None = None
    ) -> AdminSessionDTO | None:
        if not login or len(login) > 128:
            return None
        current = now or datetime.now(UTC)
        user = await self.repository.user_by_login(login.strip().lower())
        # Always perform the expensive password operation, including for unknown logins.
        encoded_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        password_ok = verify_password(password, encoded_hash)
        if user is None or not user.is_active or not password_ok:
            return None
        token = secrets.token_urlsafe(32)
        expires = current + SESSION_TTL
        await self.repository.add_session(user.id, hash_session_token(token), expires)
        user.last_login_at = current
        await self.repository.session.flush()
        return AdminSessionDTO(token, expires, AdminActor.from_model(user))

    async def create_user(
        self,
        login: str,
        password: str | SecretStr,
        role: AdminRole = AdminRole.ADMINISTRATOR,
    ) -> AdminUser:
        normalized = login.strip().lower()
        if len(normalized) < 3 or len(normalized) > 128:
            raise ValueError("Login must contain 3 to 128 characters")
        user = AdminUser(login=normalized, password_hash=hash_password(password), role=role)
        self.repository.session.add(user)
        await self.repository.session.flush()
        return user

    async def actor_for_token(self, token: str, now: datetime | None = None) -> AdminActor | None:
        if not token:
            return None
        session = await self.repository.session_by_hash(
            hash_session_token(token), now or datetime.now(UTC)
        )
        return AdminActor.from_model(session.admin) if session is not None else None

    async def logout(self, token: str, now: datetime | None = None) -> None:
        await self.repository.revoke_session(hash_session_token(token), now or datetime.now(UTC))
