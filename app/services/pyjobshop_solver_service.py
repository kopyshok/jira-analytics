"""PyJobShopSolverService — обёртка над PyJobShop для оптимизации
ресурсного плана.

Модель:
- Job = BacklogItem (одна инициатива).
- Task внутри Job = одна phase (analyst/dev/qa/opo).
- Mode = вариант исполнения phase конкретным сотрудником подходящей роли.
- Resource = Employee (renewable, дневная ёмкость = 8 единиц).

В этом скелете покрыты только:
- skill match (роль сотрудника совпадает с phase),
- single-mode capacity (один сотрудник — одна задача одновременно).

Доточка остальных hard rules в следующих task'ах.
"""

import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional, TypedDict

from sqlalchemy import or_, and_, select
from sqlalchemy.orm import Session

from app.models.absence import Absence
from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.production_calendar_day import ProductionCalendarDay
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.scheduled_block import ScheduledBlock


# Маппинг phase → роли которые могут эту phase исполнять.
# Employee.role хранит строковый код из реестра ролей; сравнение — подстрока.
PHASE_ROLE_MATCH: dict[str, set[str]] = {
    "analyst": {"analyst", "ba", "аналитик"},
    "dev": {"developer", "dev", "разработчик"},
    "qa": {"qa", "tester", "тестировщик"},
    "opo": {"developer", "dev", "analyst", "ba"},  # ОПЭ делят dev и analyst
}

# Часов в рабочем дне (ёмкость 1 renewable = 8 единиц, 1 unit = 1 час).
HOURS_PER_DAY = 8


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

        # Сотрудники команды плана (только активные)
        employees = list(self.db.scalars(
            select(Employee).where(
                Employee.team == plan.team,
                Employee.is_active == True,  # noqa: E712
            )
        ))

        model = Model()

        anchor = self._anchor_date(plan)
        horizon_days = self._horizon_days(plan)

        # Загружаем производственный календарь один раз для всего горизонта
        horizon_end = anchor + timedelta(days=horizon_days - 1)
        cal_overrides: dict[date, bool] = {
            row.date: row.is_workday
            for row in self.db.scalars(
                select(ProductionCalendarDay).where(
                    ProductionCalendarDay.date >= anchor,
                    ProductionCalendarDay.date <= horizon_end,
                )
            )
        }

        # Один renewable resource на сотрудника. Ёмкость = 8 единиц/день
        # (1 unit = 1 час, 8 ч — стандартный рабочий день).
        # resource_idx_to_emp_id используется для восстановления результата.
        resource_idx_to_emp_id: dict[int, str] = {}
        emp_id_to_resource_idx: dict[str, int] = {}
        for idx, emp in enumerate(employees):
            breaks = self._employee_breaks(emp, anchor, horizon_days, cal_overrides)
            model.add_renewable(capacity=HOURS_PER_DAY, breaks=breaks, name=emp.id)
            resource_idx_to_emp_id[idx] = emp.id
            emp_id_to_resource_idx[emp.id] = idx

        # Горизонт планирования в часах
        horizon_slots = horizon_days * HOURS_PER_DAY

        # Job per backlog_item, Task per assignment row
        jobs: dict[str, object] = {}

        for a in assignments:
            if a.backlog_item_id not in jobs:
                jobs[a.backlog_item_id] = model.add_job()

            duration_slots = max(1, int(a.hours_allocated or 1))
            task = model.add_task(
                job=jobs[a.backlog_item_id],
                latest_end=horizon_slots,
                name=a.id,
            )

            # Mode per eligible employee (skill match)
            eligible_employees = [
                emp for emp in employees
                if self._employee_can_do_phase(emp, a.phase)
            ]
            for emp in eligible_employees:
                r_idx = emp_id_to_resource_idx[emp.id]
                resource = model.resources[r_idx]
                # demand = HOURS_PER_DAY означает "сотрудник занят весь рабочий
                # день"; duration = кол-во часов (task растягивается на несколько
                # дней, если duration > capacity).
                model.add_mode(
                    task=task,
                    resources=[resource],
                    duration=duration_slots,
                    demands=[HOURS_PER_DAY],
                )

        result = model.solve(time_limit=self.time_limit_sec, display=False)

        # Статус решения
        status_str = result.status.name if hasattr(result, "status") else "UNKNOWN"

        if status_str == "INFEASIBLE":
            return SolverResult(
                assignments=[],
                infeasible_items=list(jobs.keys()),
                solver_status="INFEASIBLE",
                solve_time_ms=int((time.monotonic() - t0) * 1000),
            )

        # Извлечь результат. PyJobShop solution: result.best.tasks[i] — ScheduledTask
        # с полями start, end, mode, resources (индекс в model.resources).
        # Порядок tasks совпадает с порядком добавления через add_task().
        solution_tasks = list(result.best.tasks) if result.best is not None else []

        # Собираем per-assignment данные, порядок task'ов = порядок assignments
        per_assignment: dict[str, PhaseAllocation] = {}
        for idx, sol_task in enumerate(solution_tasks):
            a = assignments[idx]
            start_d = self._slot_to_date(anchor, sol_task.start)
            end_d = self._slot_to_date(anchor, sol_task.end)

            # Восстанавливаем сотрудника: resources — список индексов в model.resources
            chosen_emp_id: Optional[str] = None
            if sol_task.resources:
                r_idx = sol_task.resources[0]
                chosen_emp_id = resource_idx_to_emp_id.get(r_idx)

            per_assignment[a.id] = PhaseAllocation(
                phase=a.phase,
                hours=a.hours_allocated or 0.0,
                employee_id=chosen_emp_id,
                start_date=start_d,
                end_date=end_d,
            )

        # Группируем по backlog_item
        item_groups: dict[str, list[ResourcePlanAssignment]] = defaultdict(list)
        for a in assignments:
            item_groups[a.backlog_item_id].append(a)

        out_assignments: list[SolverAssignment] = []
        infeasible: list[str] = []

        for item_id, item_assignments in item_groups.items():
            phase_breakdown = [
                per_assignment[a.id] for a in item_assignments if a.id in per_assignment
            ]
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

    def _employee_breaks(
        self,
        emp: Employee,
        anchor: date,
        horizon_days: int,
        cal_overrides: dict[date, bool],
    ) -> list[tuple[int, int]]:
        """Возвращает список break-интервалов (start_slot, end_slot) для сотрудника.

        Break = любой день горизонта, когда сотрудник недоступен:
        - выходной/праздник по производственному календарю;
        - период отсутствия (Absence).
        """
        # Дни отсутствия сотрудника
        absent_days: set[date] = set()
        absences = list(self.db.scalars(
            select(Absence).where(Absence.employee_id == emp.id)
        ))
        for absence in absences:
            d = absence.start_date
            while d <= absence.end_date:
                absent_days.add(d)
                d += timedelta(days=1)

        # Дни заблокированных периодов (employee-scope и team-scope).
        # TODO: role-scoped blocks не применяются — Employee.role это строковый код,
        # не FK; join с Role требует дополнительной логики (отложено).
        horizon_start = anchor
        horizon_end = anchor + timedelta(days=horizon_days - 1)
        blocks = list(self.db.scalars(
            select(ScheduledBlock).where(
                or_(
                    ScheduledBlock.employee_id == emp.id,
                    and_(
                        ScheduledBlock.team == emp.team,
                        ScheduledBlock.employee_id.is_(None),
                        ScheduledBlock.role_id.is_(None),
                    ),
                ),
                ScheduledBlock.end_date >= horizon_start,
                ScheduledBlock.start_date <= horizon_end,
            )
        ))
        for block in blocks:
            d = block.start_date
            while d <= block.end_date:
                absent_days.add(d)
                d += timedelta(days=1)

        breaks: list[tuple[int, int]] = []
        for day_offset in range(horizon_days):
            d = anchor + timedelta(days=day_offset)
            # Производственный календарь: приоритет у переопределений,
            # дефолт — weekday < 5 рабочий, иначе выходной.
            if d in cal_overrides:
                is_workday = cal_overrides[d]
            else:
                is_workday = d.weekday() < 5

            unavailable = not is_workday or d in absent_days
            if unavailable:
                slot_start = day_offset * HOURS_PER_DAY
                slot_end = slot_start + HOURS_PER_DAY
                breaks.append((slot_start, slot_end))

        return breaks

    def _employee_can_do_phase(self, emp: Employee, phase: str) -> bool:
        """Проверяет, подходит ли роль сотрудника для данной phase."""
        if not emp.role:
            return False
        role = emp.role.lower()
        return any(token in role for token in PHASE_ROLE_MATCH.get(phase, set()))

    def _horizon_days(self, plan: ResourcePlan) -> int:
        """Горизонт квартала в рабочих днях (с запасом)."""
        return 95

    def _anchor_date(self, plan: ResourcePlan) -> date:
        """Первый день квартала плана."""
        if not plan.year or not plan.quarter:
            return date.today()
        q = int(plan.quarter.replace("Q", ""))
        start_month = (q - 1) * 3 + 1
        return date(plan.year, start_month, 1)

    def _slot_to_date(self, anchor: date, slot: int) -> date:
        """Конвертирует слот (1 unit = 1 час) в дату."""
        days_offset = slot // HOURS_PER_DAY
        return anchor + timedelta(days=days_offset)
