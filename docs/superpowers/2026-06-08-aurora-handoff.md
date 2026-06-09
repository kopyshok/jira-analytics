# Aurora Redesign — Handoff для новой сессии

**Дата:** 2026-06-08
**Ветка:** `redesign/aurora` (запушена в origin, PR ещё не открыт)
**Статус:** Aurora-dark в основном работает. **Aurora-light сейчас работает криво — нужно дочинить.**
**Связанные документы:**
- Спека: [`docs/superpowers/specs/2026-06-08-aurora-redesign-design.md`](specs/2026-06-08-aurora-redesign-design.md)
- План: [`docs/superpowers/plans/2026-06-08-aurora-redesign.md`](plans/2026-06-08-aurora-redesign.md)
- Референс: [`design-reference/redesign/`](../../design-reference/redesign/) (направление A "Аврора")
- Материалы нового белого дизайна — пользователь подготовит отдельно, см. раздел «Open»

---

## 1. Что уже сделано

### 1.1 Архитектура темы

- `<html data-theme="classic|aurora" data-mode="dark|light">` — выставляется в [`frontend/src/contexts/ThemeContext.tsx`](../../frontend/src/contexts/ThemeContext.tsx) через `applyDomAttrs()`.
- `AppLayout` ([`frontend/src/components/Layout/AppLayout.tsx`](../../frontend/src/components/Layout/AppLayout.tsx)) — диспетчер: рендерит `AuroraShell` если `isAurora`, иначе `ClassicShell`.
- `AuroraShell` ([`frontend/src/aurora/shell/AuroraShell.tsx`](../../frontend/src/aurora/shell/AuroraShell.tsx)) — glass-сайдбар + топбар + content.
- `AppTheme` расширен: `'aurora-dark' | 'aurora-light'` + 4 classic. Default → `'aurora-dark'`.
- `User.selected_theme` (бэк) принимает aurora-* значения. Endpoint `PUT /users/me/theme`, валидация в [`app/api/endpoints/users.py`](../../app/api/endpoints/users.py).

### 1.2 Runtime tokens — ключевое решение

[`frontend/src/utils/constants.ts`](../../frontend/src/utils/constants.ts):
- `DARK_THEME` теперь **Proxy** — на каждый `.cardBg` / `.cyanPrimary` / etc. читает `<html data-theme>` + `data-mode` и возвращает соответствующий цвет из `DARK_THEME_CLASSIC` / `AURORA_DARK_TOKENS` / `AURORA_LIGHT_TOKENS`.
- `CHART_COLORS` — аналогичный Proxy с тремя палитрами.
- Все 69 файлов с импортом `DARK_THEME` / `CHART_COLORS` получают Aurora-цвета автоматически без точечных правок.
- AppLayout dispatcher размонтирует/смонтирует shell при `isAurora`-смене → все компоненты re-render → Proxy отдаёт свежие значения.

### 1.3 CSS-слой

[`frontend/src/aurora/styles/`](../../frontend/src/aurora/styles/):
- `glass.css` — Aurora CSS-vars (`--bg`, `--accent-1/2`, `--glass-bg`, `--text-*`, `--good/warn/bad`). Активны при `[data-theme="aurora"][data-mode="..."]`.
- `app.css` — `.side / .topbar / .gtable / .gtabs / .ginput / .badge / .seg / .pill / .gbtn`. Все scoped под `[data-theme="aurora"]`.
- `antdGlass.css` — overlay на `.ant-*` классы. **Сейчас здесь критическая часть, см. раздел 3 (баги).**
- `fonts.css` — Fraunces / Manrope / JetBrains Mono через `@fontsource`.
- `aurora.css` — entry point, импортирован в `main.tsx`.

### 1.4 Aurora-примитивы

[`frontend/src/aurora/primitives/`](../../frontend/src/aurora/primitives/): GlassCard, GlassButton, Pill, Badge, Track, GlowRing, NeonLine, GlassTabs, Segmented, GlassInput, Avatar, LucideIcon. Используются в shell, в LoginPage. По плану должны были использоваться по страницам — но было решено идти через Proxy + overlay (см. раздел 2).

### 1.5 Recharts

[`frontend/src/aurora/charts/`](../../frontend/src/aurora/charts/): `useChartTheme()` хук + `GlassTooltip` + `CHART_COLORS_AURORA`. Не интегрировано в существующие графики — следующий шаг.

### 1.6 Переключатель темы

- ClassicShell: кнопка «Aurora» (primary) рядом с AntD Select тем — `frontend/src/components/Layout/ClassicShell.tsx`.
- AuroraShell: `ThemeToggle` в топбаре (sun/palette/moon) — цикл aurora-dark → aurora-light → dark-blue → aurora-dark. Lucide-иконки.
- Хук `useSaveTheme` ([`frontend/src/hooks/useTheme.ts`](../../frontend/src/hooks/useTheme.ts)) — устойчивый (try/catch на API), также обновляет `user.selected_theme` через `updateUser()` чтоб `useThemeSync` не перезаписывал.

---

## 2. Вынужденные изменения / отказ от первоначального плана

### 2.1 Plan говорил «свои примитивы вместо AntD на страницах» — отказались

Original Phase 6-7 предполагал переписать каждую страницу под GlassCard/GlassButton/GlassTabs etc. После пары попыток стало ясно — это 2-3 недели работы для 13 страниц.

**Решение:** работать через два слоя:
1. **AntD overlay** (`antdGlass.css`) — перекрашивает `.ant-card`, `.ant-modal`, `.ant-drawer`, `.ant-tabs`, `.ant-input`, `.ant-select`, `.ant-table`, `.ant-tree` etc.
2. **Proxy DARK_THEME / CHART_COLORS** — все inline-стили `style={{ background: DARK_THEME.cardBg }}` автоматически возвращают Aurora-значения.

Результат: ~80% UI Aurora-стилем «бесплатно». Точечные hardcoded hex (`#0f2340`, `#0a1d3a` etc.) — заменены вручную где удалось найти (commit `8c2ed3e`).

### 2.2 PageHeader сам диспетчирует

[`frontend/src/components/shared/PageHeader.tsx`](../../frontend/src/components/shared/PageHeader.tsx) теперь проверяет `useAppTheme().isAurora` и рендерит Aurora-вариант (Fraunces 30px, eyebrow, без border-bottom) или classic. **Все 13 страниц получают Aurora-заголовок без правок per-page** (commit `10f891b`).

### 2.3 LoginPage — отдельный путь

LoginPage вне AppLayout-диспетчера. В нём прямо встроена ветка `isAurora ? GlassCard центр : классический`.

### 2.4 Тяжёлые компоненты (Gantt, Recharts графики) — отложены

Spec Q3 был «полная перерисовка Gantt-баров и графиков». Реально не сделано — Recharts графики получают Aurora-палитру через `CHART_COLORS` Proxy (цвета линий/баров), но сетка/оси/tooltip остаются classic. Gantt SVG bars — classic.

---

## 3. Известные баги (актуальные) — приоритет на починку

### 3.1 ⚠️ Aurora-light сейчас работает криво (USER REPORT)

Пользователь сказал «**белая тема сейчас работает криво**» и подготовил **новые материалы белого дизайна**. Что именно ломается — пользователь покажет в следующей сессии. Подозрения:
- Контраст `--text-muted` (`#707f9e`) на `rgba(255,255,255,0.55)` фоне — слишком слабый
- Тег/Pill `--pill-bg: rgba(255,255,255,0.6)` на белом — почти невидимый
- Modal `#f0f4fc` слишком близок к page bg `#eef2fb` — стирается граница
- `--glass-border: rgba(255,255,255,0.85)` — слишком белая, не видна на светлом фоне

**Ожидаемо:** пользователь отдаст новый набор токенов / новые цвета / новый дизайн-референс для светлой темы. Применить точечно в `frontend/src/aurora/styles/glass.css` блок `[data-theme="aurora"][data-mode="light"]` + `constants.ts` блок `AURORA_LIGHT_TOKENS`.

### 3.2 Модалки/drawer'ы — длинный сериал багов прозрачности

Серия из 9 коммитов (`d5f5ba5 → a5b9c2b`) починила прозрачность модалок. **Финальное состояние:**
- `.ant-modal-content + > * + .ant-modal-body/header/footer/title + [class*="ant-modal-section/confirm"]` — solid `#0f1426` (dark) / `#f0f4fc` (light) через `html[data-theme][data-mode]` selector (3 classes equiv specificity)
- `.ant-modal-mask / .ant-drawer-mask` — `rgba(5,8,16,0.65)` + blur(3px) (промежуточное затемнение)
- `.ant-modal-footer / .ant-drawer-footer` — solid тоже
- Popups: `.ant-dropdown-menu / .ant-select-dropdown / .ant-picker-dropdown / .ant-picker-panel-container / .ant-popover-inner / .ant-tooltip-inner` — solid `#161b30` (dark) / `#ffffff` (light)

**Корень проблемы:**
1. `:where(...)` selector имеет 0 specificity → AntD cssinjs `.css-dev-only-xxx.ant-modal-content` (2 classes) побеждал
2. Inline `styles={{ body: { background: DARK_THEME.cardBg } }}` через Proxy = `rgba(255,255,255,0.06)` semi-transparent — побеждал CSS через inline specificity. Убран в 6 файлах (commit `0c991ff`)

**Если в Aurora-light всплывут такие же баги** — путь: усиливать specificity через `html[data-theme][data-mode]` + убирать inline `styles.body.background` где AntD-modal/drawer передают через props.

### 3.3 Пинг-понг при переключении темы — пофикшен (commit `ef924bd`)

`useThemeSync` синхронизирует серверное `user.selected_theme` ровно один раз на login.id (через `useRef`). Раньше: каждый remount шелла применял старое серверное значение → откат aurora→classic→aurora.

### 3.4 Тёмная пустая область в pickers — пофикшен (commit `ef924bd`)

`.ant-select-selection-item / .ant-select-selection-placeholder / .ant-picker-input > input` не имели `color: var(--text)` — текст в select/date pickers был невидимым.

---

## 4. Не сделано (по плану, follow-up'ы)

### 4.1 Recharts графики на страницах

`useChartTheme()` и `GlassTooltip` существуют, но НЕ ПОДКЛЮЧЕНЫ к существующим графикам. Recharts графики (Dashboard, Executive, Analytics, WorkTypeReport) сейчас используют `CHART_COLORS` Proxy для CSS-цветов линий/баров, но:
- `<CartesianGrid stroke="#1e3356" />` — hardcode
- `<XAxis stroke="#8faec8" />` — hardcode
- `<Tooltip contentStyle={{...}} />` — classic AntD-style tooltip

**Чтобы дочинить:** в каждом chart-компоненте импортировать `useChartTheme()` и пробросить `gridStroke`, `axisColor`, `tooltipBg`, или подменить `<Tooltip>` на `<Tooltip content={<GlassTooltip />} />`.

### 4.2 Gantt SVG bars

`/resource-planning` — Gantt-бары используют hardcode fill. Spec предполагал градиент `linear-gradient(90deg, var(--accent-1), var(--accent-2))` + glow. Не сделано.

### 4.3 Heatmap классы

`AbsenceHeatmap` и dashboard heatmap не используют классы `.heat-over/.heat-warn/.heat-ok/.heat-good` из `app.css`. Сейчас они применяют hardcode rgba inline.

### 4.4 Иконки Lucide на страницах

Lucide подключён в shell (AuroraSidebar, ThemeToggle). На страницах остались `@ant-design/icons`. Не критично.

### 4.5 E2E

Файл `frontend/e2e/aurora.spec.ts` (13 страниц × 2 режима) написан, но ни разу не запущен. Run: `cd frontend && npm run e2e -- aurora.spec.ts`.

### 4.6 PR

Ветка `redesign/aurora` запушена. PR не открыт — gh не залогинен. Открывать вручную: https://github.com/kopyshok/jira-analytics/pull/new/redesign/aurora.

---

## 5. Ключевые файлы — карта

| Что | Где |
|---|---|
| Aurora CSS-vars (dark + light) | `frontend/src/aurora/styles/glass.css` |
| AntD overlay (modal/drawer/popup/select/tree) | `frontend/src/aurora/styles/antdGlass.css` |
| Runtime tokens (Proxy) | `frontend/src/utils/constants.ts` (DARK_THEME_CLASSIC / AURORA_DARK_TOKENS / AURORA_LIGHT_TOKENS) |
| Theme dispatch | `frontend/src/contexts/ThemeContext.tsx` (applyDomAttrs) |
| Save theme | `frontend/src/hooks/useTheme.ts` (useThemeSync + useSaveTheme) |
| Shell диспетчер | `frontend/src/components/Layout/AppLayout.tsx` |
| Aurora shell | `frontend/src/aurora/shell/{AuroraShell,AuroraSidebar,AuroraTopbar,AuroraPageHead,ThemeToggle}.tsx` |
| Classic shell (бывший AppLayout) | `frontend/src/components/Layout/ClassicShell.tsx` |
| Aurora primitives (12 шт) | `frontend/src/aurora/primitives/*.tsx` |
| ConfigProvider токены | `frontend/src/aurora/theme/auroraAntdTokens.ts` |
| PageHeader (диспетчер) | `frontend/src/components/shared/PageHeader.tsx` |
| LoginPage (отдельная aurora ветка) | `frontend/src/pages/LoginPage.tsx` |
| Recharts utils | `frontend/src/aurora/charts/{colors,GlassTooltip,useChartTheme}.{ts,tsx}` |
| Backend валидация темы | `app/api/endpoints/users.py` (VALID_THEMES set) |
| Backend схема | `app/schemas/user.py` (UserResponse.selected_theme) |

---

## 6. Стратегия для починки белой темы

1. **Получить новые материалы от пользователя** — он подготовил.
2. **Применить новую палитру в двух местах:**
   - `frontend/src/aurora/styles/glass.css` блок `[data-theme="aurora"][data-mode="light"]` — все `--bg`, `--text`, `--accent-1/2`, `--glass-bg`, `--glass-border`, `--good/warn/bad` etc.
   - `frontend/src/utils/constants.ts` блок `AURORA_LIGHT_TOKENS` — все DARK_THEME shape (cardBg, cyanPrimary, etc).
3. **Решить про solid bg для modal/popup в light:**
   - Сейчас `#f0f4fc` (modal content) и `#ffffff` (popups). Если новый дизайн просит другое — менять в `antdGlass.css` блоках `html[data-theme="aurora"][data-mode="light"]`.
4. **Если новый дизайн меняет акценты chart-колоров** — обновить `CHART_COLORS_AURORA_LIGHT_OVERRIDES` в `constants.ts` + `CHART_PALETTE_AURORA` если нужно (constants.ts + aurora/charts/colors.ts — два места).
5. **Smoke тест:** запустить dev (`cd frontend && npm run dev`), переключить в Aurora-light через `ThemeToggle`, обойти страницы.

---

## 7. Команды

```bash
# Запуск
cd frontend && npm run dev            # :5173
# Backend (если нужен)
uvicorn app.main:app --reload --port 8000

# Build / lint
cd frontend && npm run build
cd frontend && npm run lint

# Тесты
py -3.10 -m pytest tests/test_user_settings.py -v   # Aurora theme валидация
cd frontend && npx vitest run                       # unit

# E2E Aurora smoke (не запускался)
cd frontend && npm run e2e -- aurora.spec.ts
```

---

## 8. Что НЕ ломать при правках Aurora-light

- `DARK_THEME` Proxy в `constants.ts` — там 3 объекта `DARK_THEME_CLASSIC / AURORA_DARK_TOKENS / AURORA_LIGHT_TOKENS` одинаковой shape `DarkThemeShape`. **Не убирать ключи**, не менять имена — иначе сломаются 69 файлов.
- `useThemeSync` ref-guard — не возвращать к старой версии без ref, иначе пинг-понг переключения.
- `html[data-theme][data-mode]` specificity — не понижать до `:where(...)` ни в одном modal/drawer/popup правиле в `antdGlass.css`, иначе вернётся прозрачность.
- Inline `styles={{ body: { background: ... } }}` в `<Modal>` / `<Drawer>` — **не возвращать**, оно overrides CSS overlay (inline > !important от внешней CSS).

---

## 9. Open / TBD от пользователя

- **Новые материалы белого дизайна** — пользователь подготовит. Ожидается: палитра, токены, mockup'ы.
- Решить: оставлять ли цикл темы `aurora-dark → aurora-light → dark-blue` или убрать classic из цикла после полной готовности.
- Решить: оставлять ли отдельную кнопку «Aurora» в ClassicShell после того как Aurora приживётся (или удалить ClassicShell вообще).
