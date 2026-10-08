# «Повод» — handoff для новой сессии

Дата упаковки: 2026-10-08, Europe/Moscow.

## Какой срез передан

Это проверенный MVP одного клуба «Повод» без мультиарендности. Направления
мероприятий хранятся данными в PostgreSQL, поэтому новые направления можно
добавлять без изменения кода. Платежи идут через T‑Bank Internet Acquiring из
кабинета Т‑Бизнеса, а не через API исходящих банковских переводов.

Рабочая ветка:

```text
codex/povod-task-3
HEAD 1cba547 feat: harden payment and delivery transaction boundaries
```

Текущий изолированный worktree:

```text
C:\Users\79268\.codex\worktrees\povod-mvp\Бот Повод
```

Исходная пользовательская папка не изменялась:

```text
C:\Users\79268\Documents\ChatGPT\Бот Повод
```

После commit `1cba547` worktree был чистым. Архив содержит именно этот срез и
документацию из следующих файлов:

- `README.md` — установка, запуск и проверки;
- `HANDOFF.md` — этот переносимый контекст;
- `docs/REVIEW_REPORT.md` — история ревью, закрытые и оставшиеся замечания;
- `docs/TEST_REPORT.md` — фактические проверки и release gates;
- `docs/superpowers/specs/2026-10-08-povod-mvp-design.md` — утверждённая
  спецификация;
- `docs/superpowers/plans/2026-10-08-povod-mvp-implementation-plan.md` — план;
- `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md` и `docs/ROADMAP.md`;
- `migrations/` — Alembic migration chain;
- `src/` — API, bot, services, repositories, models и workers;
- `tests/` — unit/integration тесты на PostgreSQL и foundation-тесты;
- `docker-compose.yml`, `Dockerfile`, `.env.example`, `pyproject.toml`.

## Что уже работает

1. `/start`, профиль Telegram, сохранение attribution `start_param`, два
   независимых согласия с версиями и `/stop`.
2. Каталог направлений и опубликованных мероприятий, типы билетов, серверная
   фиксация цен, лимиты вместимости.
3. Атомарная бронь последних мест, заказ, TTL 600 секунд, освобождение через
   worker и ленивую проверку.
4. T‑Bank v2 adapter: подпись Token, `/v2/Init`, `/v2/GetState`,
   `/v2/CheckOrder`, `/v2/Cancel`, обработка typed provider errors.
5. Telegram checkout: `buy:*` → `quantity:*` → commit заказа/брони → commit
   payment intent → T‑Bank Init вне DB-транзакции → сохранение PaymentURL.
6. Signed T‑Bank webhook, deduplication, late payment/reconciliation, tickets
   после подтвержденного статуса и QR check-in с обязательным `event_id`.
7. Потерянный Init: lookup по стабильному merchant `OrderId` через CheckOrder;
   если восстановить identity нельзя — `INIT_UNKNOWN`/
   `RECONCILIATION_REQUIRED` и ручные admin endpoints.
8. Админская cookie-session auth, RBAC, audit и payment routes:
   просмотр, reconcile, bind-provider, refund.
9. Manual provider bind теперь до привязки получает provider state и проверяет
   provider ID, сумму и, если T‑Bank её возвращает, `OrderId`.
10. Refund: локальное состояние и команда фиксируются в PostgreSQL outbox;
    worker сначала делает provider status lookup, затем Cancel только если
    возврат ещё не начат. Неясный результат переводится в `REFUND_UNKNOWN` для
    ручной сверки без слепого повторного Cancel.
11. Consent-gated CRM segments и campaign delivery. Кампания сначала создаёт
    `CampaignDelivery` + outbox в транзакции; внешний Telegram вызов выполняется
    worker вне этой транзакции, затем результат фиксируется отдельно.
12. Реальные runtime entrypoints:

    ```text
    uvicorn src.api.app:create_app --factory
    python -m src.bot.main
    python -m src.workers.main
    ```

13. Docker Compose теперь объявляет `api`, `bot`, `worker`, `postgres`, `redis`.

## Актуальные проверки именно этого среза

Все проверки выполнялись в worktree из этого файла, на disposable PostgreSQL:

```text
TEST_DATABASE_URL=postgresql+asyncpg://povod@127.0.0.1:55432/povod_task2_test
```

Результаты:

```text
pytest -q                         249 passed in 120.90s
ruff format --check .             passed; 134 files already formatted
ruff check .                      passed
mypy src                          passed; 90 source files
compileall src tests scripts      passed
import runtime entrypoints        passed without network calls
scripts/check_secrets.py          Secret scan passed
alembic upgrade head              passed
alembic check                     No new upgrade operations detected
Compose YAML parse                passed; api, bot, worker, postgres, redis
git diff --check                  passed
```

`docker compose config --quiet` не был выполнен, потому что на машине не
установлена команда `docker`. Это единственная локальная проверка, которую
нельзя было подтвердить реальным Docker CLI; YAML отдельно разобран PyYAML, а
CI должен выполнить настоящий Compose gate.

При работе с локальным PostgreSQL тесты создают схемы `task2_<uuid>` и удаляют
их после каждого теста. Это disposable database, не production data.

## Что нужно сделать в новой сессии сначала

1. Распаковать архив в новую рабочую папку и открыть именно её.
2. Прочитать `HANDOFF.md`, затем `docs/REVIEW_REPORT.md`,
   `docs/TEST_REPORT.md`, спецификацию и план.
3. Проверить:

   ```powershell
   git status --short
   git rev-parse --short HEAD
   git branch --show-current
   ```

   Ожидается `1cba547` и ветка `codex/povod-task-3`; если архив был распакован
   без `.git`, этот пункт можно пропустить.

4. Не переписывать утверждённые инварианты из roadmap: один клуб, event
   directions как данные, серверные суммы, 600 секунд брони, подтверждение
   только по проверенному T‑Bank status, deduplication, consent gate, QR
   single-use и отсутствие секретов в Git.
5. Если продолжение касается платежей, сначала прочитать
   `src/services/payments/checkout.py`, `src/services/payments/service.py`,
   `src/services/payments/tbank_client.py` и `src/workers/outbox.py`.

## Что нельзя считать production-ready без владельца

- Реальный T‑Bank sandbox smoke: Init → оплата → webhook → GetState → ticket,
  поздняя оплата, Cancel/refund и повторные webhook.
- Публичный HTTPS webhook URL и production secrets/terminal settings.
- Финальные юридические тексты согласия, их версии, retention/deletion policy
  и процедура удаления/обезличивания.
- Создание первого owner admin, HTTPS, cookie policy и secret manager.
- Backup encryption, RPO/RTO и фактическая isolated restore rehearsal.
- Реальный Telegram bot run с боевым token и проверка rate limits.
- Проверка Docker Compose настоящим Docker CLI/CI.

## Технические ограничения, которые уже записаны намеренно

- Outbox worker использует PostgreSQL polling + lease. Redis подключён в Compose,
  но не является источником финансового состояния и пока не используется как
  горизонтальный scheduler.
- Доставка Telegram имеет at-least-once окно: если Telegram принял сообщение,
  а процесс упал до фиксации результата, lease может привести к повтору. У
  Telegram API нет используемого проектом provider idempotency key; это нужно
  закрыть бизнес-политикой, provider-level deduplication или accept/retry
  decision перед масштабированием.
- Refund защищён status lookup и неясным состоянием. Если provider status
  временно не отражает принятый Cancel, операция остаётся `REFUND_UNKNOWN` и
  требует reconcile/operator action.
- `PaymentService.start()` оставлен как legacy single-session helper для
  существующих service-level callers/tests. Production Telegram router уже
  использует `PaymentCheckoutService`, который разделяет транзакции. Новые
  production callers должны использовать orchestrator, а legacy helper можно
  удалить после миграции всех внутренних вызовов.
- Потерянный T‑Bank Init можно сопоставить по OrderId, но CheckOrder может не
  вернуть PaymentURL. Тогда платеж не создаётся повторно, но клиенту нужен
  operator/reconciliation path.
- QR в Telegram сейчас передаётся как непрозрачный token-текст; генерация
  изображения QR остаётся отдельным UX улучшением, криптографическая проверка и
  single-use check-in уже реализованы.

## Официальные T‑Bank материалы

- [Init](https://developer.tbank.ru/eacq/api/init)
- [CheckOrder](https://developer.tbank.ru/eacq/api/check-order)
- [GetState](https://developer.tbank.ru/eacq/api/get-state)
- [Token](https://developer.tbank.ru/eacq/intro/developer/token)
- [Notifications](https://developer.tbank.ru/eacq/intro/developer/notification/)

## Как продолжить и проверить после распаковки

```powershell
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install -e '.[dev]'
Copy-Item .env.example .env
python -m alembic upgrade head
python -m pytest -q
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python scripts/check_secrets.py
```

Для runtime с локальными сервисами:

```powershell
docker compose up -d postgres redis
python -m alembic upgrade head
uvicorn src.api.app:create_app --factory --reload
# в отдельных окнах:
python -m src.bot.main
python -m src.workers.main
```

Или после миграции выполнить `docker compose up --build`: Compose поднимает
API, bot, worker, PostgreSQL и Redis.
