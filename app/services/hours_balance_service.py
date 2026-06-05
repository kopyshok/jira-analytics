"""Сервис расчёта баланса часов: переработки и автоотгулы.

Норма дня = производственный календарь − официальные отсутствия (кроме «Отгула»).
Дельта дня = факт − эффективная норма. Накопительный баланс по периоду.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.worklog import Worklog
from app.services.production_calendar_service import ProductionCalendarService

logger = logging.getLogger(__name__)

DAY_OFF_CODE = "day_off"
CLASS_THRESHOLD_PCT = 0.10  # ±10% от нормы — считается «норма»

MONTH_LABELS_RU = [
    "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
]


@dataclass
class DayCalc:
    day: date
    norm: float
    fact: float
    delta: float
    kind: str  # norm | overtime | skip | absence | holiday
    absence_label: Optional[str] = None


@dataclass
class EmployeeBalanceResult:
    id: str
    full_name: str
    role_label: Optional[str]
    avatar_url: Optional[str]
    initials: str
    balance_hours: float
    overtime_days: int
    overtime_hours: float
    skip_days: int
    skip_hours: float
    sparkline: list


@dataclass
class TeamBalanceResult:
    period_from: date
    period_to: date
    working_days: int
    team_summary_employees_count: int
    team_summary_overtime_hours: float
    team_summary_skip_hours: float
    team_summary_net_balance: float
    employees: list


@dataclass
class MonthlySummaryResult:
    year: int
    month: int
    label: str
    balance: float
    overtime_days: int
    skip_days: int


@dataclass
class EmployeeDetailResult:
    employee_id: str
    full_name: str
    role_label: Optional[str]
    team_label: Optional[str]
    initials: str
    avatar_url: Optional[str]
    period_from: date
    period_to: date
    balance_hours: float
    overtime_days: int
    overtime_hours: float
    skip_days: int
    skip_hours: float
    monthly: list
    days: list


class HoursBalanceService:
    def __init__(
        self,
        db: Session,
        production_calendar: Optional[ProductionCalendarService] = None,
    ) -> None:
        self.db = db
        self.production_calendar = production_calendar or ProductionCalendarService(db)
        self._warn_if_day_off_missing()

    def _warn_if_day_off_missing(self) -> None:
        exists = (
            self.db.query(AbsenceReason)
            .filter(AbsenceReason.code == DAY_OFF_CODE)
            .first()
        )
        if exists is None:
            logger.warning(
                "AbsenceReason code='%s' not found — автоотгулы детектиться не будут.",
                DAY_OFF_CODE,
            )

    def _absence_map(
        self,
        employee_ids: list[str],
        from_: date,
        to_: date,
    ) -> dict[tuple[str, date], str]:
        """Карта (employee_id, day) -> reason_label для absences кроме day_off."""
        if not employee_ids:
            return {}
        rows = (
            self.db.query(Absence, AbsenceReason)
            .join(AbsenceReason, Absence.reason_id == AbsenceReason.id)
            .filter(
                Absence.employee_id.in_(employee_ids),
                Absence.end_date >= from_,
                Absence.start_date <= to_,
                AbsenceReason.code != DAY_OFF_CODE,
            )
            .all()
        )
        result: dict[tuple[str, date], str] = {}
        for absence, reason in rows:
            cur = max(absence.start_date, from_)
            end = min(absence.end_date, to_)
            while cur <= end:
                result[(absence.employee_id, cur)] = reason.label
                cur += timedelta(days=1)
        return result

    def _worklog_map(
        self,
        employee_ids: list[str],
        from_: date,
        to_: date,
    ) -> dict[tuple[str, date], float]:
        """Карта (employee_id, day) -> sum(hours)."""
        if not employee_ids:
            return {}
        from app.models.worklog import Worklog as W
        day_col = func.date(W.started_at).label("day")
        rows = (
            self.db.query(
                W.employee_id,
                day_col,
                func.sum(W.hours).label("hours"),
            )
            .filter(
                W.employee_id.in_(employee_ids),
                W.started_at >= from_,
                W.started_at < to_ + timedelta(days=1),
            )
            .group_by(W.employee_id, day_col)
            .all()
        )
        result: dict[tuple[str, date], float] = {}
        for emp_id, day_val, hours in rows:
            # SQLite func.date returns string; coerce
            if isinstance(day_val, str):
                day_val = date.fromisoformat(day_val)
            result[(emp_id, day_val)] = float(hours or 0)
        return result

    def compute_team(
        self,
        employee_ids: list,
        from_: date,
        to_: date,
    ) -> TeamBalanceResult:
        """Считает баланс часов по команде за период."""
        if not employee_ids:
            return TeamBalanceResult(
                period_from=from_,
                period_to=to_,
                working_days=0,
                team_summary_employees_count=0,
                team_summary_overtime_hours=0.0,
                team_summary_skip_hours=0.0,
                team_summary_net_balance=0.0,
                employees=[],
            )

        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(employee_ids))
            .all()
        )
        if not employees:
            return TeamBalanceResult(
                period_from=from_,
                period_to=to_,
                working_days=0,
                team_summary_employees_count=0,
                team_summary_overtime_hours=0.0,
                team_summary_skip_hours=0.0,
                team_summary_net_balance=0.0,
                employees=[],
            )

        cal_hours = self.production_calendar.hours_in_range_map(from_, to_)
        absences = self._absence_map(employee_ids, from_, to_)
        worklogs = self._worklog_map(employee_ids, from_, to_)

        # Build list of working days + ALL days that have worklog activity
        working_days = 0
        days_iter: list[date] = []
        cur = from_
        while cur <= to_:
            ch = cal_hours.get(cur)
            if ch is not None:
                is_workday = ch > 0
            else:
                is_workday = cur.weekday() < 5
            if is_workday:
                working_days += 1
                days_iter.append(cur)
            else:
                # Include weekend/holiday days only if someone logged work there
                for emp in employees:
                    if worklogs.get((emp.id, cur), 0.0) > 0:
                        days_iter.append(cur)
                        break
            cur += timedelta(days=1)
        # Deduplicate and sort
        days_iter = sorted(set(days_iter))

        emp_results: list[EmployeeBalanceResult] = []
        team_overtime = 0.0
        team_skip = 0.0
        for e in employees:
            balance = 0.0
            overtime_days = 0
            overtime_hours = 0.0
            skip_days = 0
            skip_hours = 0.0
            sparkline: list[float] = []
            for d in days_iter:
                ch = cal_hours.get(d)
                if ch is not None:
                    base_norm = ch
                else:
                    base_norm = 8.0 if d.weekday() < 5 else 0.0
                absence_label = absences.get((e.id, d))
                # absence (not day_off) zeros the norm
                norm_eff = 0.0 if absence_label else max(0.0, base_norm)
                fact = worklogs.get((e.id, d), 0.0)
                if norm_eff == 0 and fact == 0:
                    sparkline.append(balance)
                    continue
                delta = fact - norm_eff
                balance += delta
                if delta > 0 and (norm_eff == 0 or delta > norm_eff * CLASS_THRESHOLD_PCT):
                    overtime_days += 1
                    overtime_hours += delta
                elif delta < 0 and abs(delta) > norm_eff * CLASS_THRESHOLD_PCT:
                    skip_days += 1
                    skip_hours += delta  # negative
                sparkline.append(balance)

            initials = "".join(p[0] for p in e.display_name.split()[:2]).upper() if e.display_name else "?"
            emp_results.append(EmployeeBalanceResult(
                id=e.id,
                full_name=e.display_name,
                role_label=getattr(getattr(e, "role", None), "label", None),
                avatar_url=getattr(e, "avatar_url", None),
                initials=initials,
                balance_hours=round(balance, 1),
                overtime_days=overtime_days,
                overtime_hours=round(overtime_hours, 1),
                skip_days=skip_days,
                skip_hours=round(skip_hours, 1),
                sparkline=[round(v, 1) for v in sparkline],
            ))
            team_overtime += overtime_hours
            team_skip += skip_hours

        return TeamBalanceResult(
            period_from=from_,
            period_to=to_,
            working_days=working_days,
            team_summary_employees_count=len(emp_results),
            team_summary_overtime_hours=round(team_overtime, 1),
            team_summary_skip_hours=round(team_skip, 1),
            team_summary_net_balance=round(team_overtime + team_skip, 1),
            employees=emp_results,
        )

    def compute_employee(
        self,
        employee_id: str,
        from_: date,
        to_: date,
    ) -> EmployeeDetailResult:
        """Посуточный drill-in по одному сотруднику за период."""
        e = self.db.get(Employee, employee_id)
        if e is None:
            raise ValueError(f"Employee {employee_id} not found")

        cal_hours = self.production_calendar.hours_in_range_map(from_, to_)
        absences = self._absence_map([employee_id], from_, to_)
        worklogs = self._worklog_map([employee_id], from_, to_)

        days: list[DayCalc] = []
        balance = 0.0
        overtime_days = 0
        overtime_hours = 0.0
        skip_days = 0
        skip_hours = 0.0
        monthly_acc: dict[tuple[int, int], dict] = defaultdict(
            lambda: {"balance": 0.0, "overtime_days": 0, "skip_days": 0}
        )

        cur = from_
        while cur <= to_:
            ch = cal_hours.get(cur)
            if ch is not None:
                base_norm = ch
            else:
                base_norm = 8.0 if cur.weekday() < 5 else 0.0
            absence_label = absences.get((employee_id, cur))
            fact = worklogs.get((employee_id, cur), 0.0)

            if absence_label:
                kind = "absence"
                days.append(DayCalc(cur, 0.0, fact, 0.0, kind, absence_label))
                cur += timedelta(days=1)
                continue

            if base_norm == 0:
                if fact > 0:
                    delta = fact
                    balance += delta
                    overtime_days += 1
                    overtime_hours += delta
                    monthly_acc[(cur.year, cur.month)]["balance"] += delta
                    monthly_acc[(cur.year, cur.month)]["overtime_days"] += 1
                    days.append(DayCalc(cur, 0.0, fact, delta, "overtime"))
                else:
                    # Weekend / holiday with no work — skip (don't include in days list)
                    pass
                cur += timedelta(days=1)
                continue

            # Regular workday — always process (fact=0 → auto-skip detection)
            delta = fact - base_norm
            balance += delta
            month_key = (cur.year, cur.month)
            monthly_acc[month_key]["balance"] += delta
            if delta > base_norm * CLASS_THRESHOLD_PCT:
                kind = "overtime"
                overtime_days += 1
                overtime_hours += delta
                monthly_acc[month_key]["overtime_days"] += 1
            elif -delta > base_norm * CLASS_THRESHOLD_PCT:
                kind = "skip"
                skip_days += 1
                skip_hours += delta
                monthly_acc[month_key]["skip_days"] += 1
            else:
                kind = "norm"
            days.append(DayCalc(cur, base_norm, fact, delta, kind))
            cur += timedelta(days=1)

        monthly = []
        for (y, m), acc in sorted(monthly_acc.items()):
            monthly.append(MonthlySummaryResult(
                year=y,
                month=m,
                label=MONTH_LABELS_RU[m - 1],
                balance=round(acc["balance"], 1),
                overtime_days=acc["overtime_days"],
                skip_days=acc["skip_days"],
            ))

        initials = "".join(p[0] for p in e.display_name.split()[:2]).upper() if e.display_name else "?"
        return EmployeeDetailResult(
            employee_id=e.id,
            full_name=e.display_name,
            role_label=getattr(getattr(e, "role", None), "label", None),
            team_label=getattr(e, "team", None),
            initials=initials,
            avatar_url=getattr(e, "avatar_url", None),
            period_from=from_,
            period_to=to_,
            balance_hours=round(balance, 1),
            overtime_days=overtime_days,
            overtime_hours=round(overtime_hours, 1),
            skip_days=skip_days,
            skip_hours=round(skip_hours, 1),
            monthly=monthly,
            days=days,
        )
