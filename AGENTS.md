# Working agreements

Work in an isolated implementation worktree. Follow the approved spec in
`docs/superpowers/specs/2026-10-08-povod-mvp-design.md` and preserve every invariant
in `docs/ROADMAP.md`. Keep changes inside the assigned task.

Use TDD: write the behavior test, observe its expected failure, implement the
smallest change, then refactor. Before completion claims and commits, run the
complete pytest suite, Ruff formatter check, Ruff lint, mypy, and Compose config.
Report actual results and limitations. Do not substitute code presence for verification.

Never commit real credentials, `.env`, customer data, raw payment payloads, or
secrets. Never log personal data, tokens, connection URLs, or payment details.
Dummy local database passwords are development fixtures only.

Keep this a single-club modular monolith. Directions are database records;
business rules belong to services, persistence to repositories. API/bot/admin
are boundaries, and workers share the same services. No multi-tenancy.

Do not contact providers or run migrations at import time. Migrations are explicit
operations. Store system timestamps in UTC with timezone information.

Payments require verified provider status; redirects prove nothing. Preserve
idempotency, capacity protection, server-calculated prices, unpredictable ticket
tokens, one-time check-in, and marketing consent checks immediately before delivery.
