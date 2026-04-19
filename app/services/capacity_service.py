"""Сервис расчёта доступной ёмкости сотрудников.

Формула:
    available = norm_hours - vacation_hours - mandatory_hours

где:
- norm_hours = сумма ``production_calendar_day.hours`` за месяц
  (8ч будни, 7ч предпраздничные, 0 выходные/праздники), масштабируется на
  ``hours_per_day / 8``. Если в БД дня нет — фоллбэк ``hours_per_day`` на
  каждый Пн–Пт.
- vacation_hours = норма часов за дни отпуска, попавшие в период
  (та же логика, что и для norm_hours).
- mandatory_hours = norm_hours × percent_of_norm / 100
  (из monthly_capacity_rules — обязательные работы вроде сопровождения).
"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Absence, Employee, MonthlyCapacityRule, Worklog
from app.services.production_calendar_service import ProductionCalendarService


DEFAULT_HOURS_PER_DAY = 8.0

# Квартал -> месяцы
QUARTER_MONTHS: dict[int, tuple[int, int, int]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}


@dataclass
class MonthlyCapacity:
    """Доступная ёмкость сотрудника за месяц."""

    employee_id: str
    employee_name: str
    year: int
    month: int
    workdays: int
    norm_hours: float
    vacation_hours: float
    mandatory_hours: float
    available_hours: float
    fact_hours: float = 0.0


@dataclass
class QuarterCapacity:
    """Доступная ёмкость сотрудника за квартал."""

    employee_id: str
    employee_name: str
    year: int
    quarter: int
    months: list[MonthlyCapacity] = field(default_factory=list)
    total_norm_hours: float = 0.0
    total_vacation_hours: float = 0.0
    total_mandatory_hours: float = 0.0
    total_available_hours: float = 0.0
    total_fact_hours: float = 0.0
    team: Optional[str] = None


class RulesConflict(Exception):
    def __init__(self, conflicts: list[tuple[int, int]]):
        self.conflicts = conflicts
        super().__init__(f"Target months already have rules: {conflicts}")


class CapacityService:
    """Сервис расчёта ёмкости на месяц/квартал."""

    def __init__(
        self,
        db: Session,
        hours_per_day: float = DEFAULT_HOURS_PER_DAY,
        production_calendar: Optional[ProductionCalendarService] = None,
    ):
        self.db = db
        self.hours_per_day = hours_per_day
        self.production_calendar = (
            production_calendar or ProductionCalendarService(db)
        )

    # === Календарь ===

    def _workdays_in_range(self, start: date, end: date) -> int:
        """Количество рабочих дней в интервале [start, end].

        Использует ProductionCalendarService: переопределения из таблицы
        ``production_calendar_day`` (праздники, переносы) применяются поверх
        правила по умолчанию ``weekday() < 5``.
        """
        if end < start:
            return 0
        overrides = self.production_calendar.workdays_in_range_map(start, end)
        days = 0
        current = start
        while current <= end:
            is_wd = overrides.get(current, current.weekday() < 5)
            if is_wd:
                days += 1
            current += timedelta(days=1)
        return days

    def _norm_hours_in_range(self, start: date, end: date) -> float:
        """Сумма нормы рабочих часов за интервал.

        Если день есть в ``production_calendar_day`` — берётся его ``hours``
        (предпраздничный=7, будни=8, выходной/праздник=0) и масштабируется по
        ``hours_per_day / DEFAULT_HOURS_PER_DAY``. Для дней без записи —
        фоллбэк: ``hours_per_day`` для Пн–Пт, иначе 0.
        """
        if end < start:
            return 0.0
        hours_map = self.production_calendar.hours_in_range_map(start, end)
        scale = self.hours_per_day / DEFAULT_HOURS_PER_DAY
        total = 0.0
        current = start
        while current <= end:
            cal_hours = hours_map.get(current)
            if cal_hours is not None:
                total += cal_hours * scale
            elif current.weekday() < 5:
                total += self.hours_per_day
            current += timedelta(days=1)
        return total

    def _month_bounds(self, year: int, month: int) -> tuple[date, date]:
        last_day = monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    def _workdays_in_month(self, year: int, month: int) -> int:
        start, end = self._month_bounds(year, month)
        return self._workdays_in_range(start, end)

    def _norm_hours_in_month(self, year: int, month: int) -> float:
        start, end = self._month_bounds(year, month)
        return self._norm_hours_in_range(start, end)

    # === Вычеты ===

    def _absence_hours_for_month(
        self,
        employee_id: str,
        year: int,
        month: int,
    ) -> float:
        """Часы отсутствия сотрудника, попавшие в конкретный месяц.

        Сумма нормы рабочих часов за дни пересечения каждого отсутствия с месяцем
        (делегируется в `_norm_hours_in_range`, который учитывает производственный
        календарь: предпраздничные 7 ч, будни 8 ч).
        """
        month_start, month_end = self._month_bounds(year, month)

        absences = (
            self.db.query(Absence)
            .filter(
                Absence.employee_id == employee_id,
                Absence.start_date <= month_end,
                Absence.end_date >= month_start,
            )
            .all()
        )

        total = 0.0
        for absence in absences:
            overlap_start = max(absence.start_date, month_start)
            overlap_end = min(absence.end_date, month_end)
            total += self._norm_hours_in_range(overlap_start, overlap_end)
        return total

    def _mandatory_hours_for_month(
        self,
        norm_hours: float,
        year: int,
        month: int,
    ) -> float:
        """Часы обязательных работ по правилу на месяц."""
        rule = (
            self.db.query(MonthlyCapacityRule)
            .filter(
                MonthlyCapacityRule.year == year,
                MonthlyCapacityRule.month == month,
            )
            .one_or_none()
        )
        if rule is None:
            return 0.0
        return norm_hours * rule.percent_of_norm / 100.0

    # === Основные расчёты ===

    def _get_employee(self, employee_id: str) -> Employee:
        employee = self.db.get(Employee, employee_id)
        if employee is None:
            raise ValueError(f"Employee {employee_id} not found")
        return employee

    def monthly_capacity(
        self,
        employee_id: str,
        year: int,
        month: int,
    ) -> MonthlyCapacity:
        """Доступная ёмкость сотрудника за месяц."""
        if not 1 <= month <= 12:
            raise ValueError(f"Month must be 1..12, got {month}")

        employee = self._get_employee(employee_id)

        workdays = self._workdays_in_month(year, month)
        norm_hours = self._norm_hours_in_month(year, month)
        vacation_hours = self._absence_hours_for_month(
            employee_id, year, month
        )
        mandatory_hours = self._mandatory_hours_for_month(
            norm_hours, year, month
        )
        available = max(0.0, norm_hours - vacation_hours - mandatory_hours)

        month_start = date(year, month, 1)
        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)

        fact = self.db.query(
            func.coalesce(func.sum(Worklog.hours), 0.0)
        ).filter(
            Worklog.employee_id == employee_id,
            Worklog.started_at >= datetime.combine(
                month_start, datetime.min.time()
            ),
            Worklog.started_at < datetime.combine(
                next_month_start, datetime.min.time()
            ),
        ).scalar() or 0.0

        return MonthlyCapacity(
            employee_id=employee.id,
            employee_name=employee.display_name,
            year=year,
            month=month,
            workdays=workdays,
            norm_hours=norm_hours,
            vacation_hours=vacation_hours,
            mandatory_hours=mandatory_hours,
            available_hours=available,
            fact_hours=float(fact),
        )

    def quarter_capacity(
        self,
        employee_id: str,
        year: int,
        quarter: int,
    ) -> QuarterCapacity:
        """Доступная ёмкость сотрудника за квартал."""
        if quarter not in QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1..4, got {quarter}")

        employee = self._get_employee(employee_id)

        result = QuarterCapacity(
            employee_id=employee.id,
            employee_name=employee.display_name,
            year=year,
            quarter=quarter,
            team=employee.team,
        )

        for month in QUARTER_MONTHS[quarter]:
            monthly = self.monthly_capacity(employee_id, year, month)
            result.months.append(monthly)
            result.total_norm_hours += monthly.norm_hours
            result.total_vacation_hours += monthly.vacation_hours
            result.total_mandatory_hours += monthly.mandatory_hours
            result.total_available_hours += monthly.available_hours

        result.total_fact_hours = sum(m.fact_hours for m in result.months)

        return result

    def team_quarter_capacity(
        self,
        year: int,
        quarter: int,
        employee_ids: Optional[list[str]] = None,
    ) -> list[QuarterCapacity]:
        """Ёмкость по команде за квартал.

        Если employee_ids не задан — считает для всех активных сотрудников.
        """
        query = self.db.query(Employee)
        if employee_ids:
            query = query.filter(Employee.id.in_(employee_ids))
        else:
            query = query.filter(Employee.is_active == True)  # noqa: E712

        employees = query.all()

        return [
            self.quarter_capacity(emp.id, year, quarter)
            for emp in employees
        ]

    def category_breakdown(
        self, year: int, quarter: int
    ) -> list["EmployeeCategoryBreakdown"]:
        """Факт-часы сотрудника за квартал, разложенные по 5 бакетам категорий."""
        from sqlalchemy import func
        from app.models import Employee, Issue, Worklog

        if quarter not in QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1..4, got {quarter}")
        months = QUARTER_MONTHS[quarter]
        start = date(year, months[0], 1)
        if months[-1] == 12:
            end_exclusive = date(year + 1, 1, 1)
        else:
            end_exclusive = date(year, months[-1] + 1, 1)

        rows = (
            self.db.query(
                Employee.id, Employee.display_name,
                Issue.assigned_category,
                func.coalesce(func.sum(Worklog.hours), 0.0).label("h"),
            )
            .join(Worklog, Worklog.employee_id == Employee.id)
            .join(Issue, Worklog.issue_id == Issue.id)
            .filter(
                Employee.is_active.is_(True),
                Worklog.started_at >= datetime.combine(start, datetime.min.time()),
                Worklog.started_at <  datetime.combine(end_exclusive, datetime.min.time()),
            )
            .group_by(Employee.id, Employee.display_name, Issue.assigned_category)
            .all()
        )

        per_employee: dict[str, EmployeeCategoryBreakdown] = {}
        for emp_id, name, code, hours in rows:
            row = per_employee.setdefault(
                emp_id,
                EmployeeCategoryBreakdown(
                    employee_id=emp_id, employee_name=name,
                    by_bucket={b: 0.0 for b in BUCKETS},
                    total_hours=0.0,
                ),
            )
            bucket = _bucket_for(code)
            row.by_bucket[bucket] += float(hours)
            row.total_hours += float(hours)

        return list(per_employee.values())

    def copy_rules_to_quarter(
        self,
        from_year: int,
        from_quarter: int,
        to_year: int,
        to_quarter: int,
    ) -> int:
        """Клонировать правила из (from_year, from_quarter) в (to_year, to_quarter).

        Сопоставляет M1→M1, M2→M2, M3→M3 внутри квартала.
        Raises RulesConflict если в цели уже есть правило для одного из месяцев.
        Raises ValueError если источник пуст.
        """
        src_months = QUARTER_MONTHS[from_quarter]
        dst_months = QUARTER_MONTHS[to_quarter]

        src_rules = (
            self.db.query(MonthlyCapacityRule)
            .filter(
                MonthlyCapacityRule.year == from_year,
                MonthlyCapacityRule.month.in_(src_months),
            )
            .all()
        )
        if not src_rules:
            raise ValueError(
                f"No rules found for source Q{from_quarter}/{from_year}"
            )

        by_src_month = {r.month: r for r in src_rules}

        existing = (
            self.db.query(MonthlyCapacityRule)
            .filter(
                MonthlyCapacityRule.year == to_year,
                MonthlyCapacityRule.month.in_(dst_months),
            )
            .all()
        )
        conflicts = [(to_year, e.month) for e in existing]
        if conflicts:
            raise RulesConflict(conflicts)

        created = 0
        for src_m, dst_m in zip(src_months, dst_months):
            src = by_src_month.get(src_m)
            if src is None:
                continue
            self.db.add(
                MonthlyCapacityRule(
                    year=to_year,
                    month=dst_m,
                    percent_of_norm=src.percent_of_norm,
                )
            )
            created += 1
        self.db.commit()
        return created


BUCKETS = ("active_stack", "initiatives", "archive_target",
           "archive_other", "uncategorized")


@dataclass
class EmployeeCategoryBreakdown:
    employee_id: str
    employee_name: str
    by_bucket: dict[str, float]
    total_hours: float


def _bucket_for(code: str | None) -> str:
    if code is None:
        return "uncategorized"
    if code == "archive":
        return "archive_other"
    if code == "archive_target":
        return "archive_target"
    if code == "initiatives_rfa":
        return "initiatives"
    return "active_stack"
