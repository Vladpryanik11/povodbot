import pytest

from src.services.campaigns.content import (
    CampaignFieldError,
    validate_body,
    validate_buttons,
    validate_image,
    visible_length,
)

ONLY_TAGS = "Можно только жирный, курсив и ссылку"
HTTPS_ONLY = "Ссылка должна начинаться с https://"
TOO_LONG = "Слишком длинный текст: с картинкой до 1024 знаков, без неё до 4096"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("<u>x</u>", ONLY_TAGS),
        ("<b>x", ONLY_TAGS),
        ("<b><i>x</b></i>", ONLY_TAGS),
        ('<b class="x">x</b>', ONLY_TAGS),
        ("x<br>y", ONLY_TAGS),
        ('<a href="javascript:alert(1)">x</a>', HTTPS_ONLY),
        ('<a href="http://x.ru">x</a>', HTTPS_ONLY),
        ('<a href="https://x.ru" target="_blank">x</a>', ONLY_TAGS),
        ("a < b", ONLY_TAGS),
        ("", "Напиши текст рассылки"),
        ("<b> </b>", "Напиши текст рассылки"),
    ],
)
def test_body_rejects(body, message):
    with pytest.raises(CampaignFieldError) as caught:
        validate_body(body, has_image=False)
    assert (caught.value.field, caught.value.message) == ("body", message)


def test_body_accepts():
    body = '<b>Жирно</b> <i>и</i> <a href="https://povod.club">ссылка</a> &amp;'
    validate_body(body, has_image=True)
    assert visible_length(body) == len("Жирно и ссылка &")


def test_length_limits():
    validate_body("<b>" + "я" * 1024 + "</b>", has_image=True)
    validate_body("я" * 4096, has_image=False)
    for body, has_image in (("я" * 1025, True), ("я" * 4097, False)):
        with pytest.raises(CampaignFieldError) as caught:
            validate_body(body, has_image=has_image)
        assert caught.value.message == TOO_LONG


@pytest.mark.parametrize(
    ("buttons", "has_event", "message"),
    [
        ([{"kind": "event", "label": "Вечер"}] * 3, True, "Не больше двух кнопок"),
        ([{"kind": "event", "label": "Открыть вечер"}], False, "Сначала выбери вечер"),
        ([{"kind": "url", "label": " ", "url": "https://x.ru"}], False, None),
        ([{"kind": "url", "label": "x" * 41, "url": "https://x.ru"}], False, None),
        ([{"kind": "url", "label": "Сайт", "url": "http://x.ru"}], False, HTTPS_ONLY),
        ([{"kind": "url", "label": "Сайт", "url": "https://" + "x" * 2041}], False, HTTPS_ONLY),
    ],
)
def test_buttons_reject(buttons, has_event, message):
    with pytest.raises(CampaignFieldError) as caught:
        validate_buttons(buttons, has_event=has_event)
    assert caught.value.field == "buttons"
    assert caught.value.message == (message or "Подпись кнопки — от 1 до 40 знаков")


def test_buttons_accept_and_normalize():
    buttons = [
        {"kind": "event", "label": " Открыть вечер ", "url": "https://ignored.ru"},
        {"kind": "url", "label": "Сайт", "url": "https://povod.club"},
    ]
    assert validate_buttons(buttons, has_event=True) == [
        {"kind": "event", "label": "Открыть вечер"},
        {"kind": "url", "label": "Сайт", "url": "https://povod.club"},
    ]


def test_image_kinds():
    assert validate_image({"kind": "none"}) == {"kind": "none"}
    assert validate_image({"kind": "event", "ref": "x"}) == {"kind": "event"}
    assert validate_image({"kind": "upload", "ref": "campaigns/a"}) == {
        "kind": "upload",
        "ref": "campaigns/a",
    }
    for bad in ({"kind": "upload"}, {"kind": "gif"}):
        with pytest.raises(CampaignFieldError) as caught:
            validate_image(bad)
        assert caught.value.field == "image"
