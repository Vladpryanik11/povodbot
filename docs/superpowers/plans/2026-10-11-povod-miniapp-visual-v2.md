# «Повод» Mini App — визуал v2: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести `webapp/` на визуальную систему v2: чёрный Netflix/Apple-стиль, ореол цвета афиши, меню Дом · Избранное · Кабинет, бумажный билет, голос на «ты».

**Architecture:** Меняем токены и шрифты, затем строим новые UI-компоненты в `src/ui/`, затем пересобираем экраны (`Home`, `EventScreen`, `Favorites`, `Cabinet`, `TicketScreen`) поверх существующего `AppApi`/`MockApi`. Telegram MainButton больше не используется: `useMainButton` пишет только в стор, нижнюю панель всегда рисует страница. Всё на mock-данных (этап A).

**Tech Stack:** Vite 6, React 18, TypeScript 5.7, react-router 6, TanStack Query 5, Vitest 3 + Testing Library, CSS Modules, lucide-react, `@fontsource/wix-madefor-*`.

**Spec:** `docs/superpowers/specs/2026-10-11-povod-miniapp-visual-v2-design.md` (основная логика — `2026-10-10-povod-miniapp-guest-design.md`, где v2 не говорит иначе).

## Global Constraints

- Только тёмная тема; `colorScheme` Telegram игнорируется; bg `#000000`.
- Цвет афиши — никогда не фон под текстом и не в кнопках; только ореол, точка статус-пилюли, фон «+N».
- Главная кнопка: фон `#FFFFFF`, текст `#000000`; вторичная — стекло.
- Шрифты: Wix Madefor Display 700 — заголовки; Wix Madefor Text 400/500 — остальное; без капса; минимум 13 px.
- Тап-зоны ≥ 44 px; контраст текста ≥ 4.5:1.
- Не больше двух стеклянных слоёв на экране; фолбэк `.no-blur` → `--surface-3`.
- Тексты — дословно из §8 спеки v2; на «ты», без эмодзи, без мужского/женского рода.
- `prefers-reduced-motion: reduce` → все переходы мгновенные.
- Опросы: из навигации и экрана события убрать, файлы `Polls*`, `PollCard*`, `usePollVote` не удалять.
- Никаких реальных запросов к Telegram и T-Bank; `.env` не трогать.
- Тесты гонять так: `npx vitest run <путь> 2>&1 | grep -E "Tests "`; полный прогон — `npx vitest run 2>&1 | grep -E "Tests "`. Все команды — из `webapp/`.

## Review Focus

1. Белый/очень светлый постер — текст на billboard и в шапке события должен читаться (скрим ≥ .65), ореол не выжигает экран (L ≤ 60%). → тест в Task 2 (`normalizeHsl` на `#FFFFFF`) и ручная проверка в Task 14.
2. Событие без постера и без `accentColor` — цвет по хэшу, никакого падения. → тест в Task 2.
3. Испорченное значение `fav` в CloudStorage (не JSON, не массив, 150 элементов) — избранное пустое/обрезанное, не падает. → тест в Task 6.
4. Billboard с 0 и 1 событием — без автосмены и без точек; при 0 — пустое состояние «Пока тихо». → тест в Task 8.
5. Билет на сегодня уже использован или событие уже прошло — пилюля «Сегодня» не показывается. → тест в Task 9.

---

### Task 1: Токены, шрифты, только тёмная тема

**Files:**
- Modify: `webapp/package.json` (зависимости шрифтов)
- Modify: `webapp/src/styles/tokens.css`, `webapp/src/styles/global.css`
- Modify: `webapp/src/telegram/hooks.ts` (`useTheme`)
- Test: `webapp/src/telegram/hooks.test.tsx`

**Interfaces:**
- Produces: CSS-переменные, которыми пользуются все следующие задачи:
  `--bg --surface-1 --surface-2 --surface-3 --text-1 --text-2 --text-3 --border --glass --glass-border --btn-primary --on-btn-primary --success --error --warning --tabbar --tabbar-border --paper --paper-ink --paper-muted --paper-perf --font-display --font-body --r-12 --r-16 --r-20 --r-28 --r-pill --poster` (последняя ставится JS, дефолт `transparent`).
- `useTheme(): 'dark'` — всегда `'dark'`.

- [ ] **Step 1: Тест** в `hooks.test.tsx`: `it('forces dark theme even when Telegram is light')` — рендер хука с `createTg({ colorScheme: 'light', … })` (как в соседних тестах), ожидать `document.documentElement.dataset.theme === 'dark'` и что `setChromeColor` вызван с `'#000000'`.
- [ ] **Step 2:** `npx vitest run src/telegram/hooks.test.tsx 2>&1 | grep -E "Tests "` → FAIL.
- [ ] **Step 3:** `useTheme` возвращает `'dark'` и не подписывается на `onThemeChanged`; `THEME_BG.dark = '#000000'`.
- [ ] **Step 4:** `npm i @fontsource/wix-madefor-display @fontsource/wix-madefor-text` и `npm rm @fontsource/unbounded @fontsource-variable/manrope`. В `tokens.css` импортировать `@fontsource/wix-madefor-display/{cyrillic,latin}-700.css`, `@fontsource/wix-madefor-text/{cyrillic,latin}-{400,500}.css`. Если пакета нет в npm — взять woff2 с Google Fonts в `public/fonts/` и `@font-face` с `font-display: swap`.
- [ ] **Step 5:** Переписать `tokens.css`: удалить блок `[data-theme='light']`; значения из таблицы §3 «Цвет» спеки v2 (bg `#000000`, surface `#0E0D10/#151316/#1F1C22`, text `#FFFFFF/#B8B2B5/#8F898C`, border `rgba(255,255,255,.10)`, glass `rgba(28,26,30,.72)`, glass-border `rgba(255,255,255,.12)`, tabbar `#151316`, tabbar-border `rgba(255,190,170,.16)`, paper `#F4F1EA/#141414/#6B665E/#C9C3B8`, success/error/warning как раньше). Радиусы `12 16 20 28 999`; убрать `--accent*`, `--icon-violet/mint`. В `global.css` класс `.glass` → `backdrop-filter: blur(20px) saturate(1.4)`; типографические классы `.t-billboard .t-h1 .t-h2 .t-h3 .t-body .t-body-s .t-meta .t-price` по таблице §3 «Типографика».
- [ ] **Step 6:** Тест → PASS; `npx tsc --noEmit` без ошибок; полный прогон — упавшие тесты только из-за удалённых переменных чинить заменой на новые.
- [ ] **Step 7: Commit** `feat(webapp): v2 tokens, Wix Madefor fonts, dark only`.

### Task 2: Цвет афиши

**Files:**
- Modify: `webapp/src/lib/posterColor.ts`
- Test: `webapp/src/lib/posterColor.test.ts`

**Interfaces:**
- Produces:
  - `normalizeHsl(hex: string): string` — в HSL зажимает S в [45, 80], L в [45, 60], возвращает `#rrggbb`.
  - `dominantColor(pixels: Uint8ClampedArray): string | null` — RGBA-массив; отбрасывает пиксели с яркостью < 0.15 и > 0.90 и с S < 0.2; медиана hue по оставшимся, S/L — средние; `null`, если осталось < 5% пикселей.
  - `eventColor(e: { accentColor: string | null; title: string }, extracted?: string | null): string` — `normalizeHsl(accentColor ?? extracted ?? posterColor(title))`.
  - `extractPosterColor(url: string): Promise<string | null>` — грузит `Image` с `crossOrigin='anonymous'`, рисует в canvas 32×32, отдаёт `dominantColor`; при любой ошибке `null`. Кэш в `Map` по url.

- [ ] **Step 1: Тесты:** `normalizeHsl('#FFFFFF')` → L ≤ 60 (проверить через вспомогательный `hexToHsl` в тесте); `normalizeHsl('#101010')` → L ≥ 45; `normalizeHsl('#FF0000')` → S ≤ 80; `dominantColor` на массиве из 100 пикселей `#D4537E` + 20 чёрных → hue в пределах ±10° от 340; на массиве только белых → `null`; `eventColor({accentColor:'#2244FF', title:'x'})` = `normalizeHsl('#2244FF')`; `eventColor({accentColor:null, title:'Киновечер'}, null)` = `normalizeHsl(posterColor('Киновечер'))`.
- [ ] **Step 2:** Прогон → FAIL.
- [ ] **Step 3:** Реализовать функции; `posterColor`/`POSTER_COLORS` оставить.
- [ ] **Step 4:** Прогон → PASS.
- [ ] **Step 5: Commit** `feat(webapp): poster colour from accent, image or title`.

### Task 3: Данные: направления, цвет, гости, приватность

**Files:**
- Modify: `webapp/src/api/types.ts`, `webapp/src/api/AppApi.ts`, `webapp/src/api/mock/MockApi.ts`, `webapp/src/api/mock/fixtures.ts`, `webapp/src/ui/icons.ts`
- Test: `webapp/src/api/mock/MockApi.test.ts`

**Interfaces:**
- Produces:
  - `type DirectionIcon = 'film' | 'workshop' | 'book'`; иконки: `Clapperboard`, `Palette`, `BookOpen`.
  - `EventCard` += `accentColor: string | null; attendees: { count: number; avatars: string[] }` (avatars ≤ 3).
  - `Me` += `showInAttendees: boolean`.
  - `AppApi.setShowInAttendees(value: boolean): Promise<Me>`.
- Фикстуры: направления `{ id:'d-film', title:'Киновечер' }`, `{ id:'d-workshop', title:'Мастерклассы' }`, `{ id:'d-book', title:'Книжный клуб' }`. Событий 6: по два на направление, даты на 0, 2, 4, 9, 12, 20 дней вперёд (через `mskAt`), у одного `accentColor:'#2B6FFF'`, у одного `poster:null`, у одного `seatsLeft:0`; `attendees` у трёх — `{count: 23, avatars: [3 url из public/mock]}`, у остальных `{count: 0, avatars: []}`. Один валидный билет на событие «сегодня», один `used`, один `returned`.

- [ ] **Step 1: Тесты:** `directions()` возвращает три названия выше по порядку; `events()` у каждого есть `accentColor` и `attendees.avatars.length ≤ 3`; `setShowInAttendees(true)` → следующий `me()` даёт `showInAttendees: true`.
- [ ] **Step 2:** Прогон → FAIL.
- [ ] **Step 3:** Реализовать; поправить старые тесты экранов, ссылающиеся на прежние названия/id событий (только данные в ожиданиях, не логику).
- [ ] **Step 4:** Полный прогон → PASS; `npx tsc --noEmit` чисто.
- [ ] **Step 5: Commit** `feat(webapp): mock data for v2 — directions, accent colour, attendees`.

### Task 4: Ореол

**Files:**
- Create: `webapp/src/ui/Glow.tsx`, `webapp/src/ui/Glow.module.css`
- Modify: `webapp/src/App.tsx` (обернуть в `GlowProvider`, отрисовать `<Glow />` первым ребёнком `.app`)
- Test: `webapp/src/ui/ui.test.tsx`

**Interfaces:**
- Produces: `GlowProvider({children})`; `useGlow(color: string | null): void` — экран при монтировании задаёт цвет, при размонтировании сбрасывает в `null`; `<Glow />` — `position:fixed`, высота 60vh, `background: radial-gradient(130% 55% at 50% 0%, color-mix(in srgb, var(--poster) 55%, transparent), transparent 70%)`, `transition: background 400ms ease-out` (выключается при reduced motion); при `null` — `data-off` и прозрачный фон. Цвет ставится в `--poster` на `document.documentElement`.

- [ ] **Step 1: Тест** `it('glow takes the colour of the mounted screen and clears on unmount')`: компонент-заглушка вызывает `useGlow('#D4537E')` → `document.documentElement.style.getPropertyValue('--poster') === '#D4537E'`; после unmount → `''` и `<Glow>` с `data-off`.
- [ ] **Step 2–4:** FAIL → реализация → PASS.
- [ ] **Step 5: Commit** `feat(webapp): poster-colour glow`.

### Task 5: Таб-бар с иконками владельца

**Files:**
- Create: `webapp/src/ui/icons/NavIcons.tsx` (+ исходники `home.svg`, `heart.svg`, `profile.svg` из `C:\Users\Влад\Downloads\` в ту же папку как есть)
- Modify: `webapp/src/ui/TabBar.tsx`, `webapp/src/ui/TabBar.module.css`, `webapp/src/App.tsx`
- Test: `webapp/src/ui/ui.test.tsx`

**Interfaces:**
- Produces: `HomeIcon`, `HeartIcon`, `ProfileIcon` — `({ filled }: { filled: boolean }) => JSX.Element`, viewBox 24, 26 px; `filled` → `fill="currentColor" stroke="none"`, иначе `fill="none" stroke="currentColor" strokeWidth={1.7}`. Пути — дословно из SVG владельца (у `HomeIcon` в контурном режиме тот же путь штрихом).
- `TabBar({ hidden })` — вкладки `/` «Дом», `/favorites` «Избранное», `/me` «Кабинет»; только иконки в `<nav aria-label="Разделы">`, у каждой `NavLink` `aria-label` = название, активная получает `aria-current="page"`. Активная — цвет `#FFFFFF`, неактивные — `--text-3`. Капсула: высота 56, `max-width: 300px`, по центру, `bottom: calc(12px + env(safe-area-inset-bottom))`, фон `--tabbar`, обводка `1px solid var(--tabbar-border)`. Haptic `selection` по тапу.
- `App`: `TAB_PATHS = {'/', '/favorites', '/me'}`; `TabBar hidden={!TAB_PATHS.has(pathname)}` (без условия про main button). Маршруты `/favorites` и `/me` пока ведут на заглушки `null` — экраны в Task 6 и 12. Маршрут `/polls` удалить из `Routes`; `/tickets` → `<Navigate to="/me" replace />`.

- [ ] **Step 1: Тест** `it('tab bar: three icon tabs, active one filled white')`: рендер на `/favorites`; три ссылки с `aria-label` «Дом», «Избранное», «Кабинет»; у «Избранное» `aria-current="page"` и путь внутри с `fill="currentColor"`; у «Дом» `fill="none"`; текстовых подписей нет (`queryByText('Дом')` — null).
- [ ] **Step 2–4:** FAIL → реализация → PASS.
- [ ] **Step 5: Commit** `feat(webapp): Home/Favourites/Cabinet tab bar with owner icons`.

### Task 6: Избранное

**Files:**
- Create: `webapp/src/lib/favorites.ts`, `webapp/src/lib/favorites.test.ts`, `webapp/src/ui/FavButton.tsx`, `webapp/src/ui/FavButton.module.css`, `webapp/src/screens/Favorites.tsx`, `webapp/src/screens/Favorites.module.css`, `webapp/src/screens/Favorites.test.tsx`
- Modify: `webapp/src/App.tsx` (маршрут `/favorites`)

**Interfaces:**
- Produces:
  - `parseFavorites(raw: string | null): string[]` — не JSON / не массив / не строки → `[]`; дубликаты убрать; обрезать до 100 (оставить последние).
  - `useFavorites(): { ids: string[]; has(id: string): boolean; toggle(id: string): void }` — читает/пишет `tg.storage` ключ `'fav'` (JSON-массив), оптимистично, новые id в конец.
  - `FavButton({ eventId, size?: 36 })` — стеклянный круг, иконка `HeartIcon filled={has}`, `aria-pressed`, `aria-label` «В избранное» / «Убрать из избранного», haptic `impact('light')`.
  - `Favorites` — сетка 2 колонки: постер 4:5 + название (временная разметка в `Favorites.tsx`; в Task 8 заменяется на `PosterCard`), прошедшие в конце и десатурированы; пусто — `EmptyState` «Тут будут сохранённые вечера» / «Жми сердечко на афише — соберём всё здесь».
- [ ] **Step 1: Тесты:** `parseFavorites('oops')` → `[]`; `parseFavorites('{"a":1}')` → `[]`; `parseFavorites(JSON.stringify(Array.from({length:150},(_,i)=>'e'+i)))` → длина 100, первый `'e50'`; `toggle` дважды возвращает исходное состояние и пишет в storage; экран: пусто → текст пустого состояния; после `tg.storage.set('fav', '["<id события из фикстур>"]')` — карточка с его названием.
- [ ] **Step 2–4:** FAIL → реализация → PASS.
- [ ] **Step 5: Commit** `feat(webapp): favourites in CloudStorage`.

### Task 7: Мелкие компоненты витрины

**Files:**
- Create: `webapp/src/ui/StatusPill.tsx`, `AttendeesStack.tsx`, `FilterChips.tsx`, `DateStrip.tsx` (+ `.module.css` к каждому)
- Modify: `webapp/src/lib/format.ts` (`dayKey`, `shortDay`)
- Test: `webapp/src/ui/ui.test.tsx`, `webapp/src/lib/format.test.ts`

**Interfaces:**
- Produces:
  - `StatusPill({ kind: 'today' | 'left' | 'soldout', count?: number })` — тексты «Сегодня», «Осталось N» (через `plural` не нужно — «Осталось 12»), «Мест нет»; фон `rgba(0,0,0,.55)`, точка 6 px цвета `var(--poster)` у `today`/`left`.
  - `AttendeesStack({ count, avatars })` — до 3 аватаров 22 px с обводкой 1.5 px `#fff`, затем «+N», где N = `count − avatars.length`; `count === 0` → ничего; `aria-label` «Идут N человек» (через существующий `plural`).
  - `FilterChips({ items: {id,title}[], value: string | null, onChange(id: string | null) })` — первый чип «Все» = `null`; выбранный — белый фон, чёрный текст; `role="radiogroup"`; haptic `selection`.
  - `dayKey(iso: string, tz: string): string` → `'YYYY-MM-DD'` по Москве; `shortDay(dayKey): { dow: string; day: number }` → `{dow:'пн', day:13}`.
  - `DateStrip({ from: number, days: 14, marked: Set<string>, value: string | null, onChange(key: string | null) })` — пилюли `пн` / `13`, точка над днём, если `marked.has(key)`; выбранный белый; повторный тап → `onChange(null)`.
- [ ] **Step 1: Тесты:** `AttendeesStack count=23 avatars=3` → текст «+20»; `count=0` → пусто; `FilterChips` клик по «Мастерклассы» → `onChange('d-workshop')`, клик по «Все» → `onChange(null)`; `DateStrip` с `marked` одного дня → у ровно одной пилюли `data-marked`; повторный клик по выбранной → `onChange(null)`; `dayKey('2026-10-10T21:30:00Z','Europe/Moscow')` → `'2026-10-11'`.
- [ ] **Step 2–4:** FAIL → реализация → PASS.
- [ ] **Step 5: Commit** `feat(webapp): status pills, attendees, filter chips, date strip`.

### Task 8: Дом: billboard и ряды

**Files:**
- Create: `webapp/src/ui/Billboard.tsx`, `Billboard.module.css`, `webapp/src/ui/PosterRow.tsx`, `PosterRow.module.css`, `webapp/src/screens/Home.tsx`, `Home.module.css`, `Home.test.tsx`
- Modify: `webapp/src/lib/format.ts` (`billboardSubtitle`), `webapp/src/App.tsx` (`/` → `Home`); удалить `screens/Afisha*`, `ui/DirectionTile*`, `ui/Poster*` после переноса используемых частей.
- Test: `webapp/src/lib/format.test.ts`, `Home.test.tsx`

**Interfaces:**
- Consumes: `eventColor`, `extractPosterColor` (Task 2), `useGlow` (Task 4), `StatusPill`, `AttendeesStack`, `FilterChips`, `DateStrip`, `dayKey` (Task 7), `FavButton` (Task 6).
- Produces:
  - `billboardSubtitle(startsAt: string, tz: string, now: number): string` — тот же день → «Сегодня в 20:00»; завтра → «Завтра в 20:00»; в пределах 6 дней → «Уже в эту субботу» (день недели в винительном: «в этот понедельник/вторник/четверг», «в эту среду/пятницу/субботу», «в это воскресенье»); дальше → «чт, 16 окт в 20:00».
  - `Billboard({ events: EventCard[]; now: number; onColor(hex: string): void })` — до 3 слайдов, высота = 0.9 × ширина, радиус 20; meta «<направление> · 18+», `StatusPill` справа сверху, название `.t-billboard` слева снизу, подзаголовок `billboardSubtitle`, скрим; автосмена 6 с, пауза на `pointerdown` до `pointerup` + 6 с; точки только при ≥ 2 слайдах; 0 слайдов — не рендерится. На смене слайда вызывает `onColor(eventColor(...))`.
  - `PosterCard({ event: EventCard; variant: 'wide' | 'tall' })` — экспорт из `PosterRow.tsx`; в этой же задаче `Favorites` переводится на `PosterCard variant="tall"`.
  - `PosterRow({ title: string; variant: 'wide' | 'tall'; events: EventCard[] })` — горизонтальный скролл; `wide`: 16:9, ширина 82%, название и дата на постере; `tall`: 4:5, ширина 40%, подписи под постером; `FavButton` в углу; «Мест нет» — `filter: grayscale(1)`.
  - `Home` — `FilterChips` → `DateStrip` → `Billboard` (3 ближайших) → `PosterRow wide` «На этой неделе» (≤ 7 дней, без попавших в billboard) → `PosterRow tall` «Скоро» (остальные). Фильтры по направлению и дню применяются ко всем трём. Цвет ореола: `const [color, setColor] = useState<string|null>(null); useGlow(color)`, `Billboard onColor={setColor}`. Нет событий → `EmptyState` «Пока тихо» / «Новых вечеров нет. Как появятся — маякнём в боте.». Плашка брони (`ReservationPlaque` из Afisha — перенести) остаётся.
- [ ] **Step 1: Тесты:** `billboardSubtitle` для сегодня, завтра, +3 дня (суббота) и +10 дней; Home: на старте видно название ближайшего события в billboard и заголовки рядов «На этой неделе», «Скоро»; клик по чипу «Книжный клуб» оставляет только его события; `api` с пустыми событиями → «Пока тихо» и нет точек пагинации; одно событие → billboard без точек (`queryByRole('tablist')` null).
- [ ] **Step 2–4:** FAIL → реализация → PASS (таймеры — `vi.useFakeTimers`).
- [ ] **Step 5: Commit** `feat(webapp): home with billboard and poster rows`.

### Task 9: Пилюля «Сегодня» и нижняя панель вместо MainButton

**Files:**
- Create: `webapp/src/ui/TodayPill.tsx`, `TodayPill.module.css`
- Modify: `webapp/src/telegram/hooks.ts` (`useMainButton`), `webapp/src/telegram/tg.ts` (`MainButtonState` += `summary?: string`), `webapp/src/ui/InPageMainButton.tsx` → переименовать в `BottomBar.tsx` (+css), `webapp/src/App.tsx`, `webapp/src/test/render.tsx`
- Test: `webapp/src/telegram/hooks.test.tsx`, `webapp/src/ui/ui.test.tsx`

**Interfaces:**
- Produces:
  - `useMainButton(state)` — пишет только в `mainButtonStore`; `tg.mainButton.set` больше не вызывается. Поле `summary?: string` проходит насквозь.
  - `BottomBar()` — рисуется всегда, когда в сторе есть состояние: стеклянная панель, `bottom: calc(12px + env(safe-area-inset-bottom))`; слева `summary` (`.t-price`), справа `Button` primary (белая), `loading` → спиннер при той же ширине.
  - `pickTodayTicket(tickets: Ticket[], now: number): Ticket | null` — первый `status === 'valid'` с `dayKey(startsAt) === dayKey(now)` и `startsAt + 6 ч > now`.
  - `TodayPill()` — на путях из `TAB_PATHS`, если `pickTodayTicket` не `null`: стекло, миниатюра 28 px, «Сегодня · 23:00», название, иконка `QrCode`; тап → `/tickets/<id>`. Если есть живая бронь — вместо неё плашка брони (Task 8).
- [ ] **Step 1: Тесты:** `useMainButton` не вызывает `tg.mainButton.set` (spy) и кладёт `summary` в стор; `BottomBar` показывает summary и кнопку; `pickTodayTicket`: валидный сегодня → он; `used` сегодня → `null`; валидный сегодня, но `startsAt` 7 ч назад → `null`; завтра → `null`.
- [ ] **Step 2–4:** FAIL → реализация → PASS; полный прогон — экраны, искавшие кнопку через старый `InPageMainButton`, переключить на `BottomBar` в `test/render.tsx`.
- [ ] **Step 5: Commit** `feat(webapp): today pill; page-drawn bottom bar replaces MainButton`.

### Task 10: Экран события

**Files:**
- Create: `webapp/src/ui/PosterHeader.tsx`, `PosterHeader.module.css`
- Modify: `webapp/src/screens/EventScreen.tsx`, `EventScreen.module.css`, `EventScreen.test.tsx`; удалить `ui/PhotoHeader*`
- Consumes: `useGlow`, `eventColor` (+`extractPosterColor`), `FavButton`, `AttendeesStack`, `useMainButton` с `summary`.

**Interfaces:**
- `PosterHeader({ event })` — постер на всю ширину, высота 4:5 от ширины, нижние 40% — градиент в `#000`; стеклянные круги 40 px «назад» (слева) и `FavButton` (справа); снизу на постере meta, `.t-h1` название, «сб, 25 окт · 23:00». Без постера — блок цвета `eventColor` с иконкой направления.
- Порядок: `PosterHeader` → пилюли (возраст «18+», `AttendeesStack`) → «О вечере» → «Где» (адрес + ссылка «Построить маршрут» через `tg.openLink(mapUrl)`; адреса нет — «Адрес пришлём в бот») → «Билеты» (stepper как было) → `BottomBar`.
- `useMainButton`: 0 билетов → `text:'Купить'`, `summary:'от 1 500 ₽'`, клик скроллит к блоку «Билеты»; N > 0 → `summary: '3 билета · 4 650 ₽'`, клик — создание заказа как раньше; мест нет → `text:'Мест нет'`, `enabled:false`, `summary` нет. Голосование удалить.
- [ ] **Step 1: Тесты** (обновить существующие): нет блока голосования; при 0 билетов в панели «от …» и «Купить»; после «+» дважды — «2 билета · …»; событие с `seatsLeft:0` — «Мест нет» и кнопка недоступна; без адреса — «Адрес пришлём в бот».
- [ ] **Step 2–4:** FAIL → реализация → PASS.
- [ ] **Step 5: Commit** `feat(webapp): event screen v2`.

### Task 11: Бумажный билет и веер

**Files:**
- Create: `webapp/src/ui/PaperTicket.tsx`, `PaperTicket.module.css`, `webapp/src/ui/TicketFan.tsx`, `TicketFan.module.css`
- Modify: `webapp/src/screens/TicketScreen.tsx`, `TicketScreen.module.css`; новый `TicketScreen.test.tsx`
- Consumes: `Qr` (существующий), `eventColor`, `useGlow`.

**Interfaces:**
- `PaperTicket({ ticket, guestName: string | null, torn?: boolean })` — радиус 20, фон `--paper`; постер 16:10 с названием и датой; сетка 2×2 «Гость / Дата / Вход / Билет» (подпись `--paper-muted` 12 px, значение `--paper-ink` 15/500); перфорация `2px dashed var(--paper-perf)` (штрих 6, пробел 5) с вырезами Ø22 по краям через `mask: radial-gradient(circle 11px at 0 <y>, transparent 98%, #000) , radial-gradient(circle 11px at 100% <y>, …)`; корешок — `Qr` ≥ 240 px на белом с полями 16, короткий номер, «Билет 2 из 3». Состояния: `valid` — как выше; `used` — без корешка, пилюля «Было · 25 окт»; `returned`/`transferred`/`event_cancelled` — `grayscale(1)`, корешок без QR, пилюля «Возвращён» / «Передан» / «Вечер отменён».
- `TicketFan({ tickets, index, onIndex(i: number) })` — текущий по центру, соседи видны на 14%, `rotate(±6deg) scale(.92)`, opacity .6; свайп (pointer events, порог 40 px) и точки; `index` зажат в [0, n−1].
- `TicketScreen` — фон с ореолом цвета события, `TicketFan` по всем билетам того же заказа/события; анимация отрыва (`translateY(24px) rotate(4deg)` + исчезание, 500 мс) один раз на билет — флаг `torn:<id>` в `tg.storage`.
- [ ] **Step 1: Тесты:** `PaperTicket` `valid` → есть QR и «Билет 1 из 2»; `used` → нет QR, есть «Было ·»; `returned` → «Возвращён», нет QR; `TicketFan` с 3 билетами: `onIndex(5)` не выходит за 2, клавиша `ArrowRight` листает.
- [ ] **Step 2–4:** FAIL → реализация → PASS.
- [ ] **Step 5: Commit** `feat(webapp): paper ticket with perforation and fan`.

### Task 12: Кабинет

**Files:**
- Create: `webapp/src/screens/Cabinet.tsx`, `Cabinet.module.css`, `Cabinet.test.tsx`, `webapp/src/ui/ListRow.tsx`, `webapp/src/ui/Toggle.tsx` (+css)
- Modify: `webapp/src/telegram/tg.ts` (`TgFacade.user: { firstName: string; photoUrl: string | null } | null` из `initDataUnsafe.user`), `webapp/src/App.tsx` (`/me` → `Cabinet`); удалить `screens/Tickets*` после переноса.
- Consumes: `TicketFan`, `PaperTicket`, `useTickets`, `api.me`, `api.setShowInAttendees`.

**Interfaces:**
- Шапка: аватар 72 px (или инициал на `--surface-3`), имя `.t-h1`, «N вечеров с нами» (`plural` по числу `used`-билетов; 0 — строка не показывается).
- Разделы: «Мои билеты» — `TicketFan` действующих, тап → `/tickets/<id>`; пусто — «Билетов пока нет» / «Выбери вечер на главной — билет появится здесь.»; «Прошедшие · N» свёрнуто. «Мои вечера» — горизонтальный ряд `PaperTicket torn` уменьшенных до 0.5. «Поддержка» — `ListRow` «Написать организатору» (`tg.openTelegramLink` на бота) и «Как вернуть билет». «Приватность» — `Toggle` «Показывать меня в списке гостей», значение из `me.showInAttendees`, смена → `setShowInAttendees`.
- [ ] **Step 1: Тесты:** без `tg.user` — инициал не падает; с фикстурами — виден «Мои билеты» и один действующий билет; «Мои вечера» содержит «Было ·»; переключатель меняет `me().showInAttendees` на `true`.
- [ ] **Step 2–4:** FAIL → реализация → PASS.
- [ ] **Step 5: Commit** `feat(webapp): cabinet with tickets, history, support, privacy`.

### Task 13: Тексты, приветствие, статусные экраны

**Files:**
- Modify: `webapp/src/screens/Welcome.tsx` (+css), `OrderScreen.tsx` (+css), `MockPay.tsx`, `ClaimScreen.tsx`, `webapp/src/ui/EmptyState.tsx`, `ErrorState.tsx`, `State.module.css`, `Button.tsx`/`Button.module.css`, и тесты этих экранов.

**Interfaces:**
- `Button` варианты: `primary` (белый, чёрный текст), `secondary` (стекло), `link`; `outline` удалить, вызовы перевести на `secondary`; нажатие `scale(.98)` 120 мс.
- Все строки — дословно из таблицы §8 спеки v2 (приветствие, ожидание, успех «Ты в деле!», банк молчит, неуспех, нет сети, бронь истекла, мест меньше «Пока шёл выбор, осталось 2 места. Берём 2?» / «Берём 2» · «Изменить»). Приветствие: полноэкранный billboard ближайшего события + ореол, кнопка «Заходим». Статусные экраны: чёрный фон с ореолом цвета события, `.t-h1` по центру, `BottomBar`.
- [ ] **Step 1: Тесты** — обновить ожидаемые строки в `OrderScreen.test.tsx`, `MockPay.test.tsx`, `App.test.tsx` на новые; добавить `grep`-проверку в тест `copy.test.ts`: в `src/**/*.tsx` нет строк «Выберите», «Проверьте», «у вас», «Голосуем» (`import.meta.glob('./**/*.tsx', { as: 'raw', eager: true })`).
- [ ] **Step 2–4:** FAIL → реализация → PASS.
- [ ] **Step 5: Commit** `feat(webapp): 'ты' voice, welcome and status screens v2`.

### Task 14: Движение, фолбэки, финальная проверка

**Files:**
- Modify: `webapp/src/styles/global.css`, `webapp/src/main.tsx` (класс `.no-blur` по `hardwareConcurrency ≤ 4 || deviceMemory ≤ 3`), `webapp/README.md`, `docs/superpowers/STATUS.md`

- [ ] **Step 1:** В `global.css`: `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition-duration: 0ms !important; animation-duration: 0ms !important; } }`; `.no-blur .glass, @supports not (backdrop-filter: blur(1px))` → `background: var(--surface-3)`.
- [ ] **Step 2:** `npx tsc --noEmit` чисто; `npx vitest run 2>&1 | grep -E "Tests "` — все зелёные; `npm run build` проходит.
- [ ] **Step 3:** Ручная проверка в preview (`.claude/launch.json`), ширина 320 и 390: постер `public/mock/tiny.jpg` и белый постер — текст читается; событие без постера; `.no-blur` (добавить класс руками в DevTools); reduced motion. Скриншоты Дома, события, билета и кабинета — владельцу.
- [ ] **Step 4:** `STATUS.md` — этап «визуал v2» готов; в отложенное: миграции `events.accent_color`, `users.show_in_attendees`, `attendees` в API; README — новые маршруты `/`, `/favorites`, `/me`.
- [ ] **Step 5: Commit** `chore(webapp): reduced motion, no-blur fallback, status`.
