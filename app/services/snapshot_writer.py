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
        emp_ids = [
            r[0]
            for r in self.db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team == scenario.team)
            .all()
        ]
        if not emp_ids:
            return
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(emp_ids))
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
