# API MVP

Публичные маршруты:

- `GET /health` — liveness;
- `GET /ready` — PostgreSQL readiness;
- `GET /api/public/events` и `GET /api/public/events/{id}` — опубликованная афиша;
- `POST /api/webhooks/tbank/payment-status` — подписанное уведомление Internet Acquiring.

Админские маршруты требуют HttpOnly cookie, выданную через
`POST /api/admin/auth/login`:

- `/api/admin/events` — owner/administrator;
- `/api/admin/dashboard` — dashboard и aggregate counters;
- `/api/admin/tickets/check-in` — owner/administrator/entrance;
- `/api/admin/campaigns` — owner/administrator;
- `/api/admin/auth/me` и `/api/admin/auth/logout`;
- `/metrics` — локальные counters без персональных данных.

Payload платежного webhook проверяется токеном T‑Bank до обращения к сервисному
слою. Дубликаты определяются по `EventId`, а если его нет — по паре provider
payment/status. Redirect пользователя не является подтверждением оплаты.
