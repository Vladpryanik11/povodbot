from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(default="postgresql+asyncpg://localhost:5432/povod", repr=False)
    redis_url: str = Field(default="redis://localhost:6379/0", repr=False)
    telegram_token: SecretStr = SecretStr("")
    tbank_terminal_key: SecretStr = SecretStr("")
    tbank_password: SecretStr = SecretStr("")
    tbank_api_token: SecretStr = SecretStr("")
    tbank_api_base_url: str = "https://securepay.tinkoff.ru/v2"
    tbank_webhook_secret: SecretStr = SecretStr("")
    ticket_qr_secret: SecretStr = SecretStr("")
    reservation_ttl_seconds: int = Field(default=600, gt=0)
    database_pool_size: int = Field(default=5, gt=0)
    database_max_overflow: int = Field(default=10, ge=0)
    database_timeout_seconds: int = Field(default=5, gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    campaign_rate_limit_per_second: int = Field(default=25, gt=0)

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

    @model_validator(mode="after")
    def require_production_secrets(self) -> "Settings":
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
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
