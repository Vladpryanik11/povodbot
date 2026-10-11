import pytest
from pydantic import ValidationError

from src.bot.keyboards.main_menu import main_menu
from src.core.config import Settings


def _texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_menu_without_miniapp_url_is_the_plain_chat_menu():
    markup = main_menu([], True, "draft-v1", 1)
    assert "Открыть Повод" not in _texts(markup)
    assert _texts(markup)[0] == "Мои билеты"


def test_menu_with_miniapp_url_starts_with_the_web_app_button():
    markup = main_menu([], True, "draft-v1", 1, "https://example.test/app")
    first = markup.inline_keyboard[0][0]
    assert first.text == "Открыть Повод"
    assert first.web_app is not None
    assert first.web_app.url == "https://example.test/app"
    assert _texts(markup)[1] == "Мои билеты"


def test_miniapp_url_defaults_to_empty():
    assert Settings(environment="test", telegram_token="dummy", _env_file=None).miniapp_url == ""


@pytest.mark.parametrize(
    "value", ["http://example.test", "example.test", "https://", "https://a b"]
)
def test_miniapp_url_must_be_an_absolute_https_address(value):
    with pytest.raises(ValidationError):
        Settings(environment="test", telegram_token="dummy", miniapp_url=value, _env_file=None)
