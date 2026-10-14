# Jira DC Migration Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Страница администратора «Переезд на новую Jira» (часть C спеки `docs/superpowers/specs/2026-10-14-jira-dc-migration-design.md`): пробный прогон (только чтение Jira DC, в базу — только отчёт) → отчёт с решениями администратора → «Применить» одной транзакцией (перепривязка задач, проектов, сотрудников, людей в задачах и JSON, настроек полей; удаление ворклогов и комментариев; состояние `done`) → полная синхронизация всех ворклогов → «Сверка после».

**Architecture:** Пакет `app/services/jira_migration/` (рядом с `state.py` из плана 1), разбитый по ответственности: чистые функции сопоставления (`fields.py`, `fingerprints.py`, `people.py`, `hours.py`), запросы к базе (`issues.py`), проверка возможностей (`probe.py`), хранение отчёта и решений (`store.py`, таблицы `jira_migration_reports` / `jira_migration_decisions`), сборка отчёта (`dry_run.py`), текущее состояние решений и препятствия (`resolution.py`), применение (`apply.py`), фоновые операции по образцу выгрузки базы — состояние в памяти + `BackgroundTasks` (`runner.py`), ответ страницы (`overview.py`). Эндпоинты `app/api/endpoints/jira_migration.py` под `/admin/jira-migration` (admin-only на уровне роутера). Фронт — раздел «Переезд на новую Jira» в группе «Администрирование» настроек; маршрут `/admin/jira-migration` (на него ведёт плашка плана 1) переадресует на `/settings#jira-migration`.

**Tech Stack:** Python 3.10 (`py -3.10`), FastAPI, SQLAlchemy 2.0 (ORM bulk UPDATE по первичному ключу), Alembic, pytest (asyncio_mode=auto); React 19 / TS / AntD 6, TanStack Query, vitest.

---

## Prerequisite: plan 2026-10-14-jira-dc-client.md fully implemented

Этот план выполняется **после** `docs/superpowers/plans/2026-10-14-jira-dc-client.md` (части A+B) и опирается только на его раздел «Interfaces for the migration plan». Перед Task 1 проверить:

```bash
git branch --show-current                     # feature/jira-dc-migration
grep -n "async def iter_issue_keys\|async def iter_worklogs_updated_since\|async def get_statuses\|async def get_issue_changelog" app/connectors/jira_client.py
grep -n "def set_migration_state\|STATE_DONE" app/services/jira_migration/state.py
grep -n "jira_username" app/models/employee.py
ls alembic/versions/dc02_employee_jira_username.py tests/dc_fixtures.py tests/fixtures/jira_dc/fields.json
grep -n "jira-migration-state" frontend/src/hooks/useSettings.ts
```

Все команды должны находить строки/файлы. Если что-то не найдено — остановиться: план 1 не завершён.

Используемые интерфейсы плана 1: `JiraClient.from_db`, `get_myself`, `get_projects`, `search_issues`, `iter_issue_keys`, `iter_worklogs_updated_since`, `get_fields`, `get_statuses`, `get_issue_changelog`, `get_field_configured_options`, `search_users`; `JiraClientError`; `JiraUserSchema` (`jira_account_id`, `name`, `display_name`, `email`, `is_active`), `JiraWorklogSchema` (`issueId`, `author`, `started_datetime`, `timeSpentSeconds`), `JiraProjectSchema`, `JiraSearchResponseSchema`; `state.py` (`get_migration_state`, `set_migration_state`, `STATE_PENDING`, `STATE_DONE`); `ConfluenceClient.from_db` + `get_current_user`; `employees.jira_username`; `tests/dc_fixtures.py::load_dc`; ключ запроса `['ui-config', 'jira-migration-state']`; маршрут `/admin/jira-migration`; `down_revision = "dc02_employee_jira_username"`.

---

## File Structure

### Создаются

| Файл | Ответственность |
|---|---|
| `app/models/jira_migration.py` | Таблицы `jira_migration_reports` (отчёт прогона, соответствия для применения, итог применения, сверка) и `jira_migration_decisions` (решения администратора) |
| `alembic/versions/dc03_jira_migration_tables.py` | Миграция таблиц (идемпотентная) |
| `app/services/jira_migration/store.py` | Отчёт и решения в базе, проверка формы решения |
| `app/services/jira_migration/cloud_fields.py` | Константа: названия 35 облачных полей |
| `app/services/jira_migration/fields.py` | Снимок облачных настроек полей, предложение поля DC по названию, итог сопоставления, перезапись настроек и кандидатов оценки |
| `app/services/jira_migration/fingerprints.py` | Отпечатки ворклогов, определение смещения часов облака, чтение всех ворклогов DC |
| `app/services/jira_migration/hours.py` | Часы по (команда, месяц): база против DC, сверка после |
| `app/services/jira_migration/people.py` | Голосование по совпавшим ворклогам, ФИО, итоговая привязка и конфликт «двое на одного» |
| `app/services/jira_migration/issues.py` | Новые id задач по ключам, служебные данные задачи, разбор отсутствующих в DC |
| `app/services/jira_migration/probe.py` | Проверка возможностей DC |
| `app/services/jira_migration/dry_run.py` | Сборка отчёта пробного прогона |
| `app/services/jira_migration/resolution.py` | Текущее состояние решений по отчёту, препятствия к применению |
| `app/services/jira_migration/apply.py` | Применение одной транзакцией |
| `app/services/jira_migration/runner.py` | Фоновые операции (прогон, применение), полная синхронизация после, сверка |
| `app/services/jira_migration/overview.py` | Ответ страницы, проверка цели решения |
| `app/api/endpoints/jira_migration.py` | `/admin/jira-migration`: состояние, прогон, решения, поиск пользователей DC, применение, повтор полной синхронизации, сверка |
| `frontend/src/api/jiraMigration.ts` | Типы и вызовы API |
| `frontend/src/hooks/useJiraMigration.ts` | Запросы/мутации |
| `frontend/src/utils/jiraMigration.ts` (+ `.test.ts`) | Подписи статусов, фильтр сотрудников, форматирование часов |
| `frontend/src/components/settings/jiraMigration/JiraMigrationTab.tsx` | Раздел целиком: запуск прогона, прогресс, вкладки отчёта |
| `frontend/src/components/settings/jiraMigration/ProbeSection.tsx` | Проверка возможностей |
| `frontend/src/components/settings/jiraMigration/FieldsSection.tsx` | Поля |
| `frontend/src/components/settings/jiraMigration/IssuesSection.tsx` | Задачи |
| `frontend/src/components/settings/jiraMigration/PeopleSection.tsx` | Сотрудники + окно привязки |
| `frontend/src/components/settings/jiraMigration/HoursSection.tsx` | Часы и сверка после |
| `frontend/src/components/settings/jiraMigration/ApplySection.tsx` | Препятствия, команда копии базы, галочка, «Применить», полная синхронизация, «Сверка после» |
| `docs/jira-dc-migration-runbook.md` | Порядок действий администратора и сисадмина |
| Тесты: `tests/services/jira_migration/{__init__,fake_jira,factory,test_store,test_fields,test_fingerprints_hours,test_people,test_issues,test_probe,test_dry_run,test_resolution,test_apply,test_runner}.py`, `tests/test_migration_dc03_jira_migration_tables.py`, `tests/api/test_jira_migration_api.py` | |

### Меняются

| Файл | Что |
|---|---|
| `app/models/__init__.py` | Регистрация двух моделей |
| `scripts/demo_db/anonymize.py` | Новые таблицы — в `DELETE_TABLES` (в них ФИО и логины) |
| `app/api/router.py` | Роутер `/admin/jira-migration` (admin-only) |
| `frontend/src/pages/SettingsPage.tsx` | Пункт «Переезд на новую Jira» в группе «Администрирование» |
| `frontend/src/routes.tsx` | `/admin/jira-migration` → `/settings#jira-migration` |
| `docs/help/settings.md` | Раздел 3.22 |
| `app/services/CLAUDE.md`, `app/api/CLAUDE.md`, `app/models/CLAUDE.md`, `frontend/CLAUDE.md` | Описание пакета, роутера, таблиц, раздела |

---

## Решения, уточнённые в плане (сверено с кодом)

1. **Служебные данные задачи** (`issues.service_data_reasons`) — только то, что завёл человек:
   строка `backlog_items`; `issue_classifications` с `prompt_version == "manual"` (ручная классификация, `work_type_report.py:382`; строки модели — нет); `plan_audit` с источником `manual_edit`/`manual_revert`/`conflict_accepted`/`conflict_ignored`/`dispute_choice` (записи `jira_sync`/`jira_sync_conflict` пишет синк, `sync_service.py:534`); любая строка `team_desk_marks`, `team_desk_daily_rates`, `scenario_allocation_snapshots` (утверждённый сценарий); `category_overrides` и `scope_roots` по ключу; колонки задачи `assigned_category`, `assigned_subgroup_id`, `planned_*_hours_manual`, непустой `planned_hours_choice`.
   **Не считаются:** `include_in_analysis`, `category_verified`, `subgroup_verified` (значения по умолчанию / пометки сервиса), `parent_changed`, `category_context*`, `require_child_verification` (пометки сервиса), `project_ai_summaries` (кэш ИИ: «Заполняется фоновым job'ом или ручной кнопкой», для исчезнувшей задачи пересоздать нечего).
2. **Автокэши полей.** Спека велит сбрасывать `jira_sprint_field_id`, `jira_customer_field_id`, `jira_cost_type_field_id` (+ `jira_epic_link_field_id`, `jira_parent_link_field_id` из плана 1). Но `jira_cost_type_field_id` синк читает при каждой записи задачи (`sync_service.py:392`, `:1019` — `issues.cost_type` для KPI), а заново находит его только обновление бэклога (`backlog.py:281`). Поэтому: ключ-автокэш, для которого сопоставление дало поле DC (по названию или решению), получает это поле; ключ без поля DC и автокэши, которых не было в снимке, — удаляются (синк/бэклог найдут сами). Строки сопоставления, затрагивающие только автокэши, не считаются нерешёнными.
3. **Неиспользуемые настройки** `jira_involvement_{analyst,dev,qa,opo}_field_id` (вовлечённость сервис из Jira не берёт; в коде не читаются) в снимок не входят и не требуют решений.
4. **Полная синхронизация после применения** — обычный конвейер `build_pipeline(mode="full")`, но стадия ворклогов заменяется на `WorklogsFullStage(since=<самая ранняя дата ворклога в базе − 1 день>)`: штатный «полный» режим грузит ворклоги только за 90 дней (`sync_pipeline.py:310-315`), а применение удаляет все. Запуск — на сервере (не SSE: ручной конвейер отменяется при закрытии страницы, `sync.py:84-87`), с `SyncLock` и записью `SyncRun` по образцу `scheduler.scheduled_pipeline_runner`. На странице — кнопка «Запустить полную синхронизацию заново» с той же датой.
5. **Проекты, которых нет в DC**, решений не требуют: остаются с id `cloud:<старый>` (на проект ссылаются бэклог и задачи).
6. **Сотрудники, появившиеся после прогона** (план 1 разрешает «добавить из Jira» при `pending`), блокируют применение: «запустите прогон заново».
7. **Предложение поля DC**: точное совпадение названия без учёта регистра и крайних пробелов; если одноимённых полей несколько — берётся поле того же рода (своё/системное): «Окружение» есть и системное `environment`, и своё `customfield_11018`. Системное облачное поле без известного названия ищется по тому же id.
8. **ФИО**: кандидаты — результаты `search_users(ФИО)` (только активные) ∪ авторы ворклогов DC (в том числе неактивные) с тем же нормализованным ФИО.
9. **Смещение**: на выборке до 20 000 ворклогов DC (по задачам базы) пробуются −12…+14 ч против множества отпечатков базы; при равенстве — меньшее по модулю.
10. **Голос** даёт только отпечаток, единственный и в базе, и в DC (два одинаковых списания не говорят, чьё из них чьё).
11. При применении удаляются и строки `category_mappings` вида `worklog` (иначе 160 тыс. сирот: `MappingService.recalculate_worklogs` только добавляет), и вида `issue` для удаляемых задач.
12. Время в ответе страницы — наивное UTC базы с суффиксом `Z` (`overview.iso`), возраст прогона считает сервер (`age_hours`).

---

## Conventions for every task

- Ветка: перед каждым коммитом `git branch --show-current` должен печатать `feature/jira-dc-migration`. Если нет — остановиться и спросить.
- Коммит: только `git add <пути>` + `git commit -m "<заголовок>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"` (второй `-m` даёт пустую строку перед подписью). Никогда `git commit -- <пути>`. `data/` не коммитить.
- Тесты: `py -3.10 -m pytest <файл>::<тест> -v`; полный прогон — `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py`, только в переднем плане (таймаут 600000 мс).
- Линтер бэка: `ruff check app/ tests/`.
- Фронт (из `frontend/`): типы — `npx tsc -b`; линтер по изменённым файлам — `npx eslint <файлы>`; тесты — `npx vitest run <файл>`.
- Видимые пользователю строки — на русском, без технических терминов; уведомления и `Alert` AntD 6 — `title`.

---

### Task 1: Таблицы отчёта и решений, хранилище

**Files:**
- Create: `app/models/jira_migration.py`
- Modify: `app/models/__init__.py:77-79` (импорт после блока `from app.models.kpi import (...)`), конец `__all__`
- Create: `alembic/versions/dc03_jira_migration_tables.py`
- Create: `app/services/jira_migration/store.py`
- Modify: `scripts/demo_db/anonymize.py:40-44` (`DELETE_TABLES`)
- Test: `tests/services/jira_migration/__init__.py`, `tests/services/jira_migration/test_store.py`, `tests/test_migration_dc03_jira_migration_tables.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/jira_migration/__init__.py`:

```python
```

(пустой файл — пакет тестов переезда)

`tests/services/jira_migration/test_store.py`:

```python
"""Отчёт пробного прогона и решения администратора в базе."""
from datetime import datetime, timedelta

import pytest

from app.models.jira_migration import JiraMigrationReport
from app.services.jira_migration import store

NOW = datetime(2026, 10, 14, 12, 0)


def test_decision_upsert_and_delete(db_session):
    store.set_decision(db_session, store.KIND_FIELD, "customfield_11526",
                       {"dc_field_id": "customfield_11092"}, "Админ")
    store.set_decision(db_session, store.KIND_FIELD, "customfield_11526",
                       {"dc_field_id": None}, "Админ")
    assert store.get_decisions(db_session, store.KIND_FIELD) == {
        "customfield_11526": {"dc_field_id": None}
    }
    store.set_decision(db_session, store.KIND_FIELD, "customfield_11526", None, "Админ")
    assert store.get_decisions(db_session, store.KIND_FIELD) == {}


def test_decisions_are_separated_by_kind(db_session):
    store.set_decision(db_session, store.KIND_ISSUE, "OS-1", {"action": "keep"}, "Админ")
    store.set_decision(db_session, store.KIND_PERSON, "emp-1", {"action": "unbind"}, "Админ")
    assert store.get_decisions(db_session, store.KIND_ISSUE) == {"OS-1": {"action": "keep"}}
    assert store.get_decisions(db_session, store.KIND_PERSON) == {"emp-1": {"action": "unbind"}}


@pytest.mark.parametrize("kind, decision", [
    ("field", {"dc_field_id": ""}),
    ("field", {"field": "customfield_1"}),
    ("issue", {"action": "archive"}),
    ("person", {"action": "bind"}),
    ("person", {"action": "bind", "key": "JIRAUSER1"}),
    ("person", {"action": "unbind", "key": "JIRAUSER1"}),
    ("project", {"action": "keep"}),
])
def test_invalid_decisions_rejected(kind, decision):
    with pytest.raises(ValueError):
        store.validate_decision(kind, decision)


def test_valid_decisions_accepted():
    store.validate_decision("field", {"dc_field_id": None})
    store.validate_decision("field", {"dc_field_id": "customfield_11092"})
    store.validate_decision("issue", {"action": "delete"})
    store.validate_decision("issue", None)
    store.validate_decision("person", {"action": "unbind"})
    store.validate_decision("person", {"action": "bind", "key": "JIRAUSER1",
                                       "name": None, "display_name": "Иванов Иван"})


def test_new_report_replaces_old_ones_but_keeps_decisions(db_session):
    store.set_decision(db_session, store.KIND_ISSUE, "OS-1", {"action": "keep"}, "Админ")
    first = store.start_report(db_session, NOW)
    store.finish_report(db_session, first, {"probe": []}, {"issues": {}}, NOW)

    second = store.start_report(db_session, NOW + timedelta(minutes=5))

    assert db_session.query(JiraMigrationReport).count() == 1
    row = store.latest_report(db_session)
    assert row.id == second
    assert row.status == store.STATUS_RUNNING
    assert store.get_decisions(db_session, store.KIND_ISSUE) == {"OS-1": {"action": "keep"}}


def test_finish_fail_and_extras(db_session):
    report_id = store.start_report(db_session, NOW)
    store.finish_report(db_session, report_id, {"offset_hours": 3},
                        {"issues": {"OS-1": "258783"}}, NOW + timedelta(minutes=30))
    row = store.latest_report(db_session)
    assert row.status == store.STATUS_DONE
    assert store.report_data(row) == {"offset_hours": 3}
    assert store.report_maps(row) == {"issues": {"OS-1": "258783"}}

    store.set_sync_run(db_session, report_id, "run-1")
    store.save_post_check(db_session, report_id, {"rows": []})
    row = store.latest_report(db_session)
    assert row.sync_run_id == "run-1"
    assert store.post_check_data(row) == {"rows": []}
    assert store.apply_summary(row) is None

    store.fail_report(db_session, report_id, "сбой", NOW, report={"probe": [1]})
    row = store.latest_report(db_session)
    assert row.status == store.STATUS_FAILED
    assert row.error == "сбой"
    assert store.report_data(row) == {"probe": [1]}


def test_fail_report_without_row_is_noop(db_session):
    store.fail_report(db_session, None, "сбой", NOW)
    assert store.latest_report(db_session) is None
```

`tests/test_migration_dc03_jira_migration_tables.py`:

```python
"""dc03: таблицы отчёта и решений переезда; повторный запуск на базе из create_all не падает."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

from app.models.jira_migration import JiraMigrationDecision, JiraMigrationReport

REPO_ROOT = Path(__file__).resolve().parent.parent
TABLES = {"jira_migration_reports", "jira_migration_decisions"}


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _tables(db_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_and_downgrade_drops(tmp_path):
    db = tmp_path / "m.db"
    _alembic(db, "upgrade", "dc03_jira_migration_tables")
    assert TABLES <= _tables(db)

    _alembic(db, "downgrade", "dc02_employee_jira_username")
    assert not (TABLES & _tables(db))


def test_upgrade_skips_tables_from_create_all(tmp_path):
    db = tmp_path / "pre.db"
    _alembic(db, "upgrade", "dc02_employee_jira_username")
    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    try:
        JiraMigrationReport.__table__.create(engine)
        JiraMigrationDecision.__table__.create(engine)
    finally:
        engine.dispose()

    _alembic(db, "upgrade", "dc03_jira_migration_tables")
    assert TABLES <= _tables(db)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_store.py tests/test_migration_dc03_jira_migration_tables.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.jira_migration'`.

- [ ] **Step 3: Models**

`app/models/jira_migration.py`:

```python
"""Переезд на Jira Data Center: отчёт пробного прогона и решения администратора.

Отчёт пересоздаётся каждым пробным прогоном. Решения живут отдельно и
переживают повторные прогоны: ключ решения — то, что при переезде не
меняется (облачный номер поля, ключ задачи, внутренний номер сотрудника).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class JiraMigrationReport(Base, TimestampMixin):
    """Отчёт пробного прогона, итог применения и сверка после."""

    __tablename__ = "jira_migration_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    # running | done | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Сводка для страницы (JSON-строка).
    report_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Соответствия для применения: ключ задачи → id в новой Jira и т. п. (JSON-строка).
    maps_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    apply_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Полная синхронизация, запущенная после применения.
    sync_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    post_check_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class JiraMigrationDecision(Base, TimestampMixin):
    """Решение администратора по пункту отчёта (JSON-строка в ``decision_json``)."""

    __tablename__ = "jira_migration_decisions"
    __table_args__ = (
        UniqueConstraint("kind", "item_key", name="uq_jira_migration_decision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    # field | issue | person
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    item_key: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_json: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
```

In `app/models/__init__.py` after the block

```python
from app.models.kpi import (
    KpiMetric, KpiProfile, KpiProfileMetric, KpiProfileRole, KpiCycleTimeNorm, KpiApproval,
)
```

add:

```python
from app.models.jira_migration import JiraMigrationDecision, JiraMigrationReport  # noqa: F401
```

and at the end of `__all__` replace

```python
    "PerfServerSnapshot",
]
```

with

```python
    "PerfServerSnapshot",
    "JiraMigrationReport",
    "JiraMigrationDecision",
]
```

- [ ] **Step 4: Migration**

`alembic/versions/dc03_jira_migration_tables.py`:

```python
"""jira_migration_reports + jira_migration_decisions

Revision ID: dc03_jira_migration_tables
Revises: dc02_employee_jira_username
Create Date: 2026-10-14

Отчёт пробного прогона переезда на Jira Data Center и решения
администратора. Самодостаточна: не импортирует код приложения. Локальная
база может уже иметь таблицы от create_all в tests/conftest.py — такие
пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "dc03_jira_migration_tables"
down_revision: Union[str, None] = "dc02_employee_jira_username"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    if not _has("jira_migration_reports"):
        op.create_table(
            "jira_migration_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("report_json", sa.Text(), nullable=True),
            sa.Column("maps_json", sa.Text(), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
            sa.Column("apply_summary_json", sa.Text(), nullable=True),
            sa.Column("sync_run_id", sa.String(36), nullable=True),
            sa.Column("post_check_json", sa.Text(), nullable=True),
            *_timestamps(),
        )
    if not _has("jira_migration_decisions"):
        op.create_table(
            "jira_migration_decisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("item_key", sa.String(128), nullable=False),
            sa.Column("decision_json", sa.Text(), nullable=False),
            sa.Column("decided_by", sa.String(255), nullable=True),
            *_timestamps(),
            sa.UniqueConstraint("kind", "item_key", name="uq_jira_migration_decision"),
        )


def downgrade() -> None:
    if _has("jira_migration_decisions"):
        op.drop_table("jira_migration_decisions")
    if _has("jira_migration_reports"):
        op.drop_table("jira_migration_reports")
```

- [ ] **Step 5: Store**

`app/services/jira_migration/store.py`:

```python
"""Хранение отчёта пробного прогона и решений администратора.

Отчёт — одна строка: новый прогон вытесняет прежние. Решения — отдельная
таблица, переживают повторные прогоны.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session, defer

from app.models.jira_migration import JiraMigrationDecision, JiraMigrationReport

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

KIND_FIELD = "field"
KIND_ISSUE = "issue"
KIND_PERSON = "person"
KINDS = (KIND_FIELD, KIND_ISSUE, KIND_PERSON)

ISSUE_DELETE = "delete"
ISSUE_KEEP = "keep"
PERSON_BIND = "bind"
PERSON_UNBIND = "unbind"


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(raw: Optional[str]) -> Optional[Any]:
    return json.loads(raw) if raw else None


def latest_report(db: Session) -> Optional[JiraMigrationReport]:
    """Последний отчёт. Соответствия (мегабайты) подгружаются только по запросу."""
    return (
        db.query(JiraMigrationReport)
        .options(defer(JiraMigrationReport.maps_json))
        .order_by(JiraMigrationReport.started_at.desc())
        .first()
    )


def report_data(row: Optional[JiraMigrationReport]) -> dict:
    if row is None:
        return {}
    return _load(row.report_json) or {}


def report_maps(row: Optional[JiraMigrationReport]) -> dict:
    if row is None:
        return {}
    return _load(row.maps_json) or {}


def apply_summary(row: Optional[JiraMigrationReport]) -> Optional[dict]:
    return _load(row.apply_summary_json) if row is not None else None


def post_check_data(row: Optional[JiraMigrationReport]) -> Optional[dict]:
    return _load(row.post_check_json) if row is not None else None


def start_report(db: Session, now: datetime) -> str:
    """Начать прогон: прежние отчёты удаляются (решения не трогаются). Коммитит."""
    db.query(JiraMigrationReport).delete(synchronize_session=False)
    row = JiraMigrationReport(status=STATUS_RUNNING, started_at=now)
    db.add(row)
    db.flush()
    report_id = row.id
    db.commit()
    return report_id


def finish_report(db: Session, report_id: str, report: dict, maps: dict, now: datetime) -> None:
    row = db.get(JiraMigrationReport, report_id)
    if row is None:
        return
    row.status = STATUS_DONE
    row.finished_at = now
    row.error = None
    row.report_json = _dump(report)
    row.maps_json = _dump(maps)
    db.commit()


def fail_report(
    db: Session,
    report_id: Optional[str],
    error: str,
    now: datetime,
    report: Optional[dict] = None,
) -> None:
    if report_id is None:
        return
    row = db.get(JiraMigrationReport, report_id)
    if row is None:
        return
    row.status = STATUS_FAILED
    row.finished_at = now
    row.error = error
    if report is not None:
        row.report_json = _dump(report)
    db.commit()


def set_sync_run(db: Session, report_id: str, run_id: str) -> None:
    row = db.get(JiraMigrationReport, report_id)
    if row is not None:
        row.sync_run_id = run_id
        db.commit()


def save_post_check(db: Session, report_id: str, data: dict) -> None:
    row = db.get(JiraMigrationReport, report_id)
    if row is not None:
        row.post_check_json = _dump(data)
        db.commit()


def get_decisions(db: Session, kind: str) -> dict[str, dict]:
    rows = db.query(JiraMigrationDecision).filter(JiraMigrationDecision.kind == kind).all()
    return {r.item_key: json.loads(r.decision_json) for r in rows}


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_decision(kind: str, decision: Optional[Mapping[str, Any]]) -> None:
    """Проверить форму решения; ``None`` — снять решение. Ошибка — ``ValueError``."""
    if kind not in KINDS:
        raise ValueError("Неизвестный вид решения")
    if decision is None:
        return
    keys = set(decision)
    if kind == KIND_FIELD:
        value = decision.get("dc_field_id")
        if keys != {"dc_field_id"} or (value is not None and not _is_text(value)):
            raise ValueError("Решение по полю: выберите поле новой Jira или «Не использовать»")
        return
    if kind == KIND_ISSUE:
        if keys != {"action"} or decision.get("action") not in (ISSUE_DELETE, ISSUE_KEEP):
            raise ValueError("Решение по задаче: «Удалить» или «Оставить»")
        return
    action = decision.get("action")
    if action == PERSON_UNBIND and keys == {"action"}:
        return
    if (
        action == PERSON_BIND
        and keys <= {"action", "key", "name", "display_name"}
        and _is_text(decision.get("key"))
        and _is_text(decision.get("display_name"))
        and (decision.get("name") is None or isinstance(decision.get("name"), str))
    ):
        return
    raise ValueError("Решение по сотруднику: выберите пользователя новой Jira или «Без привязки»")


def set_decision(
    db: Session,
    kind: str,
    item_key: str,
    decision: Optional[Mapping[str, Any]],
    decided_by: Optional[str],
) -> None:
    """Записать или снять (``None``) решение. Коммитит."""
    validate_decision(kind, decision)
    row = (
        db.query(JiraMigrationDecision)
        .filter(JiraMigrationDecision.kind == kind, JiraMigrationDecision.item_key == item_key)
        .first()
    )
    if decision is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(JiraMigrationDecision(
            kind=kind, item_key=item_key, decision_json=_dump(dict(decision)), decided_by=decided_by,
        ))
    else:
        row.decision_json = _dump(dict(decision))
        row.decided_by = decided_by
    db.commit()
```

- [ ] **Step 6: Demo anonymizer — new tables are wiped**

In `scripts/demo_db/anonymize.py` replace

```python
DELETE_TABLES = (
    "confluence_page_cache", "feedback_items", "project_ai_summaries", "work_type_report_snapshots",
    "executive_dashboard_snapshots", "issue_classifications", "usage_events", "usage_daily",
    "sync_run", "work_desks", "perf_minute", "perf_slow_request", "perf_server_snapshot",
)
```

with

```python
DELETE_TABLES = (
    "confluence_page_cache", "feedback_items", "project_ai_summaries", "work_type_report_snapshots",
    "executive_dashboard_snapshots", "issue_classifications", "usage_events", "usage_daily",
    "sync_run", "work_desks", "perf_minute", "perf_slow_request", "perf_server_snapshot",
    # Отчёт переезда на Jira DC и решения по нему: ФИО и логины сотрудников.
    "jira_migration_reports", "jira_migration_decisions",
)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_store.py tests/test_migration_dc03_jira_migration_tables.py tests/test_migrations_fresh_db.py tests/test_demo_db_anonymize.py -v`
Expected: PASS (test_store — 13, миграция — 2, цепочка миграций и обезличивание — как раньше; Postgres-вариант цепочки — skipped без `TEST_DATABASE_URL`).

Run: `ruff check app/models/jira_migration.py app/services/jira_migration/store.py alembic/versions/dc03_jira_migration_tables.py tests/services/jira_migration tests/test_migration_dc03_jira_migration_tables.py`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/models/jira_migration.py app/models/__init__.py alembic/versions/dc03_jira_migration_tables.py app/services/jira_migration/store.py scripts/demo_db/anonymize.py tests/services/jira_migration/__init__.py tests/services/jira_migration/test_store.py tests/test_migration_dc03_jira_migration_tables.py
git commit -m "feat(jira-migration): таблицы отчёта и решений переезда" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Поля — снимок, предложения по названию, перезапись настроек и кандидатов оценки

**Files:**
- Create: `app/services/jira_migration/cloud_fields.py`
- Create: `app/services/jira_migration/fields.py`
- Test: `tests/services/jira_migration/test_fields.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/jira_migration/test_fields.py`:

```python
"""Поля Jira при переезде: снимок облачных настроек, предложения, перезапись."""
import json

from app.models.app_setting import AppSetting
from app.services.jira_migration.cloud_fields import CLOUD_FIELD_NAMES
from app.services.jira_migration.fields import (
    build_field_rows,
    ensure_field_snapshot,
    load_field_snapshot,
    remap_plan_sources,
    resolve_fields,
    rewrite_setting_value,
    suggest_dc_field,
)
from app.services.plan_sources import Candidate, fingerprint, resolve_role
from tests.dc_fixtures import load_dc

DC_FIELDS = [
    {"id": "customfield_11092", "name": "Продуктовая команда", "custom": True},
    {"id": "customfield_11097", "name": "Разработка (ч)", "custom": True},
    {"id": "customfield_11034", "name": "Оценка 1С (ч)", "custom": True},
    {"id": "customfield_11018", "name": "Окружение", "custom": True},
    {"id": "environment", "name": "Окружение", "custom": False},
    {"id": "priority", "name": "Приоритет", "custom": False},
    {"id": "duedate", "name": "Срок исполнения", "custom": False},
    {"id": "customfield_10109", "name": "Спринт", "custom": True},
    {"id": "customfield_20001", "name": "Дубль", "custom": True},
    {"id": "customfield_20002", "name": "дубль ", "custom": True},
]


def test_cloud_names_constant():
    assert len(CLOUD_FIELD_NAMES) == 35
    assert CLOUD_FIELD_NAMES["customfield_11526"] == "Продуктовая команда"
    assert CLOUD_FIELD_NAMES["priority"] == "Приоритет"
    # «1С» — кириллическая «С», как в облаке: иначе точное сравнение не сработает.
    assert CLOUD_FIELD_NAMES["customfield_14648"] == "Оценка 1С (ч)"
    assert CLOUD_FIELD_NAMES["customfield_14649"] == "Оценка QA 1С (ч)"


def test_snapshot_taken_once_and_kept(db_session):
    db_session.add_all([
        AppSetting(key="jira_team_field_id", value="customfield_11526"),
        AppSetting(key="jira_risk_field_id", value=""),
        AppSetting(key="jira_involvement_dev_field_id", value="customfield_12437"),
        AppSetting(key="jira_base_url", value="https://jira.example.test"),
    ])
    db_session.commit()

    assert ensure_field_snapshot(db_session) == {"jira_team_field_id": "customfield_11526"}

    db_session.query(AppSetting).filter_by(key="jira_team_field_id").one().value = "customfield_11092"
    db_session.commit()

    assert ensure_field_snapshot(db_session) == {"jira_team_field_id": "customfield_11526"}
    assert load_field_snapshot(db_session) == {"jira_team_field_id": "customfield_11526"}


def test_suggestion_by_exact_name_ignoring_case_and_edges():
    assert suggest_dc_field("customfield_11526", " продуктовая КОМАНДА ", DC_FIELDS) == {
        "id": "customfield_11092", "name": "Продуктовая команда",
    }
    assert suggest_dc_field("customfield_1", "Продуктовая", DC_FIELDS) is None  # без частичных


def test_repeated_name_resolved_by_kind_of_field():
    assert suggest_dc_field("customfield_11731", "Окружение", DC_FIELDS)["id"] == "customfield_11018"
    assert suggest_dc_field("environment", "Окружение", DC_FIELDS)["id"] == "environment"
    assert suggest_dc_field("customfield_3", "Дубль", DC_FIELDS) is None


def test_system_field_without_known_name_matched_by_id():
    assert suggest_dc_field("duedate", None, DC_FIELDS) == {"id": "duedate", "name": "Срок исполнения"}
    assert suggest_dc_field("customfield_99", None, DC_FIELDS) is None


def test_rows_group_settings_by_cloud_field():
    snapshot = {
        "jira_team_field_id": "customfield_11526",
        "jira_impact_field_id": "priority",
        "jira_planned_dev_hours_field_id": json.dumps([
            {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
            {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
        ], ensure_ascii=False),
        "jira_planned_qa_hours_field_id": "customfield_14648",
        "jira_sprint_field_id": "customfield_10019",
        "jira_epic_link_field_id": "customfield_77777",
    }
    rows = {r["cloud_id"]: r for r in build_field_rows(snapshot, DC_FIELDS)}

    assert set(rows) == {
        "customfield_11526", "priority", "customfield_12432", "customfield_14648",
        "customfield_10019", "customfield_77777",
    }
    assert rows["customfield_14648"]["settings"] == [
        "jira_planned_dev_hours_field_id", "jira_planned_qa_hours_field_id",
    ]
    assert rows["customfield_14648"]["suggested_id"] == "customfield_11034"
    assert rows["customfield_12432"]["suggested_name"] == "Разработка (ч)"
    assert rows["customfield_11526"]["labels"] == ["Команда задачи"]
    assert rows["customfield_10019"]["auto_only"] is True
    assert rows["customfield_77777"]["auto_only"] is True
    assert rows["customfield_77777"]["suggested_id"] is None
    assert rows["customfield_11526"]["auto_only"] is False


def test_resolution_uses_decisions_then_suggestions():
    rows = [
        {"cloud_id": "customfield_11526", "suggested_id": "customfield_11092", "auto_only": False},
        {"cloud_id": "customfield_12434", "suggested_id": None, "auto_only": False},
        {"cloud_id": "customfield_14649", "suggested_id": None, "auto_only": False},
        {"cloud_id": "customfield_77777", "suggested_id": None, "auto_only": True},
        {"cloud_id": "customfield_12432", "suggested_id": "customfield_11097", "auto_only": False},
    ]
    decisions = {
        "customfield_14649": {"dc_field_id": None},
        "customfield_12432": {"dc_field_id": "customfield_11034"},
    }
    res = resolve_fields(rows, decisions, DC_FIELDS)

    assert res.mapping == {
        "customfield_11526": "customfield_11092",
        "customfield_12434": None,
        "customfield_14649": None,
        "customfield_77777": None,
        "customfield_12432": "customfield_11034",
    }
    assert res.unresolved == ["customfield_12434"]
    assert res.names["customfield_11092"] == "Продуктовая команда"


def test_rewrite_plain_json_and_not_used():
    mapping = {"customfield_11526": "customfield_11092", "customfield_12432": "customfield_11097",
               "customfield_14648": None}
    names = {"customfield_11092": "Продуктовая команда", "customfield_11097": "Разработка (ч)"}

    assert rewrite_setting_value("customfield_11526", mapping, names) == "customfield_11092"
    assert rewrite_setting_value("customfield_14648", mapping, names) == ""
    raw = json.dumps([
        {"field_id": "customfield_12432", "kind": "sum", "name": "Разработка"},
        {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
    ], ensure_ascii=False)
    assert json.loads(rewrite_setting_value(raw, mapping, names)) == [
        {"field_id": "customfield_11097", "kind": "sum", "name": "Разработка (ч)"},
    ]
    only_dropped = json.dumps([{"field_id": "customfield_14648", "kind": "alt", "name": "x"}])
    assert rewrite_setting_value(only_dropped, mapping, names) == ""


def test_plan_choice_stays_valid_after_remap():
    old = [Candidate("customfield_12432", "Разработка (ч)", 40.0),
           Candidate("customfield_14648", "Оценка 1С (ч)", 56.0)]
    sources = {"dev": [c.to_dict() for c in old]}
    choice = {"dev": {"source": "customfield_14648", "fingerprint": fingerprint(old)}}
    mapping = {"customfield_12432": "customfield_11097", "customfield_14648": "customfield_11034"}

    new_sources, new_choice = remap_plan_sources(sources, choice, mapping)

    assert [c["source"] for c in new_sources["dev"]] == ["customfield_11097", "customfield_11034"]
    assert new_choice["dev"]["source"] == "customfield_11034"
    candidates = [Candidate(c["source"], c["label"], c["value"]) for c in new_sources["dev"]]
    resolution = resolve_role(candidates, new_choice["dev"])
    assert resolution.disputed is False
    assert resolution.value == 56.0


def test_stale_choice_is_not_revived():
    old = [Candidate("customfield_12432", "А", 40.0), Candidate("customfield_14648", "Б", 56.0)]
    sources = {"dev": [c.to_dict() for c in old]}
    choice = {"dev": {"source": "customfield_14648", "fingerprint": "устарел"}}

    _, new_choice = remap_plan_sources(sources, choice, {"customfield_14648": "customfield_11034"})

    assert new_choice == {"dev": {"source": "customfield_11034", "fingerprint": "устарел"}}


def test_sum_and_manual_sources_untouched():
    sources = {"qa": [{"source": "sum", "label": "А + Б", "value": 10.0}]}
    choice = {"qa": {"source": "manual", "fingerprint": "x"}}
    new_sources, new_choice = remap_plan_sources(sources, choice, {"customfield_1": "customfield_2"})
    assert new_sources == sources
    assert new_choice == choice
    assert remap_plan_sources(None, None, {}) == (None, None)


def test_real_dc_fields_cover_known_cloud_names():
    dc_fields = [
        {"id": f["id"], "name": f["name"], "custom": bool(f.get("custom"))}
        for f in load_dc("fields.json")
    ]
    missing = {
        cid for cid, name in CLOUD_FIELD_NAMES.items()
        if suggest_dc_field(cid, name, dc_fields) is None
    }
    assert missing == {
        "customfield_12434", "customfield_12436", "customfield_12437",
        "customfield_12438", "customfield_12439", "customfield_14649",
    }
    assert suggest_dc_field("customfield_11526", "Продуктовая команда", dc_fields)["id"] == "customfield_11092"
    assert suggest_dc_field("customfield_11731", "Окружение", dc_fields)["id"] == "customfield_11018"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_fields.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration.cloud_fields'`.

- [ ] **Step 3: Cloud field names constant**

`app/services/jira_migration/cloud_fields.py` (35 значений сняты 2026-10-14 из облака в `data/cloud_field_names.json`; в «1С» буква «С» — кириллическая `С`):

```python
"""Названия полей облачной Jira (сняты 2026-10-14) по облачным номерам.

По точному названию для каждого облачного поля из настроек сервиса
предлагается поле новой Jira. Облако после переезда недоступно — поэтому
константа, а не запрос.
"""

CLOUD_FIELD_NAMES: dict[str, str] = {
    "customfield_11526": "Продуктовая команда",
    "customfield_11421": "Цели",
    "customfield_12434": "Пусконаладочные (ОПЭ) (ч)",
    "customfield_12437": "Вовлеченность разработчика (доля)",
    "customfield_12436": "Вовлеченность аналитика (доля)",
    "customfield_12438": "Вовлеченность тестировщика (доля)",
    "customfield_12439": "Вовлеченность аналитика и разработчика на запуск (доля)",
    "customfield_12446": "Длительность анализа, дн",
    "customfield_12443": "Длительность запуска, дн",
    "customfield_12441": "Длительность разработки, дн",
    "customfield_12442": "Длительность тестирования, дн",
    "priority": "Приоритет",
    "customfield_11464": "Заказчик (user)",
    "customfield_11506": "Тип затрат",
    "customfield_15156": "Оценка заказчика - скорость (1-5)",
    "customfield_15154": "Оценка заказчика - качество (1-5)",
    "customfield_15155": "Оценка заказчика - результат (1-5)",
    "customfield_13018": "Плановая дата начала",
    "customfield_13019": "Плановая дата окончания",
    "customfield_15258": "Цель задачи",
    "customfield_15223": "Описание текущего поведения",
    "customfield_10019": "Спринт",
    "customfield_11731": "Окружение",
    "customfield_16968": "Подтип",
    "customfield_12622": "C-Time",
    "customfield_11525": "Продуктовое направление",
    "customfield_12952": "DEV est (ч)",
    "customfield_14052": "Разработчик",
    "customfield_13052": "Участвующие команды",
    "customfield_12431": "Анализ (ч)",
    "customfield_14296": "Оценка SA/PM (ч)",
    "customfield_12433": "Тестирование (ч)",
    "customfield_14649": "Оценка QA 1С (ч)",
    "customfield_12432": "Разработка (ч)",
    "customfield_14648": "Оценка 1С (ч)",
}
```

- [ ] **Step 4: Fields module**

`app/services/jira_migration/fields.py`:

```python
"""Поля Jira при переезде: снимок облачных настроек, предложения, перезапись.

Номера полей в новой Jira другие. При первом пробном прогоне сохраняется
снимок облачных значений всех настроек полей — дальше он не меняется, даже
если администратор успел поправить настройки. Для каждого облачного поля
предлагается поле новой Jira с тем же названием; администратор подтверждает,
выбирает другое или ставит «не использовать». «Применить» переписывает
настройки из снимка по этому сопоставлению.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.services.jira_migration.cloud_fields import CLOUD_FIELD_NAMES
from app.services.plan_sources import Candidate, fingerprint, parse_field_setting

SNAPSHOT_KEY = "jira_migration_field_snapshot"
FIELD_SETTING_RE = re.compile(r"^jira_[a-z0-9_]+_field_id$")

# Настройки, которые сервис находит сам, если они пусты (синк — «Спринт»,
# «Ссылка на эпик», «Parent Link»; обновление бэклога — «Заказчик», «Тип
# затрат»). Без поля в новой Jira такие строки удаляются при применении.
AUTO_CACHE_KEYS = frozenset({
    "jira_sprint_field_id",
    "jira_customer_field_id",
    "jira_cost_type_field_id",
    "jira_epic_link_field_id",
    "jira_parent_link_field_id",
})

# Вовлечённость сервис из Jira больше не берёт: эти настройки нигде не читаются.
IGNORED_KEYS = frozenset({
    "jira_involvement_analyst_field_id",
    "jira_involvement_dev_field_id",
    "jira_involvement_qa_field_id",
    "jira_involvement_opo_field_id",
})

SETTING_LABELS: dict[str, str] = {
    "jira_team_field_id": "Команда задачи",
    "jira_participating_teams_field_id": "Участвующие команды",
    "jira_goals_field_id": "Цели (квартал)",
    "jira_goal_field_id": "Цель задачи",
    "jira_current_behavior_field_id": "Описание текущего поведения",
    "jira_planned_analyst_hours_field_id": "Плановые часы анализа",
    "jira_planned_dev_hours_field_id": "Плановые часы разработки",
    "jira_planned_qa_hours_field_id": "Плановые часы тестирования",
    "jira_planned_opo_hours_field_id": "Плановые часы ОПЭ",
    "jira_duration_analyst_field_id": "Длительность анализа",
    "jira_duration_dev_field_id": "Длительность разработки",
    "jira_duration_qa_field_id": "Длительность тестирования",
    "jira_duration_opo_field_id": "Длительность запуска",
    "jira_impact_field_id": "Влияние",
    "jira_risk_field_id": "Риск",
    "jira_rating_quality_field_id": "Оценка заказчика — качество",
    "jira_rating_speed_field_id": "Оценка заказчика — скорость",
    "jira_rating_result_field_id": "Оценка заказчика — результат",
    "jira_planned_start_date_field_id": "Плановая дата начала",
    "jira_planned_end_date_field_id": "Плановая дата окончания",
    "jira_environment_field_id": "Окружение",
    "jira_subtype_field_id": "Подтип",
    "jira_cost_type_field_id": "Тип затрат",
    "jira_cycle_time_field_id": "Фактический Cycle Time",
    "jira_direction_field_id": "Продуктовое направление",
    "jira_developer_field_id": "Разработчик",
    "jira_dev_est_field_id": "Оценка разработки (DEV est)",
    "jira_sprint_field_id": "Спринт",
    "jira_customer_field_id": "Заказчик",
    "jira_epic_link_field_id": "Ссылка на эпик",
    "jira_parent_link_field_id": "Ссылка на родителя (Parent Link)",
}
OTHER_LABEL = "Прочая настройка поля"


def read_field_settings(db: Session) -> dict[str, str]:
    """Текущие непустые значения настроек полей Jira (без неиспользуемых)."""
    out: dict[str, str] = {}
    rows = db.query(AppSetting.key, AppSetting.value).filter(AppSetting.key.startswith("jira_")).all()
    for key, value in rows:
        if not FIELD_SETTING_RE.match(key) or key in IGNORED_KEYS:
            continue
        if value and value.strip():
            out[key] = value.strip()
    return out


def load_field_snapshot(db: Session) -> dict[str, str]:
    raw = db.query(AppSetting.value).filter(AppSetting.key == SNAPSHOT_KEY).scalar()
    return json.loads(raw) if raw else {}


def ensure_field_snapshot(db: Session) -> dict[str, str]:
    """Снимок облачных значений: снимается при первом прогоне и дальше не меняется. Коммитит."""
    existing = load_field_snapshot(db)
    if existing:
        return existing
    snapshot = read_field_settings(db)
    row = db.query(AppSetting).filter(AppSetting.key == SNAPSHOT_KEY).first()
    value = json.dumps(snapshot, ensure_ascii=False)
    if row is None:
        db.add(AppSetting(key=SNAPSHOT_KEY, value=value))
    else:
        row.value = value
    db.commit()
    return snapshot


def field_ids_of(raw: Optional[str]) -> list[str]:
    """Номера полей в значении настройки: строка или JSON-список плановых часов."""
    return [spec.field_id for spec in parse_field_setting(raw)]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def suggest_dc_field(
    cloud_id: str,
    cloud_name: Optional[str],
    dc_fields: Sequence[Mapping[str, Any]],
) -> Optional[dict[str, str]]:
    """Поле новой Jira с тем же названием, что у облачного.

    Название сравнивается без учёта регистра и крайних пробелов, без
    частичных совпадений. Если одноимённых полей несколько, остаётся поле
    того же рода (своё против системного): «Окружение» есть и системное, и
    своё. Системное облачное поле без известного названия ищется по id.
    """
    if cloud_name:
        wanted = _norm(cloud_name)
        same = [f for f in dc_fields if _norm(f.get("name")) == wanted]
        if len(same) > 1:
            is_custom = cloud_id.startswith("customfield_")
            same = [f for f in same if bool(f.get("custom")) == is_custom]
        if len(same) == 1:
            found = same[0]
            return {"id": str(found["id"]), "name": str(found.get("name") or found["id"])}
        return None
    if not cloud_id.startswith("customfield_"):
        for found in dc_fields:
            if found.get("id") == cloud_id:
                return {"id": str(found["id"]), "name": str(found.get("name") or found["id"])}
    return None


def build_field_rows(
    snapshot: Mapping[str, str],
    dc_fields: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Строка отчёта на каждое облачное поле из снимка: где используется и что предложено."""
    settings_by_field: dict[str, list[str]] = {}
    for key in sorted(snapshot):
        for field_id in field_ids_of(snapshot[key]):
            settings_by_field.setdefault(field_id, []).append(key)
    rows: list[dict[str, Any]] = []
    for cloud_id, keys in settings_by_field.items():
        name = CLOUD_FIELD_NAMES.get(cloud_id)
        suggestion = suggest_dc_field(cloud_id, name, dc_fields)
        rows.append({
            "cloud_id": cloud_id,
            "cloud_name": name,
            "settings": keys,
            "labels": [SETTING_LABELS.get(key, OTHER_LABEL) for key in keys],
            "suggested_id": suggestion["id"] if suggestion else None,
            "suggested_name": suggestion["name"] if suggestion else None,
            "auto_only": all(key in AUTO_CACHE_KEYS for key in keys),
        })
    rows.sort(key=lambda r: (r["cloud_name"] or r["cloud_id"]).lower())
    return rows


@dataclass
class FieldResolution:
    """Итог сопоставления полей."""

    mapping: dict[str, Optional[str]]  # облачный id → id новой Jira; None — не использовать
    names: dict[str, str]              # id новой Jira → название
    unresolved: list[str]              # облачные id, по которым нужно решение


def resolve_fields(
    rows: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, Mapping[str, Any]],
    dc_fields: Sequence[Mapping[str, Any]],
) -> FieldResolution:
    """Решение администратора, иначе предложение по названию, иначе — нерешено.

    Поле, которое используется только автокэшами, нерешённым не считается:
    сервис найдёт его сам.
    """
    names = {str(f["id"]): str(f.get("name") or f["id"]) for f in dc_fields}
    mapping: dict[str, Optional[str]] = {}
    unresolved: list[str] = []
    for row in rows:
        cloud_id = row["cloud_id"]
        decision = decisions.get(cloud_id)
        if decision is not None:
            mapping[cloud_id] = decision.get("dc_field_id")
        elif row.get("suggested_id"):
            mapping[cloud_id] = row["suggested_id"]
        else:
            mapping[cloud_id] = None
            if not row.get("auto_only"):
                unresolved.append(cloud_id)
    return FieldResolution(mapping=mapping, names=names, unresolved=unresolved)


def rewrite_setting_value(
    raw: str,
    mapping: Mapping[str, Optional[str]],
    names: Mapping[str, str],
) -> str:
    """Значение настройки с полями новой Jira; поле «не использовать» выпадает.

    Пустая строка — настройка больше ни на что не указывает.
    """
    text = (raw or "").strip()
    if not text.startswith("["):
        new_id = mapping[text] if text in mapping else text
        return new_id or ""
    out: list[dict[str, str]] = []
    for spec in parse_field_setting(text):
        new_id = mapping[spec.field_id] if spec.field_id in mapping else spec.field_id
        if not new_id:
            continue
        out.append({
            "field_id": new_id,
            "kind": spec.kind,
            "name": names.get(new_id) or spec.name or new_id,
        })
    return json.dumps(out, ensure_ascii=False, separators=(",", ":")) if out else ""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def remap_plan_sources(
    sources: Optional[Mapping[str, Any]],
    choice: Optional[Mapping[str, Any]],
    mapping: Mapping[str, Optional[str]],
) -> tuple[Optional[dict], Optional[dict]]:
    """Кандидаты оценки и выбор при споре — с номерами полей новой Jira.

    Выбор, действовавший до переезда (его отпечаток совпадал с кандидатами),
    получает отпечаток пересчитанных кандидатов и остаётся действующим.
    Устаревший выбор не оживляется: его отпечаток не трогается. «sum» и
    «manual» — не номера полей, не меняются.
    """
    def new_source(source: Any) -> Any:
        if isinstance(source, str) and mapping.get(source):
            return mapping[source]
        return source

    old_by_role: dict[str, list[Candidate]] = {}
    new_by_role: dict[str, list[Candidate]] = {}
    new_sources: Optional[dict] = None
    if sources:
        new_sources = {}
        for role, items in sources.items():
            converted: list[Any] = []
            olds: list[Candidate] = []
            news: list[Candidate] = []
            for item in items or []:
                if not isinstance(item, Mapping):
                    converted.append(item)
                    continue
                source = item.get("source")
                label = item.get("label")
                target = new_source(source)
                new_label = target if label == source else label
                converted.append({**item, "source": target, "label": new_label})
                value = item.get("value")
                if isinstance(source, str) and _is_number(value):
                    olds.append(Candidate(source, str(label or source), float(value)))
                    news.append(Candidate(str(target), str(new_label or target), float(value)))
            new_sources[role] = converted
            old_by_role[role] = olds
            new_by_role[role] = news

    new_choice: Optional[dict] = None
    if choice:
        new_choice = {}
        for role, picked in choice.items():
            if not isinstance(picked, Mapping):
                new_choice[role] = picked
                continue
            updated = dict(picked)
            updated["source"] = new_source(picked.get("source"))
            olds = old_by_role.get(role)
            if olds and picked.get("fingerprint") == fingerprint(olds):
                updated["fingerprint"] = fingerprint(new_by_role[role])
            new_choice[role] = updated
    return new_sources, new_choice
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_fields.py -v`
Expected: PASS (12 tests).

Run: `ruff check app/services/jira_migration/cloud_fields.py app/services/jira_migration/fields.py tests/services/jira_migration/test_fields.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/cloud_fields.py app/services/jira_migration/fields.py tests/services/jira_migration/test_fields.py
git commit -m "feat(jira-migration): сопоставление полей по названию и перезапись настроек" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Тестовая Jira в памяти, отпечатки ворклогов, смещение часов, часы по командам

**Files:**
- Create: `tests/services/jira_migration/fake_jira.py`
- Create: `tests/services/jira_migration/factory.py`
- Create: `app/services/jira_migration/fingerprints.py`
- Create: `app/services/jira_migration/hours.py`
- Test: `tests/services/jira_migration/test_fingerprints_hours.py`

- [ ] **Step 1: Test helpers**

`tests/services/jira_migration/fake_jira.py`:

```python
"""Jira DC в памяти для тестов переезда: те же методы, что у JiraClient (план 1)."""
from __future__ import annotations

from typing import Any, AsyncIterator, Iterable, Optional

from app.connectors.schemas import (
    JiraProjectSchema,
    JiraSearchResponseSchema,
    JiraUserSchema,
    JiraWorklogSchema,
)


def dc_user(key: str, name: str, display_name: str, active: bool = True) -> JiraUserSchema:
    """Пользователь DC: ``key`` — идентичность, ``name`` — логин."""
    return JiraUserSchema.model_validate(
        {"key": key, "name": name, "displayName": display_name, "active": active}
    )


def dc_worklog(
    worklog_id: str,
    issue_id: str,
    author: JiraUserSchema,
    started_utc: str,
    seconds: int,
) -> JiraWorklogSchema:
    """Ворклог DC; ``started_utc`` — как шлёт DC, например ``2026-09-10T07:00:00.000+0000``."""
    return JiraWorklogSchema.model_validate({
        "id": worklog_id,
        "issueId": issue_id,
        "author": {
            "key": author.jira_account_id,
            "name": author.name,
            "displayName": author.display_name,
            "active": author.is_active,
        },
        "started": started_utc,
        "timeSpentSeconds": seconds,
    })


def _norm(value: Optional[str]) -> str:
    return " ".join((value or "").lower().replace("ё", "е").split())


class FakeJira:
    """``fail`` — имена методов, которые поднимают ошибку (сбой запроса к Jira)."""

    def __init__(
        self,
        *,
        projects: Optional[dict[str, str]] = None,
        issues: Optional[dict[str, list[tuple[str, str]]]] = None,
        worklogs: Optional[list[JiraWorklogSchema]] = None,
        users: Optional[list[JiraUserSchema]] = None,
        fields: Optional[list[dict]] = None,
        fail: Iterable[str] = (),
        field_options: Optional[list[str]] = None,
        statuses: Optional[list[dict]] = None,
    ) -> None:
        self.projects = projects or {}
        self.issues = issues or {}
        self.worklogs = worklogs or []
        self.users = users or []
        self.fields = fields if fields is not None else []
        self.fail = set(fail)
        self.field_options = field_options if field_options is not None else ["Команда А"]
        self.statuses = statuses if statuses is not None else [
            {"id": "1", "name": "Открыта", "statusCategory": {"key": "new"}},
        ]
        self.calls: list[tuple[str, Any]] = []

    async def __aenter__(self) -> "FakeJira":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def _call(self, name: str, arg: Any = None) -> None:
        self.calls.append((name, arg))
        if name in self.fail:
            raise RuntimeError(f"{name}: сервер недоступен")

    async def get_myself(self) -> JiraUserSchema:
        self._call("get_myself")
        return dc_user("JIRAUSER1", "admin_login", "Администратор")

    async def get_projects(self) -> list[JiraProjectSchema]:
        self._call("get_projects")
        return [JiraProjectSchema(id=pid, key=key, name=key) for key, pid in self.projects.items()]

    async def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
        fields: Optional[list[str]] = None,
        expand: Optional[str] = None,
    ) -> JiraSearchResponseSchema:
        self._call("search_issues", jql)
        return JiraSearchResponseSchema.model_validate(
            {"startAt": start_at, "maxResults": max_results, "total": 0, "issues": []}
        )

    async def iter_issue_keys(self, jql: str, page_size: int = 1000) -> AsyncIterator[tuple[str, str]]:
        self._call("iter_issue_keys", jql)
        project = jql.split('"')[1]
        for pair in self.issues.get(project, []):
            yield pair

    async def iter_worklogs_updated_since(self, since_ms: int) -> AsyncIterator[JiraWorklogSchema]:
        self._call("iter_worklogs_updated_since", since_ms)
        for worklog in self.worklogs:
            yield worklog

    async def get_fields(self) -> list[dict]:
        self._call("get_fields")
        return list(self.fields)

    async def get_statuses(self) -> list[dict]:
        self._call("get_statuses")
        return list(self.statuses)

    async def get_issue_changelog(self, issue_key: str) -> dict:
        self._call("get_issue_changelog", issue_key)
        return {"total": 0, "histories": []}

    async def get_field_configured_options(self, field_id: str) -> list[str]:
        self._call("get_field_configured_options", field_id)
        return list(self.field_options)

    async def search_users(self, query: str, max_results: int = 20) -> list[JiraUserSchema]:
        self._call("search_users", query)
        wanted = _norm(query)
        found = [u for u in self.users if wanted in _norm(u.display_name) or wanted in _norm(u.name)]
        return found[:max_results]
```

`tests/services/jira_migration/factory.py`:

```python
"""Данные для тестов переезда на Jira DC."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Employee, Issue, Project, Worklog
from app.services.jira_migration import store


def make_project(db: Session, key: str = "OS", jira_id: str = "11029") -> Project:
    project = Project(jira_project_id=jira_id, key=key, name=key)
    db.add(project)
    db.flush()
    return project


def make_issue(
    db: Session,
    project: Project,
    key: str,
    jira_id: str,
    team: Optional[str] = "Команда А",
    **extra: Any,
) -> Issue:
    issue = Issue(
        jira_issue_id=jira_id, key=key, summary=f"Задача {key}", issue_type="Task",
        status="Открыта", project_id=project.id, team=team, **extra,
    )
    db.add(issue)
    db.flush()
    return issue


def make_employee(db: Session, account_id: str, name: str) -> Employee:
    employee = Employee(jira_account_id=account_id, display_name=name)
    db.add(employee)
    db.flush()
    return employee


def make_worklog(
    db: Session, issue: Issue, employee: Employee, started: datetime, seconds: int, worklog_id: str,
) -> Worklog:
    worklog = Worklog(
        jira_worklog_id=worklog_id, started_at=started, hours=seconds / 3600,
        time_spent_seconds=seconds, issue_id=issue.id, employee_id=employee.id,
    )
    db.add(worklog)
    db.flush()
    return worklog


def seed_report(db: Session, report: dict, maps: dict, finished_at: datetime) -> str:
    """Успешный отчёт пробного прогона, законченный в ``finished_at``."""
    report_id = store.start_report(db, finished_at)
    store.finish_report(db, report_id, report, maps, finished_at)
    return report_id
```

- [ ] **Step 2: Write the failing tests**

`tests/services/jira_migration/test_fingerprints_hours.py`:

```python
"""Отпечатки ворклогов, смещение часов облака и часы по командам и месяцам."""
from datetime import datetime, timedelta, timezone

from app.services.jira_migration.fingerprints import (
    DbWorklog,
    DcWorklog,
    detect_offset,
    minute_of,
    scan_dc_worklogs,
)
from app.services.jira_migration.hours import (
    NO_TEAM,
    compare_hours,
    db_seconds,
    dc_seconds,
    load_db_worklogs,
    month_of_minute,
    post_check,
    to_hours,
)
from tests.services.jira_migration.factory import (
    make_employee,
    make_issue,
    make_project,
    make_worklog,
)
from tests.services.jira_migration.fake_jira import FakeJira, dc_user, dc_worklog

UTC = timezone.utc


def _db(key: str, wall: datetime, seconds: int = 3600, team: str | None = "Команда А") -> DbWorklog:
    return DbWorklog(key, minute_of(wall), seconds, "e1", team)


def _dc(key: str, utc: datetime, seconds: int = 3600) -> DcWorklog:
    return DcWorklog(key, minute_of(utc.replace(tzinfo=UTC)), seconds, "JIRAUSER1")


def test_minute_of_naive_and_aware():
    assert minute_of(datetime(1970, 1, 1, 0, 1, 59)) == 1
    msk = timezone(timedelta(hours=3))
    assert minute_of(datetime(1970, 1, 1, 3, 2, tzinfo=msk)) == 2


def test_detect_offset_finds_moscow_wall_clock():
    db_rows = [_db("OS-1", datetime(2026, 9, day, 10, 0)) for day in (10, 11, 12)]
    dc_rows = [_dc("OS-1", datetime(2026, 9, day, 7, 0)) for day in (10, 11, 12, 13)]

    offset, counts, sample = detect_offset(db_rows, dc_rows)

    assert offset == 3
    assert counts[3] == 3
    assert counts[0] == 0
    assert sample == 4


def test_detect_offset_without_matches_is_zero():
    offset, counts, sample = detect_offset(
        [_db("OS-1", datetime(2026, 9, 10, 10, 0))], [_dc("OS-2", datetime(2026, 9, 10, 7, 0))],
    )
    assert (offset, counts[0], sample) == (0, 0, 1)


def test_detect_offset_uses_sample():
    db_rows = [_db("OS-1", datetime(2026, 9, 10, 10, minute)) for minute in range(50)]
    dc_rows = [_dc("OS-1", datetime(2026, 9, 10, 7, minute)) for minute in range(50)]

    offset, counts, sample = detect_offset(db_rows, dc_rows, sample_limit=10)

    assert (offset, sample, counts[3]) == (3, 10, 10)


def test_month_of_minute():
    assert month_of_minute(minute_of(datetime(2026, 8, 31, 23, 59))) == "2026-08"


def test_hours_by_team_and_month_with_offset():
    db_rows = [
        _db("OS-1", datetime(2026, 9, 1, 2, 30), 1800),
        _db("OS-2", datetime(2026, 9, 10, 10, 0), 3600, team=None),
    ]
    dc_rows = [_dc("OS-1", datetime(2026, 8, 31, 23, 30), 1800), _dc("OS-2", datetime(2026, 9, 10, 7, 0))]
    team_by_key = {"OS-1": "Команда А", "OS-2": None}

    assert db_seconds(db_rows) == {("Команда А", "2026-09"): 1800, (NO_TEAM, "2026-09"): 3600}
    assert dc_seconds(dc_rows, team_by_key, 3) == {("Команда А", "2026-09"): 1800, (NO_TEAM, "2026-09"): 3600}
    assert dc_seconds(dc_rows, team_by_key, 0)[("Команда А", "2026-08")] == 1800
    assert to_hours({("А", "2026-09"): 5400}) == {("А", "2026-09"): 1.5}


def test_compare_flags_differences_over_one_percent():
    rows = compare_hours(
        {("А", "2026-09"): 100.0, ("Б", "2026-08"): 10.0, ("В", "2026-07"): 0.0},
        {("А", "2026-09"): 100.5, ("Б", "2026-08"): 12.0, ("В", "2026-07"): 1.0},
    )
    assert [(r["month"], r["team"], r["diff_pct"], r["flagged"]) for r in rows] == [
        ("2026-09", "А", 0.5, False),
        ("2026-08", "Б", 20.0, True),
        ("2026-07", "В", 100.0, True),
    ]


def test_load_db_worklogs(db_session):
    project = make_project(db_session)
    issue = make_issue(db_session, project, "OS-1", "1", team="Команда А")
    employee = make_employee(db_session, "acc-1", "Иванов Иван")
    employee_id = employee.id
    make_worklog(db_session, issue, employee, datetime(2026, 9, 10, 10, 0, 30), 3600, "w1")
    db_session.commit()

    assert load_db_worklogs(db_session) == [
        DbWorklog("OS-1", minute_of(datetime(2026, 9, 10, 10, 0)), 3600, employee_id, "Команда А"),
    ]


def test_post_check_compares_db_now_with_dc_from_report(db_session):
    project = make_project(db_session)
    issue = make_issue(db_session, project, "OS-1", "1", team="Команда А")
    employee = make_employee(db_session, "acc-1", "Иванов Иван")
    make_worklog(db_session, issue, employee, datetime(2026, 9, 10, 10, 0), 3600, "w1")
    db_session.commit()
    report = {"hours": {"dc_worklogs": 1, "rows": [
        {"team": "Команда А", "month": "2026-09", "db_hours": 0.0, "dc_hours": 1.0,
         "diff_pct": 100.0, "flagged": True},
    ]}}

    result = post_check(db_session, report, datetime(2026, 10, 15, 9, 0))

    assert result["checked_at"] == "2026-10-15T09:00:00Z"
    assert (result["db_worklogs"], result["dc_worklogs"]) == (1, 1)
    assert result["rows"] == [{"team": "Команда А", "month": "2026-09", "db_hours": 1.0,
                               "dc_hours": 1.0, "diff_pct": 0.0, "flagged": False}]


async def test_scan_keeps_rows_of_known_issues_and_all_authors():
    author = dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван")
    stranger = dc_user("JIRAUSER9", "Stranger", "Посторонний")
    fake = FakeJira(worklogs=[
        dc_worklog("1", "258783", author, "2026-09-10T07:00:00.000+0000", 3600),
        dc_worklog("2", "777", stranger, "2026-09-10T07:00:00.000+0000", 600),
    ])
    seen: list[int] = []

    scan = await scan_dc_worklogs(fake, {"258783": "OS-91030"}, on_progress=seen.append)

    assert scan.total == 2
    assert scan.rows == [
        DcWorklog("OS-91030", minute_of(datetime(2026, 9, 10, 7, 0, tzinfo=UTC)), 3600, "JIRAUSER5"),
    ]
    assert set(scan.authors) == {"JIRAUSER5", "JIRAUSER9"}
    assert scan.authors["JIRAUSER5"].name == "Ivanov_I"
    assert seen[-1] == 2
    assert fake.calls[0] == ("iter_worklogs_updated_since", 0)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_fingerprints_hours.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration.fingerprints'`.

- [ ] **Step 4: Fingerprints**

`app/services/jira_migration/fingerprints.py`:

```python
"""Отпечатки ворклогов и смещение «настенного» времени облака.

Отпечаток ворклога — (ключ задачи, начало до минуты, длительность в
секундах): id ворклогов при переезде сменились и пересекаются с чужими.
В базе начало хранится «настенным» временем облака (наивным), в новой Jira
— UTC; разница находится сама по максимуму совпадений.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

OFFSET_RANGE = range(-12, 15)
OFFSET_SAMPLE = 20000
PROGRESS_EVERY = 5000
_EPOCH = datetime(1970, 1, 1)


@dataclass(frozen=True, slots=True)
class DbWorklog:
    """Ворклог базы: ``minute`` — «настенное» время облака, как хранится."""

    key: str
    minute: int
    seconds: int
    employee_id: str
    team: Optional[str]


@dataclass(frozen=True, slots=True)
class DcWorklog:
    """Ворклог новой Jira: ``minute`` — UTC."""

    key: str
    minute: int
    seconds: int
    author_key: str


@dataclass(frozen=True, slots=True)
class DcUser:
    """Пользователь новой Jira: ``key`` — идентичность, ``name`` — логин."""

    key: str
    name: Optional[str]
    display_name: str

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name, "display_name": self.display_name}


@dataclass
class DcScan:
    rows: list[DcWorklog]          # только ворклоги задач, которые есть в базе
    authors: dict[str, DcUser]     # все авторы ворклогов новой Jira
    total: int                     # сколько ворклогов прочитано всего


def minute_of(dt: datetime) -> int:
    """Номер минуты от 1970-01-01. Время с поясом переводится в UTC, наивное берётся как есть."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return int((dt - _EPOCH).total_seconds() // 60)


def detect_offset(
    db_rows: Sequence[DbWorklog],
    dc_rows: Sequence[DcWorklog],
    sample_limit: int = OFFSET_SAMPLE,
) -> tuple[int, dict[int, int], int]:
    """Смещение (часы), с которым UTC новой Jira совпадает с временем базы.

    На равномерной выборке ворклогов новой Jira пробуются −12…+14 ч; берётся
    смещение с наибольшим числом совпадений (при равенстве — меньшее по
    модулю). Возвращает (смещение, совпадения по смещениям, размер выборки).
    """
    db_set = {(r.key, r.minute, r.seconds) for r in db_rows}
    step = max(1, len(dc_rows) // sample_limit) if sample_limit > 0 else 1
    sample = list(dc_rows[::step])[:sample_limit]
    counts = {hours: 0 for hours in OFFSET_RANGE}
    for row in sample:
        for hours in OFFSET_RANGE:
            if (row.key, row.minute + hours * 60, row.seconds) in db_set:
                counts[hours] += 1
    best = max(OFFSET_RANGE, key=lambda hours: (counts[hours], -abs(hours)))
    return best, counts, len(sample)


async def scan_dc_worklogs(
    jira: Any,
    id_to_key: Mapping[str, str],
    on_progress: Optional[Callable[[int], None]] = None,
) -> DcScan:
    """Все ворклоги новой Jira (``since=0``) потоком; в память — только нужное.

    Ворклог задачи, которой нет в базе, не сравнивается, но его автор
    запоминается: по авторам ищутся неактивные пользователи для ФИО.
    """
    rows: list[DcWorklog] = []
    authors: dict[str, DcUser] = {}
    total = 0
    async for worklog in jira.iter_worklogs_updated_since(0):
        total += 1
        author = worklog.author
        author_key = author.jira_account_id
        if author_key not in authors:
            authors[author_key] = DcUser(author_key, author.name, author.display_name)
        key = id_to_key.get(str(worklog.issueId))
        if key is not None:
            rows.append(DcWorklog(
                key, minute_of(worklog.started_datetime), int(worklog.timeSpentSeconds), author_key,
            ))
        if on_progress is not None and total % PROGRESS_EVERY == 0:
            on_progress(total)
    if on_progress is not None:
        on_progress(total)
    return DcScan(rows=rows, authors=authors, total=total)
```

- [ ] **Step 5: Hours**

`app/services/jira_migration/hours.py`:

```python
"""Часы по командам и месяцам: база сервиса против новой Jira.

Команда — ``issues.team`` задачи ворклога (пусто — «Без команды»), месяц —
по началу ворклога во времени базы (ворклог новой Jira сдвигается на
найденное смещение). Расхождение больше 1 % подсвечивается.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Issue, Worklog
from app.services.jira_migration.fingerprints import DbWorklog, DcWorklog, minute_of

NO_TEAM = "Без команды"
DIFF_THRESHOLD_PCT = 1.0
_EPOCH = datetime(1970, 1, 1)

TeamMonth = tuple[str, str]


def month_of_minute(minute: int) -> str:
    return (_EPOCH + timedelta(minutes=minute)).strftime("%Y-%m")


def _team(team: Optional[str]) -> str:
    return team or NO_TEAM


def load_db_worklogs(db: Session) -> list[DbWorklog]:
    """Все ворклоги базы с ключом и командой задачи."""
    query = (
        db.query(Issue.key, Worklog.started_at, Worklog.time_spent_seconds, Worklog.employee_id, Issue.team)
        .select_from(Worklog)
        .join(Issue, Issue.id == Worklog.issue_id)
        .yield_per(5000)
    )
    return [
        DbWorklog(key, minute_of(started), int(seconds or 0), employee_id, team)
        for key, started, seconds, employee_id, team in query
    ]


def db_seconds(rows: Iterable[DbWorklog]) -> dict[TeamMonth, int]:
    out: dict[TeamMonth, int] = defaultdict(int)
    for row in rows:
        out[(_team(row.team), month_of_minute(row.minute))] += row.seconds
    return dict(out)


def dc_seconds(
    rows: Iterable[DcWorklog],
    team_by_key: Mapping[str, Optional[str]],
    offset_hours: int,
) -> dict[TeamMonth, int]:
    shift = offset_hours * 60
    out: dict[TeamMonth, int] = defaultdict(int)
    for row in rows:
        out[(_team(team_by_key.get(row.key)), month_of_minute(row.minute + shift))] += row.seconds
    return dict(out)


def to_hours(seconds: Mapping[TeamMonth, int]) -> dict[TeamMonth, float]:
    return {key: round(value / 3600, 2) for key, value in seconds.items()}


def _diff_pct(base: float, other: float) -> float:
    if base == 0:
        return 0.0 if other == 0 else 100.0
    return round((other - base) / base * 100, 2)


def compare_hours(
    db_hours: Mapping[TeamMonth, float],
    dc_hours: Mapping[TeamMonth, float],
    threshold_pct: float = DIFF_THRESHOLD_PCT,
) -> list[dict[str, Any]]:
    """Строки (месяц по убыванию, команда): база, новая Jira, разница в % от базы."""
    keys = sorted(set(db_hours) | set(dc_hours), key=lambda k: k[0])
    keys.sort(key=lambda k: k[1], reverse=True)
    rows: list[dict[str, Any]] = []
    for team, month in keys:
        base = round(db_hours.get((team, month), 0.0), 2)
        other = round(dc_hours.get((team, month), 0.0), 2)
        diff = _diff_pct(base, other)
        rows.append({
            "team": team, "month": month, "db_hours": base, "dc_hours": other,
            "diff_pct": diff, "flagged": abs(diff) > threshold_pct,
        })
    return rows


def post_check(db: Session, report: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """Сверка после: часы базы сейчас против часов новой Jira из отчёта пробного прогона."""
    rows_now = load_db_worklogs(db)
    hours = report.get("hours") or {}
    dc_before = {(r["team"], r["month"]): float(r["dc_hours"]) for r in hours.get("rows", [])}
    return {
        "checked_at": now.replace(microsecond=0).isoformat() + "Z",
        "db_worklogs": len(rows_now),
        "dc_worklogs": int(hours.get("dc_worklogs", 0)),
        "rows": compare_hours(to_hours(db_seconds(rows_now)), dc_before),
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_fingerprints_hours.py -v`
Expected: PASS (10 tests).

Run: `ruff check app/services/jira_migration/fingerprints.py app/services/jira_migration/hours.py tests/services/jira_migration`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add tests/services/jira_migration/fake_jira.py tests/services/jira_migration/factory.py app/services/jira_migration/fingerprints.py app/services/jira_migration/hours.py tests/services/jira_migration/test_fingerprints_hours.py
git commit -m "feat(jira-migration): отпечатки ворклогов, смещение часов, часы по командам" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Сотрудники — голосование по списаниям, ФИО, «двое на одного»

**Files:**
- Create: `app/services/jira_migration/people.py`
- Test: `tests/services/jira_migration/test_people.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/jira_migration/test_people.py`:

```python
"""Сотрудники базы ↔ пользователи новой Jira: списания, ФИО, конфликт «двое на одного»."""
from collections import Counter
from datetime import datetime

from app.services.jira_migration.fingerprints import DbWorklog, DcUser, DcWorklog, minute_of
from app.services.jira_migration.people import (
    STATUS_BY_HOURS,
    STATUS_BY_NAME,
    STATUS_DISPUTED,
    STATUS_NOT_FOUND,
    build_people_rows,
    classify_votes,
    exact_name_matches,
    finalize_people,
    normalize_name,
    vote_people,
)
from tests.services.jira_migration.factory import make_employee
from tests.services.jira_migration.fake_jira import FakeJira, dc_user

WALL = datetime(2026, 9, 10, 10, 0)
U5 = {"key": "JIRAUSER5", "name": "Ivanov_I", "display_name": "Иванов Иван"}


def _db(key: str, employee: str, shift: int = 0) -> DbWorklog:
    return DbWorklog(key, minute_of(WALL) + shift, 3600, employee, "Команда А")


def _dc(key: str, author: str, shift: int = 0) -> DcWorklog:
    return DcWorklog(key, minute_of(WALL) - 180 + shift, 3600, author)


def _row(employee: str, status: str, auto: dict | None = None, votes: int = 0,
         name: str | None = None) -> dict:
    return {
        "employee_id": employee, "display_name": name or employee, "worklogs": votes,
        "matched": votes, "status": status,
        "candidates": [{**auto, "votes": votes}] if auto else [], "auto": auto,
    }


def test_normalize_name():
    assert normalize_name("  Пётр   ПЕТРОВ ") == "петр петров"
    assert normalize_name("Ёлкин Иван") == "елкин иван"
    assert normalize_name(None) == ""


def test_votes_use_offset_and_unique_fingerprints_only():
    db_rows = [
        _db("OS-1", "e1"), _db("OS-1", "e1", 60), _db("OS-2", "e1"),
        _db("OS-3", "e1"), _db("OS-3", "e2"),   # одинаковые списания двух людей — не голос
    ]
    dc_rows = [
        _dc("OS-1", "U1"), _dc("OS-1", "U1", 60), _dc("OS-2", "U2"),
        _dc("OS-3", "U1"), _dc("OS-3", "U3"),
    ]
    assert vote_people(db_rows, dc_rows, offset_hours=3) == {"e1": Counter({"U1": 2, "U2": 1})}
    assert vote_people(db_rows, dc_rows, offset_hours=0) == {}


def test_classify_votes_thresholds():
    assert classify_votes(Counter({"U1": 9, "U2": 1})) == (STATUS_BY_HOURS, "U1")
    assert classify_votes(Counter({"U1": 8, "U2": 2})) == (STATUS_DISPUTED, None)
    assert classify_votes(Counter({"U1": 2})) == (STATUS_DISPUTED, None)
    assert classify_votes(Counter({"U1": 3})) == (STATUS_BY_HOURS, "U1")
    assert classify_votes(Counter()) == (None, None)
    assert classify_votes(None) == (None, None)


def test_exact_name_matches_without_partial():
    users = [
        DcUser("K1", "a", "Иванов Иван"),
        DcUser("K2", "b", "Иванов Иван Михайлович"),
        DcUser("K1", "a", "Иванов Иван"),
    ]
    assert exact_name_matches("лебедев  александр", users) == [DcUser("K1", "a", "Иванов Иван")]
    assert exact_name_matches("", users) == []


async def test_people_rows_by_hours_name_and_not_found(db_session):
    employees = [
        make_employee(db_session, f"cloud-{i}", name)
        for i, name in enumerate(
            ["Иванов Иван", "Петров Пётр", "Иванов Иван", "Кузнецов Олег", "Сидоров Сидор"]
        )
    ]
    ids = {e.display_name: e.id for e in employees}
    db_session.commit()
    jira = FakeJira(users=[
        dc_user("JIRAUSER7", "Petrov_P", "петров петр"),
        dc_user("JIRAUSER11", "Novikov_A_A", "Иванов Иван"),
        dc_user("JIRAUSER12", "Novikov_A_M", "Иванов Иван"),
    ])
    authors = {
        "JIRAUSER5": DcUser("JIRAUSER5", "Ivanov_I", "Иванов Иван"),
        "JIRAUSER6": DcUser("JIRAUSER6", "Ivanov_Old", "Иванов Иван"),
        "JIRAUSER8": DcUser("JIRAUSER8", "Kuznetsov_O", "Кузнецов Олег"),
    }
    votes = {ids["Иванов Иван"]: Counter({"JIRAUSER5": 4})}
    seen: list[int] = []

    rows = await build_people_rows(
        db_session, jira, votes, authors, {ids["Иванов Иван"]: 4}, on_progress=seen.append,
    )
    by_name = {r["display_name"]: r for r in rows}

    assert by_name["Иванов Иван"]["status"] == STATUS_BY_HOURS
    assert by_name["Иванов Иван"]["auto"] == U5
    assert (by_name["Иванов Иван"]["matched"], by_name["Иванов Иван"]["worklogs"]) == (4, 4)
    assert by_name["Петров Пётр"]["status"] == STATUS_BY_NAME
    assert by_name["Петров Пётр"]["auto"]["key"] == "JIRAUSER7"
    assert by_name["Иванов Иван"]["status"] == STATUS_NOT_FOUND
    assert [c["key"] for c in by_name["Иванов Иван"]["candidates"]] == ["JIRAUSER11", "JIRAUSER12"]
    # неактивного нет в поиске, но он есть среди авторов списаний
    assert by_name["Кузнецов Олег"]["status"] == STATUS_BY_NAME
    assert by_name["Кузнецов Олег"]["auto"]["key"] == "JIRAUSER8"
    assert by_name["Сидоров Сидор"]["status"] == STATUS_NOT_FOUND
    assert by_name["Сидоров Сидор"]["candidates"] == []
    assert seen[-1] == 5


def test_finalize_auto_and_unresolved():
    rows = [_row("e1", STATUS_BY_HOURS, U5, 10), _row("e2", STATUS_DISPUTED), _row("e3", STATUS_NOT_FOUND)]
    out = finalize_people(rows, {})
    assert (out["e1"].key, out["e1"].source, out["e1"].unresolved) == ("JIRAUSER5", "auto", False)
    assert out["e2"].unresolved and out["e2"].key is None and out["e2"].note
    assert out["e3"].unresolved


def test_two_on_one_stronger_keeps_binding():
    rows = [_row("e1", STATUS_BY_HOURS, U5, 10, "Иванов Иван"),
            _row("e2", STATUS_BY_NAME, U5, 0, "Иванов И.")]
    out = finalize_people(rows, {})
    assert out["e1"].key == "JIRAUSER5" and not out["e1"].unresolved
    assert out["e2"].key is None and out["e2"].unresolved
    assert "Иванов Иван" in out["e2"].note


def test_two_on_one_tie_leaves_both_unresolved():
    out = finalize_people([_row("e1", STATUS_BY_NAME, U5), _row("e2", STATUS_BY_NAME, U5)], {})
    assert out["e1"].unresolved and out["e2"].unresolved
    assert out["e1"].key is None and out["e2"].key is None


def test_decision_wins_conflict_and_unbind_resolves():
    rows = [_row("e1", STATUS_BY_HOURS, U5, 10, "Иванов Иван"),
            _row("e2", STATUS_NOT_FOUND, name="Иванов Второй")]
    out = finalize_people(rows, {"e2": {"action": "bind", **U5}, "e1": {"action": "unbind"}})
    assert (out["e2"].key, out["e2"].source, out["e2"].unresolved) == ("JIRAUSER5", "decision", False)
    assert out["e1"].key is None and not out["e1"].unresolved


def test_decision_takes_user_from_auto_binding():
    rows = [_row("e1", STATUS_BY_HOURS, U5, 10, "Иванов Иван"),
            _row("e2", STATUS_NOT_FOUND, name="Иванов Второй")]
    out = finalize_people(rows, {"e2": {"action": "bind", **U5}})
    assert out["e2"].key == "JIRAUSER5" and not out["e2"].unresolved
    assert out["e1"].unresolved and out["e1"].key is None


def test_two_decisions_on_one_user_are_unresolved():
    rows = [_row("e1", STATUS_NOT_FOUND), _row("e2", STATUS_NOT_FOUND)]
    out = finalize_people(rows, {"e1": {"action": "bind", **U5}, "e2": {"action": "bind", **U5}})
    assert out["e1"].unresolved and out["e2"].unresolved


def test_outcome_to_dict():
    out = finalize_people([_row("e1", STATUS_BY_HOURS, U5, 10)], {})
    assert out["e1"].to_dict() == {
        "key": "JIRAUSER5", "name": "Ivanov_I", "display_name": "Иванов Иван",
        "source": "auto", "unresolved": False, "note": None,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_people.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration.people'`.

- [ ] **Step 3: People module**

`app/services/jira_migration/people.py`:

```python
"""Сопоставление сотрудников базы с пользователями новой Jira.

1. По списаниям: голосуют совпавшие ворклоги (отпечаток, единственный с
   обеих сторон). Лидер ≥ 90 % голосов и ≥ 3 совпадений — «по списаниям»;
   иначе при совпадениях — «спорно».
2. Без совпадений — по точному ФИО (регистр, ё→е, пробелы; без частичных):
   ровно один пользователь новой Jira — «по ФИО».
3. Иначе — «не найден»: решает администратор.
Почта ненадёжна (облачная почта одного человека в новой Jira — у другого),
поэтому не используется.
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models import Employee
from app.services.jira_migration.fingerprints import DbWorklog, DcUser, DcWorklog

logger = logging.getLogger(__name__)

LEADER_SHARE = 0.9
LEADER_MIN_VOTES = 3
TOP_CANDIDATES = 5
NAME_SEARCH_LIMIT = 50

STATUS_BY_HOURS = "by_hours"
STATUS_BY_NAME = "by_name"
STATUS_DISPUTED = "disputed"
STATUS_NOT_FOUND = "not_found"

SOURCE_AUTO = "auto"
SOURCE_DECISION = "decision"
SOURCE_NONE = "none"

_NOTE_BY_STATUS = {
    STATUS_DISPUTED: "Списания совпали с несколькими пользователями — выберите нужного",
    STATUS_NOT_FOUND: "Нет совпадений ни по списаниям, ни по ФИО — выберите пользователя "
                      "или оставьте без привязки",
}
NOTE_SHARED = "На одного пользователя новой Jira претендуют несколько сотрудников"


def normalize_name(value: Optional[str]) -> str:
    """ФИО для точного сравнения: регистр, ё→е, лишние пробелы."""
    return " ".join((value or "").lower().replace("ё", "е").split())


def vote_people(
    db_rows: Sequence[DbWorklog],
    dc_rows: Sequence[DcWorklog],
    offset_hours: int,
) -> dict[str, Counter]:
    """Голоса «сотрудник базы → автор в новой Jira» по совпавшим ворклогам.

    Считаются только отпечатки, единственные с обеих сторон: два одинаковых
    списания (тот же час той же задачи) не говорят, чьё из них чьё.
    """
    shift = offset_hours * 60
    db_by_fp: dict[tuple[str, int, int], list[str]] = {}
    for row in db_rows:
        db_by_fp.setdefault((row.key, row.minute, row.seconds), []).append(row.employee_id)
    dc_by_fp: dict[tuple[str, int, int], list[str]] = {}
    for row in dc_rows:
        dc_by_fp.setdefault((row.key, row.minute + shift, row.seconds), []).append(row.author_key)
    votes: dict[str, Counter] = {}
    for fp, employees in db_by_fp.items():
        authors = dc_by_fp.get(fp)
        if authors is None or len(employees) != 1 or len(authors) != 1:
            continue
        votes.setdefault(employees[0], Counter())[authors[0]] += 1
    return votes


def classify_votes(votes: Optional[Counter]) -> tuple[Optional[str], Optional[str]]:
    """(«по списаниям» | «спорно» | None, ключ лидера). None — совпадений нет."""
    if not votes:
        return None, None
    total = sum(votes.values())
    leader, count = max(votes.items(), key=lambda item: (item[1], item[0]))
    if count >= LEADER_MIN_VOTES and count / total >= LEADER_SHARE:
        return STATUS_BY_HOURS, leader
    return STATUS_DISPUTED, None


def exact_name_matches(display_name: Optional[str], candidates: Iterable[DcUser]) -> list[DcUser]:
    """Пользователи с тем же ФИО (после нормализации), без повторов, по ключу."""
    wanted = normalize_name(display_name)
    if not wanted:
        return []
    found: dict[str, DcUser] = {}
    for user in candidates:
        if normalize_name(user.display_name) == wanted and user.key not in found:
            found[user.key] = user
    return [found[key] for key in sorted(found)]


async def _search_by_name(jira: Any, display_name: str) -> list[DcUser]:
    if not normalize_name(display_name):
        return []
    try:
        users = await jira.search_users(display_name, max_results=NAME_SEARCH_LIMIT)
    except Exception:  # noqa: BLE001 — сбой поиска по одному человеку не роняет прогон
        logger.warning("Поиск пользователя новой Jira по ФИО не удался: %s", display_name, exc_info=True)
        return []
    return [DcUser(u.jira_account_id, u.name, u.display_name) for u in users]


def _candidate(user: DcUser, votes: int) -> dict[str, Any]:
    return {**user.to_dict(), "votes": votes}


async def build_people_rows(
    db: Session,
    jira: Any,
    votes: Mapping[str, Counter],
    authors: Mapping[str, DcUser],
    worklog_counts: Mapping[str, int],
    on_progress: Optional[Callable[[int], None]] = None,
) -> list[dict[str, Any]]:
    """Строка отчёта на каждого сотрудника базы.

    Кандидаты по ФИО — поиск пользователей новой Jira (только активные) и
    авторы ворклогов новой Jira (среди них и неактивные).
    """
    authors_by_name: dict[str, list[DcUser]] = {}
    for user in authors.values():
        authors_by_name.setdefault(normalize_name(user.display_name), []).append(user)
    employees = db.query(Employee.id, Employee.display_name).order_by(Employee.display_name).all()
    rows: list[dict[str, Any]] = []
    for index, (employee_id, display_name) in enumerate(employees, start=1):
        counter = votes.get(employee_id) or Counter()
        status, leader = classify_votes(counter)
        candidates = [
            _candidate(authors.get(key) or DcUser(key, None, key), count)
            for key, count in counter.most_common(TOP_CANDIDATES)
        ]
        auto: Optional[dict[str, Any]] = None
        if status == STATUS_BY_HOURS and leader is not None:
            auto = (authors.get(leader) or DcUser(leader, None, leader)).to_dict()
        elif status is None:
            found = await _search_by_name(jira, display_name)
            matches = exact_name_matches(
                display_name, [*found, *authors_by_name.get(normalize_name(display_name), [])],
            )
            if len(matches) == 1:
                status = STATUS_BY_NAME
                auto = matches[0].to_dict()
                candidates = [_candidate(matches[0], 0)]
            else:
                status = STATUS_NOT_FOUND
                candidates = [_candidate(user, 0) for user in matches]
        rows.append({
            "employee_id": employee_id,
            "display_name": display_name,
            "worklogs": int(worklog_counts.get(employee_id, 0)),
            "matched": sum(counter.values()),
            "status": status,
            "candidates": candidates,
            "auto": auto,
        })
        if on_progress is not None:
            on_progress(index)
    return rows


@dataclass(frozen=True)
class PersonOutcome:
    """Итоговая привязка сотрудника. ``key`` пуст — без привязки."""

    key: Optional[str]
    name: Optional[str]
    display_name: Optional[str]
    source: str
    unresolved: bool
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _conflict_winner(
    members: list[str],
    result: Mapping[str, PersonOutcome],
    strength: Mapping[str, int],
) -> Optional[str]:
    decided = [m for m in members if result[m].source == SOURCE_DECISION]
    if len(decided) == 1:
        return decided[0]
    if decided:
        return None
    best = max(strength.get(m, 0) for m in members)
    leaders = [m for m in members if strength.get(m, 0) == best]
    return leaders[0] if len(leaders) == 1 else None


def finalize_people(
    rows: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, Mapping[str, Any]],
) -> dict[str, PersonOutcome]:
    """Итоговая привязка каждого сотрудника с учётом решений администратора.

    Один пользователь новой Jira — не больше одного сотрудника. В конфликте
    «двое на одного» привязку сохраняет решение администратора, иначе
    сотрудник с большим числом совпавших списаний; остальным нужна другая
    привязка или «без привязки». Слияния сотрудников нет.
    """
    result: dict[str, PersonOutcome] = {}
    strength: dict[str, int] = {}
    names = {row["employee_id"]: row.get("display_name") for row in rows}
    for row in rows:
        employee_id = row["employee_id"]
        decision = decisions.get(employee_id)
        if decision is not None:
            if decision.get("action") == "bind":
                result[employee_id] = PersonOutcome(
                    decision["key"], decision.get("name"), decision.get("display_name"),
                    SOURCE_DECISION, False,
                )
            else:
                result[employee_id] = PersonOutcome(None, None, None, SOURCE_DECISION, False)
            continue
        auto = row.get("auto")
        if row.get("status") in (STATUS_BY_HOURS, STATUS_BY_NAME) and auto:
            result[employee_id] = PersonOutcome(
                auto["key"], auto.get("name"), auto.get("display_name"), SOURCE_AUTO, False,
            )
            strength[employee_id] = next(
                (c.get("votes", 0) for c in row.get("candidates", []) if c.get("key") == auto["key"]), 0,
            )
        else:
            result[employee_id] = PersonOutcome(
                None, None, None, SOURCE_NONE, True, _NOTE_BY_STATUS.get(row.get("status")),
            )

    by_key: dict[str, list[str]] = {}
    for employee_id, outcome in result.items():
        if outcome.key:
            by_key.setdefault(outcome.key, []).append(employee_id)
    for members in by_key.values():
        if len(members) < 2:
            continue
        winner = _conflict_winner(members, result, strength)
        for employee_id in members:
            if employee_id == winner:
                continue
            note = (
                f"Этот пользователь новой Jira уже привязан к сотруднику «{names.get(winner)}»"
                if winner is not None else NOTE_SHARED
            )
            result[employee_id] = PersonOutcome(None, None, None, result[employee_id].source, True, note)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_people.py -v`
Expected: PASS (12 tests).

Run: `ruff check app/services/jira_migration/people.py tests/services/jira_migration/test_people.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/people.py tests/services/jira_migration/test_people.py
git commit -m "feat(jira-migration): сопоставление сотрудников по списаниям и ФИО" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Задачи — новые id по ключам и служебные данные сервиса

**Files:**
- Create: `app/services/jira_migration/issues.py`
- Test: `tests/services/jira_migration/test_issues.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/jira_migration/test_issues.py`:

```python
"""Задачи при переезде: служебные данные сервиса и новые id по ключам."""
from datetime import datetime

from app.models import (
    BacklogItem,
    CategoryOverride,
    IssueClassification,
    MandatoryWorkType,
    PlanAudit,
    PlanningScenario,
    ProjectAISummary,
    ScenarioAllocationSnapshot,
    ScenarioRevision,
    ScopeProject,
    ScopeRoot,
    Team,
    TeamDeskDailyRate,
    TeamDeskMark,
    TeamSubgroup,
)
from app.services.jira_migration.issues import (
    REASON_BACKLOG,
    REASON_CATEGORY_OVERRIDE,
    REASON_CLASSIFICATION,
    REASON_DAILY_RATE,
    REASON_HOURS_CHOICE,
    REASON_MANUAL_CATEGORY,
    REASON_MANUAL_HOURS,
    REASON_MANUAL_SUBGROUP,
    REASON_PLAN_AUDIT,
    REASON_SCENARIO,
    REASON_SCOPE_ROOT,
    REASON_TEAM_DESK_MARK,
    classify_missing,
    scan_issue_ids,
    service_data_reasons,
)
from tests.services.jira_migration.factory import make_issue, make_project
from tests.services.jira_migration.fake_jira import FakeJira

NOW = datetime(2026, 10, 14, 12, 0)


def _work_type(db):
    work_type = MandatoryWorkType(code="migration_test_wt", label="Тестовый вид работ")
    db.add(work_type)
    db.flush()
    return work_type


def test_defaults_and_automatic_rows_are_not_service_data(db_session):
    project = make_project(db_session)
    issue = make_issue(db_session, project, "OS-1", "1",
                       include_in_analysis=False, category_verified=False, parent_changed=True)
    work_type = _work_type(db_session)
    db_session.add_all([
        IssueClassification(issue_id=issue.id, work_type_id=work_type.id, input_hash="h",
                            dictionary_version=1, prompt_version="v3"),
        PlanAudit(issue_id=issue.id, role="dev", source="jira_sync", value_after=5.0),
        PlanAudit(issue_id=issue.id, role="dev", source="jira_sync_conflict", value_after=6.0),
        ProjectAISummary(issue_id=issue.id, goals_json="[]", result_checklist_json="[]",
                         status_text="", workload_summary="", generated_at=NOW, model_used="m"),
    ])
    db_session.commit()

    assert service_data_reasons(db_session, ["OS-1"]) == {}


def test_each_kind_of_service_data_is_found(db_session):
    project = make_project(db_session)
    keys = [f"OS-{n}" for n in range(1, 13)]
    issues = {key: make_issue(db_session, project, key, str(100 + n)) for n, key in enumerate(keys)}
    work_type = _work_type(db_session)
    team = Team(name="Команда для группы")
    db_session.add(team)
    db_session.flush()
    subgroup = TeamSubgroup(team_id=team.id, name="Группа 1")
    scenario = PlanningScenario(name="Q3", status="approved")
    db_session.add_all([subgroup, scenario])
    db_session.flush()
    revision = ScenarioRevision(scenario_id=scenario.id, revision_number=1, approved_at=NOW)
    db_session.add(revision)
    db_session.flush()
    db_session.add_all([
        BacklogItem(title="Идея", issue_id=issues["OS-1"].id),
        IssueClassification(issue_id=issues["OS-2"].id, work_type_id=work_type.id, input_hash="manual",
                            dictionary_version=1, prompt_version="manual"),
        PlanAudit(issue_id=issues["OS-3"].id, role="dev", source="manual_edit", value_after=8.0),
        TeamDeskMark(issue_id=issues["OS-4"].id, flag="stale", signature="s"),
        TeamDeskDailyRate(issue_id=issues["OS-5"].id, hours=2.0),
        ScenarioAllocationSnapshot(revision_id=revision.id, title="Инициатива", issue_id=issues["OS-6"].id),
        CategoryOverride(jira_issue_key="OS-7", category_code="dev"),
        ScopeRoot(category_code="dev", jira_issue_key="OS-8"),
    ])
    issues["OS-9"].assigned_category = "dev"
    issues["OS-10"].assigned_subgroup_id = subgroup.id
    issues["OS-11"].planned_qa_hours_manual = 12.0
    issues["OS-12"].planned_hours_choice = {"dev": {"source": "manual", "fingerprint": "x"}}
    db_session.commit()

    assert service_data_reasons(db_session, keys) == {
        "OS-1": [REASON_BACKLOG],
        "OS-2": [REASON_CLASSIFICATION],
        "OS-3": [REASON_PLAN_AUDIT],
        "OS-4": [REASON_TEAM_DESK_MARK],
        "OS-5": [REASON_DAILY_RATE],
        "OS-6": [REASON_SCENARIO],
        "OS-7": [REASON_CATEGORY_OVERRIDE],
        "OS-8": [REASON_SCOPE_ROOT],
        "OS-9": [REASON_MANUAL_CATEGORY],
        "OS-10": [REASON_MANUAL_SUBGROUP],
        "OS-11": [REASON_MANUAL_HOURS],
        "OS-12": [REASON_HOURS_CHOICE],
    }


def test_classify_missing_splits_and_gives_summaries(db_session):
    project = make_project(db_session)
    with_data = make_issue(db_session, project, "OS-1", "1")
    make_issue(db_session, project, "OS-2", "2")
    db_session.add(BacklogItem(title="Идея", issue_id=with_data.id))
    db_session.commit()

    deletable, rows = classify_missing(db_session, ["OS-1", "OS-2"])

    assert deletable == ["OS-2"]
    assert rows == [{"key": "OS-1", "summary": "Задача OS-1", "reasons": [REASON_BACKLOG]}]


async def test_scan_maps_db_keys_and_counts(db_session):
    os_project = make_project(db_session, "OS", "11029")
    pmd = make_project(db_session, "PMD", "11015")
    make_project(db_session, "OLD", "11999")
    gone = make_project(db_session, "GONE", "12000")
    make_issue(db_session, os_project, "OS-91030", "683676")
    make_issue(db_session, os_project, "OS-1", "500001")
    make_issue(db_session, pmd, "PMD-19591", "258783")
    make_issue(db_session, gone, "GONE-1", "600001")
    db_session.add(ScopeProject(jira_project_key="OS", jira_project_id="11029"))
    db_session.commit()
    dc_projects = {"OS": "10901", "PMD": "10902", "OLD": "10903"}
    jira = FakeJira(projects=dc_projects, issues={
        "OS": [("OS-91030", "258783"), ("OS-5", "300005")],
        "PMD": [("PMD-19591", "999999"), ("PMD-2", "999998")],
    })
    seen: list[int] = []

    scan = await scan_issue_ids(db_session, jira, dc_projects, on_progress=seen.append)

    assert scan.key_to_id == {"OS-91030": "258783", "PMD-19591": "999999"}
    assert (scan.db_total, scan.matched, scan.new_in_dc) == (4, 2, 1)
    assert scan.missing == ["GONE-1", "OS-1"]
    assert scan.projects == [
        {"key": "GONE", "found": False}, {"key": "OLD", "found": True},
        {"key": "OS", "found": True}, {"key": "PMD", "found": True},
    ]
    assert [c for c in jira.calls if c[0] == "iter_issue_keys"] == [
        ("iter_issue_keys", 'project = "OS"'), ("iter_issue_keys", 'project = "PMD"'),
    ]
    assert seen[-1] == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_issues.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration.issues'`.

- [ ] **Step 3: Issues module**

`app/services/jira_migration/issues.py`:

```python
"""Задачи при переезде: новые id по ключам и задачи, которых нет в новой Jira.

Ключи задач при переезде сохранились, внутренние id — нет. Задача, которой
нет в новой Jira, без служебных данных сервиса удаляется при применении;
со служебными данными — решает администратор.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models import (
    BacklogItem,
    CategoryOverride,
    Issue,
    IssueClassification,
    PlanAudit,
    Project,
    ScenarioAllocationSnapshot,
    ScopeProject,
    ScopeRoot,
    TeamDeskDailyRate,
    TeamDeskMark,
)

CHUNK = 500
PROGRESS_EVERY = 5000
MANUAL_CLASSIFICATION = "manual"
HUMAN_PLAN_AUDIT_SOURCES = (
    "manual_edit", "manual_revert", "conflict_accepted", "conflict_ignored", "dispute_choice",
)

REASON_BACKLOG = "В бэклоге"
REASON_CLASSIFICATION = "Ручная классификация вида работ"
REASON_PLAN_AUDIT = "Правки плановых часов"
REASON_TEAM_DESK_MARK = "Отметки на столе тимлида"
REASON_DAILY_RATE = "Дневная норма на столе тимлида"
REASON_SCENARIO = "В утверждённом сценарии"
REASON_CATEGORY_OVERRIDE = "Исключение категории"
REASON_SCOPE_ROOT = "Корень категории"
REASON_MANUAL_CATEGORY = "Категория задана вручную"
REASON_MANUAL_SUBGROUP = "Группа задана вручную"
REASON_MANUAL_HOURS = "Плановые часы заданы вручную"
REASON_HOURS_CHOICE = "Выбрана оценка в споре"


def chunks(items: Sequence[Any], size: int = CHUNK) -> Iterator[Sequence[Any]]:
    """Порции для ``IN (...)``: SQLite ограничивает число параметров запроса."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


def service_data_reasons(db: Session, keys: Sequence[str]) -> dict[str, list[str]]:
    """Служебные данные сервиса по задачам: ``{ключ: [что есть]}``, задачи без данных не попадают.

    Служебные — только то, что завёл человек. Не служебные: значения по
    умолчанию и пометки сервиса (включена в анализ, подтверждена, сменился
    родитель), кэш саммари ИИ, классификация вида работ моделью, записи
    истории оценок от синка — всё это восстанавливается или теряет смысл
    вместе с задачей.
    """
    reasons: dict[str, list[str]] = {}

    def add(key: str, reason: str) -> None:
        bucket = reasons.setdefault(key, [])
        if reason not in bucket:
            bucket.append(reason)

    unique_keys = list(dict.fromkeys(keys))
    for chunk in chunks(unique_keys):
        rows = (
            db.query(
                Issue.id, Issue.key, Issue.assigned_category, Issue.assigned_subgroup_id,
                Issue.planned_analyst_hours_manual, Issue.planned_dev_hours_manual,
                Issue.planned_qa_hours_manual, Issue.planned_opo_hours_manual,
                Issue.planned_hours_choice,
            )
            .filter(Issue.key.in_(chunk))
            .all()
        )
        key_by_id: dict[str, str] = {}
        for row in rows:
            key_by_id[row.id] = row.key
            if row.assigned_category:
                add(row.key, REASON_MANUAL_CATEGORY)
            if row.assigned_subgroup_id:
                add(row.key, REASON_MANUAL_SUBGROUP)
            manual_hours = (
                row.planned_analyst_hours_manual, row.planned_dev_hours_manual,
                row.planned_qa_hours_manual, row.planned_opo_hours_manual,
            )
            if any(value is not None for value in manual_hours):
                add(row.key, REASON_MANUAL_HOURS)
            if row.planned_hours_choice:
                add(row.key, REASON_HOURS_CHOICE)
        ids = list(key_by_id)
        if ids:
            checks = (
                (BacklogItem.issue_id, REASON_BACKLOG, None),
                (IssueClassification.issue_id, REASON_CLASSIFICATION,
                 IssueClassification.prompt_version == MANUAL_CLASSIFICATION),
                (PlanAudit.issue_id, REASON_PLAN_AUDIT, PlanAudit.source.in_(HUMAN_PLAN_AUDIT_SOURCES)),
                (TeamDeskMark.issue_id, REASON_TEAM_DESK_MARK, None),
                (TeamDeskDailyRate.issue_id, REASON_DAILY_RATE, None),
                (ScenarioAllocationSnapshot.issue_id, REASON_SCENARIO, None),
            )
            for column, reason, condition in checks:
                query = db.query(column).filter(column.in_(ids))
                if condition is not None:
                    query = query.filter(condition)
                for (issue_id,) in query.distinct().all():
                    add(key_by_id[issue_id], reason)
        for (key,) in db.query(CategoryOverride.jira_issue_key).filter(
            CategoryOverride.jira_issue_key.in_(chunk)
        ).all():
            add(key, REASON_CATEGORY_OVERRIDE)
        for (key,) in db.query(ScopeRoot.jira_issue_key).filter(
            ScopeRoot.jira_issue_key.in_(chunk)
        ).distinct().all():
            add(key, REASON_SCOPE_ROOT)
    return reasons


def classify_missing(db: Session, missing_keys: Sequence[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """Задачи, которых нет в новой Jira: (удаляются сами, нужны решения ``[{key, summary, reasons}]``)."""
    reasons = service_data_reasons(db, missing_keys)
    with_data_keys = [key for key in missing_keys if key in reasons]
    summaries: dict[str, str] = {}
    for chunk in chunks(with_data_keys):
        summaries.update(dict(db.query(Issue.key, Issue.summary).filter(Issue.key.in_(chunk)).all()))
    deletable = [key for key in missing_keys if key not in reasons]
    with_data = [
        {"key": key, "summary": summaries.get(key, ""), "reasons": reasons[key]} for key in with_data_keys
    ]
    return deletable, with_data


@dataclass
class IssueScan:
    key_to_id: dict[str, str]   # ключ задачи базы → id в новой Jira
    db_total: int
    matched: int
    new_in_dc: int              # новые задачи проектов из scope — придут синком
    missing: list[str]          # ключи базы, которых нет в новой Jira
    projects: list[dict[str, Any]]


async def scan_issue_ids(
    db: Session,
    jira: Any,
    dc_project_ids: Mapping[str, str],
    on_progress: Optional[Callable[[int], None]] = None,
) -> IssueScan:
    """Пары (ключ, id) новой Jira по проектам задач базы и проектам из scope."""
    db_keys_by_project: dict[str, set[str]] = {}
    for key, project_key in db.query(Issue.key, Project.key).join(Project, Project.id == Issue.project_id).all():
        db_keys_by_project.setdefault(project_key, set()).add(key)
    scope = {
        key for (key,) in db.query(ScopeProject.jira_project_key)
        .filter(ScopeProject.is_enabled.is_(True)).all()
    }
    all_ids: dict[str, str] = {}
    read = 0
    for project_key in sorted(set(db_keys_by_project) | scope):
        if project_key not in dc_project_ids:
            continue
        async for key, issue_id in jira.iter_issue_keys(f'project = "{project_key}"'):
            all_ids[key] = str(issue_id)
            read += 1
            if on_progress is not None and read % PROGRESS_EVERY == 0:
                on_progress(read)
    if on_progress is not None:
        on_progress(read)
    db_keys: set[str] = set().union(*db_keys_by_project.values()) if db_keys_by_project else set()
    key_to_id = {key: all_ids[key] for key in db_keys if key in all_ids}
    new_in_dc = sum(1 for key in all_ids if key not in db_keys and key.rsplit("-", 1)[0] in scope)
    project_keys = {key for (key,) in db.query(Project.key).all()} | scope
    return IssueScan(
        key_to_id=key_to_id,
        db_total=len(db_keys),
        matched=len(key_to_id),
        new_in_dc=new_in_dc,
        missing=sorted(db_keys - set(all_ids)),
        projects=[{"key": key, "found": key in dc_project_ids} for key in sorted(project_keys)],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_issues.py -v`
Expected: PASS (4 tests).

Run: `ruff check app/services/jira_migration/issues.py tests/services/jira_migration/test_issues.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/issues.py tests/services/jira_migration/test_issues.py
git commit -m "feat(jira-migration): задачи по ключам и служебные данные сервиса" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Проверка возможностей новой Jira

**Files:**
- Create: `app/services/jira_migration/probe.py`
- Test: `tests/services/jira_migration/test_probe.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/jira_migration/test_probe.py`:

```python
"""Проверка возможностей новой Jira: каждый нужный синку запрос вызван хотя бы раз."""
from datetime import datetime, timezone
from unittest.mock import patch

from app.models import AppSetting
from app.services.jira_migration.probe import essential_failures, run_probe
from tests.services.jira_migration.fake_jira import FakeJira, dc_user, dc_worklog

NOW = datetime(2026, 10, 14, 12, 0)
WORKLOG = dc_worklog("1", "258783", dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван"),
                     "2026-10-10T07:00:00.000+0000", 3600)


async def _probe(db, jira, team_field_id="customfield_11092"):
    return await run_probe(db, jira, sample_project="OS", sample_issue_key="OS-1",
                           team_field_id=team_field_id, now=NOW)


async def test_all_checks_pass(db_session):
    jira = FakeJira(worklogs=[WORKLOG])
    results = await _probe(db_session, jira)

    assert [r.code for r in results] == [
        "myself", "projects", "search", "fields", "statuses", "worklogs",
        "changelog", "team_options", "users",
    ]
    assert all(r.ok for r in results)
    assert essential_failures(results) == []
    since_ms = int(datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert ("iter_worklogs_updated_since", since_ms) in jira.calls
    assert ("get_issue_changelog", "OS-1") in jira.calls
    assert ("search_users", "admin_login") in jira.calls


async def test_essential_failure_is_listed(db_session):
    results = await _probe(db_session, FakeJira(worklogs=[WORKLOG], fail={"get_fields"}))
    failed = essential_failures(results)
    assert [r.code for r in failed] == ["fields"]
    assert "сервер недоступен" in failed[0].detail


async def test_optional_failures_do_not_block(db_session):
    results = await _probe(db_session, FakeJira(worklogs=[WORKLOG], fail={"get_statuses", "search_users"}))
    assert essential_failures(results) == []
    assert {r.code for r in results if not r.ok} == {"statuses", "users"}


async def test_team_options_empty_or_unmapped_is_warning(db_session):
    results = await _probe(db_session, FakeJira(worklogs=[WORKLOG], field_options=[]))
    team = next(r for r in results if r.code == "team_options")
    assert (team.ok, team.essential) == (False, False)

    results = await _probe(db_session, FakeJira(worklogs=[WORKLOG]), team_field_id=None)
    team = next(r for r in results if r.code == "team_options")
    assert team.ok is False and "не сопоставлено" in team.detail


async def test_worklogs_without_recent_data_still_ok(db_session):
    results = await _probe(db_session, FakeJira())
    worklogs = next(r for r in results if r.code == "worklogs")
    assert worklogs.ok and "не проверено" in worklogs.detail


async def test_confluence_checked_when_configured(db_session):
    db_session.add(AppSetting(key="confluence_base_url", value="https://confluence.example.test"))
    db_session.commit()

    class FakeConfluence:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_current_user(self):
            return {"displayName": "Администратор"}

    with patch("app.connectors.confluence_client.ConfluenceClient.from_db", return_value=FakeConfluence()):
        results = await _probe(db_session, FakeJira(worklogs=[WORKLOG]))

    confluence = next(r for r in results if r.code == "confluence")
    assert confluence.ok and "Администратор" in confluence.detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_probe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration.probe'`.

- [ ] **Step 3: Probe module**

`app/services/jira_migration/probe.py`:

```python
"""Проверка возможностей новой Jira: каждый запрос, нужный синку, вызван хотя бы раз.

Обязательные (без них отчёт не строится и применить нельзя): список
проектов, поиск задач, список полей, ворклоги (изменённые + содержимое).
Остальные сбои — предупреждения в отчёте.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AppSetting

SEARCH_FIELDS = ["summary", "issuetype", "status", "project"]
WORKLOG_WINDOW = timedelta(days=30)


@dataclass
class ProbeResult:
    code: str
    title: str
    essential: bool
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _describe(exc: Exception) -> str:
    text = str(exc).strip()
    return text[:300] if text else exc.__class__.__name__


async def _check(
    results: list[ProbeResult],
    code: str,
    title: str,
    essential: bool,
    action: Callable[[], Awaitable[str]],
) -> None:
    try:
        detail = await action()
        results.append(ProbeResult(code, title, essential, True, detail or ""))
    except Exception as exc:  # noqa: BLE001 — любой сбой запроса попадает в отчёт
        results.append(ProbeResult(code, title, essential, False, _describe(exc)))


async def run_probe(
    db: Session,
    jira: Any,
    *,
    sample_project: Optional[str],
    sample_issue_key: Optional[str],
    team_field_id: Optional[str],
    now: datetime,
) -> list[ProbeResult]:
    """Вызвать каждый используемый синком запрос новой Jira; ошибки — в результат."""
    results: list[ProbeResult] = []
    login: dict[str, Optional[str]] = {"name": None}

    async def myself() -> str:
        user = await jira.get_myself()
        login["name"] = user.name
        return f"Вход выполнен: {user.display_name}"

    async def projects() -> str:
        return f"Проектов: {len(await jira.get_projects())}"

    async def search() -> str:
        jql = f'project = "{sample_project}"' if sample_project else "order by created DESC"
        page = await jira.search_issues(jql, max_results=1, fields=SEARCH_FIELDS, expand="changelog")
        return f"Задач по запросу: {page.total}"

    async def fields() -> str:
        return f"Полей: {len(await jira.get_fields())}"

    async def statuses() -> str:
        return f"Статусов: {len(await jira.get_statuses())}"

    async def worklogs() -> str:
        since_ms = int((now - WORKLOG_WINDOW).replace(tzinfo=timezone.utc).timestamp() * 1000)
        stream = jira.iter_worklogs_updated_since(since_ms)
        try:
            async for _worklog in stream:
                return "Списания читаются"
        finally:
            await stream.aclose()
        return "За последние 30 дней списаний нет — содержимое не проверено"

    async def changelog() -> str:
        if not sample_issue_key:
            return "Нет задачи для проверки"
        data = await jira.get_issue_changelog(sample_issue_key)
        return f"Записей истории: {len(data.get('histories') or [])}"

    async def users() -> str:
        found = await jira.search_users(login["name"] or "a", max_results=5)
        return f"Найдено пользователей: {len(found)}"

    await _check(results, "myself", "Вход по токену", False, myself)
    await _check(results, "projects", "Список проектов", True, projects)
    await _check(results, "search", "Поиск задач", True, search)
    await _check(results, "fields", "Список полей", True, fields)
    await _check(results, "statuses", "Справочник статусов", False, statuses)
    await _check(results, "worklogs", "Списания: изменённые и их содержимое", True, worklogs)
    await _check(results, "changelog", "История изменений задачи", False, changelog)

    # Клиент сам глотает ошибку запроса значений и отдаёт пустой список.
    team_title = "Значения поля команды"
    if not team_field_id:
        results.append(ProbeResult("team_options", team_title, False, False, "Поле команды не сопоставлено"))
    else:
        try:
            options = await jira.get_field_configured_options(team_field_id)
            if options:
                results.append(ProbeResult("team_options", team_title, False, True, f"Значений: {len(options)}"))
            else:
                results.append(ProbeResult(
                    "team_options", team_title, False, False,
                    "Список значений не получен — сервис возьмёт команды из задач",
                ))
        except Exception as exc:  # noqa: BLE001
            results.append(ProbeResult("team_options", team_title, False, False, _describe(exc)))

    await _check(results, "users", "Поиск пользователей", False, users)

    confluence_url = db.query(AppSetting.value).filter(AppSetting.key == "confluence_base_url").scalar()
    if confluence_url and confluence_url.strip():
        async def confluence() -> str:
            from app.connectors.confluence_client import ConfluenceClient

            async with ConfluenceClient.from_db(db) as client:
                user = await client.get_current_user()
            return f"Вход выполнен: {user.get('displayName') or user.get('username') or ''}".strip()

        await _check(results, "confluence", "Confluence", False, confluence)
    return results


def essential_failures(results: list[ProbeResult]) -> list[ProbeResult]:
    return [r for r in results if r.essential and not r.ok]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_probe.py -v`
Expected: PASS (6 tests).

Run: `ruff check app/services/jira_migration/probe.py tests/services/jira_migration/test_probe.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/probe.py tests/services/jira_migration/test_probe.py
git commit -m "feat(jira-migration): проверка возможностей новой Jira" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Пробный прогон — сборка отчёта

**Files:**
- Create: `app/services/jira_migration/dry_run.py`
- Create: `tests/services/jira_migration/world.py`
- Test: `tests/services/jira_migration/test_dry_run.py`

- [ ] **Step 1: Test world**

`tests/services/jira_migration/world.py`:

```python
"""Мир для пробного прогона: база с облачными id и новая Jira с теми же задачами.

OS-91030 в облаке был 683676, в новой Jira — 258783 (в базе это id
PMD-19591). Время ворклогов базы — московское, в новой Jira — UTC.
"""
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting, BacklogItem, ScopeProject
from app.services.jira_migration.state import STATE_PENDING, set_migration_state
from tests.services.jira_migration.factory import (
    make_employee,
    make_issue,
    make_project,
    make_worklog,
)
from tests.services.jira_migration.fake_jira import FakeJira, dc_user, dc_worklog

NOW = datetime(2026, 10, 14, 12, 0)
IVANOV_DC = dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван")
PETROV_DC = dc_user("JIRAUSER7", "Petrov_P", "Петров Пётр")
STRANGER_DC = dc_user("JIRAUSER9", "Stranger", "Посторонний")


def seed_world(db: Session) -> dict[str, str]:
    set_migration_state(db, STATE_PENDING)
    db.add(AppSetting(key="jira_team_field_id", value="customfield_11526"))
    db.add(ScopeProject(jira_project_key="OS", jira_project_id="11029"))
    os_project = make_project(db, "OS", "11029")
    pmd = make_project(db, "PMD", "11015")
    a = make_issue(db, os_project, "OS-91030", "683676")
    b = make_issue(db, pmd, "PMD-19591", "258783", team="Команда Б")
    gone = make_issue(db, os_project, "OS-1", "500001")
    make_issue(db, os_project, "OS-2", "500002")
    db.add(BacklogItem(title="Идея", issue_id=gone.id))
    ivanov = make_employee(db, "cloud-ivanov", "Иванов Иван")
    petrov = make_employee(db, "cloud-petrov", "Петров Пётр")
    for day in (10, 11, 12):
        make_worklog(db, a, ivanov, datetime(2026, 9, day, 10, 0), 3600, f"w{day}")
    make_worklog(db, b, ivanov, datetime(2026, 9, 1, 2, 30), 1800, "w1")
    ids = {"ivanov": ivanov.id, "petrov": petrov.id}
    db.commit()
    return ids


def dc_world(**overrides: Any) -> FakeJira:
    params: dict[str, Any] = {
        "projects": {"OS": "10901", "PMD": "10902"},
        "issues": {
            "OS": [("OS-91030", "258783"), ("OS-5", "300005")],
            "PMD": [("PMD-19591", "999999")],
        },
        "worklogs": [
            dc_worklog("9001", "258783", IVANOV_DC, "2026-09-10T07:00:00.000+0000", 3600),
            dc_worklog("9002", "258783", IVANOV_DC, "2026-09-11T07:00:00.000+0000", 3600),
            dc_worklog("9003", "258783", IVANOV_DC, "2026-09-12T07:00:00.000+0000", 3600),
            dc_worklog("9004", "999999", IVANOV_DC, "2026-08-31T23:30:00.000+0000", 1800),
            dc_worklog("9005", "777", STRANGER_DC, "2026-09-10T07:00:00.000+0000", 3600),
        ],
        "users": [IVANOV_DC, PETROV_DC],
        "fields": [{"id": "customfield_11092", "name": "Продуктовая команда", "custom": True}],
    }
    params.update(overrides)
    return FakeJira(**params)
```

- [ ] **Step 2: Write the failing tests**

`tests/services/jira_migration/test_dry_run.py`:

```python
"""Пробный прогон: отчёт по полям, задачам, сотрудникам и часам; данные базы не меняются."""
import pytest

from app.models import AppSetting, Issue, Worklog
from app.services.jira_migration.dry_run import DryRunAborted, build_report
from app.services.jira_migration.fields import SNAPSHOT_KEY
from app.services.jira_migration.people import STATUS_BY_HOURS, STATUS_BY_NAME
from tests.services.jira_migration.world import NOW, dc_world, seed_world


async def test_report_covers_all_sections(db_session):
    ids = seed_world(db_session)
    steps: list[str] = []

    result = await build_report(
        db_session, dc_world(), now=NOW, progress=lambda step, counters=None: steps.append(step),
    )
    report, maps = result.report, result.maps

    assert all(p["ok"] for p in report["probe"] if p["essential"])
    assert [r["cloud_id"] for r in report["fields"]] == ["customfield_11526"]
    assert report["fields"][0]["suggested_id"] == "customfield_11092"
    assert report["issues"] == {"db_total": 4, "matched": 2, "new_in_dc": 1, "missing": ["OS-1", "OS-2"]}
    assert maps == {
        "projects": {"OS": "10901", "PMD": "10902"},
        "issues": {"OS-91030": "258783", "PMD-19591": "999999"},
    }
    assert (report["offset_hours"], report["offset_matches"], report["offset_sample"]) == (3, 4, 4)
    people = {p["employee_id"]: p for p in report["people"]}
    assert people[ids["ivanov"]]["status"] == STATUS_BY_HOURS
    assert people[ids["ivanov"]]["auto"]["key"] == "JIRAUSER5"
    assert people[ids["petrov"]]["status"] == STATUS_BY_NAME
    assert people[ids["petrov"]]["auto"]["key"] == "JIRAUSER7"
    assert report["hours"]["rows"] == [
        {"team": "Команда А", "month": "2026-09", "db_hours": 3.0, "dc_hours": 3.0,
         "diff_pct": 0.0, "flagged": False},
        {"team": "Команда Б", "month": "2026-09", "db_hours": 0.5, "dc_hours": 0.5,
         "diff_pct": 0.0, "flagged": False},
    ]
    hours = report["hours"]
    assert (hours["db_worklogs"], hours["dc_worklogs"], hours["dc_worklogs_total"]) == (4, 4, 5)
    assert report["db_worklogs_min_date"] == "2026-09-01"
    assert report["projects"] == [{"key": "OS", "found": True}, {"key": "PMD", "found": True}]
    assert "Списания новой Jira" in steps


async def test_dry_run_writes_only_the_field_snapshot(db_session):
    seed_world(db_session)
    before = {(i.key, i.jira_issue_id) for i in db_session.query(Issue).all()}

    await build_report(db_session, dc_world(), now=NOW)

    assert {(i.key, i.jira_issue_id) for i in db_session.query(Issue).all()} == before
    assert db_session.query(Worklog).count() == 4
    snapshot = db_session.query(AppSetting).filter_by(key=SNAPSHOT_KEY).one()
    assert '"jira_team_field_id": "customfield_11526"' in snapshot.value


async def test_essential_failure_aborts_with_probe(db_session):
    seed_world(db_session)

    with pytest.raises(DryRunAborted) as exc:
        await build_report(db_session, dc_world(fail={"get_projects"}), now=NOW)

    assert "Список проектов" in str(exc.value)
    probe = {p["code"]: p for p in exc.value.report["probe"]}
    assert probe["projects"]["ok"] is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_dry_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration.dry_run'`.

- [ ] **Step 4: Dry run**

`app/services/jira_migration/dry_run.py`:

```python
"""Пробный прогон переезда: только чтение новой Jira, в базу пишется лишь отчёт.

Единственная запись помимо отчёта — снимок облачных настроек полей при
первом прогоне (``fields.ensure_field_snapshot``).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Issue, Project, Worklog
from app.services.jira_migration import store
from app.services.jira_migration.fields import (
    build_field_rows,
    ensure_field_snapshot,
    field_ids_of,
    resolve_fields,
)
from app.services.jira_migration.fingerprints import detect_offset, scan_dc_worklogs
from app.services.jira_migration.hours import (
    compare_hours,
    db_seconds,
    dc_seconds,
    load_db_worklogs,
    to_hours,
)
from app.services.jira_migration.issues import scan_issue_ids
from app.services.jira_migration.people import build_people_rows, vote_people
from app.services.jira_migration.probe import essential_failures, run_probe

ProgressFn = Callable[..., None]
REPORT_VERSION = 1

STEP_CHECK = "Проверка новой Jira"
STEP_PROJECTS = "Проекты"
STEP_ISSUES = "Задачи"
STEP_DB_WORKLOGS = "Списания базы"
STEP_DC_WORKLOGS = "Списания новой Jira"
STEP_PEOPLE = "Сотрудники"


class DryRunAborted(Exception):
    """Новая Jira не отвечает на обязательные запросы: отчёт строить не из чего."""

    def __init__(self, message: str, report: dict) -> None:
        super().__init__(message)
        self.report = report


@dataclass
class DryRunResult:
    report: dict   # сводка для страницы
    maps: dict     # для применения: {"projects": {ключ: id}, "issues": {ключ: id}}


def _silent(step: str, counters: Optional[dict] = None) -> None:
    return None


def _dc_fields(raw: list[dict]) -> list[dict[str, Any]]:
    return [
        {"id": str(f["id"]), "name": str(f.get("name") or f["id"]), "custom": bool(f.get("custom"))}
        for f in raw if f.get("id")
    ]


async def build_report(
    db: Session,
    jira: Any,
    *,
    now: datetime,
    progress: ProgressFn = _silent,
) -> DryRunResult:
    """Собрать отчёт пробного прогона. Обязательный запрос не работает — ``DryRunAborted``."""
    progress(STEP_CHECK, None)
    snapshot = ensure_field_snapshot(db)
    try:
        raw_fields = await jira.get_fields()
    except Exception:  # noqa: BLE001 — сбой попадёт в проверку возможностей ниже
        raw_fields = []
    dc_fields = _dc_fields(raw_fields)
    field_rows = build_field_rows(snapshot, dc_fields)
    field_map = resolve_fields(field_rows, store.get_decisions(db, store.KIND_FIELD), dc_fields).mapping
    team_ids = field_ids_of(snapshot.get("jira_team_field_id"))
    team_field_id = field_map.get(team_ids[0]) if team_ids else None
    sample = db.query(Issue.key, Project.key).join(Project, Project.id == Issue.project_id).first()
    probe = await run_probe(
        db, jira,
        sample_project=sample[1] if sample else None,
        sample_issue_key=sample[0] if sample else None,
        team_field_id=team_field_id,
        now=now,
    )
    probe_rows = [item.to_dict() for item in probe]
    failed = essential_failures(probe)
    if failed:
        raise DryRunAborted(
            "Новая Jira не отвечает на обязательные запросы: " + ", ".join(item.title for item in failed),
            {"version": REPORT_VERSION, "generated_at": now.isoformat(), "probe": probe_rows},
        )

    progress(STEP_PROJECTS, None)
    dc_projects = {p.key: str(p.id) for p in await jira.get_projects()}

    progress(STEP_ISSUES, {"issues_read": 0})
    scan = await scan_issue_ids(
        db, jira, dc_projects, on_progress=lambda n: progress(STEP_ISSUES, {"issues_read": n}),
    )

    progress(STEP_DB_WORKLOGS, None)
    db_rows = load_db_worklogs(db)
    team_by_key = dict(db.query(Issue.key, Issue.team).all())
    worklog_counts: dict[str, int] = {}
    for row in db_rows:
        worklog_counts[row.employee_id] = worklog_counts.get(row.employee_id, 0) + 1

    progress(STEP_DC_WORKLOGS, {"worklogs_read": 0})
    id_to_key = {issue_id: key for key, issue_id in scan.key_to_id.items()}
    dc = await scan_dc_worklogs(
        jira, id_to_key, on_progress=lambda n: progress(STEP_DC_WORKLOGS, {"worklogs_read": n}),
    )
    offset, offset_counts, offset_sample = detect_offset(db_rows, dc.rows)
    votes = vote_people(db_rows, dc.rows, offset)

    progress(STEP_PEOPLE, {"people_checked": 0})
    people = await build_people_rows(
        db, jira, votes, dc.authors, worklog_counts,
        on_progress=lambda n: progress(STEP_PEOPLE, {"people_checked": n}),
    )

    min_started = db.query(func.min(Worklog.started_at)).scalar()
    report = {
        "version": REPORT_VERSION,
        "generated_at": now.isoformat(),
        "probe": probe_rows,
        "fields": field_rows,
        "dc_fields": dc_fields,
        "projects": scan.projects,
        "issues": {
            "db_total": scan.db_total,
            "matched": scan.matched,
            "new_in_dc": scan.new_in_dc,
            "missing": scan.missing,
        },
        "offset_hours": offset,
        "offset_matches": offset_counts[offset],
        "offset_sample": offset_sample,
        "people": people,
        "hours": {
            "rows": compare_hours(
                to_hours(db_seconds(db_rows)), to_hours(dc_seconds(dc.rows, team_by_key, offset)),
            ),
            "db_worklogs": len(db_rows),
            "dc_worklogs": len(dc.rows),
            "dc_worklogs_total": dc.total,
        },
        "db_worklogs_min_date": min_started.date().isoformat() if min_started else None,
    }
    return DryRunResult(report=report, maps={"projects": dc_projects, "issues": scan.key_to_id})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_dry_run.py -v`
Expected: PASS (3 tests).

Run: `ruff check app/services/jira_migration/dry_run.py tests/services/jira_migration`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/dry_run.py tests/services/jira_migration/world.py tests/services/jira_migration/test_dry_run.py
git commit -m "feat(jira-migration): пробный прогон — отчёт по полям, задачам, людям и часам" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Текущее состояние решений и препятствия к применению

**Files:**
- Create: `app/services/jira_migration/resolution.py`
- Create: `tests/services/jira_migration/ready.py`
- Test: `tests/services/jira_migration/test_resolution.py`

- [ ] **Step 1: «Готово к применению» для тестов**

`tests/services/jira_migration/ready.py`:

```python
"""Состояние «готово к применению»: база до переезда, свежий отчёт, все решения приняты.

OS-91030 получает в новой Jira id 258783 — в базе это старый id PMD-19591.
OS-1 исчез без данных сервиса (удалится сам), OS-2 исчез с бэклогом
(решение «удалить»), OS-3 исчез с отметкой стола тимлида (решение
«оставить»), OS-4 — подзадача OS-2, есть в новой Jira.
Иванов найден по списаниям, Петров привязан решением, Сидоров — без привязки.
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    BacklogItem,
    CategoryMapping,
    Comment,
    IssueLink,
    KpiApproval,
    ScopeProject,
    ScopeRoot,
    TeamDeskMark,
    User,
)
from app.services.jira_migration import store
from app.services.jira_migration.fields import build_field_rows, ensure_field_snapshot
from app.services.jira_migration.state import STATE_PENDING, set_migration_state
from app.services.plan_sources import Candidate, fingerprint
from tests.services.jira_migration.factory import (
    make_employee,
    make_issue,
    make_project,
    make_worklog,
    seed_report,
)

DC_FIELDS = [
    {"id": "customfield_11092", "name": "Продуктовая команда", "custom": True},
    {"id": "customfield_11097", "name": "Разработка (ч)", "custom": True},
    {"id": "customfield_11034", "name": "Оценка 1С (ч)", "custom": True},
    {"id": "customfield_10109", "name": "Спринт", "custom": True},
]
PLANNED_DEV = json.dumps([
    {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
    {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
], ensure_ascii=False, separators=(",", ":"))
OLD_CANDIDATES = [
    Candidate("customfield_12432", "Разработка (ч)", 40.0),
    Candidate("customfield_14648", "Оценка 1С (ч)", 56.0),
]
IVANOV_DC = {"key": "JIRAUSER5", "name": "Ivanov_I", "display_name": "Иванов Иван"}


def seed_ready(db: Session, finished_at: datetime) -> dict[str, str]:
    set_migration_state(db, STATE_PENDING)
    db.add_all([
        AppSetting(key="jira_team_field_id", value="customfield_11526"),
        AppSetting(key="jira_planned_dev_hours_field_id", value=PLANNED_DEV),
        AppSetting(key="jira_sprint_field_id", value="customfield_10019"),
        AppSetting(key="jira_epic_link_field_id", value="customfield_77777"),
    ])
    db.commit()
    snapshot = ensure_field_snapshot(db)

    os_project = make_project(db, "OS", "11029")
    pmd = make_project(db, "PMD", "11015")
    a = make_issue(db, os_project, "OS-91030", "683676")
    b = make_issue(db, pmd, "PMD-19591", "258783", team="Команда Б")
    os1 = make_issue(db, os_project, "OS-1", "500001")
    os2 = make_issue(db, os_project, "OS-2", "500002")
    os3 = make_issue(db, os_project, "OS-3", "500003")
    os4 = make_issue(db, os_project, "OS-4", "500004", parent_id=os2.id)
    a.planned_hours_sources = {"dev": [c.to_dict() for c in OLD_CANDIDATES]}
    a.planned_hours_choice = {
        "dev": {"source": "customfield_14648", "fingerprint": fingerprint(OLD_CANDIDATES)},
    }
    a.assignee_account_id = "cloud-ivanov"
    a.reporter_account_id = "cloud-petrov"
    a.developer_account_id = "cloud-sidorov"
    b.developer_account_id = "someone-else"

    ivanov = make_employee(db, "cloud-ivanov", "Иванов Иван")
    petrov = make_employee(db, "cloud-petrov", "Петров Пётр")
    sidorov = make_employee(db, "cloud-sidorov", "Сидоров Сидор")
    make_worklog(db, a, ivanov, datetime(2026, 9, 10, 10, 0), 3600, "850609")
    db.add_all([
        BacklogItem(title="Инициатива", issue_id=os2.id, assignee_jira_account_at_choice="cloud-ivanov"),
        TeamDeskMark(issue_id=os3.id, flag="stale", signature="s"),
        IssueLink(source_issue_id=os2.id, target_issue_id=a.id, link_type="Relates"),
        Comment(jira_comment_id="c1", issue_id=a.id, body="текст", author_id=ivanov.id),
        CategoryMapping(entity_type="worklog", entity_id="old-worklog", category="dev"),
        CategoryMapping(entity_type="issue", entity_id=os1.id, category="dev"),
        KpiApproval(
            team="Команда А", year=2026, quarter=3, approved_by="Админ", approved_at=finished_at,
            payload_json=json.dumps({"rows": [{"employee_id": ivanov.id, "account_id": "cloud-ivanov"}]}),
        ),
        ScopeProject(jira_project_key="OS", jira_project_id="11029"),
        ScopeRoot(category_code="dev", jira_issue_key="OS-91030", jira_issue_id="683676"),
    ])
    user = db.query(User).first()
    user.team_desk_filter = {"teams": ["Команда А"], "developers": ["cloud-sidorov", "unknown"]}
    ids = {
        "a": a.id, "b": b.id, "os1": os1.id, "os2": os2.id, "os3": os3.id, "os4": os4.id,
        "ivanov": ivanov.id, "petrov": petrov.id, "sidorov": sidorov.id, "user": user.id,
    }
    db.commit()

    not_found = {"worklogs": 0, "matched": 0, "status": "not_found", "candidates": [], "auto": None}
    report = {
        "probe": [],
        "fields": build_field_rows(snapshot, DC_FIELDS),
        "dc_fields": DC_FIELDS,
        "projects": [{"key": "OS", "found": True}, {"key": "PMD", "found": True}],
        "issues": {"db_total": 6, "matched": 3, "new_in_dc": 0, "missing": ["OS-1", "OS-2", "OS-3"]},
        "offset_hours": 3,
        "offset_matches": 1,
        "offset_sample": 1,
        "people": [
            {"employee_id": ids["ivanov"], "display_name": "Иванов Иван", "worklogs": 1, "matched": 5,
             "status": "by_hours", "candidates": [{**IVANOV_DC, "votes": 5}], "auto": IVANOV_DC},
            {"employee_id": ids["petrov"], "display_name": "Петров Пётр", **not_found},
            {"employee_id": ids["sidorov"], "display_name": "Сидоров Сидор", **not_found},
        ],
        "hours": {
            "rows": [{"team": "Команда А", "month": "2026-09", "db_hours": 1.0, "dc_hours": 1.0,
                      "diff_pct": 0.0, "flagged": False}],
            "db_worklogs": 1, "dc_worklogs": 1, "dc_worklogs_total": 1,
        },
        "db_worklogs_min_date": "2026-09-10",
    }
    maps = {
        "projects": {"OS": "10901", "PMD": "10902"},
        "issues": {"OS-91030": "258783", "PMD-19591": "999999", "OS-4": "500100"},
    }
    ids["report"] = seed_report(db, report, maps, finished_at)
    store.set_decision(db, store.KIND_ISSUE, "OS-2", {"action": "delete"}, "Админ")
    store.set_decision(db, store.KIND_ISSUE, "OS-3", {"action": "keep"}, "Админ")
    store.set_decision(db, store.KIND_PERSON, ids["petrov"],
                       {"action": "bind", "key": "JIRAUSER7", "name": "Petrov_P",
                        "display_name": "Петров Пётр"}, "Админ")
    store.set_decision(db, store.KIND_PERSON, ids["sidorov"], {"action": "unbind"}, "Админ")
    return ids
```

- [ ] **Step 2: Write the failing tests**

`tests/services/jira_migration/test_resolution.py`:

```python
"""Препятствия к применению: свежесть отчёта, нерешённые пункты, копия базы, состояние."""
import json
from datetime import datetime, timedelta

from app.models import Employee, TeamDeskDailyRate
from app.services.jira_migration import store
from app.services.jira_migration.resolution import collect_blockers, resolve
from app.services.jira_migration.state import STATE_DONE, STATE_PENDING, set_migration_state
from tests.services.jira_migration.ready import seed_ready

NOW = datetime(2026, 10, 14, 12, 0)


def _blockers(db, backup=True, job=False):
    return collect_blockers(db, now=NOW, backup_confirmed=backup, job_running=job)


def test_ready_state_has_no_blockers(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))

    assert _blockers(db_session) == []
    res = resolve(db_session)
    assert res.counts() == {"fields": 0, "issues": 0, "people": 0}
    assert res.deletable == ["OS-1"]
    assert [r["key"] for r in res.with_data] == ["OS-2", "OS-3"]
    assert res.issues_to_delete() == ["OS-1", "OS-2"]


def test_backup_tick_job_and_finished_migration(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))

    assert _blockers(db_session, backup=False, job=True) == [
        "Идёт другая операция переезда — дождитесь её окончания",
        "Отметьте, что свежая копия базы сделана",
    ]
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    assert _blockers(db_session) == ["Переезд уже выполнен"]


def test_no_report_and_failed_report(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    assert _blockers(db_session) == ["Пробный прогон ещё не запускался"]

    report_id = store.start_report(db_session, NOW)
    store.fail_report(db_session, report_id, "сбой", NOW)
    assert _blockers(db_session) == [
        "Последний пробный прогон не завершился успешно — запустите его заново",
    ]


def test_stale_report_blocks(db_session):
    seed_ready(db_session, NOW - timedelta(hours=25))
    assert _blockers(db_session) == ["Пробный прогон старше суток — запустите его заново"]


def test_unresolved_issue_and_person_block(db_session):
    ids = seed_ready(db_session, NOW - timedelta(hours=1))
    store.set_decision(db_session, store.KIND_ISSUE, "OS-3", None, "Админ")
    store.set_decision(db_session, store.KIND_PERSON, ids["sidorov"], None, "Админ")

    assert _blockers(db_session) == [
        "Остались нерешённые пункты: поля — 0, задачи — 1, сотрудники — 1",
    ]


def test_unresolved_field_counts_until_decided(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))
    row = store.latest_report(db_session)
    report = store.report_data(row)
    report["fields"].append({
        "cloud_id": "customfield_12434", "cloud_name": "Пусконаладочные (ОПЭ) (ч)",
        "settings": ["jira_planned_opo_hours_field_id"], "labels": ["Плановые часы ОПЭ"],
        "suggested_id": None, "suggested_name": None, "auto_only": False,
    })
    row.report_json = json.dumps(report, ensure_ascii=False)
    db_session.commit()

    assert resolve(db_session).counts()["fields"] == 1
    store.set_decision(db_session, store.KIND_FIELD, "customfield_12434", {"dc_field_id": None}, "Админ")
    assert resolve(db_session).counts()["fields"] == 0


def test_employee_added_after_dry_run_blocks(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))
    db_session.add(Employee(jira_account_id="JIRAUSER99", display_name="Новенький"))
    db_session.commit()

    assert _blockers(db_session) == [
        "После пробного прогона появились новые сотрудники (1) — запустите прогон заново",
    ]


def test_issue_that_gained_service_data_needs_decision(db_session):
    ids = seed_ready(db_session, NOW - timedelta(hours=1))
    db_session.add(TeamDeskDailyRate(issue_id=ids["os1"], hours=1.0))
    db_session.commit()

    res = resolve(db_session)
    assert res.deletable == []
    assert res.counts()["issues"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_resolution.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration.resolution'`.

- [ ] **Step 4: Resolution module**

`app/services/jira_migration/resolution.py`:

```python
"""Текущее состояние решений по отчёту и препятствия к применению.

Служебные данные задач, которых нет в новой Jira, пересчитываются при
каждом обращении: за сутки до применения у «удаляемой» задачи могли
появиться ручные данные — тогда по ней нужно решение.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Employee
from app.models.jira_migration import JiraMigrationReport
from app.services.jira_migration import store
from app.services.jira_migration.fields import FieldResolution, resolve_fields
from app.services.jira_migration.issues import classify_missing
from app.services.jira_migration.people import PersonOutcome, finalize_people
from app.services.jira_migration.state import STATE_DONE, get_migration_state

REPORT_MAX_AGE = timedelta(hours=24)

BLOCK_DONE = "Переезд уже выполнен"
BLOCK_JOB = "Идёт другая операция переезда — дождитесь её окончания"
BLOCK_NO_REPORT = "Пробный прогон ещё не запускался"
BLOCK_FAILED = "Последний пробный прогон не завершился успешно — запустите его заново"
BLOCK_STALE = "Пробный прогон старше суток — запустите его заново"
BLOCK_BACKUP = "Отметьте, что свежая копия базы сделана"


@dataclass
class Resolution:
    row: JiraMigrationReport
    report: dict
    fields: FieldResolution
    field_decisions: dict[str, dict]
    people: dict[str, PersonOutcome]
    person_decisions: dict[str, dict]
    deletable: list[str]          # нет в новой Jira, нет служебных данных — удалятся
    with_data: list[dict]         # нет в новой Jira, есть служебные данные — нужны решения
    issue_decisions: dict[str, dict]
    new_employees: int            # сотрудники, которых нет в отчёте

    def unresolved_issue_keys(self) -> list[str]:
        return [item["key"] for item in self.with_data if item["key"] not in self.issue_decisions]

    def unresolved_people_ids(self) -> list[str]:
        return [employee_id for employee_id, outcome in self.people.items() if outcome.unresolved]

    def counts(self) -> dict[str, int]:
        return {
            "fields": len(self.fields.unresolved),
            "issues": len(self.unresolved_issue_keys()),
            "people": len(self.unresolved_people_ids()),
        }

    def issues_to_delete(self) -> list[str]:
        with_data_keys = {item["key"] for item in self.with_data}
        decided = {
            key for key, decision in self.issue_decisions.items()
            if key in with_data_keys and decision.get("action") == store.ISSUE_DELETE
        }
        return sorted(set(self.deletable) | decided)


def resolve(db: Session, row: Optional[JiraMigrationReport] = None) -> Optional[Resolution]:
    """Отчёт + решения + текущие данные. Нет успешного отчёта — ``None``."""
    row = row if row is not None else store.latest_report(db)
    if row is None or row.status != store.STATUS_DONE:
        return None
    report = store.report_data(row)
    field_decisions = store.get_decisions(db, store.KIND_FIELD)
    person_decisions = store.get_decisions(db, store.KIND_PERSON)
    issue_decisions = store.get_decisions(db, store.KIND_ISSUE)
    people_rows = report.get("people", [])
    deletable, with_data = classify_missing(db, report.get("issues", {}).get("missing", []))
    in_report = {r["employee_id"] for r in people_rows}
    new_employees = sum(1 for (employee_id,) in db.query(Employee.id).all() if employee_id not in in_report)
    return Resolution(
        row=row,
        report=report,
        fields=resolve_fields(report.get("fields", []), field_decisions, report.get("dc_fields", [])),
        field_decisions=field_decisions,
        people=finalize_people(people_rows, person_decisions),
        person_decisions=person_decisions,
        deletable=deletable,
        with_data=with_data,
        issue_decisions=issue_decisions,
        new_employees=new_employees,
    )


def collect_blockers(
    db: Session,
    *,
    now: datetime,
    backup_confirmed: bool,
    job_running: bool,
    resolution: Optional[Resolution] = None,
) -> list[str]:
    """Почему «Применить» сейчас нельзя. Пустой список — можно."""
    if get_migration_state(db) == STATE_DONE:
        return [BLOCK_DONE]
    blockers: list[str] = []
    if job_running:
        blockers.append(BLOCK_JOB)
    row = resolution.row if resolution is not None else store.latest_report(db)
    if row is None:
        blockers.append(BLOCK_NO_REPORT)
    elif row.status != store.STATUS_DONE:
        blockers.append(BLOCK_FAILED)
    else:
        if row.finished_at is None or now - row.finished_at > REPORT_MAX_AGE:
            blockers.append(BLOCK_STALE)
        res = resolution if resolution is not None else resolve(db, row)
        if res is not None:
            counts = res.counts()
            if any(counts.values()):
                blockers.append(
                    f"Остались нерешённые пункты: поля — {counts['fields']}, "
                    f"задачи — {counts['issues']}, сотрудники — {counts['people']}"
                )
            if res.new_employees:
                blockers.append(
                    f"После пробного прогона появились новые сотрудники ({res.new_employees}) — "
                    "запустите прогон заново"
                )
    if not backup_confirmed:
        blockers.append(BLOCK_BACKUP)
    return blockers
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_resolution.py -v`
Expected: PASS (8 tests).

Run: `ruff check app/services/jira_migration/resolution.py tests/services/jira_migration`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/resolution.py tests/services/jira_migration/ready.py tests/services/jira_migration/test_resolution.py
git commit -m "feat(jira-migration): состояние решений и препятствия к применению" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: «Применить» — одна транзакция перепривязки

**Files:**
- Create: `app/services/jira_migration/apply.py`
- Test: `tests/services/jira_migration/test_apply.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/jira_migration/test_apply.py`:

```python
"""Применение переезда: одна транзакция, пересечения id, удаление по решениям, люди везде."""
import json
from datetime import datetime, timedelta

import pytest

from app.models import (
    AppSetting,
    BacklogItem,
    CategoryMapping,
    Comment,
    Employee,
    Issue,
    IssueLink,
    KpiApproval,
    Project,
    ScopeProject,
    ScopeRoot,
    TeamDeskMark,
    User,
    Worklog,
)
from app.models.jira_migration import JiraMigrationReport
from app.services.jira_migration import apply as apply_module
from app.services.jira_migration.apply import ApplyRefused, apply_migration
from app.services.jira_migration.state import STATE_DONE, STATE_PENDING, get_migration_state
from app.services.plan_sources import Candidate, resolve_role
from tests.services.jira_migration.ready import seed_ready

NOW = datetime(2026, 10, 14, 12, 0)


@pytest.fixture
def ready(db_session):
    return seed_ready(db_session, NOW - timedelta(hours=1))


def _issue_ids(db) -> dict[str, str]:
    return dict(db.query(Issue.key, Issue.jira_issue_id).all())


def _apply(db):
    return apply_migration(db, now=NOW, backup_confirmed=True)


def test_refused_without_backup_tick(db_session, ready):
    with pytest.raises(ApplyRefused) as exc:
        apply_migration(db_session, now=NOW, backup_confirmed=False)

    assert "Отметьте, что свежая копия базы сделана" in exc.value.blockers
    assert _issue_ids(db_session)["OS-91030"] == "683676"
    assert get_migration_state(db_session) == STATE_PENDING


def test_issue_ids_rebound_through_collision(db_session, ready):
    _apply(db_session)

    # OS-91030 получил id, который до переезда был у PMD-19591
    assert _issue_ids(db_session) == {
        "OS-91030": "258783", "PMD-19591": "999999", "OS-3": "cloud:500003", "OS-4": "500100",
    }


def test_issues_deleted_per_decisions_with_children_cleaned(db_session, ready):
    summary = _apply(db_session)

    assert summary["issues_deleted"] == 2
    assert db_session.get(Issue, ready["os4"]).parent_id is None
    assert db_session.query(BacklogItem).one().issue_id is None
    assert db_session.query(IssueLink).count() == 0
    assert db_session.query(TeamDeskMark).one().issue_id == ready["os3"]
    assert db_session.query(CategoryMapping).filter_by(entity_type="issue").count() == 0


def test_projects_and_scope_rebound(db_session, ready):
    _apply(db_session)

    assert dict(db_session.query(Project.key, Project.jira_project_id).all()) == {"OS": "10901", "PMD": "10902"}
    assert db_session.query(ScopeProject.jira_project_id).scalar() == "10901"
    assert db_session.query(ScopeRoot.jira_issue_id).scalar() == "258783"


def test_people_rewritten_everywhere(db_session, ready):
    summary = _apply(db_session)

    employees = {e.display_name: (e.jira_account_id, e.jira_username) for e in db_session.query(Employee).all()}
    assert employees == {
        "Иванов Иван": ("JIRAUSER5", "Ivanov_I"),
        "Петров Пётр": ("JIRAUSER7", "Petrov_P"),
        "Сидоров Сидор": ("cloud:cloud-sidorov", None),
    }
    a = db_session.get(Issue, ready["a"])
    assert (a.assignee_account_id, a.reporter_account_id, a.developer_account_id) == (
        "JIRAUSER5", "JIRAUSER7", "cloud:cloud-sidorov",
    )
    assert db_session.get(Issue, ready["b"]).developer_account_id == "someone-else"
    assert db_session.query(BacklogItem.assignee_jira_account_at_choice).scalar() == "JIRAUSER5"
    assert db_session.get(User, ready["user"]).team_desk_filter["developers"] == [
        "cloud:cloud-sidorov", "unknown",
    ]
    payload = json.loads(db_session.query(KpiApproval).one().payload_json)
    assert payload["rows"][0]["account_id"] == "JIRAUSER5"
    assert (summary["employees_bound"], summary["employees_unbound"]) == (2, 1)


def test_plan_choice_still_valid(db_session, ready):
    _apply(db_session)

    a = db_session.get(Issue, ready["a"])
    candidates = [Candidate(c["source"], c["label"], c["value"]) for c in a.planned_hours_sources["dev"]]
    assert [c.source for c in candidates] == ["customfield_11097", "customfield_11034"]
    resolution = resolve_role(candidates, a.planned_hours_choice["dev"])
    assert resolution.disputed is False
    assert resolution.value == 56.0


def test_field_settings_rewritten_and_caches_dropped(db_session, ready):
    summary = _apply(db_session)

    settings = dict(db_session.query(AppSetting.key, AppSetting.value).all())
    assert settings["jira_team_field_id"] == "customfield_11092"
    assert settings["jira_sprint_field_id"] == "customfield_10109"
    assert json.loads(settings["jira_planned_dev_hours_field_id"]) == [
        {"field_id": "customfield_11097", "kind": "alt", "name": "Разработка (ч)"},
        {"field_id": "customfield_11034", "kind": "alt", "name": "Оценка 1С (ч)"},
    ]
    assert "jira_epic_link_field_id" not in settings
    assert summary["settings"] == 3


def test_worklogs_comments_deleted_and_state_done(db_session, ready):
    summary = _apply(db_session)

    assert db_session.query(Worklog).count() == 0
    assert db_session.query(Comment).count() == 0
    assert db_session.query(CategoryMapping).filter_by(entity_type="worklog").count() == 0
    assert (summary["worklogs_deleted"], summary["comments_deleted"]) == (1, 1)
    assert get_migration_state(db_session) == STATE_DONE
    row = db_session.get(JiraMigrationReport, ready["report"])
    assert row.applied_at == NOW
    assert json.loads(row.apply_summary_json)["issues_rebound"] == 3


def test_failure_rolls_everything_back(db_session, ready, monkeypatch):
    def broken(db, people_map):
        raise RuntimeError("сбой посередине")

    monkeypatch.setattr(apply_module, "_rewrite_people_refs", broken)

    with pytest.raises(RuntimeError, match="сбой посередине"):
        _apply(db_session)

    ids = _issue_ids(db_session)
    assert ids["OS-91030"] == "683676"
    assert "OS-1" in ids
    assert db_session.query(Worklog).count() == 1
    assert db_session.query(Employee.jira_account_id).filter_by(display_name="Иванов Иван").scalar() == "cloud-ivanov"
    assert db_session.query(AppSetting.value).filter_by(key="jira_team_field_id").scalar() == "customfield_11526"
    assert get_migration_state(db_session) == STATE_PENDING
    assert db_session.get(JiraMigrationReport, ready["report"]).applied_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_apply.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_migration.apply'`.

- [ ] **Step 3: Apply module**

`app/services/jira_migration/apply.py`:

```python
"""Применение переезда: перепривязка базы к новой Jira одной транзакцией.

Внутренние UUID не меняются — переписываются только id Jira. Порядок:
настройки полей → ворклоги и комментарии удаляются (на задачи и
сотрудников у них внешние ключи; вернутся полной синхронизацией) → проекты
→ задачи (удаление по решениям, затем всем id префикс «cloud:» и новые id
по ключу — так новый id, совпавший со старым id другой задачи, не упирается
в уникальность) → кандидаты оценки → сотрудники (тот же приём) → id людей в
задачах, бэклоге, фильтре стола тимлида и снимках KPI → scope → состояние
«переезд завершён». Ошибка на любом шаге — откат, база остаётся как была.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, literal, or_, update
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    BacklogItem,
    CategoryMapping,
    Comment,
    Employee,
    Issue,
    IssueClassification,
    IssueLink,
    KpiApproval,
    PlanAudit,
    Project,
    ProjectAISummary,
    ScopeProject,
    ScopeRoot,
    TeamDeskDailyRate,
    TeamDeskMark,
    User,
    Worklog,
)
from app.models.jira_migration import JiraMigrationReport
from app.services.jira_migration import store
from app.services.jira_migration.fields import (
    AUTO_CACHE_KEYS,
    load_field_snapshot,
    remap_plan_sources,
    rewrite_setting_value,
)
from app.services.jira_migration.issues import chunks
from app.services.jira_migration.resolution import (
    BLOCK_NO_REPORT,
    Resolution,
    collect_blockers,
    resolve,
)
from app.services.jira_migration.state import STATE_DONE, set_migration_state

logger = logging.getLogger(__name__)

CLOUD_PREFIX = "cloud:"
BULK = 1000
_NO_SYNC = {"synchronize_session": False}


class ApplyRefused(Exception):
    """Предусловия не выполнены — причины в ``blockers``. База не тронута."""

    def __init__(self, blockers: list[str]) -> None:
        super().__init__("; ".join(blockers))
        self.blockers = blockers


def apply_migration(db: Session, *, now: datetime, backup_confirmed: bool) -> dict[str, Any]:
    """Перепривязать базу к новой Jira и поставить «переезд завершён». Коммитит.

    Предусловия проверяются заново внутри (свежий отчёт, нет нерешённых
    пунктов, копия базы, состояние ``pending``).
    """
    res = resolve(db)
    blockers = collect_blockers(
        db, now=now, backup_confirmed=backup_confirmed, job_running=False, resolution=res,
    )
    if blockers:
        raise ApplyRefused(blockers)
    if res is None:
        raise ApplyRefused([BLOCK_NO_REPORT])
    maps = store.report_maps(res.row)
    report_id = res.row.id
    try:
        summary: dict[str, Any] = {"settings": _apply_fields(db, res)}
        summary.update(_delete_worklogs_and_comments(db))
        summary["projects"] = _rebind_projects(db, maps.get("projects", {}))
        summary["issues_deleted"] = _delete_issues(db, res.issues_to_delete())
        summary["issues_rebound"] = _rebind_issues(db, maps.get("issues", {}))
        summary["plan_sources"] = _remap_plan_sources(db, res.fields.mapping)
        people_map, bound, unbound = _rebind_employees(db, res)
        summary["employees_bound"] = bound
        summary["employees_unbound"] = unbound
        summary["people_refs"] = _rewrite_people_refs(db, people_map)
        _rebind_scope(db, maps)
        set_migration_state(db, STATE_DONE)
        row = db.get(JiraMigrationReport, report_id)
        row.applied_at = now
        row.apply_summary_json = json.dumps(summary, ensure_ascii=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Применение переезда не удалось — изменения откатаны")
        raise
    return summary


def _apply_fields(db: Session, res: Resolution) -> int:
    """Настройки полей из облачного снимка → поля новой Jira; автокэши без поля удаляются."""
    snapshot = load_field_snapshot(db)
    written = 0
    for key, old_value in snapshot.items():
        new_value = rewrite_setting_value(old_value, res.fields.mapping, res.fields.names)
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if key in AUTO_CACHE_KEYS and not new_value:
            if row is not None:
                db.delete(row)
            continue
        if row is None:
            db.add(AppSetting(key=key, value=new_value))
        else:
            row.value = new_value
        written += 1
    leftover = sorted(AUTO_CACHE_KEYS - set(snapshot))
    if leftover:
        db.execute(delete(AppSetting).where(AppSetting.key.in_(leftover)).execution_options(**_NO_SYNC))
    db.flush()
    return written


def _delete_worklogs_and_comments(db: Session) -> dict[str, int]:
    """Все ворклоги и комментарии: id в новой Jira другие, вернутся полной синхронизацией."""
    worklogs = db.execute(delete(Worklog).execution_options(**_NO_SYNC)).rowcount
    comments = db.execute(delete(Comment).execution_options(**_NO_SYNC)).rowcount
    db.execute(
        delete(CategoryMapping).where(CategoryMapping.entity_type == "worklog").execution_options(**_NO_SYNC)
    )
    return {"worklogs_deleted": worklogs or 0, "comments_deleted": comments or 0}


def _rebind_projects(db: Session, project_ids: Mapping[str, str]) -> int:
    db.execute(
        update(Project)
        .values(jira_project_id=literal(CLOUD_PREFIX) + Project.jira_project_id)
        .execution_options(**_NO_SYNC)
    )
    params = [
        {"id": pk, "jira_project_id": project_ids[key]}
        for pk, key in db.query(Project.id, Project.key).all() if key in project_ids
    ]
    if params:
        db.execute(update(Project), params)
    return len(params)


def _delete_issues(db: Session, keys: Sequence[str]) -> int:
    """Удалить задачи с их строками сервиса. Каскады не полагаются на настройки базы."""
    ids: list[str] = []
    for chunk in chunks(list(keys)):
        ids.extend(pk for (pk,) in db.query(Issue.id).filter(Issue.key.in_(chunk)).all())
    if not ids:
        return 0
    # Сначала все ссылки (иначе Postgres откажет по внешнему ключу), потом сами задачи.
    for chunk in chunks(ids):
        db.execute(
            delete(IssueLink)
            .where(or_(IssueLink.source_issue_id.in_(chunk), IssueLink.target_issue_id.in_(chunk)))
            .execution_options(**_NO_SYNC)
        )
        for model in (IssueClassification, PlanAudit, ProjectAISummary, TeamDeskMark, TeamDeskDailyRate):
            db.execute(delete(model).where(model.issue_id.in_(chunk)).execution_options(**_NO_SYNC))
        db.execute(
            update(BacklogItem).where(BacklogItem.issue_id.in_(chunk)).values(issue_id=None)
            .execution_options(**_NO_SYNC)
        )
        db.execute(
            update(Issue).where(Issue.parent_id.in_(chunk)).values(parent_id=None)
            .execution_options(**_NO_SYNC)
        )
        db.execute(
            delete(CategoryMapping)
            .where(CategoryMapping.entity_type == "issue", CategoryMapping.entity_id.in_(chunk))
            .execution_options(**_NO_SYNC)
        )
    for chunk in chunks(ids):
        db.execute(delete(Issue).where(Issue.id.in_(chunk)).execution_options(**_NO_SYNC))
    return len(ids)


def _rebind_issues(db: Session, issue_ids: Mapping[str, str]) -> int:
    """Префикс «cloud:» всем, затем новые id по ключу. Оставленные без пары сохраняют префикс."""
    db.execute(
        update(Issue)
        .values(jira_issue_id=literal(CLOUD_PREFIX) + Issue.jira_issue_id)
        .execution_options(**_NO_SYNC)
    )
    params = [
        {"id": pk, "jira_issue_id": issue_ids[key]}
        for pk, key in db.query(Issue.id, Issue.key).all() if key in issue_ids
    ]
    for chunk in chunks(params, BULK):
        db.execute(update(Issue), list(chunk))
    return len(params)


def _remap_plan_sources(db: Session, mapping: Mapping[str, Any]) -> int:
    rows = (
        db.query(Issue.id, Issue.planned_hours_sources, Issue.planned_hours_choice)
        .filter(or_(Issue.planned_hours_sources.isnot(None), Issue.planned_hours_choice.isnot(None)))
        .all()
    )
    params = []
    for pk, sources, choice in rows:
        new_sources, new_choice = remap_plan_sources(sources, choice, mapping)
        if new_sources != sources or new_choice != choice:
            params.append({"id": pk, "planned_hours_sources": new_sources, "planned_hours_choice": new_choice})
    for chunk in chunks(params, BULK):
        db.execute(update(Issue), list(chunk))
    return len(params)


def _rebind_employees(db: Session, res: Resolution) -> tuple[dict[str, str], int, int]:
    """Сотрудники отчёта: префикс всем, затем ``key`` и логин новой Jira привязанным.

    Возвращает (старый облачный id → новое значение, привязано, без привязки).
    Без привязки сотрудник сохраняет старый id с префиксом «cloud:» и в синке
    не участвует.
    """
    report_ids = [row["employee_id"] for row in res.report.get("people", [])]
    current: dict[str, str] = {}
    for chunk in chunks(report_ids):
        current.update(dict(
            db.query(Employee.id, Employee.jira_account_id).filter(Employee.id.in_(chunk)).all()
        ))
    for chunk in chunks(list(current)):
        db.execute(
            update(Employee)
            .where(Employee.id.in_(chunk))
            .values(jira_account_id=literal(CLOUD_PREFIX) + Employee.jira_account_id)
            .execution_options(**_NO_SYNC)
        )
    people_map: dict[str, str] = {}
    params: list[dict[str, Any]] = []
    bound = unbound = 0
    for employee_id, old_account in current.items():
        outcome = res.people.get(employee_id)
        if outcome is not None and outcome.key:
            params.append({"id": employee_id, "jira_account_id": outcome.key, "jira_username": outcome.name})
            people_map[old_account] = outcome.key
            bound += 1
        else:
            people_map[old_account] = CLOUD_PREFIX + old_account
            unbound += 1
    for chunk in chunks(params, BULK):
        db.execute(update(Employee), list(chunk))
    return people_map, bound, unbound


def _remap_column(db: Session, model: Any, column: str, mapping: Mapping[str, str]) -> int:
    attr = getattr(model, column)
    params: list[dict[str, Any]] = []
    for chunk in chunks(list(mapping)):
        for pk, value in db.query(model.id, attr).filter(attr.in_(chunk)).all():
            params.append({"id": pk, column: mapping[value]})
    for chunk in chunks(params, BULK):
        db.execute(update(model), list(chunk))
    return len(params)


def _replace_account_ids(node: Any, mapping: Mapping[str, str]) -> bool:
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "account_id" and isinstance(value, str) and value in mapping:
                node[key] = mapping[value]
                changed = True
            elif isinstance(value, (dict, list)):
                changed = _replace_account_ids(value, mapping) or changed
    elif isinstance(node, list):
        for item in node:
            changed = _replace_account_ids(item, mapping) or changed
    return changed


def _rewrite_people_refs(db: Session, people_map: Mapping[str, str]) -> dict[str, int]:
    """Облачные id людей → новые во всех местах, где они хранятся."""
    counts = {
        "issues_assignee": _remap_column(db, Issue, "assignee_account_id", people_map),
        "issues_reporter": _remap_column(db, Issue, "reporter_account_id", people_map),
        "issues_developer": _remap_column(db, Issue, "developer_account_id", people_map),
        "backlog_assignee_at_choice": _remap_column(
            db, BacklogItem, "assignee_jira_account_at_choice", people_map,
        ),
    }
    users = 0
    for user in db.query(User).all():
        team_desk = user.team_desk_filter
        developers = team_desk.get("developers")
        if isinstance(developers, list) and any(d in people_map for d in developers):
            team_desk["developers"] = [people_map.get(d, d) for d in developers]
            user.team_desk_filter = team_desk
            users += 1
    counts["users_team_desk_filter"] = users
    approvals = 0
    for approval in db.query(KpiApproval).all():
        payload = json.loads(approval.payload_json)
        if _replace_account_ids(payload, people_map):
            approval.payload_json = json.dumps(payload, ensure_ascii=False)
            approvals += 1
    counts["kpi_approvals"] = approvals
    db.flush()
    return counts


def _rebind_scope(db: Session, maps: Mapping[str, Any]) -> None:
    projects = maps.get("projects", {})
    issues = maps.get("issues", {})
    for scope_project in db.query(ScopeProject).all():
        scope_project.jira_project_id = projects.get(scope_project.jira_project_key)
    for root in db.query(ScopeRoot).all():
        root.jira_issue_id = issues.get(root.jira_issue_key)
    db.flush()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_apply.py -v`
Expected: PASS (9 tests).

Run: `py -3.10 -m pytest tests/services/jira_migration -q`
Expected: PASS (все тесты пакета).

Run: `ruff check app/services/jira_migration/apply.py tests/services/jira_migration/test_apply.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/apply.py tests/services/jira_migration/test_apply.py
git commit -m "feat(jira-migration): применение переезда одной транзакцией" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Фоновые операции — прогон, применение, полная синхронизация после, сверка

**Files:**
- Create: `app/services/jira_migration/runner.py`
- Test: `tests/services/jira_migration/test_runner.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/jira_migration/test_runner.py`:

```python
"""Фоновые операции переезда: прогон, применение, полная синхронизация после, сверка."""
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.connectors.jira_client import JiraClientError
from app.models import SyncRun
from app.models.jira_migration import JiraMigrationReport
from app.services.jira_migration import runner, store
from app.services.jira_migration.state import (
    STATE_DONE,
    STATE_PENDING,
    get_migration_state,
    set_migration_state,
)
from app.services.sync_lock import SyncLock
from app.services.sync_pipeline import PipelineOrchestrator, WorklogsFullStage
from tests.services.jira_migration.factory import seed_report
from tests.services.jira_migration.fake_jira import FakeJira
from tests.services.jira_migration.ready import seed_ready
from tests.services.jira_migration.world import dc_world, seed_world


@pytest.fixture(autouse=True)
def fresh_job():
    runner._job = runner.MigrationJob()
    yield
    runner._job = runner.MigrationJob()


def _session(db):
    return lambda: db


def test_claim_refuses_second_operation():
    runner.claim(runner.KIND_DRY_RUN)
    with pytest.raises(RuntimeError):
        runner.claim(runner.KIND_APPLY)


async def test_dry_run_job_saves_report(db_session):
    seed_world(db_session)
    job = runner.claim(runner.KIND_DRY_RUN)

    await runner.run_dry_run(job, session_factory=_session(db_session), jira_factory=lambda db: dc_world())

    assert (job.state, job.error) == ("done", None)
    assert job.counters["worklogs_read"] == 5
    row = store.latest_report(db_session)
    assert row.status == store.STATUS_DONE
    assert store.report_data(row)["offset_hours"] == 3
    assert store.report_maps(row)["issues"]["OS-91030"] == "258783"


async def test_dry_run_job_records_probe_failure(db_session):
    seed_world(db_session)
    job = runner.claim(runner.KIND_DRY_RUN)

    await runner.run_dry_run(
        job, session_factory=_session(db_session),
        jira_factory=lambda db: dc_world(fail={"get_projects"}),
    )

    assert job.state == "error" and "Список проектов" in job.error
    row = store.latest_report(db_session)
    assert row.status == store.STATUS_FAILED
    assert any(p["code"] == "projects" and not p["ok"] for p in store.report_data(row)["probe"])


async def test_dry_run_job_without_credentials(db_session):
    def no_credentials(db):
        raise JiraClientError("Missing Jira credentials")

    job = runner.claim(runner.KIND_DRY_RUN)
    await runner.run_dry_run(job, session_factory=_session(db_session), jira_factory=no_credentials)

    assert job.state == "error"
    assert job.error.startswith("Новая Jira недоступна")
    assert store.latest_report(db_session).status == store.STATUS_FAILED


async def test_apply_job_commits_and_starts_full_sync(db_session, monkeypatch):
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))
    full_sync = AsyncMock(return_value="run-1")
    monkeypatch.setattr(runner, "run_full_sync", full_sync)
    job = runner.claim(runner.KIND_APPLY)

    await runner.run_apply(
        job, backup_confirmed=True, session_factory=_session(db_session),
        jira_factory=lambda db: FakeJira(),
    )

    assert job.state == "done"
    assert job.counters["issues_deleted"] == 2
    assert get_migration_state(db_session) == STATE_DONE
    full_sync.assert_awaited_once()
    assert full_sync.await_args.args[2] == date(2026, 9, 9)


async def test_apply_job_refused_keeps_database(db_session, monkeypatch):
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=30))
    full_sync = AsyncMock()
    monkeypatch.setattr(runner, "run_full_sync", full_sync)
    job = runner.claim(runner.KIND_APPLY)

    await runner.run_apply(
        job, backup_confirmed=True, session_factory=_session(db_session),
        jira_factory=lambda db: FakeJira(),
    )

    assert job.state == "error" and "старше суток" in job.error
    assert get_migration_state(db_session) == STATE_PENDING
    full_sync.assert_not_awaited()


async def test_full_sync_reloads_worklogs_from_earliest_date(db_session, monkeypatch):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    report_id = seed_report(db_session, {"probe": []}, {}, datetime.utcnow())
    captured: dict = {}

    async def fake_run(self, *, mode, trigger, team=None, run_id=None):
        captured["stages"] = self.stages
        captured["mode"] = mode
        return {"status": "ok", "stages": []}

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)

    run_id = await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    stage = next(s for s in captured["stages"] if isinstance(s, WorklogsFullStage))
    assert stage.since == date(2020, 2, 26)
    assert captured["mode"] == "full"
    run = db_session.get(SyncRun, run_id)
    assert (run.status, run.mode, run.trigger) == ("ok", "full", "manual")
    assert db_session.get(JiraMigrationReport, report_id).sync_run_id == run_id
    assert SyncLock(db_session).current_run_id() is None


async def test_full_sync_skipped_while_other_sync_runs(db_session):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    report_id = seed_report(db_session, {"probe": []}, {}, datetime.utcnow())
    SyncLock(db_session).acquire("other-run")

    result = await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    assert result is None
    assert db_session.get(JiraMigrationReport, report_id).sync_run_id is None


def test_post_check_latest(db_session):
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))
    with pytest.raises(ValueError):
        runner.post_check_latest(db_session, now=datetime(2026, 10, 15, 9, 0))
    row = store.latest_report(db_session)
    row.applied_at = datetime(2026, 10, 14, 13, 0)
    db_session.commit()

    result = runner.post_check_latest(db_session, now=datetime(2026, 10, 15, 9, 0))

    assert result["rows"][0]["db_hours"] == 1.0
    assert store.post_check_data(store.latest_report(db_session)) == result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_runner.py -v`
Expected: FAIL — `ImportError: cannot import name 'runner' from 'app.services.jira_migration'`.

- [ ] **Step 3: Runner**

`app/services/jira_migration/runner.py`:

```python
"""Фоновые операции переезда: пробный прогон, применение, полная синхронизация после.

Состояние операции — в памяти процесса, как у выгрузки базы (сервис
работает одним процессом); отчёт, итог применения и запуск синхронизации —
в базе. Операции запускаются через ``BackgroundTasks`` и идут после ответа.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.connectors.jira_client import JiraClient, JiraClientError
from app.database import SessionLocal
from app.services.jira_migration import store
from app.services.jira_migration.apply import ApplyRefused, apply_migration
from app.services.jira_migration.dry_run import DryRunAborted, build_report
from app.services.jira_migration.hours import post_check

logger = logging.getLogger(__name__)

KIND_DRY_RUN = "dry_run"
KIND_APPLY = "apply"
JOB_IDLE = "idle"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_ERROR = "error"
STEP_APPLY = "Перепривязка данных к новой Jira"
DEFAULT_WORKLOG_DAYS = 90

SessionFactory = Callable[[], Session]
JiraFactory = Callable[[Session], Any]


@dataclass
class MigrationJob:
    kind: Optional[str] = None
    state: str = JOB_IDLE
    step: Optional[str] = None
    counters: dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ponytail: состояние в памяти — сервис работает одним процессом uvicorn.
# Если появятся воркеры, переносить в базу.
_job = MigrationJob()
_lock = threading.Lock()


def current_job() -> MigrationJob:
    return _job


def is_running() -> bool:
    return _job.state == JOB_RUNNING


def claim(kind: str) -> MigrationJob:
    """Занять слот фоновой операции. Уже идёт другая — ``RuntimeError``."""
    global _job
    with _lock:
        if _job.state == JOB_RUNNING:
            raise RuntimeError("Уже идёт другая операция переезда — дождитесь её окончания")
        _job = MigrationJob(kind=kind, state=JOB_RUNNING, started_at=datetime.utcnow())
        return _job


def _progress(job: MigrationJob) -> Callable[..., None]:
    def update(step: str, counters: Optional[dict] = None) -> None:
        job.step = step
        if counters:
            job.counters.update(counters)
    return update


def _finish(job: MigrationJob, error: Optional[str] = None) -> None:
    job.state = JOB_ERROR if error else JOB_DONE
    job.error = error
    job.step = None
    job.finished_at = datetime.utcnow()


def worklogs_since(report: dict) -> date:
    """С какой даты перечитать ворклоги: самая ранняя дата в базе до переезда, днём раньше."""
    raw = report.get("db_worklogs_min_date")
    start = date.fromisoformat(raw) if raw else date.today() - timedelta(days=DEFAULT_WORKLOG_DAYS)
    return start - timedelta(days=1)


async def run_dry_run(
    job: MigrationJob,
    *,
    session_factory: SessionFactory = SessionLocal,
    jira_factory: JiraFactory = JiraClient.from_db,
) -> None:
    """Пробный прогон в фоне: отчёт в базу, ход — в ``job``."""
    db = session_factory()
    report_id: Optional[str] = None
    try:
        report_id = store.start_report(db, datetime.utcnow())
        async with jira_factory(db) as jira:
            result = await build_report(db, jira, now=datetime.utcnow(), progress=_progress(job))
        store.finish_report(db, report_id, result.report, result.maps, datetime.utcnow())
        _finish(job)
    except DryRunAborted as exc:
        db.rollback()
        store.fail_report(db, report_id, str(exc), datetime.utcnow(), report=exc.report)
        _finish(job, str(exc))
    except JiraClientError as exc:
        db.rollback()
        message = f"Новая Jira недоступна: {exc}"
        store.fail_report(db, report_id, message, datetime.utcnow())
        _finish(job, message)
    except Exception as exc:  # noqa: BLE001 — состояние операции отражает любую поломку
        logger.exception("Пробный прогон переезда не удался")
        db.rollback()
        message = str(exc) or "Пробный прогон не удался"
        store.fail_report(db, report_id, message, datetime.utcnow())
        _finish(job, message)
    finally:
        db.close()


async def run_apply(
    job: MigrationJob,
    *,
    backup_confirmed: bool,
    session_factory: SessionFactory = SessionLocal,
    jira_factory: JiraFactory = JiraClient.from_db,
) -> None:
    """Применение в фоне; после фиксации — полная синхронизация всех ворклогов.

    Перепривязка идёт в отдельном потоке: десятки секунд записи в базу не
    должны останавливать остальные запросы сервиса. Операция считается
    завершённой сразу после фиксации — ход синхронизации виден по её запуску.
    """
    db = session_factory()
    try:
        job.step = STEP_APPLY
        summary = await asyncio.to_thread(
            apply_migration, db, now=datetime.utcnow(), backup_confirmed=backup_confirmed,
        )
        row = store.latest_report(db)
        report_id = row.id
        since = worklogs_since(store.report_data(row))
        job.counters.update({key: value for key, value in summary.items() if isinstance(value, int)})
        _finish(job)
        await run_full_sync(db, report_id, since, jira_factory=jira_factory)
    except ApplyRefused as exc:
        _finish(job, "Нельзя применить: " + "; ".join(exc.blockers))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Применение переезда не удалось")
        if job.state == JOB_RUNNING:
            _finish(job, f"Применение не удалось, база не изменилась: {exc}")
    finally:
        db.close()


async def run_full_sync(
    db: Session,
    report_id: str,
    worklogs_since_date: date,
    *,
    jira_factory: JiraFactory = JiraClient.from_db,
) -> Optional[str]:
    """Полная синхронизация задач и всех ворклогов из новой Jira после применения.

    Обычный конвейер «полный», но ворклоги — с самой ранней даты списаний в
    базе до переезда, а не за 90 дней: применение удалило их все. Запуск —
    как у синхронизации по расписанию: блокировка, запись в историю. Идёт
    другая синхронизация — не запускается (``None``).
    """
    from app.repositories.sync_run import SyncRunRepository
    from app.services.event_bus import get_event_bus
    from app.services.mapping_service import MappingService
    from app.services.production_calendar_service import ProductionCalendarService
    from app.services.sync_lock import SyncLock
    from app.services.sync_pipeline import PipelineOrchestrator, WorklogsFullStage, build_pipeline
    from app.services.sync_service import SyncService

    lock = SyncLock(db)
    if lock.current_run_id() and not lock.is_stale():
        logger.warning("Полная синхронизация после переезда не запущена: идёт другая синхронизация")
        return None
    runs = SyncRunRepository(db)
    run_id = runs.create(mode="full", trigger="manual").id
    if not lock.acquire(run_id):
        runs.finalize(run_id, status="skipped", stages=[], error_text="lock contention")
        return None
    store.set_sync_run(db, report_id, run_id)
    try:
        async with jira_factory(db) as jira:
            sync_service = SyncService(db, jira)
            stages = [
                WorklogsFullStage(sync_service, since=worklogs_since_date)
                if isinstance(stage, WorklogsFullStage) else stage
                for stage in build_pipeline(
                    mode="full",
                    services={
                        "sync": sync_service,
                        "calendar": ProductionCalendarService(db),
                        "mapping": MappingService(db),
                    },
                )
            ]
            result = await PipelineOrchestrator(stages=stages, db=db, bus=get_event_bus()).run(
                mode="full", trigger="manual", run_id=run_id,
            )
        runs.finalize(
            run_id, status=result["status"], stages=result.get("stages", []), error_text=result.get("error"),
        )
    except Exception as exc:  # noqa: BLE001 — запуск в истории должен получить итог
        logger.exception("Полная синхронизация после переезда упала")
        db.rollback()
        runs.finalize(run_id, status="failed", stages=[], error_text=str(exc))
    finally:
        lock.release()
    return run_id


async def restart_full_sync(
    *,
    session_factory: SessionFactory = SessionLocal,
    jira_factory: JiraFactory = JiraClient.from_db,
) -> None:
    """Повтор полной синхронизации после применения (не стартовала или упала)."""
    db = session_factory()
    try:
        row = store.latest_report(db)
        if row is None or row.applied_at is None:
            return
        await run_full_sync(db, row.id, worklogs_since(store.report_data(row)), jira_factory=jira_factory)
    finally:
        db.close()


def post_check_latest(db: Session, *, now: datetime) -> dict:
    """Сверка после: часы базы сейчас против новой Jira из отчёта. Сохраняется в отчёт."""
    row = store.latest_report(db)
    if row is None or row.applied_at is None:
        raise ValueError("Сверка доступна после применения переезда")
    result = post_check(db, store.report_data(row), now)
    store.save_post_check(db, row.id, result)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/jira_migration/test_runner.py -v`
Expected: PASS (9 tests).

Run: `ruff check app/services/jira_migration/runner.py tests/services/jira_migration/test_runner.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/runner.py tests/services/jira_migration/test_runner.py
git commit -m "feat(jira-migration): фоновые операции и полная синхронизация всех ворклогов после переезда" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6 (добавлено координатором): продление блокировки во время многочасовой полной синхронизации**

Проблема: `SyncLock` считается устаревшим через 60 минут после `started_at`, а полная синхронизация всех ворклогов после переезда идёт часами — синк по расписанию стартует поверх неё. Решение: метод `SyncLock.heartbeat(run_id)` переписывает `started_at` на текущее время, если блокировка принадлежит `run_id`; `runner.run_full_sync` вызывает его перед каждой стадией конвейера (и внутри стадии ворклогов не реже раза в 10 минут, если стадия даёт колбэк прогресса — иначе только между стадиями).

Тест в `tests/services/test_sync_lock.py` (создать, если файла нет):

```python
from datetime import datetime, timedelta

from app.services.sync_lock import SyncLock


def test_heartbeat_keeps_own_lock_fresh(db_session):
    lock = SyncLock(db_session)
    assert lock.acquire("run-1")
    lock._set_started_at(datetime.utcnow() - timedelta(minutes=90))
    assert lock.is_stale()
    lock.heartbeat("run-1")
    assert not lock.is_stale()
    assert lock.current_run_id() == "run-1"


def test_heartbeat_ignores_foreign_lock(db_session):
    lock = SyncLock(db_session)
    assert lock.acquire("run-1")
    old = datetime.utcnow() - timedelta(minutes=90)
    lock._set_started_at(old)
    lock.heartbeat("run-2")
    assert lock.is_stale()
```

Реализация в `app/services/sync_lock.py`:

```python
    def heartbeat(self, run_id: str) -> None:
        """Продлевает свою блокировку: долгий прогон не должен считаться зависшим."""
        payload = self._payload()
        if not payload or payload.get("run_id") != run_id:
            return
        payload["started_at"] = datetime.utcnow().isoformat()
        self._write(payload)
```

В `runner.run_full_sync` перед запуском каждой стадии: `SyncLock(db).heartbeat(run_id)`. Добавить в `tests/services/jira_migration/test_runner.py` тест, что после прогона с подменённой медленной стадией блокировка не устарела (через `_set_started_at` в прошлое перед второй стадией и проверку `is_stale() is False` после).

Run: `py -3.10 -m pytest tests/services/test_sync_lock.py tests/services/jira_migration/test_runner.py -v` → PASS.

Commit: `git add app/services/sync_lock.py app/services/jira_migration/runner.py tests/services/test_sync_lock.py tests/services/jira_migration/test_runner.py` и `git commit -m "fix(sync): продление блокировки во время полной синхронизации после переезда" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

---

### Task 11: Эндпоинты `/admin/jira-migration`

**Files:**
- Create: `app/services/jira_migration/overview.py`
- Create: `app/api/endpoints/jira_migration.py`
- Modify: `app/api/router.py:6-12` (импорт), `:302-307` (подключение после `admin_perf`)
- Test: `tests/api/test_jira_migration_api.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_jira_migration_api.py`:

```python
"""Страница «Переезд на новую Jira»: доступ, запуск прогона, решения, применение."""
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import User, UserRole
from app.services.jira_migration import runner
from app.services.jira_migration.state import STATE_DONE, STATE_PENDING, set_migration_state
from tests.services.jira_migration.fake_jira import FakeJira, dc_user
from tests.services.jira_migration.ready import seed_ready

BASE = "/api/v1/admin/jira-migration"


@pytest.fixture(autouse=True)
def fresh_job():
    runner._job = runner.MigrationJob()
    yield
    runner._job = runner.MigrationJob()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def ready(db_session):
    return seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))


def _pending(db):
    set_migration_state(db, STATE_PENDING)
    db.commit()


@pytest.mark.no_auth_bypass
def test_only_admin(testclient_db_session):
    for role, expected in ((UserRole.manager, 403), (UserRole.admin, 200)):
        email = f"jm_{role.value}_{uuid.uuid4().hex[:8]}@example.com"
        testclient_db_session.add(User(
            id=str(uuid.uuid4()), email=email, password_hash=hash_password("pass123"),
            display_name="Проверка доступа", role=role,
        ))
        testclient_db_session.commit()
        app.dependency_overrides[get_db] = lambda: testclient_db_session
        try:
            http = TestClient(app)
            login = http.post("/api/v1/auth/login", json={"email": email, "password": "pass123"})
            token = login.json()["access_token"]
            assert http.get(BASE, headers={"Authorization": f"Bearer {token}"}).status_code == expected
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_overview_without_report(client, db_session):
    _pending(db_session)

    body = client.get(BASE).json()

    assert body["migration_state"] == "pending"
    assert body["report"] is None
    assert body["blockers"] == ["Пробный прогон ещё не запускался"]
    assert body["backup_command"] == "docker compose exec postgres-backup /backup.sh"
    assert body["job"]["state"] == "idle"


def test_dry_run_started_once(client, db_session):
    _pending(db_session)
    with patch.object(runner, "run_dry_run", AsyncMock()) as run:
        first = client.post(f"{BASE}/dry-run")
        second = client.post(f"{BASE}/dry-run")

    assert first.status_code == 202
    assert first.json()["state"] == "running"
    assert second.status_code == 409
    run.assert_awaited_once()


def test_dry_run_refused_after_migration(client, db_session):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    assert client.post(f"{BASE}/dry-run").status_code == 409


def test_person_decision_roundtrip(client, ready):
    resp = client.put(f"{BASE}/decisions", json={
        "kind": "person", "item_key": ready["sidorov"],
        "decision": {"action": "bind", "key": "JIRAUSER8", "name": "Sidorov_S", "display_name": "Сидоров Сидор"},
    })
    assert resp.status_code == 200

    body = client.get(BASE).json()
    people = {p["employee_id"]: p for p in body["report"]["people"]}
    assert people[ready["sidorov"]]["final"]["key"] == "JIRAUSER8"
    assert [i["key"] for i in body["report"]["issues"]["missing_with_data"]] == ["OS-2", "OS-3"]
    assert body["unresolved"] == {"fields": 0, "issues": 0, "people": 0}
    assert body["blockers"] == []
    assert 0.9 <= body["report"]["age_hours"] <= 1.1

    client.put(f"{BASE}/decisions", json={"kind": "person", "item_key": ready["sidorov"], "decision": None})
    people = {p["employee_id"]: p for p in client.get(BASE).json()["report"]["people"]}
    assert people[ready["sidorov"]]["final"]["unresolved"] is True


def test_bad_decisions_rejected(client, ready):
    bad_shape = client.put(f"{BASE}/decisions", json={
        "kind": "issue", "item_key": "OS-2", "decision": {"action": "archive"},
    })
    present_in_dc = client.put(f"{BASE}/decisions", json={
        "kind": "issue", "item_key": "OS-91030", "decision": {"action": "delete"},
    })
    unknown_field = client.put(f"{BASE}/decisions", json={
        "kind": "field", "item_key": "customfield_11526", "decision": {"dc_field_id": "customfield_404"},
    })
    assert (bad_shape.status_code, present_in_dc.status_code, unknown_field.status_code) == (422, 422, 422)


def test_decisions_locked_while_operation_runs(client, ready):
    runner.claim(runner.KIND_DRY_RUN)
    resp = client.put(f"{BASE}/decisions", json={
        "kind": "issue", "item_key": "OS-3", "decision": {"action": "delete"},
    })
    assert resp.status_code == 409


def test_apply_needs_backup_tick(client, ready):
    resp = client.post(f"{BASE}/apply", json={"backup_confirmed": False})
    assert resp.status_code == 409
    assert "копия базы" in resp.json()["detail"]


def test_apply_starts_job(client, ready):
    with patch.object(runner, "run_apply", AsyncMock()) as run:
        resp = client.post(f"{BASE}/apply", json={"backup_confirmed": True})

    assert resp.status_code == 202
    run.assert_awaited_once()
    assert run.await_args.kwargs == {"backup_confirmed": True}


def test_post_check_only_after_apply(client, ready):
    assert client.post(f"{BASE}/post-check").status_code == 409


def test_full_sync_restart_only_after_apply(client, ready):
    assert client.post(f"{BASE}/full-sync").status_code == 409


def test_dc_user_search(client, db_session):
    fake = FakeJira(users=[dc_user("JIRAUSER7", "Petrov_P", "Петров Пётр")])
    with patch("app.api.endpoints.jira_migration.JiraClient.from_db", return_value=fake):
        resp = client.get(f"{BASE}/dc-users", params={"q": "Петров"})

    assert resp.status_code == 200
    assert resp.json() == [
        {"key": "JIRAUSER7", "name": "Petrov_P", "display_name": "Петров Пётр", "email": None},
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/api/test_jira_migration_api.py -v`
Expected: FAIL — все запросы отвечают 404 (роутера нет).

- [ ] **Step 3: Overview**

`app/services/jira_migration/overview.py`:

```python
"""Ответ страницы «Переезд на новую Jira»: состояние, отчёт с решениями, препятствия."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from app.models import SyncRun
from app.services.jira_migration import runner, store
from app.services.jira_migration.issues import classify_missing
from app.services.jira_migration.resolution import Resolution, collect_blockers, resolve
from app.services.jira_migration.state import get_migration_state

BACKUP_COMMAND = "docker compose exec postgres-backup /backup.sh"
INTERRUPTED = "Прогон прерван — сервис перезапускался. Запустите его заново."
DELETABLE_SAMPLE = 50


def iso(dt: Optional[datetime]) -> Optional[str]:
    """Наивное UTC-время базы → ISO с «Z», чтобы браузер не принял его за местное."""
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None


def job_dict(job: runner.MigrationJob) -> dict[str, Any]:
    return {
        "kind": job.kind,
        "state": job.state,
        "step": job.step,
        "counters": dict(job.counters),
        "error": job.error,
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
    }


def _sections(res: Resolution) -> dict[str, Any]:
    report = res.report
    fields = []
    for row in report.get("fields", []):
        cloud_id = row["cloud_id"]
        final_id = res.fields.mapping.get(cloud_id)
        fields.append({
            "cloud_id": cloud_id,
            "cloud_name": row.get("cloud_name") or cloud_id,
            "labels": row.get("labels", []),
            "suggested_id": row.get("suggested_id"),
            "suggested_name": row.get("suggested_name"),
            "decision": res.field_decisions.get(cloud_id),
            "final_id": final_id,
            "final_name": res.fields.names.get(final_id) if final_id else None,
            "auto_only": bool(row.get("auto_only")),
            "unresolved": cloud_id in res.fields.unresolved,
        })
    people = []
    for row in report.get("people", []):
        outcome = res.people.get(row["employee_id"])
        people.append({
            **row,
            "decision": res.person_decisions.get(row["employee_id"]),
            "final": outcome.to_dict() if outcome else None,
        })
    issues_report = report.get("issues", {})
    issues = {
        "db_total": issues_report.get("db_total", 0),
        "matched": issues_report.get("matched", 0),
        "new_in_dc": issues_report.get("new_in_dc", 0),
        "missing_total": len(issues_report.get("missing", [])),
        "deletable_total": len(res.deletable),
        "deletable_sample": res.deletable[:DELETABLE_SAMPLE],
        "missing_with_data": [
            {**item, "decision": res.issue_decisions.get(item["key"])} for item in res.with_data
        ],
    }
    return {
        "fields": fields,
        "dc_fields": report.get("dc_fields", []),
        "projects": report.get("projects", []),
        "issues": issues,
        "people": people,
        "hours": report.get("hours", {}),
        "offset_hours": report.get("offset_hours"),
        "offset_matches": report.get("offset_matches"),
        "offset_sample": report.get("offset_sample"),
    }


def build_overview(db: Session, *, now: datetime) -> dict[str, Any]:
    row = store.latest_report(db)
    res = resolve(db, row) if row is not None else None
    report_out: Optional[dict[str, Any]] = None
    if row is not None:
        status, error = row.status, row.error
        if status == store.STATUS_RUNNING and not runner.is_running():
            status, error = store.STATUS_FAILED, INTERRUPTED
        data = res.report if res is not None else store.report_data(row)
        report_out = {
            "status": status,
            "error": error,
            "started_at": iso(row.started_at),
            "finished_at": iso(row.finished_at),
            "age_hours": round((now - row.finished_at).total_seconds() / 3600, 1) if row.finished_at else None,
            "probe": data.get("probe", []),
        }
        if res is not None:
            report_out.update(_sections(res))
    sync_run = None
    if row is not None and row.sync_run_id:
        run = db.get(SyncRun, row.sync_run_id)
        if run is not None:
            sync_run = {
                "id": run.id, "status": run.status, "started_at": iso(run.started_at),
                "finished_at": iso(run.finished_at), "error": run.error_text,
            }
    return {
        "migration_state": get_migration_state(db),
        "job": job_dict(runner.current_job()),
        "report": report_out,
        "unresolved": res.counts() if res is not None else {"fields": 0, "issues": 0, "people": 0},
        "blockers": collect_blockers(
            db, now=now, backup_confirmed=True, job_running=runner.is_running(), resolution=res,
        ),
        "backup_command": BACKUP_COMMAND,
        "applied_at": iso(row.applied_at) if row is not None else None,
        "apply_summary": store.apply_summary(row),
        "sync_run": sync_run,
        "post_check": store.post_check_data(row),
    }


def check_decision_target(
    db: Session, kind: str, item_key: str, decision: Optional[Mapping[str, Any]],
) -> None:
    """Решение относится к пункту последнего успешного отчёта. Нет — ``ValueError``."""
    row = store.latest_report(db)
    if row is None or row.status != store.STATUS_DONE:
        raise ValueError("Сначала нужен успешный пробный прогон")
    data = store.report_data(row)
    if kind == store.KIND_FIELD:
        if item_key not in {r["cloud_id"] for r in data.get("fields", [])}:
            raise ValueError("Такого поля нет в отчёте")
        chosen = decision.get("dc_field_id") if decision else None
        if chosen and chosen not in {f["id"] for f in data.get("dc_fields", [])}:
            raise ValueError("Такого поля нет в новой Jira")
    elif kind == store.KIND_ISSUE:
        _, with_data = classify_missing(db, data.get("issues", {}).get("missing", []))
        if item_key not in {item["key"] for item in with_data}:
            raise ValueError("По этой задаче решение не нужно")
    elif kind == store.KIND_PERSON:
        if item_key not in {r["employee_id"] for r in data.get("people", [])}:
            raise ValueError("Такого сотрудника нет в отчёте")
    else:
        raise ValueError("Неизвестный вид решения")
```

- [ ] **Step 4: Endpoints and router**

`app/api/endpoints/jira_migration.py`:

```python
"""Страница «Переезд на новую Jira» (только администратор).

Пробный прогон и применение — фоновые операции: ответ 202 сразу, ход —
в ``GET`` (страница опрашивает его, пока операция идёт).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.connectors.jira_client import JiraClient, JiraClientError
from app.core.auth_deps import require_admin
from app.database import get_db
from app.models.user import User
from app.services.jira_migration import overview, runner, store
from app.services.jira_migration.resolution import collect_blockers
from app.services.jira_migration.state import STATE_DONE, get_migration_state
from app.services.sync_lock import SyncLock

router = APIRouter()


class DecisionIn(BaseModel):
    kind: Literal["field", "issue", "person"]
    item_key: str
    decision: Optional[dict[str, Any]] = None


class ApplyIn(BaseModel):
    backup_confirmed: bool = False


class DcUserOut(BaseModel):
    key: str
    name: Optional[str] = None
    display_name: str
    email: Optional[str] = None


@router.get("")
def get_overview(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return overview.build_overview(db, now=datetime.utcnow())


@router.post("/dry-run", status_code=202)
def start_dry_run(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    if get_migration_state(db) == STATE_DONE:
        raise HTTPException(status_code=409, detail="Переезд уже выполнен")
    try:
        job = runner.claim(runner.KIND_DRY_RUN)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(runner.run_dry_run, job)
    return overview.job_dict(job)


@router.put("/decisions")
def put_decision(
    body: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, bool]:
    if get_migration_state(db) == STATE_DONE:
        raise HTTPException(status_code=409, detail="Переезд уже выполнен — решения больше не меняются")
    if runner.is_running():
        raise HTTPException(status_code=409, detail="Идёт операция переезда — решения можно менять после неё")
    try:
        overview.check_decision_target(db, body.kind, body.item_key, body.decision)
        store.set_decision(db, body.kind, body.item_key, body.decision, user.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/dc-users", response_model=list[DcUserOut])
async def search_dc_users(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DcUserOut]:
    """Поиск пользователя новой Jira по ФИО или логину — для ручной привязки сотрудника."""
    try:
        async with JiraClient.from_db(db) as jira:
            users = await jira.search_users(q, max_results=20)
    except JiraClientError as exc:
        raise HTTPException(status_code=502, detail=f"Новая Jira не ответила: {exc}") from exc
    return [
        DcUserOut(key=u.jira_account_id, name=u.name, display_name=u.display_name, email=u.email)
        for u in users
    ]


@router.post("/apply", status_code=202)
def start_apply(
    body: ApplyIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    blockers = collect_blockers(
        db, now=datetime.utcnow(), backup_confirmed=body.backup_confirmed, job_running=runner.is_running(),
    )
    if blockers:
        raise HTTPException(status_code=409, detail="Нельзя применить: " + "; ".join(blockers))
    try:
        job = runner.claim(runner.KIND_APPLY)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(runner.run_apply, job, backup_confirmed=True)
    return overview.job_dict(job)


@router.post("/full-sync", status_code=202)
def restart_full_sync(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, bool]:
    """Повтор полной синхронизации со всеми ворклогами (если первая не стартовала или упала)."""
    row = store.latest_report(db)
    if get_migration_state(db) != STATE_DONE or row is None or row.applied_at is None:
        raise HTTPException(status_code=409, detail="Доступно только после применения переезда")
    lock = SyncLock(db)
    if lock.current_run_id() and not lock.is_stale():
        raise HTTPException(status_code=409, detail="Синхронизация уже идёт")
    background_tasks.add_task(runner.restart_full_sync)
    return {"ok": True}


@router.post("/post-check")
def run_post_check(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    try:
        return runner.post_check_latest(db, now=datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
```

In `app/api/router.py` after `from app.api.endpoints import admin_users as admin_users_endpoints` (line 12) add:

```python
from app.api.endpoints import jira_migration as jira_migration_endpoints
```

and after the block

```python
api_router.include_router(
    admin_perf_endpoints.router,
    prefix="/admin/perf",
    tags=["admin-perf"],
    dependencies=_admin_dep,
)
```

add:

```python
api_router.include_router(
    jira_migration_endpoints.router,
    prefix="/admin/jira-migration",
    tags=["admin-jira-migration"],
    dependencies=_admin_dep,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/api/test_jira_migration_api.py -v`
Expected: PASS (12 tests).

Run: `py -3.10 -m pytest tests/services/jira_migration tests/api/test_sync_blocked_endpoints.py tests/api/test_admin_errors.py -q`
Expected: PASS.

Run: `ruff check app/ tests/`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add app/services/jira_migration/overview.py app/api/endpoints/jira_migration.py app/api/router.py tests/api/test_jira_migration_api.py
git commit -m "feat(jira-migration): эндпоинты страницы переезда для администратора" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Проверка на Postgres

Применение — массовые обновления, внешние ключи и JSONB; SQLite в тестах внешние ключи не проверяет. Перед выпуском — тот же набор на Postgres 16 (порт 55432 на этой машине запрещён Windows — свой контейнер на 15432; Docker Desktop должен быть запущен).

**Files:** (без изменений кода, если всё зелёное)

- [ ] **Step 1: Поднять Postgres**

```bash
docker run -d --name jm-test-pg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=jira_analytics_test -p 15432:5432 --tmpfs /var/lib/postgresql/data postgres:16-alpine
for i in $(seq 1 30); do docker exec jm-test-pg pg_isready -U test -d jira_analytics_test && break; sleep 1; done
```

Expected: `... accepting connections`.

- [ ] **Step 2: Прогнать тесты переезда и цепочку миграций**

```bash
TEST_DATABASE_URL=postgresql://test:test@localhost:15432/jira_analytics_test py -3.10 -m pytest tests/services/jira_migration tests/api/test_jira_migration_api.py tests/test_migrations_fresh_db.py tests/services/test_jira_migration_state.py -v
```

Expected: PASS, в том числе `test_upgrade_head_on_empty_postgres` (цепочка с `dc03_jira_migration_tables`) и все тесты `test_apply.py` (пересечения id, удаление задач с внешними ключами, откат).

Если падает — чинить код (не тесты), повторить шаг, закоммитить исправление:

```bash
git branch --show-current   # feature/jira-dc-migration
git add <исправленные файлы>
git commit -m "fix(jira-migration): совместимость с Postgres" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Убрать контейнер**

```bash
docker rm -f jm-test-pg
```

---

### Task 13: Фронт — API, хуки, подписи и форматирование

**Files:**
- Create: `frontend/src/api/jiraMigration.ts`
- Create: `frontend/src/hooks/useJiraMigration.ts`
- Create: `frontend/src/utils/jiraMigration.ts`
- Test: `frontend/src/utils/jiraMigration.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/utils/jiraMigration.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import type { FieldRow, HoursRow, PersonFinal, PersonRow } from '../api/jiraMigration';
import {
  candidateLabel, fieldStatus, filterPeople, formatDiff, personBindingText,
} from './jiraMigration';

const field = (over: Partial<FieldRow> = {}): FieldRow => ({
  cloud_id: 'customfield_1', cloud_name: 'Поле', labels: [], suggested_id: null,
  suggested_name: null, decision: null, final_id: null, final_name: null,
  auto_only: false, unresolved: true, ...over,
});

const final = (over: Partial<PersonFinal> = {}): PersonFinal => ({
  key: null, name: null, display_name: null, source: 'none', unresolved: false, note: null, ...over,
});

const person = (over: Partial<PersonRow> = {}): PersonRow => ({
  employee_id: 'e1', display_name: 'Иванов Иван', worklogs: 0, matched: 0,
  status: 'not_found', candidates: [], auto: null, decision: null, final: null, ...over,
});

const hours = (over: Partial<HoursRow> = {}): HoursRow => ({
  team: 'Команда А', month: '2026-09', db_hours: 10, dc_hours: 10, diff_pct: 0,
  flagged: false, ...over,
});

describe('fieldStatus', () => {
  it('ручное решение', () => {
    expect(fieldStatus(field({ decision: { dc_field_id: 'customfield_2' } })).label).toBe('Выбрано вручную');
    expect(fieldStatus(field({ decision: { dc_field_id: null } })).label).toBe('Не используется');
  });
  it('предложение, автопоиск и нужно решение', () => {
    expect(fieldStatus(field({ suggested_id: 'customfield_2' })).label).toBe('Совпало по названию');
    expect(fieldStatus(field({ auto_only: true })).label).toBe('Найдётся само');
    expect(fieldStatus(field()).label).toBe('Нужно решение');
  });
});

describe('personBindingText', () => {
  it('привязка с логином', () => {
    const row = person({ final: final({ key: 'JIRAUSER5', name: 'Ivanov_I', display_name: 'Иванов Иван', source: 'auto' }) });
    expect(personBindingText(row)).toBe('Иванов Иван (Ivanov_I)');
  });
  it('без привязки и нужно решение', () => {
    expect(personBindingText(person({ final: final({ source: 'decision' }) }))).toBe('Без привязки');
    expect(personBindingText(person({ final: final({ unresolved: true }) }))).toBe('Нужно решение');
  });
});

describe('filterPeople', () => {
  const rows = [
    person({ employee_id: 'a', status: 'by_hours', final: final({ key: 'K1', source: 'auto' }) }),
    person({ employee_id: 'b', status: 'by_name', final: final({ key: 'K2', source: 'auto' }) }),
    person({ employee_id: 'c', status: 'not_found', final: final({ unresolved: true }) }),
    person({ employee_id: 'd', status: 'not_found', final: final({ source: 'decision' }) }),
  ];
  const ids = (list: PersonRow[]) => list.map((r) => r.employee_id);
  it('по признакам', () => {
    expect(ids(filterPeople(rows, 'attention'))).toEqual(['c']);
    expect(ids(filterPeople(rows, 'by_hours'))).toEqual(['a']);
    expect(ids(filterPeople(rows, 'by_name'))).toEqual(['b']);
    expect(ids(filterPeople(rows, 'unbound'))).toEqual(['d']);
    expect(filterPeople(rows, 'all')).toHaveLength(4);
  });
});

describe('formatDiff', () => {
  it('знак, дробь и пустые месяцы', () => {
    expect(formatDiff(hours({ diff_pct: 2.5 }))).toBe('+2,5 %');
    expect(formatDiff(hours({ diff_pct: -1 }))).toBe('−1 %');
    expect(formatDiff(hours({ diff_pct: 0 }))).toBe('0 %');
    expect(formatDiff(hours({ db_hours: 0, dc_hours: 0 }))).toBe('—');
  });
});

describe('candidateLabel', () => {
  it('ФИО и логин', () => {
    expect(candidateLabel({ display_name: 'Петров Пётр', name: 'Petrov_P' })).toBe('Петров Пётр (Petrov_P)');
    expect(candidateLabel({ display_name: 'Петров Пётр', name: null })).toBe('Петров Пётр');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (из `frontend/`): `npx vitest run src/utils/jiraMigration.test.ts`
Expected: FAIL — `Failed to resolve import "./jiraMigration"`.

- [ ] **Step 3: API module**

`frontend/src/api/jiraMigration.ts`:

```ts
import { api } from './client';

export type JobKind = 'dry_run' | 'apply';
export type JobState = 'idle' | 'running' | 'done' | 'error';
export type PersonStatus = 'by_hours' | 'by_name' | 'disputed' | 'not_found';
export type IssueAction = 'delete' | 'keep';

export interface MigrationJob {
  kind: JobKind | null;
  state: JobState;
  step: string | null;
  counters: Record<string, number>;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ProbeItem {
  code: string;
  title: string;
  essential: boolean;
  ok: boolean;
  detail: string;
}

export interface DcField {
  id: string;
  name: string;
  custom: boolean;
}

export interface FieldDecision {
  dc_field_id: string | null;
}

export interface FieldRow {
  cloud_id: string;
  cloud_name: string;
  labels: string[];
  suggested_id: string | null;
  suggested_name: string | null;
  decision: FieldDecision | null;
  final_id: string | null;
  final_name: string | null;
  auto_only: boolean;
  unresolved: boolean;
}

export interface DcUserRef {
  key: string;
  name: string | null;
  display_name: string;
}

export interface PersonCandidate extends DcUserRef {
  votes: number;
}

export type PersonDecision =
  | { action: 'bind'; key: string; name: string | null; display_name: string }
  | { action: 'unbind' };

export interface PersonFinal {
  key: string | null;
  name: string | null;
  display_name: string | null;
  source: 'auto' | 'decision' | 'none';
  unresolved: boolean;
  note: string | null;
}

export interface PersonRow {
  employee_id: string;
  display_name: string;
  worklogs: number;
  matched: number;
  status: PersonStatus;
  candidates: PersonCandidate[];
  auto: DcUserRef | null;
  decision: PersonDecision | null;
  final: PersonFinal | null;
}

export interface MissingIssue {
  key: string;
  summary: string;
  reasons: string[];
  decision: { action: IssueAction } | null;
}

export interface IssuesSummary {
  db_total: number;
  matched: number;
  new_in_dc: number;
  missing_total: number;
  deletable_total: number;
  deletable_sample: string[];
  missing_with_data: MissingIssue[];
}

export interface HoursRow {
  team: string;
  month: string;
  db_hours: number;
  dc_hours: number;
  diff_pct: number;
  flagged: boolean;
}

export interface HoursSummary {
  rows: HoursRow[];
  db_worklogs: number;
  dc_worklogs: number;
  dc_worklogs_total: number;
}

export interface MigrationReport {
  status: 'running' | 'done' | 'failed';
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  age_hours: number | null;
  probe: ProbeItem[];
  fields?: FieldRow[];
  dc_fields?: DcField[];
  projects?: { key: string; found: boolean }[];
  issues?: IssuesSummary;
  people?: PersonRow[];
  hours?: HoursSummary;
  offset_hours?: number | null;
  offset_matches?: number | null;
  offset_sample?: number | null;
}

export interface PostCheck {
  checked_at: string;
  db_worklogs: number;
  dc_worklogs: number;
  rows: HoursRow[];
}

export interface SyncRunBrief {
  id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface MigrationOverview {
  migration_state: 'pending' | 'done';
  job: MigrationJob;
  report: MigrationReport | null;
  unresolved: { fields: number; issues: number; people: number };
  blockers: string[];
  backup_command: string;
  applied_at: string | null;
  apply_summary: Record<string, unknown> | null;
  sync_run: SyncRunBrief | null;
  post_check: PostCheck | null;
}

export interface DcUserOut {
  key: string;
  name: string | null;
  display_name: string;
  email: string | null;
}

export type DecisionBody =
  | { kind: 'field'; item_key: string; decision: FieldDecision | null }
  | { kind: 'issue'; item_key: string; decision: { action: IssueAction } | null }
  | { kind: 'person'; item_key: string; decision: PersonDecision | null };

const BASE = '/admin/jira-migration';

export const jiraMigrationApi = {
  overview: () => api.get<MigrationOverview>(BASE),
  startDryRun: () => api.post<MigrationJob>(`${BASE}/dry-run`, {}),
  setDecision: (body: DecisionBody) => api.put<{ ok: boolean }>(`${BASE}/decisions`, body),
  searchUsers: (q: string) => api.get<DcUserOut[]>(`${BASE}/dc-users`, { q }),
  apply: (backupConfirmed: boolean) =>
    api.post<MigrationJob>(`${BASE}/apply`, { backup_confirmed: backupConfirmed }),
  restartFullSync: () => api.post<{ ok: boolean }>(`${BASE}/full-sync`, {}),
  postCheck: () => api.post<PostCheck>(`${BASE}/post-check`, {}),
};
```

- [ ] **Step 4: Utils**

`frontend/src/utils/jiraMigration.ts`:

```ts
import type { FieldRow, HoursRow, PersonRow, PersonStatus } from '../api/jiraMigration';

export const PERSON_STATUS_LABEL: Record<PersonStatus, string> = {
  by_hours: 'По списаниям',
  by_name: 'По ФИО',
  disputed: 'Спорно',
  not_found: 'Не найден',
};

export const PERSON_STATUS_COLOR: Record<PersonStatus, string> = {
  by_hours: 'green',
  by_name: 'blue',
  disputed: 'orange',
  not_found: 'red',
};

// Те же подписи, что в истории запусков на странице синхронизации.
export const SYNC_STATUS_LABEL: Record<string, string> = {
  ok: 'Успешно',
  partial: 'Частично',
  failed: 'Ошибка',
  cancelled: 'Прерван',
  running: 'Выполняется',
  skipped: 'Пропущен',
};

export const SYNC_STATUS_COLOR: Record<string, string> = {
  ok: 'success',
  partial: 'warning',
  failed: 'error',
  cancelled: 'default',
  running: 'processing',
  skipped: 'default',
};

export type PeopleFilter = 'attention' | 'all' | 'by_hours' | 'by_name' | 'unbound';

export function fieldStatus(row: FieldRow): { label: string; color: string } {
  if (row.decision) {
    return row.decision.dc_field_id
      ? { label: 'Выбрано вручную', color: 'blue' }
      : { label: 'Не используется', color: 'default' };
  }
  if (row.suggested_id) return { label: 'Совпало по названию', color: 'green' };
  if (row.auto_only) return { label: 'Найдётся само', color: 'default' };
  return { label: 'Нужно решение', color: 'red' };
}

export function candidateLabel(user: { display_name: string; name: string | null }): string {
  return user.name ? `${user.display_name} (${user.name})` : user.display_name;
}

export function personBindingText(row: PersonRow): string {
  const final = row.final;
  if (!final || !final.key) return final?.unresolved ? 'Нужно решение' : 'Без привязки';
  return candidateLabel({ display_name: final.display_name ?? final.key, name: final.name });
}

export function filterPeople(rows: PersonRow[], filter: PeopleFilter): PersonRow[] {
  switch (filter) {
    case 'attention':
      return rows.filter((r) => r.final?.unresolved);
    case 'by_hours':
      return rows.filter((r) => r.status === 'by_hours');
    case 'by_name':
      return rows.filter((r) => r.status === 'by_name');
    case 'unbound':
      return rows.filter((r) => r.final && !r.final.unresolved && !r.final.key);
    default:
      return rows;
  }
}

export function formatHours(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 1 });
}

export function formatDiff(row: HoursRow): string {
  if (row.db_hours === 0 && row.dc_hours === 0) return '—';
  const value = Math.abs(row.diff_pct).toLocaleString('ru-RU', { maximumFractionDigits: 1 });
  const sign = row.diff_pct > 0 ? '+' : row.diff_pct < 0 ? '−' : '';
  return `${sign}${value} %`;
}

export function fmtDateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString('ru-RU') : '—';
}
```

- [ ] **Step 5: Hooks**

`frontend/src/hooks/useJiraMigration.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { jiraMigrationApi } from '../api/jiraMigration';
import type { DecisionBody, MigrationOverview } from '../api/jiraMigration';

export const MIGRATION_QUERY_KEY = ['admin', 'jira-migration'] as const;

/** Состояние переезда; пока идёт операция или синхронизация — обновляется само. */
export function useMigrationOverview() {
  return useQuery<MigrationOverview>({
    queryKey: MIGRATION_QUERY_KEY,
    queryFn: () => jiraMigrationApi.overview(),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      if (data.job.state === 'running') return 2000;
      if (data.sync_run?.status === 'running') return 15000;
      return false;
    },
  });
}

function useInvalidateOverview() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: MIGRATION_QUERY_KEY });
}

export function useStartDryRun() {
  const invalidate = useInvalidateOverview();
  return useMutation({ mutationFn: () => jiraMigrationApi.startDryRun(), onSuccess: () => invalidate() });
}

export function useSetDecision() {
  const invalidate = useInvalidateOverview();
  return useMutation({
    mutationFn: (body: DecisionBody) => jiraMigrationApi.setDecision(body),
    onSuccess: () => invalidate(),
  });
}

export function useApplyMigration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (backupConfirmed: boolean) => jiraMigrationApi.apply(backupConfirmed),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MIGRATION_QUERY_KEY });
      qc.invalidateQueries({ queryKey: ['ui-config', 'jira-migration-state'] });
    },
  });
}

export function useRestartFullSync() {
  const invalidate = useInvalidateOverview();
  return useMutation({ mutationFn: () => jiraMigrationApi.restartFullSync(), onSuccess: () => invalidate() });
}

export function usePostCheck() {
  const invalidate = useInvalidateOverview();
  return useMutation({ mutationFn: () => jiraMigrationApi.postCheck(), onSuccess: () => invalidate() });
}

/** Поиск пользователя новой Jira для ручной привязки (от двух букв). */
export function useDcUserSearch(query: string) {
  const q = query.trim();
  return useQuery({
    queryKey: ['admin', 'jira-migration', 'dc-users', q],
    queryFn: () => jiraMigrationApi.searchUsers(q),
    enabled: q.length >= 2,
    staleTime: 60_000,
  });
}
```

- [ ] **Step 6: Run checks**

Run (из `frontend/`): `npx vitest run src/utils/jiraMigration.test.ts`
Expected: PASS (7 tests).

Run: `npx tsc -b`
Expected: без ошибок.

Run: `npx eslint src/api/jiraMigration.ts src/hooks/useJiraMigration.ts src/utils/jiraMigration.ts src/utils/jiraMigration.test.ts`
Expected: без ошибок.

- [ ] **Step 7: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add frontend/src/api/jiraMigration.ts frontend/src/hooks/useJiraMigration.ts frontend/src/utils/jiraMigration.ts frontend/src/utils/jiraMigration.test.ts
git commit -m "feat(jira-migration): фронт — запросы и подписи страницы переезда" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Фронт — вкладки «Проверка Jira», «Поля», «Задачи», «Часы»

**Files:**
- Create: `frontend/src/components/settings/jiraMigration/ProbeSection.tsx`
- Create: `frontend/src/components/settings/jiraMigration/FieldsSection.tsx`
- Create: `frontend/src/components/settings/jiraMigration/IssuesSection.tsx`
- Create: `frontend/src/components/settings/jiraMigration/HoursSection.tsx`

- [ ] **Step 1: Probe section**

`frontend/src/components/settings/jiraMigration/ProbeSection.tsx`:

```tsx
import { Table, Tag, Typography } from 'antd';
import type { ProbeItem } from '../../../api/jiraMigration';

export default function ProbeSection({ items }: { items: ProbeItem[] }) {
  return (
    <>
      <Typography.Paragraph type="secondary">
        Каждый запрос, которым пользуется синхронизация, вызван в новой Jira хотя бы раз.
        Если не работает обязательный, отчёт не строится и применить переезд нельзя.
      </Typography.Paragraph>
      <Table<ProbeItem>
        rowKey="code"
        size="small"
        pagination={false}
        dataSource={items}
        columns={[
          { title: 'Проверка', dataIndex: 'title' },
          {
            title: 'Обязательная',
            dataIndex: 'essential',
            width: 130,
            render: (essential: boolean) => (essential ? 'Да' : 'Нет'),
          },
          {
            title: 'Результат',
            dataIndex: 'ok',
            width: 150,
            render: (ok: boolean, row) => {
              if (ok) return <Tag color="green">Работает</Tag>;
              return row.essential
                ? <Tag color="red">Не работает</Tag>
                : <Tag color="orange">Предупреждение</Tag>;
            },
          },
          { title: 'Подробности', dataIndex: 'detail' },
        ]}
      />
    </>
  );
}
```

- [ ] **Step 2: Fields section**

`frontend/src/components/settings/jiraMigration/FieldsSection.tsx`:

```tsx
import { App, Select, Table, Tag, Typography } from 'antd';
import type { DcField, FieldDecision, FieldRow } from '../../../api/jiraMigration';
import { useSetDecision } from '../../../hooks/useJiraMigration';
import { fieldStatus } from '../../../utils/jiraMigration';

const NOT_USED = '__not_used__';
const SUGGESTED = '__suggested__';

interface Props {
  rows: FieldRow[];
  dcFields: DcField[];
  readOnly: boolean;
}

export default function FieldsSection({ rows, dcFields, readOnly }: Props) {
  const { notification } = App.useApp();
  const setDecision = useSetDecision();

  const dcOptions = [
    { value: NOT_USED, label: 'Не использовать' },
    ...dcFields.map((f) => ({ value: f.id, label: f.custom ? f.name : `${f.name} (системное)` })),
  ];

  const save = (row: FieldRow, value: string) => {
    let decision: FieldDecision | null;
    if (value === SUGGESTED) decision = null;
    else if (value === NOT_USED) decision = { dc_field_id: null };
    else decision = { dc_field_id: value };
    setDecision.mutate(
      { kind: 'field', item_key: row.cloud_id, decision },
      { onError: (e) => notification.error({ title: 'Решение не сохранено', description: e.message }) },
    );
  };

  const valueOf = (row: FieldRow): string | undefined => {
    if (row.decision) return row.decision.dc_field_id ?? NOT_USED;
    return row.suggested_id ? SUGGESTED : undefined;
  };

  return (
    <>
      <Typography.Paragraph type="secondary">
        Номера полей в новой Jira другие. Сервис предлагает поле с тем же названием, что было
        в облаке. Если предложения нет или оно неверное — выберите поле из списка или
        «Не использовать».
      </Typography.Paragraph>
      <Table<FieldRow>
        rowKey="cloud_id"
        size="small"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: 'Поле в облаке', dataIndex: 'cloud_name' },
          { title: 'Для чего', dataIndex: 'labels', render: (labels: string[]) => labels.join(', ') },
          {
            title: 'Поле в новой Jira',
            key: 'choice',
            width: 360,
            render: (_: unknown, row) => (
              <Select
                style={{ width: '100%' }}
                showSearch
                optionFilterProp="label"
                placeholder="Выберите поле"
                disabled={readOnly || setDecision.isPending}
                value={valueOf(row)}
                options={
                  row.suggested_id
                    ? [{ value: SUGGESTED, label: `${row.suggested_name} (предложено)` }, ...dcOptions]
                    : dcOptions
                }
                onChange={(value: string) => save(row, value)}
              />
            ),
          },
          {
            title: 'Статус',
            key: 'status',
            width: 190,
            render: (_: unknown, row) => {
              const status = fieldStatus(row);
              return <Tag color={status.color}>{status.label}</Tag>;
            },
          },
        ]}
      />
    </>
  );
}
```

- [ ] **Step 3: Issues section**

`frontend/src/components/settings/jiraMigration/IssuesSection.tsx`:

```tsx
import { App, Card, Col, Radio, Row, Statistic, Table, Tag, Typography } from 'antd';
import type { IssueAction, IssuesSummary, MissingIssue } from '../../../api/jiraMigration';
import { useSetDecision } from '../../../hooks/useJiraMigration';

interface Props {
  summary?: IssuesSummary;
  readOnly: boolean;
}

export default function IssuesSection({ summary, readOnly }: Props) {
  const { notification } = App.useApp();
  const setDecision = useSetDecision();
  if (!summary) return null;

  const decide = (key: string, action: IssueAction) =>
    setDecision.mutate(
      { kind: 'issue', item_key: key, decision: { action } },
      { onError: (e) => notification.error({ title: 'Решение не сохранено', description: e.message }) },
    );

  const sample = summary.deletable_sample.slice(0, 10).join(', ');

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card size="small"><Statistic title="Задач в базе" value={summary.db_total} /></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Statistic title="Нашлись в новой Jira" value={summary.matched} /></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Statistic title="Новые в новой Jira" value={summary.new_in_dc} /></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Statistic title="Нет в новой Jira" value={summary.missing_total} /></Card></Col>
      </Row>
      <Typography.Paragraph type="secondary">
        Задачи, которых нет в новой Jira и по которым в сервисе ничего не заводили вручную,
        при применении удаляются: {summary.deletable_total}
        {sample ? ` (например: ${sample})` : ''}. Новые задачи придут полной синхронизацией
        после применения.
      </Typography.Paragraph>
      <Typography.Title level={5}>Нужно решение: исчезнувшие задачи с данными сервиса</Typography.Title>
      <Table<MissingIssue>
        rowKey="key"
        size="small"
        dataSource={summary.missing_with_data}
        pagination={{ pageSize: 50, showSizeChanger: false }}
        locale={{ emptyText: 'Таких задач нет' }}
        columns={[
          { title: 'Задача', dataIndex: 'key', width: 120 },
          { title: 'Название', dataIndex: 'summary' },
          {
            title: 'Что есть в сервисе',
            dataIndex: 'reasons',
            render: (reasons: string[]) => reasons.map((r) => <Tag key={r}>{r}</Tag>),
          },
          {
            title: 'Решение',
            key: 'decision',
            width: 220,
            render: (_: unknown, row) => (
              <Radio.Group
                optionType="button"
                size="small"
                disabled={readOnly || setDecision.isPending}
                value={row.decision?.action}
                onChange={(e) => decide(row.key, e.target.value as IssueAction)}
                options={[
                  { value: 'keep', label: 'Оставить' },
                  { value: 'delete', label: 'Удалить' },
                ]}
              />
            ),
          },
        ]}
      />
    </>
  );
}
```

- [ ] **Step 4: Hours section**

`frontend/src/components/settings/jiraMigration/HoursSection.tsx`:

```tsx
import { Alert, Table, Tag, Typography } from 'antd';
import type { HoursRow, HoursSummary, PostCheck } from '../../../api/jiraMigration';
import { fmtDateTime, formatDiff, formatHours } from '../../../utils/jiraMigration';

interface Props {
  hours?: HoursSummary;
  offsetHours: number | null;
  offsetMatches: number;
  offsetSample: number;
  postCheck: PostCheck | null;
}

function HoursTable({ rows, dbTitle, dcTitle }: { rows: HoursRow[]; dbTitle: string; dcTitle: string }) {
  return (
    <Table<HoursRow>
      rowKey={(r) => `${r.team}|${r.month}`}
      size="small"
      dataSource={rows}
      pagination={{ pageSize: 50, showSizeChanger: false }}
      columns={[
        { title: 'Месяц', dataIndex: 'month', width: 110 },
        { title: 'Команда', dataIndex: 'team' },
        { title: dbTitle, dataIndex: 'db_hours', align: 'right', render: (v: number) => formatHours(v) },
        { title: dcTitle, dataIndex: 'dc_hours', align: 'right', render: (v: number) => formatHours(v) },
        {
          title: 'Разница',
          key: 'diff',
          width: 120,
          align: 'right',
          render: (_: unknown, row) =>
            row.flagged ? <Tag color="red">{formatDiff(row)}</Tag> : formatDiff(row),
        },
      ]}
    />
  );
}

export default function HoursSection({ hours, offsetHours, offsetMatches, offsetSample, postCheck }: Props) {
  if (!hours) return null;
  const flagged = hours.rows.filter((r) => r.flagged).length;
  const offsetText =
    offsetHours === null
      ? ''
      : ` Время в базе отличается от новой Jira на ${offsetHours > 0 ? '+' : ''}${offsetHours} ч `
        + `(совпало ${offsetMatches} из ${offsetSample} проверенных списаний).`;

  return (
    <>
      <Typography.Paragraph type="secondary">
        Часы по командам и месяцам: сколько списано в базе сервиса и сколько по тем же задачам
        списано в новой Jira. Расхождение больше 1 % подсвечено.
      </Typography.Paragraph>
      <Typography.Paragraph>
        Списаний в базе: {hours.db_worklogs.toLocaleString('ru-RU')}; в новой Jira по задачам
        базы: {hours.dc_worklogs.toLocaleString('ru-RU')} (всего в новой Jira —{' '}
        {hours.dc_worklogs_total.toLocaleString('ru-RU')}).{offsetText}
      </Typography.Paragraph>
      {flagged > 0 && (
        <Alert type="warning" showIcon title={`Расхождений больше 1 %: ${flagged}`} style={{ marginBottom: 12 }} />
      )}
      <HoursTable rows={hours.rows} dbTitle="В базе" dcTitle="В новой Jira" />
      {postCheck && (
        <>
          <Typography.Title level={5} style={{ marginTop: 24 }}>
            Сверка после переезда ({fmtDateTime(postCheck.checked_at)})
          </Typography.Title>
          <Typography.Paragraph type="secondary">
            Часы в базе сейчас против часов новой Jira на момент пробного прогона. Небольшая
            разница в текущем месяце — новые списания после прогона.
          </Typography.Paragraph>
          <HoursTable rows={postCheck.rows} dbTitle="В базе сейчас" dcTitle="В новой Jira (прогон)" />
        </>
      )}
    </>
  );
}
```

- [ ] **Step 5: Run checks**

Run (из `frontend/`): `npx tsc -b`
Expected: без ошибок.

Run: `npx eslint src/components/settings/jiraMigration`
Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add frontend/src/components/settings/jiraMigration/ProbeSection.tsx frontend/src/components/settings/jiraMigration/FieldsSection.tsx frontend/src/components/settings/jiraMigration/IssuesSection.tsx frontend/src/components/settings/jiraMigration/HoursSection.tsx
git commit -m "feat(jira-migration): фронт — проверка Jira, поля, задачи, часы" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Фронт — «Сотрудники», «Применить», раздел в настройках и маршрут

**Files:**
- Create: `frontend/src/components/settings/jiraMigration/PeopleSection.tsx`
- Create: `frontend/src/components/settings/jiraMigration/ApplySection.tsx`
- Create: `frontend/src/components/settings/jiraMigration/JiraMigrationTab.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx:46-50` (импорт), `:91-102` (группа «Администрирование»)
- Modify: `frontend/src/routes.tsx:63` (маршрут рядом с `settings`)

- [ ] **Step 1: People section**

`frontend/src/components/settings/jiraMigration/PeopleSection.tsx`:

```tsx
import { useState } from 'react';
import { App, Button, Modal, Segmented, Select, Space, Table, Tag, Typography } from 'antd';
import type { DcUserRef, PersonDecision, PersonRow } from '../../../api/jiraMigration';
import { useDcUserSearch, useSetDecision } from '../../../hooks/useJiraMigration';
import {
  PERSON_STATUS_COLOR, PERSON_STATUS_LABEL, candidateLabel, filterPeople, personBindingText,
} from '../../../utils/jiraMigration';
import type { PeopleFilter } from '../../../utils/jiraMigration';

const { Paragraph, Text } = Typography;

const FILTERS: { value: PeopleFilter; label: string }[] = [
  { value: 'attention', label: 'Нужно решение' },
  { value: 'all', label: 'Все' },
  { value: 'by_hours', label: 'По списаниям' },
  { value: 'by_name', label: 'По ФИО' },
  { value: 'unbound', label: 'Без привязки' },
];

function PersonModal({ row, onClose }: { row: PersonRow; onClose: () => void }) {
  const { notification } = App.useApp();
  const setDecision = useSetDecision();
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<string | undefined>(undefined);
  const search = useDcUserSearch(query);

  const users: DcUserRef[] = [
    ...row.candidates.map(({ key, name, display_name }) => ({ key, name, display_name })),
    ...(search.data ?? [])
      .filter((u) => !row.candidates.some((c) => c.key === u.key))
      .map(({ key, name, display_name }) => ({ key, name, display_name })),
  ];

  const save = (decision: PersonDecision | null) =>
    setDecision.mutate(
      { kind: 'person', item_key: row.employee_id, decision },
      {
        onSuccess: onClose,
        onError: (e) => notification.error({ title: 'Решение не сохранено', description: e.message }),
      },
    );

  const bind = () => {
    const user = users.find((u) => u.key === picked);
    if (user) save({ action: 'bind', key: user.key, name: user.name, display_name: user.display_name });
  };

  return (
    <Modal open title={`Привязка: ${row.display_name}`} onCancel={onClose} footer={null} destroyOnHidden>
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Text type="secondary">
          Выберите пользователя новой Jira — из кандидатов или поиском по ФИО либо логину.
        </Text>
        <Select
          style={{ width: '100%' }}
          showSearch
          filterOption={false}
          placeholder="ФИО или логин"
          value={picked}
          onChange={setPicked}
          onSearch={setQuery}
          loading={search.isFetching}
          options={users.map((u) => ({ value: u.key, label: candidateLabel(u) }))}
          notFoundContent={query.trim().length < 2 ? 'Введите хотя бы две буквы' : 'Никого не нашли'}
        />
        <Space wrap>
          <Button type="primary" disabled={!picked} loading={setDecision.isPending} onClick={bind}>
            Привязать
          </Button>
          <Button loading={setDecision.isPending} onClick={() => save({ action: 'unbind' })}>
            Оставить без привязки
          </Button>
          {row.decision && (
            <Button type="link" onClick={() => save(null)}>
              Вернуть автоматический вариант
            </Button>
          )}
        </Space>
      </Space>
    </Modal>
  );
}

export default function PeopleSection({ rows, readOnly }: { rows: PersonRow[]; readOnly: boolean }) {
  const [filter, setFilter] = useState<PeopleFilter>('attention');
  const [editing, setEditing] = useState<PersonRow | null>(null);
  const shown = filterPeople(rows, filter);

  return (
    <>
      <Paragraph type="secondary">
        Сотрудник находится в новой Jira по совпавшим списаниям (та же задача, то же время
        начала, та же длительность), а если списаний нет — по точному совпадению ФИО. Спорных
        и ненайденных выберите вручную или оставьте без привязки: история сотрудника в сервисе
        сохранится, но новые списания к нему приходить не будут. Один пользователь новой Jira
        может быть привязан только к одному сотруднику.
      </Paragraph>
      <Segmented<PeopleFilter> options={FILTERS} value={filter} onChange={setFilter} style={{ marginBottom: 12 }} />
      <Table<PersonRow>
        rowKey="employee_id"
        size="small"
        dataSource={shown}
        pagination={{ pageSize: 50, showSizeChanger: false }}
        columns={[
          { title: 'Сотрудник', dataIndex: 'display_name' },
          { title: 'Списаний в базе', dataIndex: 'worklogs', width: 130, align: 'right' },
          { title: 'Совпало', dataIndex: 'matched', width: 100, align: 'right' },
          {
            title: 'Как найден',
            dataIndex: 'status',
            width: 140,
            render: (status: PersonRow['status']) => (
              <Tag color={PERSON_STATUS_COLOR[status]}>{PERSON_STATUS_LABEL[status]}</Tag>
            ),
          },
          {
            title: 'Кандидаты',
            dataIndex: 'candidates',
            render: (candidates: PersonRow['candidates']) =>
              candidates.length === 0
                ? <Text type="secondary">—</Text>
                : candidates
                    .map((c) => `${candidateLabel(c)}${c.votes ? ` — ${c.votes}` : ''}`)
                    .join('; '),
          },
          {
            title: 'Привязка',
            key: 'final',
            render: (_: unknown, row) => (
              <Space orientation="vertical" size={0}>
                <Text type={row.final?.unresolved ? 'danger' : undefined}>{personBindingText(row)}</Text>
                {row.final?.note && (
                  <Text type="secondary" style={{ fontSize: 12 }}>{row.final.note}</Text>
                )}
              </Space>
            ),
          },
          {
            title: '',
            key: 'edit',
            width: 110,
            render: (_: unknown, row) => (
              <Button size="small" disabled={readOnly} onClick={() => setEditing(row)}>
                Изменить
              </Button>
            ),
          },
        ]}
      />
      {editing && <PersonModal row={editing} onClose={() => setEditing(null)} />}
    </>
  );
}
```

- [ ] **Step 2: Apply section**

`frontend/src/components/settings/jiraMigration/ApplySection.tsx`:

```tsx
import { useState } from 'react';
import { Link } from 'react-router';
import { Alert, App, Button, Checkbox, Descriptions, Popconfirm, Space, Tag, Typography } from 'antd';
import type { MigrationOverview } from '../../../api/jiraMigration';
import { useApplyMigration, usePostCheck, useRestartFullSync } from '../../../hooks/useJiraMigration';
import { SYNC_STATUS_COLOR, SYNC_STATUS_LABEL, fmtDateTime } from '../../../utils/jiraMigration';

const { Paragraph, Text } = Typography;

export default function ApplySection({ overview }: { overview: MigrationOverview }) {
  const { notification } = App.useApp();
  const [backup, setBackup] = useState(false);
  const apply = useApplyMigration();
  const restartSync = useRestartFullSync();
  const postCheck = usePostCheck();

  const done = overview.migration_state === 'done';
  const running = overview.job.state === 'running';
  const sync = overview.sync_run;
  const syncRunning = sync?.status === 'running';

  if (done) {
    return (
      <Space orientation="vertical" size="middle" style={{ width: '100%', maxWidth: 900 }}>
        <Alert
          type="success"
          showIcon
          title="Переезд применён"
          description={`База переведена на новую Jira ${fmtDateTime(overview.applied_at)}. Синхронизация снова работает.`}
        />
        <Descriptions bordered size="small" column={1}>
          <Descriptions.Item label="Полная синхронизация">
            <Space wrap>
              {sync
                ? <Tag color={SYNC_STATUS_COLOR[sync.status] ?? 'default'}>{SYNC_STATUS_LABEL[sync.status] ?? sync.status}</Tag>
                : <Text type="secondary">Не запускалась</Text>}
              <Link to="/sync">Открыть историю синхронизаций</Link>
            </Space>
          </Descriptions.Item>
          {sync?.error && <Descriptions.Item label="Ошибка">{sync.error}</Descriptions.Item>}
        </Descriptions>
        <Paragraph type="secondary">
          Полная синхронизация после переезда загружает задачи и все списания с самой ранней даты,
          что была в сервисе. Если она не стартовала или упала, запустите её отсюда: обычный
          «полный» режим на странице синхронизации грузит списания только за последние 90 дней.
        </Paragraph>
        <Space wrap>
          <Button
            disabled={syncRunning}
            loading={restartSync.isPending}
            onClick={() =>
              restartSync.mutate(undefined, {
                onSuccess: () => notification.info({ title: 'Полная синхронизация запущена' }),
                onError: (e) => notification.error({ title: 'Не удалось запустить', description: e.message }),
              })
            }
          >
            Запустить полную синхронизацию заново
          </Button>
          <Button
            type="primary"
            disabled={syncRunning}
            loading={postCheck.isPending}
            onClick={() =>
              postCheck.mutate(undefined, {
                onSuccess: () =>
                  notification.success({ title: 'Сверка готова', description: 'Результат — на вкладке «Часы».' }),
                onError: (e) => notification.error({ title: 'Сверка не удалась', description: e.message }),
              })
            }
          >
            Сверка после
          </Button>
        </Space>
      </Space>
    );
  }

  const blocked = overview.blockers.length > 0;

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%', maxWidth: 900 }}>
      {blocked ? (
        <Alert
          type="warning"
          showIcon
          title="Применить пока нельзя"
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {overview.blockers.map((b) => <li key={b}>{b}</li>)}
            </ul>
          }
        />
      ) : (
        <Alert type="success" showIcon title="Отчёт готов к применению" />
      )}
      <Paragraph style={{ marginBottom: 0 }}>
        Перед применением сисадмин делает свежую копию базы — на сервере, в папке сервиса:
      </Paragraph>
      <Text code copyable>{overview.backup_command}</Text>
      <Paragraph type="secondary">
        Если после применения что-то пойдёт не так, базу возвращают из этой копии.
      </Paragraph>
      <Checkbox checked={backup} disabled={running} onChange={(e) => setBackup(e.target.checked)}>
        Свежая копия базы сделана
      </Checkbox>
      <Paragraph>
        «Применить» за один шаг переводит задачи, проекты, сотрудников и настройки полей на новую
        Jira, удаляет задачи по решениям, а все списания и комментарии — они вернутся
        синхронизацией. Затем сама запускается полная синхронизация. Если на любом шаге случится
        ошибка, база не изменится.
      </Paragraph>
      <Popconfirm
        title="Применить переезд?"
        description="Отменить можно только восстановлением копии базы."
        okText="Применить"
        cancelText="Отмена"
        disabled={!backup || blocked || running}
        onConfirm={() =>
          apply.mutate(backup, {
            onSuccess: () => notification.info({ title: 'Применение запущено', description: 'Ход обновляется сам.' }),
            onError: (e) => notification.error({ title: 'Не удалось применить', description: e.message }),
          })
        }
      >
        <Button type="primary" danger disabled={!backup || blocked || running} loading={apply.isPending}>
          Применить
        </Button>
      </Popconfirm>
    </Space>
  );
}
```

- [ ] **Step 3: The tab**

`frontend/src/components/settings/jiraMigration/JiraMigrationTab.tsx`:

```tsx
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Alert, App, Badge, Button, Empty, Space, Spin, Tabs, Typography } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import type { MigrationJob } from '../../../api/jiraMigration';
import { useMigrationOverview, useStartDryRun } from '../../../hooks/useJiraMigration';
import { fmtDateTime } from '../../../utils/jiraMigration';
import ApplySection from './ApplySection';
import FieldsSection from './FieldsSection';
import HoursSection from './HoursSection';
import IssuesSection from './IssuesSection';
import PeopleSection from './PeopleSection';
import ProbeSection from './ProbeSection';

const { Paragraph, Text } = Typography;

const COUNTER_LABEL: Record<string, string> = {
  issues_read: 'задач прочитано',
  worklogs_read: 'списаний прочитано',
  people_checked: 'сотрудников проверено',
};

function JobProgress({ job }: { job: MigrationJob }) {
  const counters = Object.entries(job.counters)
    .filter(([key]) => key in COUNTER_LABEL)
    .map(([key, value]) => `${value.toLocaleString('ru-RU')} ${COUNTER_LABEL[key]}`);
  return (
    <Alert
      type="info"
      showIcon
      icon={<Spin size="small" />}
      title={job.kind === 'apply' ? 'Идёт применение переезда' : 'Идёт пробный прогон'}
      description={
        <>
          {job.step && <div>Этап: {job.step}</div>}
          {counters.length > 0 && <div>{counters.join(' · ')}</div>}
          <div>Страницу можно закрыть — работа продолжится.</div>
        </>
      }
    />
  );
}

function tabLabel(text: string, count: number) {
  return (
    <Badge count={count} size="small" offset={[10, 0]}>
      {text}
    </Badge>
  );
}

export default function JiraMigrationTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const overview = useMigrationOverview();
  const startDryRun = useStartDryRun();
  const data = overview.data;
  const migrationState = data?.migration_state;

  useEffect(() => {
    if (migrationState === 'done') {
      qc.invalidateQueries({ queryKey: ['ui-config', 'jira-migration-state'] });
    }
  }, [migrationState, qc]);

  if (overview.isLoading) return <Spin />;
  if (!data) return <Alert type="error" showIcon title="Не удалось загрузить состояние переезда" />;

  const report = data.report;
  const running = data.job.state === 'running';
  const done = data.migration_state === 'done';
  const ready = report?.status === 'done';
  const stale = (report?.age_hours ?? 0) > 24;
  const unresolved = data.unresolved;
  const firstOpen = unresolved.fields ? 'fields' : unresolved.issues ? 'issues' : unresolved.people ? 'people' : 'apply';

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        title="Переезд на новую Jira"
        description={
          <>
            <Paragraph style={{ marginBottom: 8 }}>
              Пробный прогон читает новую Jira и сравнивает её с базой сервиса: поля, задачи,
              сотрудников и часы. База при этом не меняется — сохраняется только отчёт.
            </Paragraph>
            <Paragraph style={{ marginBottom: 0 }}>
              Когда в отчёте не останется нерешённых пунктов и сисадмин сделает копию базы,
              «Применить» переведёт базу на новую Jira и запустит полную синхронизацию.
            </Paragraph>
          </>
        }
      />
      {done && (
        <Alert type="success" showIcon title="Переезд выполнен" description={`Применён ${fmtDateTime(data.applied_at)}`} />
      )}
      <Space wrap align="center">
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          disabled={done || running}
          loading={startDryRun.isPending}
          onClick={() =>
            startDryRun.mutate(undefined, {
              onError: (e) => notification.error({ title: 'Не удалось запустить пробный прогон', description: e.message }),
            })
          }
        >
          {report ? 'Запустить пробный прогон заново' : 'Запустить пробный прогон'}
        </Button>
        {report?.finished_at && (
          <Text type={stale && !done ? 'warning' : 'secondary'}>
            Последний прогон: {fmtDateTime(report.finished_at)}
            {stale && !done ? ' — старше суток, перед применением запустите заново' : ''}
          </Text>
        )}
      </Space>
      {running && <JobProgress job={data.job} />}
      {data.job.state === 'error' && data.job.error && (
        <Alert
          type="error"
          showIcon
          title={data.job.kind === 'apply' ? 'Применение не удалось' : 'Пробный прогон не удался'}
          description={data.job.error}
        />
      )}
      {report?.status === 'failed' && report.error && !running && data.job.state !== 'error' && (
        <Alert type="error" showIcon title="Последний пробный прогон завершился с ошибкой" description={report.error} />
      )}
      {!report && !running && <Empty description="Пробный прогон ещё не запускался" />}
      {report && !ready && report.probe.length > 0 && <ProbeSection items={report.probe} />}
      {ready && report && (
        <Tabs
          defaultActiveKey={firstOpen}
          items={[
            { key: 'probe', label: 'Проверка Jira', children: <ProbeSection items={report.probe} /> },
            {
              key: 'fields',
              label: tabLabel('Поля', unresolved.fields),
              children: <FieldsSection rows={report.fields ?? []} dcFields={report.dc_fields ?? []} readOnly={done} />,
            },
            {
              key: 'issues',
              label: tabLabel('Задачи', unresolved.issues),
              children: <IssuesSection summary={report.issues} readOnly={done} />,
            },
            {
              key: 'people',
              label: tabLabel('Сотрудники', unresolved.people),
              children: <PeopleSection rows={report.people ?? []} readOnly={done} />,
            },
            {
              key: 'hours',
              label: 'Часы',
              children: (
                <HoursSection
                  hours={report.hours}
                  offsetHours={report.offset_hours ?? null}
                  offsetMatches={report.offset_matches ?? 0}
                  offsetSample={report.offset_sample ?? 0}
                  postCheck={data.post_check}
                />
              ),
            },
            { key: 'apply', label: 'Применить', children: <ApplySection overview={data} /> },
          ]}
        />
      )}
    </Space>
  );
}
```

- [ ] **Step 4: Settings entry and route**

In `frontend/src/pages/SettingsPage.tsx` after `import PerformanceTab from '../components/settings/PerformanceTab';` add:

```tsx
import JiraMigrationTab from '../components/settings/jiraMigration/JiraMigrationTab';
```

and in the group «Администрирование» replace

```tsx
      { key: 'ai', label: 'AI', render: () => <AITab /> },
```

with

```tsx
      { key: 'jira-migration', label: 'Переезд на новую Jira', adminOnly: true, render: () => <JiraMigrationTab /> },
      { key: 'ai', label: 'AI', render: () => <AITab /> },
```

In `frontend/src/routes.tsx` after the line

```tsx
          { path: 'settings', element: <ProtectedRoute adminOnly>{page(<SettingsPage />)}</ProtectedRoute> },
```

add:

```tsx
          // Ссылка из плашки «синхронизация остановлена» — раздел переезда в настройках.
          {
            path: 'admin/jira-migration',
            element: <ProtectedRoute adminOnly><Navigate to="/settings#jira-migration" replace /></ProtectedRoute>,
          },
```

- [ ] **Step 5: Run checks**

Run (из `frontend/`): `npx tsc -b`
Expected: без ошибок.

Run: `npx eslint src/components/settings/jiraMigration src/pages/SettingsPage.tsx src/routes.tsx`
Expected: без ошибок.

Run: `npx vitest run src/utils/jiraMigration.test.ts`
Expected: PASS.

Run: `npm run build`
Expected: сборка без ошибок.

- [ ] **Step 6: Ручная проверка в браузере**

На локальной базе (`data/jira_analytics.db` — копия продакшна; после `alembic upgrade head` состояние переезда `pending`, миграция `dc01`) запустить бэкенд (`uvicorn app.main:app --port 8000`) и фронт (`npm run dev`). Под администратором:

1. Открыть `http://localhost:5173/admin/jira-migration` — открывается «Настройки → Переезд на новую Jira».
2. В разделе — пояснение, кнопка «Запустить пробный прогон», надпись «Пробный прогон ещё не запускался».
3. Плашка «Синхронизация остановлена…» на странице синхронизации ведёт сюда же.

Прогон против настоящей Jira с машины разработки недоступен (нет VPN) — отчёт проверяется на сервере (см. руководство, Task 16).

- [ ] **Step 7: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add frontend/src/components/settings/jiraMigration/PeopleSection.tsx frontend/src/components/settings/jiraMigration/ApplySection.tsx frontend/src/components/settings/jiraMigration/JiraMigrationTab.tsx frontend/src/pages/SettingsPage.tsx frontend/src/routes.tsx
git commit -m "feat(jira-migration): фронт — раздел «Переезд на новую Jira»" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Справка, руководство по переезду, документация модулей

**Files:**
- Modify: `docs/help/settings.md` (после раздела 3.21, перед `---` и «## 4. Откуда цифры»)
- Create: `docs/jira-dc-migration-runbook.md`
- Modify: `app/services/CLAUDE.md` (в конец), `app/api/CLAUDE.md` (таблица роутеров), `app/models/CLAUDE.md` (перед «### App state (1)»), `frontend/CLAUDE.md` (таблица страниц, группа «Администрирование»)

- [ ] **Step 1: Help section**

In `docs/help/settings.md` after the paragraph

```markdown
«Обновить» перечитывает данные. «Отчёт для разработки» скачивает файл с узкими местами и медленными запросами для передачи разработчикам; рядом — выгрузка тех же таблиц в Excel.
```

add:

```markdown

### 3.22. Переезд на новую Jira

Раздел только для администратора; нужен один раз — при переходе сервиса на собственный сервер Jira. Пока переезд не завершён, синхронизация с Jira остановлена (на страницах синхронизации, бэклога и стола тимлида — плашка со ссылкой сюда).

- **«Запустить пробный прогон»** — сервис читает новую Jira и сравнивает её с базой: поля, задачи, сотрудников, часы. Данные сервиса не меняются, сохраняется только отчёт. Прогон идёт десятки минут, страницу можно закрыть. Решения, принятые в отчёте, переживают повторный прогон.
- **«Проверка Jira»** — каждый запрос, нужный синхронизации, вызван хотя бы раз. Если не работает обязательный (проекты, поиск задач, поля, списания), отчёт не строится.
- **«Поля»** — для каждого поля из настроек предложено поле новой Jira с тем же названием. Нет предложения — выберите поле из списка или «Не использовать».
- **«Задачи»** — сколько задач нашлось, сколько новых, сколько исчезло. Исчезнувшие без данных сервиса при применении удаляются; с данными сервиса (бэклог, ручная категория или группа, ручные часы, отметки стола тимлида, утверждённый сценарий и т. п.) — выберите «Оставить» или «Удалить».
- **«Сотрудники»** — сотрудник находится по совпавшим списаниям, а без списаний — по точному ФИО. «Спорно» и «Не найден» — выберите пользователя или «Оставить без привязки»: история сохранится, новых списаний не будет. Один пользователь новой Jira — не больше одного сотрудника.
- **«Часы»** — часы по командам и месяцам в базе и в новой Jira; расхождение больше 1 % подсвечено.
- **«Применить»** — доступно, когда прогону меньше суток, нерешённых пунктов нет и отмечено «Свежая копия базы сделана» (команда для сисадмина — на вкладке). Применение — один шаг: ошибка на любом этапе оставляет базу как была. Затем сама запускается полная синхронизация всех списаний; ход виден в истории синхронизаций. После неё — «Сверка после»: часы в базе против новой Jira. Отменить применение можно только восстановлением копии базы.
```

- [ ] **Step 2: Runbook**

`docs/jira-dc-migration-runbook.md`:

```markdown
# Переезд на новую Jira — порядок действий

Для администратора сервиса и сисадмина. Выполняется один раз, после установки версии с поддержкой новой Jira. До завершения переезда синхронизация с Jira остановлена.

## 0. Что понадобится

- Адрес новой Jira и личный токен учётной записи, которая видит все проекты сервиса и все списания.
- Адрес и токен Confluence, если сервис его использует.
- Сисадмин с доступом к серверу сервиса (папка с `docker-compose.yml`).
- Окно 2–4 часа: применение — минуты, полная синхронизация после — часы.

## 1. Настройки

1. «Настройки → Подключение к Jira»: адрес и токен новой Jira → «Проверить».
2. Там же — адрес и токен Confluence.
3. **Настройки полей Jira до первого пробного прогона не менять.** Первый прогон запоминает облачные настройки полей — по ним предлагаются поля новой Jira.

## 2. Пробный прогон

«Настройки → Администрирование → Переезд на новую Jira» (прямая ссылка `/admin/jira-migration`) → «Запустить пробный прогон».

Прогон читает все списания новой Jira — это десятки минут. Ход виден на странице; страницу можно закрыть. Данные сервиса не меняются.

## 3. Разбор отчёта

- **Проверка Jira** — все обязательные строки «Работает». «Не работает» в обязательной — к администратору Jira (права учётной записи, доступ к проектам).
- **Поля** — проверить предложения; без предложения — выбрать поле или «Не использовать».
- **Задачи** — решить по каждой исчезнувшей задаче с данными сервиса: «Оставить» или «Удалить». Остальные исчезнувшие удалятся сами.
- **Сотрудники** — фильтр «Нужно решение»: выбрать пользователя (кандидаты или поиск) или «Оставить без привязки».
- **Часы** — посмотреть подсвеченные расхождения. Сдвиг времени облака должен быть около +3 ч, «совпало» — почти все проверенные списания.

Решения сохраняются сразу и переживают повторный прогон.

## 4. Свежий прогон

Если с последнего прогона прошло больше суток — запустить его заново. Решения сохранятся; новые спорные пункты, если появятся, будут на вкладках с отметкой.

## 5. Копия базы (сисадмин)

На сервере, в папке с `docker-compose.yml`:

    docker compose exec postgres-backup /backup.sh
    ls -lh ./backups/last/

Убедиться, что файл свежий (время — сейчас), и сообщить администратору. Подробности — `docs/backup-restore.md`.

## 6. Применить

Вкладка «Применить»: препятствий нет → галочка «Свежая копия базы сделана» → «Применить» → подтвердить.

Применение — один шаг: задачи, проекты, сотрудники и настройки полей переводятся на новую Jira, задачи удаляются по решениям, все списания и комментарии удаляются (вернутся синхронизацией), синхронизация разблокируется. Ошибка на любом этапе — база остаётся как была, текст ошибки — на странице.

## 7. Полная синхронизация

Стартует сама сразу после применения: задачи и все списания с самой ранней даты, что была в сервисе. Ход — «Синхронизация» → история запусков (или статус на вкладке «Применить»). Длится часы; в это время не запускать синхронизацию вручную.

Если не стартовала (шла другая) или упала — «Запустить полную синхронизацию заново» на вкладке «Применить». Не использовать вместо этого режим «Полный» на странице синхронизации: он грузит списания только за 90 дней.

## 8. Сверка после

Когда синхронизация закончилась — «Сверка после». Результат — вкладка «Часы», раздел «Сверка после переезда»: часы в базе сейчас против новой Jira на момент пробного прогона. Небольшая разница в текущем месяце — новые списания после прогона. Крупные расхождения в прошлых месяцах — разобрать (команда задачи, сотрудники без привязки).

## 9. Откат

Только восстановлением копии из шага 5 (сисадмин, `docs/backup-restore.md`, «Восстановление из бэкапа»):

    docker compose stop backend
    docker compose exec postgres dropdb -U app jira_analytics_prod
    docker compose exec postgres createdb -U app jira_analytics_prod
    gunzip -c ./backups/last/jira_analytics_prod-latest.sql.gz | docker compose exec -T postgres psql -U app -d jira_analytics_prod
    docker compose start backend

После восстановления сервис снова в состоянии «переезд не завершён», синхронизация остановлена; начать с шага 2.
```

- [ ] **Step 3: Module docs**

Append to the end of `app/services/CLAUDE.md`:

```markdown

## jira_migration ([jira_migration/](jira_migration/))

Переезд на Jira Data Center (страница `/admin/jira-migration`). `state.py` — блокировка синка (`pending`/`done`). Часть C:

- `fields.py` + `cloud_fields.py` — снимок облачных настроек полей (AppSetting `jira_migration_field_snapshot`, снимается один раз), предложение поля DC по точному названию (одноимённые — по роду поля), перезапись настроек и JSON плановых часов; `remap_plan_sources` сохраняет действующий выбор оценки (пересчёт отпечатка). Автокэши без поля DC удаляются.
- `fingerprints.py` — отпечаток ворклога (ключ, начало до минуты, секунды), смещение «настенного» времени облака (−12…+14 ч по максимуму совпадений), чтение всех ворклогов DC потоком.
- `people.py` — голосование (отпечаток единственный с обеих сторон; лидер ≥ 90 % и ≥ 3), точное ФИО, `finalize_people` — один пользователь DC на одного сотрудника.
- `issues.py` — `service_data_reasons` (служебные данные задачи — только заведённое человеком), `scan_issue_ids`.
- `probe.py` — проверка возможностей DC (обязательные: проекты, поиск, поля, ворклоги).
- `dry_run.py` → отчёт; `store.py` — таблицы `jira_migration_reports` / `jira_migration_decisions`; `resolution.py` — решения + препятствия (отчёт < 24 ч, нет нерешённых, нет новых сотрудников, галочка копии базы, `pending`).
- `apply.py` — одна транзакция: настройки → удаление ворклогов/комментариев → проекты → задачи (удаление по решениям, префикс `cloud:` всем, новые id по ключу) → кандидаты оценки → сотрудники (префикс; без привязки — остаются `cloud:<id>`) → id людей в задачах, бэклоге, фильтре стола тимлида, снимках KPI → scope → `done`. Любая ошибка — откат.
- `runner.py` — фоновые операции (состояние в памяти), полная синхронизация после применения: обычный конвейер «полный», но ворклоги с самой ранней даты в базе (`WorklogsFullStage(since=...)`), не за 90 дней.
```

In `app/api/CLAUDE.md` after the table row that starts with ``| `/admin/perf` |`` add:

```markdown
| `/admin/jira-migration` | `jira_migration.py` | **admin-only** — переезд на Jira DC: `GET` (состояние, отчёт с решениями, препятствия), `POST /dry-run` (фон, 202), `PUT /decisions` (`{kind: field\|issue\|person, item_key, decision}`), `GET /dc-users?q=`, `POST /apply` (`{backup_confirmed}`; фон, 202; 409 со списком препятствий), `POST /full-sync` (повтор полной синхронизации со всеми ворклогами), `POST /post-check` |
```

In `app/models/CLAUDE.md` before the line `### App state (1)` add:

```markdown
### Jira migration (2)

`JiraMigrationReport` (`jira_migration_reports`) — отчёт пробного прогона (`report_json` — для страницы, `maps_json` — ключ → id DC для применения), итог применения, запуск полной синхронизации, сверка после; новый прогон вытесняет прежний. `JiraMigrationDecision` (`jira_migration_decisions`, unique `kind`+`item_key`) — решения администратора; ключ — облачный id поля / ключ задачи / UUID сотрудника, переживают повторные прогоны (миграция `dc03_jira_migration_tables`). Обе таблицы вычищаются при сборке демо-базы.

```

In `frontend/CLAUDE.md`:

- after the Pages table row ``| `/settings` | `SettingsPage` | admin-only |`` add:

```markdown
| `/admin/jira-migration` | → `/settings#jira-migration` | переадресация из плашки «синхронизация остановлена» |
```

- replace the line

```markdown
- **Администрирование**: `ai` · `feedback` (admin) · `usage` (admin) · `whats-new` (admin) · `db-export` (admin)
```

with

```markdown
- **Администрирование**: `jira-migration` (admin, [`JiraMigrationTab`](src/components/settings/jiraMigration/JiraMigrationTab.tsx) — пробный прогон, вкладки отчёта с решениями, «Применить», полная синхронизация, сверка) · `ai` · `feedback` (admin) · `usage` (admin) · `whats-new` (admin) · `db-export` (admin)
```

- [ ] **Step 4: Commit**

```bash
git branch --show-current   # feature/jira-dc-migration
git add docs/help/settings.md docs/jira-dc-migration-runbook.md app/services/CLAUDE.md app/api/CLAUDE.md app/models/CLAUDE.md frontend/CLAUDE.md
git commit -m "docs(jira-migration): справка раздела и руководство по переезду" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Полный прогон

**Files:** (без изменений, если всё зелёное)

- [ ] **Step 1: Backend**

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py` (передний план, таймаут 600000 мс)
Expected: PASS.

Run: `ruff check app/ tests/`
Expected: `All checks passed!`

- [ ] **Step 2: Frontend** (из `frontend/`)

Run: `npx tsc -b && npx vitest run && npm run build`
Expected: без ошибок.

- [ ] **Step 3: Если что-то упало** — чинить причину, повторить шаги 1–2, закоммитить исправление отдельным коммитом (`git add <файлы>` + `git commit -m "fix(jira-migration): …" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`).

---

## Self-review (сделано при написании плана)

**Покрытие части C спеки:**

| Пункт спеки | Где |
|---|---|
| C1.1 Поля: снимок при первом прогоне, предложение по точному имени, константа, решение/«не использовать» | Task 2 (`fields.py`, `cloud_fields.py`), Task 7, Task 14 (`FieldsSection`) |
| C1.2 Проекты по ключу | Task 5 (`scan_issue_ids.projects`), Task 7 (`maps.projects`), Task 9 (`_rebind_projects`) |
| C1.3 Задачи: ключ → id, совпало / нет без данных / нет с данными / новые; служебные данные | Task 5, Task 8 (пересчёт при каждом обращении), Task 14 (`IssuesSection`) |
| C1.4 Сотрудники: все ворклоги DC, отпечаток, смещение −12…+14, по часам / спорно / по ФИО / не найден, «двое на одного» | Task 3, Task 4, Task 15 (`PeopleSection`) |
| C1.5 Часы по (команда, месяц), > 1 %, число ворклогов | Task 3 (`hours.py`), Task 7, Task 14 (`HoursSection`) |
| C1.6 Проверка возможностей | Task 6, Task 14 (`ProbeSection`) |
| Отчёт и решения в базе, решения переживают прогон | Task 1 |
| C2 Предусловия (< 24 ч, нет нерешённых, галочка, команда копии) | Task 8, Task 11, Task 15 (`ApplySection`) |
| C2 Одна транзакция: поля+JSON, автокэши, проекты, задачи (префикс, удаление), кандидаты оценки, сотрудники, люди в задачах/бэклоге/фильтре/KPI, удаление ворклогов и комментариев, `done` | Task 9 |
| Ошибка — откат | Task 9 (`test_failure_rolls_everything_back`), Task 12 (Postgres) |
| После — полная синхронизация, сверка часов | Task 10, Task 11, Task 15 |
| Фоновые операции с прогрессом по существующему шаблону | Task 10 (как `db_snapshot_service`: состояние в памяти + `BackgroundTasks`) |
| Страница в администрировании, только админ, маршрут `/admin/jira-migration` | Task 11 (роутер с `require_admin`), Task 15 |
| Проверка на SQLite и Postgres | Task 12 |

**Плейсхолдеров нет**; имена сквозные: `ensure_field_snapshot`, `build_field_rows`, `resolve_fields`, `rewrite_setting_value`, `remap_plan_sources`, `scan_dc_worklogs`, `detect_offset`, `vote_people`, `build_people_rows`, `finalize_people`, `service_data_reasons`, `classify_missing`, `scan_issue_ids`, `run_probe`, `build_report`, `resolve`, `collect_blockers`, `apply_migration`, `run_dry_run`, `run_apply`, `run_full_sync`, `restart_full_sync`, `post_check_latest`, `build_overview`, `check_decision_target`.

**Из плана 1 используются только перечисленные в его «Interfaces for the migration plan»** — плюс существующие (не меняемые планом 1) `build_pipeline`, `PipelineOrchestrator`, `WorklogsFullStage(since=…)`, `SyncLock`, `SyncRunRepository`, `plan_sources.Candidate/fingerprint/parse_field_setting`.

**Не подтверждено образцами DC / риски:**
- Время прогона: `/worklog/updated?since=0` читает все ворклоги компании (вероятно, миллионы) — десятки минут; память ограничена ворклогами задач базы.
- `get_field_configured_options` в плане 1 глотает ошибки — проверка видит только «пусто» (предупреждение, не блок).
- `SyncLock` считается устаревшим через 60 минут — синхронизация по расписанию может стартовать поверх многочасовой полной после переезда (как и у ручного «полного» сегодня). Руководство просит не запускать синхронизацию вручную; расписание при необходимости выключить на время.
- Сверка после сравнивает с часами DC на момент прогона: текущий месяц почти всегда немного расходится.
