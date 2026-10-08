# Review report — «Повод»

Дата: 2026-10-08.

## Продолжение после архивного baseline

Архивный review фиксировал состояние после `1cba547`. В текущем clone на
ветке `codex/povod-payment-hardening` дополнительно закрыты следующие
payment/campaign hardening findings:

- Payment Init получил durable lease и recovery path: конкурентный checkout не
  делает второй Init, а поздний matching response привязывается idempotently.
- Unknown webhook deduplication использует PostgreSQL `ON CONFLICT DO NOTHING`;
  известные payment transitions и refund callers используют lock order
  `event → order → payment`.
- Admin `GetState`/bind вынесены в `PaymentAdminService`: provider вызов
  происходит между короткими read/apply транзакциями, а snapshot проверяется до
  записи provider identity.
- Draft campaign schedule теперь требует timezone-aware timestamp в будущем и
  нормализуется в UTC.

Эти изменения покрыты focused PostgreSQL integration tests. Реальные T‑Bank,
Telegram, Docker/Compose и backup/restore release gates остаются внешними
ограничениями и не объявляются пройденными локальными тестами.

## История независимых ревью

### Ревью текущего `bb82cd8`

Независимый read-only reviewer проверил диапазон `e2cd386..bb82cd8` и вернул
`NEEDS_FIX`. Worktree был чистым, reviewer файлы не менял. Основные замечания:

1. P1: T‑Bank Init вызывался до гарантированного commit локального состояния.
2. P1: refund guard защищал обычный повтор, но не crash/rollback окно после
   принятого provider Cancel.
3. P1: Telegram delivery выполнялся внутри DB-транзакции; outbox был только
   foundation.
4. P2: manual provider bind не проверял provider amount/order до привязки.
5. P2: `CHECKOUT` attribution фиксировался только при confirmed payment, поэтому
   abandoned checkout выпадал из воронки.
6. Отдельно были отмечены отсутствие bot/worker entrypoints, campaign pagination,
   INIT_UNKNOWN recovery без provider identity, необязательный event scope на
   domain check-in, admin error mapping и неполная audit redaction.

### Что исправлено к `1cba547`

- Добавлен `PaymentCheckoutService`: production Telegram router сначала commit-ит
  заказ и бронь, затем отдельной транзакцией создаёт payment intent, вызывает
  T‑Bank вне транзакции и третьей транзакцией фиксирует PaymentURL/status.
- Добавлен T‑Bank `CheckOrder` (`find_by_order`) для recovery по уникальному
  merchant `OrderId`; повторный Init не используется как способ «попробовать
  ещё раз» после неизвестного результата.
- `bind_provider_payment()` делает `GetState`, проверяет provider identity,
  amount и `OrderId` при наличии поля в ответе.
- Refund теперь записывается как `payment.refund` в transactional outbox.
  `PaymentRefundOutboxWorker` забирает job с lease, делает status lookup перед
  Cancel, фиксирует terminal/unknown result отдельной транзакцией и не повторяет
  Cancel вслепую после ambiguous response.
- Campaign delivery теперь создаёт `CampaignDelivery` и
  `campaign.telegram_message` в одной DB-транзакции. Внешний Telegram call
  выполняется `CampaignOutboxWorker` после commit; lease, retry и terminal
  blocked state сохраняются в БД.
- `CHECKOUT` funnel event создаётся при создании заказа, а `PURCHASE` остаётся
  только на подтверждённой оплате.
- Compose теперь содержит отдельные `api`, `bot` и `worker` services.
- Ранее закрытые findings сохранены: обязательный event-scoped check-in,
  pagination campaign, admin payment routes/error mapping, legal consent
  validation, payload/audit redaction, inactive admin session checks,
  purchase attribution и реальные runtime entrypoints.

## Текущее состояние ревью на момент архива

После commit `1cba547` был запущен новый read-only re-review; его статус в
архивном bundle не был приложен. Поэтому текущая ветка использует отдельный
self-review checklist и не выдаёт исторический незавершённый review за новый
PASS.

## Оставшиеся риски, не замаскированные зелёными тестами

### P1/P2 — production hardening

- PostgreSQL outbox даёт at-least-once delivery. Если Telegram принял сообщение,
  а фиксация `CampaignDelivery` упала, после lease возможен повтор. Telegram
  sender не предоставляет здесь ключ идемпотентности; нужна согласованная
  бизнес-политика дублей или provider-level solution.
- Если T‑Bank Cancel принят, а worker падает до фиксации результата, следующий
  запуск сначала делает GetState. При временно несогласованном provider status
  локальная операция остаётся `REFUND_UNKNOWN`; оператор должен выполнить
  reconcile, а не повторный blind Cancel.
- Payment intent recovery по CheckOrder восстанавливает provider identity, но
  CheckOrder может не вернуть PaymentURL. Это безопасно против второго списания,
  но клиентский путь требует ручной сверки/повторной выдачи ссылки.
- `PaymentService.start()` сохранён как legacy helper. В production router он не
  используется; новые callers должны применять `PaymentCheckoutService`.
- Outbox worker сейчас polling по PostgreSQL. Redis есть в Compose, но полноценная
  Redis-backed scheduling/metrics/rate-limit политика не завершена.

### Release gates

- Реальный T‑Bank sandbox Init/GetState/CheckOrder/Cancel/webhook/refund smoke.
- Реальный Telegram token, webhook/polling run, rate limits и проверка ошибок.
- HTTPS, secret manager, production consent texts/versions, retention/deletion.
- Первичный owner admin, backup encryption, RPO/RTO и restore rehearsal.
- Docker Compose config настоящим Docker CLI или CI. Локально Docker отсутствовал;
  Compose YAML разобран PyYAML и дал services `api, bot, worker, postgres, redis`.
- Финальное review текущего continuation range `ea98bdd..HEAD` должно быть
  зафиксировано в SDD-журнале; при отсутствии subagent tool выполняется как
  отдельный self-review с code-reviewer checklist.

## Фактические проверки continuation `ea98bdd..HEAD`

```text
pytest -q                         258 passed in 186.36s
ruff format --check .             passed; 138 files already formatted
ruff check .                      passed
mypy src                          passed; 91 source files
compileall -q src tests scripts   passed
runtime imports                   passed without network calls
scripts/check_secrets.py          Secret scan passed
alembic upgrade head              passed
alembic check                     No new upgrade operations detected
PyYAML docker-compose parse       passed; api, bot, worker, postgres, redis
git diff --check                  passed
```

Docker CLI is unavailable in the local environment, so
`docker compose config --quiet` remains an unverified external gate.

## Фактические проверки архивного `1cba547`

```text
pytest -q                         249 passed in 120.90s
ruff format --check .             passed; 134 files already formatted
ruff check .                      passed
mypy src                          passed; 90 source files
compileall -q src tests scripts   passed
runtime imports                   passed without network calls
scripts/check_secrets.py          Secret scan passed
alembic upgrade head              passed
alembic check                     No new upgrade operations detected
PyYAML docker-compose parse       passed
git diff --check                  passed
```

Ранний финальный reviewer для `bb82cd8` также подтверждал полный набор старых
проверок и чистый worktree, но его итог был `NEEDS_FIX`; именно поэтому в этом
срезе были добавлены transaction-boundary/outbox изменения.
