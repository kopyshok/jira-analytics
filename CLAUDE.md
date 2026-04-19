# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

Local service for analyzing Jira Cloud data and quarterly planning.
MVP on SQLite, ORM-level PostgreSQL compatibility maintained.
Single-user mode for a project manager.

## Tech Stack

- **Backend:** Python 3.10+ (`py -3.10` on Windows) + FastAPI + SQLAlchemy 2.0 + Alembic
- **Database:** SQLite (MVP) → PostgreSQL (future)
- **HTTP Client:** httpx (async)
- **Frontend:** React 19 + TypeScript 6 + Vite 8 + Ant Design 6 + TanStack Query + Recharts

> On Windows use `py -3.10 -m pytest` — pytest is not installed under the default Python 3.14.

## Layer Architecture

```
Connector Layer → Service Layer → Repository Layer → Database
     ↓                 ↓                 ↓
  Jira API       Business logic     SQLAlchemy ORM
```

No application-layer module depends on SQLite-specific features.

## Project Structure

- `app/` — backend: `api/endpoints/`, `connectors/`, `models/`, `repositories/`, `services/`, `config.py`, `database.py`, `main.py`
- `frontend/src/` — React SPA: `api/`, `hooks/`, `pages/` (8 routable: Dashboard, Sync, Analytics, Capacity, Backlog, Planning, Settings, Scope→redirects to Sync), `components/` (incl. `capacity/AbsenceHeatmap`, `HierarchyRulesTab`, `ConnectionCard`, `JiraFieldsCard`, `ScopeAdmin`), `types/`, `utils/`
- `frontend/e2e/` — Playwright E2E tests (isolated `data/e2e.db`); specs: `navigation`, `dashboard`, `crud-flows`, `export-downloads`
- `alembic/` — DB migrations
- `tests/` — pytest backend tests (services, schemas, reference + targeted endpoint tests `test_api_*` / `test_*_endpoints`, config, models); shared sample data in `tests/fixtures/`
- `scripts/` — `local_smoke.py`, `smoke-local.ps1`, `e2e-local.ps1`, `seed_e2e.py` (creates `data/e2e.db` with `E2E Analyst` employee + `E2E` project)

## Database Schema

21 tables in 6 groups — `app/models/__init__.py` is source of truth:
- **Core (Jira sync):** Employee, EmployeeTeam (M:N, single-primary invariant), Project, Issue (user/Jira-metadata fields: `team`, `participating_teams` (JSON text), `assigned_category`, `include_in_analysis`, `out_of_scope` (Bucket B auto-ingest flag), `status_category` (Jira `new|indeterminate|done`), `status_changed_at` (from `statuscategorychangedate`), `goals` (comma-joined `customfield_11421`)), Worklog, Comment, SyncState
- **Scope / category config:** ScopeProject, ScopeRoot, CategoryOverride, WorklogQualityRule, CategoryMapping, Category (user-editable, seeded with 10 entries incl. `archive`, `archive_target`, `initiatives_rfa` — both archive codes in `ARCHIVE_CATEGORY_CODES` auto-drop `include_in_analysis` in single/batch category endpoints)
- **Hierarchy:** HierarchyRule (user-editable parent→child type rules that replace the hard-coded `CONTAINER_ISSUE_TYPES`; managed via `/settings` → «Иерархия»)
- **Capacity / planning:** Absence (was `Vacation`; migration 018; includes `reason` — see `ABSENCE_REASONS`), **MandatoryWorkType** (user-editable directory, seeded с 5 типами: organizational, management_admin, support_consult, tech_debt, technical_tasks), **RoleCapacityRule** (per (year, quarter, role?, work_type_id) — `role=NULL` = fallback «для всех»), **EmployeeCapacityOverride** (per (year, quarter, employee_id, work_type_id); приоритет выше role-rule), ProductionCalendarDay (per-day `hours` for RU calendar), BacklogItem, PlanningScenario, ScenarioAllocation
- **App state:** AppSetting (flat key-value store — see next section)

## API Endpoints

17 router includes in `app/api/router.py` (employees, projects, sync, jira, scope, analytics, mapping, capacity, backlog, planning, exports, settings, categories, issues, hierarchy-rules, production-calendar). Patterns:
- **CRUD:** GET list + POST create, GET|PATCH|DELETE by id (backlog, capacity, scope, categories, absences, hierarchy-rules, production-calendar)
- **Browse Jira (live):** `/sync/jira-projects`, `/sync/jira-epics`, `/sync/jira-fields`, `/sync/jira-teams` — no DB write, proxy Jira with `in_scope` flags; `/jira-projects?team=X` uses per-project JQL probe (see SyncService notes)
- **Settings:** `/settings/jira` (GET|PUT, redacts token), `/settings/jira/test` (no save), `/settings/generic` (PUT) + `/settings/generic/{key}` (GET) — used for arbitrary runtime keys (see AppSetting store)
- **Batch:** `/scope/projects/batch` — add/remove multiple at once
- **Exports:** `/exports/analytics.xlsx|pdf`, `/exports/scenarios/{id}.xlsx|pptx`, `/exports/capacity.xlsx`
- **Planning:** `/planning/scenarios/generate` (greedy allocation)
- **Targeted sync:** `POST /sync/issues/refresh` with `{jira_keys: [...]}` — re-reads only those keys in JQL `key in (...)` batches of 100, updates only rows that already exist locally (skips unknowns). Used by «Обновить с Jira» to dot-fill new fields without the 30-minute full resync.
- **Employees:** `GET /employees` list + `POST /employees/from-jira` (import from Jira user search), `POST /employees/recalc-active` (recompute active flag for all), `POST /employees/auto-detect-teams` (fill primary team from worklogs), `/employees/{id}/teams` M:N CRUD (GET/POST/PUT/DELETE `/{team}`) + `PUT /employees/{id}/teams/primary`; legacy `PUT /employees/{id}/team` kept as deprecated wrapper
- **Hierarchy rules:** `GET`/`POST`/`PATCH /{id}`/`DELETE /{id}` under `/hierarchy-rules` + `POST /hierarchy-rules/reorder`; consumed by issue-tree builder to decide container vs leaf types
- **Production calendar:** `GET /production-calendar?year=N` (list year), `PUT /production-calendar` (single-day manual upsert), `DELETE /production-calendar/{date}` (manual rows only), `POST /production-calendar/sync?year=N&overwrite_manual=false` (pull official RU calendar)
- **Issue tree:** `/issues/tree?project_keys=A,B&teams=T1,T2` (SQL-filtered by DB fields, teams OR'd); response includes **virtual group nodes** with `issue_type: 'group'` — `__orphans__` (parent_id set but parent excluded from DB) and `__operations__` (root leaf-type issues without children, i.e. childless non-container roots per `hierarchy_rules`). Also auto-pulls **ancestor context**: parents that fall outside the team filter get included with `is_context=true` so hierarchies stay legible; frontend renders them read-only. Mutations: `/issues/{id}/category`, `/issues/{id}/include`, `/issues/batch-category` (drives CategoryConfigTab). Archive codes (`archive`, `archive_target`) auto-drop `include_in_analysis` and are returned in `archived_ids`.

## Code Principles

- All SQL via SQLAlchemy ORM — no raw SQL, no vendor-specific SQL
- All DB changes via Alembic migrations (batch mode for SQLite)
- Async where possible (httpx, FastAPI)
- Type hints everywhere
- Docstrings in Russian for business logic
- UUID string keys (`String(36)`) for all tables
- Standard timestamps: `created_at`, `updated_at`, `synced_at`

## Runtime Configuration

- Backend settings are loaded by `app.config.Settings` from `.env`.
- **Jira credentials resolution order: AppSetting (DB) → `.env` fallback.** UI writes `jira_email`/`jira_api_token`/`jira_base_url` into AppSetting via `/settings/jira`; `.env` only kicks in for dev/CI when DB is empty.
- `DEBUG` prefers boolean values, but `dev/debug/local` map to `true` and `prod/production/release` map to `false`.
- `CORS_ORIGINS` accepts either a JSON array or a comma-separated list.
- The frontend API base URL is configured with `VITE_API_BASE_URL`; default is `http://localhost:8000/api/v1`.

## Key Architecture Details

### CategoryResolver
Priority: `category_overrides` → nearest `scope_roots` (walk up `parent_id`) → `worklog_quality_rules` → fallback.
Worklog inherits its issue's category.

### MappingService
Idempotently recalculates `category_mappings` table and the denormalized `Issue.category` field.
Commits internally — tests must clean tables after each run (see conftest).

### CapacityService
Formula: `available = norm_hours − absence_hours − mandatory_hours`, clamped to `max(0.0, ...)`.
`norm_hours` = сумма `production_calendar_day.hours` за период (8ч будни, 7ч предпраздничные, 0 выходные/праздники), масштабируется на `hours_per_day / 8`. Если в БД на дату нет записи — фоллбэк на `hours_per_day` для Пн–Пт. Source: `ProductionCalendarService`.
`absence_hours` = тот же расчёт по дням отпуска / болезни / других причин (`Absence.reason` ∈ `ABSENCE_REASONS`), перекрытие периода через `max(start, period_start)` / `min(end, period_end)`.
`mandatory_hours = norm_hours × total_percent / 100`, где `total_percent = Σ CapacityService.mandatory_percent_breakdown(employee, year, quarter).values()`. Breakdown резолвится per (employee, work_type) по приоритету: `employee_capacity_overrides` > `role_capacity_rules(role=e.role)` > `role_capacity_rules(role=NULL)` (fallback) > 0. Квартальное правило равномерно распределяется по месяцам через норму (чем больше `norm_hours_month`, тем больше вычет).
`fact_hours` — сумма `Worklog.hours` сотрудника за период; показывается отдельно и даёт plan/fact %.
Quarter mapping: `QUARTER_MONTHS = {1:(1,2,3), 2:(4,5,6), 3:(7,8,9), 4:(10,11,12)}`.

### ExportService
`openpyxl` / `reportlab` / `pptx` are **lazily imported inside methods** so a missing library doesn't break module import.
Analytics exports reuse `AnalyticsService`. Scenario exports reuse `PlanningService._team_capacity_hours`.

### PlanningService
Greedy backlog allocation by priority — items taken **whole** (no partial allocation).
Quarter stored as `"Q1"`.."Q4"` (string); API accepts integer `1..4`.
Commits internally — tests rely on conftest cleanup.

### SyncService
Dependency order: Projects → Issues (need projects) → Worklogs (need issues + auto-create employees).
Incremental sync via `sync_state.last_sync` per entity; JQL `updated >= "timestamp" ORDER BY updated ASC` for deltas.
Rate limiting: 100ms delay between requests + exponential backoff on HTTP 429.
Batch size: 100 issues per Jira API request.

**Custom field extraction:** `sync_issues` reads `jira_team_field_id`, `jira_participating_teams_field_id`, `jira_goals_field_id` from AppSetting and appends them to `fields=` on every Jira request. Values land in `JiraIssueFieldsSchema._extra`. Helper `_extract_team_values(extra, field_id)` handles the three shapes (`{value: X}`, `[{value: X}, ...]`, plain string) and powers team + goals. Written to `Issue.team` (first value), `Issue.participating_teams` (JSON-serialized list), `Issue.goals` (comma-joined string). `null` fields → `team=None`, `participating_teams='[]'`, `goals=None`.

**Per-upsert Jira metadata:** `_upsert_issue` also captures `status_category` from `status.statusCategory.key` and `status_changed_at` from `statuscategorychangedate` (parsed via `_parse_jira_datetime` into naive UTC).

**Targeted refresh:** `refresh_issues_by_keys(jira_keys)` re-reads given keys in JQL `key in (...)` batches of 100 using `iter_issues`, skips unknowns, reuses `_upsert_issue` — so any new field lands on the existing set without a full resync.

**ORM caveat:** after `db.commit()` the session expires attributes; touching them afterwards triggers a reload on a potentially thread-rotated connection (reproduced in tests: `:memory:` SQLite + TestClient async endpoints). In endpoints, **snapshot the fields you need into locals before the commit** (see `issue_config.set_issue_category`).

### Worklog sync dimensions

Два независимых прохода ворклог-синка:
- **Ведро A — issue-centric**: JQL `updated >= since`, upsert по локально существующим Issue. Ловит back-dated ворклоги за счёт перехода с `worklogDate` на `updated` — Jira двигает `issue.updated` при добавлении любого ворклога, включая записи с прошлым `started`.
- **Ведро B — employee-centric** (активируется параметром `teams`): для каждого Employee из `employee_teams.team IN teams` запускается JQL `worklogAuthor = <account> AND updated >= since`. Незнакомые Issue создаются с `out_of_scope=True`, их Project тоже автосоздаётся (без scope). Вне-scope задачи не попадают в CategoryConfigTab / дерево, но их ворклоги видны в Capacity/Analytics.

Два endpoint'а:
- `POST /sync/worklogs/update/stream` — новый, upsert-only, безопасен в повседневке. Принимает `{since, teams?}`. Запускает Ведро A всегда + Ведро B если teams указан.
- `POST /sync/worklogs/reload/stream` — жёсткая перезагрузка: `DELETE WHERE started_at >= since` + перечитать через `worklogDate >=` JQL. Нужно только если в Jira удалили ворклог и надо подчистить локальную копию.

Оба — SSE-стримы прогресса с событиями `progress` / `done` / `error` / `cancelled`. Cancel через `request.is_disconnected()` как в обычных sync-endpoint'ах.

### EmployeeTeamService

CRUD для M:N `employee_teams`. API: `list_teams`, `add_team`, `remove_team`, `set_primary`, `replace_teams`. Инвариант: ровно одна строка с `is_primary=true` на сотрудника (enforce в сервисе, не в БД — SQLite не поддерживает partial unique). Поле `Employee.team` — derived-колонка, обновляется синхронно с primary membership через `_recompute_legacy_team` для backward-compat с существующими запросами/экспортами до полного рефакторинга.

CRUD endpoint'ы: `GET /employees/{id}/teams` (list), `POST /employees/{id}/teams` (add), `PUT /employees/{id}/teams` (replace all), `DELETE /employees/{id}/teams/{team}` (remove one), `PUT /employees/{id}/teams/primary` (set primary). Legacy `PUT /employees/{id}/team` сохранён как обёртка над `replace_teams` с `deprecated=true` в OpenAPI.

Авто-определение команды по ворклогам (`auto_detect_team` / `auto_detect_all_missing`) пишет в primary membership через тот же сервис, что сохраняет инвариант.

### AppSetting store
Flat key-value table. Known keys:
- **Credentials:** `jira_email`, `jira_api_token`, `jira_base_url`
- **Jira custom field IDs:** `jira_team_field_id`, `jira_participating_teams_field_id`, `jira_goals_field_id` (seeded to `customfield_11421` by migration 012)
- **UI persistence:** `ui_team_projects` (TaskSectionsTab single team), `ui_teams_categories` (CategoryConfigTab multi-team, comma-joined) — hydrated on mount, written on every change so selections survive reloads.

Helpers `_get_setting`/`_set_setting` in `app/api/endpoints/settings.py` do get-or-insert. Settings endpoint always commits internally.

### Jira API (Atlassian Cloud)
Issue search uses `GET /rest/api/3/search/jql` — the old `GET /search` endpoint returns **410 Gone**.
**Pagination is cursor-based**, not offset-based: response carries `nextPageToken` and `isLast`; `startAt` is **ignored**. Passing `startAt` in a loop causes infinite re-reads of page 1. `JiraClient.search_issues` accepts `next_page_token`; `iter_issues` drives the loop via token + `isLast`. `JiraSearchResponseSchema.has_more` trusts `isLast` first, falls back to `nextPageToken`/`total`/length heuristic.
Pydantic response schema **requires** `summary/issuetype/status/project` — any call to `search_issues` must include them in `fields=` even when only probing existence.

### Jira field discovery
`JiraClient.get_field_configured_options(field_id)` is the **primary source** for distinct values of a select field — fetches `/field/{id}/context` + `/field/{ctxId}/option` (fast, complete, 46 teams vs. 22 via scan).
`get_field_distinct_values` falls back to a JQL scan (limited to 1000 recent issues, misses teams on stale issues) if contexts are unavailable.
`/sync/jira-teams` returns sorted union across both configured team fields.

### Team filter on `/sync/jira-projects`
Team filter cannot be a single global JQL (`ORDER BY project` + 1000-issue cap groups all results under the first project). Instead: iterate projects, probe each with `project = "K" AND (field1 = X OR field2 = X)` via `search_issues(max_results=1)`. Cost ~200ms × N projects but correct.

### Test Fixtures (tests/conftest.py)
`engine` — session-scoped in-memory SQLite.
`db_session` — function-scoped; **after each test explicitly deletes rows from all tables** (`table.delete()` in reverse order), because services like `MappingService` commit internally and a plain `rollback()` won't undo committed data.
If you add a service that commits internally — do NOT weaken this cleanup.

## Jira Cloud

```
Cloud ID: 604dc198-0f39-4cc9-bfbf-0a7cfdddd286
Base URL:  https://itgri.atlassian.net
```

## Commands

```bash
# Tests (Windows: use py -3.10)
py -3.10 -m pytest tests/ -v
py -3.10 -m pytest tests/test_capacity_service.py::TestMonthlyCapacity::test_vacation_inside_month -v

# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1

# Lint / format (make lint also runs mypy app/)
ruff check app/ tests/
mypy app/
ruff format app/ tests/

# Run server
uvicorn app.main:app --reload --port 8000

# Local full-stack smoke (starts missing servers and stops only its own)
py -3.10 scripts/local_smoke.py
# PowerShell wrapper:
.\scripts\smoke-local.ps1

# Browser E2E (uses seeded data/e2e.db; no Jira credentials required)
.\scripts\e2e-local.ps1 -InstallBrowsers  # first run
.\scripts\e2e-local.ps1

# Makefile shortcuts (make help for full list)
make dev | run | test | lint | format | migrate | migration msg='...' | clean | reset

# Frontend
cd frontend && npm install
cd frontend && npm run dev     # dev server at :5173
cd frontend && npm run lint
cd frontend && npm run build   # production build
cd frontend && npm run e2e     # starts backend :8010 and frontend :5174
```

## Frontend Architecture

- All state is server state via TanStack Query (staleTime 30s, retry 1) — no Redux/Zustand
- Ant Design 6 with Russian locale (`antd/locale/ru_RU`), `darkAlgorithm` theme
- Route-level lazy loading via `lazyPages.tsx`; Quarter/Year via URL search params, not global state
- Responsive grid: Ant Design `Col` with `xs/sm/lg` breakpoints; Sider auto-collapses on `lg`
- **Dark theme** (dark-dashboard style): tokens in `DARK_THEME` and `CHART_COLORS` (`utils/constants.ts`), configured in `main.tsx` via `ConfigProvider theme`. Page bg `#0d1c33`, cards `#0f2340`, sidebar `#091527`, primary cyan `#00c9c8`
- **Error tracking**: `errorStore.ts` captures API errors (network + HTTP); `BugReportButton` (FloatButton) shows reactive badge via `useSyncExternalStore`, copies markdown bug report to clipboard. Wired into `api/client.ts` interceptors.
- **Merged Sync+Scope page** (`SyncPage.tsx`): `/scope` redirects to `/sync`. Three tabs — `TaskSectionsTab` (project browser with pending add/remove sets + batch save, two load modes: «Загрузить из Jira» respects team filter, «Загрузить все ключи» bypasses it), `CategoryConfigTab` (see next bullet), `SyncControls` («Обновить» = incremental default, «Полная синхронизация» = `incremental:false`, secondary; worklogs separately). Team filter Select reads from `useJiraTeams` (populated from `/settings/generic/jira_team_field_id` + `jira_participating_teams_field_id`)
- **CategoryConfigTab**: multi-team Select (`teams=A,B,C` OR'd in SQL, persisted via `ui_teams_categories` AppSetting), «Скрытые статусы» (default hides `Отменено`), cancellable «Получить перечень задач» (cancel via `queryClient.cancelQueries` → AbortSignal → `fetch`), «Обновить с Jira (N)» (targeted `/sync/issues/refresh` on all non-group keys in the loaded tree). **Four nested tabs** routed by effective category (own pending/assigned OR inherited from nearest ancestor — categorizing an epic drops its whole subtree out of «Стек»):
  * `stack` — без категории
  * `active` — с категорией, не архивная
  * `archive_target` — «Архив квартальных задач»
  * `archive` — «Архив прочих задач»

  `matchesTab(effective, tab)` drives both filter and count. Row selection with `checkStrictly:false` cascades parent→children, disabled for group-nodes and `is_context` rows. «Установить категорию отмеченным» opens a modal → writes to `pendingCats` Map. Category Select stages into `pendingCats`; «Сохранить» batches PUTs via `/issues/batch-category` grouped by code and patches the tree cache locally (archive codes also clear `include_in_analysis`). Row tint deepens per depth level (`.tree-row-depth-0..5`) and italicizes context rows (`.tree-row-context`). Key column is a Jira deep link (`${base_url}/browse/{key}`); status tag uses `statusTagColor` mapping Jira `statusCategory` + name-override for cancel-like statuses; «Статус изменён» sortable with date + «N д назад» age thresholds (≥180d yellow, ≥365d red); «Цели» sortable purple tag per comma-value. Columns resizable via `react-resizable`.
- **API client AbortSignal**: `api.get(path, params, signal?)` threads AbortSignal into `fetch`. TanStack Query's queryFn context signal flows in via `useQuery({ queryFn: ({signal}) => ... })` in `useIssueTree`. `AbortError` skipped in `errorStore` so cancels don't flood the bug panel
- **SettingsPage**: 5 tabs — `connection` (ConnectionCard: Jira credentials via `/settings/jira`), `scope` (ScopeAdmin: scope projects + roots), `fields` (JiraFieldsCard: custom field IDs), `hierarchy` (HierarchyRulesTab: parent→child type rules CRUD + reorder), `calendar` (ProductionCalendarDay CRUD + «Синхронизировать» pulls official RU calendar). Active tab persisted in URL.
- **CapacityPage v2**: per-team hierarchy filter + active-employee toggle, month/quarter switch, heatmap (`AbsenceHeatmap`), copy-rules across months, xlsx export via `/exports/capacity.xlsx`, plan/fact/% breakdown by category; overload >110% coloured red.
- E2E: Playwright with isolated `data/e2e.db` on non-standard ports (:8010 backend, :5174 frontend), no Jira credentials needed

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR:
1. `pytest` (Python 3.10)
2. Frontend lint + build (Node 20)
3. Playwright E2E
