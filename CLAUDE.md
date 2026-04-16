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
- `frontend/src/` — React SPA: `api/`, `hooks/`, `pages/` (7 routable: Dashboard, Sync, Analytics, Capacity, Backlog, Planning, Scope→redirects to Sync), `components/`, `types/`, `utils/`
- `frontend/e2e/` — Playwright E2E tests (isolated `data/e2e.db`); specs: `navigation`, `dashboard`, `crud-flows`, `export-downloads`
- `alembic/` — DB migrations
- `tests/` — pytest backend tests (services, schemas, reference endpoints, config, models)
- `scripts/` — `local_smoke.py`, `smoke-local.ps1`, `e2e-local.ps1`, `seed_e2e.py` (creates `data/e2e.db` with `E2E Analyst` employee + `E2E` project)

## Database Schema

18 tables in 5 groups — `app/models/__init__.py` is source of truth:
- **Core (Jira sync):** Employee, Project, Issue, Worklog, Comment, SyncState
- **Scope / category config:** ScopeProject, ScopeRoot, CategoryOverride, WorklogQualityRule, CategoryMapping, Category
- **Planning:** Vacation, MonthlyCapacityRule, BacklogItem, PlanningScenario, ScenarioAllocation
- **App state:** AppSetting (flat key-value store — see next section)

## API Endpoints

13 routers — `app/api/router.py` is source of truth. Patterns:
- **CRUD:** GET list + POST create, GET|PATCH|DELETE by id (backlog, capacity, scope, categories)
- **Browse Jira (live):** `/sync/jira-projects`, `/sync/jira-epics`, `/sync/jira-fields`, `/sync/jira-teams` — no DB write, proxy Jira with `in_scope` flags; `/jira-projects?team=X` uses per-project JQL probe (see SyncService notes)
- **Settings:** `/settings/jira` (GET|PUT, redacts token), `/settings/jira/test` (no save), `/settings/generic` (PUT) + `/settings/generic/{key}` (GET) — used for arbitrary runtime keys like `jira_team_field_id`, `jira_participating_teams_field_id`
- **Batch:** `/scope/projects/batch` — add/remove multiple at once
- **Exports:** `/exports/analytics.xlsx|pdf`, `/exports/scenarios/{id}.xlsx|pptx`
- **Planning:** `/planning/scenarios/generate` (greedy allocation)
- **Issue tree:** `/issues/tree`, `/issues/{id}/category`, `/issues/{id}/include` (drives CategoryConfigTab)

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
Formula: `available = workdays × hours_per_day − vacation_hours − mandatory_hours`, clamped to `max(0.0, ...)`.
MVP production calendar = Mon–Fri (`weekday() < 5`), no Russian holidays.
Vacation overlap via `max(start, month_start)` / `min(end, month_end)`.
`mandatory_hours = norm × percent_of_norm / 100` from `monthly_capacity_rules`.
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
Incremental sync via `sync_state.last_sync` per entity; JQL `updated >= "timestamp"` for deltas.
Rate limiting: 100ms delay between requests + exponential backoff on HTTP 429.
Batch size: 100 issues per Jira API request.

### AppSetting store
Flat key-value table. Known keys: `jira_email`, `jira_api_token`, `jira_base_url` (credentials), `jira_team_field_id`, `jira_participating_teams_field_id` (custom field IDs for team filter). Helpers `_get_setting`/`_set_setting` in `app/api/endpoints/settings.py` do get-or-insert. Settings endpoint always commits internally.

### Jira API (Atlassian Cloud)
Issue search uses `GET /rest/api/3/search/jql` — the old `GET /search` endpoint returns **410 Gone**.
The new endpoint may omit `total` in the response; pagination uses `len(issues) >= maxResults` heuristic (see `JiraSearchResponseSchema.has_more`).
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

# Lint / format
ruff check app/
ruff format app/

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
- **Merged Sync+Scope page** (`SyncPage.tsx`): `/scope` redirects to `/sync`. Three tabs — `TaskSectionsTab` (project browser with pending add/remove sets + batch save, two load modes: «Загрузить из Jira» respects team filter, «Загрузить все ключи» bypasses it), `CategoryConfigTab` (issue tree with inline category Select + include-in-analysis checkbox), `SyncControls` (manual full-sync / worklogs triggers). Team filter Select reads from `useJiraTeams` (populated from `/settings/generic/jira_team_field_id` + `jira_participating_teams_field_id`)
- E2E: Playwright with isolated `data/e2e.db` on non-standard ports (:8010 backend, :5174 frontend), no Jira credentials needed

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR:
1. `pytest` (Python 3.10)
2. Frontend lint + build (Node 20)
3. Playwright E2E
