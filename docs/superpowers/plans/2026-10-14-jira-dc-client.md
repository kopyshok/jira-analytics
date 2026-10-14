# Jira DC Client + Sync Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести сервис с Jira Cloud на Jira Data Center 11.3.7 (клиент, схемы, парсеры синка, настройки, ссылки, Confluence) и запретить любой пишущий синк, пока база не переведена на новые идентификаторы (части A и B спеки `docs/superpowers/specs/2026-10-14-jira-dc-migration-design.md`).

**Architecture:** Сначала (Task 1–2) — блокировка: AppSetting `jira_migration_state`, единая проверка `ensure_sync_allowed(db)` в конструкторе `SyncService` (через него проходят все пишущие пути синка) плюс явная проверка в начале каждого пишущего HTTP-эндпоинта, чтобы ответ был 409, а не 500/оборванный поток. Затем обезличенные фикстуры из настоящих ответов DC, затем клиент (`Bearer`, `/rest/api/2`, поиск смещением, потоковое чтение ворклогов) и схемы (пользователь = DC `key`, логин `name` — в новой колонке сотрудника), затем парсеры синка (история изменений → «статус изменён» и дни паузы, иерархия через «Ссылку на эпик»/«Parent Link», московское настенное время ворклогов), затем ссылки, фронт, Confluence, документация.

**Tech Stack:** Python 3.10 (`py -3.10`), FastAPI, SQLAlchemy 2.0, Alembic (batch mode), httpx + respx, pytest (asyncio_mode=auto); React 19 / TS / Vite / AntD 6, TanStack Query, vitest.

---

## File Structure

### Создаются

| Файл | Ответственность |
|---|---|
| `app/services/jira_migration/__init__.py` | Пакет сервиса переезда (часть C добавит сюда свои модули) |
| `app/services/jira_migration/state.py` | Состояние переезда `pending`/`done`, `SyncBlockedError`, `ensure_sync_allowed`, `set_migration_state` |
| `alembic/versions/dc01_jira_sync_lock.py` | Ставит `jira_migration_state`: `pending` при задачах в базе, иначе `done` |
| `alembic/versions/dc02_employee_jira_username.py` | Колонка `employees.jira_username` (логин Jira DC) |
| `app/connectors/changelog.py` | Разбор `changelog.histories`: смены статуса, последняя смена категории, полнота истории |
| `scripts/make_dc_fixtures.py` | Обезличивание `data/jira_check.txt` → `tests/fixtures/jira_dc/*.json` |
| `tests/fixtures/jira_dc/*.json` | 18 обезличенных ответов DC |
| `tests/dc_fixtures.py` | `load_dc(name)` — чтение фикстур DC |
| `frontend/src/utils/jiraLinks.ts` (+ `.test.ts`) | Ссылка `<адрес>/browse/<ключ>` |
| `frontend/src/utils/syncBlocked.ts` | Текст плашки «синхронизация остановлена» |
| `frontend/src/components/shared/JiraIssueLink.tsx` | Ссылка на задачу с адресом Jira из настроек |
| `frontend/src/components/sync/SyncBlockedAlert.tsx` | Плашка со ссылкой на страницу переезда |
| `frontend/src/components/ConfluenceConnectionCard.tsx` | Карточка «адрес + токен» Confluence |
| Тесты: `tests/services/test_jira_migration_state.py`, `tests/test_migration_dc01_jira_sync_lock.py`, `tests/api/test_sync_blocked_endpoints.py`, `tests/test_dc_fixtures.py`, `tests/connectors/test_jira_dc_schemas.py`, `tests/test_employee_jira_username.py`, `tests/test_migration_dc02_employee_jira_username.py`, `tests/connectors/test_jira_dc_client.py`, `tests/test_settings_jira_endpoint.py`, `tests/connectors/test_changelog.py`, `tests/connectors/test_jira_dc_client_extras.py`, `tests/test_sync_status_changed_at.py`, `tests/test_sync_hierarchy_dc.py`, `tests/test_sync_wall_clock.py`, `tests/services/test_jira_links.py`, `tests/test_settings_confluence_endpoint.py` | |

### Меняются

| Файл | Что |
|---|---|
| `app/services/sync_service.py` | Проверка блокировки в `__init__`; автор ворклога/комментария → `_author_as_user`; «Разработчик» → `key`; логин сотрудника; Bucket B по логину; `expand=changelog` + `status_changed_at` из истории; дни паузы из поиска; автопоиск «Спринт»/«Ссылка на эпик»/«Parent Link»; родитель из трёх полей; устойчивая сортировка JQL; `_drop_tz` → московское время |
| `app/connectors/jira_client.py` | Полностью под DC: `Bearer`, `/rest/api/2`, `/search` со смещением, `iter_issue_keys`, `/project`, `/user/search?username=`, потоковые ворклоги, `/status`, `?expand=changelog`, `/customFields/{n}/options`, `jql_field_ref` |
| `app/connectors/schemas.py` | Пользователь DC (`key`, `name`), авторы = пользователь, `changelog` у задачи, поиск со смещением; убраны `statuscategorychangedate` и `JiraProjectsResponseSchema` |
| `app/models/employee.py` | `jira_username` |
| `app/main.py` | Обработчик `SyncBlockedError` → 409 |
| `app/api/endpoints/sync.py` | Проверка блокировки в пишущих эндпоинтах; проекты из `get_projects()`; фильтр команды через `cf[N]`; логин в поиске пользователей |
| `app/api/endpoints/team_desk.py`, `app/api/endpoints/backlog.py` | Проверка блокировки в обновлении задач |
| `app/api/endpoints/settings.py` | Jira без почты; настройки и проверка Confluence |
| `app/api/endpoints/ui_config.py` | `GET /ui-config/jira-migration-state` |
| `app/api/endpoints/employees.py` | Логин при добавлении сотрудника из Jira |
| `app/services/scheduler.py`, `app/jobs/backfill_issue_author.py`, `scripts/clear_stale_developer_field.py` | Пропуск при блокировке |
| `app/services/plan_common.py`, `app/services/work_desk_widgets.py`, `app/services/project_plan_service.py` | Ссылки на задачи из настроек |
| `app/connectors/confluence_client.py`, `app/services/confluence_service.py`, `app/services/project_summary_service.py` | Confluence DC: свой адрес и токен, Bearer, пути без `/wiki`, ссылки по адресу из настроек |
| `app/config.py`, `.env.example` | Без `JIRA_EMAIL` |
| `scripts/demo_db/anonymize.py` | Политика для `employees.jira_username` |
| Фронт: `ConnectionCard.tsx`, `api/settings.ts`, `api/uiConfig.ts`, `hooks/useSettings.ts`, `types/api.ts`, `types/desk.ts`, `pages/CapacityPage.tsx`, `pages/SettingsPage.tsx`, `pages/SyncHubPage.tsx`, `pages/BacklogPage.tsx`, `pages/TeamDeskPage.tsx`, `components/sync/{PipelineRunner,SyncAdvanced,SyncSchedule}.tsx`, `components/teamdesk/GroupedIssues.tsx`, 5 компонентов со ссылками, 2 виджета стола | |
| Доки: `app/connectors/CLAUDE.md` (переписан), `CLAUDE.md`, `app/models/CLAUDE.md`, `app/services/CLAUDE.md`, `app/api/CLAUDE.md`, `frontend/CLAUDE.md` | |

---

## Interfaces for the migration plan

Часть C (страница «Переезд на новую Jira») опирается только на то, что перечислено здесь. Всё появляется в задачах этого плана; номера задач указаны.

### Блокировка синка — `app/services/jira_migration/state.py` (Task 1–2)

- AppSetting `MIGRATION_STATE_KEY = "jira_migration_state"`, значения `STATE_PENDING = "pending"`, `STATE_DONE = "done"`. Строки нет → считается `done` (тестовые базы из `create_all`).
- `get_migration_state(db: Session) -> str` — `"pending"` или `"done"`.
- `is_sync_blocked(db: Session) -> bool`.
- `ensure_sync_allowed(db: Session) -> None` — поднимает `SyncBlockedError`, пока `pending`.
- `class SyncBlockedError(Exception)` — `str(exc) == SYNC_BLOCKED_MESSAGE == "Синхронизация остановлена до завершения переезда на новую Jira"`. Глобальный обработчик `app/main.py::sync_blocked_handler` отдаёт HTTP 409 `{"detail": SYNC_BLOCKED_MESSAGE}`.
- `set_migration_state(db: Session, state: str) -> None` — upsert строки + `db.flush()`, **без commit**; на значение не из `{pending, done}` — `ValueError`. «Применить» вызывает `set_migration_state(db, STATE_DONE)` внутри своей единой транзакции и коммитит её само.
- `SyncService(db, jira)` поднимает `SyncBlockedError` в конструкторе, пока `pending`. Код переезда **не создаёт `SyncService` до коммита `done`**. Полная синхронизация после применения — обычный конвейер (`build_pipeline(mode="full", services=...)` / `POST /api/v1/sync/pipeline {"mode": "full"}`) уже после коммита.
- Чтения Jira для переезда (`JiraClient` напрямую) блокировкой не ограничены.
- `GET /api/v1/ui-config/jira-migration-state` → `{"state": "pending" | "done", "sync_blocked": bool}` (любой залогиненный). Фронт держит его под ключом запроса `['ui-config', 'jira-migration-state']`; страница переезда после «Применить» инвалидирует этот ключ. Хук `useSyncBlocked()` в `frontend/src/hooks/useSettings.ts`.
- Плашка и заблокированные кнопки ведут на маршрут **`/admin/jira-migration`** — страницу и маршрут создаёт часть C.
- Миграции: `dc01_jira_sync_lock` (← `pf01_perf_metrics`), `dc02_employee_jira_username` (← `dc01_jira_sync_lock`). Первая миграция части C: `down_revision = "dc02_employee_jira_username"`.

### Клиент Jira DC — `app/connectors/jira_client.py` (Task 6, 8)

Все пути — относительно `API_PREFIX = "/rest/api/2"`. Async context manager (`async with JiraClient.from_db(db) as jira:`).

- `JiraClient.from_db(db)` — адрес `jira_base_url` + токен `jira_api_token` из AppSetting (fallback `.env`); почта не используется. `JiraClient(base_url: str | None = None, api_token: str | None = None, request_delay: float = 0.1, max_retries: int = 5)`. Заголовок `Authorization: Bearer <token>`.
- Исключения: `JiraClientError`; `JiraAuthError(JiraClientError)` на 401/403; `JiraRateLimitError(JiraClientError)` на исчерпанный 429.
- `async get_myself() -> JiraUserSchema` (`GET /myself`).
- `async get_projects() -> list[JiraProjectSchema]` — `GET /project`, массив целиком. `iter_projects()` — async-обёртка над ним.
- `async search_users(query: str, max_results: int = 20) -> list[JiraUserSchema]` — `GET /user/search?username=<query>&maxResults=<n>` (ищет по логину, имени, почте; только активные).
- `async get_fields() -> list[dict]` — без изменений (`GET /field`; у кастомного поля `id`, `name`, `schema.custom`, `schema.customId`, `clauseNames`).
- `async search_issues(jql: str, start_at: int = 0, max_results: int = 100, fields: list[str] | None = None, expand: str | None = None, lenient: bool = False) -> JiraSearchResponseSchema` — одна страница `GET /search`. По умолчанию строгий: ошибка в JQL — `JiraClientError` с пояснением Jira. `lenient=True` — по запросу вызывающего, шлёт `validateQuery=warn` (несуществующий ключ в `key in (...)` не роняет запрос); предупреждения Jira (`warningMessages`) пишутся в журнал.
- `async iter_issues(jql: str, max_results: int = 100, fields: list[str] | None = None, expand: str | None = None) -> AsyncIterator[JiraIssueSchema]` — листает `startAt` до `total`; если в JQL нет `ORDER BY`, добавляет `ORDER BY key ASC`.
- `async iter_issue_keys(jql: str, page_size: int = 1000) -> AsyncIterator[tuple[str, str]]` — пары `(key, id)` (`id` строкой), `fields=key`, без разбора схемой, та же устойчивая сортировка.
- `async iter_worklogs_updated_since(since_ms: int) -> AsyncIterator[JiraWorklogSchema]` — `GET /worklog/updated?since=` (по `lastPage`/`until`) → `POST /worklog/list` пачками `WORKLOG_LIST_BATCH = 1000`, потоком (пачка уходит, как только набралась). `since_ms=0` — все ворклоги Jira.
- `async get_worklogs_updated_since(since: datetime) -> AsyncIterator[JiraWorklogSchema]` — обёртка: `since_ms = int(since.timestamp() * 1000)`.
- `async iter_deleted_worklog_ids(since: datetime) -> AsyncIterator[int]`, `async iter_worklogs_for_issue(issue_id: str) -> AsyncIterator[JiraWorklogSchema]`, `async iter_comments_for_issue(issue_id: str)` — без изменений по смыслу.
- `async get_statuses() -> list[dict]` — `GET /status` (`id`, `name`, `statusCategory.key` ∈ `new|indeterminate|done`).
- `async get_issue_changelog(issue_key: str) -> dict` — `GET /issue/{key}?fields=status&expand=changelog` → объект `changelog` (`total`, `histories[{created, items[{field, from, fromString, to, toString}]}]`).
- `async get_status_changes(issue_key: str) -> list[tuple[str, str]]` — `(когда ISO, новый статус)` по возрастанию.
- `async get_field_configured_options(field_id: str) -> list[str]` — `GET /customFields/{n}/options`, включённые значения; ошибка/не кастомное поле → `[]`.
- `async get_field_distinct_values(field_id: str, max_issues: int = 1000) -> list[str]`.
- `async get_issue_types() -> list[dict]`, `async get_editable_field_ids(issue_key: str) -> set[str]`, `async test_connection() -> bool`.
- `jql_field_ref(field_id: str) -> str` — `"customfield_11092"` → `"cf[11092]"`, иначе имя в кавычках.

### Схемы — `app/connectors/schemas.py` (Task 4, 6, 9)

- `JiraUserSchema`: `jira_account_id: str` (из DC `key`, напр. `JIRAUSER12223`), `name: Optional[str]` (логин, напр. `Lebedev_A_A`), `display_name: str`, `email: Optional[str]`, `is_active: bool`, `avatar_url` (property). Создание: `JiraUserSchema.model_validate(raw)` или `JiraUserSchema(key=..., name=..., displayName=..., emailAddress=..., active=...)`. `JiraWorklogAuthorSchema` и `JiraCommentAuthorSchema` — псевдонимы `JiraUserSchema`.
- `JiraWorklogSchema`: `id: str`, `issueId: str`, `author: JiraUserSchema`, `started: str`, `started_datetime -> datetime` (aware; DC шлёт UTC `+0000`), `timeSpentSeconds: int`, `hours: float`, `created_datetime -> Optional[datetime]`, `comment_text`. (Имена атрибутов — как в ответе Jira: `issueId`, `timeSpentSeconds`.)
- `JiraIssueSchema`: `id`, `key`, `fields: JiraIssueFieldsSchema`, `changelog: Optional[dict]` (только при `expand="changelog"`). Кастомные поля — `fields._extra[field_id]`.
- `JiraProjectSchema`: `id`, `key`, `name`, `description`, `projectTypeKey`.
- `JiraSearchResponseSchema`: `startAt`, `maxResults`, `total`, `issues`, `has_more`.

### Сотрудники и люди в задачах (Task 4–5)

- `employees.jira_account_id` = DC `key`. Новая колонка `employees.jira_username: Optional[str]` (DC `name`) — синк обновляет при каждой встрече пользователя (и в кэшированных проходах). Ведро B ищет `worklogAuthor = "<jira_username>"`; сотрудник без логина в ведре B пропускается — так ведут себя непривязанные сотрудники с id `cloud:…`.
- `issues.assignee_account_id`, `issues.reporter_account_id`, `issues.developer_account_id` хранят DC `key`.
- `POST /api/v1/employees/from-jira` принимает `jira_username`; `GET /api/v1/jira/users/search` отдаёт `jira_username`.

### Время и поля (Task 9–11)

- `issues.status_changed_at` = время последнего перехода, сменившего **категорию** статуса (по `GET /status`), иначе `issues.jira_created_at`; naive UTC, как прочие даты задачи.
- `worklogs.started_at`, `worklogs.jira_created_at`, `comments.jira_created_at` после синка с DC хранят **московское настенное время** (как облако). Для отпечатков части C: значения из DC (UTC) переводятся `+03:00` только при записи синком; сырой `JiraWorklogSchema.started_datetime` — UTC.
- AppSetting `jira_sprint_field_id`, `jira_epic_link_field_id`, `jira_parent_link_field_id` синк заполняет сам по типу поля (`gh-sprint`, `gh-epic-link`, `jpo-custom-field-parent`), если значение пусто. «Применить» сбрасывает их (удаляет строки) вместе с `jira_customer_field_id` и `jira_cost_type_field_id`.
- Родитель задачи: `fields.parent.key` → «Ссылка на эпик» → «Parent Link» (строки-ключи).

### Confluence (Task 16)

- AppSetting `confluence_base_url`, `confluence_api_token`; `ConfluenceClient.from_db(db)` (Bearer), `async get_current_user() -> dict` (`GET /rest/api/user/current`) — годится для проверки возможностей.

### Тестовые фикстуры (Task 3)

- `tests/dc_fixtures.py::load_dc(name)`; файлы в `tests/fixtures/jira_dc/`: `server_info.json`, `issue_<KEY>.json` (OS-91030, OS-91031, RFA-4610, OS-92392, OS-93622, OS-89194, RFA-5020), `worklogs_<KEY>.json` (OS-91030, OS-91031, RFA-4610), `worklog_list.json`, `worklog_updated.json`, `search_count_OS.json`, `user_search.json`, `user_search_single.json`, `custom_field_options_error.json`, `fields.json`. Люди заменены на `JIRAUSER9NNNN` / `user_N` / `Сотрудник N` / `user_N@example.test`, адрес — `https://jira.example.test`; id задач и ворклогов настоящие.

---

## Conventions for every task

- Ветка: перед каждым коммитом `git branch --show-current` должен печатать `feature/jira-dc-migration`. Если нет — остановиться и спросить.
- Коммит: только `git add <пути>` + `git commit -m "<заголовок>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"` (второй `-m` даёт пустую строку перед подписью). Никогда `git commit -- <пути>`. `data/` не коммитить.
- Тесты: `py -3.10 -m pytest <файл>::<тест> -v`. Полный прогон: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py` (LLM-тесты висят без сети).
- Линтер бэка: `ruff check app/ tests/ scripts/make_dc_fixtures.py`.
- Фронт (из `frontend/`): типы — `npx tsc -b`; линтер по изменённым файлам — `npx eslint <файлы>` (весь `npm run lint` красный исторически); тесты — `npx vitest run <файл>`.
- Видимые пользователю строки на фронте — на русском, без технических терминов; уведомления AntD 6 — `title`, у `Alert` тоже `title`.

---

### Task 1: Состояние переезда и проверка в SyncService

**Files:**
- Create: `app/services/jira_migration/__init__.py`
- Create: `app/services/jira_migration/state.py`
- Create: `alembic/versions/dc01_jira_sync_lock.py`
- Modify: `app/services/sync_service.py:1-37` (импорт), `:645-656` (`SyncService.__init__`)
- Modify: `app/main.py:161-170` (обработчик рядом с `kpi_condition_error_handler`)
- Test: `tests/services/test_jira_migration_state.py`
- Test: `tests/test_migration_dc01_jira_sync_lock.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/test_jira_migration_state.py`:

```python
"""Состояние переезда на Jira DC: пока ``pending``, пишущий синк запрещён."""
import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.models.app_setting import AppSetting
from app.services.jira_migration.state import (
    MIGRATION_STATE_KEY,
    STATE_DONE,
    STATE_PENDING,
    SYNC_BLOCKED_MESSAGE,
    SyncBlockedError,
    ensure_sync_allowed,
    get_migration_state,
    is_sync_blocked,
    set_migration_state,
)
from app.services.sync_service import SyncService


def test_no_row_means_done(db_session):
    assert get_migration_state(db_session) == STATE_DONE
    assert is_sync_blocked(db_session) is False
    ensure_sync_allowed(db_session)


def test_pending_blocks_with_russian_message(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()

    assert is_sync_blocked(db_session) is True
    with pytest.raises(SyncBlockedError) as exc:
        ensure_sync_allowed(db_session)
    assert str(exc.value) == SYNC_BLOCKED_MESSAGE
    assert SYNC_BLOCKED_MESSAGE == "Синхронизация остановлена до завершения переезда на новую Jira"


def test_set_state_does_not_commit(db_session):
    """Применение переезда ставит done в своей транзакции — сеттер не коммитит."""
    set_migration_state(db_session, STATE_PENDING)
    assert is_sync_blocked(db_session) is True
    db_session.rollback()
    assert db_session.query(AppSetting).filter_by(key=MIGRATION_STATE_KEY).first() is None


def test_set_state_updates_existing_row(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()

    rows = db_session.query(AppSetting).filter_by(key=MIGRATION_STATE_KEY).all()
    assert [r.value for r in rows] == [STATE_DONE]


def test_unknown_state_rejected(db_session):
    with pytest.raises(ValueError):
        set_migration_state(db_session, "half")


def test_sync_service_refuses_while_pending(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    with pytest.raises(SyncBlockedError):
        SyncService(db_session, MagicMock())


def test_sync_service_allowed_when_done(db_session):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    SyncService(db_session, MagicMock())


def test_http_handler_returns_409():
    from app.main import sync_blocked_handler

    response = asyncio.run(sync_blocked_handler(None, SyncBlockedError()))
    assert response.status_code == 409
    assert json.loads(response.body) == {"detail": SYNC_BLOCKED_MESSAGE}
```

`tests/test_migration_dc01_jira_sync_lock.py`:

```python
"""dc01: состояние переезда — pending при задачах в базе, done на свежей установке.

Настоящая цепочка миграций на временной SQLite.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY = "jira_migration_state"


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _state(db_path: Path):
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT value FROM app_settings WHERE key = ?", (KEY,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def _insert_minimal(db_path: Path, table: str, values: dict) -> None:
    """Вставить строку, заполнив обязательные колонки без значения по умолчанию."""
    con = sqlite3.connect(db_path)
    try:
        row = dict(values)
        for _cid, name, col_type, notnull, default, pk in con.execute(f"PRAGMA table_info({table})"):
            if name in row or not (notnull or pk) or default is not None:
                continue
            kind = (col_type or "").upper()
            if any(t in kind for t in ("INT", "FLOAT", "REAL", "NUMERIC", "BOOL")):
                row[name] = 0
            elif "DATE" in kind or "TIME" in kind:
                row[name] = "2026-01-01 00:00:00"
            else:
                row[name] = f"{table}-{name}"
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        con.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))
        con.commit()
    finally:
        con.close()


def test_fresh_install_is_done(tmp_path):
    db = tmp_path / "fresh.db"
    _alembic(db, "upgrade", "dc01_jira_sync_lock")
    assert _state(db) == "done"


def test_existing_issues_make_pending(tmp_path):
    db = tmp_path / "with_issues.db"
    _alembic(db, "upgrade", "pf01_perf_metrics")
    _insert_minimal(db, "issues", {"id": "i1"})
    _alembic(db, "upgrade", "dc01_jira_sync_lock")
    assert _state(db) == "pending"


def test_existing_value_kept_and_downgrade_removes(tmp_path):
    db = tmp_path / "kept.db"
    _alembic(db, "upgrade", "pf01_perf_metrics")
    _insert_minimal(db, "issues", {"id": "i1"})
    _insert_minimal(db, "app_settings", {"id": "s1", "key": KEY, "value": "done"})
    _alembic(db, "upgrade", "dc01_jira_sync_lock")
    assert _state(db) == "done"

    _alembic(db, "downgrade", "pf01_perf_metrics")
    assert _state(db) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/test_jira_migration_state.py tests/test_migration_dc01_jira_sync_lock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration'`; миграционные тесты — `Can't locate revision identified by 'dc01_jira_sync_lock'`.

- [ ] **Step 3: Create the state module**

`app/services/jira_migration/__init__.py`:

```python
"""Переезд на Jira Data Center: состояние переезда и (часть C) пробный прогон и применение."""
```

`app/services/jira_migration/state.py`:

```python
"""Состояние переезда на Jira Data Center и единая проверка «синк разрешён».

Пока база не переведена на идентификаторы новой Jira (``pending``), любой
пишущий синк перезаписал бы чужие строки: id задач, ворклогов и людей в новой
Jira пересекаются со старыми id других записей. Поэтому все пишущие пути синка
проходят через :func:`ensure_sync_allowed` (конструктор ``SyncService`` и
явная проверка в начале пишущих эндпоинтов).
"""

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

MIGRATION_STATE_KEY = "jira_migration_state"
STATE_PENDING = "pending"
STATE_DONE = "done"
SYNC_BLOCKED_MESSAGE = "Синхронизация остановлена до завершения переезда на новую Jira"


class SyncBlockedError(Exception):
    """Синк запрещён до завершения переезда. HTTP-ответ — 409 (см. ``app.main``)."""

    def __init__(self) -> None:
        super().__init__(SYNC_BLOCKED_MESSAGE)


def get_migration_state(db: Session) -> str:
    """``pending`` или ``done``. Нет записи (база из ``create_all``) — ``done``."""
    value = (
        db.query(AppSetting.value)
        .filter(AppSetting.key == MIGRATION_STATE_KEY)
        .scalar()
    )
    return STATE_PENDING if value == STATE_PENDING else STATE_DONE


def is_sync_blocked(db: Session) -> bool:
    """Синк с Jira запрещён до завершения переезда."""
    return get_migration_state(db) == STATE_PENDING


def ensure_sync_allowed(db: Session) -> None:
    """Поднять :class:`SyncBlockedError`, если переезд не завершён."""
    if is_sync_blocked(db):
        raise SyncBlockedError()


def set_migration_state(db: Session, state: str) -> None:
    """Записать состояние переезда.

    **Не коммитит**: применение переезда ставит ``done`` в той же транзакции,
    что и перепривязку данных, — откат возвращает и состояние.
    """
    if state not in (STATE_PENDING, STATE_DONE):
        raise ValueError(f"Неизвестное состояние переезда: {state!r}")
    row = db.query(AppSetting).filter(AppSetting.key == MIGRATION_STATE_KEY).first()
    if row is None:
        db.add(AppSetting(key=MIGRATION_STATE_KEY, value=state))
    else:
        row.value = state
    db.flush()
```

- [ ] **Step 4: Guard the SyncService constructor**

In `app/services/sync_service.py`, after the line `from app.models.app_setting import AppSetting` (line 25) add:

```python
from app.services.jira_migration.state import ensure_sync_allowed
```

Replace the start of `SyncService.__init__` (lines 645–651):

```python
    def __init__(
        self,
        db: Session,
        jira_client: JiraClient,
        cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
    ):
        self.db = db
```

with:

```python
    def __init__(
        self,
        db: Session,
        jira_client: JiraClient,
        cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
    ):
        # Единая точка: каждый пишущий путь синка создаёт SyncService. Пока
        # база не переведена на id новой Jira, синк перезаписал бы чужие строки.
        ensure_sync_allowed(db)
        self.db = db
```

- [ ] **Step 5: Map the exception to HTTP 409**

In `app/main.py`, after the import `from app.services.kpi.conditions import ConditionError` (line 21) add:

```python
from app.services.jira_migration.state import SyncBlockedError
```

After the function `kpi_condition_error_handler` (ends at line 169, before `@app.exception_handler(Exception)`) add:

```python
@app.exception_handler(SyncBlockedError)
async def sync_blocked_handler(request, exc: SyncBlockedError) -> JSONResponse:
    """Синхронизация остановлена до переезда на новую Jira — 409 с понятным текстом."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})
```

- [ ] **Step 6: Create the migration**

`alembic/versions/dc01_jira_sync_lock.py`:

```python
"""Блокировка синхронизации до переезда на Jira Data Center

Revision ID: dc01_jira_sync_lock
Revises: pf01_perf_metrics
Create Date: 2026-10-14

Ставит AppSetting ``jira_migration_state``: ``pending`` в базе с задачами (их
идентификаторы облачные — синк с новой Jira перезаписал бы чужие строки),
``done`` на свежей установке. Уже заданное значение не трогает.

Самодостаточна: не импортирует код приложения.
"""
import uuid
from datetime import datetime
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "dc01_jira_sync_lock"
down_revision: Union[str, None] = "pf01_perf_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEY = "jira_migration_state"


def upgrade() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM app_settings WHERE key = :key"), {"key": _KEY}
    ).scalar()
    if exists:
        return
    has_issues = bind.execute(sa.text("SELECT 1 FROM issues LIMIT 1")).scalar()
    now = datetime.utcnow()
    bind.execute(
        sa.text(
            "INSERT INTO app_settings (id, key, value, created_at, updated_at) "
            "VALUES (:id, :key, :value, :now, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "key": _KEY,
            "value": "pending" if has_issues else "done",
            "now": now,
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM app_settings WHERE key = :key"), {"key": _KEY}
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/test_jira_migration_state.py tests/test_migration_dc01_jira_sync_lock.py -v`
Expected: PASS (11 tests).

Run: `py -3.10 -m pytest tests/test_sync_service.py tests/test_sync_service_v2.py tests/test_scheduler_trigger.py -q`
Expected: PASS — существующие тесты создают `SyncService` на базе без строки состояния (= `done`) или на `MagicMock`.

- [ ] **Step 8: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/__init__.py app/services/jira_migration/state.py alembic/versions/dc01_jira_sync_lock.py app/services/sync_service.py app/main.py tests/services/test_jira_migration_state.py tests/test_migration_dc01_jira_sync_lock.py
git commit -m "feat(sync): блокировка синка до переезда на Jira DC" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Проверка во всех пишущих точках входа + состояние для интерфейса

Конструктор `SyncService` уже отказывает, но эндпоинты ловят `Exception` и превращают его в 500, а потоковые эндпоинты к моменту создания сервиса уже начали ответ. Поэтому каждый пишущий эндпоинт проверяет состояние первой строкой. `team/refresh` и `schedule/{id}/run-now` вызывают `run_pipeline` напрямую — их покрывает проверка внутри `run_pipeline`.

**Files:**
- Modify: `app/api/endpoints/sync.py` (импорт + эндпоинты `run_pipeline` :47, `sync_projects` :295, `sync_issues` :320, `refresh_issues` :356, `reload_issues_stream` :388, `sync_teams` :487, `sync_worklogs` :535, `reload_worklogs` :560, `reload_worklogs_stream` :595, `update_worklogs_stream` :669, `sync_comments` :743, `full_sync` :764)
- Modify: `app/api/endpoints/team_desk.py:241-266`
- Modify: `app/api/endpoints/backlog.py:1156-1215`
- Modify: `app/services/scheduler.py:230-245`
- Modify: `app/jobs/backfill_issue_author.py:21-27, 89-93`
- Modify: `scripts/clear_stale_developer_field.py:17-27`
- Modify: `app/api/endpoints/ui_config.py`
- Test: `tests/api/test_sync_blocked_endpoints.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_sync_blocked_endpoints.py`:

```python
"""Пока переезд на новую Jira не завершён, каждый пишущий путь синка отказывает."""
import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.jobs.backfill_issue_author import FLAG_KEY, backfill_issue_author_once
from app.main import app
from app.models.app_setting import AppSetting
from app.repositories.sync_run import SyncRunRepository
from app.repositories.sync_schedule import SyncScheduleRepository
from app.services.jira_migration.state import (
    STATE_DONE,
    STATE_PENDING,
    SYNC_BLOCKED_MESSAGE,
    set_migration_state,
)
from app.services.scheduler import scheduled_pipeline_runner

WRITING_ENDPOINTS = [
    ("/api/v1/sync/pipeline", {"mode": "quick"}),
    ("/api/v1/sync/team/refresh", {"team": "Команда"}),
    ("/api/v1/sync/projects", None),
    ("/api/v1/sync/issues", None),
    ("/api/v1/sync/issues/refresh", {"jira_keys": ["OS-1"]}),
    ("/api/v1/sync/issues/reload/stream", {"since": "2026-01-01"}),
    ("/api/v1/sync/teams", {"teams": ["Команда"]}),
    ("/api/v1/sync/worklogs", None),
    ("/api/v1/sync/worklogs/reload", {"since": "2026-01-01"}),
    ("/api/v1/sync/worklogs/reload/stream", {"since": "2026-01-01"}),
    ("/api/v1/sync/worklogs/update/stream", {"since": "2026-01-01"}),
    ("/api/v1/sync/comments", None),
    ("/api/v1/sync/full", None),
    ("/api/v1/team-desk/refresh-issues", {"keys": ["OS-1"]}),
    ("/api/v1/backlog/refresh-from-jira", None),
    ("/api/v1/backlog/refresh-from-jira/stream", None),
]


@pytest.fixture
def pending_client(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    with patch(
        "app.connectors.jira_client.JiraClient.from_db",
        side_effect=AssertionError("Jira не должна вызываться"),
    ):
        yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path, body", WRITING_ENDPOINTS)
def test_writing_endpoint_refuses_while_pending(pending_client, path, body):
    if body is None:
        resp = pending_client.post(path)
    else:
        resp = pending_client.post(path, json=body)
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == SYNC_BLOCKED_MESSAGE


def test_run_schedule_now_refuses_while_pending(pending_client, db_session):
    schedule = SyncScheduleRepository(db_session).create(
        name="Ночной", cron_expr="0 3 * * *", mode="quick",
    )
    schedule_id = schedule.id
    resp = pending_client.post(f"/api/v1/sync/schedule/{schedule_id}/run-now")
    assert resp.status_code == 409
    assert resp.json()["detail"] == SYNC_BLOCKED_MESSAGE


def test_refresh_allowed_when_done(db_session):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).post("/api/v1/sync/issues/refresh", json={"jira_keys": []})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    assert resp.json()["status"] == "noop"


async def test_scheduler_skips_while_pending(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    with patch("app.services.scheduler._get_db_session", return_value=db_session), \
            patch("app.services.scheduler.JiraClient") as jira_cls:
        await scheduled_pipeline_runner(schedule_id="sched-x", mode="quick", team=None)
    jira_cls.from_db.assert_not_called()
    assert SyncRunRepository(db_session).list_latest(limit=5) == []


def test_backfill_skips_while_pending(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()

    class _NoJira:
        async def __aenter__(self):
            raise AssertionError("Jira не должна вызываться")

        async def __aexit__(self, *exc):
            return False

    changed = asyncio.run(
        backfill_issue_author_once(client=_NoJira(), _session_factory=lambda: db_session)
    )
    assert changed == 0
    assert db_session.query(AppSetting).filter_by(key=FLAG_KEY).first() is None


def test_ui_config_exposes_state(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).get("/api/v1/ui-config/jira-migration-state")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    assert resp.json() == {"state": "pending", "sync_blocked": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/api/test_sync_blocked_endpoints.py -v`
Expected: FAIL — большинство эндпоинтов отвечают 500/502 или поток с ошибкой вместо 409; `/ui-config/jira-migration-state` — 404; планировщик вызывает `JiraClient.from_db`.

- [ ] **Step 3: Guard the sync endpoints**

In `app/api/endpoints/sync.py` after `from app.services.event_bus import get_event_bus` (line 16) add:

```python
from app.services.jira_migration.state import ensure_sync_allowed
```

Then insert `ensure_sync_allowed(db)` with these exact edits (each `old` is unique in the file; `\n` below means a line break, indentation is exactly as in the file — 4 spaces inside function bodies):

1. `run_pipeline`:
   old: `    """Запустить sync pipeline. Возвращает SSE-stream стадий."""\n    lock = SyncLock(db)`
   new: `    """Запустить sync pipeline. Возвращает SSE-stream стадий."""\n    ensure_sync_allowed(db)\n    lock = SyncLock(db)`
2. `sync_projects`:
   old: `    Run this first before syncing issues.\n    """\n    try:`
   new: `    Run this first before syncing issues.\n    """\n    ensure_sync_allowed(db)\n    try:`
3. `sync_issues` (the one followed by a blank line and `try:`, not by `if background`):
   old: `    body = body or SyncRequest()\n\n    try:\n        async with JiraClient.from_db(db) as jira:\n            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))\n            count = await service.sync_issues(`
   new: `    body = body or SyncRequest()\n    ensure_sync_allowed(db)\n\n    try:\n        async with JiraClient.from_db(db) as jira:\n            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))\n            count = await service.sync_issues(`
4. `refresh_issues`:
   old: `    на текущий видимый набор задач без полной пересинхронизации.\n    """\n    if not body.jira_keys:`
   new: `    на текущий видимый набор задач без полной пересинхронизации.\n    """\n    ensure_sync_allowed(db)\n    if not body.jira_keys:`
5. `reload_issues_stream`:
   old: `    from app.api.endpoints.settings import _set_setting\n    from app.services.mapping_service import MappingService\n    from app.models import Issue`
   new: `    ensure_sync_allowed(db)\n    from app.api.endpoints.settings import _set_setting\n    from app.services.mapping_service import MappingService\n    from app.models import Issue`
6. `sync_teams`:
   old: `    if not body.teams:\n        return SyncResponse(status="noop", message="Список команд пуст")`
   new: `    ensure_sync_allowed(db)\n    if not body.teams:\n        return SyncResponse(status="noop", message="Список команд пуст")`
7. `sync_worklogs`:
   old: `    Consider running as background task for large datasets.\n    """\n    try:`
   new: `    Consider running as background task for large datasets.\n    """\n    ensure_sync_allowed(db)\n    try:`
8. `reload_worklogs`:
   old: `    from app.api.endpoints.settings import _set_setting\n\n    try:\n        async with JiraClient.from_db(db) as jira:\n            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))\n            stats = await service.reload_worklogs_v2_bulk(req.since)`
   new: `    ensure_sync_allowed(db)\n    from app.api.endpoints.settings import _set_setting\n\n    try:\n        async with JiraClient.from_db(db) as jira:\n            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))\n            stats = await service.reload_worklogs_v2_bulk(req.since)`
9. `reload_worklogs_stream`:
   old: `    from app.api.endpoints.settings import _set_setting\n\n    async def event_gen():`
   new: `    ensure_sync_allowed(db)\n    from app.api.endpoints.settings import _set_setting\n\n    async def event_gen():`
10. `update_worklogs_stream`:
    old: `    ``error`` — ошибка, ``cancelled`` — клиент отключился.\n    """\n\n    async def event_gen():\n        queue: asyncio.Queue = asyncio.Queue()\n\n        async def on_progress(stats: UpdateStats, current_key: Optional[str]) -> None:`
    new: `    ``error`` — ошибка, ``cancelled`` — клиент отключился.\n    """\n    ensure_sync_allowed(db)\n\n    async def event_gen():\n        queue: asyncio.Queue = asyncio.Queue()\n\n        async def on_progress(stats: UpdateStats, current_key: Optional[str]) -> None:`
11. `sync_comments`:
    old: `    """Синхронизация комментариев к задачам из Jira."""\n    try:`
    new: `    """Синхронизация комментариев к задачам из Jira."""\n    ensure_sync_allowed(db)\n    try:`
12. `full_sync`:
    old: `    body = body or SyncRequest()\n\n    if background and background_tasks:`
    new: `    body = body or SyncRequest()\n    ensure_sync_allowed(db)\n\n    if background and background_tasks:`

- [ ] **Step 4: Guard team desk and backlog refresh**

`app/api/endpoints/team_desk.py`: after `from app.services.sync_service import SyncService` (line 26) add `from app.services.jira_migration.state import ensure_sync_allowed`, and in `refresh_issues` replace:

```python
    видит свежие статусы, оценки, спринт и релиз по видимым задачам.
    """
    keys = list(dict.fromkeys(k.strip() for k in payload.keys if k.strip()))
```

with:

```python
    видит свежие статусы, оценки, спринт и релиз по видимым задачам.
    """
    ensure_sync_allowed(db)
    keys = list(dict.fromkeys(k.strip() for k in payload.keys if k.strip()))
```

`app/api/endpoints/backlog.py`: after `from app.services.sync_service import SyncService` (line 53) add `from app.services.jira_migration.state import ensure_sync_allowed`; replace:

```python
    """Перечитать с Jira кандидатов в бэклог (блокирующий вариант)."""
    try:
        return await _perform_refresh(db, http_request)
```

with:

```python
    """Перечитать с Jira кандидатов в бэклог (блокирующий вариант)."""
    ensure_sync_allowed(db)
    try:
        return await _perform_refresh(db, http_request)
```

and replace:

```python
    ``cancelled`` — клиент оборвал соединение (кнопка «Прервать»).
    """
    async def event_gen():
```

with:

```python
    ``cancelled`` — клиент оборвал соединение (кнопка «Прервать»).
    """
    ensure_sync_allowed(db)

    async def event_gen():
```

- [ ] **Step 5: Skip in scheduler, backfill job and stale-field script**

`app/services/scheduler.py`, in `scheduled_pipeline_runner` replace:

```python
    db = _get_db_session()
    try:
        lock = SyncLock(db)
```

with:

```python
    from app.services.jira_migration.state import is_sync_blocked

    db = _get_db_session()
    try:
        if is_sync_blocked(db):
            logger.info(
                "scheduled_pipeline_runner: пропуск — синхронизация остановлена "
                "до завершения переезда на новую Jira (schedule=%s)", schedule_id,
            )
            return
        lock = SyncLock(db)
```

`app/jobs/backfill_issue_author.py`: after `from app.models.project import Project` add `from app.services.jira_migration.state import is_sync_blocked`; replace:

```python
    db = (_session_factory or SessionLocal)()
    try:
        if not _claim(db):
            return 0
```

with:

```python
    db = (_session_factory or SessionLocal)()
    try:
        if is_sync_blocked(db):
            logger.info("backfill_issue_author: пропуск — синхронизация остановлена "
                        "до завершения переезда на новую Jira")
            return 0
        if not _claim(db):
            return 0
```

`scripts/clear_stale_developer_field.py`: after `from app.services.stale_field_cleanup import clear_stale_developer_field` add `from app.services.jira_migration.state import ensure_sync_allowed`; replace:

```python
    db = SessionLocal()
    try:
        async with JiraClient.from_db(db) as jira:
```

with:

```python
    db = SessionLocal()
    try:
        if apply:
            ensure_sync_allowed(db)
        async with JiraClient.from_db(db) as jira:
```

- [ ] **Step 6: Expose the state to the frontend**

`app/api/endpoints/ui_config.py`: after `from app.models.user import User` add:

```python
from app.services.jira_migration.state import STATE_PENDING, get_migration_state
```

after `class HiddenSectionsUpdate` add:

```python
class JiraMigrationStateResponse(BaseModel):
    state: str
    sync_blocked: bool
```

after `get_jira_base_url` add:

```python
@router.get("/jira-migration-state", response_model=JiraMigrationStateResponse)
def get_jira_migration_state(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Состояние переезда на новую Jira: пока ``pending``, синк остановлен."""
    state = get_migration_state(db)
    return JiraMigrationStateResponse(state=state, sync_blocked=state == STATE_PENDING)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/api/test_sync_blocked_endpoints.py -v`
Expected: PASS (21 tests).

Run: `py -3.10 -m pytest tests/test_scheduler_trigger.py tests/test_backfill_issue_author.py tests/test_jira_users_search_endpoint.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/api/endpoints/sync.py app/api/endpoints/team_desk.py app/api/endpoints/backlog.py app/services/scheduler.py app/jobs/backfill_issue_author.py scripts/clear_stale_developer_field.py app/api/endpoints/ui_config.py tests/api/test_sync_blocked_endpoints.py
git commit -m "feat(sync): 409 во всех пишущих путях синка до переезда" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: Обезличенные фикстуры Jira DC

Источник — `data/jira_check.txt` (в `.gitignore`, в репозиторий не попадает): строка `== <раздел>`, затем строка сырого JSON. Ответ `worklog/updated` в файле обрезан на 2000 символах — скрипт берёт только целые записи. Скрипт сам не содержит имён и почт: разделы пользователей выбираются по префиксу `user `, а не по тексту запроса.

**Files:**
- Create: `scripts/make_dc_fixtures.py`
- Create: `tests/dc_fixtures.py`
- Create (generated): `tests/fixtures/jira_dc/*.json` (18 файлов)
- Test: `tests/test_dc_fixtures.py`

- [ ] **Step 1: Write the failing test**

`tests/test_dc_fixtures.py`:

```python
"""Фикстуры Jira DC: на месте и без персональных данных."""
import json
import re

from tests.dc_fixtures import FIXTURE_DIR, load_dc

EXPECTED = {
    "server_info.json",
    "issue_OS-91030.json", "issue_OS-91031.json", "issue_RFA-4610.json",
    "issue_OS-92392.json", "issue_OS-93622.json", "issue_OS-89194.json",
    "issue_RFA-5020.json",
    "worklogs_OS-91030.json", "worklogs_OS-91031.json", "worklogs_RFA-4610.json",
    "worklog_list.json", "worklog_updated.json", "search_count_OS.json",
    "custom_field_options_error.json", "fields.json",
    "user_search.json", "user_search_single.json",
}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _users(node):
    if isinstance(node, dict):
        if "key" in node and "name" in node and ("displayName" in node or "emailAddress" in node):
            yield node
        for value in node.values():
            yield from _users(value)
    elif isinstance(node, list):
        for value in node:
            yield from _users(value)


def test_all_fixture_files_present():
    assert EXPECTED <= {p.name for p in FIXTURE_DIR.glob("*.json")}


def test_no_real_host_or_email():
    for path in FIXTURE_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for email in EMAIL_RE.findall(text):
            assert email.endswith("@example.test"), (path.name, email)


def test_people_are_replaced_consistently():
    seen = 0
    for path in FIXTURE_DIR.glob("*.json"):
        for user in _users(json.loads(path.read_text(encoding="utf-8"))):
            seen += 1
            assert re.fullmatch(r"JIRAUSER9\d{4}", user["key"]), (path.name, user["key"])
            assert re.fullmatch(r"user_\d+", user["name"]), (path.name, user["name"])
            assert user["displayName"].startswith("Сотрудник "), path.name
    assert seen > 20


def test_issue_ids_and_links_kept():
    issue = load_dc("issue_OS-91030.json")
    assert issue["id"] == "258783"
    assert issue["fields"]["customfield_10107"] == "OS-84096"
    assert load_dc("issue_OS-89194.json")["fields"]["customfield_10100"] == "RFA-4599"
    assert load_dc("worklog_updated.json")["lastPage"] is True
    assert len(load_dc("worklog_updated.json")["values"]) >= 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_dc_fixtures.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.dc_fixtures'`.

- [ ] **Step 3: Write the loader and the generator**

`tests/dc_fixtures.py`:

```python
"""Обезличенные ответы Jira DC для тестов (генерирует scripts/make_dc_fixtures.py)."""
import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "jira_dc"


def load_dc(name: str) -> Any:
    """Прочитать фикстуру ``tests/fixtures/jira_dc/<name>`` свежей копией."""
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
```

`scripts/make_dc_fixtures.py`:

```python
"""Обезличенные фикстуры Jira DC для тестов из ответа админа (data/jira_check.txt).

Формат входа: строка ``== <раздел>`` и следующая строка — сырой JSON ответа.
Имена, логины, почты, ключи пользователей, аватары и адрес сервера
заменяются выдуманными; структура ответов и id задач/ворклогов сохраняются.
Один и тот же человек во всех файлах получает одну и ту же замену.
Перед записью — проверка: ни одно настоящее имя/логин/почта не попали в вывод.

Запуск из корня репозитория:
    py -3.10 scripts/make_dc_fixtures.py
Пишет tests/fixtures/jira_dc/*.json. data/ в репозиторий не попадает.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "jira_check.txt"
OUT = ROOT / "tests" / "fixtures" / "jira_dc"
FAKE_HOST = "https://jira.example.test"

# Поля задачи, нужные тестам. Остальное (комментарии, вложения, ворклоги
# внутри задачи, текстовые поля) несёт рабочие тексты — выбрасываем.
ISSUE_FIELDS = (
    "summary", "description", "issuetype", "status", "priority", "project",
    "parent", "creator", "reporter", "assignee", "created", "updated",
    "duedate", "resolution", "resolutiondate", "issuelinks", "subtasks",
    "fixVersions",
    "customfield_10107",  # Ссылка на эпик
    "customfield_10100",  # Parent Link
    "customfield_10109",  # Спринт
    "customfield_11092",  # Продуктовая команда
    "customfield_11098",  # Разработчик
)
FIELD_KEYS = ("id", "name", "custom", "orderable", "navigable", "searchable", "clauseNames", "schema")
FAKE_DESCRIPTION = (
    "h2. Описание\nТекст задачи для теста.\n"
    "[Страница ТЗ|https://confluence.example.test/x/AbCdE]"
)
UPDATED_ITEM = re.compile(r'\{"worklogId":(\d+),"updatedTime":(\d+)\}')


def read_sections(path: Path) -> dict[str, str]:
    """``{название раздела: строка JSON}``."""
    sections: dict[str, str] = {}
    name = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("== "):
            name = line[3:].strip()
        elif name is not None and line.strip():
            sections[name] = line
            name = None
    return sections


def _is_user(node: dict) -> bool:
    return "key" in node and "name" in node and ("displayName" in node or "emailAddress" in node)


class Sanitizer:
    """Заменяет людей и адрес сервера, запоминая настоящие значения для проверки."""

    def __init__(self, real_base_url: str) -> None:
        self.real_host = real_base_url.rstrip("/")
        self.people: dict[str, int] = {}
        self.secrets: set[str] = {urlparse(real_base_url).netloc}

    def _person(self, user: dict) -> int:
        ident = user.get("key") or user.get("name") or user.get("displayName")
        if ident not in self.people:
            self.people[ident] = len(self.people) + 1
        for field in ("name", "key", "displayName", "emailAddress"):
            value = user.get(field)
            if isinstance(value, str) and value:
                self.secrets.add(value)
                if field == "emailAddress" and "@" in value:
                    self.secrets.add(value.split("@", 1)[1])
        return self.people[ident]

    def user(self, user: dict) -> dict:
        n = self._person(user)
        out = dict(user)
        out["key"] = f"JIRAUSER9{n:04d}"
        out["name"] = f"user_{n}"
        out["displayName"] = f"Сотрудник {n}"
        if "emailAddress" in out:
            out["emailAddress"] = f"user_{n}@example.test"
        if isinstance(out.get("avatarUrls"), dict):
            out["avatarUrls"] = {
                size: f"{FAKE_HOST}/secure/useravatar?size={size}&avatarId=1"
                for size in out["avatarUrls"]
            }
        if "self" in out:
            out["self"] = f"{FAKE_HOST}/rest/api/2/user?username=user_{n}"
        return out

    def walk(self, node):
        if isinstance(node, dict):
            if _is_user(node):
                node = self.user(node)
            return {k: self.walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [self.walk(v) for v in node]
        if isinstance(node, str):
            return node.replace(self.real_host, FAKE_HOST)
        return node


def clean_issue(raw: dict, s: Sanitizer) -> dict:
    fields = raw.get("fields") or {}
    kept = {k: fields[k] for k in ISSUE_FIELDS if k in fields}
    kept["summary"] = f"Задача {raw['key']}"
    if kept.get("description") is not None:
        kept["description"] = FAKE_DESCRIPTION
    for link in kept.get("issuelinks") or []:
        for side in ("inwardIssue", "outwardIssue"):
            other = link.get(side)
            if isinstance(other, dict) and isinstance(other.get("fields"), dict):
                other["fields"]["summary"] = "Связанная задача"
    for sub in kept.get("subtasks") or []:
        if isinstance(sub.get("fields"), dict):
            sub["fields"]["summary"] = "Подзадача"
    parent = kept.get("parent")
    if isinstance(parent, dict) and isinstance(parent.get("fields"), dict):
        parent["fields"]["summary"] = "Родительская задача"
    out = {k: raw[k] for k in ("expand", "id", "self", "key") if k in raw}
    out["fields"] = kept
    return s.walk(out)


def clean_worklog(worklog: dict) -> dict:
    out = dict(worklog)
    if out.get("comment") is not None:
        out["comment"] = "Комментарий к списанию"
    return out


def parse_worklog_updated(text: str) -> dict:
    """Ответ /worklog/updated; в файле админа он обрезан — берём целые записи."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        values = [
            {"worklogId": int(wid), "updatedTime": int(ts)}
            for wid, ts in UPDATED_ITEM.findall(text)
        ]
        return {
            "values": values,
            "since": values[0]["updatedTime"],
            "until": values[-1]["updatedTime"],
            "lastPage": True,
        }


def main() -> int:
    if not SOURCE.exists():
        print(f"Нет файла {SOURCE}", file=sys.stderr)
        return 1
    sections = read_sections(SOURCE)
    server = json.loads(sections["serverInfo"])
    s = Sanitizer(server["baseUrl"])

    out: dict[str, object] = {"server_info.json": s.walk(server)}
    for name, text in sections.items():
        if name.startswith("issue "):
            raw = json.loads(text)
            out[f"issue_{raw['key']}.json"] = clean_issue(raw, s)
        elif name.startswith("worklog ") and not name.startswith("worklog/"):
            key = name.split(" ", 1)[1]
            page = json.loads(text)
            page["worklogs"] = [clean_worklog(w) for w in page.get("worklogs", [])]
            out[f"worklogs_{key}.json"] = s.walk(page)
    out["worklog_list.json"] = s.walk(
        [clean_worklog(w) for w in json.loads(sections["worklog/list"])]
    )
    out["worklog_updated.json"] = parse_worklog_updated(sections["worklog/updated"])
    out["search_count_OS.json"] = s.walk(json.loads(sections["count OS"]))
    out["custom_field_options_error.json"] = json.loads(sections["team options"])
    out["fields.json"] = [
        {k: f[k] for k in FIELD_KEYS if k in f} for f in json.loads(sections["fields"])
    ]
    user_lists = sorted(
        (json.loads(t) for n, t in sections.items() if n.startswith("user ")),
        key=len, reverse=True,
    )
    out["user_search.json"] = s.walk(user_lists[0])
    singles = [u for u in user_lists if len(u) == 1]
    if singles:
        out["user_search_single.json"] = s.walk(singles[0])

    texts = {
        name: json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        for name, data in out.items()
    }
    leaks = sorted(
        {name for name, text in texts.items() for secret in s.secrets
         if secret and secret.lower() in text.lower()}
    )
    if leaks:
        print(f"Остались настоящие данные в: {', '.join(leaks)}", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (OUT / name).write_text(text, encoding="utf-8")
    print(f"Записано {len(texts)} файлов в {OUT}, людей заменено: {len(s.people)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Generate the fixtures**

Run: `py -3.10 scripts/make_dc_fixtures.py`
Expected: `Записано 18 файлов в ...tests\fixtures\jira_dc, людей заменено: N` (N > 10), код возврата 0. Если скрипт вернул 2 («Остались настоящие данные») — не коммитить, разобрать, какое значение попало в вывод.

Run: `git status --short tests/fixtures/jira_dc data`
Expected: только новые `tests/fixtures/jira_dc/*.json`; `data/` в списке нет.

- [ ] **Step 5: Run test to verify it passes**

Run: `py -3.10 -m pytest tests/test_dc_fixtures.py -v`
Expected: PASS (4 tests).

Run: `ruff check scripts/make_dc_fixtures.py tests/dc_fixtures.py tests/test_dc_fixtures.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add scripts/make_dc_fixtures.py tests/dc_fixtures.py tests/test_dc_fixtures.py tests/fixtures/jira_dc/
git commit -m "test(jira-dc): обезличенные ответы новой Jira для тестов" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Пользователь Jira DC — идентичность по `key`

У пользователя DC нет `accountId`: есть `key` (неизменный, `JIRAUSER12223`) и `name` (логин). `jira_account_id` берётся из `key`. Авторы ворклогов и комментариев — тот же пользователь. Поле «Разработчик» — `key`.

**Files:**
- Modify: `app/connectors/schemas.py:26-49` (`JiraUserSchema`), `:174-181` (`JiraWorklogAuthorSchema`), `:189`, `:247-261` (`JiraCommentAuthorSchema`, `JiraCommentSchema.author`)
- Modify: `app/services/sync_service.py:463-475` (`_extract_user_field`), новый `_author_as_user` рядом, 7 мест создания автора (`:1781-1788`, `:1874-1881`, `:2011-2017`, `:2110-2116`, `:2181-2187`, `:2272-2278`, `:2359-2365`)
- Modify tests: `tests/test_schemas.py`, `tests/test_kpi_worklog_created.py`, `tests/test_team_desk_sync_fields.py`, `tests/test_jira_client_search_users.py`, `tests/api/test_scenario_assignee.py`, `tests/test_jira_users_search_endpoint.py`, `tests/test_reload_worklogs_v2_bulk.py`, `tests/test_sync_service.py`, `tests/test_sync_service_reload.py`, `tests/test_sync_service_delete_diff.py`, `tests/test_sync_service_update.py`, `tests/test_sync_service_v2.py`
- Test: `tests/connectors/test_jira_dc_schemas.py`

- [ ] **Step 1: Write the failing test**

`tests/connectors/test_jira_dc_schemas.py`:

```python
"""Схемы на настоящих (обезличенных) ответах Jira DC: люди — по key, логин — name."""
from app.connectors.schemas import (
    JiraIssueSchema,
    JiraUserSchema,
    JiraWorklogSchema,
    JiraWorklogsResponseSchema,
)
from app.services.sync_service import _author_as_user, _extract_user_field
from tests.dc_fixtures import load_dc


def test_dc_user_identity_is_key_and_login_is_name():
    raw = load_dc("user_search.json")[0]
    user = JiraUserSchema.model_validate(raw)
    assert user.jira_account_id == raw["key"]
    assert user.jira_account_id.startswith("JIRAUSER")
    assert user.name == raw["name"]
    assert user.display_name == raw["displayName"]
    assert user.email == raw["emailAddress"]


def test_dc_issue_people_parse():
    raw = load_dc("issue_OS-91030.json")
    issue = JiraIssueSchema.model_validate(raw)
    assert issue.fields.assignee.jira_account_id == raw["fields"]["assignee"]["key"]
    assert issue.fields.reporter.name == raw["fields"]["reporter"]["name"]
    assert issue.fields.creator.display_name == raw["fields"]["creator"]["displayName"]


def test_dc_worklog_author_parses():
    raw = load_dc("worklogs_OS-91030.json")
    page = JiraWorklogsResponseSchema.model_validate(raw)
    wl = page.worklogs[0]
    assert wl.author.jira_account_id == raw["worklogs"][0]["author"]["key"]
    assert wl.author.name == raw["worklogs"][0]["author"]["name"]
    assert wl.issueId == raw["worklogs"][0]["issueId"]


def test_author_as_user_keeps_login_and_is_active():
    wl = JiraWorklogSchema.model_validate(load_dc("worklog_list.json")[0])
    user = _author_as_user(wl.author)
    assert user.jira_account_id == wl.author.jira_account_id
    assert user.name == wl.author.name
    assert user.display_name == wl.author.display_name
    assert user.is_active is True


def test_developer_field_reads_key():
    fields = load_dc("issue_OS-91030.json")["fields"]
    account, name = _extract_user_field(fields, "customfield_11098")
    assert account == fields["customfield_11098"]["key"]
    assert name == fields["customfield_11098"]["displayName"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/connectors/test_jira_dc_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name '_author_as_user'`; после его появления — `accountId Field required`.

- [ ] **Step 3: DC user schema**

In `app/connectors/schemas.py` replace the class `JiraUserSchema` (lines 28–49) with:

```python
class JiraUserSchema(BaseModel):
    """Пользователь Jira Data Center.

    Идентичность — ``key`` (``JIRAUSER12223``): не меняется при переименовании
    учётки, хранится в ``jira_account_id``. ``name`` — логин (``Lebedev_A_A``):
    нужен для JQL ``worklogAuthor`` и поиска ``/user/search?username=``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    jira_account_id: str = Field(alias="key")
    name: Optional[str] = None
    display_name: str = Field(alias="displayName")
    email: Optional[str] = Field(default=None, alias="emailAddress")
    is_active: bool = Field(default=True, alias="active")
    avatar_urls: Optional[dict] = Field(default=None, alias="avatarUrls")

    @property
    def avatar_url(self) -> Optional[str]:
        """Preferred avatar URL (48x48)."""
        if self.avatar_urls:
            return self.avatar_urls.get("48x48")
        return None

    # Back-compat alias for any existing code still referring to avatar_48
    @property
    def avatar_48(self) -> Optional[str]:
        return self.avatar_url
```

Replace the class `JiraWorklogAuthorSchema` (lines 176–181) with:

```python
# Автор ворклога в Jira DC — обычный пользователь (key, name, displayName, …).
JiraWorklogAuthorSchema = JiraUserSchema
```

In `JiraWorklogSchema` change `author: JiraWorklogAuthorSchema` to `author: JiraUserSchema`.

Replace the class `JiraCommentAuthorSchema` (lines 249–254) with:

```python
# Автор комментария в Jira DC — обычный пользователь.
JiraCommentAuthorSchema = JiraUserSchema
```

In `JiraCommentSchema` change `author: JiraCommentAuthorSchema` to `author: JiraUserSchema`.

- [ ] **Step 4: Authors and the developer field in the sync service**

In `app/services/sync_service.py` replace `_extract_user_field` (lines 463–475) with:

```python
def _extract_user_field(
    extra: dict, field_id: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Достаёт (key, displayName) из кастомного поля Jira DC типа user.

    Пустое поле, ненастроенный id или чужая форма значения → (None, None).
    """
    if not field_id:
        return None, None
    raw = (extra or {}).get(field_id)
    if not isinstance(raw, dict):
        return None, None
    return (raw.get("key") or None), (raw.get("displayName") or None)


def _author_as_user(author: Any) -> JiraUserSchema:
    """Автор ворклога/комментария как пользователь Jira для upsert сотрудника.

    Активным считаем всегда, как и раньше: признак активности сотрудника
    пересчитывается отдельно (``/employees/recalc-active``).
    """
    return JiraUserSchema(
        key=author.jira_account_id,
        name=getattr(author, "name", None),
        displayName=author.display_name,
        emailAddress=getattr(author, "email", None),
        active=True,
    )
```

Replace the seven author constructions:

1. `sync_worklogs` — old:
```python
                    # Ensure author exists as employee
                    author_schema = JiraUserSchema(
                        accountId=jira_worklog.author.accountId,
                        displayName=jira_worklog.author.displayName,
                        emailAddress=jira_worklog.author.emailAddress,
                        active=True,
                    )
                    employee = self._ensure_employee(author_schema)
```
new:
```python
                    # Ensure author exists as employee
                    employee = self._ensure_employee(_author_as_user(jira_worklog.author))
```

2. `sync_comments` — old:
```python
                    # Ensure author exists as employee
                    author_schema = JiraUserSchema(
                        accountId=jira_comment.author.accountId,
                        displayName=jira_comment.author.displayName,
                        emailAddress=jira_comment.author.emailAddress,
                        active=True,
                    )
                    employee = self._ensure_employee(author_schema)
```
new:
```python
                    # Ensure author exists as employee
                    employee = self._ensure_employee(_author_as_user(jira_comment.author))
```

3. `reload_worklogs_since` and `update_worklogs_since` (identical text, indent 16 — replace both occurrences) — old:
```python
                author_schema = JiraUserSchema(
                    accountId=wl.author.accountId,
                    displayName=wl.author.displayName,
                    emailAddress=wl.author.emailAddress,
                    active=True,
                )
                employee = self._ensure_employee(author_schema)
```
new:
```python
                employee = self._ensure_employee(_author_as_user(wl.author))
```

4. `reload_worklogs_v2_bulk` and `update_worklogs_v2` (identical text, indent 16 — replace both) — old:
```python
                author_schema = JiraUserSchema(
                    accountId=wl.author.accountId,
                    displayName=wl.author.displayName,
                    emailAddress=wl.author.emailAddress,
                    active=True,
                )
                employee = self._ensure_employee_cached(author_schema, employee_cache)
```
new:
```python
                employee = self._ensure_employee_cached(_author_as_user(wl.author), employee_cache)
```

5. `_update_worklogs_bucket_b` (indent 20) — old:
```python
                    author_schema = JiraUserSchema(
                        accountId=wl.author.accountId,
                        displayName=wl.author.displayName,
                        emailAddress=wl.author.emailAddress,
                        active=True,
                    )
                    employee = self._ensure_employee(author_schema)
```
new:
```python
                    employee = self._ensure_employee(_author_as_user(wl.author))
```

Check: `grep -n "accountId" app/services/sync_service.py` prints nothing.

- [ ] **Step 5: Update tests that build Cloud-shaped users**

Run (Git Bash, from repo root):

```bash
sed -i 's/"accountId"/"key"/g' tests/test_schemas.py tests/test_kpi_worklog_created.py tests/test_team_desk_sync_fields.py tests/test_jira_client_search_users.py
sed -i 's/accountId=/key=/' tests/api/test_scenario_assignee.py tests/test_jira_users_search_endpoint.py tests/test_reload_worklogs_v2_bulk.py tests/test_sync_service.py tests/test_sync_service_reload.py
sed -i 's/^            accountId=author_id,$/            jira_account_id=author_id,\n            name=None,/; s/^            displayName="Author",$/            display_name="Author",/; s/^            emailAddress=None,$/            email=None,/' tests/test_sync_service_delete_diff.py tests/test_sync_service_update.py tests/test_sync_service_v2.py
grep -rn "accountId" tests/ --include=*.py
```

Expected: последний `grep` ничего не печатает. В трёх последних файлах автор ворклога теперь `SimpleNamespace(jira_account_id=author_id, name=None, display_name="Author", email=None)` — атрибуты схемы, которые читает `_author_as_user`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/connectors/test_jira_dc_schemas.py tests/test_schemas.py tests/test_kpi_worklog_created.py tests/test_team_desk_sync_fields.py tests/test_jira_client_search_users.py tests/api/test_scenario_assignee.py tests/test_jira_users_search_endpoint.py tests/test_reload_worklogs_v2_bulk.py tests/test_sync_service.py tests/test_sync_service_reload.py tests/test_sync_service_delete_diff.py tests/test_sync_service_update.py tests/test_sync_service_v2.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/connectors/schemas.py app/services/sync_service.py tests/connectors/test_jira_dc_schemas.py tests/test_schemas.py tests/test_kpi_worklog_created.py tests/test_team_desk_sync_fields.py tests/test_jira_client_search_users.py tests/api/test_scenario_assignee.py tests/test_jira_users_search_endpoint.py tests/test_reload_worklogs_v2_bulk.py tests/test_sync_service.py tests/test_sync_service_reload.py tests/test_sync_service_delete_diff.py tests/test_sync_service_update.py tests/test_sync_service_v2.py
git commit -m "feat(jira-dc): пользователь по key вместо облачного accountId" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Логин сотрудника, ведро B по логину, логин при добавлении из Jira

JQL `worklogAuthor` в DC принимает логин, а не `key`. Логин хранится в новой колонке `employees.jira_username` и обновляется при каждой встрече пользователя, в том числе в проходах с кэшем сотрудников (там раньше upsert пропускался).

**Files:**
- Modify: `app/models/employee.py:26-28`
- Create: `alembic/versions/dc02_employee_jira_username.py`
- Modify: `app/services/sync_service.py:786-830` (`_upsert_employee`, `_ensure_employee_cached`), `:2337-2339` (ведро B)
- Modify: `app/api/endpoints/employees.py:89-94, 155-171`
- Modify: `app/api/endpoints/sync.py:1020-1025, 1193-1202` (`JiraUserResponse`, `search_jira_users`)
- Modify: `scripts/demo_db/anonymize.py:132`
- Modify tests: `tests/test_sync_service_update.py` (сотрудники ведра B получают логин), `tests/test_jira_users_search_endpoint.py`
- Test: `tests/test_employee_jira_username.py`, `tests/test_migration_dc02_employee_jira_username.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_employee_jira_username.py`:

```python
"""Логин Jira DC у сотрудника: пишется синком, по нему ищутся списания (ведро B)."""
from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.connectors.schemas import JiraUserSchema
from app.database import get_db
from app.main import app
from app.models import Employee, EmployeeTeam
from app.services.sync_service import SyncService, UpdateStats


def test_upsert_stores_and_refreshes_login(db_session):
    svc = SyncService(db_session, MagicMock())
    svc._ensure_employee(JiraUserSchema(key="JIRAUSER1", name="Ivanov_I_I", displayName="Иванов"))
    db_session.commit()
    svc._ensure_employee(JiraUserSchema(key="JIRAUSER1", name="Ivanov_I", displayName="Иванов"))
    db_session.commit()

    emp = db_session.query(Employee).filter_by(jira_account_id="JIRAUSER1").one()
    assert emp.jira_username == "Ivanov_I"


def test_user_without_login_keeps_stored_login(db_session):
    db_session.add(Employee(jira_account_id="JIRAUSER3", jira_username="kept",
                            display_name="Анна", is_active=True))
    db_session.commit()
    svc = SyncService(db_session, MagicMock())
    svc._ensure_employee(JiraUserSchema(key="JIRAUSER3", displayName="Анна"))
    db_session.commit()
    assert db_session.query(Employee).filter_by(jira_account_id="JIRAUSER3").one().jira_username == "kept"


def test_cached_employee_gets_renamed_login(db_session):
    emp = Employee(jira_account_id="JIRAUSER2", jira_username="old_login",
                   display_name="Пётр", is_active=True)
    db_session.add(emp)
    db_session.commit()
    svc = SyncService(db_session, MagicMock())
    cache = {emp.jira_account_id: emp}

    svc._ensure_employee_cached(
        JiraUserSchema(key="JIRAUSER2", name="new_login", displayName="Пётр"), cache,
    )
    db_session.commit()
    assert db_session.get(Employee, emp.id).jira_username == "new_login"


async def test_bucket_b_queries_by_login_and_skips_unbound(db_session):
    db_session.add_all([
        Employee(id="e-1", jira_account_id="JIRAUSER1", jira_username="Ivanov_I_I",
                 display_name="Иванов", is_active=True, synced_at=datetime.utcnow()),
        Employee(id="e-2", jira_account_id="cloud:abc", display_name="Без привязки",
                 is_active=True, synced_at=datetime.utcnow()),
    ])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(id="et-1", employee_id="e-1", team="Alpha", is_primary=True),
        EmployeeTeam(id="et-2", employee_id="e-2", team="Alpha", is_primary=True),
    ])
    db_session.commit()

    jqls: list[str] = []

    async def fake_iter_issues(jql, fields=None, max_results=100):
        jqls.append(jql)
        if False:
            yield

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    svc = SyncService(db_session, jira)
    await svc._update_worklogs_bucket_b("2026-02-01", ["Alpha"], UpdateStats())

    assert jqls == ['worklogAuthor = "Ivanov_I_I" AND updated >= "2026-02-01"']


def test_employee_from_jira_stores_login(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).post("/api/v1/employees/from-jira", json={
            "jira_account_id": "JIRAUSER7",
            "jira_username": "Petrov_P_P",
            "display_name": "Петров Пётр",
            "email": None,
            "is_active": True,
            "avatar_url": None,
        })
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    emp = db_session.query(Employee).filter_by(jira_account_id="JIRAUSER7").one()
    assert emp.jira_username == "Petrov_P_P"
```

`tests/test_migration_dc02_employee_jira_username.py`:

```python
"""dc02: колонка employees.jira_username; повторный запуск на базе из create_all не падает."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _columns(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {r[1] for r in con.execute("PRAGMA table_info(employees)")}
    finally:
        con.close()


def test_upgrade_adds_column_and_downgrade_drops(tmp_path):
    db = tmp_path / "dc02.db"
    _alembic(db, "upgrade", "dc02_employee_jira_username")
    assert "jira_username" in _columns(db)
    _alembic(db, "downgrade", "dc01_jira_sync_lock")
    assert "jira_username" not in _columns(db)


def test_upgrade_skips_existing_column(tmp_path):
    db = tmp_path / "dc02_existing.db"
    _alembic(db, "upgrade", "dc01_jira_sync_lock")
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE employees ADD COLUMN jira_username VARCHAR(255)")
        con.commit()
    finally:
        con.close()
    _alembic(db, "upgrade", "dc02_employee_jira_username")
    assert "jira_username" in _columns(db)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/test_employee_jira_username.py tests/test_migration_dc02_employee_jira_username.py -v`
Expected: FAIL — `TypeError: 'jira_username' is an invalid keyword argument for Employee`; миграция не найдена.

- [ ] **Step 3: Model and migration**

`app/models/employee.py` — after the `jira_account_id` column add:

```python
    # Логин Jira DC (``name``, например Lebedev_A_A). Учётку могут
    # переименовать, поэтому идентичность — ``jira_account_id`` (DC ``key``), а
    # логин синк обновляет при каждой встрече; по нему JQL ``worklogAuthor``.
    jira_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
```

`alembic/versions/dc02_employee_jira_username.py`:

```python
"""employees.jira_username — логин Jira Data Center

Revision ID: dc02_employee_jira_username
Revises: dc01_jira_sync_lock
Create Date: 2026-10-14

Логин нужен для JQL ``worklogAuthor`` (по ``key`` Jira DC искать не умеет).
Локальная база может уже иметь колонку от create_all в tests/conftest.py —
тогда пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "dc02_employee_jira_username"
down_revision: Union[str, None] = "dc01_jira_sync_lock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    if context.is_offline_mode():
        return False
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column("employees", "jira_username"):
        with op.batch_alter_table("employees") as batch:
            batch.add_column(sa.Column("jira_username", sa.String(255), nullable=True))


def downgrade() -> None:
    if _has_column("employees", "jira_username"):
        with op.batch_alter_table("employees") as batch:
            batch.drop_column("jira_username")
```

- [ ] **Step 4: Login in the sync service**

In `app/services/sync_service.py` replace `_upsert_employee` (lines 786–800) with:

```python
    def _upsert_employee(self, jira_user: JiraUserSchema) -> Tuple[Employee, bool]:
        """Upsert employee from Jira user (identity — DC ``key``, login refreshed)."""
        data = {
            "jira_account_id": jira_user.jira_account_id,
            "display_name": jira_user.display_name,
            "email": jira_user.email,
            "is_active": jira_user.is_active,
            "avatar_url": jira_user.avatar_url,
            "synced_at": datetime.utcnow(),
        }
        if jira_user.name:
            data["jira_username"] = jira_user.name
        return self.employee_repo.upsert_by_field(
            "jira_account_id",
            jira_user.jira_account_id,
            data,
        )
```

In `_ensure_employee_cached` replace:

```python
        eid = jira_user.jira_account_id
        cached = cache.get(eid)
        if cached is not None:
            return cached
```

with:

```python
        eid = jira_user.jira_account_id
        cached = cache.get(eid)
        if cached is not None:
            # Логин дешевле сверить, чем потерять: по нему ведро B ищет списания.
            if jira_user.name and cached.jira_username != jira_user.name:
                cached.jira_username = jira_user.name
            return cached
```

In `_update_worklogs_bucket_b` replace:

```python
        for emp in emps:
            await self._check_cancelled()
            jql = f'worklogAuthor = "{emp.jira_account_id}" AND updated >= "{since_iso}"'
```

with:

```python
        for emp in emps:
            await self._check_cancelled()
            if not emp.jira_username:
                # Без логина Jira DC искать списания нечем: сотрудник не привязан
                # к новой Jira (после переезда — id с префиксом «cloud:»).
                logger.info("Bucket B: пропуск %s — нет логина Jira", emp.display_name)
                continue
            login = emp.jira_username.replace('"', '\\"')
            jql = f'worklogAuthor = "{login}" AND updated >= "{since_iso}"'
```

- [ ] **Step 5: Login in employee endpoints and user search**

`app/api/endpoints/employees.py` — in `EmployeeFromJiraRequest` after `jira_account_id: str` add `jira_username: Optional[str] = None`. In `employee_from_jira` replace:

```python
        existing = Employee(
            id=str(uuid.uuid4()),
            jira_account_id=req.jira_account_id,
            display_name=req.display_name,
```

with:

```python
        existing = Employee(
            id=str(uuid.uuid4()),
            jira_account_id=req.jira_account_id,
            jira_username=req.jira_username,
            display_name=req.display_name,
```

and replace:

```python
    else:
        existing.display_name = req.display_name
        existing.email = req.email
```

with:

```python
    else:
        existing.display_name = req.display_name
        if req.jira_username:
            existing.jira_username = req.jira_username
        existing.email = req.email
```

`app/api/endpoints/sync.py` — in `JiraUserResponse` after `jira_account_id: str` add `jira_username: Optional[str] = None`; in `search_jira_users` replace `            jira_account_id=u.jira_account_id,` with:

```python
            jira_account_id=u.jira_account_id,
            jira_username=u.name,
```

`tests/test_jira_users_search_endpoint.py` — in the fake `JiraUserSchema(...)` after `key="a1",` add `name="ivanov",`; after `assert body[0]["jira_account_id"] == "a1"` add `assert body[0]["jira_username"] == "ivanov"`.

- [ ] **Step 6: Existing bucket B tests and the demo anonymizer**

`tests/test_sync_service_update.py`: replace all occurrences of

```python
        id="e-1", jira_account_id="acc-1", display_name="A",
```

with

```python
        id="e-1", jira_account_id="acc-1", jira_username="login-1", display_name="A",
```

(сотрудник ведра B без логина теперь пропускается).

`scripts/demo_db/anonymize.py` line 132: replace

```python
    "employees": "keep: id role; rule: jira_account_id display_name email team; clear: avatar_url department",
```

with

```python
    "employees": "keep: id role; rule: jira_account_id display_name email team; "
                 "clear: avatar_url department jira_username",
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_employee_jira_username.py tests/test_migration_dc02_employee_jira_username.py tests/test_sync_service_update.py tests/test_jira_users_search_endpoint.py tests/test_demo_db_anonymize.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/models/employee.py alembic/versions/dc02_employee_jira_username.py app/services/sync_service.py app/api/endpoints/employees.py app/api/endpoints/sync.py scripts/demo_db/anonymize.py tests/test_employee_jira_username.py tests/test_migration_dc02_employee_jira_username.py tests/test_sync_service_update.py tests/test_jira_users_search_endpoint.py
git commit -m "feat(jira-dc): логин сотрудника, списания ведра B по логину" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Клиент DC — вход по токену, `/rest/api/2`, поиск со смещением, проекты, пользователи; настройки без почты

**Files:**
- Modify (rewrite): `app/connectors/jira_client.py`
- Modify: `app/connectors/schemas.py:311-363` (`JiraSearchResponseSchema`, удалить `JiraProjectsResponseSchema`)
- Modify: `app/api/endpoints/settings.py:34-60, 112-140, 181-199`
- Modify: `app/api/endpoints/sync.py:266-292` (docstring), `:819-882` (`browse_jira_projects`)
- Modify: `app/services/sync_service.py:1206, 1615` (`ORDER BY updated ASC` → `ORDER BY key ASC`)
- Modify: `app/config.py:29-32`, `.env.example:12-16`
- Modify (rewrite): `tests/test_jira_client_search_users.py`
- Test: `tests/connectors/test_jira_dc_client.py`, `tests/test_settings_jira_endpoint.py`

- [ ] **Step 1: Write the failing tests**

`tests/connectors/test_jira_dc_client.py`:

```python
"""Клиент Jira Data Center: вход по токену, REST API v2, поиск со смещением."""
import httpx
import pytest
import respx

from app.connectors import jira_client
from app.connectors.jira_client import JiraClient, JiraClientError
from app.models.app_setting import AppSetting
from tests.dc_fixtures import load_dc

BASE = "https://jira.example.test"
API = f"{BASE}/rest/api/2"


def _client() -> JiraClient:
    return JiraClient(base_url=BASE, api_token="secret-token", max_retries=1)


def _params(request: httpx.Request) -> dict[str, str]:
    return dict(request.url.params)


@respx.mock
async def test_bearer_token_and_api_v2():
    me = load_dc("user_search_single.json")[0]
    route = respx.get(f"{API}/myself").mock(return_value=httpx.Response(200, json=me))
    async with _client() as jira:
        user = await jira.get_myself()
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"
    assert user.jira_account_id == me["key"]
    assert user.name == me["name"]


def test_from_db_needs_only_url_and_token(db_session):
    db_session.add_all([
        AppSetting(key="jira_base_url", value=BASE),
        AppSetting(key="jira_api_token", value="secret-token"),
    ])
    db_session.commit()
    jira = JiraClient.from_db(db_session)
    assert jira.base_url == BASE
    assert jira.api_token == "secret-token"


def test_missing_token_is_an_error(monkeypatch):
    class _NoEnv:
        jira_base_url = None
        jira_api_token = None

    monkeypatch.setattr(jira_client, "get_settings", lambda: _NoEnv())
    with pytest.raises(JiraClientError):
        JiraClient(base_url=BASE, api_token=None)


@respx.mock
async def test_iter_issues_pages_by_start_at_with_stable_order():
    issues = [load_dc(f"issue_{k}.json") for k in ("OS-91030", "OS-91031", "RFA-4610")]
    pages = {0: issues[:2], 2: issues[2:]}
    seen: list[dict] = []

    def handler(request):
        params = _params(request)
        seen.append(params)
        start = int(params["startAt"])
        return httpx.Response(200, json={
            "startAt": start, "maxResults": 2, "total": 3, "issues": pages[start],
        })

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        keys = [i.key async for i in jira.iter_issues('project = "OS"', max_results=2, expand="changelog")]

    assert keys == ["OS-91030", "OS-91031", "RFA-4610"]
    assert [p["startAt"] for p in seen] == ["0", "2"]
    assert seen[0]["jql"] == 'project = "OS" ORDER BY key ASC'
    assert seen[0]["validateQuery"] == "warn"
    assert seen[0]["expand"] == "changelog"


@respx.mock
async def test_iter_issues_keeps_explicit_order():
    seen: list[str] = []

    def handler(request):
        seen.append(_params(request)["jql"])
        return httpx.Response(200, json={"startAt": 0, "maxResults": 100, "total": 0, "issues": []})

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        assert [i async for i in jira.iter_issues("project = OS ORDER BY created DESC")] == []
    assert seen == ["project = OS ORDER BY created DESC"]


@respx.mock
async def test_iter_issue_keys_reads_only_keys():
    seen: list[dict] = []

    def handler(request):
        params = _params(request)
        seen.append(params)
        start = int(params["startAt"])
        batch = (
            [{"id": "258783", "key": "OS-91030"}, {"id": "258784", "key": "OS-91031"}]
            if start == 0 else [{"id": 94555, "key": "RFA-4610"}]
        )
        return httpx.Response(200, json={"startAt": start, "maxResults": 1000, "total": 3, "issues": batch})

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        pairs = [p async for p in jira.iter_issue_keys('project = "OS"')]

    assert pairs == [("OS-91030", "258783"), ("OS-91031", "258784"), ("RFA-4610", "94555")]
    assert seen[0]["fields"] == "key"
    assert seen[0]["maxResults"] == "1000"
    assert seen[0]["jql"] == 'project = "OS" ORDER BY key ASC'
    assert [p["startAt"] for p in seen] == ["0", "2"]


@respx.mock
async def test_get_projects_reads_bare_list():
    respx.get(f"{API}/project").mock(return_value=httpx.Response(200, json=[
        {"id": "10901", "key": "OS", "name": "1С", "projectTypeKey": "software"},
        {"id": "10500", "key": "RFA", "name": "Инициативы", "projectTypeKey": "business"},
    ]))
    async with _client() as jira:
        projects = await jira.get_projects()
        iterated = [p.key async for p in jira.iter_projects()]
    assert [(p.id, p.key) for p in projects] == [("10901", "OS"), ("10500", "RFA")]
    assert iterated == ["OS", "RFA"]


@respx.mock
async def test_search_users_uses_username_param():
    users_raw = load_dc("user_search.json")
    route = respx.get(f"{API}/user/search").mock(return_value=httpx.Response(200, json=users_raw))
    async with _client() as jira:
        users = await jira.search_users("Иванов", max_results=20)
    assert _params(route.calls.last.request) == {"username": "Иванов", "maxResults": "20"}
    assert [u.jira_account_id for u in users] == [u["key"] for u in users_raw]
    assert [u.name for u in users] == [u["name"] for u in users_raw]
```

`tests/test_settings_jira_endpoint.py`:

```python
"""Настройки Jira: адрес и персональный токен, почта больше не нужна."""
import httpx
import respx
from fastapi.testclient import TestClient

from app.api.endpoints import settings as settings_ep
from app.database import get_db
from app.main import app
from tests.dc_fixtures import load_dc


def test_jira_settings_have_no_email(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        put = client.put("/api/v1/settings/jira", json={"base_url": "jira.example.test", "api_token": "tok"})
        got = client.get("/api/v1/settings/jira")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 200
    assert got.json() == {"base_url": "https://jira.example.test", "has_token": True}


@respx.mock
async def test_jira_test_endpoint_uses_bearer_token():
    me = load_dc("user_search_single.json")[0]
    route = respx.get("https://jira.example.test/rest/api/2/myself").mock(
        return_value=httpx.Response(200, json=me)
    )
    result = await settings_ep.test_jira_credentials(
        settings_ep.JiraTestRequest(base_url="https://jira.example.test", api_token="tok")
    )
    assert result.connected is True
    assert result.user_name == me["displayName"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
```

Rewrite `tests/test_jira_client_search_users.py`:

```python
"""Поиск пользователей Jira DC: параметр username, пользователь по key."""
from unittest.mock import AsyncMock

from app.connectors.jira_client import JiraClient


async def test_search_users_parses_dc_response():
    fake_response = [
        {
            "key": "JIRAUSER1",
            "name": "ivanov",
            "displayName": "Иванов",
            "emailAddress": "ivanov@example.com",
            "active": True,
            "avatarUrls": {"48x48": "https://example.com/a.png"},
        },
        {
            "key": "JIRAUSER2",
            "name": "petrov",
            "displayName": "Петров",
            "emailAddress": None,
            "active": False,
            "avatarUrls": {"48x48": "https://example.com/b.png"},
        },
    ]

    client = JiraClient(base_url="https://jira.example.test", api_token="t")
    client._request = AsyncMock(return_value=fake_response)

    users = await client.search_users("ив")
    client._request.assert_awaited_once_with(
        "GET", "/user/search", params={"username": "ив", "maxResults": 20},
    )
    assert len(users) == 2
    assert users[0].jira_account_id == "JIRAUSER1"
    assert users[0].name == "ivanov"
    assert users[0].display_name == "Иванов"
    assert users[0].is_active is True
    assert users[1].email is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/connectors/test_jira_dc_client.py tests/test_settings_jira_endpoint.py tests/test_jira_client_search_users.py -v`
Expected: FAIL — `JiraClientError: Missing Jira credentials` (клиент ещё требует почту), `ValidationError` у `JiraTestRequest` без `email`, `AttributeError: ... 'iter_issue_keys'`, в ответе настроек есть `email`.

- [ ] **Step 3: Rewrite the client**

Replace the whole of `app/connectors/jira_client.py` with:

```python
"""Jira Data Center HTTP client (REST API v2): вход по токену, повторы, пагинация."""

import asyncio
import re
from datetime import datetime
from typing import AsyncIterator, List, Optional, Tuple

import httpx

from app.config import get_settings
from app.connectors.schemas import (
    JiraCommentSchema,
    JiraCommentsResponseSchema,
    JiraIssueSchema,
    JiraProjectSchema,
    JiraSearchResponseSchema,
    JiraUserSchema,
    JiraWorklogSchema,
    JiraWorklogsResponseSchema,
)

API_PREFIX = "/rest/api/2"

#: Поля задачи по умолчанию, если вызывающий не передал свой список.
DEFAULT_ISSUE_FIELDS = [
    "summary", "description", "issuetype", "status",
    "priority", "project", "parent", "creator", "reporter",
    "assignee", "created", "updated", "duedate",
]

_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)


def _with_stable_order(jql: str) -> str:
    """Добавить ``ORDER BY key ASC``, если сортировка в JQL не задана.

    Поиск DC листается смещением: без устойчивой сортировки задача, изменённая
    во время обхода, уезжает в конец выборки, соседи сдвигаются, и одна из них
    пропускается.
    """
    if _ORDER_BY_RE.search(jql):
        return jql
    return f"{jql} ORDER BY key ASC"


class JiraClientError(Exception):
    """Base exception for Jira client errors."""
    pass


class JiraAuthError(JiraClientError):
    """Authentication failed."""
    pass


class JiraRateLimitError(JiraClientError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class JiraClient:
    """Async HTTP client for Jira Data Center REST API v2.

    - Вход: ``Authorization: Bearer <персональный токен>``
    - Поиск задач: ``GET /search`` со смещением ``startAt`` и ``total``
    - Повторы с экспоненциальной паузой, отдельная ветка для 429
    """

    @classmethod
    def from_db(cls, db) -> "JiraClient":
        """Создать клиент с адресом и токеном из app_settings (fallback на .env)."""
        from app.models.app_setting import AppSetting

        def _get(key: str) -> Optional[str]:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else None

        return cls(base_url=_get("jira_base_url"), api_token=_get("jira_api_token"))

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        request_delay: float = 0.1,  # 100ms base for retry backoff
        max_retries: int = 5,
    ):
        settings = get_settings()

        self.base_url = (base_url or settings.jira_base_url or "").rstrip("/")
        self.api_token = api_token or settings.jira_api_token
        self.request_delay = request_delay
        self.max_retries = max_retries

        if not (self.base_url and self.api_token):
            raise JiraClientError(
                "Missing Jira credentials. Set JIRA_BASE_URL, JIRA_API_TOKEN"
            )

        self._headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "JiraClient":
        """Context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ):
        """Make HTTP request with retry logic."""
        if not self._client:
            raise JiraClientError("Client not initialized. Use async context manager.")

        url = f"{API_PREFIX}{path}"

        for attempt in range(self.max_retries):
            try:
                # Пауза только на повторе; на 429 отдельная ветка ниже
                # спит столько, сколько попросил сервер (Retry-After).
                if attempt > 0:
                    delay = self.request_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise JiraRateLimitError(retry_after)

                # Handle auth errors
                if response.status_code == 401:
                    raise JiraAuthError("Invalid credentials")

                if response.status_code == 403:
                    raise JiraAuthError("Access forbidden. Check permissions.")

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if attempt == self.max_retries - 1:
                    raise JiraClientError(f"HTTP error: {e}")
            except httpx.RequestError as e:
                # Network errors (DNS fail / connection refused / timeout):
                # эти проблемы держатся секунды-минуты, экспоненциальный backoff
                # с базой 1s даёт 1, 2, 4, 8 сек — хватает на большинство глитчей.
                if attempt == self.max_retries - 1:
                    raise JiraClientError(f"Request failed: {e}")
                await asyncio.sleep(1.0 * (2 ** attempt))

        raise JiraClientError("Max retries exceeded")

    # === User methods ===

    async def get_myself(self) -> JiraUserSchema:
        """Get current authenticated user."""
        data = await self._request("GET", "/myself")
        return JiraUserSchema(**data)

    async def search_users(
        self,
        query: str,
        max_results: int = 20,
    ) -> List[JiraUserSchema]:
        """Поиск пользователей Jira DC по логину, имени или почте.

        ``GET /user/search?username=`` — в DC параметр называется ``username``
        и ищет по всем трём признакам; неактивные учётки не возвращаются.
        """
        raw = await self._request(
            "GET",
            "/user/search",
            params={"username": query, "maxResults": max_results},
        )
        return [JiraUserSchema.model_validate(item) for item in raw]

    # === Project methods ===

    async def get_projects(self) -> List[JiraProjectSchema]:
        """Все проекты, видимые токену: ``GET /project`` отдаёт массив целиком."""
        data = await self._request("GET", "/project")
        return [JiraProjectSchema.model_validate(p) for p in data]

    async def iter_projects(self) -> AsyncIterator[JiraProjectSchema]:
        """Iterate through all projects."""
        for project in await self.get_projects():
            yield project

    # === Issue methods ===

    async def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
        fields: Optional[List[str]] = None,
        expand: Optional[str] = None,
    ) -> JiraSearchResponseSchema:
        """Одна страница поиска ``GET /search`` (смещение ``startAt``).

        ``validateQuery=warn``: ключ задачи, которой нет в Jira, даёт
        предупреждение, а не ошибку всего запроса — точечное обновление по
        списку ключей не падает из-за одной удалённой задачи.
        """
        params: dict = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ",".join(fields or DEFAULT_ISSUE_FIELDS),
            "validateQuery": "warn",
        }
        if expand:
            params["expand"] = expand
        data = await self._request("GET", "/search", params=params)
        return JiraSearchResponseSchema(**data)

    async def iter_issues(
        self,
        jql: str,
        max_results: int = 100,
        fields: Optional[List[str]] = None,
        expand: Optional[str] = None,
    ) -> AsyncIterator[JiraIssueSchema]:
        """Все задачи по JQL, страницами по ``max_results`` до ``total``."""
        jql = _with_stable_order(jql)
        start_at = 0
        while True:
            response = await self.search_issues(
                jql=jql,
                start_at=start_at,
                max_results=max_results,
                fields=fields,
                expand=expand,
            )
            for issue in response.issues:
                yield issue
            start_at += len(response.issues)
            if not response.issues or start_at >= response.total:
                break

    async def iter_issue_keys(
        self,
        jql: str,
        page_size: int = 1000,
    ) -> AsyncIterator[Tuple[str, str]]:
        """Пары ``(ключ, id)`` всех задач по JQL — без разбора полей схемой.

        Для сверки задач при переезде: на десятки тысяч задач нужны только
        ключ и id.
        """
        jql = _with_stable_order(jql)
        start_at = 0
        while True:
            data = await self._request(
                "GET",
                "/search",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": page_size,
                    "fields": "key",
                    "validateQuery": "warn",
                },
            )
            issues = data.get("issues") or []
            for issue in issues:
                yield issue["key"], str(issue["id"])
            start_at += len(issues)
            if not issues or start_at >= int(data.get("total") or 0):
                break

    async def get_status_changes(self, issue_key: str) -> List[Tuple[str, str]]:
        """История смен статуса задачи: список ``(когда ISO-строкой, новый статус)``.

        Полный changelog с пагинацией — в bulk-поиске Jira отдаёт только
        последние 40 записей, а пауза могла быть раньше.
        """
        changes: List[Tuple[str, str]] = []
        start_at = 0
        while True:
            data = await self._request(
                "GET",
                f"/issue/{issue_key}/changelog",
                params={"startAt": start_at, "maxResults": 100},
            )
            values = data.get("values", [])
            for entry in values:
                created = entry.get("created")
                if not created:
                    continue
                for item in entry.get("items", []):
                    if item.get("field") == "status" and item.get("toString"):
                        changes.append((created, item["toString"]))
            start_at += len(values)
            if data.get("isLast") or not values or start_at >= data.get("total", 0):
                break
        changes.sort(key=lambda c: c[0])
        return changes

    # === Worklog methods ===

    async def get_worklogs_for_issue(
        self,
        issue_id: str,
        start_at: int = 0,
        max_results: int = 100,
    ) -> JiraWorklogsResponseSchema:
        """Get worklogs for a specific issue."""
        data = await self._request(
            "GET",
            f"/issue/{issue_id}/worklog",
            params={"startAt": start_at, "maxResults": max_results},
        )
        return JiraWorklogsResponseSchema(**data)

    async def iter_worklogs_for_issue(
        self,
        issue_id: str,
        max_results: int = 100,
    ) -> AsyncIterator[JiraWorklogSchema]:
        """Iterate through all worklogs for an issue."""
        start_at = 0
        while True:
            response = await self.get_worklogs_for_issue(
                issue_id=issue_id,
                start_at=start_at,
                max_results=max_results,
            )
            for worklog in response.worklogs:
                yield worklog
            if not response.has_more:
                break
            start_at += max_results

    # === Comment methods ===

    async def get_comments_for_issue(
        self,
        issue_id: str,
        start_at: int = 0,
        max_results: int = 100,
    ) -> JiraCommentsResponseSchema:
        """Get comments for a specific issue."""
        data = await self._request(
            "GET",
            f"/issue/{issue_id}/comment",
            params={"startAt": start_at, "maxResults": max_results},
        )
        return JiraCommentsResponseSchema(**data)

    async def iter_comments_for_issue(
        self,
        issue_id: str,
        max_results: int = 100,
    ) -> AsyncIterator[JiraCommentSchema]:
        """Iterate through all comments for an issue."""
        start_at = 0
        while True:
            response = await self.get_comments_for_issue(
                issue_id=issue_id,
                start_at=start_at,
                max_results=max_results,
            )
            for comment in response.comments:
                yield comment
            if not response.has_more:
                break
            start_at += max_results

    async def iter_deleted_worklog_ids(self, since: datetime) -> AsyncIterator[int]:
        """GET /worklog/deleted?since={ms} — ID ворклогов, удалённых с момента.

        Пагинация идентична worklog/updated: lastPage + until.
        Yields int worklog IDs.
        """
        since_ms = int(since.timestamp() * 1000)
        while True:
            data = await self._request("GET", "/worklog/deleted", params={"since": since_ms})
            for item in data.get("values", []):
                yield item["worklogId"]
            if data.get("lastPage", True):
                break
            since_ms = data["until"]

    async def get_worklogs_updated_since(
        self,
        since: datetime,
    ) -> AsyncIterator[JiraWorklogSchema]:
        """Bulk worklog fetch: worklog/updated → worklog/list.

        Шаг 1: GET /worklog/updated?since={ms} — пагинация по lastPage.
        Шаг 2: POST /worklog/list батчами по 1000 ID.
        Возвращает JiraWorklogSchema каждого worklog с заполненным issueId.
        """
        since_ms = int(since.timestamp() * 1000)
        worklog_ids: list[int] = []

        while True:
            data = await self._request("GET", "/worklog/updated", params={"since": since_ms})
            worklog_ids.extend(item["worklogId"] for item in data.get("values", []))
            if data.get("lastPage", True):
                break
            since_ms = data["until"]

        for i in range(0, len(worklog_ids), 1000):
            batch = worklog_ids[i : i + 1000]
            data = await self._request("POST", "/worklog/list", json={"ids": batch})
            for wl_data in data:
                yield JiraWorklogSchema(**wl_data)

    # === Field discovery methods ===

    async def get_fields(self) -> list[dict]:
        """Получить список всех полей Jira (включая кастомные)."""
        data = await self._request("GET", "/field")
        return data

    async def get_editable_field_ids(self, issue_key: str) -> set[str]:
        """ID полей, доступных на карточке задачи.

        Jira хранит значения кастомных полей и после переезда задачи в проект,
        где такого поля на экране нет: значение остаётся в базе и приезжает по
        API, хотя никто его больше не видит и не может изменить. Единственный
        способ отличить живое значение от мёртвого — спросить, какие поля вообще
        доступны на карточке этой задачи.
        """
        data = await self._request("GET", f"/issue/{issue_key}/editmeta")
        fields = data.get("fields") or {}
        return set(fields.keys())

    async def get_issue_types(self) -> list[dict]:
        """Получить все типы задач Jira (каталог issuetype)."""
        data = await self._request("GET", "/issuetype")
        return data

    async def get_field_configured_options(self, field_id: str) -> list[str]:
        """Получить все сконфигурированные опции select/multi-select поля.

        Обходит все контексты поля и возвращает объединение включённых опций.
        Возвращает пустой список, если поле не имеет опций (user/team picker и т.п.).
        """
        values: set[str] = set()
        try:
            contexts = await self._request("GET", f"/field/{field_id}/context")
        except JiraClientError:
            return []
        for ctx in contexts.get("values", []):
            ctx_id = ctx.get("id")
            if not ctx_id:
                continue
            start_at = 0
            while True:
                page = await self._request(
                    "GET",
                    f"/field/{field_id}/context/{ctx_id}/option",
                    params={"startAt": start_at, "maxResults": 100},
                )
                for opt in page.get("values", []):
                    if opt.get("disabled"):
                        continue
                    val = opt.get("value")
                    if val:
                        values.add(val)
                if page.get("isLast", True):
                    break
                start_at += 100
        return sorted(values)

    async def get_field_distinct_values(
        self,
        field_id: str,
        max_issues: int = 1000,
    ) -> list[str]:
        """Получить уникальные значения кастомного поля.

        Сначала пытаемся через сконфигурированные опции поля — это полный список
        и быстрее. Если опций нет (поле типа user/team picker), сканируем задачи.
        """
        options = await self.get_field_configured_options(field_id)
        if options:
            return options

        jql = f'"{field_id}" is not EMPTY ORDER BY updated DESC'
        values: set[str] = set()
        start_at = 0
        # Мы просим только нужное кастомное поле, но Pydantic-схема ответа
        # требует базовые поля (summary/issuetype/status/project) — включаем их.
        required_fields = ["summary", "issuetype", "status", "project", field_id]
        while start_at < max_issues:
            response = await self.search_issues(
                jql=jql,
                start_at=start_at,
                max_results=100,
                fields=required_fields,
            )
            for issue in response.issues:
                raw = issue.fields._extra.get(field_id)
                if raw is None:
                    continue
                # Handle select/multi-select fields (dict with 'value' key)
                if isinstance(raw, dict) and "value" in raw:
                    values.add(raw["value"])
                elif isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict) and "value" in item:
                            values.add(item["value"])
                        elif isinstance(item, str):
                            values.add(item)
                elif isinstance(raw, str):
                    values.add(raw)
            if not response.has_more:
                break
            start_at += 100
        return sorted(values)

    # === Utility methods ===

    async def test_connection(self) -> bool:
        """Test connection and credentials."""
        try:
            await self.get_myself()
            return True
        except JiraClientError:
            return False
```

(Ворклоги потоком, статусы, история задачи и опции полей DC — Task 8; здесь их тела только переехали на `/rest/api/2`.)

- [ ] **Step 4: Offset search response schema**

In `app/connectors/schemas.py` replace `JiraSearchResponseSchema` (lines 313–337) with:

```python
class JiraSearchResponseSchema(BaseModel):
    """Страница поиска задач Jira DC (``GET /search``): смещение ``startAt`` + ``total``."""

    startAt: int = 0
    maxResults: int = 50
    total: int = 0
    issues: List[JiraIssueSchema] = Field(default_factory=list)

    @property
    def has_more(self) -> bool:
        """Check if there are more results."""
        return bool(self.issues) and self.startAt + len(self.issues) < self.total
```

Delete the class `JiraProjectsResponseSchema` (lines 353–363) — `GET /project` в DC отдаёт массив.

- [ ] **Step 5: Settings without email**

`app/api/endpoints/settings.py` — replace the three schemas:

```python
class JiraSettingsResponse(BaseModel):
    email: Optional[str] = None
    base_url: Optional[str] = None
    has_token: bool = False


class JiraSettingsUpdate(BaseModel):
    email: Optional[str] = None
    api_token: Optional[str] = None
    base_url: Optional[str] = None
```

with:

```python
class JiraSettingsResponse(BaseModel):
    base_url: Optional[str] = None
    has_token: bool = False


class JiraSettingsUpdate(BaseModel):
    api_token: Optional[str] = None
    base_url: Optional[str] = None
```

and

```python
class JiraTestRequest(BaseModel):
    email: str
    api_token: str
    base_url: str
```

with:

```python
class JiraTestRequest(BaseModel):
    api_token: str
    base_url: str
```

Replace `get_jira_settings` and `save_jira_settings` with:

```python
def _jira_settings(db: Session) -> JiraSettingsResponse:
    return JiraSettingsResponse(
        base_url=_get_setting(db, "jira_base_url"),
        has_token=_get_setting(db, "jira_api_token") is not None,
    )


@router.get("/jira", response_model=JiraSettingsResponse)
async def get_jira_settings(db: Session = Depends(get_db)):
    """Получить сохранённые Jira-настройки (токен не возвращается)."""
    return _jira_settings(db)


@router.put("/jira", response_model=JiraSettingsResponse)
async def save_jira_settings(
    body: JiraSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Сохранить адрес Jira и персональный токен в БД."""
    if body.api_token is not None:
        _set_setting(db, "jira_api_token", body.api_token)
    if body.base_url is not None:
        _set_setting(db, "jira_base_url", _with_scheme(body.base_url))
    db.commit()
    return _jira_settings(db)
```

In `test_jira_credentials` replace:

```python
        async with JiraClient(
            base_url=body.base_url,
            email=body.email,
            api_token=body.api_token,
        ) as jira:
```

with:

```python
        async with JiraClient(
            base_url=_with_scheme(body.base_url),
            api_token=body.api_token,
        ) as jira:
```

Строка `jira_email` в базе остаётся как есть — её больше никто не читает.

- [ ] **Step 6: Sync endpoints, stable order in sync, config**

`app/api/endpoints/sync.py`:
- `test_jira_connection` docstring first line `"""Test connection to Jira Cloud.` → `"""Проверка подключения к Jira.`
- `browse_jira_projects` docstring first line `"""Список проектов из Jira Cloud для выбора в scope.` → `"""Список проектов из Jira для выбора в scope.`
- replace `            async for p in jira.iter_projects(max_results=50):` with `            for p in await jira.get_projects():`

`app/services/sync_service.py` — in `sync_issues` producer (line ~1206) and in `sync_team_issues` (line ~1615) replace `jql += " ORDER BY updated ASC"` with:

```python
                jql += " ORDER BY key ASC"
```

(в `sync_team_issues` отступ 12 пробелов: `            jql += " ORDER BY key ASC"`). Поиск DC листается смещением — сортировка по изменяемому `updated` теряет задачи, изменённые во время обхода.

`app/config.py` — replace:

```python
    # Jira Cloud credentials
    jira_base_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
```

with:

```python
    # Jira Data Center: адрес и персональный токен (Bearer)
    jira_base_url: Optional[str] = None
    jira_api_token: Optional[str] = None
```

`.env.example` — replace:

```
# Jira Cloud credentials
# Get API token from: https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token-here
```

with:

```
# Jira Data Center: адрес и персональный токен (профиль → Персональные токены доступа)
JIRA_BASE_URL=https://jira.example.ru
JIRA_API_TOKEN=your-personal-access-token
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/connectors/test_jira_dc_client.py tests/test_settings_jira_endpoint.py tests/test_jira_client_search_users.py tests/test_jira_client_worklog_bulk.py tests/test_sync_service_cancel.py tests/test_sync_service.py tests/test_sync_issues_since_override.py -v`
Expected: PASS.

Run: `grep -rn "rest/api/3\|nextPageToken\|search/jql\|jira_email\|JiraProjectsResponseSchema" app/ tests/ --include=*.py`
Expected: только `jira_email` в `app/connectors/confluence_client.py` и `tests/services/test_confluence_service.py` (их переводит на свои настройки Task 16) и в `tests/test_demo_db_anonymize.py` (остаётся: обезличивание обязано чистить старую строку в базе).

- [ ] **Step 8: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/connectors/jira_client.py app/connectors/schemas.py app/api/endpoints/settings.py app/api/endpoints/sync.py app/services/sync_service.py app/config.py .env.example tests/connectors/test_jira_dc_client.py tests/test_settings_jira_endpoint.py tests/test_jira_client_search_users.py
git commit -m "feat(jira-dc): клиент на REST API v2 с токеном и поиском со смещением" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Разбор истории изменений задачи

**Files:**
- Create: `app/connectors/changelog.py`
- Test: `tests/connectors/test_changelog.py`

- [ ] **Step 1: Write the failing test**

`tests/connectors/test_changelog.py`:

```python
"""История изменений Jira DC: смены статуса, смена категории, полнота."""
from app.connectors.changelog import category_changed_at, is_complete, status_changes

CATEGORIES = {"1": "new", "3": "indeterminate", "10205": "indeterminate", "10001": "done"}


def _status(frm: str, to: str, frm_name: str = "", to_name: str = "") -> dict:
    return {"field": "status", "fieldtype": "jira", "from": frm, "fromString": frm_name,
            "to": to, "toString": to_name}


def _history(created: str, *items: dict) -> dict:
    return {"id": created, "created": created, "items": list(items)}


T1 = "2026-09-12T08:00:00.000+0000"
T2 = "2026-09-20T10:00:00.000+0000"
T3 = "2026-10-01T12:30:00.000+0000"


def test_status_changes_sorted_by_time():
    changelog = {"total": 3, "histories": [
        _history(T3, _status("10205", "10001", "Тестирование", "Готово")),
        _history(T1, _status("1", "3", "Открыт", "В работе")),
        _history(T2, {"field": "assignee", "from": "a", "to": "b"}),
    ]}
    assert status_changes(changelog) == [(T1, "В работе"), (T3, "Готово")]


def test_category_change_ignores_move_inside_category():
    changelog = {"total": 2, "histories": [
        _history(T1, _status("1", "3", "Открыт", "В работе")),
        _history(T2, _status("3", "10205", "В работе", "Тестирование")),
    ]}
    assert category_changed_at(changelog, CATEGORIES) == T1


def test_category_change_takes_last_one():
    changelog = {"total": 3, "histories": [
        _history(T3, _status("10205", "10001")),
        _history(T1, _status("1", "3")),
        _history(T2, _status("3", "10205")),
    ]}
    assert category_changed_at(changelog, CATEGORIES) == T3


def test_unknown_status_counts_as_change():
    changelog = {"total": 1, "histories": [_history(T2, _status("3", "777"))]}
    assert category_changed_at(changelog, CATEGORIES) == T2
    assert category_changed_at(changelog, None) == T2


def test_no_status_history_gives_none():
    changelog = {"total": 1, "histories": [_history(T1, {"field": "assignee", "from": "a", "to": "b"})]}
    assert category_changed_at(changelog, CATEGORIES) is None
    assert category_changed_at(None, CATEGORIES) is None
    assert status_changes(None) == []


def test_is_complete():
    assert is_complete({"total": 3, "histories": [_history(T1), _history(T2), _history(T3)]}) is True
    assert is_complete({"total": 5, "histories": [_history(T1)]}) is False
    assert is_complete({"histories": [_history(T1)]}) is True
    assert is_complete(None) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/connectors/test_changelog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.connectors.changelog'`.

- [ ] **Step 3: Write the module**

`app/connectors/changelog.py`:

```python
"""Разбор истории изменений задачи Jira DC (``expand=changelog``).

Формат: ``{"total": N, "histories": [{"created": "...", "items": [{"field":
"status", "from": "<id>", "fromString": "...", "to": "<id>", "toString": "..."}]}]}``.
Время ``created`` в DC приходит с одним и тем же смещением, поэтому строки
сравниваются как есть.
"""

from typing import Any, Optional


def _histories(changelog: Any) -> list[dict]:
    if not isinstance(changelog, dict):
        return []
    return [h for h in changelog.get("histories") or [] if isinstance(h, dict)]


def is_complete(changelog: Any) -> bool:
    """В ответе вся история: поиск может отдать только часть записей."""
    if not isinstance(changelog, dict):
        return True
    total = changelog.get("total")
    return not isinstance(total, int) or total <= len(_histories(changelog))


def status_changes(changelog: Any) -> list[tuple[str, str]]:
    """История смен статуса: ``(когда ISO-строкой, новый статус)`` по возрастанию времени."""
    out: list[tuple[str, str]] = []
    for history in _histories(changelog):
        created = history.get("created")
        if not created:
            continue
        for item in history.get("items") or []:
            if item.get("field") == "status" and item.get("toString"):
                out.append((created, item["toString"]))
    out.sort(key=lambda change: change[0])
    return out


def category_changed_at(
    changelog: Any, status_categories: Optional[dict[str, str]]
) -> Optional[str]:
    """Когда задача последний раз сменила категорию статуса (``new`` /
    ``indeterminate`` / ``done``) — то, что облако отдавало полем
    ``statuscategorychangedate``.

    ``status_categories`` — id статуса → ключ категории из ``GET /status``.
    Статус, которого нет в справочнике, считается сменой категории: лучше
    сдвинуть дату на этот переход, чем потерять его. ``None`` — категория ни
    разу не менялась (тогда берут дату создания задачи).
    """
    categories = status_categories or {}
    last: Optional[str] = None
    for history in sorted(_histories(changelog), key=lambda h: h.get("created") or ""):
        created = history.get("created")
        if not created:
            continue
        for item in history.get("items") or []:
            if item.get("field") != "status":
                continue
            before = categories.get(str(item.get("from")))
            after = categories.get(str(item.get("to")))
            if before is None or after is None or before != after:
                last = created
    return last
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.10 -m pytest tests/connectors/test_changelog.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/connectors/changelog.py tests/connectors/test_changelog.py
git commit -m "feat(jira-dc): разбор истории изменений задачи" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Клиент DC — ворклоги потоком, статусы, история задачи, опции полей

**Files:**
- Modify: `app/connectors/jira_client.py` (импорт, константы, `get_status_changes`, `get_worklogs_updated_since`, `get_field_configured_options`, `get_field_distinct_values`)
- Modify: `app/api/endpoints/sync.py:1-24` (импорт), `:851-861` (фильтр команды в `browse_jira_projects`)
- Test: `tests/connectors/test_jira_dc_client_extras.py`

- [ ] **Step 1: Write the failing test**

`tests/connectors/test_jira_dc_client_extras.py`:

```python
"""Клиент DC: ворклоги потоком, справочник статусов, история задачи, опции полей."""
import httpx
import respx

from app.connectors import jira_client
from app.connectors.jira_client import JiraClient, jql_field_ref
from tests.dc_fixtures import load_dc

BASE = "https://jira.example.test"
API = f"{BASE}/rest/api/2"


def _client() -> JiraClient:
    return JiraClient(base_url=BASE, api_token="secret-token", max_retries=1)


async def test_worklogs_stream_in_batches(monkeypatch):
    """Пачка уходит в POST /worklog/list, как только набралась."""
    monkeypatch.setattr(jira_client, "WORKLOG_LIST_BATCH", 10)
    updated = load_dc("worklog_updated.json")
    ids = [v["worklogId"] for v in updated["values"]]
    listed = load_dc("worklog_list.json")
    get_params: list[dict] = []
    post_batches: list[list[int]] = []

    async def fake_request(method, path, params=None, json=None):
        if method == "GET":
            assert path == "/worklog/updated"
            get_params.append(dict(params))
            return updated
        assert path == "/worklog/list"
        post_batches.append(list(json["ids"]))
        return listed

    client = JiraClient.__new__(JiraClient)
    client._request = fake_request  # type: ignore[method-assign]

    got = [wl async for wl in client.iter_worklogs_updated_since(0)]

    assert get_params == [{"since": 0}]
    assert [len(b) for b in post_batches[:-1]] == [10] * (len(post_batches) - 1)
    assert sum(post_batches, []) == ids
    assert len(got) == len(listed) * len(post_batches)
    assert got[0].author.jira_account_id == listed[0]["author"]["key"]


async def test_worklogs_stop_when_until_does_not_move():
    calls: list[int] = []

    async def fake_request(method, path, params=None, json=None):
        if method == "GET":
            calls.append(params["since"])
            return {"values": [], "until": params["since"], "lastPage": False}
        return []

    client = JiraClient.__new__(JiraClient)
    client._request = fake_request  # type: ignore[method-assign]
    assert [wl async for wl in client.iter_worklogs_updated_since(500)] == []
    assert calls == [500]


@respx.mock
async def test_get_statuses_and_issue_changelog():
    statuses = [{"id": "3", "name": "В работе", "statusCategory": {"key": "indeterminate"}}]
    respx.get(f"{API}/status").mock(return_value=httpx.Response(200, json=statuses))
    changelog = {"startAt": 0, "maxResults": 1, "total": 1, "histories": [
        {"created": "2026-09-12T08:00:00.000+0000",
         "items": [{"field": "status", "from": "1", "to": "3", "toString": "В работе"}]},
    ]}
    route = respx.get(f"{API}/issue/OS-91030").mock(
        return_value=httpx.Response(200, json={"key": "OS-91030", "changelog": changelog})
    )
    async with _client() as jira:
        assert await jira.get_statuses() == statuses
        assert await jira.get_issue_changelog("OS-91030") == changelog
        assert await jira.get_status_changes("OS-91030") == [
            ("2026-09-12T08:00:00.000+0000", "В работе"),
        ]
    assert dict(route.calls.last.request.url.params) == {"fields": "status", "expand": "changelog"}


@respx.mock
async def test_custom_field_options_from_dc_endpoint():
    respx.get(f"{API}/customFields/11092/options").mock(return_value=httpx.Response(200, json={
        "startAt": 0, "maxResults": 100, "total": 3, "isLast": True,
        "values": [
            {"id": "1", "value": "Команда Б", "disabled": False},
            {"id": "2", "value": "Команда А", "disabled": False},
            {"id": "3", "value": "Старая команда", "disabled": True},
        ],
    }))
    async with _client() as jira:
        assert await jira.get_field_configured_options("customfield_11092") == ["Команда А", "Команда Б"]


@respx.mock
async def test_custom_field_options_error_gives_empty_list():
    respx.get(f"{API}/customFields/11526/options").mock(
        return_value=httpx.Response(404, json=load_dc("custom_field_options_error.json"))
    )
    async with _client() as jira:
        assert await jira.get_field_configured_options("customfield_11526") == []
        assert await jira.get_field_configured_options("summary") == []


@respx.mock
async def test_distinct_values_fallback_uses_cf_reference():
    respx.get(f"{API}/customFields/11092/options").mock(
        return_value=httpx.Response(200, json={"values": [], "isLast": True})
    )
    issue = load_dc("issue_OS-91030.json")
    seen: list[str] = []

    def handler(request):
        seen.append(dict(request.url.params)["jql"])
        return httpx.Response(200, json={"startAt": 0, "maxResults": 100, "total": 1, "issues": [issue]})

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        values = await jira.get_field_distinct_values("customfield_11092")
    assert seen == ["cf[11092] is not EMPTY ORDER BY updated DESC"]
    assert values == [issue["fields"]["customfield_11092"]["value"]]


def test_jql_field_ref():
    assert jql_field_ref("customfield_11092") == "cf[11092]"
    assert jql_field_ref("summary") == '"summary"'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/connectors/test_jira_dc_client_extras.py -v`
Expected: FAIL — `ImportError: cannot import name 'jql_field_ref'`.

- [ ] **Step 3: Implement**

In `app/connectors/jira_client.py`:

After `from app.config import get_settings` add:

```python
from app.connectors.changelog import status_changes
```

After `_ORDER_BY_RE = re.compile(...)` add:

```python
#: Сколько id ворклогов уходит в один POST /worklog/list (предел Jira).
WORKLOG_LIST_BATCH = 1000


def jql_field_ref(field_id: str) -> str:
    """Ссылка на поле в JQL: ``customfield_11092`` → ``cf[11092]``, прочее — в кавычках."""
    numeric = field_id.split("_")[-1]
    if field_id.startswith("customfield_") and numeric.isdigit():
        return f"cf[{numeric}]"
    return f'"{field_id}"'
```

Replace the whole method `get_status_changes` with:

```python
    async def get_statuses(self) -> list[dict]:
        """Справочник статусов: ``id``, ``name``, ``statusCategory.key``."""
        return await self._request("GET", "/status")

    async def get_issue_changelog(self, issue_key: str) -> dict:
        """Полная история изменений задачи: ``GET /issue/{key}?expand=changelog``."""
        data = await self._request(
            "GET",
            f"/issue/{issue_key}",
            params={"fields": "status", "expand": "changelog"},
        )
        return data.get("changelog") or {}

    async def get_status_changes(self, issue_key: str) -> List[Tuple[str, str]]:
        """История смен статуса задачи: ``(когда ISO-строкой, новый статус)``."""
        return status_changes(await self.get_issue_changelog(issue_key))
```

Replace the whole method `get_worklogs_updated_since` with:

```python
    async def iter_worklogs_updated_since(
        self,
        since_ms: int,
    ) -> AsyncIterator[JiraWorklogSchema]:
        """Все ворклоги, созданные или изменённые с ``since_ms`` (мс эпохи).

        ``GET /worklog/updated`` листается по ``lastPage``/``until`` и отдаёт
        только id; содержимое — ``POST /worklog/list`` пачками по
        ``WORKLOG_LIST_BATCH``. Пачка уходит, как только набралась, поэтому
        полный обход (``since_ms=0``) не держит в памяти весь список id.
        """
        batch: list[int] = []
        cursor = since_ms
        while True:
            data = await self._request("GET", "/worklog/updated", params={"since": cursor})
            for item in data.get("values", []):
                batch.append(item["worklogId"])
                if len(batch) >= WORKLOG_LIST_BATCH:
                    async for worklog in self._worklog_list(batch):
                        yield worklog
                    batch = []
            until = data.get("until")
            if data.get("lastPage", True) or until is None or until == cursor:
                break
            cursor = until
        if batch:
            async for worklog in self._worklog_list(batch):
                yield worklog

    async def _worklog_list(self, ids: list[int]) -> AsyncIterator[JiraWorklogSchema]:
        data = await self._request("POST", "/worklog/list", json={"ids": ids})
        for wl_data in data:
            yield JiraWorklogSchema(**wl_data)

    async def get_worklogs_updated_since(
        self,
        since: datetime,
    ) -> AsyncIterator[JiraWorklogSchema]:
        """То же, что :meth:`iter_worklogs_updated_since`, с границей-датой."""
        async for worklog in self.iter_worklogs_updated_since(int(since.timestamp() * 1000)):
            yield worklog
```

Replace the whole method `get_field_configured_options` with:

```python
    async def get_field_configured_options(self, field_id: str) -> list[str]:
        """Включённые опции select-поля: ``GET /customFields/{n}/options`` (Jira DC).

        Не кастомное поле, нет прав или нет опций (поле-пользователь) — пустой
        список; тогда вызывающий перебирает задачи.
        """
        numeric = field_id.split("_")[-1]
        if not (field_id.startswith("customfield_") and numeric.isdigit()):
            return []
        values: set[str] = set()
        start_at = 0
        while True:
            try:
                page = await self._request(
                    "GET",
                    f"/customFields/{numeric}/options",
                    params={"startAt": start_at, "maxResults": 100},
                )
            except JiraClientError:
                return sorted(values)
            options = page.get("values") or []
            for opt in options:
                if not opt.get("disabled") and opt.get("value"):
                    values.add(opt["value"])
            start_at += len(options)
            is_last = page.get("isLast")
            if is_last is None:
                total = page.get("total")
                is_last = not (isinstance(total, int) and start_at < total)
            if is_last or not options:
                break
        return sorted(values)
```

In `get_field_distinct_values` replace:

```python
        jql = f'"{field_id}" is not EMPTY ORDER BY updated DESC'
```

with:

```python
        jql = f"{jql_field_ref(field_id)} is not EMPTY ORDER BY updated DESC"
```

In `app/api/endpoints/sync.py` replace the import line

```python
from app.connectors.jira_client import JiraClient, JiraClientError, JiraAuthError
```

with

```python
from app.connectors.jira_client import JiraClient, JiraClientError, JiraAuthError, jql_field_ref
```

and in `browse_jira_projects` replace:

```python
                clauses = " OR ".join(f'"{fid}" = "{team}"' for fid in team_field_ids)
```

with:

```python
                team_escaped = team.replace('"', '\\"')
                clauses = " OR ".join(f'{jql_field_ref(fid)} = "{team_escaped}"' for fid in team_field_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/connectors/test_jira_dc_client_extras.py tests/test_jira_client_worklog_bulk.py tests/connectors/test_jira_dc_client.py -v`
Expected: PASS (существующие тесты пакетов ворклогов проходят и на потоковой реализации).

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/connectors/jira_client.py app/api/endpoints/sync.py tests/connectors/test_jira_dc_client_extras.py
git commit -m "feat(jira-dc): ворклоги потоком, статусы, история и опции полей DC" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: «Статус изменён» и дни паузы из истории изменений

В DC нет `statuscategorychangedate`. Синк просит у поиска `expand=changelog` и считает `status_changed_at` = время последнего перехода, сменившего категорию статуса (справочник `GET /status`, один раз за проход), иначе дата создания. Дни паузы считаются из той же истории в поиске — без отдельного запроса на задачу. Сколько записей истории DC кладёт в поиск, не проверено: неполную историю (`total` > записей) задача дочитывает отдельным запросом.

**Files:**
- Modify: `app/connectors/schemas.py:92-128` (`JiraIssueFieldsSchema`), `:163-171` (`JiraIssueSchema`)
- Modify: `app/services/sync_service.py` — импорт; атрибут класса и два метода у `SyncService`; `_upsert_issue:948`; `sync_issues:1152, 1192-1211, 1232-1265`; `sync_paused_days:1360-1415`; `refresh_issues_by_keys:1448, 1467-1490, 1527`; `sync_team_issues:1559, 1592-1625, 1658`
- Modify tests: `tests/test_kpi_issue_links.py`, `tests/test_sync_issues_since_override.py`, `tests/test_sync_plan_sources.py`, `tests/test_sync_service.py` (подделки `iter_issues` принимают `expand`), `tests/api/test_sync_category_verified.py:59`, `tests/test_service_epic_parent_move.py:36`
- Test: `tests/test_sync_status_changed_at.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sync_status_changed_at.py`:

```python
"""«Статус изменён» и дни паузы в Jira DC считаются из истории изменений."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.connectors.schemas import JiraIssueSchema
from app.models import Issue, Project
from app.services.sync_service import SyncService
from tests.dc_fixtures import load_dc

CATEGORIES = {"1": "new", "3": "indeterminate", "10205": "indeterminate"}


def _dc_issue(name: str = "issue_OS-91030.json", changelog=None) -> JiraIssueSchema:
    raw = load_dc(name)
    if changelog is not None:
        raw["changelog"] = changelog
    return JiraIssueSchema.model_validate(raw)


def _project(db):
    db.add(Project(id="p-os", jira_project_id="10901", key="OS", name="1С"))
    db.commit()


def test_status_changed_at_is_last_category_change(db_session):
    _project(db_session)
    svc = SyncService(db_session, MagicMock())
    svc._status_categories = CATEGORIES
    changelog = {"total": 2, "histories": [
        {"created": "2026-09-12T08:00:00.000+0000",
         "items": [{"field": "status", "from": "1", "to": "3"}]},
        {"created": "2026-09-20T10:00:00.000+0000",
         "items": [{"field": "status", "from": "3", "to": "10205"}]},
    ]}
    issue, _ = svc._upsert_issue(_dc_issue(changelog=changelog), "p-os")
    assert issue.status_changed_at == datetime(2026, 9, 12, 8, 0)


def test_status_changed_at_falls_back_to_created(db_session):
    _project(db_session)
    svc = SyncService(db_session, MagicMock())
    svc._status_categories = CATEGORIES
    issue, _ = svc._upsert_issue(_dc_issue(changelog={"total": 0, "histories": []}), "p-os")
    assert issue.status_changed_at is not None
    assert issue.status_changed_at == issue.jira_created_at


async def test_ensure_status_categories_builds_map():
    jira = MagicMock()
    jira.get_statuses = AsyncMock(return_value=[
        {"id": "1", "name": "Открыт", "statusCategory": {"key": "new"}},
        {"id": "3", "name": "В работе", "statusCategory": {"key": "indeterminate"}},
    ])
    svc = SyncService(MagicMock(), jira)
    await svc._ensure_status_categories()
    await svc._ensure_status_categories()
    assert svc._status_categories == {"1": "new", "3": "indeterminate"}
    jira.get_statuses.assert_awaited_once()


async def test_ensure_status_categories_survives_failure():
    jira = MagicMock()
    jira.get_statuses = AsyncMock(side_effect=RuntimeError("нет связи"))
    svc = SyncService(MagicMock(), jira)
    await svc._ensure_status_categories()
    assert svc._status_categories == {}


async def test_truncated_changelog_is_fetched_in_full():
    full = {"total": 2, "histories": [{"created": "a", "items": []}, {"created": "b", "items": []}]}
    jira = MagicMock()
    jira.get_issue_changelog = AsyncMock(return_value=full)
    svc = SyncService(MagicMock(), jira)

    issue = _dc_issue(changelog={"total": 2, "histories": [{"created": "a", "items": []}]})
    await svc._complete_changelog(issue)
    assert issue.changelog == full

    await svc._complete_changelog(issue)
    await svc._complete_changelog(_dc_issue())
    jira.get_issue_changelog.assert_awaited_once_with("OS-91030")


async def test_sync_issues_requests_changelog(db_session):
    _project(db_session)
    expands: list = []

    async def fake_iter_issues(jql, max_results, fields, expand=None):
        expands.append(expand)
        yield _dc_issue()

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    svc = SyncService(db_session, jira)
    await svc.sync_issues(project_keys=["OS"], incremental=False)
    assert expands == ["changelog"]
    assert db_session.query(Issue).filter_by(key="OS-91030").one().status_changed_at is not None


async def test_paused_days_read_from_search_changelog(db_session):
    _project(db_session)
    db_session.add(Issue(id="i1", jira_issue_id="258783", key="OS-91030", summary="s",
                         issue_type="Задача", status="В работе", project_id="p-os"))
    db_session.commit()
    changelog = {"total": 2, "histories": [
        {"created": "2026-09-01T09:00:00.000+0000",
         "items": [{"field": "status", "from": "3", "to": "9", "toString": "Приостановлено"}]},
        {"created": "2026-09-04T09:00:00.000+0000",
         "items": [{"field": "status", "from": "9", "to": "3", "toString": "В работе"}]},
    ]}
    expands: list = []

    async def fake_iter_issues(jql, max_results=100, fields=None, expand=None):
        expands.append(expand)
        yield _dc_issue(changelog=changelog)

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    jira.get_status_changes = AsyncMock()
    jira.get_issue_changelog = AsyncMock()
    svc = SyncService(db_session, jira)

    updated = await svc.sync_paused_days(project_keys=["OS"], incremental=False)

    assert updated == 1
    assert expands == ["changelog"]
    assert db_session.get(Issue, "i1").paused_days == 3.0
    jira.get_status_changes.assert_not_called()
    jira.get_issue_changelog.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_sync_status_changed_at.py -v`
Expected: FAIL — `AttributeError: 'SyncService' object has no attribute '_ensure_status_categories'`; `status_changed_at` = `None`.

- [ ] **Step 3: Schemas**

In `app/connectors/schemas.py`, in `JiraIssueFieldsSchema` delete the line `    statuscategorychangedate: Optional[str] = None` and in `__init__` replace the `known` set:

```python
        known = {
            "summary", "description", "issuetype", "status", "priority",
            "project", "parent", "creator", "reporter", "assignee", "created", "updated",
            "statuscategorychangedate", "duedate", "resolution", "resolutiondate",
            "issuelinks",
        }
```

with:

```python
        known = {
            "summary", "description", "issuetype", "status", "priority",
            "project", "parent", "creator", "reporter", "assignee", "created", "updated",
            "duedate", "resolution", "resolutiondate", "issuelinks",
        }
```

Replace `JiraIssueSchema` with:

```python
class JiraIssueSchema(BaseModel):
    """Jira issue from API response.

    ``changelog`` — история изменений, только при ``expand=changelog``.
    """

    id: str
    key: str
    fields: JiraIssueFieldsSchema
    changelog: Optional[dict] = None

    class Config:
        extra = "ignore"
```

- [ ] **Step 4: Sync service — categories, full history, status date**

In `app/services/sync_service.py`, after `from app.connectors.jira_client import JiraClient` add:

```python
from app.connectors.changelog import category_changed_at, is_complete, status_changes
```

In `class SyncService`, right after the class docstring (before `def __init__`), add:

```python
    #: id статуса → ключ категории (``GET /status``); грузится раз за проход.
    #: Атрибут класса: часть тестов создаёт сервис через ``__new__``.
    _status_categories: Optional[dict[str, str]] = None
```

After `_resolve_planned_field_ids` add:

```python
    async def _ensure_status_categories(self) -> None:
        """Справочник «статус → категория» для расчёта «статус изменён» из истории."""
        if self._status_categories is not None:
            return
        try:
            statuses = await self.jira.get_statuses()
        except Exception:
            logger.warning("Справочник статусов Jira недоступен — любая смена статуса "
                           "считается сменой категории")
            statuses = []
        categories: dict[str, str] = {}
        for status in statuses or []:
            if not isinstance(status, dict):
                continue
            category = status.get("statusCategory")
            if status.get("id") and isinstance(category, dict) and category.get("key"):
                categories[str(status["id"])] = category["key"]
        self._status_categories = categories

    async def _complete_changelog(self, jira_issue: JiraIssueSchema) -> None:
        """Дочитать историю задачи, если поиск отдал её не целиком.

        Сколько записей истории Jira DC кладёт в ответ поиска, не проверено:
        по обрывку «статус изменён» и дни паузы посчитались бы неверно.
        """
        if not isinstance(jira_issue.changelog, dict) or is_complete(jira_issue.changelog):
            return
        jira_issue.changelog = await self.jira.get_issue_changelog(jira_issue.key)
```

In `_upsert_issue` replace:

```python
            "status_changed_at": _parse_jira_datetime(jira_issue.fields.statuscategorychangedate),
```

with:

```python
            # В DC нет statuscategorychangedate: последняя смена категории
            # статуса по истории, а если её не было — дата создания задачи.
            "status_changed_at": _parse_jira_datetime(
                category_changed_at(jira_issue.changelog, self._status_categories)
                or jira_issue.fields.created
            ),
```

- [ ] **Step 5: Sync service — request history in the three issue paths**

In `sync_issues`, `refresh_issues_by_keys` and `sync_team_issues` replace each

```python
        await self._ensure_sprint_field_id()
```

with

```python
        await self._ensure_sprint_field_id()
        await self._ensure_status_categories()
```

In the three base field lists (`base_request_fields` in `sync_issues`, `base_fields` in `refresh_issues_by_keys` and `sync_team_issues`) delete the token `"statuscategorychangedate", ` — e.g.

```python
            "statuscategorychangedate", "duedate", "resolution", "resolutiondate",
```

becomes

```python
            "duedate", "resolution", "resolutiondate",
```

Add `expand="changelog",` to the three `iter_issues` calls:

- `sync_issues` producer:
```python
                async for ji in self.jira.iter_issues(
                    jql=jql,
                    max_results=100,
                    fields=request_fields,
                    expand="changelog",
                ):
```
- `refresh_issues_by_keys`:
```python
            async for jira_issue in self.jira.iter_issues(
                jql=jql,
                max_results=BATCH,
                fields=fields,
                expand="changelog",
            ):
```
- `sync_team_issues`:
```python
                async for jira_issue in self.jira.iter_issues(
                    jql=jql,
                    max_results=100,
                    fields=request_fields,
                    expand="changelog",
                ):
```

Before each `_upsert_issue(` call in these three methods insert the history completion line with the loop's indentation:

- `sync_issues` (before `                issue, created = self._upsert_issue(`):
```python
                await self._complete_changelog(jira_issue)
```
- `refresh_issues_by_keys` (before `                issue_row, _ = self._upsert_issue(`):
```python
                await self._complete_changelog(jira_issue)
```
- `sync_team_issues` (before `                    _, was_created = self._upsert_issue(`):
```python
                    await self._complete_changelog(jira_issue)
```

- [ ] **Step 6: Sync service — paused days from the same history**

Replace the body of `sync_paused_days` after the docstring with:

```python
        if not project_keys:
            project_keys = self._get_scope_project_keys() or [
                p.key for p in self.project_repo.get_all(limit=1000)
            ]
        if not project_keys:
            return 0
        started_at = datetime.utcnow()
        if since is None and incremental:
            state = self._get_sync_state("paused_days")
            if state and state.last_success_at:
                since = state.last_success_at
        projects_jql = ", ".join(f'"{k}"' for k in project_keys)
        statuses_jql = ", ".join(f'"{s}"' for s in PAUSED_STATUSES)
        jql = f"project in ({projects_jql}) AND status WAS IN ({statuses_jql})"
        if since:
            jql += f' AND updated >= "{since.strftime("%Y-%m-%d %H:%M")}"'

        # История статусов приходит в том же поиске (expand=changelog) — без
        # отдельного запроса на каждую задачу; неполную историю дочитываем.
        seen = 0
        updated = 0
        async for jira_issue in self.jira.iter_issues(
            jql=jql,
            max_results=100,
            fields=["summary", "issuetype", "status", "project"],
            expand="changelog",
        ):
            await self._check_cancelled()
            seen += 1
            issue = self.issue_repo.get_by_field("key", jira_issue.key)
            if not issue:
                continue
            await self._complete_changelog(jira_issue)
            days = paused_days_from_changes(status_changes(jira_issue.changelog))
            if issue.paused_days != days:
                issue.paused_days = days
                updated += 1
                if updated % 100 == 0:
                    self.db.commit()
        self._update_sync_state("paused_days", started_at)
        self.db.commit()
        logger.info(f"Paused days: {updated} of {seen} issues updated")
        return updated
```

Update the docstring of `sync_paused_days`: replace the paragraph «Отдельный проход после задач: история статусов приходит только поштучно, поэтому сначала JQL сужает выборку до задач, которые вообще бывали на паузе (в тенанте это сотни задач, а не сотня тысяч).» with «Отдельный проход после задач: JQL сужает выборку до задач, которые вообще бывали на паузе, история статусов приходит в том же поиске (``expand=changelog``).»

- [ ] **Step 7: Update existing test doubles**

```bash
sed -i 's/fake_iter_issues(jql, max_results, fields):/fake_iter_issues(jql, max_results, fields, expand=None):/' tests/test_kpi_issue_links.py tests/test_sync_issues_since_override.py tests/test_sync_plan_sources.py tests/test_sync_service.py
sed -i 's/^    ji.fields.statuscategorychangedate = None$/    ji.changelog = None/' tests/api/test_sync_category_verified.py tests/test_service_epic_parent_move.py
grep -rn "statuscategorychangedate" app/ tests/ --include=*.py
```

Expected: последний `grep` печатает только комментарии — docstring `category_changed_at` в `app/connectors/changelog.py` и комментарий у `status_changed_at` в `_upsert_issue`; в коде и тестах поля больше нет.

- [ ] **Step 8: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_sync_status_changed_at.py tests/test_paused_days.py tests/test_kpi_issue_links.py tests/test_sync_issues_since_override.py tests/test_sync_plan_sources.py tests/test_sync_service.py tests/api/test_sync_category_verified.py tests/test_service_epic_parent_move.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/connectors/schemas.py app/services/sync_service.py tests/test_sync_status_changed_at.py tests/test_kpi_issue_links.py tests/test_sync_issues_since_override.py tests/test_sync_plan_sources.py tests/test_sync_service.py tests/api/test_sync_category_verified.py tests/test_service_epic_parent_move.py
git commit -m "feat(jira-dc): «статус изменён» и дни паузы из истории изменений" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Иерархия — «Ссылка на эпик» и «Parent Link»

В DC `fields.parent` есть только у подзадач. Задача ссылается на эпик полем «Ссылка на эпик» (`gh-epic-link`, в DC `customfield_10107`), эпик на инициативу — «Parent Link» (`jpo-custom-field-parent`, `customfield_10100`); оба значения в ответах — строка-ключ (проверено на OS-91030, OS-92392, OS-93622, OS-89194, RFA-5020). id полей синк находит по типу, как уже делает со «Спринтом», и запрашивает их в каждом чтении задач.

**Files:**
- Modify: `app/services/sync_service.py:380-407` (списки ключей настроек), рядом с `_extract_user_field` — `_parent_key_of`; `:735-754` (`_ensure_sprint_field_id` → `_ensure_auto_field_ids`); `_upsert_issue:1078`; `sync_issues:1240`; `refresh_issues_by_keys:1500`; `sync_team_issues:1632`
- Test: `tests/test_sync_hierarchy_dc.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sync_hierarchy_dc.py`:

```python
"""Иерархия Jira DC: подзадача → parent, задача → «Ссылка на эпик», эпик → «Parent Link»."""
from unittest.mock import AsyncMock, MagicMock

from app.connectors.schemas import JiraIssueSchema
from app.models import AppSetting, Issue, Project
from app.services.sync_service import SyncService, _extract_sprints, _parent_key_of
from tests.dc_fixtures import load_dc

IDS = {
    "jira_epic_link_field_id": "customfield_10107",
    "jira_parent_link_field_id": "customfield_10100",
}


def _fields(name: str):
    return JiraIssueSchema.model_validate(load_dc(name)).fields


def test_parent_from_epic_link():
    assert _parent_key_of(_fields("issue_OS-91030.json"), IDS) == "OS-84096"


def test_parent_from_parent_link():
    assert _parent_key_of(_fields("issue_OS-89194.json"), IDS) == "RFA-4599"
    assert _parent_key_of(_fields("issue_RFA-5020.json"), IDS) == "RFA-4832"


def test_subtask_parent_wins():
    raw = load_dc("issue_OS-91030.json")
    raw["fields"]["parent"] = {"id": "1", "key": "OS-1"}
    assert _parent_key_of(JiraIssueSchema.model_validate(raw).fields, IDS) == "OS-1"


def test_no_configured_fields_no_parent():
    assert _parent_key_of(_fields("issue_OS-91030.json"), {}) is None


def test_sprint_parsed_from_dc_string():
    fields = load_dc("issue_OS-91030.json")["fields"]
    assert _extract_sprints(fields, "customfield_10109") == (
        "OS 20 SKLAD 16/10/2026", ["OS 20 SKLAD 16/10/2026"],
    )


async def test_auto_field_ids_found_by_type(db_session):
    db_session.add(AppSetting(key="jira_sprint_field_id", value="customfield_99999"))
    db_session.commit()
    jira = MagicMock()
    jira.get_fields = AsyncMock(return_value=load_dc("fields.json"))

    await SyncService(db_session, jira)._ensure_auto_field_ids()

    settings = {r.key: r.value for r in db_session.query(AppSetting).all()}
    assert settings["jira_sprint_field_id"] == "customfield_99999", "ручное значение не трогаем"
    assert settings["jira_epic_link_field_id"] == "customfield_10107"
    assert settings["jira_parent_link_field_id"] == "customfield_10100"


async def test_auto_field_ids_skip_jira_when_all_set(db_session):
    for key, value in {**IDS, "jira_sprint_field_id": "customfield_10109"}.items():
        db_session.add(AppSetting(key=key, value=value))
    db_session.commit()
    jira = MagicMock()
    jira.get_fields = AsyncMock()

    await SyncService(db_session, jira)._ensure_auto_field_ids()
    jira.get_fields.assert_not_called()


async def test_sync_links_story_to_epic_by_epic_link(db_session):
    db_session.add(Project(id="p-os", jira_project_id="10901", key="OS", name="1С"))
    for key, value in IDS.items():
        db_session.add(AppSetting(key=key, value=value))
    db_session.commit()
    requested: list[str] = []

    async def fake_iter_issues(jql, max_results, fields, expand=None):
        requested.extend(fields)
        # История раньше эпика: родитель достраивается вторым проходом.
        yield JiraIssueSchema.model_validate(load_dc("issue_OS-92392.json"))  # → эпик OS-89194
        yield JiraIssueSchema.model_validate(load_dc("issue_OS-89194.json"))  # → RFA-4599, его нет

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    await SyncService(db_session, jira).sync_issues(project_keys=["OS"], incremental=False)

    story = db_session.query(Issue).filter_by(key="OS-92392").one()
    epic = db_session.query(Issue).filter_by(key="OS-89194").one()
    assert story.parent_id == epic.id
    assert epic.parent_id is None
    assert "customfield_10107" in requested
    assert "customfield_10100" in requested
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_sync_hierarchy_dc.py -v`
Expected: FAIL — `ImportError: cannot import name '_parent_key_of'` (тест спринта при этом проходит — разбор строки DC уже работает).

- [ ] **Step 3: Setting keys and auto-discovered field types**

In `app/services/sync_service.py` replace:

```python
_ALL_PLANNED_KEYS = (
    _PLANNED_NUMERIC_SETTING_KEYS
    + _PLANNED_STRING_SETTING_KEYS
    + _RATING_SETTING_KEYS
    + _PLANNED_DATE_SETTING_KEYS
    + _KPI_FIELD_SETTING_KEYS
)
```

with:

```python
# Иерархия Jira DC: задача → эпик («Ссылка на эпик»), эпик → инициатива
# («Parent Link»). Ключи входят в общий список, чтобы поля запрашивались в
# каждом чтении задач и попадали в ``_extra``.
_HIERARCHY_FIELD_SETTING_KEYS = [
    "jira_epic_link_field_id",
    "jira_parent_link_field_id",
]
_ALL_PLANNED_KEYS = (
    _PLANNED_NUMERIC_SETTING_KEYS
    + _PLANNED_STRING_SETTING_KEYS
    + _RATING_SETTING_KEYS
    + _PLANNED_DATE_SETTING_KEYS
    + _KPI_FIELD_SETTING_KEYS
    + _HIERARCHY_FIELD_SETTING_KEYS
)

#: Поля Jira Software / Advanced Roadmaps с фиксированным типом: id находим по
#: типу и кладём в настройки сами — сопоставлять их вручную не нужно.
AUTO_FIELD_TYPES: dict[str, str] = {
    "jira_sprint_field_id": "com.pyxis.greenhopper.jira:gh-sprint",
    "jira_epic_link_field_id": "com.pyxis.greenhopper.jira:gh-epic-link",
    "jira_parent_link_field_id": "com.atlassian.jpo:jpo-custom-field-parent",
}
```

- [ ] **Step 4: Parent key resolution**

After `_author_as_user` add:

```python
def _parent_key_of(fields: Any, planned_ids: dict[str, Optional[str]]) -> Optional[str]:
    """Ключ родителя задачи в Jira DC.

    Подзадача ссылается на родителя полем ``parent``; задача на эпик —
    «Ссылкой на эпик»; эпик на инициативу — «Parent Link». Обе ссылки в DC
    приходят строкой-ключом. ``planned_ids`` — значения настроек
    (``_resolve_planned_field_ids``).
    """
    if fields.parent_key:
        return fields.parent_key
    extra = getattr(fields, "_extra", None) or {}
    for setting_key in _HIERARCHY_FIELD_SETTING_KEYS:
        field_id = planned_ids.get(setting_key)
        value = extra.get(field_id) if field_id else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
```

Replace the whole method `_ensure_sprint_field_id` with:

```python
    async def _ensure_auto_field_ids(self) -> None:
        """Найти «Спринт», «Ссылку на эпик» и «Parent Link», если их нет в настройках.

        Тип у этих полей фиксированный, поэтому ищем по типу и сохраняем;
        уже заданное значение (в том числе руками) не трогаем.
        """
        missing = {
            key: field_type for key, field_type in AUTO_FIELD_TYPES.items()
            if not self._get_setting(key)
        }
        if not missing:
            return
        try:
            fields = await self.jira.get_fields()
        except Exception:  # связь с Jira не настроена — не мешаем синку
            return
        found: dict[str, str] = {}
        for field in fields or []:
            if not isinstance(field, dict):
                continue
            field_type = (field.get("schema") or {}).get("custom")
            for key, wanted in missing.items():
                if field_type == wanted and key not in found:
                    found[key] = field["id"]
        for key, field_id in found.items():
            row = self.db.query(AppSetting).filter(AppSetting.key == key).first()
            if row is None:
                self.db.add(AppSetting(key=key, value=field_id))
            else:
                row.value = field_id
            logger.info("Jira field discovered: %s = %s", key, field_id)
        if found:
            self.db.commit()
```

Replace all three occurrences of `        await self._ensure_sprint_field_id()` with `        await self._ensure_auto_field_ids()`.

Replace both occurrences (in `sync_issues` and `refresh_issues_by_keys`, 16 spaces):

```python
                parent_key = jira_issue.fields.parent_key
```

with:

```python
                parent_key = _parent_key_of(jira_issue.fields, planned_field_ids)
```

In `sync_team_issues` (20 spaces) replace:

```python
                    parent_key = jira_issue.fields.parent_key
```

with:

```python
                    parent_key = _parent_key_of(jira_issue.fields, planned_field_ids)
```

In `_upsert_issue` replace:

```python
            after = (project_id, issue.issue_type, parent_id is not None or bool(jira_issue.fields.parent_key))
```

with:

```python
            after = (
                project_id,
                issue.issue_type,
                parent_id is not None or bool(_parent_key_of(jira_issue.fields, planned_ids)),
            )
```

Check: `grep -n "_ensure_sprint_field_id\|fields.parent_key" app/services/sync_service.py` печатает только строку внутри `_parent_key_of`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_sync_hierarchy_dc.py tests/test_service_epic_parent_move.py tests/test_sync_service.py tests/test_sync_plan_sources.py tests/api/test_sync_category_verified.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/sync_service.py tests/test_sync_hierarchy_dc.py
git commit -m "feat(jira-dc): родитель задачи из «Ссылки на эпик» и «Parent Link»" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Время ворклогов — московское «настенное», как в облаке

Облако отдавало время ворклогов и комментариев с поясом учётки (`+0300`), и в базе лежали московские часы. DC отдаёт `+0000` (у всех авторов в образцах `timeZone = Europe/Moscow`, а `started` — в UTC). Без перевода ворклоги около полуночи уедут на соседний день, а срок внесения часов в KPI («12:00 следующего рабочего дня») сдвинется на 3 часа. Москва без перехода на летнее время с 2014 года — фиксированное смещение `+03:00`, базы часовых поясов не нужно.

**Files:**
- Modify: `app/services/sync_service.py:5` (импорт), `:334-344` (`_drop_tz`)
- Modify: `app/connectors/schemas.py:206-219` (docstring `created_datetime`)
- Test: `tests/test_sync_wall_clock.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sync_wall_clock.py`:

```python
"""Время ворклогов и комментариев хранится московским «настенным», как было в облаке."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.connectors.schemas import JiraWorklogsResponseSchema
from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService, _drop_tz
from tests.dc_fixtures import load_dc


def test_drop_tz_converts_utc_to_moscow():
    assert _drop_tz(datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)) == datetime(2026, 9, 11, 10, 0)
    assert _drop_tz(datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc)) == datetime(2026, 9, 12, 1, 30)


def test_drop_tz_keeps_moscow_and_naive():
    msk = timezone(timedelta(hours=3))
    assert _drop_tz(datetime(2026, 7, 24, 10, 0, tzinfo=msk)) == datetime(2026, 7, 24, 10, 0)
    assert _drop_tz(datetime(2026, 7, 24, 10, 0)) == datetime(2026, 7, 24, 10, 0)
    assert _drop_tz(None) is None


def test_dc_worklog_stored_in_moscow_time(db_session):
    db_session.add(Project(id="p-os", jira_project_id="10901", key="OS", name="1С"))
    db_session.add(Issue(id="i1", jira_issue_id="258783", key="OS-91030", summary="s",
                         issue_type="Задача", status="В работе", project_id="p-os"))
    db_session.add(Employee(id="e1", jira_account_id="JIRAUSER90001",
                            display_name="Сотрудник 1", is_active=True))
    db_session.commit()
    wl = JiraWorklogsResponseSchema.model_validate(load_dc("worklogs_OS-91030.json")).worklogs[0]
    assert wl.started == "2026-09-11T07:00:00.000+0000"

    SyncService(db_session, MagicMock())._upsert_worklog(wl, "i1", "e1")
    db_session.commit()

    stored = db_session.query(Worklog).filter_by(jira_worklog_id=wl.id).one()
    assert stored.started_at == datetime(2026, 9, 11, 10, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_sync_wall_clock.py -v`
Expected: FAIL — `assert datetime(2026, 9, 11, 7, 0) == datetime(2026, 9, 11, 10, 0)`.

- [ ] **Step 3: Implement**

In `app/services/sync_service.py` replace `from datetime import date, datetime, timezone` with:

```python
from datetime import date, datetime, timedelta, timezone
```

Replace `_drop_tz` (lines 334–344) with:

```python
# Московское время без перехода на летнее (с 2014 года) — фиксированные +03:00.
JIRA_WALL_CLOCK_TZ = timezone(timedelta(hours=3), "MSK")


def _drop_tz(dt: Optional[datetime]) -> Optional[datetime]:
    """Убрать таймзону, сохранив московские «настенные» часы.

    Колонки времени в схеме — без таймзоны. Облако присылало время с поясом
    учётки (+03:00), Jira DC — в UTC; база всегда хранила московские часы,
    поэтому приводим к ним. Без перевода ворклоги около полуночи уехали бы на
    соседний день, а срок внесения часов в KPI сдвинулся бы на 3 часа.
    Значение с зоной каждая БД записывает по-своему (PostgreSQL сдвигает к
    UTC), поэтому зону снимаем до записи.
    """
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(JIRA_WALL_CLOCK_TZ).replace(tzinfo=None)
```

In `app/connectors/schemas.py`, in the docstring of `JiraWorklogSchema.created_datetime` replace the sentence «здесь результат НЕ приводится к UTC — сохраняется локальное время того часового пояса, что прислала Jira (обычно пояс учётной записи автора).» with «здесь пояс не меняется — время такое, как прислала Jira (Jira DC шлёт UTC). В московские часы его переводит ``_drop_tz`` при записи в базу.»

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_sync_wall_clock.py tests/test_kpi_worklog_created.py tests/test_sync_service_update.py tests/test_sync_service_v2.py tests/test_reload_worklogs_v2_bulk.py -v`
Expected: PASS (облачные `+0300` в старых тестах дают те же часы).

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/sync_service.py app/connectors/schemas.py tests/test_sync_wall_clock.py
git commit -m "fix(jira-dc): время ворклогов хранится московским, как в облаке" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Ссылки на задачи из настроек (сервер)

**Files:**
- Modify: `app/services/plan_common.py:1-30, 63-64`
- Modify: `app/services/work_desk_widgets.py:24` (импорт) и функции `_assignment_projects`, `_project_children`, `_adapter_my_timeline`, `_adapter_category_breakdown`, `_adapter_team_availability`, `_adapter_awaiting_reaction`, `_adapter_stale_tasks`
- Modify: `app/services/project_plan_service.py:18` (импорт), `_children_by_root` (`:415-460`)
- Modify tests: `tests/services/test_project_plan_service.py:136-148`, `tests/test_desk_period_tree.py:190-199`
- Test: `tests/services/test_jira_links.py`

- [ ] **Step 1: Write the failing test**

`tests/services/test_jira_links.py`:

```python
"""Ссылки на задачи строятся от адреса Jira из настроек, а не от облачного домена."""
from app.models.app_setting import AppSetting
from app.services.plan_common import jira_browse_base, jira_url


def test_no_setting_no_link(db_session):
    assert jira_browse_base(db_session) == ""
    assert jira_url("OS-1", "") is None


def test_link_from_setting(db_session):
    db_session.add(AppSetting(key="jira_base_url", value="https://jira.example.test/"))
    db_session.commit()
    base = jira_browse_base(db_session)
    assert base == "https://jira.example.test/browse/"
    assert jira_url("OS-91030", base) == "https://jira.example.test/browse/OS-91030"
    assert jira_url(None, base) is None
```

Update `tests/services/test_project_plan_service.py::test_children_include_own_subtree_hours`: replace

```python
    db = db_session
    _seed_project(db)

    plan = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)
```

with

```python
    db = db_session
    _seed_project(db)
    db.add(AppSetting(key="jira_base_url", value="https://jira.example.test"))
    db.commit()

    plan = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)
```

and `    assert children[0]["jira_url"].endswith("/PP-2")` with `    assert children[0]["jira_url"] == "https://jira.example.test/browse/PP-2"`; add `from app.models.app_setting import AppSetting` to the imports of that file.

Update `tests/test_desk_period_tree.py::test_full_tree_to_leaves`: replace

```python
    _seed_tree(db_session, emp.id)
    top = _my_tasks(db_session, _desk(db_session, emp))["projects"][0]["children"]
```

with

```python
    _seed_tree(db_session, emp.id)
    db_session.add(AppSetting(key="jira_base_url", value="https://jira.example.test"))
    db_session.commit()
    top = _my_tasks(db_session, _desk(db_session, emp))["projects"][0]["children"]
```

and `    assert a["jira_url"].endswith("ITL-2")` with `    assert a["jira_url"] == "https://jira.example.test/browse/ITL-2"`; add `from app.models.app_setting import AppSetting` to its imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/test_jira_links.py tests/services/test_project_plan_service.py::test_children_include_own_subtree_hours tests/test_desk_period_tree.py::test_full_tree_to_leaves -v`
Expected: FAIL — `ImportError: cannot import name 'jira_browse_base'`; ссылки ведут на `example.atlassian.net`.

- [ ] **Step 3: Implement in plan_common**

In `app/services/plan_common.py`: after `from app.services import team_membership as tm` add `from app.models.app_setting import AppSetting`; delete the line `JIRA_BROWSE = "https://example.atlassian.net/browse/"`; replace

```python
def jira_url(key: Optional[str]) -> Optional[str]:
    return f"{JIRA_BROWSE}{key}" if key else None
```

with

```python
def jira_browse_base(db: Session) -> str:
    """Префикс ссылки на задачу ``<адрес Jira>/browse/`` из настроек; пусто — адрес не задан.

    Читается один раз на расчёт и передаётся в :func:`jira_url`, чтобы не ходить
    в базу на каждую строку.
    """
    value = db.query(AppSetting.value).filter(AppSetting.key == "jira_base_url").scalar()
    base = (value or "").strip().rstrip("/")
    return f"{base}/browse/" if base else ""


def jira_url(key: Optional[str], base: str) -> Optional[str]:
    """Ссылка на задачу; без ключа или без адреса Jira — ``None``."""
    return f"{base}{key}" if key and base else None
```

- [ ] **Step 4: Callers in work desk widgets and project plan**

`app/services/work_desk_widgets.py` — in the import block replace `    jira_url as _jira_url,` with:

```python
    jira_browse_base as _jira_browse_base,
    jira_url as _jira_url,
```

In each of these functions insert `    base = _jira_browse_base(db)` as the first statement after the docstring: `_assignment_projects`, `_project_children`, `_adapter_my_timeline`, `_adapter_category_breakdown`, `_adapter_team_availability`, `_adapter_awaiting_reaction`, `_adapter_stale_tasks`. Then change the calls:

- `_assignment_projects`: `"jira_url": _jira_url(key),` → `"jira_url": _jira_url(key, base),`
- `_project_children` (inside `build`): `"jira_url": _jira_url(r.key),` → `"jira_url": _jira_url(r.key, base),`
- `_adapter_category_breakdown`: `"jira_url": _jira_url(iss.key),` → `"jira_url": _jira_url(iss.key, base),`
- `_adapter_team_availability`: `"jira_url": _jira_url(key),` → `"jira_url": _jira_url(key, base),`
- `_adapter_stale_tasks` (inside `_row`): `"url": _jira_url(r.key),` → `"url": _jira_url(r.key, base),`
- `_adapter_my_timeline` — in the bar dict after `"key": getattr(issue, "key", None),` add:
```python
                        "jira_url": _jira_url(getattr(issue, "key", None), base),
```
- `_adapter_awaiting_reaction` — in the item dict after `"key": key,` add:
```python
                "jira_url": _jira_url(key, base),
```

(`_assignment_projects` и `_adapter_team_availability` содержат одинаковую строку `"jira_url": _jira_url(key),` — замените обе.)

`app/services/project_plan_service.py` — in the import from `app.services.plan_common` replace `    jira_url,` with:

```python
    jira_browse_base,
    jira_url,
```

In `_children_by_root`, right after its docstring and `from app.models import Issue, Worklog`, add `        base = jira_browse_base(self._db)` and change `"jira_url": jira_url(r.key),` to `"jira_url": jira_url(r.key, base),`.

Check: `grep -rn "atlassian" app/ --include=*.py` печатает только `app/connectors/confluence_client.py` и `app/services/confluence_service.py` (их переводит Task 16).

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/test_jira_links.py tests/services/test_project_plan_service.py tests/test_desk_period_tree.py -q`
Expected: PASS (тест числа запросов портфеля сравнивает малый и большой портфель — одна константная выборка настройки его не ломает).

Run: `py -3.10 -m pytest tests/ -q -k "desk or widget or project_plan" --ignore=tests/api/test_llm.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/plan_common.py app/services/work_desk_widgets.py app/services/project_plan_service.py tests/services/test_jira_links.py tests/services/test_project_plan_service.py tests/test_desk_period_tree.py
git commit -m "fix(links): ссылки на задачи от адреса Jira из настроек" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Фронт — подключение к Jira без почты, логин при добавлении сотрудника

**Files:**
- Modify: `frontend/src/types/api.ts:50-56` (`JiraUserSearchResult`), `:58-64` (`EmployeeFromJiraRequest`), `:93-97` (`JiraSettingsResponse`)
- Modify: `frontend/src/api/settings.ts:7-11`
- Modify (rewrite): `frontend/src/components/ConnectionCard.tsx`
- Modify: `frontend/src/pages/CapacityPage.tsx:99-105`

- [ ] **Step 1: Types and API**

`frontend/src/types/api.ts`:
- in `JiraUserSearchResult` after `  jira_account_id: string;` add `  jira_username: string | null;`
- in `EmployeeFromJiraRequest` after `  jira_account_id: string;` add `  jira_username?: string | null;`
- replace
```ts
export interface JiraSettingsResponse {
  email: string | null;
  base_url: string | null;
  has_token: boolean;
}
```
with
```ts
export interface JiraSettingsResponse {
  base_url: string | null;
  has_token: boolean;
}
```

`frontend/src/api/settings.ts` — replace

```ts
export const saveJiraSettings = (body: { email?: string; api_token?: string; base_url?: string }) =>
  api.put<JiraSettingsResponse>('/settings/jira', body);

export const testJiraCredentials = (body: { email: string; api_token: string; base_url: string }) =>
  api.post<JiraTestResponse>('/settings/jira/test', body);
```

with

```ts
export const saveJiraSettings = (body: { api_token?: string; base_url?: string }) =>
  api.put<JiraSettingsResponse>('/settings/jira', body);

export const testJiraCredentials = (body: { api_token: string; base_url: string }) =>
  api.post<JiraTestResponse>('/settings/jira/test', body);
```

`frontend/src/pages/CapacityPage.tsx` — in `handlePick` replace

```ts
    addMut.mutate({
      jira_account_id: user.jira_account_id,
      display_name: user.display_name,
```

with

```ts
    addMut.mutate({
      jira_account_id: user.jira_account_id,
      jira_username: user.jira_username,
      display_name: user.display_name,
```

- [ ] **Step 2: Rewrite the connection card**

Replace the whole of `frontend/src/components/ConnectionCard.tsx` with:

```tsx
import { useState } from 'react';
import { Card, Input, Button, Space, App } from 'antd';
import { Typography } from 'antd';
import { ApiOutlined, SaveOutlined } from '@ant-design/icons';
import { testConnection } from '../api/sync';
import { useJiraSettings, useSaveJiraSettings, useTestJiraCredentials } from '../hooks/useSettings';

const { Text } = Typography;

export default function ConnectionCard() {
  const { message } = App.useApp();
  const settings = useJiraSettings();
  const saveMutation = useSaveJiraSettings();
  const testMutation = useTestJiraCredentials();

  const [token, setToken] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [loaded, setLoaded] = useState(false);

  // Populate form from saved settings once
  if (settings.data && !loaded) {
    if (settings.data.base_url) setBaseUrl(settings.data.base_url);
    setLoaded(true);
  }

  const handleSave = () => {
    const body: { api_token?: string; base_url?: string } = {};
    if (token) body.api_token = token;
    if (baseUrl) body.base_url = baseUrl;
    saveMutation.mutate(body, {
      onSuccess: () => message.success('Настройки сохранены'),
      onError: (e) => message.error(e.message),
    });
  };

  const handleTest = () => {
    const testUrl = baseUrl || settings.data?.base_url || '';
    if (!testUrl) {
      message.warning('Укажите адрес Jira');
      return;
    }
    if (!token && !settings.data?.has_token) {
      message.warning('Укажите персональный токен');
      return;
    }
    // Новый токен не введён — проверяем сохранённые в базе адрес и токен
    if (!token && settings.data?.has_token) {
      testConnection().then((res) => {
        if (res.connected) message.success(`Подключение успешно (${res.user_name})`);
        else message.error(res.error || 'Не удалось подключиться');
      }).catch((e: Error) => message.error(e.message));
      return;
    }
    testMutation.mutate(
      { api_token: token, base_url: testUrl },
      {
        onSuccess: (res) => {
          if (res.connected) message.success(`Подключение успешно (${res.user_name})`);
          else message.error(res.error || 'Не удалось подключиться');
        },
        onError: (e) => message.error(e.message),
      },
    );
  };

  return (
    <Card title="Подключение к Jira" size="small">
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Space wrap>
          <Input
            placeholder="Адрес Jira (https://jira.example.ru)"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ width: 360 }}
            autoComplete="off"
            name="jira-base-url"
          />
          <Input.Password
            placeholder={settings.data?.has_token ? 'Токен сохранён (введите новый для замены)' : 'Персональный токен'}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ width: 300 }}
            autoComplete="new-password"
            name="jira-api-token"
          />
        </Space>
        <Space>
          <Button
            icon={<SaveOutlined />}
            type="primary"
            onClick={handleSave}
            loading={saveMutation.isPending}
          >
            Сохранить
          </Button>
          <Button
            icon={<ApiOutlined />}
            onClick={handleTest}
            loading={testMutation.isPending}
          >
            Проверить подключение
          </Button>
          {testMutation.data?.connected && (
            <Text type="success">{testMutation.data.user_name}</Text>
          )}
        </Space>
      </Space>
    </Card>
  );
}
```

- [ ] **Step 3: Type-check and lint**

Run (in `frontend/`): `npx tsc -b`
Expected: без ошибок.

Run (in `frontend/`): `npx eslint src/components/ConnectionCard.tsx src/pages/CapacityPage.tsx src/api/settings.ts src/types/api.ts`
Expected: без новых ошибок в этих файлах.

- [ ] **Step 4: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add frontend/src/types/api.ts frontend/src/api/settings.ts frontend/src/components/ConnectionCard.tsx frontend/src/pages/CapacityPage.tsx
git commit -m "feat(settings): подключение к Jira — адрес и токен, без почты" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Фронт — ссылки на задачи от адреса Jira из настроек

Пять экранов для залогиненных берут адрес через `useJiraBaseUrl()`. Два виджета публичного стола аналитика (`/desk/:token`, без входа) настройку прочитать не могут — для них ссылку присылает сервер (`jira_url`, Task 12).

**Files:**
- Create: `frontend/src/utils/jiraLinks.ts`, `frontend/src/utils/jiraLinks.test.ts`
- Create: `frontend/src/components/shared/JiraIssueLink.tsx`
- Modify: `frontend/src/hooks/useSettings.ts`
- Modify: `frontend/src/components/analytics/AnalyticsIssueDrawer.tsx:11, 137-155`
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx:147-160`
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx:84, 183-191, 254-262`
- Modify: `frontend/src/components/work-type-report/IssueDrillDownDrawer.tsx:20, 187, 240-248`
- Modify: `frontend/src/components/projects/ProjectHeader.tsx:139-146`
- Modify: `frontend/src/types/desk.ts:81-91, 175-181`
- Modify: `frontend/src/components/desk/MyTimelineWidget.tsx:173`, `frontend/src/components/desk/AwaitingReactionWidget.tsx:25`

- [ ] **Step 1: Write the failing test**

`frontend/src/utils/jiraLinks.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { jiraBrowseUrl } from './jiraLinks';

describe('jiraBrowseUrl', () => {
  it('строит ссылку от адреса из настроек', () => {
    expect(jiraBrowseUrl('https://jira.example.test', 'OS-1')).toBe('https://jira.example.test/browse/OS-1');
    expect(jiraBrowseUrl('https://jira.example.test/', 'OS-1')).toBe('https://jira.example.test/browse/OS-1');
  });

  it('без адреса или ключа ссылки нет', () => {
    expect(jiraBrowseUrl(null, 'OS-1')).toBeNull();
    expect(jiraBrowseUrl('', 'OS-1')).toBeNull();
    expect(jiraBrowseUrl('https://jira.example.test', null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `frontend/`): `npx vitest run src/utils/jiraLinks.test.ts`
Expected: FAIL — `Failed to resolve import "./jiraLinks"`.

- [ ] **Step 3: Helper, hook and link component**

`frontend/src/utils/jiraLinks.ts`:

```ts
/** Ссылка на задачу в Jira: `<адрес>/browse/<ключ>`. Нет адреса или ключа — `null`. */
export function jiraBrowseUrl(
  baseUrl: string | null | undefined,
  issueKey: string | null | undefined,
): string | null {
  const base = (baseUrl ?? '').trim().replace(/\/+$/, '');
  if (!base || !issueKey) return null;
  return `${base}/browse/${issueKey}`;
}
```

`frontend/src/hooks/useSettings.ts` — add the import `import { jiraBrowseUrl } from '../utils/jiraLinks';` after the existing imports, and after `useJiraBaseUrl` add:

```ts
/** Функция «ключ задачи → ссылка в Jira» по адресу из настроек. */
export function useJiraBrowseUrl(): (issueKey: string | null | undefined) => string | null {
  const baseUrl = useJiraBaseUrl().data?.base_url;
  return (issueKey) => jiraBrowseUrl(baseUrl, issueKey);
}
```

`frontend/src/components/shared/JiraIssueLink.tsx`:

```tsx
import type { AnchorHTMLAttributes } from 'react';
import { useJiraBrowseUrl } from '../../hooks/useSettings';

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href' | 'target' | 'rel'> & {
  issueKey: string;
};

/** Ссылка на задачу в Jira; пока адрес Jira не задан — просто ключ без ссылки. */
export default function JiraIssueLink({ issueKey, children, style, className, ...rest }: Props) {
  const href = useJiraBrowseUrl()(issueKey);
  if (!href) {
    return <span style={style} className={className}>{children ?? issueKey}</span>;
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" style={style} className={className} {...rest}>
      {children ?? issueKey}
    </a>
  );
}
```

- [ ] **Step 4: Replace the hardcoded links**

`AnalyticsIssueDrawer.tsx`: delete the line `const JIRA_BASE = 'https://example.atlassian.net/browse';`; add `import JiraIssueLink from '../shared/JiraIssueLink';` after `import AnalyticsWorklogsBlock from './AnalyticsWorklogsBlock';`; replace

```tsx
        <a
          href={`${JIRA_BASE}/${issueKey}`}
          target="_blank"
          rel="noreferrer"
          style={{
            fontFamily: 'monospace',
```

with

```tsx
        <JiraIssueLink
          issueKey={issueKey}
          style={{
            fontFamily: 'monospace',
```

and

```tsx
          {issueKey}
        </a>
        {!isLoading && context && (
```

with

```tsx
          {issueKey}
        </JiraIssueLink>
        {!isLoading && context && (
```

`AnalyticsTable.tsx`: add `import JiraIssueLink from '../shared/JiraIssueLink';` after `import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';`; replace

```tsx
          <a
            href={`https://example.atlassian.net/browse/${i.key}`}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
```

with

```tsx
          <JiraIssueLink
            issueKey={i.key}
            onClick={(e) => e.stopPropagation()}
```

and

```tsx
            {i.key}
          </a>
          <Tag
            color={statusTagColor(i.status, i.status_category)}
```

with

```tsx
            {i.key}
          </JiraIssueLink>
          <Tag
            color={statusTagColor(i.status, i.status_category)}
```

`GanttRows.tsx`: delete the line `const JIRA_BASE = 'https://example.atlassian.net';`; add `import JiraIssueLink from '../shared/JiraIssueLink';` after `import { computeFillGradientAlphas } from './appearanceGradient';`; replace

```tsx
            <a
              href={`${JIRA_BASE}/browse/${jiraKey}`}
              target="_blank"
              rel="noreferrer"
              onClick={e => e.stopPropagation()}
              style={{ fontSize: 10, color: 'var(--text-muted, #7a9ab8)', textDecoration: 'none', letterSpacing: 0.3 }}
            >
              {jiraKey}
            </a>
```

with

```tsx
            <JiraIssueLink
              issueKey={jiraKey}
              onClick={e => e.stopPropagation()}
              style={{ fontSize: 10, color: 'var(--text-muted, #7a9ab8)', textDecoration: 'none', letterSpacing: 0.3 }}
            >
              {jiraKey}
            </JiraIssueLink>
```

and

```tsx
        <a
          href={`${JIRA_BASE}/browse/${jiraKey}`}
          target="_blank"
          rel="noreferrer"
          onClick={e => e.stopPropagation()}
          style={{ flexShrink: 0, fontSize: 11, color: 'var(--text-muted, #7a9ab8)', textDecoration: 'none' }}
        >
          {jiraKey}
        </a>
```

with

```tsx
        <JiraIssueLink
          issueKey={jiraKey}
          onClick={e => e.stopPropagation()}
          style={{ flexShrink: 0, fontSize: 11, color: 'var(--text-muted, #7a9ab8)', textDecoration: 'none' }}
        >
          {jiraKey}
        </JiraIssueLink>
```

`IssueDrillDownDrawer.tsx`: delete the line `const JIRA_BASE = 'https://example.atlassian.net/browse';`; add `import { useJiraBrowseUrl } from '../../hooks/useSettings';` after `import { useManualClassify } from '../../hooks/useWorkTypeReport';`; in `DrawerContent` replace

```tsx
  const { data: context, isLoading, isError, refetch } = useIssueContext(issueId);
```

with

```tsx
  const { data: context, isLoading, isError, refetch } = useIssueContext(issueId);
  const browseUrl = useJiraBrowseUrl();
```

and replace

```tsx
          href={`${JIRA_BASE}/${issueKey}`}
```

with

```tsx
          href={browseUrl(issueKey) ?? undefined}
          disabled={!browseUrl(issueKey)}
```

`ProjectHeader.tsx`: add `import JiraIssueLink from '../shared/JiraIssueLink';` after `import { trackAction } from '../../lib/usage/track';`; replace

```tsx
            <a
              href={`https://example.atlassian.net/browse/${detail.key}`}
              target="_blank"
              rel="noreferrer"
              style={{ color: 'var(--accent-1, #00c9c8)', fontSize: 12, textDecoration: 'none' }}
            >
              {detail.key}
            </a>
```

with

```tsx
            <JiraIssueLink
              issueKey={detail.key}
              style={{ color: 'var(--accent-1, #00c9c8)', fontSize: 12, textDecoration: 'none' }}
            >
              {detail.key}
            </JiraIssueLink>
```

Public desk widgets — `frontend/src/types/desk.ts`: in `TimelineBar` after `  key: string | null;` add `  jira_url: string | null;`; in `AwaitingItem` after `  key: string | null;` add `  jira_url: string | null;`.

`MyTimelineWidget.tsx`: replace

```tsx
    jira_url_safe: b.key ? `https://example.atlassian.net/browse/${b.key}` : null,
```

with

```tsx
    jira_url_safe: b.jira_url,
```

`AwaitingReactionWidget.tsx`: replace

```tsx
        const jiraUrl = it.key ? `https://example.atlassian.net/browse/${it.key}` : null;
```

with

```tsx
        const jiraUrl = it.jira_url;
```

Check: `grep -rn "atlassian" frontend/src` — совпадений нет (подсказку в карточке подключения убрал Task 13).

- [ ] **Step 5: Run checks**

Run (in `frontend/`): `npx vitest run src/utils/jiraLinks.test.ts`
Expected: PASS (2 tests).

Run (in `frontend/`): `npx tsc -b`
Expected: без ошибок.

Run (in `frontend/`): `npx eslint src/utils/jiraLinks.ts src/hooks/useSettings.ts src/components/shared/JiraIssueLink.tsx src/components/analytics/AnalyticsIssueDrawer.tsx src/components/analytics/AnalyticsTable.tsx src/components/resource-planning/GanttRows.tsx src/components/work-type-report/IssueDrillDownDrawer.tsx src/components/projects/ProjectHeader.tsx src/components/desk/MyTimelineWidget.tsx src/components/desk/AwaitingReactionWidget.tsx`
Expected: без новых ошибок.

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add frontend/src/utils/jiraLinks.ts frontend/src/utils/jiraLinks.test.ts frontend/src/components/shared/JiraIssueLink.tsx frontend/src/hooks/useSettings.ts frontend/src/components/analytics/AnalyticsIssueDrawer.tsx frontend/src/components/analytics/AnalyticsTable.tsx frontend/src/components/resource-planning/GanttRows.tsx frontend/src/components/work-type-report/IssueDrillDownDrawer.tsx frontend/src/components/projects/ProjectHeader.tsx frontend/src/types/desk.ts frontend/src/components/desk/MyTimelineWidget.tsx frontend/src/components/desk/AwaitingReactionWidget.tsx
git commit -m "fix(links): ссылки на задачи на фронте от адреса Jira из настроек" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Фронт — плашка «синхронизация остановлена» и заблокированные кнопки

**Files:**
- Modify: `frontend/src/api/uiConfig.ts`, `frontend/src/hooks/useSettings.ts`
- Create: `frontend/src/utils/syncBlocked.ts`, `frontend/src/components/sync/SyncBlockedAlert.tsx`
- Modify: `frontend/src/pages/SyncHubPage.tsx`
- Modify: `frontend/src/components/sync/PipelineRunner.tsx:1-8, 46-50, 110-117`
- Modify: `frontend/src/components/sync/SyncAdvanced.tsx:12, 21-22, ~184-190, ~220, ~266-275`
- Modify: `frontend/src/components/sync/SyncSchedule.tsx:1-12, 21-23, 117-125`
- Modify: `frontend/src/pages/BacklogPage.tsx:38, 141, 1175-1190`
- Modify: `frontend/src/pages/TeamDeskPage.tsx:13, 137-155`
- Modify: `frontend/src/components/teamdesk/GroupedIssues.tsx:66-70, 192, 636-646`

- [ ] **Step 1: API, hook, text and banner**

`frontend/src/api/uiConfig.ts` — append:

```ts
export interface JiraMigrationStateResponse {
  state: 'pending' | 'done';
  sync_blocked: boolean;
}

export const getJiraMigrationState = (): Promise<JiraMigrationStateResponse> =>
  api.get<JiraMigrationStateResponse>('/ui-config/jira-migration-state');
```

`frontend/src/hooks/useSettings.ts` — change `import { getJiraBaseUrl } from '../api/uiConfig';` to `import { getJiraBaseUrl, getJiraMigrationState } from '../api/uiConfig';` and append:

```ts
/** Состояние переезда на новую Jira: пока он не завершён, синхронизация остановлена. */
export function useJiraMigrationState() {
  return useQuery({
    queryKey: ['ui-config', 'jira-migration-state'],
    queryFn: getJiraMigrationState,
    staleTime: 60_000,
  });
}

/** Синхронизация с Jira остановлена до завершения переезда. */
export function useSyncBlocked(): boolean {
  return useJiraMigrationState().data?.sync_blocked ?? false;
}
```

`frontend/src/utils/syncBlocked.ts`:

```ts
/** Текст для плашки и подсказок на заблокированных кнопках обновления из Jira. */
export const SYNC_BLOCKED_TEXT = 'Синхронизация остановлена до завершения переезда на новую Jira';
```

`frontend/src/components/sync/SyncBlockedAlert.tsx`:

```tsx
import { Alert } from 'antd';
import { Link } from 'react-router';
import { useSyncBlocked } from '../../hooks/useSettings';
import { SYNC_BLOCKED_TEXT } from '../../utils/syncBlocked';

/** Плашка «синхронизация остановлена» со ссылкой на страницу переезда. */
export default function SyncBlockedAlert() {
  const blocked = useSyncBlocked();
  if (!blocked) return null;
  return (
    <Alert
      type="warning"
      showIcon
      title={SYNC_BLOCKED_TEXT}
      description={
        <span>
          Данные из Jira не обновляются, пока администратор не завершит переезд.{' '}
          <Link to="/admin/jira-migration">Перейти к переезду</Link>
        </span>
      }
    />
  );
}
```

- [ ] **Step 2: Sync page**

Replace the whole of `frontend/src/pages/SyncHubPage.tsx` with:

```tsx
import { Tabs } from 'antd';
import { Space } from 'antd';
import PipelineRunner from '../components/sync/PipelineRunner';
import SyncSchedule from '../components/sync/SyncSchedule';
import SyncHistory from '../components/sync/SyncHistory';
import SyncAdvanced from '../components/sync/SyncAdvanced';
import SyncBlockedAlert from '../components/sync/SyncBlockedAlert';
import { useJiraTeams } from '../hooks/useSync';
import syncHelp from '../../../docs/help/sync.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';

export default function SyncHubPage() {
  const jiraTeams = useJiraTeams();
  const teams = jiraTeams.data ?? [];
  useRegisterHelp('Синхронизация с Jira', syncHelp);

  return (
    <Space orientation="vertical" style={{ width: '100%' }} size="middle">
      <SyncBlockedAlert />
      <Tabs
        items={[
          {
            key: 'pipeline',
            label: 'Синхронизация',
            children: (
              <Space orientation="vertical" style={{ width: '100%' }} size="middle">
                <PipelineRunner teams={teams} />
                <SyncHistory />
              </Space>
            ),
          },
          {
            key: 'schedule',
            label: 'Расписание',
            children: <SyncSchedule />,
          },
          {
            key: 'advanced',
            label: 'Дополнительно',
            children: <SyncAdvanced />,
          },
        ]}
      />
    </Space>
  );
}
```

- [ ] **Step 3: Sync page buttons**

`PipelineRunner.tsx` — add imports `import { useSyncBlocked } from '../../hooks/useSettings';` and `import { SYNC_BLOCKED_TEXT } from '../../utils/syncBlocked';` after `import { trackAction } from '../../lib/usage/track';`; after `  const { state, start, cancel, reset } = useSyncPipeline();` add `  const syncBlocked = useSyncBlocked();`; replace

```tsx
              onClick={handleStart}
              disabled={mode === 'team' && !team}
            >
```

with

```tsx
              onClick={handleStart}
              disabled={syncBlocked || (mode === 'team' && !team)}
              title={syncBlocked ? SYNC_BLOCKED_TEXT : undefined}
            >
```

`SyncAdvanced.tsx` — replace `import { useGenericSetting, useSaveGenericSetting } from '../../hooks/useSettings';` with:

```tsx
import { useGenericSetting, useSaveGenericSetting, useSyncBlocked } from '../../hooks/useSettings';
import { SYNC_BLOCKED_TEXT } from '../../utils/syncBlocked';
```

after `  const { notification } = App.useApp();` add `  const syncBlocked = useSyncBlocked();`; then:

- replace
```tsx
                onClick={handleUpdate}
                disabled={reload.isPending}
              >
```
with
```tsx
                onClick={handleUpdate}
                disabled={syncBlocked || reload.isPending}
                title={syncBlocked ? SYNC_BLOCKED_TEXT : undefined}
              >
```
- replace
```tsx
                onConfirm={handleReload}
                disabled={update.isPending}
              >
                <Button danger icon={<ReloadOutlined />} disabled={update.isPending}>
```
with
```tsx
                onConfirm={handleReload}
                disabled={syncBlocked || update.isPending}
              >
                <Button
                  danger
                  icon={<ReloadOutlined />}
                  disabled={syncBlocked || update.isPending}
                  title={syncBlocked ? SYNC_BLOCKED_TEXT : undefined}
                >
```
- replace
```tsx
                icon={<ReloadOutlined />}
                onClick={handleReloadIssues}
              >
```
with
```tsx
                icon={<ReloadOutlined />}
                onClick={handleReloadIssues}
                disabled={syncBlocked}
                title={syncBlocked ? SYNC_BLOCKED_TEXT : undefined}
              >
```

`SyncSchedule.tsx` — add imports `import { useSyncBlocked } from '../../hooks/useSettings';` and `import { SYNC_BLOCKED_TEXT } from '../../utils/syncBlocked';` after `import ScheduleEditorModal from './ScheduleEditorModal';`; after `  const qc = useQueryClient();` add `  const syncBlocked = useSyncBlocked();`; replace

```tsx
            loading={runNowMut.isPending}
            onClick={() => runNowMut.mutate(r.id)}
          >
```

with

```tsx
            loading={runNowMut.isPending}
            disabled={syncBlocked}
            title={syncBlocked ? SYNC_BLOCKED_TEXT : undefined}
            onClick={() => runNowMut.mutate(r.id)}
          >
```

- [ ] **Step 4: Backlog and team desk buttons**

`BacklogPage.tsx` — replace `import { useJiraBaseUrl } from '../hooks/useSettings';` with:

```tsx
import { useJiraBaseUrl, useSyncBlocked } from '../hooks/useSettings';
import { SYNC_BLOCKED_TEXT } from '../utils/syncBlocked';
```

after `  const refreshFromJiraMut = useRefreshFromJira();` add `  const syncBlocked = useSyncBlocked();`; replace

```tsx
                <Button icon={<ReloadOutlined />} onClick={() => handleRefreshFromJira()}>
                  Обновить с Jira
                </Button>
```

with

```tsx
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => handleRefreshFromJira()}
                  disabled={syncBlocked}
                  title={syncBlocked ? SYNC_BLOCKED_TEXT : undefined}
                >
                  Обновить с Jira
                </Button>
```

and replace

```tsx
                  title="Перечитать только задачи открытой вкладки"
                >
                  Обновить только видимые
```

with

```tsx
                  disabled={syncBlocked}
                  title={syncBlocked ? SYNC_BLOCKED_TEXT : 'Перечитать только задачи открытой вкладки'}
                >
                  Обновить только видимые
```

`GroupedIssues.tsx` — in `Props` after `  refreshing?: boolean;` add:

```tsx
  /** Обновление из Jira запрещено до завершения переезда — кнопка видна, но не нажимается. */
  refreshBlocked?: boolean;
```

in the destructuring replace `onHiddenColumnsChange, onGroupByDeveloperChange, onRefreshVisible, refreshing = false,` with `onHiddenColumnsChange, onGroupByDeveloperChange, onRefreshVisible, refreshing = false, refreshBlocked = false,`; add `import { SYNC_BLOCKED_TEXT } from '../../utils/syncBlocked';` to its imports; replace

```tsx
            <Tooltip title="Перечитать с Jira только задачи из этого списка">
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={refreshing}
                onClick={() => onRefreshVisible(visibleKeys)}
              >
```

with

```tsx
            <Tooltip title={refreshBlocked ? SYNC_BLOCKED_TEXT : 'Перечитать с Jira только задачи из этого списка'}>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={refreshing}
                disabled={refreshBlocked}
                onClick={() => onRefreshVisible(visibleKeys)}
              >
```

`TeamDeskPage.tsx` — replace `import { useJiraBaseUrl } from '../hooks/useSettings';` with `import { useJiraBaseUrl, useSyncBlocked } from '../hooks/useSettings';`; after `  const refreshIssues = useRefreshDeskIssues();` add `  const syncBlocked = useSyncBlocked();`; in `listProps` replace

```tsx
    onRefreshVisible: refreshVisible,
    refreshing: refreshIssues.isPending,
```

with

```tsx
    onRefreshVisible: refreshVisible,
    refreshing: refreshIssues.isPending,
    refreshBlocked: syncBlocked,
```

- [ ] **Step 5: Run checks**

Run (in `frontend/`): `npx tsc -b`
Expected: без ошибок.

Run (in `frontend/`): `npx eslint src/api/uiConfig.ts src/hooks/useSettings.ts src/utils/syncBlocked.ts src/components/sync/SyncBlockedAlert.tsx src/pages/SyncHubPage.tsx src/components/sync/PipelineRunner.tsx src/components/sync/SyncAdvanced.tsx src/components/sync/SyncSchedule.tsx src/pages/BacklogPage.tsx src/pages/TeamDeskPage.tsx src/components/teamdesk/GroupedIssues.tsx`
Expected: без новых ошибок.

Ручная проверка (по желанию, локальный стенд): поставить в локальной базе `jira_migration_state = pending` (`py -3.10 -c "from app.database import SessionLocal; from app.services.jira_migration.state import set_migration_state; db = SessionLocal(); set_migration_state(db, 'pending'); db.commit()"`), открыть `/sync` — жёлтая плашка, «Запустить» неактивна; вернуть `'done'` тем же способом.

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add frontend/src/api/uiConfig.ts frontend/src/hooks/useSettings.ts frontend/src/utils/syncBlocked.ts frontend/src/components/sync/SyncBlockedAlert.tsx frontend/src/pages/SyncHubPage.tsx frontend/src/components/sync/PipelineRunner.tsx frontend/src/components/sync/SyncAdvanced.tsx frontend/src/components/sync/SyncSchedule.tsx frontend/src/pages/BacklogPage.tsx frontend/src/pages/TeamDeskPage.tsx frontend/src/components/teamdesk/GroupedIssues.tsx
git commit -m "feat(sync): плашка и блокировка кнопок до переезда на новую Jira" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Confluence Data Center — свой адрес и токен, пути без `/wiki`, ссылки по адресу из настроек

Confluence тоже переехал на свой сервер: отдельные настройки «адрес» и «токен», вход `Bearer`, REST без `/wiki` (`/rest/api/content/{id}`), короткие ссылки `/x/…`. Описание задачи в DC — wiki-разметка, ссылка часто стоит внутри `[текст|адрес]`. Кроме прямого id (`viewpage.action?pageId=` и `/spaces/…/pages/N`) в DC часто встречаются ссылки `/display/<пространство>/<название>` — их id ищется по названию.

**Files:**
- Modify (rewrite): `app/connectors/confluence_client.py`
- Modify: `app/services/confluence_service.py:1-60, 86-90, 102-107`
- Modify: `app/services/project_summary_service.py:122-126`
- Modify: `app/api/endpoints/settings.py` (схемы, эндпоинты Confluence)
- Modify (rewrite): `tests/connectors/test_confluence_client.py`, `tests/services/test_confluence_service.py`
- Modify: `tests/services/test_project_summary_enrichment.py`
- Test: `tests/test_settings_confluence_endpoint.py`

- [ ] **Step 1: Write the failing tests**

Replace `tests/connectors/test_confluence_client.py` with:

```python
"""Confluence Data Center: свой адрес, токен Bearer, пути без /wiki."""
import httpx
import pytest
import respx

from app.connectors.confluence_client import (
    ConfluenceClient,
    ConfluenceClientError,
    page_id_from_url,
)
from app.models.app_setting import AppSetting

BASE = "https://confluence.example.test"


def _client() -> ConfluenceClient:
    return ConfluenceClient(base_url=BASE, api_token="tok")


@respx.mock
async def test_get_page_uses_bearer_and_dc_path():
    route = respx.get(f"{BASE}/rest/api/content/12345").mock(
        return_value=httpx.Response(200, json={
            "id": "12345",
            "title": "ТЗ Анализ себестоимости",
            "body": {"storage": {"value": "<p>Полный текст ТЗ</p>", "representation": "storage"}},
        })
    )
    async with _client() as c:
        page = await c.get_page("12345")
    assert page.id == "12345"
    assert page.title == "ТЗ Анализ себестоимости"
    assert "Полный текст ТЗ" in page.body_html
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
    assert dict(route.calls.last.request.url.params) == {"expand": "body.storage"}


@respx.mock
async def test_get_page_404_raises():
    respx.get(f"{BASE}/rest/api/content/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    async with _client() as c:
        with pytest.raises(ConfluenceClientError):
            await c.get_page("missing")


@respx.mock
async def test_tiny_link_follows_redirect_to_page_id():
    respx.get(f"{BASE}/x/AbCdE").mock(
        return_value=httpx.Response(302, headers={"Location": f"{BASE}/pages/viewpage.action?pageId=98765"})
    )
    async with _client() as c:
        assert await c.resolve_page_id(f"{BASE}/x/AbCdE") == "98765"


@respx.mock
async def test_display_link_is_found_by_title():
    route = respx.get(f"{BASE}/rest/api/content").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "555", "title": "План работ"}]})
    )
    async with _client() as c:
        page_id = await c.resolve_page_id(
            f"{BASE}/display/PR/%D0%9F%D0%BB%D0%B0%D0%BD+%D1%80%D0%B0%D0%B1%D0%BE%D1%82"
        )
    assert page_id == "555"
    assert dict(route.calls.last.request.url.params) == {
        "spaceKey": "PR", "title": "План работ", "limit": "1",
    }


async def test_direct_page_id_needs_no_request():
    async with _client() as c:
        assert await c.resolve_page_id(f"{BASE}/pages/viewpage.action?pageId=42") == "42"
        assert await c.resolve_page_id(f"{BASE}/spaces/PR/pages/77/Title") == "77"
    assert page_id_from_url(f"{BASE}/x/AbCdE") is None


@respx.mock
async def test_current_user():
    respx.get(f"{BASE}/rest/api/user/current").mock(
        return_value=httpx.Response(200, json={"username": "user_1", "displayName": "Сотрудник 1"})
    )
    async with _client() as c:
        assert (await c.get_current_user())["displayName"] == "Сотрудник 1"


def test_from_db_uses_confluence_settings(db_session):
    db_session.add_all([
        AppSetting(key="confluence_base_url", value=BASE + "/"),
        AppSetting(key="confluence_api_token", value="tok"),
    ])
    db_session.commit()
    assert ConfluenceClient.from_db(db_session).base_url == BASE


def test_missing_settings_raise(db_session):
    with pytest.raises(ConfluenceClientError):
        ConfluenceClient.from_db(db_session)
```

Replace `tests/services/test_confluence_service.py` with:

```python
"""ConfluenceService на Confluence DC: ссылки по адресу из настроек, кэш, разрешение id."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.models.app_setting import AppSetting
from app.models.confluence_page_cache import ConfluencePageCache
from app.services.confluence_service import (
    ConfluenceService,
    extract_confluence_urls,
    html_to_text,
    parse_page_id,
)

BASE = "https://confluence.example.test"


def _settings(db):
    db.add(AppSetting(key="confluence_base_url", value=BASE))
    db.add(AppSetting(key="confluence_api_token", value="t"))


def test_extract_dc_links_inside_wiki_markup():
    text = (
        f"См. ТЗ [страница|{BASE}/pages/viewpage.action?pageId=12345] и {BASE}/x/AbCdE, "
        f"а также {BASE}/display/PR/План+работ и {BASE}/spaces/PR/pages/777/Title."
    )
    assert extract_confluence_urls(text, BASE) == [
        f"{BASE}/pages/viewpage.action?pageId=12345",
        f"{BASE}/x/AbCdE",
        f"{BASE}/display/PR/План+работ",
        f"{BASE}/spaces/PR/pages/777/Title",
    ]


def test_extract_skips_other_hosts_and_dedups():
    text = f"https://other.example.test/x/Zz {BASE}/x/AbCdE {BASE}/x/AbCdE"
    assert extract_confluence_urls(text, BASE) == [f"{BASE}/x/AbCdE"]


def test_extract_without_base_url():
    assert extract_confluence_urls(f"{BASE}/x/AbCdE", "") == []


def test_html_to_text_strips_tags():
    html = "<h1>Заголовок</h1><p>Параграф <b>жирный</b></p><ul><li>пункт</li></ul>"
    text = html_to_text(html)
    assert "Заголовок" in text
    assert "жирный" in text
    assert "пункт" in text
    assert "<" not in text


def test_parse_page_id():
    assert parse_page_id(f"{BASE}/pages/viewpage.action?pageId=12345") == "12345"
    assert parse_page_id(f"{BASE}/spaces/PR/pages/12345/Title") == "12345"
    assert parse_page_id(f"{BASE}/x/AbCdE") is None


async def test_service_returns_cached_when_fresh(db_session):
    _settings(db_session)
    url = f"{BASE}/pages/viewpage.action?pageId=12345"
    db_session.add(ConfluencePageCache(
        page_id="12345", source_url=url, title="Cached", body_text="cached body",
        error=None, fetched_at=datetime.utcnow() - timedelta(days=1),
    ))
    db_session.commit()

    pages = await ConfluenceService(db_session).fetch_pages([url])
    assert len(pages) == 1
    assert pages[0].body_text == "cached body"


async def test_service_refetches_when_stale(db_session):
    _settings(db_session)
    url = f"{BASE}/pages/viewpage.action?pageId=99"
    db_session.add(ConfluencePageCache(
        page_id="99", source_url=url, title="Old", body_text="old body",
        error=None, fetched_at=datetime.utcnow() - timedelta(days=10),
    ))
    db_session.commit()

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.get_page.return_value = type("P", (), {
        "id": "99", "title": "Fresh", "body_html": "<p>fresh</p>",
    })()

    with patch("app.services.confluence_service.ConfluenceClient.from_db", return_value=fake_client):
        pages = await ConfluenceService(db_session).fetch_pages([url])
    assert pages[0].body_text.strip() == "fresh"


async def test_service_resolves_short_link_through_client(db_session):
    _settings(db_session)
    db_session.commit()
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.resolve_page_id.return_value = "77"
    fake_client.get_page.return_value = type("P", (), {
        "id": "77", "title": "Короткая", "body_html": "<p>текст</p>",
    })()

    with patch("app.services.confluence_service.ConfluenceClient.from_db", return_value=fake_client):
        pages = await ConfluenceService(db_session).fetch_pages([f"{BASE}/x/AbCdE"])

    fake_client.resolve_page_id.assert_awaited_once_with(f"{BASE}/x/AbCdE")
    assert pages[0].page_id == "77"
```

`tests/test_settings_confluence_endpoint.py`:

```python
"""Настройки Confluence: свой адрес и токен, проверка подключения по сохранённым."""
import httpx
import respx
from fastapi.testclient import TestClient

from app.api.endpoints import settings as settings_ep
from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting


def test_confluence_settings_saved(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        empty = client.get("/api/v1/settings/confluence").json()
        put = client.put(
            "/api/v1/settings/confluence",
            json={"base_url": "confluence.example.test", "api_token": "tok"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert empty == {"base_url": None, "has_token": False}
    assert put.status_code == 200
    assert put.json() == {"base_url": "https://confluence.example.test", "has_token": True}


@respx.mock
async def test_confluence_test_uses_saved_settings(db_session):
    db_session.add_all([
        AppSetting(key="confluence_base_url", value="https://confluence.example.test"),
        AppSetting(key="confluence_api_token", value="tok"),
    ])
    db_session.commit()
    route = respx.get("https://confluence.example.test/rest/api/user/current").mock(
        return_value=httpx.Response(200, json={"username": "user_1", "displayName": "Сотрудник 1"})
    )
    result = await settings_ep.test_confluence_connection(db=db_session)
    assert result.connected is True
    assert result.user_name == "Сотрудник 1"
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"


async def test_confluence_test_without_settings(db_session):
    result = await settings_ep.test_confluence_connection(db=db_session)
    assert result.connected is False
    assert result.error
```

`tests/services/test_project_summary_enrichment.py`: replace both occurrences of `https://example.atlassian.net/wiki/spaces/X/pages/12345/T` with `https://confluence.example.test/pages/viewpage.action?pageId=12345`; after `    p = Project(jira_project_id="P1", key="PRJ", name="P")` add

```python
    from app.models.app_setting import AppSetting
    db_session.add(AppSetting(key="confluence_base_url", value="https://confluence.example.test"))
```

and after the line `    assert "Контент ТЗ из confluence" in data["confluence_pages"][0]["body_text"]` add

```python
    mock_svc.return_value.fetch_pages.assert_awaited_once_with(
        ["https://confluence.example.test/pages/viewpage.action?pageId=12345"]
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/connectors/test_confluence_client.py tests/services/test_confluence_service.py tests/test_settings_confluence_endpoint.py tests/services/test_project_summary_enrichment.py -v`
Expected: FAIL — `TypeError: ConfluenceClient.__init__() missing ... 'email'` / `ImportError: page_id_from_url`; эндпоинта `/settings/confluence` нет (404).

- [ ] **Step 3: Rewrite the client**

Replace the whole of `app/connectors/confluence_client.py` with:

```python
"""Confluence Data Center REST client: свой адрес и персональный токен (Bearer)."""
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote_plus

import httpx


class ConfluenceClientError(Exception):
    pass


@dataclass
class ConfluencePage:
    id: str
    title: str
    body_html: str


_PAGE_ID_RE = re.compile(r"(?:pageId=|/pages/)(\d+)")
_DISPLAY_RE = re.compile(r"/display/([^/?#]+)/([^?#]+)")


def page_id_from_url(url: str) -> Optional[str]:
    """id страницы из ``…/viewpage.action?pageId=N`` или ``…/pages/N/…``; иначе ``None``."""
    m = _PAGE_ID_RE.search(url)
    return m.group(1) if m else None


class ConfluenceClient:
    """Async Confluence Data Center client."""

    @classmethod
    def from_db(cls, db) -> "ConfluenceClient":
        """Адрес и токен — свои настройки Confluence (сервер отдельный от Jira)."""
        from app.models.app_setting import AppSetting

        def _get(key: str) -> Optional[str]:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else None

        return cls(
            base_url=_get("confluence_base_url") or "",
            api_token=_get("confluence_api_token") or "",
        )

    def __init__(self, base_url: str, api_token: str) -> None:
        if not (base_url and api_token):
            raise ConfluenceClientError("Confluence credentials missing")
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "ConfluenceClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers, timeout=30.0,
            follow_redirects=False,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if not self._client:
            raise ConfluenceClientError("Use as async context manager")
        return self._client

    async def get_current_user(self) -> dict:
        """Пользователь токена — для проверки подключения."""
        r = await self._http().get("/rest/api/user/current")
        if r.status_code != 200:
            raise ConfluenceClientError(
                f"GET user/current → HTTP {r.status_code}: {r.text[:200]}"
            )
        return r.json()

    async def get_page(self, page_id: str) -> ConfluencePage:
        r = await self._http().get(
            f"/rest/api/content/{page_id}",
            params={"expand": "body.storage"},
        )
        if r.status_code != 200:
            raise ConfluenceClientError(
                f"GET page {page_id} → HTTP {r.status_code}: {r.text[:200]}"
            )
        data = r.json()
        return ConfluencePage(
            id=data["id"],
            title=data.get("title", ""),
            body_html=data.get("body", {}).get("storage", {}).get("value", ""),
        )

    async def find_page_id(self, space_key: str, title: str) -> Optional[str]:
        """id страницы по ключу пространства и точному названию."""
        r = await self._http().get(
            "/rest/api/content",
            params={"spaceKey": space_key, "title": title, "limit": 1},
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results") or []
        return str(results[0]["id"]) if results else None

    async def resolve_page_id(self, url: str) -> Optional[str]:
        """id страницы по любой ссылке Confluence DC.

        Прямой id (``pageId=`` / ``/pages/N``) — сразу; короткая ``/x/…`` —
        по переадресации; ``/display/<пространство>/<название>`` — поиском по
        названию.
        """
        page_id = page_id_from_url(url)
        if page_id:
            return page_id
        if not url.startswith(self.base_url):
            return None
        path = url[len(self.base_url):]
        if path.startswith("/x/"):
            r = await self._http().get(path)
            if r.status_code not in (301, 302):
                return None
            location = r.headers.get("Location", "")
            return page_id_from_url(location) or await self._display_page_id(location)
        return await self._display_page_id(path)

    async def _display_page_id(self, path_or_url: str) -> Optional[str]:
        m = _DISPLAY_RE.search(path_or_url)
        if not m:
            return None
        return await self.find_page_id(unquote_plus(m.group(1)), unquote_plus(m.group(2)))
```

- [ ] **Step 4: Service, project summary**

In `app/services/confluence_service.py`:
- delete `from urllib.parse import urlparse`;
- replace `from app.connectors.confluence_client import ConfluenceClient, ConfluenceClientError` with `from app.connectors.confluence_client import ConfluenceClient, ConfluenceClientError, page_id_from_url`;
- replace the block from `_URL_RE = re.compile(` through the end of `parse_page_id` with:

```python
CONFLUENCE_BASE_URL_KEY = "confluence_base_url"

# Хвост ссылки на страницу Confluence DC после адреса сервера: прямой id,
# /spaces/…/pages/N, «красивая» /display/<пространство>/<название>, короткая
# /x/…. Описание в Jira DC — wiki-разметка, ссылка часто внутри [текст|адрес]:
# «|» и «]» завершают адрес.
_LINK_TAIL = (
    r"(?:pages/viewpage\.action\?pageId=\d+"
    r"|spaces/[^\s/|\]]+/pages/\d+[^\s)|\]]*"
    r"|display/[^\s/|\]]+/[^\s)|\]]+"
    r"|x/[A-Za-z0-9_\-]+)"
)


def extract_confluence_urls(text: Optional[str], base_url: str) -> list[str]:
    """Уникальные ссылки на страницы Confluence с адреса из настроек, в порядке появления."""
    if not text or not base_url:
        return []
    pattern = re.compile(re.escape(base_url.rstrip("/")) + "/" + _LINK_TAIL)
    seen: set[str] = set()
    out: list[str] = []
    for m in pattern.finditer(text):
        url = m.group(0).rstrip(".,);")
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def parse_page_id(url: str) -> Optional[str]:
    """id из ссылки с прямым id; короткую и «красивую» ссылки разрешает клиент."""
    return page_id_from_url(url)
```

- in `ConfluenceService._base_url` replace `AppSetting.key == "jira_base_url"` with `AppSetting.key == CONFLUENCE_BASE_URL_KEY`;
- in `fetch_pages` replace

```python
                for u in unresolved:
                    try:
                        url_to_pid[u] = await client.resolve_tinyurl(u)
                    except Exception as e:
                        logger.warning("tinyurl resolve %s failed: %s", u, e)
```

with

```python
                for u in unresolved:
                    try:
                        url_to_pid[u] = await client.resolve_page_id(u)
                    except Exception as e:
                        logger.warning("Confluence page id resolve %s failed: %s", u, e)
```

- update the step comment `# 1. Резолвим page_id (tinyurl → fetch redirect, прочее regex)` to `# 1. id страницы: прямой — из ссылки, короткая и «красивая» — через клиента`.

In `app/services/project_summary_service.py` replace

```python
        base = self.db.query(AppSetting).filter(
            AppSetting.key == "jira_base_url"
        ).first()
```

with

```python
        base = self.db.query(AppSetting).filter(
            AppSetting.key == "confluence_base_url"
        ).first()
```

- [ ] **Step 5: Confluence settings endpoints**

In `app/api/endpoints/settings.py`:
- add `import httpx` after `import re`;
- after the Jira import add `from app.connectors.confluence_client import ConfluenceClient, ConfluenceClientError`;
- after `class JiraTestResponse` add:

```python
class ConfluenceSettingsResponse(BaseModel):
    base_url: Optional[str] = None
    has_token: bool = False


class ConfluenceSettingsUpdate(BaseModel):
    base_url: Optional[str] = None
    api_token: Optional[str] = None


class ConfluenceTestResponse(BaseModel):
    connected: bool
    user_name: Optional[str] = None
    error: Optional[str] = None
```

- at the end of the file add:

```python
def _confluence_settings(db: Session) -> ConfluenceSettingsResponse:
    return ConfluenceSettingsResponse(
        base_url=_get_setting(db, "confluence_base_url"),
        has_token=_get_setting(db, "confluence_api_token") is not None,
    )


@router.get("/confluence", response_model=ConfluenceSettingsResponse)
async def get_confluence_settings(db: Session = Depends(get_db)):
    """Адрес Confluence и признак сохранённого токена (сам токен не отдаём)."""
    return _confluence_settings(db)


@router.put("/confluence", response_model=ConfluenceSettingsResponse)
async def save_confluence_settings(
    body: ConfluenceSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Сохранить адрес Confluence и персональный токен."""
    if body.base_url is not None:
        _set_setting(db, "confluence_base_url", _with_scheme(body.base_url))
    if body.api_token is not None:
        _set_setting(db, "confluence_api_token", body.api_token)
    db.commit()
    return _confluence_settings(db)


@router.post("/confluence/test", response_model=ConfluenceTestResponse)
async def test_confluence_connection(db: Session = Depends(get_db)):
    """Проверить подключение к Confluence с сохранёнными адресом и токеном."""
    try:
        async with ConfluenceClient.from_db(db) as client:
            user = await client.get_current_user()
    except ConfluenceClientError as e:
        return ConfluenceTestResponse(connected=False, error=str(e))
    except httpx.HTTPError as e:
        return ConfluenceTestResponse(connected=False, error=f"Нет связи с Confluence: {e}")
    return ConfluenceTestResponse(
        connected=True,
        user_name=user.get("displayName") or user.get("username"),
    )
```

Check: `grep -rn "atlassian\|/wiki\|jira_email" app/ --include=*.py` печатает пусто.

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/connectors/test_confluence_client.py tests/services/test_confluence_service.py tests/test_settings_confluence_endpoint.py tests/services/test_project_summary_enrichment.py tests/test_prompt_build.py tests/test_confluence_page_cache_model.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/connectors/confluence_client.py app/services/confluence_service.py app/services/project_summary_service.py app/api/endpoints/settings.py tests/connectors/test_confluence_client.py tests/services/test_confluence_service.py tests/test_settings_confluence_endpoint.py tests/services/test_project_summary_enrichment.py
git commit -m "feat(confluence): свой сервер Confluence — адрес, токен, ссылки DC" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Фронт — карточка подключения к Confluence

**Files:**
- Modify: `frontend/src/types/api.ts` (после `JiraTestResponse`)
- Modify: `frontend/src/api/settings.ts`, `frontend/src/hooks/useSettings.ts`
- Create: `frontend/src/components/ConfluenceConnectionCard.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx:28, 65`

- [ ] **Step 1: Types, API, hooks**

`frontend/src/types/api.ts` — after `JiraTestResponse` add:

```ts
export interface ConfluenceSettingsResponse {
  base_url: string | null;
  has_token: boolean;
}

export interface ConfluenceTestResponse {
  connected: boolean;
  user_name: string | null;
  error: string | null;
}
```

`frontend/src/api/settings.ts` — replace the import line with

```ts
import type {
  ConfluenceSettingsResponse, ConfluenceTestResponse, JiraSettingsResponse, JiraTestResponse,
} from '../types/api';
```

and append:

```ts
export const getConfluenceSettings = () =>
  api.get<ConfluenceSettingsResponse>('/settings/confluence');

export const saveConfluenceSettings = (body: { api_token?: string; base_url?: string }) =>
  api.put<ConfluenceSettingsResponse>('/settings/confluence', body);

export const testConfluenceConnection = () =>
  api.post<ConfluenceTestResponse>('/settings/confluence/test');
```

`frontend/src/hooks/useSettings.ts` — replace

```ts
import { getJiraSettings, saveJiraSettings, testJiraCredentials, saveGenericSetting, getGenericSetting } from '../api/settings';
```

with

```ts
import {
  getJiraSettings, saveJiraSettings, testJiraCredentials, saveGenericSetting, getGenericSetting,
  getConfluenceSettings, saveConfluenceSettings, testConfluenceConnection,
} from '../api/settings';
```

and append:

```ts
export function useConfluenceSettings() {
  return useQuery({
    queryKey: ['settings', 'confluence'],
    queryFn: getConfluenceSettings,
  });
}

export function useSaveConfluenceSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: saveConfluenceSettings,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'confluence'] }),
  });
}

export function useTestConfluenceConnection() {
  return useMutation({ mutationFn: testConfluenceConnection });
}
```

- [ ] **Step 2: Card component**

`frontend/src/components/ConfluenceConnectionCard.tsx`:

```tsx
import { useState } from 'react';
import { Card, Input, Button, Space, App, Typography } from 'antd';
import { ApiOutlined, SaveOutlined } from '@ant-design/icons';
import {
  useConfluenceSettings, useSaveConfluenceSettings, useTestConfluenceConnection,
} from '../hooks/useSettings';

const { Text } = Typography;

/** Подключение к Confluence: свой адрес и персональный токен (сервер отдельный от Jira). */
export default function ConfluenceConnectionCard() {
  const { message } = App.useApp();
  const settings = useConfluenceSettings();
  const saveMutation = useSaveConfluenceSettings();
  const testMutation = useTestConfluenceConnection();

  const [token, setToken] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [loaded, setLoaded] = useState(false);

  if (settings.data && !loaded) {
    if (settings.data.base_url) setBaseUrl(settings.data.base_url);
    setLoaded(true);
  }

  const handleSave = () => {
    const body: { api_token?: string; base_url?: string } = {};
    if (token) body.api_token = token;
    if (baseUrl) body.base_url = baseUrl;
    saveMutation.mutate(body, {
      onSuccess: () => {
        setToken('');
        message.success('Настройки сохранены');
      },
      onError: (e) => message.error(e.message),
    });
  };

  const handleTest = () => {
    if (!settings.data?.base_url || !settings.data?.has_token) {
      message.warning('Сначала сохраните адрес и токен Confluence');
      return;
    }
    testMutation.mutate(undefined, {
      onSuccess: (res) => {
        if (res.connected) message.success(`Подключение успешно (${res.user_name ?? ''})`);
        else message.error(res.error || 'Не удалось подключиться');
      },
      onError: (e) => message.error(e.message),
    });
  };

  return (
    <Card title="Подключение к Confluence" size="small">
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Text type="secondary">
          Страницы Confluence из описаний задач подтягиваются в сводку проекта.
        </Text>
        <Space wrap>
          <Input
            placeholder="Адрес Confluence (https://confluence.example.ru)"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ width: 360 }}
            autoComplete="off"
            name="confluence-base-url"
          />
          <Input.Password
            placeholder={settings.data?.has_token ? 'Токен сохранён (введите новый для замены)' : 'Персональный токен'}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ width: 300 }}
            autoComplete="new-password"
            name="confluence-api-token"
          />
        </Space>
        <Space>
          <Button icon={<SaveOutlined />} type="primary" onClick={handleSave} loading={saveMutation.isPending}>
            Сохранить
          </Button>
          <Button icon={<ApiOutlined />} onClick={handleTest} loading={testMutation.isPending}>
            Проверить подключение
          </Button>
          {testMutation.data?.connected && <Text type="success">{testMutation.data.user_name}</Text>}
        </Space>
      </Space>
    </Card>
  );
}
```

- [ ] **Step 3: Settings page entry**

`frontend/src/pages/SettingsPage.tsx` — after `import ConnectionCard from '../components/ConnectionCard';` add `import ConfluenceConnectionCard from '../components/ConfluenceConnectionCard';`; replace

```tsx
      { key: 'connection', label: 'Подключение к Jira', render: () => <ConnectionCard /> },
```

with

```tsx
      { key: 'connection', label: 'Подключение к Jira', render: () => <ConnectionCard /> },
      { key: 'confluence', label: 'Подключение к Confluence', render: () => <ConfluenceConnectionCard /> },
```

- [ ] **Step 4: Type-check and lint**

Run (in `frontend/`): `npx tsc -b`
Expected: без ошибок.

Run (in `frontend/`): `npx eslint src/types/api.ts src/api/settings.ts src/hooks/useSettings.ts src/components/ConfluenceConnectionCard.tsx src/pages/SettingsPage.tsx`
Expected: без новых ошибок.

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add frontend/src/types/api.ts frontend/src/api/settings.ts frontend/src/hooks/useSettings.ts frontend/src/components/ConfluenceConnectionCard.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat(settings): карточка подключения к Confluence" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: Документация и полный прогон

**Files:**
- Modify (rewrite): `app/connectors/CLAUDE.md`
- Modify: `CLAUDE.md:19, 68, 75-80`
- Modify: `app/models/CLAUDE.md:14, 30, 76`
- Modify: `app/services/CLAUDE.md:110, 114, 119`
- Modify: `app/api/CLAUDE.md:42`
- Modify: `frontend/CLAUDE.md:58, 86`

- [ ] **Step 1: Rewrite `app/connectors/CLAUDE.md`**

Replace the whole file with:

````markdown
# app/connectors — внешние API

httpx (async). Все pydantic-схемы ответов — в [schemas.py](schemas.py).

## JiraClient ([jira_client.py](jira_client.py)) — Jira Data Center

Jira DC 11.3.7, REST API **v2** (`API_PREFIX = "/rest/api/2"`), вход `Authorization: Bearer <персональный токен>`. Облако не поддерживается (переезд — `docs/superpowers/specs/2026-10-14-jira-dc-migration-design.md`).

### Пользователи

У пользователя DC нет `accountId`. `key` (`JIRAUSER12223`, не меняется при переименовании) → `JiraUserSchema.jira_account_id` → `Employee.jira_account_id`. `name` (логин, `Lebedev_A_A`) → `JiraUserSchema.name` → `Employee.jira_username`, синк обновляет его при каждой встрече. Почта не идентификатор (в DC другая, чем была в облаке). JQL `worklogAuthor` принимает логин, не `key`. Поиск — `GET /user/search?username=` (логин, имя, почта; только активные).

### Поиск задач

`GET /search` со смещением: `startAt` / `maxResults` / `total`; `iter_issues` листает до `total`. **Если в JQL нет сортировки, клиент добавляет `ORDER BY key ASC`**: при смещении сортировка по изменяемому полю (`updated`) теряет задачи, изменённые во время обхода. Все запросы — с `validateQuery=warn`: несуществующий ключ в `key in (...)` не роняет весь запрос.

Pydantic-схема ответа **требует** `summary` / `issuetype` / `status` / `project` — любой `search_issues` должен их запрашивать. Сверка ключей без схемы — `iter_issue_keys(jql)` (`fields=key`, страницы по 1000).

`expand=changelog` кладёт историю в `JiraIssueSchema.changelog`. Сколько записей истории DC отдаёт в поиске, не проверено — синк дочитывает неполную (`total` > записей) через `get_issue_changelog(key)` (`GET /issue/{key}?expand=changelog`). Разбор — [changelog.py](changelog.py).

### Чем DC отличается от облака

- `statuscategorychangedate` нет → `Issue.status_changed_at` = последняя смена **категории** статуса по истории (категории — `GET /status`, `statusCategory.key`), иначе дата создания.
- Описание и комментарии — wiki-строка, не ADF (схемы пропускают строку как есть).
- Иерархия: подзадача → `fields.parent`; задача → эпик — «Ссылка на эпик» (`gh-epic-link`); эпик → инициатива — «Parent Link» (`jpo-custom-field-parent`). Значения — строка-ключ. id полей синк находит по типу и хранит в AppSetting `jira_epic_link_field_id` / `jira_parent_link_field_id` (как `jira_sprint_field_id`).
- Спринт — список строк `com.atlassian.greenhopper.service.sprint.Sprint@…[id=…,name=…,state=ACTIVE,…]`, разбирает `sync_service._extract_sprints`.
- Время (`started`, `created`) приходит в UTC (`+0000`). Колонки ворклогов и комментариев хранят московские «настенные» часы, как в облаке, — перевод в `sync_service._drop_tz`.
- Проекты — `GET /project` (массив целиком).

### Ворклоги

`iter_worklogs_updated_since(since_ms)`: `GET /worklog/updated` (`lastPage` / `until`) → `POST /worklog/list` пачками по 1000, потоком. `since_ms=0` — все ворклоги Jira. Удалённые — `iter_deleted_worklog_ids`.

### Опции полей

`get_field_configured_options(field_id)` → `GET /customFields/{n}/options` (включённые значения). Ошибка или не кастомное поле → `[]`; тогда `get_field_distinct_values` сканирует задачи JQL `cf[N] is not EMPTY` (до 1000 свежих). Поле в JQL — `jql_field_ref(id)` (`customfield_11092` → `cf[11092]`).

### Доступность поля на карточке

`get_editable_field_ids(issue_key)` → `GET /issue/{key}/editmeta`, множество id
полей карточки. Нужен, чтобы отличить живое значение кастомного поля от
оставшегося после переноса задачи в другой проект: Jira такие значения хранит и
отдаёт в `fields`, хотя поля на экранах нового проекта нет. Ответ зависит от
проекта, типа задачи и прав — см. `app/services/stale_field_cleanup.py`.

### Team filter на `/sync/jira-projects`

Team filter не может быть single global JQL (`ORDER BY project` + 1000-issue cap группирует всё под первым проектом). Решение: iterate projects, probe каждый `project = "K" AND (cf[N] = X OR cf[M] = X)` через `search_issues(max_results=1)`. Cost ~200ms × N projects, но корректно.

### Rate limiting

Пауза только на повторе (экспонента от 100 мс) + отдельная ветка 429 (`Retry-After`). Лимитов на сервере нет (ответ админа 2026-10-14).

### Сервер

```
Base URL: https://jira.example.ru   (только из внутренней сети)
Версия:   11.3.7, REST API v2
```

## ConfluenceClient ([confluence_client.py](confluence_client.py)) — Confluence Data Center

Свой сервер: AppSetting `confluence_base_url` + `confluence_api_token`, вход Bearer. Пути без `/wiki`: `/rest/api/content/{id}?expand=body.storage`, `/rest/api/user/current`, поиск по названию `/rest/api/content?spaceKey=&title=`. `resolve_page_id(url)`: прямой id (`viewpage.action?pageId=` / `/pages/N`), короткая `/x/…` (переадресация), `/display/<пространство>/<название>` (поиск). Ссылки в описаниях задач ищет `confluence_service.extract_confluence_urls` по адресу из настроек; описание — wiki-разметка, `|` и `]` завершают адрес.

## ProductionCalendarClient ([production_calendar_client.py](production_calendar_client.py))

Тянет официальный RU производственный календарь. Используется `POST /production-calendar/sync?year=N&overwrite_manual=false`.

## Credentials resolution

AppSetting (DB) → `.env` fallback. UI пишет `jira_base_url` / `jira_api_token` через `PUT /settings/jira` и `confluence_base_url` / `confluence_api_token` через `PUT /settings/confluence`; `.env` (`JIRA_BASE_URL`, `JIRA_API_TOKEN`) — только для dev/CI, когда база пуста. Старая строка `jira_email` в базе ни на что не влияет.

## Блокировка синка

Пока AppSetting `jira_migration_state = pending`, любой пишущий синк отказывает (`SyncBlockedError` → HTTP 409, проверка в конструкторе `SyncService` и в начале пишущих эндпоинтов). Сам клиент не ограничен: чтения для переезда и настроек работают. См. `app/services/jira_migration/state.py`.
````

- [ ] **Step 2: Targeted updates in other docs**

`CLAUDE.md`:
- line 19: `Сервис анализа данных Jira Cloud и квартального планирования.` → `Сервис анализа данных Jira Data Center и квартального планирования.`
- line 68: replace with `- **Jira credentials:** AppSetting (DB) → \`.env\` fallback. UI пишет адрес и персональный токен в AppSetting через \`PUT /settings/jira\` (Confluence — отдельно, \`PUT /settings/confluence\`); \`.env\` подключается только для dev/CI когда DB пуста`
- replace the block

````
## Jira Cloud

```
Cloud ID: 00000000-0000-0000-0000-000000000000
Base URL: https://example.atlassian.net
```
````

with

````
## Jira Data Center

```
Base URL: https://jira.example.ru   (только из внутренней сети)
Версия:   11.3.7, REST API v2, вход по персональному токену (Bearer)
```

Пока база не переведена на идентификаторы новой Jira (AppSetting `jira_migration_state = pending`), синхронизация остановлена — см. [app/connectors/CLAUDE.md](app/connectors/CLAUDE.md).
````

`app/models/CLAUDE.md`:
- after line 14 (`` `Employee`, `EmployeeTeam` (M:N), … `SyncState`. ``) add a paragraph:
```markdown
**`Employee` и Jira DC:** `jira_account_id` = DC `key` (`JIRAUSER…`, не меняется), `jira_username` = логин DC (`name`), обновляется синком при каждой встрече; по логину ищутся списания (JQL `worklogAuthor`). Сотрудник без логина в поиске списаний по людям не участвует.
```
- line 30: `- \`status_changed_at\` — из \`statuscategorychangedate\`` → `- \`status_changed_at\` — последняя смена категории статуса по истории изменений Jira DC (\`expand=changelog\` + справочник \`GET /status\`), иначе дата создания`
- line 76: `- Credentials: \`jira_email\`, \`jira_api_token\`, \`jira_base_url\`` → `- Credentials: \`jira_base_url\`, \`jira_api_token\` (Bearer); \`confluence_base_url\`, \`confluence_api_token\`; \`jira_email\` — устарела, не читается`
- after that line add:
```markdown
- Переезд на Jira DC: `jira_migration_state` (`pending` | `done`; нет строки = `done`) — пока `pending`, синк запрещён
- Автопоиск полей по типу: `jira_sprint_field_id`, `jira_epic_link_field_id`, `jira_parent_link_field_id`
```

`app/services/CLAUDE.md`:
- line 110 → `` `_upsert_issue` также захватывает `status_category` из `status.statusCategory.key` и `status_changed_at` — последнюю смену категории статуса по истории (`expand=changelog`, `app/connectors/changelog.py::category_changed_at`; категории из `GET /status` раз за проход), без неё — дату создания. Родитель — `_parent_key_of`: `fields.parent` → «Ссылка на эпик» → «Parent Link». ``
- line 114 → `**Дни простоя (\`sync_paused_days\`):** отдельный проход после задач (стадия \`paused_days\`, non-critical). JQL \`status WAS IN (PAUSED_STATUSES)\` сужает выборку до задач, которые вообще бывали на паузе; история статусов приходит в том же поиске (\`expand=changelog\`), неполная дочитывается \`JiraClient.get_issue_changelog\`. Результат — \`Issue.paused_days\`, целые сутки. Свой курсор \`sync_state\` «paused_days». Разовый пересчёт по всей истории — \`scripts/backfill_paused_days.py\`.`
- line 119: replace `запускается JQL \`worklogAuthor = <account> AND updated >= since\`.` with `запускается JQL \`worklogAuthor = "<Employee.jira_username>" AND updated >= since\` (сотрудник без логина пропускается).`
- after the `## SyncService` heading line add: `Конструктор \`SyncService\` вызывает \`ensure_sync_allowed(db)\`: пока \`jira_migration_state = pending\`, создать сервис нельзя (\`SyncBlockedError\` → 409).`

`app/api/CLAUDE.md` line 42 → `| \`/settings\` | \`settings.py\` | **admin-only** — \`/jira\` (GET\|PUT: адрес + токен, токен не отдаётся) + \`/jira/test\` + \`/confluence\` (GET\|PUT) + \`/confluence/test\` (по сохранённым) + \`/generic\` (PUT) + \`/generic/{key}\` (GET) |`; and in the `/sync` row append `; пишущие эндпоинты (и \`/team-desk/refresh-issues\`, \`/backlog/refresh-from-jira*\`) первой строкой вызывают \`ensure_sync_allowed\` → 409 до завершения переезда на Jira DC`.

`frontend/CLAUDE.md`:
- after line 58 (`Три вкладки в [\`SyncHubPage.tsx\`]…`) add: `Над вкладками — [\`SyncBlockedAlert\`](src/components/sync/SyncBlockedAlert.tsx): пока переезд на новую Jira не завершён (\`useSyncBlocked()\`, \`GET /ui-config/jira-migration-state\`), плашка со ссылкой на \`/admin/jira-migration\`; кнопки обновления из Jira здесь, в бэклоге и на столе тимлида неактивны.`
- line 86 → `- **Подключение**: \`connection\` (\`ConnectionCard\` — адрес + персональный токен) · \`confluence\` (\`ConfluenceConnectionCard\`) · \`scope\` (\`ScopeAdmin\`) · \`fields\` (\`JiraFieldsCard\`)`

- [ ] **Step 3: Full verification**

Run: `ruff check app/ tests/ scripts/make_dc_fixtures.py`
Expected: `All checks passed!`

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py`
Expected: все тесты зелёные (кроме уже красных до начала работы — сравнить со списком падений на `git stash`-чистом дереве, если такие есть).

Run (in `frontend/`): `npx tsc -b && npx vitest run`
Expected: без ошибок, тесты зелёные.

Run: `grep -rn "atlassian\|rest/api/3\|nextPageToken\|search/jql" app/ frontend/src --include=*.py --include=*.ts --include=*.tsx`
Expected: пусто.

Run: `grep -rn '"accountId"\|accountId=\|\.accountId' app/ tests/ --include=*.py`
Expected: пусто (слово accountId осталось только в двух старых комментариях — `app/models/issue.py:198`, `app/services/work_desk_widgets.py:1011` — вне объёма, не трогать).

- [ ] **Step 4: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/connectors/CLAUDE.md CLAUDE.md app/models/CLAUDE.md app/services/CLAUDE.md app/api/CLAUDE.md frontend/CLAUDE.md
git commit -m "docs(jira-dc): клиент Data Center, блокировка синка, Confluence" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review (сделано при написании плана)

**Покрытие спеки, часть A:**
- Bearer, почта не нужна (`from_db`, `__init__`, настройки, `/settings/jira/test`, `ConnectionCard`) — Task 6, 13.
- `/rest/api/2` — Task 6. Поиск `GET /search` со смещением, курсорный код удалён — Task 6.
- Проекты `GET /project` — Task 6.
- Пользователь DC, идентичность `key`, логин в новом поле, JQL `worklogAuthor` по логину, поиск `username=`, авторы ворклогов/комментариев, «Разработчик» → `key` — Task 4, 5, 6.
- История статусов `?expand=changelog`, `status_changed_at` по смене категории (`GET /status`), `expand=changelog` в поиске, дни паузы из той же истории — Task 7, 8, 9.
- Иерархия из трёх полей, автопоиск id и кэш в AppSetting — Task 10.
- Опции полей `GET /customFields/{n}/options`, облачный `/field/{id}/context` удалён, резерв — JQL `cf[N]` — Task 8.
- Спринт: тест на настоящую DC-строку — Task 10.
- Описание wiki-строкой — схемы пропускают строку (без изменений), фикстуры содержат wiki-описание.
- Ссылки на задачи из настроек (`plan_common.py` + 7 компонентов) — Task 12, 14.
- Confluence: адрес и токен, Bearer, пути без `/wiki`, распознавание по хосту из настроек — Task 16, 17.

**Покрытие спеки, часть B:** `jira_migration_state` + миграция (`pending` при задачах) — Task 1; проверка в одном месте (`SyncService.__init__`) + явная в пишущих эндпоинтах, расписание, бэклог, стол тимлида, `refresh_issues_by_keys` (через `SyncService`), `backfill_issue_author` — Task 1–2; чтения (проверка подключения, поля, пользователи, типы, проекты) не блокируются — эндпоинты `test-connection`, `jira-*`, `/jira/users/search`, `/settings/*` проверку не вызывают; фронт — плашка со ссылкой на страницу переезда и неактивные кнопки — Task 15.

**Сверх спеки (обосновано):** устойчивая сортировка JQL при смещении (Task 6), `validateQuery=warn` (Task 6), московское настенное время ворклогов (Task 11), дочитывание неполной истории (Task 9), обезличивание `employees.jira_username` в демо-базе (Task 5).

## Не подтверждено образцами DC (проверить вторым скриптом админа)

- Форма `changelog` (`?expand=changelog` у задачи и в поиске) и полнота истории в поиске — в `data/jira_check.txt` истории нет; код написан по стандартному формату Jira Server и дочитывает неполную историю.
- `GET /status`, `GET /project`, `GET /customFields/{n}/options` (есть только ответ-ошибка на облачный id 11526 — сам путь существует), поля `lastPage`/`until` у `/worklog/updated` (ответ в файле обрезан).
- `validateQuery=warn` для несуществующих ключей в `key in (...)`.
- Подзадачи (`fields.parent`) — ни одной в образцах; «Ссылка на эпик» и «Parent Link» подтверждены.
- Confluence DC: `/rest/api/content`, `/rest/api/user/current`, переадресация `/x/…` — образцов нет.
- Локальная dev-база после `alembic upgrade head` станет `pending` (в ней есть задачи): локальный синк и тесты, которые ходят в dev-базу через `SessionLocal`, получат блокировку. Вернуть `done` — командой из Task 15 Step 5.

