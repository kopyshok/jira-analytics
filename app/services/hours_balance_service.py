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
