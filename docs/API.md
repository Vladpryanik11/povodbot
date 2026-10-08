# API MVP

Публичные маршруты:

- `GET /health` — liveness;
- `GET /ready` — PostgreSQL readiness;
- `GET /api/public/events` и `GET /api/public/events/{id}` — опубликованная афиша;
- `POST /api/webhooks/tbank/payment-status` — подписанное уведомление Internet Acquiring.

Telegram-сценарии используют те же сервисы через роутер бота:

- `/start` — регистрация, атрибуция и обязательные согласия;
- каталог направлений и мероприятий — `direction:*`, `event:*`;
- покупка — `buy:*` → `quantity:*`; заказ и бронь фиксируются отдельной транзакцией,
  затем создаётся локальный payment intent и вызывается T‑Bank Init. Потерянный
  ответ восстанавливается через `CheckOrder` по стабильному `OrderId`;
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
- `/api/admin/payments/{id}/refund` — постановка возврата в transactional outbox;
  worker перед `Cancel` проверяет актуальный статус T‑Bank и не повторяет возврат
  вслепую после неясного ответа;
- `/api/admin/auth/me` и `/api/admin/auth/logout`;
- `/metrics` — локальные counters без персональных данных.

Payload платежного webhook проверяется токеном T‑Bank до обращения к сервисному
слою. Дубликаты определяются по `EventId`, а если его нет — по паре provider
payment/status. Redirect пользователя не является подтверждением оплаты.
Для неясных Init/возвратов предусмотрены состояния
`reconciliation_required` и `refunding`; provider-вызовы для checkout выполняются
между зафиксированными локальными транзакциями, а возвраты и Telegram-рассылки
проходят через transactional outbox после commit. Ручная сверка остаётся обязательной
для `INIT_UNKNOWN`/`REFUND_UNKNOWN`.
