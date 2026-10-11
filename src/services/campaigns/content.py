"""What a broadcast may carry: Telegram HTML with bold, italic and links; up to two buttons."""

from html import unescape
from html.parser import HTMLParser
from typing import Any

EMPTY_BODY = "Напиши текст рассылки"
TOO_LONG = "Слишком длинный текст: с картинкой до 1024 знаков, без неё до 4096"
ONLY_TAGS = "Можно только жирный, курсив и ссылку"
HTTPS_ONLY = "Ссылка должна начинаться с https://"
TOO_MANY_BUTTONS = "Не больше двух кнопок"
PICK_EVENT = "Сначала выбери вечер"
BAD_LABEL = "Подпись кнопки — от 1 до 40 знаков"
BAD_IMAGE = "Картинка не загрузилась. Попробуй ещё раз"

CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096
MAX_BUTTONS = 2
LABEL_LIMIT = 40
URL_LIMIT = 2048
# Telegram knows only these named entities; numeric ones are all fine.
NAMED_ENTITIES = {"lt", "gt", "amp", "quot"}


class CampaignFieldError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _not_allowed() -> CampaignFieldError:
    return CampaignFieldError("body", ONLY_TAGS)


class _TelegramHtml(HTMLParser):
    """Accepts exactly what Telegram's HTML parse mode needs from us; collects the visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.open: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("b", "i") and not attrs:
            pass
        elif tag == "a" and "a" not in self.open and [name for name, _ in attrs] == ["href"]:
            if not (attrs[0][1] or "").startswith("https://"):
                raise CampaignFieldError("body", HTTPS_ONLY)
        else:
            raise _not_allowed()
        self.open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raise _not_allowed()

    def handle_endtag(self, tag: str) -> None:
        if not self.open or self.open[-1] != tag:
            raise _not_allowed()
        self.open.pop()

    def handle_data(self, data: str) -> None:
        if any(char in data for char in "<>&"):  # Telegram needs these escaped
            raise _not_allowed()
        self.text.append(data)

    def handle_entityref(self, name: str) -> None:
        if name not in NAMED_ENTITIES:
            raise _not_allowed()
        self.text.append(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.text.append(unescape(f"&#{name};"))

    def handle_comment(self, data: str) -> None:
        raise _not_allowed()

    def handle_decl(self, decl: str) -> None:
        raise _not_allowed()

    def handle_pi(self, data: str) -> None:
        raise _not_allowed()

    def unknown_decl(self, data: str) -> None:
        raise _not_allowed()


def _visible_text(body: str) -> str:
    parser = _TelegramHtml()
    parser.feed(body)
    parser.close()
    if parser.open:
        raise _not_allowed()
    return "".join(parser.text)


def visible_length(body: str) -> int:
    # Telegram measures text in UTF-16 code units: an emoji takes two.
    return len(_visible_text(body).encode("utf-16-le")) // 2


def validate_body(body: str, *, has_image: bool) -> None:
    text = _visible_text(body)
    if not text.strip():
        raise CampaignFieldError("body", EMPTY_BODY)
    limit = CAPTION_LIMIT if has_image else MESSAGE_LIMIT
    if len(text.encode("utf-16-le")) // 2 > limit:
        raise CampaignFieldError("body", TOO_LONG)


def validate_buttons(buttons: list[dict[str, Any]], *, has_event: bool) -> list[dict[str, Any]]:
    if not isinstance(buttons, list):
        raise CampaignFieldError("buttons", BAD_LABEL)
    if len(buttons) > MAX_BUTTONS:
        raise CampaignFieldError("buttons", TOO_MANY_BUTTONS)
    normalized: list[dict[str, Any]] = []
    for button in buttons:
        label = button.get("label") if isinstance(button, dict) else None
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= LABEL_LIMIT:
            raise CampaignFieldError("buttons", BAD_LABEL)
        label = label.strip()
        if button.get("kind") == "event":
            if not has_event:
                raise CampaignFieldError("buttons", PICK_EVENT)
            normalized.append({"kind": "event", "label": label})
            continue
        url = button.get("url")
        if not isinstance(url, str) or not url.startswith("https://") or len(url) > URL_LIMIT:
            raise CampaignFieldError("buttons", HTTPS_ONLY)
        normalized.append({"kind": "url", "label": label, "url": url})
    return normalized


def validate_image(image: dict[str, Any]) -> dict[str, Any]:
    kind = image.get("kind") if isinstance(image, dict) else None
    if kind in ("none", "event"):
        return {"kind": kind}
    ref = image.get("ref") if kind == "upload" else None
    if isinstance(ref, str) and ref:
        return {"kind": "upload", "ref": ref}
    raise CampaignFieldError("image", BAD_IMAGE)
