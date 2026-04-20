"""Seed deterministic data for Playwright E2E runs.

The script expects DATABASE_URL to point at the E2E database.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Employee, EmployeeTeam, Project


E2E_EMPLOYEE_ID = "00000000-0000-0000-0000-000000000001"
E2E_PROJECT_ID = "00000000-0000-0000-0000-000000000002"
E2E_EMPLOYEE_TEAM_ID = "00000000-0000-0000-0000-000000000003"
E2E_TEAM_NAME = "E2E Squad"


def seed() -> None:
    db = SessionLocal()
    try:
        employee = db.get(Employee, E2E_EMPLOYEE_ID)
        if employee is None:
            db.add(
                Employee(
                    id=E2E_EMPLOYEE_ID,
                    jira_account_id="e2e-account-1",
                    display_name="E2E Analyst",
                    email="e2e.analyst@example.com",
                    role="analyst",
                    team=E2E_TEAM_NAME,
                    department="QA",
                    is_active=True,
                )
            )

        membership = db.get(EmployeeTeam, E2E_EMPLOYEE_TEAM_ID)
        if membership is None:
            db.add(
                EmployeeTeam(
                    id=E2E_EMPLOYEE_TEAM_ID,
                    employee_id=E2E_EMPLOYEE_ID,
                    team=E2E_TEAM_NAME,
                    is_primary=True,
                )
            )

        project = db.get(Project, E2E_PROJECT_ID)
        if project is None:
            db.add(
                Project(
                    id=E2E_PROJECT_ID,
                    jira_project_id="e2e-project-1",
                    key="E2E",
                    name="E2E Project",
                    project_type="software",
                    is_active=True,
                )
            )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
