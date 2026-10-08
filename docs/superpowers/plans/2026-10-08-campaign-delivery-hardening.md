# Povod Campaign Delivery Hardening Plan

**Goal:** Preserve the consent gate at the last safe point before a Telegram
send and close a campaign when its final staged delivery reaches a terminal
state.

**Scope:** Keep provider calls outside database transactions, preserve the
existing outbox lease/retry contract, and do not claim provider-level exactly-once
delivery that Telegram does not provide.

## Tasks

### Task 1: Last-moment consent guard

- Add a failing integration test where a delivery is queued, marketing consent
  is revoked, and the outbox worker must mark the delivery blocked without
  calling Telegram.
- Re-check current eligibility in a short database transaction after claiming
  the outbox job and before the provider call.
- Persist a blocked terminal result through the existing outbox finish path.

### Task 2: Campaign completion after final delivery

- Add a failing integration test proving the campaign becomes `COMPLETED`
  after the last queued delivery is sent, without requiring an extra campaign
  staging pass.
- Re-evaluate the current eligible audience after each terminal delivery and
  mark the campaign complete only when every currently eligible recipient has a
  terminal `SENT`/`BLOCKED` delivery and no eligible recipient remains
  unstaged.

### Task 3: Verification and handoff

- Run focused campaign integration tests, then the complete suite and static
  gates.
- Review the changed outbox path separately and record any provider-level
  at-least-once limitation as an external release risk.
- Update the handoff/test/review records and commit the slice.

## Final review

Task 1 and the Task 2 correction used the live multi-agent review workflow
enabled in Codex. If that capability becomes unavailable for a future run, a
separately recorded self-review is the fallback. This Task 3 run did not
dispatch a subagent or reviewer, per the task authorization; the author
self-reviewed the documentation and the changed outbox path. No push, merge,
deploy, or real provider call is authorized by this plan.

## Execution record — 2026-10-08

- Task 1 was reviewed **PASS** and committed as `201b3e8`. It is the
  production change that adds the last-moment consent/eligibility check before
  the Telegram call and persists the blocked terminal result. The completion
  hook already present in that reviewed change also satisfies the campaign
  completion requirement.
- Task 2's attempted implementation at `dc42d72` was reviewed **NEEDS
  REVISION**: its production edit was behaviorally equivalent to the Task 1
  base and its added test passed against that base. The no-op implementation
  and redundant test were reverted at `f21f0d0`, and the scoped re-review
  passed. Task 2 is therefore documented as **pre-satisfied by Task 1**, not as
  a new production change.
- Task 3 verification ran on `f21f0d0` before the documentation commit. The
  focused campaign module passed **6 tests in 8.08s**; the complete
  PostgreSQL suite passed **261 tests in 203.45s (3:23)** on a newly created
  disposable database `povod_task5_test`. Ruff, mypy,
  compileall, secret scan, runtime imports, Alembic, PyYAML Compose parsing,
  and `git diff --check` passed. Ruff formatter normalization of mixed line
  endings in the already-committed outbox file produced no Git content diff.
- The Docker CLI was unavailable, so `docker compose config --quiet` remains
  an external CI gate; PyYAML parsing resolved `api`, `bot`, `worker`,
  `postgres`, and `redis`. No real Telegram call was made.
- The PostgreSQL outbox still provides at-least-once Telegram delivery. A
  process failure after provider acceptance and before the finish transaction
  commits can cause a retry; Telegram does not provide a project-used
  idempotency key. This limitation is unchanged and remains an external
  release risk.
