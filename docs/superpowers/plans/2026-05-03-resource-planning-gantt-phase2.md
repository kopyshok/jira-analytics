# Resource Planning Gantt — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 2 adds CPM slack computation, enhanced conflict detection, manual assignment override, View C (resource-track by employee), intra-initiative dependency arrows fix (rowRefs), inter-initiative relay arrows, and the plan_item_dependencies table foundation.

**Architecture:** Backend adds `plan_item_dependencies` table, `_compute_cpm()` in `ResourcePlanningService`, SPLIT_REQUIRED/NO_ANALYST/NO_DEV conflict detection, and a PATCH endpoint for manual assignment overrides. Frontend fixes the broken rowRefs registration in GanttRows, adds ResourceTrackRows (View C), extends DependencyArrows with relay arrows, and updates ResourcePlanningPage with the new view option and relay toggle.

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / Alembic batch-mode / React 19 / TypeScript / Ant Design 6 / TanStack Query

**Phase 1 is complete** — all models, migrations, service, API, and frontend exist. Phase 2 builds on top without breaking anything.

---

## Codebase Context

**Critical facts for all subagents:**
- `Employee.role` = `String(50)` role code (e.g., `"аналитик"`), NOT a FK to roles table
- `ScenarioAllocation.included_flag` (not `included`)
- Auth import: `from app.core.auth_deps import get_current_user`
- `Role` model has `.label` and `.code` fields (not `.name`)
- AntD 6: `PageHeader` uses `actions` prop; `notification` uses `title` not `message`
- All Alembic migrations must use `with op.batch_alter_table(...)` for any ALTER TABLE (SQLite batch mode)
- Run tests: `py -3.10 -m pytest tests/ -v`
- Run linter: `ruff check app/ tests/` then `ruff format app/ tests/`
- Backend server must be restarted after edits (Windows `--reload` is unreliable): kill PID on :8000 + start fresh
- Frontend build: `npm run build` in `frontend/`

**Existing Phase 1 files:**
- `app/models/scheduled_block.py` — ScheduledBlock model
- `app/models/resource_plan.py` — ResourcePlan (status: draft|computing|ready|stale)
- `app/models/resource_plan_assignment.py` — ResourcePlanAssignment (phase: analyst|dev|qa|opo, part_number 1..N)
- `app/services/resource_planning_service.py` — ResourcePlanningService with PHASE_ORDER, build_availability, compute_schedule, _allocate_hours, _assign_employees
- `app/api/endpoints/resource_planning.py` — 10 endpoints, schemas: ScheduledBlockOut, ResourcePlanOut, AssignmentOut, ConflictOut, GanttProjection
- `frontend/src/api/resourcePlanning.ts` — API client
- `frontend/src/hooks/useResourcePlanning.ts` — 9 TanStack Query hooks
- `frontend/src/utils/gantt.ts` — GanttTimeline, dateToLeft, datesToWidth, quarterBounds, getWeekLabels, PHASE_COLORS, PHASE_LABELS
- `frontend/src/components/resource-planning/GanttRows.tsx` — PortfolioRows + TwoLevelRows; ViewMode = 'portfolio' | 'two-level' | 'resource-track' (last one unimplemented)
- `frontend/src/components/resource-planning/DependencyArrows.tsx` — SVG bezier arrows between phases; rowRefs never populated (bug)
- `frontend/src/components/resource-planning/GanttChart.tsx` — container with rowRefs ref, passes it to DependencyArrows but NOT to GanttRows (bug)
- `frontend/src/pages/ResourcePlanningPage.tsx` — Segmented control with 'portfolio' and 'two-level' only (missing 'resource-track')

**rowRefs bug detail:** `GanttChart` creates `rowRefs = useRef<Map<string, HTMLElement>>(new Map())` and passes it to `DependencyArrows`. `DependencyArrows` tries to look up `rowRefs.current.get(`${backlog_item_id}-${phase}-${part_number}`)`, but no component ever calls `rowRefs.current.set(...)`. Fix: GanttRows must receive rowRefs and register each bar element.

---

## File Map

**Backend — new files:**
- `app/models/plan_item_dependency.py` — PlanItemDependency model
- `alembic/versions/*_add_plan_item_dependencies.py` — migration

**Backend — modified files:**
- `app/models/resource_plan.py` — add `dependencies` relationship
- `app/models/__init__.py` — add PlanItemDependency import
- `app/services/resource_planning_service.py` — add `_compute_cpm()`, call it in `compute_schedule()`, add helper `_get_team_role_gaps()`
- `app/api/endpoints/resource_planning.py` — enhance `_detect_conflicts()` (SPLIT_REQUIRED, NO_ANALYST, NO_DEV), add `AssignmentPatch` schema, add PATCH endpoint
- `tests/test_resource_planning_service.py` — new tests for CPM and conflicts

**Frontend — modified files:**
- `frontend/src/utils/gantt.ts` — add `ITEM_PALETTE`, `getItemColor()`
- `frontend/src/api/resourcePlanning.ts` — add `AssignmentPatch` interface + `patchAssignment()`
- `frontend/src/hooks/useResourcePlanning.ts` — add `usePatchAssignment()`
- `frontend/src/components/resource-planning/GanttRows.tsx` — add `rowRefs` prop, register bars in TwoLevelRows, implement ResourceTrackRows
- `frontend/src/components/resource-planning/DependencyArrows.tsx` — add `showRelayArrows` prop, draw relay arrows
- `frontend/src/components/resource-planning/GanttChart.tsx` — pass `rowRefs` to GanttRows, add `showRelayArrows` prop
- `frontend/src/pages/ResourcePlanningPage.tsx` — add 'Ресурсы' Segmented option, relay arrows toggle

---

## Task 1: plan_item_dependencies migration

**Files:**
- Create: `alembic/versions/*_add_plan_item_dependencies.py`

- [ ] **Step 1: Generate migration**

```bash
cd d:/ClaudeDev/JiraAnalysis
alembic revision --autogenerate -m "add_plan_item_dependencies"
```

- [ ] **Step 2: Replace the generated file body**

Open the generated file (the new file in `alembic/versions/` with `add_plan_item_dependencies` in name). Replace `upgrade()` and `downgrade()` with:

```python
def upgrade() -> None:
    op.create_table(
        "plan_item_dependencies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_item_id", sa.String(36), sa.ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_item_id", sa.String(36), sa.ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dep_type", sa.String(4), nullable=False, server_default="FS"),
        sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_item_dependencies_plan_id", "plan_item_dependencies", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_item_dependencies_plan_id", table_name="plan_item_dependencies")
    op.drop_table("plan_item_dependencies")
```

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```

Expected: Migration runs without error. Table `plan_item_dependencies` created.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat(resource-planning): add plan_item_dependencies migration"
```

---

## Task 2: PlanItemDependency model + ResourcePlan update

**Files:**
- Create: `app/models/plan_item_dependency.py`
- Modify: `app/models/resource_plan.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Create the model**

Create `app/models/plan_item_dependency.py`:

```python
"""PlanItemDependency — зависимости между инициативами в плане ресурсного планирования."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.resource_plan import ResourcePlan
    from app.models.backlog_item import BacklogItem


class PlanItemDependency(Base, TimestampMixin):
    """Зависимость FS/SS/FF/SF между двумя инициативами в рамках плана.

    dep_type: FS | SS | FF | SF
    source: manual | inferred
    """

    __tablename__ = "plan_item_dependencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_plans.id", ondelete="CASCADE"), index=True
    )
    from_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="CASCADE")
    )
    to_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="CASCADE")
    )
    dep_type: Mapped[str] = mapped_column(String(4), default="FS")
    lag_days: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="manual")

    plan: Mapped["ResourcePlan"] = relationship(back_populates="dependencies")
    from_item: Mapped["BacklogItem"] = relationship(foreign_keys=[from_item_id])
    to_item: Mapped["BacklogItem"] = relationship(foreign_keys=[to_item_id])
```

- [ ] **Step 2: Add `dependencies` relationship to ResourcePlan**

Edit `app/models/resource_plan.py`. In the TYPE_CHECKING block, add:

```python
    from app.models.plan_item_dependency import PlanItemDependency
```

Add the relationship at the bottom of the class (after `assignments`):

```python
    dependencies: Mapped[List["PlanItemDependency"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
```

Full updated file `app/models/resource_plan.py`:

```python
"""ResourcePlan — план расписания для квартала/команды."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.plan_item_dependency import PlanItemDependency


class ResourcePlan(Base, TimestampMixin):
    """Ресурсный план квартала.

    status: draft | computing | ready | stale
    """

    __tablename__ = "resource_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("planning_scenarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quarter: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    scenario: Mapped[Optional["PlanningScenario"]] = relationship("PlanningScenario")
    assignments: Mapped[List["ResourcePlanAssignment"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    dependencies: Mapped[List["PlanItemDependency"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
```

- [ ] **Step 3: Update `app/models/__init__.py`**

After the `ResourcePlanAssignment` import line, add:

```python
from app.models.plan_item_dependency import PlanItemDependency
```

In `__all__`, after `"ResourcePlanAssignment"`, add:

```python
    "PlanItemDependency",
```

- [ ] **Step 4: Verify imports work**

```bash
py -3.10 -c "from app.models import PlanItemDependency; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Run tests to confirm no regressions**

```bash
py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: Same pass count as before (618 passed, 2 failed pre-existing).

- [ ] **Step 6: Commit**

```bash
git add app/models/plan_item_dependency.py app/models/resource_plan.py app/models/__init__.py
git commit -m "feat(resource-planning): PlanItemDependency model + ResourcePlan.dependencies"
```

---

## Task 3: CPM algorithm in ResourcePlanningService

**Files:**
- Modify: `app/services/resource_planning_service.py`

**Context:** `compute_schedule()` allocates hours day-by-day and persists `ResourcePlanAssignment` rows. After building `new_assignments` and before `db.commit()`, call `_compute_cpm()`. In a sequential phase chain (analyst→dev→qa→opo), total float for every phase of an initiative equals `(q_end − opo_end_date).days`. Initiatives with slack ≤ 0 are critical.

- [ ] **Step 1: Add `_compute_cpm()` to the service**

At the end of `app/services/resource_planning_service.py`, add:

```python
    def _compute_cpm(
        self,
        plan: "ResourcePlan",
        assignments: List["ResourcePlanAssignment"],
    ) -> None:
        """Вычислить slack_days и is_on_critical_path для всех назначений.

        В последовательной цепи фаз (analyst→dev→qa→opo) каждая фаза
        инициативы имеет одинаковый total float = q_end - last_phase_end.
        """
        _, q_end = self._quarter_bounds(plan)

        by_item: Dict[str, List["ResourcePlanAssignment"]] = defaultdict(list)
        for a in assignments:
            by_item[a.backlog_item_id].append(a)

        for item_assignments in by_item.values():
            opo = [a for a in item_assignments if a.phase == "opo" and a.end_date]
            all_dated = [a for a in item_assignments if a.end_date]
            if not all_dated:
                continue
            last_end = max(a.end_date for a in (opo if opo else all_dated))
            slack = (q_end - last_end).days
            for a in item_assignments:
                a.slack_days = float(slack)
                a.is_on_critical_path = slack <= 0
```

- [ ] **Step 2: Call `_compute_cpm()` in `compute_schedule()` before commit**

In `compute_schedule()`, find this block near the end:

```python
        for a in new_assignments:
            self.db.add(a)

        plan.status = "ready"
        plan.computed_at = datetime.utcnow()
        self.db.commit()
```

Replace with:

```python
        for a in new_assignments:
            self.db.add(a)

        self._compute_cpm(plan, new_assignments)

        plan.status = "ready"
        plan.computed_at = datetime.utcnow()
        self.db.commit()
```

- [ ] **Step 3: Verify lint**

```bash
ruff check app/services/resource_planning_service.py
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add app/services/resource_planning_service.py
git commit -m "feat(resource-planning): _compute_cpm — phase-level slack + critical path"
```

---

## Task 4: Enhanced conflict detection + manual override endpoint

**Files:**
- Modify: `app/api/endpoints/resource_planning.py`

**Context — current `_detect_conflicts()`:**
```python
def _detect_conflicts(plan, assignments, db):
    conflicts = []
    svc = ResourcePlanningService(db)
    q_start, q_end = svc._quarter_bounds(plan)
    for a in assignments:
        if a.phase == "opo" and a.end_date and a.end_date > q_end:
            conflicts.append(ConflictOut(
                type="QUARTER_OVERFLOW", severity="critical",
                backlog_item_id=a.backlog_item_id,
                backlog_item_title=a.backlog_item.title if a.backlog_item else "",
                employee_id=None,
                message=f"Инициатива не вмещается в квартал: ОПЭ заканчивается {a.end_date}",
            ))
    return conflicts
```

New conflicts to add:
- **SPLIT_REQUIRED** (info): any phase split into parts (part_number > 1 exists for the phase)
- **NO_ANALYST** (critical): team has no employee with analyst role
- **NO_DEV** (critical): team has no employee with dev role

Also add a PATCH endpoint for manual assignment date/employee overrides.

- [ ] **Step 1: Replace `_detect_conflicts()` with enhanced version**

Replace the existing `_detect_conflicts` function at the bottom of `app/api/endpoints/resource_planning.py`:

```python
def _detect_conflicts(plan, assignments, db):
    from collections import defaultdict
    conflicts = []
    svc = ResourcePlanningService(db)
    _, q_end = svc._quarter_bounds(plan)

    # QUARTER_OVERFLOW
    for a in assignments:
        if a.phase == "opo" and a.end_date and a.end_date > q_end:
            conflicts.append(ConflictOut(
                type="QUARTER_OVERFLOW",
                severity="critical",
                backlog_item_id=a.backlog_item_id,
                backlog_item_title=a.backlog_item.title if a.backlog_item else "",
                employee_id=None,
                message=f"Инициатива не вмещается в квартал: ОПЭ заканчивается {a.end_date}",
            ))

    # SPLIT_REQUIRED: any phase with max(part_number) > 1
    phase_max_part: dict = defaultdict(int)
    item_titles: dict = {}
    for a in assignments:
        key = (a.backlog_item_id, a.phase)
        phase_max_part[key] = max(phase_max_part[key], a.part_number)
        if a.backlog_item:
            item_titles[a.backlog_item_id] = a.backlog_item.title
    split_items: set = set()
    for (item_id, _), max_part in phase_max_part.items():
        if max_part > 1 and item_id not in split_items:
            split_items.add(item_id)
            conflicts.append(ConflictOut(
                type="SPLIT_REQUIRED",
                severity="info",
                backlog_item_id=item_id,
                backlog_item_title=item_titles.get(item_id, ""),
                employee_id=None,
                message="Инициатива разбита на части из-за заблокированного периода",
            ))

    # NO_ANALYST / NO_DEV
    analyst_codes = {"аналитик", "analyst", "an"}
    dev_codes = {"разработчик", "developer", "dev", "rp"}
    employees = svc._load_employees(plan)
    has_analyst = any(e.role and e.role.lower() in analyst_codes for e in employees)
    has_dev = any(e.role and e.role.lower() in dev_codes for e in employees)
    if not has_analyst:
        conflicts.append(ConflictOut(
            type="NO_ANALYST",
            severity="critical",
            backlog_item_id=None,
            backlog_item_title=None,
            employee_id=None,
            message=f"В команде «{plan.team}» нет аналитиков. Расписание аналитической фазы невозможно.",
        ))
    if not has_dev:
        conflicts.append(ConflictOut(
            type="NO_DEV",
            severity="critical",
            backlog_item_id=None,
            backlog_item_title=None,
            employee_id=None,
            message=f"В команде «{plan.team}» нет разработчиков. Расписание фазы разработки невозможно.",
        ))

    return conflicts
```

- [ ] **Step 2: Add `AssignmentPatch` schema**

After the `GanttProjection` class definition, add:

```python
class AssignmentPatch(BaseModel):
    employee_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hours_allocated: Optional[float] = None
```

- [ ] **Step 3: Add PATCH endpoint**

After the `get_gantt` endpoint, add:

```python
@router.patch(
    "/resource-plans/{plan_id}/assignments/{assignment_id}",
    response_model=AssignmentOut,
)
def patch_assignment(
    plan_id: str,
    assignment_id: str,
    data: AssignmentPatch,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    a = db.execute(
        select(ResourcePlanAssignment)
        .options(joinedload(ResourcePlanAssignment.backlog_item))
        .options(joinedload(ResourcePlanAssignment.employee))
        .where(
            ResourcePlanAssignment.id == assignment_id,
            ResourcePlanAssignment.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Assignment not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)

    plan = db.get(ResourcePlan, plan_id)
    if plan:
        plan.status = "stale"

    # Snapshot values before commit (SQLite session expire caveat)
    a_id = a.id
    a_backlog_item_id = a.backlog_item_id
    a_backlog_item_title = a.backlog_item.title if a.backlog_item else ""
    a_phase = a.phase
    a_part_number = a.part_number
    a_hours_allocated = a.hours_allocated
    a_start_date = a.start_date
    a_end_date = a.end_date
    a_is_on_critical_path = a.is_on_critical_path
    a_slack_days = a.slack_days
    a_employee_id = a.employee_id

    db.commit()
    db.refresh(a)

    # Re-load employee name after commit
    emp_name = a.employee.display_name if a.employee else None

    return AssignmentOut(
        id=a_id,
        backlog_item_id=a_backlog_item_id,
        backlog_item_title=a_backlog_item_title,
        phase=a_phase,
        employee_id=a_employee_id,
        employee_name=emp_name,
        part_number=a_part_number,
        hours_allocated=a_hours_allocated,
        start_date=a_start_date,
        end_date=a_end_date,
        is_on_critical_path=a_is_on_critical_path,
        slack_days=a_slack_days,
    )
```

- [ ] **Step 4: Verify lint**

```bash
ruff check app/api/endpoints/resource_planning.py
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py
git commit -m "feat(resource-planning): SPLIT_REQUIRED/NO_ANALYST/NO_DEV conflicts + PATCH assignment"
```

---

## Task 5: Backend tests for CPM and conflicts

**Files:**
- Modify: `tests/test_resource_planning_service.py`

**Context:** Existing tests in this file use `unittest.mock.MagicMock` (not pytest-mock). Existing tests: test_phase_order, test_phase_hours_field, test_block_targets_employee, test_block_targets_role, test_allocate_hours_simple, test_allocate_hours_split.

- [ ] **Step 1: Add tests to `tests/test_resource_planning_service.py`**

Append these tests to the existing file:

```python
# ── CPM tests ──────────────────────────────────────────────────────────────


def test_compute_cpm_critical_path():
    """Initiative with opo ending ON quarter end → slack=0, critical=True."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    plan = MagicMock()
    plan.quarter = "Q1"
    plan.year = 2026

    # Q1 2026: Jan 1 – Mar 31
    a_opo = MagicMock()
    a_opo.backlog_item_id = "item1"
    a_opo.phase = "opo"
    a_opo.end_date = date(2026, 3, 31)

    a_analyst = MagicMock()
    a_analyst.backlog_item_id = "item1"
    a_analyst.phase = "analyst"
    a_analyst.end_date = date(2026, 1, 20)

    svc._compute_cpm(plan, [a_opo, a_analyst])

    assert a_opo.slack_days == 0.0
    assert a_opo.is_on_critical_path is True
    assert a_analyst.slack_days == 0.0
    assert a_analyst.is_on_critical_path is True


def test_compute_cpm_slack():
    """Initiative ending 11 days before quarter end → slack=11, not critical."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    plan = MagicMock()
    plan.quarter = "Q1"
    plan.year = 2026

    a_opo = MagicMock()
    a_opo.backlog_item_id = "item2"
    a_opo.phase = "opo"
    a_opo.end_date = date(2026, 3, 20)  # 11 days before Mar 31

    svc._compute_cpm(plan, [a_opo])

    assert a_opo.slack_days == 11.0
    assert a_opo.is_on_critical_path is False


def test_compute_cpm_no_opo_uses_last_phase():
    """Initiative with no opo phase uses latest end_date among other phases."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    plan = MagicMock()
    plan.quarter = "Q2"
    plan.year = 2026

    # Q2 2026: Apr 1 – Jun 30
    a_dev = MagicMock()
    a_dev.backlog_item_id = "item3"
    a_dev.phase = "dev"
    a_dev.end_date = date(2026, 6, 15)

    a_analyst = MagicMock()
    a_analyst.backlog_item_id = "item3"
    a_analyst.phase = "analyst"
    a_analyst.end_date = date(2026, 5, 10)

    svc._compute_cpm(plan, [a_dev, a_analyst])

    expected_slack = (date(2026, 6, 30) - date(2026, 6, 15)).days  # 15
    assert a_dev.slack_days == float(expected_slack)
    assert a_analyst.slack_days == float(expected_slack)
    assert a_dev.is_on_critical_path is False


def test_compute_cpm_overflow_negative_slack():
    """Initiative overflowing quarter has negative slack → critical."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    plan = MagicMock()
    plan.quarter = "Q1"
    plan.year = 2026

    a_opo = MagicMock()
    a_opo.backlog_item_id = "item4"
    a_opo.phase = "opo"
    a_opo.end_date = date(2026, 4, 5)  # 5 days past Q1

    svc._compute_cpm(plan, [a_opo])

    assert a_opo.slack_days == -5.0
    assert a_opo.is_on_critical_path is True


def test_compute_cpm_no_end_dates_skipped():
    """Assignments without end_date are silently skipped."""
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    plan = MagicMock()
    plan.quarter = "Q1"
    plan.year = 2026

    a = MagicMock()
    a.backlog_item_id = "item5"
    a.phase = "analyst"
    a.end_date = None

    # Should not raise
    svc._compute_cpm(plan, [a])
    # slack_days not set (no all_dated items → skip)
```

- [ ] **Step 2: Run the new tests**

```bash
py -3.10 -m pytest tests/test_resource_planning_service.py -v
```

Expected: All tests pass (6 old + 5 new = 11 total).

- [ ] **Step 3: Run full test suite**

```bash
py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: Same pre-existing pass count, 0 new failures.

- [ ] **Step 4: Commit**

```bash
git add tests/test_resource_planning_service.py
git commit -m "test(resource-planning): CPM algorithm tests"
```

---

## Task 6: Frontend API + hook for patchAssignment

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts`
- Modify: `frontend/src/hooks/useResourcePlanning.ts`

- [ ] **Step 1: Add `AssignmentPatch` interface and `patchAssignment()` to `frontend/src/api/resourcePlanning.ts`**

After the `GanttProjection` interface, add:

```typescript
export interface AssignmentPatch {
  employee_id?: string | null;
  start_date?: string;
  end_date?: string;
  hours_allocated?: number;
}
```

After the `getGanttProjection` function, add:

```typescript
export async function patchAssignment(
  planId: string,
  assignmentId: string,
  data: AssignmentPatch,
): Promise<AssignmentOut> {
  return api.patch<AssignmentOut>(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}`,
    data,
  );
}
```

- [ ] **Step 2: Add `usePatchAssignment()` to `frontend/src/hooks/useResourcePlanning.ts`**

Add the import for `patchAssignment` to the existing import line (add `, patchAssignment, type AssignmentPatch` to the named imports from `'../api/resourcePlanning'`).

Append to the file:

```typescript
export function usePatchAssignment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      planId,
      assignmentId,
      data,
    }: {
      planId: string;
      assignmentId: string;
      data: AssignmentPatch;
    }) => patchAssignment(planId, assignmentId, data),
    onSuccess: (_, { planId }) => {
      qc.invalidateQueries({ queryKey: ['gantt', planId] });
      qc.invalidateQueries({ queryKey: ['resource-plans'] });
    },
  });
}
```

- [ ] **Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/hooks/useResourcePlanning.ts
git commit -m "feat(resource-planning): patchAssignment API + usePatchAssignment hook"
```

---

## Task 7: Fix rowRefs — register bars in GanttRows + pass from GanttChart

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx`
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx`

**Context:** `DependencyArrows` reads `rowRefs.current.get(`${backlog_item_id}-${phase}-${part_number}`)` to get bar DOM elements for arrow positioning. Currently no component registers bars. Fix: add `rowRefs` prop to `GanttRows` and register each bar element in `TwoLevelRows`.

- [ ] **Step 1: Add `rowRefs` to GanttRows Props and register bars**

Replace the full content of `frontend/src/components/resource-planning/GanttRows.tsx`:

```tsx
import { useMemo } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';
import type { GanttTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth, PHASE_COLORS, PHASE_LABELS, getItemColor } from '../../utils/gantt';

export type ViewMode = 'portfolio' | 'two-level' | 'resource-track';

interface Props {
  assignments: AssignmentOut[];
  timeline: GanttTimeline;
  viewMode: ViewMode;
  leftColWidth: number;
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
}

const ROW_HEIGHT = 36;

function PortfolioRows({ assignments, timeline, leftColWidth }: Omit<Props, 'viewMode'>) {
  const byItem = useMemo(() => {
    const map = new Map<string, { title: string; assignments: AssignmentOut[] }>();
    for (const a of assignments) {
      if (!map.has(a.backlog_item_id)) {
        map.set(a.backlog_item_id, { title: a.backlog_item_title, assignments: [] });
      }
      map.get(a.backlog_item_id)!.assignments.push(a);
    }
    return [...map.entries()];
  }, [assignments]);

  return (
    <>
      {byItem.map(([itemId, { title, assignments: itemAssignments }], idx) => (
        <div
          key={itemId}
          style={{
            display: 'flex',
            height: ROW_HEIGHT,
            borderBottom: '1px solid #0e2540',
            background: idx % 2 === 0 ? 'rgba(0,201,200,0.03)' : 'transparent',
          }}
        >
          <div style={{
            width: leftColWidth,
            flexShrink: 0,
            borderRight: '1px solid #1e3a5f',
            padding: '0 12px',
            display: 'flex',
            alignItems: 'center',
            fontSize: 13,
            fontWeight: 600,
            color: '#fff',
            overflow: 'hidden',
            whiteSpace: 'nowrap',
            textOverflow: 'ellipsis',
          }}>
            {title}
          </div>
          <div style={{ flex: 1, position: 'relative' }}>
            {itemAssignments.filter(a => a.start_date && a.end_date).map(a => {
              const left = dateToLeft(a.start_date!, timeline);
              const width = datesToWidth(a.start_date!, a.end_date!, timeline);
              const color = PHASE_COLORS[a.phase] ?? '#888';
              return (
                <div
                  key={a.id}
                  title={`${PHASE_LABELS[a.phase]} — ${a.employee_name ?? '—'} (${a.hours_allocated?.toFixed(0)}ч)`}
                  style={{
                    position: 'absolute',
                    left: `${left}%`,
                    width: `${width}%`,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    height: 22,
                    background: color,
                    opacity: 0.85,
                    borderRadius: 3,
                    zIndex: 2,
                    display: 'flex',
                    alignItems: 'center',
                    paddingLeft: 4,
                    fontSize: 9,
                    color: '#0d1c33',
                    fontWeight: 700,
                    overflow: 'hidden',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {PHASE_LABELS[a.phase]}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </>
  );
}

function TwoLevelRows({ assignments, timeline, leftColWidth, rowRefs }: Omit<Props, 'viewMode'>) {
  const byItem = useMemo(() => {
    const map = new Map<string, { title: string; assignments: AssignmentOut[] }>();
    for (const a of assignments) {
      if (!map.has(a.backlog_item_id)) {
        map.set(a.backlog_item_id, { title: a.backlog_item_title, assignments: [] });
      }
      map.get(a.backlog_item_id)!.assignments.push(a);
    }
    return [...map.entries()];
  }, [assignments]);

  return (
    <>
      {byItem.map(([itemId, { title, assignments: ia }]) => {
        const phases = ['analyst', 'dev', 'qa', 'opo'] as const;
        return (
          <div key={itemId}>
            <div style={{
              display: 'flex',
              height: ROW_HEIGHT,
              borderBottom: '1px solid #1e3a5f',
              background: 'rgba(0,201,200,0.05)',
            }}>
              <div style={{
                width: leftColWidth,
                flexShrink: 0,
                borderRight: '1px solid #1e3a5f',
                padding: '0 12px',
                display: 'flex',
                alignItems: 'center',
                fontSize: 13,
                fontWeight: 700,
                color: '#fff',
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis',
              }}>
                {title}
              </div>
              <div style={{ flex: 1, position: 'relative' }}>
                {(() => {
                  const starts = ia.filter(a => a.start_date).map(a => a.start_date!).sort();
                  const ends = ia.filter(a => a.end_date).map(a => a.end_date!).sort();
                  if (!starts[0] || !ends.at(-1)) return null;
                  const left = dateToLeft(starts[0], timeline);
                  const width = datesToWidth(starts[0], ends.at(-1)!, timeline);
                  return (
                    <div style={{
                      position: 'absolute',
                      left: `${left}%`,
                      width: `${width}%`,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      height: 24,
                      background: 'rgba(0,201,200,0.15)',
                      border: '1px solid rgba(0,201,200,0.4)',
                      borderRadius: 4,
                      zIndex: 2,
                    }} />
                  );
                })()}
              </div>
            </div>
            {phases.map(phase => {
              const phaseAssignments = ia.filter(a => a.phase === phase);
              if (phaseAssignments.length === 0) return null;
              const color = PHASE_COLORS[phase];
              const empName = phaseAssignments[0].employee_name ?? '—';
              return (
                <div
                  key={phase}
                  style={{
                    display: 'flex',
                    height: ROW_HEIGHT - 4,
                    borderBottom: '1px solid #0e2540',
                  }}
                >
                  <div style={{
                    width: leftColWidth,
                    flexShrink: 0,
                    borderRight: '1px solid #1e3a5f',
                    padding: '0 12px 0 32px',
                    display: 'flex',
                    alignItems: 'center',
                    fontSize: 12,
                    color: '#8ab0d8',
                    gap: 6,
                  }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }} />
                    {PHASE_LABELS[phase]}
                    <span style={{ fontSize: 10, color: '#4a6a90', marginLeft: 'auto', paddingRight: 4 }}>
                      {empName}
                    </span>
                  </div>
                  <div style={{ flex: 1, position: 'relative' }}>
                    {phaseAssignments.filter(a => a.start_date && a.end_date).map(a => {
                      const left = dateToLeft(a.start_date!, timeline);
                      const width = datesToWidth(a.start_date!, a.end_date!, timeline);
                      const refKey = `${a.backlog_item_id}-${a.phase}-${a.part_number}`;
                      return (
                        <div
                          key={a.id}
                          ref={el => {
                            if (el) rowRefs.current.set(refKey, el);
                            else rowRefs.current.delete(refKey);
                          }}
                          title={`${PHASE_LABELS[a.phase]}, ч. ${a.part_number} — ${a.hours_allocated?.toFixed(0)}ч`}
                          style={{
                            position: 'absolute',
                            left: `${left}%`,
                            width: `${Math.max(width, 0.8)}%`,
                            top: '50%',
                            transform: 'translateY(-50%)',
                            height: 18,
                            background: color,
                            opacity: a.is_on_critical_path ? 1 : 0.75,
                            borderRadius: 3,
                            border: a.is_on_critical_path ? '1px solid #e85d4a' : 'none',
                            boxShadow: a.is_on_critical_path ? '0 0 6px rgba(232,93,74,0.5)' : 'none',
                            zIndex: 2,
                          }}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}

function ResourceTrackRows({ assignments, timeline, leftColWidth, rowRefs }: Omit<Props, 'viewMode'>) {
  const itemOrder = useMemo(
    () => [...new Set(assignments.map(a => a.backlog_item_id))],
    [assignments],
  );

  const byEmployee = useMemo(() => {
    const map = new Map<string, { name: string; assignments: AssignmentOut[] }>();
    for (const a of assignments) {
      const empId = a.employee_id ?? '__unassigned__';
      if (!map.has(empId)) {
        map.set(empId, { name: a.employee_name ?? 'Без исполнителя', assignments: [] });
      }
      map.get(empId)!.assignments.push(a);
    }
    return [...map.entries()];
  }, [assignments]);

  return (
    <>
      {byEmployee.map(([empId, { name, assignments: empAssignments }]) => (
        <div
          key={empId}
          style={{
            display: 'flex',
            height: ROW_HEIGHT + 4,
            borderBottom: '1px solid #1e3a5f',
            background: 'rgba(0,201,200,0.03)',
          }}
        >
          <div style={{
            width: leftColWidth,
            flexShrink: 0,
            borderRight: '1px solid #1e3a5f',
            padding: '0 12px',
            display: 'flex',
            alignItems: 'center',
            fontSize: 13,
            fontWeight: 600,
            color: '#fff',
            overflow: 'hidden',
            whiteSpace: 'nowrap',
            textOverflow: 'ellipsis',
          }}>
            {name}
          </div>
          <div style={{ flex: 1, position: 'relative' }}>
            {empAssignments.filter(a => a.start_date && a.end_date).map(a => {
              const idx = itemOrder.indexOf(a.backlog_item_id);
              const color = getItemColor(idx);
              const left = dateToLeft(a.start_date!, timeline);
              const width = datesToWidth(a.start_date!, a.end_date!, timeline);
              const refKey = `${a.backlog_item_id}-${a.phase}-${a.part_number}`;
              return (
                <div
                  key={a.id}
                  ref={el => {
                    if (el) rowRefs.current.set(refKey, el);
                    else rowRefs.current.delete(refKey);
                  }}
                  title={`${a.backlog_item_title} — ${PHASE_LABELS[a.phase]} (${a.hours_allocated?.toFixed(0)}ч)`}
                  style={{
                    position: 'absolute',
                    left: `${left}%`,
                    width: `${Math.max(width, 0.8)}%`,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    height: 22,
                    background: color,
                    opacity: 0.85,
                    borderRadius: 3,
                    zIndex: 2,
                    display: 'flex',
                    alignItems: 'center',
                    paddingLeft: 4,
                    fontSize: 9,
                    color: '#fff',
                    fontWeight: 700,
                    overflow: 'hidden',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {a.backlog_item_title}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </>
  );
}

export default function GanttRows(props: Props) {
  if (props.viewMode === 'portfolio') return <PortfolioRows {...props} />;
  if (props.viewMode === 'resource-track') return <ResourceTrackRows {...props} />;
  return <TwoLevelRows {...props} />;
}
```

- [ ] **Step 2: Update GanttChart to pass `rowRefs` to GanttRows and add `showRelayArrows` prop**

Replace full content of `frontend/src/components/resource-planning/GanttChart.tsx`:

```tsx
import { useRef, useMemo } from 'react';
import type { AssignmentOut, ScheduledBlock } from '../../api/resourcePlanning';
import { buildTimeline, dateToLeft, quarterBounds } from '../../utils/gantt';
import type { ViewMode } from './GanttRows';
import TimelineHeader from './TimelineHeader';
import GanttRows from './GanttRows';
import BlockedZones from './BlockedZones';
import DependencyArrows from './DependencyArrows';

const LEFT_COL = 240;

interface Props {
  assignments: AssignmentOut[];
  blocks: ScheduledBlock[];
  quarter: string;
  year: number;
  viewMode: ViewMode;
  showRelayArrows?: boolean;
}

export default function GanttChart({
  assignments,
  blocks,
  quarter,
  year,
  viewMode,
  showRelayArrows = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<string, HTMLElement>>(new Map());

  const timeline = useMemo(() => {
    const { start, end } = quarterBounds(quarter, year);
    return buildTimeline(start, end);
  }, [quarter, year]);

  const todayLeft = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return dateToLeft(today, timeline);
  }, [timeline]);

  return (
    <div
      style={{
        background: '#0f2340',
        border: '1px solid #1e3a5f',
        borderRadius: 8,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <TimelineHeader timeline={timeline} leftColWidth={LEFT_COL} />

      <div
        ref={containerRef}
        style={{ position: 'relative', overflowY: 'auto', maxHeight: 'calc(100vh - 280px)' }}
      >
        {/* Today marker */}
        <div style={{
          position: 'absolute',
          left: `calc(${LEFT_COL}px + ${todayLeft / 100} * (100% - ${LEFT_COL}px))`,
          top: 0, bottom: 0,
          width: 2,
          background: 'rgba(0,201,200,0.6)',
          zIndex: 20,
          pointerEvents: 'none',
        }} />

        {/* Blocked zones */}
        <div style={{ position: 'absolute', left: LEFT_COL, right: 0, top: 0, bottom: 0, pointerEvents: 'none' }}>
          <BlockedZones blocks={blocks} timeline={timeline} />
        </div>

        {/* SVG arrows */}
        <DependencyArrows
          assignments={assignments}
          rowRefs={rowRefs}
          containerRef={containerRef as React.RefObject<HTMLDivElement>}
          showRelayArrows={showRelayArrows}
        />

        <GanttRows
          assignments={assignments}
          timeline={timeline}
          viewMode={viewMode}
          leftColWidth={LEFT_COL}
          rowRefs={rowRefs}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd frontend && npm run lint
```

Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning/GanttRows.tsx frontend/src/components/resource-planning/GanttChart.tsx
git commit -m "feat(resource-planning): register bar rowRefs + ResourceTrackRows (View C)"
```

---

## Task 8: Add getItemColor() to gantt.ts

**Files:**
- Modify: `frontend/src/utils/gantt.ts`

**Context:** View C (resource track) colors bars by initiative, not by phase. Need a deterministic palette function.

- [ ] **Step 1: Add `ITEM_PALETTE` and `getItemColor()` to `frontend/src/utils/gantt.ts`**

At the end of the file, append:

```typescript
// Palette for coloring initiatives in Resource Track view (cycles when > 8 items)
export const ITEM_PALETTE = [
  '#2a7fbf',
  '#e8864a',
  '#52d364',
  '#d4567a',
  '#a36bdb',
  '#c8a82a',
  '#4ab8d4',
  '#d48b4a',
];

export function getItemColor(itemIndex: number): string {
  return ITEM_PALETTE[itemIndex % ITEM_PALETTE.length];
}
```

- [ ] **Step 2: Verify lint**

```bash
cd frontend && npm run lint
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/gantt.ts
git commit -m "feat(resource-planning): ITEM_PALETTE + getItemColor for View C"
```

---

## Task 9: Inter-initiative relay arrows in DependencyArrows

**Files:**
- Modify: `frontend/src/components/resource-planning/DependencyArrows.tsx`

**Context:** The relay arrows show the analyst pipeline: when an analyst finishes analysis of initiative N, they move to initiative N+1. Draw dashed cyan arrows from the end of the last analyst part of item N to the start of item N+1's first analyst part, for the same employee. Uses rowRefs (now populated by GanttRows). Only drawn when `showRelayArrows=true`.

- [ ] **Step 1: Replace full content of `frontend/src/components/resource-planning/DependencyArrows.tsx`**

```tsx
import { useEffect, useRef } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';

interface Props {
  assignments: AssignmentOut[];
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  containerRef: React.RefObject<HTMLDivElement>;
  showRelayArrows?: boolean;
}

export default function DependencyArrows({
  assignments,
  rowRefs,
  containerRef,
  showRelayArrows = true,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    const container = containerRef.current;
    if (!svg || !container) return;

    svg.innerHTML = '';

    // Re-inject defs after clearing innerHTML
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');

    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'rp-arrowhead');
    marker.setAttribute('markerWidth', '6');
    marker.setAttribute('markerHeight', '4');
    marker.setAttribute('refX', '6');
    marker.setAttribute('refY', '2');
    marker.setAttribute('orient', 'auto');
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('points', '0 0, 6 2, 0 4');
    poly.setAttribute('fill', 'rgba(180,200,240,0.5)');
    marker.appendChild(poly);
    defs.appendChild(marker);

    const relayMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    relayMarker.setAttribute('id', 'rp-relay-arrowhead');
    relayMarker.setAttribute('markerWidth', '6');
    relayMarker.setAttribute('markerHeight', '4');
    relayMarker.setAttribute('refX', '6');
    relayMarker.setAttribute('refY', '2');
    relayMarker.setAttribute('orient', 'auto');
    const relayPoly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    relayPoly.setAttribute('points', '0 0, 6 2, 0 4');
    relayPoly.setAttribute('fill', 'rgba(0,201,200,0.7)');
    relayMarker.appendChild(relayPoly);
    defs.appendChild(relayMarker);

    svg.appendChild(defs);

    const cRect = container.getBoundingClientRect();

    // Helper: draw a bezier arrow path
    function drawArrow(
      x1: number, y1: number, x2: number, y2: number,
      color: string, width: string, dashArray: string, markerId: string,
    ) {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const cx = (x1 + x2) / 2;
      path.setAttribute('d', `M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`);
      path.setAttribute('stroke', color);
      path.setAttribute('stroke-width', width);
      path.setAttribute('fill', 'none');
      if (dashArray) path.setAttribute('stroke-dasharray', dashArray);
      path.setAttribute('marker-end', `url(#${markerId})`);
      svg.appendChild(path);
    }

    // ── Intra-initiative arrows (phase → next phase, same item) ────────────
    const PHASE_ORDER = ['analyst', 'dev', 'qa', 'opo'];
    const byItem = new Map<string, AssignmentOut[]>();
    for (const a of assignments) {
      if (!byItem.has(a.backlog_item_id)) byItem.set(a.backlog_item_id, []);
      byItem.get(a.backlog_item_id)!.push(a);
    }

    for (const [, itemAssignments] of byItem) {
      for (let i = 0; i < PHASE_ORDER.length - 1; i++) {
        const fromPhase = PHASE_ORDER[i];
        const toPhase = PHASE_ORDER[i + 1];
        const fromCandidates = itemAssignments.filter(a => a.phase === fromPhase);
        const maxPart = Math.max(...fromCandidates.map(x => x.part_number), 0);
        const from = fromCandidates.find(a => a.part_number === maxPart);
        const to = itemAssignments.find(a => a.phase === toPhase && a.part_number === 1);
        if (!from || !to) continue;

        const fromEl = rowRefs.current.get(`${from.backlog_item_id}-${from.phase}-${from.part_number}`);
        const toEl = rowRefs.current.get(`${to.backlog_item_id}-${to.phase}-${to.part_number}`);
        if (!fromEl || !toEl) continue;

        const fRect = fromEl.getBoundingClientRect();
        const tRect = toEl.getBoundingClientRect();
        drawArrow(
          fRect.right - cRect.left,
          fRect.top + fRect.height / 2 - cRect.top,
          tRect.left - cRect.left,
          tRect.top + tRect.height / 2 - cRect.top,
          'rgba(180,200,240,0.35)', '1.5', '', 'rp-arrowhead',
        );
      }
    }

    // ── Inter-initiative relay arrows (analyst pipeline) ───────────────────
    if (showRelayArrows) {
      // Group analyst assignments by employee
      const byEmp = new Map<string, AssignmentOut[]>();
      for (const a of assignments) {
        if (a.phase !== 'analyst' || !a.employee_id || !a.start_date) continue;
        if (!byEmp.has(a.employee_id)) byEmp.set(a.employee_id, []);
        byEmp.get(a.employee_id)!.push(a);
      }

      for (const [, empAssignments] of byEmp) {
        // Group by item, then order items by first start_date
        const byItemEmp = new Map<string, AssignmentOut[]>();
        for (const a of empAssignments) {
          if (!byItemEmp.has(a.backlog_item_id)) byItemEmp.set(a.backlog_item_id, []);
          byItemEmp.get(a.backlog_item_id)!.push(a);
        }
        const orderedItems = [...byItemEmp.entries()].sort((a, b) => {
          const aStart = a[1].reduce((mn, x) => x.start_date! < mn ? x.start_date! : mn, a[1][0].start_date!);
          const bStart = b[1].reduce((mn, x) => x.start_date! < mn ? x.start_date! : mn, b[1][0].start_date!);
          return aStart.localeCompare(bStart);
        });

        for (let i = 0; i < orderedItems.length - 1; i++) {
          const [fromItemId, fromParts] = orderedItems[i];
          const [toItemId] = orderedItems[i + 1];
          const maxPart = Math.max(...fromParts.map(a => a.part_number));
          const fromEl = rowRefs.current.get(`${fromItemId}-analyst-${maxPart}`);
          const toEl = rowRefs.current.get(`${toItemId}-analyst-1`);
          if (!fromEl || !toEl) continue;

          const fRect = fromEl.getBoundingClientRect();
          const tRect = toEl.getBoundingClientRect();
          drawArrow(
            fRect.right - cRect.left,
            fRect.top + fRect.height / 2 - cRect.top,
            tRect.left - cRect.left,
            tRect.top + tRect.height / 2 - cRect.top,
            'rgba(0,201,200,0.55)', '1.5', '5 3', 'rp-relay-arrowhead',
          );
        }
      }
    }
  });

  return (
    <svg
      ref={svgRef}
      style={{
        position: 'absolute',
        top: 0, left: 0,
        width: '100%', height: '100%',
        pointerEvents: 'none',
        overflow: 'visible',
        zIndex: 10,
      }}
    />
  );
}
```

- [ ] **Step 2: Verify lint**

```bash
cd frontend && npm run lint
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/resource-planning/DependencyArrows.tsx
git commit -m "feat(resource-planning): inter-initiative relay arrows + showRelayArrows prop"
```

---

## Task 10: ResourcePlanningPage — View C option + relay toggle

**Files:**
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx`

**Changes:**
1. Add `'Ресурсы'` (value `'resource-track'`) to the Segmented control
2. Add `showRelayArrows` state (Switch toggle)
3. Pass `showRelayArrows` to `GanttChart`

- [ ] **Step 1: Replace full content of `frontend/src/pages/ResourcePlanningPage.tsx`**

```tsx
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { App, Button, Empty, Select, Segmented, Space, Spin, Switch, Tag } from 'antd';
import {
  BarChartOutlined,
  CalculatorOutlined,
  ScheduleOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import GanttChart from '../components/resource-planning/GanttChart';
import ConflictPanel from '../components/resource-planning/ConflictPanel';
import ScheduledBlocksModal from '../components/resource-planning/ScheduledBlocksModal';
import type { ViewMode } from '../components/resource-planning/GanttRows';
import {
  useGanttProjection, useResourcePlans, useComputeResourcePlan,
  useScheduledBlocks, useCreateResourcePlan,
} from '../hooks/useResourcePlanning';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

export default function ResourcePlanningPage() {
  const { message } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTeams } = useGlobalTeamFilter();
  const team = selectedTeams[0] ?? '';

  const [planId, setPlanId] = useState<string | null>(searchParams.get('plan_id'));
  const [viewMode, setViewMode] = useState<ViewMode>('two-level');
  const [blocksOpen, setBlocksOpen] = useState(false);
  const [showRelayArrows, setShowRelayArrows] = useState(true);

  const scenarioId = searchParams.get('scenario_id');
  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(team || undefined);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);
  const { data: blocks = [] } = useScheduledBlocks(team || undefined);
  const compute = useComputeResourcePlan();
  const createPlan = useCreateResourcePlan();

  // Auto-create plan when navigating from approved scenario
  useEffect(() => {
    if (scenarioId && !planId && !plansLoading) {
      const existing = plans.find(p => p.scenario_id === scenarioId);
      if (existing) {
        setPlanId(existing.id);
        setSearchParams({ plan_id: existing.id });
      } else if (plans.length === 0) {
        createPlan.mutateAsync({
          scenario_id: scenarioId,
          team,
          quarter: searchParams.get('quarter') ?? 'Q2',
          year: parseInt(searchParams.get('year') ?? String(new Date().getFullYear())),
        }).then(plan => {
          setPlanId(plan.id);
          setSearchParams({ plan_id: plan.id });
        }).catch(() => message.error('Ошибка создания плана'));
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, planId, plansLoading, plans.length]);

  const handleCompute = async () => {
    if (!planId) return;
    try {
      await compute.mutateAsync(planId);
      message.success('Расписание рассчитано');
    } catch {
      message.error('Ошибка расчёта');
    }
  };

  const planOptions = plans.map(p => ({
    label: `${p.quarter} ${p.year} — ${p.team ?? '—'} [${p.status}]`,
    value: p.id,
  }));

  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader
        title="Ресурсное планирование"
        actions={
          <Space>
            <Button icon={<SettingOutlined />} onClick={() => setBlocksOpen(true)} size="small">
              Заблокированные периоды
            </Button>
          </Space>
        }
      />

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <Select
          loading={plansLoading}
          placeholder="Выберите план"
          value={planId}
          onChange={id => { setPlanId(id); setSearchParams(id ? { plan_id: id } : {}); }}
          options={planOptions}
          style={{ minWidth: 320 }}
          allowClear
        />
        {planId && (
          <Button
            icon={<CalculatorOutlined />}
            type="primary"
            loading={compute.isPending || gantt?.plan.status === 'computing'}
            onClick={handleCompute}
          >
            Пересчитать
          </Button>
        )}
        {gantt && (
          <Tag color={gantt.plan.status === 'ready' ? 'cyan' : 'orange'}>
            {gantt.plan.status === 'ready' ? 'Готово' : gantt.plan.status}
          </Tag>
        )}

        <Space size={4} style={{ marginLeft: 'auto' }}>
          {viewMode !== 'resource-track' && (
            <Space size={4}>
              <Switch
                checked={showRelayArrows}
                onChange={setShowRelayArrows}
                size="small"
              />
              <span style={{ fontSize: 12, color: '#8ab0d8' }}>Связи</span>
            </Space>
          )}
          <Segmented
            value={viewMode}
            onChange={v => setViewMode(v as ViewMode)}
            options={[
              { label: 'Портфель', value: 'portfolio', icon: <BarChartOutlined /> },
              { label: 'Фазы', value: 'two-level', icon: <ScheduleOutlined /> },
              { label: 'Ресурсы', value: 'resource-track', icon: <TeamOutlined /> },
            ]}
          />
        </Space>
      </div>

      {gantt && <ConflictPanel conflicts={gantt.conflicts} />}

      {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
      {!planId && !ganttLoading && (
        <Empty description="Выберите план или создайте его из утверждённого сценария" />
      )}
      {gantt && !ganttLoading && (
        <GanttChart
          assignments={gantt.assignments}
          blocks={blocks}
          quarter={gantt.plan.quarter ?? 'Q1'}
          year={gantt.plan.year ?? new Date().getFullYear()}
          viewMode={viewMode}
          showRelayArrows={showRelayArrows}
        />
      )}

      <ScheduledBlocksModal open={blocksOpen} onClose={() => setBlocksOpen(false)} team={team || undefined} />
    </div>
  );
}
```

- [ ] **Step 2: Verify lint**

```bash
cd frontend && npm run lint
```

Expected: No errors.

- [ ] **Step 3: Build frontend**

```bash
cd frontend && npm run build
```

Expected: Build succeeds, no TypeScript errors.

- [ ] **Step 4: Run backend tests**

```bash
py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -15
```

Expected: 623+ passed (618 + 5 new CPM tests), 2 pre-existing failures max.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "feat(resource-planning): add Ресурсы view + relay arrows toggle"
```

- [ ] **Step 6: Push**

```bash
git push origin main
```

---

## Summary of Changes

**Backend (new):**
- `alembic/versions/*_add_plan_item_dependencies.py` — new table
- `app/models/plan_item_dependency.py` — PlanItemDependency model

**Backend (modified):**
- `app/models/resource_plan.py` — adds `dependencies` relationship
- `app/models/__init__.py` — adds PlanItemDependency
- `app/services/resource_planning_service.py` — `_compute_cpm()` + call in `compute_schedule()`
- `app/api/endpoints/resource_planning.py` — SPLIT_REQUIRED/NO_ANALYST/NO_DEV conflicts + PATCH assignment endpoint
- `tests/test_resource_planning_service.py` — 5 new CPM tests

**Frontend (modified):**
- `frontend/src/api/resourcePlanning.ts` — AssignmentPatch + patchAssignment()
- `frontend/src/hooks/useResourcePlanning.ts` — usePatchAssignment()
- `frontend/src/utils/gantt.ts` — ITEM_PALETTE + getItemColor()
- `frontend/src/components/resource-planning/GanttRows.tsx` — rowRefs registration + ResourceTrackRows
- `frontend/src/components/resource-planning/DependencyArrows.tsx` — relay arrows + showRelayArrows prop + defs re-injection fix
- `frontend/src/components/resource-planning/GanttChart.tsx` — passes rowRefs to GanttRows + showRelayArrows prop
- `frontend/src/pages/ResourcePlanningPage.tsx` — Ресурсы view + relay toggle
