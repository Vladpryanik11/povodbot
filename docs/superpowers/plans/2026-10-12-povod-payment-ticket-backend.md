# Фаза 1: платёж и билет. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** доводим платёжный бэкенд до состояния, в котором реальная оплата через T-Bank проходит до конца: банк получает `OK`, гость получает билет в боте, возврат не теряется, а поздняя оплата решается одной кнопкой админа.

**Architecture:** правки точечные, в существующих модулях `src/services/payments`, `src/api/webhooks/tbank.py` и `src/workers/outbox.py`. Новое добавляется в двух местах:
- сообщение «билет выдан» идёт через outbox: строка `ticket.issued` пишется в той же транзакции, что и билеты, а воркер отправляет её через уже существующий `CampaignSender`;
- адреса для Init собираются из настроек (`PUBLIC_BASE_URL`, `MINIAPP_LINK`) в каждом запросе, и настройки терминала в кабинете не меняются.

**Tech Stack:** Python 3.12, FastAPI, aiogram 3, SQLAlchemy async + PostgreSQL, httpx, pytest (`asyncio_mode = "auto"`).

**Spec:** `docs/superpowers/plans/2026-10-11-povod-launch-roadmap.md`, фаза 1 (пробелы A1–A5, A10). Решения владельца от 2026-10-12:
- бот работает через старый магазин «Club Povod», тот же, что у `povodclub.tb.ru/pay1`;
- оплата одностадийная;
- онлайн-касса отложена, поэтому A8 (`Receipt`) в этот план не входит;
- доступа к кабинету у нас нет, поэтому всё проверяется на моках, а smoke на DEMO-терминале пройдёт позже.

## Global Constraints

- Не делать реальных запросов к T-Bank и Telegram. В тестах только `httpx.MockTransport` и fake-шлюзы/отправители.
- Не печатать и не коммитить `.env`. Секреты не должны попадать в тесты, логи и фронтенд. В тестах пароль терминала — строка вида `"test-password"`.
- Не пушить и не выкладывать на сервер без слова владельца.
- Ответ на уведомление банка — HTTP 200, `text/plain`, тело ровно `OK`. Иначе банк повторяет уведомление.
- Подпись уведомления — только поле `Token` в теле: SHA-256 от корневых скаляров, отсортированных по ключу, плюс `Password`. Своего заголовка банк не шлёт.
- Настройки терминала в кабинете не трогаем. `NotificationURL`, `SuccessURL` и `FailURL` передаются в каждом Init.
- Редирект на `SuccessURL` не доказывает оплату. Доказательство — уведомление с подписью или `GetState`.
- Тексты для гостя на «ты», в голосе бренда. Новые строки живут в `src/bot/copy.py`, финальные формулировки утверждает владелец.
- Тесты: интеграционные нужны в `TEST_DATABASE_URL` (временный trust-кластер на 55433, см. память). Вывод печатать только итоговой строкой: `python -m pytest <path> -q 2>&1 | tail -1`.
- Бесплатные билеты, `Receipt` и `DATA.OperationInitiatorType` в этот план не входят. Бесплатные переходят в фазу 3, остальное ждёт кассы или smoke на DEMO.

## Review Focus

1. **Пустой пароль на стенде.** Если на staging нет ключей, а уведомление подписано пустым паролем, его нельзя принимать. Ожидание: при пустом `TBANK_PASSWORD` маршрут отвечает 503 и ничего не пишет в базу. Тест: задача 1, `test_webhook_without_configured_password_is_unavailable`.
2. **AUTHORIZED приходит после CONFIRMED.** При одностадийной оплате банк шлёт оба уведомления почти одновременно, и порядок не гарантирован. Ожидание: оплаченный заказ остаётся оплаченным, билет не пропадает. Тест: задача 2, `test_authorized_after_confirmed_is_stale`.
3. **Гость заблокировал бота до того, как пришёл билет.** Ожидание: билет выдан, задача закрыта, воркер не крутится вечно. Тест: задача 5, `test_ticket_issued_job_closes_when_recipient_blocked`.
4. **Банк недоступен в момент возврата.** Ожидание: возврат не теряется и повторяется сам; после серии неудач платёж виден админу как требующий сверки, и возврат можно запустить снова. Тест: задача 6, `test_refund_retries_after_gateway_error_and_succeeds` и `test_refund_after_give_up_can_be_requested_again`.
5. **Поздняя оплата при распроданном зале.** Ожидание: билет не выдаётся сверх вместимости, админ получает понятный отказ и делает возврат. Тест: задача 7, `test_late_payment_issue_refuses_when_sold_out`.

---

### Task 1: Маршрут уведомлений отвечает банку как надо (A1, A2)

**Files:**
- Modify: `src/api/webhooks/tbank.py`. Убрать `_provided_secret`, заголовки `Authorization` и `X-TBank-Webhook-Secret` и сравнение с секретом.
- Modify: `src/services/payments/tbank_client.py:74-79`, метод `verify_notification`.
- Modify: `src/core/config.py`:
  - убрать поле `tbank_webhook_secret` (строка 21);
  - убрать его из обязательных для production (строка 92).
- Modify: `src/core/logging.py:20`. Убрать секрет из списка редактируемых.
- Modify: `.env.example:10`, `deploy/server.env.example:31`, `docs/DEPLOYMENT.md:85`, `README.md:67`. Убрать `TBANK_WEBHOOK_SECRET` и одной строкой указать, что подпись — `Token` в теле.
- Modify: `tests/unit/test_config.py` (строки 18, 28, 46, 78, 120). Убрать поле из фикстур и из списка обязательных.
- Test: `tests/integration/test_tbank_webhook_http.py` (новый).

**Interfaces:**
- Produces: `POST /api/webhooks/tbank/payment-status`:
  - при принятом, дубликате, неизвестном платеже и устаревшем статусе отвечает `PlainTextResponse("OK")`;
  - при неверной подписи или чужом `TerminalKey` отвечает 401;
  - при отсутствии `PaymentId` или `Status` отвечает 422;
  - при пустом `tbank_password` отвечает 503.
- Produces: `TBankPaymentGateway.verify_notification(payload) -> bool` возвращает `False`, а не исключение, если `Token` не ASCII-строка.

- [ ] **Step 1: Написать падающие тесты**

В `tests/integration/test_tbank_webhook_http.py`:
- Настройки: `monkeypatch.setenv("TBANK_TERMINAL_KEY", "TestTerminalDEMO")`, `setenv("TBANK_PASSWORD", "test-password")`, `get_settings.cache_clear()`.
- Клиент: `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")`.
- Подпись: тело собирается как у банка (`TerminalKey`, `OrderId`, `Success`, `Status`, `PaymentId`, `ErrorCode`, `Amount`, `Pan`, `ExpDate`, а также `Data` словарём, который в подпись не входит). `Token` = `TBankPaymentGateway.build_token(body, "test-password")`.
- Заказ и платёж: фикстуры `catalog`, `reservations` и `PaymentService.start` с fake-шлюзом (как в `tests/integration/test_payment_after_expiry.py:24-37`). Коммит через `pg_factory`.

Тесты:
- `test_signed_confirmed_notification_returns_plain_ok`: ответ 200, `response.text == "OK"`, `response.headers["content-type"].startswith("text/plain")`. Заказ в базе `OrderStatus.PAID`, у заказа есть билеты.
- `test_duplicate_notification_returns_plain_ok`: то же тело дважды, оба ответа `"OK"`, билетов столько же, сколько мест в заказе.
- `test_unknown_payment_returns_plain_ok`: подписанное уведомление с `PaymentId`, которого нет в базе. Ответ 200 `"OK"`.
- `test_bad_token_is_rejected`: `Token` из 64 символов `"0"` даёт 401.
- `test_non_ascii_token_is_rejected_not_crashed`: `Token = "токен"` даёт 401, а не 500.
- `test_foreign_terminal_key_is_rejected`: тело подписано правильно, но `TerminalKey = "OtherTerminal"`, ответ 401.
- `test_webhook_without_configured_password_is_unavailable`: `TBANK_PASSWORD=""`, тело подписано пустым паролем. Ответ 503, в `payment_events` ни одной новой строки.
- `test_header_secret_is_not_required`: подписанное тело без заголовков `Authorization` и `X-TBank-Webhook-Secret` даёт 200 `"OK"`.

- [ ] **Step 2: Запустить и убедиться, что тесты падают**

Run: `python -m pytest tests/integration/test_tbank_webhook_http.py -q 2>&1 | tail -1`
Expected: FAIL (сейчас 401 из-за заголовка и JSON вместо `OK`).

- [ ] **Step 3: Реализовать**

Порядок в `payment_status`:
1. Если пароль пуст → `HTTPException(503)`.
2. Распарсить JSON (не объект → 422).
3. `TerminalKey` тела не равен `settings.tbank_terminal_key` → 401.
4. `verify_notification` → 401.
5. Нет `PaymentId` или `Status` → 422.
6. `apply_webhook`, затем `PlainTextResponse("OK")`.

Возвращаемый тип маршрута меняется на `Response`. В `verify_notification` добавить `if not token.isascii(): return False` перед `compare_digest`.

- [ ] **Step 4: Запустить тесты маршрута и конфига**

Run: `python -m pytest tests/integration/test_tbank_webhook_http.py tests/unit/test_config.py tests/unit/services/test_tbank_client.py -q 2>&1 | tail -1`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/webhooks/tbank.py src/services/payments/tbank_client.py src/core/config.py src/core/logging.py .env.example deploy/server.env.example docs/DEPLOYMENT.md README.md tests/unit/test_config.py tests/integration/test_tbank_webhook_http.py
git commit -m "fix(payments): T-Bank webhook answers plain OK and trusts only the body Token"
```

---

### Task 2: Статус платежа не откатывается назад (A10)

**Files:**
- Modify: `src/services/payments/service.py`, `apply_webhook` (строки 425–645). Проверка на устаревший статус ставится до `payment.provider_status = normalized` (строка 549).
- Test: `tests/integration/test_payment_status_order.py` (новый).

**Interfaces:**
- Produces: `apply_webhook` для устаревшего статуса:
  - сохраняет событие оплаты с `ignored_reason="stale_status"`;
  - не меняет ни `payment.status`, ни `payment.provider_status`, ни заказ;
  - возвращает результат с `reason == "stale_status"`.

Неизвестный статус у оплаченного платежа сохраняется с `ignored_reason="unknown_status"` и не ведёт к сверке.

Правило устаревания. Перед применением берутся прежний `provider_status` и локальный `status` платежа.
- Входящий статус из `AUTHORIZED_STATUSES` или из набора «в процессе» (`NEW`, `FORM_SHOWED`, `3DS_CHECKING`, `3DS_CHECKED`, `AUTHORIZING`, `CONFIRMING`) устарел, если выполнено хотя бы одно:
  - прежний `provider_status` входит в `CONFIRMED_STATUSES ∪ REFUNDING_STATUSES ∪ REFUNDED_STATUSES`;
  - локальный статус — `CONFIRMED`, `REFUNDING` или `REFUNDED`.
- Входящий статус из `REFUNDING_STATUSES` устарел, если локальный статус `REFUNDED`.
- Входящий неизвестный статус (не из `KNOWN_STATUSES`) при тех же условиях, что для `AUTHORIZED`, получает `unknown_status`, а не сверку.

- [ ] **Step 1: Написать падающие тесты**

Сценарии строятся на `db_session` и fake-шлюзе, как в `tests/integration/test_tbank_webhook_idempotency.py`.
- `test_authorized_after_confirmed_is_stale`: сначала `CONFIRMED`, потом `AUTHORIZED` с другим `event_id`. Платёж `PaymentStatus.CONFIRMED`, `provider_status == "CONFIRMED"`, заказ `OrderStatus.PAID`, билеты на месте, у второго события `ignored_reason == "stale_status"`.
- `test_authorized_before_confirmed_still_applies`: сначала `AUTHORIZED`, потом `CONFIRMED`. Итог `CONFIRMED` / `PAID`.
- `test_new_after_late_payment_keeps_reconciliation`: поздняя оплата (как в `test_confirmation_after_expiry_requires_reconciliation_and_releases_reservation`), потом `AUTHORIZED`. Платёж остаётся `RECONCILIATION_REQUIRED`, `provider_status == "CONFIRMED"`.
- `test_refunding_after_refunded_is_stale`: подтвердить, затем `REFUNDED`, затем `REFUNDING`. Платёж остаётся `REFUNDED`.
- `test_unknown_status_on_paid_order_does_not_require_reconciliation`: после `CONFIRMED` приходит статус `"RECEIPT"`. Заказ `PAID`, `ignored_reason == "unknown_status"`.

- [ ] **Step 2: Запустить и убедиться, что падают**

Run: `python -m pytest tests/integration/test_payment_status_order.py -q 2>&1 | tail -1`
Expected: FAIL (`test_authorized_after_confirmed_is_stale` и другие).

- [ ] **Step 3: Реализовать правило в `apply_webhook`**

Вынести проверку в `PaymentService._stale_reason(payment: Payment, normalized: str) -> str | None` и вызывать её после блокировок и дедупликации, до проверки суммы.

- [ ] **Step 4: Прогнать платёжные тесты**

Run: `python -m pytest tests/integration/test_payment_status_order.py tests/integration/test_tbank_webhook_idempotency.py tests/integration/test_payment_hardening.py tests/integration/test_payment_to_ticket.py -q 2>&1 | tail -1`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/payments/service.py tests/integration/test_payment_status_order.py
git commit -m "fix(payments): late AUTHORIZED or unknown status no longer rolls back a paid order"
```

---

### Task 3: CheckOrder читает список `Payments` (A10)

**Files:**
- Modify: `src/services/payments/tbank_client.py:153-170`, `find_by_order`.
- Modify: `tests/unit/services/test_tbank_client.py:62-87`. Ответ мока переписать в реальный формат.

**Interfaces:**
- Produces: `find_by_order(order_id) -> ProviderPaymentStatus`:
  - разбирает `{"Success": true, "OrderId": ..., "Payments": [{"PaymentId", "Amount", "Status", ...}]}`;
  - при пустом или отсутствующем `Payments` бросает `PaymentGatewayError("CheckOrder found no payment")`, и вызывающий код (`checkout.py`) уже уходит в `mark_init_unknown`;
  - при двух и более платежах бросает `PaymentGatewayError("CheckOrder found several payments")`;
  - кладёт `OrderId` верхнего уровня в `raw`, чтобы проверка заказа в `attach_recovered_init` работала.

- [ ] **Step 1: Переписать тест и добавить два новых**

- `test_check_order_recovers_provider_identity_after_lost_init_response`: мок отвечает `{"Success": True, "OrderId": "order-1", "Payments": [{"PaymentId": 9876, "Amount": 15000, "Status": "NEW", "Success": True}]}`. Ожидаются `provider_payment_id == "9876"`, `provider_status == "NEW"`, `amount_minor == 15000`, `raw["OrderId"] == "order-1"`.
- `test_check_order_without_payments_raises`: `"Payments": []` даёт `pytest.raises(PaymentGatewayError)`.
- `test_check_order_with_several_payments_raises`: два элемента дают `pytest.raises(PaymentGatewayError)`.

- [ ] **Step 2: Run** `python -m pytest tests/unit/services/test_tbank_client.py -q 2>&1 | tail -1`. Expected: FAIL.

- [ ] **Step 3: Реализовать разбор списка в `find_by_order`**

- [ ] **Step 4: Run** `python -m pytest tests/unit/services/test_tbank_client.py tests/integration/test_payment_hardening.py tests/integration/test_payment_after_expiry.py -q 2>&1 | tail -1`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/payments/tbank_client.py tests/unit/services/test_tbank_client.py
git commit -m "fix(payments): CheckOrder reads the Payments list T-Bank actually returns"
```

---

### Task 4: Init передаёт адреса уведомления и возврата (A3)

**Files:**
- Create: `src/services/payments/urls.py`.
- Modify: `src/services/payments/service.py`, `prepare` (строка 185, сборка `CreatePaymentRequest`).
- Test: `tests/unit/services/test_payment_urls.py` (новый) и дополнение в `tests/integration/test_payment_hardening.py`.

**Interfaces:**
- Produces: `PaymentUrls(notification_url: str | None, success_url: str | None, fail_url: str | None)`, frozen dataclass.
- Produces: `payment_urls(order_id: UUID, settings: Settings | None = None) -> PaymentUrls`. При `None` вызывает `get_settings()`, как это делает `src/services/tickets/qr.py`.
  - `notification_url = f"{public_base_url.rstrip('/')}/api/webhooks/tbank/payment-status"`, если `public_base_url` не пуст, иначе `None`.
  - `success_url == fail_url == f"{miniapp_link.rstrip('/')}?startapp=order_{order_id.hex}"`, если `miniapp_link` не пуст, иначе `None`. Mini App покажет статус заказа в фазе 5.

- [ ] **Step 1: Написать тесты**

- `test_payment_urls_from_settings`: `Settings(public_base_url="https://144-31-76-55.sslip.io/", miniapp_link="https://t.me/povod_bot/app", ...)`. Ожидаются `notification_url == "https://144-31-76-55.sslip.io/api/webhooks/tbank/payment-status"` и `success_url == fail_url == "https://t.me/povod_bot/app?startapp=order_<hex>"`.
- `test_payment_urls_are_omitted_without_settings`: пустые настройки дают три `None`.
- В `test_payment_hardening.py` добавить `test_init_request_carries_notification_and_return_urls`. Fake-шлюз запоминает `request`. При заданных через `monkeypatch.setenv` + `cache_clear` `PUBLIC_BASE_URL` и `MINIAPP_LINK` у `request.notification_url` нужный адрес, а `request.success_url` оканчивается на `order_{order_id.hex}`.

- [ ] **Step 2: Run** `python -m pytest tests/unit/services/test_payment_urls.py -q 2>&1 | tail -1`. Expected: FAIL (нет модуля).

- [ ] **Step 3: Реализовать `payment_urls` и передать три поля в `CreatePaymentRequest` в `prepare`**

- [ ] **Step 4: Run** `python -m pytest tests/unit/services/test_payment_urls.py tests/integration/test_payment_hardening.py -q 2>&1 | tail -1`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/payments/urls.py src/services/payments/service.py tests/unit/services/test_payment_urls.py tests/integration/test_payment_hardening.py
git commit -m "feat(payments): Init passes NotificationURL and Mini App return URLs per order"
```

---

### Task 5: Гость получает сообщение «билет выдан» (A3)

**Files:**
- Create: `src/services/tickets/delivery.py`.
- Modify: `src/services/payments/service.py`. Сразу после `issue_for_paid_order` (строка 635) вызвать `enqueue_ticket_issued`.
- Modify: `src/workers/outbox.py`:
  - перенести `_postpone` из `CampaignOutboxWorker` (строка 156) в `_OutboxWorker`;
  - добавить `TicketIssuedOutboxWorker`.
- Modify: `src/workers/main.py`, `run_once`. Добавить `TicketIssuedOutboxWorker(session_factory, sender).process_pending(100)` после рассылок.
- Modify: `src/bot/copy.py`. Добавить `TICKET_ISSUED_ONE` и `TICKET_ISSUED_MANY`.
- Test: `tests/integration/test_ticket_issued_delivery.py` (новый).

**Interfaces:**
- Consumes: `CampaignSender.send(telegram_id: int, message: RenderedMessage) -> SentMessage`, `RetryAfter(seconds)` и `RecipientBlocked` из `src/services/campaigns/telegram.py`; `RenderedMessage` из `src/services/campaigns/render.py`.
- Produces:
  - `TICKET_ISSUED_EVENT = "ticket.issued"`.
  - `async def enqueue_ticket_issued(session: AsyncSession, order_id: UUID) -> None` пишет `Outbox(event_type="ticket.issued", deduplication_key=f"ticket:issued:{order_id}", payload={"order_id": str(order_id)})`, если такой строки ещё нет. Транзакция вызывающего.
  - `async def build_ticket_issued(session: AsyncSession, order_id: UUID) -> tuple[int, RenderedMessage] | None` возвращает `telegram_id` покупателя и текст. Если у заказа нет выданных билетов или нет `telegram_id`, возвращается `None`.
  - `TicketIssuedOutboxWorker(session_factory, sender)` и `process_pending(limit: int = 100) -> int`.

Черновик текстов, финал за владельцем. Дата и время форматируются так же, как в `src/bot/handlers/tickets.py` `mine()`:

```python
TICKET_ISSUED_ONE = "Оплата прошла, билет твой.\n{title}, {date} в {time}.\nQR для входа — в «Мои билеты»."
TICKET_ISSUED_MANY = "Оплата прошла, билеты твои — {count} шт.\n{title}, {date} в {time}.\nQR для входа — в «Мои билеты»."
```

Кнопки нет: экран билетов в Mini App пока на моках. Кнопка `?startapp=tickets` появится в фазе 5.

Воркер:
- `None` от `build_ticket_issued` → закрыть задачу;
- `RetryAfter` → `_postpone(job, e.seconds)`;
- `RecipientBlocked` → закрыть;
- прочие ошибки отправки → `available_at = now + min(30 * 2**attempts, 3600)` с; после `MAX_DELIVERY_ATTEMPTS` (5) закрыть;
- успех → закрыть.

«Закрыть» значит `processed_at = now`.

- [ ] **Step 1: Написать тесты**

Fake-отправитель запоминает вызовы или бросает заданное исключение.
- `test_paid_order_enqueues_one_ticket_issued_job`: `CONFIRMED` дважды (дубликат) дают одну строку outbox `ticket:issued:{order_id}`.
- `test_ticket_issued_message_names_event_and_time`: после воркера у отправителя один вызов с `telegram_id` покупателя. `text` начинается с `"Оплата прошла, билет твой."` и содержит название вечера.
- `test_ticket_issued_job_closes_when_recipient_blocked`: отправитель бросает `RecipientBlocked`, после одного прохода у задачи `processed_at is not None`, билеты не тронуты.
- `test_ticket_issued_job_waits_on_retry_after`: `RetryAfter(30)` оставляет `processed_at is None`, а `available_at` ≥ now + 30 с.
- `test_ticket_issued_gives_up_after_max_attempts`: отправитель всегда бросает `RuntimeError`. После 5 проходов (с ручным сдвигом `available_at` в прошлое между ними) задача закрыта.

- [ ] **Step 2: Run** `python -m pytest tests/integration/test_ticket_issued_delivery.py -q 2>&1 | tail -1`. Expected: FAIL.

- [ ] **Step 3: Реализовать `delivery.py`, вызов в `apply_webhook`, воркер, перенос `_postpone` и подключение в `run_once`**

- [ ] **Step 4: Run** `python -m pytest tests/integration -k "ticket or campaign or outbox" -q 2>&1 | tail -1`. Expected: PASS (рассылки не сломаны переносом `_postpone`).

- [ ] **Step 5: Commit**

```bash
git add src/services/tickets/delivery.py src/services/payments/service.py src/workers/outbox.py src/workers/main.py src/bot/copy.py tests/integration/test_ticket_issued_delivery.py
git commit -m "feat(tickets): guest gets a 'ticket issued' message after payment via outbox"
```

---

### Task 6: Возврат не теряется (A4)

**Files:**
- Modify: `src/workers/outbox.py`, класс `PaymentRefundOutboxWorker`: `process_pending` (строки 329–357) и `_finish` (строки 294–327).
- Modify: `src/services/payments/service.py`, `request_refund` (строки 794–845).
- Modify: `tests/integration/test_payment_after_expiry.py`. Тест `test_refund_worker_reconciles_ambiguous_cancel_without_retrying` переписывается под повтор.
- Test: `tests/integration/test_refund_retry.py` (новый).

**Interfaces:**
- Produces: в `src/workers/outbox.py` константы `REFUND_MAX_ATTEMPTS = 10` и `refund_backoff(attempts: int) -> timedelta` = `min(30 * 2**attempts, 3600)` с.
- Produces: результаты `PaymentRefundOutboxWorker.process_pending`:
  - **`PaymentProviderTimeout` или `PaymentGatewayError` (не `Rejected`), попытки не исчерпаны.** Задача остаётся открытой, `available_at = now + refund_backoff(attempts)`, `payment.provider_status = "REFUND_RETRY"`. Повтор безопасен: каждая попытка начинается с `GetState`, и `Cancel` не отправляется, если банк уже вернул деньги.
  - **То же после `REFUND_MAX_ATTEMPTS`.** Задача закрывается, `provider_status = "REFUND_UNKNOWN"`, `payment.status = RECONCILIATION_REQUIRED`.
  - **`PaymentProviderRejected`.** Задача закрывается, `provider_status = "REFUND_REJECTED"`, `payment.status = RECONCILIATION_REQUIRED`.
  - **`ValueError` или `KeyError` (битая задача).** Задача закрывается, как сейчас, с `REFUND_UNKNOWN`.
- Produces: `request_refund` принимает платёж в `RECONCILIATION_REQUIRED`, если его `provider_status` входит в `REFUNDABLE_AFTER_RECONCILIATION = {"CONFIRMED", "REFUND_RETRY", "REFUND_UNKNOWN", "REFUND_REJECTED"}`. Это поздняя оплата или неудавшийся возврат. Уже закрытая команда `payment:refund:{id}` открывается заново (`processed_at=None`, `attempts=0`, `available_at=now`, свежий `reason`), новая строка не создаётся.

- [ ] **Step 1: Написать тесты**

В `test_refund_retry.py` используется gateway с очередью ответов на `refund`: исключение или `ProviderOperationResult`. `get_status` возвращает `CONFIRMED`, пока возврат не прошёл.
- `test_refund_retries_after_gateway_error_and_succeeds`: сначала `PaymentGatewayError`, потом `REFUNDED`. После первого прохода задача открыта, `provider_status == "REFUND_RETRY"`. Затем сдвинуть `available_at` в прошлое и пройти второй раз: платёж `REFUNDED`, заказ `OrderStatus.REFUNDED`, задача закрыта, `refund_calls == 2`.
- `test_refund_retry_does_not_cancel_twice_when_bank_already_refunded`: первый `refund` бросает ошибку, а `get_status` на втором проходе отвечает `REFUNDED`. `refund_calls == 1`, платёж `REFUNDED`.
- `test_refund_gives_up_after_max_attempts`: `refund` всегда бросает `PaymentGatewayError`. После `REFUND_MAX_ATTEMPTS` проходов задача закрыта, `provider_status == "REFUND_UNKNOWN"`, `payment.status == RECONCILIATION_REQUIRED`.
- `test_rejected_refund_is_closed_for_operator`: `PaymentProviderRejected` после одного прохода закрывает задачу, `provider_status == "REFUND_REJECTED"`.
- `test_refund_after_give_up_can_be_requested_again`: после give-up повторный `request_refund` открывает ту же строку outbox (по `deduplication_key` строка одна, `processed_at is None`). Следующий проход с успешным `refund` даёт `REFUNDED`.
- `test_late_payment_can_be_refunded`: поздняя оплата (платёж `RECONCILIATION_REQUIRED`, `provider_status == "CONFIRMED"`). `request_refund` создаёт команду, проход воркера доводит платёж до `REFUNDED`.

Тест `test_refund_worker_reconciles_ambiguous_cancel_without_retrying` переименовать в `test_refund_worker_retries_ambiguous_cancel_later`. Ожидание: после первого прохода `process_pending() == 1`, `provider_status == "REFUND_RETRY"`, задача открыта, а второй немедленный проход возвращает `0`, потому что `available_at` в будущем.

- [ ] **Step 2: Run** `python -m pytest tests/integration/test_refund_retry.py -q 2>&1 | tail -1`. Expected: FAIL.

- [ ] **Step 3: Реализовать повтор в воркере и правки `request_refund`**

- [ ] **Step 4: Run** `python -m pytest tests/integration/test_refund_retry.py tests/integration/test_payment_after_expiry.py -q 2>&1 | tail -1`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/workers/outbox.py src/services/payments/service.py tests/integration/test_refund_retry.py tests/integration/test_payment_after_expiry.py
git commit -m "fix(payments): refund retries with backoff instead of closing on the first error"
```

---

### Task 7: Админ выдаёт билет по поздней оплате (A5)

**Files:**
- Modify: `src/models/commerce.py:36-43`. Добавить `OrderTransition.RESOLVE_PAYMENT = "resolve_payment"`. Миграция не нужна, у `order_events` нет ограничения на значения.
- Modify: `src/services/orders/service.py`. Разрешить `RECONCILIATION_REQUIRED → PAID` по `RESOLVE_PAYMENT` в `_ALLOWED`. В `_apply_transition_locked` для этого перехода резерв заказа (`EXPIRED`/`RELEASED`) переводится в `CONVERTED`.
- Modify: `src/services/payments/service.py`. Добавить `issue_late_payment`.
- Modify: `src/services/payments/admin.py`. Добавить `PaymentAdminService.issue_late_payment`.
- Modify: `src/api/admin/payments.py`. Добавить `POST /{payment_id}/issue` с аудитом `payment.issue_late`.
- Test: `tests/integration/test_late_payment_issue.py` (новый).

**Interfaces:**
- Consumes: `enqueue_ticket_issued` (задача 5), `CapacityExceeded` из `src/services/reservations/service.py`.
- Produces: `PaymentService.issue_late_payment(payment_id: UUID, provider: ProviderPaymentStatus) -> PaymentDTO`. Транзакция вызывающего, блокировки в порядке event → order → payment. Требования, иначе `PaymentStateError`:
  - платёж и заказ в `RECONCILIATION_REQUIRED`;
  - `provider.provider_status == "CONFIRMED"`;
  - `provider.provider_payment_id == payment.provider_payment_id`;
  - `provider.amount_minor == payment.amount_kopecks`;
  - `now < event.ends_at`.

  Места проверяются так же, как в `OrderService.create_pending` (`src/services/orders/service.py:223-236`): занятые по `occupied_by_ticket` плюс места заказа против `event.capacity` и лимита типа. Нехватка → `CapacityExceeded`. Успех:
  - переход `RESOLVE_PAYMENT`, причина `"late_payment_resolved"`;
  - `payment.status = CONFIRMED`, `paid_at = now`;
  - `TicketIssuer.issue_for_paid_order`;
  - `enqueue_ticket_issued`.
- Produces: `PaymentAdminService.issue_late_payment(payment_id: UUID) -> PaymentDTO`:
  1. транзакция: прочитать `provider_payment_id` (нет → `PaymentStateError`);
  2. `gateway.get_status` вне транзакции;
  3. вторая транзакция: `PaymentService.issue_late_payment`.
- Produces: `POST /api/admin/payments/{payment_id}/issue` с правом `require_payment_admin`. Ответы: 404 без платежа, 409 с `detail="Payment cannot be issued"` при `PaymentStateError`, 409 с `detail="No seats left, refund instead"` при `CapacityExceeded`, 502 при `PaymentGatewayError`.

- [ ] **Step 1: Написать тесты**

Поздняя оплата строится как в `test_confirmation_after_expiry_requires_reconciliation_and_releases_reservation`.
- `test_late_payment_issue_converts_order_and_issues_tickets`: при свободных местах заказ `PAID`, платёж `CONFIRMED`, резерв `CONVERTED`, билеты выданы, строка outbox `ticket:issued:{order_id}` есть.
- `test_late_payment_issue_refuses_when_sold_out`: `catalog(session, capacity=1)`, пока заказ висел, другой гость купил последнее место. `pytest.raises(CapacityExceeded)`, заказ остаётся `RECONCILIATION_REQUIRED`, билетов нет.
- `test_late_payment_issue_requires_confirmed_provider_state`: `GetState` отвечает `REJECTED`, результат `PaymentStateError`.
- `test_late_payment_issue_rejects_amount_mismatch`: `GetState` с другой суммой даёт `PaymentStateError`.
- `test_late_payment_issue_refuses_after_event_ended`: часы после `event.ends_at` дают `PaymentStateError`.
- `test_admin_issue_endpoint_records_audit`: HTTP-вызов эндпоинта по образцу админ-тестов из `tests/integration/test_event_capacity.py` (как там получают админа и заголовки). Ответ 200, в аудите действие `payment.issue_late`.

- [ ] **Step 2: Run** `python -m pytest tests/integration/test_late_payment_issue.py -q 2>&1 | tail -1`. Expected: FAIL.

- [ ] **Step 3: Реализовать переход, сервис, админ-сервис и эндпоинт**

- [ ] **Step 4: Прогнать весь набор**

Run: `python -m pytest -q 2>&1 | tail -1`
Expected: все тесты проходят (было 261 плюс новые).

- [ ] **Step 5: Обновить `docs/superpowers/STATUS.md`**

Отметить, что фаза 1 сделана. Следующие шаги:
- smoke на DEMO-терминале, когда будут ключи;
- `OperationInitiatorType`;
- бесплатные билеты в фазе 3;
- `Receipt` после кассы;
- кнопка «Мои билеты» в фазе 5;
- `TBANK_WEBHOOK_SECRET` можно удалить из серверного `.env`, он больше не читается.

- [ ] **Step 6: Commit**

```bash
git add src/models/commerce.py src/services/orders/service.py src/services/payments/service.py src/services/payments/admin.py src/api/admin/payments.py tests/integration/test_late_payment_issue.py docs/superpowers/STATUS.md
git commit -m "feat(payments): admin can issue tickets for a late payment when seats remain"
```

---

## После плана, не в коде

Smoke на DEMO-терминале магазина «Club Povod» делается, когда владелец внесёт ключи на сервер сам:
- обязательные тестовые сценарии кабинета;
- проверка, что уведомления доходят на зарубежный адрес;
- проверка, что `pay1` продолжает работать.

Касса и `Receipt` — отдельным планом, до включения кассы в кабинете.
