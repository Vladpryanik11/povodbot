# База данных

PostgreSQL является источником истины. Схема изменяется только явными командами
Alembic:

```text
python -m alembic upgrade head
python -m alembic check
```

Миграции `0001`–`0003` содержат identity, события и коммерческий контур;
`0004`–`0005` — T‑Bank payments, билеты и check-in; `0006` — администраторов,
сессии и аудит; `0007` — consent-gated campaigns и attribution.

Для тестов используется отдельная PostgreSQL database/schema. SQLite разрешён
только для foundation-проверок, но не подтверждает блокировки, миграции или
конкурентную бронь.

Все системные даты timezone-aware и хранятся в UTC. Денежные суммы — целые
копейки в `RUB`; цена в `order_items` является snapshot и не пересчитывается по
текущему справочнику билетов.
