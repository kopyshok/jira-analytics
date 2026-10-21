"""Объединение двойников сотрудников: перенос данных, отказ, синк по старой учётке."""
from datetime import date, datetime

import pytest

from app.database import Base
from app.models import (
    Employee,
    EmployeeAccountAlias,
    EmployeePersonalSetting,
    EmployeeTeam,
    Issue,
    Project,
    Worklog,
)
from app.services import employee_merge
from app.services.employee_merge import MergeError
from app.services.sync_service import SyncService


def _people(db):
    old = Employee(jira_account_id="JIRAUSER13143", jira_username="medvedeva-n",
                   display_name="Медведева Надежда Владимировна", role="consultant")
    new = Employee(jira_account_id="JIRAUSER12022", jira_username="Medvedeva_N_V",
                   display_name="Медведева Надежда")
    db.add_all([old, new])
    db.flush()
    project = Project(jira_project_id="p1", key="OS", name="OS")
    db.add(project)
    db.flush()
    issue = Issue(jira_issue_id="i1", key="OS-1", summary="s", issue_type="Task",
                  status="Open", project_id=project.id,
                  assignee_account_id="JIRAUSER13143", developer_account_id="JIRAUSER13143")
    db.add(issue)
    db.flush()
    for n, (emp, day) in enumerate([(old, 2), (old, 3), (new, 10)]):
        db.add(Worklog(jira_worklog_id=f"w{n}", started_at=datetime(2026, 10, day, 10),
                       hours=1.0, time_spent_seconds=3600, issue_id=issue.id, employee_id=emp.id))
    db.add(EmployeeTeam(employee_id=old.id, team="Товарный учёт", is_primary=True))
    db.flush()
    return old, new, issue


def test_merge_moves_everything_and_removes_duplicate(db_session):
    db = db_session
    old, new, issue = _people(db)
    db.add_all([
        EmployeePersonalSetting(employee_id=old.id, effective_year=2026, effective_quarter=3,
                                involvement=0.5),
        EmployeePersonalSetting(employee_id=old.id, effective_year=2026, effective_quarter=4,
                                involvement=0.5),
        EmployeePersonalSetting(employee_id=new.id, effective_year=2026, effective_quarter=4,
                                involvement=0.8),
    ])
    db.flush()
    old_id, new_id = old.id, new.id

    preview = employee_merge.preview(db, new_id, old_id)
    assert preview["blockers"] == []
    assert {"label": "Списания", "count": 2} in preview["moves"]

    employee_merge.merge(db, new_id, old_id)
    db.commit()

    assert db.get(Employee, old_id) is None
    assert db.query(Worklog).filter(Worklog.employee_id == new_id).count() == 3
    team = db.query(EmployeeTeam).one()
    assert (team.employee_id, team.is_primary) == (new_id, True)
    kept = db.get(Employee, new_id)
    assert (kept.role, kept.team) == ("consultant", "Товарный учёт")
    # Своя запись правильной карточки на тот же квартал главнее.
    settings = {
        s.effective_quarter: s.involvement
        for s in db.query(EmployeePersonalSetting).filter_by(employee_id=new_id)
    }
    assert settings == {3: 0.5, 4: 0.8}
    db.refresh(issue)
    assert issue.assignee_account_id == "JIRAUSER12022"
    assert issue.developer_account_id == "JIRAUSER12022"
    alias = db.query(EmployeeAccountAlias).one()
    assert (alias.jira_account_id, alias.employee_id) == ("JIRAUSER13143", new_id)


def test_no_row_points_to_merged_card(db_session):
    """Новая таблица со ссылкой на сотрудника без правки объединения — тест падает."""
    db = db_session
    old, new, _ = _people(db)
    old_id = old.id
    employee_merge.merge(db, new.id, old_id)
    db.commit()
    plain = {(m.__tablename__, c) for m, c, _ in employee_merge._PLAIN_COLUMNS}
    scoped = {m.__tablename__ for m, _, _ in employee_merge._SCOPED}
    handled = {"employee_teams", "employee_subgroup_shares", "employee_account_aliases"}
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if any(fk.column.table.name == "employees" for fk in col.foreign_keys):
                assert (table.name, col.name) in plain or table.name in scoped | handled, (
                    f"{table.name}.{col.name} ссылается на сотрудника, а объединение его не переносит"
                )
            if col.foreign_keys or not col.name.endswith("employee_id"):
                continue
            assert (table.name, col.name) in plain, f"{table.name}.{col.name} не переносится"
        if "employee_id" in table.columns:
            assert db.execute(
                table.select().where(table.c.employee_id == old_id)
            ).first() is None


def test_overlapping_membership_in_same_team_is_refused(db_session):
    db = db_session
    old, new, _ = _people(db)
    db.add(EmployeeTeam(employee_id=new.id, team="Товарный учёт", is_primary=True,
                        joined_at=date(2026, 10, 9)))
    db.flush()
    assert employee_merge.preview(db, new.id, old.id)["blockers"]
    with pytest.raises(MergeError, match="Товарный учёт"):
        employee_merge.merge(db, new.id, old.id)


def test_sync_resolves_merged_account(db_session):
    """Старая учётка в авторах и исполнителях — правильный сотрудник, двойник не заводится."""
    from app.connectors.schemas import JiraUserSchema

    db = db_session
    old, new, _ = _people(db)
    new_id = new.id
    employee_merge.merge(db, new_id, old.id)
    db.commit()

    sync = SyncService(db, jira_client=None)
    employee = sync._ensure_employee(JiraUserSchema(
        key="JIRAUSER13143", name="medvedeva-n", displayName="Медведева Надежда Владимировна",
    ))
    assert employee.id == new_id
    assert employee.jira_username == "Medvedeva_N_V"
    assert sync._canonical_account("JIRAUSER13143") == "JIRAUSER12022"
    assert sync._canonical_account("JIRAUSER99999") == "JIRAUSER99999"
    assert db.query(Employee).count() == 1


def test_suggestions_group_same_name_with_freshest_first(db_session):
    db = db_session
    _people(db)
    db.add(Employee(jira_account_id="x", display_name="Иванов Иван"))
    reversed_name = Employee(jira_account_id="y", jira_username="nadezhda-rp",
                             display_name="Надежда Медведева РП")
    db.add(reversed_name)
    db.flush()
    db.add(EmployeeTeam(employee_id=reversed_name.id, team="Завод"))
    db.flush()
    groups = employee_merge.suggestions(db)
    assert len(groups) == 1
    assert [c["jira_username"] for c in groups[0]["cards"]][:2] == ["Medvedeva_N_V", "medvedeva-n"]
    assert "nadezhda-rp" in [c["jira_username"] for c in groups[0]["cards"]]
