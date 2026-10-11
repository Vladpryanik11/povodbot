# Развёртывание

Один сервер, Docker Compose, один домен. Файлы: `docker-compose.prod.yml`,
`deploy/` (Caddy, бэкап, шаблон `.env`). Сервисы: `postgres`, `redis`, `migrate`
(разовая, применяет миграции), `api`, `bot`, `worker`, `caddy` (HTTPS, статика Mini App,
`/api/*`, `/media/*`).

## Режимы

| `ENVIRONMENT` | Для чего | Что обязательно |
|---|---|---|
| `staging` | сервер до подключения T-Bank: бот, превью Mini App, режим владельца | `TELEGRAM_TOKEN`, `TICKET_QR_SECRET` |
| `production` | продажа билетов за деньги | то же + ключи T-Bank, секрет webhook, утверждённые тексты согласия |

В обоих режимах cookie админки с `Secure`, ключ QR обязателен, `/docs`, `/redoc`,
`/openapi.json`, `/metrics` и `/ready` Caddy наружу не отдаёт. В `staging` бот показывает
тестовые тексты согласия — настоящих гостей на нём принимать нельзя.

## Что нужно заранее

- VPS с Ubuntu 22.04/24.04, доступ по SSH. **Сервер должен быть за пределами России:** из российских
  дата-центров Telegram недоступен, бот не сможет получать сообщения (проверено на практике).
  Подходит Германия/Нидерланды/Финляндия. Выбор площадки под платежи (ФЗ-152, T-Bank) — отдельное
  решение, см. STATUS.md. Рекомендуется 2 ГБ памяти (загрузка афиши 40 Мп даёт
  пик 300–400 МБ). Минимум — 1 ГБ памяти, 10 ГБ диска и 1 ядро: работает, но только со swap (шаг 1)
  и без фото в десятки мегапикселей.
- Домен с A-записью на IP сервера (иначе Caddy не получит сертификат).
- Токен бота от @BotFather. Если токен когда-либо попадал в чат или лог — перевыпустить
  (`/revoke`).

## Первая выкладка

1. Docker на сервере: `curl -fsSL https://get.docker.com | sh` (на Ubuntu 24.04 так же работают
   `apt install docker.io docker-compose-v2`). Файрвол: открыть 22, 80, 443
   (`ufw allow 22,80,443/tcp && ufw allow 443/udp && ufw enable`). БД и Redis наружу не
   публикуются.
   Swap (обязателен при 1 ГБ памяти, при 2 ГБ не мешает): `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`.
   Если `swapon` отказывает (контейнерная виртуализация), 1 ГБ слишком мало — брать тариф с 2 ГБ.
2. Код: `git clone https://github.com/Vladpryanik11/povodbot.git /opt/povod`. Для приватного
   репозитория — deploy key (read-only) в настройках репозитория.
3. Секреты: `cd /opt/povod && cp deploy/server.env.example .env && chmod 600 .env`, затем
   заполнить `DOMAIN`, `POSTGRES_PASSWORD`, `TELEGRAM_TOKEN`, `TICKET_QR_SECRET`
   (`openssl rand -hex 32`). Пароль БД — длинный, только буквы и цифры.
4. Запуск: `docker compose -f docker-compose.prod.yml --env-file .env up -d --build`.
   Миграции применятся сами, остальные сервисы ждут их окончания.
5. Проверка:
   - `docker compose -f docker-compose.prod.yml ps` — `api` healthy, `migrate` Exited (0);
   - `curl https://ДОМЕН/health` → `{"status":"ok"}`;
   - `docker compose -f docker-compose.prod.yml logs --tail 30 bot` — нет ошибок;
   - написать боту `/start`.
6. Первый владелец (чтобы открылся «Режим владельца»):
   `docker compose -f docker-compose.prod.yml exec api python -m scripts.create_admin --login owner --role owner --telegram-id ВАШ_TELEGRAM_ID`.
   Пароль вводится в скрытом запросе, минимум 12 символов. Свой Telegram ID показывает бот
   @userinfobot.

## Обновление

```bash
cd /opt/povod && git pull
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Миграции применяются автоматически; `up -d` пересоздаёт только изменившиеся сервисы.
На диске в 10 ГБ после каждого обновления чистить старые образы и кэш сборки:
`docker image prune -f && docker builder prune -f`. Свободное место — `df -h /`.
Бот работает через polling: **держать ровно один экземпляр `bot`**, иначе Telegram вернёт
конфликт. `TICKET_QR_SECRET` после выдачи билетов не менять — старые QR перестанут
читаться.

## Резервные копии

- `./deploy/backup.sh` — копия в `backups/`, последние 14 хранятся, архив проверяется на
  читаемость. Расписание: `15 3 * * * cd /opt/povod && ./deploy/backup.sh >> backups/backup.log 2>&1`.
- `./deploy/restore.sh backups/ФАЙЛ.dump --rehearse` — репетиция: восстановление во
  временную БД, боевая не тронута. Сделать один раз до запуска и после крупных изменений.
- Восстановление в боевую БД: остановить `api bot worker`, `./deploy/restore.sh ФАЙЛ.dump`
  (нужно ввести `RESTORE`), запустить обратно.
- Афиши лежат в томе `media`, не в БД; копировать отдельно: `docker run --rm -v povod_media:/m -v "$PWD/backups":/b alpine tar czf /b/media.tgz -C /m .`.
- Копии на том же диске не защищают от потери сервера: периодически забирать `backups/` на
  другой компьютер.

## Переход на production (после подключения T-Bank)

1. В `.env`: `ENVIRONMENT=production`, `TBANK_TERMINAL_KEY`, `TBANK_PASSWORD`,
   `TBANK_WEBHOOK_SECRET`, утверждённые `PERSONAL_CONSENT_*` и `MARKETING_CONSENT_*`.
2. Зарегистрировать T-Bank webhook на `https://ДОМЕН/api/webhooks/tbank/payment-status`.
3. Пройти пробный платёж в sandbox, затем боевой на минимальную сумму с возвратом.

## Откат

Сначала остановить `worker`, затем откатить код (`git checkout ТЕГ`, `up -d --build`).
Откат схемы — только после проверки совместимости данных и свежей копии БД.

## Известные ограничения (до этапа «Подключение фронта»)

- Mini App на сервере работает на тестовых данных: настоящие вечера в нём не появятся,
  пока не будет `/api/app` и подключения фронта (см. `plans/2026-10-11-povod-launch-roadmap.md`).
- Воркер завершается на первой необработанной ошибке; `restart: unless-stopped` поднимает
  его заново. Правка с обработкой ошибок в цикле — фаза 2 дорожной карты.
- `/ready` проверяет только соединение с БД, не версию схемы.
