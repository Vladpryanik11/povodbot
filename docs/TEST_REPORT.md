# Отчёт проверок MVP

Дата прогона: 2026-10-08, окружение `Europe/Moscow`.

## Пройдено

- `pytest -q` — **245 passed** (`118.29s`) на PostgreSQL после очистки
  disposable public schema
  `127.0.0.1:55432/povod_task2_test`.
- `pytest tests/integration/test_identity_migration.py -q` — **2 passed** (`2.26s`);
  миграции проходят upgrade/downgrade/upgrade и metadata comparison.
- Regression набор — **10 passed**: batched campaign delivery, event-scoped
  check-in, unknown Init binding/reconciliation and refund recovery.
- Telegram checkout/tickets + recreated dispatcher — **16 passed**: consent
  onboarding, checkout reservation/payment link and user ticket QR view.
- `python -m ruff format --check .` — passed.
- `python -m ruff check .` — passed.
- `python -m mypy src` — passed, 86 source files.
- `python -m compileall -q src tests scripts` — passed.
- `python -m alembic upgrade head` — passed on disposable PostgreSQL.
- `python -m alembic check` — `No new upgrade operations detected.`
- `git diff --check` — passed; CRLF warnings Git не являются ошибками содержимого.
- `python scripts/check_secrets.py` — `Secret scan passed`.
- Task 4 независимое ownership review — **PASS**; PostgreSQL triggers и порядок
  downgrade проверены отдельным reviewer.

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
- Telegram delivery пока выполняется через текущий worker-контракт; перед
  production нужен Redis-backed runner/outbox для отделения внешнего Telegram
  вызова от транзакции БД. Возвраты и потерянные Init защищены локальными
  состояниями и ручной сверкой, но всё равно требуют provider smoke/recovery
  rehearsal.

## Release risks requiring owner confirmation

- Утвердить юридические тексты согласий и retention/deletion policy.
- Утвердить production webhook URL, T‑Bank fiscalization/sandbox settings,
  backup encryption, RPO/RTO и способ создания первого owner admin.
- Выполнить sandbox payment + refund smoke test и isolated restore rehearsal.
