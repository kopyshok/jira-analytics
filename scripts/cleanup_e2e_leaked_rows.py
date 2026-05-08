"""One-shot script to remove E2E seed rows that leaked into the dev DB.

Run once:
    py -3.10 scripts/cleanup_e2e_leaked_rows.py

Refuses to run if DATABASE_URL points at a file ending with 'e2e.db'.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.database import engine, SessionLocal

# Guard: refuse to run against the e2e database itself
db_path = str(engine.url.database or "")
if db_path.endswith("e2e.db"):
    print(f"ERROR: target DB is '{db_path}' — refusing to clean an e2e database.")
    sys.exit(1)

print(f"Target DB: {db_path}")

E2E_WORK_TYPE_ID = "00000000-0000-0000-0000-000000000010"
E2E_EMPLOYEE_ID = "00000000-0000-0000-0000-000000000001"
E2E_PROJECT_ID = "00000000-0000-0000-0000-000000000002"
E2E_EMPLOYEE_TEAM_ID = "00000000-0000-0000-0000-000000000003"
E2E_USER_ID = "e2e-admin-id"
E2E_ISSUE_IDS = [f"00000000-0000-0000-0001-{i:012d}" for i in range(1, 6)]

db = SessionLocal()
totals: dict[str, int] = {}

try:
    def delete_where(table: str, condition: str, params: dict) -> int:
        result = db.execute(text(f"DELETE FROM {table} WHERE {condition}"), params)
        return result.rowcount

    # IssueClassification for e2e work type
    totals["issue_classifications"] = delete_where(
        "issue_classifications", "work_type_id = :wt_id", {"wt_id": E2E_WORK_TYPE_ID}
    )

    # WorkTypeReportSnapshot for e2e work type
    totals["work_type_report_snapshots"] = delete_where(
        "work_type_report_snapshots", "work_type_id = :wt_id", {"wt_id": E2E_WORK_TYPE_ID}
    )

    # WorkTypeReportLayout for e2e work type
    totals["work_type_report_layouts"] = delete_where(
        "work_type_report_layouts", "work_type_id = :wt_id", {"wt_id": E2E_WORK_TYPE_ID}
    )

    # Theme rows for e2e work type
    totals["themes"] = delete_where(
        "themes", "work_type_id = :wt_id", {"wt_id": E2E_WORK_TYPE_ID}
    )

    # Category rows for e2e work type
    totals["categories"] = delete_where(
        "categories", "work_type_id = :wt_id", {"wt_id": E2E_WORK_TYPE_ID}
    )

    # Worklogs for e2e issues or by e2e employee
    issue_placeholders = ", ".join([f":iid{i}" for i in range(len(E2E_ISSUE_IDS))])
    issue_params = {f"iid{i}": v for i, v in enumerate(E2E_ISSUE_IDS)}
    totals["worklogs"] = delete_where(
        "worklogs",
        f"issue_id IN ({issue_placeholders}) OR employee_id = :emp_id",
        {**issue_params, "emp_id": E2E_EMPLOYEE_ID},
    )

    # Issues
    totals["issues"] = delete_where(
        "issues",
        f"id IN ({issue_placeholders})",
        issue_params,
    )

    # Project
    totals["projects"] = delete_where(
        "projects", "id = :pid", {"pid": E2E_PROJECT_ID}
    )

    # EmployeeTeam
    totals["employee_teams"] = delete_where(
        "employee_teams", "id = :etid", {"etid": E2E_EMPLOYEE_TEAM_ID}
    )

    # Employee
    totals["employees"] = delete_where(
        "employees", "id = :eid", {"eid": E2E_EMPLOYEE_ID}
    )

    # User
    totals["users"] = delete_where(
        "users", "id = :uid", {"uid": E2E_USER_ID}
    )

    # MandatoryWorkType
    totals["mandatory_work_types"] = delete_where(
        "mandatory_work_types", "id = :wt_id", {"wt_id": E2E_WORK_TYPE_ID}
    )

    db.commit()
    print("\nDeleted rows per table:")
    for tbl, cnt in totals.items():
        print(f"  {tbl}: {cnt}")
    print("\nDone.")

except Exception as exc:
    db.rollback()
    print(f"ERROR: {exc}")
    sys.exit(1)
finally:
    db.close()
