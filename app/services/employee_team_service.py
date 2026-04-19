"""Авто-определение команды сотрудника по ворклогам.

Мода берётся по суммарным часам на задачах с заданным `issue.team`,
в окне последних `lookback_days` дней. Возвращает None, если у сотрудника
нет worklog'ов с ненулевым team за окно.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Category, Employee, Issue, Worklog


# Коды категорий, исключаемые из скана: «Архив прочих задач» + «Инициативы».
# Остальные — «Активный стек» ∪ «Архив квартальных задач».
EXCLUDED_CATEGORY_CODES: set[str] = {"archive", "initiatives_rfa"}


@dataclass
class AutoDetectSummary:
    assigned: int
    skipped: int
    details: list[dict]


class EmployeeTeamService:
    def __init__(self, db: Session):
        self.db = db

    def _target_category_codes(self) -> set[str]:
        all_codes = {c.code for c in self.db.query(Category).all()}
        return all_codes - EXCLUDED_CATEGORY_CODES

    def auto_detect_team(
        self, employee_id: str, *, lookback_days: Optional[int] = None
    ) -> Optional[str]:
        target_codes = self._target_category_codes()
        q = (
            self.db.query(
                Issue.team.label("team"),
                func.coalesce(func.sum(Worklog.time_spent_seconds), 0).label("seconds"),
            )
            .join(Worklog, Worklog.issue_id == Issue.id)
            .filter(
                Worklog.employee_id == employee_id,
                Issue.team.isnot(None),
                Issue.team != "",
                Issue.category.in_(target_codes),
            )
        )
        if lookback_days is not None:
            cutoff = datetime.utcnow() - timedelta(days=lookback_days)
            q = q.filter(Worklog.started_at >= cutoff)
        rows = (
            q.group_by(Issue.team)
            .order_by(func.sum(Worklog.time_spent_seconds).desc())
            .all()
        )
        if not rows:
            return None
        return rows[0].team

    def auto_detect_all_missing(self) -> AutoDetectSummary:
        assigned = 0
        skipped = 0
        details: list[dict] = []
        employees = (
            self.db.query(Employee)
            .filter(Employee.is_active == True)  # noqa: E712
            .all()
        )
        for emp in employees:
            if emp.team:
                skipped += 1
                continue
            team = self.auto_detect_team(emp.id)
            if team is None:
                skipped += 1
                continue
            emp.team = team
            assigned += 1
            details.append({"employee_id": emp.id, "team": team})
        self.db.commit()
        return AutoDetectSummary(assigned=assigned, skipped=skipped, details=details)
