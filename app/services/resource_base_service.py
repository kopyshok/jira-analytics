"""База ресурса команды — посуточная матрица доступных часов.

Для каждого сотрудника команды вычисляет количество «проектных» часов на
каждый рабочий день квартала: вычитает дни отсутствия и процент нормы,
занятый обязательными работами (только те виды работ, у которых
``subtracts_from_pool=True``).

Используется в Этапе B планирования (Task 11): фронтенд опирается на
посуточные итоги для пересчёта ролевых ёмкостей при выборе инициатив.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Absence,
    AbsenceReason,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    ScenarioRule,
)

DEFAULT_HOURS_PER_DAY = 8.0

ROLE_PREFERRED_ORDER = ['analyst', 'dev', 'qa', 'consultant', 'project_manager']


@dataclass
class WorkTypeSummaryRow:
    """Строка разбивки по одному виду обязательных работ."""

    work_type_id: str
    work_type_label: str
    hours_by_role: dict[str, float]           # role_code -> часы (0 если нет правила)
    pct_by_role: dict[str, Optional[float]]   # role_code -> % (None если нет правила)
    total_hours: float
    subtracts_from_pool: bool


@dataclass
class ResourceSummary:
    """Сводная разбивка ресурса команды по видам обязательных работ и ролям."""

    year: int
    quarter: int
    team: str
    roles: list[str]                           # упорядоченные коды ролей в команде
    role_employee_names: dict[str, list[str]]  # role_code -> отсортированные имена
    gross_by_role: dict[str, float]            # норма-часы до вычета обязательных
    gross_total: float
    work_type_rows: list[WorkTypeSummaryRow]   # только subtracts_from_pool=True
    available_by_role: dict[str, float]        # после вычета обязательных
    available_total: float
    external_qa_hours: Optional[float]
    calendar_gross_by_role: dict[str, float]          # production calendar hours, no deductions
    absence_days_by_employee: list[dict]               # [{employee_id, display_name, role, planned_days, unplanned_days}]


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

    def compute_summary(self, scenario: PlanningScenario) -> ResourceSummary:
        """Сводная разбивка: норма-часы → обязательные работы → на бэклог, по ролям."""
        year = scenario.year
        q = int(str(scenario.quarter).replace("Q", ""))
        team = scenario.team
        months = self.QUARTER_MONTHS[q]
        period_start = date(year, months[0], 1)
        last_m = months[-1]
        next_year = year + 1 if last_m == 12 else year
        next_month = 1 if last_m == 12 else last_m + 1
        period_end = date(next_year, next_month, 1)

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

        # --- производственный календарь ---
        cal_overrides: dict[date, float] = {
            row.date: float(row.hours)
            for row in self.db.query(ProductionCalendarDay).filter(
                ProductionCalendarDay.date >= period_start,
                ProductionCalendarDay.date < period_end,
            ).all()
        }

        def day_hours(d: date) -> float:
            if d in cal_overrides:
                return cal_overrides[d]
            return DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0

        # --- виды обязательных работ (все активные) ---
        work_types = (
            self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.is_active == True)  # noqa: E712
            .order_by(MandatoryWorkType.sort_order.asc().nullsfirst())
            .all()
        )
        wt_ids = {wt.id for wt in work_types}

        # --- правила сценария для этих видов работ ---
        rules: list[ScenarioRule] = []
        if wt_ids:
            rules = (
                self.db.query(ScenarioRule)
                .filter(
                    ScenarioRule.scenario_id == scenario.id,
                    ScenarioRule.work_type_id.in_(wt_ids),
                )
                .all()
            )

        # Словарь: (work_type_id, role_or_None) -> pct
        rule_lookup: dict[tuple[str, Optional[str]], float] = {}
        for r in rules:
            key = (r.work_type_id, r.role)
            rule_lookup[key] = rule_lookup.get(key, 0.0) + r.percent_of_norm

        def wt_pct_for_role(wt_id: str, role: Optional[str]) -> Optional[float]:
            if role and (wt_id, role) in rule_lookup:
                return rule_lookup[(wt_id, role)]
            if (wt_id, None) in rule_lookup:
                return rule_lookup[(wt_id, None)]
            return None

        # --- брутто: производственный календарь × сотрудники (без любых вычетов) ---
        calendar_gross_by_role: dict[str, float] = {}
        for e in employees:
            total_cal = 0.0
            cur = period_start
            while cur < period_end:
                total_cal += day_hours(cur)
                cur += timedelta(days=1)
            if e.role:
                calendar_gross_by_role[e.role] = (
                    calendar_gross_by_role.get(e.role, 0.0) + round(total_cal, 2)
                )

        # --- валовые часы по сотрудникам (без вычета обязательных) ---
        gross_by_emp: dict[str, float] = {}
        emp_role: dict[str, Optional[str]] = {}
        emp_name: dict[str, str] = {}

        for e in employees:
            abs_ranges = (
                self.db.query(Absence)
                .filter(
                    Absence.employee_id == e.id,
                    Absence.start_date < period_end,
                    Absence.end_date >= period_start,
                )
                .all()
            )
            total = 0.0
            cur = period_start
            while cur < period_end:
                norm = day_hours(cur)
                if norm > 0:
                    on_absence = any(a.start_date <= cur <= a.end_date for a in abs_ranges)
                    if not on_absence:
                        total += norm
                cur += timedelta(days=1)

            gross_by_emp[e.id] = round(total, 2)
            emp_role[e.id] = e.role
            emp_name[e.id] = e.display_name

        # --- дни отсутствия по сотрудникам (отпуск vs прочее) ---
        reason_planned_map: dict[str, bool] = {
            r.id: r.is_planned for r in self.db.query(AbsenceReason).all()
        }
        absence_days_by_employee: list[dict] = []
        for e in employees:
            abs_ranges = (
                self.db.query(Absence)
                .filter(
                    Absence.employee_id == e.id,
                    Absence.start_date < period_end,
                    Absence.end_date >= period_start,
                )
                .all()
            )
            planned_days = 0.0
            unplanned_days = 0.0
            cur = period_start
            while cur < period_end:
                if day_hours(cur) > 0:
                    covering = [a for a in abs_ranges if a.start_date <= cur <= a.end_date]
                    if covering:
                        # день относим к «отпуску», если хотя бы одна покрывающая
                        # причина — плановая; иначе — к «прочему».
                        is_planned_day = any(
                            reason_planned_map.get(a.reason_id, False) for a in covering
                        )
                        if is_planned_day:
                            planned_days += 1.0
                        else:
                            unplanned_days += 1.0
                cur += timedelta(days=1)
            if planned_days > 0 or unplanned_days > 0:
                absence_days_by_employee.append({
                    "employee_id": e.id,
                    "display_name": e.display_name,
                    "role": e.role,
                    "planned_days": planned_days,
                    "unplanned_days": unplanned_days,
                })

        # --- агрегация по ролям ---
        role_employee_names: dict[str, list[str]] = {}
        gross_by_role: dict[str, float] = {}
        for emp_id, gross in gross_by_emp.items():
            role = emp_role[emp_id]
            if role:
                gross_by_role[role] = gross_by_role.get(role, 0.0) + gross
                role_employee_names.setdefault(role, []).append(emp_name[emp_id])

        for names in role_employee_names.values():
            names.sort()

        # Упорядочиваем роли по предпочтительному порядку.
        # Если задан external_qa_hours, добавляем 'qa' в список даже при отсутствии
        # ТС-сотрудников в команде — чтобы колонка Тестировщики всегда отображалась.
        base_roles = set(gross_by_role.keys())
        if scenario.external_qa_hours is not None:
            # Внешний QA ПОЛНОСТЬЮ замещает часы штатных QA-сотрудников —
            # так же, как в compute() (role_totals['qa'] = external_qa_hours)
            # и как описано в тултипе ExternalQaInput: «При пустом значении
            # используются часы штатных QA». Иначе верхняя таблица показывала
            # бы qa = внутренний + внешний, а правый блок — только внешний,
            # что давало расхождение у пользователя (680 vs 340).
            base_roles.add('qa')
            ext = float(scenario.external_qa_hours)
            gross_by_role['qa'] = ext
            calendar_gross_by_role['qa'] = ext
            role_employee_names.setdefault('qa', [])
        roles_ordered = sorted(
            base_roles,
            key=lambda r: (
                ROLE_PREFERRED_ORDER.index(r)
                if r in ROLE_PREFERRED_ORDER
                else len(ROLE_PREFERRED_ORDER)
            ),
        )

        # --- строки по видам работ ---
        wt_rows: list[WorkTypeSummaryRow] = []
        for wt in work_types:
            hours_by_role: dict[str, float] = {}
            pct_by_role: dict[str, Optional[float]] = {}
            total_wt = 0.0
            for role in roles_ordered:
                pct = wt_pct_for_role(wt.id, role)
                pct_by_role[role] = pct
                h = round(gross_by_role.get(role, 0.0) * (pct or 0.0) / 100.0, 2)
                hours_by_role[role] = h
                total_wt += h
            if total_wt > 0 or any(v is not None for v in pct_by_role.values()):
                wt_rows.append(
                    WorkTypeSummaryRow(
                        work_type_id=wt.id,
                        work_type_label=wt.label,
                        hours_by_role=hours_by_role,
                        pct_by_role=pct_by_role,
                        total_hours=round(total_wt, 2),
                        subtracts_from_pool=wt.subtracts_from_pool,
                    )
                )

        # --- доступные часы = валовые − обязательные (только subtracts_from_pool=True) ---
        available_by_role: dict[str, float] = {}
        for role in roles_ordered:
            gross = gross_by_role.get(role, 0.0)
            mandatory_total = sum(
                row.hours_by_role.get(role, 0.0)
                for row in wt_rows
                if row.subtracts_from_pool
            )
            available_by_role[role] = round(max(0.0, gross - mandatory_total), 2)

        gross_total = round(sum(gross_by_role.values()), 2)
        available_total = round(sum(available_by_role.values()), 2)

        return ResourceSummary(
            year=year,
            quarter=q,
            team=team,
            roles=list(roles_ordered),
            role_employee_names=role_employee_names,
            gross_by_role=gross_by_role,
            gross_total=gross_total,
            work_type_rows=wt_rows,
            available_by_role=available_by_role,
            available_total=available_total,
            external_qa_hours=scenario.external_qa_hours,
            calendar_gross_by_role=calendar_gross_by_role,
            absence_days_by_employee=absence_days_by_employee,
        )
