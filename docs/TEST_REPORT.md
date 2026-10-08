# Отчёт проверок MVP

Дата прогона: 2026-10-08, окружение `Europe/Moscow`.

## Continuation hardening status

Текущая ветка `codex/povod-payment-hardening` продолжает архивный baseline
`ea98bdd`. Добавлены и проверены PostgreSQL integration tests для durable Init
lease/recovery, concurrent unknown-webhook deduplication, canonical payment
lock order, admin provider orchestration и campaign schedule validation.

Focused результаты перед финальным полным прогоном:

- `test_payment_hardening.py`, `test_tbank_webhook_idempotency.py` и
  `test_payment_after_expiry.py` — **16 passed**.
- `test_payment_admin_orchestration.py` вместе с payment-after-expiry — **9
  passed**.
- `test_consent_gated_campaign.py` — **4 passed**.

Финальный continuation suite и статические gates завершены:

- `pytest -q` — **259 passed** (`179.79s`) на disposable PostgreSQL
  `127.0.0.1:55432/povod_task4_test`.
- `ruff format --check .` — passed; 138 files already formatted.
- `ruff check .` — passed.
- `mypy src` — passed; 91 source files.
- `compileall -q src tests scripts` — passed.
- `scripts/check_secrets.py` — `Secret scan passed`.
- `alembic upgrade head` и `alembic check` — passed; no new upgrade operations.
- Runtime imports и PyYAML Compose parse — passed; services `api, bot, worker,
  postgres, redis`.
- `git diff --check` — passed.

Отдельный self-review continuation range `ea98bdd..HEAD` завершён. В ходе
проверки найден и исправлен regression промежуточных статусов T‑Bank: они
ошибочно классифицировались как refund flow. Добавлен regression test; после
фикса focused webhook suite — **3 passed**, полный suite — **259 passed**.
Неразрешённых Critical/Important findings по текущему срезу не осталось.

Приведённые ниже 249 тестов относятся к архивному baseline и сохранены как
историческая точка сравнения.

## Пройдено

- `pytest -q` — **249 passed** (`120.90s`) на PostgreSQL после очистки
  disposable public schema
  `127.0.0.1:55432/povod_task2_test`.
- `pytest tests/integration/test_identity_migration.py -q` — **2 passed** (`2.26s`);
  миграции проходят upgrade/downgrade/upgrade и metadata comparison.
- Regression набор после transaction-boundary hardening — **13 passed**: batched
  campaign outbox delivery, event-scoped check-in, unknown Init recovery,
  provider bind validation, payment-intent orchestration and refund outbox.
- Telegram checkout/tickets + recreated dispatcher — **16 passed**: consent
  onboarding, checkout reservation/payment link and user ticket QR view.
- `python -m ruff format --check .` — passed.
- `python -m ruff check .` — passed.
- `python -m mypy src` — passed, 90 source files.
- `python -m compileall -q src tests scripts` — passed.
- `python -c "import src.bot.main, src.workers.main"` — runtime entrypoints
  import without network calls.
- `python -m alembic upgrade head` — passed on disposable PostgreSQL.
- `python -m alembic check` — `No new upgrade operations detected.`
- Compose YAML parsed with PyYAML; services resolved as `api, bot, worker,
  postgres, redis`.
- `git diff --check` — passed; CRLF warnings Git не являются ошибками содержимого.
- `python scripts/check_secrets.py` — `Secret scan passed`.
- Архивное ownership review — **PASS**; PostgreSQL triggers и порядок downgrade
  проверены отдельным reviewer.

## Ограничения

- `docker compose config --quiet` не выполнен локально: в рабочем окружении нет
  команды `docker`. CI workflow содержит этот gate.
- Реальный sandbox-платёж T‑Bank и Telegram API не вызываются из тестов; вместо
  этого проверены официальный token algorithm, HTTP adapter, webhook signature,
  duplicate/late status policy и fake gateway сценарии. Перед коммерческим
  запуском нужен отдельный sandbox smoke test с credentials владельца.
- Backup/restore scripts проверены статически и защищены явным target/confirmation;
  фактический restore требует отдельного recovery PostgreSQL и инфраструктурных
  credentials.
- Telegram delivery и refund commands теперь проходят через PostgreSQL
  transactional outbox: внешний вызов выполняется вне DB-транзакции, результат
  фиксируется отдельной транзакцией. Worker использует lease и status lookup.
  Redis-backed scheduler для горизонтального масштабирования пока не включён.
  При краше между успешным Telegram-вызовом и фиксацией результата возможна
  повторная доставка: Telegram API не предоставляет используемый здесь ключ
  идемпотентности, поэтому это остаётся release-hardening риском.

## Release risks requiring owner confirmation

- Утвердить юридические тексты согласий и retention/deletion policy.
- Утвердить production webhook URL, T‑Bank fiscalization/sandbox settings,
  backup encryption, RPO/RTO и способ создания первого owner admin.
- Выполнить sandbox payment + refund smoke test и isolated restore rehearsal.
- Self-review continuation range `ea98bdd..HEAD` выполнен и сохранён в
  SDD-журнале; остающиеся пункты выше требуют внешнего sandbox/infrastructure
  подтверждения перед коммерческим запуском.
