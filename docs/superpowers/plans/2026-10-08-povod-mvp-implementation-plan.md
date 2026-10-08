# «Повод» MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить тестируемый MVP Telegram-продукта клуба «Повод» с продажей билетов через API интернет-эквайринга Т‑Банка, CRM, QR-билетами, check-in, админкой и согласованными рассылками.

**Architecture:** Один репозиторий и модульный монолит с отдельными runtime-процессами для Telegram-бота, FastAPI и worker. PostgreSQL является источником истины для пользователей, мероприятий, броней, заказов, платежей, билетов и аудита; Redis используется для фоновых задач и очереди. Платёжный провайдер изолирован портом `PaymentGateway`, а направления мероприятий представлены данными, а не жёстким перечислением в коде.

**Tech Stack:** Python 3.12+, aiogram 3, FastAPI, Uvicorn, SQLAlchemy 2 async, asyncpg, PostgreSQL, Alembic, Pydantic Settings, httpx, Redis, Python worker, Jinja2/HTMX для первой веб-админки, pytest, pytest-asyncio, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-08-povod-mvp-design.md`

**Status (2026-10-08):** исторический implementation plan для MVP baseline.
Базовая реализация передана в архивном срезе; payment/campaign continuation
ведётся отдельным планом
`docs/superpowers/plans/2026-10-08-povod-payment-hardening.md`. Чекбоксы ниже
сохраняют исторический журнал агентской сессии и не являются актуальным
release checklist. Реальные T‑Bank/Telegram/Docker/backup gates остаются
неподтверждёнными без соответствующей инфраструктуры и credentials.

## Global Constraints

- Один клуб «Повод»; мультиарендность и организации не входят в MVP.
- Направления мероприятий хранятся в таблице и добавляются без выпуска новой версии приложения.
- Общий MVP-сценарий: мероприятие → билеты → бронь → платёж Т‑Банка → подтверждение → QR-билет → check-in.
- Срок временной брони — 600 секунд; истечение обрабатывается worker-задачей и ленивой проверкой при новой покупке.
- Подтверждение оплаты определяется проверенным статусом Т‑Банка, а не редиректом клиента.
- Повторные и пришедшие не по порядку webhook-события не должны создавать повторные заказы, билеты или возвраты.
- Сумма заказа рассчитывается только на сервере по цене, зафиксированной в `order_items`.
- Telegram ID, slug направления, внешний ID платежа в рамках провайдера и deduplication key webhook-события уникальны.
- Рекламные сообщения отправляются только при действующем согласии, проверенном непосредственно перед доставкой.
- QR-токен не является последовательным ID; повторный check-in запрещён.
- Персональные данные, токены, ключи и платёжные реквизиты не попадают в Git и обычные логи.
- Все временные значения timezone-aware; хранение системных timestamps — в UTC, часовой пояс мероприятия хранится явно.
- Реализация начинается с теста, затем минимальный код, затем рефакторинг; каждый срез завершается фактически запущенными проверками и отдельным коммитом.
- Реализация ведётся в изолированной рабочей ветке/worktree; основная ветка не изменяется до прохождения проверок.

## Review Focus

- Конкурентная покупка последних мест: два одновременных заказа не могут превысить вместимость — тест в Task 4.
- Дублированные и переставленные webhook Т‑Банка: побочные эффекты применяются ровно один раз — тест в Task 5.
- Отзыв рекламного согласия или блокировка бота перед рассылкой: сообщение не отправляется и результат фиксируется — тест в Task 8.
- Подделанный или уже использованный QR-токен: check-in отклоняется без изменения действительного билета — тест в Task 6.
- Эскалация административных прав и экспорт CRM сотрудником на входе: действие запрещается и не раскрывает данные — тест в Task 7.

---

## Task 1: Repository and Runtime Foundation

**Files:**

- Create: `AGENTS.md`
- Create: `README.md`
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.github/workflows/ci.yml`
- Create: `src/__init__.py`
- Create: `src/core/__init__.py`
- Create: `src/core/config.py`
- Create: `src/core/logging.py`
- Create: `src/db/__init__.py`
- Create: `src/db/session.py`
- Create: `src/api/__init__.py`
- Create: `src/api/app.py`
- Create: `src/api/health.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/integration/test_health.py`
- Create: `docs/ROADMAP.md`
- Create: `docs/ARCHITECTURE.md`
- Create: `docs/DECISIONS.md`

**Interfaces:**

- `get_settings() -> Settings` returns a cached validated configuration object.
- `get_async_session() -> AsyncIterator[AsyncSession]` provides a transaction-scoped database session for FastAPI dependencies and service tests.
- `create_app() -> FastAPI` builds the application and includes `/health` and `/ready`.
- `Settings` exposes environment, database URL, Redis URL, Telegram token, T‑Bank credentials, reservation TTL and default operational values without storing secrets in source.

- [ ] **Step 1: Write failing configuration tests**

  Add tests proving that `Settings` requires production secrets in production, accepts test values in the test environment, parses `reservation_ttl_seconds` as an integer, rejects naive/invalid URLs, and does not expose secret values in `repr`.

- [ ] **Step 2: Run configuration tests and verify the expected failure**

  Run: `pytest tests/unit/test_config.py -q`

  Expected: FAIL because the package and `Settings` implementation do not exist yet.

- [ ] **Step 3: Implement the package and configuration layer**

  Define `Settings(BaseSettings)` in `src/core/config.py`, `get_settings()` with caching, structured logging setup in `src/core/logging.py`, and the package exports. Use environment variables documented in `.env.example`; keep production-only validation explicit.

- [ ] **Step 4: Write failing health and application tests**

  Add `test_health_returns_ok` and `test_readiness_reports_database_dependency` in `tests/integration/test_health.py`. The readiness test must use the test database fixture and fail when the database dependency is unavailable.

- [ ] **Step 5: Implement database session and FastAPI app**

  Create `AsyncEngine`, `async_sessionmaker`, `get_async_session()`, `create_app()`, `/health`, and `/ready`. The app must not perform network calls or migrations at import time.

- [ ] **Step 6: Add project tooling and local services**

  Configure `pyproject.toml` scripts for `pytest`, formatting, linting and type checking. Add a non-secret `.env.example`, `.gitignore`, Dockerfile, Docker Compose services for PostgreSQL and Redis, and a CI workflow that installs dependencies and runs the checks.

- [ ] **Step 7: Document working agreements**

  Copy the approved product roadmap into `docs/ROADMAP.md`. Document the selected architecture in `docs/ARCHITECTURE.md`, and create `docs/DECISIONS.md` with the modular-monolith, T‑Bank acquiring and single-club decisions. `AGENTS.md` must require tests before completion claims, no secrets in Git, and preservation of the roadmap invariants.

- [ ] **Step 8: Run the complete foundation checks**

  Run: `pytest -q`, the configured formatter/linter/type checker, and `docker compose config`.

  Expected: all tests pass, static checks exit 0, and Compose configuration validates without requiring real credentials.

- [ ] **Step 9: Commit the foundation**

  ```bash
  git add AGENTS.md README.md pyproject.toml .gitignore .env.example Dockerfile docker-compose.yml .github src tests docs/ROADMAP.md docs/ARCHITECTURE.md docs/DECISIONS.md
  git commit -m "chore: establish povod application foundation"
  ```

## Task 2: Users, Consents, Directions and `/start`

**Files:**

- Create: `src/models/base.py`
- Create: `src/models/identity.py`
- Create: `src/models/directions.py`
- Create: `src/models/outbox.py`
- Create: `src/repositories/users.py`
- Create: `src/repositories/consents.py`
- Create: `src/repositories/directions.py`
- Create: `src/services/users/service.py`
- Create: `src/services/consents/service.py`
- Create: `src/services/directions/service.py`
- Create: `src/bot/router.py`
- Create: `src/bot/handlers/start.py`
- Create: `src/bot/keyboards/main_menu.py`
- Create: `migrations/versions/0001_identity_directions_outbox.py`
- Create: `tests/unit/services/test_users.py`
- Create: `tests/unit/services/test_consents.py`
- Create: `tests/unit/services/test_directions.py`
- Create: `tests/integration/test_start_flow.py`
- Create: `tests/integration/test_consent_revocation.py`

**Interfaces:**

- `UserService.upsert_telegram_user(telegram_id: int, first_name: str | None, last_name: str | None, username: str | None, start_param: str | None) -> UserDTO` creates or updates one CRM record without duplicating the Telegram ID.
- `ConsentService.record(user_id: UUID, consent_type: ConsentType, text_version: str, source: ConsentSource) -> ConsentDTO` appends an immutable consent event.
- `ConsentService.is_active(user_id: UUID, consent_type: ConsentType) -> bool` returns the current effective status.
- `ConsentService.revoke(user_id: UUID, consent_type: ConsentType, source: ConsentSource) -> ConsentDTO` records a revocation without deleting history.
- `DirectionService.create(command: CreateDirectionCommand) -> DirectionDTO`, `DirectionService.list_active() -> list[DirectionDTO]`, and `DirectionService.set_active(direction_id: UUID, active: bool) -> DirectionDTO` manage data-driven directions.
- `StartHandler` calls `UserService` and never writes to the database directly.

- [ ] **Step 1: Write failing user and consent tests**

  Test first `/start` creation, repeated `/start` update without duplicate, changed username update, first `start_param` preservation, separate personal-data and marketing consents, consent version recording, and revocation.

- [ ] **Step 2: Run the tests and verify failure**

  Run: `pytest tests/unit/services/test_users.py tests/unit/services/test_consents.py -q`

  Expected: FAIL because models, repositories and services do not exist.

- [ ] **Step 3: Implement identity and consent models**

  Define UUID primary keys, unique Telegram ID, nullable profile fields, immutable consent events, consent type/status enums, text version, source, timestamps and safe indexes. Use UTC timestamps and database constraints for uniqueness.

- [ ] **Step 4: Implement repositories and services**

  Implement `upsert_telegram_user` as a single transaction-safe operation. Preserve the first attribution parameter while allowing the latest known source to be updated later. Implement append-only consent history and effective-status lookup.

- [ ] **Step 5: Write failing direction tests**

  Test creating active/inactive directions, unique slugs, stable ordering, and listing only active directions for the client.

- [ ] **Step 6: Implement direction model, repository and service**

  Add configurable direction records and seed only the initial data through an explicit seed command or migration, not through import side effects.

- [ ] **Step 7: Add migration and `/start` flow**

  Create the Alembic migration, bot router, `/start` handler, consent prompt and main-menu keyboard. The handler must recover from a restarted process using persisted user data.

- [ ] **Step 8: Verify the integration scenarios**

  Run: `pytest tests/integration/test_start_flow.py tests/integration/test_consent_revocation.py -q`

  Expected: user creation is idempotent, consent history is preserved, and revoked marketing consent is reported inactive.

- [ ] **Step 9: Commit the identity slice**

  ```bash
  git add src/models src/repositories src/services/users src/services/consents src/services/directions src/bot migrations tests
  git commit -m "feat: add users consents and event directions"
  ```

## Task 3: Events, Ticket Types and Public Showcases

**Files:**

- Create: `src/models/events.py`
- Create: `src/repositories/events.py`
- Create: `src/services/events/service.py`
- Create: `src/api/admin/events.py`
- Create: `src/api/public/events.py`
- Create: `src/bot/handlers/events.py`
- Create: `src/bot/keyboards/events.py`
- Create: `migrations/versions/0002_events_ticket_types.py`
- Create: `tests/unit/services/test_events.py`
- Create: `tests/integration/test_event_publication.py`
- Create: `tests/integration/test_event_capacity.py`

**Interfaces:**

- `EventService.create_draft(command: CreateEventCommand) -> EventDTO` validates required event data and creates a draft.
- `EventService.publish(event_id: UUID) -> EventDTO` validates direction, date, timezone, capacity and at least one active ticket type before publication.
- `EventService.update(event_id: UUID, command: UpdateEventCommand) -> EventDTO` applies allowed edits without silently changing historical order prices.
- `EventService.list_public(direction_id: UUID | None, from_date: date | None) -> list[PublicEventDTO]` returns only published, non-cancelled, non-completed events.
- `EventService.get_public(event_id: UUID) -> PublicEventDTO` returns the client-safe event card.

- [ ] **Step 1: Write failing event lifecycle tests**

  Test draft creation, required-field validation, publication rejection without ticket types, publication success, cancellation, completion, inactive directions and client filtering.

- [ ] **Step 2: Run the tests and verify failure**

  Run: `pytest tests/unit/services/test_events.py -q`

  Expected: FAIL because event models and services do not exist.

- [ ] **Step 3: Implement event and ticket-type models**

  Store title, description, cover reference, direction, start/end timestamps, explicit timezone, address, map URL, capacity, status and publication timestamps. Store ticket name, price in integer kopecks, currency, limit and active status.

- [ ] **Step 4: Implement event repository and service state transitions**

  Enforce lifecycle transitions in the service. Do not delete published events; use cancellation/completion states so orders and audit history remain referentially valid.

- [ ] **Step 5: Add API and bot read paths**

  Add admin endpoints for drafts and edits, public endpoints for the client-safe view, and bot handlers/keyboards for direction and event selection. Do not expose administrative fields or internal IDs unnecessarily.

- [ ] **Step 6: Verify capacity and publication integration**

  Run: `pytest tests/integration/test_event_publication.py tests/integration/test_event_capacity.py -q`

  Expected: only valid events appear in the public showcase, and capacity is visible without allowing client-side mutation.

- [ ] **Step 7: Commit the events slice**

  ```bash
  git add src/models/events.py src/repositories/events.py src/services/events src/api/admin/events.py src/api/public/events.py src/bot migrations tests
  git commit -m "feat: add event catalog and ticket types"
  ```

## Task 4: Reservations, Orders and Checkout State Machines

**Files:**

- Create: `src/models/commerce.py`
- Create: `src/repositories/reservations.py`
- Create: `src/repositories/orders.py`
- Create: `src/services/reservations/service.py`
- Create: `src/services/orders/service.py`
- Create: `src/services/commerce/clock.py`
- Create: `src/workers/reservation_expiry.py`
- Create: `migrations/versions/0003_orders_reservations.py`
- Create: `tests/unit/services/test_order_state.py`
- Create: `tests/unit/services/test_reservation_expiry.py`
- Create: `tests/integration/test_checkout_capacity.py`
- Create: `tests/integration/test_concurrent_last_seat.py`

**Interfaces:**

- `ReservationService.reserve(event_id: UUID, items: list[ReservationItem], user_id: UUID, now: datetime) -> ReservationResult` returns reservation ID, order ID, expiry and line items.
- `ReservationService.release_expired(now: datetime, limit: int) -> int` releases expired active reservations and returns the count.
- `OrderService.create_pending(user_id: UUID, event_id: UUID, items: list[OrderItemInput], now: datetime) -> PendingOrderDTO` creates the order after the reservation transaction succeeds.
- `OrderService.transition(order_id: UUID, transition: OrderTransition, reason: str) -> OrderDTO` applies only allowed state transitions and writes an audit/event record.
- `Clock.now() -> datetime` is injectable in tests so expiry scenarios are deterministic.

- [ ] **Step 1: Write failing order state tests**

  Pin allowed transitions for `pending_payment`, `paid`, `payment_failed`, `expired`, `cancelled`, `refund_requested`, `refunded` and `reconciliation_required`; reject transitions from terminal states unless an explicit refund operation allows them.

- [ ] **Step 2: Run the state tests and verify failure**

  Run: `pytest tests/unit/services/test_order_state.py -q`

  Expected: FAIL because the commerce models and transition service do not exist.

- [ ] **Step 3: Implement order, order-item, reservation and reservation-item models**

  Store prices as integer minor units, snapshot the currency and ticket label, use timezone-aware expiry, and add constraints preventing duplicate active reservation rows for the same order item.

- [ ] **Step 4: Implement atomic reservation**

  In one database transaction lock the event capacity row, release expired reservations for that event, calculate sold plus active reserved quantity, reject insufficient capacity, then create reservation and pending order. The caller must receive a stable expiry timestamp.

- [ ] **Step 5: Write the concurrency test**

  Start two independent transactions attempting to reserve the final available seat. Assert exactly one succeeds, the other receives a domain-level `CapacityExceeded` error, and the database never reports more active/sold seats than capacity.

- [ ] **Step 6: Run the concurrency test and verify the expected failure**

  Run: `pytest tests/integration/test_concurrent_last_seat.py -q`

  Expected before the implementation is complete: FAIL because the reservation service and locking policy are absent.

- [ ] **Step 7: Implement expiry worker and lazy expiry**

  Add `release_expired`, a worker entry point, and a lazy cleanup call in the reservation transaction. Re-running expiry must be harmless.

- [ ] **Step 8: Verify checkout and expiry scenarios**

  Run: `pytest tests/integration/test_checkout_capacity.py tests/unit/services/test_reservation_expiry.py -q`

  Expected: reservation TTL is 600 seconds, expired reservations free capacity, and prices are immutable after order creation.

- [ ] **Step 9: Commit the checkout core**

  ```bash
  git add src/models/commerce.py src/repositories/reservations.py src/repositories/orders.py src/services/reservations src/services/orders src/services/commerce src/workers migrations tests
  git commit -m "feat: add orders and atomic ticket reservations"
  ```

## Task 5: T‑Bank Acquiring API and Payment Webhooks

**Files:**

- Create: `src/services/payments/ports.py`
- Create: `src/services/payments/dtos.py`
- Create: `src/services/payments/tbank_client.py`
- Create: `src/services/payments/service.py`
- Create: `src/repositories/payments.py`
- Create: `src/api/webhooks/tbank.py`
- Create: `src/api/admin/payments.py`
- Create: `migrations/versions/0004_payments_events.py`
- Create: `tests/unit/services/test_payment_state.py`
- Create: `tests/unit/services/test_tbank_client.py`
- Create: `tests/integration/test_tbank_webhook_idempotency.py`
- Create: `tests/integration/test_payment_after_expiry.py`

**Interfaces:**

- `PaymentGateway.create_payment(request: CreatePaymentRequest) -> CreatePaymentResponse` returns provider payment ID, payment URL and provider status.
- `PaymentGateway.get_status(provider_payment_id: str) -> ProviderPaymentStatus` fetches the current provider state for reconciliation.
- `PaymentGateway.cancel(provider_payment_id: str, amount_minor: int | None) -> ProviderOperationResult` requests cancellation where supported.
- `PaymentGateway.refund(provider_payment_id: str, amount_minor: int, reason: str) -> ProviderOperationResult` requests a refund.
- `TBankPaymentGateway` implements the port using `httpx` and current official T‑Bank acquiring contracts.
- `PaymentService.start(order_id: UUID) -> PaymentCheckoutDTO` persists the local payment before/with the provider call and returns `payment_url` without exposing provider secrets.
- `PaymentService.apply_webhook(event: PaymentWebhookDTO) -> PaymentApplicationResult` deduplicates, validates and applies a provider status once.
- `PaymentService.reconcile(payment_id: UUID) -> PaymentDTO` fetches the provider state for unknown/reconciliation-required cases.

- [ ] **Step 1: Write failing provider-port and state tests**

  Test conversion of provider statuses to local payment/order transitions, refusal to mark a payment paid from a client redirect, rejection of unknown states, and protection against refunding an already refunded payment.

- [ ] **Step 2: Run the payment state tests and verify failure**

  Run: `pytest tests/unit/services/test_payment_state.py -q`

  Expected: FAIL because payment ports, models and service transitions do not exist.

- [ ] **Step 3: Implement payment and payment-event models**

  Store provider name, local order, provider payment ID, amount, currency, local status, provider status, payment URL, timestamps, refund metadata, deduplication key and a redacted/raw-safe event payload. Add unique constraints required by the global constraints.

- [ ] **Step 4: Implement the provider client behind `PaymentGateway`**

  Use configuration-injected credentials and `httpx`. Map the T‑Bank create-payment response to `CreatePaymentResponse`, map transport/API errors to typed domain errors, set timeouts, and never log tokens or payment credentials. Keep the exact request signing/authentication rules aligned with the current official documentation.

- [ ] **Step 5: Write HTTP client contract tests**

  Use `httpx.MockTransport` to test successful create-payment with `PaymentURL`, provider rejection, timeout, malformed response, status lookup, cancellation and refund. Assert no secret appears in raised error strings or logs captured by the test.

- [ ] **Step 6: Run the provider contract tests and verify failure**

  Run: `pytest tests/unit/services/test_tbank_client.py -q`

  Expected: FAIL until the typed client and status mapping are implemented.

- [ ] **Step 7: Implement payment service and order integration**

  Start payments only for a valid `pending_payment` order with an active reservation. Store the provider response, return the payment URL, and make retries use the existing local payment/order mapping instead of creating an uncontrolled duplicate.

- [ ] **Step 8: Implement the HTTPS webhook endpoint**

  Add `/api/webhooks/tbank/payment-status`. Validate the configured webhook authentication, parse the event, persist a deduplication record, and return a safe 2xx response only after the event is durably accepted. The endpoint must not create tickets directly outside `PaymentService`.

- [ ] **Step 9: Write duplicate, out-of-order and late-payment tests**

  Test the same webhook twice, a failed status followed by a confirmed status, a confirmed status after reservation expiry, and a malformed/unauthenticated event. Assert exactly-once side effects and no overbooking.

- [ ] **Step 10: Run payment integration tests**

  Run: `pytest tests/integration/test_tbank_webhook_idempotency.py tests/integration/test_payment_after_expiry.py -q`

  Expected: duplicate events are no-ops, unknown events enter reconciliation, and late confirmation follows the documented manual-resolution/refund rule without issuing excess tickets.

- [ ] **Step 11: Commit the payment slice**

  ```bash
  git add src/services/payments src/repositories/payments.py src/api/webhooks/tbank.py src/api/admin/payments.py migrations tests
  git commit -m "feat: integrate t-bank acquiring payments"
  ```

## Task 6: Electronic Tickets and Check-in

**Files:**

- Create: `src/models/tickets.py`
- Create: `src/repositories/tickets.py`
- Create: `src/services/tickets/issuer.py`
- Create: `src/services/tickets/checkin.py`
- Create: `src/services/tickets/qr.py`
- Create: `src/api/admin/tickets.py`
- Create: `src/bot/handlers/tickets.py`
- Create: `src/bot/keyboards/tickets.py`
- Create: `migrations/versions/0005_tickets_checkins.py`
- Create: `tests/unit/services/test_ticket_issuer.py`
- Create: `tests/unit/services/test_qr_tokens.py`
- Create: `tests/integration/test_checkin.py`
- Create: `tests/integration/test_payment_to_ticket.py`

**Interfaces:**

- `TicketIssuer.issue_for_paid_order(order_id: UUID) -> list[TicketDTO]` is idempotent and creates one ticket per paid order item.
- `QrTokenService.generate(ticket_id: UUID) -> str` returns a cryptographically unpredictable token or signed opaque value without exposing sequential IDs.
- `CheckinService.check(token: str, actor_id: UUID, now: datetime) -> CheckinResult` atomically validates and consumes a ticket.
- `CheckinService.lookup(query: TicketLookupQuery) -> list[TicketDTO]` supports restricted manual administrator search.
- `TicketService.void(ticket_id: UUID, reason: str, actor_id: UUID) -> TicketDTO` records an auditable administrative invalidation.

- [ ] **Step 1: Write failing ticket issuance tests**

  Test one ticket per quantity, idempotent repeated issuance, no issuance for unpaid/refunded orders, event association, and stable ticket snapshots.

- [ ] **Step 2: Implement ticket and check-in models**

  Store opaque token hash, event/order/type references, issued/voided/check-in timestamps, and the actor for check-in. Add constraints that prevent duplicate active tickets for the same order item position.

- [ ] **Step 3: Implement secure token generation and verification**

  Use a cryptographically secure random source, store only the verification form needed by the server, and compare tokens in constant-time where applicable. Do not encode personal data in the QR payload.

- [ ] **Step 4: Connect payment confirmation to ticket issuance**

  Extend the confirmed-payment transaction/outbox handler to issue tickets exactly once and enqueue a client notification. A retry must find existing tickets rather than creating more.

- [ ] **Step 5: Write the QR security and check-in tests**

  Test valid check-in, tampered token, unknown token, already checked-in ticket, voided ticket, wrong-event check-in and repeated concurrent check-in.

- [ ] **Step 6: Run the check-in tests and verify failure before implementation is complete**

  Run: `pytest tests/unit/services/test_qr_tokens.py tests/integration/test_checkin.py -q`

  Expected during the red phase: FAIL because token and atomic check-in behavior are absent.

- [ ] **Step 7: Implement check-in and admin lookup**

  Lock the ticket row during check-in, write one check-in record, reject subsequent use, and restrict lookup/void operations through the role service from Task 7.

- [ ] **Step 8: Verify payment-to-ticket integration**

  Run: `pytest tests/integration/test_payment_to_ticket.py -q`

  Expected: only a confirmed payment creates tickets; duplicate confirmation produces the original ticket set.

- [ ] **Step 9: Commit the ticket slice**

  ```bash
  git add src/models/tickets.py src/repositories/tickets.py src/services/tickets src/api/admin/tickets.py src/bot migrations tests
  git commit -m "feat: issue QR tickets and record check-ins"
  ```

## Task 7: Administrative Authentication, Roles and Web UI

**Files:**

- Create: `src/models/admin.py`
- Create: `src/repositories/admin.py`
- Create: `src/services/admin/auth.py`
- Create: `src/services/admin/permissions.py`
- Create: `src/services/audit/service.py`
- Create: `src/api/admin/auth.py`
- Create: `src/api/admin/dashboard.py`
- Create: `src/admin/templates/base.html`
- Create: `src/admin/templates/login.html`
- Create: `src/admin/templates/dashboard.html`
- Create: `src/admin/templates/events.html`
- Create: `src/admin/templates/orders.html`
- Create: `src/admin/templates/tickets.html`
- Create: `src/admin/templates/users.html`
- Create: `src/admin/static/admin.css`
- Create: `migrations/versions/0006_admin_audit.py`
- Create: `tests/unit/services/test_permissions.py`
- Create: `tests/integration/test_admin_auth.py`
- Create: `tests/integration/test_admin_audit.py`
- Create: `tests/integration/test_admin_data_access.py`

**Interfaces:**

- `AdminAuthService.authenticate(login: str, password: SecretStr) -> AdminSessionDTO | None` authenticates without leaking whether a login exists.
- `PermissionService.require(actor: AdminActor, permission: Permission) -> None` raises a typed authorization error.
- `AuditService.record(actor_id: UUID, action: AuditAction, object_type: str, object_id: UUID | None, metadata: dict[str, str]) -> AuditLogDTO` writes a redacted critical-action record.
- `AdminSession` dependency returns the actor for authenticated requests and rejects expired/invalid sessions.

- [ ] **Step 1: Write failing role matrix tests**

  Pin that owner can manage all resources, administrator can manage events/orders/CRM/campaigns but not system secrets, and entrance staff can only look up/check-in tickets. Explicitly test that entrance staff cannot export CRM, refund orders, edit prices or change roles.

- [ ] **Step 2: Implement admin models, session auth and permission service**

  Store password hashes only, use secure session cookies, CSRF protection for state-changing form requests, and role-to-permission mapping in one service.

- [ ] **Step 3: Write failing audit tests**

  Test audit records for price changes, refunds, ticket voids, consent/data exports, role changes and campaign actions; assert secrets and full personal data are redacted.

- [ ] **Step 4: Implement audit service and middleware/dependencies**

  Require explicit service calls for critical mutations and attach actor/correlation information. Audit failures must not silently turn a successful critical mutation into an unaudited action.

- [ ] **Step 5: Add the minimal web admin shell**

  Implement login, dashboard, event/order/ticket/user list pages and shared navigation with Jinja2/HTMX. Reuse service/API contracts; do not put business rules in templates.

- [ ] **Step 6: Run access and audit tests**

  Run: `pytest tests/unit/services/test_permissions.py tests/integration/test_admin_auth.py tests/integration/test_admin_audit.py tests/integration/test_admin_data_access.py -q`

  Expected: role denial, session expiry, audit creation and data minimization all pass.

- [ ] **Step 7: Commit the admin slice**

  ```bash
  git add src/models/admin.py src/repositories/admin.py src/services/admin src/services/audit src/api/admin src/admin migrations tests
  git commit -m "feat: add admin roles and audit trail"
  ```

## Task 8: CRM, Attribution, Campaigns and Worker Delivery

**Files:**

- Create: `src/models/campaigns.py`
- Create: `src/models/attribution.py`
- Create: `src/repositories/campaigns.py`
- Create: `src/repositories/attribution.py`
- Create: `src/services/crm/segments.py`
- Create: `src/services/campaigns/composer.py`
- Create: `src/services/campaigns/delivery.py`
- Create: `src/services/analytics/attribution.py`
- Create: `src/workers/queue.py`
- Create: `src/workers/campaign_delivery.py`
- Create: `src/api/admin/campaigns.py`
- Create: `src/bot/handlers/settings.py`
- Create: `src/bot/handlers/support.py`
- Create: `migrations/versions/0007_campaigns_attribution.py`
- Create: `tests/unit/services/test_segments.py`
- Create: `tests/unit/services/test_campaign_delivery.py`
- Create: `tests/integration/test_consent_gated_campaign.py`
- Create: `tests/integration/test_attribution_funnel.py`

**Interfaces:**

- `SegmentService.resolve(segment: SegmentDefinition) -> AsyncIterator[UserRecipient]` returns only currently eligible recipients.
- `CampaignService.create_draft(command: CampaignDraftCommand) -> CampaignDTO` validates content and audience definition.
- `CampaignService.preview(campaign_id: UUID, actor_id: UUID) -> CampaignPreviewDTO` renders content without sending to the audience.
- `CampaignService.send_test(campaign_id: UUID, admin_chat_id: int) -> DeliveryResult` sends only to the explicitly selected administrator.
- `CampaignDeliveryWorker.deliver(campaign_id: UUID, batch_size: int) -> DeliveryBatchResult` rechecks consent immediately before sending and records success/error/block states.
- `AttributionService.record_start(user_id: UUID, start_param: str, observed_at: datetime) -> AttributionDTO` preserves first and latest source according to the spec.
- `AttributionService.record_funnel_event(user_id: UUID, event: FunnelEvent) -> None` records launch, showcase, checkout and purchase milestones.

- [ ] **Step 1: Write failing segment and consent-gate tests**

  Cover directions of interest, prior purchasers, never-purchased users, combined segments, revoked consent, missing consent and blocked bot state.

- [ ] **Step 2: Implement campaign, delivery and attribution models**

  Store draft/scheduled/running/completed/cancelled states, content variants, schedule, audience definition, delivery status/error, click/purchase counters and source parameters.

- [ ] **Step 3: Implement segment resolver and campaign composer**

  Keep segment evaluation queryable and bounded. Preview and test send must not mutate delivery state for the full audience.

- [ ] **Step 4: Write the worker delivery tests**

  Test rate-limited batches, retry of transient Telegram errors, permanent block handling, cancellation between batches, consent revoked between selection and send, and safe retry without duplicate delivery records.

- [ ] **Step 5: Implement the worker queue and delivery process**

  Use Redis-backed jobs, an explicit idempotency key per campaign/user/message attempt, a configurable rate limit, and graceful shutdown. The worker must re-check consent immediately before calling Telegram.

- [ ] **Step 6: Add attribution and user settings flows**

  Persist first/latest source, funnel events, notification settings and unsubscribe actions. `/stop` or the equivalent UI must update eligibility before returning success to the user.

- [ ] **Step 7: Add campaign admin endpoints and tests**

  Support draft, preview, test send, scheduling, cancellation and delivery statistics with role checks and audit records.

- [ ] **Step 8: Run campaign and attribution integration tests**

  Run: `pytest tests/integration/test_consent_gated_campaign.py tests/integration/test_attribution_funnel.py -q`

  Expected: no revoked/blocked recipient receives a marketing message, and attribution survives repeated `/start` events.

- [ ] **Step 9: Commit the CRM and campaigns slice**

  ```bash
  git add src/models/campaigns.py src/models/attribution.py src/repositories/campaigns.py src/repositories/attribution.py src/services/crm src/services/campaigns src/services/analytics src/workers src/api/admin/campaigns.py src/bot/handlers migrations tests
  git commit -m "feat: add CRM segments campaigns and attribution"
  ```

## Task 9: Documentation, Observability, Backup and Release Verification

**Files:**

- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DECISIONS.md`
- Create: `docs/DATABASE.md`
- Create: `docs/API.md`
- Create: `docs/DEPLOYMENT.md`
- Create: `docs/RECOVERY.md`
- Create: `docs/TEST_REPORT.md`
- Create: `src/core/observability.py`
- Create: `src/api/metrics.py`
- Create: `scripts/check_secrets.py`
- Create: `scripts/backup_database.sh`
- Create: `scripts/restore_database.sh`
- Create: `tests/integration/test_mvp_acceptance.py`
- Create: `tests/integration/test_recovery_procedure.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `docker-compose.yml`

**Interfaces:**

- `configure_observability(settings: Settings) -> None` configures structured logs, correlation IDs and redaction.
- `run_secret_scan(paths: Sequence[Path]) -> SecretScanResult` returns a non-zero process result when a credential-shaped value is found.
- `backup_database(source: DatabaseTarget, destination: Path) -> BackupResult` and `restore_database(backup_path: Path, target: DatabaseTarget) -> RestoreResult` are documented, non-interactive operational commands with explicit target validation.
- `tests/integration/test_mvp_acceptance.py` is the executable acceptance checklist for the approved MVP criteria.

- [ ] **Step 1: Write the acceptance test matrix**

  Cover registration, duplicate `/start`, event publication, one/multiple-ticket purchase, T‑Bank confirmation, duplicate webhook, expired reservation, concurrent last seat, QR issuance, repeated scan, refund/void, consent-gated campaign, blocked user and restart recovery.

- [ ] **Step 2: Run the acceptance tests and record the initial gaps**

  Run: `pytest tests/integration/test_mvp_acceptance.py -q`

  Expected: any remaining gaps are explicit failures mapped to Tasks 1–8; do not mark the MVP ready based on partial execution.

- [ ] **Step 3: Implement observability and redaction**

  Add structured event names, correlation IDs across bot/API/payment operations, error counters, queue metrics and payload redaction. Verify that logs contain no Telegram/T‑Bank secrets or full customer data.

- [ ] **Step 4: Add backup and restore scripts**

  Use explicit database connection inputs, refuse ambiguous destinations, document encryption/storage policy, and test restore into an isolated database. Do not overwrite the production database from a restore script without an explicit target.

- [ ] **Step 5: Add secret scan and CI gates**

  Make CI run migrations against a disposable PostgreSQL, unit/integration tests, lint/type checks, secret scan and `docker compose config`. Fail the workflow on any test or scan failure.

- [ ] **Step 6: Complete operational documentation**

  Document local setup, migrations, Telegram webhook/polling modes, T‑Bank sandbox/production configuration, webhook registration, deployment, backup, restore, rollback, monitoring and incident handling.

- [ ] **Step 7: Run final verification**

  Run: `pytest -q`, the configured formatter/linter/type checker, `python scripts/check_secrets.py`, `docker compose config`, and the documented backup/restore test.

  Expected: all commands exit 0, the acceptance matrix passes, and `docs/TEST_REPORT.md` contains command output summaries, limitations and unresolved operational risks.

- [ ] **Step 8: Commit release hardening**

  ```bash
  git add README.md docs src/core/observability.py src/api/metrics.py scripts tests .github/workflows/ci.yml docker-compose.yml
  git commit -m "chore: harden MVP operations and release checks"
  ```

## Final Handoff Checklist

- [ ] All task commits are present on the isolated implementation branch.
- [ ] No uncommitted changes remain except intentionally documented local configuration.
- [ ] `docs/ROADMAP.md` status reflects actual verified progress, not code presence alone.
- [ ] `docs/TEST_REPORT.md` lists real commands and results.
- [ ] T‑Bank sandbox payment, duplicate webhook, refund and late-payment policies are verified against the current provider contract.
- [ ] Consent, deletion/retention and commercial launch documents have been reviewed by the business/legal owner.
- [ ] Recovery from backup has been tested on an isolated database.
- [ ] A final independent review covers payments, security, QA, performance and business logic before merging.
