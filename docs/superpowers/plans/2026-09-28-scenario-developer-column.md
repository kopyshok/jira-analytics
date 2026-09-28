# Колонка «Разработчик» в сценариях — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Руководитель указывает разработчика задачи в сценарии (и на бэклоге); ресурсное планирование отдаёт ему фазу «Разработка». Колонка «Исполнитель» становится «Аналитик».

**Architecture:** Новое поле `BacklogItem.developer_employee_id` (ручное, Jira не трогает). Планировщик (`_assign_employees`) ставит его на разработку раньше всех авто-источников, без проверки ёмкости; исполнитель строки при заполненной колонке идёт на анализ (если это не тот же человек). API сценария и бэклога отдают и принимают поле; один человек не может быть и аналитиком, и разработчиком строки (422).

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic (batch mode), pytest; React 19 + AntD 6 + TanStack Query.

Спецификация: `docs/superpowers/specs/2026-09-28-scenario-developer-column-design.md`.

Общие правила:
- Тесты: `py -3.10 -m pytest <путь> -v` (Windows). Весь прогон — `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py` (LLM-тесты висят без сети).
- Докстринги и комментарии — по-русски, в стиле окружающего кода.
- **Не коммитить** — коммиты делает координатор после ревью.

---

### Task 1: Поле в модели + миграция

**Files:**
- Modify: `app/models/backlog_item.py` (после `assignee_jira_account_at_choice`, и relationship после `assignee`)
- Modify: `app/models/scenario_allocation_snapshot.py` (после `assignee_role_at_approval`)
- Create: `alembic/versions/sd01_backlog_developer.py`
- Test: `tests/test_migration_sd01_backlog_developer.py`

- [ ] **Step 1: тест миграции**

```python
"""sd01: разработчик строки бэклога и снимка — вверх, вниз, снова вверх."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _columns(db_path: Path, table: str) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(tmp_path):
    db_path = tmp_path / "sd01.db"
    url = f"sqlite:///{db_path.as_posix()}"
    _alembic(url, "upgrade", "head")
    assert "developer_employee_id" in _columns(db_path, "backlog_items")
    assert "developer_employee_id" in _columns(db_path, "scenario_allocation_snapshots")
    _alembic(url, "downgrade", "nw01_normed_reserve")
    assert "developer_employee_id" not in _columns(db_path, "backlog_items")
    assert "developer_employee_id" not in _columns(db_path, "scenario_allocation_snapshots")
    _alembic(url, "upgrade", "head")
    assert "developer_employee_id" in _columns(db_path, "backlog_items")


def test_postgres_offline_sql():
    sql = _alembic(
        "postgresql://offline:offline@localhost:1/offline",
        "upgrade", "nw01_normed_reserve:sd01_backlog_developer", "--sql",
    )
    assert "ADD COLUMN developer_employee_id VARCHAR(36)" in sql
```

- [ ] **Step 2:** `py -3.10 -m pytest tests/test_migration_sd01_backlog_developer.py -v` → FAIL (нет ревизии).

- [ ] **Step 3: модель**

`app/models/backlog_item.py`, после `assignee_jira_account_at_choice`:
```python
    # Разработчик задачи — выбирают вручную в сценарии или на бэклоге. Jira
    # его не пишет и не затирает. Пусто — фазу «Разработка» ресурсное
    # планирование подбирает само («Разработчик» из Jira, подбор по команде).
    developer_employee_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```
и после relationship `assignee`:
```python
    developer: Mapped[Optional["Employee"]] = relationship(
        "Employee",
        foreign_keys=[developer_employee_id],
    )
```

`app/models/scenario_allocation_snapshot.py`, после `assignee_role_at_approval`:
```python
    developer_employee_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
```

- [ ] **Step 4: миграция** `alembic/versions/sd01_backlog_developer.py`

```python
"""backlog_items + scenario_allocation_snapshots: разработчик строки

Revision ID: sd01_backlog_developer
Revises: nw01_normed_reserve
Create Date: 2026-09-28

Разработчик задачи, выбранный вручную в сценарии или на бэклоге; копия — в
снимке утверждённого сценария. Самодостаточна: не импортирует код
приложения. Локальная dev-база может уже иметь колонки от create_all в
tests/conftest.py — такие пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "sd01_backlog_developer"
down_revision: Union[str, None] = "nw01_normed_reserve"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    insp = sa.inspect(op.get_bind())
    return "developer_employee_id" in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has("backlog_items"):
        with op.batch_alter_table("backlog_items") as batch:
            batch.add_column(sa.Column(
                "developer_employee_id",
                sa.String(36),
                sa.ForeignKey(
                    "employees.id", ondelete="SET NULL",
                    name="fk_backlog_items_developer_employee_id",
                ),
                nullable=True,
            ))
            batch.create_index(
                "ix_backlog_items_developer_employee_id", ["developer_employee_id"]
            )
    if not _has("scenario_allocation_snapshots"):
        with op.batch_alter_table("scenario_allocation_snapshots") as batch:
            batch.add_column(sa.Column("developer_employee_id", sa.String(36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scenario_allocation_snapshots") as batch:
        batch.drop_column("developer_employee_id")
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_index("ix_backlog_items_developer_employee_id")
        batch.drop_column("developer_employee_id")
```

Проверить имя таблицы снимка: `__tablename__` в `app/models/scenario_allocation_snapshot.py` — если не `scenario_allocation_snapshots`, поправить в миграции и тесте.

- [ ] **Step 5:** тест миграции → PASS. Затем `alembic upgrade head` на локальной базе (`data/jira_analytics.db`) → без ошибок.

---

### Task 2: Планировщик — разработчик из колонки

**Files:**
- Modify: `app/services/resource_planning_service.py` — `compute_schedule` (блок `manual_executors` ~стр. 639-653), `_load_borrowed` (докстринг), `_assign_employees` (~1913-2039)
- Test: `tests/services/test_rp_scenario_developer.py`

- [ ] **Step 1: тесты**

```python
"""Разработчик из колонки сценария получает разработку; один человек — одна фаза."""

from sqlalchemy import select

from app.models import BacklogItem, PlanConflict, ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, make_employee, make_plan
from tests.services.test_rp_scenario_executor import _weekdays


def _item(db, dev=10.0, analyst=8.0, assignee=None, developer=None, manual=False):
    it = BacklogItem(
        title="x", priority=1, estimate_dev_hours=dev, estimate_analyst_hours=analyst,
        estimate_qa_hours=0.0, estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
        assignee_manual=manual,
        developer_employee_id=developer.id if developer else None,
    )
    db.add(it)
    db.flush()
    return it


def test_developer_column_takes_dev_over_jira_and_capacity(db_session):
    dev_col = make_employee(db_session, "Из колонки", "B")
    jira_dev = make_employee(db_session, "Из Jira", "B")
    an = make_employee(db_session, "Аналитик", "B", role="analyst")
    item = _item(db_session, developer=dev_col)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [dev_col, jira_dev, an],
        jira_dev={item.id: jira_dev.id},
        capacity={dev_col.id: 0.0},  # ёмкости нет — всё равно он
    )

    assert res["dev"][item.id] == dev_col.id
    assert res["analyst"][item.id] == an.id


def test_developer_role_executor_goes_to_analysis_when_column_set(db_session):
    """Колонка заполнена: исполнитель строки — на анализ, какая бы ни была роль."""
    executor = make_employee(db_session, "Исполнитель-разработчик", "B")  # роль dev по умолчанию
    dev_col = make_employee(db_session, "Из колонки", "B")
    item = _item(db_session, assignee=executor, developer=dev_col)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [executor, dev_col])

    assert res["analyst"][item.id] == executor.id
    assert res["dev"][item.id] == dev_col.id


def test_same_person_in_both_columns_takes_only_dev(db_session):
    same = make_employee(db_session, "Один", "B", role="analyst")
    an = make_employee(db_session, "Другой аналитик", "B", role="analyst")
    item = _item(db_session, assignee=same, developer=same)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [same, an])

    assert res["dev"][item.id] == same.id
    assert res["analyst"][item.id] == an.id


def test_greedy_analyst_skips_row_developer(db_session):
    only_an = make_employee(db_session, "Единственный аналитик", "B", role="analyst")
    item = _item(db_session, developer=only_an)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [only_an])

    assert res["dev"][item.id] == only_an.id
    assert res["analyst"][item.id] is None


def test_empty_column_keeps_old_behaviour(db_session):
    executor = make_employee(db_session, "Исполнитель-разработчик", "B")
    an = make_employee(db_session, "Аналитик", "B", role="analyst")
    item = _item(db_session, assignee=executor)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [executor, an])

    assert res["dev"][item.id] == executor.id
    assert res["analyst"][item.id] == an.id


def test_busy_developer_from_other_team_is_borrowed_and_reported(db_session):
    make_employee(db_session, "Свой B", "B")
    ext = make_employee(db_session, "Шутов", "A")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=1), ext,
         _weekdays("2026-01-01", "2026-04-30"))
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12)
    item.developer_employee_id = ext.id
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    rows = db_session.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_b.id, ResourcePlanAssignment.phase == "dev"
        )
    ).scalars().all()
    assert rows == []
    [c] = db_session.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan_b.id, PlanConflict.type == "UNPLACED_HOURS"
        )
    ).scalars().all()
    assert c.backlog_item_id == item.id
    assert c.employee_id == ext.id
```

Роль по умолчанию в `make_employee` проверить в `tests/services/xteam_factory.py` — если не разработческая, передать `role="dev"` там, где в тесте нужен разработчик.

- [ ] **Step 2:** `py -3.10 -m pytest tests/services/test_rp_scenario_developer.py -v` → FAIL (нет поля/логики).

- [ ] **Step 3: привлечённые** — в `compute_schedule` рядом с `manual_executors`:

```python
        manual_developers = {
            it.developer_employee_id for it in items if it.developer_employee_id
        }
        ...
        borrowed_rows = self._load_borrowed(
            (pinned_ids | set(jira_dev.values()) | manual_executors | manual_developers)
            - team_ids
        )
```
Комментарий над блоком: добавить «или стоят в колонке «Разработчик» сценария». Докстринг `_load_borrowed`: добавить источник «разработчик из колонки сценария».

- [ ] **Step 4: `_assign_employees`**

В цикле `for item in items:` сразу после вызова `_scenario_executor`:
```python
            # Разработчик из колонки сценария (выбран вручную). Тогда
            # исполнитель строки идёт на анализ, какая бы ни была роль; один
            # человек не ведёт обе фазы — совпал с разработчиком, анализ
            # подбирается из пула.
            dev_col = item.developer_employee_id
            if dev_col not in all_by_id:
                dev_col = None
            if dev_col:
                if executor_id == dev_col:
                    executor_id, executor_phase = None, None
                elif executor_id:
                    executor_phase = "analyst"
```
Жадный подбор аналитика — пул без разработчика строки:
```python
            if not analyst_id and analyst_ids:
                analyst_id = self._pick_in_group(
                    [x for x in analyst_ids if x != dev_col],
                    item_group.get(item.id), load, an_hours,
                    emp_group, capacity,
                )
```
Разработка — сразу после `dev_id = pinned.get((item.id, "dev", 1))`:
```python
            # Разработчик из колонки ставится без проверки ёмкости:
            # нехватка времени — конфликт, как у ручного исполнителя.
            if not dev_id and dev_col:
                dev_id = dev_col
```
Докстринг `_assign_employees`: в перечне приоритетов после «закреп вручную» вставить «→ разработчик из колонки сценария (для разработки; без проверки ёмкости; исполнитель строки тогда идёт на анализ, а совпавший с разработчиком — никуда)».

- [ ] **Step 5:** тесты Task 2 + `tests/services/test_rp_scenario_executor.py` + `tests/services/test_rp_borrowed_staff.py` → PASS.

---

### Task 3: API сценария

**Files:**
- Modify: `app/api/endpoints/planning.py` — `AllocationResponse` (~344-358), `_to_allocation_resp` (~463-530), новые `AllocationDeveloperPatch` + эндпоинт после `patch_allocation_assignee` (~1760), `patch_allocation_assignee` (проверка совпадения), `scenario_assignee_candidates` (~1767-1811), все `joinedload(BacklogItem.assignee)` в этом файле → добавить `joinedload(BacklogItem.developer)`
- Test: `tests/api/test_scenario_developer.py`

- [ ] **Step 1: тесты** (фикстуры `client`, `row` — как в `tests/api/test_scenario_assignee.py`; импортировать оттуда: `from tests.api.test_scenario_assignee import client, row  # noqa: F401`)

```python
"""Разработчик строки сценария: ручной выбор, только в черновике, не тот же, что аналитик."""

from app.models import BacklogItem
from tests.api.test_scenario_assignee import PLANNING, client, row  # noqa: F401


def _choose_dev(client, row, employee_id):
    return client.patch(
        f"{PLANNING}/{row.sc.id}/allocations/{row.alloc.id}/developer",
        json={"developer_employee_id": employee_id},
    )


def test_set_and_clear_developer(client, db_session, row):
    r = _choose_dev(client, row, row.own.id)
    assert r.status_code == 200, r.text
    assert r.json()["developer_employee_id"] == row.own.id
    assert r.json()["developer_display_name"] == "Свой B"
    db_session.expire_all()
    assert db_session.get(BacklogItem, row.item.id).developer_employee_id == row.own.id

    r = _choose_dev(client, row, None)
    assert r.status_code == 200, r.text
    assert r.json()["developer_employee_id"] is None
    assert r.json()["developer_display_name"] is None


def test_developer_same_as_assignee_is_422(client, row):
    r = _choose_dev(client, row, row.jira.id)  # row.jira — исполнитель строки
    assert r.status_code == 422, r.text


def test_assignee_same_as_developer_is_422(client, row):
    assert _choose_dev(client, row, row.own.id).status_code == 200
    r = client.patch(
        f"{PLANNING}/{row.sc.id}/allocations/{row.alloc.id}/assignee",
        json={"assignee_employee_id": row.own.id},
    )
    assert r.status_code == 422, r.text


def test_developer_unknown_employee_is_404(client, row):
    assert _choose_dev(client, row, "nope").status_code == 404


def test_developer_in_approved_scenario_is_rejected(client, db_session, row):
    row.sc.status = "approved"
    db_session.commit()
    r = _choose_dev(client, row, row.own.id)
    assert r.status_code in (400, 409), r.text  # как _require_draft у исполнителя


def test_dev_candidates_jira_group_is_jira_developer(client, db_session, row):
    row.issue.developer_account_id = "acc-chosen"  # «Выбранный», команда C
    db_session.commit()
    r = client.get(
        f"{PLANNING}/{row.sc.id}/assignee-candidates",
        params={"backlog_item_id": row.item.id, "phase": "dev"},
    )
    assert r.status_code == 200, r.text
    groups = {g["key"]: g for g in r.json()}
    assert [c["employee_id"] for c in groups["jira"]["employees"]] == [row.chosen.id]
```

Код `_require_draft` посмотреть — ожидаемый статус в `test_developer_in_approved_scenario_is_rejected` поставить точный. «Выбранный» создан без роли — `jira_developers_for_items` его примет (роль пустая), если он состоит в команде в квартале сценария (`make_employee` создаёт членство — проверить).

- [ ] **Step 2:** тесты → FAIL.

- [ ] **Step 3: схема ответа** — в `AllocationResponse` после `assignee_role`:
```python
    developer_employee_id: Optional[str] = None
    developer_display_name: Optional[str] = None
```
В `_to_allocation_resp` в конструктор `AllocationResponse(...)` после `assignee_role=resolved_role,`:
```python
        developer_employee_id=item.developer_employee_id,
        developer_display_name=item.developer.display_name if item.developer else None,
```
Все `.options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))` в файле → `.options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee), joinedload(BacklogItem.developer))`.

- [ ] **Step 4: PATCH разработчика** — после `patch_allocation_assignee`:

```python
class AllocationDeveloperPatch(BaseModel):
    developer_employee_id: Optional[str] = None


@router.patch(
    "/scenarios/{scenario_id}/allocations/{alloc_id}/developer",
    response_model=AllocationResponse,
)
async def patch_allocation_developer(
    scenario_id: str,
    alloc_id: str,
    data: AllocationDeveloperPatch,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Сменить разработчика строки сценария. Выбор только ручной; один человек
    не может быть и аналитиком, и разработчиком строки."""
    alloc = (
        db.query(ScenarioAllocation)
        .filter(
            ScenarioAllocation.id == alloc_id,
            ScenarioAllocation.scenario_id == scenario_id,
        )
        .first()
    )
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")
    scenario = db.get(PlanningScenario, scenario_id)
    _require_draft(scenario)
    backlog_item = db.get(BacklogItem, alloc.backlog_item_id)
    if not backlog_item:
        raise HTTPException(status_code=404, detail="BacklogItem not found")
    if data.developer_employee_id is not None:
        if not db.get(Employee, data.developer_employee_id):
            raise HTTPException(status_code=404, detail="Employee not found")
        if data.developer_employee_id == backlog_item.assignee_employee_id:
            raise HTTPException(
                status_code=422, detail="Этот сотрудник уже аналитик задачи"
            )
    backlog_item.developer_employee_id = data.developer_employee_id
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    backlog_item = (
        db.query(BacklogItem)
        .options(
            joinedload(BacklogItem.issue),
            joinedload(BacklogItem.assignee),
            joinedload(BacklogItem.developer),
        )
        .filter(BacklogItem.id == backlog_item.id)
        .first()
    )
    return _to_allocation_resp(
        alloc,
        backlog_item,
        subgroup_by_employee=_subgroup_by_employee(db, scenario.team),
    )
```

В `patch_allocation_assignee` сразу после проверки `if not emp: ... 404`:
```python
        if data.assignee_employee_id == backlog_item.developer_employee_id:
            raise HTTPException(
                status_code=422, detail="Этот сотрудник уже разработчик задачи"
            )
```

- [ ] **Step 5: кандидаты** — в `scenario_assignee_candidates` параметр:
```python
    phase: Literal["analyst", "dev"] = Query("analyst", description="Колонка: аналитик или разработчик"),
```
(импорт `Literal` из `typing`, если нет). Вместо `jira_employee_id=jira_assignee_id(db, item.issue if item else None)`:
```python
    if phase == "dev":
        # «Из Jira» для разработчика — поле «Разработчик» задачи или её подзадач.
        jira_id = jira_developers_for_items(db, [item], start, end).get(item.id) if item else None
    else:
        jira_id = jira_assignee_id(db, item.issue if item else None)
```
и `jira_employee_id=jira_id`. Импорт: `from app.services.jira_developer import jira_developers_for_items`.

- [ ] **Step 6:** `py -3.10 -m pytest tests/api/test_scenario_developer.py tests/api/test_scenario_assignee.py -v` → PASS.

---

### Task 4: API бэклога

**Files:**
- Modify: `app/api/endpoints/backlog.py` — `BacklogItemUpdate` (~72), `BacklogItemResponse` (~178), `_item_response`/построитель ответа (~479), `update_backlog_item` (~1204), все `joinedload(BacklogItem.assignee)` → + `joinedload(BacklogItem.developer)`
- Test: `tests/api/test_backlog_developer.py`

- [ ] **Step 1: тесты**

```python
"""Бэклог: аналитик и разработчик строки правятся; один человек — одна роль."""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem
from tests.services.xteam_factory import make_employee


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def idea(db_session):
    it = BacklogItem(title="Идея", team="B")
    db_session.add(it)
    db_session.commit()
    return it


def _patch(client, item_id, body):
    return client.patch(f"/api/v1/backlog/{item_id}", json=body)


def test_patch_developer_and_assignee(client, db_session, idea):
    an = make_employee(db_session, "Аналитик", "B", role="analyst")
    dev = make_employee(db_session, "Разработчик", "B")
    db_session.commit()

    r = _patch(client, idea.id, {"assignee_employee_id": an.id, "developer_employee_id": dev.id})

    assert r.status_code == 200, r.text
    assert r.json()["assignee_employee_id"] == an.id
    assert r.json()["developer_employee_id"] == dev.id
    assert r.json()["developer_display_name"] == "Разработчик"


def test_patch_same_person_is_422(client, db_session, idea):
    dev = make_employee(db_session, "Разработчик", "B")
    db_session.commit()
    assert _patch(client, idea.id, {"developer_employee_id": dev.id}).status_code == 200

    r = _patch(client, idea.id, {"assignee_employee_id": dev.id})

    assert r.status_code == 422, r.text


def test_patch_unknown_developer_is_404(client, idea):
    assert _patch(client, idea.id, {"developer_employee_id": "nope"}).status_code == 404
```

Если эндпоинт требует авторизацию (`get_current_user`) — посмотреть, как это решено в существующих тестах бэклога (`tests/api/test_backlog*.py`), и сделать так же.

- [ ] **Step 2:** тесты → FAIL.

- [ ] **Step 3:** `BacklogItemUpdate` — добавить:
```python
    # Правка аналитика — только у идей без задачи Jira (у задачи он из Jira).
    assignee_employee_id: Optional[str] = None
    developer_employee_id: Optional[str] = None
```
`BacklogItemResponse` — после `assignee_display_name`:
```python
    developer_employee_id: Optional[str] = None
    developer_display_name: Optional[str] = None
```
Построитель ответа — после `assignee_display_name=(...)`:
```python
        developer_employee_id=item.developer_employee_id,
        developer_display_name=item.developer.display_name if item.developer else None,
```
В `update_backlog_item` после `if not patch: return ...`:
```python
    for key in ("assignee_employee_id", "developer_employee_id"):
        eid = patch.get(key)
        if eid is not None and not db.get(Employee, eid):
            raise HTTPException(status_code=404, detail="Employee not found")
    assignee = patch.get("assignee_employee_id", item.assignee_employee_id)
    developer = patch.get("developer_employee_id", item.developer_employee_id)
    if assignee and assignee == developer:
        raise HTTPException(
            status_code=422, detail="Один сотрудник не может быть и аналитиком, и разработчиком"
        )
```
(импорт `Employee` из `app.models`, если нет.)

- [ ] **Step 4:** тесты Task 4 + `py -3.10 -m pytest tests/api -k backlog -q` → PASS.

---

### Task 5: Снимок утверждённого сценария

**Files:**
- Modify: `app/services/snapshot_writer.py` (`write_allocation_snapshot`, ~541), `app/services/snapshot_differ.py` (`_ALLOC_COMPARE_FIELDS`)
- Test: дописать в существующий тест снимков (`grep -rln "write_allocation_snapshot\|SnapshotDiffer" tests`) — кейс «сменили разработчика → changed содержит developer_employee_id».

- [ ] **Step 1:** тест: две ревизии с разным `developer_employee_id` у одной строки → `diff(...)["allocations"]["changed"][0]["developer_employee_id"] == {"before": a, "after": b}`. Построить по образцу соседнего теста на `assignee_employee_id` (найти grep'ом).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** в `ScenarioAllocationSnapshot(...)` после `assignee_role_at_approval=...`:
```python
                    developer_employee_id=bi.developer_employee_id,
```
В `_ALLOC_COMPARE_FIELDS` после `"assignee_role_at_approval",`:
```python
    "developer_employee_id",
```
Докстринг `write_allocation_snapshot` — дописать `developer_employee_id` в перечень.
- [ ] **Step 4:** PASS. Проверить фронт `ScenarioRevisionHistoryDrawer.tsx` / `ScenarioDiffPanel.tsx`: если поля изменений показываются по словарю подписей — добавить подпись «Разработчик» рядом с исполнителем; если генерик — ничего.

---

### Task 6: Выгрузка сценария в Excel

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — `INCLUDED_HEADERS/WIDTHS`, `EXCLUDED_HEADERS/WIDTHS` (~126-138), `_initiative_row_mid` (~162), итоговые строки `_sheet_included`/`_sheet_excluded` (~906-925, ~1010-1028)
- Test: существующий тест экспорта (`grep -rln "scenario_xlsx\|INCLUDED_HEADERS" tests`)

- [ ] **Step 1: тест** — в существующем файле тестов экспорта: у строки задан аналитик (вручную) и разработчик; в листе «Включено» заголовки строки 2 заканчиваются на `["Цели", "Аналитик", "Разработчик"]`, в строке данных — их имена; итоговая строка не падает и сумма «Итого, ч» верная.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** заголовки — в конец:
```python
INCLUDED_HEADERS = [
    "Ключ Jira", "Название", "Приоритет", "Заказчик",
    "Аналитик, ч", "Разработка, ч", "QA, ч", "ОПЭ, ч",
    "Итого, ч", "План, ч", "Цели", "Аналитик", "Разработчик",
]
INCLUDED_WIDTHS = [14, 50, 8, 18, 11, 11, 11, 11, 12, 12, 28, 22, 22]

EXCLUDED_HEADERS = [
    "Ключ Jira", "Название", "Приоритет", "Заказчик",
    "Аналитик, ч", "Разработка, ч", "QA, ч", "ОПЭ, ч",
    "Итого, ч", "Цели", "Аналитик", "Разработчик",
]
EXCLUDED_WIDTHS = [14, 50, 8, 18, 11, 11, 11, 11, 12, 28, 22, 22]
```
Имя аналитика — та же логика, что колонка сценария (`_to_allocation_resp` в planning.py):
```python
def _analyst_name(item: BacklogItem) -> str:
    """Имя в колонке «Аналитик» — как в сценарии: выбранный вручную, иначе
    исполнитель из Jira, иначе привязанный сотрудник."""
    assignee = getattr(item, "assignee", None)
    if item.assignee_manual:
        return assignee.display_name if assignee else ""
    issue = getattr(item, "issue", None)
    if issue is not None and issue.assignee_display_name:
        return issue.assignee_display_name
    return assignee.display_name if assignee else ""
```
В `_initiative_row_mid` после `base.append(goals)`:
```python
    developer = getattr(item, "developer", None)
    base.append(_analyst_name(item))
    base.append(developer.display_name if developer else "")
```
Итоговые строки: `sum_cols = list(range(5, len(headers)))` → `list(range(5, len(headers) - 2))` в обоих листах (последние три колонки — «Цели» и два имени — текст). Пустые ячейки-заливки итоговой строки: для «Включено» — колонки `len(headers) - 2 .. len(headers)` вместо жёсткой `11`; для «Не вошло» — то же вместо `10`:
```python
        for c_idx in range(len(headers) - 2, len(headers) + 1):
            ws.cell(row=total_row_idx, column=c_idx, value="").fill = _Style.HEADER_FILL
```
Убедиться, что запрос контекста экспорта подгружает `BacklogItem.developer` (joinedload рядом с `assignee`, если он есть) — иначе ленивая загрузка тоже работает, но N+1.
- [ ] **Step 4:** тесты экспорта → PASS (включая вариант с отсечкой ОПЭ, если он есть в тестах).

---

### Task 7: Фронтенд

**Files:**
- Modify: `frontend/src/types/api.ts` (`AllocationResponse` ~710, `BacklogItemResponse` ~520)
- Modify: `frontend/src/api/planning.ts` (новый `patchAllocationDeveloper`, `getScenarioAssigneeCandidates(…, phase)`)
- Modify: `frontend/src/hooks/usePlanning.ts` (`usePatchAllocationDeveloper`, `useScenarioAssigneeCandidates(…, phase)`)
- Modify: `frontend/src/utils/rpCandidates.ts` (`candidateOptions` — опция `disabledId`)
- Modify: `frontend/src/components/planning/BacklogAllocRow.tsx`
- Modify: `frontend/src/pages/PlanningPage.tsx` (сетки 67-69, заголовок 917-920, пропсы строки ~984)
- Modify: `frontend/src/pages/BacklogPage.tsx` (колонка ~414-434)
- Modify: `frontend/src/api/backlog.ts` (тип patch-а, если там перечислены поля)

- [ ] **Step 1: типы.** В `AllocationResponse` и `BacklogItemResponse` (types/api.ts) после `assignee_*`:
```ts
  developer_employee_id: string | null;
  developer_display_name: string | null;
```
В `frontend/src/api/backlog.ts` — если тип тела PATCH перечисляет поля, добавить `developer_employee_id?: string | null` (и `assignee_employee_id`, если его нет).

- [ ] **Step 2: API + хуки.** `api/planning.ts`:
```ts
export const patchAllocationDeveloper = (
  scenarioId: string,
  allocId: string,
  developerEmployeeId: string | null,
): Promise<AllocationResponse> =>
  api.patch<AllocationResponse>(
    `/planning/scenarios/${scenarioId}/allocations/${allocId}/developer`,
    { developer_employee_id: developerEmployeeId },
  );

/** Кандидаты строки сценария: «Из Jira» / «Моя команда» / «Другие команды».
 *  phase='dev' — для колонки «Разработчик» («Из Jira» — поле «Разработчик»). */
export const getScenarioAssigneeCandidates = (
  scenarioId: string,
  backlogItemId: string,
  phase: 'analyst' | 'dev' = 'analyst',
) =>
  api.get<AssignmentCandidateGroup[]>(
    `/planning/scenarios/${scenarioId}/assignee-candidates`,
    { backlog_item_id: backlogItemId, phase },
  );
```
`hooks/usePlanning.ts`: `useScenarioAssigneeCandidates(scenarioId, backlogItemId, enabled, phase: 'analyst' | 'dev' = 'analyst')` — `phase` в `queryKey` (после `backlogItemId`) и в вызов. Новый хук по образцу `usePatchAllocationAssignee`:
```ts
export const usePatchAllocationDeveloper = () => {
  const qc = useQueryClient();
  const { notification } = App.useApp();
  return useMutation<
    AllocationResponse,
    Error,
    { scenarioId: string; allocId: string; developerEmployeeId: string | null }
  >({
    mutationFn: ({ scenarioId, allocId, developerEmployeeId }) =>
      patchAllocationDeveloper(scenarioId, allocId, developerEmployeeId),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ['planning', 'allocations', vars.scenarioId] });
      qc.invalidateQueries({ queryKey: ['backlog'] });
    },
    onError: () => {
      notification.error({ title: 'Не удалось сменить разработчика' });
    },
  });
};
```
В `usePatchAllocationAssignee.onSuccess` тоже добавить `qc.invalidateQueries({ queryKey: ['backlog'] })` — значение общее с бэклогом.

- [ ] **Step 3: `candidateOptions`** — третий необязательный аргумент:
```ts
/** Группы опций для AntD Select. ``busy`` — кто уже занят в соседней колонке
 *  строки: неактивен, с подсказкой. */
export function candidateOptions(
  groups: AssignmentCandidateGroup[],
  roleLabels: ReadonlyMap<string, string>,
  busy?: { id: string | null | undefined; hint: string },
) {
  return groups.map((g) => ({
    label: g.label,
    title: g.label,
    options: g.employees.map((e) => {
      const taken = !!busy?.id && e.employee_id === busy.id;
      const label = candidateLabel(e, g.key, roleLabels);
      return { value: e.employee_id, label: taken ? `${label} — ${busy!.hint}` : label, disabled: taken };
    }),
  }));
}
```
Существующие вызовы (`rpCandidates` используют и в ресурсном планировании) без третьего аргумента работают как раньше.

- [ ] **Step 4: `BacklogAllocRow.tsx`** — вынести выбор человека в локальный компонент того же файла и использовать дважды.

```tsx
type PersonSelectProps = {
  scenarioId: string;
  backlogItemId: string;
  phase: 'analyst' | 'dev';
  isDraft: boolean;
  value: string | null;
  displayName: string | null;
  /** Кто стоит в соседней колонке — его выбрать нельзя. */
  busyId: string | null;
  busyHint: string;
  teamAssigneeOptions: { label: string; value: string }[];
  roleLabels: ReadonlyMap<string, string>;
  onChange: (employeeId: string | null) => void;
};

function PersonSelect({
  scenarioId, backlogItemId, phase, isDraft, value, displayName, busyId, busyHint,
  teamAssigneeOptions, roleLabels, onChange,
}: PersonSelectProps) {
  const { notification } = App.useApp();
  // Кандидаты — все, кто в квартале сценария состоит в какой-либо команде.
  // Грузятся, только пока список открыт: строк в сценарии много.
  const [open, setOpen] = useState(false);
  const candidates = useScenarioAssigneeCandidates(scenarioId, backlogItemId, open, phase);
  // Пока список не пришёл — одна опция с текущим; не загрузился — состав
  // команды сценария, как было до выбора из всех команд.
  const options = useMemo<SelectProps['options']>(
    () =>
      candidates.data?.length
        ? candidateOptions(candidates.data, roleLabels, { id: busyId, hint: busyHint })
        : candidates.isError
          ? teamAssigneeOptions.map((o) =>
              o.value === busyId ? { ...o, disabled: true, label: `${o.label} — ${busyHint}` } : o,
            )
          : value
            ? [{ value, label: displayName ?? '—' }]
            : [],
    [candidates.data, candidates.isError, roleLabels, busyId, busyHint, teamAssigneeOptions, value, displayName],
  );
  // Каждая неудачная загрузка списка — одно уведомление (с тем же ключом
  // повтор заменяет прежнее, а не копит стопку).
  const candidatesError = candidates.error;
  useEffect(() => {
    if (!candidatesError) return;
    notification.error({
      key: 'scenario-assignee-candidates',
      title: 'Не удалось загрузить список сотрудников',
      description: 'Показан состав команды сценария.',
    });
  }, [candidatesError, notification]);

  if (!isDraft && !value) {
    return <span style={{ fontSize: 12, color: DARK_THEME.textMuted }}>{displayName ?? '—'}</span>;
  }
  return (
    <Select
      size="small"
      value={value ?? undefined}
      placeholder={displayName ?? '—'}
      allowClear
      disabled={!isDraft}
      style={{ width: '100%', fontSize: 12 }}
      // Шире колонки: подпись с названием команды и загрузкой целиком
      // помещается почти у всех. Числом, а не false — иначе AntD
      // выключает виртуальный список.
      popupMatchSelectWidth={640}
      showSearch={{ optionFilterProp: 'label' }}
      loading={candidates.isFetching}
      notFoundContent={
        candidates.isFetching
          ? <Spin size="small" />
          : candidates.isError
            ? 'Не удалось загрузить список сотрудников'
            : undefined
      }
      options={options}
      onOpenChange={setOpen}
      // В закрытом поле — только имя; роль, команда и загрузка — в списке.
      labelRender={({ label }) => displayName ?? label}
      onChange={(v: string | undefined) => onChange(v ?? null)}
    />
  );
}
```
В `BacklogAllocRowBase`: удалить `notification`, `assigneeOpen`, `candidates`, `assigneeOptions`, `candidatesError`-эффект (переехали в `PersonSelect`); `roleLabels` оставить. Новый проп `onDeveloperChange: (allocId: string, employeeId: string | null) => void;` в типе и деструктуризации. Ячейку исполнителя (`<div onClick={(e) => e.stopPropagation()}>` со старым Select) заменить на две:
```tsx
      <div onClick={(e) => e.stopPropagation()}>
        <PersonSelect
          scenarioId={scenarioId}
          backlogItemId={a.backlog_item_id}
          phase="analyst"
          isDraft={isDraft}
          value={a.assignee_employee_id}
          displayName={a.assignee_display_name}
          busyId={a.developer_employee_id}
          busyHint="уже разработчик этой задачи"
          teamAssigneeOptions={teamAssigneeOptions}
          roleLabels={roleLabels}
          onChange={(id) => onAssigneeChange(a.id, id)}
        />
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <PersonSelect
          scenarioId={scenarioId}
          backlogItemId={a.backlog_item_id}
          phase="dev"
          isDraft={isDraft}
          value={a.developer_employee_id}
          displayName={a.developer_display_name}
          busyId={a.assignee_employee_id}
          busyHint="уже аналитик этой задачи"
          teamAssigneeOptions={teamAssigneeOptions}
          roleLabels={roleLabels}
          onChange={(id) => onDeveloperChange(a.id, id)}
        />
      </div>
```
Обновить JSDoc пропа `teamAssigneeOptions`: «список аналитика и разработчика».

- [ ] **Step 5: `PlanningPage.tsx`.**
Сетки — колонка 150px для разработчика после исполнителя:
```ts
const GRID = '24px 36px 48px minmax(0, 1fr) 150px 150px 180px 260px 90px';
const GRID_WITH_SUBGROUP = '24px 36px 48px minmax(0, 1fr) 150px 150px 140px 180px 260px 90px';
```
(если рядом есть комментарий с перечнем колонок — обновить.) Проверить `SubgroupSectionHeader` и любые другие места, использующие `GRID`/`gridTemplate` (grep по `GRID` и `gridTemplateColumns` в `components/planning`) — сдвинуть их ячейки так же.
Заголовок: «Исполнитель» → «Аналитик»; после него:
```tsx
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <CodeOutlined style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
                    Разработчик
                  </span>
```
(`CodeOutlined` из `@ant-design/icons`.) Хендлер рядом с `handleAssigneeChange`:
```tsx
  const { mutate: patchDeveloper } = usePatchAllocationDeveloper();
  const handleDeveloperChange = useCallback(
    (allocId: string, employeeId: string | null) => {
      if (!scenarioId) return;
      patchDeveloper({ scenarioId, allocId, developerEmployeeId: employeeId });
    },
    [patchDeveloper, scenarioId],
  );
```
(посмотреть, как объявлен `patchAssignee`, и объявить так же.) Проп строке: `onDeveloperChange={handleDeveloperChange}`.

- [ ] **Step 6: `BacklogPage.tsx`.** Колонку `title: 'Исполнитель'` переименовать в `'Аналитик'`; в её `Select` (ветка идеи без задачи) опциям добавить `disabled: e.id === r.developer_employee_id`. После неё новая колонка:
```tsx
    {
      title: 'Разработчик',
      key: 'developer',
      width: 140,
      render: (_: unknown, r: BacklogItemResponse) => (
        <Select
          size="small"
          allowClear
          variant="borderless"
          value={r.developer_employee_id ?? undefined}
          style={{ width: '100%', fontSize: 12 }}
          showSearch={{ optionFilterProp: 'label' }}
          options={activeEmployees.map((e) => ({
            label: e.display_name,
            value: e.id,
            disabled: e.id === r.assignee_employee_id,
          }))}
          onChange={(val) => patch(r.id, { developer_employee_id: val ?? null })}
        />
      ),
    },
```
Проверить, что `patch(...)` на бэклоге инвалидирует `['planning', 'allocations']` (сценарий показывает то же значение) — если нет, добавить инвалидацию `['planning']` в его `onSuccess`.

- [ ] **Step 7:** `cd frontend && npm run lint && npm run build` → без ошибок. Если есть юнит-тесты фронта для `rpCandidates` (`*.test.ts`) — `npx vitest run src/utils` → PASS; добавить кейс на `busy` (опция неактивна, подпись с подсказкой).

---

### Task 8: Справка и заметка к релизу

**Files:**
- Modify: `docs/help/planning.md` (стр. 75 — строка таблицы «Исполнитель», стр. 163 — шаг 7)
- Modify: `docs/help/backlog.md` (стр. 50)
- Modify: `docs/help/resource-planning.md` (стр. 93 — порядок выбора исполнителя)
- Modify: `release_notes/drafts.json`

- [ ] **Step 1:** `planning.md` — строку «Исполнитель» переименовать в «Аналитик» (текст тот же, плюс: «если заполнен «Разработчик», аналитик встаёт на анализ при любой роли»); новая строка «Разработчик»: «Кто делает разработку. Заполняется только вручную, тот же список с группами; «Из Jira» — поле «Разработчик» задачи. Один человек не может быть и аналитиком, и разработчиком задачи. В ресурсном плане получает фазу «Разработка» даже при нехватке времени — остаток виден конфликтом «Часы не размещены»; из другой команды — как привлечённый. Пусто — разработчика подбирает планировщик.» Шаг 7: «…в колонке «Аналитик»; если разработчик известен заранее — в колонке «Разработчик»».
- [ ] **Step 2:** `backlog.md` — «Исполнитель» → «Аналитик»; строка «Разработчик»: «Разработчик задачи — выпадающий список сотрудников, в любой строке. То же значение, что в сценариях.»
- [ ] **Step 3:** `resource-planning.md` стр. 93 — после «закреплённый на этой фазе вручную →» вставить «для разработки — разработчик из колонки «Разработчик» сценария (ставится, даже если не хватает времени; исполнитель строки тогда встаёт на анализ, а если он же разработчик — анализ подбирается из команды) →».
- [ ] **Step 4:** `release_notes/drafts.json` — в конец массива (формат как у соседних записей):
```json
    {
      "type": "feature",
      "section": "planning",
      "title": "Разработчик задачи в сценарии",
      "description": "В сценариях и на странице «Бэклог» появилась колонка «Разработчик», а «Исполнитель» переименован в «Аналитик». Если разработчик задачи известен заранее, укажите его — ресурсное планирование отдаст ему фазу «Разработка», даже если у него не хватает времени (тогда появится конфликт). Один человек не может быть и аналитиком, и разработчиком одной задачи. Разработчик попадает и в выгрузку сценария в Excel.",
      "sort_order": 0
    }
```
Значения `type`/`section` сверить с существующими записями файла (какой `type` у новых возможностей, как называется раздел сценариев).
- [ ] **Step 5:** `py -3.10 -c "import json;json.load(open('release_notes/drafts.json',encoding='utf-8'))"` → без ошибок.

---

### Task 9: Полный прогон

- [ ] `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py` → всё зелёное (кроме заранее известных падений — сверить с `main`).
- [ ] `ruff check app/ tests/` → чисто.
- [ ] `cd frontend && npm run lint && npm run build` → чисто.
- [ ] `graphify update .`
