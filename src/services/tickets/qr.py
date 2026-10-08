from __future__ import annotations

import base64
import hashlib
import hmac
from uuid import UUID

from pydantic import SecretStr

from src.core.config import get_settings


class InvalidQrToken(ValueError):
    pass


class QrTokenService:
    def __init__(self, secret: str | SecretStr | None = None):
        if secret is None:
            settings = get_settings()
            secret = (
                settings.ticket_qr_secret.get_secret_value()
                or settings.tbank_password.get_secret_value()
            )
        self.secret = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
        if not self.secret:
            if get_settings().environment == "production":
                raise ValueError("TICKET_QR_SECRET is required in production")
            self.secret = hashlib.sha256(b"povod-development-qr-key").hexdigest()

    def generate(self, ticket_id: UUID) -> str:
        payload = base64.urlsafe_b64encode(ticket_id.bytes).decode().rstrip("=")
        signature = hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).digest()[:24]
        encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return f"pv1.{payload}.{encoded_signature}"

    def ticket_id(self, token: str) -> UUID:
        try:
            version, payload, signature = token.split(".", 2)
            if version != "pv1":
                raise InvalidQrToken("Unsupported QR token")
            expected = hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).digest()[
                :24
            ]
            supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
            if not hmac.compare_digest(expected, supplied):
                raise InvalidQrToken("Invalid QR token")
            raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            return UUID(bytes=raw)
        except (ValueError, TypeError) as exc:
            raise InvalidQrToken("Invalid QR token") from exc

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
