# Развёртывание

1. Создать PostgreSQL и Redis в закрытой сети.
2. Передать секреты через secret manager или environment runtime; `.env` не
   коммитится.
3. Выполнить `python -m alembic upgrade head` отдельным release job.
4. Запустить API, Telegram bot и worker отдельными процессами из одного образа.
5. Зарегистрировать T‑Bank webhook на публичный HTTPS URL
   `/api/webhooks/tbank/payment-status` и настроить shared webhook secret.
6. Проверить `/health`, `/ready`, `/metrics`, логи redaction и тестовый платёж.

В production обязательны `ENVIRONMENT=production`, Telegram token, terminal key,
T‑Bank password, webhook secret и отдельный QR secret. Секреты не выводятся в
логах и не передаются в URL. Cookie админки в production помечена `Secure`.

Для rollback сначала остановить worker, затем откатить приложение. Откат схемы
разрешён только после проверки совместимости данных и отдельного backup.
