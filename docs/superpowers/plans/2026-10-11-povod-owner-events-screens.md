# Режим владельца: экраны на моках — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В Mini App — «Режим владельца» для админов: список «Мои вечера», форма события с публикацией, шит постера с точкой фокуса и предпросмотр «Как видит гость»; всё на `MockOwnerApi` по контракту `/api/owner`.

**Architecture:** Контракт — `webapp/src/api/owner/` (типы один в один с `src/api/owner/schemas.py`, интерфейс `OwnerApi`, ошибка `OwnerApiError` и разбор трёх форм ошибок сервера, мок со своими правилами в стиле `MockApi`). Чистая модель формы — `webapp/src/owner/` (форма ↔ JSON, часовой пояс, рубли, «чего не хватает», предпросмотр); там же хранилище черновиков в памяти, чтобы ввод переживал переход в предпросмотр. Экраны — `webapp/src/screens/owner/`, маршруты `/owner/*`. HTTP-клиент `OwnerApi` — этап B, здесь его нет.

**Tech Stack:** Vite 6, React 18, TypeScript 5, react-router 6 (HashRouter), TanStack Query 5, vitest 3 + Testing Library + jsdom, lucide-react.

**Spec:** `docs/superpowers/specs/2026-10-11-povod-owner-events-design.md` (§3 экраны, §6 ошибки, §7 тесты); контракт — `docs/superpowers/STATUS.md`, раздел «Контракт для экранов»; точные формы JSON — `src/api/owner/schemas.py`, `router.py`, `posters.py`, `errors.py` в ветке `owner-events-backend`.

## Исполнение (решение владельца)

Сам исполнитель, по `superpowers:executing-plans`, в двух сессиях:

- **Сессия 1 — задачи 1–5.** В конце в `STATUS.md` добавить строку «Экраны владельца: задачи 1–5 готовы, дальше задача 6» и закоммитить.
- **Сессия 2 — задачи 6–10.** В конце ревью всей ветки и фикс-пасс: только Critical и Important, минорные замечания — одной строкой в `STATUS.md`. Ревью делает сам исполнитель, сабагент-ревьюер (Sonnet) — только по слову владельца.

## Global Constraints

- Ветка `owner-events-screens` от `owner-events-backend` (в ней уже визуал v2). Не пушить, не сливать.
- Только моки: никаких `fetch`, запросов к Telegram и Т‑Банку. `.env` не трогать.
- Тёмная дизайн-система v2: цвета, радиусы, отступы — только токены `webapp/src/styles/tokens.css` (`--surface-2`, `--r-12`, `--s-16`, `--error`, …), поверхности — класс `glass`; текст не мельче 14 px.
- Голос на «ты»; `src/copy.test.ts` сканирует все `.tsx` и ловит «вы»-формы (`выберите`, `проверьте`, `откройте`, `вам`, `ваш…`).
- JSON — camelCase как в `schemas.py`; загрузка постера — multipart `file`, `focus_x`, `focus_y` (snake_case); тело смены фокуса — `{focusX, focusY}`.
- `updatedAt` — непрозрачная строка: не парсить, не сравнивать, только вернуть в `PATCH`. Ответы загрузки постера и смены фокуса несут свежий `updatedAt` — брать его.
- `poster.width/height` бывают `0` (старые постеры-URL) — нигде не делить на них.
- Право на режим — строка `'manage_events'` в `OwnerMe.permissions`.
- Лимит фото — `15 * 1024 * 1024` байт; форматы — `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif`.
- Превью обрезки: 4:5 «Скоро», 16:9 «На этой неделе», 3:1 «Билет»; `object-position` — `${Math.round(x * 100)}% ${Math.round(y * 100)}%`, как в `ui/PosterImage.tsx`.
- Часовой пояс нового вечера — `'Europe/Moscow'`; в списке (у строки нет `timezone`) даты форматируются в нём же.
- Тесты запускать с выводом только итога: `cd webapp && npx vitest run <path> 2>&1 | grep -E "Tests "`.
- Коммиты заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Владелец правит название, не сохраняя, и загружает фото — ответ загрузки меняет `updatedAt`; следующее «Сохранить» проходит без 409 и не теряет правку (тест в Task 8).
2. Браузер не умеет показать выбранное фото (HEIC в Android WebView) — шит не застревает: подсказка и загрузка с фокусом по центру (тест в Task 8).
3. Двойной тап по «Сохранить» — один запрос, один новый вечер (тест в Task 6).
4. Открыт прошедший или отменённый вечер из «Прошли» — форма только для чтения, «Сохранить» нет (тест в Task 7).
5. Переход в «Как видит гость» и обратно — несохранённый ввод на месте (тест в Task 9).

---

### Task 1: Контракт `OwnerApi` и разбор ошибок

**Files:**
- Create: `webapp/src/api/owner/types.ts`, `webapp/src/api/owner/OwnerApi.ts`, `webapp/src/api/owner/messages.ts`
- Test: `webapp/src/api/owner/OwnerApi.test.ts`

**Interfaces:**
- Produces (`types.ts`, поля один в один со `schemas.py`/`router.py`):
  - `EventStatus = 'draft' | 'published' | 'cancelled' | 'completed'`; `OwnerFilter = 'all' | 'draft' | 'past'`; `Focus = { x: number; y: number }`.
  - `OwnerMe { role: string; permissions: string[] }`, `OwnerDirection { id: string; name: string }`.
  - `OwnerTicketType { id; name; priceKopecks; currency; limit; active }`.
  - `OwnerEventListItem { id; title; startsAt; status; capacity; sold; poster: Poster | null }` (`Poster` — из `api/types.ts`).
  - `OwnerEvent { id; title; description; directionId; startsAt; endsAt; timezone; address: string | null; mapUrl: string | null; capacity; ticketTypes: OwnerTicketType[]; status; publishedAt: string | null; createdAt; updatedAt: string; accentColor: string | null; poster: Poster | null; sold }`.
  - `OwnerTicketTypeInput { id?: string; name; priceKopecks; limit; currency?: 'RUB'; active?: boolean }`.
  - `OwnerEventInput { title; description; directionId; startsAt; endsAt; timezone; address: string | null; capacity; mapUrl: string | null; accentColor: string | null; ticketTypes: OwnerTicketTypeInput[] }`; `OwnerEventPatch = Partial<OwnerEventInput> & { updatedAt: string }`.
- Produces (`OwnerApi.ts`):
  - `interface OwnerApi { me(); directions(); events(filter: OwnerFilter); event(id); createEvent(input: OwnerEventInput); updateEvent(id, patch: OwnerEventPatch); publish(id); unpublish(id); uploadPoster(id, file: File, focus: Focus); setPosterFocus(id, focus: Focus) }` — всё `Promise`, методы событий отдают `OwnerEvent`. Комментарий над интерфейсом: маршрут и метод HTTP на каждый метод (таблица §4 спеки) и правило snake_case для multipart.
  - `class OwnerApiError extends Error { constructor(readonly status: number, message: string, readonly field: string | null = null) }`; `status === 0` — нет сети.
  - `parseOwnerError(status: number, body: unknown): OwnerApiError`.
- Produces (`messages.ts`): `export const MSG = { … } as const` — тексты сервера дословно (`src/services/events/service.py`, `src/services/media/posters.py`, `src/api/owner/*.py`): `title 'Назови вечер'`, `description 'Добавь пару слов о вечере'`, `address 'Укажи адрес или выбери «Место уточняется»'`, `capacity 'Сколько мест?'`, `dateTime 'Укажи дату и время'`, `endsBeforeStart 'Конец должен быть позже начала'`, `mapUrl 'Ссылка на карту не открывается'`, `accentColor 'Цвет в формате #RRGGBB'`, `ticketName 'У билета нет названия'`, `ticketPrice 'Проверь цену билета'`, `ticketLimit 'Проверь количество билетов'`, `needTicket 'Добавь хотя бы один билет'`, `needPoster 'Без фото опубликовать нельзя'`, `started 'Вечер уже начался — поменяй дату'`, `capacityBelowSold 'Уже занято больше мест'`, `conflict 'Событие уже изменили — обнови'`, `hasOrders 'Уже есть брони — отменить можно будет через возвраты'`, `notFound 'Вечер не найден'`, `rejected 'Так изменить вечер нельзя'`, `photoTooBig 'Фото больше 15 МБ'`, `notAPhoto 'Это не фото — подойдут JPEG, PNG, WebP или HEIC'`, `photoSmall 'Фото маловато — нужно хотя бы 800×1000'`, `uploadBusy 'Фото ещё загружается — подожди'`, `focus 'Точка фокуса вне фото'`; клиентские: `network 'Нет связи — данные не потерялись, попробуй ещё раз'`, `direction 'Выбери направление'`, `signIn 'Открой Mini App заново из Telegram'`, `noAccess 'Режим владельца — только для админов клуба'`, `unavailable 'Сервис недоступен — попробуй позже'`, `unknown 'Что-то пошло не так — попробуй ещё раз'`, `checkField 'Проверь это поле'`.

- [ ] **Step 1: Ветка и план первым коммитом**

```bash
git switch -c owner-events-screens owner-events-backend
git add docs/superpowers/plans/2026-10-11-povod-owner-events-screens.md
git commit -m "docs: plan — owner screens on mocks"
```

- [ ] **Step 2: Написать падающий тест `OwnerApi.test.ts`**

```ts
it('keeps the owner error body as is', () => {
  const e = parseOwnerError(422, { field: 'capacity', message: 'Сколько мест?' });
  expect([e.status, e.field, e.message]).toEqual([422, 'capacity', 'Сколько мест?']);
  expect(parseOwnerError(409, { message: MSG.conflict }).field).toBeNull();
});
it('turns English detail strings into owner copy by status', () => {
  expect(parseOwnerError(401, { detail: 'Telegram sign-in required' }).message).toBe(MSG.signIn);
  expect(parseOwnerError(403, { detail: 'Admin access required' }).message).toBe(MSG.noAccess);
  expect(parseOwnerError(503, { detail: 'Telegram sign-in is not configured' }).message).toBe(MSG.unavailable);
  expect(parseOwnerError(400, { detail: 'x' }).message).toBe(MSG.unknown);
});
it('takes the field from a FastAPI validation error', () => {
  const e = parseOwnerError(422, { detail: [{ loc: ['body', 'capacity'], msg: 'Input should be a valid integer' }] });
  expect([e.field, e.message]).toEqual(['capacity', MSG.checkField]);
  expect(parseOwnerError(422, { detail: [{ loc: ['query', 'filter'] }] }).field).toBeNull();
});
it('falls back for bodies it does not know', () => {
  expect(parseOwnerError(500, '<html>').message).toBe(MSG.unknown);
  expect(parseOwnerError(500, null).field).toBeNull();
});
```

- [ ] **Step 3: Запустить — падает** (`Cannot find module './OwnerApi'`)

Run: `cd webapp && npx vitest run src/api/owner 2>&1 | grep -E "Tests |Error"`

- [ ] **Step 4: Реализовать `types.ts`, `messages.ts`, `OwnerApi.ts`**

`parseOwnerError`: объект со строкой `message` → как есть (`field` — если строка); `detail`-строка → по статусу 401/403/503, иначе `unknown`; `detail`-массив → `field = loc[1]`, только если `loc[0] === 'body'` и `loc[1]` строка, текст `checkField`; всё прочее → `unknown`.

- [ ] **Step 5: Запустить — проходит**; `npm run typecheck` чистый.

- [ ] **Step 6: Коммит** — `feat(webapp): owner API contract and error parsing`

---

### Task 2: Модель формы события

**Files:**
- Create: `webapp/src/owner/form.ts`
- Test: `webapp/src/owner/form.test.ts`

**Interfaces:**
- Consumes: типы и `MSG` из Task 1; `EventDetail` из `api/types.ts`.
- Produces:
  - `CLUB_TIMEZONE = 'Europe/Moscow'`.
  - `interface TicketRow { key: string; id: string | null; name: string; price: string; limit: string; active: boolean }` (`key` — стабильный ключ React; у сохранённых = `id`).
  - `interface EventForm { title; description; directionId; startsLocal; endsLocal; timezone; venueTbd: boolean; address; mapUrl; capacity: string; accentColor: string /* '' = нет */; tickets: TicketRow[] }` — все строки, кроме отмеченных.
  - `FORM_FIELDS = ['title','description','directionId','startsAt','endsAt','address','mapUrl','capacity','accentColor','ticketTypes','poster'] as const`; `type FormField = typeof FORM_FIELDS[number]`.
  - `toZonedIso(local: string, timeZone: string): string` (`'2026-10-20T19:00'` → ISO со смещением пояса), `fromZonedIso(iso: string, timeZone: string): string` (→ `'YYYY-MM-DDTHH:mm'`).
  - `parseRubles(text: string): number | null` (копейки), `formatRubles(kopecks: number): string`, `parseCount(text: string): number | null` (целое ≥ 1).
  - `emptyForm(): EventForm`, `newTicketRow(): TicketRow`, `formFromEvent(event: OwnerEvent): EventForm`.
  - `formToInput(form: EventForm): { ok: true; input: OwnerEventInput } | { ok: false; field: FormField; message: string }`.
  - `publishGaps(form: EventForm, hasPoster: boolean): string[]`.
  - `toPreviewDetail(form: EventForm, event: OwnerEvent | undefined, now: number): EventDetail`.

- [ ] **Step 1: Написать падающие тесты**

```ts
it('converts Moscow wall time both ways', () => {
  expect(toZonedIso('2026-10-20T19:00', 'Europe/Moscow')).toBe('2026-10-20T19:00:00+03:00');
  expect(fromZonedIso('2026-10-20T16:00:00Z', 'Europe/Moscow')).toBe('2026-10-20T19:00');
  expect(fromZonedIso('2026-10-20T16:00:00.123456+00:00', 'Europe/Moscow')).toBe('2026-10-20T19:00');
});
it('reads rubles the way people type them', () => {
  expect(parseRubles('1 500')).toBe(150000);
  expect(parseRubles('1500,50')).toBe(150050);
  expect(parseRubles('1 500.5')).toBe(150050);
  expect(parseRubles('0')).toBe(0);
  for (const bad of ['', '-5', '12,345', 'abc']) expect(parseRubles(bad)).toBeNull();
  expect(formatRubles(150050)).toBe('1500,50');
  expect(formatRubles(150000)).toBe('1500');
  expect(parseCount('30')).toBe(30);
  for (const bad of ['', '0', '2.5', '-1']) expect(parseCount(bad)).toBeNull();
});
it('round-trips an event through the form', () => {
  const input = formToInput(formFromEvent(EVENT));            // EVENT — OwnerEvent-литерал в тесте
  expect(input).toEqual({ ok: true, input: expect.objectContaining({
    startsAt: '2026-10-20T19:00:00+03:00', address: 'Покровка, 1', mapUrl: null, accentColor: null,
    ticketTypes: [{ id: 't1', name: 'Входной', priceKopecks: 150000, limit: 30, currency: 'RUB', active: true }],
  }) });
});
it('sends null for the venue when it is still being decided', () => {
  const form = { ...formFromEvent(EVENT), venueTbd: true, address: 'старый' };
  expect(formToInput(form)).toMatchObject({ ok: true, input: { address: null } });
});
it('names the first field it cannot send', () => {
  expect(formToInput({ ...emptyForm(), title: 'x' })).toEqual({ ok: false, field: 'directionId', message: MSG.direction });
  const base = formFromEvent(EVENT);
  expect(formToInput({ ...base, endsLocal: '' })).toMatchObject({ field: 'endsAt', message: MSG.dateTime });
  expect(formToInput({ ...base, capacity: 'много' })).toMatchObject({ field: 'capacity', message: MSG.capacity });
  expect(formToInput({ ...base, tickets: [{ ...base.tickets[0], price: 'дорого' }] })).toMatchObject({ field: 'ticketTypes', message: MSG.ticketPrice });
});
it('lists what publishing still needs', () => {
  expect(publishGaps(emptyForm(), false)).toEqual(['название', 'направление', 'дату и время', 'адрес', 'описание', 'вместимость', 'билет', 'фото']);
  expect(publishGaps({ ...formFromEvent(EVENT), venueTbd: true, address: '' }, true)).toEqual([]);
  const off = formFromEvent(EVENT); off.tickets[0].active = false;
  expect(publishGaps(off, true)).toEqual(['билет']);
});
it('builds the guest view from unsaved input', () => {
  const form = { ...formFromEvent(EVENT), title: 'Новое имя', capacity: '20' };
  const detail = toPreviewDetail(form, { ...EVENT, sold: 5 }, T0);
  expect(detail).toMatchObject({ title: 'Новое имя', seatsLeft: 15, soldOut: false, minPriceKopecks: 150000, poll: null, attendees: { count: 0, avatars: [] } });
  expect(toPreviewDetail({ ...emptyForm(), capacity: 'x' }, undefined, T0)).toMatchObject({ seatsLeft: 0, ticketTypes: [], poster: null });
});
```

- [ ] **Step 2: Запустить — падает**

Run: `cd webapp && npx vitest run src/owner/form.test.ts 2>&1 | grep -E "Tests |Error"`

- [ ] **Step 3: Реализовать `form.ts`**

- Смещение пояса — через `Intl.DateTimeFormat(…, { timeZone, hourCycle: 'h23', … }).formatToParts` в момент времени (две итерации для перехода на летнее время); в ISO смещение `±HH:MM`.
- `formToInput` проверяет по порядку только то, что нельзя отправить: `directionId` пуст → `MSG.direction`; пустые `startsLocal`/`endsLocal` → `MSG.dateTime` (`startsAt`/`endsAt`); `parseCount(capacity)` → `MSG.capacity`; для каждой строки билета: пустое имя → `ticketName`, цена → `ticketPrice`, количество → `ticketLimit`. Остальное (пустое название, описание, адрес, конец раньше начала) проверяет сервер/мок. `title`, `description`, `address` — `trim()`; `mapUrl`, `accentColor` `''` → `null`; `venueTbd` → `address: null`; у строки без `id` поле `id` не отправляется.
- `publishGaps` — порядок из теста: `название`, `направление`, `дату и время`, `адрес` (если не `venueTbd` и пусто), `описание`, `вместимость`, `билет` (нет активной строки), `фото`.
- `toPreviewDetail` — не бросает на плохом вводе: `seatsLeft = max(0, capacity − sold)` (нечитаемая вместимость = 0), `soldOut = seatsLeft === 0`, в `ticketTypes` — активные строки с читаемой ценой (`id ?? key`, `seatsLeft = min(limit, seatsLeft)`), пустая дата → `new Date(now).toISOString()`, `poster` и `sold` — из `event`, `id` — `event?.id ?? 'preview'`.

- [ ] **Step 4: Запустить — проходит**

- [ ] **Step 5: Коммит** — `feat(webapp): owner event form model`

---

### Task 3: `MockOwnerApi`, провайдер и черновики

**Files:**
- Create: `webapp/src/api/owner/ownerFixtures.ts`, `webapp/src/api/owner/MockOwnerApi.ts`, `webapp/src/api/owner/OwnerApiProvider.tsx`, `webapp/src/owner/drafts.ts`
- Modify: `webapp/src/test/render.tsx` (опция `ownerApi`), `webapp/src/main.tsx` (обернуть в `OwnerApiProvider`), `webapp/vitest.setup.ts` (заглушка `URL.createObjectURL`/`revokeObjectURL`, их нет в jsdom)
- Test: `webapp/src/api/owner/MockOwnerApi.test.ts`

**Interfaces:**
- Consumes: Task 1, `mskAt` из `api/mock/fixtures.ts`.
- Produces:
  - `type OwnerRole = 'owner' | 'entrance' | 'guest'`; `ownerRoleFromUrl(search?: string): OwnerRole` — `?owner=guest|entrance`, иначе `'owner'`.
  - `class MockOwnerApi implements OwnerApi`, `constructor({ role?, now?, latencyMs? = 300, offline?, fixtures? })`.
  - `type OwnerFixtures = { directions: OwnerDirection[]; events: OwnerEvent[] }`; `buildOwnerFixtures(now: number): OwnerFixtures`; `LEGACY_POSTER_URL = './mock/tiny.jpg'`. Направления `d-film 'Киновечер'`, `d-workshop 'Мастерклассы'`, `d-book 'Книжный клуб'` (те же id, что у гостевого мока). У каждого события заполнены все поля формы, `capacity 30`, `timezone 'Europe/Moscow'`, 19:00–23:00 МСК (`mskAt`) и один активный билет «Входной» 150000 коп., лимит 30 — иначе проверка билета на публикации сработает раньше проверки фото. События: `e-own-film` опубликован, постер `./mock/kino.jpg` 800×1000, `sold 18`, через 3 дня; `e-own-free` опубликован, постер `./mock/talk.jpg` 1600×800, `sold 0`, через 5 дней; `e-own-workshop` черновик, постер `./mock/party.jpg` 800×1000, через 7 дней; `e-own-book` черновик без постера, через 10 дней; `e-own-past` `completed`, постер `./mock/kino.jpg`, `sold 25`, 5 дней назад; `e-own-legacy` черновик, постер `LEGACY_POSTER_URL` с `width: 0, height: 0`, через 12 дней.
  - `OwnerApiProvider({ api?, children })`, `useOwnerApi(): OwnerApi`, `useOwnerDrafts(): DraftStore` — без провайдера оба берут общий экземпляр по умолчанию (как `useApi`).
  - `class DraftStore { get(key: string): EventForm | undefined; set(key: string, form: EventForm): void; clear(key: string): void }` — ключ: id события или `'new'`.
  - `renderScreen(…, { ownerApi?: OwnerApi })` — по умолчанию `new MockOwnerApi({ latencyMs: 0, now: () => T0 })`, свежий `OwnerApiProvider` на каждый рендер.

Правила мока повторяют сервер (тексты — `MSG`): роль `guest` → любой метод 403 `noAccess`; `entrance` → `me()` `{ role: 'entrance', permissions: ['checkin_tickets', 'lookup_tickets'] }`, остальное 403; `offline` → всё `status 0`, `MSG.network`. Фильтры — как `list_for_owner`: `all` — черновики и опубликованные с `endsAt ≥ now` по возрастанию начала; `draft` — только черновики; `past` — не отменённые с `endsAt < now` по убыванию. Создание/правка — проверки `validate` (поля и тексты как в `service.py`), `422 {field, message}`; правка: нет события → 404, `completed/cancelled` → 422 `rejected`, чужой `updatedAt` → 409 `conflict`, вместимость ниже `sold` → `capacityBelowSold`, у опубликованного — ещё требования публикации; строки без `id` получают новый id, сохранённые, которых нет в списке, — `active: false`. `publish`: не черновик → `rejected`; нет активного билета → `needTicket`; нет постера → `{field:'poster', needPoster}`; начало в прошлом → `{field:'startsAt', started}`. `unpublish`: `sold > 0` → 409 `hasOrders`. `uploadPoster`: размер > лимита → 413 `{field:'poster', photoTooBig}`, тип не из списка → 415 `notAPhoto`, фокус вне 0–1 → 422 `{field:'focus'}`, вторая загрузка, пока идёт первая, → 429 `uploadBusy`; успех — постер `{ url: URL.createObjectURL(file), focusX, focusY, width: 1080, height: 1350 }`. Каждое изменение даёт новый `updatedAt` (ISO-подобная строка, уникальная даже при застывших часах). Наружу — копии, не ссылки на внутреннее состояние.

- [ ] **Step 1: Написать падающие тесты `MockOwnerApi.test.ts`** (`latencyMs: 0`, `now: () => T0`)

```ts
it('lets the owner in and keeps guests and door staff out', async () => {
  expect((await api().me()).permissions).toContain('manage_events');
  await expect(api({ role: 'guest' }).me()).rejects.toMatchObject({ status: 403, message: MSG.noAccess });
  expect((await api({ role: 'entrance' }).me()).permissions).not.toContain('manage_events');
  await expect(api({ role: 'entrance' }).events('all')).rejects.toMatchObject({ status: 403 });
  await expect(api({ offline: true }).events('all')).rejects.toMatchObject({ status: 0, message: MSG.network });
});
it('filters like the server', async () => {
  const a = api();
  expect((await a.events('all')).map((e) => e.id)).toEqual(['e-own-film', 'e-own-free', 'e-own-workshop', 'e-own-book', 'e-own-legacy']);
  expect((await a.events('draft')).every((e) => e.status === 'draft')).toBe(true);
  expect((await a.events('past')).map((e) => e.id)).toEqual(['e-own-past']);
});
it('creates a draft and rejects a stale version', async () => {
  const a = api();
  const created = await a.createEvent(INPUT);
  expect(created).toMatchObject({ status: 'draft', poster: null, sold: 0 });
  const saved = await a.updateEvent(created.id, { updatedAt: created.updatedAt, title: 'Другое' });
  expect(saved.updatedAt).not.toBe(created.updatedAt);
  await expect(a.updateEvent(created.id, { updatedAt: created.updatedAt, title: 'Третье' })).rejects.toMatchObject({ status: 409, message: MSG.conflict });
  await expect(a.createEvent({ ...INPUT, title: ' ' })).rejects.toMatchObject({ status: 422, field: 'title', message: MSG.title });
});
it('keeps saved ticket rows and switches off the dropped ones', async () => {
  const a = api();
  const e = await a.event('e-own-workshop');
  const saved = await a.updateEvent(e.id, { updatedAt: e.updatedAt, ticketTypes: [{ name: 'Новый', priceKopecks: 0, limit: 5 }] });
  expect(saved.ticketTypes.filter((t) => t.active).map((t) => t.name)).toEqual(['Новый']);
  expect(saved.ticketTypes.length).toBe(e.ticketTypes.length + 1);
});
it('publishes only with a poster and unpublishes only without sales', async () => {
  const a = api();
  await expect(a.publish('e-own-book')).rejects.toMatchObject({ status: 422, field: 'poster', message: MSG.needPoster });
  expect((await a.publish('e-own-workshop')).status).toBe('published');
  await expect(a.unpublish('e-own-film')).rejects.toMatchObject({ status: 409, message: MSG.hasOrders });
  expect((await a.unpublish('e-own-free')).status).toBe('draft');
});
it('checks the photo before taking it', async () => {
  const a = api();
  const big = new File(['x'], 'big.jpg', { type: 'image/jpeg' });
  Object.defineProperty(big, 'size', { value: 15 * 1024 * 1024 + 1 });
  await expect(a.uploadPoster('e-own-book', big, { x: 0.5, y: 0.5 })).rejects.toMatchObject({ status: 413, field: 'poster' });
  await expect(a.uploadPoster('e-own-book', new File(['x'], 'a.pdf', { type: 'application/pdf' }), { x: 0.5, y: 0.5 })).rejects.toMatchObject({ status: 415 });
  const before = await a.event('e-own-book');
  const after = await a.uploadPoster('e-own-book', new File(['x'], 'a.heic', { type: 'image/heic' }), { x: 0.3, y: 0.4 });
  expect(after.poster).toMatchObject({ focusX: 0.3, focusY: 0.4, width: 1080 });
  expect(after.updatedAt).not.toBe(before.updatedAt);
});
it('takes one upload at a time', async () => {
  const a = api({ latencyMs: 20 });
  const file = new File(['x'], 'a.jpg', { type: 'image/jpeg' });
  const first = a.uploadPoster('e-own-book', file, { x: 0.5, y: 0.5 });
  await expect(a.uploadPoster('e-own-book', file, { x: 0.5, y: 0.5 })).rejects.toMatchObject({ status: 429, message: MSG.uploadBusy });
  await first;
});
```

- [ ] **Step 2: Запустить — падает**

Run: `cd webapp && npx vitest run src/api/owner 2>&1 | grep -E "Tests |Error"`

- [ ] **Step 3: Реализовать фикстуры, мок, `DraftStore`, провайдер; дописать `render.tsx`, `main.tsx`, `vitest.setup.ts`**

`main.tsx`: `new MockOwnerApi({ role: ownerRoleFromUrl(), offline: scenarioFromUrl() === 'offline' })`.

- [ ] **Step 4: Запустить весь набор — проходит** (старые тесты не сломаны)

Run: `cd webapp && npx vitest run 2>&1 | grep -E "Tests "`

- [ ] **Step 5: Коммит** — `feat(webapp): mock owner API with server rules`

---

### Task 4: Пункт «Режим владельца» в Кабинете

**Files:**
- Create: `webapp/src/owner/useOwnerAccess.ts`
- Modify: `webapp/src/screens/Cabinet.tsx` (секция «Клуб» перед «Поддержкой»)
- Test: `webapp/src/screens/Cabinet.test.tsx`

**Interfaces:**
- Consumes: `useOwnerApi` (Task 3).
- Produces: `useOwnerAccess(): boolean` — `useQuery({ queryKey: ['owner', 'me'], retry: false, staleTime: Infinity })`; `true` только при `'manage_events'` в правах; ошибка любого рода → `false`.

- [ ] **Step 1: Написать падающие тесты**

```ts
it('shows owner mode to an owner and opens it', async () => {
  renderScreen(<Cabinet />, { at: '/me' });
  await userEvent.click(await screen.findByRole('button', { name: 'Режим владельца' }));
  expect(screen.getByTestId('where')).toHaveTextContent('/owner');
});
it.each(['guest', 'entrance'] as const)('hides owner mode from %s', async (role) => {
  renderScreen(<Cabinet />, { at: '/me', ownerApi: new MockOwnerApi({ role, latencyMs: 0 }) });
  await screen.findByRole('heading', { name: 'Поддержка' });
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Режим владельца' })).not.toBeInTheDocument());
});
it('hides owner mode when the check fails', async () => {
  renderScreen(<Cabinet />, { at: '/me', ownerApi: new MockOwnerApi({ offline: true, latencyMs: 0 }) });
  await screen.findByRole('heading', { name: 'Поддержка' });
  expect(screen.queryByRole('button', { name: 'Режим владельца' })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Запустить — падает**

Run: `cd webapp && npx vitest run src/screens/Cabinet.test.tsx 2>&1 | grep -E "Tests "`

- [ ] **Step 3: Реализовать** — `useOwnerAccess`; в `Cabinet` секция с заголовком «Клуб» (`h2`, как соседние) и `ListRow icon={CalendarCog} label="Режим владельца" onClick={() => navigate('/owner')}`, рендерится только при `true`.

- [ ] **Step 4: Запустить — проходит**

- [ ] **Step 5: Коммит** — `feat(webapp): owner mode entry in the cabinet`

---

### Task 5: «Мои вечера» — список

**Files:**
- Create: `webapp/src/owner/status.ts`, `webapp/src/screens/owner/OwnerRoutes.tsx`, `webapp/src/screens/owner/OwnerEvents.tsx` + `.module.css`, `webapp/src/screens/owner/OwnerLoadError.tsx`
- Modify: `webapp/src/App.tsx` (`<Route path="/owner/*" element={<OwnerRoutes />} />`), `webapp/src/ui/FilterChips.tsx` (необязательный проп `label`, по умолчанию `'Направления'` → `aria-label`)
- Test: `webapp/src/owner/status.test.ts`, `webapp/src/screens/owner/OwnerEvents.test.tsx`

**Interfaces:**
- Consumes: Task 1–3; `Pill`, `FilterChips`, `EmptyState`, `ErrorState`, `Skeleton`, `useMainButton`, `useBackButton`, `formatDateTime`.
- Produces:
  - `ownerStatus(item: { status: EventStatus; sold: number; capacity: number; poster: Poster | null }, past: boolean): { text: string; tone: PillTone }` — тона: опубликованный `success`, черновик без фото `warning`, остальное `muted`.
  - `OwnerRoutes()` — вложенные `<Routes>`: `index` → `OwnerEvents`, `*` → `<Navigate to="/owner" replace />` (Task 6 и 9 добавят свои пути).
  - `OwnerLoadError({ error, onRetry }: { error: unknown; onRetry(): void })` — 401/403 → `EmptyState` «Нет доступа» с текстом ошибки; 404 → `EmptyState` «Вечер не найден» и действие «К списку» (`/owner`); иначе `ErrorState` «Нет связи» + «Повторить».

- [ ] **Step 1: Написать падающие тесты**

`status.test.ts`:

```ts
expect(ownerStatus({ status: 'published', sold: 18, capacity: 30, poster: P }, false)).toEqual({ text: 'Опубликовано · 18/30', tone: 'success' });
expect(ownerStatus({ status: 'draft', sold: 0, capacity: 30, poster: P }, false).text).toBe('Черновик');
expect(ownerStatus({ status: 'draft', sold: 0, capacity: 30, poster: null }, false)).toEqual({ text: 'Черновик · нет фото', tone: 'warning' });
expect(ownerStatus({ status: 'completed', sold: 25, capacity: 30, poster: P }, true).text).toBe('Прошёл · 25/30');
expect(ownerStatus({ status: 'published', sold: 25, capacity: 30, poster: P }, true).text).toBe('Прошёл · 25/30');
expect(ownerStatus({ status: 'cancelled', sold: 0, capacity: 30, poster: P }, true).text).toBe('Отменён');
```

`OwnerEvents.test.tsx` (`renderScreen(<OwnerRoutes />, { at: '/owner', path: '/owner/*' })`):

```ts
it('lists live evenings with status pills', async () => {
  expect(await screen.findByText('Опубликовано · 18/30')).toBeInTheDocument();
  expect(screen.getByText('Черновик · нет фото')).toBeInTheDocument();
  expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toContain('/owner/events/e-own-film');
  expect(screen.getAllByTestId('thumb-empty').length).toBe(1);           // e-own-book
});
it('filters drafts and past evenings', async () => {
  await userEvent.click(await screen.findByRole('radio', { name: 'Прошли' }));
  expect(await screen.findByText('Прошёл · 25/30')).toBeInTheDocument();
  expect(screen.queryByText('Опубликовано · 18/30')).not.toBeInTheDocument();
  expect(screen.getByRole('radiogroup', { name: 'Фильтр вечеров' })).toBeInTheDocument();
});
it('shows a legacy poster without its size', async () => {
  const { container } = renderScreen(<OwnerRoutes />, { at: '/owner', path: '/owner/*' });
  await screen.findByText('Опубликовано · 18/30');
  expect(container.querySelector(`img[src="${LEGACY_POSTER_URL}"]`)).not.toBeNull();   // alt="" — не через getByRole
});
it('starts a new evening from the bottom bar', async () => {
  await userEvent.click(await screen.findByRole('button', { name: /Новый вечер/ }));
  expect(screen.getByTestId('where')).toHaveTextContent('/owner/events/new');
});
it('says when there are no drafts', async () => {
  // ownerApi с fixtures, где events отфильтрованы от черновиков; «Черновики» → текст «Черновиков нет»
});
it('turns a guest away', async () => { /* role guest: текст MSG.noAccess, кнопки «Новый вечер» нет */ });
```

- [ ] **Step 2: Запустить — падает**

Run: `cd webapp && npx vitest run src/owner src/screens/owner 2>&1 | grep -E "Tests "`

- [ ] **Step 3: Реализовать**

- Заголовок `h1` «Мои вечера»; `FilterChips label="Фильтр вечеров" items={[{id:'draft',title:'Черновики'},{id:'past',title:'Прошли'}]}`, `null` = «Все»; запрос `['owner', 'events', filter]`.
- Строка — `<Link to={/owner/events/:id}>`, `glass`: миниатюра 56×70 (4:5) — `<img>` с `object-fit: cover` и `object-position` из фокуса; без постера — блок `data-testid="thumb-empty"` с подписью «нет фото»; название, `formatDateTime(startsAt, CLUB_TIMEZONE)`, `Pill` из `ownerStatus(item, filter === 'past')`.
- Пусто: «Вечеров пока нет» / «Создай первый — это пара минут»; «Черновиков нет»; «Прошедших вечеров пока нет».
- `useMainButton({ text: '+ Новый вечер', enabled: true, progress: false, onClick: () => navigate('/owner/events/new') })`, пока нет ошибки доступа; `useBackButton(() => navigate('/me'))`.
- Ошибки загрузки — `OwnerLoadError`.

- [ ] **Step 4: Запустить — проходит**, затем весь набор

- [ ] **Step 5: Коммит** — `feat(webapp): owner evenings list`

---

### Task 6: Форма события — правка и сохранение

**Files:**
- Create: `webapp/src/screens/owner/OwnerEventForm.tsx` + `.module.css`, `webapp/src/screens/owner/TicketRowsEditor.tsx`
- Modify: `webapp/src/screens/owner/OwnerRoutes.tsx` (`events/:id` → `OwnerEventForm`; `:id === 'new'` — новый вечер)
- Test: `webapp/src/screens/owner/OwnerEventForm.test.tsx`

**Interfaces:**
- Consumes: Task 2 (`EventForm`, `formFromEvent`, `formToInput`, `emptyForm`, `newTicketRow`, `FORM_FIELDS`), Task 3 (`useOwnerApi`, `useOwnerDrafts`), `OwnerLoadError` (Task 5), `Toggle`, `Button`, `useMainButton`, `useBackButton`, `useClosingConfirmation`.
- Produces (для Task 7–9):
  - запросы `['owner', 'event', id]`, `['owner', 'directions']`; после любого изменения — `setQueryData` на событие и `invalidateQueries(['owner', 'events'])`;
  - в компоненте: `form: EventForm` (только ввод — без постера, статуса, `updatedAt`), `event: OwnerEvent | undefined` (сервер), `errors: Partial<Record<FormField, string>>`, `banner: { text: string; reload?: boolean } | null`, `save(): Promise<OwnerEvent | null>`, `showError(error: unknown): void`;
  - `TicketRowsEditor({ rows, error, onChange }: { rows: TicketRow[]; error?: string; onChange(rows: TicketRow[]): void })`.

Поведение:
- Начальная форма: `drafts.get(id)`, иначе `formFromEvent(event)` после загрузки, у `new` — `emptyForm()`. Любая правка → `setForm`, `drafts.set(id, form)`, `dirty = true`, ошибка этого поля стирается. `dirty` при входе = `drafts.get(id) !== undefined`. `useClosingConfirmation(dirty)`.
- Поля с видимыми подписями: «Название», «Направление» (`select`, пустой пункт «Выбери направление»), «Начало», «Конец» (`datetime-local`), `Toggle` «Место уточняется» (прячет «Адрес»), «Адрес», «Ссылка на карту», «Описание» (`textarea`), «Вместимость» (`inputMode="numeric"`), `Toggle` «Свой цвет афиши» + `input type="color"` «Цвет афиши», «Билеты». Ошибка поля — текст под ним, `aria-describedby`. Ошибки `field`, которых нет в `FORM_FIELDS`, и ошибки без поля — в `banner`.
- Строка билета: «Название билета N», «Цена билета N, ₽» (`inputMode="decimal"`), «Сколько билетов N»; несохранённая строка — кнопка «Убрать билет N», сохранённая — `Toggle` «В продаже». Кнопка «Добавить билет» → `newTicketRow()`.
- `useMainButton({ text: 'Сохранить', enabled: dirty && !saving, progress: saving, onClick: save })`.
- `save()`: повторный вызов, пока идёт первый, ничего не делает (`useRef`); `formToInput` с ошибкой → `errors`; новый → `createEvent`, затем `drafts.clear('new')` и `navigate('/owner/events/<id>', { replace: true })`; существующий → `updateEvent(id, { ...input, updatedAt: event.updatedAt })`; при успехе `drafts.clear(id)`, `dirty = false`, `form = formFromEvent(result)` (новые билеты получают id — иначе следующее сохранение их задвоит).
- `showError`: `status 0` → `banner MSG.network` (ввод не трогать); 409 → `banner { text: error.message, reload: true }` с кнопкой «Загрузить свежую версию» (стирает черновик, перезагружает событие, `form = formFromEvent(fresh)`); поле из `FORM_FIELDS` → под полем; иначе `banner error.message`.
- Загрузка — `Skeleton`; ошибки загрузки — `OwnerLoadError`. `useBackButton(() => navigate('/owner'))`.

- [ ] **Step 1: Написать падающие тесты** (`renderScreen(<OwnerRoutes />, { at: '/owner/events/<id>', path: '/owner/*' })`; даты — `fireEvent.change(input, { target: { value: '2026-10-20T19:00' } })`)

```ts
it('creates a draft and moves to its address', async () => {
  // at '/owner/events/new': заполнить название, направление, начало, конец, адрес, описание, вместимость
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
  await waitFor(() => expect(screen.getByTestId('where').textContent).toMatch(/^\/owner\/events\/(?!new)/));
});
it('saves only once on a double tap', async () => {
  const create = vi.spyOn(ownerApi, 'createEvent');
  // заполнить форму, затем два клика подряд без await между ними
  await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
});
it('shows the server message under its field', async () => {
  // e-own-book: очистить «Название», «Сохранить»
  expect(await screen.findByText(MSG.title)).toBeInTheDocument();
  expect(screen.getByLabelText('Название')).toHaveAccessibleDescription(MSG.title);
});
it('checks prices before sending', async () => {
  // «Цена билета 1, ₽» = «дорого» → текст MSG.ticketPrice, updateEvent не вызван
});
it('does not duplicate a new ticket on the second save', async () => {
  // e-own-book: «Добавить билет» «Студенческий» · 500 · 10, «Сохранить»; поменять название, «Сохранить»
  expect((await ownerApi.event('e-own-book')).ticketTypes.filter((t) => t.name === 'Студенческий').length).toBe(1);
});
it('keeps the input when the network is gone', async () => {
  // updateEvent → rejects new OwnerApiError(0, MSG.network); после «Сохранить»: текст MSG.network, в «Название» — введённое
});
it('offers the fresh version on a version conflict', async () => {
  // параллельно ownerApi.updateEvent(id, { updatedAt, title: 'Чужая правка' }); в форме поменять название, «Сохранить»
  expect(await screen.findByText(MSG.conflict)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Загрузить свежую версию' }));
  expect(await screen.findByDisplayValue('Чужая правка')).toBeInTheDocument();
});
it('hides the address when the venue is not decided', async () => {
  // Toggle «Место уточняется» → поля «Адрес» нет; после «Сохранить» event.address === null
});
```

- [ ] **Step 2: Запустить — падает**

Run: `cd webapp && npx vitest run src/screens/owner/OwnerEventForm.test.tsx 2>&1 | grep -E "Tests "`

- [ ] **Step 3: Реализовать `OwnerEventForm`, `TicketRowsEditor`, стили** — поля 48 px, фон `--surface-2`, радиус `--r-12`, подписи `--text-2`, ошибки `--error` 14 px; форма одной колонкой со скроллом, отступ снизу под нижнюю панель.

- [ ] **Step 4: Запустить — проходит**, затем весь набор и `npm run typecheck`

- [ ] **Step 5: Коммит** — `feat(webapp): owner event form with save`

---

### Task 7: Форма — публикация, снятие, только чтение

**Files:**
- Modify: `webapp/src/screens/owner/OwnerEventForm.tsx` + `.module.css`
- Test: `webapp/src/screens/owner/OwnerEventForm.test.tsx`

**Interfaces:**
- Consumes: `save`, `showError`, `form`, `event` (Task 6), `publishGaps` (Task 2), `ownerStatus` (Task 5), `publish`/`unpublish` (Task 1).

Поведение:
- Вверху формы — `Pill` из `ownerStatus(event, false)`.
- Черновик: кнопка «Опубликовать» под формой; `gaps = publishGaps(form, event?.poster != null)`; при непустом списке кнопка выключена, под ней «Чтобы опубликовать, добавь: <gaps через запятую>». Нажатие: если `dirty` — сначала `save()` (неудача — стоп), потом `publish(id)`; ошибки — `showError` (`poster`, `startsAt`, `ticketTypes` — под полями).
- Опубликованный: вместо неё «Снять с публикации» (`variant` вторичный) → `unpublish(id)`; 409 — `banner` с текстом сервера.
- `completed`/`cancelled`: поля в `<fieldset disabled>`, нижней панели нет (`useMainButton(null)`), кнопок публикации нет, `banner` «Вечер прошёл — править нельзя» / «Вечер отменён — править нельзя».

- [ ] **Step 1: Дописать падающие тесты**

```ts
it('says what publishing still needs', async () => {
  // e-own-book (нет фото)
  expect(await screen.findByRole('button', { name: 'Опубликовать' })).toBeDisabled();
  expect(screen.getByText('Чтобы опубликовать, добавь: фото')).toBeInTheDocument();
});
it('saves unsaved input, then publishes', async () => {
  // e-own-workshop: поменять название, «Опубликовать»
  expect(await screen.findByText(/^Опубликовано · /)).toBeInTheDocument();
  expect((await ownerApi.event('e-own-workshop')).title).toBe('Новое название');
});
it('unpublishes an evening without sales', async () => {
  // e-own-free: «Снять с публикации» → Pill «Черновик», появилась «Опубликовать»
});
it('explains why an evening with sales stays published', async () => {
  // e-own-film: «Снять с публикации» → текст MSG.hasOrders
});
it('opens a past evening read-only', async () => {
  // e-own-past
  expect(await screen.findByText('Вечер прошёл — править нельзя')).toBeInTheDocument();
  expect(screen.getByLabelText('Название')).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Запустить — новые падают**

Run: `cd webapp && npx vitest run src/screens/owner/OwnerEventForm.test.tsx 2>&1 | grep -E "Tests "`

- [ ] **Step 3: Реализовать**

- [ ] **Step 4: Запустить — проходит**, затем весь набор

- [ ] **Step 5: Коммит** — `feat(webapp): publish and unpublish from the owner form`

---

### Task 8: Шит постера

**Files:**
- Create: `webapp/src/screens/owner/PosterSheet.tsx` + `.module.css`
- Modify: `webapp/src/screens/owner/OwnerEventForm.tsx` (блок постера вверху формы)
- Test: `webapp/src/screens/owner/PosterSheet.test.tsx`, `webapp/src/screens/owner/OwnerEventForm.test.tsx`

**Interfaces:**
- Consumes: `uploadPoster`, `setPosterFocus` (Task 1), `MSG`, `useOwnerApi`.
- Produces:
  - `focusFromTap(clientX: number, clientY: number, rect: { left: number; top: number; width: number; height: number }): Focus | null` — доля 0–1 с обрезкой краёв, округление до 3 знаков; `null` при нулевой ширине или высоте.
  - `objectPosition(focus: Focus): string` — `${Math.round(x * 100)}% ${Math.round(y * 100)}%`.
  - `PosterSheet({ eventId, poster, onDone, onClose }: { eventId: string; poster: Poster | null; onDone(event: OwnerEvent): void; onClose(): void })`.

Поведение шита (оверлей поверх формы, `role="dialog"`, заголовок «Постер»):
- Скрытый `<input type="file" aria-label="Фото из галереи" accept="image/jpeg,image/png,image/webp,image/heic,image/heif">`; кнопка «Выбрать фото» (если постера нет) или «Другое фото».
- Файл больше лимита → сразу `MSG.photoTooBig`, без загрузки. Иначе `URL.createObjectURL(file)` (отозвать при смене и закрытии), фокус `{0.5, 0.5}`.
- «Тапни на главное»: фото целиком, точка-маркер; обёртка по размеру картинки (`tabIndex=0`, `aria-label="Точка фокуса"`); клик → `focusFromTap` по `getBoundingClientRect()` обёртки; стрелки клавиатуры сдвигают фокус на 0.05 с обрезкой 0–1 и округлением до 3 знаков.
- Три превью: `figure` с `aria-label` и видимой `figcaption` «Скоро» (4:5), «На этой неделе» (16:9), «Билет» (3:1); `img alt=""` с `object-fit: cover` и `objectPosition(focus)`.
- `onError` у картинки: превью и маркер скрыты, текст «Здесь фото не показать — загрузи его, а точку выберешь потом»; «Готово» доступно, фокус `{0.5, 0.5}`.
- «Готово»: новый файл → `uploadPoster`; иначе фокус сдвинут → `setPosterFocus`; иначе `onClose()`. Пока идёт — «Готово» с прогрессом. Успех → `onDone(result)`. Ошибка: `status 0` → `MSG.network`, иначе `error.message` сервера (413/415/422/429) в шите.
- «Закрыть» → `onClose()`.

В форме: блок постера — миниатюра 4:5 или заглушка «нет фото» и кнопка «Сменить фото» / «Добавить фото»; у `new` кнопка выключена, подпись «Фото добавишь после первого сохранения». Пока шит открыт: `useMainButton(null)`, кнопка «назад» Telegram закрывает шит. `onDone(result)` → только `setQueryData(['owner','event',id], result)` и `invalidateQueries(['owner','events'])` — ввод формы не трогается, следующий `save()` берёт свежий `event.updatedAt`. Ошибка `poster` из публикации показывается под блоком постера.

- [ ] **Step 1: Написать падающие тесты**

`PosterSheet.test.tsx` (рендер шита напрямую через `renderScreen`):

```ts
it('turns a tap into a focus point', () => {
  expect(focusFromTap(130, 240, { left: 100, top: 200, width: 100, height: 100 })).toEqual({ x: 0.3, y: 0.4 });
  expect(focusFromTap(90, 400, { left: 100, top: 200, width: 100, height: 100 })).toEqual({ x: 0, y: 1 });
  expect(focusFromTap(1, 1, { left: 0, top: 0, width: 0, height: 0 })).toBeNull();
});
it('moves all three crop previews to the tapped point', async () => {
  // upload файла; у «Точка фокуса» подменить getBoundingClientRect → {left:0, top:0, width:200, height:250}; fireEvent.click с clientX 60, clientY 100
  for (const name of ['Скоро', 'На этой неделе', 'Билет']) {
    expect(screen.getByRole('figure', { name }).querySelector('img')).toHaveStyle({ objectPosition: '30% 40%' });
  }
});
it('uploads the photo with its focus', async () => {
  // upload → ArrowRight ×2 → «Готово»: uploadPoster('e-own-book', file, { x: 0.6, y: 0.5 }), onDone вызван
});
it('only moves the focus of the current poster', async () => {
  // poster задан, ArrowDown → «Готово»: setPosterFocus вызван, uploadPoster — нет
});
it('refuses a file over 15 MB without uploading', async () => {
  // File с size 15 МБ + 1 → текст MSG.photoTooBig, uploadPoster не вызван
});
it.each([[415, MSG.notAPhoto], [422, MSG.photoSmall], [429, MSG.uploadBusy], [0, MSG.network]])('shows the %s answer in the sheet', async (status, text) => {
  // uploadPoster → rejects new OwnerApiError(status, status === 0 ? MSG.network : text, 'poster')
});
it('uploads a photo the browser cannot show at the centre', async () => {
  // fireEvent.error на img → текст «Здесь фото не показать…»; «Готово» → uploadPoster(…, { x: 0.5, y: 0.5 })
});
```

`OwnerEventForm.test.tsx`:

```ts
it('keeps unsaved input across a poster upload and saves without a conflict', async () => {
  // e-own-book: поменять «Название» на «Без конфликта»; «Добавить фото» → upload → «Готово»
  // «Сохранить» → нет текста MSG.conflict; ownerApi.event('e-own-book') → title «Без конфликта», poster не null
});
it('disables photos for an unsaved evening', async () => {
  // '/owner/events/new': кнопка «Добавить фото» выключена, подпись «Фото добавишь после первого сохранения»
});
```

- [ ] **Step 2: Запустить — падает**

Run: `cd webapp && npx vitest run src/screens/owner 2>&1 | grep -E "Tests "`

- [ ] **Step 3: Реализовать шит и блок постера**

- [ ] **Step 4: Запустить — проходит**, затем весь набор

- [ ] **Step 5: Коммит** — `feat(webapp): poster sheet with focus point and crop previews`

---

### Task 9: «Как видит гость»

**Files:**
- Create: `webapp/src/screens/owner/OwnerPreview.tsx`
- Modify: `webapp/src/screens/EventScreen.tsx` (проп `preview`), `webapp/src/screens/owner/OwnerRoutes.tsx` (`events/:id/preview`), `webapp/src/screens/owner/OwnerEventForm.tsx` (кнопка «Как видит гость»)
- Test: `webapp/src/screens/EventScreen.test.tsx`, `webapp/src/screens/owner/OwnerPreview.test.tsx`

**Interfaces:**
- Consumes: `toPreviewDetail`, `formFromEvent`, `emptyForm` (Task 2), `useOwnerDrafts` (Task 3), запрос `['owner','event',id]` (Task 6).
- Produces: `EventScreen({ preview }: { preview?: EventDetail })` — с `preview` запрос `['event', id]` выключен (`enabled: !preview`), данные — `preview`; над телом — `Pill tone="glass"` «Так увидит гость»; нижняя панель — та же надпись и сумма, что у гостя, но `enabled: false`; `pay()` ничего не делает. Без `preview` поведение прежнее.

`OwnerPreview`: `id` из пути; событие из `['owner','event',id]` (выключено для `new`); форма — `drafts.get(id) ?? (event ? formFromEvent(event) : emptyForm())`; рендер `<EventScreen preview={toPreviewDetail(form, event, Date.now())} />`. Кнопка в форме «Как видит гость» (вторичная, рядом с публикацией) → `drafts.set(id, form)` и `navigate('/owner/events/<id>/preview')`.

- [ ] **Step 1: Написать падающие тесты**

`EventScreen.test.tsx`:

```ts
it('shows a preview without loading or buying', async () => {
  const event = vi.spyOn(api, 'event');
  renderScreen(<EventScreen preview={DETAIL} />, { at: '/events/x', path: '/events/:id', api });
  expect(screen.getByText('Так увидит гость')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Купить/ })).toBeDisabled();
  expect(event).not.toHaveBeenCalled();
});
```

`OwnerPreview.test.tsx` (`renderScreen(<OwnerRoutes />, { at: '/owner/events/e-own-film', path: '/owner/*' })`):

```ts
it('shows unsaved input to the guest and keeps it on return', async () => {
  // поменять «Название» на «Новое имя»; «Как видит гость»
  expect(screen.getByTestId('where')).toHaveTextContent('/owner/events/e-own-film/preview');
  expect(await screen.findByRole('heading', { name: 'Новое имя' })).toBeInTheDocument();
  // «Назад» в шапке афиши
  expect(await screen.findByLabelText('Название')).toHaveValue('Новое имя');
  expect(screen.getByRole('button', { name: 'Сохранить' })).toBeEnabled();
});
it('previews a new evening before its first save', async () => {
  // '/owner/events/new': ввести название, «Как видит гость» → заголовок с ним, блок без фото (poster-fallback)
});
```

- [ ] **Step 2: Запустить — падает**

Run: `cd webapp && npx vitest run src/screens/EventScreen.test.tsx src/screens/owner 2>&1 | grep -E "Tests "`

- [ ] **Step 3: Реализовать**

- [ ] **Step 4: Запустить — проходит**, затем весь набор

- [ ] **Step 5: Коммит** — `feat(webapp): owner guest preview`

---

### Task 10: Итоговая проверка и STATUS

**Files:**
- Modify: `docs/superpowers/STATUS.md`

- [ ] **Step 1: Весь набор, типы, сборка**

Run: `cd webapp && npx vitest run 2>&1 | grep -E "Tests " && npm run build 2>&1 | tail -3`
Expected: все тесты зелёные (было 175 + новые), `tsc` без ошибок, сборка проходит; размер gzip записать.

- [ ] **Step 2: Ручная проверка в браузере**

`preview_start { name: "webapp" }` (порт 5174), `resize_window { preset: "mobile" }`. Вне Telegram `createTg()` работает без `window.Telegram`, нижняя панель рисуется страницей. Пройти: Кабинет → «Режим владельца» → фильтры → «+ Новый вечер» → заполнить → «Сохранить» → «Добавить фото» (любой JPEG ≥ 800×1000) → тап по фото, три превью → «Готово» → «Как видит гость» → назад → «Опубликовать» → «Снять с публикации»; `e-own-film` → «Снять с публикации» → 409; `/?owner=guest#/me` — пункта нет; `/?scenario=offline#/owner` — «Нет связи». Читать текстом (`read_page`/`get_page_text`); один скриншот формы и шита — владельцу.

- [ ] **Step 3: Обновить `STATUS.md`** — в «Сделано»: «Режим владельца — экраны на моках готовы», ветка, план, число тестов; в «Отложено»: HTTP-клиент `OwnerApi` (fetch + `parseOwnerError`, заголовок `Authorization: tma …`) и подмена мока в `main.tsx` — этап B; у строки списка нет `timezone` — даты в `Europe/Moscow`; мок владельца не связан с гостевым (опубликованное не появляется в афише мока); минорные замечания исполнителя — одной строкой.

- [ ] **Step 4: Коммит** — `docs: owner screens done, status`
