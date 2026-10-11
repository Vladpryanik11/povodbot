from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = Field(default="postgresql+asyncpg://localhost:5432/povod", repr=False)
    redis_url: str = Field(default="redis://localhost:6379/0", repr=False)
    telegram_token: SecretStr = SecretStr("")
    tbank_terminal_key: SecretStr = SecretStr("")
    tbank_password: SecretStr = SecretStr("")
    tbank_api_token: SecretStr = SecretStr("")
    tbank_api_base_url: str = "https://securepay.tinkoff.ru/v2"
    tbank_webhook_secret: SecretStr = SecretStr("")
    ticket_qr_secret: SecretStr = SecretStr("")
    personal_consent_text: str = ""
    personal_consent_version: str = ""
    marketing_consent_text: str = ""
    marketing_consent_version: str = ""
    reservation_ttl_seconds: int = Field(default=600, gt=0)
    database_pool_size: int = Field(default=5, gt=0)
    database_max_overflow: int = Field(default=10, ge=0)
    database_timeout_seconds: int = Field(default=5, gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    campaign_rate_limit_per_second: int = Field(default=25, gt=0)
    media_root: Path = Path("media")
    miniapp_url: str = ""

    @field_validator("database_url", "redis_url")
    @classmethod
    def validate_url(cls, value: str, info: ValidationInfo) -> str:
        try:
            parsed = urlsplit(value)
            _ = parsed.port
            schemes = (
                {"postgresql+asyncpg"} if info.field_name == "database_url" else {"redis", "rediss"}
            )
            if (
                parsed.scheme not in schemes
                or not parsed.hostname
                or any(c.isspace() for c in value)
            ):
                raise ValueError
            if info.field_name == "database_url" and parsed.path in {"", "/"}:
                raise ValueError
        except ValueError:
            raise ValueError(
                "Expected an absolute runtime URL with a valid host and database"
            ) from None
        return value

    @field_validator("miniapp_url")
    @classmethod
    def validate_miniapp_url(cls, value: str) -> str:
        """Empty keeps the bot a plain chat menu; otherwise Telegram needs an https address."""
        value = value.strip()
        if not value:
            return ""
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or any(c.isspace() for c in value):
            raise ValueError("miniapp_url must be an absolute https:// address")
        return value

    @property
    def hardened(self) -> bool:
        """Staging is a real server with real users: production-grade security, no payments."""
        return self.environment in {"staging", "production"}

    @model_validator(mode="after")
    def require_production_secrets(self) -> "Settings":
        if self.environment == "staging":
            for name in ("telegram_token", "ticket_qr_secret"):
                if not getattr(self, name).get_secret_value().strip():
                    raise ValueError(f"{name} is required in staging")
        if self.environment == "production":
            for name in (
                "telegram_token",
                "tbank_terminal_key",
                "tbank_password",
                "tbank_webhook_secret",
                "ticket_qr_secret",
            ):
                if not getattr(self, name).get_secret_value().strip():
                    raise ValueError(f"{name} is required in production")
            for name in (
                "personal_consent_text",
                "personal_consent_version",
                "marketing_consent_text",
                "marketing_consent_version",
            ):
                value = getattr(self, name).strip()
                if not value or value.lower().startswith("draft"):
                    raise ValueError(f"{name} must be approved in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
