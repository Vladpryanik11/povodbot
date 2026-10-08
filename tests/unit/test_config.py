import pytest
from pydantic import ValidationError

from src.core.config import Settings, get_settings


def test_test_environment_accepts_dummy_secrets():
    settings = Settings(environment="test", telegram_token="dummy", _env_file=None)
    assert settings.telegram_token.get_secret_value() == "dummy"


@pytest.mark.parametrize(
    "field", ["telegram_token", "tbank_terminal_key", "tbank_password", "tbank_webhook_secret"]
)
def test_production_requires_each_secret(field):
    values = dict(
        environment="production",
        telegram_token="fake-token",
        tbank_terminal_key="fake-terminal",
        tbank_password="fake-password",
        tbank_webhook_secret="fake-webhook",
    )
    values[field] = ""
    with pytest.raises(ValidationError):
        Settings(**values, _env_file=None)


def test_production_accepts_explicit_secrets():
    Settings(
        environment="production",
        telegram_token="fake-token",
        tbank_terminal_key="fake-terminal",
        tbank_password="fake-password",
        tbank_webhook_secret="fake-webhook",
        _env_file=None,
    )


def test_ttl_is_parsed_from_environment(monkeypatch):
    monkeypatch.setenv("RESERVATION_TTL_SECONDS", "900")
    assert Settings(_env_file=None).reservation_ttl_seconds == 900


@pytest.mark.parametrize("value", ["oops", "0", "-1"])
def test_invalid_ttl_is_rejected(value):
    with pytest.raises(ValidationError):
        Settings(reservation_ttl_seconds=value, _env_file=None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("database_url", "localhost/db"),
        ("database_url", "postgresql://localhost/db"),
        ("database_url", "postgresql+asyncpg://localhost"),
        ("redis_url", "localhost:6379"),
        ("redis_url", "https://localhost/0"),
        ("database_url", "sqlite+aiosqlite:///test.db"),
    ],
)
def test_invalid_runtime_urls_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_repr_does_not_expose_secrets_or_connection_credentials():
    settings = Settings(
        telegram_token="private-token",
        tbank_terminal_key="private-key",
        tbank_password="private-password",
        tbank_webhook_secret="private-webhook",
        database_url="postgresql+asyncpg://user:private-db@localhost/povod",
        redis_url="redis://:private-redis@localhost:6379/0",
        _env_file=None,
    )
    for value in [
        "private-token",
        "private-key",
        "private-password",
        "private-webhook",
        "private-db",
        "private-redis",
    ]:
        assert value not in repr(settings)


def test_settings_are_cached(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert get_settings() is get_settings()
    get_settings.cache_clear()


def test_structured_logging_hides_configured_secrets(capsys):
    import json

    import structlog

    from src.core.logging import configure_logging

    settings = Settings(telegram_token="fake-private-token", _env_file=None)
    configure_logging(settings)
    structlog.get_logger().info(
        "runtime_started", correlation_id="test-id", token=settings.telegram_token
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "runtime_started"
    assert payload["correlation_id"] == "test-id"
    assert "fake-private-token" not in str(payload)


def test_logging_redacts_nested_secrets_and_connection_credentials(capsys):
    import structlog

    from src.core.logging import configure_logging

    settings = Settings(
        telegram_token="fake-nested-token",
        database_url="postgresql+asyncpg://user:fake-db-password@localhost/povod",
        _env_file=None,
    )
    configure_logging(settings)
    structlog.get_logger().info(
        "safe_event",
        details={"message": "fake-nested-token", "password": "arbitrary-password"},
        notes=["fake-db-password"],
    )
    output = capsys.readouterr().out
    for value in ("fake-nested-token", "fake-db-password", "arbitrary-password"):
        assert value not in output
