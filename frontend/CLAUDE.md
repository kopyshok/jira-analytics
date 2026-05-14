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
| `/sync` | `SyncHubPage` | Запуск + расписание + ворклог-backfill |
| `/categories` | `CategoriesEditorPage` | Разбор задач (бывший `CategoryConfigTab`) |
| `/scope` | redirect → `/sync` | |
| `/capacity` | `CapacityPage` | |
| `/backlog` | `BacklogPage` | Активные / В работе / Архив |
| `/planning` | `PlanningPage` | Сценарии |
| `/resource-planning` (+ `/compare`) | `ResourcePlanningPage` / `ScenarioComparatorPage` | |
| `/settings` | `SettingsPage` | admin-only |
| `/login` | `LoginPage` | |

Source-of-truth для текущих роутов — [`routes.tsx`](src/routes.tsx); если что-то расходится с таблицей выше — фикси таблицу.

## Architecture Principles

- All state is server state via TanStack Query (staleTime 30s, retry 1) — no Redux/Zustand
- Route-level lazy loading via `lazyPages.tsx`; Quarter/Year via URL search params, not global state
- Responsive grid: AntD `Col` with `xs/sm/lg` breakpoints; Sider auto-collapses on `lg`
- API client base URL: `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`)

## Dark Theme

Tokens in `DARK_THEME` and `CHART_COLORS` (`utils/constants.ts`), configured in `main.tsx` via `ConfigProvider theme`. Page bg `#0d1c33`, cards `#0f2340`, sidebar `#091527`, primary cyan `#00c9c8`.

## Error Tracking

`errorStore.ts` captures API errors (network + HTTP); `BugReportButton` (FloatButton) shows reactive badge via `useSyncExternalStore`, copies markdown bug report to clipboard. Wired into `api/client.ts` interceptors. `AbortError` is skipped so cancels don't flood the bug panel.

## API Client AbortSignal

`api.get(path, params, signal?)` threads AbortSignal into `fetch`. TanStack Query's queryFn context signal flows in via `useQuery({ queryFn: ({signal}) => ... })` (see `useIssueTree`).

## SyncHubPage

Три вкладки в [`SyncHubPage.tsx`](src/pages/SyncHubPage.tsx):
- **«Синхронизация»** ([`PipelineRunner`](src/components/sync/PipelineRunner.tsx) + [`SyncHistory`](src/components/sync/SyncHistory.tsx)) — единая кнопка «Запустить» с режимами (быстрый / обычный / полный) + лента запусков (ручные + cron).
- **«Расписание»** ([`SyncSchedule`](src/components/sync/SyncSchedule.tsx)) — APScheduler-задачи (быстрый авто-синк каждые 2 ч).
- **«Дополнительно»** ([`SyncAdvanced`](src/components/sync/SyncAdvanced.tsx)) — ручной backfill ворклогов с даты + полная перезагрузка (единственный способ почистить worklog, удалённые в Jira).

Кнопки старого `SyncPage` (per-entity sync, scope-projects browser, jira-fields, recalc-mapping) удалены при M10 sync consolidation 2026-04-27. Категоризация задач переехала в `/categories` (`CategoriesEditorPage`). Пересчёт маппинга — **Настройки → Категории работ** (`CategoriesTab`).

## CategoriesEditorPage (`/categories`)

Multi-team Select (`teams=A,B,C` OR'd in SQL, persisted via `ui_teams_categories` AppSetting). «Скрытые статусы» (default hides `Отменено`). Cancellable «Получить перечень задач» (cancel via `queryClient.cancelQueries` → AbortSignal → `fetch`). «Обновить с Jira (N)» — targeted `/sync/issues/refresh` on all non-group keys in the loaded tree.

**Four nested tabs** routed by effective category (own pending/assigned OR inherited from nearest ancestor — categorizing an epic drops its whole subtree out of «Стек»):
* `stack` — без категории
* `active` — с категорией, не архивная
* `archive_target` — «Архив квартальных задач»
* `archive` — «Архив прочих задач»

`matchesTab(effective, tab)` drives both filter and count. Row selection with `checkStrictly:false` cascades parent→children, disabled for group-nodes and `is_context` rows. «Установить категорию отмеченным» opens a modal → writes to `pendingCats` Map. Category Select stages into `pendingCats`; «Сохранить» batches PUTs via `/issues/batch-category` grouped by code and patches the tree cache locally (archive codes also clear `include_in_analysis`).

Row tint deepens per depth level (`.tree-row-depth-0..5`) and italicizes context rows (`.tree-row-context`). Key column is a Jira deep link (`${base_url}/browse/{key}`); status tag uses `statusTagColor` mapping Jira `statusCategory` + name-override for cancel-like statuses; «Статус изменён» sortable with date + «N д назад» age thresholds (≥180d yellow, ≥365d red); «Цели» sortable purple tag per comma-value. Columns resizable via `react-resizable`.

## SettingsPage (`/settings`, admin-only)

Вкладки (порядок и точные ключи — [`SettingsPage.tsx`](src/pages/SettingsPage.tsx)):
- `connection` — `ConnectionCard` (Jira credentials)
- `scope` — `ScopeAdmin` (проекты + roots)
- `fields` — `JiraFieldsCard` (custom field IDs)
- `hierarchy` — `HierarchyRulesTab`
- `reasons` — `AbsenceReasonsTab`
- `categories` — `CategoriesTab` — **тут живёт кнопка «Пересчитать маппинг по задачам»**
- `worktypes` — `WorkTypesTab`
- `calendar` — `ProductionCalendarTab` (+ кнопка «Синхронизировать» с RU календарём)
- `ai` — `AITab`
- `visibility` — `VisibilityTab`
- `users` — `UsersTab` (только admin)

Активная вкладка зашита в URL.

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
