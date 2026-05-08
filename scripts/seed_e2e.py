"""Seed deterministic data for Playwright E2E runs.

The script expects DATABASE_URL to point at the E2E database.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Employee, EmployeeTeam, Issue, Project, Worklog
from app.models.category import Category
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.user import User, UserRole
from app.core.security import hash_password


E2E_EMPLOYEE_ID = "00000000-0000-0000-0000-000000000001"
E2E_PROJECT_ID = "00000000-0000-0000-0000-000000000002"
E2E_EMPLOYEE_TEAM_ID = "00000000-0000-0000-0000-000000000003"
E2E_TEAM_NAME = "E2E Squad"

# Thematic report fixtures — deterministic UUIDs
E2E_WORK_TYPE_ID = "00000000-0000-0000-0000-000000000010"
E2E_CATEGORY_ID = "00000000-0000-0000-0000-000000000011"
E2E_CATEGORY_CODE = "e2e_support_consult"

# 5 issues for the thematic report smoke test
E2E_ISSUE_IDS = [
    f"00000000-0000-0000-0001-{i:012d}" for i in range(1, 6)
]
E2E_WORKLOG_IDS = [
    f"00000000-0000-0000-0002-{i:012d}" for i in range(1, 6)
]

# Worklogs in Q2 2026 (May — matches the global period month default on 2026-05-07)
E2E_WORKLOG_DATES = [
    datetime(2026, 5, 1, 9, 0),
    datetime(2026, 5, 2, 10, 0),
    datetime(2026, 5, 3, 9, 30),
    datetime(2026, 5, 4, 11, 0),
    datetime(2026, 5, 5, 14, 0),
]


def seed() -> None:
    from app.database import engine as _engine
    db_file = str(_engine.url.database or "")
    if not db_file.endswith("e2e.db"):
        raise RuntimeError(
            f"seed_e2e.py refuses to run on non-e2e DB (got: {db_file!r}). "
            "Set DATABASE_URL to point at data/e2e.db."
        )

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

        if not db.get(User, "e2e-admin-id"):
            db.add(
                User(
                    id="e2e-admin-id",
                    email="e2e-admin@example.com",
                    password_hash=hash_password("e2etest123"),
                    display_name="E2E Admin",
                    role=UserRole.admin,
                    default_team=None,
                    is_active=True,
                )
            )

        # ── Thematic report fixtures ──────────────────────────────────────
        # MandatoryWorkType for "Сопровождение и консультация"
        work_type = db.get(MandatoryWorkType, E2E_WORK_TYPE_ID)
        if work_type is None:
            db.add(
                MandatoryWorkType(
                    id=E2E_WORK_TYPE_ID,
                    code="e2e_support_consult",
                    label="E2E Сопровождение",
                    is_active=True,
                    sort_order=99,
                    subtracts_from_pool=True,
                    is_system=False,
                    theme_dict_version=1,
                )
            )

        # Category linked to that work type
        category = db.get(Category, E2E_CATEGORY_ID)
        if category is None:
            db.add(
                Category(
                    id=E2E_CATEGORY_ID,
                    code=E2E_CATEGORY_CODE,
                    label="E2E Сопровождение и консультация",
                    work_type_id=E2E_WORK_TYPE_ID,
                    is_system=False,
                    sort_order=99,
                )
            )

        # 5 issues with assigned_category → our category code
        for idx, issue_id in enumerate(E2E_ISSUE_IDS, start=1):
            if not db.get(Issue, issue_id):
                db.add(
                    Issue(
                        id=issue_id,
                        jira_issue_id=f"e2e-issue-{idx}",
                        key=f"E2E-{200 + idx}",
                        summary=f"E2E сопровождение задача {idx}",
                        issue_type="Task",
                        status="In Progress",
                        project_id=E2E_PROJECT_ID,
                        category="support_consult",
                        assigned_category=E2E_CATEGORY_CODE,
                        team=E2E_TEAM_NAME,
                        include_in_analysis=True,
                        out_of_scope=False,
                    )
                )

        # Worklogs for those issues in Q2 2026 (May — matches global period month default)
        for idx, (worklog_id, issue_id, started_at) in enumerate(
            zip(E2E_WORKLOG_IDS, E2E_ISSUE_IDS, E2E_WORKLOG_DATES), start=1
        ):
            existing_wl = db.execute(
                select(Worklog).where(Worklog.jira_worklog_id == f"e2e-wl-{idx}")
            ).scalar_one_or_none()
            if existing_wl is None:
                db.add(
                    Worklog(
                        id=worklog_id,
                        jira_worklog_id=f"e2e-wl-{idx}",
                        issue_id=issue_id,
                        employee_id=E2E_EMPLOYEE_ID,
                        started_at=started_at,
                        hours=4.0,
                        time_spent_seconds=14400,
                        comment_text=f"E2E worklog {idx}",
                    )
                )
            else:
                # Update dates if they point to the old April fixtures
                existing_wl.started_at = started_at
                existing_wl.issue_id = issue_id

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
