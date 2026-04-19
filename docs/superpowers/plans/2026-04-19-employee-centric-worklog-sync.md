# Employee-centric worklog sync + team membership — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Видеть ворклоги сотрудников команды на задачах вне scope, ловить back-dated записи при обновлении, безопасно разделить «обновить» и «полная перезагрузка».

**Architecture:** Новая M:N таблица `employee_teams` с флагом `is_primary`; флаг `Issue.out_of_scope` для задач, ингестированных через ворклоги сотрудников; два SyncService-метода — `update_worklogs_since` (upsert-only, оба ведра) и существующий `reload_worklogs_since` (delete+re-insert, для ручной очистки). JQL переезжает на `updated >= since` для ловли back-dated.

**Tech Stack:** FastAPI / SQLAlchemy 2.0 / Alembic (batch mode) / pytest / React 19 + TypeScript 6 + AntD 6 + TanStack Query

**Spec:** [docs/superpowers/specs/2026-04-19-employee-centric-worklog-sync-design.md](../specs/2026-04-19-employee-centric-worklog-sync-design.md)

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `alembic/versions/019_employee_teams_and_out_of_scope.py` | Create | Таблица `employee_teams`, колонка `issues.out_of_scope`, дата-миграция из `employees.team` |
| `app/models/employee_team.py` | Create | ORM модель EmployeeTeam |
| `app/models/__init__.py` | Modify | Экспорт EmployeeTeam |
| `app/models/employee.py` | Modify | Relationship `teams`, helper `primary_team_name` |
| `app/models/issue.py` | Modify | Колонка `out_of_scope: bool` |
| `app/services/employee_team_service.py` | Modify | CRUD методы + инвариант single-primary |
| `app/api/endpoints/employees.py` | Modify | Новые endpoint'ы, `with_teams` в list, deprecate single-team PUT |
| `app/services/sync_service.py` | Modify | Новый `update_worklogs_since`, Ведро B helpers |
| `app/api/endpoints/sync.py` | Modify | Новый `POST /sync/worklogs/update/stream` |
| `tests/test_employee_team_model.py` | Create | Unit-тесты модели/сервиса |
| `tests/test_employee_teams_endpoints.py` | Create | Интеграционные тесты CRUD |
| `tests/test_sync_service_update.py` | Create | Тесты `update_worklogs_since` (back-dated, upsert, Ведро B) |
| `tests/test_sync_update_endpoint.py` | Create | Тест SSE-стрима нового endpoint'а |
| `frontend/src/types/api.ts` | Modify | EmployeeTeam типы, EmployeeResponse.teams |
| `frontend/src/api/employees.ts` | Modify | Клиенты для CRUD employee_teams |
| `frontend/src/api/sync.ts` | Modify | `updateWorklogsStream` SSE-клиент |
| `frontend/src/hooks/useCapacity.ts` | Modify | `useSetEmployeeTeams`, `useEmployeesWithTeams` |
| `frontend/src/hooks/useSync.ts` | Modify | `useUpdateWorklogs` mutation |
| `frontend/src/pages/CapacityPage.tsx` | Modify | Multi-select с primary в TeamTab |
| `frontend/src/pages/SyncPage.tsx` | Modify | Split «Обновить» / «Полная перезагрузка», чекбокс «включить команды» |
| `CLAUDE.md` | Modify | Описать M:N employee_teams + update vs reload |

---

## Phase 1 — Data model

### Task 1: Создать модель EmployeeTeam

**Files:**
- Create: `app/models/employee_team.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/employee.py`
- Test: `tests/test_employee_team_model.py`

- [ ] **Step 1: Write failing test for model existence + fields**

```python
# tests/test_employee_team_model.py
"""Tests for EmployeeTeam model."""

from datetime import datetime
import pytest

from app.models import Employee, EmployeeTeam


def test_employee_team_fields(db_session):
    emp = Employee(
        id="emp-1",
        jira_account_id="acc-1",
        display_name="Test",
        is_active=True,
        synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.commit()

    et = EmployeeTeam(
        id="et-1",
        employee_id=emp.id,
        team="Team A",
        is_primary=True,
    )
    db_session.add(et)
    db_session.commit()

    loaded = db_session.query(EmployeeTeam).one()
    assert loaded.employee_id == "emp-1"
    assert loaded.team == "Team A"
    assert loaded.is_primary is True
    assert loaded.created_at is not None


def test_employee_relationship_teams(db_session):
    emp = Employee(
        id="emp-2", jira_account_id="acc-2", display_name="E",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(id="et-a", employee_id="emp-2", team="A", is_primary=True))
    db_session.add(EmployeeTeam(id="et-b", employee_id="emp-2", team="B", is_primary=False))
    db_session.commit()

    emp = db_session.query(Employee).filter_by(id="emp-2").one()
    team_names = sorted(t.team for t in emp.teams)
    assert team_names == ["A", "B"]
    assert emp.primary_team_name() == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_employee_team_model.py -v`
Expected: ImportError — `EmployeeTeam` does not exist.

- [ ] **Step 3: Create EmployeeTeam model**

Write `app/models/employee_team.py`:

```python
"""EmployeeTeam model - M:N employee ↔ team membership."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import generate_uuid
from app.database import Base


class EmployeeTeam(Base):
    """Членство сотрудника в команде.

    Сотрудник может состоять в нескольких командах (кросс-функциональные
    роли, матричный менеджмент). Ровно одна из записей для данного
    employee_id должна иметь ``is_primary=True`` — она используется для
    агрегаций Capacity (план/факт, % загрузки).

    Инвариант single-primary enforce'ится в EmployeeTeamService, а не в БД:
    SQLite не поддерживает partial unique index.
    """

    __tablename__ = "employee_teams"
    __table_args__ = (
        UniqueConstraint("employee_id", "team", name="uq_employee_teams_employee_team"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    employee = relationship("Employee", back_populates="teams")

    def __repr__(self) -> str:
        return f"<EmployeeTeam {self.employee_id}:{self.team}{' *' if self.is_primary else ''}>"
```

- [ ] **Step 4: Update Employee model — add relationship + helper**

Modify `app/models/employee.py` — replace the relationships block:

```python
    # Relationships
    worklogs = relationship("Worklog", back_populates="employee")
    comments = relationship("Comment", back_populates="author")
    absences = relationship("Absence", back_populates="employee")
    teams = relationship(
        "EmployeeTeam",
        back_populates="employee",
        cascade="all, delete-orphan",
    )

    def primary_team_name(self) -> Optional[str]:
        """Название primary-команды (берётся из teams relationship)."""
        for t in self.teams:
            if t.is_primary:
                return t.team
        return None

    def __repr__(self) -> str:
        return f"<Employee {self.display_name}>"
```

- [ ] **Step 5: Export from package**

Modify `app/models/__init__.py` — add import and `__all__` entry:

```python
from app.models.employee_team import EmployeeTeam  # after Employee import
```
And add `"EmployeeTeam",` to the `__all__` list (alphabetically near Employee).

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_employee_team_model.py -v`
Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/models/employee_team.py app/models/__init__.py app/models/employee.py tests/test_employee_team_model.py
git commit -m "feat(model): EmployeeTeam M:N for multi-team membership"
```

---

### Task 2: Issue.out_of_scope колонка

**Files:**
- Modify: `app/models/issue.py`
- Test: `tests/test_employee_team_model.py` (добавляем тест там же для простоты)

- [ ] **Step 1: Write failing test**

Append to `tests/test_employee_team_model.py`:

```python
def test_issue_out_of_scope_defaults_false(db_session):
    from app.models import Project, Issue

    proj = Project(
        id="p-1", jira_project_id="10000", key="PRJ",
        name="Test", is_archived=False,
        synced_at=datetime.utcnow(),
    )
    db_session.add(proj)
    issue = Issue(
        id="i-1", jira_issue_id="20000", key="PRJ-1",
        project_id="p-1", summary="t", issue_type="Task",
        status="Open", status_category="new",
        synced_at=datetime.utcnow(),
    )
    db_session.add(issue)
    db_session.commit()

    loaded = db_session.query(Issue).one()
    assert loaded.out_of_scope is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_employee_team_model.py::test_issue_out_of_scope_defaults_false -v`
Expected: AttributeError — `out_of_scope` missing.

- [ ] **Step 3: Add column**

Modify `app/models/issue.py` — find the other boolean columns and add right after `include_in_analysis`:

```python
    out_of_scope: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True,
    )
```

(Don't forget to add `Boolean` to the import if not present — check the file's existing imports first.)

- [ ] **Step 4: Run test**

Run: `py -3.10 -m pytest tests/test_employee_team_model.py::test_issue_out_of_scope_defaults_false -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/issue.py tests/test_employee_team_model.py
git commit -m "feat(model): Issue.out_of_scope flag"
```

---

### Task 3: Alembic migration

**Files:**
- Create: `alembic/versions/019_employee_teams_and_out_of_scope.py`

- [ ] **Step 1: Create migration file**

```python
"""employee_teams table + issues.out_of_scope + data migration

Revision ID: 019_employee_teams_and_out_of_scope
Revises: 018_rename_vacations_to_absences
Create Date: 2026-04-19
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '019_employee_teams_and_out_of_scope'
down_revision: Union[str, None] = '018_rename_vacations_to_absences'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. employee_teams
    op.create_table(
        'employee_teams',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('employee_id', sa.String(36), nullable=False),
        sa.Column('team', sa.String(100), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['employee_id'], ['employees.id'],
            ondelete='CASCADE',
            name='fk_employee_teams_employee_id',
        ),
        sa.UniqueConstraint('employee_id', 'team', name='uq_employee_teams_employee_team'),
    )
    op.create_index('ix_employee_teams_employee_id', 'employee_teams', ['employee_id'])
    op.create_index('ix_employee_teams_team', 'employee_teams', ['team'])

    # 2. issues.out_of_scope
    with op.batch_alter_table('issues') as batch:
        batch.add_column(sa.Column(
            'out_of_scope', sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ))
    op.create_index('ix_issues_out_of_scope', 'issues', ['out_of_scope'])

    # 3. Data migration: copy employees.team → employee_teams(is_primary=true)
    bind = op.get_bind()
    now = datetime.utcnow().isoformat()
    rows = bind.execute(sa.text(
        "SELECT id, team FROM employees WHERE team IS NOT NULL AND team != ''"
    )).fetchall()
    for emp_id, team in rows:
        bind.execute(sa.text(
            "INSERT INTO employee_teams (id, employee_id, team, is_primary, created_at) "
            "VALUES (:id, :eid, :team, 1, :now)"
        ), {"id": str(uuid.uuid4()), "eid": emp_id, "team": team, "now": now})


def downgrade() -> None:
    op.drop_index('ix_issues_out_of_scope', table_name='issues')
    with op.batch_alter_table('issues') as batch:
        batch.drop_column('out_of_scope')

    op.drop_index('ix_employee_teams_team', table_name='employee_teams')
    op.drop_index('ix_employee_teams_employee_id', table_name='employee_teams')
    op.drop_table('employee_teams')
```

- [ ] **Step 2: Verify revision chain**

Run: `py -3.10 -m alembic history | head -5`
Expected: new revision `019_employee_teams_and_out_of_scope` appears, previous is `018_rename_vacations_to_absences`.

- [ ] **Step 3: Apply to dev DB**

Run: `py -3.10 -m alembic upgrade head`
Expected: `Running upgrade 018_rename_vacations_to_absences -> 019_employee_teams_and_out_of_scope` success.

- [ ] **Step 4: Verify schema + data migrated**

Run: `py -3.10 -c "from app.database import engine; from sqlalchemy import text; c = engine.connect(); print(list(c.execute(text('SELECT COUNT(*) FROM employee_teams WHERE is_primary=1')))); print(list(c.execute(text('SELECT name FROM pragma_table_info(\"issues\") WHERE name=\"out_of_scope\"'))))"`
Expected: count ≥ number of employees with non-null team, and one row showing `out_of_scope`.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/019_employee_teams_and_out_of_scope.py
git commit -m "migration: employee_teams M:N + issues.out_of_scope"
```

---

## Phase 2 — Team membership service + API

### Task 4: EmployeeTeamService CRUD + single-primary invariant

**Files:**
- Modify: `app/services/employee_team_service.py`
- Test: `tests/test_employee_team_model.py` (добавляем `TestEmployeeTeamService` class туда же)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_employee_team_model.py`:

```python
class TestEmployeeTeamService:
    def _make_emp(self, db, eid="emp-x"):
        emp = Employee(
            id=eid, jira_account_id=f"acc-{eid}",
            display_name=eid, is_active=True,
            synced_at=datetime.utcnow(),
        )
        db.add(emp)
        db.commit()
        return emp

    def test_add_team_first_becomes_primary(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "Team A")
        rows = db_session.query(EmployeeTeam).filter_by(employee_id=emp.id).all()
        assert len(rows) == 1
        assert rows[0].is_primary is True

    def test_add_second_team_not_primary(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.add_team(emp.id, "B")
        primaries = db_session.query(EmployeeTeam).filter_by(
            employee_id=emp.id, is_primary=True
        ).all()
        assert len(primaries) == 1
        assert primaries[0].team == "A"

    def test_set_primary_reassigns(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.add_team(emp.id, "B")
        svc.set_primary(emp.id, "B")
        primaries = db_session.query(EmployeeTeam).filter_by(
            employee_id=emp.id, is_primary=True
        ).all()
        assert len(primaries) == 1
        assert primaries[0].team == "B"

    def test_remove_team_reassigns_primary_if_needed(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.add_team(emp.id, "B")
        svc.remove_team(emp.id, "A")
        primaries = db_session.query(EmployeeTeam).filter_by(
            employee_id=emp.id, is_primary=True
        ).all()
        assert len(primaries) == 1
        assert primaries[0].team == "B"

    def test_remove_last_team_ok(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.remove_team(emp.id, "A")
        assert db_session.query(EmployeeTeam).filter_by(employee_id=emp.id).count() == 0

    def test_legacy_team_column_mirrors_primary(self, db_session):
        """Employee.team всегда = имя primary team (derived). Пишется сервисом
        для обратной совместимости с существующими запросами."""
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        db_session.refresh(emp)
        assert emp.team == "A"
        svc.add_team(emp.id, "B")
        svc.set_primary(emp.id, "B")
        db_session.refresh(emp)
        assert emp.team == "B"
        svc.remove_team(emp.id, "B")
        db_session.refresh(emp)
        assert emp.team == "A"  # B removed, A was only remaining → auto-primary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/test_employee_team_model.py::TestEmployeeTeamService -v`
Expected: fails (methods missing on service).

- [ ] **Step 3: Extend EmployeeTeamService**

Modify `app/services/employee_team_service.py` — append new methods inside the existing class (keep auto_detect methods untouched):

```python
    def _recompute_legacy_team(self, employee_id: str) -> None:
        """Обновить ``Employee.team`` = имя primary membership (или None).

        Derived-колонка для backward-compat с кодом, который ещё читает
        ``Employee.team`` напрямую. Вызывается из всех мутаций.
        """
        primary = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.is_primary == True)  # noqa: E712
            .one_or_none()
        )
        emp = self.db.query(Employee).filter(Employee.id == employee_id).one()
        emp.team = primary.team if primary else None

    def list_teams(self, employee_id: str) -> list["EmployeeTeam"]:
        return (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id)
            .order_by(EmployeeTeam.is_primary.desc(), EmployeeTeam.team)
            .all()
        )

    def add_team(self, employee_id: str, team: str, *, is_primary: bool = False) -> "EmployeeTeam":
        """Добавить команду. Если у сотрудника ещё нет команд — становится primary
        автоматически, независимо от ``is_primary`` аргумента.
        """
        existing = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .one_or_none()
        )
        if existing is not None:
            if is_primary and not existing.is_primary:
                self.set_primary(employee_id, team)
            return existing

        has_any = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id)
            .count()
        ) > 0
        make_primary = is_primary or not has_any
        if make_primary:
            # Сбросить у других
            self.db.query(EmployeeTeam).filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.is_primary == True,  # noqa: E712
            ).update({EmployeeTeam.is_primary: False}, synchronize_session=False)

        row = EmployeeTeam(
            employee_id=employee_id,
            team=team,
            is_primary=make_primary,
        )
        self.db.add(row)
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(row)
        return row

    def remove_team(self, employee_id: str, team: str) -> None:
        row = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .one_or_none()
        )
        if row is None:
            return
        was_primary = row.is_primary
        self.db.delete(row)
        self.db.flush()
        if was_primary:
            # Промоутим любую оставшуюся (отсортировано по team для детерминизма).
            leftover = (
                self.db.query(EmployeeTeam)
                .filter(EmployeeTeam.employee_id == employee_id)
                .order_by(EmployeeTeam.team)
                .first()
            )
            if leftover is not None:
                leftover.is_primary = True
        self._recompute_legacy_team(employee_id)
        self.db.commit()

    def set_primary(self, employee_id: str, team: str) -> None:
        target = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .one_or_none()
        )
        if target is None:
            raise ValueError(f"Employee {employee_id} not in team {team!r}")
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id,
        ).update({EmployeeTeam.is_primary: False}, synchronize_session=False)
        target.is_primary = True
        self._recompute_legacy_team(employee_id)
        self.db.commit()

    def replace_teams(
        self,
        employee_id: str,
        teams: list[str],
        primary: Optional[str] = None,
    ) -> list["EmployeeTeam"]:
        """Заменить весь набор. Если primary указан — делает его primary,
        иначе — первую команду в списке. Пустой список очищает всё.
        """
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id,
        ).delete(synchronize_session=False)
        self.db.flush()
        chosen_primary = primary if primary in teams else (teams[0] if teams else None)
        for t in teams:
            self.db.add(EmployeeTeam(
                employee_id=employee_id,
                team=t,
                is_primary=(t == chosen_primary),
            ))
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        return self.list_teams(employee_id)
```

And add imports at the top of the file:

```python
from app.models import Category, Employee, EmployeeTeam, Issue, Worklog
```

(replace the existing import line that lists models).

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_employee_team_model.py::TestEmployeeTeamService -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/employee_team_service.py tests/test_employee_team_model.py
git commit -m "feat(service): EmployeeTeamService CRUD + single-primary invariant"
```

---

### Task 5: API endpoints для employee_teams

**Files:**
- Modify: `app/api/endpoints/employees.py`
- Create: `tests/test_employee_teams_endpoints.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_employee_teams_endpoints.py
"""Integration tests for /employees/{id}/teams endpoints."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def emp(db_session):
    e = Employee(
        id="emp-1", jira_account_id="acc-1", display_name="Test",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(e)
    db_session.commit()
    return e


def test_get_teams_empty(client, emp):
    resp = client.get(f"/api/v1/employees/{emp.id}/teams")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_team_first_is_primary(client, emp):
    resp = client.post(
        f"/api/v1/employees/{emp.id}/teams", json={"team": "Alpha"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team"] == "Alpha"
    assert body["is_primary"] is True


def test_put_teams_replaces_and_sets_primary(client, emp):
    resp = client.put(
        f"/api/v1/employees/{emp.id}/teams",
        json={"teams": ["A", "B", "C"], "primary": "B"},
    )
    assert resp.status_code == 200
    body = resp.json()
    names = {r["team"] for r in body}
    assert names == {"A", "B", "C"}
    primaries = [r for r in body if r["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["team"] == "B"


def test_delete_team(client, emp):
    client.post(f"/api/v1/employees/{emp.id}/teams", json={"team": "A"})
    client.post(f"/api/v1/employees/{emp.id}/teams", json={"team": "B"})
    resp = client.delete(f"/api/v1/employees/{emp.id}/teams/A")
    assert resp.status_code == 204
    remaining = client.get(f"/api/v1/employees/{emp.id}/teams").json()
    assert [r["team"] for r in remaining] == ["B"]
    assert remaining[0]["is_primary"] is True


def test_put_primary(client, emp):
    client.put(
        f"/api/v1/employees/{emp.id}/teams",
        json={"teams": ["A", "B"], "primary": "A"},
    )
    resp = client.put(
        f"/api/v1/employees/{emp.id}/teams/primary", json={"team": "B"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert next(r for r in body if r["team"] == "B")["is_primary"] is True
    assert next(r for r in body if r["team"] == "A")["is_primary"] is False


def test_put_primary_unknown_team_404(client, emp):
    client.post(f"/api/v1/employees/{emp.id}/teams", json={"team": "A"})
    resp = client.put(
        f"/api/v1/employees/{emp.id}/teams/primary", json={"team": "Nope"}
    )
    assert resp.status_code == 404


def test_list_employees_with_teams(client, emp):
    client.put(
        f"/api/v1/employees/{emp.id}/teams",
        json={"teams": ["A", "B"], "primary": "B"},
    )
    resp = client.get("/api/v1/employees?with_teams=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["teams"] == [
        {"team": "B", "is_primary": True},
        {"team": "A", "is_primary": False},
    ]


def test_legacy_put_team_still_works(client, emp):
    resp = client.put(
        f"/api/v1/employees/{emp.id}/team", json={"team": "Legacy"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team"] == "Legacy"
    teams = client.get(f"/api/v1/employees/{emp.id}/teams").json()
    assert teams == [{"team": "Legacy", "is_primary": True}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/test_employee_teams_endpoints.py -v`
Expected: all fail (endpoints missing).

- [ ] **Step 3: Add endpoints + response models + update list endpoint**

Modify `app/api/endpoints/employees.py` — add new response model and endpoints. Full replacement of the file:

```python
"""Employees API endpoints.

Список сотрудников для использования во фронтенде (выпадающие списки и т.п.).
"""

from datetime import datetime
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, EmployeeTeam
from app.services.employee_team_service import EmployeeTeamService


router = APIRouter()


class EmployeeTeamItem(BaseModel):
    team: str
    is_primary: bool

    model_config = {"from_attributes": True}


class EmployeeResponse(BaseModel):
    id: str
    jira_account_id: str
    display_name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    team: Optional[str] = None  # legacy: имя primary team
    teams: Optional[List[EmployeeTeamItem]] = None  # присутствует только если with_teams=true

    model_config = {"from_attributes": True}


class EmployeeFromJiraRequest(BaseModel):
    jira_account_id: str
    display_name: str
    email: Optional[str] = None
    is_active: bool = True
    avatar_url: Optional[str] = None


class RecalcActiveResponse(BaseModel):
    activated: int
    deactivated: int
    total_active: int


@router.get("", response_model=List[EmployeeResponse])
def list_employees(
    is_active: Optional[bool] = Query(None),
    with_teams: bool = Query(False, description="Включить M:N teams в ответ"),
    db: Session = Depends(get_db),
):
    """Список сотрудников."""
    query = db.query(Employee).order_by(Employee.display_name)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    employees = query.all()

    result: List[EmployeeResponse] = []
    for e in employees:
        payload = EmployeeResponse.model_validate(e)
        if with_teams:
            # Отсортировать: primary первым, потом по имени.
            teams = sorted(
                e.teams,
                key=lambda t: (not t.is_primary, t.team),
            )
            payload.teams = [EmployeeTeamItem.model_validate(t) for t in teams]
        result.append(payload)
    return result


@router.post("/from-jira", response_model=EmployeeResponse)
def employee_from_jira(
    req: EmployeeFromJiraRequest,
    db: Session = Depends(get_db),
):
    """Явное добавление сотрудника из Jira (автокомплит на фронте)."""
    existing = (
        db.query(Employee)
        .filter(Employee.jira_account_id == req.jira_account_id)
        .one_or_none()
    )
    if existing is None:
        existing = Employee(
            id=str(uuid.uuid4()),
            jira_account_id=req.jira_account_id,
            display_name=req.display_name,
            email=req.email,
            avatar_url=req.avatar_url,
            is_active=True,
            synced_at=datetime.utcnow(),
        )
        db.add(existing)
    else:
        existing.display_name = req.display_name
        existing.email = req.email
        existing.avatar_url = req.avatar_url
        existing.is_active = True
        existing.synced_at = datetime.utcnow()

    db.flush()
    response = EmployeeResponse.model_validate(existing)
    db.commit()
    return response


@router.post("/recalc-active", response_model=RecalcActiveResponse)
def recalc_active(db: Session = Depends(get_db)):
    from app.services.employee_service import EmployeeService

    stats = EmployeeService(db).recalc_active_by_categories()
    return RecalcActiveResponse(
        activated=stats.activated,
        deactivated=stats.deactivated,
        total_active=stats.total_active,
    )


class AutoDetectResponse(BaseModel):
    assigned: int
    skipped: int
    details: List[dict]


@router.post("/auto-detect-teams", response_model=AutoDetectResponse)
def auto_detect_teams(db: Session = Depends(get_db)):
    summary = EmployeeTeamService(db).auto_detect_all_missing()
    return AutoDetectResponse(
        assigned=summary.assigned,
        skipped=summary.skipped,
        details=summary.details,
    )


# ─── Legacy single-team endpoint (deprecated, kept for compat) ───

class TeamUpdateRequest(BaseModel):
    team: Optional[str] = None


@router.put(
    "/{employee_id}/team",
    response_model=EmployeeResponse,
    deprecated=True,
    description="Deprecated — используйте /teams endpoints для multi-team",
)
def set_team_legacy(
    employee_id: str,
    req: TeamUpdateRequest,
    db: Session = Depends(get_db),
):
    """Заменяет все membership одной командой и делает её primary.
    Пустое значение = очистить все membership."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    svc = EmployeeTeamService(db)
    if req.team:
        svc.replace_teams(employee_id, [req.team], primary=req.team)
    else:
        svc.replace_teams(employee_id, [])
    db.refresh(emp)
    return EmployeeResponse.model_validate(emp)


# ─── New M:N team endpoints ───

class AddTeamRequest(BaseModel):
    team: str
    is_primary: bool = False


class ReplaceTeamsRequest(BaseModel):
    teams: List[str]
    primary: Optional[str] = None


class SetPrimaryRequest(BaseModel):
    team: str


@router.get("/{employee_id}/teams", response_model=List[EmployeeTeamItem])
def get_teams(employee_id: str, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    rows = EmployeeTeamService(db).list_teams(employee_id)
    return [EmployeeTeamItem.model_validate(r) for r in rows]


@router.post("/{employee_id}/teams", response_model=EmployeeTeamItem)
def post_team(
    employee_id: str,
    req: AddTeamRequest,
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    row = EmployeeTeamService(db).add_team(
        employee_id, req.team, is_primary=req.is_primary,
    )
    return EmployeeTeamItem.model_validate(row)


@router.put("/{employee_id}/teams", response_model=List[EmployeeTeamItem])
def put_teams(
    employee_id: str,
    req: ReplaceTeamsRequest,
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    rows = EmployeeTeamService(db).replace_teams(
        employee_id, req.teams, primary=req.primary,
    )
    return [EmployeeTeamItem.model_validate(r) for r in rows]


@router.delete("/{employee_id}/teams/{team}", status_code=204)
def delete_team(
    employee_id: str,
    team: str,
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    EmployeeTeamService(db).remove_team(employee_id, team)
    return Response(status_code=204)


@router.put("/{employee_id}/teams/primary", response_model=List[EmployeeTeamItem])
def put_primary(
    employee_id: str,
    req: SetPrimaryRequest,
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    svc = EmployeeTeamService(db)
    try:
        svc.set_primary(employee_id, req.team)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Employee not in team {req.team!r}")
    rows = svc.list_teams(employee_id)
    return [EmployeeTeamItem.model_validate(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_employee_teams_endpoints.py -v`
Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/employees.py tests/test_employee_teams_endpoints.py
git commit -m "feat(api): employee_teams CRUD endpoints + with_teams=true in list"
```

---

## Phase 3 — Sync service: Ведро A + Ведро B с upsert-only

### Task 6: `update_worklogs_since` — Ведро A с `updated >= since` JQL

**Files:**
- Modify: `app/services/sync_service.py`
- Create: `tests/test_sync_service_update.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sync_service_update.py
"""Tests for SyncService.update_worklogs_since (upsert-only)."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService


@pytest.fixture
def project(db_session):
    p = Project(
        id="p-1", jira_project_id="10000", key="PRJ",
        name="Test", is_archived=False,
        synced_at=datetime.utcnow(),
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def issue(db_session, project):
    i = Issue(
        id="i-1", jira_issue_id="20000", key="PRJ-1",
        project_id=project.id, summary="s", issue_type="Task",
        status="Open", status_category="new",
        synced_at=datetime.utcnow(),
    )
    db_session.add(i)
    db_session.commit()
    return i


def _fake_issue(jira_id: str, key: str):
    return SimpleNamespace(
        id=jira_id, key=key,
        fields=SimpleNamespace(
            summary="s",
            issuetype=SimpleNamespace(name="Task"),
            status=SimpleNamespace(
                name="Open",
                statusCategory=SimpleNamespace(key="new"),
            ),
            project=SimpleNamespace(id="10000", key="PRJ", name="Test"),
        ),
    )


def _fake_worklog(wl_id: str, started_iso: str, author_id="acc-1", seconds=3600):
    # started_datetime uses UTC-naive to match production parser output
    return SimpleNamespace(
        id=wl_id,
        started_datetime=datetime.fromisoformat(started_iso),
        time_spent_seconds=seconds,
        author=SimpleNamespace(
            accountId=author_id,
            displayName="Author",
            emailAddress=None,
        ),
        comment=None,
    )


@pytest.mark.asyncio
async def test_update_does_not_delete_existing(db_session, issue):
    """Reload удаляет worklogs; update — нет."""
    # Pre-existing worklog before since
    pre = Worklog(
        id="w-old", jira_worklog_id="old-1",
        issue_id=issue.id, employee_id=None,
        started_at=datetime(2026, 1, 1),
        time_spent_seconds=3600,
        synced_at=datetime.utcnow(),
    )
    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add_all([emp, pre])
    pre.employee_id = emp.id
    db_session.commit()

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        # No issues matched
        if False:
            yield
        return
    jira.iter_issues = fake_iter_issues

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 2, 1))
    assert stats.deleted == 0
    # Old worklog still present
    assert db_session.query(Worklog).filter_by(id="w-old").one() is not None


@pytest.mark.asyncio
async def test_update_catches_back_dated_via_updated_jql(db_session, issue):
    """issue.updated = сегодня, worklog.started в прошлом < since — ловим."""
    captured_jqls: list[str] = []
    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        captured_jqls.append(jql)
        yield _fake_issue("20000", "PRJ-1")
    jira.iter_issues = fake_iter_issues

    async def fake_iter_worklogs_for_issue(jira_issue_id):
        # started BEFORE since (2026-02-01), but should still land because
        # JQL is now based on issue.updated
        yield _fake_worklog("wl-backdated", "2026-01-20T10:00:00")
    jira.iter_worklogs_for_issue = fake_iter_worklogs_for_issue

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 2, 1))
    assert any("updated" in q for q in captured_jqls)
    assert stats.worklogs_upserted == 1
    wl = db_session.query(Worklog).filter_by(jira_worklog_id="wl-backdated").one()
    assert wl.started_at == datetime(2026, 1, 20, 10, 0, 0)


@pytest.mark.asyncio
async def test_update_upserts_changed_started_at(db_session, issue):
    """Повторный upsert с изменённым started_at обновляет запись, не плодит дубль."""
    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(Worklog(
        id="w-1", jira_worklog_id="wl-1",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 2, 5, 10),
        time_spent_seconds=3600,
        synced_at=datetime.utcnow(),
    ))
    db_session.commit()

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        yield _fake_issue("20000", "PRJ-1")
    jira.iter_issues = fake_iter_issues

    async def fake_iter_worklogs_for_issue(jira_issue_id):
        yield _fake_worklog("wl-1", "2026-02-05T14:00:00")  # новый started
    jira.iter_worklogs_for_issue = fake_iter_worklogs_for_issue

    svc = SyncService(db_session, jira)
    await svc.update_worklogs_since(date(2026, 2, 1))

    wls = db_session.query(Worklog).filter_by(jira_worklog_id="wl-1").all()
    assert len(wls) == 1
    assert wls[0].started_at == datetime(2026, 2, 5, 14, 0, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/test_sync_service_update.py -v`
Expected: all fail (method missing).

- [ ] **Step 3: Add `UpdateStats` dataclass + `update_worklogs_since`**

Modify `app/services/sync_service.py` — add dataclass right after `ReloadStats`:

```python
@dataclass
class UpdateStats:
    """Результат мягкого обновления ворклогов (без удаления).

    ``bucket_a_*`` — проход по всем issue с ``updated >= since``.
    ``bucket_b_*`` — проход по ворклогам сотрудников выбранных команд
    (включая задачи вне scope, которые создаются с ``out_of_scope=True``).
    """

    bucket_a_issues_scanned: int = 0
    bucket_a_worklogs_upserted: int = 0
    bucket_b_issues_scanned: int = 0
    bucket_b_worklogs_upserted: int = 0
    bucket_b_out_of_scope_created: int = 0

    @property
    def worklogs_upserted(self) -> int:
        return self.bucket_a_worklogs_upserted + self.bucket_b_worklogs_upserted

    @property
    def deleted(self) -> int:
        # Семантическая константа — update никогда не удаляет, нужна для
        # совместимости с SSE-обёрткой, которая уже знает это поле.
        return 0
```

Then add the method inside `SyncService`, next to `reload_worklogs_since`:

```python
    async def update_worklogs_since(
        self,
        since: date,
        teams: Optional[List[str]] = None,
        on_progress: Optional[
            Callable[["UpdateStats", Optional[str]], Awaitable[None]]
        ] = None,
    ) -> "UpdateStats":
        """Мягкое обновление ворклогов: upsert без удаления.

        - **Ведро A** (всегда): JQL ``updated >= since``. Для каждого issue,
          уже существующего локально, перечитываются ворклоги и upsert'ятся.
          Незнакомые issue пропускаются.
        - **Ведро B** (если ``teams`` задан): JQL
          ``worklogAuthor = <id> AND updated >= since`` по каждому сотруднику
          из ``employee_teams.team IN teams``. Незнакомые issue создаются
          с ``out_of_scope=True``.

        Ничего не удаляет и не трогает ``sync_state``. Прогресс — через
        ``on_progress(stats, current_key)``.
        """
        stats = UpdateStats()
        since_iso = since.isoformat()

        # ─── Ведро A ───
        jql_a = f'updated >= "{since_iso}"'
        async for jira_issue in self.jira.iter_issues(
            jql_a,
            fields=["summary", "issuetype", "status", "project"],
            max_results=100,
        ):
            await self._check_cancelled()
            local = (
                self.db.query(Issue)
                .filter(Issue.jira_issue_id == jira_issue.id)
                .one_or_none()
            )
            if local is None:
                continue
            stats.bucket_a_issues_scanned += 1
            async for wl in self.jira.iter_worklogs_for_issue(jira_issue.id):
                author_schema = JiraUserSchema(
                    accountId=wl.author.accountId,
                    displayName=wl.author.displayName,
                    emailAddress=wl.author.emailAddress,
                    active=True,
                )
                employee = self._ensure_employee(author_schema)
                self._upsert_worklog(wl, local.id, employee.id)
                stats.bucket_a_worklogs_upserted += 1
            self.db.commit()
            if on_progress is not None:
                await on_progress(stats, jira_issue.key)

        # ─── Ведро B ───
        if teams:
            await self._update_worklogs_bucket_b(
                since_iso, teams, stats, on_progress,
            )

        return stats

    async def _update_worklogs_bucket_b(
        self,
        since_iso: str,
        teams: List[str],
        stats: "UpdateStats",
        on_progress,
    ) -> None:
        """Ведро B — placeholder, реализуется в Task 7."""
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_sync_service_update.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_service.py tests/test_sync_service_update.py
git commit -m "feat(sync): update_worklogs_since (Bucket A, upsert-only, updated>= JQL)"
```

---

### Task 7: Ведро B — employee-centric sync

**Files:**
- Modify: `app/services/sync_service.py`
- Modify: `tests/test_sync_service_update.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sync_service_update.py`:

```python
@pytest.mark.asyncio
async def test_bucket_b_creates_out_of_scope_issue(db_session):
    """Ворклог сотрудника команды на чужой задаче → создаётся Issue(out_of_scope=True)."""
    from app.models import EmployeeTeam

    # Employee in team "Alpha"
    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id="et-1", employee_id="e-1", team="Alpha", is_primary=True,
    ))
    db_session.commit()

    jira = MagicMock()
    a_calls: list[str] = []
    b_calls: list[str] = []

    async def fake_iter_issues(jql, fields=None, max_results=100):
        if "worklogAuthor" in jql:
            b_calls.append(jql)
            yield _fake_issue("30000", "OTHER-1")  # not in local DB
        else:
            a_calls.append(jql)
            if False:
                yield

    async def fake_iter_worklogs_for_issue(jira_issue_id):
        yield _fake_worklog("wl-b", "2026-02-10T10:00:00", author_id="acc-1")

    jira.iter_issues = fake_iter_issues
    jira.iter_worklogs_for_issue = fake_iter_worklogs_for_issue

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 2, 1), teams=["Alpha"])

    assert stats.bucket_b_out_of_scope_created == 1
    assert stats.bucket_b_worklogs_upserted == 1
    created = db_session.query(Issue).filter_by(jira_issue_id="30000").one()
    assert created.out_of_scope is True
    assert created.key == "OTHER-1"
    # Project auto-created too
    assert created.project_id is not None


@pytest.mark.asyncio
async def test_bucket_b_does_not_clobber_in_scope(db_session, issue):
    """Existing in-scope issue (out_of_scope=False) остаётся in-scope даже если
    Ведро B находит по ней ворклоги нашего сотрудника."""
    from app.models import EmployeeTeam

    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id="et-1", employee_id="e-1", team="Alpha", is_primary=True,
    ))
    db_session.commit()

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        if "worklogAuthor" in jql:
            yield _fake_issue("20000", "PRJ-1")  # EXISTS in DB as in-scope
        else:
            if False:
                yield

    async def fake_iter_worklogs_for_issue(jira_issue_id):
        yield _fake_worklog("wl-b", "2026-02-10T10:00:00", author_id="acc-1")

    jira.iter_issues = fake_iter_issues
    jira.iter_worklogs_for_issue = fake_iter_worklogs_for_issue

    svc = SyncService(db_session, jira)
    await svc.update_worklogs_since(date(2026, 2, 1), teams=["Alpha"])

    db_session.refresh(issue)
    assert issue.out_of_scope is False


@pytest.mark.asyncio
async def test_bucket_b_skips_when_team_has_no_employees(db_session):
    """Если в ``employee_teams`` нет записей для заданной команды — пропускаем."""
    jira = MagicMock()
    calls: list[str] = []

    async def fake_iter_issues(jql, fields=None, max_results=100):
        calls.append(jql)
        if False:
            yield

    jira.iter_issues = fake_iter_issues

    svc = SyncService(db_session, jira)
    await svc.update_worklogs_since(date(2026, 2, 1), teams=["NonexistentTeam"])
    # Only Bucket A JQL fired, no Bucket B
    assert all("worklogAuthor" not in q for q in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/test_sync_service_update.py -v -k bucket_b`
Expected: all 3 fail.

- [ ] **Step 3: Implement Ведро B**

Modify `app/services/sync_service.py` — replace the placeholder body of `_update_worklogs_bucket_b` with:

```python
    async def _update_worklogs_bucket_b(
        self,
        since_iso: str,
        teams: List[str],
        stats: "UpdateStats",
        on_progress,
    ) -> None:
        """Employee-centric проход. Для каждого сотрудника из указанных
        команд — JQL по ``worklogAuthor``. Незнакомые issue создаём
        с ``out_of_scope=True``; их ворклоги от ЛЮБОГО автора (не только
        наших) попадают в БД, чтобы не разделять граф."""
        from app.models import EmployeeTeam

        # Собрать distinct accountId сотрудников в этих командах
        emps = (
            self.db.query(Employee)
            .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .filter(EmployeeTeam.team.in_(teams))
            .distinct()
            .all()
        )
        for emp in emps:
            await self._check_cancelled()
            jql = f'worklogAuthor = "{emp.jira_account_id}" AND updated >= "{since_iso}"'
            async for jira_issue in self.jira.iter_issues(
                jql,
                fields=["summary", "issuetype", "status", "project"],
                max_results=100,
            ):
                await self._check_cancelled()
                local = (
                    self.db.query(Issue)
                    .filter(Issue.jira_issue_id == jira_issue.id)
                    .one_or_none()
                )
                if local is None:
                    local = self._create_out_of_scope_issue(jira_issue)
                    stats.bucket_b_out_of_scope_created += 1
                stats.bucket_b_issues_scanned += 1
                async for wl in self.jira.iter_worklogs_for_issue(jira_issue.id):
                    author_schema = JiraUserSchema(
                        accountId=wl.author.accountId,
                        displayName=wl.author.displayName,
                        emailAddress=wl.author.emailAddress,
                        active=True,
                    )
                    employee = self._ensure_employee(author_schema)
                    self._upsert_worklog(wl, local.id, employee.id)
                    stats.bucket_b_worklogs_upserted += 1
                self.db.commit()
                if on_progress is not None:
                    await on_progress(stats, jira_issue.key)

    def _create_out_of_scope_issue(self, jira_issue) -> "Issue":
        """Создать Issue с ``out_of_scope=True`` + автосоздать Project
        если его нет. Минимальный набор полей — summary/type/status/project."""
        proj_payload = jira_issue.fields.project
        project = (
            self.db.query(Project)
            .filter(Project.jira_project_id == proj_payload.id)
            .one_or_none()
        )
        if project is None:
            project = Project(
                jira_project_id=proj_payload.id,
                key=proj_payload.key,
                name=proj_payload.name,
                is_archived=False,
                synced_at=datetime.utcnow(),
            )
            self.db.add(project)
            self.db.flush()

        status_obj = jira_issue.fields.status
        status_cat = None
        cat_obj = getattr(status_obj, "statusCategory", None)
        if cat_obj is not None:
            status_cat = getattr(cat_obj, "key", None)

        issue = Issue(
            jira_issue_id=jira_issue.id,
            key=jira_issue.key,
            project_id=project.id,
            summary=jira_issue.fields.summary,
            issue_type=jira_issue.fields.issuetype.name,
            status=status_obj.name,
            status_category=status_cat,
            out_of_scope=True,
            synced_at=datetime.utcnow(),
        )
        self.db.add(issue)
        self.db.flush()
        return issue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_sync_service_update.py -v`
Expected: all 6 tests PASS (3 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_service.py tests/test_sync_service_update.py
git commit -m "feat(sync): Bucket B — employee-centric sync with out_of_scope ingest"
```

---

### Task 8: SSE endpoint `POST /sync/worklogs/update/stream`

**Files:**
- Modify: `app/api/endpoints/sync.py`
- Create: `tests/test_sync_update_endpoint.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_sync_update_endpoint.py
"""Tests for POST /sync/worklogs/update/stream SSE endpoint."""

import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services.sync_service import UpdateStats


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@asynccontextmanager
async def _fake_jira_ctx(*args, **kwargs):
    yield object()


def _parse_sse(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def test_update_stream_emits_progress_and_done(client, db_session):
    from app.models import AppSetting
    db_session.query(AppSetting).first()  # pin session to thread

    async def fake_update(self, since, teams=None, on_progress=None):
        stats = UpdateStats(
            bucket_a_issues_scanned=1,
            bucket_a_worklogs_upserted=2,
        )
        if on_progress is not None:
            await on_progress(stats, "PRJ-1")
        stats.bucket_b_out_of_scope_created = 1
        stats.bucket_b_worklogs_upserted = 3
        if on_progress is not None:
            await on_progress(stats, "OTHER-1")
        return stats

    with patch(
        "app.api.endpoints.sync.JiraClient.from_db",
        return_value=_fake_jira_ctx(),
    ), patch(
        "app.services.sync_service.SyncService.update_worklogs_since",
        new=fake_update,
    ):
        with client.stream(
            "POST",
            "/api/v1/sync/worklogs/update/stream",
            json={"since": "2026-02-01", "teams": ["Alpha"]},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert types[0] == "progress"
    assert types[-1] == "done"
    done = events[-1]
    assert done == {
        "type": "done",
        "bucket_a_issues_scanned": 1,
        "bucket_a_worklogs_upserted": 2,
        "bucket_b_issues_scanned": 0,
        "bucket_b_worklogs_upserted": 3,
        "bucket_b_out_of_scope_created": 1,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_sync_update_endpoint.py -v`
Expected: 404 — endpoint missing.

- [ ] **Step 3: Add endpoint**

Modify `app/api/endpoints/sync.py` — update the import line for sync_service:

```python
from app.services.sync_service import SyncService, SyncStats, ReloadStats, UpdateStats
```

Add new Pydantic body schema near other request classes (after `WorklogReloadRequest`):

```python
class WorklogUpdateRequest(BaseModel):
    """Запрос на мягкое обновление ворклогов (upsert, без удаления)."""
    since: date
    teams: Optional[List[str]] = None
```

Add the endpoint right after `reload_worklogs_stream`:

```python
@router.post("/worklogs/update/stream")
async def update_worklogs_stream(
    req: WorklogUpdateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """SSE-стрим мягкого обновления ворклогов.

    Два прохода:
    1. Ведро A — ``updated >= since`` JQL, upsert по известным Issue;
    2. Ведро B (если ``teams`` указан) — ``worklogAuthor`` по сотрудникам
       перечисленных команд; неизвестные Issue создаются с
       ``out_of_scope=True``.

    События: ``progress`` после каждого issue, ``done`` — финальные stats,
    ``error`` — ошибка, ``cancelled`` — клиент отключился.
    """

    async def event_gen():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(stats: UpdateStats, current_key: Optional[str]) -> None:
            await queue.put({
                "type": "progress",
                "bucket_a_issues_scanned": stats.bucket_a_issues_scanned,
                "bucket_a_worklogs_upserted": stats.bucket_a_worklogs_upserted,
                "bucket_b_issues_scanned": stats.bucket_b_issues_scanned,
                "bucket_b_worklogs_upserted": stats.bucket_b_worklogs_upserted,
                "bucket_b_out_of_scope_created": stats.bucket_b_out_of_scope_created,
                "current_key": current_key,
            })

        async def run() -> None:
            try:
                async with JiraClient.from_db(db) as jira:
                    service = SyncService(
                        db, jira,
                        cancel_check=_disconnect_checker(http_request),
                    )
                    stats = await service.update_worklogs_since(
                        req.since, teams=req.teams, on_progress=on_progress,
                    )
                await queue.put({
                    "type": "done",
                    "bucket_a_issues_scanned": stats.bucket_a_issues_scanned,
                    "bucket_a_worklogs_upserted": stats.bucket_a_worklogs_upserted,
                    "bucket_b_issues_scanned": stats.bucket_b_issues_scanned,
                    "bucket_b_worklogs_upserted": stats.bucket_b_worklogs_upserted,
                    "bucket_b_out_of_scope_created": stats.bucket_b_out_of_scope_created,
                })
            except asyncio.CancelledError:
                await queue.put({"type": "cancelled"})
                raise
            except JiraClientError as e:
                await queue.put({"type": "error", "detail": f"Jira error: {e}"})
            except Exception as e:
                await queue.put({"type": "error", "detail": str(e)})

        task = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                if event["type"] in ("done", "error", "cancelled"):
                    break
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.10 -m pytest tests/test_sync_update_endpoint.py -v`
Expected: PASS.

- [ ] **Step 5: Full backend test suite check**

Run: `py -3.10 -m pytest tests/ --ignore=tests/test_sync_service.py --ignore=tests/test_hierarchy_rules_endpoints.py -q`
Expected: all pass (except pre-existing skips).

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/sync.py tests/test_sync_update_endpoint.py
git commit -m "feat(api): POST /sync/worklogs/update/stream SSE endpoint"
```

---

## Phase 4 — Frontend: multi-team membership UI

### Task 9: API types + employees client

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/employees.ts` (create if missing)

- [ ] **Step 1: Check if employees.ts exists and list current types**

Run: `cat frontend/src/api/employees.ts 2>/dev/null || echo "CREATE"`
Run: `grep -n "EmployeeResponse\|EmployeeTeam" frontend/src/types/api.ts`

- [ ] **Step 2: Update types**

Modify `frontend/src/types/api.ts` — find `EmployeeResponse` interface and update; add new types near it:

```typescript
export interface EmployeeTeamItem {
  team: string;
  is_primary: boolean;
}

export interface EmployeeResponse {
  id: string;
  jira_account_id: string;
  display_name: string;
  email: string | null;
  avatar_url: string | null;
  is_active: boolean;
  team: string | null;  // legacy: имя primary team
  teams?: EmployeeTeamItem[];  // присутствует только если запросили with_teams=true
}
```

- [ ] **Step 3: Add/extend employees API client**

Modify (or create) `frontend/src/api/employees.ts`:

```typescript
import { api } from './client';
import type { EmployeeResponse, EmployeeTeamItem } from '../types/api';

export const getEmployees = (params?: { is_active?: boolean; with_teams?: boolean }) => {
  const qp: Record<string, string> = {};
  if (params?.is_active !== undefined) qp.is_active = String(params.is_active);
  if (params?.with_teams) qp.with_teams = 'true';
  return api.get<EmployeeResponse[]>('/employees', qp);
};

export const getEmployeeTeams = (employeeId: string) =>
  api.get<EmployeeTeamItem[]>(`/employees/${employeeId}/teams`);

export const replaceEmployeeTeams = (
  employeeId: string,
  body: { teams: string[]; primary?: string },
) => api.put<EmployeeTeamItem[]>(`/employees/${employeeId}/teams`, body);

export const setEmployeePrimaryTeam = (employeeId: string, team: string) =>
  api.put<EmployeeTeamItem[]>(`/employees/${employeeId}/teams/primary`, { team });

export const deleteEmployeeTeam = (employeeId: string, team: string) =>
  api.del<void>(`/employees/${employeeId}/teams/${encodeURIComponent(team)}`);
```

- [ ] **Step 4: Verify frontend build**

Run: `cd frontend && npm run build`
Expected: success, no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/employees.ts
git commit -m "feat(frontend): employee teams types + API client"
```

---

### Task 10: Hooks for multi-team CRUD

**Files:**
- Modify: `frontend/src/hooks/useCapacity.ts`

- [ ] **Step 1: Find existing `useSetEmployeeTeam` definition**

Run: `grep -n "useSetEmployeeTeam\|setEmployeeTeam" frontend/src/hooks/useCapacity.ts frontend/src/api/capacity.ts`

- [ ] **Step 2: Add new hooks**

Modify `frontend/src/hooks/useCapacity.ts` — add imports and new hooks:

```typescript
import {
  replaceEmployeeTeams, setEmployeePrimaryTeam,
} from '../api/employees';

// ... existing hooks kept intact ...

export const useReplaceEmployeeTeams = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ employeeId, teams, primary }: {
      employeeId: string;
      teams: string[];
      primary?: string;
    }) => replaceEmployeeTeams(employeeId, { teams, primary }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useSetPrimaryTeam = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ employeeId, team }: { employeeId: string; team: string }) =>
      setEmployeePrimaryTeam(employeeId, team),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useCapacity.ts
git commit -m "feat(frontend): useReplaceEmployeeTeams + useSetPrimaryTeam hooks"
```

---

### Task 11: TeamTab multi-select UI

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 1: Locate the current single-team Select**

Run: `grep -n "useSetEmployeeTeam\|setTeam\.mutate" frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 2: Update useEmployees hook to accept params**

Modify `frontend/src/hooks/useCapacity.ts` — replace the existing `useEmployees`:

```typescript
export const useEmployees = (params?: { withTeams?: boolean; isActive?: boolean }) =>
  useQuery({
    queryKey: ['employees', params?.withTeams ?? false, params?.isActive ?? null],
    queryFn: () => getEmployees({
      with_teams: params?.withTeams,
      is_active: params?.isActive,
    }),
    staleTime: 30_000,
  });
```

Existing callers without args keep working (params undefined). `getEmployees` already accepts `with_teams` from Task 9.

Run: `cd frontend && npm run build`
Expected: success.

- [ ] **Step 3: Replace single Select with multi + primary handling**

Modify `frontend/src/pages/CapacityPage.tsx`. Replace the current hook import and the team-column render. Locate the block:

```tsx
const setTeam = useSetEmployeeTeam();
```

Replace with:

```tsx
const setTeam = useSetEmployeeTeam();           // kept for legacy single-team fallback
const replaceTeams = useReplaceEmployeeTeams();
const setPrimary = useSetPrimaryTeam();
```

Update imports at the top of the file:

```tsx
import {
  useTeamCapacity, useCapacityRules, useAddCapacityRule, useRemoveCapacityRule,
  useEmployees, useRecalcActiveEmployees, useSearchJiraUsers, useAddEmployeeFromJira,
  useCategoryBreakdown, useSetEmployeeTeam, useAutoDetectTeams, useCopyRules,
  useReplaceEmployeeTeams, useSetPrimaryTeam,
} from '../hooks/useCapacity';
```

Then find the single-team column's `Select` (around line 219 — "value={currentTeam}"). Replace it with a multi-select that shows the full `teams` array and a dropdown action to set primary. Full replacement of that `render`:

```tsx
render: (_: unknown, r: TreeRow) => {
  if ('isTeam' in r) {
    return <Text strong>{r.team ?? 'без команды'}</Text>;
  }
  const teams = r.teams ?? [];
  const primary = teams.find(t => t.is_primary)?.team;
  const value = teams.map(t => t.team);
  return (
    <Select
      mode="multiple"
      allowClear
      size="small"
      style={{ width: 220 }}
      placeholder="Команды"
      value={value}
      options={teamOptions}
      onChange={(next) => replaceTeams.mutate({
        employeeId: r.employee_id,
        teams: next,
        primary: next.includes(primary ?? '') ? primary : next[0],
      })}
      onDropdownVisibleChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
      loading={jiraTeams.isFetching}
      tagRender={(props) => {
        const isPrimary = props.value === primary;
        return (
          <Tag
            color={isPrimary ? 'gold' : 'default'}
            closable={props.closable}
            onClose={props.onClose}
            style={{ marginInlineEnd: 4, cursor: 'pointer' }}
            onClick={() => {
              if (!isPrimary) {
                setPrimary.mutate({ employeeId: r.employee_id, team: String(props.value) });
              }
            }}
            title={isPrimary ? 'Основная команда' : 'Клик — сделать основной'}
          >
            {isPrimary ? '★ ' : ''}{props.label}
          </Tag>
        );
      }}
    />
  );
},
```

(Requires `Tag` in AntD imports — it's already imported in the file; verify.)

Also update the data source: the employees-per-row currently read `r.team`. Change the `useEmployees` hook invocation to request `with_teams=true`, and make sure `QuarterCapacityResponse` (or the row type) includes `teams?: EmployeeTeamItem[]`.

Search for where `useEmployees` is called in the file and hook behavior, then update `frontend/src/api/capacity.ts` / `useCapacity.ts` accordingly. Expected shape inside TeamTab row: `{employee_id, display_name, team (primary name for grouping), teams: [{team, is_primary}], plan_hours, fact_hours, ...}`.

Backend side: the capacity endpoint already joins via `Employee.team` primary, so for minimal impact on backend we fetch `teams` separately via `useEmployees({with_teams: true})` and zip by employee_id in the page. Draft:

```tsx
const employeesFull = useEmployees({ withTeams: true });
const teamsByEmpId = useMemo(() => {
  const m = new Map<string, EmployeeTeamItem[]>();
  (employeesFull.data ?? []).forEach(e => m.set(e.id, e.teams ?? []));
  return m;
}, [employeesFull.data]);
```

And inside render:

```tsx
const teams = teamsByEmpId.get(r.employee_id) ?? [];
```

(Replaces `const teams = r.teams ?? []` above.)

- [ ] **Step 4: Build & lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: build succeeds; lint may show pre-existing warnings but no new errors in the touched files.

- [ ] **Step 5: Smoke test**

Start dev servers:
- Backend: `py -3.10 -m uvicorn app.main:app --port 8000 --reload`
- Frontend: `cd frontend && npm run dev`

Open `http://localhost:5173/capacity`, navigate to TeamTab:
- Each employee row shows multi-select of current teams
- Primary team has ★ and gold color
- Click non-primary tag → becomes primary (API call fires)
- Add a team from dropdown → appears without ★; removing all and re-adding one makes it primary
- Persistence: refresh page, state sticks

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/CapacityPage.tsx frontend/src/hooks/useCapacity.ts
git commit -m "feat(frontend): TeamTab multi-team select with primary toggle"
```

---

## Phase 5 — Frontend: split reload/update buttons

### Task 12: SSE client for update

**Files:**
- Modify: `frontend/src/api/sync.ts`

- [ ] **Step 1: Add types and stream client**

Append to `frontend/src/api/sync.ts`:

```typescript
export type WorklogUpdateProgress = {
  type: 'progress';
  bucket_a_issues_scanned: number;
  bucket_a_worklogs_upserted: number;
  bucket_b_issues_scanned: number;
  bucket_b_worklogs_upserted: number;
  bucket_b_out_of_scope_created: number;
  current_key: string | null;
};

export type WorklogUpdateDone = Omit<WorklogUpdateProgress, 'type' | 'current_key'> & {
  type: 'done';
};

type WorklogUpdateEvent =
  | WorklogUpdateProgress
  | WorklogUpdateDone
  | { type: 'error'; detail: string }
  | { type: 'cancelled' };

export async function updateWorklogsStream(
  req: { since: string; teams?: string[] },
  onProgress: (e: WorklogUpdateProgress) => void,
  signal?: AbortSignal,
): Promise<WorklogUpdateDone> {
  const url = `${BASE_URL}/sync/worklogs/update/stream`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(req),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    pushError({
      ts: new Date().toISOString(), method: 'POST', url,
      status: null, detail: (e as Error).message,
      requestBody: JSON.stringify(req),
    });
    throw e;
  }
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail || res.statusText;
    pushError({
      ts: new Date().toISOString(), method: 'POST', url,
      status: res.status, detail,
      requestBody: JSON.stringify(req),
    });
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: WorklogUpdateDone | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf('\n\n');
    while (sep !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      sep = buffer.indexOf('\n\n');
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const payload = JSON.parse(line.slice(5).trim()) as WorklogUpdateEvent;
        if (payload.type === 'progress') onProgress(payload);
        else if (payload.type === 'done') final = payload;
        else if (payload.type === 'error') throw new Error(payload.detail);
        else if (payload.type === 'cancelled') {
          const err = new Error('Sync cancelled by client');
          err.name = 'AbortError';
          throw err;
        }
      }
    }
  }
  if (!final) throw new Error('Stream ended without done event');
  return final;
}
```

- [ ] **Step 2: Build verify**

Run: `cd frontend && npm run build`
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/sync.ts
git commit -m "feat(frontend): updateWorklogsStream SSE client"
```

---

### Task 13: useUpdateWorklogs hook

**Files:**
- Modify: `frontend/src/hooks/useSync.ts`

- [ ] **Step 1: Add hook**

Modify `frontend/src/hooks/useSync.ts` — update imports:

```typescript
import {
  testConnection, syncProjects, syncIssues, syncWorklogs, syncComments, syncFull,
  refreshIssuesByKeys, syncTeams,
  reloadWorklogsStream, type WorklogReloadProgress, type WorklogReloadDone,
  updateWorklogsStream, type WorklogUpdateProgress, type WorklogUpdateDone,
  getSyncStatus, getJiraProjects, getJiraEpics, getJiraFields, getJiraTeams,
  getJiraIssueTypes,
} from '../api/sync';
```

Add hook right after `useReloadWorklogs`:

```typescript
type UpdateInput = {
  req: { since: string; teams?: string[] };
  onProgress?: (e: WorklogUpdateProgress) => void;
  signal?: AbortSignal;
};
export const useUpdateWorklogs = () => {
  const qc = useQueryClient();
  return useMutation<WorklogUpdateDone, Error, UpdateInput>({
    mutationFn: ({ req, onProgress, signal }) =>
      updateWorklogsStream(req, onProgress ?? (() => {}), signal),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};
```

- [ ] **Step 2: Build verify**

Run: `cd frontend && npm run build`
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useSync.ts
git commit -m "feat(frontend): useUpdateWorklogs hook"
```

---

### Task 14: SyncControls split — Обновить vs Полная перезагрузка

**Files:**
- Modify: `frontend/src/pages/SyncPage.tsx`

- [ ] **Step 1: Locate SyncControls block**

The worklog reload block is around [SyncPage.tsx:1184-1210] (Space wrap with DatePicker + reload button). We'll replace it with two-button layout + checkbox for Bucket B.

- [ ] **Step 2: Add imports & state**

Modify `frontend/src/pages/SyncPage.tsx` — extend imports:

```tsx
import {
  useSyncStatus, useSyncMutation, useRecalculateMapping,
  useJiraTeams, useRefreshIssuesByKeys, useSyncTeams, useReloadWorklogs,
  useUpdateWorklogs,
} from '../hooks/useSync';
import type { WorklogReloadProgress, WorklogUpdateProgress } from '../api/sync';
```

Inside `SyncControls` (next to the existing `reload` hook usage):

```tsx
const update = useUpdateWorklogs();
const updateAbortRef = useRef<AbortController | null>(null);
const [updateProgress, setUpdateProgress] = useState<WorklogUpdateProgress | null>(null);
const [includeTeams, setIncludeTeams] = useState<boolean>(false);
const storedCategoryTeams = useGenericSetting('ui_teams_categories');
const selectedTeams = useMemo(
  () => (storedCategoryTeams.data?.value ?? '').split(',').filter(Boolean),
  [storedCategoryTeams.data],
);

const handleUpdate = () => {
  const iso = sinceDate.format('YYYY-MM-DD');
  const ctl = new AbortController();
  updateAbortRef.current = ctl;
  setUpdateProgress(null);
  update.mutate({
    req: {
      since: iso,
      teams: includeTeams && selectedTeams.length ? selectedTeams : undefined,
    },
    onProgress: (e) => setUpdateProgress(e),
    signal: ctl.signal,
  }, {
    onSuccess: (stats) => {
      notification.success({
        message: 'Ворклоги обновлены',
        description:
          `A: issues ${stats.bucket_a_issues_scanned}, worklog ${stats.bucket_a_worklogs_upserted}. ` +
          `B: issues ${stats.bucket_b_issues_scanned}, worklog ${stats.bucket_b_worklogs_upserted}, ` +
          `новых вне scope ${stats.bucket_b_out_of_scope_created}`,
      });
      saveReloadSince.mutate({ key: 'worklog_reload_since_date', value: iso });
    },
    onError: (e) => {
      if (e.name === 'AbortError') return;
      notification.error({ message: 'Ошибка обновления', description: e.message });
    },
    onSettled: () => {
      updateAbortRef.current = null;
      setUpdateProgress(null);
    },
  });
};

const cancelUpdate = () => updateAbortRef.current?.abort();
```

- [ ] **Step 3: Replace the worklog reload Space block**

Find the existing block:

```tsx
<Space wrap>
  <DatePicker ... />
  ...
  <Button icon={<ReloadOutlined />}>
    Перезагрузить worklog'и с даты
  </Button>
  ...
</Space>
{reload.isPending && ( ... )}
```

Replace with (keeping DatePicker shared between both actions):

```tsx
<Space wrap>
  <DatePicker
    value={sinceDate}
    onChange={(d) => d && setSinceDate(d)}
    format="DD.MM.YYYY"
    allowClear={false}
    disabled={reload.isPending || update.isPending}
  />
  {update.isPending ? (
    <Button danger icon={<CloseOutlined />} onClick={cancelUpdate}>
      Прервать обновление
    </Button>
  ) : (
    <Button
      type="primary"
      icon={<ReloadOutlined />}
      onClick={handleUpdate}
      disabled={reload.isPending}
    >
      Обновить ворклоги с даты
    </Button>
  )}
  <Checkbox
    checked={includeTeams}
    disabled={update.isPending || selectedTeams.length === 0}
    onChange={(e) => setIncludeTeams(e.target.checked)}
  >
    Включить выбранные команды ({selectedTeams.length})
  </Checkbox>
  {reload.isPending ? (
    <Button danger icon={<CloseOutlined />} onClick={cancelReload}>
      Прервать полную перезагрузку
    </Button>
  ) : (
    <Popconfirm
      title="Полная перезагрузка ворклогов"
      description={
        <div style={{ maxWidth: 340 }}>
          <b>Удалит</b> все worklog с started ≥ {sinceDate.format('DD.MM.YYYY')} и перечитает
          из Jira. Используется только если в Jira удалили ворклог и нужно подчистить локальную
          копию. В повседневке — «Обновить ворклоги с даты».
        </div>
      }
      icon={<ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />}
      okText="Перезагрузить"
      cancelText="Отмена"
      okButtonProps={{ danger: true }}
      onConfirm={handleReload}
      disabled={update.isPending}
    >
      <Button danger icon={<ReloadOutlined />} disabled={update.isPending}>
        Полная перезагрузка (удалить и перечитать)
      </Button>
    </Popconfirm>
  )}
</Space>
{(reload.isPending || update.isPending) && (
  <Space direction="vertical" size={2} style={{ width: '100%', maxWidth: 640 }}>
    <Progress
      percent={99.9}
      status="active"
      showInfo={false}
      strokeColor={DARK_THEME.cyanPrimary}
    />
    <Text type="secondary" style={{ fontSize: 12 }}>
      {update.isPending ? (
        updateProgress
          ? `A: issues ${updateProgress.bucket_a_issues_scanned} · worklog ${updateProgress.bucket_a_worklogs_upserted} · B: issues ${updateProgress.bucket_b_issues_scanned} · worklog ${updateProgress.bucket_b_worklogs_upserted} · новых ${updateProgress.bucket_b_out_of_scope_created}${updateProgress.current_key ? ` · ${updateProgress.current_key}` : ''}`
          : 'Подготовка…'
      ) : (
        reloadProgress
          ? `Удалено: ${reloadProgress.deleted} · Обработано ${reloadProgress.issues_scanned} · Вставлено ${reloadProgress.worklogs_inserted}${reloadProgress.current_key ? ` · ${reloadProgress.current_key}` : ''}`
          : 'Подготовка…'
      )}
    </Text>
  </Space>
)}
```

Import `Checkbox` — already imported in the file (it's used in CategoryConfigTab).

- [ ] **Step 4: Build & lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: build passes; no new lint errors on this file.

- [ ] **Step 5: Smoke test**

Restart dev servers. Go to `/sync` → tab «Синхронизация»:
- Default: «Обновить ворклоги с даты» (primary) + «Полная перезагрузка» (danger) visible
- Click «Обновить» — progress bar + counters A/B
- Switch to CategoryConfigTab, select teams, back to Синхронизация — checkbox enabled with count
- Check checkbox + «Обновить» — payload includes `teams: [...]`
- «Полная перезагрузка» → Popconfirm with red warning → proceed runs old SSE endpoint

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SyncPage.tsx
git commit -m "feat(frontend): split SyncControls — Обновить (safe) + Полная перезагрузка (danger)"
```

---

## Phase 6 — Docs + production readiness

### Task 15: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add section about M:N employee_teams**

Modify `CLAUDE.md`. In the «Database Schema» section, update the Core group line to mention `employee_teams`:

```
- **Core (Jira sync):** Employee, EmployeeTeam (M:N, single-primary invariant), Project, Issue (+ `out_of_scope` flag for Bucket B auto-ingest), Worklog, Comment, SyncState
```

Add new subsection right after «SyncService» block:

```
### Worklog sync dimensions

Два независимых прохода:
- **Ведро A — issue-centric**: JQL `updated >= since`, upsert по локально существующим Issue.
- **Ведро B — employee-centric** (активируется параметром `teams`): для каждого Employee из `employee_teams.team IN teams` запускается JQL `worklogAuthor = <account> AND updated >= since`. Незнакомые Issue создаются с `out_of_scope=True`, их Project тоже автосоздаётся (без scope).

Два endpoint'а:
- `POST /sync/worklogs/update/stream` — новый, upsert-only, безопасен в повседневке. Ловит back-dated ворклоги за счёт `updated >=` JQL.
- `POST /sync/worklogs/reload/stream` — жёсткая перезагрузка: `DELETE WHERE started_at >= since` + перечитать через `worklogDate >=` JQL. Нужно только если в Jira удалили ворклог и надо подчистить локальную копию.

Оба — SSE-стримы прогресса с событиями `progress` / `done` / `error` / `cancelled`.

### EmployeeTeamService

CRUD для M:N `employee_teams`. Инвариант: ровно одна строка с `is_primary=true` на сотрудника (enforce в сервисе, не в БД). Поле `Employee.team` — derived-колонка, обновляется синхронно с primary membership для backward-compat.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: M:N employee_teams + Bucket A/B worklog sync"
```

---

### Task 16: Full test + lint pass

- [ ] **Step 1: Run full pytest**

Run: `py -3.10 -m pytest tests/ --ignore=tests/test_sync_service.py --ignore=tests/test_hierarchy_rules_endpoints.py -q`
Expected: all pass.

- [ ] **Step 2: Frontend build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: build passes; lint may warn on pre-existing issues (`SyncIndicator.tsx`, `SyncPage.tsx:1030 setSinceDate`) but no new errors on touched lines.

- [ ] **Step 3: Manual end-to-end smoke**

Restart both dev servers. Reproduce the scenarios from the spec:
- **Back-dated ворклог.** В Jira (тест-тенанте или продуктиве) создать ворклог сегодня с `started = 10 дней назад`. Нажать «Обновить ворклоги с даты» с датой 5 дней назад. Проверить в Analytics — ворклог виден.
- **Сотрудник в нескольких командах.** На CapacityPage → TeamTab выбрать сотрудника, добавить второй тег команды, проверить что первая остаётся primary (★), кликнуть по второй — становится primary, ★ переезжает.
- **Ворклог вне scope.** Создать ворклог сотрудника команды на задаче не из scope. «Обновить ворклоги с даты» + «Включить выбранные команды» + эта команда. Проверить: задача не появилась в CategoryConfigTab, но её часы видны в Capacity breakdown.
- **Безопасный reload.** Нажать «Обновить» — существующий ворклог на нужной дате остаётся (не DELETE-ится).
- **Полная перезагрузка.** Popconfirm с красной иконкой, после подтверждения запускается старый flow.

- [ ] **Step 4: Final commit + push**

If any drift was discovered during smoke test, fix and commit. Then user pushes (main protected — `git push origin main`).

---

## Execution order & rollback

Phases 1 → 6 are strictly sequential. Each phase leaves `main` in a shippable state (tests green, build passes). Rollback strategy per phase:

- Phase 1 — `alembic downgrade -1`; remove model files.
- Phase 2 — revert endpoint commits; legacy single-team endpoint unaffected.
- Phase 3 — revert sync_service changes; reload endpoint unchanged.
- Phase 4-5 — revert frontend commits; UI falls back to single-team Select (legacy endpoint still works).
- Phase 6 — docs only.

## Done criteria

- [ ] All `tests/test_employee_team*.py`, `tests/test_sync_service_update.py`, `tests/test_sync_update_endpoint.py` green
- [ ] `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` работают на dev DB
- [ ] `cd frontend && npm run build` — 0 errors
- [ ] Manual smoke of 5 scenarios в Task 16 Step 3 проходит
- [ ] CLAUDE.md обновлён

---

## Follow-ups (НЕ в скоупе этого плана)

Зафиксированы в спеке (раздел 9 + 6.3); выносятся в отдельные задачи:

- **UI-индикация `out_of_scope` в Analytics / Capacity breakdown** — колонка / тег «Вне scope» на задачах с `out_of_scope=true`. Требует понимания текущей структуры отчётов Analytics и Capacity breakdown — отдельная brainstorming-сессия.
- **Удаление deprecated `Employee.team` колонки** — после стабилизации, когда все читатели переедут на `employee_teams`. Требует аудита всех использований `Employee.team` в сервисах, репозиториях, экспортах.
- **User-level isolation для multi-PM продуктива** — scope_projects / category_overrides / employee_teams per-user. Крупная инфраструктурная работа.
- **Сводный отчёт «Ворклоги вне scope»** — страница с фильтром `Issue.out_of_scope=true`, список задач с часами сотрудников команды, без перехода в сами задачи.
- **Shared rate-limiter на JiraClient** — semaphore на tenant-уровне для multi-user сценария, чтобы одновременные синки не упирались в Jira 429.
