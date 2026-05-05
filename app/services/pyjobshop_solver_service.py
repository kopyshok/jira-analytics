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
from app.models.plan_item_dependency import PlanItemDependency
from app.models.production_calendar_day import ProductionCalendarDay
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.scheduled_block import ScheduledBlock


# Маппинг phase → роли которые могут эту phase исполнять.
# Employee.role хранит строковый код из реестра ролей; сравнение — точное
# (case-insensitive). Если у компании роль называется иначе — добавьте код
# роли в нужный набор. Раньше использовалась подстрока (`in`), что приводило
# к ложным совпадениям типа «ba-team-lead» → analyst.
PHASE_ROLE_MATCH: dict[str, set[str]] = {
    "analyst": {"analyst", "ba", "аналитик"},
    "dev": {"developer", "dev", "разработчик"},
    "qa": {"qa", "tester", "тестировщик"},
    "opo": {"developer", "dev", "analyst", "ba"},  # ОПЭ делят dev и analyst
}

# Порядок ролей для выбора главного assignee инициативы. Первая фаза из этого
# списка с назначенным employee_id становится представителем задачи на Gantt.
# Раньше брали phase с max часами — на Gantt всплывал QA вместо аналитика.
PHASE_ASSIGNEE_PRIORITY: list[str] = ["analyst", "dev", "qa", "opo"]

# Часов в рабочем дне (ёмкость 1 renewable = 8 единиц, 1 unit = 1 час).
HOURS_PER_DAY = 8

# Маппинг phase → (поле involvement, поле duration_days) в BacklogItem.
# Используется солвером для вычисления длительности и нагрузки по фазе.
PHASE_TO_FIELD: dict[str, tuple[str, str]] = {
    "analyst": ("involvement_analyst", "duration_analyst_days"),
    "dev":     ("involvement_dev",     "duration_dev_days"),
    "qa":      ("involvement_qa",      "duration_qa_days"),
    "opo":     ("involvement_launch",  "duration_launch_days"),
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

    def __init__(self, db: Session, time_limit_sec: int = 15):
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

        # Загружаем зависимости (FS) для плана
        fs_deps = list(self.db.scalars(
            select(PlanItemDependency).where(
                PlanItemDependency.plan_id == plan_id,
                PlanItemDependency.dep_type == "FS",
            )
        ))
        # TODO: SS/FF/SF зависимости не поддерживаются в v1, пропускаются.

        # Загружаем backlog_items для priority weight
        item_ids = list({a.backlog_item_id for a in assignments})
        backlog_items: dict[str, BacklogItem] = {
            item.id: item
            for item in self.db.scalars(
                select(BacklogItem).where(BacklogItem.id.in_(item_ids))
            )
        }

        # Job per backlog_item, Task per assignment row.
        # task_id → Task object (для построения FS-ограничений).
        jobs: dict[str, object] = {}
        # backlog_item_id → список Task (для FS: last task of from_item, first task of to_item)
        item_tasks: dict[str, list[object]] = {}
        # Параллельно solution_tasks: какие assignments реально добавлены в модель.
        # Skipped assignments (no eligible employees) — не в этом списке, попадают в infeasible.
        added_assignments: list[ResourcePlanAssignment] = []
        skipped_item_ids: set[str] = set()
        # Для warm start (F7): индекс assignment.id → {resource_idx → global_mode_idx}.
        # Глобальный mode_idx — позиция mode в model.data().modes (counter).
        global_mode_idx = 0
        assignment_modes: dict[str, dict[int, int]] = {}

        for a in assignments:
            # B. Pinned assignment: если is_pinned и employee_id задан — единственный mode.
            pinned_resource_idx: Optional[int] = None
            if a.is_pinned and a.employee_id and a.employee_id in emp_id_to_resource_idx:
                pinned_resource_idx = emp_id_to_resource_idx[a.employee_id]

            # Mode per eligible employee (skill match)
            if pinned_resource_idx is not None:
                eligible_resource_indices = [pinned_resource_idx]
            else:
                eligible_resource_indices = [
                    emp_id_to_resource_idx[emp.id]
                    for emp in employees
                    if self._employee_can_do_phase(emp, a.phase)
                    and emp.id in emp_id_to_resource_idx
                ]

            if not eligible_resource_indices:
                # Нет ни одного сотрудника подходящей роли в команде — фаза не может
                # быть запланирована солвером. Помечаем backlog_item как infeasible
                # и не добавляем task в модель (иначе pyjobshop падает с
                # "Processing modes missing for task N").
                skipped_item_ids.add(a.backlog_item_id)
                continue

            if a.backlog_item_id not in jobs:
                # C. Priority weight: priority 1 → weight 10, priority 10 → weight 1.
                # priority=None → weight=1 (хвост): без явного приоритета задача
                # не должна получать «средний» вес и пролезать вперёд приоритетных.
                bi = backlog_items.get(a.backlog_item_id)
                priority = bi.priority if bi is not None else None
                weight = max(1, 11 - priority) if priority is not None else 1
                # due_date = конец горизонта (soft deadline для tardiness objective)
                jobs[a.backlog_item_id] = model.add_job(
                    weight=weight, due_date=horizon_slots
                )

            # Вычисляем длительность и нагрузку с учётом Jira-полей involvement/duration.
            # Если поля не заданы — поведение совпадает со старым (involvement=1.0,
            # duration = hours_allocated/8), то есть сотрудник занят весь день.
            inv_field, dur_field = PHASE_TO_FIELD.get(a.phase, (None, None))
            bi = backlog_items.get(a.backlog_item_id)
            involvement = (
                float(getattr(bi, inv_field, None) or 1.0)
                if (bi and inv_field) else 1.0
            )
            duration_days_raw = (
                float(getattr(bi, dur_field, None) or 0)
                if (bi and dur_field) else 0.0
            )
            if duration_days_raw <= 0:
                # Fallback: часы / (involvement × 8)
                fallback_hours = float(a.hours_allocated or 1)
                duration_days_raw = fallback_hours / max(0.1, involvement * HOURS_PER_DAY)
            duration_slots = max(1, int(round(duration_days_raw * HOURS_PER_DAY)))
            demand_per_slot = max(1, int(round(involvement * HOURS_PER_DAY)))

            task = model.add_task(
                job=jobs[a.backlog_item_id],
                latest_end=horizon_slots,
                name=a.id,
            )
            item_tasks.setdefault(a.backlog_item_id, []).append(task)
            added_assignments.append(a)

            mode_map: dict[int, int] = {}
            for r_idx in eligible_resource_indices:
                resource = model.resources[r_idx]
                # demand = кол-во ч/день занятости сотрудника (involvement × 8);
                # duration = длительность задачи в часах (calendar days × 8).
                # При involvement=1.0 поведение совпадает со старым (8 ч/день).
                model.add_mode(
                    task=task,
                    resources=[resource],
                    duration=duration_slots,
                    demands=[demand_per_slot],
                )
                mode_map[r_idx] = global_mode_idx
                global_mode_idx += 1
            assignment_modes[a.id] = mode_map

        # A. FS Dependencies: last task of from_item must end before first task of to_item.
        # lag_days временно не учитывается — был подозрением на SIGSEGV под
        # Windows (откат вместе с F5/F7). Вернём после стабилизации.
        for dep in fs_deps:
            from_tasks = item_tasks.get(dep.from_item_id, [])
            to_tasks = item_tasks.get(dep.to_item_id, [])
            if not from_tasks or not to_tasks:
                continue
            for from_task in from_tasks:
                for to_task in to_tasks:
                    model.add_end_before_start(from_task, to_task)

        # C. Objective: weighted_tardiness. Двойная цель (tardiness+flow_time)
        # вызывала SIGSEGV в OR-Tools под Windows — откат на single objective.
        # Чтобы задачи не разъезжались по горизонту, weight через add_job уже
        # применён (priority 1→10, None→1).
        model.set_objective(weight_total_tardiness=1)

        # F7. Warm start временно отключён: вызывает SIGSEGV в OR-Tools
        # под Windows на некоторых hint-комбинациях. Вернёмся когда найдём
        # минимальный воспроизводящий пример или обновим pyjobshop.
        # См. _build_warm_start ниже — оставлен как future reference.
        result = model.solve(
            time_limit=self.time_limit_sec,
            display=False,
        )

        # Статус решения
        status_str = result.status.name if hasattr(result, "status") else "UNKNOWN"

        if status_str == "INFEASIBLE":
            return SolverResult(
                assignments=[],
                infeasible_items=list(set(jobs.keys()) | skipped_item_ids),
                solver_status="INFEASIBLE",
                solve_time_ms=int((time.monotonic() - t0) * 1000),
            )

        # Извлечь результат. PyJobShop solution: result.best.tasks[i] — ScheduledTask
        # с полями start, end, mode, resources (индекс в model.resources).
        # Порядок tasks совпадает с порядком добавления через add_task() — то есть
        # с порядком added_assignments (skipped исключены).
        solution_tasks = list(result.best.tasks) if result.best is not None else []

        # Собираем per-assignment данные, порядок task'ов = порядок added_assignments
        per_assignment: dict[str, PhaseAllocation] = {}
        for idx, sol_task in enumerate(solution_tasks):
            a = added_assignments[idx]
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

        # Полностью пропущенные backlog_items (ни одной фазы не размещено)
        infeasible.extend(sorted(skipped_item_ids))

        for item_id, item_assignments in item_groups.items():
            if item_id in skipped_item_ids and item_id not in jobs:
                # Уже добавлено в infeasible выше, нет ни одной задачи в модели
                continue
            phase_breakdown = [
                per_assignment[a.id] for a in item_assignments if a.id in per_assignment
            ]
            if not phase_breakdown:
                if item_id not in infeasible:
                    infeasible.append(item_id)
                continue

            # Главный assignee — первая фаза из PHASE_ASSIGNEE_PRIORITY
            # с назначенным employee_id. Раньше брали phase с max часами,
            # из-за чего на Gantt появлялся QA вместо аналитика.
            phase_to_alloc = {p["phase"]: p for p in phase_breakdown}
            main_employee_id: Optional[str] = None
            for ph in PHASE_ASSIGNEE_PRIORITY:
                alloc = phase_to_alloc.get(ph)
                if alloc and alloc["employee_id"]:
                    main_employee_id = alloc["employee_id"]
                    break
            if main_employee_id is None:
                # Fallback: любой назначенный
                for p in phase_breakdown:
                    if p["employee_id"]:
                        main_employee_id = p["employee_id"]
                        break

            out_assignments.append(SolverAssignment(
                backlog_item_id=item_id,
                assignee_employee_id=main_employee_id,
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

    def _build_warm_start(
        self,
        model,
        added_assignments: list[ResourcePlanAssignment],
        assignment_modes: dict[str, dict[int, int]],
        anchor: date,
        horizon_slots: int,
    ):
        """Строит initial_solution для PyJobShop из текущих start_date/employee.

        Возвращает Solution или None если нельзя построить полный hint.
        """
        from pyjobshop.Solution import ScheduledTask, Solution

        # Если хоть одна задача стоит до anchor (план был построен на старый
        # квартал-старт, а anchor сдвинут на today), warm start даст плохой
        # hint — все clamped в start_slot=0, конфликты ресурсов. Лучше пусть
        # solver строит с нуля.
        for a in added_assignments:
            if a.start_date is not None and a.start_date < anchor:
                return None

        scheduled: list[ScheduledTask] = []
        for a in added_assignments:
            mode_map = assignment_modes.get(a.id, {})
            if not mode_map:
                return None
            # Выбираем resource_idx: текущий employee_id если он среди eligible,
            # иначе первый eligible как fallback. resource.name = employee.id
            # (см. add_renewable выше).
            resource_idx: Optional[int] = None
            if a.employee_id is not None:
                for r_idx in mode_map:
                    if model.resources[r_idx].name == a.employee_id:
                        resource_idx = r_idx
                        break
            if resource_idx is None:
                # Fallback на первый eligible
                resource_idx = next(iter(mode_map))
            mode_idx = mode_map[resource_idx]

            # Конвертируем даты в slots
            if a.start_date is None or a.end_date is None:
                # Нет текущих дат — ставим в начало горизонта на duration
                start_slot = 0
                end_slot = max(1, int(a.hours_allocated or 1))
            else:
                start_offset = (a.start_date - anchor).days
                if start_offset < 0:
                    start_offset = 0
                start_slot = start_offset * HOURS_PER_DAY
                duration = max(1, int(a.hours_allocated or 1))
                end_slot = start_slot + duration

            if start_slot >= horizon_slots or end_slot > horizon_slots:
                return None

            scheduled.append(
                ScheduledTask(
                    mode=mode_idx,
                    resources=[resource_idx],
                    start=start_slot,
                    end=end_slot,
                )
            )

        if not scheduled:
            return None
        try:
            return Solution(model.data(), scheduled)
        except Exception:
            # Если что-то пошло не так — solver просто решит без hint.
            return None

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
        """Проверяет, подходит ли роль сотрудника для данной phase.

        Сравнение точное (case-insensitive). Если у сотрудника
        ``role='developer-lead'``, он не подойдёт под phase=dev — нужен ровно
        один из кодов в ``PHASE_ROLE_MATCH[phase]``. Это лечит ситуацию когда
        тимлид с ролью «ba-team-lead» получал аналитические задачи.
        """
        if not emp.role:
            return False
        return emp.role.lower() in PHASE_ROLE_MATCH.get(phase, set())

    def _horizon_days(self, plan: ResourcePlan) -> int:
        """Горизонт квартала в рабочих днях (с запасом)."""
        return 95

    def _anchor_date(self, plan: ResourcePlan) -> date:
        """Стартовая дата планирования: max(начало квартала, сегодня).

        Раньше брался первый день квартала — solver мог приземлять задачи в
        прошлое (например, при оптимизации в середине квартала). Теперь
        задачи не уезжают раньше «сегодня».
        """
        today = date.today()
        if not plan.year or not plan.quarter:
            return today
        q = int(plan.quarter.replace("Q", ""))
        start_month = (q - 1) * 3 + 1
        quarter_start = date(plan.year, start_month, 1)
        return max(quarter_start, today)

    def _slot_to_date(self, anchor: date, slot: int) -> date:
        """Конвертирует слот (1 unit = 1 час) в дату."""
        days_offset = slot // HOURS_PER_DAY
        return anchor + timedelta(days=days_offset)
