import pytest
from pydantic import ValidationError

from src.core.config import Settings, get_settings


def test_test_environment_accepts_dummy_secrets():
    settings = Settings(environment="test", telegram_token="dummy", _env_file=None)
    assert settings.telegram_token.get_secret_value() == "dummy"


@pytest.mark.parametrize(
    "field",
    [
        "telegram_token",
        "tbank_terminal_key",
        "tbank_password",
        "ticket_qr_secret",
    ],
)
def test_production_requires_each_secret(field):
    values = dict(
        environment="production",
        telegram_token="fake-token",
        tbank_terminal_key="fake-terminal",
        tbank_password="fake-password",
        ticket_qr_secret="fake-qr-secret",
        personal_consent_text="Approved personal data consent",
        personal_consent_version="legal-v1",
        marketing_consent_text="Approved marketing consent",
        marketing_consent_version="legal-v1",
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
        ticket_qr_secret="fake-qr-secret",
        personal_consent_text="Approved personal data consent",
        personal_consent_version="legal-v1",
        marketing_consent_text="Approved marketing consent",
        marketing_consent_version="legal-v1",
        _env_file=None,
    )


@pytest.mark.parametrize("field", ["telegram_token", "ticket_qr_secret"])
def test_staging_requires_bot_token_and_qr_secret(field):
    values = dict(environment="staging", telegram_token="fake-token", ticket_qr_secret="fake-qr")
    values[field] = ""
    with pytest.raises(ValidationError):
        Settings(**values, _env_file=None)


def test_staging_runs_without_payment_credentials_but_is_hardened():
    settings = Settings(
        environment="staging",
        telegram_token="fake-token",
        ticket_qr_secret="fake-qr",
        _env_file=None,
    )
    assert settings.hardened
    assert not Settings(environment="development", _env_file=None).hardened
    assert Settings(
        environment="production",
        telegram_token="t",
        tbank_terminal_key="k",
        tbank_password="p",
        ticket_qr_secret="q",
        personal_consent_text="Approved",
        personal_consent_version="v1",
        marketing_consent_text="Approved",
        marketing_consent_version="v1",
        _env_file=None,
    ).hardened


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
        database_url="postgresql+asyncpg://user:private-db@localhost/povod",
        redis_url="redis://:private-redis@localhost:6379/0",
        _env_file=None,
    )
    for value in [
        "private-token",
        "private-key",
        "private-password",
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


@pytest.mark.parametrize("field", ["database_url", "redis_url"])
def test_logging_redacts_encoded_and_decoded_connection_passwords(capsys, field):
    import json

    import structlog

    from src.core.logging import configure_logging

    url = (
        "postgresql+asyncpg://user:review%40dummy@localhost/povod"
        if field == "database_url"
        else "redis://:review%40dummy@localhost:6379/0"
    )
    configure_logging(Settings(**{field: url}, _env_file=None))
    structlog.get_logger().info(
        "connection_failed", details={"encoded": url, "decoded": "review@dummy"}
    )
    output = capsys.readouterr().out
    assert "review%40dummy" not in output
    assert "review@dummy" not in output
    payload = json.loads(output)
    assert payload["event"] == "connection_failed"
    assert payload["details"]["decoded"] == "[REDACTED]"


@pytest.mark.parametrize("value_kind", ["exception", "arbitrary_object"])
def test_logging_redacts_configured_secrets_in_serialized_objects(capsys, value_kind):
    import json

    import structlog

    from src.core.logging import configure_logging

    class ProviderFailure:
        def __repr__(self):
            return "ProviderFailure(review-dummy-telegram-token)"

    value = (
        RuntimeError("provider failed with review-dummy-telegram-token")
        if value_kind == "exception"
        else ProviderFailure()
    )
    configure_logging(Settings(telegram_token="review-dummy-telegram-token", _env_file=None))
    structlog.get_logger().error("provider_failed", details={"errors": [value]}, attempts=1)
    output = capsys.readouterr().out
    assert "review-dummy-telegram-token" not in output
    payload = json.loads(output)
    assert "[REDACTED]" in payload["details"]["errors"][0]
    assert payload["event"] == "provider_failed"
    assert payload["attempts"] == 1
