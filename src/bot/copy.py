"""All bot-facing texts in one place. Voice: informal "ты", the club speaks as "мы".

Source of truth: docs/brand/bot-entry-copy.md.
"""

BTN_OPEN = "Открыть Повод"
BTN_TICKETS = "Мои билеты"
BTN_SUPPORT = "Поддержка"
BTN_MENU = "Меню"

START_FIRST_NAMED = (
    "Привет, {name}! Это «Повод».\n\nВсе наши вечера и билеты в приложении, открывается кнопкой."
)
START_FIRST_ANON = (
    "Привет! Это «Повод».\n\nВсе наши вечера и билеты в приложении, открывается кнопкой."
)
START_AGAIN_NAMED = "Привет, {name}! Открывай, посмотри, что у нас скоро."
START_AGAIN_ANON = "Привет! Открывай, посмотри, что у нас скоро."

TICKETS_TITLE = "Твои билеты:"
TICKETS_EMPTY = "Билетов пока нет. Загляни в приложение, там афиша."
TICKET_LINE = "{title}, {date} в {time}. {status}"
TICKET_ISSUED_ONE = (
    "Оплата прошла, билет твой.\n{title}, {date} в {time}.\nQR для входа — в «Мои билеты»."
)
TICKET_ISSUED_MANY = (
    "Оплата прошла, билеты твои — {count} шт.\n{title}, {date} в {time}.\n"
    "QR для входа — в «Мои билеты»."
)
TICKET_STATUS = {
    "issued": "Действует",
    "checked_in": "Использован",
    "voided": "Отменён",
    "cancelled": "Отменён",
    "refunded": "Деньги вернули",
}

SUPPORT_CONTACT_DEFAULT = "https://t.me/vladpryanik"

SUPPORT_WITH_CONTACT = (
    "Если что-то не так с билетом или оплатой, напиши нам: {contact}\n\n"
    "Сразу укажи, на какой вечер билет, так быстрее разберёмся."
)
UNKNOWN_TEXT = (
    "Мы тут отвечаем только на кнопки. Афиша и билеты в приложении, "
    "а если есть вопрос, нажми «Поддержка»."
)

ERR_START_PARAM = "Что-то не так со ссылкой. Отправь просто /start."
ORDER_CREATED = "Заказ есть. Сейчас пришлём ссылку на оплату."
ERR_ORDER = "Не получилось оформить заказ. Открой афишу заново и попробуй ещё раз."
ERR_PAYMENT = "Заказ есть, но оплата не запустилась. Напиши в поддержку, разберёмся."
