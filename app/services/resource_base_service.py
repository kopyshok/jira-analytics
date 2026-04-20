"""База ресурса команды — посуточная матрица доступных часов.

Для каждого сотрудника команды вычисляет количество «проектных» часов на
каждый рабочий день квартала: вычитает дни отсутствия и процент нормы,
занятый обязательными работами (только те виды работ, у которых
``subtracts_from_pool=True``).

Используется в Этапе B планирования (Task 11): фронтенд опирается на
посуточные итоги для пересчёта ролевых ёмкостей при выборе инициатив.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Absence,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    ScenarioRule,
)

DEFAULT_HOURS_PER_DAY = 8.0


@dataclass
class EmployeeDayHours:
    """Количество доступных проектных часов сотрудника за один день."""

    date: date
    hours: float


@dataclass
class EmployeeBase:
    """Посуточная база ресурса одного сотрудника."""

    employee_id: str
    display_name: str
    role: Optional[str]
    days: list[EmployeeDayHours]
    total_hours: float


@dataclass
class ResourceBase:
    """Сводная база ресурса команды на квартал."""

    year: int
    quarter: int
    team: str
    employees: list[EmployeeBase]
    role_totals: dict[str, float]           # role_code -> суммарные доступные часы
    external_qa_hours: Optional[float]       # переопределяет role_totals['qa'] если задано


class ResourceBaseService:
    """Вычисляет посуточную матрицу доступных часов для команды в рамках сценария.

    Логика:
    - Берёт активных сотрудников команды (через ``EmployeeTeam``).
    - Для каждого рабочего дня квартала вычитает дни отсутствия.
    - Уменьшает оставшиеся часы на долю обязательных работ (``ScenarioRule``)
      только если ``MandatoryWorkType.subtracts_from_pool=True``.
    - Если у сценария задан ``external_qa_hours``, он заменяет сумму по роли «qa».
    """

    QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}

    def __init__(self, db: Session) -> None:
        self.db = db

    def compute(self, scenario: PlanningScenario) -> ResourceBase:
        """Вычислить базу ресурса для переданного сценария."""
        year = scenario.year
        q = int(str(scenario.quarter).replace("Q", ""))
        team = scenario.team
        months = self.QUARTER_MONTHS[q]
        period_start = date(year, months[0], 1)
        last_m = months[-1]
        next_year = year + 1 if last_m == 12 else year
        next_month = 1 if last_m == 12 else last_m + 1
        period_end = date(next_year, next_month, 1)  # exclusive upper bound

        # --- сотрудники команды ---
        emp_ids = [
            r[0]
            for r in self.db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team == team)
            .all()
        ]
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(emp_ids), Employee.is_active == True)  # noqa: E712
            .all()
        )

        # --- карта аномалий производственного календаря ---
        # Только аномалии (праздники, переносы, сокращённые дни) хранятся в БД.
        # Для остальных дней: Пн-Пт = 8 ч, Сб-Вс = 0.
        cal_overrides: dict[date, float] = {
            row.date: float(row.hours)
            for row in self.db.query(ProductionCalendarDay).filter(
                ProductionCalendarDay.date >= period_start,
                ProductionCalendarDay.date < period_end,
            ).all()
        }
        cal_is_workday: dict[date, bool] = {
            row.date: bool(row.is_workday)
            for row in self.db.query(ProductionCalendarDay).filter(
                ProductionCalendarDay.date >= period_start,
                ProductionCalendarDay.date < period_end,
            ).all()
        }

        def day_hours(d: date) -> float:
            """Норма часов для дня с учётом производственного календаря."""
            if d in cal_overrides:
                return cal_overrides[d]
            # Fallback: Пн-Пт = 8 ч, Сб-Вс = 0 ч
            return DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0

        # --- правила сценария (только subtracts_from_pool=True) ---
        sub_wt_ids = {
            w.id
            for w in self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.subtracts_from_pool == True)  # noqa: E712
            .all()
        }
        if not sub_wt_ids:
            rules: list[ScenarioRule] = []
        else:
            rules = (
                self.db.query(ScenarioRule)
                .filter(
                    ScenarioRule.scenario_id == scenario.id,
                    ScenarioRule.work_type_id.in_(sub_wt_ids),
                )
                .all()
            )

        # percent_of_norm по роли: role=None — фоллбэк для всех
        fallback_pct = sum(r.percent_of_norm for r in rules if r.role is None)
        by_role_pct: dict[str, float] = {}
        for r in rules:
            if r.role:
                by_role_pct[r.role] = by_role_pct.get(r.role, 0.0) + r.percent_of_norm

        def mandatory_pct(role: Optional[str]) -> float:
            """% нормы, занятый обязательными работами для данной роли."""
            if role and role in by_role_pct:
                return by_role_pct[role]
            return fallback_pct

        # --- итерация по сотрудникам ---
        result_emps: list[EmployeeBase] = []
        role_totals: dict[str, float] = {}

        for e in employees:
            # Отсутствия сотрудника, пересекающиеся с кварталом
            abs_ranges = (
                self.db.query(Absence)
                .filter(
                    Absence.employee_id == e.id,
                    Absence.start_date < period_end,
                    Absence.end_date >= period_start,
                )
                .all()
            )

            days_out: list[EmployeeDayHours] = []
            cur = period_start
            while cur < period_end:
                norm = day_hours(cur)
                if norm <= 0.0:
                    cur += timedelta(days=1)
                    continue

                # Проверка отсутствия: end_date ВКЛЮЧИТЕЛЬНО (как в CapacityService)
                on_absence = any(
                    a.start_date <= cur <= a.end_date for a in abs_ranges
                )
                if on_absence:
                    cur += timedelta(days=1)
                    continue

                pct = 1.0 - mandatory_pct(e.role) / 100.0
                # Зажимаем в [0.0, 1.0] для защиты от некорректных данных правил
                if pct < 0.0:
                    pct = 0.0
                if pct > 1.0:
                    pct = 1.0

                days_out.append(EmployeeDayHours(date=cur, hours=round(norm * pct, 2)))
                cur += timedelta(days=1)

            total = round(sum(d.hours for d in days_out), 2)
            result_emps.append(
                EmployeeBase(
                    employee_id=e.id,
                    display_name=e.display_name,
                    role=e.role,
                    days=days_out,
                    total_hours=total,
                )
            )
            if e.role:
                role_totals[e.role] = role_totals.get(e.role, 0.0) + total

        # external_qa_hours переопределяет сумму по роли «qa»
        if scenario.external_qa_hours is not None:
            role_totals["qa"] = scenario.external_qa_hours

        return ResourceBase(
            year=year,
            quarter=q,
            team=team,
            employees=result_emps,
            role_totals=role_totals,
            external_qa_hours=scenario.external_qa_hours,
        )
