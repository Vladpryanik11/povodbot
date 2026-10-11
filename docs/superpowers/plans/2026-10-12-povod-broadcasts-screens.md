# Рассылки: экраны в Mini App на моках — план реализации (этап 2 из 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** раздел «Рассылки» в режиме владельца: список, старт, редактор с предпросмотром и живым счётчиком аудитории, отправка (сейчас / по времени / ночной переспрос), экраны идущей и отправленной рассылки со статистикой, шаблоны — всё на `MockCampaignApi`, повторяющем настоящий `/api/owner/campaigns*`.

**Architecture:** отдельный контракт `CampaignApi` (`webapp/src/api/campaigns/`) рядом с `OwnerApi`: типы поле в поле с `src/api/owner/campaign_schemas.py`, ошибки — тот же `OwnerApiError` плюс `QuietHoursError` с `suggestedAt`. Логика без React — в `webapp/src/owner/campaigns/` (разметка текста ↔ Telegram HTML, длина в UTF-16, подстановки, подписи статусов и причин). Экраны — `webapp/src/screens/owner/campaigns/`, по образцу «Мои вечера» (`OwnerEvents`, `OwnerEventForm`): `useMainButton`, `useBackButton`, `OwnerLoadError`, react-query, CSS-модули. Внутри Telegram HTTP-клиента рассылок ещё нет (этап 3) — там вкладка скрыта.

**Tech Stack:** Vite, React 18, TypeScript, react-router 6, @tanstack/react-query, vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-11-povod-broadcasts-design.md` (разделы 3, 5, 7, 9, 10); бэкенд-контракт — `src/api/owner/campaign_schemas.py`, `src/api/owner/campaigns.py`, тексты — `src/services/campaigns/{content,launch,owner,templates}.py`, причины — `src/workers/outbox.py`, `src/services/campaigns/stats.py`.

## Global Constraints

- Голос — на «ты», без «пожалуйста» и «!»; `src/copy.test.ts` зелёный.
- JSON — camelCase; ошибки `{message[, field]}`, `field` в camelCase (`body`, `buttons`, `image`, `eventId`, `audience`, `at`, `title`, `name`, `updatedAt`); тихие часы «сейчас» — `422 {field: "at", message, suggestedAt}`.
- Тексты сервера — дословно из бэкенда (`messages.ts`), кроме отказа старта из-за вечера: «Вечер больше не опубликован» (спека §10; бэкенд выровнять на этапе 3).
- Тело — Telegram HTML: только `<b>`, `<i>`, `<a href="https://…">`; `<`, `>`, `&` в тексте — `&lt;`, `&gt;`, `&amp;`.
- Длина — видимый текст в единицах UTF-16 (эмодзи = 2): ≤ 1024 с картинкой (`image.kind !== 'none'`), ≤ 4096 без.
- Кнопок ≤ 2; подпись 1–40 знаков после `trim`; ссылка `https://`, ≤ 2048; «Открыть вечер» — только при выбранном вечере (в шаблоне — всегда).
- Тихие часы 22:00–10:00 по `Europe/Moscow`; лимит 2 рассылки / 7 дней — показывается как `overLimit`.
- Счётчик аудитории — запрос через 300 мс после последнего изменения фильтра.
- Тесты — только итоговая строка: `cd webapp && npx vitest run 2>&1 | grep -E "Tests "`; типы — `npx tsc -b 2>&1 | tail -3`.
- Без реальных запросов к Telegram и Т‑Банку; без пуша.

## Review Focus

1. Владелец пишет `a < b && c > d` или буквально `<b>` — сохраняется экранированным, в пузыре видно как написано, сервер не отклоняет (тест в Task 2 и Task 7).
2. Текст на грани лимита с эмодзи: 1023 знака + 😀 с картинкой — счётчик 1025/1024, ошибка до сохранения (тест в Task 2 и Task 6).
3. Шаблон с `{event}` открыт без вечера — подсказка под текстом, «Отправить…» недоступна, пока не выбран вечер (тест в Task 7).
4. Двойной тап «Отправить N гостям» — один вызов `send` (тест в Task 8).
5. «Сейчас» в 23:00 МСК — переспрос «Отправить в 10:00?»; «Да» планирует на `suggestedAt`, «Нет» оставляет черновик (тест в Task 8).

---

## Файлы

```
webapp/src/api/campaigns/
  types.ts               формы API (camelCase)
  messages.ts            CMSG — тексты сервера дословно + свои
  CampaignApi.ts         интерфейс, QuietHoursError, parseCampaignError
  campaignFixtures.ts    рассылки во всех статусах, статистика, 5 готовых + 1 свой шаблон
  MockCampaignApi.ts     мок с проверками как на сервере
  CampaignApiProvider.tsx  провайдер + useCampaignApi(): CampaignApi | null
webapp/src/owner/campaigns/
  text.ts                разметка ↔ HTML, длина, подстановки
  labels.ts              статус-пилюля, причины неудач, подписи аудитории
  useCampaignAccess.ts   право manage_campaigns + наличие клиента
  useAudienceCount.ts    счётчик с задержкой 300 мс
webapp/src/screens/owner/
  OwnerTabs.tsx          «Вечера | Рассылки» (+ OwnerEvents, OwnerRoutes, Cabinet)
  campaigns/
    CampaignList.tsx     список с фильтрами
    CampaignStart.tsx    готовый / свой шаблон / чистый лист
    CampaignScreen.tsx   маршрут :id → редактор или просмотр по статусу
    CampaignEditor.tsx   редактор (new / draft / scheduled)
    SendFlow.tsx         «Отправить…»: сейчас / по времени, ночь, подтверждение
    CampaignView.tsx     идущая / отправленная / остановленная / отменённая + статистика
    Templates.tsx        шаблоны: готовые и свои
    TemplateEditor.tsx   свой шаблон
    parts/TextEditor.tsx, ButtonsEditor.tsx, AudienceEditor.tsx, MessageBubble.tsx
    campaigns.module.css общий стиль раздела
```

`renderScreen` (`src/test/render.tsx`) получает опцию `campaignApi` и оборачивает в `CampaignApiProvider`.

---

### Task 1: Контракт `CampaignApi`

**Files:** Create `webapp/src/api/campaigns/{types.ts,messages.ts,CampaignApi.ts,CampaignApi.test.ts}`

**Interfaces — Produces:**
- `types.ts`: `CampaignStatus = 'draft'|'scheduled'|'running'|'completed'|'cancelled'|'stopped'`; `CampaignFilter = 'draft'|'scheduled'|'sent'`; `ImageKind = 'event'|'upload'|'none'`; `CampaignImage {kind; ref?: string|null; url?: string|null}`; `CampaignButton = {kind:'event'; label} | {kind:'url'; label; url}`; `AudienceRelation = 'going'|'liked'|'liked_not_bought'|'attended'`; `AudienceFilter {event: {id; relation}|null; directionId: string|null; purchases: 'any'|'bought'|'never'}`; `Campaign {id; title; body; image: CampaignImage; buttons; eventId: string|null; audience: AudienceFilter; status; scheduledAt; startedAt; finishedAt; recipientCount: number|null; cancelReason: string|null; updatedAt}`; `CampaignListItem = Campaign & {delivered; clicked}`; `CampaignInput {title?; body?; image?: {kind:'event'|'none'}; buttons?; eventId?: string|null; audience?}`; `CampaignPatch = CampaignInput & {updatedAt}`; `AudienceCount {count; overLimit}`; `CampaignStats {recipients; delivered; failed; failedReasons: Record<string, number>; skippedLimit; clicked; anonymousClicks; bought: number|null}`; `CampaignTemplate {id; name; body; imageKind: ImageKind; buttons; isBuiltin; updatedAt}`; `TemplateInput {name?; body?; imageKind?; buttons?}`.
- `CampaignApi` (комментарий-контракт с методом и путём, как в `OwnerApi.ts`): `campaigns(filter)`, `campaign(id)`, `createCampaign(input)`, `updateCampaign(id, patch)`, `uploadImage(id, file)` (multipart `file`), `clearImage(id)`, `sendTest(id): Promise<void>`, `send(id, at: string|null)`, `cancel(id)`, `stop(id)`, `duplicate(id)`, `stats(id)`, `audienceCount(filter)`, `templates()`, `createTemplate(input)`, `updateTemplate(id, input)`, `deleteTemplate(id): Promise<void>`, `saveAsTemplate(campaignId, name)`.
- `class QuietHoursError extends OwnerApiError { readonly suggestedAt: string }` (status 422, field `'at'`).
- `parseCampaignError(status, body): OwnerApiError` — `QuietHoursError`, если в теле есть строка `suggestedAt`; иначе `parseOwnerError`.
- `CMSG` — дословно: `emptyBody` «Напиши текст рассылки», `tooLong` «Слишком длинный текст: с картинкой до 1024 знаков, без неё до 4096», `onlyTags` «Можно только жирный, курсив и ссылку», `httpsOnly` «Ссылка должна начинаться с https://», `tooManyButtons` «Не больше двух кнопок», `pickEvent` «Сначала выбери вечер», `badLabel` «Подпись кнопки — от 1 до 40 знаков», `badImage` «Картинка не загрузилась. Попробуй ещё раз», `past` «Это время уже прошло», `quietAt` «С 22:00 до 10:00 не отправляем. Выбери другое время», `night` «Ночью не отправляем. Отправить в 10:00?», `noRecipients` «Получателей нет», `cancelOnlyScheduled`, `stopOnlyRunning`, `emptyTitle` «Напиши название рассылки», `eventNotPublished` «Вечер не опубликован» (правка), `eventGone` «Вечер больше не опубликован» (старт, спека §10), `stale` «Рассылку уже изменили в другой вкладке. Обнови страницу», `locked` «Эту рассылку уже не изменить», `emptyName` «Назови шаблон», `builtinLocked` «Готовый шаблон не меняется. Скопируй его в свои», `campaignNotFound`, `templateNotFound`, `botBlocked` «Бот не может тебе написать. Открой бота и нажми «Старт»», `telegramBusy`, `notConfigured` «Кнопки пока не настроены. Напиши разработчику».

- [ ] **Step 1: тест** `CampaignApi.test.ts`: `parseCampaignError(422, {field:'at', message: CMSG.night, suggestedAt:'2026-10-11T07:00:00+00:00'})` → `instanceof QuietHoursError`, `.field === 'at'`, `.suggestedAt` как в теле; `parseCampaignError(409, {message: CMSG.stale})` → `OwnerApiError` без `suggestedAt`; `{detail:'Forbidden'}` при 403 → `MSG.noAccess`.
- [ ] **Step 2:** запуск — FAIL (нет модуля). **Step 3:** реализовать. **Step 4:** PASS, `tsc` чистый.
- [ ] **Step 5:** commit `feat(webapp): campaign API contract and error parsing`.

### Task 2: Текст — разметка ↔ Telegram HTML

**Files:** Create `webapp/src/owner/campaigns/text.ts`, `text.test.ts`

Редактор показывает владельцу разметку, как в самом Telegram: `**жирный**`, `__курсив__`, `[подпись](https://…)`. В API уходит HTML.

**Interfaces — Produces:**
- `markupToHtml(markup: string): string` — экранирует `&`, `<`, `>` (и `"` в `href`), превращает маркеры в теги. Ссылка — `\[([^\]\n]+)\]\((https:\/\/[^\s)"<>]+)\)`, подпись ссылки — простой текст. `**`/`__` — переключатели со стеком: закрывает только верхний открытый; маркер, закрывающий не верхний, и незакрытые маркеры остаются буквальным текстом.
- `htmlToMarkup(html: string): string` — обратное для наших тегов и сущностей (`&lt; &gt; &amp; &quot;` и числовые).
- `visibleText(html: string): string`; `telegramLength(html: string): number` = `visibleText(html).length` (JS считает в UTF-16).
- `CAPTION_LIMIT = 1024`, `MESSAGE_LIMIT = 4096`, `textLimit(imageKind: ImageKind): number`.
- `PLACEHOLDERS = ['{event}', '{date}']`; `hasPlaceholders(text: string): boolean`; `fillPlaceholders(markup, event: {title: string; startsAt: string}): string` — `{event}` → название, `{date}` → «18 октября» (`Intl` `ru-RU`, `day:'numeric', month:'long'`, `Europe/Moscow`).

- [ ] **Step 1: тесты**:
  - `markupToHtml('a < b && c > d')` → `'a &lt; b &amp;&amp; c &gt; d'`; `markupToHtml('<b>x</b>')` → `'&lt;b&gt;x&lt;/b&gt;'`.
  - `markupToHtml('**Кино** и __вино__ [тут](https://povod.club/a?b=1&c=2)')` → `'<b>Кино</b> и <i>вино</i> <a href="https://povod.club/a?b=1&amp;c=2">тут</a>'`.
  - пересечение: `markupToHtml('**a __b** c__')` → `'**a <i>b** c</i>'` (второй `**` закрывает не верхний — литерал, первый остался незакрытым — литерал); `markupToHtml('**жирный')` → `'**жирный'`; `markupToHtml('[x](http://a.ru)')` → `'[x](http://a.ru)'`.
  - круг: для каждого `h` из `['<b>Кино</b> &amp; <i>вино</i>', '<a href="https://a.ru/?x=1&amp;y=2">тут</a>', 'a &lt; b']` — `markupToHtml(htmlToMarkup(h)) === h`.
  - `telegramLength('<b>Кино</b> &amp; 😀')` → `8`; `telegramLength('a'.repeat(1023) + '😀')` → `1025`, больше `textLimit('event')`, меньше `textLimit('none')`.
  - `fillPlaceholders('{date} у нас «{event}»', {title:'Кино на крыше', startsAt:'2026-10-18T16:00:00Z'})` → `'18 октября у нас «Кино на крыше»'`; `hasPlaceholders('Завтра «{event}»')` → `true`.
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat(webapp): campaign text markup, Telegram HTML and UTF-16 length`.

### Task 3: `MockCampaignApi`, фикстуры, провайдер

**Files:** Create `webapp/src/api/campaigns/{campaignFixtures.ts,MockCampaignApi.ts,MockCampaignApi.test.ts,CampaignApiProvider.tsx}`; Modify `webapp/src/test/render.tsx`

**Interfaces:**
- Consumes: Task 1 (типы, `CMSG`, ошибки), Task 2 (`telegramLength`, `textLimit`), `buildOwnerFixtures`, `ownerRoleFromUrl`, `scenarioFromUrl`, `MAX_PHOTO_BYTES`, `PHOTO_TYPES`, `MSG`.
- Produces: `new MockCampaignApi({role?, now?, latencyMs?, offline?, fixtures?, telegramLinked?})`; `buildCampaignFixtures(now): {campaigns: Campaign[]; stats: Record<string, CampaignStats>; templates: CampaignTemplate[]; events: CampaignEventRef[]}`, где `CampaignEventRef {id; title; startsAt; status; directionId; sold; posterUrl: string|null}` — из `buildOwnerFixtures(now).events`; `CampaignApiProvider({api?, children})`, `useCampaignApi(): CampaignApi | null` — без `api` вне Telegram мок (`?owner=`, `?scenario=offline`), внутри Telegram `null`.
- `renderScreen(..., {campaignApi?})` — по умолчанию `new MockCampaignApi({latencyMs: 0, now: () => T0})`.

Фикстуры (id стабильные, тесты на них опираются):
- `c-draft` «Анонс «Амели»» — `draft`, вечер `e-own-film`, `**`-жирный в тексте, картинка `event`, кнопка «Открыть вечер», аудитория `{event:{id:'e-own-film', relation:'liked'}}`.
- `c-gone` «Мастерская» — `draft`, вечер `e-own-workshop` (он черновик), текст и аудитория валидны.
- `c-scheduled` — `scheduled` на T0 + 2 дня 12:00 МСК, `recipientCount: null`.
- `c-running` — `running`, `recipientCount: 214`; `c-done` — `completed`, статистика `{recipients:214, delivered:205, failed:6, failedReasons:{bot_blocked:3, recipient_not_eligible:1, 'Telegram server says - Bad Request: chat not found':2}, skippedLimit:3, clicked:37, anonymousClicks:4, bought:5}`; `c-stopped` — `stopped`; `c-cancelled` — `cancelled`, `cancelReason: 'event_unpublished'`.
- Шаблоны: 5 готовых дословно из `migrations/versions/0010_broadcasts.py` (`isBuiltin: true`, порядок по имени) + свой `t-own` «Мой анонс».

Правила мока (как в сервисах бэкенда):
- `guest`/`entrance` → 403 `MSG.noAccess`; `offline` → `OwnerApiError(0, MSG.network)`; задержка `latencyMs` (по умолчанию 300).
- `campaigns(filter)`: `draft` — по `updatedAt` убыв.; `scheduled` — по `scheduledAt`; `sent` — `running|completed|stopped|cancelled` по `startedAt ?? updatedAt` убыв.; `delivered`/`clicked` из статистики (иначе 0).
- `createCampaign`/`updateCampaign` — проверки `_apply`: пустое название → `title`/`emptyTitle`; `eventId` не опубликованного вечера → `eventId`/`eventNotPublished`; `image.kind==='event'` без вечера → `image`/`pickEvent`; кнопки — `tooManyButtons`/`badLabel`/`pickEvent`/`httpsOnly` с полем `buttons`; непустое тело — `onlyTags` при недопустимом HTML (достаточно: голые `<>&` вне тегов, теги кроме `b,i,a href="https://…"`), `tooLong` по `textLimit`; правка не `draft|scheduled` → 422 `locked`; `updatedAt` не совпал → 409 `stale`; каждое изменение — новый `updatedAt` (как `stamp()` в `MockOwnerApi`).
- `uploadImage`: тип/размер как у постера (`MSG.notAPhoto`, `MSG.photoTooBig`, поле `image`), тело перепроверяется на 1024 → `body`/`tooLong`; результат `image {kind:'upload', ref:'campaigns/mock-<n>', url: URL.createObjectURL(file)}`.
- `audienceCount(f)`: пусто → `{count:214, overLimit:9}`; `event.relation` `going|attended` → `sold` вечера, `liked` → 37, `liked_not_bought` → 19; `directionId` → `round(n/2)`; `bought` → `round(n*0.6)`, `never` → `n - round(n*0.6)`; `overLimit = n >= 100 ? 9 : 0`.
- `send(id, at)`: не `draft` → 422 `locked`; пустое тело → `body`/`emptyBody`; вечер не опубликован → `eventId`/`eventGone`; 0 получателей → `audience`/`noRecipients`; `at === null` ночью → `QuietHoursError(night, suggestedAt = ближайшие 10:00 МСК в ISO)`; `at === null` днём → `running`, `startedAt`, `recipientCount`, статистика с нулями; `at <= now` → `at`/`past`; `at` в тихие часы → `at`/`quietAt`; иначе `scheduled`.
- `sendTest`: `telegramLinked === false` → 422 `botBlocked`; кнопка `event` без вечера → 422 `pickEvent`.
- `cancel` (только `scheduled`, иначе 422 `cancelOnlyScheduled`) → `cancelled`; `stop` (только `running`, иначе `stopOnlyRunning`) → `stopped`; `duplicate` → черновик «<название> (копия)»; `stats` → из фикстур.
- Шаблоны: готовые первыми, свои — новые первыми; правка/удаление готового → 403 `builtinLocked`; пустое имя → `name`/`emptyName`; `saveAsTemplate` копирует `body`, `image.kind`, `buttons`.

- [ ] **Step 1: тесты** `MockCampaignApi.test.ts` (по одному на правило): фильтры списка и порядок; 409 при старом `updatedAt`; `eventGone` при `send('c-gone', null)`; ночь (`now = 2026-10-10T20:00:00Z`) → `QuietHoursError`, `suggestedAt === '2026-10-11T07:00:00.000Z'`; `at` = 22:00 МСК → поле `at`, `quietAt`; 21:59 МСК → `scheduled`; `audienceCount` для пустого, `e-own-film/going` (18), `e-own-free/going` (0); `send` при 0 → `noRecipients`; готовый шаблон не правится (403); тело `'a < b'` → 422 `onlyTags`; `sendTest` без Telegram → `botBlocked`.
- [ ] **Step 2:** FAIL. **Step 3:** реализовать мок, фикстуры, провайдер, опцию в `renderScreen`. **Step 4:** PASS, все прежние тесты зелёные.
- [ ] **Step 5:** commit `feat(webapp): MockCampaignApi mirroring /api/owner/campaigns`.

### Task 4: Подписи — статус, причины, аудитория

**Files:** Create `webapp/src/owner/campaigns/labels.ts`, `labels.test.ts`

**Interfaces — Produces:**
- `campaignStatus(c: Pick<Campaign,'status'|'scheduledAt'|'cancelReason'>): {text; tone: PillTone}` — `draft` «Черновик»/muted; `scheduled` «Запланирована · <formatDateTime МСК>»/accent; `running` «Идёт отправка»/warning; `completed` «Отправлена»/success; `stopped` «Остановлена»/muted; `cancelled` «Отменена»/muted, при `event_unpublished` — «Отменена · вечер снят с публикации».
- `failureLabel(reason: string): string` — `bot_blocked` → «Заблокировали бота»; `recipient_not_eligible` → «Отказались от рассылок или заблокировали бота»; `unknown` → «Причина неизвестна»; текст Telegram по подстроке (без учёта регистра): `chat not found` → «Чат с гостем не найден»; `user is deactivated` → «Аккаунт гостя удалён»; `wrong file|photo|image|http url content|wrong type of the web page` → «Telegram не принял картинку»; `can't parse entities` → «Telegram не разобрал оформление текста»; `too many requests|retry after` → «Telegram попросил подождать»; `timeout|timed out|connect` → «Не было связи с Telegram»; остальное → «Ошибка Telegram».
- `groupFailures(reasons: Record<string, number>): {label: string; count: number}[]` — сумма по одинаковым подписям, по убыванию.
- `RELATION_LABEL: Record<AudienceRelation,string>` — «Идут на вечер», «Лайкнули», «Лайкнули, но не купили», «Были на вечере»; `PURCHASE_LABEL` — `any` «Неважно», `bought` «Покупали», `never` «Ни разу не покупали»; `guestsLabel(n)` — «214 гостей» (через `plural`).

- [ ] **Step 1: тесты**: каждая ветка `failureLabel` (в т.ч. `'Telegram server says - Bad Request: chat not found'`), `groupFailures({bot_blocked:3, 'Bad Request: chat not found':2, 'Telegram server says - Bad Request: chat not found':2, recipient_not_eligible:1})` → `[{«Чат с гостем не найден», 4}, {«Заблокировали бота», 3}, {«Отказались…», 1}]`; `campaignStatus` для `cancelled`+`event_unpublished`; `guestsLabel(1|3|214)`.
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat(webapp): campaign status, failure reasons and audience labels`.

### Task 5: Доступ, вкладки, маршруты, список

**Files:** Create `webapp/src/owner/campaigns/useCampaignAccess.ts`, `webapp/src/screens/owner/OwnerTabs.tsx`, `webapp/src/screens/owner/campaigns/{CampaignList.tsx,CampaignList.test.tsx,campaigns.module.css}`; Modify `OwnerRoutes.tsx`, `OwnerEvents.tsx`, `screens/Cabinet.tsx`, `main.tsx`/`App.tsx` (провайдер), `ui/FilterChips.tsx` (опция `allTitle: string | null`, по умолчанию «Все»).

**Interfaces — Produces:**
- `useCampaignAccess(): boolean` — `useCampaignApi() !== null` и `me.permissions` содержит `manage_campaigns` (запрос `['owner','me']`, как `useOwnerAccess`).
- `OwnerTabs({current: 'events'|'campaigns'})` — две ссылки «Вечера» `/owner` и «Рассылки» `/owner/campaigns`, `aria-current="page"` у текущей; рендерится, только если есть оба права.
- Маршруты под `/owner`: `campaigns` → `CampaignList`; `campaigns/start` → `CampaignStart`; `campaigns/templates` → `Templates`; `campaigns/templates/:id` → `TemplateEditor`; `campaigns/:id` → `CampaignScreen` (Task 7/9 заполняют; до них — заглушки).
- Кабинет: строка «Режим владельца» при `manage_events` или `manage_campaigns`; ведёт на `/owner`, а при одном `manage_campaigns` — на `/owner/campaigns`.
- `CampaignList`: заголовок «Рассылки», `OwnerTabs`, фильтр «Черновики / Запланированы / Отправлены» (`FilterChips` без «Все», по умолчанию черновики), ссылка «Шаблоны», карточки → `/owner/campaigns/:id`: название; строка даты — `scheduledAt`/`startedAt` (`formatDateTime` МСК) или «Черновик»; `recipientCount` → «214 гостей»; после старта — «доставлено 209 · нажали 37»; пилюля `campaignStatus`. Пусто: «Черновиков нет», «Запланированных нет», «Отправленных пока нет». `useMainButton` «+ Новая рассылка» → `/owner/campaigns/start`; «назад» → `/owner`. Ошибки — `OwnerLoadError`.

- [ ] **Step 1: тесты** `CampaignList.test.tsx`: черновики по умолчанию (видно «Анонс «Амели»», нет `c-done`); «Отправлены» → «доставлено 205 · нажали 37», «214 гостей», «Отменена · вечер снят с публикации»; кнопка «Новая рассылка» ведёт на `/owner/campaigns/start`; `?owner=entrance`-мок → «Нет доступа». В `OwnerEvents.test.tsx`: вкладка «Рассылки» есть у владельца и ведёт на `/owner/campaigns`; при `campaignApi = null` вкладок нет. Кабинет: при одном `manage_campaigns` строка ведёт на `/owner/campaigns` (тест в существующем `Cabinet` тесте, если есть, иначе в `CampaignList.test.tsx`).
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS + `tsc`.
- [ ] **Step 5:** commit `feat(webapp): broadcasts tab, routes and campaign list`.

### Task 6: Части редактора — текст, кнопки, аудитория, пузырь

**Files:** Create `webapp/src/screens/owner/campaigns/parts/{TextEditor.tsx,ButtonsEditor.tsx,AudienceEditor.tsx,MessageBubble.tsx,parts.test.tsx}`, `webapp/src/owner/campaigns/useAudienceCount.ts`

**Interfaces — Produces:**
- `TextEditor({id, value, onChange, limit, error?})` — `value` в разметке; панель «Ж» (`aria-label="Жирный"`), «К» («Курсив»), «Ссылка»: оборачивает выделение `**…**` / `__…__`; «Ссылка» открывает строку с полем адреса и «Вставить» → `[выделение или «ссылка»](url)`; не `https://` — ошибка `CMSG.httpsOnly` в строке. Под полем — счётчик `«N / limit»` по `telegramLength(markupToHtml(value))`, сверх лимита — красный и `CMSG.tooLong`.
- `ButtonsEditor({buttons, onChange, hasEvent, error?})` — до 2 строк; вид «Открыть вечер» (недоступен без вечера) / «Ссылка» (подпись + адрес); «+ Кнопка» скрыта при двух; «Убрать».
- `useAudienceCount(filter): {count: number|null; overLimit: number; pending: boolean}` — вызывает `api.audienceCount` через 300 мс после последнего изменения (сравнение по `JSON.stringify`), устаревшие ответы игнорирует.
- `AudienceEditor({value, onChange, events, directions})` — переключатель «Связь с вечером» → выбор вечера (опубликованные и прошедшие) и отношения (`RELATION_LABEL`); «Направление» — select «Любое» + направления; «Покупки» — `PURCHASE_LABEL`. Ниже — «Получат N» (`aria-live="polite"`), при `overLimit > 0` — «Ещё M уже получили 2 рассылки за неделю — им не придёт».
- `MessageBubble({html, imageUrl, buttons})` — пузырь Telegram: картинка сверху, `dangerouslySetInnerHTML` только для вывода `markupToHtml`, кнопки кнопками-подписями под пузырём; пустой текст — «Здесь будет текст».

- [ ] **Step 1: тесты** `parts.test.tsx`: выделение «Кино» + «Жирный» → `**Кино**`; «Ссылка» с `http://a.ru` → `httpsOnly`, с `https://a.ru` → `[Кино](https://a.ru)`; счётчик с картинкой для `'a'.repeat(1023)+'😀'` → «1025 / 1024» и `tooLong`; третьей кнопки добавить нельзя; «Открыть вечер» недоступна без вечера; `useAudienceCount` на фейковых таймерах: три быстрых изменения → один вызов `audienceCount` через 300 мс; `MessageBubble` с разметкой `'<script>x</script> **ok**'` → в DOM нет `script`, есть `strong`/`b` с «ok».
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat(webapp): campaign text, buttons, audience editors and message bubble`.

### Task 7: Редактор рассылки

**Files:** Create `webapp/src/screens/owner/campaigns/{CampaignScreen.tsx,CampaignEditor.tsx,CampaignEditor.test.tsx}`, `webapp/src/owner/campaigns/form.ts` (+ тест в `CampaignEditor.test.tsx` или `form.test.ts`)

**Interfaces:**
- Consumes: Tasks 1–6; `useOwnerApi().events('all'|'past')` и `.directions()` для выбора вечера и направлений.
- Produces: `CampaignForm {title; markup; eventId: string|null; imageKind: ImageKind; buttons: CampaignButton[]; audience: AudienceFilter}`; `formFromCampaign(c)`, `formFromTemplate(t|null)`, `formToInput(form): CampaignInput` (тело — `markupToHtml`, `image` без `upload`: загруженная картинка меняется только загрузкой), `formErrors(form): Partial<Record<'title'|'body'|'image'|'buttons', string>>` — те же проверки и тексты, что у сервера (`emptyTitle`, `tooLong`, `pickEvent`, `badLabel`, `httpsOnly`); `CampaignScreen` — по `:id`: `new` или `draft|scheduled` → `CampaignEditor`, остальное → `CampaignView` (Task 9).

Поведение:
- `/owner/campaigns/new?template=<id>` — форма из шаблона (`htmlToMarkup`, `imageKind`, кнопки), без параметра — чистый лист; первый «Сохранить черновик» создаёт и заменяет адрес на `/owner/campaigns/<id>` (`replace`).
- Секции сверху вниз: Название; Вечер (select «Без вечера» + опубликованные будущие); Текст (`TextEditor`); Картинка (радио «Афиша вечера» — без вечера недоступна, «Своя» — файл, «Без картинки»); Кнопки; Аудитория; Предпросмотр (`MessageBubble`, картинка — афиша выбранного вечера / загруженная).
- Выбор вечера: в разметке `{event}`/`{date}` заменяются (`fillPlaceholders`); если картинка была «Без картинки» и шаблон просил афишу — ставится «Афиша вечера»; если кнопок нет — добавляется «Открыть вечер»; аудитория не меняется.
- Остались плейсхолдеры → под текстом «Выбери вечер — {event} и {date} заменятся сами», «Отправить…» недоступна.
- «Своя» картинка: у новой рассылки сначала тихо сохраняется черновик, потом `uploadImage`; ответ даёт свежий `updatedAt`.
- Действия внизу страницы: «Сохранить черновик», «Отправить себе» (успех — «Отправили тебе в Telegram»), «Сохранить как шаблон» (имя = название; успех — «Шаблон сохранён»), у `scheduled` — «Отменить рассылку» с `Dialog`. Каждое действие сначала сохраняет несохранённое. `useMainButton`: «Отправить…» (Task 8; для `scheduled` — не показывается), недоступна при ошибках формы, плейсхолдерах или `count === 0`; «Получат 0» видно рядом.
- Ошибки сервера с `field` — под полем (`eventId` → под «Вечер», `audience` → под аудиторией, `at` → в SendFlow); 409 — баннер с «Загрузить свежую версию», как в `OwnerEventForm`. `useClosingConfirmation(dirty)`; «назад» → `/owner/campaigns`.

- [ ] **Step 1: тесты** `CampaignEditor.test.tsx`: новый из готового «Новый вечер в афише» → подсказка о плейсхолдерах и «Отправить…» недоступна; выбор «Кино на крыше: «Амели»» → текст «18 октября у нас «Кино на крыше: «Амели»»…» (дата — по фикстуре), «Афиша вечера» выбрана, кнопка «Открыть вечер»; ввод `a < b & c` + «Сохранить черновик» → `api.campaign(newId).body === 'a &lt; b &amp; c'`, адрес `/owner/campaigns/<id>`; правка `c-draft` после чужой правки (через `api.updateCampaign` в тесте) → баннер `CMSG.stale`; «Отправить себе» при `telegramLinked: false` → `CMSG.botBlocked`; `c-scheduled` → есть «Отменить рассылку», после подтверждения статус «Отменена»; аудитория `e-own-free/going` → «Получат 0» и «Отправить…» недоступна.
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS + `tsc`.
- [ ] **Step 5:** commit `feat(webapp): campaign editor with preview, placeholders and audience`.

### Task 8: Отправка — сейчас, по времени, ночь, подтверждение

**Files:** Create `webapp/src/screens/owner/campaigns/{SendFlow.tsx,SendFlow.test.tsx}`; Modify `CampaignEditor.tsx`

**Interfaces:**
- Consumes: `CampaignApi.send`, `QuietHoursError`, `guestsLabel`, счётчик из Task 6.
- Produces: `SendFlow({campaignId, recipients, onSent(c: Campaign), onClose})` — шит: «Сейчас» / «Запланировать» (поля даты и времени, по МСК, перевод в ISO с `+03:00`), затем `Dialog` «Отправить 214 гостям?» (для плана — «Запланировать на 18 окт, 12:00 для 214 гостей?»). Во время запроса кнопка подтверждения недоступна и показывает прогресс. `QuietHoursError` → второй `Dialog` с `CMSG.night`: «Да» → `send(id, suggestedAt)`, «Нет» — закрыть, черновик остаётся. Ошибка с полем `at` — под полем времени; с другим полем — `onClose` и показ в редакторе. Успех: «Сейчас» → переход на `/owner/campaigns/<id>` (экран идущей); план → в список «Запланированы».

- [ ] **Step 1: тесты** (`now` = T0 = 12:00 МСК): `c-draft` (аудитория `e-own-film/liked` = 37) → «Сейчас» → «Отправить 37 гостям?» → двойной клик по подтверждению → `send` вызван один раз (шпион на `api.send`), адрес — экран рассылки, «Идёт отправка»; мок с `now = 2026-10-10T20:00:00Z` → «Сейчас» → `CMSG.night` → «Да» → статус `scheduled`, `scheduledAt === '2026-10-11T07:00:00.000Z'`; «Нет» → статус `draft`; «Запланировать» на 22:30 → под полем `CMSG.quietAt`; `c-gone` → «Сейчас» → в редакторе под «Вечер» `CMSG.eventGone`.
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat(webapp): send flow with schedule, quiet hours offer and confirmation`.

### Task 9: Идущая и отправленная рассылка — просмотр и статистика

**Files:** Create `webapp/src/screens/owner/campaigns/{CampaignView.tsx,CampaignView.test.tsx}`

**Interfaces — Produces:** `CampaignView({campaign})` — заголовок, пилюля `campaignStatus`, даты (запланирована / начата / закончена), предпросмотр `MessageBubble` (только чтение), статистика `api.stats(id)` (при `running` — обновление раз в 5 с): «Получатели 214», «Доставлено 205», «Не доставлено 6» со списком `groupFailures` («Заблокировали бота — 3»…), «Пропущено из-за лимита 3», «Нажали 37» (+ «и ещё 4 нажатия без входа» при `anonymousClicks > 0`), «Купили 5» (только при `bought !== null`). `running` → «Остановить» с `Dialog` («Остановить рассылку? Кто ещё не получил — не получит.»). Отправленная/остановленная/отменённая → «Повторить» → `duplicate` → `/owner/campaigns/<новый id>`. У `cancelled` статистики нет: «Рассылка отменена — никто ничего не получил».

- [ ] **Step 1: тесты**: `c-done` — все числа и «Чат с гостем не найден — 2», «Отказались от рассылок или заблокировали бота — 1»; `c-running` → «Остановить» → подтверждение → «Остановлена»; `c-done` → «Повторить» → адрес новой рассылки, поле названия «… (копия)»; `c-cancelled` → текст об отмене, без чисел.
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat(webapp): running and sent campaign view with human-readable stats`.

### Task 10: Старт, шаблоны, свой шаблон

**Files:** Create `webapp/src/screens/owner/campaigns/{CampaignStart.tsx,Templates.tsx,TemplateEditor.tsx,templates.test.tsx}`

**Interfaces — Produces:**
- `CampaignStart` — «С чистого листа» → `/owner/campaigns/new`; «Готовые шаблоны» и «Свои шаблоны» (пусто — «Своих шаблонов пока нет. Сохрани рассылку как шаблон или создай в «Шаблонах»») — строка с именем и первой строкой текста → `/owner/campaigns/new?template=<id>`.
- `Templates` — две секции; у готового — «Использовать», «Скопировать в свои» (`createTemplate` с тем же содержимым и именем «<имя> (копия)»); у своего — «Использовать», «Править» → `/owner/campaigns/templates/<id>`, «Удалить» с `Dialog`. `useMainButton` «+ Новый шаблон» → `/owner/campaigns/templates/new`.
- `TemplateEditor` — имя, `TextEditor` (лимит по виду картинки), вид картинки («Афиша вечера» / «Своя» / «Без картинки»), `ButtonsEditor` с `hasEvent` = true; подсказка «{event} и {date} заменятся, когда выберешь вечер». Сохранение → `createTemplate`/`updateTemplate`, назад в «Шаблоны». Готовый шаблон по прямому адресу — только чтение с «Скопировать в свои».

- [ ] **Step 1: тесты**: старт → «Завтра вечер» → редактор с текстом «Завтра «{event}». Если билета ещё нет, он тут.»; «Скопировать в свои» у готового → в «Свои» появляется «Осталось мало мест (копия)»; свой шаблон: правка имени и текста `**скидка**` → сохранён `body` `<b>скидка</b>`; удаление своего после подтверждения; у готового нет «Править»/«Удалить».
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS + `tsc` + `npm run build`.
- [ ] **Step 5:** commit `feat(webapp): campaign start screen and templates`.

### Task 11: Проверка в браузере и STATUS

**Files:** Modify `docs/superpowers/STATUS.md`

- [ ] **Step 1:** весь прогон: `npx vitest run 2>&1 | grep -E "Tests "` — все зелёные; `npx tsc -b`; `npm run build` — размер gzip.
- [ ] **Step 2:** `npm run dev`, путь в браузере: Кабинет → Режим владельца → «Рассылки» → «Новая рассылка» → «Новый вечер в афише» → выбрать вечер → аудитория → «Отправить…» → «Сейчас» → подтверждение → экран идущей; «Отправлены» → статистика. Скриншот владельцу.
- [ ] **Step 3:** STATUS: этап 2 готов, запуск (`/#/owner/campaigns`, `?owner=`, `?scenario=offline`), отложенное для этапа 3: `HttpCampaignApi` (`parseCampaignError`), включение вкладки в Telegram, выравнивание текста старта на бэкенде («Вечер больше не опубликован» в `launch.py`), минорные замечания.
- [ ] **Step 4:** commit `docs: broadcasts screens stage done`.
