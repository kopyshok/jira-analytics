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

from app.models import Employee, Issue, Worklog


@dataclass
class AutoDetectSummary:
    assigned: int
    skipped: int
    details: list[dict]


class EmployeeTeamService:
    def __init__(self, db: Session):
        self.db = db

    def auto_detect_team(
        self, employee_id: str, *, lookback_days: int = 180
    ) -> Optional[str]:
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        rows = (
            self.db.query(
                Issue.team.label("team"),
                func.coalesce(func.sum(Worklog.time_spent_seconds), 0).label("seconds"),
            )
            .join(Worklog, Worklog.issue_id == Issue.id)
            .filter(
                Worklog.employee_id == employee_id,
                Worklog.started_at >= cutoff,
                Issue.team.isnot(None),
                Issue.team != "",
            )
            .group_by(Issue.team)
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
