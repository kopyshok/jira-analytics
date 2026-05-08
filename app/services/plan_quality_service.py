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
    DEFAULT_HOURS_PER_DAY = 8.0

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

        # Капасити = hours_per_day сотрудника (грубое приближение, без отсутствий)
        emp_caps: dict[str, float] = {}
        for emp_id in {a.employee_id for a in assignments if a.employee_id}:
            # Employee не хранит hours_per_day; используем стандарт 8ч/день
            emp_caps[emp_id] = self.DEFAULT_HOURS_PER_DAY

        overload_days = 0
        total_days = 0
        utilization_sum = 0.0
        for (_d, emp_id), hours in load.items():
            cap = emp_caps.get(emp_id, self.DEFAULT_HOURS_PER_DAY)
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
