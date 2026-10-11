# Режим владельца: бэкенд — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API `/api/owner/*` для владельца из Mini App: вход по Telegram initData, список/создание/правка/публикация/снятие событий, загрузка постера с фокусом.

**Architecture:** Тонкий роутер `src/api/owner/` над существующим `EventService`; новые правила событий — в `src/services/events/service.py`; обработка фото — отдельный чистый модуль `src/services/media/posters.py` (байты → файлы WebP в `MEDIA_ROOT`). Схема — миграция 0009.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, aiogram 3 (`safe_parse_webapp_init_data`), Pillow + pillow-heif, pytest.

**Spec:** `docs/superpowers/specs/2026-10-11-povod-owner-events-design.md`

## Global Constraints

- Без реальных запросов к Т‑Банку и Telegram; initData в тестах подписывается тестовым токеном.
- `.env` не читать, не печатать, не коммитить.
- Интеграционные тесты — только PostgreSQL через `TEST_DATABASE_URL` (фикстура `pg_factory`).
- Тесты запускать с выводом только итога: `python -m pytest <path> -q 2>&1 | tail -1`.
- Тексты ошибок для владельца — на «ты», без «пожалуйста» и «!».
- Фото: ≤ 15 МБ; JPEG/PNG/WebP/HEIC; ≤ 40 Мп; ≥ 800×1000; WebP q=82 без метаданных; варианты 480, 1080, master (длинная сторона ≤ 2000).
- initData `auth_date` не старше 24 часов.
- Каждое изменяющее действие владельца — запись в `admin_audit_logs`.

## Review Focus

1. Фото с GPS в EXIF — в сохранённых файлах нет EXIF вообще (тест в Task 3).
2. Повёрнутое фото с телефона (EXIF Orientation=6) — сохраняется «стоя» (тест в Task 3).
3. Снятие с публикации, когда заказ есть, но бронь истекла и оплата ещё может прийти (поздняя оплата) — запрещено: проверяем наличие **любого заказа**, а не только активной брони (тест в Task 2).
4. Две вкладки сохраняют одно событие — вторая получает 409, а не тихо затирает первую (тест в Task 5).
5. Вторая загрузка фото, пока первая обрабатывается, — 429, а не две параллельные тяжёлые обработки (тест в Task 6).

---

### Task 1: Схема 0009 и привязка админа к Telegram

**Files:**
- Create: `migrations/versions/0009_owner_mode.py`
- Modify: `src/models/events.py` (поля `Event`), `src/models/admin.py` (`AdminUser`), `src/repositories/admin.py`
- Create: `scripts/link_admin_telegram.py`
- Test: `tests/integration/test_owner_schema.py`

**Interfaces:**
- Produces: `Event.address: str | None`, `Event.cover_focus_x: float`, `Event.cover_focus_y: float`, `Event.cover_width: int | None`, `Event.cover_height: int | None`, `Event.accent_color: str | None`; `AdminUser.telegram_id: int | None`; `AdminRepository.user_by_telegram_id(telegram_id: int) -> AdminUser | None`; `async def link_admin_telegram(session: AsyncSession, login: str, telegram_id: int) -> None` (LookupError, если логина нет).

Миграция 0009 (`revision = "0009"`, `down_revision = "0008"`):
- `admin_users.telegram_id` BigInteger, nullable, unique (`uq_admin_users_telegram_id`).
- `events.cover_focus_x`, `events.cover_focus_y` — `Numeric(4,3)`, NOT NULL, server_default `0.5`, check `BETWEEN 0 AND 1`.
- `events.cover_width`, `events.cover_height` — Integer, nullable (размеры варианта 1080; нужны для `Poster.width/height` в webapp — дополнение к спеке §4).
- `events.accent_color` — String(7), nullable, check `accent_color ~ '^#[0-9A-Fa-f]{6}$'`.
- `events.address` → nullable.
- downgrade обратный; для `address` — сперва `UPDATE events SET address = 'Место уточняется' WHERE address IS NULL`.

В модели `cover_focus_*` маппить как `Mapped[float]` с `Numeric(4, 3, asdecimal=False)`.

- [ ] **Step 1: Failing tests** в `tests/integration/test_owner_schema.py`:
  - `test_event_accepts_null_address_and_defaults_focus` — вставить `Event` с `address=None` через ORM, перечитать: `address is None`, `cover_focus_x == 0.5`, `cover_focus_y == 0.5`.
  - `test_focus_and_accent_constraints` — `cover_focus_x=1.5` → `IntegrityError`; `accent_color="red"` → `IntegrityError`.
  - `test_link_admin_telegram` — создать `AdminUser(login="owner", password_hash="x", role="owner")`, `await link_admin_telegram(session, "owner", 42)`, затем `AdminRepository(session).user_by_telegram_id(42)` возвращает этого админа; `link_admin_telegram(session, "nobody", 1)` → `LookupError`; второй админ с тем же `telegram_id` → `IntegrityError`.
  Событие для вставки — через `catalog(session)` из `tests/commerce_fixtures.py` или прямой ORM с направлением из него.
- [ ] **Step 2:** `python -m pytest tests/integration/test_owner_schema.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** Миграция, поля моделей, `user_by_telegram_id`, `link_admin_telegram`. Скрипт: `argparse` (`--login`, `--telegram-id`), сессия из `src.db.session`, коммит, печать `Linked <login> → <telegram_id>`; функция `link_admin_telegram` — в том же файле, её импортирует тест.
- [ ] **Step 4:** Тот же прогон → PASS; затем весь набор `python -m pytest -q 2>&1 | tail -1` — ничего не сломано (адрес в старых тестах всегда задан).
- [ ] **Step 5:** Commit `feat(owner): migration 0009 — telegram link, poster focus, accent, optional address`.

---

### Task 2: Правила событий для владельца

**Files:**
- Modify: `src/services/events/service.py`, `src/repositories/orders.py`, `src/bot/handlers/events.py:60`
- Modify: `tests/unit/services/test_events.py` (`draft()` получает `cover_ref="posters/test"`)
- Test: `tests/unit/services/test_events_owner.py`

**Interfaces:**
- Consumes: поля Task 1.
- Produces (всё в `src/services/events/service.py`):
  - `class EventFieldError(ValueError)` с атрибутами `field: str`, `message: str` (русский текст для владельца).
  - `class EventConflict(Exception)` с атрибутом `message: str`.
  - `CreateEventCommand.address: str | None`, новое `accent_color: str | None = None`; `UpdateEventCommand.accent_color: str | None = None`; `accent_color` и `address` допустимы в `clear_fields`.
  - `EventDTO` и `PublicEventDTO`: `address: str | None`; `EventDTO` добавляет `accent_color: str | None`, `cover_focus_x: float`, `cover_focus_y: float`, `cover_width: int | None`, `cover_height: int | None`.
  - `EventService.update(event_id, command, *, expected_updated_at: datetime | None = None) -> EventDTO` — при несовпадении `EventConflict("Событие уже изменили — обнови")`.
  - `EventService.unpublish(event_id: UUID) -> EventDTO`.
  - `EventService.set_poster(event_id: UUID, key: str, width: int, height: int, focus_x: float, focus_y: float) -> EventDTO`.
  - `EventService.set_poster_focus(event_id: UUID, focus_x: float, focus_y: float) -> EventDTO`.
  - `OrderRepository.exists_for_event(event_id: UUID) -> bool`.

Правила:
- `validate` поднимает `EventFieldError` (подкласс `ValueError` — старый `domain_result` продолжает отдавать 422). Поля и тексты:

| field | условие | message |
|---|---|---|
| `title` | пусто / > 256 | «Назови вечер» / «Название длиннее 256 символов» |
| `description` | пусто / > 100000 | «Добавь пару слов о вечере» / «Описание слишком длинное» |
| `address` | задан, но пусто или > 1024 | «Укажи адрес или выбери «Место уточняется»» |
| `starts_at` | без пояса | «Укажи дату и время» |
| `ends_at` | ≤ начала | «Конец должен быть позже начала» |
| `capacity` | вне диапазона / ниже занятого | «Сколько мест?» / «Уже занято больше мест» |
| `map_url` | не http(s) | «Ссылка на карту не открывается» |
| `ticket_types` | нет активных / имя / цена / лимит / ниже занятого | «Добавь хотя бы один билет» / «У билета нет названия» / «Проверь цену билета» / «Проверь количество билетов» / «Уже продано больше билетов этого типа» |
| `accent_color` | не `#RRGGBB` | «Цвет в формате #RRGGBB» |
| `poster` | публикация без `cover_ref` | «Без фото опубликовать нельзя» |
| `focus` | вне 0–1 | «Точка фокуса вне фото» |

- `address=None` допустим и в черновике, и при публикации.
- `_publication_requirements` требует `cover_ref` (field `poster`).
- `unpublish`: только `PUBLISHED`; если `OrderRepository.exists_for_event` → `EventConflict("Уже есть брони — отменить можно будет через возвраты")`. Иначе `status=DRAFT`, `published_at=None`. Проверка по любому заказу закрывает позднюю оплату (Review Focus 3).
- `set_poster`/`set_poster_focus` работают для `DRAFT` и `PUBLISHED`, обновляют `updated_at`.
- Бот: при `address is None` строка «Место уточняется».

- [ ] **Step 1: Failing tests** в `test_events_owner.py` (фикстура `db_session`, хелперы `draft`, `service` из `test_events.py`):
  - `test_draft_without_address_publishes` — `draft(address=None)` создаётся и публикуется; `dto.address is None`.
  - `test_publish_requires_poster` — `draft(cover_ref=None)` → `publish` поднимает `EventFieldError` с `field == "poster"`.
  - `test_field_error_names_field` — `draft(title=" ")` → `EventFieldError`, `field == "title"`, `message == "Назови вечер"`.
  - `test_unpublish_without_orders` — опубликовать, `unpublish` → `status == DRAFT`, `published_at is None`.
  - `test_unpublish_blocked_by_any_order` — опубликовать, создать заказ через `orders(session)` из `commerce_fixtures` и дать брони истечь (статус `EXPIRED`) → `EventConflict`.
  - `test_update_version_conflict` — `update(..., expected_updated_at=dto.updated_at - timedelta(seconds=1))` → `EventConflict`; с точным `dto.updated_at` проходит.
  - `test_set_poster_and_focus` — `set_poster(id, "posters/abc", 1080, 1350, 0.3, 0.7)` → DTO с этими значениями; `set_poster_focus(id, 1.2, 0.5)` → `EventFieldError` `field == "focus"`.
  - `test_accent_color_validated_and_clearable` — `"#FF8800"` сохраняется; `"orange"` → `EventFieldError("accent_color")`; `clear_fields={"accent_color"}` обнуляет.
- [ ] **Step 2:** `python -m pytest tests/unit/services/test_events_owner.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** Реализовать правила выше; `draft()` в `test_events.py` — `cover_ref="posters/test"`; бот — «Место уточняется».
- [ ] **Step 4:** Новый файл → PASS; весь набор `python -m pytest -q 2>&1 | tail -1` → PASS (старые тесты публикации проходят благодаря `cover_ref` в `draft()`; если какой-то тест публикует событие из `commerce_fixtures.catalog`, дать там `cover_ref="posters/test"`).
- [ ] **Step 5:** Commit `feat(events): owner rules — optional address, poster required, unpublish, version check, field errors`.

---

### Task 3: Обработка постера

**Files:**
- Modify: `pyproject.toml` (deps: `Pillow==11.3.0`, `pillow-heif==1.1.0`, `python-multipart==0.0.20`), `src/core/config.py` (`media_root: Path = Path("media")`)
- Create: `src/services/media/__init__.py`, `src/services/media/posters.py`
- Test: `tests/unit/services/test_posters.py`

**Interfaces:**
- Produces (`src/services/media/posters.py`):
  - `MAX_BYTES = 15 * 1024 * 1024`, `MAX_PIXELS = 40_000_000`, `MIN_SIZE = (800, 1000)`.
  - `class PosterError(ValueError)` с `status: int` (413/415/422) и `message: str`.
  - `@dataclass(frozen=True) class StoredPoster: key: str; width: int; height: int` — `key = "posters/<sha256 hex>"`, `width/height` — размеры варианта 1080.
  - `def store_poster(data: bytes, media_root: Path) -> StoredPoster` — синхронная (вызывается в threadpool).
  - `def poster_url(key: str) -> str` → `f"/media/{key}-1080.webp"`.

Порядок в `store_poster`:
1. `len(data) > MAX_BYTES` → 413 «Фото больше 15 МБ».
2. Сигнатура: JPEG `FF D8 FF`; PNG `89 50 4E 47 0D 0A 1A 0A`; WebP `RIFF????WEBP`; HEIC — `data[4:8] == b"ftyp"` и `data[8:12]` ∈ {`heic`,`heix`,`heif`,`mif1`,`msf1`,`hevc`}. Иначе 415 «Это не фото — подойдут JPEG, PNG, WebP или HEIC».
3. `pillow_heif.register_heif_opener()` один раз на модуль; `Image.open(BytesIO(data))`; если `w*h > MAX_PIXELS` → 422 «Фото слишком большое по пикселям»; любая ошибка Pillow → 415 (тот же текст).
4. `ImageOps.exif_transpose`, `convert("RGB")`; меньше `MIN_SIZE` (по ширине или высоте, после поворота) → 422 «Фото маловато — нужно хотя бы 800×1000».
5. Master: `thumbnail((2000, 2000))`; WebP q=82 в `BytesIO` без `exif`/`icc_profile`; sha256 этих байтов → hash.
6. Варианты 480 и 1080 по ширине из master (не увеличивать). Запись в `media_root/posters/<hash>-{480,1080,master}.webp` через временный файл в той же папке + `os.replace`; если `-master.webp` уже есть — не писать.

- [ ] **Step 1: Failing tests** (картинки генерировать в тесте через Pillow, `tmp_path` как `media_root`):
  - `test_stores_three_webp_variants` — JPEG 1200×1500 → три файла; `-1080.webp` шириной 1080; `StoredPoster.width == 1080`, `height == 1350`.
  - `test_strips_exif_gps` — JPEG с EXIF (GPSInfo тег 34853) → у всех вариантов `Image.open(...).getexif()` пуст и `"exif" not in info`.
  - `test_applies_orientation` — JPEG 1500×1200 с Orientation=6 → master выше, чем шире.
  - `test_heic_accepted` — сохранить 1000×1250 через `pillow_heif` в HEIF → проходит.
  - `test_rejects_small` — 700×900 → `PosterError` 422, текст «Фото маловато — нужно хотя бы 800×1000».
  - `test_rejects_non_image` — `b"%PDF-1.7..."` → 415; обрезанный JPEG (первые 200 байт валидного) → 415.
  - `test_rejects_pixel_bomb` — PNG 8000×6000 (однотонный, маленький по байтам) → 422.
  - `test_rejects_oversize_bytes` — `b"\xff\xd8\xff" + bytes(MAX_BYTES)` → 413.
  - `test_same_photo_same_key` — дважды одни байты → одинаковый `key`, файлов по-прежнему три.
- [ ] **Step 2:** `pip install -e ".[dev]"`, затем `python -m pytest tests/unit/services/test_posters.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** Реализовать модуль и настройку `media_root` (env `MEDIA_ROOT`). Если на Windows пин `pillow-heif` не ставится колесом — взять ближайшую версию с колесом под текущий Python и отметить в коммите.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5:** Commit `feat(media): poster processing — webp variants, exif stripped, heic`.

---

### Task 4: Вход владельца по initData

**Files:**
- Create: `src/api/owner/__init__.py`, `src/api/owner/auth.py`, `src/api/owner/router.py`
- Modify: `src/api/app.py` (подключить `owner_router`)
- Create: `tests/owner_fixtures.py` (подпись initData, клиент)
- Test: `tests/integration/test_owner_auth.py`

**Interfaces:**
- Consumes: `AdminRepository.user_by_telegram_id` (Task 1), `PermissionService`, `AdminActor`.
- Produces:
  - `async def get_owner_actor(authorization: str | None = Header(None), session=Depends(get_async_session)) -> AdminActor` — 401 без/с битым заголовком или просроченным `auth_date`; 403 если активного админа с таким `telegram_id` нет.
  - `async def require_owner_events(actor=Depends(get_owner_actor)) -> AdminActor` — 403 без `Permission.MANAGE_EVENTS`.
  - `router = APIRouter(prefix="/api/owner", tags=["owner"])` в `src/api/owner/router.py`; Task 5/6 добавляют в него маршруты.
  - `GET /api/owner/me` → `{"role": str, "permissions": list[str]}` (только `get_owner_actor`).
  - `GET /api/owner/directions` → `[{"id", "name"}]` активных направлений (`require_owner_events`).
  - `tests/owner_fixtures.py`: `TOKEN = "123:test"`; `def sign_init_data(user_id: int, auth_date: int | None = None, token: str = TOKEN) -> str` (по алгоритму Telegram: `secret = HMAC_SHA256(key=b"WebAppData", msg=token)`, `hash = HMAC_SHA256(secret, data_check_string).hex()`; `user` — JSON с `id`, `first_name`); `def owner_app(factory) -> FastAPI` (как `app_for` в `test_event_publication.py`, без override прав); фикстура `owner_env(monkeypatch)` ставит `TELEGRAM_TOKEN=TOKEN` и чистит `get_settings.cache_clear()`; `async def make_admin(factory, role="owner", telegram_id=42) -> UUID`.

Разбор: заголовок `Authorization: tma <initData>`; `aiogram.utils.web_app.safe_parse_webapp_init_data(token, init_data)`; `ValueError` → 401; `now - auth_date > 24h` → 401; `user.id` → поиск админа, `is_active` обязателен.

- [ ] **Step 1: Failing tests:**
  - `test_me_for_owner` — `make_admin(role="owner")`, заголовок с `sign_init_data(42)` → 200, `"manage_events" in permissions`.
  - `test_missing_or_bad_signature_401` — без заголовка → 401; подпись другим токеном → 401.
  - `test_expired_auth_date_401` — `auth_date = now - 25h` → 401.
  - `test_unknown_or_inactive_user_403` — `sign_init_data(999)` → 403; админ с `is_active=False` → 403.
  - `test_entrance_role_cannot_manage_events` — `role="entrance"`: `/me` 200, `/directions` 403.
- [ ] **Step 2:** `python -m pytest tests/integration/test_owner_auth.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** Реализовать.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5:** Commit `feat(owner): telegram initData auth, /me, /directions`.

---

### Task 5: События в API владельца

**Files:**
- Create: `src/api/owner/events.py` (маршруты добавляются в `router` из Task 4), `src/api/owner/schemas.py`
- Modify: `src/repositories/events.py` (`list_for_owner`), `src/repositories/reservations.py` (`occupied_by_events`)
- Test: `tests/integration/test_owner_events.py`

**Interfaces:**
- Consumes: Task 2 (`EventService` методы, `EventFieldError`, `EventConflict`, `EventDTO`), Task 3 (`poster_url`), Task 4 (`require_owner_events`, фикстуры).
- Produces:
  - `EventRepository.list_for_owner(filter: Literal["all","draft","past"], now: datetime) -> list[Event]` — `all`: `ends_at >= now`, статусы draft/published, по `starts_at` ↑; `draft`: статус draft, `ends_at >= now`, по `starts_at` ↑; `past`: `ends_at < now`, по `starts_at` ↓. Отменённые не показываются.
  - `ReservationRepository.occupied_by_events(event_ids: list[UUID]) -> dict[UUID, int]` — тот же учёт, что `occupied_by_ticket` (ACTIVE + CONVERTED), сгруппированный по событию.
  - Схемы (`schemas.py`): `PosterOut {url, focusX, focusY, width, height}` (`None`, если `cover_ref` пуст; для старых URL-значений `cover_ref` — `url = cover_ref`, размеры 0); `OwnerEventListItem {id, title, startsAt, status, capacity, sold, poster}`; `OwnerEventOut` — все поля `EventDTO` в camelCase + `accentColor`, `poster`, `sold`, `updatedAt`; `OwnerEventInput` (create) и `OwnerEventPatch` (+ обязательное `updatedAt`) — как `CreateEventInput`/`UpdateEventInput` в `src/api/admin/events.py`, плюс `accentColor`, без `cover_ref`.
  - Ошибки: `EventFieldError` → 422 `{"field", "message"}`; `EventConflict` → 409 `{"message"}`; `LookupError` → 404 `{"message": "Вечер не найден"}`.
  - Маршруты (`require_owner_events`): `GET /events?filter=`, `GET /events/{id}`, `POST /events` (201), `PATCH /events/{id}`, `POST /events/{id}/publish`, `POST /events/{id}/unpublish`. Аудит: `owner.event.create|update|publish|unpublish`, `object_type="event"`.

- [ ] **Step 1: Failing tests** (`owner_env`, `make_admin`, `sign_init_data`):
  - `test_create_get_list` — POST черновика без адреса → 201, `address is None`, `poster is None`; GET по id совпадает; `GET /events?filter=draft` содержит его с `sold == 0`.
  - `test_field_error_shape` — POST с `title=""` → 422, тело `{"field": "title", "message": "Назови вечер"}`.
  - `test_publish_needs_poster` — publish без фото → 422 `field == "poster"`.
  - `test_patch_version_conflict` — два PATCH с одним и тем же `updatedAt`: первый 200, второй 409 `{"message": "Событие уже изменили — обнови"}` (Review Focus 4).
  - `test_unpublish_with_order_409` — событие с постером (`EventService.set_poster` напрямую), publish, заказ через `commerce_fixtures` → unpublish 409.
  - `test_past_filter_and_sold` — событие в прошлом (ORM напрямую) только в `past`; активная бронь на 2 места → `sold == 2` в `all`.
  - `test_audit_written` — после create есть запись `owner.event.create` с `actor_id` админа.
- [ ] **Step 2:** `python -m pytest tests/integration/test_owner_events.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** Реализовать.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5:** Commit `feat(owner): events list, form, publish and unpublish`.

---

### Task 6: Загрузка постера и фокус

**Files:**
- Create: `src/api/owner/posters.py`
- Modify: `docker-compose.yml` (volume `media` → `/app/media` у сервиса API, `MEDIA_ROOT=/app/media`), `docs/superpowers/STATUS.md`
- Test: `tests/integration/test_owner_posters.py`

**Interfaces:**
- Consumes: `store_poster`, `PosterError`, `poster_url` (Task 3); `EventService.set_poster`, `set_poster_focus` (Task 2); `require_owner_events`, схема `OwnerEventOut` (Task 4/5).
- Produces:
  - `POST /api/owner/events/{id}/poster` — multipart `file`, form `focus_x: float`, `focus_y: float` → `OwnerEventOut`. Чтение файла не больше `MAX_BYTES + 1` байт; `store_poster` через `run_in_threadpool`; `PosterError` → `{status}` с `{"field": "poster", "message"}`. Аудит `owner.event.poster` с `metadata={"key": key}`.
  - `PATCH /api/owner/events/{id}/poster-focus` — JSON `{focusX, focusY}` → `OwnerEventOut`; аудит `owner.event.poster_focus`.
  - Модульный `_upload_locks: dict[UUID, asyncio.Lock]`; если замок админа занят → 429 `{"message": "Фото ещё загружается — подожди"}`. Замок — на процесс; при нескольких воркерах uvicorn ограничение мягкое (записать в STATUS).

- [ ] **Step 1: Failing tests** (`MEDIA_ROOT` → `tmp_path` через monkeypatch + `get_settings.cache_clear()`):
  - `test_upload_sets_poster` — JPEG 1200×1500, фокус 0.3/0.7 → 200; `poster.url` начинается с `/media/posters/` и оканчивается `-1080.webp`; файл существует в `tmp_path`; `focusX == 0.3`; после этого publish → 200.
  - `test_upload_rejects_small` — 700×900 → 422 `{"field": "poster", "message": "Фото маловато — нужно хотя бы 800×1000"}`; `cover_ref` не изменился.
  - `test_focus_only` — PATCH `{focusX: 0.1, focusY: 0.9}` → 200 со значениями; `{focusX: 2}` → 422 `field == "focus"`.
  - `test_parallel_upload_429` — занять `_upload_locks[admin_id]` в тесте (`async with lock:`) и отправить загрузку → 429 (Review Focus 5).
- [ ] **Step 2:** `python -m pytest tests/integration/test_owner_posters.py -q 2>&1 | tail -1` → FAIL.
- [ ] **Step 3:** Реализовать; volume в `docker-compose.yml`; в `STATUS.md` — что сделан бэкенд режима владельца, что дальше (план экранов), и отложенное: Caddy `/media/*` с `immutable` (этап B), мягкий замок загрузки при нескольких воркерах, чистка осиротевших файлов.
- [ ] **Step 4:** Новый файл → PASS; весь набор `python -m pytest -q 2>&1 | tail -1`; `python -m ruff check . && python -m mypy src` — без ошибок.
- [ ] **Step 5:** Commit `feat(owner): poster upload and focus`.
