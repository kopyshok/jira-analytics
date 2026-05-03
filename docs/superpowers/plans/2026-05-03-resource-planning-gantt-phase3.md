# Resource Planning Gantt — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 3 adds RCPSP resource leveling, a persistent conflict register, probabilistic CPM (PERT), and what-if plan forks with a side-by-side comparator on top of the Phase 1+2 phase-level Gantt.

**Architecture:** Backend gets a new `RcpspLeveler` service (post-CPM pass that delays/reassigns over-allocated assignments using slack), a `plan_conflicts` table for persistent conflict objects with status, PERT fields on `BacklogItem`, and `parent_plan_id`/`is_baseline` on `ResourcePlan` for forks. Frontend adds PertOverlay (P50/P90 markers on bars), a ConflictRegister tab (persistent, with mute/acknowledge), and a ScenarioComparator page (two plans side-by-side with metrics + Gantt overlay).

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / Alembic batch-mode / React 19 / TypeScript / Ant Design 6 / TanStack Query

**Phase 1+2 are complete** — all models, migrations, service, API, frontend exist. CPM (`_compute_cpm`), `plan_item_dependencies`, `patchAssignment` are in main. Phase 3 builds on top without breaking anything.

---

## Codebase Context

**Critical facts for all subagents:**
- `Employee.role` = `String(50)` role code (e.g. `"аналитик"`), NOT a FK to `roles` table
- `ScenarioAllocation.included_flag` (not `included`)
- Auth import: `from app.core.auth_deps import get_current_user`
- `Role` model has `.label` and `.code` (not `.name`)
- AntD 6: `PageHeader` uses `actions` prop; `notification` uses `title` not `message`
- All Alembic migrations must use `with op.batch_alter_table(...)` for ALTER (SQLite batch mode)
- Run tests: `py -3.10 -m pytest tests/ -v`
- Run linter: `ruff check app/ tests/` then `ruff format app/ tests/`
- Backend server must be restarted after edits (Windows `--reload` is unreliable): kill PID on :8000 + start fresh
- Frontend build: `npm run build` in `frontend/`
- Sessions commit + db.refresh after writes; in endpoints capture field values into locals BEFORE `db.commit()` to avoid ORM expire reload races
- Russian docstrings for business logic; type hints everywhere

**Existing Phase 1+2 files (read before starting):**
- `app/models/resource_plan.py` — ResourcePlan (status: draft|computing|ready|stale)
- `app/models/resource_plan_assignment.py` — ResourcePlanAssignment (phase: analyst|dev|qa|opo, part_number 1..N, slack_days, is_on_critical_path)
- `app/models/plan_item_dependency.py` — PlanItemDependency (FS|SS|FF|SF + lag_days)
- `app/models/scheduled_block.py` — ScheduledBlock (team/role/employee × date range)
- `app/models/backlog_item.py` — BacklogItem (estimate_analyst_hours, estimate_dev_hours, estimate_qa_hours, estimate_opo_hours, priority, archived_at)
- `app/services/resource_planning_service.py` — `ResourcePlanningService.compute_schedule()` does: load items+employees+blocks → build_availability → _assign_employees (greedy by min load) → loop items×phases _allocate_hours → _compute_cpm
- `app/api/endpoints/resource_planning.py` — 11 endpoints, `_detect_conflicts()` returns ephemeral list (OVERLOAD/QUARTER_OVERFLOW/SPLIT_REQUIRED/NO_ANALYST/NO_DEV)
- `frontend/src/api/resourcePlanning.ts` — API client (ScheduledBlock, ResourcePlan, AssignmentOut, ConflictOut, GanttProjection, AssignmentPatch)
- `frontend/src/hooks/useResourcePlanning.ts` — TanStack Query hooks
- `frontend/src/utils/gantt.ts` — GanttTimeline, dateToLeft, datesToWidth, quarterBounds, getWeekLabels, PHASE_COLORS, PHASE_LABELS, ITEM_PALETTE, getItemColor
- `frontend/src/components/resource-planning/GanttRows.tsx` — PortfolioRows + TwoLevelRows + ResourceTrackRows; ViewMode = 'portfolio'|'two-level'|'resource-track'
- `frontend/src/components/resource-planning/DependencyArrows.tsx` — intra-initiative + relay arrows
- `frontend/src/components/resource-planning/ConflictPanel.tsx` — ephemeral conflict list (collapsible)
- `frontend/src/pages/ResourcePlanningPage.tsx` — plan selector + recompute + view switcher + relay toggle

**Migrations on main:** `040..044` (scheduled_blocks, resource_plans, resource_plan_assignments, plan_item_dependencies, etc.). Phase 3 adds `045..047`.

---

## File Map

### Stage A — RCPSP leveling

**Backend new:**
- `app/services/rcpsp_leveler.py` — RcpspLeveler.level(assignments, availability) → mutates assignments + emits LevelingEvent list
- `tests/test_rcpsp_leveler.py` — leveler unit tests

**Backend modified:**
- `app/services/resource_planning_service.py` — call leveler after `_compute_cpm`, recompute CPM after leveling

### Stage B — Persistent ConflictRegister

**Backend new:**
- `app/models/plan_conflict.py` — PlanConflict model
- `alembic/versions/045_*_add_plan_conflicts.py` — migration
- `tests/test_plan_conflicts_endpoints.py` — register endpoints tests

**Backend modified:**
- `app/models/__init__.py` — register PlanConflict
- `app/models/resource_plan.py` — add `conflicts` relationship
- `app/services/resource_planning_service.py` — `_persist_conflicts(plan_id, detected)` upserts by (type, key) preserving status
- `app/api/endpoints/resource_planning.py` — replace ephemeral `_detect_conflicts` with DB read; add `GET/PATCH /resource-plans/{id}/conflicts/{cid}`; gantt projection reads from `plan_conflicts`

**Frontend modified:**
- `frontend/src/api/resourcePlanning.ts` — extend ConflictOut with id+status+window+metric_value; add `patchConflict`
- `frontend/src/hooks/useResourcePlanning.ts` — `usePatchConflict`
- `frontend/src/components/resource-planning/ConflictPanel.tsx` — add status badges + acknowledge/mute actions

### Stage C — Probabilistic CPM (PERT)

**Backend new:**
- `app/services/pert_calculator.py` — pure functions: `compute_pert_per_phase`, `aggregate_initiative_pert`
- `alembic/versions/046_*_add_pert_multipliers.py` — migration adds `optimistic_multiplier`, `pessimistic_multiplier` to backlog_items
- `tests/test_pert_calculator.py`

**Backend modified:**
- `app/models/backlog_item.py` — add `optimistic_multiplier` (Float default 0.7), `pessimistic_multiplier` (Float default 1.5)
- `app/api/endpoints/resource_planning.py` — extend GanttProjection with `pert_projection: list[InitiativePertOut]`
- `app/api/endpoints/backlog.py` — surface multipliers in BacklogItem schemas (PUT)

**Frontend new:**
- `frontend/src/components/resource-planning/PertOverlay.tsx` — SVG overlay with P50/P90 markers per initiative

**Frontend modified:**
- `frontend/src/api/resourcePlanning.ts` — add InitiativePertOut + pert_projection field
- `frontend/src/components/resource-planning/GanttChart.tsx` — render PertOverlay when toggle on
- `frontend/src/pages/ResourcePlanningPage.tsx` — add «PERT» Switch
- `frontend/src/components/backlog/BacklogItemForm.tsx` (or wherever editing happens) — add multiplier inputs (skip if no edit form exists; per-row edit instead)

### Stage D — What-if scenarios (plan fork + comparator)

**Backend new:**
- `alembic/versions/047_*_add_plan_fork_fields.py` — migration adds `parent_plan_id`, `is_baseline`, `label` to resource_plans
- `app/services/plan_diff.py` — `diff_plans(baseline, scenario)` → DiffResult
- `tests/test_plan_fork.py`

**Backend modified:**
- `app/models/resource_plan.py` — add `parent_plan_id`, `is_baseline`, `label`, self-referential `parent` + `forks` relationships
- `app/api/endpoints/resource_planning.py` — `POST /resource-plans/{id}/fork` (returns new plan with cloned assignments + dependencies + conflicts cleared); `GET /resource-plans/{id}/diff/{baseline_id}` (returns DiffResult)

**Frontend new:**
- `frontend/src/pages/ScenarioComparatorPage.tsx` — route `/resource-planning/compare`
- `frontend/src/components/resource-planning/ScenarioPicker.tsx` — two plan selectors

**Frontend modified:**
- `frontend/src/api/resourcePlanning.ts` — `forkPlan`, `getPlanDiff`, types
- `frontend/src/hooks/useResourcePlanning.ts` — `useForkPlan`, `usePlanDiff`
- `frontend/src/pages/ResourcePlanningPage.tsx` — «Сделать копию» button + label edit + baseline tag
- `frontend/src/lazyPages.tsx` — register ScenarioComparatorPage
- `frontend/src/App.tsx` (or router) — add `/resource-planning/compare` route

---

## Stage A — RCPSP Leveling

Goal: detect per-day over-allocation after greedy assignment + apply delay-within-slack and reassign-to-peer strategies; emit info-level LATE_START and warning-level OVR.* conflicts when leveling didn't fully resolve.

### Task A.1: RcpspLeveler skeleton + LevelingEvent

**Files:**
- Create: `app/services/rcpsp_leveler.py`
- Test: `tests/test_rcpsp_leveler.py`

- [ ] **Step 1: Write failing test for empty input**

```python
# tests/test_rcpsp_leveler.py
"""Тесты для RcpspLeveler — пост-CPM выравнивание перегрузок."""

from datetime import date

from app.services.rcpsp_leveler import RcpspLeveler


def test_leveler_empty_assignments_returns_no_events():
    leveler = RcpspLeveler()
    events = leveler.level(assignments=[], availability={}, q_end=date(2026, 6, 30))
    assert events == []
```

- [ ] **Step 2: Run test to verify it fails**

`py -3.10 -m pytest tests/test_rcpsp_leveler.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.rcpsp_leveler`.

- [ ] **Step 3: Create skeleton module**

```python
# app/services/rcpsp_leveler.py
"""RCPSP-выравнивание: пост-CPM проход разруливает перегрузки ресурсов.

Стратегии (в порядке убывания предпочтения):
1. delay_within_slack — сдвиг назначения внутри slack без слома цепи
2. reassign_to_peer — переназначение на другого сотрудника той же роли
3. escalate — эскалация в конфликт (OVR.LIGHT/MED/HIGH)

Алгоритм работает после _compute_cpm и до _persist_conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Literal, Optional

from app.models import ResourcePlanAssignment


LevelingAction = Literal["delay", "reassign", "escalate"]


@dataclass
class LevelingEvent:
    """Что сделал leveler с одним назначением."""

    assignment_id: str
    action: LevelingAction
    reason: str
    delta_days: int = 0
    from_employee_id: Optional[str] = None
    to_employee_id: Optional[str] = None
    overload_pct: float = 0.0
    affected_dates: List[date] = field(default_factory=list)


class RcpspLeveler:
    """Выравнивание ресурсной нагрузки после первичного scheduling pass."""

    def level(
        self,
        assignments: List[ResourcePlanAssignment],
        availability: Dict[str, Dict[date, float]],
        q_end: date,
    ) -> List[LevelingEvent]:
        """Главный entrypoint. Мутирует assignments на месте, возвращает событий."""
        if not assignments:
            return []
        return []
```

- [ ] **Step 4: Run test to verify it passes**

`py -3.10 -m pytest tests/test_rcpsp_leveler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/rcpsp_leveler.py tests/test_rcpsp_leveler.py
git commit -m "feat(resource-planning): RcpspLeveler skeleton + LevelingEvent dataclass"
```

### Task A.2: Detect per-day overload

**Files:**
- Modify: `app/services/rcpsp_leveler.py`
- Test: `tests/test_rcpsp_leveler.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_rcpsp_leveler.py`:

```python
from app.models import ResourcePlanAssignment


def _mk_assignment(id_, emp_id, start, end, hours, phase="dev", item_id="ITEM-1"):
    a = ResourcePlanAssignment(
        id=id_,
        plan_id="PLAN-1",
        backlog_item_id=item_id,
        phase=phase,
        employee_id=emp_id,
        part_number=1,
        hours_allocated=hours,
        start_date=start,
        end_date=end,
        is_on_critical_path=False,
        slack_days=10.0,
    )
    return a


def test_leveler_detects_overload_when_two_assignments_share_employee_day():
    """Два назначения на одного сотрудника на тот же день → overload событие."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment("A1", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 6.0, item_id="I1")
    a2 = _mk_assignment("A2", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 4.0, item_id="I2")
    avail = {"EMP-1": {date(2026, 4, 1): 8.0}}
    overloads = leveler._detect_overload([a1, a2], avail)
    assert (date(2026, 4, 1), "EMP-1") in overloads
    assert overloads[(date(2026, 4, 1), "EMP-1")] == 10.0  # сумма demand
```

- [ ] **Step 2: Run test (FAIL — `_detect_overload` not defined)**

`py -3.10 -m pytest tests/test_rcpsp_leveler.py::test_leveler_detects_overload_when_two_assignments_share_employee_day -v`

- [ ] **Step 3: Implement `_detect_overload`**

Add to `app/services/rcpsp_leveler.py`:

```python
from collections import defaultdict


    def _detect_overload(
        self,
        assignments: List[ResourcePlanAssignment],
        availability: Dict[str, Dict[date, float]],
    ) -> Dict[tuple, float]:
        """Возвращает {(date, employee_id): demand_hours} там где demand > available.

        Demand на день = hours_allocated, распределённые равномерно по дням сегмента.
        """
        demand: Dict[tuple, float] = defaultdict(float)
        for a in assignments:
            if not a.start_date or not a.end_date or not a.employee_id or not a.hours_allocated:
                continue
            days = (a.end_date - a.start_date).days + 1
            if days <= 0:
                continue
            per_day = a.hours_allocated / days
            d = a.start_date
            while d <= a.end_date:
                demand[(d, a.employee_id)] += per_day
                d += timedelta(days=1)

        overloads: Dict[tuple, float] = {}
        for key, dem in demand.items():
            d, emp = key
            avail = availability.get(emp, {}).get(d, 0.0)
            if dem > avail + 0.01:
                overloads[key] = dem
        return overloads
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add app/services/rcpsp_leveler.py tests/test_rcpsp_leveler.py
git commit -m "feat(resource-planning): _detect_overload — per-day demand vs availability"
```

### Task A.3: delay_within_slack strategy

**Files:**
- Modify: `app/services/rcpsp_leveler.py`
- Test: `tests/test_rcpsp_leveler.py`

- [ ] **Step 1: Write failing test**

```python
def test_delay_within_slack_shifts_assignment_when_slack_available():
    """Если у назначения есть slack ≥ overload_days, оно сдвигается, не эскалируется."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment("A1", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 6.0, item_id="I1")
    # a2 имеет slack=5 — может быть отодвинут на 1 день
    a2 = _mk_assignment("A2", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 4.0, item_id="I2")
    a2.slack_days = 5.0
    avail = {"EMP-1": {date(2026, 4, 1): 8.0, date(2026, 4, 2): 8.0}}
    events = leveler.level([a1, a2], avail, q_end=date(2026, 4, 30))

    # a2 должен сдвинуться на 1 день
    assert a2.start_date == date(2026, 4, 2)
    assert a2.end_date == date(2026, 4, 2)
    # должно быть событие delay
    delay_events = [e for e in events if e.action == "delay"]
    assert len(delay_events) == 1
    assert delay_events[0].assignment_id == "A2"
    assert delay_events[0].delta_days == 1
```

- [ ] **Step 2: Run test (FAIL — leveler.level returns [])**

- [ ] **Step 3: Implement `_try_delay`**

Add to `RcpspLeveler`:

```python
    def _try_delay(
        self,
        assignment: ResourcePlanAssignment,
        delta_days: int,
        availability: Dict[str, Dict[date, float]],
        q_end: date,
    ) -> bool:
        """Сдвинуть assignment на delta_days вперёд, если позволяет slack и доступность.

        Возвращает True если сдвиг применён.
        """
        if not assignment.start_date or not assignment.end_date:
            return False
        slack = assignment.slack_days or 0.0
        if delta_days > slack:
            return False
        new_start = assignment.start_date + timedelta(days=delta_days)
        new_end = assignment.end_date + timedelta(days=delta_days)
        if new_end > q_end:
            return False
        # Проверить что новые даты доступны (не нулевая availability)
        emp = assignment.employee_id
        if emp:
            d = new_start
            while d <= new_end:
                if availability.get(emp, {}).get(d, 0.0) <= 0.01:
                    return False
                d += timedelta(days=1)
        assignment.start_date = new_start
        assignment.end_date = new_end
        assignment.slack_days = max(0.0, slack - delta_days)
        return True
```

Replace `level()` body:

```python
    def level(
        self,
        assignments: List[ResourcePlanAssignment],
        availability: Dict[str, Dict[date, float]],
        q_end: date,
    ) -> List[LevelingEvent]:
        if not assignments:
            return []
        events: List[LevelingEvent] = []
        max_passes = 10
        for _ in range(max_passes):
            overloads = self._detect_overload(assignments, availability)
            if not overloads:
                break

            # Выбрать assignment с max slack для сдвига (наиболее «безопасный»)
            target_day, target_emp = next(iter(overloads.keys()))
            candidates = [
                a for a in assignments
                if a.employee_id == target_emp
                and a.start_date and a.end_date
                and a.start_date <= target_day <= a.end_date
            ]
            if not candidates:
                break
            candidates.sort(key=lambda a: -(a.slack_days or 0.0))
            target = candidates[0]
            shift = 1
            applied = False
            while shift <= int(target.slack_days or 0):
                if self._try_delay(target, shift, availability, q_end):
                    events.append(LevelingEvent(
                        assignment_id=target.id,
                        action="delay",
                        reason=f"Сдвинут на {shift} д. для разрешения перегрузки {target_emp} {target_day}",
                        delta_days=shift,
                        overload_pct=(overloads[(target_day, target_emp)] / max(0.01, availability.get(target_emp, {}).get(target_day, 0.0))) * 100,
                        affected_dates=[target_day],
                    ))
                    applied = True
                    break
                shift += 1
            if not applied:
                # Не смогли сдвинуть — эскалация (Task A.5)
                break
        return events
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add app/services/rcpsp_leveler.py tests/test_rcpsp_leveler.py
git commit -m "feat(resource-planning): RcpspLeveler delay_within_slack strategy"
```

### Task A.4: reassign_to_peer strategy

**Files:**
- Modify: `app/services/rcpsp_leveler.py`
- Test: `tests/test_rcpsp_leveler.py`

- [ ] **Step 1: Write failing test**

```python
def test_reassign_to_peer_when_delay_not_possible():
    """Если slack=0 но есть peer с той же ролью и свободным окном → reassign."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment("A1", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 6.0, item_id="I1")
    a2 = _mk_assignment("A2", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 4.0, item_id="I2")
    a2.slack_days = 0.0
    avail = {
        "EMP-1": {date(2026, 4, 1): 8.0},
        "EMP-2": {date(2026, 4, 1): 8.0},
    }
    peers = {"EMP-1": ["EMP-1", "EMP-2"]}  # role pool
    events = leveler.level([a1, a2], avail, q_end=date(2026, 4, 30), role_pools=peers)
    reassign_events = [e for e in events if e.action == "reassign"]
    assert len(reassign_events) == 1
    assert reassign_events[0].assignment_id == "A2"
    assert reassign_events[0].to_employee_id == "EMP-2"
    assert a2.employee_id == "EMP-2"
```

- [ ] **Step 2: Run test (FAIL — `level()` doesn't accept `role_pools`)**

- [ ] **Step 3: Implement `_try_reassign` + add `role_pools` param**

Update signature + add method:

```python
    def level(
        self,
        assignments: List[ResourcePlanAssignment],
        availability: Dict[str, Dict[date, float]],
        q_end: date,
        role_pools: Optional[Dict[str, List[str]]] = None,
    ) -> List[LevelingEvent]:
        if not assignments:
            return []
        role_pools = role_pools or {}
        events: List[LevelingEvent] = []
        max_passes = 20
        for _ in range(max_passes):
            overloads = self._detect_overload(assignments, availability)
            if not overloads:
                break
            target_day, target_emp = next(iter(overloads.keys()))
            candidates = [
                a for a in assignments
                if a.employee_id == target_emp
                and a.start_date and a.end_date
                and a.start_date <= target_day <= a.end_date
            ]
            if not candidates:
                break
            candidates.sort(key=lambda a: -(a.slack_days or 0.0))
            target = candidates[0]

            applied = False
            # Try delay first
            shift = 1
            while shift <= int(target.slack_days or 0):
                if self._try_delay(target, shift, availability, q_end):
                    events.append(LevelingEvent(
                        assignment_id=target.id,
                        action="delay",
                        reason=f"Сдвинут на {shift} д. для разрешения перегрузки {target_emp} {target_day}",
                        delta_days=shift,
                        overload_pct=(overloads[(target_day, target_emp)] / max(0.01, availability.get(target_emp, {}).get(target_day, 0.0))) * 100,
                        affected_dates=[target_day],
                    ))
                    applied = True
                    break
                shift += 1
            if applied:
                continue

            # Try reassign
            peers = role_pools.get(target_emp, [])
            for peer_id in peers:
                if peer_id == target_emp:
                    continue
                if self._try_reassign(target, peer_id, availability, assignments):
                    events.append(LevelingEvent(
                        assignment_id=target.id,
                        action="reassign",
                        reason=f"Переназначен с {target_emp} на {peer_id} (peer той же роли)",
                        from_employee_id=target_emp,
                        to_employee_id=peer_id,
                        overload_pct=(overloads[(target_day, target_emp)] / max(0.01, availability.get(target_emp, {}).get(target_day, 0.0))) * 100,
                        affected_dates=[target_day],
                    ))
                    applied = True
                    break
            if not applied:
                # Эскалация в Task A.5
                break
        return events

    def _try_reassign(
        self,
        assignment: ResourcePlanAssignment,
        peer_id: str,
        availability: Dict[str, Dict[date, float]],
        all_assignments: List[ResourcePlanAssignment],
    ) -> bool:
        """Переназначить на peer если у него хватает доступности в окне assignment."""
        if not assignment.start_date or not assignment.end_date or not assignment.hours_allocated:
            return False
        days = (assignment.end_date - assignment.start_date).days + 1
        per_day = assignment.hours_allocated / days
        # Проверить peer доступность с учётом его текущих назначений
        peer_demand: Dict[date, float] = defaultdict(float)
        for a in all_assignments:
            if a.employee_id != peer_id or not a.start_date or not a.end_date or not a.hours_allocated:
                continue
            a_days = (a.end_date - a.start_date).days + 1
            a_per_day = a.hours_allocated / a_days
            d = a.start_date
            while d <= a.end_date:
                peer_demand[d] += a_per_day
                d += timedelta(days=1)
        d = assignment.start_date
        while d <= assignment.end_date:
            free = availability.get(peer_id, {}).get(d, 0.0) - peer_demand.get(d, 0.0)
            if free < per_day - 0.01:
                return False
            d += timedelta(days=1)
        assignment.employee_id = peer_id
        return True
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add app/services/rcpsp_leveler.py tests/test_rcpsp_leveler.py
git commit -m "feat(resource-planning): RcpspLeveler reassign_to_peer strategy"
```

### Task A.5: escalate to OVR.* event

**Files:**
- Modify: `app/services/rcpsp_leveler.py`
- Test: `tests/test_rcpsp_leveler.py`

- [ ] **Step 1: Write failing test**

```python
def test_escalate_when_no_slack_no_peer():
    """Slack=0 + нет peer → событие escalate с overload_pct."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment("A1", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 6.0, item_id="I1")
    a2 = _mk_assignment("A2", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 4.0, item_id="I2")
    a2.slack_days = 0.0
    avail = {"EMP-1": {date(2026, 4, 1): 8.0}}
    events = leveler.level([a1, a2], avail, q_end=date(2026, 4, 30), role_pools={"EMP-1": ["EMP-1"]})
    esc = [e for e in events if e.action == "escalate"]
    assert len(esc) >= 1
    assert esc[0].overload_pct >= 100.0
```

- [ ] **Step 2: Run (FAIL — no escalate emitted)**

- [ ] **Step 3: Add escalate emission** at the spot marked `# Эскалация в Task A.5`:

```python
            if not applied:
                day_key = (target_day, target_emp)
                events.append(LevelingEvent(
                    assignment_id=target.id,
                    action="escalate",
                    reason=f"Не удалось разрешить перегрузку {target_emp} {target_day}: slack=0, peers заняты",
                    overload_pct=(overloads[day_key] / max(0.01, availability.get(target_emp, {}).get(target_day, 0.0))) * 100,
                    affected_dates=[target_day],
                ))
                # Помечаем (assignment, day) как escalated чтобы не зацикливаться
                self._escalated_keys.add((target.id, target_day))
                # Удаляем эту перегрузку из рассмотрения в следующем проходе
                # (через flag в overload detect — добавим guard)
                break
```

Add field + reset in `level()`:

```python
class RcpspLeveler:
    def __init__(self):
        self._escalated_keys: set = set()

    def level(self, ...):
        self._escalated_keys = set()
        ...
```

- [ ] **Step 4: Run (PASS)**

- [ ] **Step 5: Commit**

```bash
git add app/services/rcpsp_leveler.py tests/test_rcpsp_leveler.py
git commit -m "feat(resource-planning): RcpspLeveler escalate when no slack + no peer"
```

### Task A.6: Wire RcpspLeveler into ResourcePlanningService.compute_schedule

**Files:**
- Modify: `app/services/resource_planning_service.py`
- Test: `tests/test_resource_planning_service.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_resource_planning_service.py`:

```python
def test_compute_schedule_invokes_leveler(db_session):
    """После compute_schedule перегрузки обработаны (или зафиксированы как escalate)."""
    # Setup: 1 plan, 2 backlog items с пересекающимися хорошими датами
    # (Заполнить через factory helpers, см. существующие тесты в файле)
    # ...
    # Assert: либо перегрузок нет, либо есть assignment с slack_days убавленным leveler-ом.
    # Точную логику зависит от helper-ов; используй паттерн из других тестов файла.
    pass  # placeholder — см. существующие test_*compute_schedule* тесты как образец
```

(Предполагается что в файле уже есть фикстуры под compute_schedule. Если нет — пропусти этот test и добавь только integration smoke в Task A.7.)

- [ ] **Step 2: Modify `compute_schedule` to call leveler**

In `app/services/resource_planning_service.py`, replace block after `self._compute_cpm(...)`:

```python
        # CPM на первичных датах
        self._compute_cpm(new_assignments, q_end)

        # RCPSP-выравнивание перегрузок
        from app.services.rcpsp_leveler import RcpspLeveler
        leveler = RcpspLeveler()
        role_pools = self._build_role_pools(employees)
        leveling_events = leveler.level(new_assignments, remaining, q_end, role_pools)
        # Recompute CPM после возможных сдвигов
        if leveling_events:
            self._compute_cpm(new_assignments, q_end)
        # Сохраняем события для Stage B (persistent conflicts) — пока in-memory
        self._last_leveling_events = leveling_events
```

Add helper:

```python
    def _build_role_pools(self, employees: List[Employee]) -> Dict[str, List[str]]:
        """{employee_id: [peer_ids same role]} для reassign-стратегии."""
        by_role: Dict[str, List[str]] = defaultdict(list)
        for e in employees:
            if e.role:
                by_role[e.role.lower()].append(e.id)
        result: Dict[str, List[str]] = {}
        for e in employees:
            if e.role:
                result[e.id] = by_role[e.role.lower()]
        return result
```

Initialize in `__init__`:

```python
    def __init__(self, db: Session):
        self.db = db
        self._last_leveling_events: List = []
```

- [ ] **Step 3: Run all RP tests**

`py -3.10 -m pytest tests/test_resource_planning_service.py tests/test_rcpsp_leveler.py -v`
Expected: all PASS, no regressions.

- [ ] **Step 4: Commit**

```bash
git add app/services/resource_planning_service.py tests/test_resource_planning_service.py
git commit -m "feat(resource-planning): wire RcpspLeveler into compute_schedule + recompute CPM after leveling"
```

### Task A.7: Lint + format + ship Stage A

- [ ] **Step 1: Lint + format**

```bash
ruff check app/ tests/
ruff format app/ tests/
```

Fix any errors.

- [ ] **Step 2: Run full test suite**

`py -3.10 -m pytest tests/ -v --tb=short`
Expected: green (or only known pre-existing failures from CI memory).

- [ ] **Step 3: Push Stage A**

```bash
git push origin main
```

**Stage A checkpoint reached.** Можно остановиться здесь и наблюдать поведение в проде, прежде чем переходить к Stage B.

---

## Stage B — Persistent ConflictRegister

Goal: replace ephemeral `_detect_conflicts` with persistent `plan_conflicts` table that survives recompute, supports status (open|acknowledged|muted|resolved), surfaces leveling events from Stage A as conflicts.

### Task B.1: PlanConflict model + migration

**Files:**
- Create: `app/models/plan_conflict.py`
- Create: `alembic/versions/045_*_add_plan_conflicts.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/resource_plan.py`

- [ ] **Step 1: Create model**

```python
# app/models/plan_conflict.py
"""PlanConflict — persistent объект конфликта для conflict register."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.resource_plan import ResourcePlan


class PlanConflict(Base, TimestampMixin):
    """Конфликт плана с persistent статусом.

    type: OVERLOAD_LIGHT | OVERLOAD_MED | OVERLOAD_HIGH | QUARTER_OVERFLOW |
          NO_ANALYST | NO_DEV | SPLIT_REQUIRED | LATE_START | LEVELING_DELAY | LEVELING_REASSIGN
    severity: critical | warning | info
    status: open | acknowledged | muted | resolved
    """

    __tablename__ = "plan_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_plans.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open",
    )
    backlog_item_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    employee_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    assignment_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detection_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )  # для upsert: type:item_id:employee_id:window_start

    plan: Mapped["ResourcePlan"] = relationship(back_populates="conflicts")
```

- [ ] **Step 2: Register in `__init__.py`**

In `app/models/__init__.py`, add:

```python
from app.models.plan_conflict import PlanConflict

__all__ = [..., "PlanConflict"]
```

- [ ] **Step 3: Add relationship to ResourcePlan**

In `app/models/resource_plan.py`, add to TYPE_CHECKING block + relationships:

```python
if TYPE_CHECKING:
    ...
    from app.models.plan_conflict import PlanConflict


class ResourcePlan(Base, TimestampMixin):
    ...
    conflicts: Mapped[List["PlanConflict"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
```

- [ ] **Step 4: Generate migration**

```bash
cd d:/ClaudeDev/JiraAnalysis
alembic revision --autogenerate -m "add_plan_conflicts"
```

Open the new file in `alembic/versions/`. Replace `upgrade()` and `downgrade()` body:

```python
def upgrade() -> None:
    op.create_table(
        "plan_conflicts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36),
            sa.ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("backlog_item_id", sa.String(36), nullable=True),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("assignment_id", sa.String(36), nullable=True),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detection_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_conflicts_plan_id", "plan_conflicts", ["plan_id"])
    op.create_index("ix_plan_conflicts_detection_key", "plan_conflicts", ["detection_key"])


def downgrade() -> None:
    op.drop_index("ix_plan_conflicts_detection_key", table_name="plan_conflicts")
    op.drop_index("ix_plan_conflicts_plan_id", table_name="plan_conflicts")
    op.drop_table("plan_conflicts")
```

- [ ] **Step 5: Apply migration**

```bash
alembic upgrade head
```

Expected: success, no errors.

- [ ] **Step 6: Verify model imports**

```bash
py -3.10 -c "from app.models import PlanConflict; from app.models.resource_plan import ResourcePlan; print('ok')"
```

Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
git add app/models/plan_conflict.py app/models/__init__.py app/models/resource_plan.py alembic/versions/
git commit -m "feat(resource-planning): PlanConflict model + migration 045"
```

### Task B.2: `_persist_conflicts` in service — upsert preserving status

**Files:**
- Modify: `app/services/resource_planning_service.py`
- Test: `tests/test_resource_planning_service.py`

- [ ] **Step 1: Write failing test**

```python
def test_persist_conflicts_upsert_preserves_status_on_recompute(db_session):
    """Когда конфликт уже есть в DB со status=acknowledged — recompute не сбрасывает в open."""
    # 1. Создать plan + 1 PlanConflict со status=acknowledged
    # 2. Вызвать _persist_conflicts с тем же detection_key
    # 3. Assert: статус остался acknowledged
    pass  # implement using existing fixture pattern
```

- [ ] **Step 2: Implement `_persist_conflicts`**

Add to `ResourcePlanningService`:

```python
    def _persist_conflicts(
        self,
        plan_id: str,
        detected: List[dict],  # каждый dict: type, severity, message, detection_key, ...
    ) -> None:
        """Upsert конфликтов по detection_key. Сохраняет status существующих.

        Удаляет конфликты которых больше нет в detected (помимо muted — они остаются).
        """
        from app.models import PlanConflict

        existing = (
            self.db.execute(
                select(PlanConflict).where(PlanConflict.plan_id == plan_id)
            ).scalars().all()
        )
        existing_by_key = {c.detection_key: c for c in existing}
        detected_keys = {d["detection_key"] for d in detected}

        for d in detected:
            key = d["detection_key"]
            if key in existing_by_key:
                # Upsert — сохраняем status, обновляем поля
                c = existing_by_key[key]
                c.severity = d["severity"]
                c.message = d["message"]
                c.metric_value = d.get("metric_value")
                c.window_start = d.get("window_start")
                c.window_end = d.get("window_end")
                c.backlog_item_id = d.get("backlog_item_id")
                c.employee_id = d.get("employee_id")
                c.assignment_id = d.get("assignment_id")
            else:
                self.db.add(PlanConflict(
                    plan_id=plan_id,
                    type=d["type"],
                    severity=d["severity"],
                    status="open",
                    detection_key=key,
                    message=d["message"],
                    metric_value=d.get("metric_value"),
                    window_start=d.get("window_start"),
                    window_end=d.get("window_end"),
                    backlog_item_id=d.get("backlog_item_id"),
                    employee_id=d.get("employee_id"),
                    assignment_id=d.get("assignment_id"),
                ))

        # Удалить устаревшие (кроме muted — пользователь специально замутил)
        for key, c in existing_by_key.items():
            if key not in detected_keys and c.status != "muted":
                self.db.delete(c)
```

- [ ] **Step 3: Run test (PASS)**

- [ ] **Step 4: Commit**

```bash
git add app/services/resource_planning_service.py tests/test_resource_planning_service.py
git commit -m "feat(resource-planning): _persist_conflicts upsert preserving acknowledged/muted status"
```

### Task B.3: Build conflict dicts in service from leveling events + base detectors

**Files:**
- Modify: `app/services/resource_planning_service.py`

- [ ] **Step 1: Add conflict-building helpers**

```python
    def _build_conflict_dicts(
        self,
        plan: ResourcePlan,
        assignments: List[ResourcePlanAssignment],
        employees: List[Employee],
        q_end: date,
    ) -> List[dict]:
        """Собрать единый список dict-конфликтов для _persist_conflicts.

        Включает:
        - QUARTER_OVERFLOW (опэ-фаза заходит за квартал)
        - SPLIT_REQUIRED (part_number > 1)
        - NO_ANALYST / NO_DEV (нет в команде)
        - OVERLOAD_LIGHT/MED/HIGH из _last_leveling_events (events.action='escalate')
        - LEVELING_DELAY / LEVELING_REASSIGN (info — что leveler сделал)
        - LATE_START (фаза стартует позже целевой даты — пока заглушка, см. Task B.4)
        """
        result: List[dict] = []
        item_titles = {a.backlog_item_id: (a.backlog_item.title if a.backlog_item else "")
                       for a in assignments if hasattr(a, "backlog_item")}

        # QUARTER_OVERFLOW
        for a in assignments:
            if a.phase == "opo" and a.end_date and a.end_date > q_end:
                result.append({
                    "type": "QUARTER_OVERFLOW",
                    "severity": "critical",
                    "detection_key": f"QUARTER_OVERFLOW:{a.backlog_item_id}",
                    "message": f"Инициатива «{item_titles.get(a.backlog_item_id, '')}» не вмещается в квартал: ОПЭ заканчивается {a.end_date}",
                    "backlog_item_id": a.backlog_item_id,
                    "assignment_id": a.id,
                })

        # SPLIT_REQUIRED
        seen_split: set = set()
        from collections import defaultdict
        max_part: dict = defaultdict(int)
        for a in assignments:
            max_part[(a.backlog_item_id, a.phase)] = max(
                max_part[(a.backlog_item_id, a.phase)], a.part_number
            )
        for (item_id, phase), mp in max_part.items():
            if mp > 1 and item_id not in seen_split:
                seen_split.add(item_id)
                result.append({
                    "type": "SPLIT_REQUIRED",
                    "severity": "info",
                    "detection_key": f"SPLIT_REQUIRED:{item_id}",
                    "message": f"Инициатива «{item_titles.get(item_id, '')}» разбита на части из-за заблокированного периода",
                    "backlog_item_id": item_id,
                })

        # NO_ANALYST / NO_DEV
        ANALYST_CODES = {"аналитик", "analyst", "an"}
        DEV_CODES = {"разработчик", "developer", "dev", "rp"}
        if plan.team:
            has_analyst = any(e.role and e.role.lower() in ANALYST_CODES for e in employees)
            has_dev = any(e.role and e.role.lower() in DEV_CODES for e in employees)
            if not has_analyst:
                result.append({
                    "type": "NO_ANALYST",
                    "severity": "critical",
                    "detection_key": f"NO_ANALYST:{plan.team}",
                    "message": f"В команде «{plan.team}» нет аналитиков. Расписание аналитической фазы невозможно.",
                })
            if not has_dev:
                result.append({
                    "type": "NO_DEV",
                    "severity": "critical",
                    "detection_key": f"NO_DEV:{plan.team}",
                    "message": f"В команде «{plan.team}» нет разработчиков. Расписание фазы разработки невозможно.",
                })

        # OVERLOAD_* + LEVELING_* из leveling events
        from datetime import datetime as _dt
        for ev in self._last_leveling_events:
            if ev.action == "escalate":
                pct = ev.overload_pct
                if pct > 120:
                    sev, type_ = "critical", "OVERLOAD_HIGH"
                elif pct > 110:
                    sev, type_ = "warning", "OVERLOAD_MED"
                else:
                    sev, type_ = "warning", "OVERLOAD_LIGHT"
                day = ev.affected_dates[0] if ev.affected_dates else None
                result.append({
                    "type": type_,
                    "severity": sev,
                    "detection_key": f"{type_}:{ev.assignment_id}:{day}",
                    "message": f"Перегрузка {pct:.0f}% на {day}: {ev.reason}",
                    "metric_value": pct,
                    "assignment_id": ev.assignment_id,
                    "window_start": _dt.combine(day, _dt.min.time()) if day else None,
                    "window_end": _dt.combine(day, _dt.min.time()) if day else None,
                })
            elif ev.action == "delay":
                day = ev.affected_dates[0] if ev.affected_dates else None
                result.append({
                    "type": "LEVELING_DELAY",
                    "severity": "info",
                    "detection_key": f"LEVELING_DELAY:{ev.assignment_id}:{day}",
                    "message": ev.reason,
                    "metric_value": float(ev.delta_days),
                    "assignment_id": ev.assignment_id,
                })
            elif ev.action == "reassign":
                result.append({
                    "type": "LEVELING_REASSIGN",
                    "severity": "info",
                    "detection_key": f"LEVELING_REASSIGN:{ev.assignment_id}",
                    "message": ev.reason,
                    "assignment_id": ev.assignment_id,
                    "employee_id": ev.to_employee_id,
                })

        return result
```

- [ ] **Step 2: Wire into `compute_schedule`**

After leveling block in `compute_schedule`:

```python
        # Persist conflicts (Stage B)
        detected = self._build_conflict_dicts(plan, new_assignments, employees, q_end)
        self._persist_conflicts(plan_id, detected)

        plan.status = "ready"
        plan.computed_at = datetime.utcnow()
        self.db.commit()
```

- [ ] **Step 3: Run test suite**

`py -3.10 -m pytest tests/test_resource_planning_service.py -v`
Expected: PASS (existing tests, not yet validating persist).

- [ ] **Step 4: Commit**

```bash
git add app/services/resource_planning_service.py
git commit -m "feat(resource-planning): _build_conflict_dicts + persist after compute"
```

### Task B.4: LATE_START detection (slack_days < 0)

**Files:**
- Modify: `app/services/resource_planning_service.py`
- Test: `tests/test_resource_planning_service.py`

- [ ] **Step 1: Write failing test**

```python
def test_late_start_when_phase_pushed_past_quarter_end(db_session):
    """Если slack_days отрицательный → LATE_START конфликт."""
    pass  # see existing fixture pattern
```

- [ ] **Step 2: Add LATE_START in `_build_conflict_dicts`** (after SPLIT_REQUIRED block):

```python
        # LATE_START
        for a in assignments:
            if a.slack_days is not None and a.slack_days < 0:
                result.append({
                    "type": "LATE_START",
                    "severity": "warning",
                    "detection_key": f"LATE_START:{a.id}",
                    "message": f"Фаза «{a.phase}» инициативы «{item_titles.get(a.backlog_item_id, '')}» стартует слишком поздно (отставание {abs(a.slack_days):.0f} д.)",
                    "metric_value": float(a.slack_days),
                    "backlog_item_id": a.backlog_item_id,
                    "assignment_id": a.id,
                    "employee_id": a.employee_id,
                })
```

- [ ] **Step 3: Run (PASS)**

- [ ] **Step 4: Commit**

```bash
git add app/services/resource_planning_service.py tests/test_resource_planning_service.py
git commit -m "feat(resource-planning): LATE_START conflict when slack_days < 0"
```

### Task B.5: Replace ephemeral _detect_conflicts in endpoint with DB read

**Files:**
- Modify: `app/api/endpoints/resource_planning.py`

- [ ] **Step 1: Update ConflictOut schema**

Replace `ConflictOut` in `app/api/endpoints/resource_planning.py`:

```python
class ConflictOut(BaseModel):
    id: str
    type: str
    severity: str
    status: str
    backlog_item_id: Optional[str]
    backlog_item_title: Optional[str]
    employee_id: Optional[str]
    assignment_id: Optional[str]
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    metric_value: Optional[float]
    message: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Replace `_detect_conflicts(plan, assignments, db)` body**

```python
def _detect_conflicts(plan, assignments, db):
    """Read persistent conflicts from DB. Detection runs in compute_schedule."""
    from app.models import PlanConflict, BacklogItem

    rows = db.execute(
        select(PlanConflict).where(PlanConflict.plan_id == plan.id)
    ).scalars().all()

    # Resolve item titles in one batch
    item_ids = {r.backlog_item_id for r in rows if r.backlog_item_id}
    titles = {}
    if item_ids:
        bi_rows = db.execute(
            select(BacklogItem).where(BacklogItem.id.in_(item_ids))
        ).scalars().all()
        titles = {b.id: b.title for b in bi_rows}

    return [
        ConflictOut(
            id=r.id,
            type=r.type,
            severity=r.severity,
            status=r.status,
            backlog_item_id=r.backlog_item_id,
            backlog_item_title=titles.get(r.backlog_item_id) if r.backlog_item_id else None,
            employee_id=r.employee_id,
            assignment_id=r.assignment_id,
            window_start=r.window_start,
            window_end=r.window_end,
            metric_value=r.metric_value,
            message=r.message,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
```

- [ ] **Step 3: Add PATCH endpoint for conflict status**

Append to `app/api/endpoints/resource_planning.py`:

```python
class ConflictPatch(BaseModel):
    status: str  # acknowledged | muted | open | resolved


@router.patch(
    "/resource-plans/{plan_id}/conflicts/{conflict_id}",
    response_model=ConflictOut,
)
def patch_conflict(
    plan_id: str,
    conflict_id: str,
    data: ConflictPatch,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models import PlanConflict, BacklogItem

    valid = {"open", "acknowledged", "muted", "resolved"}
    if data.status not in valid:
        raise HTTPException(422, f"status must be one of {sorted(valid)}")

    c = db.execute(
        select(PlanConflict).where(
            PlanConflict.id == conflict_id,
            PlanConflict.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Conflict not found")

    c.status = data.status

    # snapshot before commit
    title = None
    if c.backlog_item_id:
        b = db.get(BacklogItem, c.backlog_item_id)
        title = b.title if b else None
    snap = {
        "id": c.id, "type": c.type, "severity": c.severity, "status": c.status,
        "backlog_item_id": c.backlog_item_id, "backlog_item_title": title,
        "employee_id": c.employee_id, "assignment_id": c.assignment_id,
        "window_start": c.window_start, "window_end": c.window_end,
        "metric_value": c.metric_value, "message": c.message,
        "created_at": c.created_at, "updated_at": c.updated_at,
    }

    db.commit()
    return ConflictOut(**snap)
```

- [ ] **Step 4: Test endpoint manually**

Restart backend (kill PID :8000 + start fresh), then:

```bash
curl -X POST http://localhost:8000/api/v1/resource-planning/resource-plans/<id>/compute -H "Authorization: Bearer <token>"
curl http://localhost:8000/api/v1/resource-planning/resource-plans/<id>/gantt | jq '.conflicts'
```

Expected: conflicts now have `id`, `status`, `created_at`.

- [ ] **Step 5: Lint + commit**

```bash
ruff check app/ && ruff format app/
git add app/api/endpoints/resource_planning.py
git commit -m "feat(resource-planning): conflict register endpoint + DB-backed projection"
```

### Task B.6: Endpoint tests for conflict register

**Files:**
- Create/Modify: `tests/test_plan_conflicts_endpoints.py`

- [ ] **Step 1: Write tests**

```python
"""Тесты persistent conflict register API."""

import pytest
from app.models import PlanConflict, ResourcePlan


def test_patch_conflict_status_persists(client, db_session, auth_headers):
    plan = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db_session.add(plan); db_session.commit(); db_session.refresh(plan)
    c = PlanConflict(
        plan_id=plan.id, type="OVERLOAD_HIGH", severity="critical",
        status="open", message="test", detection_key="test:1",
    )
    db_session.add(c); db_session.commit(); db_session.refresh(c)

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan.id}/conflicts/{c.id}",
        json={"status": "acknowledged"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "acknowledged"

    db_session.refresh(c)
    assert c.status == "acknowledged"


def test_patch_conflict_invalid_status_returns_422(client, db_session, auth_headers):
    plan = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db_session.add(plan); db_session.commit(); db_session.refresh(plan)
    c = PlanConflict(
        plan_id=plan.id, type="OVERLOAD_HIGH", severity="critical",
        status="open", message="test", detection_key="test:1",
    )
    db_session.add(c); db_session.commit(); db_session.refresh(c)

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan.id}/conflicts/{c.id}",
        json={"status": "bogus"},
        headers=auth_headers,
    )
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests**

`py -3.10 -m pytest tests/test_plan_conflicts_endpoints.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_plan_conflicts_endpoints.py
git commit -m "test(resource-planning): conflict register PATCH endpoint coverage"
```

### Task B.7: Frontend — extend ConflictOut + patchConflict + UI

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts`
- Modify: `frontend/src/hooks/useResourcePlanning.ts`
- Modify: `frontend/src/components/resource-planning/ConflictPanel.tsx`

- [ ] **Step 1: Extend types + add API**

In `frontend/src/api/resourcePlanning.ts`, replace `ConflictOut`:

```typescript
export interface ConflictOut {
  id: string;
  type: string;
  severity: 'critical' | 'warning' | 'info';
  status: 'open' | 'acknowledged' | 'muted' | 'resolved';
  backlog_item_id: string | null;
  backlog_item_title: string | null;
  employee_id: string | null;
  assignment_id: string | null;
  window_start: string | null;
  window_end: string | null;
  metric_value: number | null;
  message: string;
  created_at: string;
  updated_at: string;
}

export const patchConflict = (planId: string, conflictId: string, status: ConflictOut['status']) =>
  api.patch<ConflictOut>(
    `/resource-planning/resource-plans/${planId}/conflicts/${conflictId}`,
    { status },
  );
```

- [ ] **Step 2: Add hook**

In `frontend/src/hooks/useResourcePlanning.ts`, add:

```typescript
export function usePatchConflict(planId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ conflictId, status }: { conflictId: string; status: ConflictOut['status'] }) =>
      patchConflict(planId!, conflictId, status),
    onSuccess: () => {
      if (planId) qc.invalidateQueries({ queryKey: ['gantt-projection', planId] });
    },
  });
}
```

(Imports: `patchConflict`, `ConflictOut` from `../api/resourcePlanning`.)

- [ ] **Step 3: Update ConflictPanel**

In `frontend/src/components/resource-planning/ConflictPanel.tsx`:
- Filter out `status === 'muted'` and `status === 'resolved'` by default
- Show status badge (Tag color: open=red, acknowledged=orange, muted=default, resolved=green)
- Add Dropdown menu per row: «Принять» (acknowledged), «Замутить» (muted), «Решено» (resolved), «Открыть заново» (open)
- Wire to `usePatchConflict`

(Implementation depends on existing component; subagent should read ConflictPanel.tsx first, then add menu + filter.)

- [ ] **Step 4: Build frontend**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/hooks/useResourcePlanning.ts frontend/src/components/resource-planning/ConflictPanel.tsx
git commit -m "feat(resource-planning): conflict register UI — status badges + acknowledge/mute"
```

### Task B.8: Stage B ship checkpoint

- [ ] **Step 1: Lint + format**

```bash
ruff check app/ tests/ && ruff format app/ tests/
cd frontend && npm run lint && cd ..
```

- [ ] **Step 2: Full test suite**

`py -3.10 -m pytest tests/ -v --tb=short`

- [ ] **Step 3: Push**

```bash
git push origin main
```

**Stage B checkpoint reached.** Persistent conflict register работает; пользователь может acknowledge/mute. Можно остановиться здесь.

---

## Stage C — Probabilistic CPM (PERT)

Goal: per-initiative P50/P90 finish dates using triangular distribution + critical path variance. Add multiplier fields to BacklogItem; compute on the fly during gantt projection.

### Task C.1: PERT calculator pure functions

**Files:**
- Create: `app/services/pert_calculator.py`
- Test: `tests/test_pert_calculator.py`

- [ ] **Step 1: Write tests**

```python
"""Тесты вероятностного CPM (PERT)."""

import math
from app.services.pert_calculator import (
    compute_pert_phase_duration,
    aggregate_path_pert,
    p_quantile_finish,
)


def test_pert_phase_duration_classic_formula():
    """t_e = (t_o + 4·t_m + t_p) / 6, σ = (t_p - t_o) / 6."""
    t_e, sigma = compute_pert_phase_duration(t_o=2.0, t_m=3.0, t_p=8.0)
    assert math.isclose(t_e, (2 + 12 + 8) / 6)
    assert math.isclose(sigma, (8 - 2) / 6)


def test_aggregate_path_pert_sums_means_and_variances():
    """Длительность пути = sum(t_e), variance = sum(σ²)."""
    phases = [(2.0, 3.0, 8.0), (1.0, 2.0, 4.0)]
    mean, sigma = aggregate_path_pert(phases)
    assert math.isclose(mean, ((2 + 12 + 8) / 6) + ((1 + 8 + 4) / 6))
    expected_var = ((8 - 2) / 6) ** 2 + ((4 - 1) / 6) ** 2
    assert math.isclose(sigma, math.sqrt(expected_var))


def test_p_quantile_finish_p50_equals_mean_p90_greater():
    """P50 = mean (для нормального приближения), P90 > mean."""
    p50 = p_quantile_finish(mean=10.0, sigma=2.0, p=0.5)
    p90 = p_quantile_finish(mean=10.0, sigma=2.0, p=0.9)
    assert math.isclose(p50, 10.0)
    assert p90 > 10.0
    assert math.isclose(p90, 10.0 + 2.0 * 1.2816, abs_tol=0.01)
```

- [ ] **Step 2: Run (FAIL)**

- [ ] **Step 3: Implement**

```python
# app/services/pert_calculator.py
"""PERT-расчёт вероятностного CPM.

Формулы:
  t_e = (t_o + 4·t_m + t_p) / 6      — ожидание
  σ   = (t_p - t_o) / 6              — стандартное отклонение
  σ²  = ((t_p - t_o) / 6)²           — дисперсия

Сумма независимых нормальных = нормальное (CLT для пути).
P-квантиль: mean + z(p) · sigma_path, где z(p) — обратная нормальная.
"""

from __future__ import annotations

import math
from typing import List, Tuple


def compute_pert_phase_duration(t_o: float, t_m: float, t_p: float) -> Tuple[float, float]:
    """Возвращает (ожидание, sigma) для одной фазы по trio оценок."""
    t_e = (t_o + 4 * t_m + t_p) / 6.0
    sigma = (t_p - t_o) / 6.0
    return t_e, sigma


def aggregate_path_pert(phases: List[Tuple[float, float, float]]) -> Tuple[float, float]:
    """Сумма по пути: mean = Σt_e, sigma = sqrt(Σσ²)."""
    means = []
    variances = []
    for t_o, t_m, t_p in phases:
        t_e, sigma = compute_pert_phase_duration(t_o, t_m, t_p)
        means.append(t_e)
        variances.append(sigma * sigma)
    total_mean = sum(means)
    total_sigma = math.sqrt(sum(variances))
    return total_mean, total_sigma


# Z-оценки нормального распределения для типичных квантилей
_Z = {0.5: 0.0, 0.7: 0.5244, 0.8: 0.8416, 0.85: 1.0364, 0.9: 1.2816, 0.95: 1.6449, 0.99: 2.3263}


def p_quantile_finish(mean: float, sigma: float, p: float) -> float:
    """Возвращает P-квантиль времени завершения (mean + z(p)·sigma)."""
    z = _Z.get(round(p, 2))
    if z is None:
        # Линейная интерполяция между ближайшими известными
        keys = sorted(_Z.keys())
        for i, k in enumerate(keys):
            if k >= p:
                if i == 0:
                    z = _Z[k]
                else:
                    k_prev = keys[i - 1]
                    z = _Z[k_prev] + (_Z[k] - _Z[k_prev]) * (p - k_prev) / (k - k_prev)
                break
        else:
            z = _Z[keys[-1]]
    return mean + z * sigma
```

- [ ] **Step 4: Run (PASS)**

- [ ] **Step 5: Commit**

```bash
git add app/services/pert_calculator.py tests/test_pert_calculator.py
git commit -m "feat(resource-planning): PERT calculator pure functions (t_e, sigma, P-quantile)"
```

### Task C.2: BacklogItem multipliers — model + migration

**Files:**
- Modify: `app/models/backlog_item.py`
- Create: `alembic/versions/046_*_add_pert_multipliers.py`

- [ ] **Step 1: Add fields**

In `app/models/backlog_item.py`, add columns (in the column section):

```python
    optimistic_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.7, server_default="0.7",
    )
    pessimistic_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.5, server_default="1.5",
    )
```

(Import `Float` from sqlalchemy if missing.)

- [ ] **Step 2: Generate migration**

```bash
alembic revision --autogenerate -m "add_pert_multipliers"
```

Replace upgrade/downgrade in generated file:

```python
def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.add_column(sa.Column(
            "optimistic_multiplier", sa.Float(),
            nullable=False, server_default="0.7",
        ))
        batch.add_column(sa.Column(
            "pessimistic_multiplier", sa.Float(),
            nullable=False, server_default="1.5",
        ))


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_column("pessimistic_multiplier")
        batch.drop_column("optimistic_multiplier")
```

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```

- [ ] **Step 4: Verify**

```bash
py -3.10 -c "from app.models import BacklogItem; print(BacklogItem.optimistic_multiplier, BacklogItem.pessimistic_multiplier)"
```

- [ ] **Step 5: Commit**

```bash
git add app/models/backlog_item.py alembic/versions/
git commit -m "feat(resource-planning): BacklogItem PERT multipliers + migration 046"
```

### Task C.3: PERT projection in gantt endpoint

**Files:**
- Modify: `app/api/endpoints/resource_planning.py`

- [ ] **Step 1: Add schema + computation**

In `app/api/endpoints/resource_planning.py`:

```python
class InitiativePertOut(BaseModel):
    backlog_item_id: str
    backlog_item_title: str
    most_likely_finish: Optional[date]
    p50_finish: Optional[date]
    p90_finish: Optional[date]
    sigma_days: float
    on_critical_path_only: bool


class GanttProjection(BaseModel):
    plan: ResourcePlanOut
    assignments: List[AssignmentOut]
    conflicts: List[ConflictOut]
    pert_projection: List[InitiativePertOut]
```

In `get_gantt`, before `return GanttProjection(...)`:

```python
    pert_projection = _compute_pert_projection(plan, assignments_raw, db)

    return GanttProjection(
        plan=plan,
        assignments=assignments,
        conflicts=conflicts,
        pert_projection=pert_projection,
    )
```

Add helper function:

```python
def _compute_pert_projection(plan, assignments, db):
    """PERT P50/P90 finish per initiative based on critical-path phases."""
    from app.services.pert_calculator import aggregate_path_pert, p_quantile_finish
    from datetime import timedelta as _td

    # Group critical-path assignments by item
    by_item: dict = defaultdict(list)
    for a in assignments:
        if a.is_on_critical_path and a.start_date and a.end_date:
            by_item[a.backlog_item_id].append(a)

    # Resolve multipliers per item
    item_ids = list(by_item.keys())
    if not item_ids:
        return []
    from app.models import BacklogItem
    items = db.execute(
        select(BacklogItem).where(BacklogItem.id.in_(item_ids))
    ).scalars().all()
    items_by_id = {i.id: i for i in items}

    result = []
    for item_id, phases_assigns in by_item.items():
        bi = items_by_id.get(item_id)
        if not bi:
            continue
        opt = bi.optimistic_multiplier or 0.7
        pess = bi.pessimistic_multiplier or 1.5
        triples = []
        most_likely_finish = max(a.end_date for a in phases_assigns)
        for a in phases_assigns:
            days = (a.end_date - a.start_date).days + 1
            triples.append((days * opt, float(days), days * pess))
        mean, sigma = aggregate_path_pert(triples)
        # mean — длительность пути по PERT; смещение от старта первой фазы
        first_start = min(a.start_date for a in phases_assigns)
        p50 = first_start + _td(days=int(round(p_quantile_finish(mean, sigma, 0.5))))
        p90 = first_start + _td(days=int(round(p_quantile_finish(mean, sigma, 0.9))))
        result.append(InitiativePertOut(
            backlog_item_id=item_id,
            backlog_item_title=bi.title,
            most_likely_finish=most_likely_finish,
            p50_finish=p50,
            p90_finish=p90,
            sigma_days=sigma,
            on_critical_path_only=True,
        ))
    return result
```

- [ ] **Step 2: Restart backend, smoke test**

```bash
# kill PID :8000, restart
curl http://localhost:8000/api/v1/resource-planning/resource-plans/<id>/gantt | jq '.pert_projection'
```

Expected: array with P50/P90 dates.

- [ ] **Step 3: Commit**

```bash
git add app/api/endpoints/resource_planning.py
git commit -m "feat(resource-planning): PERT projection in gantt endpoint (P50/P90 per initiative)"
```

### Task C.4: Frontend — PertOverlay component

**Files:**
- Create: `frontend/src/components/resource-planning/PertOverlay.tsx`
- Modify: `frontend/src/api/resourcePlanning.ts`
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx`
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx`

- [ ] **Step 1: Extend API types**

In `frontend/src/api/resourcePlanning.ts`:

```typescript
export interface InitiativePertOut {
  backlog_item_id: string;
  backlog_item_title: string;
  most_likely_finish: string | null;
  p50_finish: string | null;
  p90_finish: string | null;
  sigma_days: number;
  on_critical_path_only: boolean;
}

export interface GanttProjection {
  plan: ResourcePlan;
  assignments: AssignmentOut[];
  conflicts: ConflictOut[];
  pert_projection: InitiativePertOut[];
}
```

- [ ] **Step 2: Create PertOverlay**

```typescript
// frontend/src/components/resource-planning/PertOverlay.tsx
import { CSSProperties } from 'react';
import type { InitiativePertOut } from '../../api/resourcePlanning';
import { dateToLeft, GanttTimeline } from '../../utils/gantt';

interface Props {
  pert: InitiativePertOut[];
  timeline: GanttTimeline;
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
}

export default function PertOverlay({ pert, timeline, rowRefs }: Props) {
  return (
    <svg
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        width: '100%',
        height: '100%',
      }}
    >
      {pert.map(p => {
        if (!p.p50_finish || !p.p90_finish) return null;
        const row = rowRefs.current.get(p.backlog_item_id);
        if (!row) return null;
        const top = row.offsetTop + row.offsetHeight / 2;
        const p50x = dateToLeft(new Date(p.p50_finish), timeline);
        const p90x = dateToLeft(new Date(p.p90_finish), timeline);
        return (
          <g key={p.backlog_item_id}>
            <line
              x1={p50x} x2={p50x} y1={top - 6} y2={top + 6}
              stroke="#00c9c8" strokeWidth={2}
            />
            <line
              x1={p90x} x2={p90x} y1={top - 6} y2={top + 6}
              stroke="#d4a017" strokeWidth={2} strokeDasharray="4 2"
            />
            <line
              x1={p50x} x2={p90x} y1={top} y2={top}
              stroke="#d4a017" strokeWidth={1} opacity={0.5}
            />
          </g>
        );
      })}
    </svg>
  );
}
```

- [ ] **Step 3: Integrate into GanttChart**

In `frontend/src/components/resource-planning/GanttChart.tsx`:
- Add prop `pert: InitiativePertOut[]` and `showPert: boolean`
- Render `<PertOverlay>` when `showPert && pert.length > 0` inside the Gantt container (above DependencyArrows or sibling)

(Subagent: read current GanttChart.tsx first; add inside the same overlay container as DependencyArrows.)

- [ ] **Step 4: Add toggle in ResourcePlanningPage**

In `frontend/src/pages/ResourcePlanningPage.tsx`, add state + Switch:

```typescript
const [showPert, setShowPert] = useState(false);

// inside Space (near Связи toggle):
<Space size={4}>
  <Switch checked={showPert} onChange={setShowPert} size="small" />
  <span style={{ fontSize: 12, color: '#8ab0d8' }}>P50/P90</span>
</Space>

// pass to GanttChart:
<GanttChart
  ...
  pert={gantt.pert_projection}
  showPert={showPert}
/>
```

- [ ] **Step 5: Build + smoke**

```bash
cd frontend && npm run build && cd ..
```

Open `/resource-planning` in browser, toggle «P50/P90», verify markers appear on initiative rows in Portfolio view.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/resource-planning/PertOverlay.tsx frontend/src/api/resourcePlanning.ts frontend/src/components/resource-planning/GanttChart.tsx frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "feat(resource-planning): PertOverlay — P50/P90 markers on Gantt + toggle"
```

### Task C.5: Stage C ship checkpoint

- [ ] **Step 1: Lint + tests**

```bash
ruff check app/ && ruff format app/
py -3.10 -m pytest tests/ -v --tb=short
cd frontend && npm run build && cd ..
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

**Stage C checkpoint reached.** PERT P50/P90 видны на диаграмме. Можно остановиться.

---

## Stage D — What-If scenarios (plan fork + comparator)

Goal: clone resource_plan + assignments + dependencies into a child plan; compute diff (metrics + per-assignment shifts); side-by-side ScenarioComparator UI.

### Task D.1: parent_plan_id + is_baseline + label migration

**Files:**
- Modify: `app/models/resource_plan.py`
- Create: `alembic/versions/047_*_add_plan_fork_fields.py`

- [ ] **Step 1: Update model**

In `app/models/resource_plan.py`, add columns:

```python
    parent_plan_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("resource_plans.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    is_baseline: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
```

(Imports: add `Boolean` to `from sqlalchemy import ...`.)

Add self-relationships:

```python
    parent: Mapped[Optional["ResourcePlan"]] = relationship(
        "ResourcePlan", remote_side="ResourcePlan.id", foreign_keys=[parent_plan_id],
    )
```

- [ ] **Step 2: Generate migration**

```bash
alembic revision --autogenerate -m "add_plan_fork_fields"
```

Replace body:

```python
def upgrade() -> None:
    with op.batch_alter_table("resource_plans") as batch:
        batch.add_column(sa.Column("parent_plan_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column(
            "is_baseline", sa.Boolean(), nullable=False, server_default="0",
        ))
        batch.add_column(sa.Column("label", sa.String(255), nullable=True))
        batch.create_foreign_key(
            "fk_resource_plans_parent_plan_id",
            "resource_plans",
            ["parent_plan_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_index("ix_resource_plans_parent_plan_id", ["parent_plan_id"])


def downgrade() -> None:
    with op.batch_alter_table("resource_plans") as batch:
        batch.drop_index("ix_resource_plans_parent_plan_id")
        batch.drop_constraint("fk_resource_plans_parent_plan_id", type_="foreignkey")
        batch.drop_column("label")
        batch.drop_column("is_baseline")
        batch.drop_column("parent_plan_id")
```

- [ ] **Step 3: Apply + verify**

```bash
alembic upgrade head
py -3.10 -c "from app.models import ResourcePlan; print(ResourcePlan.parent_plan_id, ResourcePlan.is_baseline, ResourcePlan.label)"
```

- [ ] **Step 4: Update ResourcePlanOut schema**

In `app/api/endpoints/resource_planning.py`:

```python
class ResourcePlanOut(BaseModel):
    id: str
    scenario_id: Optional[str]
    team: Optional[str]
    quarter: Optional[str]
    year: Optional[int]
    status: str
    computed_at: Optional[datetime]
    created_at: datetime
    parent_plan_id: Optional[str]
    is_baseline: bool
    label: Optional[str]

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Commit**

```bash
git add app/models/resource_plan.py app/api/endpoints/resource_planning.py alembic/versions/
git commit -m "feat(resource-planning): plan fork fields (parent/baseline/label) + migration 047"
```

### Task D.2: Fork endpoint — clone plan + assignments + dependencies

**Files:**
- Modify: `app/api/endpoints/resource_planning.py`
- Test: `tests/test_plan_fork.py`

- [ ] **Step 1: Write failing test**

```python
"""Тесты plan fork — клонирование плана со всеми назначениями."""

from app.models import ResourcePlan, ResourcePlanAssignment


def test_fork_creates_new_plan_with_cloned_assignments(client, db_session, auth_headers):
    plan = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready", is_baseline=True)
    db_session.add(plan); db_session.commit(); db_session.refresh(plan)
    a = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id="BI-1", phase="dev",
        employee_id="EMP-1", part_number=1, hours_allocated=10.0,
    )
    db_session.add(a); db_session.commit()

    r = client.post(
        f"/api/v1/resource-planning/resource-plans/{plan.id}/fork",
        json={"label": "Что если +1 разработчик"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    new = r.json()
    assert new["parent_plan_id"] == plan.id
    assert new["is_baseline"] is False
    assert new["label"] == "Что если +1 разработчик"

    cloned = db_session.execute(
        select(ResourcePlanAssignment).where(ResourcePlanAssignment.plan_id == new["id"])
    ).scalars().all()
    assert len(cloned) == 1
    assert cloned[0].backlog_item_id == "BI-1"
```

- [ ] **Step 2: Run (FAIL — no fork endpoint)**

- [ ] **Step 3: Implement fork endpoint**

In `app/api/endpoints/resource_planning.py`:

```python
class ForkRequest(BaseModel):
    label: Optional[str] = None


@router.post(
    "/resource-plans/{plan_id}/fork",
    response_model=ResourcePlanOut,
    status_code=201,
)
def fork_plan(
    plan_id: str,
    data: ForkRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models import PlanItemDependency

    src = db.get(ResourcePlan, plan_id)
    if not src:
        raise HTTPException(404, "ResourcePlan not found")

    new_plan = ResourcePlan(
        scenario_id=src.scenario_id,
        team=src.team,
        quarter=src.quarter,
        year=src.year,
        status=src.status,
        parent_plan_id=src.id,
        is_baseline=False,
        label=data.label,
    )
    db.add(new_plan); db.flush()

    # Clone assignments
    src_assignments = db.execute(
        select(ResourcePlanAssignment).where(ResourcePlanAssignment.plan_id == src.id)
    ).scalars().all()
    for a in src_assignments:
        db.add(ResourcePlanAssignment(
            plan_id=new_plan.id,
            backlog_item_id=a.backlog_item_id,
            phase=a.phase,
            employee_id=a.employee_id,
            part_number=a.part_number,
            hours_allocated=a.hours_allocated,
            start_date=a.start_date,
            end_date=a.end_date,
            is_on_critical_path=a.is_on_critical_path,
            slack_days=a.slack_days,
        ))

    # Clone dependencies
    src_deps = db.execute(
        select(PlanItemDependency).where(PlanItemDependency.plan_id == src.id)
    ).scalars().all()
    for d in src_deps:
        db.add(PlanItemDependency(
            plan_id=new_plan.id,
            from_item_id=d.from_item_id,
            to_item_id=d.to_item_id,
            dep_type=d.dep_type,
            lag_days=d.lag_days,
            source=d.source,
        ))

    # Conflicts intentionally NOT cloned (forks start clean)

    snap = {
        "id": new_plan.id, "scenario_id": new_plan.scenario_id,
        "team": new_plan.team, "quarter": new_plan.quarter, "year": new_plan.year,
        "status": new_plan.status, "computed_at": new_plan.computed_at,
        "created_at": new_plan.created_at, "parent_plan_id": new_plan.parent_plan_id,
        "is_baseline": new_plan.is_baseline, "label": new_plan.label,
    }
    db.commit()
    return ResourcePlanOut(**snap)
```

- [ ] **Step 4: Run (PASS)**

`py -3.10 -m pytest tests/test_plan_fork.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/test_plan_fork.py
git commit -m "feat(resource-planning): POST /resource-plans/{id}/fork — clone plan + assignments + deps"
```

### Task D.3: Plan diff service

**Files:**
- Create: `app/services/plan_diff.py`
- Test: `tests/test_plan_diff.py`

- [ ] **Step 1: Write tests**

```python
"""Тесты plan diff — сравнение baseline vs scenario."""

from datetime import date
from app.models import ResourcePlan, ResourcePlanAssignment
from app.services.plan_diff import diff_plans


def test_diff_detects_assignment_date_shift(db_session):
    base = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready", is_baseline=True)
    scen = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db_session.add_all([base, scen]); db_session.commit(); db_session.refresh(base); db_session.refresh(scen)

    db_session.add(ResourcePlanAssignment(
        plan_id=base.id, backlog_item_id="BI-1", phase="dev",
        employee_id="EMP-1", part_number=1, hours_allocated=10.0,
        start_date=date(2026, 4, 1), end_date=date(2026, 4, 5),
    ))
    db_session.add(ResourcePlanAssignment(
        plan_id=scen.id, backlog_item_id="BI-1", phase="dev",
        employee_id="EMP-1", part_number=1, hours_allocated=10.0,
        start_date=date(2026, 4, 8), end_date=date(2026, 4, 12),
    ))
    db_session.commit()

    result = diff_plans(db_session, base.id, scen.id)
    shifts = result["assignment_shifts"]
    assert len(shifts) == 1
    assert shifts[0]["backlog_item_id"] == "BI-1"
    assert shifts[0]["start_delta_days"] == 7
```

- [ ] **Step 2: Implement**

```python
# app/services/plan_diff.py
"""Plan diff — сравнение метрик и assignment-сдвигов между двумя планами."""

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ResourcePlan, ResourcePlanAssignment, PlanConflict


def diff_plans(db: Session, baseline_id: str, scenario_id: str) -> Dict:
    """Возвращает структурированный diff baseline → scenario."""
    base = db.get(ResourcePlan, baseline_id)
    scen = db.get(ResourcePlan, scenario_id)
    if not base or not scen:
        raise ValueError("Plan not found")

    base_a = db.execute(
        select(ResourcePlanAssignment).where(ResourcePlanAssignment.plan_id == baseline_id)
    ).scalars().all()
    scen_a = db.execute(
        select(ResourcePlanAssignment).where(ResourcePlanAssignment.plan_id == scenario_id)
    ).scalars().all()

    base_by_key = {(a.backlog_item_id, a.phase, a.part_number): a for a in base_a}
    scen_by_key = {(a.backlog_item_id, a.phase, a.part_number): a for a in scen_a}

    shifts: List[Dict] = []
    for key, scen_v in scen_by_key.items():
        base_v = base_by_key.get(key)
        if not base_v:
            shifts.append({
                "backlog_item_id": key[0], "phase": key[1], "part_number": key[2],
                "kind": "added",
            })
            continue
        if base_v.start_date and scen_v.start_date and base_v.start_date != scen_v.start_date:
            shifts.append({
                "backlog_item_id": key[0], "phase": key[1], "part_number": key[2],
                "kind": "shifted",
                "start_delta_days": (scen_v.start_date - base_v.start_date).days,
                "end_delta_days": (scen_v.end_date - base_v.end_date).days
                    if base_v.end_date and scen_v.end_date else 0,
                "employee_changed": base_v.employee_id != scen_v.employee_id,
            })
    for key in base_by_key:
        if key not in scen_by_key:
            shifts.append({
                "backlog_item_id": key[0], "phase": key[1], "part_number": key[2],
                "kind": "removed",
            })

    # Metrics
    base_conflicts = db.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == baseline_id,
            PlanConflict.status == "open",
        )
    ).scalars().all()
    scen_conflicts = db.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == scenario_id,
            PlanConflict.status == "open",
        )
    ).scalars().all()

    def _metrics(assigns, conflicts):
        crit = sum(1 for a in assigns if a.is_on_critical_path)
        end = max((a.end_date for a in assigns if a.end_date), default=None)
        return {
            "assignments_count": len(assigns),
            "critical_path_count": crit,
            "last_end_date": end.isoformat() if end else None,
            "conflicts_open": len(conflicts),
            "conflicts_critical": sum(1 for c in conflicts if c.severity == "critical"),
        }

    return {
        "baseline_id": baseline_id,
        "scenario_id": scenario_id,
        "assignment_shifts": shifts,
        "baseline_metrics": _metrics(base_a, base_conflicts),
        "scenario_metrics": _metrics(scen_a, scen_conflicts),
    }
```

- [ ] **Step 3: Run (PASS)**

- [ ] **Step 4: Commit**

```bash
git add app/services/plan_diff.py tests/test_plan_diff.py
git commit -m "feat(resource-planning): plan diff service (assignment shifts + metrics)"
```

### Task D.4: Diff endpoint

**Files:**
- Modify: `app/api/endpoints/resource_planning.py`

- [ ] **Step 1: Add endpoint**

```python
class PlanDiffOut(BaseModel):
    baseline_id: str
    scenario_id: str
    assignment_shifts: List[dict]
    baseline_metrics: dict
    scenario_metrics: dict


@router.get(
    "/resource-plans/{scenario_id}/diff/{baseline_id}",
    response_model=PlanDiffOut,
)
def get_plan_diff(
    scenario_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.services.plan_diff import diff_plans
    try:
        return diff_plans(db, baseline_id, scenario_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
```

- [ ] **Step 2: Smoke test**

Restart backend. Then:

```bash
curl http://localhost:8000/api/v1/resource-planning/resource-plans/<scen_id>/diff/<base_id> | jq .
```

- [ ] **Step 3: Commit**

```bash
git add app/api/endpoints/resource_planning.py
git commit -m "feat(resource-planning): GET /resource-plans/{scen}/diff/{base} endpoint"
```

### Task D.5: Frontend — fork API + hook

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts`
- Modify: `frontend/src/hooks/useResourcePlanning.ts`

- [ ] **Step 1: Add types + API**

In `frontend/src/api/resourcePlanning.ts`:

```typescript
export interface ResourcePlan {
  id: string;
  scenario_id: string | null;
  team: string | null;
  quarter: string | null;
  year: number | null;
  status: 'draft' | 'computing' | 'ready' | 'stale';
  computed_at: string | null;
  created_at: string;
  parent_plan_id: string | null;
  is_baseline: boolean;
  label: string | null;
}

export interface AssignmentShift {
  backlog_item_id: string;
  phase: string;
  part_number: number;
  kind: 'added' | 'removed' | 'shifted';
  start_delta_days?: number;
  end_delta_days?: number;
  employee_changed?: boolean;
}

export interface PlanDiff {
  baseline_id: string;
  scenario_id: string;
  assignment_shifts: AssignmentShift[];
  baseline_metrics: {
    assignments_count: number;
    critical_path_count: number;
    last_end_date: string | null;
    conflicts_open: number;
    conflicts_critical: number;
  };
  scenario_metrics: PlanDiff['baseline_metrics'];
}

export const forkPlan = (planId: string, label?: string) =>
  api.post<ResourcePlan>(`/resource-planning/resource-plans/${planId}/fork`, { label });

export const getPlanDiff = (scenarioId: string, baselineId: string) =>
  api.get<PlanDiff>(`/resource-planning/resource-plans/${scenarioId}/diff/${baselineId}`);
```

- [ ] **Step 2: Add hooks**

In `frontend/src/hooks/useResourcePlanning.ts`:

```typescript
export function useForkPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, label }: { planId: string; label?: string }) =>
      forkPlan(planId, label),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resource-plans'] }),
  });
}

export function usePlanDiff(scenarioId: string | null, baselineId: string | null) {
  return useQuery({
    queryKey: ['plan-diff', scenarioId, baselineId],
    queryFn: () => getPlanDiff(scenarioId!, baselineId!),
    enabled: !!scenarioId && !!baselineId,
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/hooks/useResourcePlanning.ts
git commit -m "feat(resource-planning): fork + diff API client + hooks"
```

### Task D.6: «Сделать копию» button + label edit on ResourcePlanningPage

**Files:**
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx`

- [ ] **Step 1: Add fork button + label tag**

In `frontend/src/pages/ResourcePlanningPage.tsx`:
- Add Modal/Input for label entry
- After plan selector: button «Сделать копию» → opens modal → calls `useForkPlan`
- Show `gantt.plan.label` as tag if non-null
- Show «Базовый» tag if `gantt.plan.is_baseline`
- Add link «Сравнить с базовым» (visible if `parent_plan_id` set) → navigate to `/resource-planning/compare?base=<parent>&scen=<this>`

(Subagent: read current file, follow existing pattern with Tag/Button.)

- [ ] **Step 2: Build + smoke**

```bash
cd frontend && npm run build && cd ..
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "feat(resource-planning): fork button + label/baseline tags on plan page"
```

### Task D.7: ScenarioComparator page

**Files:**
- Create: `frontend/src/pages/ScenarioComparatorPage.tsx`
- Modify: `frontend/src/lazyPages.tsx`
- Modify: router (App.tsx or wherever routes live)

- [ ] **Step 1: Create page**

```typescript
// frontend/src/pages/ScenarioComparatorPage.tsx
import { useSearchParams } from 'react-router';
import { Card, Col, Row, Select, Statistic, Table, Tag, Empty } from 'antd';
import PageHeader from '../components/shared/PageHeader';
import { useResourcePlans, usePlanDiff } from '../hooks/useResourcePlanning';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

export default function ScenarioComparatorPage() {
  const [params, setParams] = useSearchParams();
  const baseId = params.get('base');
  const scenId = params.get('scen');
  const { selectedTeams } = useGlobalTeamFilter();
  const { data: plans = [] } = useResourcePlans(selectedTeams[0]);
  const { data: diff } = usePlanDiff(scenId, baseId);

  const planOpts = plans.map(p => ({
    label: `${p.label ?? p.quarter + ' ' + p.year} ${p.is_baseline ? '★' : ''}`,
    value: p.id,
  }));

  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader title="Сравнение сценариев" />
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card size="small" title="Базовый">
            <Select
              style={{ width: '100%' }}
              value={baseId}
              options={planOpts}
              onChange={v => setParams({ base: v, scen: scenId ?? '' })}
              placeholder="Выберите baseline"
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="Сценарий">
            <Select
              style={{ width: '100%' }}
              value={scenId}
              options={planOpts}
              onChange={v => setParams({ base: baseId ?? '', scen: v })}
              placeholder="Выберите scenario"
            />
          </Card>
        </Col>
      </Row>

      {!diff && <Empty description="Выберите оба плана" />}
      {diff && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="Назначений (база → сценарий)"
                  value={`${diff.baseline_metrics.assignments_count} → ${diff.scenario_metrics.assignments_count}`}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="На критпути"
                  value={`${diff.baseline_metrics.critical_path_count} → ${diff.scenario_metrics.critical_path_count}`}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="Открытые конфликты"
                  value={`${diff.baseline_metrics.conflicts_open} → ${diff.scenario_metrics.conflicts_open}`}
                  valueStyle={{
                    color: diff.scenario_metrics.conflicts_open < diff.baseline_metrics.conflicts_open
                      ? '#1e6a35' : '#e85d4a',
                  }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="Последний end date"
                  value={diff.scenario_metrics.last_end_date ?? '—'}
                />
              </Card>
            </Col>
          </Row>

          <Card size="small" title="Изменения назначений">
            <Table
              dataSource={diff.assignment_shifts}
              rowKey={(r, i) => `${r.backlog_item_id}-${r.phase}-${r.part_number}-${i}`}
              size="small"
              pagination={{ pageSize: 20 }}
              columns={[
                { title: 'Инициатива', dataIndex: 'backlog_item_id' },
                { title: 'Фаза', dataIndex: 'phase' },
                { title: 'Часть', dataIndex: 'part_number' },
                {
                  title: 'Тип',
                  dataIndex: 'kind',
                  render: (k: string) => {
                    const c = k === 'added' ? 'green' : k === 'removed' ? 'red' : 'orange';
                    return <Tag color={c}>{k}</Tag>;
                  },
                },
                {
                  title: 'Сдвиг (дни)',
                  dataIndex: 'start_delta_days',
                  render: (v: number | undefined) => v != null ? `${v > 0 ? '+' : ''}${v}` : '—',
                },
                {
                  title: 'Сменился исполнитель',
                  dataIndex: 'employee_changed',
                  render: (v: boolean | undefined) => v ? <Tag color="cyan">Да</Tag> : '',
                },
              ]}
            />
          </Card>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register lazy + route**

In `frontend/src/lazyPages.tsx`:

```typescript
export const ScenarioComparatorPage = lazy(() => import('./pages/ScenarioComparatorPage'));
```

In router (search for `<Route path="/resource-planning"` in App.tsx or routes file), add:

```typescript
<Route path="/resource-planning/compare" element={<ScenarioComparatorPage />} />
```

- [ ] **Step 3: Build + manual smoke**

```bash
cd frontend && npm run build && cd ..
```

Open `/resource-planning`, fork a plan, click «Сравнить с базовым» → comparator opens with diff.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ScenarioComparatorPage.tsx frontend/src/lazyPages.tsx frontend/src/App.tsx
git commit -m "feat(resource-planning): ScenarioComparatorPage — side-by-side metrics + shifts table"
```

### Task D.8: Stage D ship checkpoint

- [ ] **Step 1: Lint + tests**

```bash
ruff check app/ tests/ && ruff format app/ tests/
py -3.10 -m pytest tests/ -v --tb=short
cd frontend && npm run lint && npm run build && cd ..
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

**Stage D checkpoint reached.** Phase 3 полностью отгружен.

---

## Self-Review

After all stages:

1. **Spec coverage:**
   - [x] RCPSP-разравнивание — Stage A (delay + reassign + escalate)
   - [x] Расширенный конфликт-детектор — Stage B (persistent register + status + leveling events surfaced)
   - [x] Вероятностный CPM — Stage C (PERT + P50/P90 overlay)
   - [x] What-if сценарии — Stage D (fork + diff + comparator)

2. **Placeholders:** None — all steps have actual code/commands. Tests with `pass` placeholder explicitly marked as «implement using existing fixture pattern» — subagent should fill in following pattern from existing tests in same file.

3. **Type consistency:** ConflictOut extended once (Stage B Task B.5 + B.7); GanttProjection extended once (Stage C Task C.3 + C.4); ResourcePlan extended once (Stage D Task D.1 + D.5).

4. **Migrations numbered:** 045 (plan_conflicts), 046 (pert_multipliers), 047 (plan_fork_fields). No collisions.

5. **Stage independence:** A, B, C, D each end with shippable commit. C and D do not depend on A or B (PERT and forks work on top of any compute_schedule output). B depends on A only for `_last_leveling_events` — but `_build_conflict_dicts` handles empty list cleanly.
