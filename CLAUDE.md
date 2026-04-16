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

```
jira-analytics/
├── app/
│   ├── api/endpoints/     # FastAPI routers (sync, scope, analytics, mapping, capacity, backlog, planning, exports, employees, projects)
│   ├── connectors/        # Jira HTTP client + Pydantic schemas
│   ├── models/            # SQLAlchemy models (16 tables)
│   ├── repositories/      # Data access layer
│   ├── services/          # Business logic (sync, category_resolver, mapping, analytics, capacity, planning, export)
│   ├── config.py          # Pydantic Settings
│   ├── database.py        # Engine + Session + Base
│   └── main.py            # FastAPI app
├── frontend/              # React + TypeScript SPA
│   ├── src/api/           # API client + domain modules
│   ├── src/hooks/         # TanStack Query hooks per domain
│   ├── src/pages/         # 7 pages (Dashboard, Analytics, Sync, Scope, Capacity, Backlog, Planning)
│   ├── src/components/    # UI components by feature area
│   ├── src/types/api.ts   # TS interfaces mirroring Pydantic schemas
│   └── src/utils/         # Constants (category labels/colors), formatters
├── alembic/               # DB migrations
├── tests/                 # pytest + pytest-asyncio
└── data/                  # SQLite file (gitignored)
```

## Database Schema (16 tables)

### Core entities (Jira sync)
- **employees** — id, jira_account_id, display_name, email, is_active, role, team, department
- **projects** — id, jira_project_id, key, name
- **issues** — id, jira_issue_id, key, summary, issue_type, status, parent_id, project_id, category
- **worklogs** — id, jira_worklog_id, issue_id, employee_id, started_at, hours
- **comments** — id, jira_comment_id, issue_id, author_id, body
- **sync_state** — incremental sync state

### Scope configuration
- **scope_projects** — allowed Jira projects (jira_project_key, is_enabled)
- **scope_roots** — root epics/issues for auto-categorization (category_code, jira_issue_key)
- **category_overrides** — per-issue category overrides (jira_issue_key, category_code)
- **worklog_quality_rules** — rules for detecting questionable worklogs (rule_code, threshold_value)

### Category mapping
- **category_mappings** — entity-to-category links (entity_type, entity_id, category, source_rule)

### Planning
- **vacations** — employee vacations (employee_id, start_date, end_date, hours_total)
- **monthly_capacity_rules** — mandatory work deductions as % of norm (month, year, percent_of_norm)
- **backlog_items** — quarterly backlog (title, project_id, quarter, year, estimate_hours, priority)
- **planning_scenarios** — planning scenarios (name, quarter, year)
- **scenario_allocations** — scenario results (scenario_id, backlog_item_id, planned_hours, included_flag)

## Work Categories

Priority order for category resolution:
1. Explicit issue override (`category_overrides`)
2. Nearest configured root epic/issue (`scope_roots`, walk up `parent_id`)
3. System quality rules (`worklog_quality_rules`)
4. Fallback: "unfilled / questionable worklogs"

Categories: Support & Consultation, Business Process Analysis, Non-development Meetings,
Administrative Waste, Internal Communications, Unfilled/Questionable Worklogs, Tech Debt / Other.

## API Endpoints

```
GET  /health
GET  /api/v1/

# Reference data
GET  /api/v1/employees?is_active=
GET  /api/v1/projects?is_active=

# Sync
GET  /api/v1/sync/test-connection
POST /api/v1/sync/projects | issues | worklogs | comments | full
GET  /api/v1/sync/status

# Scope
GET|POST   /api/v1/scope/projects
DELETE     /api/v1/scope/projects/{key}
GET|POST   /api/v1/scope/roots
DELETE     /api/v1/scope/roots/{id}
GET|POST   /api/v1/scope/overrides
DELETE     /api/v1/scope/overrides/{key}

# Mapping
POST /api/v1/mapping/recalculate
POST /api/v1/mapping/recalculate/issues
POST /api/v1/mapping/recalculate/worklogs

# Analytics
GET /api/v1/analytics/hours/by-employee|by-project|by-category|by-period
GET /api/v1/analytics/context-switching

# Capacity
GET|POST   /api/v1/capacity/vacations
DELETE     /api/v1/capacity/vacations/{id}
GET|POST   /api/v1/capacity/rules
DELETE     /api/v1/capacity/rules/{id}
GET /api/v1/capacity/monthly/{employee_id}?year=&month=
GET /api/v1/capacity/quarter/{employee_id}?year=&quarter=
GET /api/v1/capacity/team?year=&quarter=

# Backlog
GET|POST        /api/v1/backlog?year=&quarter=&project_id=
GET|PATCH|DELETE /api/v1/backlog/{id}

# Planning
GET    /api/v1/planning/scenarios?year=&quarter=
GET|DELETE /api/v1/planning/scenarios/{id}
GET    /api/v1/planning/scenarios/{id}/allocations
POST   /api/v1/planning/scenarios/generate

# Exports
GET /api/v1/exports/analytics.xlsx|pdf?start=&end=
GET /api/v1/exports/scenarios/{id}.xlsx|pptx
```

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
Returns ready bytes (xlsx/pdf/pptx); endpoints wrap in `Response` with correct MIME + `Content-Disposition: attachment`.
`openpyxl` / `reportlab` / `pptx` are **lazily imported inside methods** so a missing library doesn't break module import.
Analytics exports reuse `AnalyticsService`. Scenario exports reuse `PlanningService._team_capacity_hours` — numbers match POST `/planning/scenarios/generate`.
Scenario data loaded via `_load_scenario_rows` (join `ScenarioAllocation` ↔ `BacklogItem`); excluded items sorted after included.
Tests are smoke-only: open the file with the corresponding library and check key artifacts (sheets, headers, slide text); layout is not validated.

### PlanningService
Greedy backlog allocation by priority.
Quarter capacity = sum of `total_available_hours` from `CapacityService.team_quarter_capacity`.
Sort key: `(priority is None, priority, estimate_hours, title)` — lower priority value first, `None` last.
Items taken **whole** (no partial allocation): fits in remaining capacity → included, otherwise skipped (`reason="no_capacity_left"`).
Zero/empty estimate → `reason="no_estimate"`, skipped.
`ScenarioAllocation` saved for both included and skipped items (`included_flag` distinguishes them).
Commits internally — tests rely on conftest cleanup.
Quarter stored as `"Q1"`.."Q4"` (string); API accepts integer `1..4`.

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

# Makefile shortcuts
make dev | run | test | migrate | clean

# Frontend
cd frontend && npm install
cd frontend && npm run dev     # dev server at :5173
cd frontend && npm run lint
cd frontend && npm run build   # production build
```

## Frontend Architecture

- **State:** TanStack Query (React Query) — all state is server state, no Redux/Zustand
- **UI:** Ant Design 6 with Russian locale (`antd/locale/ru_RU`)
- **Charts:** Recharts (BarChart, PieChart, LineChart)
- **Routing:** React Router v7, 7 pages
- **Bundle:** route-level lazy loading for pages; AppLayout stays in the entry chunk
- **API client:** thin fetch wrapper at `frontend/src/api/client.ts`, base URL from `VITE_API_BASE_URL`
- **Quarter/Year:** URL search params (`?year=&quarter=`), not global state
- **Hooks pattern:** one file per API domain in `frontend/src/hooks/`, wraps API calls in `useQuery`/`useMutation`
