# API MVP

Публичные маршруты:

- `GET /health` — liveness;
- `GET /ready` — PostgreSQL readiness;
- `GET /api/public/events` и `GET /api/public/events/{id}` — опубликованная афиша;
- `POST /api/webhooks/tbank/payment-status` — подписанное уведомление Internet Acquiring.

Telegram-сценарии используют те же сервисы через роутер бота:

- `/start` — регистрация, атрибуция и обязательные согласия;
- каталог направлений и мероприятий — `direction:*`, `event:*`;
- покупка — `buy:*` → `quantity:*`, затем создаются заказ, бронь и T‑Bank Init;
- `tickets:mine` — выданные билеты и непрозрачный QR-токен;
- `/stop` — отзыв рекламного согласия.

Админские маршруты требуют HttpOnly cookie, выданную через
`POST /api/admin/auth/login`:

- `/api/admin/events` — owner/administrator;
- `/api/admin/dashboard` — dashboard и aggregate counters;
- `/api/admin/tickets/check-in` — owner/administrator/entrance;
- `/api/admin/campaigns` — owner/administrator;
- `/api/admin/payments/{id}` — просмотр платежа;
- `/api/admin/payments/{id}/reconcile` — сверка с T‑Bank;
- `/api/admin/payments/{id}/bind-provider` — ручная привязка внешнего ID после
  потерянного ответа Init;
- `/api/admin/payments/{id}/refund` — запуск возврата с идемпотентным локальным
  состоянием;
- `/api/admin/auth/me` и `/api/admin/auth/logout`;
- `/metrics` — локальные counters без персональных данных.

Payload платежного webhook проверяется токеном T‑Bank до обращения к сервисному
слою. Дубликаты определяются по `EventId`, а если его нет — по паре provider
payment/status. Redirect пользователя не является подтверждением оплаты.
Для неясных Init/возвратов предусмотрены состояния
`reconciliation_required` и `refunding`; повторный внешний вызов не выполняется
только на основании потерянного HTTP-ответа.
