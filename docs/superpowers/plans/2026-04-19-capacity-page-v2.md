# Capacity Page v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the `/capacity` page: team hierarchy in the Team tab, absences (was vacations) with typed reasons + heatmap, copy-rules-to-next-quarter, capacity xlsx export, overload colour threshold, employee-team assignment (inline + auto-detect).

**Architecture:** One alembic migration renames `vacations` → `absences` with a new `reason` column; the `Vacation` model/schema/endpoints are renamed in lock-step. `EmployeeTeamService` (new) derives team from worklog mode; `PUT /employees/{id}/team` persists it. `CapacityService` gains `copy_rules_to_quarter`; `ExportService` gains `export_capacity_xlsx`. Frontend splits `useCapacity.ts` into `useAbsences.ts` + stays, rewrites `TeamTab`/`VacationsTab`, adds `AbsenceHeatmap`.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic, openpyxl (lazy). React 19, TypeScript, Ant Design 6, TanStack Query, Playwright.

**Reference spec:** [docs/superpowers/specs/2026-04-19-capacity-page-v2-design.md](../specs/2026-04-19-capacity-page-v2-design.md)

**Windows run note:** Use `py -3.10 -m pytest ...` — pytest is not installed under Python 3.14. If `uvicorn --reload` hangs after backend edits, kill the PID on `:8000` and restart.

---

## Phase 0 — Preconditions

- [ ] Working on `main` (per user convention for multi-file features).
- [ ] `alembic upgrade head` applies cleanly before starting.
- [ ] `py -3.10 -m pytest tests/ -v` is green before starting (expected: pre-existing `test_sync_service.py` failure per memory — this is tolerated baseline).

---

## Phase 1 — Rename `Vacation` → `Absence` (backend)

### Task 1.1: Migration — rename table, add `reason`

**Files:**
- Create: `alembic/versions/018_rename_vacations_to_absences.py`

- [ ] **Step 1: Create the migration file**

```python
"""Renaming vacations → absences + reason.

Revision ID: 018_rename_vacations_to_absences
Revises: 017_production_calendar_hours
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "018_rename_vacations_to_absences"
down_revision: Union[str, None] = "017_production_calendar_hours"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("vacations", "absences")
    with op.batch_alter_table("absences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reason",
                sa.String(32),
                nullable=False,
                server_default="vacation",
            ),
        )
    # Ensure all existing rows carry the default reason explicitly.
    op.execute("UPDATE absences SET reason='vacation' WHERE reason IS NULL OR reason=''")


def downgrade() -> None:
    with op.batch_alter_table("absences") as batch_op:
        batch_op.drop_column("reason")
    op.rename_table("absences", "vacations")
```

- [ ] **Step 2: Apply migration**

Run: `alembic upgrade head`
Expected: `INFO ... Running upgrade 017_production_calendar_hours -> 018_rename_vacations_to_absences`.

- [ ] **Step 3: Smoke-check the DB**

Run: `py -3.10 -c "import sqlite3; c=sqlite3.connect('data/jira_analytics.db'); print([r for r in c.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name IN (\"vacations\",\"absences\")')]); print([r for r in c.execute('PRAGMA table_info(absences)')])"`
Expected: table `absences` present, `vacations` absent, `reason` column at end with `String(32)` default `vacation`.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/018_rename_vacations_to_absences.py
git commit -m "Migration 018: rename vacations → absences + reason column"
```

### Task 1.2: Rename the `Vacation` model → `Absence`

**Files:**
- Create: `app/models/absence.py`
- Delete: `app/models/vacation.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/employee.py` (line 40 — relationship)
- Modify: `app/services/capacity_service.py` (lines referencing `Vacation`)
- Modify: `tests/test_capacity_service.py` (imports + references)

- [ ] **Step 1: Create `app/models/absence.py`**

```python
"""Absence model - employee time-off periods (vacation / sick / day-off / other)."""

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.employee import Employee


ABSENCE_REASONS = ("vacation", "sick", "day_off", "other")


class Absence(Base, TimestampMixin):
    """Запись об отсутствии сотрудника.

    Источник вычета capacity при квартальном планировании.
    Все reason'ы обрабатываются одинаково в расчёте часов.
    """

    __tablename__ = "absences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="vacation")
    hours_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="absences")

    def __repr__(self) -> str:
        return f"<Absence {self.reason} {self.start_date} — {self.end_date}>"
```

- [ ] **Step 2: Delete `app/models/vacation.py`**

```bash
git rm app/models/vacation.py
```

- [ ] **Step 3: Update `app/models/__init__.py`**

Replace the `Vacation` import line with:

```python
from app.models.absence import Absence, ABSENCE_REASONS
```

And in `__all__`, replace `"Vacation"` with `"Absence", "ABSENCE_REASONS"`.

- [ ] **Step 4: Update `app/models/employee.py` relationship (line 40)**

Replace:

```python
    vacations = relationship("Vacation", back_populates="employee")
```

with:

```python
    absences = relationship("Absence", back_populates="employee")
```

- [ ] **Step 5: Update `app/services/capacity_service.py`**

In the import at line 25, replace `Vacation` with `Absence`.
Rename the private method `_vacation_hours_for_month` → `_absence_hours_for_month` (definition at line 145 **and** its caller at line 216 — replace `self._vacation_hours_for_month(...)` with `self._absence_hours_for_month(...)`).
Rename the local variable `vacations` → `absences` (line 158) and the loop variable `vac` → `absence` (line 169).
Replace `Vacation.` column references with `Absence.` (lines 159–163).
Keep `MonthlyCapacity.vacation_hours` / `QuarterCapacity.total_vacation_hours` dataclass field names **unchanged** for now (they are serialisation-facing; breaking them would touch the whole frontend) — but update the doc-comment: "vacation_hours = часы любых отсутствий сотрудника (vacation/sick/day_off/other)".

- [ ] **Step 6: Update `tests/test_capacity_service.py`**

Replace `from app.models import ... Vacation ...` with `Absence`.
Global search/replace `Vacation(` → `Absence(` in the test bodies (lines 80, 100, 132, 154, 199).
Keep assertions like `result.vacation_hours == 40.0` — `MonthlyCapacity.vacation_hours` is the dataclass field and was intentionally left unchanged in Step 5.

- [ ] **Step 7: Run the capacity tests**

Run: `py -3.10 -m pytest tests/test_capacity_service.py -v`
Expected: all pass.

- [ ] **Step 8: Run the full backend suite**

Run: `py -3.10 -m pytest tests/ -v`
Expected: everything that was green before is still green (only the pre-existing `test_sync_service.py` failure remains).

- [ ] **Step 9: Commit**

```bash
git add app/models/absence.py app/models/__init__.py app/models/employee.py app/services/capacity_service.py tests/test_capacity_service.py
git commit -m "Rename Vacation model → Absence, update relationships + tests"
```

---

## Phase 2 — Replace `/capacity/vacations` with `/capacity/absences`

### Task 2.1: Schemas + endpoints

**Files:**
- Modify: `app/api/endpoints/capacity.py` (schemas + 3 endpoints)
- Create: `tests/test_api_absences.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/test_api_absences.py`:

```python
"""Тесты API /capacity/absences."""

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.database import get_db
from app.models import Absence, Employee


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def employee(db_session):
    e = Employee(
        id="emp1", jira_account_id="a1", display_name="Иванов И.",
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    return e


def test_list_empty(client):
    r = client.get("/api/v1/capacity/absences")
    assert r.status_code == 200
    assert r.json() == []


def test_create_with_reason_sick(client, employee, db_session):
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "reason": "sick",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reason"] == "sick"
    assert body["start_date"] == "2026-04-10"
    row = db_session.query(Absence).one()
    assert row.reason == "sick"


def test_create_defaults_reason_to_vacation(client, employee):
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 201
    assert r.json()["reason"] == "vacation"


def test_create_rejects_unknown_reason(client, employee):
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "reason": "bogus",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 422


def test_create_rejects_inverted_dates(client, employee):
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-12",
        "end_date": "2026-04-10",
        "reason": "vacation",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 400


def test_delete(client, employee, db_session):
    a = Absence(
        id="a1", employee_id=employee.id,
        start_date="2026-04-10", end_date="2026-04-12", reason="vacation",
    )
    db_session.add(a)
    db_session.commit()
    r = client.delete(f"/api/v1/capacity/absences/{a.id}")
    assert r.status_code == 200
    assert db_session.query(Absence).count() == 0


def test_old_vacations_endpoints_are_gone(client):
    r = client.get("/api/v1/capacity/vacations")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/test_api_absences.py -v`
Expected: all fail (endpoints don't exist yet).

- [ ] **Step 3: Rewrite the vacation endpoints in `app/api/endpoints/capacity.py`**

Replace the `from app.models import MonthlyCapacityRule, Vacation` import (line 15) with:

```python
from app.models import MonthlyCapacityRule, Absence, ABSENCE_REASONS
```

Replace the `VacationCreate` / `VacationResponse` schemas (lines 38–53) with:

```python
from typing import Literal

AbsenceReason = Literal["vacation", "sick", "day_off", "other"]


class AbsenceCreate(BaseModel):
    employee_id: str
    start_date: date
    end_date: date
    reason: AbsenceReason = "vacation"
    hours_total: Optional[float] = None


class AbsenceResponse(BaseModel):
    id: str
    employee_id: str
    start_date: date
    end_date: date
    reason: AbsenceReason
    hours_total: Optional[float] = None

    class Config:
        from_attributes = True
```

Replace the three vacation endpoints (lines 123–166) with:

```python
# === Absences CRUD ===

@router.get("/absences", response_model=List[AbsenceResponse])
async def list_absences(
    employee_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Список отсутствий (опционально — по сотруднику)."""
    query = db.query(Absence)
    if employee_id:
        query = query.filter(Absence.employee_id == employee_id)
    return query.order_by(Absence.start_date).all()


@router.post("/absences", response_model=AbsenceResponse, status_code=201)
async def create_absence(
    data: AbsenceCreate,
    db: Session = Depends(get_db),
):
    """Добавить отсутствие (отпуск / больничный / отгул / прочее)."""
    if data.end_date < data.start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be >= start_date",
        )
    repo = BaseRepository(Absence, db)
    absence = repo.create(data.model_dump())
    db.commit()
    db.refresh(absence)
    return absence


@router.delete("/absences/{absence_id}")
async def delete_absence(
    absence_id: str,
    db: Session = Depends(get_db),
):
    """Удалить отсутствие."""
    repo = BaseRepository(Absence, db)
    existing = repo.get(absence_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Absence not found")
    repo.delete(existing)
    db.commit()
    return {"status": "deleted", "id": absence_id}
```

- [ ] **Step 4: Run the new test file**

Run: `py -3.10 -m pytest tests/test_api_absences.py -v`
Expected: all pass.

- [ ] **Step 5: Run the full backend suite**

Run: `py -3.10 -m pytest tests/ -v`
Expected: all formerly-green tests still green.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/capacity.py tests/test_api_absences.py
git commit -m "Replace /capacity/vacations with /capacity/absences (+ reason field)"
```

---

## Phase 3 — Backend: Team on capacity + team endpoints

### Task 3.1: `team` field on `QuarterCapacityResponse`

**Files:**
- Modify: `app/services/capacity_service.py` (`QuarterCapacity` dataclass + `team_quarter_capacity`)
- Modify: `app/api/endpoints/capacity.py` (`QuarterCapacityResponse` schema + `from_dataclass`)
- Modify: `tests/test_capacity_service.py` (add `team` assertion)

- [ ] **Step 1: Write failing test**

Append to `tests/test_capacity_service.py`:

```python
class TestTeamCapacityIncludesTeamField:
    def test_team_field_populated(self, db_session):
        from app.models import Employee
        from app.services.capacity_service import CapacityService

        e1 = Employee(id="e1", jira_account_id="a1", display_name="Иванов", is_active=True, team="Alpha")
        e2 = Employee(id="e2", jira_account_id="a2", display_name="Петров", is_active=True, team=None)
        db_session.add_all([e1, e2])
        db_session.commit()

        svc = CapacityService(db_session)
        rows = svc.team_quarter_capacity(2026, 2)
        by_id = {r.employee_id: r for r in rows}
        assert by_id["e1"].team == "Alpha"
        assert by_id["e2"].team is None
```

- [ ] **Step 2: Run test to verify failure**

Run: `py -3.10 -m pytest tests/test_capacity_service.py::TestTeamCapacityIncludesTeamField -v`
Expected: fail with `AttributeError: 'QuarterCapacity' object has no attribute 'team'`.

- [ ] **Step 3: Add `team` to `QuarterCapacity` dataclass**

In `app/services/capacity_service.py`, add to the `QuarterCapacity` dataclass (the one with `total_available_hours`, around line 60):

```python
@dataclass
class QuarterCapacity:
    employee_id: str
    employee_name: str
    year: int
    quarter: int
    months: list[MonthlyCapacity]
    total_norm_hours: float
    total_vacation_hours: float
    total_mandatory_hours: float
    total_available_hours: float
    total_fact_hours: float = 0.0
    team: Optional[str] = None
```

In `team_quarter_capacity`, after building the `QuarterCapacity` object, set `result.team = employee.team`. If the current code uses a single `self.quarter_capacity(employee_id, ...)` call inside the loop, pass the team through by looking it up from the employee row (or join in the outer query).

- [ ] **Step 4: Update `QuarterCapacityResponse` schema**

In `app/api/endpoints/capacity.py` (line 93+), add `team: Optional[str] = None` to `QuarterCapacityResponse`, and pass `team=data.team` in `from_dataclass`.

- [ ] **Step 5: Run the test**

Run: `py -3.10 -m pytest tests/test_capacity_service.py::TestTeamCapacityIncludesTeamField -v`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/capacity_service.py app/api/endpoints/capacity.py tests/test_capacity_service.py
git commit -m "Include Employee.team on QuarterCapacityResponse"
```

### Task 3.2: `PUT /employees/{id}/team`

**Files:**
- Modify: `app/api/endpoints/employees.py`
- Create: `tests/test_api_employees_team.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_api_employees_team.py`:

```python
"""Тесты PUT /employees/{id}/team."""

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.database import get_db
from app.models import Employee


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def employee(db_session):
    e = Employee(id="emp1", jira_account_id="a1", display_name="Иванов",
                 is_active=True, team=None)
    db_session.add(e)
    db_session.commit()
    return e


def test_set_team(client, employee, db_session):
    r = client.put(f"/api/v1/employees/{employee.id}/team", json={"team": "Alpha"})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.get(Employee, employee.id).team == "Alpha"


def test_clear_team(client, employee, db_session):
    employee.team = "Alpha"
    db_session.commit()
    r = client.put(f"/api/v1/employees/{employee.id}/team", json={"team": None})
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Employee, employee.id).team is None


def test_404_on_missing(client):
    r = client.put("/api/v1/employees/does-not-exist/team", json={"team": "Alpha"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify failure**

Run: `py -3.10 -m pytest tests/test_api_employees_team.py -v`
Expected: all fail (endpoint 404s).

- [ ] **Step 3: Add the endpoint to `app/api/endpoints/employees.py`**

Append to `employees.py` (after `recalc_active`):

```python
class TeamUpdateRequest(BaseModel):
    team: Optional[str] = None


@router.put("/{employee_id}/team", response_model=EmployeeResponse)
def set_team(
    employee_id: str,
    req: TeamUpdateRequest,
    db: Session = Depends(get_db),
):
    """Назначить или очистить команду сотрудника.

    Значение берётся из конфигурируемых опций Jira-поля «Продуктовая команда»
    (/sync/jira-teams), но здесь не валидируется — это свободный справочник.
    """
    from fastapi import HTTPException

    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.team = (req.team or None)
    db.flush()
    # Snapshot before commit — see CLAUDE.md ORM caveat.
    response = EmployeeResponse.model_validate(emp)
    db.commit()
    return response
```

Extend `EmployeeResponse` with `team: Optional[str] = None` (line 27-ish).

- [ ] **Step 4: Run the test**

Run: `py -3.10 -m pytest tests/test_api_employees_team.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/employees.py tests/test_api_employees_team.py
git commit -m "PUT /employees/{id}/team — set or clear team"
```

### Task 3.3: Auto-detect teams — service + endpoint

**Files:**
- Create: `app/services/employee_team_service.py`
- Modify: `app/api/endpoints/employees.py` (new route)
- Create: `tests/test_employee_team_service.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_employee_team_service.py`:

```python
"""Тесты авто-определения команды сотрудника из ворклогов."""

from datetime import date, datetime, timedelta
import pytest

from app.models import Employee, Issue, Project, Worklog
from app.services.employee_team_service import EmployeeTeamService


@pytest.fixture
def seed(db_session):
    p = Project(id="p1", jira_project_id="100", key="PRJ", name="PRJ")
    db_session.add(p)
    # Issues with team set
    i_alpha = Issue(id="i_a", jira_issue_id="1", key="PRJ-1", summary="x",
                    project_id="p1", issuetype="Task", status="Готово", team="Alpha")
    i_beta = Issue(id="i_b", jira_issue_id="2", key="PRJ-2", summary="x",
                   project_id="p1", issuetype="Task", status="Готово", team="Beta")
    i_none = Issue(id="i_n", jira_issue_id="3", key="PRJ-3", summary="x",
                   project_id="p1", issuetype="Task", status="Готово", team=None)
    emp = Employee(id="e1", jira_account_id="a1", display_name="Иванов",
                   is_active=True, team=None)
    db_session.add_all([i_alpha, i_beta, i_none, emp])
    db_session.flush()
    db_session.commit()
    return {"emp": emp, "i_alpha": i_alpha, "i_beta": i_beta, "i_none": i_none}


def _log(db, emp, issue, hours, days_ago):
    w = Worklog(
        id=f"w-{emp.id}-{issue.id}-{days_ago}",
        jira_worklog_id=f"j-{emp.id}-{issue.id}-{days_ago}",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime.utcnow() - timedelta(days=days_ago),
        hours=hours, time_spent_seconds=int(hours * 3600),
    )
    db.add(w)


def test_mode_picks_dominant_team(db_session, seed):
    # Alpha: 3 logs × 2h = 6h ; Beta: 1 log × 8h = 8h  → Beta wins on total time
    _log(db_session, seed["emp"], seed["i_alpha"], 2, 5)
    _log(db_session, seed["emp"], seed["i_alpha"], 2, 10)
    _log(db_session, seed["emp"], seed["i_alpha"], 2, 15)
    _log(db_session, seed["emp"], seed["i_beta"], 8, 20)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    assert svc.auto_detect_team(seed["emp"].id) == "Beta"


def test_ignores_worklogs_outside_lookback(db_session, seed):
    _log(db_session, seed["emp"], seed["i_alpha"], 10, 200)  # outside 180 d
    _log(db_session, seed["emp"], seed["i_beta"], 2, 10)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    assert svc.auto_detect_team(seed["emp"].id) == "Beta"


def test_returns_none_when_no_teamed_logs(db_session, seed):
    _log(db_session, seed["emp"], seed["i_none"], 5, 10)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    assert svc.auto_detect_team(seed["emp"].id) is None


def test_bulk_auto_detect_all_missing(db_session, seed):
    _log(db_session, seed["emp"], seed["i_alpha"], 5, 10)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    summary = svc.auto_detect_all_missing()
    assert summary.assigned == 1
    assert summary.skipped == 0
    db_session.expire_all()
    assert db_session.get(Employee, seed["emp"].id).team == "Alpha"


def test_bulk_skips_employees_with_existing_team(db_session, seed):
    seed["emp"].team = "Preserved"
    db_session.commit()
    _log(db_session, seed["emp"], seed["i_alpha"], 5, 10)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    summary = svc.auto_detect_all_missing()
    assert summary.assigned == 0
    assert summary.skipped == 1
    db_session.expire_all()
    assert db_session.get(Employee, seed["emp"].id).team == "Preserved"
```

- [ ] **Step 2: Run tests — verify failure**

Run: `py -3.10 -m pytest tests/test_employee_team_service.py -v`
Expected: import error (service does not exist yet).

- [ ] **Step 3: Implement the service**

Create `app/services/employee_team_service.py`:

```python
"""Авто-определение команды сотрудника по ворклогам.

Мода берётся по суммарным часам на задачах с заданным `issue.team`,
в окне последних `lookback_days` дней. Возвращает None, если у сотрудника
нет worklog'ов с ненулевым team за окно.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Employee, Issue, Worklog


@dataclass
class AutoDetectSummary:
    assigned: int
    skipped: int
    details: list[dict]


class EmployeeTeamService:
    def __init__(self, db: Session):
        self.db = db

    def auto_detect_team(
        self, employee_id: str, *, lookback_days: int = 180
    ) -> Optional[str]:
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        rows = (
            self.db.query(
                Issue.team.label("team"),
                func.coalesce(func.sum(Worklog.time_spent_seconds), 0).label("seconds"),
            )
            .join(Worklog, Worklog.issue_id == Issue.id)
            .filter(
                Worklog.employee_id == employee_id,
                Worklog.started_at >= cutoff,
                Issue.team.isnot(None),
                Issue.team != "",
            )
            .group_by(Issue.team)
            .order_by(func.sum(Worklog.time_spent_seconds).desc())
            .all()
        )
        if not rows:
            return None
        return rows[0].team

    def auto_detect_all_missing(self) -> AutoDetectSummary:
        assigned = 0
        skipped = 0
        details: list[dict] = []
        employees = (
            self.db.query(Employee)
            .filter(Employee.is_active == True)  # noqa: E712
            .all()
        )
        for emp in employees:
            if emp.team:
                skipped += 1
                continue
            team = self.auto_detect_team(emp.id)
            if team is None:
                skipped += 1
                continue
            emp.team = team
            assigned += 1
            details.append({"employee_id": emp.id, "team": team})
        self.db.commit()
        return AutoDetectSummary(assigned=assigned, skipped=skipped, details=details)
```

- [ ] **Step 4: Add the endpoint**

Append to `app/api/endpoints/employees.py`:

```python
class AutoDetectResponse(BaseModel):
    assigned: int
    skipped: int
    details: List[dict]


@router.post("/auto-detect-teams", response_model=AutoDetectResponse)
def auto_detect_teams(db: Session = Depends(get_db)):
    """Массово проставить Employee.team по ворклогам (для сотрудников с team=NULL)."""
    from app.services.employee_team_service import EmployeeTeamService

    summary = EmployeeTeamService(db).auto_detect_all_missing()
    return AutoDetectResponse(
        assigned=summary.assigned,
        skipped=summary.skipped,
        details=summary.details,
    )
```

- [ ] **Step 5: Run the service tests**

Run: `py -3.10 -m pytest tests/test_employee_team_service.py -v`
Expected: all pass.

- [ ] **Step 6: Run full suite**

Run: `py -3.10 -m pytest tests/ -v`
Expected: all formerly-green tests still green.

- [ ] **Step 7: Commit**

```bash
git add app/services/employee_team_service.py app/api/endpoints/employees.py tests/test_employee_team_service.py
git commit -m "Auto-detect Employee.team from worklog mode + bulk endpoint"
```

---

## Phase 4 — Backend: rules copy + capacity xlsx

### Task 4.1: Copy rules to target quarter

**Files:**
- Modify: `app/services/capacity_service.py` (new method)
- Modify: `app/api/endpoints/capacity.py` (new endpoint + schema)
- Create: `tests/test_capacity_rules_copy.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_capacity_rules_copy.py`:

```python
"""Тесты копирования правил обязательных работ в следующий квартал."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models import MonthlyCapacityRule
from app.services.capacity_service import CapacityService, RulesConflict


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def q1_rules(db_session):
    rows = [
        MonthlyCapacityRule(id=f"r{i}", year=2026, month=m, percent_of_norm=10.0 + i)
        for i, m in enumerate([1, 2, 3])
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


def test_service_copies_rules(db_session, q1_rules):
    svc = CapacityService(db_session)
    created = svc.copy_rules_to_quarter(2026, 1, 2026, 2)
    assert created == 3
    months = {r.month: r.percent_of_norm for r in db_session.query(MonthlyCapacityRule).filter_by(year=2026).all()}
    assert months == {1: 10.0, 2: 11.0, 3: 12.0, 4: 10.0, 5: 11.0, 6: 12.0}


def test_service_rollover_q4_to_next_year_q1(db_session):
    rows = [
        MonthlyCapacityRule(id=f"r{i}", year=2026, month=m, percent_of_norm=5.0)
        for i, m in enumerate([10, 11, 12])
    ]
    db_session.add_all(rows)
    db_session.commit()
    svc = CapacityService(db_session)
    created = svc.copy_rules_to_quarter(2026, 4, 2027, 1)
    assert created == 3
    by_ym = {(r.year, r.month): r.percent_of_norm for r in db_session.query(MonthlyCapacityRule).all()}
    assert by_ym[(2027, 1)] == 5.0
    assert by_ym[(2027, 3)] == 5.0


def test_service_raises_on_conflict(db_session, q1_rules):
    db_session.add(MonthlyCapacityRule(id="rx", year=2026, month=5, percent_of_norm=1.0))
    db_session.commit()
    svc = CapacityService(db_session)
    with pytest.raises(RulesConflict) as exc:
        svc.copy_rules_to_quarter(2026, 1, 2026, 2)
    assert (2026, 5) in exc.value.conflicts


def test_service_raises_when_source_empty(db_session):
    svc = CapacityService(db_session)
    with pytest.raises(ValueError):
        svc.copy_rules_to_quarter(2025, 1, 2026, 2)


def test_endpoint_happy_path(client, q1_rules, db_session):
    r = client.post(
        "/api/v1/capacity/rules/copy-to-quarter",
        json={"from_year": 2026, "from_quarter": 1, "to_year": 2026, "to_quarter": 2},
    )
    assert r.status_code == 201, r.text
    assert r.json()["created"] == 3


def test_endpoint_409_on_conflict(client, q1_rules, db_session):
    db_session.add(MonthlyCapacityRule(id="rx", year=2026, month=5, percent_of_norm=1.0))
    db_session.commit()
    r = client.post(
        "/api/v1/capacity/rules/copy-to-quarter",
        json={"from_year": 2026, "from_quarter": 1, "to_year": 2026, "to_quarter": 2},
    )
    assert r.status_code == 409
    assert [2026, 5] in r.json()["detail"]["conflicts"]
```

- [ ] **Step 2: Run tests — verify failure**

Run: `py -3.10 -m pytest tests/test_capacity_rules_copy.py -v`
Expected: all fail (method + endpoint do not exist).

- [ ] **Step 3: Add the service method**

In `app/services/capacity_service.py`, add near the top (after dataclasses):

```python
class RulesConflict(Exception):
    def __init__(self, conflicts: list[tuple[int, int]]):
        self.conflicts = conflicts
        super().__init__(f"Target months already have rules: {conflicts}")
```

Add method to `CapacityService`:

```python
from app.models import MonthlyCapacityRule  # already imported — don't duplicate

QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}


def copy_rules_to_quarter(
    self,
    from_year: int,
    from_quarter: int,
    to_year: int,
    to_quarter: int,
) -> int:
    """Клонировать правила из (from_year, from_quarter) в (to_year, to_quarter).

    Сопоставляет M1→M1, M2→M2, M3→M3 внутри квартала.
    Raises RulesConflict если в цели уже есть правило для одного из месяцев.
    Raises ValueError если источник пуст.
    """
    src_months = QUARTER_MONTHS[from_quarter]
    dst_months = QUARTER_MONTHS[to_quarter]

    src_rules = (
        self.db.query(MonthlyCapacityRule)
        .filter(
            MonthlyCapacityRule.year == from_year,
            MonthlyCapacityRule.month.in_(src_months),
        )
        .all()
    )
    if not src_rules:
        raise ValueError(
            f"No rules found for source Q{from_quarter}/{from_year}"
        )

    by_src_month = {r.month: r for r in src_rules}

    existing = (
        self.db.query(MonthlyCapacityRule)
        .filter(
            MonthlyCapacityRule.year == to_year,
            MonthlyCapacityRule.month.in_(dst_months),
        )
        .all()
    )
    conflicts = [(to_year, e.month) for e in existing]
    if conflicts:
        raise RulesConflict(conflicts)

    created = 0
    for src_m, dst_m in zip(src_months, dst_months):
        src = by_src_month.get(src_m)
        if src is None:
            continue
        self.db.add(
            MonthlyCapacityRule(
                year=to_year,
                month=dst_m,
                percent_of_norm=src.percent_of_norm,
            )
        )
        created += 1
    self.db.commit()
    return created
```

Note: if `QUARTER_MONTHS` already exists at module top (it does in `CapacityService` per CLAUDE.md), reuse that and delete the local copy above.

- [ ] **Step 4: Add the endpoint**

In `app/api/endpoints/capacity.py`, add near the rules endpoints:

```python
class CopyRulesRequest(BaseModel):
    from_year: int
    from_quarter: int = Field(ge=1, le=4)
    to_year: int
    to_quarter: int = Field(ge=1, le=4)


class CopyRulesResponse(BaseModel):
    created: int


@router.post(
    "/rules/copy-to-quarter",
    response_model=CopyRulesResponse,
    status_code=201,
)
def copy_rules(
    req: CopyRulesRequest,
    db: Session = Depends(get_db),
):
    """Скопировать правила обязательных работ из одного квартала в другой."""
    from app.services.capacity_service import RulesConflict

    svc = CapacityService(db)
    try:
        created = svc.copy_rules_to_quarter(
            req.from_year, req.from_quarter, req.to_year, req.to_quarter
        )
    except RulesConflict as exc:
        raise HTTPException(status_code=409, detail={"conflicts": exc.conflicts})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return CopyRulesResponse(created=created)
```

- [ ] **Step 5: Run tests**

Run: `py -3.10 -m pytest tests/test_capacity_rules_copy.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/capacity_service.py app/api/endpoints/capacity.py tests/test_capacity_rules_copy.py
git commit -m "Copy monthly capacity rules to next quarter (+ endpoint)"
```

### Task 4.2: Capacity xlsx export

**Files:**
- Modify: `app/services/export_service.py`
- Modify: `app/api/endpoints/exports.py`
- Create: `tests/test_capacity_export.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_capacity_export.py`:

```python
"""Тесты экспорта capacity в xlsx."""

import io
import pytest
from openpyxl import load_workbook

from app.models import Employee
from app.services.export_service import ExportService


@pytest.fixture
def team_employees(db_session):
    rows = [
        Employee(id="e1", jira_account_id="a1", display_name="Иванов", is_active=True, team="Alpha"),
        Employee(id="e2", jira_account_id="a2", display_name="Петров", is_active=True, team="Alpha"),
        Employee(id="e3", jira_account_id="a3", display_name="Сидоров", is_active=True, team=None),
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


def test_export_capacity_xlsx_structure(db_session, team_employees):
    svc = ExportService(db_session)
    blob = svc.export_capacity_xlsx(2026, 2)

    assert isinstance(blob, bytes)
    assert len(blob) > 100

    wb = load_workbook(io.BytesIO(blob))
    ws = wb.active
    # Row 1: header with Сотрудник + months × (plan/fact/%) + totals
    header = [c.value for c in ws[1]]
    assert header[0] == "Сотрудник"
    # Three months × 3 cols each + 3 totals = 12 cols → 13 including first
    assert len(header) == 13

    # Team group rows plus employee rows must be present
    body_names = [ws.cell(r, 1).value for r in range(2, ws.max_row + 1)]
    assert "Alpha" in body_names           # team row
    assert "Без команды" in body_names      # unassigned group
    assert "Иванов" in body_names
    assert "Петров" in body_names
    assert "Сидоров" in body_names
```

- [ ] **Step 2: Run test — verify failure**

Run: `py -3.10 -m pytest tests/test_capacity_export.py -v`
Expected: fail with `AttributeError: 'ExportService' object has no attribute 'export_capacity_xlsx'`.

- [ ] **Step 3: Implement `export_capacity_xlsx`**

In `app/services/export_service.py`, add a new method on `ExportService`. Lazy-import `openpyxl` inside the method (matches the existing pattern — see CLAUDE.md):

```python
def export_capacity_xlsx(self, year: int, quarter: int) -> bytes:
    """Excel-выгрузка квартальной ёмкости команды, с группировкой по команде."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    from app.services.capacity_service import CapacityService
    from app.utils.constants import QUARTER_MONTHS, MONTH_NAMES  # if it exists; otherwise inline the maps below
    # Fallback if MONTH_NAMES not in app/utils: inline.
    MONTH_LABELS = {
        1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
        7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
    }
    Q = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}

    rows = CapacityService(self.db).team_quarter_capacity(year, quarter)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Capacity Q{quarter} {year}"

    bold = Font(bold=True)
    team_fill = PatternFill("solid", fgColor="FFF2E8")
    right = Alignment(horizontal="right")

    months = Q[quarter]
    header: list = ["Сотрудник"]
    for m in months:
        header += [f"{MONTH_LABELS[m]} План", f"{MONTH_LABELS[m]} Факт", f"{MONTH_LABELS[m]} %"]
    header += ["Итого План", "Итого Факт", "Итого %"]
    ws.append(header)
    for c in ws[1]:
        c.font = bold

    # Group rows by team, unassigned last
    groups: dict[str, list] = {}
    for r in rows:
        key = r.team or "__none__"
        groups.setdefault(key, []).append(r)
    ordered_keys = sorted([k for k in groups if k != "__none__"])
    if "__none__" in groups:
        ordered_keys.append("__none__")

    def _pct(plan: float, fact: float) -> str:
        return f"{round(fact / plan * 100)}%" if plan > 0 else "—"

    for k in ordered_keys:
        members = groups[k]
        label = "Без команды" if k == "__none__" else k
        # Team summary row
        team_plan_per_m = [
            sum((next((x for x in r.months if x.month == m), None).available_hours if next((x for x in r.months if x.month == m), None) else 0) for r in members)
            for m in months
        ]
        team_fact_per_m = [
            sum((next((x for x in r.months if x.month == m), None).fact_hours if next((x for x in r.months if x.month == m), None) else 0) for r in members)
            for m in months
        ]
        team_row: list = [label]
        for plan, fact in zip(team_plan_per_m, team_fact_per_m):
            team_row += [round(plan, 1), round(fact, 1), _pct(plan, fact)]
        total_plan = sum(r.total_available_hours for r in members)
        total_fact = sum(r.total_fact_hours for r in members)
        team_row += [round(total_plan, 1), round(total_fact, 1), _pct(total_plan, total_fact)]
        ws.append(team_row)
        for c in ws[ws.max_row]:
            c.font = bold
            c.fill = team_fill

        for r in members:
            emp_row: list = [r.employee_name]
            for m in months:
                mc = next((x for x in r.months if x.month == m), None)
                if mc is None:
                    emp_row += ["", "", ""]
                else:
                    emp_row += [round(mc.available_hours, 1), round(mc.fact_hours, 1), _pct(mc.available_hours, mc.fact_hours)]
            emp_row += [round(r.total_available_hours, 1), round(r.total_fact_hours, 1), _pct(r.total_available_hours, r.total_fact_hours)]
            ws.append(emp_row)
            for c in ws[ws.max_row][1:]:
                c.alignment = right

    ws.column_dimensions["A"].width = 28
    for col_letter in "BCDEFGHIJKLM":
        ws.column_dimensions[col_letter].width = 12

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

Note on imports: if `app.utils.constants` doesn't exist on the backend (constants are frontend-only), use the inline `MONTH_LABELS` and `Q` maps as shown above. Do not import from frontend.

- [ ] **Step 4: Add the endpoint**

In `app/api/endpoints/exports.py`, add alongside the existing exports:

```python
from fastapi.responses import Response

@router.get("/capacity.xlsx")
def export_capacity_xlsx(
    year: int,
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    """Capacity квартала в xlsx, группировка по командам."""
    from app.services.export_service import ExportService
    blob = ExportService(db).export_capacity_xlsx(year, quarter)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="capacity_Q{quarter}_{year}.xlsx"'},
    )
```

(Match the existing analytics.xlsx handler style — copy its imports + Query usage.)

- [ ] **Step 5: Run the test**

Run: `py -3.10 -m pytest tests/test_capacity_export.py -v`
Expected: pass.

- [ ] **Step 6: Run full backend suite**

Run: `py -3.10 -m pytest tests/ -v`
Expected: all formerly-green tests remain green.

- [ ] **Step 7: Commit**

```bash
git add app/services/export_service.py app/api/endpoints/exports.py tests/test_capacity_export.py
git commit -m "Capacity xlsx export — team-grouped, /exports/capacity.xlsx"
```

---

## Phase 5 — Frontend: types, absences hooks, Vacations→Absences rename

### Task 5.1: Type + API + hook rename

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/capacity.ts`
- Create: `frontend/src/api/absences.ts`
- Create: `frontend/src/hooks/useAbsences.ts`
- Modify: `frontend/src/hooks/useCapacity.ts`

- [ ] **Step 1: Add types**

In `frontend/src/types/api.ts`, replace `VacationResponse` with:

```ts
export type AbsenceReason = 'vacation' | 'sick' | 'day_off' | 'other';

export interface AbsenceResponse {
  id: string;
  employee_id: string;
  start_date: string;
  end_date: string;
  reason: AbsenceReason;
  hours_total: number | null;
}

export interface AbsenceCreateRequest {
  employee_id: string;
  start_date: string;
  end_date: string;
  reason: AbsenceReason;
  hours_total?: number;
}
```

Add `team: string | null` to `QuarterCapacityResponse` (keep all existing fields).

Add `team: string | null` to the existing `EmployeeResponse` (if it's typed on the frontend).

- [ ] **Step 2: Create `frontend/src/api/absences.ts`**

```ts
import { api } from './client';
import type { AbsenceResponse, AbsenceCreateRequest } from '../types/api';

export const getAbsences = (employeeId?: string) =>
  api.get<AbsenceResponse[]>('/capacity/absences', { employee_id: employeeId });

export const addAbsence = (data: AbsenceCreateRequest) =>
  api.post<AbsenceResponse>('/capacity/absences', data);

export const removeAbsence = (id: string) =>
  api.del(`/capacity/absences/${id}`);
```

- [ ] **Step 3: Remove vacation bits from `frontend/src/api/capacity.ts`**

Delete the three vacation functions (lines 4–9 per the grep) and their type import.

- [ ] **Step 4: Create `frontend/src/hooks/useAbsences.ts`**

```ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAbsences, addAbsence, removeAbsence } from '../api/absences';

const KEY = ['capacity', 'absences'];

export const useAbsences = () =>
  useQuery({ queryKey: KEY, queryFn: () => getAbsences() });

export const useAddAbsence = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: addAbsence,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }),
  });
};

export const useRemoveAbsence = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: removeAbsence,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }),
  });
};
```

- [ ] **Step 5: Remove `useVacations` / `useAddVacation` / `useRemoveVacation` from `frontend/src/hooks/useCapacity.ts`**

Delete lines 14–25 (per the grep). Remove the imports at line 2 that reference vacation functions.

Add in the same file (helpers for team + copy + auto-detect):

```ts
import { api } from '../api/client';

export const useSetEmployeeTeam = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, team }: { id: string; team: string | null }) =>
      api.put(`/employees/${id}/team`, { team }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useAutoDetectTeams = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<{ assigned: number; skipped: number; details: Array<{ employee_id: string; team: string }> }>(
        '/employees/auto-detect-teams',
        {},
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useCopyRules = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { from_year: number; from_quarter: number; to_year: number; to_quarter: number }) =>
      api.post<{ created: number }>('/capacity/rules/copy-to-quarter', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity', 'rules'] }),
  });
};
```

If `api.put` does not exist in `api/client.ts`, add it using the existing `api.post` pattern (one-line wrapper over `fetch(..., { method: 'PUT' })`).

- [ ] **Step 6: Run frontend lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: both pass with no errors related to missing Vacation identifiers (the page itself still imports them — Task 5.2 fixes that).

> Interim breakage is fine because these tasks go together; the next task finishes the rename on the UI.

- [ ] **Step 7: Commit (with Task 5.2 together if build broken)**

Skip commit here; commit at the end of Task 5.2 as one unit.

### Task 5.2: `AbsencesTab` component — CRUD with reason

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx` — replace `VacationsTab` with `AbsencesTab`

- [ ] **Step 1: Replace imports (line 2, 7, 12)**

```tsx
import { useTeamCapacity, useCapacityRules, useAddCapacityRule, useRemoveCapacityRule, useEmployees, useRecalcActiveEmployees, useSearchJiraUsers, useAddEmployeeFromJira, useCategoryBreakdown, useSetEmployeeTeam, useAutoDetectTeams, useCopyRules } from '../hooks/useCapacity';
import { useAbsences, useAddAbsence, useRemoveAbsence } from '../hooks/useAbsences';
import type { QuarterCapacityResponse, AbsenceResponse, AbsenceReason, CapacityRuleResponse, JiraUserSearchResult, CategoryBreakdownResponse } from '../types/api';
```

- [ ] **Step 2: Replace the `VacationsTab` component (lines 222-278) with:**

```tsx
const REASON_OPTIONS: { value: AbsenceReason; label: string; color: string }[] = [
  { value: 'vacation', label: 'Отпуск',     color: '#fa8c16' },
  { value: 'sick',     label: 'Больничный', color: '#f5222d' },
  { value: 'day_off',  label: 'Отгул',      color: '#1677ff' },
  { value: 'other',    label: 'Прочее',     color: '#8c8c8c' },
];

function reasonMeta(r: AbsenceReason) {
  return REASON_OPTIONS.find(o => o.value === r) ?? REASON_OPTIONS[0];
}

function AbsencesTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useAbsences();
  const { data: employees } = useEmployees();
  const add = useAddAbsence();
  const remove = useRemoveAbsence();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const employeeMap = new Map(employees?.map((e) => [e.id, e.display_name]));

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      {/* Heatmap is rendered by <AbsenceHeatmap/> in Task 5.3 — placeholder in this step */}
      <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>
        Добавить отсутствие
      </Button>
      <Modal
        title="Новое отсутствие"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={add.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ reason: 'vacation' }}
          onFinish={(vals) => {
            add.mutate(
              {
                employee_id: vals.employee_id,
                start_date: vals.dates[0].format('YYYY-MM-DD'),
                end_date: vals.dates[1].format('YYYY-MM-DD'),
                reason: vals.reason,
              },
              {
                onSuccess: () => {
                  setOpen(false);
                  form.resetFields();
                  notification.success({ title: 'Отсутствие добавлено' });
                },
                onError: (e) =>
                  notification.error({ title: 'Ошибка', description: e.message }),
              },
            );
          }}
        >
          <Form.Item name="employee_id" label="Сотрудник" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label"
              options={employees?.map((e) => ({ value: e.id, label: e.display_name }))} />
          </Form.Item>
          <Form.Item name="reason" label="Причина" rules={[{ required: true }]}>
            <Select options={REASON_OPTIONS.map(o => ({ value: o.value, label: o.label }))} />
          </Form.Item>
          <Form.Item name="dates" label="Даты" rules={[{ required: true }]}>
            <DatePicker.RangePicker format="DD.MM.YYYY" />
          </Form.Item>
        </Form>
      </Modal>
      <Table<AbsenceResponse>
        dataSource={data}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Сотрудник', dataIndex: 'employee_id',
            render: (id: string) => employeeMap.get(id) || id },
          { title: 'Причина', dataIndex: 'reason', width: 130,
            render: (v: AbsenceReason) => {
              const m = reasonMeta(v);
              return <span style={{ color: m.color }}>{m.label}</span>;
            },
          },
          { title: 'Начало', dataIndex: 'start_date',
            render: (v: string) => dayjs(v).format('DD.MM.YYYY') },
          { title: 'Окончание', dataIndex: 'end_date',
            render: (v: string) => dayjs(v).format('DD.MM.YYYY') },
          { title: 'Часов', dataIndex: 'hours_total',
            render: (v: number | null) => v != null ? formatHours(v) : '—' },
          {
            title: '', width: 50,
            render: (_, r) => (
              <Popconfirm title="Удалить?" onConfirm={() => remove.mutate(r.id)}>
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}
```

Update the Tabs items array (CapacityPage, line 370-ish): replace `{ key: 'vacations', label: 'Отпуска', children: <VacationsTab /> }` with `{ key: 'absences', label: 'Отсутствия', children: <AbsencesTab /> }`.

- [ ] **Step 3: Frontend lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: pass.

- [ ] **Step 4: Commit (bundles Tasks 5.1 + 5.2)**

```bash
git add frontend/src/types/api.ts frontend/src/api/absences.ts frontend/src/api/capacity.ts frontend/src/hooks/useAbsences.ts frontend/src/hooks/useCapacity.ts frontend/src/pages/CapacityPage.tsx
git commit -m "Frontend: replace Vacations with Absences tab (+ reason)"
```

### Task 5.3: `AbsenceHeatmap` component

**Files:**
- Create: `frontend/src/components/capacity/AbsenceHeatmap.tsx`
- Modify: `frontend/src/pages/CapacityPage.tsx` — render heatmap in `AbsencesTab`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/capacity/AbsenceHeatmap.tsx
import { Tooltip } from 'antd';
import dayjs from 'dayjs';
import type { AbsenceResponse, AbsenceReason } from '../../types/api';

const REASON_COLOR: Record<AbsenceReason, string> = {
  vacation: '#fa8c16',
  sick:     '#f5222d',
  day_off:  '#1677ff',
  other:    '#8c8c8c',
};
const REASON_LABEL: Record<AbsenceReason, string> = {
  vacation: 'Отпуск', sick: 'Больничный', day_off: 'Отгул', other: 'Прочее',
};

const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12],
};

interface Props {
  year: number;
  quarter: number;
  employees: Array<{ id: string; display_name: string }>;
  absences: AbsenceResponse[];
}

export default function AbsenceHeatmap({ year, quarter, employees, absences }: Props) {
  const months = QUARTER_MONTHS[quarter] ?? [];
  const start = dayjs(`${year}-${String(months[0]).padStart(2, '0')}-01`);
  const end = dayjs(`${year}-${String(months[months.length - 1]).padStart(2, '0')}-01`).endOf('month');
  const days: dayjs.Dayjs[] = [];
  for (let d = start; d.isBefore(end) || d.isSame(end, 'day'); d = d.add(1, 'day')) {
    days.push(d);
  }

  const byEmployee = new Map<string, AbsenceResponse[]>();
  for (const a of absences) {
    const arr = byEmployee.get(a.employee_id) ?? [];
    arr.push(a);
    byEmployee.set(a.employee_id, arr);
  }

  const reasonForDay = (list: AbsenceResponse[] | undefined, d: dayjs.Dayjs): AbsenceResponse | null => {
    if (!list) return null;
    for (const a of list) {
      if (d.isBefore(dayjs(a.start_date))) continue;
      if (d.isAfter(dayjs(a.end_date))) continue;
      return a;
    }
    return null;
  };

  const cell = 18;
  return (
    <div style={{ overflowX: 'auto', marginBottom: 12 }}>
      <div style={{ display: 'inline-grid', gridTemplateColumns: `180px repeat(${days.length}, ${cell}px)`, gap: 1 }}>
        <div />
        {days.map((d) => (
          <div key={d.format('YYYY-MM-DD')}
               style={{ fontSize: 9, textAlign: 'center',
                        color: d.day() === 0 || d.day() === 6 ? '#6b7a94' : '#c0c8d4' }}>
            {d.date() === 1 || d.date() % 5 === 0 ? d.date() : ''}
          </div>
        ))}
        {employees.map((e) => {
          const list = byEmployee.get(e.id);
          return (
            <>
              <div key={`${e.id}-name`} style={{ fontSize: 12, paddingRight: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {e.display_name}
              </div>
              {days.map((d) => {
                const a = reasonForDay(list, d);
                const weekend = d.day() === 0 || d.day() === 6;
                const bg = a
                  ? REASON_COLOR[a.reason]
                  : (weekend ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.06)');
                const tip = a
                  ? `${e.display_name}: ${REASON_LABEL[a.reason]}, ${dayjs(a.start_date).format('DD.MM')}–${dayjs(a.end_date).format('DD.MM')}`
                  : `${e.display_name} · ${d.format('DD.MM')}`;
                return (
                  <Tooltip key={`${e.id}-${d.format('YYYY-MM-DD')}`} title={tip} mouseEnterDelay={0.3}>
                    <div style={{ height: 18, background: bg, borderRadius: 2 }} />
                  </Tooltip>
                );
              })}
            </>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Render heatmap in `AbsencesTab`**

Edit `frontend/src/pages/CapacityPage.tsx`:

1. Add `import AbsenceHeatmap from '../components/capacity/AbsenceHeatmap';`
2. In `AbsencesTab`, replace the heatmap-placeholder line with:

```tsx
const { year, quarter } = useQuarterYear();
const activeEmployees = (employees ?? []).filter(e => e.is_active);
<AbsenceHeatmap
  year={Number(year)}
  quarter={Number(quarter)}
  employees={activeEmployees.map(e => ({ id: e.id, display_name: e.display_name }))}
  absences={data ?? []}
/>
```

(Place `useQuarterYear` call at top of `AbsencesTab`; already imported.)

- [ ] **Step 3: Build + run dev server to eyeball**

Run: `cd frontend && npm run build`
Expected: no TS errors.

Optional manual check: `npm run dev` → open `/capacity` → Отсутствия tab → grid renders, hover tooltip works.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/capacity/AbsenceHeatmap.tsx frontend/src/pages/CapacityPage.tsx
git commit -m "AbsenceHeatmap: day×employee grid on Отсутствия tab"
```

---

## Phase 6 — Frontend: TeamTab grouping, filters, toggles, overload colour

### Task 6.1: TeamTab rewrite

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx` (`TeamTab` function, lines 16-220)
- Modify: `frontend/src/utils/constants.ts` (if a named export is needed for the colours — not required)

- [ ] **Step 1: Add new state/hooks at top of `TeamTab`**

Replace the body of `TeamTab` with the version below. Key new behaviours: team filter, two AppSetting-backed toggles, tree data (team groups → employees), inline team Select, overload-red colour, "Определить команды" button, Excel export.

```tsx
import { Switch } from 'antd';
// (other imports as before + useJiraTeams from existing hook path if needed)

function TeamTab() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useTeamCapacity(year, quarter);
  const { data: employees } = useEmployees();
  const recalc = useRecalcActiveEmployees();
  const setTeam = useSetEmployeeTeam();
  const autoDetect = useAutoDetectTeams();

  // Team-filter Select uses the configured Jira team values.
  // useJiraTeams comes from the existing frontend hook that reads AppSetting + /sync/jira-teams.
  const { data: jiraTeams } = useJiraTeams();
  const teamOptions = (jiraTeams ?? []).map(t => ({ value: t, label: t }));

  const storedEmp = useGenericSetting('ui_capacity_team_filter');
  const storedTeams = useGenericSetting('ui_capacity_team_filter_teams');
  const storedShowFact = useGenericSetting('ui_capacity_show_fact');
  const storedShowPct  = useGenericSetting('ui_capacity_show_pct');
  const saveStored = useSaveGenericSetting();

  const [selectedEmpIds, setSelectedEmpIds] = useState<string[]>([]);
  const [selectedTeams, setSelectedTeams] = useState<string[]>([]);
  const [showFact, setShowFact] = useState(false);
  const [showPct,  setShowPct]  = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated) return;
    if (storedEmp.data === undefined || storedTeams.data === undefined
        || storedShowFact.data === undefined || storedShowPct.data === undefined) return;
    setSelectedEmpIds((storedEmp.data?.value || '').split(',').filter(Boolean));
    setSelectedTeams((storedTeams.data?.value || '').split(',').filter(Boolean));
    setShowFact(storedShowFact.data?.value === '1');
    setShowPct(storedShowPct.data?.value === '1');
    setHydrated(true);
  }, [hydrated, storedEmp.data, storedTeams.data, storedShowFact.data, storedShowPct.data]);

  const persist = (key: string, value: string) => saveStored.mutate({ key, value });

  // ------------ Filter visible rows ------------
  const visible = (data ?? []).filter(r => {
    if (selectedEmpIds.length && !selectedEmpIds.includes(r.employee_id)) return false;
    if (selectedTeams.length) {
      const teamKey = r.team ?? '__none__';
      if (!selectedTeams.includes(teamKey)) return false;
    }
    return true;
  });

  // ------------ Tree grouping ------------
  interface TeamRow {
    key: string;
    isTeam: true;
    employee_id: string;        // synthetic, used only as rowKey source
    employee_name: string;      // shown as team label
    team: string | null;
    months: QuarterCapacityResponse['months'];  // aggregate
    total_available_hours: number;
    total_fact_hours: number;
    children: QuarterCapacityResponse[];
  }
  const groupByTeam = (rows: QuarterCapacityResponse[]): (QuarterCapacityResponse | TeamRow)[] => {
    const buckets = new Map<string, QuarterCapacityResponse[]>();
    for (const r of rows) {
      const k = r.team ?? '__none__';
      const arr = buckets.get(k) ?? [];
      arr.push(r);
      buckets.set(k, arr);
    }
    const keys = Array.from(buckets.keys()).filter(k => k !== '__none__').sort();
    if (buckets.has('__none__')) keys.push('__none__');
    return keys.map(k => {
      const members = buckets.get(k)!;
      const monthSums: QuarterCapacityResponse['months'] = [];
      if (members[0]) {
        for (const m of members[0].months) {
          monthSums.push({
            ...m,
            available_hours: members.reduce((s, mem) => s + (mem.months.find(x => x.month === m.month)?.available_hours ?? 0), 0),
            fact_hours:      members.reduce((s, mem) => s + (mem.months.find(x => x.month === m.month)?.fact_hours ?? 0), 0),
          });
        }
      }
      const total_available_hours = members.reduce((s, m) => s + m.total_available_hours, 0);
      const total_fact_hours      = members.reduce((s, m) => s + m.total_fact_hours, 0);
      return {
        key: `team:${k}`,
        isTeam: true,
        employee_id: `team:${k}`,
        employee_name: k === '__none__' ? 'Без команды' : k,
        team: k === '__none__' ? null : k,
        months: monthSums,
        total_available_hours,
        total_fact_hours,
        children: members,
      } as TeamRow;
    });
  };
  const tree = groupByTeam(visible);

  // ------------ Cell helpers ------------
  const pctColor = (plan: number, fact: number): string | undefined => {
    if (plan <= 0) return undefined;
    const pct = (fact / plan) * 100;
    if (pct > 110) return 'var(--ant-color-error, #ff4d4f)';
    if (pct >= 100) return 'var(--ant-color-success, #52c41a)';
    if (pct < 50)  return 'var(--ant-color-text-secondary, #999)';
    return undefined;
  };
  const pctText = (plan: number, fact: number): string => {
    if (plan <= 0) return '—';
    return `${Math.round((fact / plan) * 100)}%`;
  };

  // ------------ Columns, responsive to toggles ------------
  const months = QUARTER_MONTHS[Number(quarter)] || [];
  const monthGroup = (m: number) => ({
    title: MONTH_NAMES[m],
    children: [
      { title: 'План', key: `m${m}_plan`, width: 80,
        render: (_: unknown, r: any) => {
          const mc = r.months?.find((x: any) => x.month === m);
          return mc ? formatHours(mc.available_hours) : '—';
        } },
      ...(showFact ? [{
        title: 'Факт', key: `m${m}_fact`, width: 80,
        render: (_: unknown, r: any) => {
          const mc = r.months?.find((x: any) => x.month === m);
          return mc ? formatHours(mc.fact_hours) : '—';
        },
      }] : []),
      ...(showPct ? [{
        title: '%', key: `m${m}_pct`, width: 60,
        render: (_: unknown, r: any) => {
          const mc = r.months?.find((x: any) => x.month === m);
          if (!mc) return '—';
          return (
            <span style={{ color: pctColor(mc.available_hours, mc.fact_hours) }}>
              {pctText(mc.available_hours, mc.fact_hours)}
            </span>
          );
        },
      }] : []),
    ],
  });

  const nameColumn = {
    title: 'Сотрудник', key: 'name', fixed: 'left' as const, width: 260,
    render: (_: unknown, r: any) => {
      if (r.isTeam) {
        return <span style={{ fontWeight: 600 }}>{r.employee_name} <Text type="secondary">· {r.children.length}</Text></span>;
      }
      const currentTeam = r.team ?? undefined;
      return (
        <Space>
          <span>{r.employee_name}</span>
          <Select
            size="small"
            style={{ minWidth: 140 }}
            placeholder="Без команды"
            allowClear
            value={currentTeam}
            options={teamOptions}
            onChange={(val) => setTeam.mutate({ id: r.employee_id, team: val ?? null })}
            showSearch optionFilterProp="label"
          />
        </Space>
      );
    },
  };

  const columns = [
    nameColumn,
    ...months.map(monthGroup),
    {
      title: 'Итого',
      children: [
        { title: 'План', dataIndex: 'total_available_hours', render: formatHours, width: 90 },
        ...(showFact ? [{ title: 'Факт', dataIndex: 'total_fact_hours', render: formatHours, width: 90 }] : []),
        ...(showPct ? [{
          title: '%', width: 70,
          render: (_: unknown, r: any) => (
            <span style={{ color: pctColor(r.total_available_hours, r.total_fact_hours) }}>
              {pctText(r.total_available_hours, r.total_fact_hours)}
            </span>
          ),
        }] : []),
      ],
    },
  ];

  // ------------ Download xlsx ------------
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
  const exportHref = `${apiBase}/exports/capacity.xlsx?year=${year}&quarter=${quarter}`;

  // ------------ Add-employee modal (unchanged — keep the existing code block) ------------
  // … (leave existing Modal + AutoComplete from original TeamTab as-is; omitted here for brevity)

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Select mode="multiple" allowClear placeholder="Фильтр по команде"
          style={{ minWidth: 220 }}
          value={selectedTeams}
          onChange={(v) => { setSelectedTeams(v); persist('ui_capacity_team_filter_teams', v.join(',')); }}
          options={[...teamOptions, { value: '__none__', label: 'Без команды' }]}
          showSearch optionFilterProp="label"
        />
        <Select mode="multiple" allowClear placeholder="Фильтр по сотруднику"
          style={{ minWidth: 260 }}
          value={selectedEmpIds}
          onChange={(v) => { setSelectedEmpIds(v); persist('ui_capacity_team_filter', v.join(',')); }}
          options={(employees ?? []).filter(e => e.is_active)
            .map(e => ({ value: e.id, label: e.display_name }))}
          showSearch optionFilterProp="label"
        />
        <Space>
          <Switch checked={showFact} onChange={(v) => { setShowFact(v); persist('ui_capacity_show_fact', v ? '1' : '0'); }} />
          <Text>Факт</Text>
          <Switch checked={showPct} onChange={(v) => { setShowPct(v); persist('ui_capacity_show_pct', v ? '1' : '0'); }} />
          <Text>%</Text>
        </Space>
        <Popconfirm
          title="Определить команды по ворклогам для всех без команды?"
          okText="Определить" cancelText="Отмена"
          onConfirm={() => autoDetect.mutate(undefined, {
            onSuccess: (s) => notification.success({
              title: 'Команды обновлены',
              description: `Назначено: ${s.assigned}, пропущено: ${s.skipped}`,
            }),
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          })}
        >
          <Button loading={autoDetect.isPending}>Определить команды авто</Button>
        </Popconfirm>
        <Popconfirm
          title="Пересчитать состав по worklog'ам активных задач?"
          okText="Пересчитать" cancelText="Отмена"
          okButtonProps={{ danger: true }}
          onConfirm={() => recalc.mutate(undefined, {
            onSuccess: (s) => notification.success({ title: 'Состав обновлён',
              description: `Активировано: ${s.activated}, деактивировано: ${s.deactivated}` }),
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          })}
        >
          <Button loading={recalc.isPending}>Пересчитать состав</Button>
        </Popconfirm>
        <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>Добавить сотрудника</Button>
        <Button href={exportHref} target="_blank" rel="noreferrer">Экспорт в Excel</Button>
      </Space>
      <Table
        dataSource={tree}
        rowKey="key"
        loading={isLoading}
        columns={columns as any}
        pagination={false}
        size="small"
        scroll={{ x: 1400 }}
        expandable={{ defaultExpandAllRows: true, childrenColumnName: 'children' }}
        rowClassName={(r: any) => r.isTeam ? 'capacity-team-row' : ''}
      />
      {/* … existing Add-employee Modal block preserved … */}
    </Space>
  );
}
```

Add CSS for the team-row highlight — in `frontend/src/index.css` (or the closest page-level CSS):

```css
.capacity-team-row td {
  background: rgba(250, 140, 22, 0.06);
}
```

Keep the existing Add-employee Modal block (`Modal`, `AutoComplete`, `useSearchJiraUsers`) — do not delete it; just ensure it still renders inside `TeamTab`.

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run lint && npm run build`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/CapacityPage.tsx frontend/src/index.css
git commit -m "TeamTab v2: team grouping, filters, toggles, inline team edit, overload red"
```

---

## Phase 7 — Frontend: RulesTab copy-to-quarter

### Task 7.1: Copy button

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx` (`RulesTab`)

- [ ] **Step 1: Add the button**

Inside `RulesTab`, alongside the existing "Добавить правило" button:

```tsx
const { year, quarter } = useQuarterYear();
const copy = useCopyRules();

const next = () => {
  const q = Number(quarter);
  return q === 4 ? { y: Number(year) + 1, q: 1 } : { y: Number(year), q: q + 1 };
};
const { y: toYear, q: toQuarter } = next();

<Popconfirm
  title={`Скопировать правила из Q${quarter} ${year} в Q${toQuarter} ${toYear}?`}
  okText="Скопировать" cancelText="Отмена"
  onConfirm={() => copy.mutate(
    { from_year: Number(year), from_quarter: Number(quarter), to_year: toYear, to_quarter: toQuarter },
    {
      onSuccess: (s) => notification.success({
        title: 'Скопировано',
        description: `Создано правил: ${s.created}`,
      }),
      onError: (e: any) => {
        const detail = e?.body?.detail?.conflicts as number[][] | undefined;
        if (detail) {
          const months = detail.map(([y, m]) => `${MONTH_NAMES[m]} ${y}`).join(', ');
          notification.warning({ title: 'Конфликт', description: `В цели уже есть правила: ${months}` });
        } else {
          notification.error({ title: 'Ошибка', description: e.message });
        }
      },
    },
  )}
>
  <Button loading={copy.isPending}>Скопировать в следующий квартал</Button>
</Popconfirm>
```

> Note: `e.body` on errors comes from `api/client.ts` — if it doesn't exist there, swap for reading `e.message` text that contains the conflict list, or extend the error object in `client.ts` (small single-line change).

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/CapacityPage.tsx
git commit -m "RulesTab: copy rules to next quarter button"
```

---

## Phase 8 — E2E + seed

### Task 8.1: E2E seed gets a team

**Files:**
- Modify: `scripts/seed_e2e.py`

- [ ] **Step 1: Assign a team to `E2E Analyst`**

Find the Employee creation in `scripts/seed_e2e.py` and add `team='E2E'`:

```python
employee = Employee(
    id='e2e-employee',
    jira_account_id='e2e-account',
    display_name='E2E Analyst',
    email='e2e@example.com',
    is_active=True,
    team='E2E',
)
```

- [ ] **Step 2: Re-seed**

Run: `py -3.10 scripts/seed_e2e.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_e2e.py
git commit -m "E2E seed: assign team to E2E Analyst"
```

### Task 8.2: Playwright — Absences tab + column toggles + rules copy

**Files:**
- Create: `frontend/e2e/capacity-v2.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '@playwright/test';

test.describe('Capacity v2', () => {
  test('column toggles persist', async ({ page }) => {
    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Команда' }).click();

    // Факт + % columns hidden by default
    await expect(page.getByRole('columnheader', { name: 'Факт', exact: true })).toHaveCount(0);

    await page.getByRole('switch').first().click();  // Факт
    await expect(page.getByRole('columnheader', { name: 'Факт', exact: true })).toBeVisible();

    await page.reload();
    await expect(page.getByRole('columnheader', { name: 'Факт', exact: true })).toBeVisible();
  });

  test('team group row renders and collapses', async ({ page }) => {
    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Команда' }).click();
    await expect(page.getByText('E2E', { exact: true })).toBeVisible();        // team row
    await expect(page.getByText('E2E Analyst')).toBeVisible();                 // child row
  });

  test('Отсутствия: add a sick leave, heatmap cell appears', async ({ page }) => {
    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Отсутствия' }).click();

    await page.getByRole('button', { name: 'Добавить отсутствие' }).click();
    await page.getByLabel('Сотрудник').click();
    await page.getByRole('option', { name: 'E2E Analyst' }).click();
    await page.getByLabel('Причина').click();
    await page.getByRole('option', { name: 'Больничный' }).click();
    // Range picker — open; pick two days in current quarter.
    // … implementation-specific selectors omitted here; follow existing e2e patterns.
    await page.getByRole('button', { name: 'OK' }).click();

    await expect(page.locator('td').filter({ hasText: 'Больничный' })).toBeVisible();
  });

  test('Правила: copy to next quarter', async ({ page }) => {
    // Seed a rule first via API; assumes /api/v1 at 8010.
    await page.request.post('http://localhost:8010/api/v1/capacity/rules', {
      data: { year: 2026, month: 4, percent_of_norm: 12 },
    });

    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Правила' }).click();
    await page.getByRole('button', { name: /Скопировать в следующий квартал/ }).click();
    await page.getByRole('button', { name: 'Скопировать' }).click();

    await expect(page.getByText(/Создано правил:/)).toBeVisible();
  });
});
```

- [ ] **Step 2: Run Playwright**

Run: `cd frontend && npm run e2e -- capacity-v2.spec.ts`
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/capacity-v2.spec.ts
git commit -m "E2E: capacity v2 — toggles, grouping, absence+heatmap, rules copy"
```

---

## Phase 9 — Final verification

### Task 9.1: Full suite + smoke + push

- [ ] **Step 1: Backend tests**

Run: `py -3.10 -m pytest tests/ -v`
Expected: all formerly-green tests still green; new tests green.

- [ ] **Step 2: Frontend build + lint**

Run: `cd frontend && npm run lint && npm run build`
Expected: pass.

- [ ] **Step 3: Local smoke**

Run: `py -3.10 scripts/local_smoke.py`
Expected: backend + frontend start, `/capacity` loads, all four tabs render, no console errors.

- [ ] **Step 4: Push**

```bash
git push origin main
```

Expected: CI green.
