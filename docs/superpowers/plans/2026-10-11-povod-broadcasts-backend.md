# Рассылки: бэкенд — план реализации (этап 1 из 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** серверная часть рассылок владельца: лайки на сервере, сегменты, шаблоны, API `/api/owner/campaigns*`, отправка с заморозкой списка, лимитом 2/7 и тихими часами, клики и статистика.

**Architecture:** новый роутер `src/api/owner/campaigns.py` над сервисами в `src/services/campaigns/` (содержимое, аудитория, запуск, рендер, статистика). Существующий конвейер (`CampaignDeliveryWorker` → `Outbox` → `CampaignOutboxWorker`) остаётся единственным: он начинает с заморозки списка в `campaign_deliveries`, а отправитель получает готовое `RenderedMessage` (фото, HTML, кнопки). Схема — миграция 0010. Cookie-админка `src/api/admin/campaigns.py` не меняется и едет по тому же конвейеру.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, aiogram 3, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-10-11-povod-broadcasts-design.md`

## Этапы

1. **Этап 1 — бэкенд** (этот план, Task 1–9).
2. **Этап 2 — экраны «Рассылки» на моках** (`webapp/`, отдельный план и сессия): вкладка «Рассылки» в режиме владельца при `manage_campaigns`; список с фильтрами и карточками; старт (готовый / свой шаблон / чистый лист); редактор (название, вечер с подстановкой `{event}`/`{date}`, текст с b/i/ссылкой и счётчиком 1024/4096, картинка, до 2 кнопок, аудитория с живым счётчиком через 300 мс, предпросмотр-пузырь); «Отправить себе / черновик / как шаблон / Отправить… сейчас или по времени» с переспросом ночью; экраны запланированной, идущей, отправленной; шаблоны. Всё на `MockCampaignApi` по контракту раздела 7 и этого плана, голос — `copy.test.ts`.
3. **Этап 3 — подключение** (отдельный план и сессия): HTTP-клиент рассылок вместо мока; лайки на сервер (`PUT/DELETE /favorites`, повтор при следующем открытии) и разовый `import` из `localStorage` с флагом; разбор `startapp=event_<id>[_c<code>]` и `POST /api/app/campaign-open`; ручная проверка на staging.

## Global Constraints

- Без реальных запросов к Т‑Банку и Telegram: отправитель в тестах всегда подменён.
- `.env` не читать, не печатать, не коммитить.
- Интеграционные тесты — PostgreSQL через `TEST_DATABASE_URL` (фикстуры `pg_factory`, `db_session`); прогон: `python -m pytest <path> -q 2>&1 | tail -1`.
- Ошибки для владельца — `{message[, field]}` через `OwnerApiError`, на «ты», без «пожалуйста» и «!». Поля в ответах и запросах — camelCase (`OwnerIn`/`to_camel`, как у событий).
- Право — `Permission.MANAGE_CAMPAIGNS`; без него 403.
- Тело — Telegram HTML: только `b`, `i`, `a href="https://…"`. Длина видимого текста ≤ 1024 с картинкой, ≤ 4096 без.
- Кнопок ≤ 2; подпись 1–40 знаков; ссылка только `https://`, ≤ 2048.
- Лимит: гость с ≥ 2 доставками `sent` за последние 7 дней при заморозке получает `skipped_limit`.
- Тихие часы 22:00–10:00 МСК (`Europe/Moscow`): 21:59 можно, 22:00 нельзя, 09:59 нельзя, 10:00 можно.
- Скорость ≤ `settings.campaign_rate_limit_per_second` (25) сообщений/с на процесс.
- Ключ дедупликации — `campaign:<id>:user:<id>` (уже так).
- Аудит: `owner.campaign.create|update|image|schedule|start|cancel|stop|duplicate|test`, `owner.template.create|update|delete` через `AuditService`.

## Review Focus

1. Двойной тап «Отправить» — вторая заявка получает 422 «Эту рассылку уже не изменить», список не замораживается дважды (тест в Task 7).
2. Вечер сняли с публикации между планированием и временем отправки — воркер отменяет рассылку с `cancel_reason = "event_unpublished"`, никто ничего не получает (тест в Task 7).
3. Текст с `<u>`, незакрытым `<b>`, `href="javascript:…"` или голым `<` — 422 на сохранении, а не ошибка Telegram посреди отправки (тест в Task 3).
4. Гость заблокировал бота посреди рассылки — `users.is_blocked = true`, в следующую рассылку не попадает (тест в Task 8).
5. Время в `at` с другим поясом (`Z`, `+05:00`) — тихие часы считаются по МСК, а не по поясу запроса (тест в Task 7).

---

### Task 1: Схема 0010 и модели

**Files:**
- Create: `migrations/versions/0010_broadcasts.py`, `src/models/favorites.py`
- Modify: `src/models/campaigns.py`, `src/models/__init__.py`
- Test: `tests/integration/test_broadcasts_schema.py`

**Interfaces:**
- Produces: `Favorite(user_id, event_id, created_at)`; `Campaign` + поля `image: dict`, `buttons: list`, `event_id: UUID | None`, `started_at`, `finished_at`, `recipient_count: int | None`, `short_code: str`, `telegram_photo_id: str | None`, `cancel_reason: str | None`; `CampaignStatus.STOPPED`; `DeliveryStatus.SKIPPED_LIMIT`; `CampaignTemplate(id, name, body, image_kind, buttons, is_builtin, created_by, created_at, updated_at)`; `CampaignLink(code, campaign_id, button_index, url)`; `CampaignClick(id, campaign_id, user_id | None, button_index, clicked_at)`; `new_short_code() -> str` в `src/models/campaigns.py` (8 символов `[A-Za-z0-9]`, `secrets`).

Миграция (`revision = "0010"`, `down_revision = "0009"`):
- `favorites`: `user_id` FK users RESTRICT, `event_id` FK events RESTRICT, `created_at` timestamptz NOT NULL default now(); PK (`user_id`, `event_id`); индекс `ix_favorites_event`.
- `campaigns`: `image` JSONB NOT NULL default `'{"kind": "none"}'`; `buttons` JSONB NOT NULL default `'[]'`; `event_id` FK events RESTRICT nullable; `started_at`, `finished_at` timestamptz; `recipient_count` Integer; `short_code` String(12) — добавить nullable, заполнить `substr(md5(id::text), 1, 8)`, сделать NOT NULL + unique; `telegram_photo_id` String(256); `cancel_reason` String(64). Снять `body_nonempty` (черновик с чистого листа пуст; непустоту проверяет запуск). Check статуса + `'stopped'`.
- `campaign_deliveries`: check статуса + `'skipped_limit'`; индекс `ix_campaign_deliveries_user_sent` (`user_id`, `sent_at`).
- `campaign_templates`: `id` UUID PK, `name` String(128) NOT NULL, `body` Text NOT NULL, `image_kind` String(8) check `IN ('event','upload','none')`, `buttons` JSONB NOT NULL default `'[]'`, `is_builtin` bool NOT NULL default false, `created_by` FK admin_users SET NULL, `created_at`/`updated_at`. Вставить пять готовых (ниже).
- `campaign_links`: `code` String(12) PK, `campaign_id` FK CASCADE, `button_index` SmallInteger, `url` String(2048); unique (`campaign_id`, `button_index`).
- `campaign_clicks`: `id` UUID PK, `campaign_id` FK CASCADE, `user_id` FK users RESTRICT nullable, `button_index` SmallInteger, `clicked_at` timestamptz default now(); индекс (`campaign_id`, `user_id`).
- downgrade обратный; перед возвратом check статусов — `DELETE` строк `skipped_limit`, `UPDATE campaigns SET status='cancelled' WHERE status='stopped'`.

Готовые шаблоны (голос `docs/brand/bot-entry-copy.md`; `{event}`/`{date}` подставляет редактор при выборе вечера):

| name | body | image_kind | buttons |
|---|---|---|---|
| Новый вечер в афише | `{date} у нас «{event}». Билеты уже можно взять.` | event | `[{"kind":"event","label":"Открыть вечер"}]` |
| Осталось мало мест | `На «{event}» осталось совсем немного мест. Если думаешь пойти, лучше не откладывать.` | event | то же |
| Завтра вечер | `Завтра «{event}». Если билета ещё нет, он тут.` | event | то же |
| Спасибо, что пришли | `Спасибо за «{event}», было здорово. Следующий вечер уже в афише.` | none | `[]` |
| Вечер перенесён | `С «{event}» поменялись планы. Все подробности по кнопке.` | event | то же |

- [ ] **Step 1: Failing tests** в `tests/integration/test_broadcasts_schema.py`:
  - `test_favorite_primary_key` — два одинаковых `Favorite` → `IntegrityError`.
  - `test_campaign_defaults_and_short_code` — новый `Campaign` с пустым `body=""`: `image == {"kind": "none"}`, `buttons == []`, `len(short_code) == 8`; `status="stopped"` сохраняется; `status="bogus"` → `IntegrityError`.
  - `test_delivery_accepts_skipped_limit`.
  - `test_builtin_templates_seeded` — 5 строк `is_builtin`, имена из таблицы выше.
- [ ] **Step 2:** `python -m pytest tests/integration/test_broadcasts_schema.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** миграция, модели (`short_code` default `new_short_code`), экспорт в `src/models/__init__.py`.
- [ ] **Step 4:** тот же прогон → PASS; весь набор `python -m pytest -q 2>&1 | tail -1` зелёный.
- [ ] **Step 5:** Commit `feat(campaigns): migration 0010 — favorites, rich campaigns, templates, links, clicks`.

---

### Task 2: Вход гостя по initData и лайки на сервере

**Files:**
- Create: `src/api/telegram_auth.py`, `src/api/guest/auth.py`, `src/api/guest/favorites.py`, `src/repositories/favorites.py`
- Modify: `src/api/owner/auth.py` (разбор initData переезжает в общий модуль), `src/api/guest/router.py` (импорт модуля с маршрутами)
- Test: `tests/integration/test_guest_favorites.py`

**Interfaces:**
- Produces: `parse_init_data(authorization: str | None) -> aiogram WebAppUser` (401/503 как сейчас в `get_owner_actor`); `async def get_guest_user(session, authorization) -> User` — `UserService.upsert_telegram_user(user.id, first_name, last_name, username, None)` и возврат модели; `FavoriteRepository(session)`: `add(user_id, event_id) -> None` (`ON CONFLICT DO NOTHING`), `remove(user_id, event_id) -> None`, `list_ids(user_id) -> list[UUID]` (по `created_at`), `import_ids(user_id, ids: list[UUID]) -> None` (только опубликованные вечера, остальные молча пропускаются).

Маршруты (`/api/app`, заголовок `Authorization: tma <initData>`):
- `PUT /favorites/{event_id}` → 204; вечер не найден или не `published` → 404 `{"message": "Вечер не найден"}`.
- `DELETE /favorites/{event_id}` → 204 всегда.
- `GET /favorites` → `{"eventIds": [...]}`.
- `POST /favorites/import` `{"eventIds": [...]}` → `{"eventIds": [...]}` (итоговый список); больше 200 id → 422.

- [ ] **Step 1: Failing tests** (initData подписывать `sign_init_data` из `tests/owner_fixtures.py`, окружение — `owner_env`):
  - `test_favorites_need_init_data` — без заголовка 401.
  - `test_put_is_idempotent_and_get_lists` — два `PUT` одного вечера → `GET` даёт `[id]`; пользователь создан по `telegram_id` из initData.
  - `test_put_unpublished_event_is_404`.
  - `test_delete_is_idempotent` — `DELETE` несуществующего → 204.
  - `test_import_skips_unknown_and_unpublished` — `[published, draft, uuid4()]` → `{"eventIds": [published]}`; 201 id → 422.
- [ ] **Step 2:** прогон → FAIL.
- [ ] **Step 3:** реализация; `get_owner_actor` теперь зовёт `parse_init_data` — `tests/integration/test_owner_auth.py` должен остаться зелёным.
- [ ] **Step 4:** `python -m pytest tests/integration/test_guest_favorites.py tests/integration/test_owner_auth.py -q 2>&1 | tail -1` → PASS.
- [ ] **Step 5:** Commit `feat(app): guest initData sign-in and server-side favorites`.

---

### Task 3: Содержимое рассылки — проверка текста и кнопок

**Files:**
- Create: `src/services/campaigns/content.py`
- Test: `tests/unit/test_campaign_content.py`

**Interfaces:**
- Produces: `class CampaignFieldError(ValueError)` с `field: str`, `message: str`; `visible_length(body: str) -> int`; `validate_body(body: str, *, has_image: bool) -> None`; `validate_buttons(buttons: list[dict], *, has_event: bool) -> list[dict]` (нормализует к `{"kind","label"[,"url"]}`); `validate_image(image: dict) -> dict` (`{"kind":"none"}`, `{"kind":"event"}`, `{"kind":"upload","ref":str}`).

Разбор — `html.parser.HTMLParser`: разрешены `b`, `i`, `a` с единственным атрибутом `href`, начинающимся с `https://`; теги должны быть закрыты и вложены правильно; видимый текст = данные + раскрытые сущности. Сообщения:

| случай | field | message |
|---|---|---|
| пусто (после strip видимого текста) | body | Напиши текст рассылки |
| длина > лимита | body | Слишком длинный текст: с картинкой до 1024 знаков, без неё до 4096 |
| чужой тег / атрибут / незакрытый тег / голый `<` | body | Можно только жирный, курсив и ссылку |
| href не https | body | Ссылка должна начинаться с https:// |
| кнопок > 2 | buttons | Не больше двух кнопок |
| `kind: event` без вечера | buttons | Сначала выбери вечер |
| подпись не 1–40 | buttons | Подпись кнопки — от 1 до 40 знаков |
| url не https или > 2048 | buttons | Ссылка должна начинаться с https:// |

- [ ] **Step 1: Failing tests** — параметризованный `test_body_rejects` на `"<u>x</u>"`, `"<b>x"`, `'<a href="javascript:alert(1)">x</a>'`, `'<a href="http://x.ru">x</a>'`, `"a < b"`, `""`, `"<b> </b>"`; `test_body_accepts` на `'<b>Жирно</b> <i>и</i> <a href="https://povod.club">ссылка</a> &amp;'`; `test_length_limits` — 1024 видимых знака с картинкой ок, 1025 → ошибка, 4096 без картинки ок, 4097 → ошибка, теги в счёт не идут; `test_buttons` — три кнопки, event без вечера, пустая подпись, `http://` → ошибки с `field == "buttons"`; валидная пара проходит.
- [ ] **Step 2:** `python -m pytest tests/unit/test_campaign_content.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** реализация.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat(campaigns): validate Telegram HTML body and buttons`.

---

### Task 4: Аудитория и лимит

**Files:**
- Create: `src/services/campaigns/audience.py`, `tests/campaign_fixtures.py`
- Modify: `src/services/crm/segments.py`
- Test: `tests/integration/test_campaign_audience.py`

**Interfaces:**
- Produces: `AudienceFilter` (pydantic, camelCase, `extra="forbid"`): `event: AudienceEvent | None` (`id: UUID`, `relation: Literal["going","liked","liked_not_bought","attended"]`), `direction_id: UUID | None`, `purchases: Literal["any","bought","never"] = "any"`; `AudienceFilter.to_definition() -> dict` (ключи `event`, `directionId`, `purchases` в JSONB); `SegmentService.count(definition) -> int`; `async def limited_user_ids(session, user_ids: list[UUID], now: datetime) -> set[UUID]` — у кого ≥ 2 `sent` с `sent_at > now - 7 дней`; `async def audience_count(session, definition, now) -> tuple[int, int]` — (получат, отсечено лимитом).
- Consumes: старые ключи `SegmentService` (`telegram_ids`, `prior_purchasers`, …) работают как раньше.

`_eligible_statement` дополняется ключами из таблицы раздела 5 спеки; билет связан с гостем через `Ticket.order_id → Order.user_id`; «билет» для `directionId` — `issued` или `checked_in`.

- [ ] **Step 1: Failing tests.** `tests/campaign_fixtures.py`: `async def guest(session, telegram_id, *, liked=(), going=(), attended=(), paid=(), blocked=False, revoked=False) -> User` — прямые ORM-вставки `Order(status=PAID)` + `Ticket` нужного статуса, `Favorite`, `Consent revoked`. Сценарий на два вечера X (направление D1) и Y (D2): A идёт на X; B был на X; C лайкнул X без покупки; E лайкнул X и купил; F ничего; G лайкнул X, `is_blocked`; H лайкнул X, маркетинг `revoked`. Тесты по множествам `telegram_id`:
  - `going X` → {A, E}; `attended X` → {B}; `liked X` → {C, E}; `liked_not_bought X` → {C}.
  - `directionId D1` → {A, B, C, E}; `directionId D2` → {}.
  - `purchases bought` → {A, B, E}; `never` → {C, F}.
  - `liked X` + `purchases never` → {C}; пустой фильтр → {A, B, C, E, F}.
  - `test_audience_filter_rejects_unknown_relation` — `ValidationError`.
  - `test_limit_counts_two_sent_in_seven_days` — у A две `sent` 6 дней назад → A в `limited`; у B одна `sent` + одна `failed` → нет; у C две `sent` 8 дней назад → нет; `audience_count` для пустого фильтра → `(4, 1)`.
- [ ] **Step 2:** прогон → FAIL.
- [ ] **Step 3:** реализация.
- [ ] **Step 4:** PASS; `tests/integration/test_consent_gated_campaign.py` зелёный.
- [ ] **Step 5:** Commit `feat(campaigns): audience filters by event, direction, purchases and weekly limit`.

---

### Task 5: API рассылок и шаблонов (без отправки)

**Files:**
- Create: `src/services/campaigns/owner.py`, `src/services/campaigns/templates.py`, `src/api/owner/campaigns.py`, `src/api/owner/campaign_schemas.py`
- Modify: `src/api/owner/auth.py` (`require_owner_campaigns`), `src/api/owner/__init__.py` (импорт модуля), `src/services/media/posters.py` (общее `store_image`)
- Test: `tests/integration/test_owner_campaigns.py`

**Interfaces:**
- Consumes: Task 3 (`validate_*`), Task 4 (`AudienceFilter`, `audience_count`).
- Produces: `OwnerCampaignService(session)`: `create(actor_id, data) -> Campaign`, `update(campaign_id, patch, updated_at) -> Campaign`, `get(campaign_id) -> Campaign`, `list(which: Literal["draft","scheduled","sent"]) -> list[Campaign]`, `duplicate(campaign_id, actor_id) -> Campaign`, `set_image(campaign_id, key)`, `clear_image(campaign_id)`; ошибки — `CampaignFieldError`, `CampaignConflict(message)` (409), `LookupError` (404), `CampaignLocked` (422 «Эту рассылку уже не изменить»). `TemplateService(session)`: `list()`, `create(actor_id, data)`, `update(id, data)`, `delete(id)`, `from_campaign(campaign_id, actor_id, name)`; правка/удаление готового → `TemplateLocked` (403 «Готовый шаблон не меняется. Скопируй его в свои»). `store_image(data, media_root, folder, min_size) -> StoredPoster`; `store_poster` = `store_image(…, "posters", (800, 1000))`; для рассылок `("campaigns", (320, 320))`. `CampaignOut` (camelCase): `id, title, body, image {kind, ref?, url?}, buttons, eventId, audience, status, scheduledAt, startedAt, finishedAt, recipientCount, cancelReason, updatedAt`, в списке ещё `delivered`, `clicked`.

Правила:
- `POST /campaigns` принимает необязательные `title` (по умолчанию «Новая рассылка»), `body`, `image`, `buttons`, `eventId`, `audience` → 201. Черновик хранит и незаконченный текст: в `create`/`update` пустое тело допустимо, но всё непустое проверяется `validate_*`.
- `eventId` — только опубликованный вечер (422 `field: "eventId"`, «Вечер не опубликован»).
- `PATCH` — только `draft`/`scheduled`, иначе `CampaignLocked`; `updatedAt` не совпал → 409 «Рассылку уже изменили в другой вкладке. Обнови страницу».
- `filter=sent` — `running|completed|stopped|cancelled`, по `started_at`/`updated_at` убыв.
- `duplicate` — новый черновик: содержимое, картинка (ссылка на тот же файл, файлы не удаляются) и аудитория; название «<title> (копия)»; новый `short_code`, `telegram_photo_id` не копируется.
- Шаблоны: готовые первыми, затем свои по `updated_at` убыв.
- Картинка: `POST /campaigns/{id}/image` (multipart `file`) — блокировка «одна загрузка на админа» как у постеров; `DELETE` → `{"kind":"none"}`.
- `POST /campaigns/audience-count` (`AudienceFilter`) → `{"count": n, "overLimit": m}`.

- [ ] **Step 1: Failing tests** (`owner_app`, `make_admin`, `owner_headers` из `tests/owner_fixtures.py`):
  - `test_campaigns_need_manage_campaigns` — роль `entrance` → 403 на `GET /api/owner/campaigns`.
  - `test_create_draft_from_scratch_and_patch` — `POST {}` → 201, `title == "Новая рассылка"`, `body == ""`; `PATCH` с текстом и `updatedAt` → 200; старый `updatedAt` → 409.
  - `test_patch_rejects_bad_body_with_field` — `"<u>x</u>"` → 422 `{"field": "body", …}`.
  - `test_event_must_be_published` — черновик вечера → 422 `field == "eventId"`.
  - `test_list_filters` — черновик, запланированная, завершённая попадают каждая в свой фильтр.
  - `test_duplicate_makes_draft_copy`.
  - `test_builtin_template_is_read_only` — `PATCH`/`DELETE` готового → 403; свой создаётся, правится, удаляется; `save-as-template` переносит `body`, `image.kind`, `buttons`.
  - `test_audience_count` — на фикстуре Task 4 → `{"count": …, "overLimit": …}`.
  - `test_upload_campaign_image` — PNG 400×400 → `image.kind == "upload"`, файл `MEDIA_ROOT/campaigns/*-1080.webp` есть; `DELETE` → `kind == "none"`.
  - Каждое изменение пишет `owner.campaign.*` / `owner.template.*` в `admin_audit_logs` (проверить в одном тесте).
- [ ] **Step 2:** прогон → FAIL.
- [ ] **Step 3:** реализация.
- [ ] **Step 4:** PASS; `tests/integration/test_owner_posters.py` зелёный после выноса `store_image`.
- [ ] **Step 5:** Commit `feat(owner): campaigns and templates API`.

---

### Task 6: Рендер сообщения и отправитель Telegram

**Files:**
- Create: `src/services/campaigns/render.py`, `src/services/campaigns/telegram.py`
- Modify: `src/core/config.py` (`miniapp_link: str = ""` — `https://t.me/<бот>/<app>`; `public_base_url: str = ""`), `.env.example` (если есть)
- Test: `tests/unit/test_campaign_render.py`, `tests/unit/test_campaign_telegram.py`

**Interfaces:**
- Produces: `InlineButton(label: str, url: str)`; `RenderedMessage(text: str, photo_path: Path | None, photo_file_id: str | None, buttons: list[InlineButton])`; `render(campaign: Campaign, event: Event | None, links: dict[int, str], *, media_root, miniapp_link, public_base_url, direct_urls: bool = False) -> RenderedMessage` — кнопка `event` → `f"{miniapp_link}?startapp=event_{event.id}_c{campaign.short_code}"`; `url` → `f"{public_base_url}/r/{links[i]}"`, при `direct_urls=True` — исходный `url` (для «Отправить себе»); картинка `event` → `media_root / f"{event.cover_ref}-1080.webp"`, `upload` → `media_root / f"{ref}-1080.webp"`; при `campaign.telegram_photo_id` — он вместо пути. Нет нужной настройки → `CampaignNotReady("Кнопки пока не настроены. Напиши разработчику")`. `SentMessage(message_id: str, photo_file_id: str | None)`; `class RetryAfter(Exception)` с `seconds: float`; `class RecipientBlocked(Exception)`; протокол `CampaignSender.send(telegram_id: int, message: RenderedMessage) -> SentMessage`; `AiogramCampaignSender(bot)`.

`AiogramCampaignSender.send`: с фото — `bot.send_photo(chat_id, photo=file_id or FSInputFile(path), caption=text, parse_mode="HTML", reply_markup=…)`, `photo_file_id` = самый большой размер из ответа; без фото — `bot.send_message(…, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))`; `TelegramRetryAfter` → `RetryAfter(e.retry_after)`; `TelegramForbiddenError` → `RecipientBlocked`.

- [ ] **Step 1: Failing tests.** Render: startapp-ссылка ровно `https://t.me/povodbot/app?startapp=event_<uuid>_c<code>` и не длиннее 64 знаков после `startapp=`; url-кнопка → `https://povod.club/r/<code>`; `direct_urls=True` → исходный url; картинка вечера → путь `…/posters/<key>-1080.webp`; закешированный `telegram_photo_id` побеждает путь; пустой `miniapp_link` при event-кнопке → `CampaignNotReady`. Telegram: фейковый bot-объект с `send_photo`/`send_message`, записывающий аргументы; проверка `parse_mode`, отключённого превью, разметки кнопок; исключения aiogram превращаются в `RetryAfter(3)` и `RecipientBlocked`.
- [ ] **Step 2:** `python -m pytest tests/unit/test_campaign_render.py tests/unit/test_campaign_telegram.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** реализация.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat(campaigns): render photo, HTML and buttons; aiogram sender`.

---

### Task 7: Запуск — заморозка, тихие часы, отмена, остановка, «себе»

**Files:**
- Create: `src/services/campaigns/launch.py`
- Modify: `src/services/campaigns/delivery.py`, `src/api/owner/campaigns.py`
- Test: `tests/unit/test_quiet_hours.py`, `tests/integration/test_campaign_launch.py`

**Interfaces:**
- Consumes: Task 4 (`resolve`, `limited_user_ids`), Task 6 (`render`, `CampaignSender`).
- Produces: `is_quiet(at: datetime) -> bool`; `next_morning(at: datetime) -> datetime` (ближайшие 10:00 МСК, в UTC); `CampaignLauncher(session)`: `send(campaign_id, at: datetime | None, now) -> Campaign` (`QuietHours(suggested_at)` при `at=None` ночью), `freeze(campaign, now) -> None`, `cancel(campaign_id) -> Campaign`, `stop(campaign_id, now) -> Campaign`; `async def send_test(session, campaign_id, telegram_id, sender, settings) -> None`; FastAPI-зависимость `campaign_sender()` (подменяется в тестах).

Правила:
- `send` — блокировка строки (`with_for_update`), только `draft`; проверка готовности: `validate_body(…, has_image=image.kind != "none")`, `validate_buttons`, вечер опубликован, `render` без `CampaignNotReady`, получателей > 0 («Получателей нет»). `at=None`: ночью — `QuietHours`; днём — `freeze` в этой же транзакции. `at` задан: в прошлом → 422 `field "at"` «Это время уже прошло»; в тихие часы → 422 `field "at"` «С 22:00 до 10:00 не отправляем. Выбери другое время»; иначе `scheduled`.
- `QuietHours` → 422 `{"field": "at", "message": "Ночью не отправляем. Отправить в 10:00?", "suggestedAt": iso}`.
- `freeze`: вечер не опубликован → `cancelled`, `cancel_reason="event_unpublished"`, `finished_at`; иначе все получатели → `campaign_deliveries` (`queued` или `skipped_limit`) одним `INSERT`; создать `CampaignLink` для url-кнопок; `recipient_count`, `started_at=now`, `running`; нет ни одного `queued` → `completed`.
- `CampaignDeliveryWorker.deliver` (переписать): `scheduled` и `scheduled_at` ≤ now (или `None`) → `freeze`; `running` → поставить в `Outbox` до `batch_size` доставок `queued` без строки outbox (payload `{"delivery_id", "campaign_id", "telegram_id"}`); вернуть число поставленных. Повторный проход не создаёт дублей.
- `cancel`: только `scheduled` → `cancelled`, иначе 422 «Отменить можно только запланированную рассылку». `stop`: только `running` → `stopped`, `finished_at`; необработанные строки outbox этой рассылки → `processed_at=now`; иначе 422 «Остановить можно только идущую рассылку».
- `send_test`: тот же `render` c `direct_urls=True`, владельцу `telegram_id` из initData; лимиты и тихие часы не действуют; ничего не пишет в `campaign_deliveries`.
- API: `POST /campaigns/{id}/send {at?}`, `/cancel`, `/stop`, `/test` → `CampaignOut` (`/test` → 204). Аудит `schedule|start|cancel|stop|test`.

- [ ] **Step 1: Failing tests.**
  - `tests/unit/test_quiet_hours.py`: МСК 21:59 → не тихо; 22:00 → тихо; 09:59 → тихо; 10:00 → не тихо; `2026-10-11T19:00:00Z` (22:00 МСК) → тихо; `2026-10-12T09:30:00+05:00` (07:30 МСК) → тихо; `next_morning(23:30 МСК)` → 10:00 МСК следующего дня, `next_morning(03:00 МСК)` → 10:00 того же дня.
  - `test_send_now_freezes_list` — фикстура Task 4 + у A две `sent` 6 дней назад, пустой фильтр: `recipient_count == 5`, 4 `queued` + A `skipped_limit`, статус `running`, `started_at == now`; новый лайк после этого не добавляет строк.
  - `test_send_twice_is_rejected` — второй `send` → `CampaignLocked`, строк не прибавилось.
  - `test_send_at_night_suggests_morning` — `now` = 23:00 МСК → `QuietHours.suggested_at` = 10:00 МСК; через API → 422 с `suggestedAt`.
  - `test_schedule_rejects_past_and_quiet` и `test_schedule_then_worker_freezes_when_due`.
  - `test_unpublished_event_cancels_scheduled` — запланировали, сняли вечер с публикации, `deliver` → `cancelled`, `cancel_reason == "event_unpublished"`, доставок 0.
  - `test_zero_recipients_rejected`.
  - `test_cancel_and_stop` — `stop` идущей: оставшиеся outbox помечены обработанными, `CampaignOutboxWorker` ничего не шлёт.
  - `test_send_test_uses_direct_urls_and_writes_nothing` — фейковый отправитель получил одно сообщение на id владельца с исходным url.
  - Существующие `tests/integration/test_consent_gated_campaign.py` переводятся на новый протокол отправителя (`send(telegram_id, message)`) и остаются зелёными.
- [ ] **Step 2:** прогон → FAIL.
- [ ] **Step 3:** реализация.
- [ ] **Step 4:** `python -m pytest tests/unit/test_quiet_hours.py tests/integration/test_campaign_launch.py tests/integration/test_consent_gated_campaign.py -q 2>&1 | tail -1` → PASS.
- [ ] **Step 5:** Commit `feat(campaigns): freeze recipients, weekly limit, quiet hours, cancel and stop`.

---

### Task 8: Отправка из outbox — рендер, 429, 403, скорость, завершение

**Files:**
- Modify: `src/workers/outbox.py` (`CampaignOutboxWorker`), `src/workers/main.py`, `src/workers/campaign_delivery.py`
- Create: `src/workers/throttle.py`
- Test: `tests/unit/test_throttle.py`, `tests/integration/test_campaign_outbox.py`

**Interfaces:**
- Consumes: Task 6 (`render`, `CampaignSender`, `RetryAfter`, `RecipientBlocked`), Task 7 (`CampaignLink` созданы при заморозке).
- Produces: `Throttle(rate: int, clock=time.monotonic, sleep=asyncio.sleep)` с `async def wait() -> None`; `CampaignOutboxWorker(session_factory, sender, *, settings=None, sleep=asyncio.sleep, throttle=None)`.

Поведение:
- Перед отправкой: рассылка не `running` → outbox обработан, доставка остаётся `queued`; гость сейчас `is_blocked` или маркетинг `revoked` → `blocked`, `error="recipient_not_eligible"`.
- Успех → `sent`, `sent_at`, `provider_message_id`; первый полученный `photo_file_id` записать в `campaign.telegram_photo_id`.
- `RetryAfter(s)` → попытка не считается (`attempts -= 1`), `available_at = now + s`, `await sleep(s)`, проход продолжается.
- `RecipientBlocked` → `blocked`, `error="bot_blocked"`, `users.is_blocked = true`.
- Прочие ошибки → доставка остаётся `queued` с `error`, повтор с паузой `min(attempts*30, 300)` с; после 5-й попытки → `failed`.
- Рассылка `completed` + `finished_at`, когда не осталось ни одной `queued`.
- Перед каждой отправкой `await throttle.wait()` (по умолчанию `settings.campaign_rate_limit_per_second`).
- `src/workers/main.py`: `AiogramCampaignSender(bot)` вместо `AiogramSender`; `TelegramSender` из `campaign_delivery.py` убрать.

- [ ] **Step 1: Failing tests.**
  - `test_throttle_spaces_calls` — `rate=25`, 26 вызовов `wait()` с фейковыми часами → суммарный сон ≥ 1.0 с; первые 25 не спят дольше 1 с суммарно.
  - `test_retry_after_waits_and_does_not_burn_attempt` — отправитель бросает `RetryAfter(3)` один раз: `sleep` вызван с 3, доставка `queued`, `attempts` не вырос; сдвинуть `available_at` в прошлое, второй проход → `sent`.
  - `test_forbidden_marks_user_blocked` — `RecipientBlocked` → доставка `blocked`, `error == "bot_blocked"`, `users.is_blocked`; следующий `audience_count` его не считает.
  - `test_failure_retries_then_fails` — 5 ошибок → `failed`, рассылка `completed`.
  - `test_photo_file_id_is_cached` — после первой отправки с фото следующему гостю уходит `photo_file_id`, а не путь.
  - `test_stopped_campaign_sends_nothing`.
- [ ] **Step 2:** прогон → FAIL.
- [ ] **Step 3:** реализация.
- [ ] **Step 4:** `python -m pytest tests/unit/test_throttle.py tests/integration/test_campaign_outbox.py tests/integration/test_consent_gated_campaign.py -q 2>&1 | tail -1` → PASS.
- [ ] **Step 5:** Commit `feat(campaigns): outbox sends photo and buttons, honours 429, 403 and rate`.

---

### Task 9: Клики, `/r/{code}`, `campaign-open`, статистика

**Files:**
- Create: `src/api/public/redirect.py`, `src/services/campaigns/stats.py`
- Modify: `src/api/guest/favorites.py` (или новый `src/api/guest/campaigns.py`) — `campaign-open`; `src/api/owner/campaigns.py` (`/stats`, сводка в списке); `src/api/app.py` (роутер `/r`); `docs/superpowers/STATUS.md`
- Test: `tests/integration/test_campaign_stats.py`

**Interfaces:**
- Consumes: Task 1 (`CampaignLink`, `CampaignClick`), Task 2 (`get_guest_user`).
- Produces: `CampaignStats(recipients, delivered, failed, failed_reasons: dict[str, int], skipped_limit, clicked, anonymous_clicks, bought: int | None)`; `async def campaign_stats(session, campaign_id, now) -> CampaignStats`; `async def summaries(session, ids) -> dict[UUID, tuple[int, int]]` (delivered, clicked) для списка.

- `GET /r/{code}` → запись клика (`user_id=None`) → 302 на `url`; неизвестный код → 404.
- `POST /api/app/campaign-open {"campaign": "<short_code>"}` (initData) → клик с `user_id` и индексом кнопки `event` → 204; неизвестный код → тоже 204.
- `bought` — получатели с `sent`, у которых `Order PAID` на `event_id`, а строка `order_events` с `next_status='paid'` в [`started_at`, `started_at + 7 дней`]; без вечера → `null`.
- `clicked` — уникальные `user_id` кликов; `anonymousClicks` — клики `/r/` без пользователя.

- [ ] **Step 1: Failing tests.**
  - `test_redirect_records_click` — `GET /r/<code>` (без следования редиректу) → 302, `Location` = url, клик записан; `/r/nope` → 404.
  - `test_campaign_open_records_event_button` — кнопки `[url, event]` → клик с `button_index == 1`.
  - `test_stats` — 4 получателя: 2 `sent`, 1 `blocked (bot_blocked)`, 1 `skipped_limit`; 2 клика одного гостя + 1 анонимный; один `sent` оплатил вечер через 2 дня, другой — через 8 → `{"recipients": 4, "delivered": 2, "failed": 1, "failedReasons": {"bot_blocked": 1}, "skippedLimit": 1, "clicked": 1, "anonymousClicks": 1, "bought": 1}`.
  - `test_list_card_summary` — в `GET /campaigns?filter=sent` у карточки `delivered` и `clicked`.
- [ ] **Step 2:** прогон → FAIL.
- [ ] **Step 3:** реализация; в `STATUS.md` — этап 1 сделан, новые настройки `MINIAPP_LINK`, `PUBLIC_BASE_URL`, следующий шаг — этап 2.
- [ ] **Step 4:** PASS; весь набор `python -m pytest -q 2>&1 | tail -1` зелёный; `ruff check src tests` чисто.
- [ ] **Step 5:** Commit `feat(campaigns): click tracking, /r redirects and campaign stats`.
