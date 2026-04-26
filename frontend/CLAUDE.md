# Frontend CLAUDE.md

Guidance for Claude Code when working in `frontend/`.

## Stack

React 19 + TypeScript 6 + Vite 8 + Ant Design 6 (`darkAlgorithm`, ru locale) + TanStack Query + Recharts.

## Pages

8 routable in `pages/`: Dashboard, Sync, Analytics, Capacity, Backlog, Planning, Settings. `/scope` redirects to `/sync`.

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

## SyncPage (Sync + Scope merged)

Three tabs in `SyncPage.tsx`:
- **`TaskSectionsTab`** — project browser with pending add/remove sets + batch save. Two load modes: «Загрузить из Jira» respects team filter, «Загрузить все ключи» bypasses it.
- **`CategoryConfigTab`** — see below.
- **`SyncControls`** — «Обновить» = incremental default, «Полная синхронизация» = `incremental:false`, secondary; worklogs separately.

Team filter Select reads from `useJiraTeams` (populated from `/settings/generic/jira_team_field_id` + `jira_participating_teams_field_id`).

## CategoryConfigTab

Multi-team Select (`teams=A,B,C` OR'd in SQL, persisted via `ui_teams_categories` AppSetting). «Скрытые статусы» (default hides `Отменено`). Cancellable «Получить перечень задач» (cancel via `queryClient.cancelQueries` → AbortSignal → `fetch`). «Обновить с Jira (N)» — targeted `/sync/issues/refresh` on all non-group keys in the loaded tree.

**Four nested tabs** routed by effective category (own pending/assigned OR inherited from nearest ancestor — categorizing an epic drops its whole subtree out of «Стек»):
* `stack` — без категории
* `active` — с категорией, не архивная
* `archive_target` — «Архив квартальных задач»
* `archive` — «Архив прочих задач»

`matchesTab(effective, tab)` drives both filter and count. Row selection with `checkStrictly:false` cascades parent→children, disabled for group-nodes and `is_context` rows. «Установить категорию отмеченным» opens a modal → writes to `pendingCats` Map. Category Select stages into `pendingCats`; «Сохранить» batches PUTs via `/issues/batch-category` grouped by code and patches the tree cache locally (archive codes also clear `include_in_analysis`).

Row tint deepens per depth level (`.tree-row-depth-0..5`) and italicizes context rows (`.tree-row-context`). Key column is a Jira deep link (`${base_url}/browse/{key}`); status tag uses `statusTagColor` mapping Jira `statusCategory` + name-override for cancel-like statuses; «Статус изменён» sortable with date + «N д назад» age thresholds (≥180d yellow, ≥365d red); «Цели» sortable purple tag per comma-value. Columns resizable via `react-resizable`.

## SettingsPage

5 tabs — `connection` (ConnectionCard: Jira credentials via `/settings/jira`), `scope` (ScopeAdmin: scope projects + roots), `fields` (JiraFieldsCard: custom field IDs), `hierarchy` (HierarchyRulesTab: parent→child type rules CRUD + reorder), `calendar` (ProductionCalendarDay CRUD + «Синхронизировать» pulls official RU calendar). Active tab persisted in URL.

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
