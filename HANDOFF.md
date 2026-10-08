# «Повод» — handoff для новой сессии

Дата упаковки: 2026-10-08, Europe/Moscow.

## Какой срез передан

Это проверенный MVP одного клуба «Повод» без мультиарендности. Направления
мероприятий хранятся данными в PostgreSQL, поэтому новые направления можно
добавлять без изменения кода. Платежи идут через T‑Bank Internet Acquiring из
кабинета Т‑Бизнеса, а не через API исходящих банковских переводов.

Архивный базовый срез был передан в ветке `codex/povod-task-3` на commit
`1cba547`. Продолжение ведётся в отдельном clone/worktree:

```text
codex/povod-payment-hardening
base ea98bdd docs: add project handoff and review record
C:\Users\Влад\Documents\Codex\2026-09-24\b2b-1-ux-ui-sku-2-2\work\povod-mvp-git
```

Исходные пользовательские папки и приложенные bundle/zip не изменялись. В
продолжении закрыты четыре payment/campaign hardening среза: durable Init
lease и recovery, атомарная deduplication неизвестных webhook, порядок lock
`event → order → payment`, admin orchestration для provider `GetState`/bind и
валидация timezone-aware будущего расписания кампании. Архивный baseline и
документация находятся в следующих файлах:

- `README.md` — установка, запуск и проверки;
- `HANDOFF.md` — этот переносимый контекст;
- `docs/REVIEW_REPORT.md` — история ревью, закрытые и оставшиеся замечания;
- `docs/TEST_REPORT.md` — фактические проверки и release gates;
- `docs/superpowers/specs/2026-10-08-povod-mvp-design.md` — рабочая
  архитектурная спецификация;
- `docs/superpowers/plans/2026-10-08-povod-mvp-implementation-plan.md` — план;
- `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md` и `docs/ROADMAP.md`;
- `migrations/` — Alembic migration chain;
- `src/` — API, bot, services, repositories, models и workers;
- `tests/` — unit/integration тесты на PostgreSQL и foundation-тесты;
- `docker-compose.yml`, `Dockerfile`, `.env.example`, `pyproject.toml`.
- `migrations/versions/0008_payment_init_lease.py` — durable lease для Init.
- `docs/superpowers/plans/2026-10-08-povod-payment-hardening.md` — план
  продолжения hardening.

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
14. Payment Init получает durable lease: конкурентный checkout делает один
    provider Init, а просроченный lease переводит платеж в recovery без
    повторного списания; поздний matching response привязывается idempotently.
15. Webhook path атомарно дедуплицирует неизвестные события через PostgreSQL
    `ON CONFLICT DO NOTHING`; известные платежные переходы используют единый
    lock order `event → order → payment`, включая refund request/worker.
16. Admin reconcile и bind разделяют короткие DB-транзакции и внешний
    provider вызов; проверенный snapshot применяется отдельной транзакцией.
17. `CampaignService.create_draft()` валидирует optional `scheduled_at` как
    timezone-aware timestamp в будущем и сохраняет его в UTC.

## Актуальные проверки именно этого среза

Проверки продолжения выполняются в текущем clone на disposable PostgreSQL:

```text
TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/povod_task4_test
```

Результаты:

```text
pytest -q                         259 passed in 180.28s
ruff format --check .             passed; 138 files already formatted
ruff check .                      passed
mypy src                          passed; 91 source files
compileall src tests scripts      passed
import runtime entrypoints        passed without network calls
scripts/check_secrets.py          Secret scan passed
alembic upgrade head              passed
alembic check                     No new upgrade operations detected
Compose YAML parse                passed; api, bot, worker, postgres, redis
git diff --check                  passed
```

Отдельный self-review continuation range `ea98bdd..HEAD` завершён. Он выявил
и закрыл regression, при котором промежуточные статусы T‑Bank ошибочно
попадали в refund flow; добавлен regression test, а полный suite после фикса
проходит зелёным. Неразрешённых Critical/Important findings по текущему
срезу не осталось; внешние release gates перечислены ниже.

`docker compose config --quiet` по-прежнему не выполнен, потому что на машине
не установлена команда `docker`. YAML отдельно разбирается PyYAML, а CI должен
выполнить настоящий Compose gate.

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

   Ожидается ветка `codex/povod-payment-hardening`; точный HEAD зависит от
   последнего continuation-коммита. Если архив был распакован без `.git`, этот
   пункт можно пропустить.

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
- Portable PostgreSQL 16.15 для локальной проверки запускается без Windows
  service на `127.0.0.1:55432`; это disposable test environment, не production
  database.

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
