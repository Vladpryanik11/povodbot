# Архитектура «Повод»

Авторитетный источник: `superpowers/specs/2026-10-08-povod-mvp-design.md`.
Один клуб, один репозиторий, модульный монолит, общая PostgreSQL как источник
истины. API, Telegram-бот и worker запускаются отдельными процессами и используют
общие сервисы. Redis служит очереди, а не источником финансового состояния.

API/FastAPI, bot/aiogram 3 и лёгкая web-admin/Jinja2/HTMX образуют границы.
Services определяют бизнес-операции, repositories изолируют SQL и блокировки,
models описывают данные. Направления — записи базы, а не enum. Платёжный адаптер
Т-Банка реализует порт PaymentGateway; бизнес-сервисы не зависят от payload банка.
Надёжная доставка важных событий использует transactional outbox или эквивалент.

Task 1 реализует `core/config`, `core/logging`, `db/session`, фабрику `api/app`
и endpoints `/health` и `/ready`. `get_settings()` кеширует валидированную
конфигурацию; секретные поля используют SecretStr, URL скрыты из repr.
Engine и sessionmaker создаются лениво. Dependency открывает транзакцию,
фиксирует успешную работу, откатывает исключение и закрывает session.
Lifespan настраивает JSON-логи и освобождает engine при остановке.
Импорт и создание app не выполняют миграции или сетевые вызовы.

`/health` возвращает 200 без БД. `/ready` выполняет `SELECT 1` и возвращает 200
или безопасный 503 без текста ошибки драйвера. Таймаут ограничивает проверку БД.
Redis readiness добавляется при реализации worker; сейчас он не нужен API.

Python 3.12+, SQLAlchemy 2 async/asyncpg, Pydantic Settings, FastAPI/Uvicorn,
structlog; версии прямых зависимостей закреплены в pyproject.toml.
CI проверяет pytest на disposable PostgreSQL, Ruff, mypy и Compose config.
Локальные foundation-тесты допускают временный SQLite исключительно для SELECT 1
и базовых транзакций; конкурентная бронь требует настоящего PostgreSQL.

Суммы вычисляются сервером, бронь длится 600 секунд, timestamps timezone-aware
в UTC, timezone мероприятия хранится явно. Подтверждение платежей, дедупликация,
защита вместимости, QR и согласия реализуются последующими задачами плана.
