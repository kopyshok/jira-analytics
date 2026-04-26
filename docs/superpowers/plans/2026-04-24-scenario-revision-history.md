# Scenario Revision History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При каждом утверждении сценария фиксировать снапшот нормы сотрудников по месяцам и дифф изменений инициатив, чтобы PM видел историю пересмотров.

**Architecture:** Three new tables — `scenario_revisions` (one per approval), `scenario_revision_items` (diff vs previous revision), `scenario_capacity_snapshots` (per-employee per-month norm at approval time). The `POST /scenarios/{id}/approve` endpoint gains an optional `note` body and now writes all three. A new `GET /scenarios/{id}/revisions` endpoint exposes the history.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic (batch mode for SQLite), CapacityService for norm computation.

---

## File Map

**Create:**
- `alembic/versions/031_scenario_revision_history.py`
- `app/models/scenario_revision.py`
- `app/models/scenario_revision_item.py`
- `app/models/scenario_capacity_snapshot.py`
- `tests/test_scenario_revision_history.py`

**Modify:**
- `app/models/__init__.py` — add 3 new imports + __all__ entries
- `app/models/planning_scenario.py` — add `revisions` relationship
- `app/api/endpoints/planning.py` — update `approve_scenario`, add `GET /scenarios/{id}/revisions`

---

## Task 1: Migration 031 — create 3 tables

**Files:**
- Create: `alembic/versions/031_scenario_revision_history.py`

- [ ] **Step 1: Write migration**

```python
"""Scenario revision history: revisions, revision items, capacity snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "031_scenario_revision_history"
down_revision = "030_work_types_all_subtract"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scenario_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("planning_scenarios.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("revision_number", sa.Integer, nullable=False),
        sa.Column("approved_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "scenario_revision_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36),
                  sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("backlog_item_id", sa.String(36),
                  sa.ForeignKey("backlog_items.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("backlog_item_name", sa.String(500), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),  # 'included' | 'excluded'
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "scenario_capacity_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36),
                  sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("employee_id", sa.String(36),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("norm_hours", sa.Float, nullable=False),
        sa.Column("available_hours", sa.Float, nullable=False),
        sa.Column("snapshot_taken_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("scenario_capacity_snapshots")
    op.drop_table("scenario_revision_items")
    op.drop_table("scenario_revisions")
```

- [ ] **Step 2: Apply migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade 030_work_types_all_subtract -> 031_scenario_revision_history, OK`

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/031_scenario_revision_history.py
git commit -m "feat(db): migration 031 — scenario revision history tables"
```

---

## Task 2: SQLAlchemy models

**Files:**
- Create: `app/models/scenario_revision.py`
- Create: `app/models/scenario_revision_item.py`
- Create: `app/models/scenario_capacity_snapshot.py`
- Modify: `app/models/planning_scenario.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Create `app/models/scenario_revision.py`**

```python
"""ScenarioRevision model — one record per scenario approval event."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.planning_scenario import PlanningScenario
    from app.models.scenario_revision_item import ScenarioRevisionItem
    from app.models.scenario_capacity_snapshot import ScenarioCapacitySnapshot


class ScenarioRevision(Base, TimestampMixin):
    """Запись об одном утверждении сценария.

    Создаётся при каждом POST /scenarios/{id}/approve. Хранит порядковый
    номер, момент утверждения, необязательный комментарий PM и ссылки на
    дифф инициатив и снапшот ресурсов.
    """

    __tablename__ = "scenario_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_scenarios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scenario: Mapped["PlanningScenario"] = relationship(back_populates="revisions")
    items: Mapped[List["ScenarioRevisionItem"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    capacity_snapshots: Mapped[List["ScenarioCapacitySnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ScenarioRevision scenario={self.scenario_id} rev={self.revision_number}>"
```

- [ ] **Step 2: Create `app/models/scenario_revision_item.py`**

```python
"""ScenarioRevisionItem model — one diff entry per changed initiative per revision."""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision
    from app.models.backlog_item import BacklogItem


class ScenarioRevisionItem(Base, TimestampMixin):
    """Строка диффа инициатив при пересмотре сценария.

    action='included' — задача добавлена в сценарий.
    action='excluded' — задача убрана из сценария.
    backlog_item_name денормализовано на случай последующего удаления задачи.
    """

    __tablename__ = "scenario_revision_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    backlog_item_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    backlog_item_name: Mapped[str] = mapped_column(String(500), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)  # 'included' | 'excluded'

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="items")
    backlog_item: Mapped[Optional["BacklogItem"]] = relationship()

    def __repr__(self) -> str:
        return f"<ScenarioRevisionItem {self.action} {self.backlog_item_name}>"
```

- [ ] **Step 3: Create `app/models/scenario_capacity_snapshot.py`**

```python
"""ScenarioCapacitySnapshot model — per-employee per-month norm at approval time."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision
    from app.models.employee import Employee


class ScenarioCapacitySnapshot(Base, TimestampMixin):
    """Снапшот нормы одного сотрудника за один месяц на момент утверждения сценария.

    Позволяет впоследствии сравнить плановую норму (зафиксированную при утверждении)
    с текущей нормой (с учётом незапланированных отсутствий, добавленных позже).
    employee_name денормализовано на случай удаления сотрудника.
    """

    __tablename__ = "scenario_capacity_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    norm_hours: Mapped[float] = mapped_column(Float, nullable=False)
    available_hours: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="capacity_snapshots")
    employee: Mapped[Optional["Employee"]] = relationship()

    def __repr__(self) -> str:
        return f"<ScenarioCapacitySnapshot emp={self.employee_name} {self.year}-{self.month:02d}>"
```

- [ ] **Step 4: Add `revisions` relationship to `app/models/planning_scenario.py`**

Add to imports:
```python
if TYPE_CHECKING:
    from app.models.scenario_allocation import ScenarioAllocation
    from app.models.scenario_revision import ScenarioRevision
```

Add to class body after `allocations` relationship:
```python
    revisions: Mapped[List["ScenarioRevision"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan",
        order_by="ScenarioRevision.revision_number",
    )
```

- [ ] **Step 5: Update `app/models/__init__.py`**

Add after `from app.models.scenario_rule import ScenarioRule`:
```python
from app.models.scenario_revision import ScenarioRevision
from app.models.scenario_revision_item import ScenarioRevisionItem
from app.models.scenario_capacity_snapshot import ScenarioCapacitySnapshot
```

Add to `__all__`:
```python
    "ScenarioRevision",
    "ScenarioRevisionItem",
    "ScenarioCapacitySnapshot",
```

- [ ] **Step 6: Verify imports load cleanly**

```bash
py -3.10 -c "from app.models import ScenarioRevision, ScenarioRevisionItem, ScenarioCapacitySnapshot; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add app/models/scenario_revision.py app/models/scenario_revision_item.py \
        app/models/scenario_capacity_snapshot.py app/models/planning_scenario.py \
        app/models/__init__.py
git commit -m "feat(models): ScenarioRevision, ScenarioRevisionItem, ScenarioCapacitySnapshot"
```

---

## Task 3: Update approve endpoint + add revisions GET

**Files:**
- Modify: `app/api/endpoints/planning.py`

### 3a — New schemas

- [ ] **Step 1: Add schemas to `app/api/endpoints/planning.py`**

After the existing `ScenarioUpdate` schema, add:

```python
class ApproveBody(BaseModel):
    note: Optional[str] = None


class CapacitySnapshotOut(BaseModel):
    employee_id: Optional[str]
    employee_name: str
    year: int
    month: int
    norm_hours: float
    available_hours: float

    class Config:
        from_attributes = True


class RevisionItemOut(BaseModel):
    backlog_item_id: Optional[str]
    backlog_item_name: str
    action: str  # 'included' | 'excluded'

    class Config:
        from_attributes = True


class RevisionOut(BaseModel):
    id: str
    revision_number: int
    approved_at: str  # ISO datetime string
    note: Optional[str]
    items: List[RevisionItemOut]
    capacity_snapshots: List[CapacitySnapshotOut]

    class Config:
        from_attributes = True
```

### 3b — Update approve endpoint

- [ ] **Step 2: Add imports at top of `app/api/endpoints/planning.py`**

Add to the existing `from app.models import (...)` block:
```python
    Employee,
    EmployeeTeam,
    ScenarioRevision,
    ScenarioRevisionItem,
    ScenarioCapacitySnapshot,
```

Add at top-level imports:
```python
from datetime import datetime
from app.services.capacity_service import CapacityService
```

- [ ] **Step 3: Replace `approve_scenario` with the full implementation**

```python
QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}


@router.post("/scenarios/{scenario_id}/approve", response_model=ScenarioResponse)
async def approve_scenario(
    scenario_id: str,
    body: ApproveBody = ApproveBody(),
    db: Session = Depends(get_db),
):
    """Зафиксировать сценарий: status='approved'.

    Создаёт запись пересмотра с диффом инициатив и снапшотом нормы команды.
    """
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    now = datetime.utcnow()

    # --- Порядковый номер ревизии ---
    prev_count = (
        db.query(ScenarioRevision)
        .filter(ScenarioRevision.scenario_id == scenario_id)
        .count()
    )
    revision_number = prev_count + 1

    # --- Создать запись ревизии ---
    revision = ScenarioRevision(
        scenario_id=scenario_id,
        revision_number=revision_number,
        approved_at=now,
        note=body.note,
    )
    db.add(revision)
    db.flush()  # нужен revision.id

    # --- Дифф инициатив ---
    # Текущий включённый набор
    current_included: dict[str, str] = {
        alloc.backlog_item_id: (
            db.get(BacklogItem, alloc.backlog_item_id).title
            if db.get(BacklogItem, alloc.backlog_item_id) else alloc.backlog_item_id
        )
        for alloc in db.query(ScenarioAllocation).filter(
            ScenarioAllocation.scenario_id == scenario_id,
            ScenarioAllocation.included_flag == True,  # noqa: E712
        ).all()
    }

    # Предыдущий включённый набор (из последней ревизии перед этой)
    prev_revision = (
        db.query(ScenarioRevision)
        .filter(
            ScenarioRevision.scenario_id == scenario_id,
            ScenarioRevision.revision_number == revision_number - 1,
        )
        .first()
    )
    if prev_revision:
        prev_included_ids = {
            item.backlog_item_id
            for item in db.query(ScenarioRevisionItem).filter(
                ScenarioRevisionItem.revision_id == prev_revision.id,
                ScenarioRevisionItem.action == "included",
            ).all()
            if item.backlog_item_id is not None
        }
        # Добавить убранные в предыдущей ревизии и потом снова добавленные —
        # точный дифф: added = в текущем, но не в предыдущем; removed = в предыдущем, но не в текущем
        prev_all_included = {
            item.backlog_item_id: item.backlog_item_name
            for item in db.query(ScenarioRevisionItem).filter(
                ScenarioRevisionItem.revision_id == prev_revision.id,
                ScenarioRevisionItem.action == "included",
            ).all()
            if item.backlog_item_id is not None
        }
        added = {k: v for k, v in current_included.items() if k not in prev_included_ids}
        removed = {k: v for k, v in prev_all_included.items() if k not in current_included}
    else:
        # Первая ревизия — все включённые считаются «добавленными»
        added = current_included
        removed = {}

    for item_id, item_name in added.items():
        db.add(ScenarioRevisionItem(
            revision_id=revision.id,
            backlog_item_id=item_id,
            backlog_item_name=item_name,
            action="included",
        ))
    for item_id, item_name in removed.items():
        db.add(ScenarioRevisionItem(
            revision_id=revision.id,
            backlog_item_id=item_id,
            backlog_item_name=item_name,
            action="excluded",
        ))

    # --- Снапшот нормы команды ---
    if scenario.team and scenario.year and scenario.quarter:
        q = int(str(scenario.quarter).replace("Q", ""))
        months = QUARTER_MONTHS[q]
        emp_ids = [
            r[0]
            for r in db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team == scenario.team)
            .all()
        ]
        employees = (
            db.query(Employee)
            .filter(Employee.id.in_(emp_ids), Employee.is_active == True)  # noqa: E712
            .all()
        )
        capacity_svc = CapacityService(db)
        for emp in employees:
            for month in months:
                mc = capacity_svc.monthly_capacity(emp.id, scenario.year, month)
                db.add(ScenarioCapacitySnapshot(
                    revision_id=revision.id,
                    employee_id=emp.id,
                    employee_name=emp.display_name,
                    year=scenario.year,
                    month=month,
                    norm_hours=mc.norm_hours,
                    available_hours=mc.available_hours,
                    snapshot_taken_at=now,
                ))

    scenario.status = "approved"
    db.commit()
    db.refresh(scenario)
    return _to_scenario_resp(scenario)
```

### 3c — New GET revisions endpoint

- [ ] **Step 4: Add GET revisions endpoint** (place before the generic `GET /scenarios/{scenario_id}` route)

```python
@router.get(
    "/scenarios/{scenario_id}/revisions",
    response_model=List[RevisionOut],
)
async def list_scenario_revisions(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """История пересмотров сценария: дифф инициатив и снапшот нормы по каждому утверждению."""
    if not db.get(PlanningScenario, scenario_id):
        raise HTTPException(status_code=404, detail="Scenario not found")

    revisions = (
        db.query(ScenarioRevision)
        .filter(ScenarioRevision.scenario_id == scenario_id)
        .order_by(ScenarioRevision.revision_number)
        .all()
    )

    result = []
    for rev in revisions:
        items = (
            db.query(ScenarioRevisionItem)
            .filter(ScenarioRevisionItem.revision_id == rev.id)
            .all()
        )
        snapshots = (
            db.query(ScenarioCapacitySnapshot)
            .filter(ScenarioCapacitySnapshot.revision_id == rev.id)
            .order_by(
                ScenarioCapacitySnapshot.employee_name,
                ScenarioCapacitySnapshot.month,
            )
            .all()
        )
        result.append(RevisionOut(
            id=rev.id,
            revision_number=rev.revision_number,
            approved_at=rev.approved_at.isoformat(),
            note=rev.note,
            items=[
                RevisionItemOut(
                    backlog_item_id=i.backlog_item_id,
                    backlog_item_name=i.backlog_item_name,
                    action=i.action,
                )
                for i in items
            ],
            capacity_snapshots=[
                CapacitySnapshotOut(
                    employee_id=s.employee_id,
                    employee_name=s.employee_name,
                    year=s.year,
                    month=s.month,
                    norm_hours=s.norm_hours,
                    available_hours=s.available_hours,
                )
                for s in snapshots
            ],
        ))
    return result
```

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/planning.py
git commit -m "feat(planning): approve creates revision history + capacity snapshot"
```

---

## Task 4: Tests

**Files:**
- Create: `tests/test_scenario_revision_history.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for scenario revision history: approve creates revision + items + snapshots."""

import pytest
from datetime import date
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    PlanningScenario,
    ProductionCalendarDay,
    ScenarioAllocation,
    ScenarioCapacitySnapshot,
    ScenarioRevision,
    ScenarioRevisionItem,
)
from app.models.base import generate_uuid

client = TestClient(app)


def _make_scenario(db, team="TeamA", year=2026, quarter="Q2", status="draft"):
    s = PlanningScenario(
        id=generate_uuid(), name="Test", year=year, quarter=quarter,
        status=status, team=team,
    )
    db.add(s)
    db.flush()
    return s


def _make_item(db, title="Init X"):
    item = BacklogItem(id=generate_uuid(), title=title)
    db.add(item)
    db.flush()
    return item


def _make_employee(db, name="Alice", team="TeamA"):
    emp = Employee(
        id=generate_uuid(), display_name=name,
        jira_account_id=generate_uuid(), is_active=True,
        hours_per_day=8.0,
    )
    db.add(emp)
    db.flush()
    db.add(EmployeeTeam(
        id=generate_uuid(), employee_id=emp.id, team=team, is_primary=True,
    ))
    db.flush()
    return emp


def _make_allocation(db, scenario_id, item_id, included=True):
    alloc = ScenarioAllocation(
        id=generate_uuid(), scenario_id=scenario_id,
        backlog_item_id=item_id,
        included_flag=included, planned_hours=10.0 if included else 0.0,
    )
    db.add(alloc)
    db.flush()
    return alloc


class TestApproveCreatesRevision:
    def test_first_approve_creates_revision_number_1(self, db_session):
        scenario = _make_scenario(db_session)
        item = _make_item(db_session)
        _make_allocation(db_session, scenario.id, item.id, included=True)
        db_session.commit()

        resp = client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve",
                           json={"note": "Initial plan"})
        assert resp.status_code == 200

        rev = db_session.query(ScenarioRevision).filter_by(scenario_id=scenario.id).first()
        assert rev is not None
        assert rev.revision_number == 1
        assert rev.note == "Initial plan"

    def test_first_approve_all_included_items_marked_included(self, db_session):
        scenario = _make_scenario(db_session)
        item1 = _make_item(db_session, "Task A")
        item2 = _make_item(db_session, "Task B")
        _make_allocation(db_session, scenario.id, item1.id, included=True)
        _make_allocation(db_session, scenario.id, item2.id, included=False)
        db_session.commit()

        client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})

        rev = db_session.query(ScenarioRevision).filter_by(scenario_id=scenario.id).first()
        items = db_session.query(ScenarioRevisionItem).filter_by(revision_id=rev.id).all()
        assert len(items) == 1
        assert items[0].action == "included"
        assert items[0].backlog_item_name == "Task A"

    def test_second_approve_records_diff(self, db_session):
        scenario = _make_scenario(db_session)
        item1 = _make_item(db_session, "Task A")
        item2 = _make_item(db_session, "Task B")
        _make_allocation(db_session, scenario.id, item1.id, included=True)
        alloc2 = _make_allocation(db_session, scenario.id, item2.id, included=False)
        db_session.commit()

        # First approval: only item1 included
        client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})

        # Revert to draft
        client.post(f"/api/v1/planning/scenarios/{scenario.id}/revert-to-draft")

        # Exclude item1, include item2
        alloc1 = db_session.query(ScenarioAllocation).filter_by(
            scenario_id=scenario.id, backlog_item_id=item1.id
        ).first()
        alloc1.included_flag = False
        alloc1.planned_hours = 0
        alloc2.included_flag = True
        alloc2.planned_hours = 10
        db_session.commit()

        # Second approval
        client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve",
                    json={"note": "Replaced A with B"})

        revisions = (
            db_session.query(ScenarioRevision)
            .filter_by(scenario_id=scenario.id)
            .order_by(ScenarioRevision.revision_number)
            .all()
        )
        assert len(revisions) == 2
        rev2_items = (
            db_session.query(ScenarioRevisionItem)
            .filter_by(revision_id=revisions[1].id)
            .all()
        )
        actions = {i.backlog_item_name: i.action for i in rev2_items}
        assert actions["Task B"] == "included"
        assert actions["Task A"] == "excluded"
        assert revisions[1].note == "Replaced A with B"

    def test_approve_no_team_skips_capacity_snapshot(self, db_session):
        scenario = _make_scenario(db_session, team=None)
        db_session.commit()

        resp = client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})
        assert resp.status_code == 200

        snapshots = db_session.query(ScenarioCapacitySnapshot).join(
            ScenarioRevision,
            ScenarioCapacitySnapshot.revision_id == ScenarioRevision.id,
        ).filter(ScenarioRevision.scenario_id == scenario.id).all()
        assert snapshots == []

    def test_approve_with_team_creates_capacity_snapshots(self, db_session):
        scenario = _make_scenario(db_session, team="TeamSnap", year=2026, quarter="Q2")
        _make_employee(db_session, name="Bob", team="TeamSnap")
        db_session.commit()

        resp = client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})
        assert resp.status_code == 200

        rev = db_session.query(ScenarioRevision).filter_by(scenario_id=scenario.id).first()
        snapshots = (
            db_session.query(ScenarioCapacitySnapshot)
            .filter_by(revision_id=rev.id)
            .all()
        )
        # Q2 = months 4, 5, 6 → 3 snapshots for 1 employee
        assert len(snapshots) == 3
        months = {s.month for s in snapshots}
        assert months == {4, 5, 6}
        for s in snapshots:
            assert s.employee_name == "Bob"
            assert s.norm_hours >= 0
            assert s.available_hours >= 0


class TestRevisionsEndpoint:
    def test_get_revisions_empty(self, db_session):
        scenario = _make_scenario(db_session)
        db_session.commit()

        resp = client.get(f"/api/v1/planning/scenarios/{scenario.id}/revisions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_revisions_returns_history(self, db_session):
        scenario = _make_scenario(db_session)
        item = _make_item(db_session, "Feature X")
        _make_allocation(db_session, scenario.id, item.id, included=True)
        db_session.commit()

        client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve",
                    json={"note": "Q2 plan"})

        resp = client.get(f"/api/v1/planning/scenarios/{scenario.id}/revisions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["revision_number"] == 1
        assert data[0]["note"] == "Q2 plan"
        assert len(data[0]["items"]) == 1
        assert data[0]["items"][0]["action"] == "included"
        assert data[0]["items"][0]["backlog_item_name"] == "Feature X"

    def test_get_revisions_404_unknown_scenario(self, db_session):
        resp = client.get("/api/v1/planning/scenarios/no-such-id/revisions")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests**

```bash
py -3.10 -m pytest tests/test_scenario_revision_history.py -v
```

Expected: all tests pass. If `CapacityService._get_employee` raises for unknown employee — check that test employees have all required fields (`jira_account_id`, `hours_per_day`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_scenario_revision_history.py
git commit -m "test(planning): scenario revision history tests"
```

---

## Task 5: Full test suite + push

- [ ] **Step 1: Run full test suite**

```bash
py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all previously passing tests still pass.

- [ ] **Step 2: Push**

```bash
git push origin main
```
