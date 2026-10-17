# Frontend CLAUDE.md

Guidance for Claude Code when working in `frontend/`.

## Stack

React 19 + TypeScript 6 + Vite 8 + Ant Design 6 (`darkAlgorithm`, ru locale) + TanStack Query + Recharts.

## Pages

Routable pages live in `pages/` and are lazy-loaded via [`lazyPages.tsx`](src/pages/lazyPages.tsx); routes wired in [`routes.tsx`](src/routes.tsx):

| Path | Page | Notes |
|---|---|---|
| `/` | `DashboardPage` | KPI + per-employee + heatmap |
| `/projects`, `/projects/:key` | `ProjectsPage` | Master-detail + AI summary |
| `/analytics` | `AnalyticsPage` | Иерархический отчёт |
| `/analytics/work-type-report` (+ `/print`) | `WorkTypeReportPage` / `…PrintPage` | |
| `/executive` | `ExecutiveDashboardPage` | KPI/тренды/риски |
| `/kpi` | `KpiPage` | Ведомость КЭ аналитиков + вкладки сотрудников. Период — месяц / квартал / последние N месяцев / свой отрезок (`KpiPeriodPicker` + чистые хелперы в [`utils/kpiPeriod.ts`](src/utils/kpiPeriod.ts)); в URL живут `kpiYear`/`kpiMonth`/`kpiMonths`. По умолчанию раздел скрыт — см. «Видимость разделов» |
| `/team-desk` | `TeamDeskPage` | Рабочий стол тимлида: три раскладки (Светофор / Ведомость / Проблемы вперёд), выбор раскладки — в `localStorage['team-desk-layout']`, вся шапка (команды, люди, режим среза, окно периода, переключатели «просмотренные» и «выполненные подзадачи», выбор статусов-счётчиков) — в профиле (`/users/me/team-desk-filter`). Счётчики статусов (`StatusCounters`) есть во всех трёх раскладках, клик фильтрует список задач по паре разработчик+статус; порядок статусов — `orderedStatuses` из `api/teamDesk.ts`. Над раскладками две компактные полосы-фильтра в одну строку: `FlagFilterBar` (замечания) и `StatusFilterBar` (итог по статусам на весь срез, клик снимает выбор человека) |
| `/sync` | `SyncHubPage` | Запуск + расписание + ворклог-backfill |
| `/categories` | `CategoriesEditorPage` | Разбор задач (бывший `CategoryConfigTab`) |
| `/scope` | redirect → `/sync` | |
| `/capacity` | `CapacityPage` | |
| `/backlog` | `BacklogPage` | Активные / В работе / Архив |
| `/planning` | `PlanningPage` | Сценарии |
| `/resource-planning` (+ `/compare`) | `ResourcePlanningPage` / `ScenarioComparatorPage` | |
| `/settings` | `SettingsPage` | admin-only |
| `/admin/jira-migration` | → `/settings#jira-migration` | переадресация из плашки «синхронизация остановлена» |
| `/desk/:token` | `DeskPage` | публичный рабочий стол аналитика — без авторизации и вне shell (отдельный top-level route) |
| `/login` | `LoginPage` | |

Source-of-truth для текущих роутов — [`routes.tsx`](src/routes.tsx); если что-то расходится с таблицей выше — фикси таблицу.

## Architecture Principles

- All state is server state via TanStack Query (staleTime 30s, retry 1) — no Redux/Zustand
- Route-level lazy loading via `lazyPages.tsx`; Quarter/Year via URL search params, not global state
- Responsive grid: AntD `Col` with `xs/sm/lg` breakpoints; Sider auto-collapses on `lg`
- API client base URL: `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`)

## Themes

Две темы, обе Aurora: `aurora-dark` (по умолчанию) и `aurora-light`. Классическая `dark-blue` удалена вместе с `ClassicShell`/`SideMenu` — оболочка теперь всегда `aurora/shell/AuroraShell`. Пункты меню, группы, скрытые разделы и активный пункт — в общем [`aurora/shell/navConfig.ts`](src/aurora/shell/navConfig.ts) (`NAV_GROUPS` + хук `useNavSections()`), им пользуется [`AuroraSidebar.tsx`](src/aurora/shell/AuroraSidebar.tsx) и любая другая оболочка. Список пунктов должен совпадать с `SECTIONS` в `VisibilityTab`.

Скин «Тёплая» (`warm-light`) — слой поверх Aurora light: на `<html>` остаются `data-theme="aurora"` + `data-mode="light"` и добавляется `data-skin="warm"` (у тем Aurora атрибута нет). Режим и скин темы берутся из `APP_THEMES[id].mode/skin`; `DARK_THEME`, `CHART_COLORS`, `FONTS` — Proxy, отдающие набор скина. Оболочка своя — [`skins/warm/shell/WarmShell.tsx`](src/skins/warm/shell/WarmShell.tsx) (+ `.css`, классы `wm-*`): `AppLayout` выбирает её по `useSkin()`, AuroraShell не тронута. Те же обязанности, что у AuroraShell (поток событий, синхронизация темы, справка, обратная связь, учёт, «Что нового»), то же меню из `navConfig` (свои значки по ключу пункта), те же `data-tour`; общие кнопки получают вид пропом с прежним поведением по умолчанию: `ThemeSelect variant="icon"`, `OnboardingButton labeled`, `FeedbackButton variant="pills"`. Остальной вид — CSS [`aurora/styles/skins/warm.css`](src/aurora/styles/skins/warm.css) под полным префиксом `html[data-theme][data-mode][data-skin]`, AntD — `buildWarmAntdConfig()`. Крючки для скина: классы `app-shell`/`app-main`/`scroll-y` у оболочки скина, `page-head-*` (у Aurora на них правил нет). Общие компоненты с цветами «под тёмную тему» берут цвет из переменной с прежним значением в запасе (`var(--fg-warn, #faad14)`, `--ui-divider`, `--header-icon`, `--empty-opacity`, `--heat-rgb` …): значения для Aurora light — в `glass.css`, для скина — в его CSS, у Aurora dark переменных нет. Шрифт Onest — локально из `@fontsource/onest`.

Раскладки страниц скина. Пять разделов (стол тимлида, аналитика, проекты, сценарии, ресурсное планирование) в «Тёплой» повторяют макеты C-* один в один: страница выбирает раскладку по `useSkin()` (`contexts/ThemeContext.tsx`; у Aurora — `null`, рендер прежний), данные/состояние/обработчики вынесены в один хук на страницу (`hooks/use{TeamDesk,Analytics,Projects,Planning,ResourcePlanning}Page.ts`) — его используют и раскладка Aurora, и раскладка скина `skins/warm/pages/*Layout.tsx` (+ `.css`; общие классы `wr-*` — `skins/warm/warm-layout.css`, `.wr-fit` = страница в экран, длинные блоки прокручиваются внутри). Компоненты получают вид скина без изменения Aurora: необязательный проп (`compact`, `variant="compact"`, `docked`) с прежним рендером по умолчанию или CSS-переменная с прежним значением в запасе (`var(--rp-surface, #0a1628)`; значения скина — в его CSS). Цвета из данных (роли, виды работ, категории, причины отсутствий, аватары) в скине — только через `readablePair(hex)` / `readableText(hex)` (`utils/readableColor.ts`): светлая подложка + тёмный текст того же оттенка, контраст ≥ 4,5:1. Новых правил по строке инлайн-стиля (`[style*=…]`) не добавлять.

`ThemeContext` ставит на `<html>` атрибуты `data-theme="aurora"` + `data-mode="dark|light"` (+ `data-skin` у скина); `DARK_THEME` — Proxy в `utils/constants.ts`, читающий их и отдающий нужный набор токенов. Прежние значения тем (`dark-blue`, `dark`, `dark-slate`, `dark-charcoal`) сводятся к `aurora-dark` и на фронте (`normalizeTheme`), и в БД (миграция `td03a`).

## Error Tracking

`errorStore.ts` captures API errors (network + HTTP); `BugReportButton` (FloatButton) shows reactive badge via `useSyncExternalStore`, copies markdown bug report to clipboard. Wired into `api/client.ts` interceptors. `AbortError` is skipped so cancels don't flood the bug panel.

## API Client AbortSignal

`api.get(path, params, signal?)` threads AbortSignal into `fetch`. TanStack Query's queryFn context signal flows in via `useQuery({ queryFn: ({signal}) => ... })` (see `useIssueTree`).

## SyncHubPage

Три вкладки в [`SyncHubPage.tsx`](src/pages/SyncHubPage.tsx):
- **«Синхронизация»** ([`PipelineRunner`](src/components/sync/PipelineRunner.tsx) + [`SyncHistory`](src/components/sync/SyncHistory.tsx)) — единая кнопка «Запустить» с режимами (быстрый / обычный / полный) + лента запусков (ручные + cron).
- **«Расписание»** ([`SyncSchedule`](src/components/sync/SyncSchedule.tsx)) — APScheduler-задачи (быстрый авто-синк каждые 2 ч).
- **«Дополнительно»** ([`SyncAdvanced`](src/components/sync/SyncAdvanced.tsx)) — ручной backfill ворклогов с даты + полная перезагрузка (единственный способ почистить worklog, удалённые в Jira).

Над вкладками — [`SyncBlockedAlert`](src/components/sync/SyncBlockedAlert.tsx): пока переезд на новую Jira не завершён (`useSyncBlocked()`, `GET /ui-config/jira-migration-state`), плашка со ссылкой на `/admin/jira-migration`; кнопки обновления из Jira здесь, в бэклоге и на столе тимлида неактивны.

Кнопки старого `SyncPage` (per-entity sync, scope-projects browser, jira-fields, recalc-mapping) удалены при M10 sync consolidation 2026-04-27. Категоризация задач переехала в `/categories` (`CategoriesEditorPage`). Пересчёт маппинга — **Настройки → Категории работ** (`CategoriesTab`).

## CategoriesEditorPage (`/categories`)

Multi-team Select (`teams=A,B,C` OR'd in SQL, persisted via `ui_teams_categories` AppSetting). «Скрытые статусы» (default hides `Отменено`). Cancellable «Получить перечень задач» (cancel via `queryClient.cancelQueries` → AbortSignal → `fetch`). «Обновить с Jira (N)» — targeted `/sync/issues/refresh` on all non-group keys in the loaded tree.

**Four nested tabs** routed by effective category (own pending/assigned OR inherited from nearest ancestor — categorizing an epic drops its whole subtree out of «Стек»):
* `stack` — без категории
* `active` — с категорией, не архивная
* `archive_target` — «Архив квартальных задач»
* `archive` — «Архив прочих задач»

**Ленивая загрузка** через [`useIssueLazyTree`](src/hooks/useIssueLazyTree.ts): `useIssueRoots`/`useIssueTreeCounts`/`useEpicCandidates`/`useLoadChildrenMutation`. Сервер отдаёт только корни активной вкладки (с `has_children`/`descendant_count`/`descendant_match_count`); потомки тянутся по `onExpand` через `/issues/{id}/children?tab=...`. Счётчики вкладок — отдельный запрос `/issues/tree/counts`. Поиск — server-side (`search` query param на roots). Старый `/issues/tree` страница больше не дёргает, но эндпоинт остаётся для других модулей. «Развернуть всё» отключено (info-сообщение). Все мутации в дереве (`include`/`verify`/`save pending`) → `qc.invalidateQueries(['issues','tree'])`, локальный patch удалён.

Tab routing — серверный (`_node_matches_tab` + walk-up по родителям в эндпоинте). Row selection с `checkStrictly:false` каскадирует parent→children, disabled для group-nodes и `is_context` rows. «Установить категорию отмеченным» → modal → пишет в `pendingCats` Map. Category Select stages в `pendingCats`; «Сохранить» батчит PUT'ы через `/issues/batch-category` (archive codes также снимают `include_in_analysis`). `setPendingCategory` cascade работает только на ЗАГРУЖЕННЫЕ потомки (`loadedChildren` map).

Row tint deepens per depth level (`.tree-row-depth-0..5`) and italicizes context rows (`.tree-row-context`). Key column is a Jira deep link (`${base_url}/browse/{key}`); status tag uses `statusTagColor` mapping Jira `statusCategory` + name-override for cancel-like statuses; «Статус изменён» sortable with date + «N д назад» age thresholds (≥180d yellow, ≥365d red); «Цели» sortable purple tag per comma-value. Columns resizable via `react-resizable`.

**Bulk drawer:** кнопка «Массовые операции» в тулбаре открывает [`BulkTriageDrawer`](src/components/categories/BulkTriageDrawer.tsx) с тремя секциями — архив по фильтру, принять подсказки, каскад от эпика. Хук [`useBulkTriage`](src/hooks/useBulkTriage.ts) держит мутации с общей инвалидацией (`issues/tree`, `backlog`, `planning`, `analytics`). Бэк: `/issues/bulk/{preview,archive,accept-suggestions,cascade-inherit}` — фильтр серверный (`BulkFilter` повторяет shape `/tree`). Используется на онбординге PM с большим стеком задач (6000+).

## SettingsPage (`/settings`, admin-only)

Навигация — левое `Menu mode="inline"` с группами (не `Tabs`); `Grid.useBreakpoint()` → на `<md` вместо меню `Select`. Рендерится только активная секция (`render()`), состояние неактивных не живёт. Группы и точные ключи — `GROUPS` в [`SettingsPage.tsx`](src/pages/SettingsPage.tsx):
- **Подключение**: `connection` (`ConnectionCard` — адрес + персональный токен) · `confluence` (`ConfluenceConnectionCard`) · `scope` (`ScopeAdmin`) · `fields` (`JiraFieldsCard`)
- **Справочники**: `hierarchy` · `reasons` · `categories` (**тут кнопка «Пересчитать маппинг по задачам»**) · `worktypes` · `calendar` (`ProductionCalendarTab`, + синк с RU календарём) · `kpi` (`KpiSettingsTab` — четыре вкладки: профили/конструктор метрики с `MetricPreview`/нормативы Cycle Time/общие правила; admin-only маршруты `/kpi-settings/*`)
- **Доступ**: `users` (admin) · `visibility`
- **Администрирование**: `jira-migration` (admin, [`JiraMigrationTab`](src/components/settings/jiraMigration/JiraMigrationTab.tsx) — пробный прогон, вкладки отчёта с решениями, «Применить», полная синхронизация, сверка) · `ai` · `feedback` (admin) · `usage` (admin) · `whats-new` (admin) · `db-export` (admin)

Активная секция зашита в URL-хеше; `adminOnly`-пункты вырезаются, пустые группы скрываются.

## CapacityPage v2

Per-team hierarchy filter + active-employee toggle, month/quarter switch, heatmap (`AbsenceHeatmap`), copy-rules across months, xlsx export via `/exports/capacity.xlsx`, plan/fact/% breakdown by category; overload >110% coloured red.

## E2E

Playwright with isolated `data/e2e.db` on non-standard ports (:8010 backend, :5174 frontend), no Jira credentials needed. Specs in `e2e/`: `navigation`, `dashboard`, `crud-flows`, `export-downloads`.

## Commands

```bash
npm install
npm run dev     # dev server :5173
npm run lint
npm run build   # production build
npm run e2e     # starts backend :8010 + frontend :5174
```
