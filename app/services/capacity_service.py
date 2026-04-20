"""Сервис расчёта доступной ёмкости сотрудников (v3).

Формула:
    effective_norm    = max(0, norm_hours − absence_hours)
    productive_pct    = Σ правил для work_types, у которых есть хоть одна
                        привязанная категория (Category.work_type_id = wt.id)
    available_hours   = effective_norm × productive_pct / 100
    mandatory_hours   = effective_norm − available_hours

Где ``mandatory_percent_breakdown`` резолвит процент per (employee, work_type) по
приоритету: employee_capacity_overrides > role_capacity_rules[role=e.role] >
role_capacity_rules[role=NULL] > 0.

v3 отличие от v2: проценты теперь описывают 100 % времени; «продуктивные» виды
работ вычитаются из нормы только косвенно (через долю НЕпродуктивных), а факт
(ворклоги) группируется per work_type через Category.work_type_id.
"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    Employee,
    EmployeeCapacityOverride,
    MandatoryWorkType,
    RoleCapacityRule,
    Worklog,
)
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


@dataclass
class WorkTypeBreakdownRow:
    work_type_id: Optional[str]
    work_type_label: str
    is_productive: bool
    plan_hours: float
    plan_pct: float
    fact_hours: float


class RulesConflict(Exception):
    """Целевой квартал уже содержит правила, подлежащие копированию."""

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__(f"Target quarter already has rules: {conflicts}")


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

    @staticmethod
    def _quarter_of(month: int) -> int:
        return (month - 1) // 3 + 1

    def mandatory_percent_breakdown(
        self,
        employee: Employee,
        year: int,
        quarter: int,
    ) -> dict[str, float]:
        """Для каждого активного work_type — итоговый процент обязательной нагрузки.

        Приоритет: employee_capacity_overrides > role_capacity_rules[role=e.role]
        > role_capacity_rules[role=NULL] > 0.
        """
        wts = (
            self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.is_active.is_(True))
            .all()
        )
        if not wts:
            return {}

        overrides = {
            o.work_type_id: o.percent_of_norm
            for o in self.db.query(EmployeeCapacityOverride)
            .filter(
                EmployeeCapacityOverride.employee_id == employee.id,
                EmployeeCapacityOverride.year == year,
                EmployeeCapacityOverride.quarter == quarter,
            )
            .all()
        }

        role_filter = (
            or_(
                RoleCapacityRule.role == employee.role,
                RoleCapacityRule.role.is_(None),
            )
            if employee.role is not None
            else RoleCapacityRule.role.is_(None)
        )
        role_rules = (
            self.db.query(RoleCapacityRule)
            .filter(
                RoleCapacityRule.year == year,
                RoleCapacityRule.quarter == quarter,
                role_filter,
            )
            .all()
        )
        by_wt_role: dict[str, float] = {}
        by_wt_fallback: dict[str, float] = {}
        for r in role_rules:
            if r.role == employee.role and employee.role is not None:
                by_wt_role[r.work_type_id] = r.percent_of_norm
            elif r.role is None:
                by_wt_fallback[r.work_type_id] = r.percent_of_norm

        result: dict[str, float] = {}
        for wt in wts:
            if wt.id in overrides:
                pct = overrides[wt.id]
            elif wt.id in by_wt_role:
                pct = by_wt_role[wt.id]
            elif wt.id in by_wt_fallback:
                pct = by_wt_fallback[wt.id]
            else:
                pct = 0.0
            result[wt.code] = pct
        return result

    def _productive_work_type_ids(self) -> set[str]:
        """IDs of work types that have at least one linked Category.

        These are the ``productive`` work types — their rule percentages
        contribute to ``available_hours`` (= productive share of norm).
        """
        from app.models import Category

        rows = (
            self.db.query(Category.work_type_id)
            .filter(Category.work_type_id.is_not(None))
            .distinct()
            .all()
        )
        return {row[0] for row in rows}

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
        """Доступная ёмкость сотрудника за месяц (v3)."""
        if not 1 <= month <= 12:
            raise ValueError(f"Month must be 1..12, got {month}")

        employee = self._get_employee(employee_id)

        workdays = self._workdays_in_month(year, month)
        norm_hours = self._norm_hours_in_month(year, month)
        absence_hours = self._absence_hours_for_month(
            employee_id, year, month
        )

        quarter = self._quarter_of(month)
        breakdown = self.mandatory_percent_breakdown(employee, year, quarter)
        productive_ids = self._productive_work_type_ids()

        wt_id_by_code = {
            w.code: w.id
            for w in self.db.query(MandatoryWorkType).all()
        }
        productive_pct = sum(
            pct
            for code, pct in breakdown.items()
            if wt_id_by_code.get(code) in productive_ids
        )

        effective_norm = max(0.0, norm_hours - absence_hours)
        available = effective_norm * (productive_pct / 100.0)
        mandatory_hours = effective_norm - available

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
            vacation_hours=absence_hours,
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

    def work_type_breakdown(
        self,
        employee_id: str,
        year: int,
        quarter: int,
    ) -> list[WorkTypeBreakdownRow]:
        """Plan vs fact per work_type for an employee in a given quarter."""
        from app.models import Category, Issue, MandatoryWorkType

        if quarter not in QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1..4, got {quarter}")

        employee = self._get_employee(employee_id)

        # Compute quarter norm minus absences (same approach as quarter_capacity).
        months = QUARTER_MONTHS[quarter]
        effective_norm = 0.0
        for m in months:
            nh = self._norm_hours_in_month(year, m)
            ah = self._absence_hours_for_month(employee_id, year, m)
            effective_norm += max(0.0, nh - ah)

        breakdown = self.mandatory_percent_breakdown(employee, year, quarter)
        productive_ids = self._productive_work_type_ids()

        all_wts = (
            self.db.query(MandatoryWorkType)
            .order_by(MandatoryWorkType.sort_order, MandatoryWorkType.code)
            .all()
        )

        # Fact: sum worklog hours in quarter, grouped by work_type via Issue.assigned_category.
        start = date(year, months[0], 1)
        if months[-1] == 12:
            end_exclusive = date(year + 1, 1, 1)
        else:
            end_exclusive = date(year, months[-1] + 1, 1)

        fact_rows = (
            self.db.query(
                Category.work_type_id,
                func.coalesce(func.sum(Worklog.hours), 0.0).label("h"),
            )
            .outerjoin(Issue, Issue.assigned_category == Category.code)
            .outerjoin(
                Worklog,
                (Worklog.issue_id == Issue.id)
                & (Worklog.employee_id == employee_id)
                & (Worklog.started_at >= datetime.combine(start, datetime.min.time()))
                & (Worklog.started_at < datetime.combine(end_exclusive, datetime.min.time())),
            )
            .group_by(Category.work_type_id)
            .all()
        )
        fact_by_wt: dict[Optional[str], float] = {
            wt_id: float(h) for wt_id, h in fact_rows
        }

        # Worklogs whose issue.assigned_category is None OR whose category code doesn't
        # appear in categories table → attribute to the None (uncategorized) bucket.
        none_hours = (
            self.db.query(func.coalesce(func.sum(Worklog.hours), 0.0))
            .join(Issue, Worklog.issue_id == Issue.id)
            .outerjoin(Category, Category.code == Issue.assigned_category)
            .filter(
                Worklog.employee_id == employee_id,
                Worklog.started_at >= datetime.combine(start, datetime.min.time()),
                Worklog.started_at < datetime.combine(end_exclusive, datetime.min.time()),
                (Category.id.is_(None)) | (Category.work_type_id.is_(None)),
            )
            .scalar() or 0.0
        )
        fact_by_wt[None] = float(none_hours)

        wt_id_by_code = {w.code: w.id for w in all_wts}

        rows: list[WorkTypeBreakdownRow] = []
        for wt in all_wts:
            pct = breakdown.get(wt.code, 0.0)
            rows.append(WorkTypeBreakdownRow(
                work_type_id=wt.id,
                work_type_label=wt.label,
                is_productive=wt.id in productive_ids,
                plan_hours=effective_norm * pct / 100.0,
                plan_pct=pct,
                fact_hours=fact_by_wt.get(wt.id, 0.0),
            ))
        rows.append(WorkTypeBreakdownRow(
            work_type_id=None,
            work_type_label="Без вида работ",
            is_productive=False,
            plan_hours=0.0,
            plan_pct=0.0,
            fact_hours=fact_by_wt.get(None, 0.0),
        ))
        return rows

    def copy_role_rules_to_quarter(
        self,
        from_year: int,
        from_quarter: int,
        to_year: int,
        to_quarter: int,
    ) -> int:
        """Клонировать все role_capacity_rules из одного квартала в другой.

        Raises RulesConflict если хотя бы одна запись в цели уже существует.
        Raises ValueError если источник пуст.
        """
        src_rules = (
            self.db.query(RoleCapacityRule)
            .filter(
                RoleCapacityRule.year == from_year,
                RoleCapacityRule.quarter == from_quarter,
            )
            .all()
        )
        if not src_rules:
            raise ValueError(
                f"No rules found for source Q{from_quarter}/{from_year}"
            )

        existing = (
            self.db.query(RoleCapacityRule)
            .filter(
                RoleCapacityRule.year == to_year,
                RoleCapacityRule.quarter == to_quarter,
            )
            .all()
        )
        if existing:
            conflicts = [
                {"role": r.role, "work_type_id": r.work_type_id}
                for r in existing
            ]
            raise RulesConflict(conflicts)

        for r in src_rules:
            self.db.add(
                RoleCapacityRule(
                    year=to_year,
                    quarter=to_quarter,
                    role=r.role,
                    work_type_id=r.work_type_id,
                    percent_of_norm=r.percent_of_norm,
                )
            )
        self.db.commit()
        return len(src_rules)


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
