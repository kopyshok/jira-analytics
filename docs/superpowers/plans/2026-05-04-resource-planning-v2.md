# Resource Planning v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Параллельный раздел `/resource-planning-v2` («Планирование β») на готовой Gantt-библиотеке (SVAR `wx-react-gantt`) и промышленном constraint-solver (PyJobShop), аддитивно к старому `/resource-planning`.

**Architecture:** Approach B — общий бэк, один новый эндпоинт `POST /resource-plans/{id}/optimize` (форк + solver), один новый сервис `PyJobShopSolverService`, один общий `PlanQualityService` + бейдж в обоих разделах. Новая страница + папка компонентов на фронте, старая страница не трогается кроме монтирования бейджа.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + `pyjobshop>=0.0.8` (MIT, поверх OR-Tools CP-SAT) / React 19 + TS 6 + AntD 6 + TanStack Query + `wx-react-gantt` (MIT).

**Spec:** [docs/superpowers/specs/2026-05-04-resource-planning-v2-design.md](../specs/2026-05-04-resource-planning-v2-design.md)

---

## File Structure

**Backend (новые):**
- `app/services/pyjobshop_solver_service.py` — обёртка над PyJobShop. Читает `BacklogItem`, `Employee`, `ResourcePlanAssignment`, `ProductionCalendarDay`, `Absence`, `BlockedZone`, `PlanItemDependency`. Возвращает `SolverResult`.
- `app/services/plan_quality_service.py` — метрика качества плана (overload_days_pct, late_count, mean_utilization_pct).
- `app/schemas/resource_planning_v2.py` — Pydantic-модели `OptimizeResponse`, `QualityMetric`, `SolverResultSchema`.
- `app/api/endpoints/resource_planning_v2.py` — два эндпоинта (`POST /optimize`, `GET /quality`).
- `tests/test_pyjobshop_solver_service.py` — синтетические сценарии под каждый hard rule.
- `tests/test_plan_quality_service.py` — формулы метрик.
- `tests/test_resource_planning_v2_endpoints.py` — integration по эндпоинтам.

**Backend (модификации):**
- `requirements.txt` — добавить `pyjobshop>=0.0.8`.
- `app/api/router.py` — добавить `include_router` для нового модуля.
- `app/api/endpoints/__init__.py` — экспорт `resource_planning_v2`.

**Frontend (новые):**
- `frontend/src/pages/ResourcePlanningV2Page.tsx` — page-уровень.
- `frontend/src/components/resource-planning-v2/SvarGanttChart.tsx` — обёртка `wx-react-gantt` с двумя режимами + dark theme.
- `frontend/src/components/resource-planning-v2/OptimizeButton.tsx` — кнопка + диалог результата.
- `frontend/src/components/resource-planning-v2/index.ts` — barrel.
- `frontend/src/components/resource-planning/PlanQualityBadge.tsx` — общий бейдж.
- `frontend/src/api/resourcePlanningV2.ts` — API client.
- `frontend/src/hooks/useResourcePlanningV2.ts` — TanStack хуки.
- `frontend/e2e/resource-planning-v2.spec.ts` — Playwright smoke.

**Frontend (модификации):**
- `frontend/package.json` — добавить `wx-react-gantt`.
- `frontend/src/pages/lazyPages.tsx` — `ResourcePlanningV2Page` lazy import.
- `frontend/src/routes.tsx` — роут `/resource-planning-v2`.
- `frontend/src/components/Layout/SideMenu.tsx` — пункт «Планирование β».
- `frontend/src/pages/ResourcePlanningPage.tsx` — добавить `<PlanQualityBadge plan_id={planId}/>` в шапку.

---

## Phase 1 — Backend foundation: dependency + quality service

### Task 1: Установить pyjobshop в зависимости

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Добавить пакет**

В `requirements.txt` добавить строку (порядок алфавитный по соседству):

```
pyjobshop>=0.0.8
```

- [ ] **Step 2: Установить**

Run: `py -3.10 -m pip install -r requirements.txt`
Expected: `Successfully installed pyjobshop-...` без ошибок.

- [ ] **Step 3: Smoke-import**

Run: `py -3.10 -c "from pyjobshop import Model; m = Model(); print(type(m).__name__)"`
Expected: `Model`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(deps): pyjobshop для resource planning v2 solver"
```

---

### Task 2: PlanQualityService — метрика качества плана

**Files:**
- Create: `app/services/plan_quality_service.py`
- Test: `tests/test_plan_quality_service.py`

- [ ] **Step 1: Failing test**

Создать `tests/test_plan_quality_service.py`:

```python
"""Tests for PlanQualityService."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.employee import Employee
from app.services.plan_quality_service import PlanQualityService


def _make_employee(db: Session, name: str = "Иванов И.И.") -> Employee:
    emp = Employee(
        id=None,  # uuid auto
        full_name=name,
        team="Команда А",
        is_active=True,
        hours_per_day=8.0,
    )
    db.add(emp)
    db.flush()
    return emp


def test_quality_empty_plan_returns_zeros(db_session: Session):
    plan = ResourcePlan(team="Команда А", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.flush()

    metric = PlanQualityService(db_session).compute(plan.id)

    assert metric["plan_id"] == plan.id
    assert metric["overload_days_pct"] == 0.0
    assert metric["late_count"] == 0
    assert metric["mean_utilization_pct"] == 0.0


def test_quality_counts_overload_when_assignment_exceeds_capacity(db_session: Session):
    """Один сотрудник, 2 параллельных назначения по 8ч/день каждое = перегруз 200%."""
    emp = _make_employee(db_session)
    plan = ResourcePlan(team="Команда А", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.flush()

    # Два пересекающихся назначения один и тот же день
    for _ in range(2):
        db_session.add(ResourcePlanAssignment(
            plan_id=plan.id,
            backlog_item_id="dummy",  # FK relaxed in test fixture
            phase="dev",
            employee_id=emp.id,
            hours_allocated=8.0,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        ))
    db_session.flush()

    metric = PlanQualityService(db_session).compute(plan.id)

    # День один, один сотрудник, перегружен → 100% перегруза
    assert metric["overload_days_pct"] > 0.0
```

- [ ] **Step 2: Run failing test**

Run: `py -3.10 -m pytest tests/test_plan_quality_service.py -v`
Expected: ImportError or ModuleNotFoundError на `plan_quality_service`.

- [ ] **Step 3: Implement service**

Создать `app/services/plan_quality_service.py`:

```python
"""PlanQualityService — метрика качества ресурсного плана.

Возвращает три числа: % перегруженных дней, число просрочек, среднее
использование ёмкости. Используется обоими разделами планирования (старым
и новым) для сравнения качества.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.employee import Employee
from app.models.production_calendar_day import ProductionCalendarDay
from app.models.absence import Absence


class QualityMetric(TypedDict):
    plan_id: str
    overload_days_pct: float
    late_count: int
    mean_utilization_pct: float


class PlanQualityService:
    """Считает метрику качества плана.

    Перегрузка = день, в котором сумма часов сотрудника > 110% от его
    ёмкости в этот день. % перегрузки = перегруженных дней / всего
    рабочих дней сотрудников.
    """

    OVERLOAD_THRESHOLD = 1.10

    def __init__(self, db: Session):
        self.db = db

    def compute(self, plan_id: str) -> QualityMetric:
        plan = self.db.get(ResourcePlan, plan_id)
        if plan is None:
            raise ValueError(f"Plan {plan_id} not found")

        assignments = list(self.db.scalars(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan_id
            )
        ))

        if not assignments:
            return QualityMetric(
                plan_id=plan_id,
                overload_days_pct=0.0,
                late_count=0,
                mean_utilization_pct=0.0,
            )

        # День × employee → суммарные часы
        load: dict[tuple[date, str], float] = defaultdict(float)
        for a in assignments:
            if a.employee_id is None or a.start_date is None or a.end_date is None:
                continue
            days = self._workdays_between(a.start_date, a.end_date)
            if not days:
                continue
            per_day = (a.hours_allocated or 0.0) / len(days)
            for d in days:
                load[(d, a.employee_id)] += per_day

        # Капасити = hours_per_day сотрудника (грубое приближение, без отсутствий
        # для метрики достаточно; PyJobShop сам считает точнее)
        emp_caps: dict[str, float] = {}
        for emp_id in {a.employee_id for a in assignments if a.employee_id}:
            emp = self.db.get(Employee, emp_id)
            emp_caps[emp_id] = emp.hours_per_day if emp else 8.0

        overload_days = 0
        total_days = 0
        utilization_sum = 0.0
        for (_d, emp_id), hours in load.items():
            cap = emp_caps.get(emp_id, 8.0)
            total_days += 1
            if cap > 0:
                util = hours / cap
                utilization_sum += util
                if util > self.OVERLOAD_THRESHOLD:
                    overload_days += 1

        overload_pct = (overload_days / total_days * 100.0) if total_days else 0.0
        mean_util = (utilization_sum / total_days * 100.0) if total_days else 0.0

        # Late count: assignments с end_date > target_end_date сценария
        target_end = self._scenario_target_end(plan)
        late = 0
        if target_end:
            for a in assignments:
                if a.end_date and a.end_date > target_end:
                    late += 1

        return QualityMetric(
            plan_id=plan_id,
            overload_days_pct=round(overload_pct, 2),
            late_count=late,
            mean_utilization_pct=round(mean_util, 2),
        )

    def _workdays_between(self, start: date, end: date) -> list[date]:
        result: list[date] = []
        d = start
        while d <= end:
            if d.weekday() < 5:  # Пн-Пт
                result.append(d)
            d = d + timedelta(days=1)
        return result

    def _scenario_target_end(self, plan: ResourcePlan) -> Optional[date]:
        if not plan.year or not plan.quarter:
            return None
        q = int(plan.quarter.replace("Q", "")) if plan.quarter.startswith("Q") else 0
        if q < 1 or q > 4:
            return None
        end_month = q * 3
        # Последний день месяца
        if end_month == 12:
            return date(plan.year, 12, 31)
        return date(plan.year, end_month + 1, 1) - timedelta(days=1)
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `py -3.10 -m pytest tests/test_plan_quality_service.py -v`
Expected: 2 passed.

Если `db_session` fixture не имеет relaxed FK — взять `conftest.py` паттерн из соседнего test_capacity_service.py для подсказки. Если FK мешают — добавить fixture-помощник `_make_backlog_item(db, scenario_id)` рядом с `_make_employee`.

- [ ] **Step 5: Commit**

```bash
git add app/services/plan_quality_service.py tests/test_plan_quality_service.py
git commit -m "feat(planning): PlanQualityService — overload/late/utilization метрика для обоих разделов"
```

---

### Task 3: Schemas + endpoint GET /resource-plans/{id}/quality

**Files:**
- Create: `app/schemas/resource_planning_v2.py`
- Create: `app/api/endpoints/resource_planning_v2.py`
- Modify: `app/api/router.py`
- Test: `tests/test_resource_planning_v2_endpoints.py` (только GET /quality пока)

- [ ] **Step 1: Schema**

Создать `app/schemas/resource_planning_v2.py`:

```python
"""Pydantic schemas для resource planning v2."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class QualityMetricSchema(BaseModel):
    plan_id: str
    overload_days_pct: float
    late_count: int
    mean_utilization_pct: float
    computed_at: datetime


class PhaseAllocationSchema(BaseModel):
    phase: Literal["analyst", "dev", "qa", "opo"]
    hours: float
    employee_id: Optional[str]
    start_date: date
    end_date: date


class SolverAssignmentSchema(BaseModel):
    backlog_item_id: str
    assignee_employee_id: Optional[str]
    start_date: date
    end_date: date
    phase_breakdown: list[PhaseAllocationSchema] = Field(default_factory=list)


class SolverResultSchema(BaseModel):
    assignments: list[SolverAssignmentSchema]
    infeasible_items: list[str] = Field(default_factory=list)
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE"]
    solve_time_ms: int


class OptimizeResponse(BaseModel):
    new_plan_id: str
    before: QualityMetricSchema
    after: QualityMetricSchema
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE"]
    solve_time_ms: int
    infeasible_items: list[str]
```

- [ ] **Step 2: Endpoint stub**

Создать `app/api/endpoints/resource_planning_v2.py`:

```python
"""Resource Planning v2 endpoints — solver optimize + quality metric."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.resource_planning_v2 import OptimizeResponse, QualityMetricSchema
from app.services.plan_quality_service import PlanQualityService

router = APIRouter()


@router.get("/{plan_id}/quality", response_model=QualityMetricSchema)
def get_plan_quality(plan_id: str, db: Session = Depends(get_db)) -> QualityMetricSchema:
    """Метрика качества плана: % перегрузок, просрочки, использование ёмкости."""
    try:
        metric = PlanQualityService(db).compute(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return QualityMetricSchema(
        plan_id=metric["plan_id"],
        overload_days_pct=metric["overload_days_pct"],
        late_count=metric["late_count"],
        mean_utilization_pct=metric["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )


@router.post("/{plan_id}/optimize", response_model=OptimizeResponse)
def optimize_plan(plan_id: str, db: Session = Depends(get_db)) -> OptimizeResponse:
    """PyJobShop-оптимизация: создаёт форк плана с новыми ассайнами + датами.

    Реализация в Task 8.
    """
    raise HTTPException(status_code=501, detail="Not implemented yet")
```

- [ ] **Step 3: Register router**

В `app/api/router.py` после блока `resource_planning.router`:

```python
from app.api.endpoints import resource_planning_v2  # add to imports

api_router.include_router(
    resource_planning_v2.router,
    prefix="/resource-planning-v2",
    tags=["resource-planning-v2"],
    dependencies=_auth_dep,
)
```

(Точное имя `_auth_dep` или `[Depends(...)]` — посмотреть как соседние routers подключены.)

- [ ] **Step 4: Endpoint test**

Создать `tests/test_resource_planning_v2_endpoints.py`:

```python
"""Tests for /api/v1/resource-planning-v2 endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.models.resource_plan import ResourcePlan


def test_get_quality_returns_zeros_for_empty_plan(authed_client: TestClient, db_session):
    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()

    r = authed_client.get(f"/api/v1/resource-planning-v2/{plan.id}/quality")
    assert r.status_code == 200
    body = r.json()
    assert body["plan_id"] == plan.id
    assert body["overload_days_pct"] == 0.0
    assert body["late_count"] == 0
    assert body["mean_utilization_pct"] == 0.0
    assert "computed_at" in body


def test_get_quality_404_for_unknown_plan(authed_client: TestClient):
    r = authed_client.get("/api/v1/resource-planning-v2/nonexistent/quality")
    assert r.status_code == 404


def test_optimize_501_until_implemented(authed_client: TestClient, db_session):
    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()

    r = authed_client.post(f"/api/v1/resource-planning-v2/{plan.id}/optimize")
    assert r.status_code == 501  # удалится в Task 8
```

- [ ] **Step 5: Run tests**

Run: `py -3.10 -m pytest tests/test_resource_planning_v2_endpoints.py -v`
Expected: 3 passed.

- [ ] **Step 6: Restart backend manually**

Windows uvicorn `--reload` ненадёжен. Найти PID на :8000 и убить:
```bash
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```
Запустить заново:
```bash
py -3.10 -m uvicorn app.main:app --port 8000
```

Smoke: `curl http://localhost:8000/api/v1/resource-planning-v2/whatever/quality` → 401 (auth required) или 404 (если authed). Главное — не 500.

- [ ] **Step 7: Commit**

```bash
git add app/schemas/resource_planning_v2.py app/api/endpoints/resource_planning_v2.py app/api/router.py tests/test_resource_planning_v2_endpoints.py
git commit -m "feat(api): /resource-planning-v2 quality endpoint + optimize stub"
```

---

## Phase 2 — Backend solver: PyJobShop wrapper, инкрементально по constraints

### Task 4: Solver skeleton — модель без constraints, всё на пуле сотрудников

**Files:**
- Create: `app/services/pyjobshop_solver_service.py`
- Test: `tests/test_pyjobshop_solver_service.py`

Цель: построить minimal viable solver — Job per BacklogItem, Mode per phase, нет hard rules кроме capacity и role-match. Дальнейшие task'и доточат остальное.

- [ ] **Step 1: Failing test (минимальный сценарий)**

Создать `tests/test_pyjobshop_solver_service.py`:

```python
"""Unit tests for PyJobShopSolverService на синтетических данных."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.backlog_item import BacklogItem
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.services.pyjobshop_solver_service import PyJobShopSolverService


@pytest.fixture
def simple_plan(db_session: Session):
    """1 сотрудник-разработчик, 1 backlog с phase=dev на 16ч → 2 рабочих дня."""
    emp = Employee(
        full_name="Dev1",
        team="A",
        is_active=True,
        hours_per_day=8.0,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()

    item = BacklogItem(
        team="A",
        title="Story 1",
        priority=1,
        estimate_dev_hours=16.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=16.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
    )
    db_session.add(assignment)
    db_session.commit()
    return {"plan": plan, "employee": emp, "item": item, "assignment": assignment}


def test_solver_assigns_dev_to_developer(simple_plan, db_session):
    plan = simple_plan["plan"]
    emp = simple_plan["employee"]

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    # Один dev на эту задачу — должен быть назначен наш единственный разработчик
    assert a["assignee_employee_id"] == emp.id
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run: `py -3.10 -m pytest tests/test_pyjobshop_solver_service.py::test_solver_assigns_dev_to_developer -v`
Expected: ImportError на `pyjobshop_solver_service`.

- [ ] **Step 3: Implement skeleton**

Создать `app/services/pyjobshop_solver_service.py`:

```python
"""PyJobShopSolverService — обёртка над PyJobShop для оптимизации
ресурсного плана.

Модель:
- Job = BacklogItem (одна инициатива).
- Task внутри Job = одна phase (analyst/dev/qa/opo).
- Mode = вариант исполнения phase конкретным сотрудником подходящей роли.
- Resource = Employee (renewable, дневная ёмкость).

В этом скелете покрыты только:
- skill match (роль = phase),
- single-mode capacity (один сотрудник одновременно — одну задачу).

Доточка остальных hard rules в следующих task'ах.
"""

import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment


# Маппинг phase → роли которые могут эту phase исполнять.
# Если у Employee.role нет строгого справочника — используем мягкое
# сравнение по подстроке (см. _employee_can_do_phase).
PHASE_ROLE_MATCH = {
    "analyst": {"analyst", "ba", "аналитик"},
    "dev": {"developer", "dev", "разработчик"},
    "qa": {"qa", "tester", "тестировщик"},
    "opo": {"developer", "dev", "analyst", "ba"},  # ОПЭ делят dev и analyst
}


class PhaseAllocation(TypedDict):
    phase: str
    hours: float
    employee_id: Optional[str]
    start_date: date
    end_date: date


class SolverAssignment(TypedDict):
    backlog_item_id: str
    assignee_employee_id: Optional[str]
    start_date: date
    end_date: date
    phase_breakdown: list[PhaseAllocation]


class SolverResult(TypedDict):
    assignments: list[SolverAssignment]
    infeasible_items: list[str]
    solver_status: str
    solve_time_ms: int


class PyJobShopSolverService:
    """Constraint-based оптимизатор ресурсного плана."""

    def __init__(self, db: Session, time_limit_sec: int = 30):
        self.db = db
        self.time_limit_sec = time_limit_sec

    def solve(self, plan_id: str) -> SolverResult:
        from pyjobshop import Model
        from pyjobshop.solve import SolveStatus

        t0 = time.monotonic()

        plan = self.db.get(ResourcePlan, plan_id)
        if plan is None:
            raise ValueError(f"Plan {plan_id} not found")

        assignments = list(self.db.scalars(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan_id
            )
        ))

        if not assignments:
            return SolverResult(
                assignments=[],
                infeasible_items=[],
                solver_status="OPTIMAL",
                solve_time_ms=0,
            )

        # Сотрудники команды плана (фильтр на is_active)
        employees = list(self.db.scalars(
            select(Employee).where(
                Employee.team == plan.team,
                Employee.is_active == True,  # noqa: E712
            )
        ))

        model = Model()

        # Resource per employee
        emp_resources = {emp.id: model.add_renewable(capacity=int((emp.hours_per_day or 8) * 4))  # 1 unit = 15 min
                        for emp in employees}

        # Quarter horizon (рабочие дни)
        horizon_days = self._horizon_days(plan)
        # Конвертация в часы (15-минутные слоты)
        horizon_slots = horizon_days * 8 * 4

        # Job per backlog_item, Task per assignment row
        jobs: dict[str, object] = {}
        tasks: dict[str, object] = {}  # assignment.id → Task

        for a in assignments:
            if a.backlog_item_id not in jobs:
                jobs[a.backlog_item_id] = model.add_job()

            duration_slots = max(1, int((a.hours_allocated or 0) * 4))
            task = model.add_task(job=jobs[a.backlog_item_id], duration=duration_slots)
            tasks[a.id] = task

            # Mode per eligible employee
            for emp in employees:
                if not self._employee_can_do_phase(emp, a.phase):
                    continue
                model.add_mode(task=task, resources=[emp_resources[emp.id]], duration=duration_slots, demands=[duration_slots])

        result = model.solve(time_limit=self.time_limit_sec, display=False)

        # Map result → SolverAssignment
        item_groups: dict[str, list[ResourcePlanAssignment]] = defaultdict(list)
        for a in assignments:
            item_groups[a.backlog_item_id].append(a)

        out_assignments: list[SolverAssignment] = []
        infeasible: list[str] = []

        # SolveStatus.OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN
        status_str = result.status.name if hasattr(result, "status") else "UNKNOWN"
        if status_str == "INFEASIBLE":
            return SolverResult(
                assignments=[],
                infeasible_items=[item_id for item_id in jobs.keys()],
                solver_status="INFEASIBLE",
                solve_time_ms=int((time.monotonic() - t0) * 1000),
            )

        # Извлечь стартовые слоты per task. PyJobShop solution API:
        # result.best.tasks[i] → {start, end, mode}
        start_date_anchor = self._anchor_date(plan)
        solution_tasks = list(result.best.tasks) if hasattr(result, "best") else []
        # solution_tasks упорядочены по добавлению в model — то же что наш порядок assignments
        idx_to_assignment = list(assignments)

        per_assignment: dict[str, PhaseAllocation] = {}
        for idx, sol_task in enumerate(solution_tasks):
            a = idx_to_assignment[idx]
            start_slot = sol_task.start
            end_slot = sol_task.end
            start_d = self._slot_to_date(start_date_anchor, start_slot)
            end_d = self._slot_to_date(start_date_anchor, end_slot)
            chosen_mode = sol_task.mode
            # mode index → eligible employee. Восстановить из add_mode порядка.
            chosen_employee_id = self._mode_index_to_employee(a, employees, chosen_mode)

            per_assignment[a.id] = PhaseAllocation(
                phase=a.phase,
                hours=a.hours_allocated or 0.0,
                employee_id=chosen_employee_id,
                start_date=start_d,
                end_date=end_d,
            )

        for item_id, items in item_groups.items():
            phase_breakdown = [per_assignment[a.id] for a in items if a.id in per_assignment]
            if not phase_breakdown:
                infeasible.append(item_id)
                continue
            # Главный assignee = тот у кого самая длинная phase
            main = max(phase_breakdown, key=lambda p: p["hours"])
            out_assignments.append(SolverAssignment(
                backlog_item_id=item_id,
                assignee_employee_id=main["employee_id"],
                start_date=min(p["start_date"] for p in phase_breakdown),
                end_date=max(p["end_date"] for p in phase_breakdown),
                phase_breakdown=phase_breakdown,
            ))

        return SolverResult(
            assignments=out_assignments,
            infeasible_items=infeasible,
            solver_status=status_str,
            solve_time_ms=int((time.monotonic() - t0) * 1000),
        )

    def _employee_can_do_phase(self, emp: Employee, phase: str) -> bool:
        if not emp.role:
            return False
        role = emp.role.lower()
        return any(token in role for token in PHASE_ROLE_MATCH.get(phase, set()))

    def _horizon_days(self, plan: ResourcePlan) -> int:
        # Q2 2026 = 91 day; для упрощения — 95 (с запасом)
        return 95

    def _anchor_date(self, plan: ResourcePlan) -> date:
        if not plan.year or not plan.quarter:
            return date.today()
        q = int(plan.quarter.replace("Q", ""))
        start_month = (q - 1) * 3 + 1
        return date(plan.year, start_month, 1)

    def _slot_to_date(self, anchor: date, slot: int) -> date:
        # 1 unit = 15 min, 32 units = 1 рабочий день (8ч)
        days_offset = slot // 32
        return anchor + timedelta(days=days_offset)

    def _mode_index_to_employee(
        self, assignment: ResourcePlanAssignment, employees: list[Employee], mode_idx: int
    ) -> Optional[str]:
        eligible = [emp for emp in employees if self._employee_can_do_phase(emp, assignment.phase)]
        if 0 <= mode_idx < len(eligible):
            return eligible[mode_idx].id
        return None
```

- [ ] **Step 4: Run skeleton test**

Run: `py -3.10 -m pytest tests/test_pyjobshop_solver_service.py::test_solver_assigns_dev_to_developer -v`
Expected: 1 passed.

Если падает на API PyJobShop (имя `add_renewable`, `add_mode` сигнатура, `result.best.tasks` структура) — открыть `py -3.10 -c "import pyjobshop; help(pyjobshop.Model)"` или их `examples/` в репо. Подкорректировать вызовы. Это библиотека-первой-версии (0.0.x), API может отличаться от того что в плане. **Допускается:** упростить slot-маппинг на 1 unit = 1 час (и `* 1` вместо `* 4`), если 15-минутные слоты не работают сразу.

- [ ] **Step 5: Commit**

```bash
git add app/services/pyjobshop_solver_service.py tests/test_pyjobshop_solver_service.py
git commit -m "feat(planning): PyJobShopSolverService skeleton — skill match + capacity"
```

---

### Task 5: Solver constraint — calendar (отсутствия + выходные)

**Files:**
- Modify: `app/services/pyjobshop_solver_service.py`
- Modify: `tests/test_pyjobshop_solver_service.py`

- [ ] **Step 1: Failing test**

Добавить в `tests/test_pyjobshop_solver_service.py`:

```python
def test_solver_respects_employee_absence(db_session):
    """Сотрудник в отпуске 1-15 апреля → задача начинается ≥ 16 апреля."""
    from app.models.absence import Absence
    from app.models.absence_reason import AbsenceReason

    reason = db_session.scalar(select(AbsenceReason).limit(1)) or AbsenceReason(code="vacation", label="Отпуск")
    if reason.id is None:
        db_session.add(reason)
        db_session.flush()

    emp = Employee(full_name="Dev1", team="A", is_active=True, hours_per_day=8.0, role="developer")
    db_session.add(emp)
    db_session.flush()

    db_session.add(Absence(
        employee_id=emp.id,
        reason_id=reason.id,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 15),
    ))

    item = BacklogItem(team="A", title="X", priority=1, estimate_dev_hours=8.0,
                       estimate_analyst_hours=0, estimate_qa_hours=0, estimate_opo_hours=0)
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    db_session.add(ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="dev",
        hours_allocated=8.0, start_date=date(2026, 4, 1), end_date=date(2026, 4, 1),
    ))
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)
    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    a = result["assignments"][0]
    assert a["start_date"] >= date(2026, 4, 16)
```

(Добавить `from sqlalchemy import select` если нет.)

- [ ] **Step 2: Run, expect FAIL**

Run: `py -3.10 -m pytest tests/test_pyjobshop_solver_service.py::test_solver_respects_employee_absence -v`
Expected: FAIL — задача стартует 4/1 (отпуск игнорируется).

- [ ] **Step 3: Реализовать absence-aware capacity**

В `pyjobshop_solver_service.py` модифицировать `solve()` — для каждого сотрудника прочитать `Absence` за горизонт плана, передать в `add_renewable` через `capacities` per timeslot (PyJobShop поддерживает variable capacity через `Resource.capacities=[c0, c1, c2, ...]` per период).

Если PyJobShop в текущей версии не поддерживает per-slot capacity — fallback: вырезать дни отсутствия из горизонта, делая `Mode.duration` для этих сотрудников = 0 в эти периоды. Точная реализация зависит от API библиотеки — engineer должен прочитать docs/examples.

Также добавить `ProductionCalendarDay` (выходные/праздники) — в эти дни capacity = 0.

Helper:

```python
def _employee_capacity_per_day(self, emp: Employee, plan: ResourcePlan) -> dict[date, float]:
    """Возвращает {день → доступные часы} для сотрудника на горизонт квартала."""
    from app.models.absence import Absence
    from app.models.production_calendar_day import ProductionCalendarDay

    anchor = self._anchor_date(plan)
    horizon = self._horizon_days(plan)

    # Дефолтная норма из ProductionCalendarDay или fallback hours_per_day Пн-Пт
    cal_rows = list(self.db.scalars(
        select(ProductionCalendarDay).where(
            ProductionCalendarDay.day >= anchor,
            ProductionCalendarDay.day < anchor + timedelta(days=horizon),
        )
    ))
    cal_map = {r.day: r.hours for r in cal_rows}

    caps: dict[date, float] = {}
    for offset in range(horizon):
        d = anchor + timedelta(days=offset)
        if d in cal_map:
            base = cal_map[d] * (emp.hours_per_day / 8.0)
        else:
            base = emp.hours_per_day if d.weekday() < 5 else 0.0
        caps[d] = base

    # Вычесть отсутствия
    abs_rows = list(self.db.scalars(
        select(Absence).where(
            Absence.employee_id == emp.id,
            Absence.end_date >= anchor,
            Absence.start_date < anchor + timedelta(days=horizon),
        )
    ))
    for ab in abs_rows:
        d = max(ab.start_date, anchor)
        end = min(ab.end_date, anchor + timedelta(days=horizon - 1))
        while d <= end:
            caps[d] = 0.0
            d = d + timedelta(days=1)

    return caps
```

И использовать в `add_renewable` для построения per-slot capacity vector.

- [ ] **Step 4: Run, expect PASS**

Run: `py -3.10 -m pytest tests/test_pyjobshop_solver_service.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/pyjobshop_solver_service.py tests/test_pyjobshop_solver_service.py
git commit -m "feat(planning): solver учитывает календарь сотрудника (отсутствия + выходные)"
```

---

### Task 6: Solver constraint — blocked zones (заблокированные периоды)

**Files:**
- Modify: `app/services/pyjobshop_solver_service.py`
- Modify: `tests/test_pyjobshop_solver_service.py`

Заблокированные зоны живут в `BlockedZone` (см. модель + `BlockedZones.tsx` на фронте). В эти периоды сотрудник недоступен (как отпуск).

- [ ] **Step 1: Test**

Добавить тест аналогично absence (создать `BlockedZone` для сотрудника, проверить что start ≥ end_of_zone).

- [ ] **Step 2: Implement**

В `_employee_capacity_per_day` добавить чтение `BlockedZone` (where `employee_id == emp.id` пересекается с горизонтом) и вычитание тех же дней.

- [ ] **Step 3: Run + commit**

```bash
git add ...
git commit -m "feat(planning): solver учитывает заблокированные периоды"
```

---

### Task 7: Solver constraint — dependencies + pinned assignments + priority

**Files:**
- Modify: `app/services/pyjobshop_solver_service.py`
- Modify: `tests/test_pyjobshop_solver_service.py`

Три hard rule сразу (каждый — короткий хук):

**A. Precedence (зависимости).** Читать `PlanItemDependency where plan_id=plan.id` (тип FS — finish-to-start). Для каждой пары добавить `model.add_end_before_start(predecessor_task, successor_task)`.

**B. Pinned assignments.** Если `assignment.is_pinned == True and assignment.employee_id`, то солвер не должен переназначать — закрепить mode на единственного сотрудника (отфильтровать `eligible` до `[emp where emp.id == assignment.employee_id]`).

**C. Project priority.** `BacklogItem.priority` (1 = высший). Добавить в objective веса: `tardiness_weight = 11 - priority` (priority 1 → вес 10; priority 10 → вес 1).

- [ ] **Step 1-3: Tests + impl + commit**

Тесты по одному на каждое правило (3 теста). Реализация — точечно, по соответствующему месту в `solve()`.

```bash
git commit -m "feat(planning): solver учитывает зависимости, pinned, приоритет"
```

---

### Task 8: Endpoint POST /resource-plans/{id}/optimize — fork + apply solver

**Files:**
- Modify: `app/api/endpoints/resource_planning_v2.py`
- Modify: `tests/test_resource_planning_v2_endpoints.py`

- [ ] **Step 1: Найти fork-helper из старого**

В `app/api/endpoints/resource_planning.py` есть `POST /{plan_id}/fork` — найти реализующую функцию и переиспользовать (либо вынести в helper `app/services/resource_plan_forker.py` если она inlined).

- [ ] **Step 2: Implement endpoint**

В `app/api/endpoints/resource_planning_v2.py` заменить stub `optimize_plan`:

```python
@router.post("/{plan_id}/optimize", response_model=OptimizeResponse)
def optimize_plan(plan_id: str, db: Session = Depends(get_db)) -> OptimizeResponse:
    """PyJobShop-оптимизация: создаёт форк + применяет результат + меряет качество."""
    plan = db.get(ResourcePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    quality_service = PlanQualityService(db)
    solver = PyJobShopSolverService(db)

    before = quality_service.compute(plan_id)
    result = solver.solve(plan_id)

    if result["solver_status"] == "INFEASIBLE":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Невозможно построить расписание под текущие правила",
                "infeasible_items": result["infeasible_items"][:5],
            },
        )

    # Fork plan
    fork = _fork_plan(db, plan, label="auto-PyJobShop")

    # Apply solver result to fork's assignments
    fork_assignments = list(db.scalars(
        select(ResourcePlanAssignment).where(ResourcePlanAssignment.plan_id == fork.id)
    ))
    by_item: dict[str, list[ResourcePlanAssignment]] = defaultdict(list)
    for a in fork_assignments:
        by_item[a.backlog_item_id].append(a)

    for sol in result["assignments"]:
        rows = by_item.get(sol["backlog_item_id"], [])
        for row, phase in zip(sorted(rows, key=lambda r: r.phase), sol["phase_breakdown"]):
            if not row.is_pinned:
                row.employee_id = phase["employee_id"]
                row.start_date = phase["start_date"]
                row.end_date = phase["end_date"]

    fork.status = "ready"
    db.commit()

    after = quality_service.compute(fork.id)

    return OptimizeResponse(
        new_plan_id=fork.id,
        before=QualityMetricSchema(**before, computed_at=datetime.now(timezone.utc)),
        after=QualityMetricSchema(**after, computed_at=datetime.now(timezone.utc)),
        solver_status=result["solver_status"],
        solve_time_ms=result["solve_time_ms"],
        infeasible_items=result["infeasible_items"],
    )
```

(Если `_fork_plan` не выделен — извлечь его из `resource_planning.py` в `app/services/resource_plan_forker.py` отдельным предварительным коммитом.)

Imports наверх: `from collections import defaultdict`, `from app.models.resource_plan import ResourcePlan`, `from app.models.resource_plan_assignment import ResourcePlanAssignment`, `from app.services.pyjobshop_solver_service import PyJobShopSolverService`, `from sqlalchemy import select`.

- [ ] **Step 3: Integration test**

Заменить `test_optimize_501_until_implemented` на полноценный:

```python
def test_optimize_creates_fork_and_returns_quality_diff(authed_client, db_session):
    # Фикстура: 1 dev + 1 task на 8ч
    emp = Employee(full_name="Dev", team="A", is_active=True, hours_per_day=8.0, role="developer")
    db_session.add(emp)
    db_session.flush()
    item = BacklogItem(team="A", title="X", priority=1, estimate_dev_hours=8,
                       estimate_analyst_hours=0, estimate_qa_hours=0, estimate_opo_hours=0)
    db_session.add(item)
    db_session.flush()
    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.flush()
    db_session.add(ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="dev",
        hours_allocated=8.0, start_date=date(2026, 4, 1), end_date=date(2026, 4, 1),
    ))
    db_session.commit()

    r = authed_client.post(f"/api/v1/resource-planning-v2/{plan.id}/optimize")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_plan_id"] != plan.id
    assert "before" in body and "after" in body
    assert body["solver_status"] in ("OPTIMAL", "FEASIBLE")

    # Форк существует и имеет правильный label
    fork = db_session.get(ResourcePlan, body["new_plan_id"])
    assert fork is not None
    assert fork.label == "auto-PyJobShop"
    assert fork.parent_plan_id == plan.id
```

- [ ] **Step 4: Run all tests**

Run: `py -3.10 -m pytest tests/test_resource_planning_v2_endpoints.py tests/test_pyjobshop_solver_service.py tests/test_plan_quality_service.py -v`
Expected: all pass.

- [ ] **Step 5: Restart backend, smoke**

(см. Task 3 шаг 6 — kill PID + restart)

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/resource_planning_v2.py tests/test_resource_planning_v2_endpoints.py
git commit -m "feat(api): /resource-planning-v2/{id}/optimize — fork + solver + quality diff"
git push origin main
```

---

## Phase 3 — Frontend foundation: SVAR + route + menu

### Task 9: Установить wx-react-gantt + smoke-страница

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/pages/ResourcePlanningV2Page.tsx` (заглушка)
- Modify: `frontend/src/pages/lazyPages.tsx`
- Modify: `frontend/src/routes.tsx`
- Modify: `frontend/src/components/Layout/SideMenu.tsx`

- [ ] **Step 1: Install package**

```bash
cd frontend && npm install wx-react-gantt
```

Expected: `added 1 package` без ошибок.

- [ ] **Step 2: Page stub**

Создать `frontend/src/pages/ResourcePlanningV2Page.tsx`:

```tsx
import PageHeader from '../components/shared/PageHeader';
import { Tag } from 'antd';

export default function ResourcePlanningV2Page() {
  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader
        title={<span>Планирование <Tag color="purple" style={{ marginLeft: 8 }}>β</Tag></span>}
      />
      <div style={{ color: '#8ab0d8', marginTop: 24 }}>
        Заглушка — здесь будет SVAR Gantt + кнопка «Оптимизировать».
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Lazy import**

В `frontend/src/pages/lazyPages.tsx` добавить рядом с `ResourcePlanningPage`:

```tsx
export const ResourcePlanningV2Page = lazy(() => import('./ResourcePlanningV2Page'));
```

- [ ] **Step 4: Route**

В `frontend/src/routes.tsx`:
- В импорт-список из `./pages/lazyPages`: `ResourcePlanningV2Page`,
- В список путей рядом с `resource-planning`:

```tsx
{ path: 'resource-planning-v2', element: <ProtectedRoute>{page(<ResourcePlanningV2Page />)}</ProtectedRoute> },
```

- [ ] **Step 5: Menu item**

В `frontend/src/components/Layout/SideMenu.tsx` рядом с `/resource-planning` (строка 42 ссылка):

```tsx
{ key: '/resource-planning-v2', icon: <ProjectOutlined />, label: <>Планирование <span style={{ marginLeft: 4, padding: '0 6px', background: '#722ed1', borderRadius: 4, fontSize: 10 }}>β</span></> },
```

- [ ] **Step 6: Dev server smoke**

```bash
cd frontend && npm run dev
```

Открыть `http://localhost:5173/resource-planning-v2` — должна показаться заглушка с заголовком и тегом β. В сайдбаре виден новый пункт.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/pages/ResourcePlanningV2Page.tsx frontend/src/pages/lazyPages.tsx frontend/src/routes.tsx frontend/src/components/Layout/SideMenu.tsx
git commit -m "feat(frontend): /resource-planning-v2 заглушка + меню β"
```

---

### Task 10: SvarGanttChart — обёртка с тестовыми данными

**Files:**
- Create: `frontend/src/components/resource-planning-v2/SvarGanttChart.tsx`
- Create: `frontend/src/components/resource-planning-v2/index.ts`
- Modify: `frontend/src/pages/ResourcePlanningV2Page.tsx`

Цель: подключить `wx-react-gantt` с захардкоженными dummy данными, убедиться что рендерится. Маппинг реальных данных — в Task 11.

- [ ] **Step 1: Component**

Создать `frontend/src/components/resource-planning-v2/SvarGanttChart.tsx`:

```tsx
import { Gantt, Willow } from 'wx-react-gantt';
import 'wx-react-gantt/dist/gantt.css';

const dummyTasks = [
  { id: 1, text: 'Story 1 — analyst', start: new Date(2026, 3, 1), end: new Date(2026, 3, 3), type: 'task', progress: 0 },
  { id: 2, text: 'Story 1 — dev', start: new Date(2026, 3, 4), end: new Date(2026, 3, 8), type: 'task', progress: 0 },
];
const dummyLinks = [{ id: 1, source: 1, target: 2, type: 'e2s' }];

export default function SvarGanttChart() {
  return (
    <div style={{ height: 600, background: '#0f2340', borderRadius: 8, padding: 8 }}>
      <Willow>
        <Gantt tasks={dummyTasks} links={dummyLinks} scales={[
          { unit: 'month', step: 1, format: 'MMMM yyyy' },
          { unit: 'day', step: 1, format: 'd' },
        ]} />
      </Willow>
    </div>
  );
}
```

(Точные имена компонентов и пропсов — посмотреть в `node_modules/wx-react-gantt/README.md` или их документации. API на момент написания плана — `Gantt`, `Willow` theme, `tasks`/`links`/`scales`.)

- [ ] **Step 2: Mount in page**

В `frontend/src/pages/ResourcePlanningV2Page.tsx` заменить заглушку на:

```tsx
import PageHeader from '../components/shared/PageHeader';
import { Tag } from 'antd';
import SvarGanttChart from '../components/resource-planning-v2/SvarGanttChart';

export default function ResourcePlanningV2Page() {
  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader title={<span>Планирование <Tag color="purple" style={{ marginLeft: 8 }}>β</Tag></span>} />
      <SvarGanttChart />
    </div>
  );
}
```

- [ ] **Step 3: Smoke**

`npm run dev` → открыть страницу. Должна появиться Gantt-сетка с двумя задачами и стрелкой.

- [ ] **Step 4: Lint check**

```bash
cd frontend && npm run lint
```

Expected: no errors. Если ошибки на типах wx-react-gantt — добавить `// @ts-expect-error` рядом с проблемной строкой и комментарий-TODO.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/resource-planning-v2/
git commit -m "feat(frontend): SvarGanttChart с dummy данными — smoke"
```

---

### Task 11: Маппинг реальных данных — useGanttProjection → SVAR формат

**Files:**
- Modify: `frontend/src/components/resource-planning-v2/SvarGanttChart.tsx`
- Modify: `frontend/src/pages/ResourcePlanningV2Page.tsx`

- [ ] **Step 1: Page подключает хук**

В `ResourcePlanningV2Page.tsx` использовать существующий `useGanttProjection(planId)` (он вернёт `{plan, assignments, conflicts}` — те же данные что в старом разделе) и передать в `SvarGanttChart`. Также — выпадашку плана через существующий `useResourcePlans`.

```tsx
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { Empty, Select, Spin, Tag } from 'antd';
import PageHeader from '../components/shared/PageHeader';
import SvarGanttChart from '../components/resource-planning-v2/SvarGanttChart';
import { useGanttProjection, useResourcePlans } from '../hooks/useResourcePlanning';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

export default function ResourcePlanningV2Page() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTeams } = useGlobalTeamFilter();
  const team = selectedTeams[0] ?? '';
  const [planId, setPlanId] = useState<string | null>(searchParams.get('plan_id'));

  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(team || undefined);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);

  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader title={<span>Планирование <Tag color="purple" style={{ marginLeft: 8 }}>β</Tag></span>} />
      <Select
        loading={plansLoading}
        placeholder="Выберите план"
        value={planId}
        onChange={id => { setPlanId(id); setSearchParams(id ? { plan_id: id } : {}); }}
        options={plans.map(p => ({ label: `${p.quarter} ${p.year} — ${p.team ?? '—'} [${p.status}]`, value: p.id }))}
        style={{ minWidth: 320, marginBottom: 16 }}
        allowClear
      />
      {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
      {!planId && !ganttLoading && <Empty description="Выберите план" />}
      {gantt && !ganttLoading && planId && (
        <SvarGanttChart assignments={gantt.assignments} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Mapper в SvarGanttChart**

Расширить `SvarGanttChart.tsx`:

```tsx
import { Gantt, Willow } from 'wx-react-gantt';
import 'wx-react-gantt/dist/gantt.css';
import type { Assignment } from '../../api/resourcePlanning';

interface Props {
  assignments: Assignment[];
}

export default function SvarGanttChart({ assignments }: Props) {
  const tasks = assignments.map((a, idx) => ({
    id: a.id ?? idx + 1,
    text: `${a.backlog_item_key ?? a.backlog_item_id?.slice(0, 6)} · ${a.phase}`,
    start: a.start_date ? new Date(a.start_date) : new Date(),
    end: a.end_date ? new Date(a.end_date) : new Date(),
    type: 'task',
    progress: 0,
  }));

  return (
    <div style={{ height: 600, background: '#0f2340', borderRadius: 8, padding: 8 }}>
      <Willow>
        <Gantt tasks={tasks} links={[]} scales={[
          { unit: 'month', step: 1, format: 'MMMM yyyy' },
          { unit: 'day', step: 1, format: 'd' },
        ]} />
      </Willow>
    </div>
  );
}
```

(Точное имя поля `Assignment` — посмотреть в `frontend/src/api/resourcePlanning.ts`. Если `backlog_item_key` нет — использовать `backlog_item_id`.)

- [ ] **Step 3: Smoke**

`npm run dev`. Открыть страницу с реальным `?plan_id=X`. Должны появиться полоски задач из реального плана.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning-v2/SvarGanttChart.tsx frontend/src/pages/ResourcePlanningV2Page.tsx
git commit -m "feat(frontend): SvarGanttChart мапит assignments в формат wx-react-gantt"
```

---

### Task 12: Два режима «По задачам» / «По сотрудникам»

**Files:**
- Modify: `frontend/src/components/resource-planning-v2/SvarGanttChart.tsx`
- Modify: `frontend/src/pages/ResourcePlanningV2Page.tsx`

- [ ] **Step 1: Toggle в page**

В `ResourcePlanningV2Page.tsx` добавить `Segmented`:

```tsx
import { Segmented } from 'antd';
import { ScheduleOutlined, TeamOutlined } from '@ant-design/icons';

// Внутри компонента:
const [viewMode, setViewMode] = useState<'task' | 'employee'>('task');

// Рядом с Select:
<Segmented
  value={viewMode}
  onChange={v => setViewMode(v as 'task' | 'employee')}
  options={[
    { label: 'По задачам', value: 'task', icon: <ScheduleOutlined /> },
    { label: 'По сотрудникам', value: 'employee', icon: <TeamOutlined /> },
  ]}
  style={{ marginLeft: 12, marginBottom: 16 }}
/>

// При рендере:
<SvarGanttChart assignments={gantt.assignments} viewMode={viewMode} />
```

- [ ] **Step 2: Mapper в SvarGanttChart**

Добавить `viewMode` в props. Если `'task'` — текущая логика (одна полоска per assignment, группируем по `backlog_item_id` через `parent`-relation в SVAR). Если `'employee'` — группируем по `employee_id`, родительская строка = сотрудник, детям — его задачи.

```tsx
interface Props {
  assignments: Assignment[];
  viewMode: 'task' | 'employee';
}

function buildTasksByTask(assignments: Assignment[]) {
  // Один parent на backlog_item, дети — phases
  const groups = new Map<string, Assignment[]>();
  assignments.forEach(a => {
    const key = a.backlog_item_id ?? 'unknown';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(a);
  });

  const tasks: Array<Record<string, unknown>> = [];
  let id = 1;
  groups.forEach((items, itemId) => {
    const parentId = id++;
    const sortedStarts = items.map(a => a.start_date).filter(Boolean).sort();
    const sortedEnds = items.map(a => a.end_date).filter(Boolean).sort().reverse();
    tasks.push({
      id: parentId,
      text: items[0].backlog_item_key ?? itemId.slice(0, 6),
      start: sortedStarts[0] ? new Date(sortedStarts[0]) : new Date(),
      end: sortedEnds[0] ? new Date(sortedEnds[0]) : new Date(),
      type: 'summary',
      open: false,
    });
    items.forEach(a => {
      tasks.push({
        id: id++,
        parent: parentId,
        text: a.phase,
        start: a.start_date ? new Date(a.start_date) : new Date(),
        end: a.end_date ? new Date(a.end_date) : new Date(),
        type: 'task',
      });
    });
  });
  return tasks;
}

function buildTasksByEmployee(assignments: Assignment[]) {
  const groups = new Map<string, Assignment[]>();
  assignments.forEach(a => {
    const key = a.employee_id ?? '__pool__';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(a);
  });

  const tasks: Array<Record<string, unknown>> = [];
  let id = 1;
  groups.forEach((items, empId) => {
    const parentId = id++;
    tasks.push({
      id: parentId,
      text: empId === '__pool__' ? '(Пул)' : items[0].employee_name ?? empId.slice(0, 6),
      start: new Date(),
      end: new Date(),
      type: 'summary',
      open: true,
    });
    items.forEach(a => {
      tasks.push({
        id: id++,
        parent: parentId,
        text: `${a.backlog_item_key ?? '?'} · ${a.phase}`,
        start: a.start_date ? new Date(a.start_date) : new Date(),
        end: a.end_date ? new Date(a.end_date) : new Date(),
        type: 'task',
      });
    });
  });
  return tasks;
}

export default function SvarGanttChart({ assignments, viewMode }: Props) {
  const tasks = viewMode === 'task' ? buildTasksByTask(assignments) : buildTasksByEmployee(assignments);
  return (
    <div style={{ height: 600, background: '#0f2340', borderRadius: 8, padding: 8 }}>
      <Willow>
        <Gantt tasks={tasks} links={[]} scales={[
          { unit: 'month', step: 1, format: 'MMMM yyyy' },
          { unit: 'day', step: 1, format: 'd' },
        ]} />
      </Willow>
    </div>
  );
}
```

- [ ] **Step 3: Smoke оба режима**

В браузере переключать тогл, видеть две разные группировки.

- [ ] **Step 4: Commit**

```bash
git add ...
git commit -m "feat(frontend): SvarGanttChart два режима — по задачам / по сотрудникам"
```

---

### Task 13: Dark theme overrides

**Files:**
- Create: `frontend/src/components/resource-planning-v2/svar-dark.css`
- Modify: `frontend/src/components/resource-planning-v2/SvarGanttChart.tsx`

- [ ] **Step 1: CSS файл**

Создать `frontend/src/components/resource-planning-v2/svar-dark.css`:

```css
/* Dark theme overrides для wx-react-gantt — синхронизация с DARK_THEME */
.wx-gantt {
  background: #0f2340;
  color: #e8eef9;
}
.wx-gantt-header,
.wx-gantt-grid-header {
  background: #091527;
  color: #8ab0d8;
}
.wx-gantt-task-bar {
  background: #00c9c8;
}
.wx-gantt-task-bar.wx-gantt-task-summary {
  background: #1668dc;
}
.wx-gantt-grid-row:nth-child(odd) {
  background: #0d1c33;
}
.wx-gantt-grid-cell,
.wx-gantt-row {
  border-color: #1d2f4f;
}
```

(Точные классы проверить через DevTools после первого рендера. Имена `.wx-gantt-...` могут отличаться.)

- [ ] **Step 2: Import in component**

В `SvarGanttChart.tsx` добавить:

```tsx
import './svar-dark.css';
```

- [ ] **Step 3: Smoke**

Перезагрузить страницу. Цвета должны соответствовать общей теме приложения.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning-v2/svar-dark.css frontend/src/components/resource-planning-v2/SvarGanttChart.tsx
git commit -m "feat(frontend): dark theme для SvarGanttChart"
```

---

## Phase 4 — Quality badge + Optimize flow

### Task 14: PlanQualityBadge — общий компонент

**Files:**
- Create: `frontend/src/api/resourcePlanningV2.ts`
- Create: `frontend/src/hooks/useResourcePlanningV2.ts`
- Create: `frontend/src/components/resource-planning/PlanQualityBadge.tsx`

- [ ] **Step 1: API client**

Создать `frontend/src/api/resourcePlanningV2.ts`:

```typescript
import { api } from './client';

export interface QualityMetric {
  plan_id: string;
  overload_days_pct: number;
  late_count: number;
  mean_utilization_pct: number;
  computed_at: string;
}

export interface OptimizeResult {
  new_plan_id: string;
  before: QualityMetric;
  after: QualityMetric;
  solver_status: 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE';
  solve_time_ms: number;
  infeasible_items: string[];
}

export const resourcePlanningV2Api = {
  quality: (planId: string, signal?: AbortSignal) =>
    api.get<QualityMetric>(`/resource-planning-v2/${planId}/quality`, undefined, signal),
  optimize: (planId: string) =>
    api.post<OptimizeResult>(`/resource-planning-v2/${planId}/optimize`),
};
```

(Сигнатура `api.get` / `api.post` — посмотреть в существующем `frontend/src/api/client.ts` и подогнать.)

- [ ] **Step 2: Hooks**

Создать `frontend/src/hooks/useResourcePlanningV2.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { resourcePlanningV2Api } from '../api/resourcePlanningV2';

export function usePlanQuality(planId: string | null) {
  return useQuery({
    queryKey: ['plan-quality', planId],
    queryFn: ({ signal }) => resourcePlanningV2Api.quality(planId!, signal),
    enabled: !!planId,
    staleTime: 30_000,
  });
}

export function useOptimizePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => resourcePlanningV2Api.optimize(planId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['resource-plans'] });
      qc.invalidateQueries({ queryKey: ['gantt-projection'] });
    },
  });
}
```

- [ ] **Step 3: Badge component**

Создать `frontend/src/components/resource-planning/PlanQualityBadge.tsx`:

```tsx
import { Tag, Tooltip, Skeleton } from 'antd';
import { usePlanQuality } from '../../hooks/useResourcePlanningV2';

interface Props {
  planId: string | null;
}

export default function PlanQualityBadge({ planId }: Props) {
  const { data, isLoading } = usePlanQuality(planId);

  if (!planId) return null;
  if (isLoading) return <Skeleton.Button active size="small" style={{ width: 200 }} />;
  if (!data) return null;

  const overloadColor = data.overload_days_pct > 20 ? 'red' : data.overload_days_pct > 5 ? 'orange' : 'green';
  const lateColor = data.late_count > 0 ? 'red' : 'green';

  return (
    <Tooltip title="Качество расписания: % перегруженных дней · число просрочек · среднее использование ёмкости">
      <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
        <Tag color={overloadColor}>Перегрузки: {data.overload_days_pct}%</Tag>
        <Tag color={lateColor}>Просрочки: {data.late_count}</Tag>
        <Tag color="blue">Утилизация: {data.mean_utilization_pct}%</Tag>
      </span>
    </Tooltip>
  );
}
```

- [ ] **Step 4: Mount в обоих страницах**

В `frontend/src/pages/ResourcePlanningPage.tsx` после `Tag` блоков gantt-status (строка ~133):

```tsx
import PlanQualityBadge from '../components/resource-planning/PlanQualityBadge';
// ...
<PlanQualityBadge planId={planId} />
```

В `frontend/src/pages/ResourcePlanningV2Page.tsx` рядом с Select плана:

```tsx
import PlanQualityBadge from '../components/resource-planning/PlanQualityBadge';
// ...
<PlanQualityBadge planId={planId} />
```

- [ ] **Step 5: Smoke**

Открыть оба раздела с одним и тем же `?plan_id` — увидеть одинаковые цифры.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/resourcePlanningV2.ts frontend/src/hooks/useResourcePlanningV2.ts frontend/src/components/resource-planning/PlanQualityBadge.tsx frontend/src/pages/ResourcePlanningPage.tsx frontend/src/pages/ResourcePlanningV2Page.tsx
git commit -m "feat(frontend): PlanQualityBadge — общий бейдж в обоих разделах"
```

---

### Task 15: OptimizeButton + dialog flow

**Files:**
- Create: `frontend/src/components/resource-planning-v2/OptimizeButton.tsx`
- Modify: `frontend/src/pages/ResourcePlanningV2Page.tsx`

- [ ] **Step 1: Component**

Создать `frontend/src/components/resource-planning-v2/OptimizeButton.tsx`:

```tsx
import { useState } from 'react';
import { Button, Modal, App } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { useOptimizePlan } from '../../hooks/useResourcePlanningV2';
import type { OptimizeResult } from '../../api/resourcePlanningV2';

interface Props {
  planId: string;
  onSwitchPlan: (newPlanId: string) => void;
}

export default function OptimizeButton({ planId, onSwitchPlan }: Props) {
  const { message } = App.useApp();
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const optimize = useOptimizePlan();

  const handleClick = async () => {
    try {
      const r = await optimize.mutateAsync(planId);
      setResult(r);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (detail?.message) {
        message.error(`${detail.message}. Затронуты задачи: ${detail.infeasible_items?.join(', ') ?? '—'}`);
      } else {
        message.error('Ошибка оптимизации');
      }
    }
  };

  return (
    <>
      <Button
        type="primary"
        icon={<ThunderboltOutlined />}
        loading={optimize.isPending}
        onClick={handleClick}
      >
        Оптимизировать
      </Button>
      <Modal
        open={!!result}
        title="Оптимизация завершена"
        okText="Открыть новый план"
        cancelText="Остаться на текущем"
        onOk={() => { if (result) onSwitchPlan(result.new_plan_id); setResult(null); }}
        onCancel={() => setResult(null)}
      >
        {result && (
          <div>
            <div>Статус солвера: <b>{result.solver_status}</b></div>
            <div>Время решения: {result.solve_time_ms} мс</div>
            <div style={{ marginTop: 16 }}>
              <div>Качество <b>до</b>: перегрузки {result.before.overload_days_pct}%, просрочки {result.before.late_count}, утилизация {result.before.mean_utilization_pct}%</div>
              <div>Качество <b>после</b>: перегрузки {result.after.overload_days_pct}%, просрочки {result.after.late_count}, утилизация {result.after.mean_utilization_pct}%</div>
            </div>
            {result.infeasible_items.length > 0 && (
              <div style={{ marginTop: 16, color: '#ff7875' }}>
                Не удалось разместить задачи: {result.infeasible_items.length}
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
```

- [ ] **Step 2: Mount**

В `ResourcePlanningV2Page.tsx` рядом с Select:

```tsx
import OptimizeButton from '../components/resource-planning-v2/OptimizeButton';
// ...
{planId && (
  <OptimizeButton
    planId={planId}
    onSwitchPlan={id => { setPlanId(id); setSearchParams({ plan_id: id }); }}
  />
)}
```

- [ ] **Step 3: Smoke**

В новом разделе нажать «Оптимизировать» → дождаться диалога с метриками → нажать «Открыть» → page переключается на новый `plan_id`, в выпадашке появляется план с меткой «auto-PyJobShop».

- [ ] **Step 4: Lint + commit**

```bash
cd frontend && npm run lint
git add frontend/src/components/resource-planning-v2/OptimizeButton.tsx frontend/src/pages/ResourcePlanningV2Page.tsx
git commit -m "feat(frontend): OptimizeButton — запуск солвера + диалог результата"
```

---

## Phase 5 — Acceptance + cleanup

### Task 16: E2E smoke

**Files:**
- Create: `frontend/e2e/resource-planning-v2.spec.ts`

- [ ] **Step 1: Test**

Создать `frontend/e2e/resource-planning-v2.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test('resource planning v2 page loads', async ({ page }) => {
  await page.goto('/resource-planning-v2');
  await expect(page.locator('text=Планирование')).toBeVisible();
  await expect(page.locator('text=β')).toBeVisible();
});

test('sidebar has both planning entries', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('text=Ресурс. планир.')).toBeVisible();
  await expect(page.locator('text=Планирование β')).toBeVisible();
});
```

- [ ] **Step 2: Run**

```bash
cd frontend && npm run e2e -- resource-planning-v2.spec.ts
```

Expected: 2 passed.

- [ ] **Step 3: Commit + push весь батч**

```bash
git add frontend/e2e/resource-planning-v2.spec.ts
git commit -m "test(e2e): resource-planning-v2 smoke"
git push origin main
```

---

### Task 17: Memory + final notes

**Files:**
- Create: `C:\Users\akim2\.claude\projects\d--ClaudeDev-JiraAnalysis\memory\project_resource_planning_v2_shipped.md`
- Modify: `C:\Users\akim2\.claude\projects\d--ClaudeDev-JiraAnalysis\memory\MEMORY.md`

- [ ] **Step 1: Memory entry**

Создать файл с описанием:
- что отгружено (раздел `/resource-planning-v2`, SVAR Gantt, PyJobShop, общий PlanQualityBadge),
- что в proverbial окне ~1 месяца — пользователь решает оставить,
- что удалить если проигрывает (папка `resource-planning-v2`, эндпоинт, пакеты, пункт меню),
- ссылка на спек и план.

- [ ] **Step 2: Index**

В `MEMORY.md` добавить строку:

```
- [Resource Planning v2 — отгружен (β)](project_resource_planning_v2_shipped.md) — 2026-05-04: SVAR Gantt + PyJobShop solver + общий PlanQualityBadge; параллельно старому, ~1 месяц на выбор победителя
```

- [ ] **Step 3: Done — ничего коммитить не надо** (memory вне репозитория).

---

## Self-review notes (для исполняющего агента)

- **PyJobShop API нестабилен** (версия 0.0.x). Если сигнатуры в коде плана не совпадают с реальной версией — engineer открывает их examples (`pyjobshop/PyJobShop/tree/main/examples`) и подгоняет. Главное — сохранить контракт `SolverResult` и hard rules.
- **wx-react-gantt API** — то же самое. Smoke-первая стратегия в Task 10 даёт быструю проверку API раньше чем строится сложная логика.
- **Тесты на solver** требуют живого `db_session` fixture с минимальным набором моделей (Employee, BacklogItem, ResourcePlan, ResourcePlanAssignment, Absence, ProductionCalendarDay, BlockedZone). Если fixture не покрывает relaxed FK — добавить `_make_*` helpers в test-файле.
- **После каждого backend-task'а:** kill PID на :8000, перезапустить uvicorn вручную (Windows reload ненадёжен).
- **После каждой Phase коммитить + push в main** (одна Phase = один cohesive batch).
- **Если solver падает на >30 сек** — оставить как known limitation в memory, не блокировать MVP.

## Acceptance criteria

- [ ] Старый раздел `/resource-planning` работает без изменений (кроме нового бейджа в шапке).
- [ ] Новый раздел `/resource-planning-v2` доступен через меню «Планирование β».
- [ ] В обоих разделах виден одинаковый PlanQualityBadge.
- [ ] Кнопка «Оптимизировать» в новом разделе создаёт форк плана с label `auto-PyJobShop`, не трогает оригинал.
- [ ] Solver учитывает: роль, календарь сотрудника, заблокированные зоны, зависимости, ёмкость, приоритет, pinned.
- [ ] При INFEASIBLE — диалог с пояснением, форк не создаётся.
- [ ] Все тесты зелёные: pyjobshop_solver, plan_quality, resource_planning_v2_endpoints + e2e smoke.
- [ ] Удаление = `rm -rf frontend/src/components/resource-planning-v2/ frontend/src/pages/ResourcePlanningV2Page.tsx app/services/pyjobshop_solver_service.py app/api/endpoints/resource_planning_v2.py app/schemas/resource_planning_v2.py` + revert меню/route/router/lazyPages + uninstall packages. Без миграций БД.
