"""SnapshotWriter — заполнение всех snapshot-таблиц при создании ревизии сценария.

Один экземпляр = один проход. Все методы add()-ят строки в сессию;
commit делает вызывающий код.
"""
from sqlalchemy.orm import Session

from app.models import (
    Employee,
    EmployeeTeam,
    PlanningScenario,
    ScenarioRevision,
    ScenarioTeamSnapshot,
)


class SnapshotWriter:
    def __init__(self, db: Session):
        self.db = db

    def write_team_snapshot(
        self, revision: ScenarioRevision, scenario: PlanningScenario
    ) -> None:
        """Snapshot активных сотрудников команды сценария.

        Копирует display_name, role, hours_per_day=8.0, is_active.
        Если у сценария нет team или в команде нет сотрудников — ничего не пишет.
        """
        if not scenario.team:
            return
        employees = (
            self.db.query(Employee)
            .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .filter(
                EmployeeTeam.team == scenario.team,
                Employee.is_active.is_(True),
            )
            .all()
        )
        for emp in employees:
            self.db.add(
                ScenarioTeamSnapshot(
                    revision_id=revision.id,
                    employee_id=emp.id,
                    display_name=emp.display_name,
                    role=emp.role,
                    hours_per_day=8.0,
                    is_active=bool(emp.is_active),
                    is_external=False,
                )
            )
