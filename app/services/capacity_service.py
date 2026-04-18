"""Сервис расчёта доступной ёмкости сотрудников.

Формула:
    available = norm_hours - vacation_hours - mandatory_hours

где:
- norm_hours = количество рабочих дней в месяце × hours_per_day
- vacation_hours = пересечение отпусков сотрудника с периодом × hours_per_day
- mandatory_hours = norm_hours × percent_of_norm / 100
  (из monthly_capacity_rules — обязательные работы вроде сопровождения)

Для MVP используется упрощённый производственный календарь: рабочие дни —
понедельник-пятница. Реальный календарь с праздниками будет добавлен позже
как отдельная таблица/конфиг.
"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Employee, MonthlyCapacityRule, Vacation
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

    def _month_bounds(self, year: int, month: int) -> tuple[date, date]:
        last_day = monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    def _workdays_in_month(self, year: int, month: int) -> int:
        start, end = self._month_bounds(year, month)
        return self._workdays_in_range(start, end)

    # === Вычеты ===

    def _vacation_hours_for_month(
        self,
        employee_id: str,
        year: int,
        month: int,
    ) -> float:
        """Часы отпуска сотрудника, попавшие в конкретный месяц.

        Считается как количество рабочих дней пересечения каждого
        отпуска с месяцем × hours_per_day.
        """
        month_start, month_end = self._month_bounds(year, month)

        vacations = (
            self.db.query(Vacation)
            .filter(
                Vacation.employee_id == employee_id,
                Vacation.start_date <= month_end,
                Vacation.end_date >= month_start,
            )
            .all()
        )

        total = 0.0
        for vac in vacations:
            overlap_start = max(vac.start_date, month_start)
            overlap_end = min(vac.end_date, month_end)
            workdays = self._workdays_in_range(overlap_start, overlap_end)
            total += workdays * self.hours_per_day
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
        norm_hours = workdays * self.hours_per_day
        vacation_hours = self._vacation_hours_for_month(
            employee_id, year, month
        )
        mandatory_hours = self._mandatory_hours_for_month(
            norm_hours, year, month
        )
        available = max(0.0, norm_hours - vacation_hours - mandatory_hours)

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
        )

        for month in QUARTER_MONTHS[quarter]:
            monthly = self.monthly_capacity(employee_id, year, month)
            result.months.append(monthly)
            result.total_norm_hours += monthly.norm_hours
            result.total_vacation_hours += monthly.vacation_hours
            result.total_mandatory_hours += monthly.mandatory_hours
            result.total_available_hours += monthly.available_hours

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
