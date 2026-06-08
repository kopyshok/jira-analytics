# Aurora Redesign — Дизайн

**Дата:** 2026-06-08
**Статус:** черновик, ждёт ревью PM
**Ветка:** `redesign/aurora` (отдельная, PR в draft с самого начала; merge — опционально по итогам визуального ревью)

## 1. Цель

Полное визуальное преображение фронтенда под референс из `design-reference/redesign/` (направление A — «Аврора», stack glassmorphism + cyan→violet gradient, тёмная/светлая тема). Структура форм и функциональность сохраняются 1:1.

Пользователь переключает классику ↔ Aurora глобальной кнопкой в шапке. Выбор сохраняется на сервере per-user. Старый дизайн (`classic`) остаётся доступен на той же ветке.

## 2. Решения принятые на брейнсторме

- **Q1 Способ переключения:** глобальный тумблер в шапке, persisted per-user в БД.
- **Q2 Глубина:** замена примитивов — свои `<GlassCard>`, `<GlassButton>`, ... ; AntD остаётся внутри сложных форм/модалок и перетемизируется через ConfigProvider tokens.
- **Q3 Тяжёлые страницы (Gantt, charts, мега-таблицы):** полная перерисовка, не «обёртка + нативное ядро». Принимаем риск регрессий, чиним по ходу.

## 3. Архитектура

### 3.1 Слои

```
┌─────────────────────────────────────────────────────────┐
│ <html data-aurora="dark|light" | classic>               │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ThemeProvider (новый)                               │ │
│ │  ├─ AntD ConfigProvider                             │ │
│ │  │   ├─ classic: DARK_THEME (текущий)               │ │
│ │  │   └─ aurora-dark/light: auroraAntdTokens         │ │
│ │  ├─ глобальные стили:                               │ │
│ │  │   ├─ fonts.css (Fraunces, Manrope, JBMono)       │ │
│ │  │   ├─ glass.css (CSS-vars Aurora)                 │ │
│ │  │   ├─ app.css (.gtable, .gtabs, .ginput, .side)   │ │
│ │  │   └─ antdGlass.css (override .ant-* в Aurora)    │ │
│ │  └─ Shell:                                          │ │
│ │      ├─ classic → AppLayout (текущий)               │ │
│ │      └─ aurora  → AuroraShell (новый)               │ │
│ │           └─ Routes (те же 14 роутов, неизменно)    │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Расположение кода

```
frontend/src/aurora/
  styles/
    fonts.css            — @font-face Fraunces / Manrope / JetBrains Mono
    glass.css            — копия из reference (dir=a, dark+light), CSS-переменные
    app.css              — копия из reference (.side, .topbar, .gtable, .gtabs, .ginput, .badge, .seg)
    antdGlass.css        — overlay на .ant-*-классы под селектором [data-aurora]
    aurora.css           — единая точка входа (импортирует всё выше)
  primitives/
    GlassCard.tsx        — .glass обёртка с slot'ами (header, body, footer)
    GlassButton.tsx      — .gbtn / .gbtn-primary / .gbtn-ghost
    Pill.tsx             — .pill (с иконкой/индикатором)
    Track.tsx            — neon progress bar
    Badge.tsx            — .badge-good/warn/bad/accent/key
    GlassTabs.tsx        — .gtabs (с поддержкой ant-style controlled API)
    Segmented.tsx        — .seg
    GlassInput.tsx       — .ginput (text/search)
    GlowRing.tsx         — SVG progress ring из reference
    NeonLine.tsx         — SVG спарклайн из reference
    LucideIcon.tsx       — обёртка lucide-react
    Avatar.tsx           — градиентный аватар
  shell/
    AuroraShell.tsx      — layout (sidebar + topbar + content)
    AuroraSidebar.tsx    — навигация (NAV_GROUPS из текущего SideMenu)
    AuroraTopbar.tsx     — global team filter pill + period picker + theme toggle + user
    AuroraPageHead.tsx   — заголовок страницы (eyebrow + title + extra)
    ThemeToggle.tsx      — три состояния: classic / aurora-dark / aurora-light
  theme/
    auroraAntdTokens.ts  — токены ConfigProvider для двух Aurora-mod (dark + light)
    ThemeProvider.tsx    — новый, заменяет текущую логику в main.tsx
    useThemeMode.ts      — хук (читает из User.preferences, мутирует через api)
  index.ts               — публичный экспорт
```

### 3.3 Переключение темы

- Атрибут на корне DOM: `<html data-theme="classic">` | `<html data-theme="aurora" data-mode="dark">` | `<html data-theme="aurora" data-mode="light">`.
- `glass.css` использует `[data-theme="aurora"][data-mode="dark"]` и `[data-theme="aurora"][data-mode="light"]` (адаптация из `[data-dir="a"]` в reference).
- `antdGlass.css` целиком обёрнут в `:where([data-theme="aurora"]) .ant-... { ... }` — нулевая специфичность для классики.
- Шрифты Aurora грузятся всегда (preload), чтобы переключение было мгновенным.

### 3.4 Бэкенд

- Миграция: добавить `User.theme_preference VARCHAR(20)` default `'classic'`, допустимые значения через app-level enum: `classic | aurora-dark | aurora-light`.
- Расширить существующий `PUT /users/me/preferences` (уже принимает `selected_teams`) — принимает `theme_preference`.
- `/auth/me` возвращает поле в payload.
- Никаких других бэкенд-изменений: данные не меняются, только подача.

### 3.5 Зависимости (npm)

- `lucide-react` — иконки для Aurora-режима (классика остаётся на `@ant-design/icons`).
- `@fontsource/fraunces`, `@fontsource/manrope`, `@fontsource/jetbrains-mono` — self-hosted шрифты.

## 4. Логика переключения

1. При логине `/auth/me` отдаёт `theme_preference`.
2. `AuthProvider` пишет в `ThemeContext`.
3. `ThemeProvider` ставит `data-theme` / `data-mode` на `<html>`, выбирает Shell (классика/Aurora), подсовывает AntD tokens.
4. Кнопка `<ThemeToggle>` в шапке (видна всегда, в обоих режимах):
   - В классике: одна иконка «луна-палитра» с подписью «Aurora». Клик → `aurora-dark`.
   - В Aurora: цикл `aurora-dark → aurora-light → classic → aurora-dark`. Доступна также pill «классика» для прямого возврата.
5. Мутация `PUT /users/me/preferences { theme_preference }` через TanStack mutation; optimistic update DOM-атрибутов до подтверждения.
6. Anonymous (страница `/login`): только классика (нет user → нет preference). Aurora не применяется.

## 5. Дизайн-система Aurora

### 5.1 Токены

Полностью копируются из `design-reference/redesign/glass.css` блок `[data-dir="a"]`. Адаптация: селектор → `[data-theme="aurora"][data-mode="..."]`.

Переменные (dark / light):
- Фон: `--bg`, `--wash-1`, `--wash-2` (радиальные градиенты)
- Текст: `--text`, `--text-2`, `--text-muted`
- Акценты: `--accent-1` (cyan), `--accent-2` (violet), `--on-accent`, `--accent-border`, `--accent-glow`
- Стекло: `--glass-bg`, `--glass-border`, `--glass-sheen`, `--glass-shadow`, `--blur` (18px)
- Пиллы/треки: `--pill-bg`, `--pill-border`, `--track-bg`
- Статусы загрузки: `--good`, `--warn`, `--bad` (нагрузка >110% — красный, 70–110% — жёлтый, <70% — зелёный)
- Радиусы: `--radius` (20px), `--radius-sm` (12px), `--radius-pill` (999px)

### 5.2 Шрифты

- Display: **Fraunces** (заголовки страниц, числа KPI крупным кеглем)
- Body: **Manrope** (всё остальное)
- Mono: **JetBrains Mono** (числа в таблицах, ключи задач, ID)

### 5.3 Примитивы

| Компонент | Заменяет | Использование |
|---|---|---|
| `GlassCard` | `Card` | Все карточки, виджеты, обёртки страниц |
| `GlassButton` | `Button` (Aurora-режим) | Все кнопки |
| `Pill` | `Tag` (Aurora-режим) | Чипы, индикаторы статуса, мини-фильтры |
| `Badge` | `Tag` со статусом | Загрузка, состояния задач |
| `Track` | прогресс-бары | Бары нагрузки, прогресс |
| `GlowRing` | Donut / Progress | KPI-кольца дашборда |
| `NeonLine` | Recharts LineChart (в Aurora) | Тренды KPI |
| `GlassTabs` | `Tabs` | Все вкладки (Settings, Backlog, Categories, Capacity, Projects) |
| `Segmented` | `Segmented` | Переключатели режимов (quarter/year, фильтры) |
| `GlassInput` | `Input` (Aurora-режим) | Поля поиска в шапках страниц |
| `Avatar` | `Avatar` (Aurora-режим) | Аватары сотрудников |

**Сложные AntD-компоненты остаются нативными, но темизируются через ConfigProvider + antdGlass.css overlay:**
- `Form`, `Form.Item` (валидация, layout)
- `Modal`, `Drawer` (со стеклянным backdrop)
- `Select`, `DatePicker`, `TimePicker`, `Cascader`, `TreeSelect` (сложные popup-меню)
- `Table` (низкоуровневая таблица — в `.ant-table` лезем через overlay)
- `Tree` (lazy-tree категорий)
- `Notification`, `Modal.confirm`, `App.useApp()` контекст

## 6. Реcкин страниц (полный охват)

### 6.1 Шелл (обновляется для всех 14 страниц)

| Элемент | Изменение |
|---|---|
| Sidebar | `AuroraSidebar` — лейблы групп («Обзор», «Планирование», «Данные»), pills вместо AntD Menu items, glow на active |
| Topbar | `AuroraTopbar` — eyebrow + права: pill «синхронизировано» / «команда» / «период», theme toggle, аватар |
| PageHead | `AuroraPageHead` на каждой странице — заменяет текущий `PageHeader` |
| Версия | Pill в правом нижнем углу sidebar, как сейчас |

### 6.2 Перерисовка по страницам

**Обычные (форма + таблица, низкий риск):**
- `/login` — Aurora не применяется (anonymous), остаётся классика.
- `/settings` (11 вкладок) — каждая вкладка обёрнута в `GlassCard`. `GlassTabs` поверх AntD `Tabs` (controlled). Формы — нативные AntD с overlay-стилями (поля `.ant-input`, `.ant-select-selector` в стекле).
- `/sync` (3 вкладки) — `GlassCard` хост; PipelineRunner перерисован: большие glass-кнопки режимов, neon-track прогресса, лента истории с pill-статусами.
- `/feedback` (общедоступная) — список, фильтры, drawer; форма в `GlassCard`.
- `/capacity` — top-bar фильтров (Segmented quarter/month), heatmap-таблица перекрашена через `antdGlass.css` + heat-классы из reference; кнопки экспорта — `GlassButton`.
- `/backlog` (3 вкладки) — `GlassTabs`, карточки-инициативы как `GlassCard glass-hover` с pill «команда» / «приоритет».
- `/planning` — карточка сценария + матрица покрытия. Bars нагрузки заменены на `Track`. Approve celebration — glass-overlay.
- `/projects` (master-detail) — список слева как glass-cards; detail-панель — собрана из `GlassCard` секций (status / goals / employees / ratings / categories / top issues). Presentation view — отдельная страница, тоже Aurora.

**Тяжёлые (полная перерисовка, высокий риск):**

- `/` Dashboard:
  - 4 виджета (KPI per-project, per-employee, heatmap, hours balance) — заменены на Aurora-блоки.
  - KPI tiles → `GlowRing` + `NeonLine` спарклайн.
  - Heatmap (5×N) → таблица с классами `heat-over/warn/ok/good`.
  - Recharts графики остаются, но получают Aurora-палитру (`CHART_COLORS` v2: accent-1, accent-2, good/warn/bad из CSS-vars; рантайм-считывание через `getComputedStyle`).

- `/executive`:
  - KpiCard → `GlassCard` + `GlowRing` per metric.
  - RiskList → vertical list с pill-статусами.
  - AISummary секции → 3 столбца `GlassCard` с типографикой Fraunces для заголовков.
  - ModuleHealth → `Track` per module.

- `/analytics` (иерархический отчёт):
  - Master-detail layout сохраняется.
  - Левая колонка — `GlassCard` + кастомная мега-таблица: `.gtable` поверх AntD Table (overlay скрывает дефолтный chrome). Резизабельность колонок сохраняется.
  - KPI-tiles наверху → `GlowRing`.
  - WorklogsBlock — карточки с pill-статусами задач.
  - Drill-down anchors сохраняют логику; визуально — `Pill` с иконкой Lucide.

- `/analytics/work-type-report` (+ `/print`):
  - HierarchyTable перерисована как `.gtable` с подсветкой тем.
  - KpiRow → `GlassCard` row.
  - ThemeDistribution → `Track` per theme.
  - Print view — отдельные стили `@media print` поверх Aurora (упрощённая палитра без glow).

- `/categories` (lazy-tree, 4 вкладки):
  - `GlassTabs` сверху, поиск — `GlassInput` с иконкой Lucide search.
  - Дерево — AntD `Tree` с overlay (background, hover, expand-icons под Aurora).
  - Drawer массовых операций — нативный AntD Drawer с glass-backdrop.

- `/resource-planning` (Gantt, **наибольший риск**):
  - Sidebar 6 секций — переделать в `GlassCard` секции; ползунки внешнего вида (`AppearanceModal`) — нативные AntD Sliders в overlay.
  - GanttChart timeline header — `app.css`-стиль с pill-датами.
  - **Бары задач:** градиент `--accent-1 → --accent-2` + glow по краю; для конфликтных — `--bad` с red-glow; pinned — outline `--accent-border`.
  - **NonWorkingZones** (weekends) — полупрозрачный stripe-паттерн на `--glass-bg`.
  - **PertOverlay** — пунктирные `--accent-2` линии с glow.
  - **TrackGridlines** — `--glass-border` тонкими.
  - **EmployeeAvatar** в левой колонке — `Avatar` (градиент) + Pill ключа Jira.
  - **PlaneGantt** (alt view) — то же преобразование.
  - **EmployeeLoadHeatmap** — `Track` per day.
  - **BulkResetDropdown** — `GlassButton` ghost с Lucide chevron.
  - **ConflictPanel** — `GlassCard` + Badge counts.
  - `/compare` — две колонки `GlassCard`, diff-индикаторы через Pill.

### 6.3 Иконки

- В Aurora-shell и Aurora-примитивах: **Lucide** (`lucide-react`).
- В AntD-нативных компонентах внутри Aurora (Form, Modal, Drawer кнопки close): остаются `@ant-design/icons`. Через overlay перекрашиваются в `--text-2`.
- В классике: всё `@ant-design/icons` как сейчас.

## 7. Графики (Recharts)

Aurora-палитра для Recharts:
- Базовая: `CHART_COLORS_AURORA` — массив `[accent-1, accent-2, good, warn, bad, +5 ступеней градиента]`.
- Цвета считываются рантайм через `getComputedStyle(document.documentElement).getPropertyValue('--accent-1')` при смене темы — single source of truth.
- Tooltip — кастомный, в `.glass` обёртке.
- Grid lines — `--glass-border`.
- Axis text — `--text-muted`.

Альтернатива (опционально для отдельных виджетов): заменить Recharts линейные графики на `NeonLine` из reference. Решение per-widget в плане реализации.

## 8. Совместимость

- Классика остаётся **полностью функциональной**. Все 14 страниц работают так же, как до PR.
- Никаких изменений в данных, API endpoints (кроме расширения `/users/me/preferences`).
- Никаких изменений в роутах, query keys, мутациях, hooks.
- Cypress/Playwright E2E selectors (по `data-testid`, role, text) сохраняются.

## 9. Тестирование

### 9.1 Юнит/интеграция

- Тесты темы: `ThemeProvider` set `data-theme` атрибут, `useThemeMode` мутации.
- Тесты примитивов: `GlassButton`, `Pill`, `Badge`, `Track` — render snapshots + базовые props.
- Бэкенд: миграция, расширение `PUT /users/me/preferences`, валидация enum.

### 9.2 Visual smoke

- Playwright sweep по всем 14 роутам в трёх режимах: `classic`, `aurora-dark`, `aurora-light`. Screenshot каждой страницы (на seeded `data/e2e.db`).
- Проверка переключателя: клик в шапке → DOM-атрибут обновился → API mutation отправлена.

### 9.3 Регрессии (must)

- Все существующие E2E (`navigation`, `dashboard`, `crud-flows`, `export-downloads`) проходят в классике без изменений.
- Те же E2E прогоняются в Aurora-режиме (через `localStorage.setItem('theme_preference', 'aurora-dark')` перед login). Падения чинятся.
- Ручной smoke по тяжёлым страницам (`/resource-planning`, `/analytics`, `/categories`) — оба режима.

## 10. Откат

- PR в draft до финального ревью.
- Если PM отвергает после ревью: `git branch -D redesign/aurora` + закрыть PR. Main не затронут.
- Если приняли, но после нашли критические регрессии в проде: feature-flag через `AppSetting.aurora_enabled` (boolean, default true после merge). При false — `theme_preference` игнорируется, все видят классику. Включает админ.

## 11. Метрики готовности (definition of done)

- [ ] Кнопка переключения в шапке доступна авторизованному пользователю в любом режиме.
- [ ] Все 14 страниц рендерятся без runtime-ошибок в Aurora-dark и Aurora-light.
- [ ] Все формы (Settings, Sync, Backlog modal, Capacity drawers, Planning popovers, Projects filters, RP appearance modal) — функциональны (submit/cancel работает, валидация работает).
- [ ] Все 4 виджета дашборда отображают корректные числа.
- [ ] Resource Planning Gantt: бары видны, конфликты подсвечены, drag-операции работают.
- [ ] Analytics: drill-down с дашборда и executive ведёт на правильную секцию.
- [ ] Categories: lazy-tree разворачивается, массовые операции работают.
- [ ] Sync: «Запустить» в режимах быстрый/обычный/полный работает.
- [ ] Все existing pytest проходят (1090+ tests). Все existing E2E проходят в классике.
- [ ] Aurora-визуальный smoke (screenshots) утверждён PM.

## 12. План разбивки задач (для writing-plans)

Этапы будут детализированы планом, но укрупнённо:

1. **Foundation:** миграция, ThemeContext, ThemeProvider, ThemeToggle, импорт стилей и шрифтов, обёртка глобального layout.
2. **Primitives:** все компоненты в `aurora/primitives/`.
3. **Shell:** AuroraSidebar, AuroraTopbar, AuroraPageHead, AuroraShell wrapper.
4. **AntD theming:** `auroraAntdTokens.ts` + `antdGlass.css` для Form/Select/DatePicker/Table/Tree/Modal/Drawer/Notification.
5. **Reskin лёгких страниц:** Settings, Sync, Feedback, Capacity, Backlog, Planning, Projects, Login (login пропускается — anonymous).
6. **Reskin тяжёлых страниц:** Dashboard, Executive, Analytics (+ work-type-report), Categories, Resource Planning (+ compare).
7. **Recharts:** `CHART_COLORS_AURORA`, кастомный Tooltip, Grid/Axis токены.
8. **E2E + smoke:** добавить fixture для force-aurora-mode, прогнать в обоих режимах.
9. **Polish:** визуальный pass от PM, точечные фиксы.

## 13. Open questions

- Анимация переключения темы: instant vs 200ms fade? **Предложение:** instant в первой итерации (no FOUC), fade — follow-up.
- Aurora-light в принципе нужен? **Предложение:** да — это два клика, токены и шрифты общие, ценность для пользователей у которых тёмная тема вызывает усталость глаз.
- Login page включить в Aurora? **Предложение:** нет — anonymous, theme preference недоступен.
- Версия в sidebar: оставить старый компонент или Aurora-pill? **Предложение:** Aurora-pill в обоих режимах sidebar (унификация).
