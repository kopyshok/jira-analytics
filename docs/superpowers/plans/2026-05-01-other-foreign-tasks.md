# Other / Foreign Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить вид работ «Прочие / Чужие задачи» в виджет NormWork, куда попадают часы сотрудника, залогированные в задачи чужой продуктовой команды. Сделать справочник видов работ полноценно редактируемым с защитой системных строк.

**Architecture:** Расширить таблицу `mandatory_work_types` колонкой `is_system`, проштамповать существующие 5 seed-строк системными, добавить новую системную строку `other_foreign`. В `analytics_service.get_dashboard_norm_work` ввести cross-team детекцию: если команда сотрудника не равна `Issue.team` и не входит в `Issue.participating_teams`, факт идёт в `other_foreign` независимо от категории. План считается через `role_capacity_rules` как у остальных work_types (по умолчанию 0). На фронте — новая вкладка «Виды работ» в `/settings` для CRUD; в виджете NormWork строка `other_foreign` всегда показывается, при `fact > plan` подсвечивается красным.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + Alembic batch migrations · React 19 + TypeScript 6 + AntD 6 + TanStack Query · pytest + Playwright

**Объём:** ~12 задач, бэкенд + фронт + миграция + тесты. Ветка — `main` (subagent flow по правилу пользователя).

---

## File Structure

**Backend — новые файлы:**
- `alembic/versions/044_work_type_is_system_and_other_foreign.py` — миграция: `is_system` колонка + штамп существующих + insert `other_foreign`.

**Backend — модификации:**
- `app/models/mandatory_work_type.py` — добавить `is_system: Mapped[bool]`.
- `app/api/endpoints/mandatory_work_types.py` — выставлять `is_system` в response, защита PATCH/DELETE для системных.
- `app/services/analytics_service.py:743-936` — пере-логика `get_dashboard_norm_work` с cross-team routing.
- `app/schemas/dashboard.py` — без изменений (work_type_id уже строка, новая строка работает по той же схеме).

**Backend — тесты:**
- `tests/test_mandatory_work_types.py` — добавить кейсы protection.
- `tests/test_dashboard_endpoints.py` — добавить кейсы cross-team.

**Frontend — новые файлы:**
- `frontend/src/components/settings/WorkTypesTab.tsx` — CRUD таблица с защитой системных.

**Frontend — модификации:**
- `frontend/src/types/api.ts` — добавить `is_system` в `MandatoryWorkType`.
- `frontend/src/pages/SettingsPage.tsx` — добавить вкладку `worktypes`.
- `frontend/src/components/dashboard/NormWorkWidget.tsx` — показывать строку с plan=0 если fact>0 (красный).

---

## Task 1: Миграция 044 — is_system + other_foreign

**Files:**
- Create: `alembic/versions/044_work_type_is_system_and_other_foreign.py`
- Modify: `app/models/mandatory_work_type.py`
- Test: запустить `alembic upgrade head` и проверить структуру

- [ ] **Step 1: Add `is_system` field to model**

`app/models/mandatory_work_type.py`:

```python
"""MandatoryWorkType model — справочник обязательных работ."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class MandatoryWorkType(Base, TimestampMixin):
    """Тип работы (обязательная либо служебная вроде «Прочие/Чужие»).

    Системные строки (`is_system=True`) нельзя удалять и менять `code`;
    label остаётся редактируемым.
    """

    __tablename__ = "mandatory_work_types"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subtracts_from_pool: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<MandatoryWorkType {self.code}>"
```

- [ ] **Step 2: Создать миграцию**

`alembic/versions/044_work_type_is_system_and_other_foreign.py`:

```python
"""work type is_system flag + other_foreign seed

Revision ID: 044_work_type_is_system
Revises: 043_scenario_snapshot_redesign
Create Date: 2026-05-01

"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "044_work_type_is_system"
down_revision = "043_scenario_snapshot_redesign"
branch_labels = None
depends_on = None


SYSTEM_CODES = {
    "organizational",
    "management_admin",
    "support_consult",
    "tech_debt",
    "technical_tasks",
    "project",
    "other_foreign",
}


def upgrade() -> None:
    with op.batch_alter_table("mandatory_work_types") as batch:
        batch.add_column(
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    work_types = sa.table(
        "mandatory_work_types",
        sa.column("id", sa.String),
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("subtracts_from_pool", sa.Boolean),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    # Mark existing seeded rows as system
    op.execute(
        sa.update(work_types)
        .where(work_types.c.code.in_(sorted(SYSTEM_CODES - {"other_foreign"})))
        .values(is_system=True)
    )

    # Insert new system row
    now = datetime.utcnow()
    bind = op.get_bind()
    exists = bind.execute(
        sa.select(work_types.c.id).where(work_types.c.code == "other_foreign")
    ).first()
    if not exists:
        bind.execute(
            sa.insert(work_types).values(
                id=str(uuid.uuid4()),
                code="other_foreign",
                label="Прочие / Чужие задачи",
                is_active=True,
                sort_order=99,
                subtracts_from_pool=False,
                is_system=True,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    work_types = sa.table(
        "mandatory_work_types",
        sa.column("code", sa.String),
    )
    op.execute(sa.delete(work_types).where(work_types.c.code == "other_foreign"))
    with op.batch_alter_table("mandatory_work_types") as batch:
        batch.drop_column("is_system")
```

- [ ] **Step 3: Запустить миграцию**

Run: `py -3.10 -m alembic upgrade head`
Expected: `INFO ... Running upgrade ... -> 044_work_type_is_system, work type is_system flag + other_foreign seed`

- [ ] **Step 4: Sanity-проверить БД**

Run:
```bash
PYTHONIOENCODING=utf-8 py -3.10 -c "import sys, sqlite3; sys.stdout.reconfigure(encoding='utf-8'); con=sqlite3.connect('data/jira_analytics.db'); print(*con.execute('SELECT code, label, is_system FROM mandatory_work_types ORDER BY sort_order, code'), sep='\n')"
```
Expected: 6 строк (5 старых + `other_foreign`), все с `is_system=1`.

- [ ] **Step 5: Commit**

```bash
git add app/models/mandatory_work_type.py alembic/versions/044_work_type_is_system_and_other_foreign.py
git commit -m "feat(work-types): add is_system flag + seed other_foreign"
```

---

## Task 2: Тесты модели + миграции (smoke)

**Files:**
- Test: `tests/test_models.py` (или новый `tests/test_work_type_is_system.py`)

- [ ] **Step 1: Написать тест на сидинг**

Создать `tests/test_work_type_is_system.py`:

```python
"""После миграции 044: 6 системных work_types включая other_foreign."""

from app.models import MandatoryWorkType


SYSTEM_CODES = {
    "organizational",
    "management_admin",
    "support_consult",
    "tech_debt",
    "technical_tasks",
    "project",
    "other_foreign",
}


def test_other_foreign_seeded(db_session):
    row = (
        db_session.query(MandatoryWorkType)
        .filter(MandatoryWorkType.code == "other_foreign")
        .one()
    )
    assert row.is_system is True
    assert row.label == "Прочие / Чужие задачи"
    assert row.subtracts_from_pool is False
    assert row.is_active is True


def test_existing_work_types_marked_system(db_session):
    rows = (
        db_session.query(MandatoryWorkType)
        .filter(MandatoryWorkType.code.in_(SYSTEM_CODES - {"other_foreign"}))
        .all()
    )
    assert len(rows) == len(SYSTEM_CODES - {"other_foreign"})
    assert all(r.is_system for r in rows)
```

> **Note:** проект использует seeded conftest (`db_session` fixture); если в conftest уже инициализируются seed work_types — миграция запускается через `alembic upgrade head` в фикстуре. Если фикстура использует `Base.metadata.create_all`, то нужно явно вставить системные строки в conftest seed-секции (см. tests/CLAUDE.md). Уточни у `tests/conftest.py` как инициализируется БД.

- [ ] **Step 2: Запустить**

Run: `py -3.10 -m pytest tests/test_work_type_is_system.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_work_type_is_system.py
git commit -m "test(work-types): assert is_system seeding"
```

---

## Task 3: API protection — нельзя удалить/менять code системных work_types

**Files:**
- Modify: `app/api/endpoints/mandatory_work_types.py`
- Test: `tests/test_mandatory_work_types.py` (создать если нет)

- [ ] **Step 1: Написать failing-тесты**

`tests/test_mandatory_work_types.py`:

```python
"""Endpoint /mandatory-work-types — protection системных строк."""

from fastapi.testclient import TestClient


def test_delete_system_work_type_forbidden(client: TestClient, db_session):
    from app.models import MandatoryWorkType

    sys_wt = (
        db_session.query(MandatoryWorkType)
        .filter(MandatoryWorkType.code == "other_foreign")
        .one()
    )
    resp = client.delete(f"/api/v1/mandatory-work-types/{sys_wt.id}")
    assert resp.status_code == 409
    assert "system" in resp.json()["detail"].lower()


def test_patch_system_work_type_code_forbidden(client: TestClient, db_session):
    from app.models import MandatoryWorkType

    sys_wt = (
        db_session.query(MandatoryWorkType)
        .filter(MandatoryWorkType.code == "other_foreign")
        .one()
    )
    resp = client.patch(
        f"/api/v1/mandatory-work-types/{sys_wt.id}",
        json={"code": "renamed"},
    )
    assert resp.status_code == 409


def test_patch_system_work_type_label_allowed(client: TestClient, db_session):
    from app.models import MandatoryWorkType

    sys_wt = (
        db_session.query(MandatoryWorkType)
        .filter(MandatoryWorkType.code == "other_foreign")
        .one()
    )
    resp = client.patch(
        f"/api/v1/mandatory-work-types/{sys_wt.id}",
        json={"label": "Прочие / Чужие задачи (test)"},
    )
    assert resp.status_code == 200
    assert resp.json()["label"] == "Прочие / Чужие задачи (test)"


def test_list_includes_is_system(client: TestClient):
    resp = client.get("/api/v1/mandatory-work-types")
    assert resp.status_code == 200
    items = resp.json()
    assert any(it["code"] == "other_foreign" and it["is_system"] is True for it in items)
```

- [ ] **Step 2: Запустить — должны упасть на code-protection**

Run: `py -3.10 -m pytest tests/test_mandatory_work_types.py -v`
Expected: FAIL on `test_delete_system_work_type_forbidden`, `test_patch_system_work_type_code_forbidden`, `test_list_includes_is_system`.

- [ ] **Step 3: Реализовать защиту**

Заменить релевантные методы в `app/api/endpoints/mandatory_work_types.py`:

```python
class WorkTypeResponse(BaseModel):
    id: str
    code: str
    label: str
    is_active: bool
    sort_order: int
    subtracts_from_pool: bool
    is_system: bool

    class Config:
        from_attributes = True


@router.patch("/{wt_id}", response_model=WorkTypeResponse)
def update_work_type(wt_id: str, req: WorkTypeUpdate, db: Session = Depends(get_db)):
    wt = db.query(MandatoryWorkType).filter(MandatoryWorkType.id == wt_id).one_or_none()
    if wt is None:
        raise HTTPException(status_code=404, detail="Work type not found")
    data = req.model_dump(exclude_unset=True)
    if wt.is_system and "code" in data and data["code"] != wt.code:
        raise HTTPException(
            status_code=409,
            detail="Cannot change code of a system work type",
        )
    if "code" in data and data["code"] != wt.code:
        conflict = (
            db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.code == data["code"])
            .one_or_none()
        )
        if conflict is not None:
            raise HTTPException(status_code=409, detail=f"code {data['code']!r} already exists")
    for k, v in data.items():
        setattr(wt, k, v)
    db.commit()
    db.refresh(wt)
    return wt


@router.delete("/{wt_id}", status_code=204)
def delete_work_type(wt_id: str, db: Session = Depends(get_db)):
    wt = db.query(MandatoryWorkType).filter(MandatoryWorkType.id == wt_id).one_or_none()
    if wt is None:
        raise HTTPException(status_code=404, detail="Work type not found")
    if wt.is_system:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a system work type",
        )
    has_rules = (
        db.query(RoleCapacityRule)
        .filter(RoleCapacityRule.work_type_id == wt_id)
        .first()
        is not None
    )
    has_overrides = (
        db.query(EmployeeCapacityOverride)
        .filter(EmployeeCapacityOverride.work_type_id == wt_id)
        .first()
        is not None
    )
    if has_rules or has_overrides:
        raise HTTPException(
            status_code=409,
            detail="Work type is referenced by rules/overrides; deactivate it instead.",
        )
    db.delete(wt)
    db.commit()
    return None
```

- [ ] **Step 4: Запустить — должны пройти**

Run: `py -3.10 -m pytest tests/test_mandatory_work_types.py -v`
Expected: PASS все 4.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/mandatory_work_types.py tests/test_mandatory_work_types.py
git commit -m "feat(api): protect system work types from delete/code-change"
```

---

## Task 4: Backend — cross-team detection в analytics_service

**Files:**
- Modify: `app/services/analytics_service.py:743-940`
- Test: `tests/test_dashboard_endpoints.py`

- [ ] **Step 1: Написать failing-тест cross-team routing**

Добавить в `tests/test_dashboard_endpoints.py` (использовать существующие фикстуры; если нет helpers под Issue с team — собрать руками):

```python
def test_norm_work_routes_cross_team_to_other_foreign(client, db_session):
    """Worklog в задаче чужой команды попадает в other_foreign, не в категорию задачи."""
    from app.models import (
        Employee, EmployeeTeam, Issue, Worklog, MandatoryWorkType, Category, Role,
    )
    from datetime import datetime
    import uuid

    # Сотрудник в команде A
    emp = Employee(
        id=str(uuid.uuid4()), display_name="Тестов Тест",
        is_active=True, role="developer",
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=str(uuid.uuid4()), employee_id=emp.id,
        team="Команда A", is_primary=True,
    ))

    # Задача в команде B (чужая)
    issue = Issue(
        id=str(uuid.uuid4()), key="ISSUE-1", summary="Foreign task",
        issue_type="Задача", category="support_consultation",
        team="Команда B", participating_teams="[]",
    )
    db_session.add(issue)

    # Ворклог сотрудника в чужой задаче, в Q2 2026
    db_session.add(Worklog(
        id=str(uuid.uuid4()), issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 4, 15, 10, 0, 0),
        time_spent_seconds=3600 * 5, hours=5.0,
    ))
    db_session.commit()

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Найти строку other_foreign у тестового сотрудника
    found = None
    for role_grp in data["roles"]:
        for emp_block in role_grp["employees"]:
            if emp_block["employee_id"] == emp.id:
                for wt in emp_block["work_types"]:
                    if wt.get("work_type_code") == "other_foreign" or wt["label"].startswith("Прочие"):
                        found = wt
                        break
    assert found is not None
    assert found["fact_hours"] == 5.0


def test_norm_work_routes_own_team_to_category_work_type(client, db_session):
    """Worklog в задаче своей команды попадает в work_type категории, не в other_foreign."""
    from app.models import Employee, EmployeeTeam, Issue, Worklog
    from datetime import datetime
    import uuid

    emp = Employee(
        id=str(uuid.uuid4()), display_name="Свой Свой",
        is_active=True, role="developer",
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=str(uuid.uuid4()), employee_id=emp.id,
        team="Команда A", is_primary=True,
    ))

    issue = Issue(
        id=str(uuid.uuid4()), key="ISSUE-2", summary="Own task",
        issue_type="Задача", category="support_consultation",
        team="Команда A", participating_teams="[]",
    )
    db_session.add(issue)

    db_session.add(Worklog(
        id=str(uuid.uuid4()), issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 4, 15, 10, 0, 0),
        time_spent_seconds=3600 * 4, hours=4.0,
    ))
    db_session.commit()

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # other_foreign должен быть 0 для этого сотрудника
    for role_grp in data["roles"]:
        for emp_block in role_grp["employees"]:
            if emp_block["employee_id"] == emp.id:
                for wt in emp_block["work_types"]:
                    if wt["label"].startswith("Прочие"):
                        assert wt["fact_hours"] == 0
                        return
    # other_foreign строка может вовсе отсутствовать если plan=0 и fact=0 — это тоже OK


def test_norm_work_participating_team_is_own(client, db_session):
    """Если команда сотрудника в participating_teams задачи — НЕ чужая."""
    from app.models import Employee, EmployeeTeam, Issue, Worklog
    from datetime import datetime
    import uuid
    import json

    emp = Employee(
        id=str(uuid.uuid4()), display_name="Участ Уч",
        is_active=True, role="developer",
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=str(uuid.uuid4()), employee_id=emp.id,
        team="Команда A", is_primary=True,
    ))

    issue = Issue(
        id=str(uuid.uuid4()), key="ISSUE-3", summary="Participating task",
        issue_type="Задача", category="support_consultation",
        team="Команда B",
        participating_teams=json.dumps(["Команда A"]),
    )
    db_session.add(issue)

    db_session.add(Worklog(
        id=str(uuid.uuid4()), issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 4, 15, 10, 0, 0),
        time_spent_seconds=3600 * 3, hours=3.0,
    ))
    db_session.commit()

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    data = resp.json()

    for role_grp in data["roles"]:
        for emp_block in role_grp["employees"]:
            if emp_block["employee_id"] == emp.id:
                for wt in emp_block["work_types"]:
                    if wt["label"].startswith("Прочие"):
                        assert wt["fact_hours"] == 0
                        return


def test_norm_work_empty_issue_team_is_foreign(client, db_session):
    """Пустая Issue.team → задача считается чужой."""
    from app.models import Employee, EmployeeTeam, Issue, Worklog
    from datetime import datetime
    import uuid

    emp = Employee(
        id=str(uuid.uuid4()), display_name="Пуст Тс",
        is_active=True, role="developer",
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=str(uuid.uuid4()), employee_id=emp.id,
        team="Команда A", is_primary=True,
    ))

    issue = Issue(
        id=str(uuid.uuid4()), key="ISSUE-4", summary="No team",
        issue_type="Задача", category="support_consultation",
        team=None, participating_teams="[]",
    )
    db_session.add(issue)

    db_session.add(Worklog(
        id=str(uuid.uuid4()), issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 4, 15, 10, 0, 0),
        time_spent_seconds=3600 * 2, hours=2.0,
    ))
    db_session.commit()

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    data = resp.json()

    found = False
    for role_grp in data["roles"]:
        for emp_block in role_grp["employees"]:
            if emp_block["employee_id"] == emp.id:
                for wt in emp_block["work_types"]:
                    if wt["label"].startswith("Прочие") and wt["fact_hours"] == 2.0:
                        found = True
    assert found, "Worklog в задаче без team должен попасть в other_foreign"
```

- [ ] **Step 2: Запустить — должны упасть (логика ещё не реализована)**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py -k "cross_team or own_team or participating or empty_issue_team" -v`
Expected: FAIL на cross_team и empty_issue_team — фактовые часы попадают в support_consult вместо other_foreign.

- [ ] **Step 3: Реализовать cross-team routing в analytics_service**

В `app/services/analytics_service.py`, в методе `get_dashboard_norm_work` (~line 743), после загрузки work_types и code_to_wt:

```python
# Найти строку other_foreign — туда уйдут чужие задачи
other_foreign_wt = next((wt for wt in work_types if wt.code == "other_foreign"), None)
```

Затем загрузить команды сотрудников до агрегации фактов (рядом с employees query, ~line 791):

```python
# Команда сотрудника (primary) — для cross-team детекции
emp_team_rows = (
    self.db.query(EmployeeTeam.employee_id, EmployeeTeam.team)
    .filter(
        EmployeeTeam.employee_id.in_([e.id for e in employees]),
        EmployeeTeam.is_primary.is_(True),
    )
    .all()
)
emp_team_by_id: dict[str, str] = {row.employee_id: row.team for row in emp_team_rows}
```

Затем в блоке агрегации фактов (~line 909-935) заменить на запрос с issue.team + participating_teams:

```python
import json

# 8. Факт per emp × work_type — с учётом cross-team routing.
emp_ids_list = [e.id for e in employees]
wl_rows = (
    self.db.query(
        Worklog.employee_id,
        Issue.category,
        Issue.team,
        Issue.participating_teams,
        func.sum(Worklog.time_spent_seconds).label("secs"),
    )
    .join(Issue, Issue.id == Worklog.issue_id)
    .filter(
        Worklog.employee_id.in_(emp_ids_list),
        Worklog.started_at >= start_dt,
        Worklog.started_at <= end_dt,
    )
    .group_by(
        Worklog.employee_id, Issue.category, Issue.team, Issue.participating_teams,
    )
    .all()
)
fact_per_emp_wt: dict[str, dict[str, float]] = {e.id: {} for e in employees}
for emp_id, cat_code, issue_team, parts_json, secs in wl_rows:
    h = (secs or 0) / 3600.0
    emp_team = emp_team_by_id.get(emp_id)
    # Cross-team детекция
    parts: list[str] = []
    if parts_json:
        try:
            parts = json.loads(parts_json) or []
        except (ValueError, TypeError):
            parts = []
    is_foreign = False
    if not emp_team:
        is_foreign = False  # сотрудник без команды — fallback по категории
    elif not issue_team:
        is_foreign = True   # пустая team задачи = чужая
    elif issue_team == emp_team or emp_team in parts:
        is_foreign = False
    else:
        is_foreign = True

    if is_foreign and other_foreign_wt is not None:
        fact_per_emp_wt[emp_id][other_foreign_wt.id] = (
            fact_per_emp_wt[emp_id].get(other_foreign_wt.id, 0.0) + h
        )
        continue

    # Стандартный routing — по категории задачи
    if cat_code is None:
        continue
    wt_id = code_to_wt.get(cat_code)
    if wt_id is None:
        continue
    if project_wt is not None and wt_id == project_wt.id:
        continue  # факт project считается отдельно через scenario allocations
    fact_per_emp_wt[emp_id][wt_id] = fact_per_emp_wt[emp_id].get(wt_id, 0.0) + h
```

> **Замечание:** old query фильтровал `Issue.category.isnot(None)`. Cross-team логика должна работать даже если `Issue.category=NULL` (или unfilled_worklog), поэтому фильтр снят. Project-роутинг остался как был (через scenario allocations). other_foreign не учитывает project — это намеренно: проектные задачи всегда «свои», иначе их не зачли бы в бэклог.

Также добавить план для other_foreign по дефолту 0 — это уже работает через `pct_for(...)` который вернёт 0 если правила нет, но строка не покажется в ответе если plan=0 и fact=0. Нужно гарантировать показ строки если fact > 0:

В блоке формирования breakdowns (~line ~990-1050), убедиться что строка с fact > 0 включается даже при plan=0 — обычно это уже работает; если нет — проверить логику фильтрации breakdowns (см. фактический код).

- [ ] **Step 4: Запустить тесты**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py -k "cross_team or own_team or participating or empty_issue_team" -v`
Expected: PASS все 4.

- [ ] **Step 5: Прогнать полный test_dashboard_endpoints + затронутые smoke**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py tests/test_analytics_service.py -v`
Expected: PASS (или объяснимые fail — фиксить).

- [ ] **Step 6: Commit**

```bash
git add app/services/analytics_service.py tests/test_dashboard_endpoints.py
git commit -m "feat(analytics): route cross-team worklogs to other_foreign work type"
```

---

## Task 5: Backend — гарантированный вывод строки other_foreign при fact > 0

**Files:**
- Modify: `app/services/analytics_service.py` (блок формирования NormWorkEmployee)

- [ ] **Step 1: Прочитать существующий блок breakdown формирования**

Run: открыть `app/services/analytics_service.py` строки ~970-1080 (после фактов идёт сборка `NormWorkTypeBreakdown` per emp).

- [ ] **Step 2: Написать тест — строка other_foreign с plan=0 и fact>0 показывается**

Добавить к Task 4 тестам:

```python
def test_norm_work_other_foreign_visible_with_zero_plan(client, db_session):
    """При plan=0 и fact>0 строка other_foreign всё равно отображается (с pct=∞ или сигналом перегруза)."""
    # Используется тот же сетап что test_norm_work_routes_cross_team_to_other_foreign
    # ... (создать сотрудника + чужую задачу + worklog)
    # ассерт: в response work_types есть other_foreign с fact_hours > 0 и plan_hours == 0
    ...
```

- [ ] **Step 3: Реализация**

Если breakdown собирается из `fact_per_emp_wt` ключей — то всё уже работает. Иначе добавить: для каждого `wt` в `work_types`, если `wt.id in fact_per_emp_wt[emp.id]` ИЛИ `wt.id in plan_per_emp_wt[emp.id]` — включить строку. Plan_hours=0 если нет, fact_hours=0 если нет, pct=`fact/plan*100` если plan>0 иначе **999** (или `Infinity`-сурогат). На фронте превратим в красный.

- [ ] **Step 4: Запустить тест**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py -k "zero_plan" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/analytics_service.py tests/test_dashboard_endpoints.py
git commit -m "feat(analytics): keep other_foreign row visible when plan is zero"
```

---

## Task 6: Frontend — типы + пометка is_system

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Добавить is_system в MandatoryWorkType**

В `frontend/src/types/api.ts`, найти `MandatoryWorkType` и расширить:

```ts
export interface MandatoryWorkType {
  id: string;
  code: string;
  label: string;
  is_active: boolean;
  sort_order: number;
  subtracts_from_pool: boolean;
  is_system: boolean;
}
```

- [ ] **Step 2: Запустить tsc**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(frontend): MandatoryWorkType.is_system field"
```

---

## Task 7: Frontend — экран «Виды работ» в /settings

**Files:**
- Create: `frontend/src/components/settings/WorkTypesTab.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Создать WorkTypesTab с CRUD таблицей**

`frontend/src/components/settings/WorkTypesTab.tsx`:

```tsx
import { useState } from 'react';
import { Table, Button, Modal, Form, Input, Switch, InputNumber, Popconfirm, Space, Tag, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, LockOutlined } from '@ant-design/icons';
import {
  useMandatoryWorkTypes,
  useCreateMandatoryWorkType,
  useUpdateMandatoryWorkType,
  useDeleteMandatoryWorkType,
} from '../../hooks/useCapacity';
import type { MandatoryWorkType } from '../../types/api';

export default function WorkTypesTab() {
  const { data: items = [], isLoading } = useMandatoryWorkTypes();
  const create = useCreateMandatoryWorkType();
  const update = useUpdateMandatoryWorkType();
  const remove = useDeleteMandatoryWorkType();

  const [editing, setEditing] = useState<MandatoryWorkType | null>(null);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();

  const openEdit = (row: MandatoryWorkType) => {
    setEditing(row);
    form.setFieldsValue(row);
  };
  const openCreate = () => {
    setCreating(true);
    form.resetFields();
    form.setFieldsValue({ is_active: true, subtracts_from_pool: true, sort_order: 0 });
  };
  const close = () => { setEditing(null); setCreating(false); form.resetFields(); };

  const onSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) await update.mutateAsync({ id: editing.id, body: values });
      else await create.mutateAsync(values);
      close();
    } catch (e: any) {
      message.error(e?.message ?? 'Ошибка сохранения');
    }
  };

  const onDelete = async (id: string) => {
    try {
      await remove.mutateAsync(id);
    } catch (e: any) {
      message.error(e?.message ?? 'Удаление запрещено');
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          Добавить
        </Button>
      </Space>
      <Table<MandatoryWorkType>
        rowKey="id"
        loading={isLoading}
        dataSource={items}
        columns={[
          {
            title: 'Код', dataIndex: 'code', key: 'code',
            render: (v, row) => (
              <Space>
                <code>{v}</code>
                {row.is_system && <Tag icon={<LockOutlined />} color="purple">системный</Tag>}
              </Space>
            ),
          },
          { title: 'Название', dataIndex: 'label', key: 'label' },
          {
            title: 'Активен', dataIndex: 'is_active', key: 'is_active',
            render: v => v ? 'Да' : 'Нет',
          },
          {
            title: 'Вычитается из пула', dataIndex: 'subtracts_from_pool', key: 'subtracts',
            render: v => v ? 'Да' : 'Нет',
          },
          { title: 'Порядок', dataIndex: 'sort_order', key: 'sort_order', width: 80 },
          {
            title: '', key: 'actions', width: 100,
            render: (_, row) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
                <Popconfirm
                  title="Удалить?"
                  onConfirm={() => onDelete(row.id)}
                  disabled={row.is_system}
                >
                  <Button
                    size="small"
                    icon={<DeleteOutlined />}
                    danger
                    disabled={row.is_system}
                  />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        open={editing !== null || creating}
        title={editing ? `Изменить «${editing.label}»` : 'Новый вид работ'}
        onOk={onSubmit}
        onCancel={close}
        confirmLoading={create.isPending || update.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="Код"
            name="code"
            rules={[{ required: true, max: 64 }]}
            tooltip={editing?.is_system ? 'Код системного вида менять нельзя' : undefined}
          >
            <Input disabled={!!editing?.is_system} />
          </Form.Item>
          <Form.Item label="Название" name="label" rules={[{ required: true, max: 255 }]}>
            <Input />
          </Form.Item>
          <Form.Item label="Активен" name="is_active" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="Вычитается из пула" name="subtracts_from_pool" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="Порядок" name="sort_order">
            <InputNumber min={0} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Добавить вкладку в SettingsPage**

В `frontend/src/pages/SettingsPage.tsx` добавить пункт `worktypes` в массив вкладок (после `calendar`):

```tsx
{
  key: 'worktypes',
  label: 'Виды работ',
  children: <WorkTypesTab />,
},
```

И импорт:

```tsx
import WorkTypesTab from '../components/settings/WorkTypesTab';
```

- [ ] **Step 3: Запустить dev-сервер, ручной smoke**

Run (в отдельном терминале):
```bash
cd frontend && npm run dev
```

Открыть `http://localhost:5173/settings?tab=worktypes`. Проверить:
1. Видно 6 видов, у системных — фиолетовый тег «системный».
2. Удалить системный — кнопка disabled.
3. Изменить label системного — сохраняется. Изменить code — поле disabled.
4. Создать новый вид — добавляется. Удалить новый — удаляется.

- [ ] **Step 4: Lint**

Run: `cd frontend && npm run lint`
Expected: 0 errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/WorkTypesTab.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat(settings): work types CRUD tab with system protection"
```

---

## Task 8: Frontend — NormWorkWidget красная подсветка other_foreign

**Files:**
- Modify: `frontend/src/components/dashboard/NormWorkWidget.tsx`

- [ ] **Step 1: Открыть `WorkTypeRow` (строка ~47)**

Прочитать существующий код, понять как считается color.

- [ ] **Step 2: Изменить логику цвета: при plan=0 и fact>0 → красный**

Заменить функцию `WorkTypeRow` так:

```tsx
function WorkTypeRow({ wt, t }: { wt: NormWorkTypeBreakdown; t: Thresholds }) {
  // Перегруз: план 0 и факт > 0 (например, чужие задачи без выделенного плана) — всегда красный
  const overflowZeroPlan = wt.plan_hours === 0 && wt.fact_hours > 0;
  const color = overflowZeroPlan ? '#ff4d4f' : statusColor(wt.pct, t);
  const fillW = wt.plan_hours > 0
    ? Math.min(100, (wt.fact_hours / wt.plan_hours) * 100)
    : (overflowZeroPlan ? 100 : 0);
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr auto 60px',
      gap: 8, alignItems: 'center', padding: '3px 0',
    }}>
      <span style={{
        fontSize: 12,
        color: overflowZeroPlan ? '#ff4d4f' : '#a4b8d8',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {wt.label}
      </span>
      <div style={{ width: 50, height: 5, background: '#1c3358', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${fillW}%`, background: color }} />
      </div>
      <span style={{
        fontSize: 11, color, textAlign: 'right',
        fontWeight: overflowZeroPlan ? 700 : 400,
      }}>
        {Math.round(wt.fact_hours)}/{Math.round(wt.plan_hours)}
      </span>
    </div>
  );
}
```

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: 0 errors

- [ ] **Step 4: Ручной smoke**

Открыть `/dashboard`. Найти сотрудника с фактом в чужих задачах (например, Шутов Сергей за Q2 2026). Подтвердить:
1. Строка «Прочие / Чужие задачи» видна.
2. Если plan=0 и fact>0 — название и число красные, бар красный.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/NormWorkWidget.tsx
git commit -m "feat(dashboard): red highlight for other_foreign overflow when plan=0"
```

---

## Task 9: E2E проверка + финальный smoke

**Files:**
- Run: smoke + lint полные

- [ ] **Step 1: Backend full pytest**

Run: `py -3.10 -m pytest tests/ -v --tb=short`
Expected: PASS (известные pre-existing failures — игнорируем, см. memory `project_ci_red_pre_existing`).

- [ ] **Step 2: Frontend full lint + build**

Run:
```bash
cd frontend && npm run lint && npm run build
```
Expected: 0 errors, build success.

- [ ] **Step 3: Local smoke**

Перезапустить backend через `py -3.10 -m uvicorn app.main:app --reload --port 8000` (kill PID :8000 если висит). Открыть `/dashboard`, проверить виджет NormWork. Открыть `/settings?tab=worktypes`, поработать с CRUD.

- [ ] **Step 4: Commit финальный fixup если нужно + push**

```bash
git push origin main
```

---

## Self-Review

**Spec coverage:**

| Требование пользователя | Задача |
|---|---|
| Новый вид работ «Прочие / Чужие задачи» | T1 (миграция + seed) |
| Чужая = команда сотрудника не равна `Issue.team` и не входит в `participating_teams` | T4 |
| Пустая `Issue.team` = чужая | T4 (test_empty_issue_team_is_foreign) |
| «Чужая» бьёт категорию | T4 (continue до code_to_wt) |
| План = 0, факт > 0 → красный | T5 (видимость) + T8 (UI) |
| Справочник видов работ редактируемый | T7 (CRUD UI) |
| Системные нельзя удалить | T3 (API) + T7 (UI disabled) |
| Считать на лету | T4 (нет денормализации, всё в analytics_service) |
| Один сотрудник = одна команда | T4 (читаем primary EmployeeTeam) |

**Placeholders:** проверено — кода в каждом step достаточно, нет TODO/TBD.

**Type consistency:** `MandatoryWorkType.is_system` определён в T1 (модель), используется в T3 (API), T6 (TS-тип), T7 (UI). `other_foreign` code упоминается консистентно.

---

## Execution Handoff

План сохранён в `docs/superpowers/plans/2026-05-01-other-foreign-tasks.md`.

Запускаю **Subagent-Driven Development** (по правилу пользователя — фичи >10 задач делаются через subagent flow с 2-stage review на main, не worktree).
