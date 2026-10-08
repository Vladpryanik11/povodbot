# Повод

Single-club modular monolith for Telegram ticket sales, CRM and check-in. The
MVP core is assembled in the isolated implementation branch: onboarding and
consents, directions and showcase, reservations/orders, T‑Bank Internet
Acquiring, webhook reconciliation, tickets/check-in, admin RBAC and audit,
consent-gated CRM campaigns, attribution and operational tooling. External
provider sandbox and recovery rehearsal remain release gates; see
[ROADMAP](docs/ROADMAP.md) and [TEST_REPORT](docs/TEST_REPORT.md).

## Local setup

Requires Python 3.12+ and Docker Compose v2 for PostgreSQL/Redis.

```powershell
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install -e '.[dev]'
Copy-Item .env.example .env
docker compose up -d postgres redis
python -m alembic upgrade head
uvicorn src.api.app:create_app --factory --reload
```

On Unix, activate with `source .venv/bin/activate` and copy with `cp .env.example .env`.
Or run `docker compose up --build` for the API and its local services.
Visit `/health` for liveness and `/ready` for database readiness (503 on failure).
The minimal admin shell is available at `/admin`; authenticate via
`POST /api/admin/auth/login`. Campaign delivery rechecks marketing consent and
blocked-user state immediately before sending. `/stop` in the Telegram bot
revokes marketing consent.
Readiness currently probes only PostgreSQL; Redis is the queue boundary for the
next worker deployment slice. No schema or migration is created automatically.

## Checks

```text
python -m pytest -q
python -m ruff format --check .
python -m ruff check .
python -m mypy src
docker compose config --quiet
python scripts/check_secrets.py
python -m alembic check
```

Use `python -m ruff format .` to format. Commands and options are configured in
`pyproject.toml`; `poe test`, `poe format`, `poe format-check`, `poe lint`,
`poe typecheck` and `poe check` provide equivalent task shortcuts.
The local foundation fixture uses a fresh temporary SQLite file
for SQL/session and readiness tests. To exercise PostgreSQL, create a disposable
`povod_test` database and set `TEST_DATABASE_URL` as shown in `.env.example`.
CI uses PostgreSQL. SQLite is not supported as an application database and must
not be used for future capacity, locking or concurrency tests.

## Configuration

Settings load environment variables and optional `.env`; `get_settings()` caches
the validated object. Restart after configuration changes. Production requires
nonblank `TELEGRAM_TOKEN`, `TBANK_TERMINAL_KEY`, `TBANK_PASSWORD` and
`TBANK_WEBHOOK_SECRET`. The payment slice uses T‑Bank Internet Acquiring from
the T‑Business cabinet (`/v2/Init`, `GetState`, `Cancel`); `TBANK_API_TOKEN` is
optional when the terminal contract does not require a bearer token. Integration
credentials remain blank for development.
Database/Redis URLs must include a host; the database uses `postgresql+asyncpg`.
All defaults and environment names are shown in `.env.example`; reservation TTL
defaults to 600 seconds. Pool size, timeouts and delivery rate must be positive;
pool overflow may be zero.

Compose contains public dummy development database credentials and binds exposed
ports to localhost. It is a local development configuration; production must
supply managed credentials and deployment settings separately.
Keep `.env` out of Git. Never log Settings dumps, URLs, personal data or provider
payloads. JSON logging preserves correlation IDs bound by callers; comprehensive
cross-runtime observability is scheduled for Task 9.

See [architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md), and the
[approved design](docs/superpowers/specs/2026-10-08-povod-mvp-design.md).
Operational details: [API](docs/API.md), [deployment](docs/DEPLOYMENT.md),
[database](docs/DATABASE.md), and [recovery](docs/RECOVERY.md).
