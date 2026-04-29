# Scenario Snapshot Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Зафиксировать в БД полный набор данных каждой ревизии сценария квартального планирования (команда, календарь, правила, отсутствия, allocations с помесячной разбивкой по ролям/сотрудникам, копии справочников) — чтобы любая утверждённая ревизия в любой момент в будущем могла быть прочитана и сопоставлена с фактом, а две ревизии — сравнены через diff API. Удаление ревизии — каскадно по всем snapshot-таблицам с переводом сценария в draft если последняя.

**Architecture:** Все snapshot-вставки выносятся из `app/api/endpoints/planning.py:approve_scenario` в отдельный сервис `SnapshotWriter` (один модуль = одно действие), что упрощает тестирование. Расчёт capacity per-emp×month исправляется (учёт отсутствий + внешний QA как «виртуальный сотрудник»). Алгоритм автосплита allocations по месяцам и ролям использует `available_hours` из свежезаписанного `ScenarioCapacitySnapshot`. Старые v1-ревизии не пересчитываются — помечаются `algo_version='v1'`. Diff между ревизиями — отдельный сервис `SnapshotDiffer`, читает обе ревизии и сравнивает по срезам.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + Alembic batch migrations + pytest. SQLite (MVP) → PostgreSQL (target).

**Specификация:** [docs/superpowers/specs/2026-04-29-scenario-snapshot-redesign-design.md](../specs/2026-04-29-scenario-snapshot-redesign-design.md)

---

## Файловая структура

### Создаются

```
alembic/versions/043_scenario_snapshot_redesign.py
app/models/scenario_team_snapshot.py
app/models/scenario_calendar_snapshot.py
app/models/scenario_rules_snapshot.py
app/models/scenario_allocation_snapshot.py
app/models/scenario_allocation_breakdown_snapshot.py
app/models/scenario_dictionary_snapshot.py
app/services/snapshot_writer.py
app/services/snapshot_differ.py
app/schemas/snapshot.py
tests/test_snapshot_writer.py
tests/test_snapshot_writer_breakdown.py
tests/test_snapshot_writer_external_qa.py
tests/test_snapshot_delete.py
tests/test_snapshot_differ.py
tests/test_snapshot_breakdown_endpoint.py
scripts/link_v1_revisions.py
```

### Модифицируются

```
app/models/scenario_revision.py             — +parent_revision_id, +approved_by_user_id, +algo_version, +relationships для новых snapshot
app/models/scenario_capacity_snapshot.py    — +gross_hours, +absence_hours, +mandatory_hours, +project_hours
app/models/scenario_norm_snapshot.py        — +is_external
app/models/__init__.py                      — экспорты новых моделей
app/api/endpoints/planning.py               — approve использует SnapshotWriter; +DELETE revision; +GET diff; +GET breakdown
app/services/CLAUDE.md                      — упомянуть SnapshotWriter и SnapshotDiffer
```

---

## Порядок задач

Phase 1 — DB schema (T1–T3)
Phase 2 — Snapshot writer (T4–T10)
Phase 3 — Approve endpoint (T11–T12)
Phase 4 — Delete revision (T13–T14)
Phase 5 — Diff API (T15–T16)
Phase 6 — Breakdown debug API (T17)
Phase 7 — v1 backlink + smoke (T18–T19)

---

## Phase 1 — DB schema

### Task 1: Alembic migration 043

**Files:**
- Create: `alembic/versions/043_scenario_snapshot_redesign.py`

- [ ] **Step 1: Create migration file**

```python
"""scenario snapshot redesign

- расширение scenario_revisions: parent_revision_id, approved_by_user_id, algo_version
- расширение scenario_capacity_snapshots: gross_hours, absence_hours, mandatory_hours, project_hours
- расширение scenario_norm_snapshots: is_external
- новые таблицы: scenario_team_snapshots, scenario_calendar_snapshots, scenario_rules_snapshots,
  scenario_allocation_snapshots, scenario_allocation_breakdown_snapshots, scenario_dictionary_snapshots

Revision ID: 043
Revises: 042
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = '043'
down_revision = '042'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- scenario_revisions: новые поля ---
    with op.batch_alter_table("scenario_revisions") as batch_op:
        batch_op.add_column(sa.Column("parent_revision_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("approved_by_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("algo_version", sa.String(length=16), nullable=False, server_default="v1"))
        batch_op.create_foreign_key(
            "fk_scenario_revisions_parent",
            "scenario_revisions",
            ["parent_revision_id"], ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_scenario_revisions_user",
            "users",
            ["approved_by_user_id"], ["id"],
            ondelete="SET NULL",
        )

    # --- scenario_capacity_snapshots: новые поля ---
    with op.batch_alter_table("scenario_capacity_snapshots") as batch_op:
        batch_op.add_column(sa.Column("gross_hours", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("absence_hours", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("mandatory_hours", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("project_hours", sa.Float(), nullable=True))

    # --- scenario_norm_snapshots: is_external ---
    with op.batch_alter_table("scenario_norm_snapshots") as batch_op:
        batch_op.add_column(sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()))

    # --- scenario_team_snapshots ---
    op.create_table(
        "scenario_team_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("hours_per_day", sa.Float(), nullable=False, server_default="8.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scenario_team_snapshots_revision_role", "scenario_team_snapshots", ["revision_id", "role"])

    # --- scenario_calendar_snapshots ---
    op.create_table(
        "scenario_calendar_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("is_workday", sa.Boolean(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("revision_id", "date", name="uq_scenario_calendar_snap_rev_date"),
    )

    # --- scenario_rules_snapshots ---
    op.create_table(
        "scenario_rules_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("work_type_id", sa.String(36), nullable=True),
        sa.Column("work_type_label", sa.String(255), nullable=False),
        sa.Column("pct_of_norm", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("revision_id", "role", "work_type_id", name="uq_scenario_rules_snap_rev_role_wt"),
    )

    # --- scenario_allocation_snapshots ---
    op.create_table(
        "scenario_allocation_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("allocation_id", sa.String(36), nullable=True),
        sa.Column("backlog_item_id", sa.String(36), nullable=True),
        sa.Column("sort_order", sa.Float(), nullable=True),
        sa.Column("included_flag", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("involvement_coefficient", sa.Float(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("issue_id", sa.String(36), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("customer", sa.Text(), nullable=True),
        sa.Column("cost_type", sa.String(50), nullable=True),
        sa.Column("impact", sa.String(20), nullable=True),
        sa.Column("risk", sa.String(20), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("estimate_analyst_hours", sa.Float(), nullable=True),
        sa.Column("estimate_dev_hours", sa.Float(), nullable=True),
        sa.Column("estimate_qa_hours", sa.Float(), nullable=True),
        sa.Column("estimate_opo_hours", sa.Float(), nullable=True),
        sa.Column("opo_analyst_ratio", sa.Float(), nullable=True),
        sa.Column("assignee_employee_id", sa.String(36), nullable=True),
        sa.Column("assignee_role_at_approval", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- scenario_allocation_breakdown_snapshots ---
    op.create_table(
        "scenario_allocation_breakdown_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("allocation_id", sa.String(36), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_alloc_breakdown_rev_alloc_month",
        "scenario_allocation_breakdown_snapshots",
        ["revision_id", "allocation_id", "month"],
    )

    # --- scenario_dictionary_snapshots ---
    op.create_table(
        "scenario_dictionary_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("original_id", sa.String(36), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("extra_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("revision_id", "kind", "original_id", name="uq_scenario_dict_snap_rev_kind_id"),
    )


def downgrade() -> None:
    op.drop_table("scenario_dictionary_snapshots")
    op.drop_index("ix_alloc_breakdown_rev_alloc_month", table_name="scenario_allocation_breakdown_snapshots")
    op.drop_table("scenario_allocation_breakdown_snapshots")
    op.drop_table("scenario_allocation_snapshots")
    op.drop_table("scenario_rules_snapshots")
    op.drop_table("scenario_calendar_snapshots")
    op.drop_index("ix_scenario_team_snapshots_revision_role", table_name="scenario_team_snapshots")
    op.drop_table("scenario_team_snapshots")
    with op.batch_alter_table("scenario_norm_snapshots") as batch_op:
        batch_op.drop_column("is_external")
    with op.batch_alter_table("scenario_capacity_snapshots") as batch_op:
        batch_op.drop_column("project_hours")
        batch_op.drop_column("mandatory_hours")
        batch_op.drop_column("absence_hours")
        batch_op.drop_column("gross_hours")
    with op.batch_alter_table("scenario_revisions") as batch_op:
        batch_op.drop_constraint("fk_scenario_revisions_user", type_="foreignkey")
        batch_op.drop_constraint("fk_scenario_revisions_parent", type_="foreignkey")
        batch_op.drop_column("algo_version")
        batch_op.drop_column("approved_by_user_id")
        batch_op.drop_column("parent_revision_id")
```

- [ ] **Step 2: Run upgrade**

Run: `alembic upgrade head`
Expected: Output ends with `Running upgrade 042 -> 043`. No errors.

- [ ] **Step 3: Verify schema in dev DB**

Run: `py -3.10 -c "import sqlite3; db=sqlite3.connect('data/jira_analytics.db'); c=db.cursor(); [print(t) for t in c.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'scenario_%'\").fetchall()]"`
Expected: All 9 scenario_* tables listed (including 6 new ones).

- [ ] **Step 4: Verify downgrade**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: Both commands succeed; final state matches step 3.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/043_scenario_snapshot_redesign.py
git commit -m "feat(planning): migration 043 — scenario snapshot redesign tables"
```

---

### Task 2: Extend ScenarioRevision model

**Files:**
- Modify: `app/models/scenario_revision.py`

- [ ] **Step 1: Add new columns and relationships**

Modify `app/models/scenario_revision.py` — replace whole file with:

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
    from app.models.scenario_norm_snapshot import ScenarioNormSnapshot
    from app.models.scenario_absence_snapshot import ScenarioAbsenceSnapshot
    from app.models.scenario_team_snapshot import ScenarioTeamSnapshot
    from app.models.scenario_calendar_snapshot import ScenarioCalendarSnapshot
    from app.models.scenario_rules_snapshot import ScenarioRulesSnapshot
    from app.models.scenario_allocation_snapshot import ScenarioAllocationSnapshot
    from app.models.scenario_allocation_breakdown_snapshot import ScenarioAllocationBreakdownSnapshot
    from app.models.scenario_dictionary_snapshot import ScenarioDictionarySnapshot
    from app.models.user import User


class ScenarioRevision(Base, TimestampMixin):
    __tablename__ = "scenario_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_scenarios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    parent_revision_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    algo_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")

    scenario: Mapped["PlanningScenario"] = relationship(back_populates="revisions")
    items: Mapped[List["ScenarioRevisionItem"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    capacity_snapshots: Mapped[List["ScenarioCapacitySnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    norm_snapshots: Mapped[List["ScenarioNormSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    absence_snapshots: Mapped[List["ScenarioAbsenceSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    team_snapshots: Mapped[List["ScenarioTeamSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    calendar_snapshots: Mapped[List["ScenarioCalendarSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    rules_snapshots: Mapped[List["ScenarioRulesSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    allocation_snapshots: Mapped[List["ScenarioAllocationSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    allocation_breakdown_snapshots: Mapped[List["ScenarioAllocationBreakdownSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    dictionary_snapshots: Mapped[List["ScenarioDictionarySnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    approved_by: Mapped[Optional["User"]] = relationship(foreign_keys=[approved_by_user_id])

    def __repr__(self) -> str:
        return f"<ScenarioRevision scenario={self.scenario_id} rev={self.revision_number}>"
```

- [ ] **Step 2: Update ScenarioCapacitySnapshot model**

Modify `app/models/scenario_capacity_snapshot.py` — add new optional columns. Replace the field block (after `available_hours`) with:

```python
    available_hours: Mapped[float] = mapped_column(Float, nullable=False)
    backlog_pool_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    absence_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mandatory_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    project_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    snapshot_taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

- [ ] **Step 3: Update ScenarioNormSnapshot model**

Modify `app/models/scenario_norm_snapshot.py` — after `norm_hours` add:

```python
    norm_hours: Mapped[float] = mapped_column(Float, nullable=False)
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

Add `Boolean` to the imports: `from sqlalchemy import Boolean, Float, ForeignKey, Integer, String`.

- [ ] **Step 4: Run app smoke**

Run: `py -3.10 -c "from app.models import ScenarioRevision, ScenarioCapacitySnapshot, ScenarioNormSnapshot; print(ScenarioRevision.__table__.columns.keys())"`
Expected: list includes `parent_revision_id`, `approved_by_user_id`, `algo_version`.

- [ ] **Step 5: Commit**

```bash
git add app/models/scenario_revision.py app/models/scenario_capacity_snapshot.py app/models/scenario_norm_snapshot.py
git commit -m "feat(models): extend ScenarioRevision/CapacitySnapshot/NormSnapshot for v2 redesign"
```

---

### Task 3: Create new snapshot models

**Files:**
- Create: `app/models/scenario_team_snapshot.py`, `scenario_calendar_snapshot.py`, `scenario_rules_snapshot.py`, `scenario_allocation_snapshot.py`, `scenario_allocation_breakdown_snapshot.py`, `scenario_dictionary_snapshot.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Create scenario_team_snapshot.py**

```python
"""ScenarioTeamSnapshot — состав команды на момент утверждения."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioTeamSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_team_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hours_per_day: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="team_snapshots")
```

- [ ] **Step 2: Create scenario_calendar_snapshot.py**

```python
"""ScenarioCalendarSnapshot — производственный календарь квартала на момент утверждения."""
from datetime import date
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioCalendarSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_calendar_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    is_workday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="calendar_snapshots")
```

- [ ] **Step 3: Create scenario_rules_snapshot.py**

```python
"""ScenarioRulesSnapshot — снимок scenario_rules на момент утверждения."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioRulesSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_rules_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    work_type_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    work_type_label: Mapped[str] = mapped_column(String(255), nullable=False)
    pct_of_norm: Mapped[float] = mapped_column(Float, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="rules_snapshots")
```

- [ ] **Step 4: Create scenario_allocation_snapshot.py**

```python
"""ScenarioAllocationSnapshot — копия allocation + атрибутов backlog_item."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioAllocationSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_allocation_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    allocation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    backlog_item_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    sort_order: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    included_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    involvement_coefficient: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    issue_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    customer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    impact: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimate_analyst_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_dev_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_qa_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_opo_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opo_analyst_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assignee_employee_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    assignee_role_at_approval: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="allocation_snapshots")
```

- [ ] **Step 5: Create scenario_allocation_breakdown_snapshot.py**

```python
"""ScenarioAllocationBreakdownSnapshot — помесячный сплит allocation × роль × сотрудник."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioAllocationBreakdownSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_allocation_breakdown_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    allocation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    employee_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hours: Mapped[float] = mapped_column(Float, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="allocation_breakdown_snapshots")
```

- [ ] **Step 6: Create scenario_dictionary_snapshot.py**

```python
"""ScenarioDictionarySnapshot — снимки справочников (work_types, roles, absence_reasons)."""
from typing import Any, Optional, TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioDictionarySnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_dictionary_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    original_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="dictionary_snapshots")
```

- [ ] **Step 7: Update app/models/__init__.py**

Add 6 new imports and `__all__` entries:

```python
from app.models.scenario_team_snapshot import ScenarioTeamSnapshot
from app.models.scenario_calendar_snapshot import ScenarioCalendarSnapshot
from app.models.scenario_rules_snapshot import ScenarioRulesSnapshot
from app.models.scenario_allocation_snapshot import ScenarioAllocationSnapshot
from app.models.scenario_allocation_breakdown_snapshot import ScenarioAllocationBreakdownSnapshot
from app.models.scenario_dictionary_snapshot import ScenarioDictionarySnapshot
```

And in `__all__` list, add: `"ScenarioTeamSnapshot", "ScenarioCalendarSnapshot", "ScenarioRulesSnapshot", "ScenarioAllocationSnapshot", "ScenarioAllocationBreakdownSnapshot", "ScenarioDictionarySnapshot",`.

- [ ] **Step 8: Verify imports work**

Run: `py -3.10 -c "from app.models import ScenarioTeamSnapshot, ScenarioCalendarSnapshot, ScenarioRulesSnapshot, ScenarioAllocationSnapshot, ScenarioAllocationBreakdownSnapshot, ScenarioDictionarySnapshot; print('ok')"`
Expected: `ok`.

- [ ] **Step 9: Commit**

```bash
git add app/models/
git commit -m "feat(models): new snapshot models (team/calendar/rules/allocation/breakdown/dictionary)"
```

---

## Phase 2 — Snapshot writer

### Task 4: SnapshotWriter skeleton + team snapshot

**Files:**
- Create: `app/services/snapshot_writer.py`
- Test: `tests/test_snapshot_writer.py`

- [ ] **Step 1: Write failing test for team snapshot**

Create `tests/test_snapshot_writer.py`:

```python
"""Тесты SnapshotWriter: создание снапшотов при approve сценария."""
from datetime import datetime
import pytest
from sqlalchemy.orm import Session
from app.models import (
    Employee, EmployeeTeam, PlanningScenario, ScenarioRevision,
    ScenarioTeamSnapshot,
)
from app.services.snapshot_writer import SnapshotWriter


@pytest.fixture
def team_setup(db: Session):
    """Создать команду из 2 активных сотрудников + сценарий."""
    e1 = Employee(id="e-1", jira_account_id="j1", display_name="Иванов И.", role="analyst", is_active=True)
    e2 = Employee(id="e-2", jira_account_id="j2", display_name="Петров П.", role="dev", is_active=True)
    db.add_all([e1, e2])
    db.add_all([
        EmployeeTeam(id="et-1", employee_id="e-1", team="T1", is_primary=True),
        EmployeeTeam(id="et-2", employee_id="e-2", team="T1", is_primary=True),
    ])
    sc = PlanningScenario(
        id="s-1", name="Q2", year=2026, quarter="Q2", team="T1",
        status="draft", external_qa_hours=None,
    )
    db.add(sc)
    rev = ScenarioRevision(id="r-1", scenario_id="s-1", revision_number=1, approved_at=datetime.utcnow())
    db.add(rev)
    db.commit()
    return {"scenario": sc, "revision": rev}


def test_write_team_snapshot_copies_active_team_members(db: Session, team_setup):
    writer = SnapshotWriter(db)
    writer.write_team_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    db.commit()

    rows = db.query(ScenarioTeamSnapshot).filter_by(revision_id="r-1").order_by(ScenarioTeamSnapshot.display_name).all()
    assert len(rows) == 2
    assert rows[0].display_name == "Иванов И."
    assert rows[0].role == "analyst"
    assert rows[1].display_name == "Петров П."
    assert rows[1].role == "dev"
    assert all(r.is_active for r in rows)
```

- [ ] **Step 2: Run test, expect failure**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py::test_write_team_snapshot_copies_active_team_members -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.snapshot_writer'`.

- [ ] **Step 3: Implement minimal SnapshotWriter**

Create `app/services/snapshot_writer.py`:

```python
"""SnapshotWriter — заполнение всех snapshot-таблиц при создании ревизии сценария.

Один экземпляр = один проход. Все методы add()-ят строки в сессию;
commit делает вызывающий код.
"""
from sqlalchemy.orm import Session

from app.models import (
    Employee, EmployeeTeam, PlanningScenario, ScenarioRevision,
    ScenarioTeamSnapshot,
)


class SnapshotWriter:
    def __init__(self, db: Session):
        self.db = db

    def write_team_snapshot(self, revision: ScenarioRevision, scenario: PlanningScenario) -> None:
        if not scenario.team:
            return
        emp_ids = [
            r[0]
            for r in self.db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team == scenario.team)
            .all()
        ]
        if not emp_ids:
            return
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(emp_ids))
            .all()
        )
        for emp in employees:
            self.db.add(ScenarioTeamSnapshot(
                revision_id=revision.id,
                employee_id=emp.id,
                display_name=emp.display_name,
                role=emp.role,
                hours_per_day=8.0,
                is_active=bool(emp.is_active),
                is_external=False,
            ))
```

- [ ] **Step 4: Run test, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py::test_write_team_snapshot_copies_active_team_members -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/snapshot_writer.py tests/test_snapshot_writer.py
git commit -m "feat(snapshot): SnapshotWriter skeleton with team snapshot"
```

---

### Task 5: Calendar + dictionary + rules snapshots

**Files:**
- Modify: `app/services/snapshot_writer.py`
- Modify: `tests/test_snapshot_writer.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_snapshot_writer.py`:

```python
from datetime import date as ddate
from app.models import (
    ProductionCalendarDay, MandatoryWorkType, ScenarioRule,
    AbsenceReason, Role,
    ScenarioCalendarSnapshot, ScenarioRulesSnapshot, ScenarioDictionarySnapshot,
)


def test_write_calendar_snapshot_copies_quarter_days(db: Session, team_setup):
    db.add(ProductionCalendarDay(date=ddate(2026, 4, 1), hours=8.0, is_workday=True, kind="workday", source="manual"))
    db.add(ProductionCalendarDay(date=ddate(2026, 5, 9), hours=0.0, is_workday=False, kind="holiday", source="manual"))
    db.add(ProductionCalendarDay(date=ddate(2026, 6, 30), hours=8.0, is_workday=True, kind="workday", source="manual"))
    db.add(ProductionCalendarDay(date=ddate(2026, 7, 1), hours=8.0, is_workday=True, kind="workday", source="manual"))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_calendar_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    db.commit()

    rows = db.query(ScenarioCalendarSnapshot).filter_by(revision_id="r-1").all()
    dates = sorted(r.date for r in rows)
    assert ddate(2026, 4, 1) in dates
    assert ddate(2026, 5, 9) in dates
    assert ddate(2026, 6, 30) in dates
    assert ddate(2026, 7, 1) not in dates  # вне Q2
    holiday = next(r for r in rows if r.date == ddate(2026, 5, 9))
    assert holiday.kind == "holiday"
    assert holiday.is_workday is False


def test_write_rules_snapshot_copies_scenario_rules(db: Session, team_setup):
    wt = MandatoryWorkType(id="wt-1", code="support", label="Сопровождение", is_active=True, sort_order=1, subtracts_from_pool=True)
    db.add(wt)
    db.add(ScenarioRule(id="sr-1", scenario_id="s-1", role="analyst", work_type_id="wt-1", percent_of_norm=35.0))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_rules_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    db.commit()

    rows = db.query(ScenarioRulesSnapshot).filter_by(revision_id="r-1").all()
    assert len(rows) == 1
    assert rows[0].role == "analyst"
    assert rows[0].work_type_id == "wt-1"
    assert rows[0].work_type_label == "Сопровождение"
    assert rows[0].pct_of_norm == 35.0


def test_write_dictionary_snapshot_copies_work_types_and_roles(db: Session, team_setup):
    db.add(MandatoryWorkType(id="wt-1", code="support", label="Сопровождение", is_active=True, sort_order=1, subtracts_from_pool=True))
    db.add(MandatoryWorkType(id="wt-2", code="org", label="Орг. вопросы", is_active=False, sort_order=2, subtracts_from_pool=True))
    db.add(Role(id="ro-1", code="analyst", label="Аналитик", sort_order=1, is_active=True))
    db.add(AbsenceReason(id="ar-1", label="Отпуск", is_planned=True, color="#fff", is_active=True, sort_order=1))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_dictionary_snapshot(revision=team_setup["revision"])
    db.commit()

    rows = db.query(ScenarioDictionarySnapshot).filter_by(revision_id="r-1").all()
    kinds = {(r.kind, r.original_id): r for r in rows}
    assert ("work_type", "wt-1") in kinds
    assert kinds[("work_type", "wt-1")].label == "Сопровождение"
    assert kinds[("work_type", "wt-1")].extra_json == {"subtracts_from_pool": True, "is_active": True}
    assert ("work_type", "wt-2") in kinds  # неактивные тоже копируются для readability
    assert ("role", "ro-1") in kinds
    assert ("absence_reason", "ar-1") in kinds
```

- [ ] **Step 2: Run tests, expect failures**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py -v`
Expected: 3 new tests FAIL with `AttributeError: 'SnapshotWriter' object has no attribute ...`.

- [ ] **Step 3: Implement methods**

Append to `app/services/snapshot_writer.py`:

```python
import calendar
from datetime import date

from app.models import (
    ProductionCalendarDay, ScenarioRule, MandatoryWorkType,
    Role, AbsenceReason,
    ScenarioCalendarSnapshot, ScenarioRulesSnapshot, ScenarioDictionarySnapshot,
)
from app.services.capacity_service import QUARTER_MONTHS


def _quarter_bounds(year: int, quarter_str: str) -> tuple[date, date]:
    q = int(str(quarter_str).replace("Q", ""))
    months = QUARTER_MONTHS[q]
    start = date(year, months[0], 1)
    end_day = calendar.monthrange(year, months[-1])[1]
    end = date(year, months[-1], end_day)
    return start, end


# --- new methods on SnapshotWriter ---


def _writer_write_calendar_snapshot(self, revision, scenario) -> None:  # type: ignore[no-untyped-def]
    if not (scenario.year and scenario.quarter):
        return
    start, end = _quarter_bounds(scenario.year, scenario.quarter)
    days = (
        self.db.query(ProductionCalendarDay)
        .filter(ProductionCalendarDay.date >= start, ProductionCalendarDay.date <= end)
        .all()
    )
    for d in days:
        self.db.add(ScenarioCalendarSnapshot(
            revision_id=revision.id,
            date=d.date,
            hours=float(d.hours),
            is_workday=bool(d.is_workday),
            kind=d.kind,
        ))


def _writer_write_rules_snapshot(self, revision, scenario) -> None:  # type: ignore[no-untyped-def]
    rules = self.db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario.id).all()
    if not rules:
        return
    wt_ids = {r.work_type_id for r in rules if r.work_type_id}
    wt_map = {
        wt.id: wt.label
        for wt in self.db.query(MandatoryWorkType).filter(MandatoryWorkType.id.in_(wt_ids)).all()
    } if wt_ids else {}
    for r in rules:
        self.db.add(ScenarioRulesSnapshot(
            revision_id=revision.id,
            role=r.role,
            work_type_id=r.work_type_id,
            work_type_label=wt_map.get(r.work_type_id, ""),
            pct_of_norm=float(r.percent_of_norm),
        ))


def _writer_write_dictionary_snapshot(self, revision) -> None:  # type: ignore[no-untyped-def]
    for wt in self.db.query(MandatoryWorkType).all():
        self.db.add(ScenarioDictionarySnapshot(
            revision_id=revision.id,
            kind="work_type",
            original_id=wt.id,
            code=wt.code,
            label=wt.label,
            sort_order=wt.sort_order,
            extra_json={"subtracts_from_pool": bool(wt.subtracts_from_pool), "is_active": bool(wt.is_active)},
        ))
    for role in self.db.query(Role).all():
        self.db.add(ScenarioDictionarySnapshot(
            revision_id=revision.id,
            kind="role",
            original_id=role.id,
            code=role.code,
            label=role.label,
            sort_order=role.sort_order,
            extra_json={"is_active": bool(role.is_active)},
        ))
    for ar in self.db.query(AbsenceReason).all():
        self.db.add(ScenarioDictionarySnapshot(
            revision_id=revision.id,
            kind="absence_reason",
            original_id=ar.id,
            code=None,
            label=ar.label,
            sort_order=ar.sort_order,
            extra_json={"is_planned": bool(ar.is_planned), "color": ar.color, "is_active": bool(ar.is_active)},
        ))


SnapshotWriter.write_calendar_snapshot = _writer_write_calendar_snapshot
SnapshotWriter.write_rules_snapshot = _writer_write_rules_snapshot
SnapshotWriter.write_dictionary_snapshot = _writer_write_dictionary_snapshot
```

- [ ] **Step 4: Run tests, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/snapshot_writer.py tests/test_snapshot_writer.py
git commit -m "feat(snapshot): writer for calendar/rules/dictionary snapshots"
```

---

### Task 6: Capacity snapshot with new fields

**Files:**
- Modify: `app/services/snapshot_writer.py`
- Modify: `tests/test_snapshot_writer.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_snapshot_writer.py`:

```python
from app.models import Absence, ScenarioCapacitySnapshot


def test_write_capacity_snapshot_per_emp_per_month(db: Session, team_setup):
    # Календарь Q2: апрель 22 рабочих дня, май 19, июнь 21 — но для теста зададим просто 8ч × 3 дня в каждом месяце
    for d in [ddate(2026, 4, 1), ddate(2026, 4, 2), ddate(2026, 4, 3),
              ddate(2026, 5, 1), ddate(2026, 5, 4), ddate(2026, 5, 5),
              ddate(2026, 6, 1), ddate(2026, 6, 2), ddate(2026, 6, 3)]:
        db.add(ProductionCalendarDay(date=d, hours=8.0, is_workday=True, kind="workday", source="manual"))
    # Иванов в отпуске весь май
    db.add(Absence(id="ab-1", employee_id="e-1", start_date=ddate(2026, 5, 1), end_date=ddate(2026, 5, 31)))
    # Правило: analyst — Сопровождение 35%, Орг 15% (вычитается из пула)
    db.add(MandatoryWorkType(id="wt-1", code="support", label="Сопровождение", is_active=True, sort_order=1, subtracts_from_pool=True))
    db.add(MandatoryWorkType(id="wt-2", code="org", label="Орг", is_active=True, sort_order=2, subtracts_from_pool=True))
    db.add(ScenarioRule(id="sr-1", scenario_id="s-1", role="analyst", work_type_id="wt-1", percent_of_norm=35.0))
    db.add(ScenarioRule(id="sr-2", scenario_id="s-1", role="analyst", work_type_id="wt-2", percent_of_norm=15.0))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_capacity_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    db.commit()

    rows = db.query(ScenarioCapacitySnapshot).filter_by(
        revision_id="r-1", employee_id="e-1"
    ).order_by(ScenarioCapacitySnapshot.month).all()
    assert len(rows) == 3
    apr, may, jun = rows
    # апрель: 24 ч брутто, 0 отсутствий → доступно 24 ч; mandatory = 24×0.5 = 12 ч; project = 12 ч
    assert apr.month == 4
    assert apr.gross_hours == 24.0
    assert apr.absence_hours == 0.0
    assert apr.available_hours == 24.0
    assert apr.mandatory_hours == 12.0
    assert apr.project_hours == 12.0
    # май: 24 ч брутто, 24 отсутствий (весь месяц) → доступно 0 ч
    assert may.absence_hours == 24.0
    assert may.available_hours == 0.0
    assert may.mandatory_hours == 0.0
    assert may.project_hours == 0.0
    # июнь: 24/0/24/12/12
    assert jun.gross_hours == 24.0
    assert jun.available_hours == 24.0
    # legacy norm_hours = gross_hours
    assert apr.norm_hours == 24.0
```

- [ ] **Step 2: Run, expect fail**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py::test_write_capacity_snapshot_per_emp_per_month -v`
Expected: FAIL with `AttributeError: write_capacity_snapshot`.

- [ ] **Step 3: Implement**

Append to `app/services/snapshot_writer.py`:

```python
from datetime import datetime as _dt, timedelta
from app.models import Absence, Employee, EmployeeTeam, ScenarioCapacitySnapshot


def _writer_write_capacity_snapshot(self, revision, scenario) -> None:  # type: ignore[no-untyped-def]
    """Per-emp × month: gross/absence/available/mandatory/project часы."""
    if not (scenario.team and scenario.year and scenario.quarter):
        return

    q = int(str(scenario.quarter).replace("Q", ""))
    months = QUARTER_MONTHS[q]

    # сотрудники команды (только активные на момент утверждения)
    emp_ids = [
        r[0] for r in self.db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team == scenario.team).all()
    ]
    employees = self.db.query(Employee).filter(Employee.id.in_(emp_ids), Employee.is_active.is_(True)).all() if emp_ids else []
    if not employees:
        return

    # календарь квартала per-day
    start, end = _quarter_bounds(scenario.year, scenario.quarter)
    cal_days = self.db.query(ProductionCalendarDay).filter(
        ProductionCalendarDay.date >= start, ProductionCalendarDay.date <= end
    ).all()
    cal_by_date = {d.date: float(d.hours) for d in cal_days}

    # отсутствия команды за период
    absences = self.db.query(Absence).filter(
        Absence.employee_id.in_([e.id for e in employees]),
        Absence.start_date <= end,
        Absence.end_date >= start,
    ).all()
    abs_by_emp: dict[str, list[tuple[date, date]]] = {}
    for a in absences:
        abs_by_emp.setdefault(a.employee_id, []).append((a.start_date, a.end_date))

    # правила сценария: подсчитать sum_pct mandatory per role
    rules = self.db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario.id).all()
    wt_subtracts: dict[str, bool] = {}
    if rules:
        wt_ids = {r.work_type_id for r in rules if r.work_type_id}
        if wt_ids:
            for wt in self.db.query(MandatoryWorkType).filter(MandatoryWorkType.id.in_(wt_ids)).all():
                wt_subtracts[wt.id] = bool(wt.subtracts_from_pool)

    def sum_pct_for_role(role: str | None) -> float:
        return sum(
            r.percent_of_norm for r in rules
            if (r.role is None or r.role == role) and wt_subtracts.get(r.work_type_id, False)
        )

    now = _dt.utcnow()
    for emp in employees:
        for month in months:
            # рабочие дни месяца
            month_start = date(scenario.year, month, 1)
            last_day = calendar.monthrange(scenario.year, month)[1]
            month_end = date(scenario.year, month, last_day)

            gross = 0.0
            absence_hrs = 0.0
            cur = month_start
            emp_abs = abs_by_emp.get(emp.id, [])
            while cur <= month_end:
                day_h = cal_by_date.get(cur, 0.0)
                if day_h > 0:
                    gross += day_h
                    if any(s <= cur <= e for s, e in emp_abs):
                        absence_hrs += day_h
                cur += timedelta(days=1)

            available = max(0.0, gross - absence_hrs)
            pct_mandatory = sum_pct_for_role(emp.role)
            mandatory = round(available * pct_mandatory / 100, 2)
            project = round(max(0.0, available - mandatory), 2)

            self.db.add(ScenarioCapacitySnapshot(
                revision_id=revision.id,
                employee_id=emp.id,
                employee_name=emp.display_name,
                year=scenario.year,
                month=month,
                norm_hours=round(gross, 2),  # legacy alias = gross
                available_hours=round(available, 2),
                backlog_pool_hours=project,  # legacy alias = project
                gross_hours=round(gross, 2),
                absence_hours=round(absence_hrs, 2),
                mandatory_hours=mandatory,
                project_hours=project,
                snapshot_taken_at=now,
            ))


SnapshotWriter.write_capacity_snapshot = _writer_write_capacity_snapshot
```

- [ ] **Step 4: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py::test_write_capacity_snapshot_per_emp_per_month -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/snapshot_writer.py tests/test_snapshot_writer.py
git commit -m "feat(snapshot): capacity snapshot with gross/absence/mandatory/project per-emp×month"
```

---

### Task 7: Norm snapshot fix (absences + external QA)

**Files:**
- Modify: `app/services/snapshot_writer.py`
- Modify: `tests/test_snapshot_writer.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_snapshot_writer.py`:

```python
from app.models import ScenarioNormSnapshot


def test_write_norm_snapshot_uses_available_not_gross(db: Session, team_setup):
    """Норм. часы = available × pct, НЕ gross × pct (отсутствия учтены)."""
    for d in [ddate(2026, 4, 1), ddate(2026, 4, 2),
              ddate(2026, 5, 4), ddate(2026, 5, 5),
              ddate(2026, 6, 1), ddate(2026, 6, 2)]:
        db.add(ProductionCalendarDay(date=d, hours=8.0, is_workday=True, kind="workday", source="manual"))
    # Иванов в отпуске 1-2 апреля
    db.add(Absence(id="ab-1", employee_id="e-1", start_date=ddate(2026, 4, 1), end_date=ddate(2026, 4, 2)))
    db.add(MandatoryWorkType(id="wt-1", code="support", label="Сопровождение", is_active=True, sort_order=1, subtracts_from_pool=True))
    db.add(ScenarioRule(id="sr-1", scenario_id="s-1", role="analyst", work_type_id="wt-1", percent_of_norm=35.0))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_capacity_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    writer.write_norm_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    db.commit()

    apr = db.query(ScenarioNormSnapshot).filter_by(
        revision_id="r-1", employee_id="e-1", month=4, work_type_id="wt-1"
    ).one()
    # gross = 16, absence = 16 (оба дня) → available = 0 → norm 0 (НЕ 16×0.35=5.6)
    assert apr.norm_hours == 0.0
    assert apr.is_external is False

    may = db.query(ScenarioNormSnapshot).filter_by(
        revision_id="r-1", employee_id="e-1", month=5, work_type_id="wt-1"
    ).one()
    # gross=16, absence=0 → available=16 → norm 16×0.35 = 5.6
    assert may.norm_hours == 5.6


def test_write_norm_snapshot_external_qa(db: Session, team_setup):
    """external_qa_hours = 600 → 200/мес × pct правила QA."""
    team_setup["scenario"].external_qa_hours = 600.0
    db.commit()
    db.add(MandatoryWorkType(id="wt-1", code="support", label="Сопровождение", is_active=True, sort_order=1, subtracts_from_pool=True))
    db.add(ScenarioRule(id="sr-1", scenario_id="s-1", role="qa", work_type_id="wt-1", percent_of_norm=35.0))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_capacity_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    writer.write_norm_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    db.commit()

    qa_rows = db.query(ScenarioNormSnapshot).filter_by(
        revision_id="r-1", is_external=True
    ).all()
    assert len(qa_rows) == 3  # 3 месяца
    for r in qa_rows:
        assert r.employee_id is None
        assert r.role == "qa"
        assert r.work_type_id == "wt-1"
        assert r.norm_hours == 70.0  # 200 × 0.35
```

- [ ] **Step 2: Run, expect fail**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py::test_write_norm_snapshot_uses_available_not_gross tests/test_snapshot_writer.py::test_write_norm_snapshot_external_qa -v`
Expected: FAIL — `write_norm_snapshot` не существует.

- [ ] **Step 3: Implement**

Append to `app/services/snapshot_writer.py`:

```python
from app.models import ScenarioNormSnapshot


def _writer_write_norm_snapshot(self, revision, scenario) -> None:  # type: ignore[no-untyped-def]
    """Норм. часы = available × pct правила; для внешнего QA — отдельные строки."""
    if not (scenario.team and scenario.year and scenario.quarter):
        return

    q = int(str(scenario.quarter).replace("Q", ""))
    months = QUARTER_MONTHS[q]

    # available_hours per emp×month — читаем из только что записанных capacity snapshots
    cap_rows = self.db.query(ScenarioCapacitySnapshot).filter_by(revision_id=revision.id).all()
    available_by_emp_month: dict[tuple[str, int], float] = {
        (r.employee_id, r.month): float(r.available_hours)
        for r in cap_rows if r.employee_id
    }

    # employees (для role)
    emp_ids = [
        r[0] for r in self.db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team == scenario.team).all()
    ]
    employees = self.db.query(Employee).filter(Employee.id.in_(emp_ids), Employee.is_active.is_(True)).all() if emp_ids else []
    emp_by_id = {e.id: e for e in employees}

    # правила
    rules = self.db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario.id).all()
    wt_label_by_id: dict[str, str] = {}
    if rules:
        wt_ids = {r.work_type_id for r in rules if r.work_type_id}
        if wt_ids:
            for wt in self.db.query(MandatoryWorkType).filter(MandatoryWorkType.id.in_(wt_ids)).all():
                wt_label_by_id[wt.id] = wt.label

    # 1. Штатные сотрудники
    for emp in employees:
        emp_role = emp.role
        for month in months:
            available = available_by_emp_month.get((emp.id, month), 0.0)
            for r in rules:
                if r.role is None or r.role == emp_role:
                    norm = round(available * r.percent_of_norm / 100, 2)
                    self.db.add(ScenarioNormSnapshot(
                        revision_id=revision.id,
                        employee_id=emp.id,
                        employee_name=emp.display_name,
                        role=emp_role,
                        year=scenario.year,
                        month=month,
                        work_type_id=r.work_type_id,
                        work_type_label=wt_label_by_id.get(r.work_type_id, ""),
                        norm_hours=norm,
                        is_external=False,
                    ))

    # 2. Внешний QA
    if scenario.external_qa_hours is not None and float(scenario.external_qa_hours) > 0:
        ext_per_month = float(scenario.external_qa_hours) / len(months)
        qa_rules = [r for r in rules if r.role == "qa"]
        for month in months:
            for r in qa_rules:
                norm = round(ext_per_month * r.percent_of_norm / 100, 2)
                self.db.add(ScenarioNormSnapshot(
                    revision_id=revision.id,
                    employee_id=None,
                    employee_name="(внешний QA)",
                    role="qa",
                    year=scenario.year,
                    month=month,
                    work_type_id=r.work_type_id,
                    work_type_label=wt_label_by_id.get(r.work_type_id, ""),
                    norm_hours=norm,
                    is_external=True,
                ))


SnapshotWriter.write_norm_snapshot = _writer_write_norm_snapshot
```

- [ ] **Step 4: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/snapshot_writer.py tests/test_snapshot_writer.py
git commit -m "fix(snapshot): norm uses available_hours + external QA rows"
```

---

### Task 8: Allocation snapshot

**Files:**
- Modify: `app/services/snapshot_writer.py`
- Modify: `tests/test_snapshot_writer.py`

- [ ] **Step 1: Add test**

Append to `tests/test_snapshot_writer.py`:

```python
from app.models import BacklogItem, ScenarioAllocation, ScenarioAllocationSnapshot


def test_write_allocation_snapshot_copies_included_only(db: Session, team_setup):
    bi1 = BacklogItem(
        id="bi-1", title="Инициатива A",
        estimate_analyst_hours=20.0, estimate_dev_hours=40.0, estimate_qa_hours=10.0,
        estimate_opo_hours=8.0, opo_analyst_ratio=0.5,
        impact="high", risk="medium", customer="Иванов", cost_type="run",
        priority=1, assignee_employee_id="e-1",
    )
    bi2 = BacklogItem(
        id="bi-2", title="Инициатива B (не включена)",
        estimate_analyst_hours=5.0,
    )
    db.add_all([bi1, bi2])
    db.add(ScenarioAllocation(
        id="al-1", scenario_id="s-1", backlog_item_id="bi-1",
        included_flag=True, sort_order=1.0, involvement_coefficient=1.0, planned_hours=78.0,
    ))
    db.add(ScenarioAllocation(
        id="al-2", scenario_id="s-1", backlog_item_id="bi-2",
        included_flag=False, sort_order=2.0,
    ))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_allocation_snapshot(revision=team_setup["revision"], scenario=team_setup["scenario"])
    db.commit()

    rows = db.query(ScenarioAllocationSnapshot).filter_by(revision_id="r-1").all()
    assert len(rows) == 1
    snap = rows[0]
    assert snap.allocation_id == "al-1"
    assert snap.backlog_item_id == "bi-1"
    assert snap.title == "Инициатива A"
    assert snap.estimate_analyst_hours == 20.0
    assert snap.estimate_dev_hours == 40.0
    assert snap.estimate_qa_hours == 10.0
    assert snap.estimate_opo_hours == 8.0
    assert snap.opo_analyst_ratio == 0.5
    assert snap.impact == "high"
    assert snap.customer == "Иванов"
    assert snap.assignee_employee_id == "e-1"
    assert snap.assignee_role_at_approval == "analyst"
    assert snap.involvement_coefficient == 1.0
```

- [ ] **Step 2: Run, expect fail**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py::test_write_allocation_snapshot_copies_included_only -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `app/services/snapshot_writer.py`:

```python
from app.models import BacklogItem, ScenarioAllocation, ScenarioAllocationSnapshot


def _writer_write_allocation_snapshot(self, revision, scenario) -> None:  # type: ignore[no-untyped-def]
    rows = (
        self.db.query(ScenarioAllocation, BacklogItem)
        .join(BacklogItem, ScenarioAllocation.backlog_item_id == BacklogItem.id)
        .filter(
            ScenarioAllocation.scenario_id == scenario.id,
            ScenarioAllocation.included_flag.is_(True),
        )
        .all()
    )
    if not rows:
        return

    # роли assignee — берём из живой Employee (один SELECT для всех)
    assignee_ids = {bi.assignee_employee_id for _, bi in rows if bi.assignee_employee_id}
    role_by_emp: dict[str, str | None] = {}
    if assignee_ids:
        for e in self.db.query(Employee).filter(Employee.id.in_(assignee_ids)).all():
            role_by_emp[e.id] = e.role

    for alloc, bi in rows:
        self.db.add(ScenarioAllocationSnapshot(
            revision_id=revision.id,
            allocation_id=alloc.id,
            backlog_item_id=bi.id,
            sort_order=alloc.sort_order,
            included_flag=True,
            involvement_coefficient=alloc.involvement_coefficient,
            title=bi.title,
            issue_id=bi.issue_id,
            project_id=bi.project_id,
            customer=bi.customer,
            cost_type=bi.cost_type,
            impact=bi.impact,
            risk=bi.risk,
            priority=bi.priority,
            estimate_analyst_hours=bi.estimate_analyst_hours,
            estimate_dev_hours=bi.estimate_dev_hours,
            estimate_qa_hours=bi.estimate_qa_hours,
            estimate_opo_hours=bi.estimate_opo_hours,
            opo_analyst_ratio=bi.opo_analyst_ratio,
            assignee_employee_id=bi.assignee_employee_id,
            assignee_role_at_approval=role_by_emp.get(bi.assignee_employee_id) if bi.assignee_employee_id else None,
        ))


SnapshotWriter.write_allocation_snapshot = _writer_write_allocation_snapshot
```

- [ ] **Step 4: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py::test_write_allocation_snapshot_copies_included_only -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/snapshot_writer.py tests/test_snapshot_writer.py
git commit -m "feat(snapshot): allocation snapshot with backlog_item attribute copy"
```

---

### Task 9: Allocation breakdown auto-split

**Files:**
- Modify: `app/services/snapshot_writer.py`
- Create: `tests/test_snapshot_writer_breakdown.py`

- [ ] **Step 1: Add test**

Create `tests/test_snapshot_writer_breakdown.py`:

```python
"""Тест автосплита allocation по месяцам и ролям."""
from datetime import date as ddate, datetime
import pytest
from sqlalchemy.orm import Session
from app.models import (
    Employee, EmployeeTeam, PlanningScenario, ScenarioRevision,
    BacklogItem, ScenarioAllocation, ScenarioCapacitySnapshot,
    ScenarioAllocationBreakdownSnapshot, ProductionCalendarDay,
)
from app.services.snapshot_writer import SnapshotWriter


@pytest.fixture
def fixed_caps_setup(db: Session):
    """Команда: 1 analyst (assignee), 1 RP, 2 devs. Available helpers зафиксированы вручную."""
    e_an = Employee(id="e-an", jira_account_id="j1", display_name="Аналитик А.", role="analyst", is_active=True)
    e_rp = Employee(id="e-rp", jira_account_id="j2", display_name="РП Р.", role="RP", is_active=True)
    e_d1 = Employee(id="e-d1", jira_account_id="j3", display_name="Девелопер 1", role="dev", is_active=True)
    e_d2 = Employee(id="e-d2", jira_account_id="j4", display_name="Девелопер 2", role="dev", is_active=True)
    db.add_all([e_an, e_rp, e_d1, e_d2])
    for i, emp in enumerate([e_an, e_rp, e_d1, e_d2]):
        db.add(EmployeeTeam(id=f"et-{i}", employee_id=emp.id, team="T1", is_primary=True))

    sc = PlanningScenario(id="s-1", name="Q2", year=2026, quarter="Q2", team="T1", status="draft")
    db.add(sc)
    rev = ScenarioRevision(id="r-1", scenario_id="s-1", revision_number=1, approved_at=datetime.utcnow())
    db.add(rev)

    # capacity snapshots вручную (имитируем результат write_capacity_snapshot)
    # Аналитик: 100/100/100 ч × 3 мес. РП: 80/80/80. Дев1: 60/60/60. Дев2: 40/40/40.
    for emp_id, hrs in [("e-an", 100), ("e-rp", 80), ("e-d1", 60), ("e-d2", 40)]:
        for m in [4, 5, 6]:
            db.add(ScenarioCapacitySnapshot(
                revision_id="r-1", employee_id=emp_id, employee_name="x",
                year=2026, month=m,
                norm_hours=hrs, available_hours=hrs, gross_hours=hrs,
                absence_hours=0.0, mandatory_hours=0.0, project_hours=hrs,
                snapshot_taken_at=datetime.utcnow(),
            ))
    db.commit()
    return {"scenario": sc, "revision": rev}


def test_breakdown_splits_analyst_to_assignee_proportional_to_months(db: Session, fixed_caps_setup):
    bi = BacklogItem(
        id="bi-1", title="Инициатива",
        estimate_analyst_hours=30.0, estimate_dev_hours=0.0, estimate_qa_hours=0.0,
        estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
        assignee_employee_id="e-an",
    )
    db.add(bi)
    db.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_allocation_snapshot(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    writer.write_allocation_breakdown(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    db.commit()

    rows = db.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="r-1", role="analyst"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()
    # 100/100/100 → равномерно 10/10/10
    assert len(rows) == 3
    assert all(r.employee_id == "e-an" for r in rows)
    assert all(r.is_external is False for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(30.0)
    assert rows[0].hours == pytest.approx(10.0)


def test_breakdown_splits_dev_into_pool_proportional_to_team_capacity(db: Session, fixed_caps_setup):
    bi = BacklogItem(
        id="bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=300.0,
        estimate_qa_hours=0.0, estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
    )
    db.add(bi)
    db.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_allocation_snapshot(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    writer.write_allocation_breakdown(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    db.commit()

    rows = db.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="r-1", role="dev"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()
    # суммарный available dev = 100/мес × 3 = 300, всё равномерно по 100, делим 300 → 100/100/100
    assert len(rows) == 3
    assert all(r.employee_id is None for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(300.0)
    assert rows[0].hours == pytest.approx(100.0)


def test_breakdown_qa_external(db: Session, fixed_caps_setup):
    fixed_caps_setup["scenario"].external_qa_hours = 600.0
    db.commit()
    bi = BacklogItem(
        id="bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=0.0, estimate_qa_hours=60.0,
        estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
    )
    db.add(bi)
    db.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_allocation_snapshot(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    writer.write_allocation_breakdown(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    db.commit()

    rows = db.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="r-1", role="qa"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()
    assert len(rows) == 3
    assert all(r.is_external is True for r in rows)
    assert all(r.employee_id is None for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(60.0)
    assert rows[0].hours == pytest.approx(20.0)


def test_breakdown_rp_to_single_team_rp(db: Session, fixed_caps_setup):
    bi = BacklogItem(
        id="bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=0.0, estimate_qa_hours=0.0,
        estimate_opo_hours=30.0, opo_analyst_ratio=0.5,
    )
    db.add(bi)
    db.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db.commit()

    writer = SnapshotWriter(db)
    writer.write_allocation_snapshot(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    writer.write_allocation_breakdown(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    db.commit()

    rp_rows = db.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="r-1", role="RP"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()
    # ОПЭ=30, аналитик-доля=0.5 → 15 ч аналитику + 15 ч РП. Аналитик assignee нет (NULL) — равномерно. РП → e-rp.
    assert len(rp_rows) == 3
    assert all(r.employee_id == "e-rp" for r in rp_rows)
    assert sum(r.hours for r in rp_rows) == pytest.approx(15.0)
```

- [ ] **Step 2: Run, expect fail**

Run: `py -3.10 -m pytest tests/test_snapshot_writer_breakdown.py -v`
Expected: 4 FAIL — `write_allocation_breakdown` отсутствует.

- [ ] **Step 3: Implement breakdown**

Append to `app/services/snapshot_writer.py`:

```python
from app.models import ScenarioAllocationBreakdownSnapshot


def _split_proportional(total: float, weights: list[float]) -> list[float]:
    """Делит total по весам weights пропорционально, последний элемент компенсирует ошибку округления."""
    n = len(weights)
    if n == 0:
        return []
    s = sum(weights)
    if s <= 0:
        # равномерный split
        equal = round(total / n, 2)
        out = [equal] * (n - 1) + [round(total - equal * (n - 1), 2)]
        return out
    out: list[float] = []
    accumulated = 0.0
    for i, w in enumerate(weights):
        if i == n - 1:
            out.append(round(total - accumulated, 2))
        else:
            v = round(total * w / s, 2)
            out.append(v)
            accumulated += v
    return out


def _writer_write_allocation_breakdown(self, revision, scenario) -> None:  # type: ignore[no-untyped-def]
    if not (scenario.team and scenario.year and scenario.quarter):
        return

    q = int(str(scenario.quarter).replace("Q", ""))
    months = QUARTER_MONTHS[q]

    # capacity snapshots — для available_hours per emp×month
    cap_rows = self.db.query(ScenarioCapacitySnapshot).filter_by(revision_id=revision.id).all()
    avail_emp_month: dict[tuple[str, int], float] = {
        (r.employee_id, r.month): float(r.available_hours)
        for r in cap_rows if r.employee_id
    }

    # роли сотрудников команды
    emp_ids = [
        r[0] for r in self.db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team == scenario.team).all()
    ]
    employees = self.db.query(Employee).filter(Employee.id.in_(emp_ids), Employee.is_active.is_(True)).all() if emp_ids else []
    devs = [e for e in employees if e.role == "dev"]
    qas = [e for e in employees if e.role == "qa"]
    rps = [e for e in employees if e.role == "RP"]
    rp_emp_id = sorted(rps, key=lambda e: e.display_name)[0].id if rps else None

    # available по группе ролей × месяц
    def avail_role_month(role_emps: list[Employee], month: int) -> float:
        return sum(avail_emp_month.get((e.id, month), 0.0) for e in role_emps)

    # allocations
    allocs = (
        self.db.query(ScenarioAllocation, BacklogItem)
        .join(BacklogItem, ScenarioAllocation.backlog_item_id == BacklogItem.id)
        .filter(
            ScenarioAllocation.scenario_id == scenario.id,
            ScenarioAllocation.included_flag.is_(True),
        )
        .all()
    )
    role_by_emp: dict[str, str | None] = {e.id: e.role for e in employees}

    qa_external = scenario.external_qa_hours is not None and float(scenario.external_qa_hours or 0) > 0

    for alloc, bi in allocs:
        # 1. Часы по ролям (квартальные суммы)
        opo = float(bi.estimate_opo_hours or 0)
        opo_an_ratio = float(bi.opo_analyst_ratio if bi.opo_analyst_ratio is not None else 0.5)
        an_total = float(bi.estimate_analyst_hours or 0) + opo * opo_an_ratio
        rp_total = opo * (1 - opo_an_ratio)
        dev_total = float(bi.estimate_dev_hours or 0)
        qa_total = float(bi.estimate_qa_hours or 0)

        # роль assignee → analyst или consultant
        assignee_role = role_by_emp.get(bi.assignee_employee_id) if bi.assignee_employee_id else None
        an_role = "consultant" if assignee_role == "consultant" else "analyst"
        an_emp_id = bi.assignee_employee_id if assignee_role in {"analyst", "consultant"} else None

        # 2. Сплит по месяцам
        def split_for_emp(total: float, emp_id: str | None) -> list[float]:
            if total == 0:
                return [0.0] * len(months)
            if emp_id is None:
                return _split_proportional(total, [1.0] * len(months))
            return _split_proportional(total, [avail_emp_month.get((emp_id, m), 0.0) for m in months])

        def split_for_pool(total: float, role_emps: list[Employee]) -> list[float]:
            if total == 0:
                return [0.0] * len(months)
            return _split_proportional(total, [avail_role_month(role_emps, m) for m in months])

        # an
        if an_total > 0:
            for month, h in zip(months, split_for_emp(an_total, an_emp_id)):
                self.db.add(ScenarioAllocationBreakdownSnapshot(
                    revision_id=revision.id, allocation_id=alloc.id, month=month,
                    role=an_role, employee_id=an_emp_id, is_external=False, hours=h,
                ))
        # rp
        if rp_total > 0:
            for month, h in zip(months, split_for_emp(rp_total, rp_emp_id)):
                self.db.add(ScenarioAllocationBreakdownSnapshot(
                    revision_id=revision.id, allocation_id=alloc.id, month=month,
                    role="RP", employee_id=rp_emp_id, is_external=False, hours=h,
                ))
        # dev
        if dev_total > 0:
            for month, h in zip(months, split_for_pool(dev_total, devs)):
                self.db.add(ScenarioAllocationBreakdownSnapshot(
                    revision_id=revision.id, allocation_id=alloc.id, month=month,
                    role="dev", employee_id=None, is_external=False, hours=h,
                ))
        # qa
        if qa_total > 0:
            if qa_external:
                # равномерно
                for month, h in zip(months, _split_proportional(qa_total, [1.0] * len(months))):
                    self.db.add(ScenarioAllocationBreakdownSnapshot(
                        revision_id=revision.id, allocation_id=alloc.id, month=month,
                        role="qa", employee_id=None, is_external=True, hours=h,
                    ))
            else:
                for month, h in zip(months, split_for_pool(qa_total, qas)):
                    self.db.add(ScenarioAllocationBreakdownSnapshot(
                        revision_id=revision.id, allocation_id=alloc.id, month=month,
                        role="qa", employee_id=None, is_external=False, hours=h,
                    ))


SnapshotWriter.write_allocation_breakdown = _writer_write_allocation_breakdown
```

- [ ] **Step 4: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_writer_breakdown.py -v`
Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/snapshot_writer.py tests/test_snapshot_writer_breakdown.py
git commit -m "feat(snapshot): allocation auto-split per month/role with proportional weights"
```

---

### Task 10: External QA edge case + 0/multi РП

**Files:**
- Create: `tests/test_snapshot_writer_external_qa.py`

- [ ] **Step 1: Add tests for edge cases**

Create `tests/test_snapshot_writer_external_qa.py`:

```python
"""Edge cases для SnapshotWriter: 0/несколько РП, внешний QA, отсутствие dev."""
from datetime import date as ddate, datetime
import pytest
from sqlalchemy.orm import Session
from app.models import (
    Employee, EmployeeTeam, PlanningScenario, ScenarioRevision,
    BacklogItem, ScenarioAllocation, ScenarioCapacitySnapshot,
    ScenarioAllocationBreakdownSnapshot,
)
from app.services.snapshot_writer import SnapshotWriter


def _make_scenario(db: Session, team: str = "T1", external_qa: float | None = None) -> dict:
    sc = PlanningScenario(id="s-1", name="Q2", year=2026, quarter="Q2", team=team, status="draft", external_qa_hours=external_qa)
    db.add(sc)
    rev = ScenarioRevision(id="r-1", scenario_id="s-1", revision_number=1, approved_at=datetime.utcnow())
    db.add(rev)
    db.commit()
    return {"scenario": sc, "revision": rev}


def test_breakdown_zero_rp_in_team_writes_null_employee(db: Session):
    """Команда без РП: rp_hours идут со строкой employee_id=NULL (сигнал не назначено)."""
    db.add(Employee(id="e-an", jira_account_id="j", display_name="Аналитик", role="analyst", is_active=True))
    db.add(EmployeeTeam(id="et", employee_id="e-an", team="T1", is_primary=True))
    setup = _make_scenario(db)
    db.add(ScenarioCapacitySnapshot(
        revision_id="r-1", employee_id="e-an", employee_name="x",
        year=2026, month=4, norm_hours=100, available_hours=100, gross_hours=100,
        absence_hours=0, mandatory_hours=0, project_hours=100, snapshot_taken_at=datetime.utcnow(),
    ))
    db.add(ScenarioCapacitySnapshot(
        revision_id="r-1", employee_id="e-an", employee_name="x",
        year=2026, month=5, norm_hours=100, available_hours=100, gross_hours=100,
        absence_hours=0, mandatory_hours=0, project_hours=100, snapshot_taken_at=datetime.utcnow(),
    ))
    db.add(ScenarioCapacitySnapshot(
        revision_id="r-1", employee_id="e-an", employee_name="x",
        year=2026, month=6, norm_hours=100, available_hours=100, gross_hours=100,
        absence_hours=0, mandatory_hours=0, project_hours=100, snapshot_taken_at=datetime.utcnow(),
    ))
    bi = BacklogItem(id="bi", title="X", estimate_opo_hours=30.0, opo_analyst_ratio=0.5)
    db.add(bi)
    db.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi", included_flag=True))
    db.commit()

    w = SnapshotWriter(db)
    w.write_allocation_snapshot(revision=setup["revision"], scenario=setup["scenario"])
    w.write_allocation_breakdown(revision=setup["revision"], scenario=setup["scenario"])
    db.commit()

    rp_rows = db.query(ScenarioAllocationBreakdownSnapshot).filter_by(role="RP").all()
    assert len(rp_rows) == 3
    assert all(r.employee_id is None for r in rp_rows)


def test_breakdown_multiple_rps_picks_first_alphabetical(db: Session):
    db.add(Employee(id="e-rp-z", jira_account_id="j1", display_name="Я-Зоркий", role="RP", is_active=True))
    db.add(Employee(id="e-rp-a", jira_account_id="j2", display_name="А-Активный", role="RP", is_active=True))
    db.add(EmployeeTeam(id="et1", employee_id="e-rp-z", team="T1", is_primary=True))
    db.add(EmployeeTeam(id="et2", employee_id="e-rp-a", team="T1", is_primary=True))
    setup = _make_scenario(db)
    for emp_id in ["e-rp-z", "e-rp-a"]:
        for m in [4, 5, 6]:
            db.add(ScenarioCapacitySnapshot(
                revision_id="r-1", employee_id=emp_id, employee_name="x",
                year=2026, month=m, norm_hours=100, available_hours=100, gross_hours=100,
                absence_hours=0, mandatory_hours=0, project_hours=100, snapshot_taken_at=datetime.utcnow(),
            ))
    bi = BacklogItem(id="bi", title="X", estimate_opo_hours=30.0, opo_analyst_ratio=0.5)
    db.add(bi)
    db.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi", included_flag=True))
    db.commit()

    w = SnapshotWriter(db)
    w.write_allocation_snapshot(revision=setup["revision"], scenario=setup["scenario"])
    w.write_allocation_breakdown(revision=setup["revision"], scenario=setup["scenario"])
    db.commit()

    rp_rows = db.query(ScenarioAllocationBreakdownSnapshot).filter_by(role="RP").all()
    assert all(r.employee_id == "e-rp-a" for r in rp_rows)  # alphabetical first


def test_breakdown_zero_dev_writes_null_employee(db: Session):
    """estimate_dev_hours > 0 но в команде нет dev — пишем employee_id=NULL."""
    db.add(Employee(id="e-an", jira_account_id="j", display_name="Аналитик", role="analyst", is_active=True))
    db.add(EmployeeTeam(id="et", employee_id="e-an", team="T1", is_primary=True))
    setup = _make_scenario(db)
    for m in [4, 5, 6]:
        db.add(ScenarioCapacitySnapshot(
            revision_id="r-1", employee_id="e-an", employee_name="x",
            year=2026, month=m, norm_hours=100, available_hours=100, gross_hours=100,
            absence_hours=0, mandatory_hours=0, project_hours=100, snapshot_taken_at=datetime.utcnow(),
        ))
    bi = BacklogItem(id="bi", title="X", estimate_dev_hours=30.0)
    db.add(bi)
    db.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi", included_flag=True))
    db.commit()

    w = SnapshotWriter(db)
    w.write_allocation_snapshot(revision=setup["revision"], scenario=setup["scenario"])
    w.write_allocation_breakdown(revision=setup["revision"], scenario=setup["scenario"])
    db.commit()

    dev_rows = db.query(ScenarioAllocationBreakdownSnapshot).filter_by(role="dev").all()
    assert len(dev_rows) == 3
    assert all(r.employee_id is None for r in dev_rows)
    # суммы должны быть равны total через равномерный split при нулевом весе
    assert sum(r.hours for r in dev_rows) == pytest.approx(30.0)
```

- [ ] **Step 2: Run, expect pass (logic уже реализована в Task 9)**

Run: `py -3.10 -m pytest tests/test_snapshot_writer_external_qa.py -v`
Expected: All 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snapshot_writer_external_qa.py
git commit -m "test(snapshot): edge cases for 0/multi RP and missing dev"
```

---

## Phase 3 — Approve endpoint

### Task 11: Wire SnapshotWriter into approve_scenario

**Files:**
- Modify: `app/api/endpoints/planning.py`

- [ ] **Step 1: Replace inline snapshot logic in approve_scenario**

In `app/api/endpoints/planning.py`, locate `approve_scenario` function. Replace entire body of «Снапшот нормы команды» + «Снапшот отсутствий команды» blocks (approximately lines 571–675) with:

```python
    # --- Заполнение всех snapshot-таблиц через SnapshotWriter (algo_version='v2') ---
    revision.parent_revision_id = prev_revision.id if prev_revision else None
    revision.algo_version = "v2"

    from app.services.snapshot_writer import SnapshotWriter
    writer = SnapshotWriter(db)
    writer.write_team_snapshot(revision=revision, scenario=scenario)
    writer.write_calendar_snapshot(revision=revision, scenario=scenario)
    writer.write_rules_snapshot(revision=revision, scenario=scenario)
    writer.write_dictionary_snapshot(revision=revision)
    writer.write_capacity_snapshot(revision=revision, scenario=scenario)
    writer.write_norm_snapshot(revision=revision, scenario=scenario)
    writer.write_allocation_snapshot(revision=revision, scenario=scenario)
    writer.write_allocation_breakdown(revision=revision, scenario=scenario)

    # absence snapshot — оставлено inline, переедет в writer в отдельном PR
    if scenario.team and scenario.year and scenario.quarter:
        q = int(str(scenario.quarter).replace("Q", ""))
        months = QUARTER_MONTHS[q]
        emp_ids = [
            r[0]
            for r in db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team == scenario.team)
            .all()
        ]
        employees_for_abs = (
            db.query(Employee)
            .filter(Employee.id.in_(emp_ids), Employee.is_active == True)  # noqa: E712
            .all()
        )
        quarter_start = date(scenario.year, months[0], 1)
        last_day = calendar.monthrange(scenario.year, months[-1])[1]
        quarter_end = date(scenario.year, months[-1], last_day)
        absences = db.query(Absence).filter(
            Absence.employee_id.in_([emp.id for emp in employees_for_abs]),
            Absence.start_date <= quarter_end,
            Absence.end_date >= quarter_start,
        ).all()
        reason_ids = list({a.reason_id for a in absences if a.reason_id})
        reasons: dict[str, str] = {}
        if reason_ids:
            reasons = {
                r.id: r.label
                for r in db.query(AbsenceReason).filter(AbsenceReason.id.in_(reason_ids)).all()
            }
        emp_names = {emp.id: emp.display_name for emp in employees_for_abs}
        capacity_svc = CapacityService(db)
        for ab in absences:
            db.add(ScenarioAbsenceSnapshot(
                revision_id=revision.id,
                employee_id=ab.employee_id,
                employee_name=emp_names.get(ab.employee_id, ""),
                original_absence_id=ab.id,
                start_date=ab.start_date,
                end_date=ab.end_date,
                reason_id=ab.reason_id,
                reason_label=reasons.get(ab.reason_id) if ab.reason_id else None,
                hours_total=_resolve_absence_hours(ab, capacity_svc),
            ))
```

- [ ] **Step 2: Run existing planning endpoint tests**

Run: `py -3.10 -m pytest tests/ -k "scenario" -v`
Expected: existing tests PASS (or fail only on previously-known failures from `feedback_capacity_overhaul_followups` memory).

- [ ] **Step 3: Run full backend test suite**

Run: `py -3.10 -m pytest tests/ -v --tb=short`
Expected: All snapshot writer tests PASS; pre-existing failures unchanged.

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/planning.py
git commit -m "refactor(planning): approve_scenario uses SnapshotWriter (algo_version=v2)"
```

---

### Task 12: Integration test — approve creates all v2 snapshots

**Files:**
- Modify: `tests/test_snapshot_writer.py`

- [ ] **Step 1: Add E2E approve test**

Append to `tests/test_snapshot_writer.py`:

```python
from fastapi.testclient import TestClient
from app.main import app


def test_approve_endpoint_writes_v2_snapshots(client: TestClient, db: Session, team_setup):
    """Полный e2e: POST /scenarios/{id}/approve → все snapshot-таблицы заполнены, algo_version=v2."""
    # минимальный inventory: календарь + правило + бэклог
    for d in [ddate(2026, 4, 1), ddate(2026, 5, 1), ddate(2026, 6, 1)]:
        db.add(ProductionCalendarDay(date=d, hours=8.0, is_workday=True, kind="workday", source="manual"))
    db.add(MandatoryWorkType(id="wt-1", code="support", label="Сопровождение", is_active=True, sort_order=1, subtracts_from_pool=True))
    db.add(ScenarioRule(id="sr-1", scenario_id="s-1", role="analyst", work_type_id="wt-1", percent_of_norm=35.0))
    db.add(BacklogItem(id="bi-1", title="X", estimate_analyst_hours=10.0, assignee_employee_id="e-1"))
    db.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db.commit()

    resp = client.post("/api/v1/planning/scenarios/s-1/approve", json={})
    assert resp.status_code == 200

    # последняя ревизия — v2
    rev = db.query(ScenarioRevision).filter_by(scenario_id="s-1").order_by(ScenarioRevision.revision_number.desc()).first()
    assert rev.algo_version == "v2"

    # все snapshot-таблицы заполнены (хотя бы одна строка где это возможно)
    assert db.query(ScenarioTeamSnapshot).filter_by(revision_id=rev.id).count() == 2
    assert db.query(ScenarioCalendarSnapshot).filter_by(revision_id=rev.id).count() == 3
    assert db.query(ScenarioRulesSnapshot).filter_by(revision_id=rev.id).count() == 1
    assert db.query(ScenarioDictionarySnapshot).filter_by(revision_id=rev.id, kind="work_type").count() == 1
    assert db.query(ScenarioCapacitySnapshot).filter_by(revision_id=rev.id).count() == 6  # 2 emp × 3 мес
    assert db.query(ScenarioNormSnapshot).filter_by(revision_id=rev.id).count() >= 1
    assert db.query(ScenarioAllocationSnapshot).filter_by(revision_id=rev.id).count() == 1
    assert db.query(ScenarioAllocationBreakdownSnapshot).filter_by(revision_id=rev.id).count() >= 1
```

- [ ] **Step 2: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py::test_approve_endpoint_writes_v2_snapshots -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snapshot_writer.py
git commit -m "test(planning): e2e approve writes all v2 snapshots"
```

---

## Phase 4 — Delete revision

### Task 13: DELETE revision endpoint

**Files:**
- Modify: `app/api/endpoints/planning.py`
- Create: `tests/test_snapshot_delete.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_snapshot_delete.py`:

```python
"""Тесты DELETE /planning/scenarios/{sid}/revisions/{rid}."""
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models import PlanningScenario, ScenarioRevision, ScenarioCapacitySnapshot


@pytest.fixture
def two_revisions(db: Session):
    sc = PlanningScenario(id="s-1", name="Q2", year=2026, quarter="Q2", team="T1", status="approved")
    db.add(sc)
    rev1 = ScenarioRevision(id="r-1", scenario_id="s-1", revision_number=1, approved_at=datetime(2026, 4, 1))
    rev2 = ScenarioRevision(id="r-2", scenario_id="s-1", revision_number=2, approved_at=datetime(2026, 4, 15), parent_revision_id="r-1")
    rev3 = ScenarioRevision(id="r-3", scenario_id="s-1", revision_number=3, approved_at=datetime(2026, 4, 20), parent_revision_id="r-2")
    db.add_all([rev1, rev2, rev3])
    # одна snapshot-строка чтобы проверить каскад
    db.add(ScenarioCapacitySnapshot(
        revision_id="r-2", employee_id="e-1", employee_name="x",
        year=2026, month=4, norm_hours=100, available_hours=100,
        snapshot_taken_at=datetime.utcnow(),
    ))
    db.commit()
    return sc


def test_delete_middle_revision_relinks_parent(client: TestClient, db: Session, two_revisions):
    resp = client.delete("/api/v1/planning/scenarios/s-1/revisions/r-2")
    assert resp.status_code == 204

    # r-2 удалён + каскад
    assert db.get(ScenarioRevision, "r-2") is None
    assert db.query(ScenarioCapacitySnapshot).filter_by(revision_id="r-2").count() == 0
    # r-3.parent_revision_id перецеплено на r-1
    rev3 = db.get(ScenarioRevision, "r-3")
    assert rev3 is not None
    assert rev3.parent_revision_id == "r-1"


def test_delete_last_remaining_revision_drafts_scenario(client: TestClient, db: Session):
    sc = PlanningScenario(id="s-2", name="Q3", year=2026, quarter="Q3", team="T", status="approved")
    db.add(sc)
    rev = ScenarioRevision(id="r-only", scenario_id="s-2", revision_number=1, approved_at=datetime.utcnow())
    db.add(rev)
    db.commit()

    resp = client.delete("/api/v1/planning/scenarios/s-2/revisions/r-only")
    assert resp.status_code == 204

    db.refresh(sc)
    assert sc.status == "draft"


def test_delete_unknown_revision_returns_404(client: TestClient):
    resp = client.delete("/api/v1/planning/scenarios/s-1/revisions/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run, expect fail**

Run: `py -3.10 -m pytest tests/test_snapshot_delete.py -v`
Expected: FAIL — endpoint not found (404 on POST routes; or method not allowed).

- [ ] **Step 3: Implement endpoint**

In `app/api/endpoints/planning.py`, add new endpoint near revision endpoints (search for "scenarios/{scenario_id}/revisions"):

```python
from fastapi import status as http_status


@router.delete(
    "/scenarios/{scenario_id}/revisions/{revision_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def delete_revision(
    scenario_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Удалить ревизию: каскад на все snapshot-таблицы + перепривязка parent."""
    rev = db.query(ScenarioRevision).filter_by(id=revision_id, scenario_id=scenario_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")

    # перепривязать детей: их parent_revision_id → этого rev.parent_revision_id
    db.query(ScenarioRevision).filter(
        ScenarioRevision.parent_revision_id == revision_id
    ).update(
        {"parent_revision_id": rev.parent_revision_id},
        synchronize_session=False,
    )

    # удаляем сам rev (cascade по snapshot-таблицам через ondelete='CASCADE')
    db.delete(rev)
    db.flush()

    # если у сценария approved и больше нет ревизий — переводим в draft
    remaining = db.query(ScenarioRevision).filter_by(scenario_id=scenario_id).count()
    if remaining == 0:
        scenario = db.get(PlanningScenario, scenario_id)
        if scenario and scenario.status == "approved":
            scenario.status = "draft"

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    return None
```

- [ ] **Step 4: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_delete.py -v`
Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_snapshot_delete.py
git commit -m "feat(planning): DELETE /scenarios/{sid}/revisions/{rid} with parent re-link"
```

---

### Task 14: Verify cascade for all v2 snapshot tables

**Files:**
- Modify: `tests/test_snapshot_delete.py`

- [ ] **Step 1: Add cascade-check test**

Append to `tests/test_snapshot_delete.py`:

```python
from app.models import (
    ScenarioTeamSnapshot, ScenarioCalendarSnapshot, ScenarioRulesSnapshot,
    ScenarioDictionarySnapshot, ScenarioAllocationSnapshot,
    ScenarioAllocationBreakdownSnapshot, ScenarioNormSnapshot,
    ScenarioAbsenceSnapshot, ScenarioRevisionItem,
)
from datetime import date as ddate


def test_delete_cascades_all_v2_snapshot_tables(client: TestClient, db: Session):
    sc = PlanningScenario(id="s-x", name="X", year=2026, quarter="Q2", team="T", status="approved")
    db.add(sc)
    rev = ScenarioRevision(id="r-x", scenario_id="s-x", revision_number=1, approved_at=datetime.utcnow())
    db.add(rev)
    db.add(ScenarioTeamSnapshot(revision_id="r-x", display_name="X"))
    db.add(ScenarioCalendarSnapshot(revision_id="r-x", date=ddate(2026, 4, 1), hours=8.0, is_workday=True, kind="workday"))
    db.add(ScenarioRulesSnapshot(revision_id="r-x", role="analyst", work_type_id="wt", work_type_label="L", pct_of_norm=10.0))
    db.add(ScenarioDictionarySnapshot(revision_id="r-x", kind="role", original_id="ro", label="Аналитик"))
    db.add(ScenarioAllocationSnapshot(revision_id="r-x", title="X"))
    db.add(ScenarioAllocationBreakdownSnapshot(revision_id="r-x", allocation_id="al", month=4, role="analyst", hours=10.0))
    db.add(ScenarioNormSnapshot(revision_id="r-x", employee_name="x", year=2026, month=4, work_type_label="L", norm_hours=10.0))
    db.add(ScenarioAbsenceSnapshot(revision_id="r-x", employee_name="x", start_date=ddate(2026, 4, 1), end_date=ddate(2026, 4, 5), hours_total=8.0))
    db.add(ScenarioRevisionItem(revision_id="r-x", backlog_item_id="bi", backlog_item_name="X", action="included"))
    db.commit()

    resp = client.delete("/api/v1/planning/scenarios/s-x/revisions/r-x")
    assert resp.status_code == 204

    for model in [
        ScenarioTeamSnapshot, ScenarioCalendarSnapshot, ScenarioRulesSnapshot,
        ScenarioDictionarySnapshot, ScenarioAllocationSnapshot,
        ScenarioAllocationBreakdownSnapshot, ScenarioNormSnapshot,
        ScenarioAbsenceSnapshot, ScenarioRevisionItem,
    ]:
        assert db.query(model).filter_by(revision_id="r-x").count() == 0, f"Cascade failed for {model.__name__}"
```

- [ ] **Step 2: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_delete.py::test_delete_cascades_all_v2_snapshot_tables -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snapshot_delete.py
git commit -m "test(planning): verify cascade for all v2 snapshot tables on DELETE"
```

---

## Phase 5 — Diff API

### Task 15: SnapshotDiffer — allocations + team + rules

**Files:**
- Create: `app/services/snapshot_differ.py`
- Create: `tests/test_snapshot_differ.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_snapshot_differ.py`:

```python
"""Тесты SnapshotDiffer: сравнение двух ревизий по срезам."""
from datetime import datetime
import pytest
from sqlalchemy.orm import Session
from app.models import (
    PlanningScenario, ScenarioRevision,
    ScenarioAllocationSnapshot, ScenarioTeamSnapshot, ScenarioRulesSnapshot,
)
from app.services.snapshot_differ import SnapshotDiffer


@pytest.fixture
def two_revs_with_snapshots(db: Session):
    sc = PlanningScenario(id="s-1", name="Q2", year=2026, quarter="Q2", team="T", status="approved")
    db.add(sc)
    rev1 = ScenarioRevision(id="r-1", scenario_id="s-1", revision_number=1, approved_at=datetime(2026, 4, 1), algo_version="v2")
    rev2 = ScenarioRevision(id="r-2", scenario_id="s-1", revision_number=2, approved_at=datetime(2026, 4, 15), parent_revision_id="r-1", algo_version="v2")
    db.add_all([rev1, rev2])

    # allocations
    db.add(ScenarioAllocationSnapshot(revision_id="r-1", allocation_id="a", title="A", estimate_analyst_hours=10.0))
    db.add(ScenarioAllocationSnapshot(revision_id="r-1", allocation_id="b", title="B", estimate_analyst_hours=20.0))
    db.add(ScenarioAllocationSnapshot(revision_id="r-2", allocation_id="a", title="A", estimate_analyst_hours=15.0))  # changed
    db.add(ScenarioAllocationSnapshot(revision_id="r-2", allocation_id="c", title="C", estimate_analyst_hours=5.0))   # added

    # team
    db.add(ScenarioTeamSnapshot(revision_id="r-1", employee_id="e-1", display_name="A", role="analyst"))
    db.add(ScenarioTeamSnapshot(revision_id="r-1", employee_id="e-2", display_name="B", role="dev"))
    db.add(ScenarioTeamSnapshot(revision_id="r-2", employee_id="e-1", display_name="A", role="consultant"))  # role_changed
    # e-2 removed, e-3 added
    db.add(ScenarioTeamSnapshot(revision_id="r-2", employee_id="e-3", display_name="C", role="dev"))

    # rules
    db.add(ScenarioRulesSnapshot(revision_id="r-1", role="analyst", work_type_id="wt-1", work_type_label="L1", pct_of_norm=30.0))
    db.add(ScenarioRulesSnapshot(revision_id="r-2", role="analyst", work_type_id="wt-1", work_type_label="L1", pct_of_norm=35.0))  # changed
    db.add(ScenarioRulesSnapshot(revision_id="r-2", role="dev", work_type_id="wt-2", work_type_label="L2", pct_of_norm=10.0))     # added
    db.commit()


def test_diff_allocations(db: Session, two_revs_with_snapshots):
    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="r-2", against_revision_id="r-1")

    alloc = diff["allocations"]
    assert sorted(a["allocation_id"] for a in alloc["added"]) == ["c"]
    assert sorted(a["allocation_id"] for a in alloc["removed"]) == ["b"]
    assert len(alloc["changed"]) == 1
    assert alloc["changed"][0]["allocation_id"] == "a"
    assert alloc["changed"][0]["estimate_analyst_hours"] == {"before": 10.0, "after": 15.0}


def test_diff_team(db: Session, two_revs_with_snapshots):
    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="r-2", against_revision_id="r-1")

    team = diff["team"]
    assert sorted(e["employee_id"] for e in team["added"]) == ["e-3"]
    assert sorted(e["employee_id"] for e in team["removed"]) == ["e-2"]
    assert len(team["role_changed"]) == 1
    assert team["role_changed"][0]["employee_id"] == "e-1"
    assert team["role_changed"][0]["role"] == {"before": "analyst", "after": "consultant"}


def test_diff_rules(db: Session, two_revs_with_snapshots):
    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="r-2", against_revision_id="r-1")

    rules = diff["rules"]
    assert len(rules["added"]) == 1
    assert rules["added"][0]["role"] == "dev"
    assert len(rules["changed"]) == 1
    assert rules["changed"][0]["pct_of_norm"] == {"before": 30.0, "after": 35.0}
```

- [ ] **Step 2: Run, expect fail**

Run: `py -3.10 -m pytest tests/test_snapshot_differ.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement differ**

Create `app/services/snapshot_differ.py`:

```python
"""SnapshotDiffer — diff между двумя ревизиями по snapshot-таблицам."""
from typing import Any
from sqlalchemy.orm import Session
from app.models import (
    ScenarioRevision, ScenarioAllocationSnapshot,
    ScenarioTeamSnapshot, ScenarioRulesSnapshot,
)


_ALLOC_COMPARE_FIELDS = (
    "estimate_analyst_hours", "estimate_dev_hours", "estimate_qa_hours",
    "estimate_opo_hours", "opo_analyst_ratio", "involvement_coefficient",
    "impact", "risk", "customer", "cost_type", "title",
    "assignee_employee_id", "assignee_role_at_approval", "priority",
)


class SnapshotDiffer:
    def __init__(self, db: Session):
        self.db = db

    def diff(self, *, revision_id: str, against_revision_id: str) -> dict[str, Any]:
        return {
            "allocations": self._diff_allocations(revision_id, against_revision_id),
            "team": self._diff_team(revision_id, against_revision_id),
            "rules": self._diff_rules(revision_id, against_revision_id),
        }

    def _diff_allocations(self, rid: str, against: str) -> dict[str, list[dict]]:
        cur = {a.allocation_id: a for a in self.db.query(ScenarioAllocationSnapshot).filter_by(revision_id=rid).all() if a.allocation_id}
        prev = {a.allocation_id: a for a in self.db.query(ScenarioAllocationSnapshot).filter_by(revision_id=against).all() if a.allocation_id}

        added = [self._alloc_to_dict(cur[k]) for k in cur if k not in prev]
        removed = [self._alloc_to_dict(prev[k]) for k in prev if k not in cur]
        changed = []
        for k in cur:
            if k not in prev:
                continue
            diff_fields: dict[str, dict] = {}
            for field in _ALLOC_COMPARE_FIELDS:
                a = getattr(cur[k], field)
                b = getattr(prev[k], field)
                if a != b:
                    diff_fields[field] = {"before": b, "after": a}
            if diff_fields:
                changed.append({"allocation_id": k, **diff_fields})
        return {"added": added, "removed": removed, "changed": changed}

    @staticmethod
    def _alloc_to_dict(a: ScenarioAllocationSnapshot) -> dict:
        return {
            "allocation_id": a.allocation_id,
            "backlog_item_id": a.backlog_item_id,
            "title": a.title,
            "estimate_analyst_hours": a.estimate_analyst_hours,
            "estimate_dev_hours": a.estimate_dev_hours,
            "estimate_qa_hours": a.estimate_qa_hours,
            "estimate_opo_hours": a.estimate_opo_hours,
        }

    def _diff_team(self, rid: str, against: str) -> dict[str, list[dict]]:
        cur = {t.employee_id: t for t in self.db.query(ScenarioTeamSnapshot).filter_by(revision_id=rid).all() if t.employee_id}
        prev = {t.employee_id: t for t in self.db.query(ScenarioTeamSnapshot).filter_by(revision_id=against).all() if t.employee_id}

        added = [{"employee_id": k, "display_name": cur[k].display_name, "role": cur[k].role} for k in cur if k not in prev]
        removed = [{"employee_id": k, "display_name": prev[k].display_name, "role": prev[k].role} for k in prev if k not in cur]
        role_changed = [
            {
                "employee_id": k,
                "display_name": cur[k].display_name,
                "role": {"before": prev[k].role, "after": cur[k].role},
            }
            for k in cur
            if k in prev and cur[k].role != prev[k].role
        ]
        return {"added": added, "removed": removed, "role_changed": role_changed}

    def _diff_rules(self, rid: str, against: str) -> dict[str, list[dict]]:
        def key(r: ScenarioRulesSnapshot) -> tuple:
            return (r.role, r.work_type_id)
        cur = {key(r): r for r in self.db.query(ScenarioRulesSnapshot).filter_by(revision_id=rid).all()}
        prev = {key(r): r for r in self.db.query(ScenarioRulesSnapshot).filter_by(revision_id=against).all()}

        added = [
            {"role": k[0], "work_type_id": k[1], "work_type_label": cur[k].work_type_label, "pct_of_norm": cur[k].pct_of_norm}
            for k in cur if k not in prev
        ]
        removed = [
            {"role": k[0], "work_type_id": k[1], "work_type_label": prev[k].work_type_label, "pct_of_norm": prev[k].pct_of_norm}
            for k in prev if k not in cur
        ]
        changed = [
            {
                "role": k[0], "work_type_id": k[1], "work_type_label": cur[k].work_type_label,
                "pct_of_norm": {"before": prev[k].pct_of_norm, "after": cur[k].pct_of_norm},
            }
            for k in cur
            if k in prev and cur[k].pct_of_norm != prev[k].pct_of_norm
        ]
        return {"added": added, "removed": removed, "changed": changed}
```

- [ ] **Step 4: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_differ.py -v`
Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/snapshot_differ.py tests/test_snapshot_differ.py
git commit -m "feat(snapshot): SnapshotDiffer for allocations/team/rules"
```

---

### Task 16: Diff for external_qa + capacity delta + GET endpoint

**Files:**
- Modify: `app/services/snapshot_differ.py`
- Modify: `app/api/endpoints/planning.py`
- Modify: `tests/test_snapshot_differ.py`

- [ ] **Step 1: Add tests for external_qa + capacity diff + endpoint**

Append to `tests/test_snapshot_differ.py`:

```python
from app.models import ScenarioCapacitySnapshot, PlanningScenario


def test_diff_external_qa(db: Session):
    sc = PlanningScenario(id="s-x", name="X", year=2026, quarter="Q2", team="T", status="approved", external_qa_hours=600.0)
    db.add(sc)
    rev1 = ScenarioRevision(id="r-1", scenario_id="s-x", revision_number=1, approved_at=datetime(2026, 4, 1))
    rev2 = ScenarioRevision(id="r-2", scenario_id="s-x", revision_number=2, approved_at=datetime(2026, 4, 15), parent_revision_id="r-1")
    db.add_all([rev1, rev2])
    # external_qa в snapshot — берём из allocation snapshots? нет, мы храним только в planning_scenario.
    # Но scenario.external_qa_hours живой. Решение: используем ScenarioRulesSnapshot is_external? Нет.
    # Вариант: добавим в diff просто чтение текущего scenario.external_qa_hours для обеих ревизий невозможно
    # (была единая запись). Для simplicity: diff external_qa = diff между sum norm_snapshots is_external=True.
    from app.models import ScenarioNormSnapshot
    # rev1: external 600 ч → 200/мес × 35% = 70/мес × 3 = 210
    db.add(ScenarioNormSnapshot(revision_id="r-1", is_external=True, role="qa", year=2026, month=4, work_type_label="L", norm_hours=70.0, employee_name="ext"))
    db.add(ScenarioNormSnapshot(revision_id="r-1", is_external=True, role="qa", year=2026, month=5, work_type_label="L", norm_hours=70.0, employee_name="ext"))
    db.add(ScenarioNormSnapshot(revision_id="r-1", is_external=True, role="qa", year=2026, month=6, work_type_label="L", norm_hours=70.0, employee_name="ext"))
    # rev2: external 900 → 300/мес × 35% = 105/мес × 3 = 315
    db.add(ScenarioNormSnapshot(revision_id="r-2", is_external=True, role="qa", year=2026, month=4, work_type_label="L", norm_hours=105.0, employee_name="ext"))
    db.add(ScenarioNormSnapshot(revision_id="r-2", is_external=True, role="qa", year=2026, month=5, work_type_label="L", norm_hours=105.0, employee_name="ext"))
    db.add(ScenarioNormSnapshot(revision_id="r-2", is_external=True, role="qa", year=2026, month=6, work_type_label="L", norm_hours=105.0, employee_name="ext"))
    db.commit()

    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="r-2", against_revision_id="r-1")
    assert diff["external_qa_total_hours"] == {"before": 210.0, "after": 315.0}


def test_diff_capacity_per_emp_month(db: Session):
    sc = PlanningScenario(id="s-y", name="Y", year=2026, quarter="Q2", team="T", status="approved")
    db.add(sc)
    rev1 = ScenarioRevision(id="r-a", scenario_id="s-y", revision_number=1, approved_at=datetime(2026, 4, 1))
    rev2 = ScenarioRevision(id="r-b", scenario_id="s-y", revision_number=2, approved_at=datetime(2026, 4, 15), parent_revision_id="r-a")
    db.add_all([rev1, rev2])
    db.add(ScenarioCapacitySnapshot(revision_id="r-a", employee_id="e", employee_name="x", year=2026, month=4, norm_hours=160, available_hours=160, gross_hours=160, absence_hours=0, snapshot_taken_at=datetime.utcnow()))
    db.add(ScenarioCapacitySnapshot(revision_id="r-b", employee_id="e", employee_name="x", year=2026, month=4, norm_hours=160, available_hours=120, gross_hours=160, absence_hours=40, snapshot_taken_at=datetime.utcnow()))  # 40 ч новых отсутствий
    db.commit()

    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="r-b", against_revision_id="r-a")
    cap = diff["capacity_changes"]
    assert len(cap) == 1
    assert cap[0]["employee_id"] == "e"
    assert cap[0]["month"] == 4
    assert cap[0]["available_hours"] == {"before": 160.0, "after": 120.0}


def test_diff_endpoint(client: TestClient, db: Session, two_revs_with_snapshots):
    resp = client.get("/api/v1/planning/scenarios/s-1/revisions/r-2/diff")
    assert resp.status_code == 200
    data = resp.json()
    assert "allocations" in data
    assert "team" in data
    assert "rules" in data
    # default against = parent_revision_id
    assert any(a["allocation_id"] == "c" for a in data["allocations"]["added"])


def test_diff_endpoint_explicit_against(client: TestClient, db: Session, two_revs_with_snapshots):
    resp = client.get("/api/v1/planning/scenarios/s-1/revisions/r-2/diff?against=r-1")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run, expect fail**

Run: `py -3.10 -m pytest tests/test_snapshot_differ.py -v`
Expected: 4 new tests FAIL.

- [ ] **Step 3: Extend SnapshotDiffer**

Append to `app/services/snapshot_differ.py`:

```python
from app.models import ScenarioNormSnapshot, ScenarioCapacitySnapshot


def _differ_diff_external_qa(self, rid: str, against: str) -> dict:  # type: ignore[no-untyped-def]
    def total(rev: str) -> float:
        rows = self.db.query(ScenarioNormSnapshot).filter_by(revision_id=rev, is_external=True).all()
        return round(sum(r.norm_hours for r in rows), 2)
    return {"before": total(against), "after": total(rid)}


def _differ_diff_capacity(self, rid: str, against: str) -> list[dict]:  # type: ignore[no-untyped-def]
    cur = {(r.employee_id, r.month): r for r in self.db.query(ScenarioCapacitySnapshot).filter_by(revision_id=rid).all() if r.employee_id}
    prev = {(r.employee_id, r.month): r for r in self.db.query(ScenarioCapacitySnapshot).filter_by(revision_id=against).all() if r.employee_id}
    out: list[dict] = []
    for k in cur:
        if k not in prev:
            continue
        if cur[k].available_hours != prev[k].available_hours:
            out.append({
                "employee_id": k[0],
                "month": k[1],
                "available_hours": {"before": float(prev[k].available_hours), "after": float(cur[k].available_hours)},
            })
    return out


SnapshotDiffer._diff_external_qa = _differ_diff_external_qa
SnapshotDiffer._diff_capacity = _differ_diff_capacity


# patch main diff method to include new sections
_orig_diff = SnapshotDiffer.diff


def _patched_diff(self, *, revision_id: str, against_revision_id: str):  # type: ignore[no-untyped-def]
    base = _orig_diff(self, revision_id=revision_id, against_revision_id=against_revision_id)
    base["external_qa_total_hours"] = self._diff_external_qa(revision_id, against_revision_id)
    base["capacity_changes"] = self._diff_capacity(revision_id, against_revision_id)
    return base


SnapshotDiffer.diff = _patched_diff
```

- [ ] **Step 4: Add diff endpoint to planning.py**

In `app/api/endpoints/planning.py`, add near revision endpoints:

```python
@router.get("/scenarios/{scenario_id}/revisions/{revision_id}/diff")
async def diff_revision(
    scenario_id: str,
    revision_id: str,
    against: Optional[str] = Query(None, description="ID ревизии для сравнения; по умолчанию parent_revision_id"),
    db: Session = Depends(get_db),
):
    """Diff между двумя ревизиями того же сценария."""
    rev = db.query(ScenarioRevision).filter_by(id=revision_id, scenario_id=scenario_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    against_id = against or rev.parent_revision_id
    if not against_id:
        return {"allocations": {"added": [], "removed": [], "changed": []},
                "team": {"added": [], "removed": [], "role_changed": []},
                "rules": {"added": [], "removed": [], "changed": []},
                "external_qa_total_hours": {"before": 0.0, "after": 0.0},
                "capacity_changes": []}
    against_rev = db.query(ScenarioRevision).filter_by(id=against_id, scenario_id=scenario_id).first()
    if not against_rev:
        raise HTTPException(status_code=404, detail="Against revision not found in same scenario")

    from app.services.snapshot_differ import SnapshotDiffer
    return SnapshotDiffer(db).diff(revision_id=revision_id, against_revision_id=against_id)
```

- [ ] **Step 5: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_differ.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/snapshot_differ.py app/api/endpoints/planning.py tests/test_snapshot_differ.py
git commit -m "feat(snapshot): diff external_qa + capacity changes + GET diff endpoint"
```

---

## Phase 6 — Breakdown debug API

### Task 17: GET breakdown endpoint

**Files:**
- Modify: `app/api/endpoints/planning.py`
- Create: `tests/test_snapshot_breakdown_endpoint.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_snapshot_breakdown_endpoint.py`:

```python
"""Тест GET /scenarios/{sid}/revisions/{rid}/breakdown — отладочный read-only вывод."""
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models import (
    PlanningScenario, ScenarioRevision, ScenarioAllocationBreakdownSnapshot,
)


def test_breakdown_endpoint_returns_rows(client: TestClient, db: Session):
    sc = PlanningScenario(id="s-1", name="X", year=2026, quarter="Q2", team="T", status="approved")
    db.add(sc)
    rev = ScenarioRevision(id="r-1", scenario_id="s-1", revision_number=1, approved_at=datetime.utcnow())
    db.add(rev)
    db.add(ScenarioAllocationBreakdownSnapshot(revision_id="r-1", allocation_id="al", month=4, role="analyst", employee_id="e", hours=10.0))
    db.add(ScenarioAllocationBreakdownSnapshot(revision_id="r-1", allocation_id="al", month=5, role="analyst", employee_id="e", hours=10.0))
    db.commit()

    resp = client.get("/api/v1/planning/scenarios/s-1/revisions/r-1/breakdown")
    assert resp.status_code == 200
    data = resp.json()
    assert "rows" in data
    assert len(data["rows"]) == 2
    assert all(r["allocation_id"] == "al" for r in data["rows"])
    assert sorted(r["month"] for r in data["rows"]) == [4, 5]


def test_breakdown_endpoint_404_unknown(client: TestClient):
    resp = client.get("/api/v1/planning/scenarios/nope/revisions/none/breakdown")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run, expect fail**

Run: `py -3.10 -m pytest tests/test_snapshot_breakdown_endpoint.py -v`
Expected: FAIL — endpoint missing.

- [ ] **Step 3: Add endpoint**

In `app/api/endpoints/planning.py`:

```python
from app.models import ScenarioAllocationBreakdownSnapshot


@router.get("/scenarios/{scenario_id}/revisions/{revision_id}/breakdown")
async def get_revision_breakdown(
    scenario_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
):
    """Read-only вывод scenario_allocation_breakdown_snapshots для отладки."""
    rev = db.query(ScenarioRevision).filter_by(id=revision_id, scenario_id=scenario_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    rows = (
        db.query(ScenarioAllocationBreakdownSnapshot)
        .filter_by(revision_id=revision_id)
        .order_by(
            ScenarioAllocationBreakdownSnapshot.allocation_id,
            ScenarioAllocationBreakdownSnapshot.month,
            ScenarioAllocationBreakdownSnapshot.role,
        )
        .all()
    )
    return {
        "revision_id": revision_id,
        "algo_version": rev.algo_version,
        "rows": [
            {
                "allocation_id": r.allocation_id,
                "month": r.month,
                "role": r.role,
                "employee_id": r.employee_id,
                "is_external": r.is_external,
                "hours": r.hours,
            }
            for r in rows
        ],
    }
```

- [ ] **Step 4: Run, expect pass**

Run: `py -3.10 -m pytest tests/test_snapshot_breakdown_endpoint.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_snapshot_breakdown_endpoint.py
git commit -m "feat(planning): GET /revisions/{rid}/breakdown debug endpoint"
```

---

## Phase 7 — v1 backlink + smoke

### Task 18: Script — link v1 revisions parent chain

**Files:**
- Create: `scripts/link_v1_revisions.py`

- [ ] **Step 1: Implement one-shot script**

Create `scripts/link_v1_revisions.py`:

```python
"""Одноразовый скрипт: проставить parent_revision_id для существующих v1-ревизий
по упорядочиванию revision_number внутри каждого сценария.

Запуск: py -3.10 scripts/link_v1_revisions.py [--dry-run]
"""
import sys
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import ScenarioRevision, PlanningScenario


def link(db: Session, dry_run: bool = False) -> dict:
    scenarios = db.query(PlanningScenario).all()
    updated = 0
    for sc in scenarios:
        revs = (
            db.query(ScenarioRevision)
            .filter_by(scenario_id=sc.id)
            .order_by(ScenarioRevision.revision_number.asc())
            .all()
        )
        prev_id = None
        for rev in revs:
            if rev.parent_revision_id != prev_id:
                if not dry_run:
                    rev.parent_revision_id = prev_id
                updated += 1
            prev_id = rev.id
    if not dry_run:
        db.commit()
    return {"updated": updated, "scenarios": len(scenarios)}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        result = link(db, dry_run=dry)
        print(f"{'DRY-RUN ' if dry else ''}linked: {result['updated']} ревизий в {result['scenarios']} сценариях")
    finally:
        db.close()
```

- [ ] **Step 2: Run dry-run**

Run: `py -3.10 scripts/link_v1_revisions.py --dry-run`
Expected: prints `DRY-RUN linked: N ревизий в M сценариях` (N>0 if any v1 revisions exist).

- [ ] **Step 3: Run actual**

Run: `py -3.10 scripts/link_v1_revisions.py`
Expected: same N reported, this time committed.

- [ ] **Step 4: Verify in DB**

Run: `py -3.10 -c "import sqlite3; db=sqlite3.connect('data/jira_analytics.db'); c=db.cursor(); c.execute('SELECT scenario_id, revision_number, parent_revision_id FROM scenario_revisions ORDER BY scenario_id, revision_number'); [print(r) for r in c.fetchall()[:10]]"`
Expected: output shows parent_revision_id populated for all rows except revision_number=1 of each scenario.

- [ ] **Step 5: Commit**

```bash
git add scripts/link_v1_revisions.py
git commit -m "chore(snapshot): one-shot script to link v1 revisions parent chain"
```

---

### Task 19: Full-cycle smoke + lint + docs

**Files:**
- Modify: `app/services/CLAUDE.md`

- [ ] **Step 1: Run full backend test suite**

Run: `py -3.10 -m pytest tests/ -v --tb=short`
Expected: All snapshot-related tests PASS. Pre-existing failures (test_sync_service drift, see memory `project_capacity_overhaul_followups`) acceptable.

- [ ] **Step 2: Run lint**

Run: `ruff check app/ tests/ scripts/`
Expected: No new errors.

- [ ] **Step 3: Run typecheck**

Run: `mypy app/`
Expected: No new errors. Existing baseline preserved.

- [ ] **Step 4: Update services CLAUDE.md**

Append to `app/services/CLAUDE.md` after `## SyncService` section:

```markdown
## SnapshotWriter ([snapshot_writer.py](snapshot_writer.py))

Заполняет все snapshot-таблицы при создании ревизии сценария (`POST /scenarios/{id}/approve`). Один экземпляр = один проход. Методы: `write_team_snapshot`, `write_calendar_snapshot`, `write_rules_snapshot`, `write_dictionary_snapshot`, `write_capacity_snapshot`, `write_norm_snapshot`, `write_allocation_snapshot`, `write_allocation_breakdown`. Все добавляют строки в сессию; commit делает вызывающий код. Ревизии, созданные через writer, помечаются `algo_version='v2'`. Старые v1-ревизии не пересчитываются.

Algo notes:
- `write_capacity_snapshot` считает `gross/absence/available/mandatory/project` per emp×month с учётом отсутствий и правил роли.
- `write_norm_snapshot` использует `available_hours × pct/100` (НЕ gross), внешний QA — отдельные строки `employee_id=NULL, is_external=TRUE` с равномерным split `external_qa_hours / 3`.
- `write_allocation_breakdown` — авто-сплит часов allocation по месяцам и ролям пропорционально `available_hours`. Для AN/Cons — на assignee; для RP — на единственного РП команды (alphabetical first если несколько); для dev/qa — пул роли (`employee_id=NULL`); для внешнего QA — равномерно. Edge cases: 0 РП, 0 dev, удалённый assignee → строка с `employee_id=NULL`.

## SnapshotDiffer ([snapshot_differ.py](snapshot_differ.py))

Diff между двумя ревизиями того же сценария. Срезы: allocations (added/removed/changed), team (added/removed/role_changed), rules (added/removed/changed), external_qa_total_hours (before/after), capacity_changes (per emp×month available_hours delta). Чистое чтение snapshot-таблиц.
```

- [ ] **Step 5: Run smoke approve+delete cycle**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py tests/test_snapshot_writer_breakdown.py tests/test_snapshot_writer_external_qa.py tests/test_snapshot_delete.py tests/test_snapshot_differ.py tests/test_snapshot_breakdown_endpoint.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit + push**

```bash
git add app/services/CLAUDE.md
git commit -m "docs(services): document SnapshotWriter and SnapshotDiffer"
git push origin main
```

---

## Self-review checklist

После прохождения всех задач — пробежать по спеке и убедиться:

- [ ] Spec §3.1 (расширение `scenario_revisions`) → Task 1 миграция + Task 2 модель ✓
- [ ] Spec §3.2 (`scenario_team_snapshots`) → Task 1 + Task 3 + Task 4 writer ✓
- [ ] Spec §3.3 (`scenario_calendar_snapshots`) → Task 1 + Task 3 + Task 5 writer ✓
- [ ] Spec §3.4 (`scenario_absence_snapshots`) → не менялась ✓
- [ ] Spec §3.5 (`scenario_rules_snapshots`) → Task 1 + Task 3 + Task 5 writer ✓
- [ ] Spec §3.6 (расширение `scenario_capacity_snapshots`) → Task 1 + Task 2 + Task 6 writer ✓
- [ ] Spec §3.7 (`norm_snapshot` исправление + `is_external`) → Task 1 + Task 2 + Task 7 writer ✓
- [ ] Spec §3.8 (`scenario_allocation_snapshots`) → Task 1 + Task 3 + Task 8 writer ✓
- [ ] Spec §3.9 (`scenario_allocation_breakdown_snapshots` + автосплит + edge cases) → Task 1 + Task 3 + Task 9 + Task 10 writer ✓
- [ ] Spec §3.10 (`scenario_dictionary_snapshots`) → Task 1 + Task 3 + Task 5 writer ✓
- [ ] Spec §4 (удаление ревизии: каскад + re-link parent + last → draft) → Task 13 + Task 14 ✓
- [ ] Spec §5 (diff API) → Task 15 + Task 16 ✓
- [ ] Spec §6 (algo при approve) → Task 11 ✓
- [ ] Spec §7 (миграция без backfill v1, link script) → Task 1 + Task 18 ✓
- [ ] Spec §8 (`/breakdown` debug endpoint) → Task 17 ✓
- [ ] Не виджеты (out of scope) ✓
- [ ] Не ресурсное планирование (out of scope) ✓
- [ ] Не restore (out of scope) ✓
