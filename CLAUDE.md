# CLAUDE.md
ВАЖНО! Пользователь не является разработчиком и не надо ему писать технические переменные и технические данные, код и прочую информацию, только если он сам не попросит. Писать только на языке аналитика

Индекс проекта. Детали по модулям подгружаются автоматически когда Claude входит в подкаталог.

## Карта детальных доков

| Где работаешь | Что читать |
|---|---|
| `app/models/` | [app/models/CLAUDE.md](app/models/CLAUDE.md) — 29 таблиц (6 групп), UUID + timestamp инварианты, M:N single-primary, AppSetting keys |
| `app/api/` | [app/api/CLAUDE.md](app/api/CLAUDE.md) — 27 routers (включая auth/users/admin/llm/teams/events/roles), паттерны (CRUD/batch/SSE), scenario flow, issue tree, ORM caveat |
| `app/services/` | [app/services/CLAUDE.md](app/services/CLAUDE.md) — CategoryResolver, MappingService, CapacityService, ResourceBaseService, EmployeeTeamService, ExportService, PlanningService, SyncService (+ Worklog buckets), AnalyticsService, BacklogService, ProductionCalendarService |
| `app/connectors/` | [app/connectors/CLAUDE.md](app/connectors/CLAUDE.md) — Jira API caveats: cursor pagination, field discovery, team filter probe, rate limiting, credentials resolution |
| `tests/` | [tests/CLAUDE.md](tests/CLAUDE.md) — conftest cleanup инвариант + endpoint test ORM caveat |
| `frontend/` | [frontend/CLAUDE.md](frontend/CLAUDE.md) — React 19 / TS 6 / Vite 8 / AntD 6, страницы, dark theme, error tracking, SyncPage / CategoryConfigTab / SettingsPage / CapacityPage |

## Project Context

Сервис анализа данных Jira Data Center и квартального планирования. MVP на SQLite, ORM-уровневая совместимость с PostgreSQL поддерживается.

**Целевой режим: многопользовательский.** Сервис будет опубликован для команды компании. Несколько сотрудников работают одновременно, у каждого своя команда (фильтрация по team). Синхронизация с Jira — общая, по расписанию. Все архитектурные решения принимаются исходя из этого режима: server-side push вместо client-only инвалидации, масштабируемость, изоляция данных по команде.

## Tech Stack

- **Backend:** Python 3.10+ (`py -3.10` на Windows) + FastAPI + SQLAlchemy 2.0 + Alembic
- **Database:** SQLite (MVP) → PostgreSQL (future)
- **HTTP Client:** httpx (async)
- **Frontend:** см. [frontend/CLAUDE.md](frontend/CLAUDE.md)

> Windows: `py -3.10 -m pytest` — pytest не установлен под дефолтным Python 3.14.

## Layer Architecture

```
Connector Layer → Service Layer → Repository Layer → Database
     ↓                 ↓                 ↓
  Jira API       Business logic     SQLAlchemy ORM
```

Ни один application-layer модуль не зависит от SQLite-specific фич.

## Project Structure

```
app/         backend (api/endpoints/, connectors/, models/, repositories/, services/)
frontend/    React SPA
alembic/     DB миграции
tests/       pytest backend
scripts/     local_smoke.py, smoke-local.ps1, e2e-local.ps1, seed_e2e.py
docs/        дизайн-доки, спеки, планы
```

`scripts/seed_e2e.py` создаёт `data/e2e.db` с `E2E Analyst` employee + `E2E` project.

## Code Principles

- All SQL через SQLAlchemy ORM — no raw SQL, no vendor-specific SQL
- All DB changes через Alembic миграции (batch mode для SQLite)
- Async где возможно (httpx, FastAPI)
- Type hints везде
- Docstrings на русском для бизнес-логики
- UUID string keys (`String(36)`) для всех таблиц
- Стандартные timestamps: `created_at`, `updated_at`, `synced_at`

## Runtime Configuration

- Backend settings грузит `app.config.Settings` из `.env`
- **Jira credentials:** AppSetting (DB) → `.env` fallback. UI пишет адрес и персональный токен в AppSetting через `PUT /settings/jira` (Confluence — отдельно, `PUT /settings/confluence`); `.env` подключается только для dev/CI когда DB пуста
- `DEBUG` prefers boolean; `dev/debug/local` → `true`, `prod/production/release` → `false`
- `CORS_ORIGINS` принимает JSON array или comma-separated list
- Frontend API base URL: `VITE_API_BASE_URL`, default `http://localhost:8000/api/v1`
- **Локальная копия прода и переезд на Jira DC:** после `alembic upgrade head` база с задачами получает `jira_migration_state = pending` — синк заблокирован, пока переезд не применён. Для локальной копии прода: либо пройти страницу переезда (`/admin/jira-migration`) против новой Jira из внутренней сети, либо взять свежий бэкап, снятый после переезда на проде. **Никогда** не ставить `jira_migration_state = done` руками в базе с облачными id — синк перезапишет чужие строки.

Подробности по AppSetting keys — см. [app/models/CLAUDE.md](app/models/CLAUDE.md).

## Jira Data Center

```
Base URL: https://jira.example.ru   (только из внутренней сети)
Версия:   11.3.7, REST API v2, вход по персональному токену (Bearer)
```

Пока база не переведена на идентификаторы новой Jira (AppSetting `jira_migration_state = pending`), синхронизация остановлена — см. [app/connectors/CLAUDE.md](app/connectors/CLAUDE.md).

## Commands

```bash
# Tests (Windows: use py -3.10)
py -3.10 -m pytest tests/ -v

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
.\scripts\smoke-local.ps1

# Browser E2E (uses seeded data/e2e.db; no Jira credentials required)
.\scripts\e2e-local.ps1 -InstallBrowsers  # first run
.\scripts\e2e-local.ps1

# Makefile shortcuts (make help for full list)
make dev | run | test | lint | format | migrate | migration msg='...' | clean | reset
```

Frontend команды — см. [frontend/CLAUDE.md](frontend/CLAUDE.md).

## CI

GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) на каждом push/PR:
1. `pytest` (Python 3.10)
2. Frontend lint + build (Node 20)
3. Playwright E2E

## Перед релизом — проверка безопасности (обязательно)

Перед каждым тегом релиза сервис проверяется двумя навыками (стоят в `~/.claude/skills/`):

1. **`github-security-review`** — оповещения GitHub по `kopyshok/jira-analytics`: Dependabot, CodeQL, secret scanning.
   Из папки навыка: `bash scripts/fetch.sh kopyshok/jira-analytics | python3 scripts/analyze.py`.
   Нужны `gh` и `jq` (winget, `%LOCALAPPDATA%\Microsoft\WinGet\Links`). `fetch.sh` поправлен локально под Windows — при переустановке навыка правку повторить.
2. **`semgrep-code-security`** — правила Semgrep (источник `semgrep/skills`, `skills/code-security`). Не сканер: по ним просматривается diff от прошлого тега — для Python и TS в первую очередь инъекции, path traversal, SSRF, XSS, секреты, JWT, Docker, GitHub Actions.

Critical/High из обоих — исправить до тега; остальное — в отчёт к релизу с решением, чинить или нет.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
