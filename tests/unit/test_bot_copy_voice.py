"""Guard: the bot talks to guests as "ты" and never uses "вы" or imperative -ите forms."""

import re

from src.bot import copy

TEXTS = {name: value for name, value in vars(copy).items() if name.isupper()}

FORBIDDEN = re.compile(
    r"(?<![а-яё])(вы|вас|вам|вами|ваш\w*|\w+(?:ите|итесь|йте|йтесь))(?![а-яё])",
    re.IGNORECASE,
)
# Words that merely end the same way.
ALLOWED = {"билете", "оплате", "сайте", "приложение"}


def _strings():
    for name, value in TEXTS.items():
        if isinstance(value, dict):
            for item in value.values():
                yield name, item
        else:
            yield name, value


def test_copy_module_has_texts():
    assert len(TEXTS) > 15


def test_no_formal_address_in_bot_copy():
    offenders = []
    for name, text in _strings():
        for match in FORBIDDEN.finditer(text):
            if match.group(0).lower() not in ALLOWED:
                offenders.append((name, match.group(0)))
    assert offenders == []


def test_no_emoji_and_no_word_advertising():
    for name, text in _strings():
        assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", text), name
        assert "реклам" not in text.lower(), name
