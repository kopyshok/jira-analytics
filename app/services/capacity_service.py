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

# Планирование учитывает только эти три роли. Остальные (``other``, None)
# игнорируются в ``team_role_capacity`` и ``PlanningService``.
ROLE_WHITELIST: tuple[str, ...] = ("analyst", "dev", "qa")


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
        """Ёмкость по команде за квартал — batch-версия.

        Всю зависимую data (календарь, отсутствия, правила, ворклоги)
        читает одним набором запросов и считает in-memory, чтобы избежать
        N+1 при 300+ сотрудниках.
        """
        if quarter not in QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1..4, got {quarter}")

        from sqlalchemy import extract
        from app.models import Category, ProductionCalendarDay

        months = QUARTER_MONTHS[quarter]
        q_start = date(year, months[0], 1)
        last_day = monthrange(year, months[-1])[1]
        q_end = date(year, months[-1], last_day)

        query = self.db.query(Employee)
        if employee_ids:
            query = query.filter(Employee.id.in_(employee_ids))
        else:
            query = query.filter(Employee.is_active.is_(True))
        employees = query.all()
        if not employees:
            return []
        emp_ids = [e.id for e in employees]

        # 1. Календарь за квартал — одним запросом.
        cal_rows = (
            self.db.query(ProductionCalendarDay)
            .filter(
                ProductionCalendarDay.date >= q_start,
                ProductionCalendarDay.date <= q_end,
            )
            .all()
        )
        cal_hours: dict[date, float] = {r.date: float(r.hours) for r in cal_rows}
        cal_is_wd: dict[date, bool] = {r.date: bool(r.is_workday) for r in cal_rows}
        scale = self.hours_per_day / DEFAULT_HOURS_PER_DAY

        def _day_hours(d: date) -> float:
            h = cal_hours.get(d)
            if h is not None:
                return h * scale
            return self.hours_per_day if d.weekday() < 5 else 0.0

        def _day_is_workday(d: date) -> bool:
            is_wd = cal_is_wd.get(d)
            if is_wd is not None:
                return is_wd
            return d.weekday() < 5

        # 2. Помесячная норма и рабочие дни (не зависят от сотрудника).
        month_norm: dict[int, float] = {}
        month_workdays: dict[int, int] = {}
        for m in months:
            ms, me = self._month_bounds(year, m)
            norm = 0.0
            wd = 0
            cur = ms
            while cur <= me:
                if _day_is_workday(cur):
                    wd += 1
                norm += _day_hours(cur)
                cur += timedelta(days=1)
            month_norm[m] = norm
            month_workdays[m] = wd

        # 3. Отсутствия, пересекающие квартал, — одним запросом.
        abs_rows = (
            self.db.query(Absence)
            .filter(
                Absence.employee_id.in_(emp_ids),
                Absence.start_date <= q_end,
                Absence.end_date >= q_start,
            )
            .all()
        )
        abs_by_emp: dict[str, list[Absence]] = {}
        for a in abs_rows:
            abs_by_emp.setdefault(a.employee_id, []).append(a)

        # 4. Справочник видов работ + productive IDs.
        wts = (
            self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.is_active.is_(True))
            .all()
        )
        productive_ids: set[str] = {
            row[0]
            for row in self.db.query(Category.work_type_id)
            .filter(Category.work_type_id.is_not(None))
            .distinct()
            .all()
        }

        # 5. Правила per-role + overrides per-employee.
        role_rule_rows = (
            self.db.query(RoleCapacityRule)
            .filter(
                RoleCapacityRule.year == year,
                RoleCapacityRule.quarter == quarter,
            )
            .all()
        )
        # {role (or None) -> {work_type_id -> pct}}
        rules_by_role: dict[Optional[str], dict[str, float]] = {}
        for r in role_rule_rows:
            rules_by_role.setdefault(r.role, {})[r.work_type_id] = r.percent_of_norm
        fallback_rules = rules_by_role.get(None, {})

        override_rows = (
            self.db.query(EmployeeCapacityOverride)
            .filter(
                EmployeeCapacityOverride.year == year,
                EmployeeCapacityOverride.quarter == quarter,
                EmployeeCapacityOverride.employee_id.in_(emp_ids),
            )
            .all()
        )
        overrides_by_emp: dict[str, dict[str, float]] = {}
        for o in override_rows:
            overrides_by_emp.setdefault(o.employee_id, {})[o.work_type_id] = (
                o.percent_of_norm
            )

        # 6. Factt-часы per (employee, month) — одним SQL-агрегатом.
        q_start_dt = datetime.combine(q_start, datetime.min.time())
        # Exclusive upper bound on next month after quarter end.
        if months[-1] == 12:
            q_exclusive_end = datetime(year + 1, 1, 1)
        else:
            q_exclusive_end = datetime(year, months[-1] + 1, 1)

        fact_rows = (
            self.db.query(
                Worklog.employee_id,
                extract("month", Worklog.started_at).label("m"),
                func.coalesce(func.sum(Worklog.hours), 0.0).label("h"),
            )
            .filter(
                Worklog.employee_id.in_(emp_ids),
                Worklog.started_at >= q_start_dt,
                Worklog.started_at < q_exclusive_end,
            )
            .group_by(Worklog.employee_id, "m")
            .all()
        )
        fact_map: dict[tuple[str, int], float] = {
            (emp_id, int(m)): float(h) for emp_id, m, h in fact_rows
        }

        # 7. Сборка результатов.
        results: list[QuarterCapacity] = []
        for emp in employees:
            emp_overrides = overrides_by_emp.get(emp.id, {})
            role_rules_for_emp = (
                rules_by_role.get(emp.role, {}) if emp.role else {}
            )

            productive_pct = 0.0
            for wt in wts:
                if wt.id in emp_overrides:
                    pct = emp_overrides[wt.id]
                elif wt.id in role_rules_for_emp:
                    pct = role_rules_for_emp[wt.id]
                elif wt.id in fallback_rules:
                    pct = fallback_rules[wt.id]
                else:
                    pct = 0.0
                if wt.id in productive_ids:
                    productive_pct += pct

            qc = QuarterCapacity(
                employee_id=emp.id,
                employee_name=emp.display_name,
                year=year,
                quarter=quarter,
                team=emp.team,
            )

            emp_absences = abs_by_emp.get(emp.id, [])
            for m in months:
                ms, me = self._month_bounds(year, m)
                absence_hours = 0.0
                for a in emp_absences:
                    ov_start = max(a.start_date, ms)
                    ov_end = min(a.end_date, me)
                    if ov_end < ov_start:
                        continue
                    cur = ov_start
                    while cur <= ov_end:
                        absence_hours += _day_hours(cur)
                        cur += timedelta(days=1)

                norm_hours = month_norm[m]
                workdays = month_workdays[m]
                effective_norm = max(0.0, norm_hours - absence_hours)
                available = effective_norm * (productive_pct / 100.0)
                mandatory = effective_norm - available
                fact = fact_map.get((emp.id, m), 0.0)

                qc.months.append(
                    MonthlyCapacity(
                        employee_id=emp.id,
                        employee_name=emp.display_name,
                        year=year,
                        month=m,
                        workdays=workdays,
                        norm_hours=norm_hours,
                        vacation_hours=absence_hours,
                        mandatory_hours=mandatory,
                        available_hours=available,
                        fact_hours=fact,
                    )
                )
                qc.total_norm_hours += norm_hours
                qc.total_vacation_hours += absence_hours
                qc.total_mandatory_hours += mandatory
                qc.total_available_hours += available
                qc.total_fact_hours += fact

            results.append(qc)

        return results

    # === Per-role aggregation (для backlog-planning) ===

    def employee_monthly_capacity(
        self,
        employee_id: str,
        year: int,
        month: int,
    ) -> dict:
        """Возвращает месячную ёмкость сотрудника как словарь.

        Тонкая обёртка над :meth:`monthly_capacity` — используется
        ``employee_quarter_capacity`` для удобной агрегации.
        """
        m = self.monthly_capacity(employee_id, year, month)
        return {
            "year": m.year,
            "month": m.month,
            "workdays": m.workdays,
            "norm_hours": m.norm_hours,
            "absence_hours": m.vacation_hours,
            "mandatory_hours": m.mandatory_hours,
            "available_hours": m.available_hours,
            "fact_hours": m.fact_hours,
        }

    def employee_quarter_capacity(
        self,
        employee_id: str,
        year: int,
        quarter: int,
    ) -> float:
        """Сумма ``available_hours`` сотрудника за 3 месяца квартала."""
        if quarter not in QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1..4, got {quarter}")
        total = 0.0
        for m in QUARTER_MONTHS[quarter]:
            total += self.employee_monthly_capacity(
                employee_id, year, m
            )["available_hours"]
        return total

    def team_role_capacity(
        self,
        year: int,
        quarter: int,
        team_filter: Optional[list[str]] = None,
    ) -> dict[str, float]:
        """Ёмкость активной команды, сгруппированная по ``Employee.role``.

        Возвращает словарь с ключами ``analyst``/``dev``/``qa`` (все три
        всегда присутствуют; 0, если нет сотрудников с данной ролью).
        Роли вне whitelist (``other``, None) игнорируются.

        ``team_filter`` — список названий команд. Сотрудник матчится, если
        состоит хотя бы в одной из указанных команд (через
        ``EmployeeTeam``). Дубли по JOIN устраняются через ``distinct()``.
        """
        if quarter not in QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1..4, got {quarter}")

        out: dict[str, float] = {r: 0.0 for r in ROLE_WHITELIST}
        query = self.db.query(Employee).filter(Employee.is_active.is_(True))
        if team_filter:
            from app.models import EmployeeTeam

            query = (
                query.join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
                .filter(EmployeeTeam.team.in_(team_filter))
                .distinct()
            )
        for emp in query.all():
            role = (emp.role or "").strip().lower()
            if role not in out:
                continue
            out[role] += self.employee_quarter_capacity(emp.id, year, quarter)
        return out

