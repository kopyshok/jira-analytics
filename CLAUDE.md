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
- `frontend/src/` — React SPA: `api/`, `hooks/`, `pages/` (7), `components/`, `types/`, `utils/`
- `frontend/e2e/` — Playwright E2E tests (isolated `data/e2e.db`)
- `alembic/` — DB migrations
- `tests/` — pytest backend tests
- `scripts/` — smoke, E2E, seed scripts

## Database Schema

16 tables in 4 groups — see `app/models/` for full definitions:
- **Core (Jira sync):** employees, projects, issues, worklogs, comments, sync_state
- **Scope config:** scope_projects, scope_roots, category_overrides, worklog_quality_rules
- **Category mapping:** category_mappings
- **Planning:** vacations, monthly_capacity_rules, backlog_items, planning_scenarios, scenario_allocations

## API Endpoints

10 routers: sync, scope, analytics, mapping, capacity, backlog, planning, exports, employees, projects.
Full list: see `app/api/router.py`. Key patterns:
- CRUD: GET list + POST create, GET|PATCH|DELETE by id (backlog, capacity, scope)
- Exports: GET `/exports/analytics.xlsx|pdf`, `/exports/scenarios/{id}.xlsx|pptx`
- Planning: POST `/planning/scenarios/generate` (greedy allocation)

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
`openpyxl` / `reportlab` / `pptx` are **lazily imported inside methods** so a missing library doesn't break module import.
Analytics exports reuse `AnalyticsService`. Scenario exports reuse `PlanningService._team_capacity_hours`.

### PlanningService
Greedy backlog allocation by priority — items taken **whole** (no partial allocation).
Quarter stored as `"Q1"`.."Q4"` (string); API accepts integer `1..4`.
Commits internally — tests rely on conftest cleanup.

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

# Makefile shortcuts
make dev | run | test | migrate | clean

# Frontend
cd frontend && npm install
cd frontend && npm run dev     # dev server at :5173
cd frontend && npm run lint
cd frontend && npm run build   # production build
cd frontend && npm run e2e     # starts backend :8010 and frontend :5174
```

## Frontend Architecture

- All state is server state via TanStack Query — no Redux/Zustand
- Ant Design 6 with Russian locale (`antd/locale/ru_RU`)
- Route-level lazy loading; Quarter/Year via URL search params, not global state
- E2E: Playwright with isolated `data/e2e.db`, no Jira credentials needed
