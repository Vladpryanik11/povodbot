# Povod Payment Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make payment initialization and provider reconciliation safe under concurrent requests, lost provider responses, duplicate webhooks, and administrative operations.

**Architecture:** Keep PostgreSQL as the source of truth and use a short durable lease on each local payment intent to claim T-Bank `Init` exactly once at a time. Provider calls run outside database transactions; their results are persisted through fresh transactions. Webhook processing uses the canonical event → order → payment lock order and an atomic PostgreSQL insert for unknown-event deduplication.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, PostgreSQL, Alembic, pytest/pytest-asyncio, T-Bank gateway port.

**Spec:** `docs/superpowers/specs/2026-10-08-povod-mvp-design.md`, constrained by `AGENTS.md` and `docs/ROADMAP.md`.

## Global Constraints

- One club/no multitenancy; directions remain data in PostgreSQL.
- Prices and totals are calculated and snapshotted on the server.
- Reservation TTL remains exactly 600 seconds.
- A payment is confirmed only by verified provider status; a redirect or `Init` response is not payment proof.
- Provider webhooks remain idempotent, order-state transitions remain canonical, and late/ambiguous evidence requires reconciliation.
- All stored timestamps are timezone-aware UTC values.
- No secrets, raw credentials, card data, provider tokens, or sensitive provider payloads may enter Git or logs.
- Consent gating, QR token secrecy, and one-time event-scoped check-in behavior must remain unchanged.

## Review Focus

- Two simultaneous checkout requests for one order must produce at most one T-Bank `Init` call; covered by Task 1 concurrency test.
- A process crash or database failure after provider acceptance must recover by `CheckOrder`/reconciliation and never issue a second `Init`; covered by Task 1 recovery test.
- A provider response with a mismatched amount or `OrderId` must not attach to the local payment; covered by Task 1 response-validation tests.
- Two identical unknown-payment webhooks arriving concurrently must yield one stored event and one duplicate result without a unique-constraint error; covered by Task 2 integration test.
- Provider status lookups for admin reconcile/bind must not hold a payment row lock while waiting on the network; covered by Task 3 orchestration test.

---

### Task 1: Durable payment Init claim and recovery

**Files:**
- Create: `migrations/versions/0008_payment_init_lease.py`
- Modify: `src/models/payments.py`
- Modify: `src/services/payments/service.py`
- Modify: `src/services/payments/checkout.py`
- Test: `tests/integration/test_payment_hardening.py`

**Interfaces:**
- Consumes: existing `PaymentCheckoutService.start(order_id)`, `PaymentService.prepare(order_id)`, `PaymentService.complete_init(payment_id, response)`, and T-Bank `find_by_order` recovery support.
- Produces: `Payment.init_lease_until: datetime | None`; `PaymentInitIntent.recovery_required: bool`; `PAYMENT_INIT_LEASE`; idempotent `complete_init()` behavior that accepts a late matching response and rejects conflicting provider identity/order/amount.

- [ ] **Step 1: Write failing integration tests**

  Add tests for:
  - concurrent `PaymentCheckoutService.start()` calls with a gateway blocked inside `create_payment`; assert `create_payment` is called once and the second caller receives no second request;
  - an expired `init_lease_until` with a gateway that can recover by order; assert recovery calls `find_by_order`, never `create_payment`, and persists the provider identity;
  - a late matching `CreatePaymentResponse` after the local payment is marked reconciliation-required; assert it is attached idempotently;
  - mismatched response amount and raw `OrderId`; assert `PaymentStateError` and no provider identity is persisted.

- [ ] **Step 2: Run the focused tests to verify RED**

  Run: `python -m pytest -q tests/integration/test_payment_hardening.py`

  Expected: FAIL because the model has no Init lease/recovery field and the orchestrator can issue duplicate `create_payment` calls.

- [ ] **Step 3: Add the nullable lease column and model field**

  Add `payments.init_lease_until TIMESTAMP WITH TIME ZONE NULL` in migration `0008`, with downgrade support, and map it as `Mapped[datetime | None]` on `Payment`.

- [ ] **Step 4: Implement the minimal durable claim/recovery state machine**

  In `PaymentService.prepare()`, lock the event then order then payment, claim a pending intent by setting `status=PROCESSING`, `provider_status=INIT_IN_PROGRESS`, and `init_lease_until=now + PAYMENT_INIT_LEASE`. An active lease returns no provider request. An expired lease becomes `RECONCILIATION_REQUIRED`/`INIT_UNKNOWN` and returns `recovery_required=True`; it must never issue a new Init.

  In `PaymentCheckoutService.start()`, handle `recovery_required` with `find_by_order` outside the database transaction, then persist either the recovered provider identity or `INIT_UNKNOWN` in a fresh transaction.

  Clear the lease in `complete_init()`, `attach_recovered_init()`, and `mark_init_unknown()`. Make `complete_init()` idempotent for a matching provider identity and validate amount plus optional raw `OrderId` before persistence.

- [ ] **Step 5: Run the focused tests to verify GREEN**

  Run: `python -m pytest -q tests/integration/test_payment_hardening.py`

  Expected: all Task 1 tests pass, including the single-Init concurrency assertion and recovery-without-retry assertion.

- [ ] **Step 6: Commit the task**

  ```powershell
  git add migrations/versions/0008_payment_init_lease.py src/models/payments.py src/services/payments/service.py src/services/payments/checkout.py tests/integration/test_payment_hardening.py
  git commit -m "fix: make payment init claim and recovery idempotent"
  ```

### Task 2: Canonical payment locking and atomic unknown-webhook deduplication

**Files:**
- Modify: `src/repositories/payments.py`
- Modify: `src/services/payments/service.py`
- Modify: `src/workers/outbox.py`
- Modify: `tests/integration/test_payment_hardening.py`
- Modify: `tests/integration/test_tbank_webhook_idempotency.py`

**Interfaces:**
- Consumes: Task 1’s event → order → payment locking rule and `Payment.init_lease_until` state.
- Produces: non-locking payment lookup for lock-order discovery and an atomic `insert_payment_event_if_absent()` repository operation backed by PostgreSQL `ON CONFLICT DO NOTHING`.

- [ ] **Step 1: Write the failing concurrent webhook test**

  Add an async integration test that invokes `PaymentService.apply_webhook()` from two independent sessions with the same unknown provider payment and identical `event_id`; assert both requests are accepted, exactly one is marked `duplicate`, and exactly one `PaymentEvent` exists.

- [ ] **Step 2: Run the test to verify RED**

  Run: `python -m pytest -q tests/integration/test_payment_hardening.py::test_concurrent_unknown_webhooks_are_idempotent`

  Expected: FAIL with a PostgreSQL unique-constraint/transaction error from the concurrent insert.

- [ ] **Step 3: Implement atomic unknown-event insertion and canonical lock discovery**

  Add a non-locking provider-payment lookup and `insert_payment_event_if_absent()` to `PaymentRepository`. Use PostgreSQL `ON CONFLICT DO NOTHING` for the unknown-payment branch and return the existing event as a duplicate when the insert loses the race.

  Rework `apply_webhook()` to discover the order from the unlocked payment/event payload, lock the event row first, then the order, then the payment. Rework `prepare()`, legacy reconciliation, and refund-outbox callers as needed so all payment/order transition paths use the same event → order → payment order. Keep status validation, safe payload redaction, and existing order-state transitions unchanged.

- [ ] **Step 4: Run focused and regression tests**

  Run: `python -m pytest -q tests/integration/test_payment_hardening.py::test_concurrent_unknown_webhooks_are_idempotent tests/integration/test_tbank_webhook_idempotency.py`

  Expected: the concurrent test and existing known-payment idempotency tests pass without changing ticket/payment side-effect counts.

- [ ] **Step 5: Commit the task**

  ```powershell
  git add src/repositories/payments.py src/services/payments/service.py tests/integration/test_payment_hardening.py tests/integration/test_tbank_webhook_idempotency.py
  git commit -m "fix: make unknown payment webhooks atomically idempotent"
  ```

### Task 3: Move admin provider operations outside DB transactions

**Files:**
- Create: `src/services/payments/admin.py`
- Modify: `src/services/payments/service.py`
- Modify: `src/api/admin/payments.py`
- Test: `tests/integration/test_payment_admin_orchestration.py`

**Interfaces:**
- Consumes: `async_sessionmaker[AsyncSession]`, `PaymentGateway.get_status()`, Task 2’s canonical webhook/application path, and the existing `PaymentService` state rules.
- Produces: `PaymentAdminService.reconcile(payment_id) -> PaymentDTO` and `PaymentAdminService.bind_provider_payment(payment_id, provider_payment_id) -> PaymentDTO`, with provider calls occurring between short read and write transactions rather than inside a held payment lock.

- [ ] **Step 1: Write failing orchestration tests**

  Add tests with a blocking gateway that waits in `get_status()`; while it is blocked, prove another session can acquire and release the target payment row lock. Add a bind test asserting amount/order mismatch is rejected before persistence.

- [ ] **Step 2: Run the tests to verify RED**

  Run: `python -m pytest -q tests/integration/test_payment_admin_orchestration.py`

  Expected: FAIL because the orchestration service does not exist.

- [ ] **Step 3: Implement the orchestration service and pure persistence methods**

  Add `PaymentAdminService` with separate transactions for provider identity discovery, external `GetState`, and applying the verified snapshot. Add a transaction-only `bind_provider_snapshot()` method to `PaymentService`; keep legacy service methods only as compatibility wrappers, but production admin routes must use the orchestrator.

- [ ] **Step 4: Route admin reconcile/bind through the orchestrator**

  Update `src/api/admin/payments.py` to obtain the configured session factory, use `PaymentAdminService` for reconcile/bind, preserve existing permissions/error mapping/audit records, and remove unnecessary provider construction from the refund endpoint because refunds are outbox commands.

- [ ] **Step 5: Run focused tests to verify GREEN**

  Run: `python -m pytest -q tests/integration/test_payment_admin_orchestration.py tests/integration/test_payment_after_expiry.py`

  Expected: all orchestration, bind validation, refund, and reconciliation tests pass.

- [ ] **Step 6: Commit the task**

  ```powershell
  git add src/services/payments/admin.py src/services/payments/service.py src/api/admin/payments.py tests/integration/test_payment_admin_orchestration.py
  git commit -m "fix: keep admin provider calls outside database locks"
  ```

### Task 4: Campaign scheduling guard and handoff synchronization

**Files:**
- Modify: `src/services/campaigns/composer.py`
- Modify: `tests/integration/test_consent_gated_campaign.py`
- Modify: `HANDOFF.md`
- Modify: `docs/REVIEW_REPORT.md`
- Modify: `docs/TEST_REPORT.md`
- Modify: `docs/superpowers/specs/2026-10-08-povod-mvp-design.md`
- Modify: `docs/superpowers/plans/2026-10-08-povod-mvp-implementation-plan.md`

**Interfaces:**
- Consumes: existing campaign `create_draft()`/`schedule()` APIs and the release-risk record from Tasks 1–3.
- Produces: consistent timezone-aware future validation for an optional draft schedule and documentation that distinguishes completed implementation from unverified release gates.

- [ ] **Step 1: Write failing campaign schedule tests**

  Add tests asserting `create_draft(..., scheduled_at=naive_datetime)` and a past aware datetime raise `ValueError`, while a future aware datetime is normalized to UTC and accepted.

- [ ] **Step 2: Run the tests to verify RED**

  Run: `python -m pytest -q tests/integration/test_consent_gated_campaign.py -k schedule`

  Expected: FAIL because draft creation currently stores the optional value without validating it.

- [ ] **Step 3: Implement the shared schedule validation**

  Normalize and validate `scheduled_at` in `CampaignService.create_draft()` using the same timezone-aware/future rules as `schedule()`; do not change consent or delivery semantics.

- [ ] **Step 4: Update project records**

  Record the new payment-hardening commits and actual local verification status, mark the specification/plan status consistently, and retain external T‑Bank/Telegram/Docker/backup gates as explicitly unverified until real environments are available.

- [ ] **Step 5: Run the complete verification suite**

  Run: `python -m pytest -q`, `python -m ruff format --check .`, `python -m ruff check .`, `python -m mypy src`, `python scripts/check_secrets.py`, `python -m compileall -q src tests scripts`, and `git diff --check`.

  Expected: all available checks pass; Docker Compose remains reported as unavailable if the CLI is still absent.

- [ ] **Step 6: Commit the task**

  ```powershell
  git add src/services/campaigns/composer.py tests/integration/test_consent_gated_campaign.py HANDOFF.md docs/REVIEW_REPORT.md docs/TEST_REPORT.md docs/superpowers/specs/2026-10-08-povod-mvp-design.md docs/superpowers/plans/2026-10-08-povod-mvp-implementation-plan.md
  git commit -m "docs: synchronize payment hardening handoff"
  ```

## Final Review

- Generate a review package for the branch range from `ea98bdd` to `HEAD`.
- Because no subagent dispatch tool is available in this session, perform a separate self-review using the code-reviewer checklist and record `Final review: self-review (no subagent tool)` in the SDD ledger.
- Re-grade findings by user impact. Fix Critical/Important findings with a new RED → GREEN test and one final full-suite run; record deferred Minor findings without silently expanding scope.
- Do not push, merge, deploy, or call real providers without explicit user authorization and the required secrets/environment.
