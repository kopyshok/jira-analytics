# Resource Planning Gantt — Implementation Plan (Phase 1 MVP)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Новый раздел «Ресурсное планирование» — фазовый Gantt-планировщик квартала на базе утверждённых сценариев.

**Architecture:** Три новые таблицы (scheduled_blocks, resource_plans, resource_plan_assignments) + сервис расписания + REST API `/resource-planning` + React-страница с кастомным Gantt-компонентом без внешних библиотек (rc-virtual-list + SVG).

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / Alembic batch-mode / React 19 / TypeScript / Ant Design 6 / TanStack Query / rc-virtual-list

---

## File Map

**Backend — новые файлы:**
- `app/models/scheduled_block.py` — модель ScheduledBlock
- `app/models/resource_plan.py` — модель ResourcePlan
- `app/models/resource_plan_assignment.py` — модель ResourcePlanAssignment
- `app/services/resource_planning_service.py` — движок расписания
- `app/api/endpoints/resource_planning.py` — router `/resource-planning`
- `alembic/versions/*_scheduled_blocks.py`
- `alembic/versions/*_resource_plans.py`
- `alembic/versions/*_resource_plan_assignments.py`

**Backend — изменяемые:**
- `app/models/__init__.py` — добавить импорты
- `app/api/router.py` — подключить новый router
- `app/api/endpoints/planning.py` — добавить `resource_plan_id` в ответ approve

**Frontend — новые файлы:**
- `frontend/src/api/resourcePlanning.ts`
- `frontend/src/hooks/useResourcePlanning.ts`
- `frontend/src/utils/gantt.ts` — date↔px расчёты
- `frontend/src/pages/ResourcePlanningPage.tsx`
- `frontend/src/components/resource-planning/GanttChart.tsx`
- `frontend/src/components/resource-planning/TimelineHeader.tsx`
- `frontend/src/components/resource-planning/GanttRows.tsx`
- `frontend/src/components/resource-planning/BlockedZones.tsx`
- `frontend/src/components/resource-planning/DependencyArrows.tsx`
- `frontend/src/components/resource-planning/ConflictPanel.tsx`
- `frontend/src/components/resource-planning/ScheduledBlocksModal.tsx`
- `frontend/src/components/resource-planning/PlanToolbar.tsx`

**Frontend — изменяемые:**
- `frontend/src/pages/lazyPages.tsx`
- `frontend/src/routes.tsx`
- `frontend/src/components/Layout/SideMenu.tsx`
- `frontend/src/components/planning/ScenarioRevisionHistoryDrawer.tsx` — кнопка «Открыть диаграмму»

---

## Task 1: Миграции — три новые таблицы

**Files:**
- Create: `alembic/versions/*_scheduled_blocks.py`
- Create: `alembic/versions/*_resource_plans.py`
- Create: `alembic/versions/*_resource_plan_assignments.py`

- [ ] **Step 1: Сгенерировать миграцию scheduled_blocks**

```bash
cd d:/ClaudeDev/JiraAnalysis
alembic revision --autogenerate -m "add_scheduled_blocks"
```

Открыть созданный файл и заменить тело `upgrade` / `downgrade` на:

```python
def upgrade() -> None:
    with op.batch_alter_table.__module__:
        pass
    op.create_table(
        "scheduled_blocks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

def downgrade() -> None:
    op.drop_table("scheduled_blocks")
```

- [ ] **Step 2: Сгенерировать миграцию resource_plans**

```bash
alembic revision --autogenerate -m "add_resource_plans"
```

Тело:
```python
def upgrade() -> None:
    op.create_table(
        "resource_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("planning_scenarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("quarter", sa.String(10), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("computed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

def downgrade() -> None:
    op.drop_table("resource_plans")
```

- [ ] **Step 3: Сгенерировать миграцию resource_plan_assignments**

```bash
alembic revision --autogenerate -m "add_resource_plan_assignments"
```

Тело:
```python
def upgrade() -> None:
    op.create_table(
        "resource_plan_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("backlog_item_id", sa.String(36), sa.ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("part_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("hours_allocated", sa.Float, nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("is_on_critical_path", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("slack_days", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

def downgrade() -> None:
    op.drop_table("resource_plan_assignments")
```

- [ ] **Step 4: Применить миграции**

```bash
alembic upgrade head
```

Ожидаемый вывод: три `Running upgrade ... -> ...` без ошибок.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(resource-planning): add scheduled_blocks, resource_plans, resource_plan_assignments migrations"
```

---

## Task 2: Backend модели

**Files:**
- Create: `app/models/scheduled_block.py`
- Create: `app/models/resource_plan.py`
- Create: `app/models/resource_plan_assignment.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Создать `app/models/scheduled_block.py`**

```python
"""ScheduledBlock — периоды, когда сотрудники/роли недоступны для проектной работы."""

from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.role import Role


class ScheduledBlock(Base, TimestampMixin):
    """Заблокированный период для проектной работы (напр. закрытие месяца).

    Если employee_id=None и role_id=None — блок для всей команды.
    Если role_id задан — блок для всех сотрудников этой роли в команде.
    Если employee_id задан — блок только для конкретного сотрудника.
    """

    __tablename__ = "scheduled_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    role_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[Optional["Role"]] = relationship("Role")
    employee: Mapped[Optional["Employee"]] = relationship("Employee")
```

- [ ] **Step 2: Создать `app/models/resource_plan.py`**

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
```

- [ ] **Step 3: Создать `app/models/resource_plan_assignment.py`**

```python
"""ResourcePlanAssignment — назначение фазы инициативы на сотрудника с датами."""

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.resource_plan import ResourcePlan
    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee


class ResourcePlanAssignment(Base, TimestampMixin):
    """Фаза инициативы в ресурсном плане.

    phase: analyst | dev | qa | opo
    part_number: 1..N для split-фаз (частичная сдача).
    """

    __tablename__ = "resource_plan_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    backlog_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    part_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    hours_allocated: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_on_critical_path: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    slack_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    plan: Mapped["ResourcePlan"] = relationship(back_populates="assignments")
    backlog_item: Mapped["BacklogItem"] = relationship("BacklogItem")
    employee: Mapped[Optional["Employee"]] = relationship("Employee")
```

- [ ] **Step 4: Добавить импорты в `app/models/__init__.py`**

Найти блок `from app.models.role import Role` и после него добавить:

```python
from app.models.scheduled_block import ScheduledBlock
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
```

В список `__all__` добавить: `"ScheduledBlock"`, `"ResourcePlan"`, `"ResourcePlanAssignment"`.

- [ ] **Step 5: Проверить импорты**

```bash
py -3.10 -c "from app.models import ScheduledBlock, ResourcePlan, ResourcePlanAssignment; print('ok')"
```

- [ ] **Step 6: Commit**

```bash
git add app/models/
git commit -m "feat(resource-planning): add ScheduledBlock, ResourcePlan, ResourcePlanAssignment models"
```

---

## Task 3: Сервис расписания — доступность ресурсов

**Files:**
- Create: `app/services/resource_planning_service.py`
- Create: `tests/test_resource_planning_service.py`

Сервис строит словарь `available_hours[employee_id][date] = float` — сколько часов доступен сотрудник для проектной работы в каждый рабочий день квартала.

- [ ] **Step 1: Написать тест на availability calendar**

```python
# tests/test_resource_planning_service.py
from datetime import date
import pytest
from sqlalchemy.orm import Session
from app.services.resource_planning_service import ResourcePlanningService


def test_availability_excludes_absence_days(db: Session, test_employee, test_absence_factory):
    """Дни отсутствия = 0 часов для проектной работы."""
    test_absence_factory(test_employee.id, date(2026, 4, 6), date(2026, 4, 8))
    svc = ResourcePlanningService(db)
    avail = svc.build_availability(
        [test_employee],
        date(2026, 4, 1), date(2026, 4, 10),
        scheduled_blocks=[]
    )
    assert avail[test_employee.id][date(2026, 4, 6)] == 0.0
    assert avail[test_employee.id][date(2026, 4, 7)] == 0.0
    assert avail[test_employee.id][date(2026, 4, 8)] == 0.0


def test_availability_excludes_scheduled_blocks(db: Session, test_employee, test_block_factory):
    """Заблокированные периоды = 0 часов."""
    block = test_block_factory(employee_id=test_employee.id, start=date(2026, 4, 5), end=date(2026, 4, 9))
    svc = ResourcePlanningService(db)
    avail = svc.build_availability(
        [test_employee],
        date(2026, 4, 1), date(2026, 4, 10),
        scheduled_blocks=[block]
    )
    for d in [date(2026, 4, 6), date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)]:
        assert avail[test_employee.id][d] == 0.0


def test_availability_normal_workday(db: Session, test_employee):
    """Рабочий день без ограничений = capacity_hours_per_day."""
    svc = ResourcePlanningService(db)
    avail = svc.build_availability(
        [test_employee],
        date(2026, 4, 1), date(2026, 4, 2),
        scheduled_blocks=[]
    )
    # 2026-04-01 is Wednesday — working day
    assert avail[test_employee.id][date(2026, 4, 1)] > 0.0
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
py -3.10 -m pytest tests/test_resource_planning_service.py -v 2>&1 | head -30
```

- [ ] **Step 3: Реализовать `ResourcePlanningService.build_availability`**

```python
# app/services/resource_planning_service.py
"""Сервис ресурсного планирования — расписание фаз инициатив на квартал."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    BacklogItem,
    Employee,
    ProductionCalendarDay,
    ResourcePlan,
    ResourcePlanAssignment,
    Role,
    ScenarioAllocation,
    ScheduledBlock,
)

PHASE_ORDER = ["analyst", "dev", "qa", "opo"]
PHASE_HOURS_FIELD = {
    "analyst": "estimate_analyst_hours",
    "dev": "estimate_dev_hours",
    "qa": "estimate_qa_hours",
    "opo": "estimate_opo_hours",
}
DEFAULT_HOURS_PER_DAY = 6.0


class ResourcePlanningService:
    def __init__(self, db: Session):
        self.db = db

    # ── Availability calendar ──────────────────────────────────────────────

    def build_availability(
        self,
        employees: List[Employee],
        start: date,
        end: date,
        scheduled_blocks: List[ScheduledBlock],
    ) -> Dict[str, Dict[date, float]]:
        """Возвращает {employee_id: {date: available_hours}}.

        available_hours = capacity_per_day если рабочий день,
        0.0 если выходной / праздник / отсутствие / заблокированный период.
        """
        emp_ids = [e.id for e in employees]

        # Производственный календарь
        cal_rows = self.db.execute(
            select(ProductionCalendarDay).where(
                and_(
                    ProductionCalendarDay.date >= start,
                    ProductionCalendarDay.date <= end,
                )
            )
        ).scalars().all()
        cal = {row.date: row.hours for row in cal_rows}

        # Отсутствия
        absences = self.db.execute(
            select(Absence).where(
                and_(
                    Absence.employee_id.in_(emp_ids),
                    Absence.start_date <= end,
                    Absence.end_date >= start,
                )
            )
        ).scalars().all()
        absent_days: Dict[str, set] = defaultdict(set)
        for a in absences:
            d = max(a.start_date, start)
            while d <= min(a.end_date, end):
                absent_days[a.employee_id].add(d)
                d += timedelta(days=1)

        # Заблокированные периоды
        blocked_days: Dict[str, set] = defaultdict(set)
        for b in scheduled_blocks:
            targets = self._block_targets(b, employees)
            d = max(b.start_date, start)
            while d <= min(b.end_date, end):
                for eid in targets:
                    blocked_days[eid].add(d)
                d += timedelta(days=1)

        # Сборка результата
        result: Dict[str, Dict[date, float]] = {}
        for emp in employees:
            daily: Dict[date, float] = {}
            d = start
            while d <= end:
                if d in absent_days[emp.id] or d in blocked_days[emp.id]:
                    daily[d] = 0.0
                else:
                    # Часы из производственного календаря (0 = выходной)
                    cal_hours = cal.get(d, None)
                    if cal_hours is None:
                        # Фолбэк: пн-пт = DEFAULT_HOURS_PER_DAY, сб/вс = 0
                        cal_hours = DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0
                    daily[d] = cal_hours
                d += timedelta(days=1)
            result[emp.id] = daily
        return result

    def _block_targets(self, block: ScheduledBlock, employees: List[Employee]) -> List[str]:
        """Определить employee_id'ы на которые распространяется блок."""
        if block.employee_id:
            return [block.employee_id]
        if block.role_id:
            return [e.id for e in employees if e.role_id == block.role_id]
        if block.team:
            return [e.id for e in employees if e.team == block.team]
        return [e.id for e in employees]
```

- [ ] **Step 4: Запустить тесты**

```bash
py -3.10 -m pytest tests/test_resource_planning_service.py -v
```

Ожидаемый вывод: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/services/resource_planning_service.py tests/test_resource_planning_service.py
git commit -m "feat(resource-planning): ResourcePlanningService.build_availability"
```

---

## Task 4: Движок расписания — планирование фаз

**Files:**
- Modify: `app/services/resource_planning_service.py`
- Modify: `tests/test_resource_planning_service.py`

- [ ] **Step 1: Написать тест на scheduler**

```python
# добавить в tests/test_resource_planning_service.py

def test_schedule_sequential_phases(db: Session, test_plan_with_items):
    """Фазы одной инициат��вы идут строго последовательно."""
    svc = ResourcePlanningService(db)
    plan, items = test_plan_with_items
    svc.compute_schedule(plan.id)
    db.refresh(plan)

    assignments = (
        db.execute(
            select(ResourcePlanAssignment)
            .where(ResourcePlanAssignment.plan_id == plan.id)
            .where(ResourcePlanAssignment.backlog_item_id == items[0].id)
            .order_by(ResourcePlanAssignment.phase)
        ).scalars().all()
    )
    by_phase = {a.phase: a for a in assignments}

    assert by_phase["analyst"].end_date <= by_phase["dev"].start_date
    assert by_phase["dev"].end_date <= by_phase["qa"].start_date
    assert by_phase["qa"].end_date <= by_phase["opo"].start_date


def test_pipeline_analyst_moves_to_next_initiative(db: Session, test_plan_with_two_items):
    """Аналитик начинает вторую инициативу сразу после первой."""
    svc = ResourcePlanningService(db)
    plan, items = test_plan_with_two_items
    svc.compute_schedule(plan.id)

    a1 = db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.backlog_item_id == items[0].id,
            ResourcePlanAssignment.phase == "analyst",
        )
    ).scalar_one()
    a2 = db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.backlog_item_id == items[1].id,
            ResourcePlanAssignment.phase == "analyst",
        )
    ).scalar_one()

    assert a2.start_date >= a1.end_date
```

- [ ] **Step 2: Реализовать `compute_schedule`**

Добавить в `ResourcePlanningService`:

```python
    # ── Scheduler ─────────────────────────────────────────────────────────

    def compute_schedule(self, plan_id: str) -> None:
        """Рассчитать расписание фаз для всех инициатив плана.

        Алгоритм:
        1. Загрузить инициативы из сценария (по приоритету).
        2. Назначить аналитика и программиста на каждую (greedy по загрузке).
        3. Для каждой инициативы последовательно назначить фазы,
           учитывая доступность и конвейер.
        """
        from datetime import date as date_type
        plan = self.db.get(ResourcePlan, plan_id)
        if not plan:
            raise ValueError(f"ResourcePlan {plan_id} not found")

        # Удалить старые assignments
        self.db.execute(
            ResourcePlanAssignment.__table__.delete().where(
                ResourcePlanAssignment.plan_id == plan_id
            )
        )

        # Загрузить инициативы
        items = self._load_items(plan)
        if not items:
            plan.status = "ready"
            plan.computed_at = __import__("datetime").datetime.utcnow()
            self.db.commit()
            return

        # Определить границы квартала
        q_start, q_end = self._quarter_bounds(plan)

        # Загрузить сотрудников команды
        employees = self._load_employees(plan)
        if not employees:
            plan.status = "ready"
            self.db.commit()
            return

        # Заблокированные периоды
        blocks = self.db.execute(
            select(ScheduledBlock).where(
                ScheduledBlock.team == plan.team
            )
        ).scalars().all()

        # Доступность
        avail = self.build_availability(employees, q_start, q_end, blocks)

        # Назначить исполнителей
        assignments_by_role = self._assign_employees(items, employees)

        # Остаток доступности (мутируемая копия)
        remaining: Dict[str, Dict[date_type, float]] = {
            eid: dict(days) for eid, days in avail.items()
        }

        # Запланировать фазы
        new_assignments: List[ResourcePlanAssignment] = []
        for item in items:
            phase_end: Optional[date_type] = None
            for phase in PHASE_ORDER:
                hours_field = PHASE_HOURS_FIELD[phase]
                hours = getattr(item, hours_field) or 0.0
                if hours <= 0:
                    continue

                employee_id = assignments_by_role.get(phase, {}).get(item.id)
                if not employee_id:
                    continue

                earliest_start = max(
                    q_start,
                    (phase_end + timedelta(days=1)) if phase_end else q_start,
                )

                segments = self._allocate_hours(
                    employee_id, hours, earliest_start, q_end, remaining
                )
                for seg_start, seg_end, seg_hours, part_num in segments:
                    a = ResourcePlanAssignment(
                        plan_id=plan_id,
                        backlog_item_id=item.id,
                        phase=phase,
                        employee_id=employee_id,
                        part_number=part_num,
                        hours_allocated=seg_hours,
                        start_date=seg_start,
                        end_date=seg_end,
                    )
                    new_assignments.append(a)

                if segments:
                    phase_end = segments[-1][1]  # end_date последнего сегмента

        for a in new_assignments:
            self.db.add(a)

        plan.status = "ready"
        plan.computed_at = __import__("datetime").datetime.utcnow()
        self.db.commit()

    def _allocate_hours(
        self,
        employee_id: str,
        total_hours: float,
        earliest_start: date,
        deadline: date,
        remaining: Dict[str, Dict[date, float]],
    ) -> List[tuple]:
        """Разложить total_hours по рабочим дням сотрудника начиная с earliest_start.

        Возвращает список (start_date, end_date, hours, part_number).
        Создаёт split если встречает 0-дни после начала (заблокированный период).
        """
        emp_days = remaining.get(employee_id, {})
        remaining_h = total_hours
        segments = []
        part_num = 1
        seg_start: Optional[date] = None
        seg_hours = 0.0
        in_gap = False

        d = earliest_start
        while remaining_h > 0.01 and d <= deadline:
            avail_h = emp_days.get(d, 0.0)
            if avail_h > 0:
                if seg_start is None:
                    seg_start = d
                if in_gap and seg_start is not None:
                    # Закрыть предыдущий сегмент, открыть новый
                    part_num += 1
                    seg_start = d
                    seg_hours = 0.0
                    in_gap = False
                used = min(avail_h, remaining_h)
                emp_days[d] -= used
                remaining_h -= used
                seg_hours += used
                seg_end = d
            else:
                if seg_start is not None and seg_hours > 0:
                    in_gap = True
            d += timedelta(days=1)

        # Закрыть последний открытый сегмент
        if seg_start is not None and seg_hours > 0:
            segments.append((seg_start, seg_end, seg_hours, part_num))

        return segments

    def _load_items(self, plan: ResourcePlan) -> List[BacklogItem]:
        """Загрузить инициативы из сценария, отсортированные по приоритету."""
        if plan.scenario_id:
            rows = self.db.execute(
                select(BacklogItem)
                .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
                .where(
                    ScenarioAllocation.scenario_id == plan.scenario_id,
                    ScenarioAllocation.included == True,
                )
                .order_by(BacklogItem.priority.nullslast())
            ).scalars().all()
            return list(rows)
        return []

    def _load_employees(self, plan: ResourcePlan) -> List[Employee]:
        from app.models.employee_team import EmployeeTeam
        rows = self.db.execute(
            select(Employee)
            .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .where(
                EmployeeTeam.team == plan.team,
                Employee.is_active == True,
            )
        ).scalars().all()
        return list(rows)

    def _quarter_bounds(self, plan: ResourcePlan):
        from app.services.capacity_service import QUARTER_MONTHS
        months = QUARTER_MONTHS.get(int(plan.quarter.replace("Q", "")), (1, 2, 3))
        year = plan.year or __import__("datetime").date.today().year
        q_start = date(year, months[0], 1)
        last_month = months[-1]
        import calendar
        last_day = calendar.monthrange(year, last_month)[1]
        q_end = date(year, last_month, last_day)
        return q_start, q_end

    def _assign_employees(
        self, items: List[BacklogItem], employees: List[Employee]
    ) -> Dict[str, Dict[str, str]]:
        """Greedy назначение: {phase: {item_id: employee_id}}.

        Для каждой инициативы назначает одного аналитика и одного программиста
        с минимальной суммарной нагрузкой на квартал.
        """
        from app.models.role import Role
        # Группировка сотрудников по роли
        role_emp: Dict[str, List[str]] = defaultdict(list)
        for e in employees:
            if e.role and e.role.name:
                role_emp[e.role.name.lower()].append(e.id)

        analyst_ids = role_emp.get("аналитик", []) or role_emp.get("analyst", [])
        dev_ids = role_emp.get("разработчик", []) or role_emp.get("developer", []) or role_emp.get("dev", [])
        qa_ids = role_emp.get("qa", []) or role_emp.get("тестировщик", [])

        load: Dict[str, float] = defaultdict(float)
        result: Dict[str, Dict[str, str]] = {p: {} for p in PHASE_ORDER}

        for item in items:
            for phase, pool in [
                ("analyst", analyst_ids),
                ("dev", dev_ids),
                ("qa", qa_ids),
                ("opo", analyst_ids + dev_ids),
            ]:
                if not pool:
                    continue
                chosen = min(pool, key=lambda eid: load[eid])
                hours_field = PHASE_HOURS_FIELD[phase]
                load[chosen] += getattr(item, hours_field) or 0.0
                result[phase][item.id] = chosen

        return result
```

- [ ] **Step 3: Запустить тесты**

```bash
py -3.10 -m pytest tests/test_resource_planning_service.py -v
```

- [ ] **Step 4: Commit**

```bash
git add app/services/resource_planning_service.py tests/test_resource_planning_service.py
git commit -m "feat(resource-planning): scheduling engine — phase allocation + pipeline"
```

---

## Task 5: API — ScheduledBlocks + ResourcePlan

**Files:**
- Create: `app/api/endpoints/resource_planning.py`
- Modify: `app/api/router.py`

- [ ] **Step 1: Создать `app/api/endpoints/resource_planning.py`**

```python
"""Resource Planning API — ScheduledBlocks + ResourcePlan + Gantt projection."""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.auth import get_current_user
from app.database import get_db
from app.models import (
    BacklogItem,
    Employee,
    ResourcePlan,
    ResourcePlanAssignment,
    Role,
    ScenarioAllocation,
    ScheduledBlock,
)
from app.models.user import User
from app.services.resource_planning_service import ResourcePlanningService

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────

class ScheduledBlockCreate(BaseModel):
    team: Optional[str] = None
    role_id: Optional[str] = None
    employee_id: Optional[str] = None
    start_date: date
    end_date: date
    reason: str


class ScheduledBlockOut(BaseModel):
    id: str
    team: Optional[str]
    role_id: Optional[str]
    employee_id: Optional[str]
    start_date: date
    end_date: date
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class ResourcePlanCreate(BaseModel):
    scenario_id: Optional[str] = None
    team: str
    quarter: str
    year: int


class ResourcePlanOut(BaseModel):
    id: str
    scenario_id: Optional[str]
    team: Optional[str]
    quarter: Optional[str]
    year: Optional[int]
    status: str
    computed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class AssignmentOut(BaseModel):
    id: str
    backlog_item_id: str
    backlog_item_title: str
    phase: str
    employee_id: Optional[str]
    employee_name: Optional[str]
    part_number: int
    hours_allocated: Optional[float]
    start_date: Optional[date]
    end_date: Optional[date]
    is_on_critical_path: bool
    slack_days: Optional[float]

    class Config:
        from_attributes = True


class ConflictOut(BaseModel):
    type: str
    severity: str
    backlog_item_id: Optional[str]
    backlog_item_title: Optional[str]
    employee_id: Optional[str]
    message: str


class GanttProjection(BaseModel):
    plan: ResourcePlanOut
    assignments: List[AssignmentOut]
    conflicts: List[ConflictOut]


# ── ScheduledBlocks ────────────────────────────────────────────────────────

@router.get("/scheduled-blocks", response_model=List[ScheduledBlockOut])
def list_scheduled_blocks(
    team: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(ScheduledBlock).order_by(ScheduledBlock.start_date)
    if team:
        q = q.where(ScheduledBlock.team == team)
    return db.execute(q).scalars().all()


@router.post("/scheduled-blocks", response_model=ScheduledBlockOut, status_code=201)
def create_scheduled_block(
    data: ScheduledBlockCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if data.end_date < data.start_date:
        raise HTTPException(422, "end_date must be >= start_date")
    block = ScheduledBlock(**data.model_dump())
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.patch("/scheduled-blocks/{block_id}", response_model=ScheduledBlockOut)
def update_scheduled_block(
    block_id: str,
    data: ScheduledBlockCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    block = db.get(ScheduledBlock, block_id)
    if not block:
        raise HTTPException(404, "ScheduledBlock not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(block, k, v)
    db.commit()
    db.refresh(block)
    return block


@router.delete("/scheduled-blocks/{block_id}", status_code=204)
def delete_scheduled_block(
    block_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    block = db.get(ScheduledBlock, block_id)
    if not block:
        raise HTTPException(404, "ScheduledBlock not found")
    db.delete(block)
    db.commit()


# ── ResourcePlans ──────────────────────────────────────────────────────────

@router.get("/resource-plans", response_model=List[ResourcePlanOut])
def list_plans(
    team: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(ResourcePlan).order_by(ResourcePlan.created_at.desc())
    if team:
        q = q.where(ResourcePlan.team == team)
    return db.execute(q).scalars().all()


@router.post("/resource-plans", response_model=ResourcePlanOut, status_code=201)
def create_plan(
    data: ResourcePlanCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = ResourcePlan(**data.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/resource-plans/{plan_id}", response_model=ResourcePlanOut)
def get_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "ResourcePlan not found")
    return plan


@router.delete("/resource-plans/{plan_id}", status_code=204)
def delete_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404)
    db.delete(plan)
    db.commit()


@router.post("/resource-plans/{plan_id}/compute", response_model=ResourcePlanOut)
def compute_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Запустить движок расписания синхронно."""
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "ResourcePlan not found")
    plan.status = "computing"
    db.commit()
    svc = ResourcePlanningService(db)
    svc.compute_schedule(plan_id)
    db.refresh(plan)
    return plan


@router.get("/resource-plans/{plan_id}/gantt", response_model=GanttProjection)
def get_gantt(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Gantt-проекция: все assignments + список конфликтов."""
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404)

    assignments_raw = db.execute(
        select(ResourcePlanAssignment)
        .options(joinedload(ResourcePlanAssignment.backlog_item))
        .options(joinedload(ResourcePlanAssignment.employee))
        .where(ResourcePlanAssignment.plan_id == plan_id)
        .order_by(ResourcePlanAssignment.start_date)
    ).scalars().all()

    assignments = [
        AssignmentOut(
            id=a.id,
            backlog_item_id=a.backlog_item_id,
            backlog_item_title=a.backlog_item.title if a.backlog_item else "",
            phase=a.phase,
            employee_id=a.employee_id,
            employee_name=a.employee.display_name if a.employee else None,
            part_number=a.part_number,
            hours_allocated=a.hours_allocated,
            start_date=a.start_date,
            end_date=a.end_date,
            is_on_critical_path=a.is_on_critical_path,
            slack_days=a.slack_days,
        )
        for a in assignments_raw
    ]

    conflicts = _detect_conflicts(plan, assignments_raw, db)

    return GanttProjection(plan=plan, assignments=assignments, conflicts=conflicts)


def _detect_conflicts(
    plan: ResourcePlan,
    assignments: List[ResourcePlanAssignment],
    db: Session,
) -> List[ConflictOut]:
    conflicts = []
    from collections import defaultdict
    from app.services.resource_planning_service import ResourcePlanningService

    svc = ResourcePlanningService(db)
    q_start, q_end = svc._quarter_bounds(plan)

    # Проверка: есть ли инициативы, чьи ОПЭ выходят за квартал
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

    return conflicts
```

- [ ] **Step 2: Подключить router в `app/api/router.py`**

Найти блок с `from app.api.endpoints` и добавить:
```python
from app.api.endpoints.resource_planning import router as resource_planning_router
```

В блоке `api_router.include_router(...)` добавить:
```python
api_router.include_router(
    resource_planning_router,
    prefix="/resource-planning",
    tags=["resource-planning"],
)
```

- [ ] **Step 3: Проверить что сервер стартует**

```bash
py -3.10 -m uvicorn app.main:app --port 8000 --no-access-log 2>&1 | head -5
```

Ожидаемый вывод: `Application startup complete.` без ошибок.

- [ ] **Step 4: Проверить эндпоинты**

```bash
curl -s http://localhost:8000/api/v1/resource-planning/scheduled-blocks \
  -H "Authorization: Bearer $(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@example.com","password":"admin"}' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')" | python -m json.tool
```

Ожидаемый вывод: `[]`

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py app/api/router.py
git commit -m "feat(resource-planning): REST API — ScheduledBlocks + ResourcePlan + Gantt projection"
```

---

## Task 6: Frontend — API client + hooks

**Files:**
- Create: `frontend/src/api/resourcePlanning.ts`
- Create: `frontend/src/hooks/useResourcePlanning.ts`

- [ ] **Step 1: Создать `frontend/src/api/resourcePlanning.ts`**

```typescript
import { api } from './client';

export interface ScheduledBlock {
  id: string;
  team: string | null;
  role_id: string | null;
  employee_id: string | null;
  start_date: string;
  end_date: string;
  reason: string;
  created_at: string;
}

export interface ResourcePlan {
  id: string;
  scenario_id: string | null;
  team: string | null;
  quarter: string | null;
  year: number | null;
  status: 'draft' | 'computing' | 'ready' | 'stale';
  computed_at: string | null;
  created_at: string;
}

export interface AssignmentOut {
  id: string;
  backlog_item_id: string;
  backlog_item_title: string;
  phase: 'analyst' | 'dev' | 'qa' | 'opo';
  employee_id: string | null;
  employee_name: string | null;
  part_number: number;
  hours_allocated: number | null;
  start_date: string | null;
  end_date: string | null;
  is_on_critical_path: boolean;
  slack_days: number | null;
}

export interface ConflictOut {
  type: string;
  severity: 'critical' | 'warning' | 'info';
  backlog_item_id: string | null;
  backlog_item_title: string | null;
  employee_id: string | null;
  message: string;
}

export interface GanttProjection {
  plan: ResourcePlan;
  assignments: AssignmentOut[];
  conflicts: ConflictOut[];
}

// ── ScheduledBlocks ────────────────────────────────────────────────────────
export const getScheduledBlocks = (team?: string) =>
  api.get<ScheduledBlock[]>('/resource-planning/scheduled-blocks', team ? { team } : {});

export const createScheduledBlock = (data: Omit<ScheduledBlock, 'id' | 'created_at'>) =>
  api.post<ScheduledBlock>('/resource-planning/scheduled-blocks', data);

export const updateScheduledBlock = (id: string, data: Partial<Omit<ScheduledBlock, 'id' | 'created_at'>>) =>
  api.patch<ScheduledBlock>(`/resource-planning/scheduled-blocks/${id}`, data);

export const deleteScheduledBlock = (id: string) =>
  api.del(`/resource-planning/scheduled-blocks/${id}`);

// ── ResourcePlans ──────────────────────────────────────────────────────────
export const getResourcePlans = (team?: string) =>
  api.get<ResourcePlan[]>('/resource-planning/resource-plans', team ? { team } : {});

export const createResourcePlan = (data: { scenario_id?: string; team: string; quarter: string; year: number }) =>
  api.post<ResourcePlan>('/resource-planning/resource-plans', data);

export const deleteResourcePlan = (id: string) =>
  api.del(`/resource-planning/resource-plans/${id}`);

export const computeResourcePlan = (id: string) =>
  api.post<ResourcePlan>(`/resource-planning/resource-plans/${id}/compute`, {});

export const getGanttProjection = (id: string) =>
  api.get<GanttProjection>(`/resource-planning/resource-plans/${id}/gantt`);
```

- [ ] **Step 2: Создать `frontend/src/hooks/useResourcePlanning.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  computeResourcePlan, createResourcePlan, createScheduledBlock,
  deleteResourcePlan, deleteScheduledBlock, getGanttProjection,
  getResourcePlans, getScheduledBlocks, updateScheduledBlock,
} from '../api/resourcePlanning';

export const useScheduledBlocks = (team?: string) =>
  useQuery({
    queryKey: ['scheduled-blocks', team],
    queryFn: () => getScheduledBlocks(team),
    staleTime: 30_000,
  });

export const useCreateScheduledBlock = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createScheduledBlock,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-blocks'] }),
  });
};

export const useUpdateScheduledBlock = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateScheduledBlock>[1] }) =>
      updateScheduledBlock(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-blocks'] }),
  });
};

export const useDeleteScheduledBlock = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteScheduledBlock,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-blocks'] }),
  });
};

export const useResourcePlans = (team?: string) =>
  useQuery({
    queryKey: ['resource-plans', team],
    queryFn: () => getResourcePlans(team),
    staleTime: 30_000,
  });

export const useCreateResourcePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createResourcePlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resource-plans'] }),
  });
};

export const useDeleteResourcePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteResourcePlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resource-plans'] }),
  });
};

export const useComputeResourcePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: computeResourcePlan,
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['resource-plans'] });
      qc.invalidateQueries({ queryKey: ['gantt', id] });
    },
  });
};

export const useGanttProjection = (planId: string | null) =>
  useQuery({
    queryKey: ['gantt', planId],
    queryFn: () => getGanttProjection(planId!),
    enabled: !!planId,
    staleTime: 60_000,
  });
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/hooks/useResourcePlanning.ts
git commit -m "feat(resource-planning): frontend API client + TanStack Query hooks"
```

---

## Task 7: Gantt утилиты — date ↔ px

**Files:**
- Create: `frontend/src/utils/gantt.ts`

- [ ] **Step 1: Создать `frontend/src/utils/gantt.ts`**

```typescript
/**
 * Gantt date ↔ pixel utilities.
 * Timeline spans [startDate, endDate] mapped to [0, timelineWidth].
 */

export interface GanttTimeline {
  startDate: Date;
  endDate: Date;
  totalDays: number;
}

export function buildTimeline(startDate: Date, endDate: Date): GanttTimeline {
  const totalDays = Math.ceil((endDate.getTime() - startDate.getTime()) / 86_400_000) + 1;
  return { startDate, endDate, totalDays };
}

/** Date string "YYYY-MM-DD" → left % within timeline. */
export function dateToLeft(dateStr: string, tl: GanttTimeline): number {
  const d = new Date(dateStr + 'T00:00:00');
  const offsetDays = (d.getTime() - tl.startDate.getTime()) / 86_400_000;
  return Math.max(0, (offsetDays / tl.totalDays) * 100);
}

/** Two date strings → width % within timeline. */
export function datesToWidth(startStr: string, endStr: string, tl: GanttTimeline): number {
  const s = new Date(startStr + 'T00:00:00');
  const e = new Date(endStr + 'T00:00:00');
  const days = (e.getTime() - s.getTime()) / 86_400_000 + 1;
  return Math.max(0.5, (days / tl.totalDays) * 100);
}

/** Quarter string "Q2" + year → {start, end} Date. */
export function quarterBounds(quarter: string, year: number): { start: Date; end: Date } {
  const q = parseInt(quarter.replace('Q', ''));
  const months: Record<number, [number, number]> = {
    1: [0, 2], 2: [3, 5], 3: [6, 8], 4: [9, 11],
  };
  const [startM, endM] = months[q] ?? [0, 2];
  const start = new Date(year, startM, 1);
  const end = new Date(year, endM + 1, 0);
  return { start, end };
}

/** Generate week labels for timeline header. */
export function getWeekLabels(tl: GanttTimeline): Array<{ label: string; leftPct: number; widthPct: number }> {
  const weeks: Array<{ label: string; leftPct: number; widthPct: number }> = [];
  const d = new Date(tl.startDate);
  // Align to Monday
  const dow = d.getDay();
  if (dow !== 1) d.setDate(d.getDate() - ((dow + 6) % 7));

  let weekNum = 1;
  while (d <= tl.endDate) {
    const weekStart = new Date(d);
    const weekEnd = new Date(d);
    weekEnd.setDate(weekEnd.getDate() + 6);
    const left = dateToLeft(weekStart.toISOString().slice(0, 10), tl);
    const end = new Date(Math.min(weekEnd.getTime(), tl.endDate.getTime()));
    const width = datesToWidth(weekStart.toISOString().slice(0, 10), end.toISOString().slice(0, 10), tl);
    weeks.push({ label: `W${weekNum}`, leftPct: left, widthPct: width });
    d.setDate(d.getDate() + 7);
    weekNum++;
  }
  return weeks;
}

/** Phase color mapping. */
export const PHASE_COLORS: Record<string, string> = {
  analyst: '#00c9c8',
  dev: '#2a7fbf',
  qa: '#e8864a',
  opo: '#52d364',
};

export const PHASE_LABELS: Record<string, string> = {
  analyst: 'Анализ',
  dev: 'Разработка',
  qa: 'Тестирование',
  opo: 'ОПЭ',
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/utils/gantt.ts
git commit -m "feat(resource-planning): gantt date-to-pixel utilities"
```

---

## Task 8: Gantt компоненты — TimelineHeader + GanttRows

**Files:**
- Create: `frontend/src/components/resource-planning/TimelineHeader.tsx`
- Create: `frontend/src/components/resource-planning/BlockedZones.tsx`
- Create: `frontend/src/components/resource-planning/GanttRows.tsx`

- [ ] **Step 1: Создать `TimelineHeader.tsx`**

```tsx
// frontend/src/components/resource-planning/TimelineHeader.tsx
import { useMemo } from 'react';
import type { GanttTimeline } from '../../utils/gantt';
import { getWeekLabels } from '../../utils/gantt';

interface Props {
  timeline: GanttTimeline;
  leftColWidth: number;
}

const MONTH_NAMES = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

export default function TimelineHeader({ timeline, leftColWidth }: Props) {
  const weeks = useMemo(() => getWeekLabels(timeline), [timeline]);

  // Group weeks by month
  const months = useMemo(() => {
    const map = new Map<string, { label: string; leftPct: number; rightPct: number }>();
    weeks.forEach(w => {
      const approxDate = new Date(timeline.startDate);
      approxDate.setDate(approxDate.getDate() + Math.round(w.leftPct / 100 * timeline.totalDays));
      const key = `${approxDate.getFullYear()}-${approxDate.getMonth()}`;
      const label = `${MONTH_NAMES[approxDate.getMonth()]} ${approxDate.getFullYear()}`;
      if (!map.has(key)) map.set(key, { label, leftPct: w.leftPct, rightPct: w.leftPct + w.widthPct });
      else map.get(key)!.rightPct = w.leftPct + w.widthPct;
    });
    return [...map.values()];
  }, [weeks, timeline]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid #1e3a5f' }}>
      {/* Month row */}
      <div style={{ display: 'flex', height: 28, background: '#091829' }}>
        <div style={{ width: leftColWidth, flexShrink: 0, borderRight: '1px solid #1e3a5f' }} />
        <div style={{ flex: 1, position: 'relative' }}>
          {months.map(m => (
            <div
              key={m.label}
              style={{
                position: 'absolute',
                left: `${m.leftPct}%`,
                width: `${m.rightPct - m.leftPct}%`,
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 700,
                color: '#5a7aaa',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                borderRight: '1px solid #1e3a5f',
              }}
            >
              {m.label}
            </div>
          ))}
        </div>
      </div>
      {/* Week row */}
      <div style={{ display: 'flex', height: 24, background: '#0a1e35' }}>
        <div style={{ width: leftColWidth, flexShrink: 0, borderRight: '1px solid #1e3a5f' }} />
        <div style={{ flex: 1, position: 'relative' }}>
          {weeks.map(w => (
            <div
              key={w.label}
              style={{
                position: 'absolute',
                left: `${w.leftPct}%`,
                width: `${w.widthPct}%`,
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 10,
                color: '#4a6a90',
                borderRight: '1px solid #142a45',
              }}
            >
              {w.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Создать `BlockedZones.tsx`**

```tsx
// frontend/src/components/resource-planning/BlockedZones.tsx
import type { ScheduledBlock } from '../../api/resourcePlanning';
import type { GanttTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth } from '../../utils/gantt';

interface Props {
  blocks: ScheduledBlock[];
  timeline: GanttTimeline;
}

export default function BlockedZones({ blocks, timeline }: Props) {
  return (
    <>
      {blocks.map(b => {
        const left = dateToLeft(b.start_date, timeline);
        const width = datesToWidth(b.start_date, b.end_date, timeline);
        return (
          <div
            key={b.id}
            title={b.reason}
            style={{
              position: 'absolute',
              left: `${left}%`,
              width: `${width}%`,
              top: 0,
              bottom: 0,
              background: 'repeating-linear-gradient(45deg, rgba(100,120,150,0.08), rgba(100,120,150,0.08) 4px, transparent 4px, transparent 10px)',
              borderLeft: '1px dashed rgba(100,150,200,0.3)',
              borderRight: '1px dashed rgba(100,150,200,0.3)',
              zIndex: 1,
              pointerEvents: 'none',
            }}
          >
            <span style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%) rotate(-90deg)',
              fontSize: 9,
              color: 'rgba(150,180,220,0.5)',
              whiteSpace: 'nowrap',
              letterSpacing: '0.05em',
            }}>
              {b.reason}
            </span>
          </div>
        );
      })}
    </>
  );
}
```

- [ ] **Step 3: Создать `GanttRows.tsx` — View A (Portfolio)**

```tsx
// frontend/src/components/resource-planning/GanttRows.tsx
import { useMemo } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';
import type { GanttTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth, PHASE_COLORS, PHASE_LABELS } from '../../utils/gantt';

export type ViewMode = 'portfolio' | 'two-level' | 'resource-track';

interface Props {
  assignments: AssignmentOut[];
  timeline: GanttTimeline;
  viewMode: ViewMode;
  leftColWidth: number;
}

const ROW_HEIGHT = 36;

/** View A — Portfolio: одна строка на инициативу, фазы как сегменты. */
function PortfolioRows({ assignments, timeline, leftColWidth }: Omit<Props, 'viewMode'>) {
  // Группировка по инициативе
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
      {byItem.map(([itemId, { title, assignments: itemAssignments }], idx) => {
        // Границы инициативы целиком
        const starts = itemAssignments.filter(a => a.start_date).map(a => a.start_date!);
        const ends = itemAssignments.filter(a => a.end_date).map(a => a.end_date!);
        const minStart = starts.sort()[0];
        const maxEnd = ends.sort().at(-1);

        return (
          <div
            key={itemId}
            style={{
              display: 'flex',
              height: ROW_HEIGHT,
              borderBottom: '1px solid #0e2540',
              background: idx % 2 === 0 ? 'rgba(0,201,200,0.03)' : 'transparent',
            }}
          >
            {/* Name column */}
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
            {/* Timeline bars */}
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
        );
      })}
    </>
  );
}

/** View B — Two-level: инициатива + 4 строки фаз. */
function TwoLevelRows({ assignments, timeline, leftColWidth }: Omit<Props, 'viewMode'>) {
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
            {/* Initiative header row */}
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
                {/* Roll-up bar */}
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
            {/* Phase rows */}
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
                    background: 'transparent',
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
                    {phaseAssignments.filter(a => a.start_date && a.end_date).map((a, segIdx) => {
                      const left = dateToLeft(a.start_date!, timeline);
                      const width = datesToWidth(a.start_date!, a.end_date!, timeline);
                      return (
                        <div
                          key={a.id}
                          title={`${PHASE_LABELS[a.phase]}, часть ${a.part_number} — ${a.hours_allocated?.toFixed(0)}ч`}
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
                            border: a.is_on_critical_path ? `1px solid #e85d4a` : 'none',
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

export default function GanttRows(props: Props) {
  if (props.viewMode === 'portfolio') return <PortfolioRows {...props} />;
  if (props.viewMode === 'two-level') return <TwoLevelRows {...props} />;
  return <TwoLevelRows {...props} />;  // resource-track — Task 9
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning/
git commit -m "feat(resource-planning): TimelineHeader, BlockedZones, GanttRows (portfolio + two-level)"
```

---

## Task 9: DependencyArrows + ConflictPanel

**Files:**
- Create: `frontend/src/components/resource-planning/DependencyArrows.tsx`
- Create: `frontend/src/components/resource-planning/ConflictPanel.tsx`

- [ ] **Step 1: Создать `DependencyArrows.tsx`**

```tsx
// frontend/src/components/resource-planning/DependencyArrows.tsx
import { useEffect, useRef } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';

interface Props {
  assignments: AssignmentOut[];
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  containerRef: React.RefObject<HTMLElement>;
}

export default function DependencyArrows({ assignments, rowRefs, containerRef }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    const container = containerRef.current;
    if (!svg || !container) return;

    svg.innerHTML = '';
    const cRect = container.getBoundingClientRect();

    // Intra-initiative arrows: analyst→dev, dev→qa, qa→opo
    const PHASE_ORDER = ['analyst', 'dev', 'qa', 'opo'];
    const byItem = new Map<string, AssignmentOut[]>();
    for (const a of assignments) {
      if (!byItem.has(a.backlog_item_id)) byItem.set(a.backlog_item_id, []);
      byItem.get(a.backlog_item_id)!.push(a);
    }

    for (const [, itemAssignments] of byItem) {
      for (let i = 0; i < PHASE_ORDER.length - 1; i++) {
        const from = itemAssignments.find(a => a.phase === PHASE_ORDER[i] && a.part_number === Math.max(...itemAssignments.filter(x => x.phase === PHASE_ORDER[i]).map(x => x.part_number)));
        const to = itemAssignments.find(a => a.phase === PHASE_ORDER[i + 1] && a.part_number === 1);
        if (!from || !to) continue;

        const fromEl = rowRefs.current.get(`${from.backlog_item_id}-${from.phase}-${from.part_number}`);
        const toEl = rowRefs.current.get(`${to.backlog_item_id}-${to.phase}-${to.part_number}`);
        if (!fromEl || !toEl) continue;

        const fRect = fromEl.getBoundingClientRect();
        const tRect = toEl.getBoundingClientRect();
        const x1 = fRect.right - cRect.left;
        const y1 = fRect.top + fRect.height / 2 - cRect.top;
        const x2 = tRect.left - cRect.left;
        const y2 = tRect.top + tRect.height / 2 - cRect.top;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const cx = (x1 + x2) / 2;
        path.setAttribute('d', `M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`);
        path.setAttribute('stroke', 'rgba(180,200,240,0.35)');
        path.setAttribute('stroke-width', '1.5');
        path.setAttribute('fill', 'none');
        path.setAttribute('marker-end', 'url(#arrowhead)');
        svg.appendChild(path);
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
    >
      <defs>
        <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="6" refY="2" orient="auto">
          <polygon points="0 0, 6 2, 0 4" fill="rgba(180,200,240,0.5)" />
        </marker>
      </defs>
    </svg>
  );
}
```

- [ ] **Step 2: Создать `ConflictPanel.tsx`**

```tsx
// frontend/src/components/resource-planning/ConflictPanel.tsx
import { Alert, Collapse } from 'antd';
import type { ConflictOut } from '../../api/resourcePlanning';

interface Props {
  conflicts: ConflictOut[];
}

const SEVERITY_TYPE: Record<string, 'error' | 'warning' | 'info'> = {
  critical: 'error',
  warning: 'warning',
  info: 'info',
};

export default function ConflictPanel({ conflicts }: Props) {
  if (conflicts.length === 0) return null;

  const criticals = conflicts.filter(c => c.severity === 'critical');
  const warnings = conflicts.filter(c => c.severity === 'warning');

  return (
    <Collapse
      size="small"
      style={{ marginBottom: 16 }}
      items={[{
        key: '1',
        label: (
          <span>
            Конфликты{' '}
            {criticals.length > 0 && (
              <span style={{ color: '#e85d4a', fontWeight: 700 }}>
                {criticals.length} критических
              </span>
            )}
            {warnings.length > 0 && (
              <span style={{ color: '#ffb432', marginLeft: 8 }}>
                {warnings.length} предупреждений
              </span>
            )}
          </span>
        ),
        children: (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {conflicts.map((c, i) => (
              <Alert
                key={i}
                type={SEVERITY_TYPE[c.severity] ?? 'info'}
                message={c.backlog_item_title ? `${c.backlog_item_title}: ${c.message}` : c.message}
                showIcon
              />
            ))}
          </div>
        ),
      }]}
    />
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/resource-planning/DependencyArrows.tsx \
        frontend/src/components/resource-planning/ConflictPanel.tsx
git commit -m "feat(resource-planning): DependencyArrows (SVG bezier) + ConflictPanel"
```

---

## Task 10: GanttChart — главный компонент

**Files:**
- Create: `frontend/src/components/resource-planning/GanttChart.tsx`

- [ ] **Step 1: Создать `GanttChart.tsx`**

```tsx
// frontend/src/components/resource-planning/GanttChart.tsx
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
}

export default function GanttChart({ assignments, blocks, quarter, year, viewMode }: Props) {
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

      {/* Scrollable rows area */}
      <div
        ref={containerRef}
        style={{ position: 'relative', overflowY: 'auto', maxHeight: 'calc(100vh - 280px)' }}
      >
        {/* Today marker */}
        <div style={{
          position: 'absolute',
          left: `calc(${LEFT_COL}px + ${todayLeft}% * (100% - ${LEFT_COL}px) / 100)`,
          top: 0, bottom: 0,
          width: 2,
          background: 'rgba(0,201,200,0.6)',
          zIndex: 20,
          pointerEvents: 'none',
        }} />

        {/* Blocked zones overlay (behind bars) */}
        <div style={{ position: 'absolute', left: LEFT_COL, right: 0, top: 0, bottom: 0 }}>
          <BlockedZones blocks={blocks} timeline={timeline} />
        </div>

        {/* SVG dependency arrows */}
        <DependencyArrows
          assignments={assignments}
          rowRefs={rowRefs}
          containerRef={containerRef}
        />

        <GanttRows
          assignments={assignments}
          timeline={timeline}
          viewMode={viewMode}
          leftColWidth={LEFT_COL}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/resource-planning/GanttChart.tsx
git commit -m "feat(resource-planning): GanttChart — main chart container with today marker"
```

---

## Task 11: ResourcePlanningPage + навигация

**Files:**
- Create: `frontend/src/pages/ResourcePlanningPage.tsx`
- Create: `frontend/src/components/resource-planning/ScheduledBlocksModal.tsx`
- Modify: `frontend/src/pages/lazyPages.tsx`
- Modify: `frontend/src/routes.tsx`
- Modify: `frontend/src/components/Layout/SideMenu.tsx`

- [ ] **Step 1: Создать `ScheduledBlocksModal.tsx`**

```tsx
// frontend/src/components/resource-planning/ScheduledBlocksModal.tsx
import { useState } from 'react';
import { App, Button, DatePicker, Form, Input, Modal, Popconfirm, Select, Table } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ScheduledBlock } from '../../api/resourcePlanning';
import {
  useScheduledBlocks, useCreateScheduledBlock,
  useDeleteScheduledBlock, useUpdateScheduledBlock,
} from '../../hooks/useResourcePlanning';
import { useRoles } from '../../hooks/useRoles';

interface Props {
  open: boolean;
  onClose: () => void;
  team?: string;
}

export default function ScheduledBlocksModal({ open, onClose, team }: Props) {
  const { message } = App.useApp();
  const { data: blocks = [] } = useScheduledBlocks(team);
  const { data: roles = [] } = useRoles();
  const createBlock = useCreateScheduledBlock();
  const deleteBlock = useDeleteScheduledBlock();
  const [form] = Form.useForm();

  const onFinish = async (values: Record<string, unknown>) => {
    try {
      await createBlock.mutateAsync({
        team: team ?? null,
        role_id: (values.role_id as string) ?? null,
        employee_id: null,
        start_date: (values.dates as [dayjs.Dayjs, dayjs.Dayjs])[0].format('YYYY-MM-DD'),
        end_date: (values.dates as [dayjs.Dayjs, dayjs.Dayjs])[1].format('YYYY-MM-DD'),
        reason: values.reason as string,
      });
      form.resetFields();
      message.success('Период добавлен');
    } catch {
      message.error('Ошибка сохранения');
    }
  };

  const columns = [
    { title: 'Начало', dataIndex: 'start_date', width: 100 },
    { title: 'Конец', dataIndex: 'end_date', width: 100 },
    { title: 'Причина', dataIndex: 'reason', ellipsis: true },
    {
      title: '',
      width: 40,
      render: (_: unknown, r: ScheduledBlock) => (
        <Popconfirm title="Удалить?" onConfirm={() => deleteBlock.mutate(r.id)}>
          <Button size="small" icon={<DeleteOutlined />} danger type="text" />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Modal
      title="Заблокированные периоды"
      open={open}
      onCancel={onClose}
      footer={null}
      width={600}
    >
      <Form form={form} layout="inline" onFinish={onFinish} style={{ marginBottom: 16 }}>
        <Form.Item name="dates" rules={[{ required: true, message: 'Выберите даты' }]}>
          <DatePicker.RangePicker size="small" format="DD.MM.YYYY" />
        </Form.Item>
        <Form.Item name="role_id">
          <Select
            size="small"
            placeholder="Роль (необяз.)"
            allowClear
            style={{ width: 140 }}
            options={roles.map(r => ({ label: r.name, value: r.id }))}
          />
        </Form.Item>
        <Form.Item name="reason" rules={[{ required: true, message: 'Укажите причину' }]}>
          <Input size="small" placeholder="Причина" style={{ width: 160 }} />
        </Form.Item>
        <Form.Item>
          <Button size="small" type="primary" htmlType="submit" icon={<PlusOutlined />}>
            Добавить
          </Button>
        </Form.Item>
      </Form>
      <Table
        dataSource={blocks}
        columns={columns}
        rowKey="id"
        size="small"
        pagination={false}
      />
    </Modal>
  );
}
```

- [ ] **Step 2: Создать `ResourcePlanningPage.tsx`**

```tsx
// frontend/src/pages/ResourcePlanningPage.tsx
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { App, Button, Empty, Select, Segmented, Space, Spin, Tag } from 'antd';
import {
  BarChartOutlined, CalculatorOutlined, ScheduleOutlined, SettingOutlined,
} from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import GanttChart from '../components/resource-planning/GanttChart';
import ConflictPanel from '../components/resource-planning/ConflictPanel';
import ScheduledBlocksModal from '../components/resource-planning/ScheduledBlocksModal';
import type { ViewMode } from '../components/resource-planning/GanttRows';
import {
  useGanttProjection, useResourcePlans, useComputeResourcePlan,
  useScheduledBlocks,
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

  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(team);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);
  const { data: blocks = [] } = useScheduledBlocks(team);
  const compute = useComputeResourcePlan();

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
        extra={
          <Space>
            <Button
              icon={<SettingOutlined />}
              onClick={() => setBlocksOpen(true)}
              size="small"
            >
              Заблокированные периоды
            </Button>
          </Space>
        }
      />

      {/* Plan selector + toolbar */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <Select
          loading={plansLoading}
          placeholder="Выберите план"
          value={planId}
          onChange={id => { setPlanId(id); setSearchParams({ plan_id: id }); }}
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
        <Segmented
          value={viewMode}
          onChange={v => setViewMode(v as ViewMode)}
          options={[
            { label: 'Портфель', value: 'portfolio', icon: <BarChartOutlined /> },
            { label: 'Фазы', value: 'two-level', icon: <ScheduleOutlined /> },
          ]}
          style={{ marginLeft: 'auto' }}
        />
      </div>

      {/* Conflicts */}
      {gantt && <ConflictPanel conflicts={gantt.conflicts} />}

      {/* Gantt */}
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
        />
      )}

      <ScheduledBlocksModal
        open={blocksOpen}
        onClose={() => setBlocksOpen(false)}
        team={team}
      />
    </div>
  );
}
```

- [ ] **Step 3: Добавить маршрут в `lazyPages.tsx`**

Добавить в конец файла:
```typescript
export const ResourcePlanningPage = lazy(() => import('./ResourcePlanningPage'));
```

- [ ] **Step 4: Добавить маршрут в `routes.tsx`**

В импортах добавить `ResourcePlanningPage`.

В массив `children` добавить:
```typescript
{ path: 'resource-planning', element: <ProtectedRoute>{page(<ResourcePlanningPage />)}</ProtectedRoute> },
```

- [ ] **Step 5: Добавить пункт меню в `SideMenu.tsx`**

Найти строку с `/planning` и после неё добавить:
```typescript
{ key: '/resource-planning', icon: <ProjectOutlined />, label: 'Ресурс. планир.' },
```

Добавить `ProjectOutlined` в импорты из `@ant-design/icons`.

- [ ] **Step 6: Lint + build**

```bash
cd frontend && npm run lint && npm run build 2>&1 | tail -20
```

Ожидаемый вывод: 0 ошибок линтера, успешный build.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ResourcePlanningPage.tsx \
        frontend/src/components/resource-planning/ScheduledBlocksModal.tsx \
        frontend/src/pages/lazyPages.tsx \
        frontend/src/routes.tsx \
        frontend/src/components/Layout/SideMenu.tsx
git commit -m "feat(resource-planning): ResourcePlanningPage + navigation + ScheduledBlocks UI"
```

---

## Task 12: Кнопка «Открыть диаграмму» из PlanningPage

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 1: Добавить кнопку в карточку утверждённого сценария**

В `PlanningPage.tsx` найти место где отображается кнопка `Approve` или статус `approved` и добавить рядом:

```tsx
import { useNavigate } from 'react-router';
// ...внутри компонента:
const navigate = useNavigate();
// ...в JSX рядом с кнопками утверждённого сценария:
{scenario.status === 'approved' && (
  <Button
    icon={<BarChartOutlined />}
    size="small"
    onClick={() => navigate(`/resource-planning?scenario_id=${scenario.id}`)}
  >
    Диаграмма
  </Button>
)}
```

Добавить `BarChartOutlined` в импорты.

- [ ] **Step 2: Обработать `scenario_id` в `ResourcePlanningPage`**

В `ResourcePlanningPage.tsx` добавить автосоздание плана при переходе со `scenario_id`:

```tsx
const scenarioId = searchParams.get('scenario_id');
const createPlan = useCreateResourcePlan();

useEffect(() => {
  if (scenarioId && !planId && plans.length === 0 && !plansLoading) {
    createPlan.mutateAsync({
      scenario_id: scenarioId,
      team,
      quarter: 'Q2',  // TODO: read from scenario
      year: new Date().getFullYear(),
    }).then(plan => {
      setPlanId(plan.id);
      setSearchParams({ plan_id: plan.id });
    });
  }
}, [scenarioId, planId, plans, plansLoading]);
```

- [ ] **Step 3: Lint + commit**

```bash
cd frontend && npm run lint
git add frontend/src/pages/PlanningPage.tsx frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "feat(resource-planning): button 'Открыть диаграмму' from approved scenario"
```

---

## Task 13: Интеграционные тесты API

**Files:**
- Create: `tests/test_resource_planning_api.py`

- [ ] **Step 1: Написать тесты**

```python
# tests/test_resource_planning_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def auth_headers(db):
    client = TestClient(app)
    r = client.post('/api/v1/auth/login', json={'email': 'admin@test.com', 'password': 'admin'})
    token = r.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_scheduled_blocks_crud(auth_headers):
    client = TestClient(app)
    # Create
    r = client.post('/api/v1/resource-planning/scheduled-blocks',
        json={'start_date': '2026-04-05', 'end_date': '2026-04-09', 'reason': 'Закрытие месяца', 'team': 'Team A'},
        headers=auth_headers)
    assert r.status_code == 201
    block_id = r.json()['id']

    # List
    r = client.get('/api/v1/resource-planning/scheduled-blocks', headers=auth_headers)
    assert any(b['id'] == block_id for b in r.json())

    # Delete
    r = client.delete(f'/api/v1/resource-planning/scheduled-blocks/{block_id}', headers=auth_headers)
    assert r.status_code == 204


def test_resource_plan_create_and_compute(auth_headers, db, test_approved_scenario):
    client = TestClient(app)
    r = client.post('/api/v1/resource-planning/resource-plans',
        json={'scenario_id': test_approved_scenario.id, 'team': 'Team A', 'quarter': 'Q2', 'year': 2026},
        headers=auth_headers)
    assert r.status_code == 201
    plan_id = r.json()['id']

    r = client.post(f'/api/v1/resource-planning/resource-plans/{plan_id}/compute', headers=auth_headers)
    assert r.status_code == 200
    assert r.json()['status'] == 'ready'

    r = client.get(f'/api/v1/resource-planning/resource-plans/{plan_id}/gantt', headers=auth_headers)
    assert r.status_code == 200
    assert 'assignments' in r.json()
    assert 'conflicts' in r.json()
```

- [ ] **Step 2: Запустить**

```bash
py -3.10 -m pytest tests/test_resource_planning_api.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_resource_planning_api.py
git commit -m "test(resource-planning): API integration tests"
```

---

## Task 14: Финальная проверка + smoke test

- [ ] **Step 1: Запустить все тесты**

```bash
py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Ожидаемый вывод: все новые тесты PASS, нет регрессий.

- [ ] **Step 2: Frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 3: Запустить полный стек и проверить страницу**

```bash
py -3.10 scripts/local_smoke.py
```

Открыть http://localhost:5173/resource-planning — страница должна отображаться без ошибок в консоли.

- [ ] **Step 4: Push**

```bash
git push origin main
```

---

## Self-Review

**Spec coverage:**
- ✅ `ScheduledBlock` — Task 1-2, Task 3 API, Task 11 UI
- ✅ `ResourcePlan` + `ResourcePlanAssignment` — Task 1-2
- ✅ Scheduling engine (availability + phases) — Task 3-4
- ✅ REST API — Task 5
- ✅ Frontend API client + hooks — Task 6
- ✅ Gantt utilities — Task 7
- ✅ Timeline header — Task 8
- ✅ Blocked zones — Task 8
- ✅ View A (Portfolio) — Task 8
- ✅ View B (Two-level) — Task 8
- ✅ Dependency arrows — Task 9
- ✅ Conflict panel — Task 9
- ✅ GanttChart container — Task 10
- ✅ ResourcePlanningPage + navigation — Task 11
- ✅ Кнопка из PlanningPage — Task 12
- ✅ Тесты — Task 3, 13

**Gaps / Phase 2:**
- View C (resource track) — отмечен как Phase 2
- Межинициативные стрелки (relay) — Phase 2
- Jira task integration — Phase 2
- `employee.full_name` — нужно проверить что поле существует в модели Employee (может быть `display_name` или `name`)
