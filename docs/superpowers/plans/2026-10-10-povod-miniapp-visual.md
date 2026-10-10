# «Повод» Mini App — этап A (визуал на мок-данных) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Гостевой Telegram Mini App со всеми экранами, дизайн-системой «Стеклянный вечер» и поведением Telegram, работающий на локальном мок-API без бэкенда и оплаты.

**Architecture:** Отдельное приложение `webapp/` (Vite + React + TS). Весь доступ к данным — через интерфейс `AppApi`, повторяющий контракт раздела 5 спеки; на этапе A его реализует `MockApi` в памяти со сценариями. Telegram — через тонкую обёртку над `window.Telegram.WebApp` со стабом для браузера, где главная кнопка рисуется внутри страницы.

**Tech Stack:** Node 24, npm, React 18.3, react-router-dom 6 (`HashRouter`), @tanstack/react-query 5, TypeScript 5, Vite 6, Vitest 3 + @testing-library/react + jsdom, lucide-react, qrcode, @fontsource/unbounded, @fontsource-variable/manrope, CSS Modules + CSS-переменные.

**Spec:** `docs/superpowers/specs/2026-10-10-povod-miniapp-guest-design.md` (разделы 3 «Порядок работ», 5, 8–12).

## Global Constraints

- Всё в `webapp/`; Python-код, миграции и бот на этапе A не трогаем.
- Цвета, шрифты, радиусы, отступы — только из `src/styles/tokens.css`, значения дословно из таблиц раздела 9 спеки; хардкод цветов в компонентах запрещён.
- Тема — только `colorScheme` Telegram + `themeChanged`; `themeParams` не используются.
- Формат даты «чт, 16 окт», время «20:00», цена «1 550 ₽» с неразрывным пробелом (U+00A0) между разрядами и перед «₽»; часовой пояс — пояс мероприятия (`Europe/Moscow` в фикстурах).
- Склонения только через `plural()`; тексты экранов — дословно из раздела 10 спеки.
- Тап-зоны ≥ 44 px, текст ≥ 4.5:1, вёрстка в rem, `prefers-reduced-motion` отключает анимации.
- Аватары и имена других гостей нигде не показываются.
- Никаких сетевых запросов, кроме загрузки самого приложения; `telegram-web-app.js` подключается из `https://telegram.org/js/telegram-web-app.js`.
- Проверка перед каждым коммитом: `npm run typecheck && npm test` в `webapp/`.

## Review Focus

1. Длинные русские названия мероприятий (60+ символов) и длинные адреса — карточки и шапка не должны ломаться: `line-clamp`, уменьшение размера после 28 символов (тест в Task 7).
2. Гость с активной бронью открывает приложение по ссылке на другое мероприятие — должен попасть на экран брони, а не потерять её (тест в Task 6).
3. Двойное нажатие «Оплатить» — ровно один вызов `createOrder` (тест в Task 8).
4. Таймер брони, дошедший до нуля, пока экран открыт, — переход в «Бронь закончилась» без перезагрузки (тест в Task 9).
5. Билет «Возвращён»/«Передан»/«Вечер отменён» никогда не показывает QR, в том числе из офлайн-кэша (тест в Task 10).

---

## File Structure

```text
webapp/
  index.html                  подключает telegram-web-app.js, #root
  package.json, tsconfig.json, vite.config.ts, vitest.setup.ts
  src/main.tsx                QueryClient, ApiProvider, ThemeProvider, HashRouter
  src/App.tsx                 маршруты + StartGate + TabBar
  src/styles/tokens.css       токены dark/light, шрифты
  src/styles/global.css       reset, rem-база, reduced-motion
  src/lib/format.ts           plural, formatDate, formatTime, formatPrice, seatsLabel
  src/lib/posterColor.ts      цвет блока без фото по хэшу названия
  src/lib/ticketCache.ts      офлайн-кэш билетов (localStorage)
  src/telegram/tg.ts          типизированная обёртка + браузерный стаб
  src/telegram/hooks.ts       useMainButton, useBackButton, useClosingConfirmation, useTheme
  src/api/types.ts            DTO контракта раздела 5
  src/api/AppApi.ts           интерфейс + ApiError
  src/api/ApiProvider.tsx     контекст выбора реализации
  src/api/mock/fixtures.ts    мероприятия, билеты, голосования
  src/api/mock/MockApi.ts     реализация в памяти + сценарии
  src/ui/*.tsx + *.module.css Button, Pill, Stepper, TabBar, DirectionTile,
                              Poster, PhotoHeader, EmptyState, ErrorState,
                              Skeleton, Dialog, InPageMainButton
  src/screens/Welcome.tsx, Afisha.tsx, EventScreen.tsx, OrderScreen.tsx,
              Tickets.tsx, TicketScreen.tsx, ClaimScreen.tsx, Polls.tsx
  src/**/*.test.ts(x)         рядом с кодом
```

---

### Task 1: Каркас webapp, токены, тема

**Files:**
- Create: `webapp/package.json`, `webapp/tsconfig.json`, `webapp/vite.config.ts`, `webapp/vitest.setup.ts`, `webapp/index.html`, `webapp/src/main.tsx`, `webapp/src/App.tsx`, `webapp/src/styles/tokens.css`, `webapp/src/styles/global.css`, `webapp/src/telegram/tg.ts`, `webapp/src/telegram/hooks.ts`
- Modify: `.gitignore` (добавить `webapp/node_modules/`, `webapp/dist/`), `.github/workflows/ci.yml` (job `webapp`: `npm ci`, `npm run typecheck`, `npm test`, `npm run build` в `webapp/`)
- Test: `webapp/src/telegram/tg.test.ts`, `webapp/src/telegram/hooks.test.tsx`

**Interfaces:**
- Produces:
  - `tg: TgFacade` из `tg.ts`; `TgFacade` = `{ isTelegram: boolean; colorScheme: 'light'|'dark'; startParam: string|null; ready(); expand(); disableVerticalSwipes(); onThemeChanged(cb): () => void; setChromeColor(hex: string); openLink(url); openTelegramLink(url); haptic: { impact(style:'light'|'medium'), selection(), notify(type:'success'|'warning'|'error') }; mainButton: { set(state: MainButtonState|null) }; backButton: { set(onBack: (() => void)|null) }; closingConfirmation(enabled: boolean); storage: { get(key): Promise<string|null>; set(key, value): Promise<void> } }`.
  - `MainButtonState = { text: string; enabled: boolean; progress: boolean; onClick: () => void }`.
  - `createTg(webApp?: TelegramWebApp): TgFacade` — фабрика для тестов; без `webApp` возвращает стаб (`isTelegram=false`, тема из `prefers-color-scheme`, storage → `localStorage`, `mainButton.set` пишет состояние в `mainButtonStore`).
  - `mainButtonStore` — `{ subscribe(cb), get(): MainButtonState|null }` для `InPageMainButton` (Task 4).
  - Хуки: `useTheme(): 'light'|'dark'` (ставит `data-theme` на `<html>` и `setChromeColor(bg)`), `useMainButton(state: MainButtonState|null)`, `useBackButton(onBack|null)`, `useClosingConfirmation(enabled: boolean)`.
- npm-скрипты: `dev`, `build`, `preview`, `typecheck` (`tsc --noEmit`), `test` (`vitest run`).

- [ ] **Step 1: Создать проект** — `npm create vite@latest webapp -- --template react-ts`, поставить зависимости из Tech Stack, удалить демо-файлы шаблона. В `index.html` — `<script src="https://telegram.org/js/telegram-web-app.js"></script>` до бандла.
- [ ] **Step 2: Токены.** `tokens.css`: переменные `--bg`, `--surface-1..3`, `--text-1..3`, `--accent`, `--accent-pressed`, `--on-accent`, `--accent-text`, `--icon-violet`, `--icon-mint`, `--success`, `--error`, `--warning`, `--border`, `--border-strong`, `--glass`, `--glass-nav` для `[data-theme='dark']` и `[data-theme='light']` — значения дословно из таблицы раздела 9; радиусы `--r-8 … --r-26`, `--r-pill: 999px`; отступы `--s-2 … --s-40`; типографика `--font-display: 'Unbounded'`, `--font-body: 'Manrope Variable'` и классы шкалы раздела 9. Шрифты — импорт `@fontsource/unbounded/cyrillic-500.css`, `@fontsource/unbounded/latin-500.css`, `@fontsource-variable/manrope`. `global.css`: `html{font-size:100%}`, `@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}`.
- [ ] **Step 3: Падающие тесты обёртки** (`tg.test.ts`):
  - `createTg(webAppWithoutMainButton)` (старый клиент) → `mainButton.set` пишет в `mainButtonStore`, как стаб.
  - `createTg()` без WebApp → `isTelegram === false`, `storage.set('k','v')` затем `get('k')` → `'v'` (через localStorage).
  - `createTg(fakeWebApp)` → `ready/expand/disableVerticalSwipes` вызывают одноимённые методы фейка; `mainButton.set({text:'Оплатить 3 100 ₽', enabled:true, progress:false, onClick})` вызывает `MainButton.setText('Оплатить 3 100 ₽')`, `enable()`, `show()`; `set(null)` → `hide()` и снятие обработчика (повторный `set` не копит обработчики: `onClick` фейка зарегистрирован ровно один).
  - `startParam` берётся из `initDataUnsafe.start_param`.
  - `hooks.test.tsx`: `useTheme` ставит `document.documentElement.dataset.theme` в `'dark'` при `colorScheme='dark'` и меняет на `'light'` после события `themeChanged`.
- [ ] **Step 4: Запустить** `cd webapp && npm test` — FAIL (модули не существуют).
- [ ] **Step 5: Реализовать** `tg.ts` и `hooks.ts` по Interfaces. `setChromeColor` вызывает `setHeaderColor`, `setBackgroundColor`, `setBottomBarColor`, если методы есть (проверка `typeof === 'function'` — старые клиенты).
- [ ] **Step 6: Проверить** `npm run typecheck && npm test && npm run build` — PASS, `dist/` собран.
- [ ] **Step 7: Commit** `feat(webapp): scaffold mini app with tokens and telegram wrapper`.

### Task 2: Форматирование и цвет постера

**Files:**
- Create: `webapp/src/lib/format.ts`, `webapp/src/lib/posterColor.ts`
- Test: `webapp/src/lib/format.test.ts`, `webapp/src/lib/posterColor.test.ts`

**Interfaces:**
- Produces: `plural(n: number, forms: [string, string, string]): string`; `ticketsLabel(n): string` («1 билет»…); `seatsLabel(n): string` («осталось 1 место», 0 → «мест нет»); `formatDate(iso: string, tz: string): string`; `formatTime(iso, tz): string`; `formatDateTime(iso, tz)` → «чт, 16 окт · 20:00»; `formatPrice(kopecks: number): string`; `posterColor(title: string): string` (один из 8 hex раздела 9).

- [ ] **Step 1: Падающие тесты** — `ticketsLabel`: 1→«1 билет», 2→«2 билета», 5→«5 билетов», 11→«11 билетов», 21→«21 билет», 22→«22 билета»; `seatsLabel(1)`→«осталось 1 место», `seatsLabel(5)`→«осталось 5 мест», `seatsLabel(0)`→«мест нет»; `formatDate('2026-10-16T17:00:00Z','Europe/Moscow')`→«чт, 16 окт»; `formatTime(...)`→«20:00»; `formatPrice(155000)`→`'1 550 ₽'`, `formatPrice(310000)`→`'3 100 ₽'`, `formatPrice(90000)`→`'900 ₽'`; `posterColor('Киновечер')` стабилен между вызовами и входит в список из 8 цветов.
- [ ] **Step 2: Запустить** — FAIL.
- [ ] **Step 3: Реализовать.** Даты — `Intl.DateTimeFormat('ru-RU', {weekday:'short', day:'numeric', month:'short', timeZone})` с удалением точек («окт.» → «окт»); цена — `Intl.NumberFormat('ru-RU')` с заменой узкого пробела U+202F на U+00A0; `posterColor` — FNV-1a 32-бит по названию, индекс `hash % 8`.
- [ ] **Step 4: Запустить** — PASS. **Step 5: Commit** `feat(webapp): add russian formatting helpers`.

### Task 3: Контракт API и MockApi

**Files:**
- Create: `webapp/src/api/types.ts`, `webapp/src/api/AppApi.ts`, `webapp/src/api/ApiProvider.tsx`, `webapp/src/api/mock/fixtures.ts`, `webapp/src/api/mock/MockApi.ts`
- Test: `webapp/src/api/mock/MockApi.test.ts`

**Interfaces:**
- Produces (`types.ts`): `Direction {id, title, icon: 'film'|'dice'|'talk'|'party'}`; `EventCard {id, title, startsAt, timezone, address: string|null, poster: Poster|null, minPriceKopecks, seatsLeft, soldOut, directionId}`; `Poster {url, focusX, focusY, width, height}`; `TicketTypeOffer {id, name, priceKopecks, seatsLeft}`; `EventDetail extends EventCard {description, mapUrl: string|null, ticketTypes: TicketTypeOffer[], poll: Poll|null}`; `OrderStatus = 'pending'|'paid'|'failed'|'expired'|'reconciliation'`; `Order {id, eventId, status, expiresAt, paymentUrl, items: {ticketTypeId, qty}[], totalKopecks, paymentUncertain: boolean}`; `TicketStatus = 'valid'|'used'|'returned'|'transferred'|'event_cancelled'`; `Ticket {id, eventId, eventTitle, startsAt, timezone, address, mapUrl, typeName, position, ofCount, shortCode, status, qrToken: string|null, poster: Poster|null}`; `Poll {id, question, closesAt, closed, options: {id, title, percent: number|null}[], myOptionId: string|null, votes: number}`; `Me {welcomeAccepted: boolean, activeOrder: Order|null}`.
- Produces (`AppApi.ts`): `interface AppApi { me(); acceptWelcome(); directions(); events(directionId?); event(id); createOrder(eventId, items); order(id); cancelOrder(id); tickets(); shareTicket(id): Promise<{shareUrl}>; revokeShare(id); claimTicket(token): Promise<Ticket>; polls(); vote(pollId, optionId) }` (все — `Promise`); `class ApiError extends Error { code: 'active_order_exists'|'not_enough_seats'|'poll_closed'|'payment_uncertain'|'already_claimed'|'not_found'|'network'; data?: {orderId?: string; seatsLeft?: number} }`.
- `ApiProvider`/`useApi(): AppApi`; на этапе A всегда `new MockApi(scenarioFromUrl())`.
- `MockApi(options: {scenario: Scenario; now?: () => number; latencyMs?: number})`, `Scenario = 'happy'|'pay_fail'|'pay_pending'|'late'|'sold_out'|'empty'|'offline'`; `scenarioFromUrl()` читает `?scenario=` из `location.search`. «Оплата» имитируется: `createOrder` возвращает `paymentUrl = '#/mock-pay/<orderId>'`; маршрут `mock-pay` (Task 8) переводит заказ по сценарию.

- [ ] **Step 1: Фикстуры** — 4 мероприятия: «Повод для киновечера» (16 окт 20:00, 1 550 ₽, 5 мест, с фото и голосованием «Амели» / «Ла-Ла Ленд»), «Настолки до утра» (без фото), вечер с `address: null`, распроданный; направления Кино/Настолки/Разговоры/Вечеринки; 4 билета гостя: два действующих (1 из 2, 2 из 2), «Возвращён», «Передан»; 1 закрытое голосование. Постеры — локальные файлы в `webapp/public/mock/` (2 любых фото 4:5 и 2:1 с лицензией CC0, источник записать в `public/mock/SOURCES.md`).
- [ ] **Step 2: Падающие тесты MockApi:**
  - `createOrder` при уже активном заказе → `ApiError('active_order_exists')` с `data.orderId`.
  - `createOrder` на 3 билета при `seatsLeft=2` → `ApiError('not_enough_seats')`, `data.seatsLeft === 2`.
  - сценарий `pay_pending`: `cancelOrder` → `ApiError('payment_uncertain')`.
  - `vote` дважды разными вариантами → `myOptionId` = второй, `votes` не растёт; после `closesAt` → `ApiError('poll_closed')`.
  - `claimTicket` вторым вызовом → `ApiError('already_claimed')`; после claim у исходного билета статус `transferred`, `qrToken === null`.
  - заказ с `expiresAt` в прошлом (через `now`) → `order(id).status === 'expired'`.
  - сценарий `offline` → любой метод отклоняется `ApiError('network')`.
- [ ] **Step 3: Запустить** — FAIL. **Step 4: Реализовать** `MockApi` (состояние в памяти, `latencyMs` по умолчанию 300, в тестах 0). **Step 5:** PASS. **Step 6: Commit** `feat(webapp): add api contract and mock implementation`.

### Task 4: UI-кит

**Files:**
- Create: `webapp/src/ui/{Button,Pill,Stepper,TabBar,DirectionTile,Poster,PhotoHeader,EmptyState,ErrorState,Skeleton,Dialog,InPageMainButton}.tsx` + `.module.css`
- Test: `webapp/src/ui/ui.test.tsx`

**Interfaces:**
- Consumes: токены (Task 1), `posterColor` (Task 2), `mainButtonStore` (Task 1).
- Produces: `Button({variant:'primary'|'outline'|'link', loading?, disabled?, children, onClick})`; `Pill({tone:'accent'|'glass'|'success'|'warning'|'error', children})`; `Stepper({value, min=0, max, label, onChange})`; `TabBar({hidden})` с вкладками `/` «Афиша», `/tickets` «Билеты», `/polls` «Голосуем» (иконки lucide `CalendarDays`, `Ticket`, `Vote`); `DirectionTile({direction, selected, onSelect})`; `Poster({poster, title, ratio:'4:5'|'2:1'|'3:1', icon})` — фото со скримом или цветной блок; `PhotoHeader({poster, title, onBack})`; `EmptyState({title, text, action?})`; `ErrorState({title, text, actionLabel, onAction})`; `Skeleton({height})`; `Dialog({title, text, confirmLabel, cancelLabel, onConfirm, onCancel})`; `InPageMainButton()` — рисует состояние `mainButtonStore`, только если `!tg.isTelegram`.

- [ ] **Step 1: Падающие тесты:**
  - `Stepper` value=2,max=2: кнопка «+» `disabled`, рядом текст «Больше нет»; aria-label кнопки «−» — «Входной: 2 билета. Убавить» (label=«Входной»); нажатие «+» при value=0 вызывает `onChange(1)`.
  - `Poster` с `poster=null` рендерит блок с `style.backgroundColor === posterColor(title)` и иконкой; с постером — `<img>` с `object-position: 30% 40%` для focus 0.3/0.4 и элемент скрима.
  - `Poster` при `width < 600` или `height < 600` ведёт себя как без фото.
  - `Button loading` — `aria-busy="true"`, ширина не меняется (фиксируется `min-width` из первого рендера).
  - `InPageMainButton` при `tg.isTelegram=false` показывает кнопку с текстом из `mainButtonStore`, неактивную при `enabled:false`.
- [ ] **Step 2: Запустить** — FAIL. **Step 3: Реализовать.** Стекло — класс `.glass` из раздела 9 с `@supports not (backdrop-filter: blur(1px))`; класс `no-blur` на `<html>` ставится в `main.tsx`, если `navigator.hardwareConcurrency <= 4` или `navigator.deviceMemory <= 3`. Скрим — `linear-gradient(to top, rgba(15,14,18,.8), rgba(15,14,18,.65) 45%, transparent)`. Нажатие — `transform: scale(.98)`.
- [ ] **Step 4:** PASS. **Step 5: Commit** `feat(webapp): add glass evening ui kit`.

### Task 5: Проверка кита глазами — страница-витрина

**Files:**
- Create: `webapp/src/screens/Kit.tsx` (маршрут `#/kit`, только в dev: `import.meta.env.DEV`)

- [ ] **Step 1:** Вывести все компоненты Task 4 во всех состояниях, в обеих темах (переключатель `data-theme`).
- [ ] **Step 2:** `npm run dev`, открыть `http://localhost:5173/#/kit` в ширине 375 px; проверить: текст на фото читается, «осталось 5 мест» на стеклянной пилюле, кнопки ≥ 44 px, светлая тема не инверсия тёмной. Скриншоты обеих тем приложить к отчёту задачи.
- [ ] **Step 3: Commit** `chore(webapp): add dev-only component showcase`.

### Task 6: Каркас приложения, старт и deep links

**Files:**
- Create: `webapp/src/screens/Welcome.tsx`, `webapp/src/start.ts`
- Modify: `webapp/src/App.tsx`, `webapp/src/main.tsx`
- Test: `webapp/src/start.test.ts`, `webapp/src/App.test.tsx`

**Interfaces:**
- Consumes: `tg`, `useApi`, UI-кит.
- Produces: `resolveStart(startParam: string|null, me: Me): string` — путь для `HashRouter`: активный заказ → `/order/<id>` (всегда, независимо от параметра); `event_<id>` → `/events/<id>`; `order_<id>` → `/order/<id>`; `ticket_<id>` → `/tickets/<id>`; `claim_<token>` → `/claim/<token>`; `vote_<id>` → `/polls`; иначе `/`. Маршруты: `/`, `/events/:id`, `/order/:id`, `/mock-pay/:id`, `/tickets`, `/tickets/:id`, `/claim/:token`, `/polls`, `/kit` (dev).
- Стек: при deep link на карточку сначала `navigate('/')`, затем `navigate(path)`, чтобы «назад» вёл в афишу.

- `StartGate` дополнительно: если `me.activeOrder === null`, а `tg.storage.get('activeOrderId')` вернул id и `api.order(id).status` — `pending` или `paid`, ведёт на `/order/<id>`; иначе очищает ключ.

- [ ] **Step 1: Падающие тесты:** `resolveStart('event_e2', {welcomeAccepted:true, activeOrder:null})` → `'/events/e2'`; `resolveStart('event_e2', {…, activeOrder:{id:'o1', status:'pending'}})` → `'/order/o1'` (Review Focus 2); `resolveStart('garbage', …)` → `'/'`. `App.test.tsx`: при `welcomeAccepted:false` показывается «Привет, это «Повод»», кнопка «Заходим» вызывает `acceptWelcome`, затем открывается путь из `resolveStart` (deep link не потерян); при повторном старте приветствия нет.
- [ ] **Step 2:** FAIL. **Step 3: Реализовать.** `main.tsx`: `tg.ready(); tg.expand(); tg.disableVerticalSwipes()`; `QueryClient` с `retry: 1`. `TabBar hidden`, когда `mainButtonStore.get() !== null` или маршрут не вкладка. Высота — `min-height: var(--tg-viewport-stable-height, 100dvh)`; нижний отступ контента `calc(96px + env(safe-area-inset-bottom))`. Текст приветствия — дословно из раздела 10 спеки, на месте текста владельца — `<p data-slot="owner-consent" />`.
- [ ] **Step 4:** PASS. **Step 5: Commit** `feat(webapp): add app shell, welcome and deep links`.

### Task 7: Афиша

**Files:**
- Create: `webapp/src/screens/Afisha.tsx`, `Afisha.module.css`
- Test: `webapp/src/screens/Afisha.test.tsx`

**Interfaces:** Consumes `api.directions()`, `api.events(directionId?)`, `api.me()` (плашка брони), `Poster`, `DirectionTile`, `Pill`, `format.ts`.

- [ ] **Step 1: Падающие тесты:** hero — ближайшее мероприятие, на нём «чт, 16 окт», «осталось 5 мест», «от 1 550 ₽»; выбор плитки «Настолки» оставляет только мероприятия направления (haptic `selection` вызван); распроданное — «мест нет» и класс десатурации; сценарий `empty` → «Пока тихо» / «Новых вечеров нет. Как появятся, напишем в боте.»; сценарий `offline` → «Нет связи» и «Повторить» перезапрашивает; при активном заказе — плашка «Бронь ждёт оплаты · MM:SS» ведёт на `/order/<id>`; название из 70 символов получает класс `titleLong` (Review Focus 1).
- [ ] **Step 2:** FAIL. **Step 3: Реализовать:** hero 2:1, ряд плиток, «Скоро» сеткой 2 колонки 4:5, skeleton при загрузке. **Step 4:** PASS. **Step 5: Commit** `feat(webapp): add afisha screen`.

### Task 8: Карточка мероприятия и оформление

**Files:**
- Create: `webapp/src/screens/EventScreen.tsx`, `EventScreen.module.css`, `webapp/src/screens/MockPay.tsx`, `webapp/src/checkout/cart.ts`
- Test: `webapp/src/checkout/cart.test.ts`, `webapp/src/screens/EventScreen.test.tsx`

**Interfaces:**
- Produces: `cartReducer(state: CartState, action: {type:'inc'|'dec', ticketTypeId} | {type:'clamp', ticketTypeId, max}): CartState`; `cartTotal(cart, offers): {count: number; kopecks: number}`; `CartState = Record<string, number>`.
- Consumes: `api.event`, `api.createOrder`, `useMainButton`, `useBackButton`, `Stepper`, `PhotoHeader`, `Dialog`.

- [ ] **Step 1: Падающие тесты:** `cartReducer` не уходит ниже 0 и выше `seatsLeft` типа; `cartTotal` для 2×1 550 + 1×1 550 → `{count:3, kopecks:465000}`. Экран: итог «3 билета · 4 650 ₽»; MainButton — «Оплатить 4 650 ₽» (enabled), при пустой корзине «Выберите билеты» (disabled), для распроданного «Мест нет»; двойной клик по MainButton → `createOrder` вызван ровно один раз, `progress:true` (Review Focus 3); `active_order_exists` → диалог «У вас уже есть бронь на «…». Продолжить оплату или отменить?»; `not_enough_seats` (seatsLeft 2) → «Мест стало меньше» / «Пока вы выбирали, осталось 2 места. Взять 2 билета?», «Взять 2» ставит корзину в 2 и повторяет заказ; `address: null` → «Место пока уточняется. Напишем в боте, как только определимся.»; успех → `tg.openLink(paymentUrl)`, `closingConfirmation(true)`, `tg.storage.set('activeOrderId', id)`, переход на `/order/<id>`; при диалоге «Мест стало меньше» — haptic `notify('warning')`; блок голосования вечера показывает вопрос (голосование — Task 11).
- [ ] **Step 2:** FAIL. **Step 3: Реализовать.** Haptic `impact('light')` на −/+. Правило возврата мелким текстом: «Полный возврат — если до вечера больше 3 дней». `MockPay` — экран-имитация банка (белый, «Тестовая оплата»), кнопки «Оплатить» / «Отказаться» переводят мок-заказ и возвращают на `#/order/<id>`; в Telegram `openLink` на hash-URL открывает его во внешнем браузере — на этапе A допустимо, т.к. оплату не подключаем.
- [ ] **Step 4:** PASS. **Step 5: Commit** `feat(webapp): add event screen and mock checkout`.

### Task 9: Экраны брони и результата

**Files:**
- Create: `webapp/src/screens/OrderScreen.tsx`, `OrderScreen.module.css`, `webapp/src/checkout/useCountdown.ts`
- Test: `webapp/src/screens/OrderScreen.test.tsx`

**Interfaces:** Consumes `api.order` (опрос каждые 3 с через `refetchInterval`), `api.cancelOrder`, `Dialog`, хуки Telegram. Produces `useCountdown(expiresAt: string, now?: () => number): {left: string /* 'MM:SS' */; expired: boolean}`.

- [ ] **Step 1: Падающие тесты (fake timers):**
  - `pending`: «Бронь ждёт оплаты», «Места за вами ещё 08:42», элемент `role="timer"`, MainButton «Открыть оплату снова» вызывает `openLink`; «Отменить бронь» → диалог «Отменить бронь?» / «Места вернутся в продажу.» → `cancelOrder`, `closingConfirmation(false)`.
  - `paymentUncertain: true` → «Отменить бронь» отсутствует.
  - таймер дошёл до 0 при открытом экране → «Бронь закончилась» / «Десять минут прошли, места вернулись в продажу.», кнопка «Выбрать заново», haptic `notify('warning')` (Review Focus 4).
  - `paid` → «Билеты у вас» / «Ждём в чт, 16 окт в 20:00. Копия ушла в бот.», MainButton «Показать билеты», haptic success, `closingConfirmation(false)`.
  - `pay_pending` 60 с без перехода → «Банк отвечает дольше обычного» / «Если оплата прошла, билет придёт сообщением в бот. Страницу можно закрыть.».
  - `failed` при живой брони → «Оплата не прошла» / «Деньги не списаны. Бронь ещё держим — 6 минут.», «Попробовать снова», haptic `notify('error')`.
  - `reconciliation` → «Оплата дошла после окончания брони. Администратор проверит и напишет вам сегодня».
  - «назад» с результата → `/tickets`, с ожидания → `/` без отмены брони.
- [ ] **Step 2:** FAIL. **Step 3: Реализовать.** Озвучка таймера: `aria-live="polite"` обновляется только на 5, 2, 1, 0 минутах; рядом текст «до HH:MM». **Step 4:** PASS. **Step 5: Commit** `feat(webapp): add order status screens`.

### Task 10: Билеты, QR, передача, офлайн

**Files:**
- Create: `webapp/src/screens/Tickets.tsx`, `TicketScreen.tsx`, `ClaimScreen.tsx` + `.module.css`, `webapp/src/lib/ticketCache.ts`, `webapp/src/ui/Qr.tsx`
- Test: `webapp/src/lib/ticketCache.test.ts`, `webapp/src/screens/Tickets.test.tsx`

**Interfaces:**
- Produces: `ticketCache.save(tickets: Ticket[])`, `ticketCache.load(): Ticket[]` — сохраняет `qrToken` только для `status === 'valid'`; `Qr({value, size})` — SVG через `qrcode.toString(value, {type:'svg', margin:2})` на белой плашке.
- Consumes: `api.tickets`, `api.shareTicket`, `api.revokeShare`, `api.claimTicket`, `tg.openTelegramLink`.

- [ ] **Step 1: Падающие тесты:**
  - список: «Ближайшие» с «2 билета» у киновечера; «Прошедшие · N» свёрнуто; «Возвращён» и «Передан» — серым, без QR.
  - экран билета: QR ≥ 240 px, «Билет 1 из 2», «Покажите QR на входе», «Номер 4821 — если QR не читается», свайп/стрелка ведёт к «Билет 2 из 2», «На карте» открывает `mapUrl`.
  - `ticketCache.load()` после `save` со статусами valid/returned/transferred/event_cancelled возвращает `qrToken` только у valid (Review Focus 5); сценарий `offline` → билеты из кэша и подпись «Билет сохранён на телефоне».
  - «Отправить другу» → `shareTicket`, затем `openTelegramLink('https://t.me/share/url?url=<shareUrl>')`; повторный claim → «Этот билет уже забрал другой гость».
- [ ] **Step 2:** FAIL. **Step 3: Реализовать.** Пустое состояние: «Билетов пока нет» / «Выберите вечер в афише — билеты появятся здесь.» / «Открыть афишу». **Step 4:** PASS. **Step 5: Commit** `feat(webapp): add tickets, qr and sharing`.

### Task 11: Голосования

**Files:**
- Create: `webapp/src/screens/Polls.tsx`, `Polls.module.css`, `webapp/src/ui/PollCard.tsx`
- Test: `webapp/src/screens/Polls.test.tsx`

**Interfaces:** Consumes `api.polls`, `api.vote`. Produces `PollCard({poll, onVote})` — используется и в карточке мероприятия (Task 8 подключает после этой задачи; до неё блок голосования в карточке — заглушка с тем же пропсом).

- [ ] **Step 1: Падающие тесты:** до голоса проценты скрыты; тап по варианту → `vote`, haptic `selection`, видны проценты и «Можно передумать до чт, 16 окт, 18:00»; смена голоса двигает выбор; закрытое — итог и «Голосование уже закрыто» при попытке; пусто — «Сейчас ничего не выбираем» / «Новое голосование появится — напишем в боте.»; «Проголосовало 24».
- [ ] **Step 2:** FAIL. **Step 3: Реализовать**, заменить заглушку в `EventScreen` на `PollCard`. **Step 4:** PASS. **Step 5: Commit** `feat(webapp): add polls`.

### Task 12: Финальная проверка и показ

**Files:**
- Modify: `webapp/README.md` (создать: запуск, сценарии `?scenario=`, ограничения этапа A)

- [ ] **Step 1:** `npm run typecheck && npm test && npm run build` — всё зелёное; размер `dist/assets/*.js` gzip ≤ 250 КБ (вывод `vite build`).
- [ ] **Step 2:** `npm run preview`, пройти в ширине 375 px и в обеих темах сценарии `happy`, `pay_fail`, `pay_pending`, `late`, `sold_out`, `empty`, `offline`; включить системное увеличение шрифта 200% — без обрезанных кнопок. Скриншоты ключевых экранов приложить к отчёту.
- [ ] **Step 3:** Показ в Telegram требует HTTPS-адреса и кнопки меню бота — **не публиковать без решения владельца**: в отчёте предложить варианты (VPS владельца или временный статический хостинг) и ждать выбора.
- [ ] **Step 4: Commit** `docs(webapp): document stage A preview`.
