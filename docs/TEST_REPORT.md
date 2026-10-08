# Отчёт проверок MVP

Дата прогона: 2026-10-08, окружение `Europe/Moscow`.

## Пройдено

- `pytest -q` — **240 passed** (`106.78s`) на PostgreSQL после очистки
  disposable public schema
  `127.0.0.1:55432/povod_task2_test`.
- `pytest tests/integration/test_identity_migration.py -q` — **2 passed**;
  миграции проходят upgrade/downgrade/upgrade и metadata comparison.
- Scoped Task 7/8 набор — **8 passed**: admin session, permissions, campaign
  consent gate, idempotent delivery, migration and queue checks.
- `python -m ruff format --check .` — passed.
- `python -m ruff check .` — passed.
- `python -m mypy src` — passed, 82 source files.
- `python -m compileall -q src tests scripts` — passed.
- `git diff --check` — passed; CRLF warnings Git не являются ошибками содержимого.
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

## Release risks requiring owner confirmation

- Утвердить юридические тексты согласий и retention/deletion policy.
- Утвердить production webhook URL, T‑Bank fiscalization/sandbox settings,
  backup encryption, RPO/RTO и способ создания первого owner admin.
- Выполнить sandbox payment + refund smoke test и isolated restore rehearsal.
