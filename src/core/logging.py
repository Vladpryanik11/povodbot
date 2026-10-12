import logging
from urllib.parse import unquote, urlsplit

import structlog
from pydantic import SecretStr
from structlog.types import EventDict

from src.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure JSON events; callers must never pass PII or raw provider payloads."""
    configured_secrets = tuple(
        secret.get_secret_value()
        for secret in (
            settings.telegram_token,
            settings.tbank_terminal_key,
            settings.tbank_password,
            settings.tbank_api_token,
            settings.ticket_qr_secret,
        )
        if secret.get_secret_value()
    )

    connection_secrets = tuple(
        form
        for url in (settings.database_url, settings.redis_url)
        if (password := urlsplit(url).password)
        for form in (password, unquote(password))
        if form
    )
    secrets = sorted(set(configured_secrets + connection_secrets), key=len, reverse=True)

    def sanitize(value: object, key: str = "") -> object:
        if isinstance(value, SecretStr) or any(
            part in key.lower() for part in ("token", "secret", "password", "credential")
        ):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(k): sanitize(v, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [sanitize(item) for item in value]
        # Normalize unsupported JSON values before redaction, so JSONRenderer cannot
        # introduce unredacted credentials later through an object's representation.
        if value is not None and not isinstance(value, (str, bool, int, float)):
            value = repr(value)
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[REDACTED]")
        return value

    def redact(_logger: object, _method: str, event: EventDict) -> EventDict:
        return {key: sanitize(value, key) for key, value in event.items()}

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, settings.log_level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
