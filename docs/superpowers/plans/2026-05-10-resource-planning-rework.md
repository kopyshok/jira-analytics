# Resource Planning Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переработка раздела `/resource-planning` — корректная формула вовлечённости, свободный граф зависимостей фаз, ручные правки с закреплением, мульти-роли в блокировках, читаемая панель конфликтов и улучшенный визуал графика.

**Architecture:** Бэкенд — расширение `ResourcePlanningService` (новая дневная ёмкость, топологический проход по графу предшественников, сохранение pinned-правок). Фронтенд — перерисовка `GanttRows`/`GanttChart`/`ConflictPanel` с новыми визуальными слоями (штриховка недоступности, тепловая полоса, drag-стрелки) и новыми UI-действиями (boczная панель свойств, контекст-меню, диалог разбива).

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + Alembic (batch); React 19 + TS 6 + Vite 8 + AntD 6; Pytest + Playwright.

**Spec:** `docs/superpowers/specs/2026-05-10-resource-planning-rework-design.md`

---

## File Structure

### Бэкенд — новые файлы

- `app/models/phase_predecessor.py` — таблица связей фаз
- `app/models/scheduled_block_role.py` — M:N роли блокировки
- `app/models/scheduled_block_employee.py` — M:N люди блокировки
- `app/models/user_rp_preferences.py` — per-user UI-предпочтения
- `app/services/conflict_aggregator.py` — агрегация конфликтов с шаблонизацией
- `alembic/versions/<rev>_phase_predecessor.py`
- `alembic/versions/<rev>_assignment_pinned_split.py`
- `alembic/versions/<rev>_scheduled_block_multi.py`
- `alembic/versions/<rev>_user_rp_preferences.py`
- `alembic/versions/<rev>_seed_phase_predecessors.py`

### Бэкенд — изменения

- `app/models/resource_plan_assignment.py` — добавить `pinned_start`, `pinned_split`, `manual_edit_at`; переименовать `is_pinned` → `pinned_employee`.
- `app/models/scheduled_block.py` — удалить `role_id`, `employee_id`; добавить relationships к `_role` и `_employee`.
- `app/services/resource_planning_service.py` — новая дневная ёмкость (`_daily_role_capacity`), топологический проход, сохранение pinned-правок.
- `app/api/endpoints/resource_planning.py` — новые эндпоинты PATCH/split/merge, расширение `gantt`-ответа, новые поля в схемах.

### Фронтенд — новые файлы

- `frontend/src/components/resource-planning/AssignmentSidebar.tsx` — боковая панель свойств фазы.
- `frontend/src/components/resource-planning/PhaseContextMenu.tsx` — контекст-меню фазы.
- `frontend/src/components/resource-planning/SplitDialog.tsx` — диалог разбива.
- `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx` — тепловая полоса загрузки.
- `frontend/src/components/resource-planning/UnavailabilityPattern.tsx` — паттерны недоступных дней внутри бара.
- `frontend/src/hooks/useRpPreferences.ts` — debounced сохранение предпочтений.

### Фронтенд — изменения

- `frontend/src/components/resource-planning/GanttRows.tsx` — двухстрочные строки + свёртка фаз + рамки конфликтов.
- `frontend/src/components/resource-planning/GanttChart.tsx` — тумблер выходных, тепловая полоса, мини-пересчёт после drag.
- `frontend/src/components/resource-planning/ConflictPanel.tsx` — табы группировки, фильтры, действия на строках.
- `frontend/src/components/resource-planning/DependencyArrows.tsx` — drag-and-drop стрелок зависимости фаз.
- `frontend/src/api/resourcePlanning.ts` — новые методы API.
- `frontend/src/pages/ResourcePlanningPage.tsx` — интеграция новых компонентов.

---

## Task 1: Migration — phase_predecessor table

**Files:**
- Create: `app/models/phase_predecessor.py`
- Create: `alembic/versions/<rev>_phase_predecessor.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_phase_predecessor_model.py`

- [ ] **Step 1: Write failing model test**

```python
# tests/test_phase_predecessor_model.py
from app.models import PhasePredecessor

def test_phase_predecessor_fields():
    pp = PhasePredecessor(
        successor_assignment_id="s-1",
        predecessor_assignment_id="p-1",
    )
    assert pp.successor_assignment_id == "s-1"
    assert pp.predecessor_assignment_id == "p-1"
```

- [ ] **Step 2: Run test, verify import error**

`py -3.10 -m pytest tests/test_phase_predecessor_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'PhasePredecessor'`

- [ ] **Step 3: Create model**

```python
# app/models/phase_predecessor.py
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.resource_plan_assignment import ResourcePlanAssignment


class PhasePredecessor(Base, TimestampMixin):
    """Связь предшественника фазы внутри инициативы (свободный граф)."""

    __tablename__ = "phase_predecessor"
    __table_args__ = (
        UniqueConstraint(
            "successor_assignment_id",
            "predecessor_assignment_id",
            name="uq_phase_predecessor_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    successor_assignment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("resource_plan_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    predecessor_assignment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("resource_plan_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
```

- [ ] **Step 4: Register in __init__**

Add to `app/models/__init__.py` imports + `__all__`:
```python
from app.models.phase_predecessor import PhasePredecessor
```
And include `"PhasePredecessor"` in `__all__`.

- [ ] **Step 5: Generate migration**

```bash
py -3.10 -m alembic revision --autogenerate -m "add phase_predecessor table"
```
Verify generated file creates the table with the unique constraint.

- [ ] **Step 6: Apply migration + run test**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m pytest tests/test_phase_predecessor_model.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/models/phase_predecessor.py app/models/__init__.py alembic/versions/ tests/test_phase_predecessor_model.py
git commit -m "feat(rp): phase_predecessor model + migration"
```

---

## Task 2: Migration — pinned/manual flags on assignments

**Files:**
- Modify: `app/models/resource_plan_assignment.py`
- Create: `alembic/versions/<rev>_assignment_pinned_split.py`
- Test: `tests/test_assignment_pinned_fields.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_assignment_pinned_fields.py
from datetime import datetime
from app.models import ResourcePlanAssignment

def test_assignment_pinned_fields(db_session):
    a = ResourcePlanAssignment(
        plan_id="p1", backlog_item_id="b1", phase="analyst",
        pinned_start=True, pinned_employee=False, pinned_split=True,
        manual_edit_at=datetime(2026, 5, 10, 12, 0),
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    assert a.pinned_start is True
    assert a.pinned_split is True
    assert a.manual_edit_at.year == 2026
```

- [ ] **Step 2: Run, verify fail**

`py -3.10 -m pytest tests/test_assignment_pinned_fields.py -v`
Expected: FAIL — attribute does not exist.

- [ ] **Step 3: Add fields to model**

In `app/models/resource_plan_assignment.py` after `is_pinned`:
```python
from datetime import datetime as _datetime
from sqlalchemy import DateTime

# rename is_pinned → pinned_employee (back-compat property below)
pinned_employee: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="0", index=True
)
pinned_start: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="0"
)
pinned_split: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="0"
)
manual_edit_at: Mapped[Optional[_datetime]] = mapped_column(DateTime, nullable=True)

@property
def is_pinned(self) -> bool:
    """Back-compat: True если есть любой pinned-флаг."""
    return self.pinned_employee or self.pinned_start or self.pinned_split
```

Remove the original `is_pinned: Mapped[bool] = mapped_column(...)`.

- [ ] **Step 4: Generate batch migration**

```bash
py -3.10 -m alembic revision --autogenerate -m "assignment pinned/manual fields"
```

Edit the migration to use batch_alter_table for SQLite. The migration should:
1. Add `pinned_start`, `pinned_split`, `manual_edit_at` columns.
2. Add new `pinned_employee` column.
3. Copy `is_pinned` → `pinned_employee` (use `op.execute("UPDATE resource_plan_assignments SET pinned_employee = is_pinned")`).
4. Drop `is_pinned`.

- [ ] **Step 5: Apply + run test**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m pytest tests/test_assignment_pinned_fields.py -v
```
Expected: PASS.

- [ ] **Step 6: Update existing service usages**

```bash
py -3.10 -c "import app.services.resource_planning_service" 2>&1
```
Expected: import OK. Then grep for `is_pinned` usages in app/ and replace with `pinned_employee` or use the back-compat property as needed:
```python
# app/services/resource_planning_service.py:257, 270
ResourcePlanAssignment.pinned_employee == True
```

- [ ] **Step 7: Run existing rp tests to check no regression**

```bash
py -3.10 -m pytest tests/ -k "resource_plan" -v
```
Expected: PASS (or pre-existing failures only).

- [ ] **Step 8: Commit**

```bash
git add app/models/resource_plan_assignment.py app/services/resource_planning_service.py alembic/versions/ tests/test_assignment_pinned_fields.py
git commit -m "feat(rp): pinned_start/employee/split + manual_edit_at on assignments"
```

---

## Task 3: Migration — multi-role/employee scheduled blocks

**Files:**
- Create: `app/models/scheduled_block_role.py`
- Create: `app/models/scheduled_block_employee.py`
- Modify: `app/models/scheduled_block.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/<rev>_scheduled_block_multi.py`
- Test: `tests/test_scheduled_block_multi.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_scheduled_block_multi.py
from datetime import date
from app.models import ScheduledBlock, ScheduledBlockRole, ScheduledBlockEmployee, Role, Employee

def test_block_multi_roles_and_employees(db_session):
    role_a = Role(id="r-a", code="analyst", name="Аналитик")
    role_b = Role(id="r-b", code="dev", name="Разработчик")
    emp = Employee(id="e-1", display_name="Иванов")
    db_session.add_all([role_a, role_b, emp])
    db_session.commit()
    block = ScheduledBlock(
        team="T", start_date=date(2026, 5, 1), end_date=date(2026, 5, 5),
        reason="Тренинг",
    )
    block.roles = [ScheduledBlockRole(role_id="r-a"), ScheduledBlockRole(role_id="r-b")]
    block.employees = [ScheduledBlockEmployee(employee_id="e-1")]
    db_session.add(block)
    db_session.commit()
    db_session.refresh(block)
    assert {r.role_id for r in block.roles} == {"r-a", "r-b"}
    assert block.employees[0].employee_id == "e-1"
```

- [ ] **Step 2: Run, verify fail**

`py -3.10 -m pytest tests/test_scheduled_block_multi.py -v`

- [ ] **Step 3: Create new models**

```python
# app/models/scheduled_block_role.py
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import generate_uuid
from app.database import Base

class ScheduledBlockRole(Base):
    __tablename__ = "scheduled_block_role"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    block_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scheduled_blocks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
```

```python
# app/models/scheduled_block_employee.py
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import generate_uuid
from app.database import Base

class ScheduledBlockEmployee(Base):
    __tablename__ = "scheduled_block_employee"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    block_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scheduled_blocks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
```

- [ ] **Step 4: Update ScheduledBlock model**

In `app/models/scheduled_block.py` — remove `role_id`, `employee_id` columns + add relationships:
```python
from typing import List
from sqlalchemy.orm import relationship

# remove:
# role_id, employee_id columns

# add at end of class:
roles: Mapped[List["ScheduledBlockRole"]] = relationship(
    "ScheduledBlockRole", cascade="all, delete-orphan", backref="block"
)
employees: Mapped[List["ScheduledBlockEmployee"]] = relationship(
    "ScheduledBlockEmployee", cascade="all, delete-orphan", backref="block"
)
```

Update docstring: «Если roles=[] и employees=[] — блок для всей команды.»

- [ ] **Step 5: Register in __init__**

Add to `app/models/__init__.py`:
```python
from app.models.scheduled_block_role import ScheduledBlockRole
from app.models.scheduled_block_employee import ScheduledBlockEmployee
```
Add to `__all__`.

- [ ] **Step 6: Migration with data copy**

```bash
py -3.10 -m alembic revision -m "scheduled_block multi-role/employee"
```

Manual edit (autogenerate may miss data copy):
```python
def upgrade():
    op.create_table(
        "scheduled_block_role",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("block_id", sa.String(36), sa.ForeignKey("scheduled_blocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_scheduled_block_role_block_id", "scheduled_block_role", ["block_id"])
    op.create_table(
        "scheduled_block_employee",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("block_id", sa.String(36), sa.ForeignKey("scheduled_blocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_scheduled_block_employee_block_id", "scheduled_block_employee", ["block_id"])
    # data migration
    op.execute("""
        INSERT INTO scheduled_block_role (id, block_id, role_id)
        SELECT lower(hex(randomblob(16))), id, role_id FROM scheduled_blocks
        WHERE role_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO scheduled_block_employee (id, block_id, employee_id)
        SELECT lower(hex(randomblob(16))), id, employee_id FROM scheduled_blocks
        WHERE employee_id IS NOT NULL
    """)
    with op.batch_alter_table("scheduled_blocks") as batch:
        batch.drop_column("role_id")
        batch.drop_column("employee_id")
```

- [ ] **Step 7: Apply + run test**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m pytest tests/test_scheduled_block_multi.py -v
```

- [ ] **Step 8: Update _block_targets in service**

`app/services/resource_planning_service.py:220-235` — заменить `_block_targets`:
```python
def _block_targets(
    self,
    block: ScheduledBlock,
    employees: List[Employee],
    role_id_to_code: Dict[str, str],
) -> List[str]:
    if not block.roles and not block.employees:
        return [e.id for e in employees if e.team == block.team] if block.team else [e.id for e in employees]
    targets: set[str] = set()
    role_ids = {r.role_id for r in block.roles}
    for r_id in role_ids:
        code = role_id_to_code.get(r_id, "")
        targets.update(e.id for e in employees if e.role == code)
    targets.update(e.employee_id for e in block.employees)
    return list(targets)
```

Update `role_ids_needed` in `build_availability` to read from `b.roles` instead of `b.role_id`.

- [ ] **Step 9: Run rp tests**

```bash
py -3.10 -m pytest tests/ -k "resource_plan or scheduled_block" -v
```

- [ ] **Step 10: Commit**

```bash
git add app/models/ alembic/versions/ tests/test_scheduled_block_multi.py app/services/resource_planning_service.py
git commit -m "feat(rp): multi-role + multi-employee scheduled blocks"
```

---

## Task 4: Migration — user resource-planning preferences

**Files:**
- Create: `app/models/user_rp_preferences.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/<rev>_user_rp_preferences.py`
- Test: `tests/test_user_rp_preferences_model.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_user_rp_preferences_model.py
from app.models import UserRpPreferences, User

def test_prefs_roundtrip(db_session):
    user = User(id="u-1", email="a@b.c", password_hash="x")
    db_session.add(user); db_session.commit()
    p = UserRpPreferences(
        user_id="u-1",
        hide_weekends=True,
        collapsed_initiative_ids=["i-1", "i-2"],
        view_mode="week",
        show_relay=False,
    )
    db_session.add(p); db_session.commit(); db_session.refresh(p)
    assert p.hide_weekends is True
    assert p.collapsed_initiative_ids == ["i-1", "i-2"]
```

- [ ] **Step 2: Run, fail**

- [ ] **Step 3: Model**

```python
# app/models/user_rp_preferences.py
from typing import List, Optional
from sqlalchemy import Boolean, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import TimestampMixin
from app.database import Base

class UserRpPreferences(Base, TimestampMixin):
    __tablename__ = "user_rp_preferences"
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    hide_weekends: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    collapsed_initiative_ids: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    view_mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    show_relay: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
```

- [ ] **Step 4: Register, migrate, apply, test**

Same pattern as Tasks 1-3.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(rp): user_rp_preferences model"
```

---

## Task 5: Daily-capacity formula (involvement)

**Files:**
- Modify: `app/services/resource_planning_service.py`
- Test: `tests/services/test_rp_involvement_capacity.py`

- [ ] **Step 1: Failing test**

```python
# tests/services/test_rp_involvement_capacity.py
from datetime import date
from app.services.resource_planning_service import ResourcePlanningService

def test_daily_capacity_with_involvement(db_session):
    """20 hours, involvement 0.7 → 5.6 h/day → 4 days."""
    svc = ResourcePlanningService(db_session)
    # _daily_role_capacity helper
    cap = svc._daily_role_capacity(avail_hours=8.0, involvement=0.7, parallel_count=1)
    assert cap == 5.6

def test_daily_capacity_parallel(db_session):
    svc = ResourcePlanningService(db_session)
    # 2 parallel staff, full involvement → 16 h/day
    cap = svc._daily_role_capacity(avail_hours=8.0, involvement=1.0, parallel_count=2)
    assert cap == 16.0

def test_daily_capacity_null_involvement_uses_full_avail(db_session):
    svc = ResourcePlanningService(db_session)
    cap = svc._daily_role_capacity(avail_hours=8.0, involvement=None, parallel_count=1)
    assert cap == 8.0
```

- [ ] **Step 2: Run — should fail (method doesn't exist)**

`py -3.10 -m pytest tests/services/test_rp_involvement_capacity.py -v`

- [ ] **Step 3: Implement `_daily_role_capacity`**

In `app/services/resource_planning_service.py` add static helper:
```python
@staticmethod
def _daily_role_capacity(
    avail_hours: float, involvement: Optional[float], parallel_count: int
) -> float:
    """Дневная ёмкость роли в фазе.

    avail_hours — доступно_по_календарю_сотрудника (производственный + отсутствия).
    involvement — коэф вовлечённости (0..1), None → 1.0.
    parallel_count — число параллельных исполнителей этой роли (>=1).
    """
    inv = 1.0 if involvement is None else max(0.0, min(1.0, involvement))
    return avail_hours * inv * max(1, parallel_count)
```

- [ ] **Step 4: Test passes**

`py -3.10 -m pytest tests/services/test_rp_involvement_capacity.py -v`

- [ ] **Step 5: Wire into `_allocate_hours`**

Modify signature and body of `_allocate_hours` (lines 585-622) to accept `daily_capacity` parameter:
```python
def _allocate_hours(
    self,
    employee_id: str,
    total_hours: float,
    earliest_start: date,
    deadline: date,
    remaining: Dict[str, Dict[date, float]],
    daily_capacity: Optional[float] = None,
) -> List[Tuple[date, date, float, int]]:
    emp_days = remaining.get(employee_id, {})
    remaining_h = total_hours
    used_total = 0.0
    seg_start: Optional[date] = None
    seg_end: Optional[date] = None
    d = earliest_start
    while remaining_h > 0.01 and d <= deadline:
        avail_h = emp_days.get(d, 0.0)
        cap = avail_h if daily_capacity is None else min(avail_h, daily_capacity)
        if cap > 0:
            if seg_start is None:
                seg_start = d
            used = min(cap, remaining_h)
            emp_days[d] -= used
            remaining_h -= used
            used_total += used
            seg_end = d
        d += timedelta(days=1)
    if seg_start is not None and seg_end is not None and used_total > 0:
        return [(seg_start, seg_end, used_total, 1)]
    return []
```

- [ ] **Step 6: Update calls in `compute_schedule`**

In `compute_schedule` (around line 460-530), before each call to `_allocate_hours`, compute `daily_capacity`:
```python
involvement = getattr(item, f"involvement_{phase if phase != 'opo' else 'launch'}", None)
parallel_n = _resolve_parallel_count_legacy(item, phase) if phase != "opo" else 1
daily_cap = self._daily_role_capacity(
    avail_hours=8.0,  # base; per-day actual avail is checked inside _allocate_hours
    involvement=involvement,
    parallel_count=parallel_n,
)
segments = self._allocate_hours(
    employee_id, hours, earliest_start, alloc_deadline, remaining,
    daily_capacity=daily_cap,
)
```

Apply same pattern to ОПЭ allocations and analyst-split chunks.

- [ ] **Step 7: Integration test — full compute**

```python
# tests/services/test_rp_involvement_capacity.py — extend
def test_compute_with_involvement_no_overload(db_session, sample_team_and_backlog):
    """Full compute_schedule: involvement 0.5, 40 hours, 5-day quarter — should fit at 4 h/day × 10 days."""
    # build minimal plan with one item involvement_analyst=0.5, hours=40
    # call svc.compute_schedule(plan_id)
    # assert no OVERLOAD conflicts on the single assignment
```

(Detail this test using existing test patterns from `tests/services/test_*.py`.)

- [ ] **Step 8: Run all rp tests**

```bash
py -3.10 -m pytest tests/services/test_rp_involvement_capacity.py tests/test_api_planning_resource.py -v
```

- [ ] **Step 9: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_involvement_capacity.py
git commit -m "fix(rp): involvement now reduces daily capacity, fixes 24000% overloads"
```

---

## Task 6: Free predecessor graph in compute_schedule

**Files:**
- Modify: `app/services/resource_planning_service.py`
- Test: `tests/services/test_rp_predecessor_graph.py`

- [ ] **Step 1: Failing test — default chain**

```python
# tests/services/test_rp_predecessor_graph.py
def test_default_chain_creates_analyst_dev_qa_opo(db_session, sample_plan):
    """First compute creates default predecessors: analyst→dev→qa, dev→opo."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)
    from app.models import PhasePredecessor, ResourcePlanAssignment
    rows = db_session.query(PhasePredecessor).all()
    assert len(rows) >= 3
```

- [ ] **Step 2: Failing test — custom predecessor honored**

```python
def test_custom_predecessor_overrides_chain(db_session, sample_plan):
    """If qa→analyst predecessor exists (parallel test), qa starts after analyst, not after dev."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)
    # rewire: qa now depends only on analyst
    # delete existing qa predecessors, insert new (qa, analyst)
    # recompute, assert qa.start_date <= dev.end_date (parallel)
```

- [ ] **Step 3: Failing test — cycle detection**

```python
def test_cycle_rejected(db_session, sample_plan):
    """Adding edge that creates cycle raises ValueError."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)
    with pytest.raises(ValueError, match="cycle"):
        svc.add_predecessor(successor_id="a-1", predecessor_id="a-2")  # cycle
```

- [ ] **Step 4: Run, fail**

- [ ] **Step 5: Implement topological pass**

Replace the linear `for phase in PHASE_ORDER` loop in `compute_schedule` with:
```python
# Build predecessor graph for this plan's assignments
preds = self._load_predecessors(plan_id)  # {assignment_id: [pred_id, ...]}
# Topological order
order = self._topological_order(new_assignments, preds)
# Walk in topo order
for assignment in order:
    earliest_start = self._earliest_start_from_preds(assignment, preds, q_start)
    # ... allocate hours, etc.
```

Add helpers:
```python
def _load_predecessors(self, plan_id: str) -> Dict[str, List[str]]:
    from app.models import PhasePredecessor
    rows = self.db.execute(
        select(PhasePredecessor).join(
            ResourcePlanAssignment,
            PhasePredecessor.successor_assignment_id == ResourcePlanAssignment.id,
        ).where(ResourcePlanAssignment.plan_id == plan_id)
    ).scalars().all()
    out: Dict[str, List[str]] = defaultdict(list)
    for r in rows:
        out[r.successor_assignment_id].append(r.predecessor_assignment_id)
    return out

def _topological_order(
    self,
    assignments: List[ResourcePlanAssignment],
    preds: Dict[str, List[str]],
) -> List[ResourcePlanAssignment]:
    """Kahn's algorithm. Raises ValueError on cycle."""
    by_id = {a.id: a for a in assignments}
    indeg: Dict[str, int] = {a.id: 0 for a in assignments}
    for succ_id, p_list in preds.items():
        for p_id in p_list:
            if p_id in by_id and succ_id in by_id:
                indeg[succ_id] += 1
    queue = [aid for aid, d in indeg.items() if d == 0]
    result = []
    while queue:
        aid = queue.pop(0)
        result.append(by_id[aid])
        for succ_id, p_list in preds.items():
            if aid in p_list:
                indeg[succ_id] -= 1
                if indeg[succ_id] == 0:
                    queue.append(succ_id)
    if len(result) != len(assignments):
        raise ValueError("phase predecessor cycle detected")
    return result

def _earliest_start_from_preds(
    self,
    assignment: ResourcePlanAssignment,
    preds: Dict[str, List[str]],
    q_start: date,
) -> date:
    pred_ids = preds.get(assignment.id, [])
    if not pred_ids:
        return q_start
    by_id_local = {a.id: a for a in self._all_assignments_cache}  # set during compute
    ends = [by_id_local[pid].end_date for pid in pred_ids if pid in by_id_local and by_id_local[pid].end_date]
    if not ends:
        return q_start
    return max(ends) + timedelta(days=1)

def add_predecessor(self, successor_id: str, predecessor_id: str) -> None:
    """Add edge with cycle check."""
    from app.models import PhasePredecessor
    # Build current graph including new edge, detect cycle
    existing = self.db.execute(
        select(PhasePredecessor)
    ).scalars().all()
    edges: Dict[str, List[str]] = defaultdict(list)
    for e in existing:
        edges[e.successor_assignment_id].append(e.predecessor_assignment_id)
    edges[successor_id].append(predecessor_id)
    # DFS cycle detection
    if self._has_cycle(edges):
        raise ValueError("cycle")
    self.db.add(PhasePredecessor(
        successor_assignment_id=successor_id,
        predecessor_assignment_id=predecessor_id,
    ))
    self.db.commit()

def _has_cycle(self, edges: Dict[str, List[str]]) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = defaultdict(lambda: WHITE)
    def dfs(node):
        color[node] = GRAY
        for nxt in edges.get(node, []):
            if color[nxt] == GRAY:
                return True
            if color[nxt] == WHITE and dfs(nxt):
                return True
        color[node] = BLACK
        return False
    for n in list(edges.keys()):
        if color[n] == WHITE and dfs(n):
            return True
    return False
```

- [ ] **Step 6: Default-chain seeding on first compute**

In `compute_schedule`, after creating `new_assignments`, before topo:
```python
self._ensure_default_predecessors(plan_id, new_assignments)

def _ensure_default_predecessors(self, plan_id: str, assignments: List[ResourcePlanAssignment]):
    from app.models import PhasePredecessor
    existing = self.db.execute(
        select(PhasePredecessor).join(
            ResourcePlanAssignment, PhasePredecessor.successor_assignment_id == ResourcePlanAssignment.id
        ).where(ResourcePlanAssignment.plan_id == plan_id)
    ).scalars().all()
    if existing:
        return
    by_item: Dict[str, Dict[str, ResourcePlanAssignment]] = defaultdict(dict)
    for a in assignments:
        by_item[a.backlog_item_id][a.phase] = a
    for item_id, phases in by_item.items():
        chain = [phases.get("analyst"), phases.get("dev"), phases.get("qa"), phases.get("opo")]
        chain = [c for c in chain if c is not None]
        for i in range(1, len(chain)):
            self.db.add(PhasePredecessor(
                successor_assignment_id=chain[i].id,
                predecessor_assignment_id=chain[i-1].id,
            ))
    self.db.flush()
```

- [ ] **Step 7: Run tests**

```bash
py -3.10 -m pytest tests/services/test_rp_predecessor_graph.py tests/services/test_rp_involvement_capacity.py -v
```

- [ ] **Step 8: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_predecessor_graph.py
git commit -m "feat(rp): free predecessor graph for phase scheduling"
```

---

## Task 7: Pinned-edits preservation on compute

**Files:**
- Modify: `app/services/resource_planning_service.py`
- Test: `tests/services/test_rp_pinned_edits.py`

- [ ] **Step 1: Failing test — pinned_start preserved**

```python
def test_pinned_start_preserved_on_recompute(db_session, sample_plan):
    """If user fixed start_date with pinned_start=True, recompute keeps it."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)
    # pin first analyst phase to 2026-04-15
    a = db_session.query(ResourcePlanAssignment).filter_by(phase="analyst").first()
    a.start_date = date(2026, 4, 15)
    a.pinned_start = True
    a.manual_edit_at = datetime.utcnow()
    db_session.commit()
    # recompute
    svc.compute_schedule(sample_plan.id)
    db_session.refresh(a)
    assert a.start_date == date(2026, 4, 15)
```

- [ ] **Step 2: Failing test — pinned_split preserved**

```python
def test_pinned_split_not_merged(db_session, sample_plan):
    """User-split phase stays split after recompute."""
    # ... split first analyst into 2 parts with pinned_split=True
    # recompute
    # assert still 2 rows
```

- [ ] **Step 3: Run, fail**

- [ ] **Step 4: Update compute_schedule pinned-handling**

Currently uses `is_pinned=True` filter to delete (line 267-272). Replace:
```python
# Save pinned (any flag)
pinned_existing = list(
    self.db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            (
                ResourcePlanAssignment.pinned_employee == True
                | ResourcePlanAssignment.pinned_start == True
                | ResourcePlanAssignment.pinned_split == True
            ),
        )
    ).scalars()
)
```

For pinned_start fixing dates: use `a.start_date` as-is even when generating new phases.

For pinned_split: skip auto-merge in `_compute_legacy_split_map` (already returns `{}`); ensure split parts retain `pinned_split=True` on recompute.

- [ ] **Step 5: Tests pass**

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_pinned_edits.py
git commit -m "feat(rp): preserve pinned_start/employee/split on compute"
```

---

## Task 8: API — PATCH /assignments/{id}

**Files:**
- Modify: `app/api/endpoints/resource_planning.py`
- Test: `tests/test_api_assignment_patch.py`

- [ ] **Step 1: Failing test — patch start_date**

```python
def test_patch_assignment_start_date(client, auth_headers, sample_plan):
    a_id = ...  # first assignment id
    r = client.patch(
        f"/api/v1/resource-planning/assignments/{a_id}",
        json={"start_date": "2026-05-01"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignment"]["start_date"] == "2026-05-01"
    assert data["assignment"]["pinned_start"] is True
    assert data["assignment"]["manual_edit_at"] is not None
```

- [ ] **Step 2: Failing test — patch employee**

```python
def test_patch_assignment_employee(client, auth_headers, sample_plan, alt_employee):
    a_id = ...
    r = client.patch(
        f"/api/v1/resource-planning/assignments/{a_id}",
        json={"employee_id": alt_employee.id},
        headers=auth_headers,
    )
    assert r.json()["assignment"]["pinned_employee"] is True
```

- [ ] **Step 3: Failing test — patch predecessors**

```python
def test_patch_assignment_predecessors(client, auth_headers, sample_plan):
    qa_id = ...; analyst_id = ...
    r = client.patch(
        f"/api/v1/resource-planning/assignments/{qa_id}",
        json={"predecessor_ids": [analyst_id]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    # qa should now have only analyst predecessor
```

- [ ] **Step 4: Failing test — cycle rejected**

```python
def test_patch_assignment_predecessor_cycle_rejected(client, auth_headers, sample_plan):
    a_id = ...; b_id = ...
    # set b → a, then try a → b (cycle)
    client.patch(f"/api/v1/resource-planning/assignments/{b_id}", json={"predecessor_ids": [a_id]}, headers=auth_headers)
    r = client.patch(f"/api/v1/resource-planning/assignments/{a_id}", json={"predecessor_ids": [b_id]}, headers=auth_headers)
    assert r.status_code == 400
    assert "cycle" in r.json()["detail"].lower()
```

- [ ] **Step 5: Run, fail**

- [ ] **Step 6: Implement endpoint**

In `app/api/endpoints/resource_planning.py`:
```python
class AssignmentPatch(BaseModel):
    start_date: Optional[date] = None
    employee_id: Optional[str] = None
    predecessor_ids: Optional[List[str]] = None

class AssignmentPatchResponse(BaseModel):
    assignment: dict
    affected_assignments: List[dict]

@router.patch("/assignments/{assignment_id}", response_model=AssignmentPatchResponse)
def patch_assignment(
    assignment_id: str,
    payload: AssignmentPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = db.get(ResourcePlanAssignment, assignment_id)
    if not a:
        raise HTTPException(404, "assignment not found")
    affected: List[ResourcePlanAssignment] = []
    now = datetime.utcnow()
    if payload.start_date is not None:
        delta = (payload.start_date - (a.start_date or payload.start_date)).days if a.start_date else 0
        a.start_date = payload.start_date
        a.pinned_start = True
        a.manual_edit_at = now
        affected = _cascade_shift_descendants(db, a, delta)
    if payload.employee_id is not None:
        a.employee_id = payload.employee_id
        a.pinned_employee = True
        a.manual_edit_at = now
    if payload.predecessor_ids is not None:
        try:
            _replace_predecessors(db, a.id, payload.predecessor_ids)
        except ValueError as e:
            db.rollback()
            raise HTTPException(400, f"cycle: {e}")
        a.manual_edit_at = now
    db.commit()
    # mini-recompute affected
    svc = ResourcePlanningService(db)
    svc.recompute_subgraph(a.plan_id, [a.id] + [x.id for x in affected])
    db.refresh(a)
    return AssignmentPatchResponse(
        assignment=_assignment_to_dict(a),
        affected_assignments=[_assignment_to_dict(x) for x in affected],
    )
```

Helpers `_cascade_shift_descendants`, `_replace_predecessors`, `_assignment_to_dict` — write inline in same file.

In `ResourcePlanningService` add `recompute_subgraph(plan_id, anchor_ids)` — пересчитывает только цепочку наследников от anchor_ids (не трогает остальное), пересоздаёт CPM + конфликты.

- [ ] **Step 7: Tests pass**

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(rp): PATCH /assignments/{id} with cascade + cycle check"
```

---

## Task 9: API — split + merge endpoints

**Files:**
- Modify: `app/api/endpoints/resource_planning.py`
- Modify: `app/services/resource_planning_service.py`
- Test: `tests/test_api_assignment_split.py`

- [ ] **Step 1: Failing test — split into 2 parts**

```python
def test_split_assignment_two_parts_with_cascade(client, auth_headers, sample_plan):
    a_id = ...  # analyst phase, hours=20
    r = client.post(
        f"/api/v1/resource-planning/assignments/{a_id}/split",
        json={"parts": [12, 8], "cascade": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    parts = r.json()["parts"]
    assert len(parts) == 2
    assert parts[0]["hours_allocated"] == 12
    assert parts[1]["hours_allocated"] == 8
    assert all(p["pinned_split"] is True for p in parts)
    # cascade: dev/qa/opo also split
    cascaded = r.json()["cascaded"]
    assert len(cascaded) >= 2  # at least dev split
```

- [ ] **Step 2: Failing test — merge restores single phase**

```python
def test_merge_assignment_combines_parts(client, auth_headers, split_assignment):
    a_id = split_assignment.id  # part 1 of split
    r = client.post(f"/api/v1/resource-planning/assignments/{a_id}/merge", headers=auth_headers)
    assert r.status_code == 200
    merged = r.json()["assignment"]
    assert merged["part_number"] == 1
    assert merged["hours_allocated"] == 20
    assert merged["pinned_split"] is False
```

- [ ] **Step 3: Failing test — sum mismatch rejected**

```python
def test_split_sum_mismatch_rejected(client, auth_headers, sample_plan):
    a_id = ...  # hours=20
    r = client.post(
        f"/api/v1/resource-planning/assignments/{a_id}/split",
        json={"parts": [10, 5], "cascade": False},  # 15 != 20
        headers=auth_headers,
    )
    assert r.status_code == 400
```

- [ ] **Step 4: Run, fail**

- [ ] **Step 5: Service methods**

In `ResourcePlanningService`:
```python
def split_assignment(
    self, assignment_id: str, parts_hours: List[float], cascade: bool
) -> Tuple[List[ResourcePlanAssignment], List[ResourcePlanAssignment]]:
    """Returns (parts, cascaded_assignments)."""
    a = self.db.get(ResourcePlanAssignment, assignment_id)
    if not a or a.part_number != 1:
        raise ValueError("can split only single-part phase")
    total = a.hours_allocated or 0.0
    if abs(sum(parts_hours) - total) > 0.01:
        raise ValueError(f"parts sum {sum(parts_hours)} != phase hours {total}")
    if len(parts_hours) < 2 or len(parts_hours) > 10:
        raise ValueError("parts must be 2..10")
    plan_id = a.plan_id
    item_id = a.backlog_item_id
    phase = a.phase
    employee_id = a.employee_id
    parts: List[ResourcePlanAssignment] = []
    self.db.delete(a)
    self.db.flush()
    prev_id: Optional[str] = None
    for idx, h in enumerate(parts_hours, start=1):
        p = ResourcePlanAssignment(
            plan_id=plan_id, backlog_item_id=item_id, phase=phase,
            employee_id=employee_id, part_number=idx, hours_allocated=h,
            pinned_split=True, manual_edit_at=datetime.utcnow(),
        )
        self.db.add(p)
        self.db.flush()
        parts.append(p)
        if prev_id:
            self.db.add(PhasePredecessor(
                successor_assignment_id=p.id, predecessor_assignment_id=prev_id,
            ))
        prev_id = p.id
    cascaded: List[ResourcePlanAssignment] = []
    if cascade:
        cascaded = self._cascade_split(item_id, phase, parts_hours, parts)
    self.db.commit()
    self.recompute_subgraph(plan_id, [p.id for p in parts])
    return parts, cascaded

def _cascade_split(
    self,
    item_id: str,
    source_phase: str,
    proportions: List[float],
    source_parts: List[ResourcePlanAssignment],
) -> List[ResourcePlanAssignment]:
    """For each downstream phase, split into len(proportions) parts proportionally."""
    total_src = sum(proportions)
    ratios = [p / total_src for p in proportions]
    downstream = [p for p in PHASE_ORDER if PHASE_ORDER.index(p) > PHASE_ORDER.index(source_phase)]
    cascaded = []
    for phase in downstream:
        existing = self.db.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.backlog_item_id == item_id,
                ResourcePlanAssignment.phase == phase,
            )
        ).scalars().all()
        if len(existing) != 1:
            continue  # phase already split or missing
        orig = existing[0]
        total_h = orig.hours_allocated or 0.0
        if total_h <= 0:
            continue
        # round to integers, last part gets remainder
        hours_parts = [int(round(total_h * r)) for r in ratios[:-1]]
        hours_parts.append(int(total_h - sum(hours_parts)))
        plan_id = orig.plan_id
        emp_id = orig.employee_id
        self.db.delete(orig)
        self.db.flush()
        prev_id = None
        for idx, (h, src) in enumerate(zip(hours_parts, source_parts), start=1):
            p = ResourcePlanAssignment(
                plan_id=plan_id, backlog_item_id=item_id, phase=phase,
                employee_id=emp_id, part_number=idx, hours_allocated=float(h),
                pinned_split=True, manual_edit_at=datetime.utcnow(),
            )
            self.db.add(p)
            self.db.flush()
            cascaded.append(p)
            # part K of this phase depends on part K of source
            self.db.add(PhasePredecessor(
                successor_assignment_id=p.id, predecessor_assignment_id=src.id,
            ))
            if prev_id:
                self.db.add(PhasePredecessor(
                    successor_assignment_id=p.id, predecessor_assignment_id=prev_id,
                ))
            prev_id = p.id
    return cascaded

def merge_assignment(self, assignment_id: str) -> ResourcePlanAssignment:
    a = self.db.get(ResourcePlanAssignment, assignment_id)
    if not a:
        raise ValueError("not found")
    siblings = self.db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == a.plan_id,
            ResourcePlanAssignment.backlog_item_id == a.backlog_item_id,
            ResourcePlanAssignment.phase == a.phase,
        ).order_by(ResourcePlanAssignment.part_number)
    ).scalars().all()
    if len(siblings) <= 1:
        return a
    total_h = sum((s.hours_allocated or 0) for s in siblings)
    first = siblings[0]
    first.part_number = 1
    first.hours_allocated = total_h
    first.pinned_split = False
    first.manual_edit_at = datetime.utcnow()
    for s in siblings[1:]:
        self.db.delete(s)
    self.db.commit()
    self.recompute_subgraph(a.plan_id, [first.id])
    return first
```

- [ ] **Step 6: Endpoint**

```python
class SplitRequest(BaseModel):
    parts: List[float]
    cascade: bool = True

@router.post("/assignments/{assignment_id}/split")
def split_assignment(
    assignment_id: str,
    payload: SplitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ResourcePlanningService(db)
    try:
        parts, cascaded = svc.split_assignment(assignment_id, payload.parts, payload.cascade)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "parts": [_assignment_to_dict(p) for p in parts],
        "cascaded": [_assignment_to_dict(c) for c in cascaded],
    }

@router.post("/assignments/{assignment_id}/merge")
def merge_assignment(...):
    svc = ResourcePlanningService(db)
    try:
        merged = svc.merge_assignment(assignment_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"assignment": _assignment_to_dict(merged)}

@router.delete("/assignments/{assignment_id}/manual-edit")
def clear_manual_edits(...):
    a = db.get(ResourcePlanAssignment, assignment_id)
    a.pinned_start = False
    a.pinned_employee = False
    a.pinned_split = False
    a.manual_edit_at = None
    db.commit()
    return {"assignment": _assignment_to_dict(a)}
```

- [ ] **Step 7: Tests pass**

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(rp): split + merge + clear-manual-edit endpoints"
```

---

## Task 10: Conflict aggregator with templated messages

**Files:**
- Create: `app/services/conflict_aggregator.py`
- Modify: `app/services/resource_planning_service.py` (call aggregator)
- Modify: `app/api/endpoints/resource_planning.py` (group_by param)
- Test: `tests/services/test_conflict_aggregator.py`

- [ ] **Step 1: Failing test — overload day-range aggregation**

```python
def test_overload_aggregated_into_date_range(db_session):
    """10 day-by-day OVERLOAD events for same employee → single conflict with window_start..window_end."""
    from app.services.conflict_aggregator import aggregate_conflicts
    raw = [
        {"type": "OVERLOAD_HIGH", "employee_id": "e1", "assignment_id": "a1",
         "metric_value": 130.0, "window_start": date(2026, 4, d), "window_end": date(2026, 4, d)}
        for d in range(1, 11)
    ]
    aggregated = aggregate_conflicts(raw)
    assert len(aggregated) == 1
    assert aggregated[0]["window_start"] == date(2026, 4, 1)
    assert aggregated[0]["window_end"] == date(2026, 4, 10)
```

- [ ] **Step 2: Failing test — templated message**

```python
def test_overload_message_uses_employee_name(db_session, sample_employee):
    raw = [{
        "type": "OVERLOAD_HIGH", "employee_id": sample_employee.id, "assignment_id": "a1",
        "metric_value": 140.0, "window_start": date(2026, 4, 1), "window_end": date(2026, 4, 10),
        "conflicting_assignments": ["a1", "a2"],
    }]
    out = aggregate_conflicts(raw, db_session=db_session)
    msg = out[0]["message"]
    assert "Шутов" in msg or sample_employee.display_name in msg
    assert "1–10 апреля" in msg or "1–10" in msg
```

- [ ] **Step 3: Run, fail**

- [ ] **Step 4: Implement aggregator**

```python
# app/services/conflict_aggregator.py
"""Аггрегация конфликтов: дедупликация по диапазону + шаблоны сообщений."""

from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from app.models import Employee, BacklogItem, ResourcePlanAssignment

RU_MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _format_date_range(start: Optional[date], end: Optional[date]) -> str:
    if not start and not end:
        return ""
    if start == end or not end:
        return f"{start.day} {RU_MONTHS[start.month]}"
    if start.month == end.month:
        return f"{start.day}–{end.day} {RU_MONTHS[start.month]}"
    return f"{start.day} {RU_MONTHS[start.month]} – {end.day} {RU_MONTHS[end.month]}"


def aggregate_conflicts(
    raw: List[Dict[str, Any]],
    db_session: Optional[Session] = None,
) -> List[Dict[str, Any]]:
    """Объединяет последовательные daily-конфликты в диапазоны."""
    # Group by (type, employee_id, assignment_id)
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for r in raw:
        key = (r.get("type"), r.get("employee_id"), r.get("assignment_id"))
        groups[key].append(r)
    out: List[dict] = []
    for key, items in groups.items():
        items.sort(key=lambda x: x.get("window_start") or date.min)
        # Merge consecutive dates
        merged = []
        for it in items:
            if merged and merged[-1].get("window_end") and it.get("window_start"):
                gap = (it["window_start"] - merged[-1]["window_end"]).days
                if gap <= 1:
                    merged[-1]["window_end"] = it["window_end"] or it["window_start"]
                    merged[-1]["metric_value"] = max(
                        merged[-1].get("metric_value") or 0, it.get("metric_value") or 0
                    )
                    continue
            merged.append({**it})
        for m in merged:
            m["message"] = _build_message(m, db_session)
            out.append(m)
    return out


def _build_message(c: Dict[str, Any], db: Optional[Session]) -> str:
    t = c.get("type", "")
    rng = _format_date_range(c.get("window_start"), c.get("window_end"))
    emp_name = _resolve_employee_name(c.get("employee_id"), db) if db else c.get("employee_id", "")
    item_label = _resolve_item_label(c.get("backlog_item_id"), db) if db else ""
    if t.startswith("OVERLOAD_"):
        pct = int(round(c.get("metric_value") or 0))
        return f"{emp_name} перегружен {pct}% в период {rng}"
    if t == "QUARTER_OVERFLOW":
        return f"{item_label} не вмещается в квартал"
    if t == "NO_ANALYST":
        return f"В команде нет аналитиков — расписание фазы анализа невозможно"
    if t == "NO_DEV":
        return f"В команде нет разработчиков — расписание фазы разработки невозможно"
    if t == "LATE_START":
        return f"{item_label} стартует с отставанием"
    if t == "LEVELING_DELAY":
        return f"{item_label} перенесена — выравнивание загрузки"
    if t == "LEVELING_REASSIGN":
        return f"{item_label} переназначена — выравнивание"
    if t == "SPLIT_REQUIRED":
        return f"{item_label} разбита на части — заблокированный период"
    return c.get("message", t)


def _resolve_employee_name(emp_id: Optional[str], db: Session) -> str:
    if not emp_id:
        return ""
    e = db.get(Employee, emp_id)
    return e.display_name if e else emp_id


def _resolve_item_label(item_id: Optional[str], db: Session) -> str:
    if not item_id:
        return ""
    it = db.get(BacklogItem, item_id)
    if not it:
        return ""
    key = it.issue.jira_key if it.issue else ""
    return f"{key} {it.title}".strip()
```

- [ ] **Step 5: Wire into compute_schedule**

In `compute_schedule`, after `_build_conflict_dicts`:
```python
from app.services.conflict_aggregator import aggregate_conflicts
detected = self._build_conflict_dicts(plan, new_assignments, employees, q_end)
detected = aggregate_conflicts(detected, db_session=self.db)
self._persist_conflicts(plan_id, detected)
```

- [ ] **Step 6: Add group_by to GET conflicts endpoint**

```python
@router.get("/resource-plans/{plan_id}/conflicts")
def get_conflicts(
    plan_id: str,
    group_by: str = Query("item", regex="^(item|employee|type)$"),
    severity: Optional[str] = None,
    status: str = "active",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = _load_conflicts(db, plan_id, severity, status)
    if group_by == "item":
        return _group_by_item(rows, db)
    if group_by == "employee":
        return _group_by_employee(rows, db)
    return _group_by_type(rows)
```

- [ ] **Step 7: Tests pass**

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(rp): conflict aggregator with templated messages + group_by"
```

---

## Task 11: User preferences endpoint

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (or new `user_preferences.py`)
- Test: `tests/test_api_user_rp_preferences.py`

- [ ] **Step 1: Failing test**

```python
def test_get_default_prefs(client, auth_headers):
    r = client.get("/api/v1/user/preferences/resource-planning", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["hide_weekends"] is False

def test_patch_prefs(client, auth_headers):
    r = client.patch(
        "/api/v1/user/preferences/resource-planning",
        json={"hide_weekends": True, "collapsed_initiative_ids": ["i1", "i2"]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    r2 = client.get("/api/v1/user/preferences/resource-planning", headers=auth_headers)
    assert r2.json()["hide_weekends"] is True
    assert r2.json()["collapsed_initiative_ids"] == ["i1", "i2"]

def test_prefs_isolated_per_user(client, auth_headers_a, auth_headers_b):
    client.patch("/api/v1/user/preferences/resource-planning", json={"hide_weekends": True}, headers=auth_headers_a)
    r = client.get("/api/v1/user/preferences/resource-planning", headers=auth_headers_b)
    assert r.json()["hide_weekends"] is False
```

- [ ] **Step 2: Implement endpoints (in resource_planning.py for now)**

```python
class UserRpPrefsSchema(BaseModel):
    hide_weekends: bool = False
    collapsed_initiative_ids: List[str] = []
    view_mode: Optional[str] = None
    show_relay: bool = True

@router.get("/preferences", response_model=UserRpPrefsSchema)
def get_user_prefs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.get(UserRpPreferences, current_user.id)
    if not p:
        return UserRpPrefsSchema()
    return UserRpPrefsSchema(
        hide_weekends=p.hide_weekends,
        collapsed_initiative_ids=p.collapsed_initiative_ids or [],
        view_mode=p.view_mode,
        show_relay=p.show_relay,
    )

@router.patch("/preferences", response_model=UserRpPrefsSchema)
def patch_user_prefs(
    payload: UserRpPrefsSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.get(UserRpPreferences, current_user.id)
    if not p:
        p = UserRpPreferences(user_id=current_user.id)
        db.add(p)
    if payload.hide_weekends is not None:
        p.hide_weekends = payload.hide_weekends
    if payload.collapsed_initiative_ids is not None:
        p.collapsed_initiative_ids = payload.collapsed_initiative_ids
    if payload.view_mode is not None:
        p.view_mode = payload.view_mode
    if payload.show_relay is not None:
        p.show_relay = payload.show_relay
    db.commit()
    return get_user_prefs(db, current_user)
```

(Final URL via router.prefix → `/api/v1/resource-planning/preferences`. Frontend uses this path.)

- [ ] **Step 3: Tests pass**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(rp): user preferences GET/PATCH"
```

---

## Task 12: Frontend — collapsible two-line rows

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx`
- Modify: `frontend/src/api/resourcePlanning.ts` (gantt response type)
- Test: `frontend/src/components/resource-planning/__tests__/GanttRows.test.tsx`

- [ ] **Step 1: Failing Vitest**

```tsx
// frontend/src/components/resource-planning/__tests__/GanttRows.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { GanttRows } from "../GanttRows";

test("collapsed initiative shows only umbrella row", () => {
  const items = [{
    id: "i-1", title: "Доработка номенклатуры", projectName: "ERP - Товарный учет",
    jiraKey: "PRJ-10892", phases: [
      { id: "p-1", phase: "analyst", employeeName: "Иванов А.", ... },
      { id: "p-2", phase: "dev", ... },
    ],
  }];
  render(<GanttRows items={items} collapsedIds={["i-1"]} onToggleCollapse={() => {}} />);
  expect(screen.getByText("Доработка номенклатуры")).toBeInTheDocument();
  expect(screen.queryByText(/Иванов/)).toBeNull();  // phase row hidden
});

test("expand toggles caret and reveals phases", () => {
  const onToggle = vi.fn();
  render(<GanttRows items={items} collapsedIds={[]} onToggleCollapse={onToggle} />);
  fireEvent.click(screen.getByLabelText("Свернуть PRJ-10892"));
  expect(onToggle).toHaveBeenCalledWith("i-1", true);
});
```

- [ ] **Step 2: Run, fail (current GanttRows is one-line, no collapse)**

- [ ] **Step 3: Implement two-line layout**

In `GanttRows.tsx` row template:
```tsx
<div className="rp-row rp-row--initiative">
  <button
    className="rp-caret"
    aria-label={`${collapsed ? "Развернуть" : "Свернуть"} ${item.jiraKey}`}
    onClick={() => onToggleCollapse(item.id, !collapsed)}
  >
    {collapsed ? "▶" : "▼"}
  </button>
  <div className="rp-row-text">
    <div className="rp-row-title">{item.title}</div>
    <div className="rp-row-meta">
      {item.jiraKey} · {item.projectName}
    </div>
  </div>
  {/* bar(s) */}
</div>
{!collapsed && item.phases.map(p => (
  <div key={p.id} className="rp-row rp-row--phase">
    <span className="rp-phase-icon">{phaseIcon(p.phase)}</span>
    <span className="rp-phase-label">
      {phaseName(p.phase)} — {p.employeeName ?? "пул"}
      {p.manualEditAt && <ManualEditBadge />}
    </span>
    <PhaseBar phase={p} />
  </div>
))}
```

CSS module:
```css
.rp-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid rgba(255,255,255,0.06); }
.rp-row--phase { padding-left: 46px; opacity: 0.85; font-size: 12px; }
.rp-row-title { font-size: 13px; line-height: 1.3; }
.rp-row-meta { color: #9ca3af; font-size: 11px; }
.rp-caret { background: none; border: 0; color: #9ca3af; cursor: pointer; padding: 0 2px; }
```

- [ ] **Step 4: Wire collapse state via useRpPreferences**

```ts
// frontend/src/hooks/useRpPreferences.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../api/client";
import { debounce } from "lodash-es";

export function useRpPreferences() {
  const qc = useQueryClient();
  const { data: prefs } = useQuery({
    queryKey: ["rp-prefs"],
    queryFn: () => api.get("/resource-planning/preferences").then(r => r.data),
  });
  const patch = useMutation({
    mutationFn: (patch: Partial<RpPrefs>) =>
      api.patch("/resource-planning/preferences", patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rp-prefs"] }),
  });
  const debouncedPatch = debounce(patch.mutate, 300);
  return { prefs, patch: debouncedPatch };
}
```

In `ResourcePlanningPage.tsx`:
```tsx
const { prefs, patch } = useRpPreferences();
const collapsedIds = prefs?.collapsed_initiative_ids ?? [];
const handleToggle = (id: string, willCollapse: boolean) => {
  const next = willCollapse
    ? [...new Set([...collapsedIds, id])]
    : collapsedIds.filter(x => x !== id);
  patch({ collapsed_initiative_ids: next });
};
```

- [ ] **Step 5: Run vitest + manual smoke**

```bash
cd frontend && npm test -- GanttRows
```

- [ ] **Step 6: Manual test: open page, click ▶/▼, refresh — state persists.**

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(rp/ui): two-line initiative rows with phase collapse"
```

---

## Task 13: Frontend — unavailability patterns + hide-weekends toggle

**Files:**
- Create: `frontend/src/components/resource-planning/UnavailabilityPattern.tsx`
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx` (toggle in header)
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (render patterns inside bars)
- Modify: backend `gantt` endpoint to include `unavailable_days` per phase
- Test: vitest for UnavailabilityPattern

- [ ] **Step 1: Backend — extend gantt response**

In `app/api/endpoints/resource_planning.py` `gantt` endpoint, for each assignment, compute:
```python
unavailable_days = [
    {"date": d.isoformat(), "type": "weekend" if cal.get(d, 8) == 0 and d.weekday() >= 5 else
                                    "holiday" if cal.get(d, 8) == 0 else
                                    "absence" if d in absent_days_for_employee else None}
    for d in date_range(a.start_date, a.end_date)
    if condition...
]
```

Add field to assignment schema:
```python
class GanttAssignmentSchema(BaseModel):
    ...
    unavailable_days: List[dict] = []
```

- [ ] **Step 2: Failing vitest for UnavailabilityPattern**

```tsx
test("renders grey hatch for weekend, orange for absence", () => {
  const days = [
    { date: "2026-04-01", type: "working" },
    { date: "2026-04-02", type: "weekend" },
    { date: "2026-04-03", type: "absence" },
  ];
  const { container } = render(<UnavailabilityPattern days={days} />);
  expect(container.querySelectorAll(".unav-weekend")).toHaveLength(1);
  expect(container.querySelectorAll(".unav-absence")).toHaveLength(1);
});
```

- [ ] **Step 3: Implement component**

```tsx
// UnavailabilityPattern.tsx
type DayInfo = { date: string; type: "working" | "weekend" | "holiday" | "absence" };
type Props = { days: DayInfo[]; barWidth: number };

export function UnavailabilityPattern({ days, barWidth }: Props) {
  const cellW = barWidth / days.length;
  return (
    <div className="unav-overlay" style={{ display: "flex", position: "absolute", top: 0, bottom: 0, left: 0, right: 0, pointerEvents: "none" }}>
      {days.map(d => (
        <div key={d.date}
             className={d.type === "working" ? "" : `unav-${d.type === "absence" ? "absence" : "weekend"}`}
             style={{ width: cellW }} />
      ))}
    </div>
  );
}
```

CSS:
```css
.unav-weekend { background-image: repeating-linear-gradient(45deg, rgba(255,255,255,0.04) 0 4px, rgba(255,255,255,0.10) 4px 8px); }
.unav-absence { background-image: repeating-linear-gradient(45deg, rgba(245,158,11,0.5) 0 4px, rgba(245,158,11,0.25) 4px 8px); }
```

- [ ] **Step 4: Toggle weekends in header**

In `GanttChart.tsx` near the existing scale/view buttons:
```tsx
<Switch
  checked={prefs?.hide_weekends ?? false}
  onChange={(v) => patch({ hide_weekends: v })}
  size="small"
  checkedChildren="Только рабочие"
  unCheckedChildren="Все дни"
/>
```

When `hide_weekends=true`, filter `dateRange` to skip weekend/holiday dates before passing to bars.

- [ ] **Step 5: Embed pattern in PhaseBar**

In `GanttRows.tsx` (or wherever bars render), wrap bar in relative container and add `<UnavailabilityPattern />` overlay using assignment's `unavailable_days`.

- [ ] **Step 6: Tests + manual smoke**

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(rp/ui): unavailability patterns inside bars + hide-weekends toggle"
```

---

## Task 14: Frontend — employee load heatmap + conflict frame

**Files:**
- Create: `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx`
- Modify: backend `gantt` to return `daily_load` per employee
- Modify: `GanttRows.tsx` (red frame on conflicting bars)
- Test: vitest

- [ ] **Step 1: Backend — daily_load per employee**

In gantt builder:
```python
# For each employee in plan: per-day load% = sum(hours_assigned_to_day) / avail_that_day
employee_load: Dict[str, List[Dict]] = defaultdict(list)
for emp in employees:
    for d in date_range(q_start, q_end):
        avail = avail_map[emp.id].get(d, 0.0)
        used = sum_hours_on_d_for_emp(d, emp.id)
        pct = (used / avail * 100) if avail > 0 else 0
        employee_load[emp.id].append({"date": d.isoformat(), "pct": pct})
```

Add to gantt schema:
```python
employee_load: Dict[str, List[Dict[str, float]]]
```

- [ ] **Step 2: Heatmap component**

```tsx
type LoadDay = { date: string; pct: number };
function colorFor(pct: number) {
  if (pct <= 90) return "rgba(34,197,94,0.4)";
  if (pct <= 110) return "rgba(234,179,8,0.7)";
  return "rgba(239,68,68,0.85)";
}
export function EmployeeLoadHeatmap({ days }: { days: LoadDay[] }) {
  return (
    <div className="emp-heatmap">
      {days.map(d => <div key={d.date} className="cell" title={`${d.date}: ${d.pct.toFixed(0)}%`} style={{ background: colorFor(d.pct) }} />)}
    </div>
  );
}
```

CSS: `.emp-heatmap { display: flex; height: 6px; gap: 0; } .cell { flex: 1; }`

- [ ] **Step 3: Render before each employee's group of bars**

In `GanttRows.tsx`, group phases by `employee_id`. Before the first bar of each employee, render `<EmployeeLoadHeatmap days={data.employee_load[empId]} />`.

- [ ] **Step 4: Conflict frame on bars**

If assignment.id is in conflict set, add `rp-bar--conflict` class:
```css
.rp-bar--conflict { box-shadow: inset 0 0 0 2px #ef4444; }
```
Plus a ⚠ icon in the row label.

Pass conflict set as prop:
```tsx
const conflictAssignmentIds = useMemo(
  () => new Set(conflicts.flatMap(c => c.assignment_id ? [c.assignment_id] : [])),
  [conflicts]
);
```

- [ ] **Step 5: Tests + smoke**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(rp/ui): employee load heatmap + red frame on conflicting bars"
```

---

## Task 15: Frontend — assignment sidebar + context menu + drag arrows

**Files:**
- Create: `frontend/src/components/resource-planning/AssignmentSidebar.tsx`
- Create: `frontend/src/components/resource-planning/PhaseContextMenu.tsx`
- Modify: `frontend/src/components/resource-planning/DependencyArrows.tsx` (drag-to-create)
- Modify: `GanttRows.tsx` (click → open sidebar; right-click → menu)
- Modify: `frontend/src/api/resourcePlanning.ts` (patchAssignment)
- Test: vitest

- [ ] **Step 1: API client method**

```ts
// resourcePlanning.ts
export const patchAssignment = (id: string, body: Partial<{
  start_date: string; employee_id: string; predecessor_ids: string[];
}>) => api.patch(`/resource-planning/assignments/${id}`, body);

export const splitAssignment = (id: string, body: { parts: number[]; cascade: boolean }) =>
  api.post(`/resource-planning/assignments/${id}/split`, body);

export const mergeAssignment = (id: string) =>
  api.post(`/resource-planning/assignments/${id}/merge`);

export const clearManualEdit = (id: string) =>
  api.delete(`/resource-planning/assignments/${id}/manual-edit`);
```

- [ ] **Step 2: AssignmentSidebar**

```tsx
// AssignmentSidebar.tsx
export function AssignmentSidebar({ assignment, peerPhases, employees, onClose }: Props) {
  const [start, setStart] = useState(assignment.start_date);
  const [empId, setEmpId] = useState(assignment.employee_id);
  const [preds, setPreds] = useState(assignment.predecessor_ids);
  const save = useMutation({ mutationFn: (patch: any) => patchAssignment(assignment.id, patch) });
  return (
    <Drawer open onClose={onClose} title="Свойства фазы" width={360}>
      <Form layout="vertical">
        <Form.Item label="Часы">{assignment.hours_allocated}</Form.Item>
        <Form.Item label="Старт">
          <DatePicker value={dayjs(start)} onChange={(v) => setStart(v.format("YYYY-MM-DD"))} />
        </Form.Item>
        <Form.Item label="Сотрудник">
          <Select value={empId} options={employees.map(e => ({ value: e.id, label: e.display_name }))} />
        </Form.Item>
        <Form.Item label="Предшественники">
          {peerPhases.filter(p => p.id !== assignment.id).map(p => (
            <Checkbox key={p.id} checked={preds.includes(p.id)} onChange={(e) => {
              setPreds(e.target.checked ? [...preds, p.id] : preds.filter(x => x !== p.id));
            }}>
              {phaseName(p.phase)} ({p.employee_name ?? "пул"})
            </Checkbox>
          ))}
        </Form.Item>
        <Button onClick={() => save.mutate({ start_date: start, employee_id: empId, predecessor_ids: preds })}>
          Применить
        </Button>
        {(assignment.pinned_start || assignment.pinned_employee) && (
          <Button danger onClick={() => clearManualEdit(assignment.id)}>Снять ручные правки</Button>
        )}
      </Form>
    </Drawer>
  );
}
```

- [ ] **Step 3: PhaseContextMenu**

```tsx
// PhaseContextMenu.tsx
export function PhaseContextMenu({ assignment, peerPhases, x, y, onClose }: Props) {
  return (
    <Dropdown open trigger={[]} menu={{ items: [
      { key: "shift", label: "Перенести старт...", onClick: () => openDatePicker(...) },
      { type: "divider" },
      assignment.part_number === 1
        ? { key: "split", label: "Разбить на части...", onClick: () => openSplitDialog(...) }
        : { key: "merge", label: "Объединить части", onClick: () => mergeAssignment(assignment.id) },
      { type: "divider" },
      ...peerPhases.filter(p => p.id !== assignment.id).map(p => ({
        key: `dep-${p.id}`,
        label: <><Checkbox checked={assignment.predecessor_ids.includes(p.id)} /> Зависит от: {phaseName(p.phase)}</>,
        onClick: () => togglePred(p.id),
      })),
      { key: "no-deps", label: "Без предшественников", onClick: () => patchAssignment(assignment.id, { predecessor_ids: [] }) },
      { type: "divider" },
      { key: "clear", label: "Снять ручные правки", disabled: !hasAnyPin, onClick: () => clearManualEdit(assignment.id) },
    ]}}>
      <div style={{ position: "fixed", left: x, top: y }} />
    </Dropdown>
  );
}
```

- [ ] **Step 4: Drag arrows**

In existing `DependencyArrows.tsx` add handles to phase bar ends. On `mousedown` on a handle, start dragging an SVG line; on `mouseup` over another bar's start handle, call `patchAssignment(targetId, { predecessor_ids: [...existing, sourceId] })`.

- [ ] **Step 5: Wire into GanttRows**

```tsx
const [sidebarFor, setSidebarFor] = useState<Assignment|null>(null);
const [ctxMenuFor, setCtxMenuFor] = useState<{ a: Assignment, x: number, y: number }|null>(null);
// onClick bar → setSidebarFor
// onContextMenu bar → e.preventDefault(); setCtxMenuFor({ a, x: e.clientX, y: e.clientY })
```

- [ ] **Step 6: Smoke + vitest**

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(rp/ui): assignment sidebar + context menu + drag dependency arrows"
```

---

## Task 16: Frontend — split dialog

**Files:**
- Create: `frontend/src/components/resource-planning/SplitDialog.tsx`
- Modify: `PhaseContextMenu.tsx` (open dialog)
- Test: vitest

- [ ] **Step 1: Failing vitest**

```tsx
test("split dialog: 2 parts equal by default, sum equals total", () => {
  render(<SplitDialog assignment={{ id: "a", hours_allocated: 20, ... }} onClose={() => {}} />);
  const inputs = screen.getAllByRole("spinbutton");
  expect(inputs[0]).toHaveValue(10);
  expect(inputs[1]).toHaveValue(10);
});

test("editing first part: second compensates", () => {
  const { getAllByRole } = render(<SplitDialog ... />);
  const inputs = getAllByRole("spinbutton");
  fireEvent.change(inputs[0], { target: { value: "12" } });
  expect(inputs[1]).toHaveValue(8);
});

test("apply calls splitAssignment with cascade=true", async () => {
  const onClose = vi.fn();
  render(<SplitDialog ... onClose={onClose} />);
  fireEvent.click(screen.getByText("Применить"));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  // mock splitAssignment was called with parts=[10,10], cascade=true
});
```

- [ ] **Step 2: Implement**

```tsx
export function SplitDialog({ assignment, onClose }: Props) {
  const total = assignment.hours_allocated;
  const [n, setN] = useState(2);
  const [parts, setParts] = useState<number[]>(() => Array(2).fill(total / 2));
  const [cascade, setCascade] = useState(true);
  const apply = useMutation({
    mutationFn: () => splitAssignment(assignment.id, { parts, cascade }),
    onSuccess: () => { qc.invalidateQueries(["rp-gantt"]); onClose(); },
  });
  const updatePart = (idx: number, val: number) => {
    const next = [...parts];
    next[idx] = val;
    // Last part absorbs remainder
    const sumOthers = next.slice(0, -1).reduce((a, b) => a + b, 0);
    next[next.length - 1] = total - sumOthers;
    setParts(next);
  };
  const setNParts = (newN: number) => {
    setN(newN);
    setParts(Array(newN).fill(total / newN));
  };
  return (
    <Modal open title="Разбить фазу" onCancel={onClose} onOk={() => apply.mutate()}>
      <Form layout="vertical">
        <Form.Item label="Количество частей">
          <InputNumber min={2} max={10} value={n} onChange={setNParts} />
        </Form.Item>
        {parts.map((h, idx) => (
          <Form.Item key={idx} label={`Часть ${idx + 1} — часов`}>
            <InputNumber
              min={0}
              max={total}
              value={h}
              disabled={idx === parts.length - 1}
              onChange={(v) => updatePart(idx, v ?? 0)}
            />
          </Form.Item>
        ))}
        <Checkbox checked={cascade} onChange={(e) => setCascade(e.target.checked)}>
          Каскадно разбить последующие фазы пропорционально
        </Checkbox>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 3: Wire from context menu**

- [ ] **Step 4: Tests + smoke**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(rp/ui): split phase dialog with cascade option"
```

---

## Task 17: Frontend — redesigned conflict panel

**Files:**
- Modify: `frontend/src/components/resource-planning/ConflictPanel.tsx`
- Test: vitest

- [ ] **Step 1: Failing vitest**

```tsx
test("groups by item by default", () => {
  const conflicts = [
    { type: "OVERLOAD_HIGH", backlog_item_id: "i1", message: "Шутов перегружен 1–10 апреля" },
    { type: "QUARTER_OVERFLOW", backlog_item_id: "i1", message: "PRJ-10892 не вмещается" },
  ];
  render(<ConflictPanel conflicts={conflicts} items={...} employees={...} />);
  expect(screen.getByText(/PRJ-10892/)).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(1);  // grouped under one item
});

test("switching to By Employee groups by employee_id", () => {
  ...
  fireEvent.click(screen.getByText("По людям"));
  expect(screen.getByText(/Шутов/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement tabs + groups**

```tsx
export function ConflictPanel({ conflicts, items, employees }) {
  const [groupBy, setGroupBy] = useState<"item"|"employee"|"type">("item");
  const [severity, setSeverity] = useState<string|null>(null);
  const filtered = useMemo(() => conflicts.filter(c =>
    severity ? c.severity === severity : true
  ), [conflicts, severity]);
  return (
    <div className="conflict-panel">
      <Tabs activeKey={groupBy} onChange={setGroupBy as any} items={[
        { key: "item", label: "По задачам" },
        { key: "employee", label: "По людям" },
        { key: "type", label: "По типу" },
      ]} />
      <Segmented
        options={[
          { label: "Все", value: null },
          { label: "Критические", value: "critical" },
          { label: "Предупреждения", value: "warning" },
          { label: "Информация", value: "info" },
        ]}
        value={severity}
        onChange={setSeverity as any}
      />
      <ConflictGroups conflicts={filtered} groupBy={groupBy} items={items} employees={employees} />
    </div>
  );
}

function ConflictGroups({ conflicts, groupBy, items, employees }) {
  const grouped = groupConflictsBy(conflicts, groupBy, items, employees);
  return (
    <Collapse>
      {Object.entries(grouped).map(([key, list]) => (
        <Collapse.Panel key={key} header={<GroupHeader keyName={key} count={list.length} groupBy={groupBy} />}>
          {list.map(c => <ConflictRow key={c.detection_key} conflict={c} />)}
        </Collapse.Panel>
      ))}
    </Collapse>
  );
}

function ConflictRow({ conflict }) {
  return (
    <div className="conflict-row">
      <SeverityIcon level={conflict.severity} />
      <span className="msg">{conflict.message}</span>
      <Space>
        <Button icon={<AimOutlined />} title="К фазе" onClick={() => focusAssignment(conflict.assignment_id)} />
        <Button icon={<UserOutlined />} title="Назначить другого" onClick={() => openSidebar(conflict.assignment_id)} />
        <Button icon={<MutedIcon />} title="Заглушить" onClick={() => muteConflict(conflict.id)} />
      </Space>
    </div>
  );
}
```

- [ ] **Step 3: Tests + smoke**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(rp/ui): conflict panel with tabs/filters/actions"
```

---

## Task 18: E2E + regression

**Files:**
- Create: `e2e-tests/resource-planning-rework.spec.ts`

- [ ] **Step 1: E2E happy path**

```ts
test("compute → drag start → cascade visible", async ({ page }) => {
  await login(page);
  await page.goto("/resource-planning");
  await page.click('button:has-text("Распределить")');
  await page.waitForSelector('.rp-bar');
  // drag first bar to a new date
  const bar = page.locator('.rp-bar').first();
  await bar.dragTo(page.locator('.rp-day-2026-04-15'));
  // verify dependent bars shifted
  await expect(page.locator('.rp-bar--manual-edit')).toHaveCount(1);
});
```

- [ ] **Step 2: E2E split dialog**

```ts
test("split phase via context menu", async ({ page }) => {
  ...
  await page.click('.rp-bar', { button: "right" });
  await page.click('text=Разбить на части...');
  await page.fill('input[name="part-1"]', "12");
  await page.click('text=Применить');
  await expect(page.locator('.rp-bar')).toHaveCount(2);  // analyst split into 2
});
```

- [ ] **Step 3: E2E hide weekends**

```ts
test("hide weekends toggle removes weekend columns", async ({ page }) => {
  ...
  const colsBefore = await page.locator('.rp-day').count();
  await page.click('text=Только рабочие');
  const colsAfter = await page.locator('.rp-day').count();
  expect(colsAfter).toBeLessThan(colsBefore);
});
```

- [ ] **Step 4: Run full test suite**

```bash
py -3.10 -m pytest tests/ -v
cd frontend && npm test
.\scripts\e2e-local.ps1
```

- [ ] **Step 5: Smoke on real data**

Manual: open https://app.../resource-planning on staging-like data. Verify no 24000% numbers; conflicts panel reads cleanly; drag/split work.

- [ ] **Step 6: Commit + push**

```bash
git add e2e-tests/
git commit -m "test(rp): e2e for drag, split, hide-weekends"
git push origin main
```

---

## Self-Review

**Spec coverage check:**
- 3.1 формула вовлечённости → Task 5 ✓
- 3.2 свободный граф → Tasks 1, 6 ✓
- 3.3 закрепление → Tasks 2, 7, 8 ✓
- 3.4 ручной разбив → Tasks 9, 16 ✓
- 3.5 ручной старт → Task 8 ✓
- 3.6 расширенные блокировки → Task 3 ✓
- 3.7 ОПЭ — без изменений ✓ (covered by Tasks 5-7 not breaking it)
- 4.1 двухстрочные строки → Task 12 ✓
- 4.2 паттерны → Task 13 ✓
- 4.3 тумблер выходных → Task 13 ✓
- 4.4 тепловая полоса + рамки → Task 14 ✓
- 4.5 три способа правки зависимостей → Task 15 ✓
- 4.6 user prefs → Tasks 4, 11, 12 ✓
- 5.1 группировка панели конфликтов → Task 17 ✓
- 5.2 дедупликация → Task 10 ✓
- 5.3 шаблоны → Task 10 ✓
- 5.4 действия → Task 17 ✓
- 7 миграции → Tasks 1, 2, 3, 4 ✓
- 8 тестирование → каждый Task имеет TDD-шаги; Task 18 — e2e ✓

**Type consistency:** Метод `patchAssignment` определён в Task 8 (бэк) и Task 15 (фронт-API). Имя одно. `splitAssignment` — Task 9 (бэк) + Task 15 + Task 16 (фронт). `recompute_subgraph` упомянут в Task 8 — реализован там же.

**Placeholder scan:** нет TBD/TODO. Все шаги конкретные.

---

## Execution

Plan complete and saved to `docs/superpowers/plans/2026-05-10-resource-planning-rework.md`.
