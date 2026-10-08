# Отчёт проверок MVP

Дата прогона: 2026-10-08, окружение `Europe/Moscow`.

## Continuation hardening status

Текущая ветка `codex/povod-payment-hardening` продолжает архивный baseline
`ea98bdd`; проверка Task 3 выполнялась на `f21f0d0` до документационного
коммита. Task 1 был рассмотрен live multi-agent reviewer и получил **PASS** в
`201b3e8`. Попытка Task 2 в `dc42d72` получила **NEEDS REVISION**, потому что
не меняла production behavior относительно Task 1 и добавляла redundant test;
она откатена в `f21f0d0`, scoped re-review получил **PASS**. Поэтому Task 2
считается pre-satisfied Task 1, а не отдельным production change.

Fresh Task 3 verification:

- `python -m pytest -q tests/integration/test_consent_gated_campaign.py` —
  **6 passed in 8.08s** на disposable PostgreSQL
  `127.0.0.1:55432/povod_task5_test`.
- `python -m pytest -q` — **261 passed in 203.45s (0:03:23)** на том же
  disposable PostgreSQL.
- `python -m ruff format --check .` — passed; **138 files already formatted**.
  Mixed line endings in the already-committed outbox file were normalized
  mechanically; the normalized file has no Git content diff.
- `python -m ruff check .` — `All checks passed!`.
- `python -m mypy src` — `Success: no issues found in 91 source files`.
- `python -m compileall -q src tests scripts` — passed.
- `python scripts/check_secrets.py` — `Secret scan passed`.
- Runtime imports of `src.api.app`, `src.bot.main` and `src.workers.main` —
  passed without network calls.
- `python -m alembic upgrade head` и `python -m alembic check` — passed; no
  new upgrade operations detected.
- PyYAML Compose parse — passed; services resolved as `api, bot, worker,
  postgres, redis`.
- `git diff --check` — passed.

The Docker CLI is not installed, so `docker compose config --quiet` remains an
unverified CI gate. No real Telegram call was made. The PostgreSQL outbox
still has the unchanged at-least-once limitation: if Telegram accepts a
message and the process fails before the finish transaction commits, the lease
can cause a retry, and Telegram does not provide a project-used idempotency
key. This remains an external release risk.

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
