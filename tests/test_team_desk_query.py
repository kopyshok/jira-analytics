"""Срез задач рабочего стола тимлида."""
import uuid
from datetime import datetime, timedelta

from app.models import Employee, Issue, Project, Worklog
from app.services.team_desk.query import build_overview


def _project(db_session) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        jira_project_id=str(uuid.uuid4()),
        key=f"OS{uuid.uuid4().hex[:4]}",
        name="OS",
    )
    db_session.add(project)
    db_session.flush()
    return project


def _issue(db_session, project, key, **kw) -> Issue:
    row = Issue(
        id=str(uuid.uuid4()),
        jira_issue_id=str(uuid.uuid4()),
        key=key,
        summary=kw.pop("summary", key),
        issue_type=kw.pop("issue_type", "Задача"),
        status=kw.pop("status", "В РАБОТЕ"),
        project_id=project.id,
        **kw,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _employee(db_session, account_id, name) -> Employee:
    emp = Employee(
        id=str(uuid.uuid4()),
        jira_account_id=account_id,
        display_name=name,
    )
    db_session.add(emp)
    db_session.flush()
    return emp


def test_issue_has_developer_and_dev_estimate(db_session):
    project = _project(db_session)
    _issue(
        db_session, project, "OS-1",
        developer_account_id="acc-1",
        developer_display_name="Шутов Сергей",
        dev_est_hours=16.0,
    )
    db_session.commit()

    loaded = db_session.query(Issue).filter_by(key="OS-1").one()
    assert loaded.developer_display_name == "Шутов Сергей"
    assert loaded.developer_account_id == "acc-1"
    assert loaded.dev_est_hours == 16.0


def test_overview_groups_issues_by_developer(db_session):
    project = _project(db_session)
    emp = _employee(db_session, "acc-1", "Шутов Сергей")
    issue = _issue(
        db_session, project, "OS-1",
        developer_account_id="acc-1",
        developer_display_name="Шутов Сергей",
        dev_est_hours=6.0,
        status_changed_at=datetime.utcnow() - timedelta(days=9),
    )
    db_session.add(
        Worklog(
            id=str(uuid.uuid4()),
            jira_worklog_id=str(uuid.uuid4()),
            issue_id=issue.id,
            employee_id=emp.id,
            hours=9.0,
            time_spent_seconds=9 * 3600,
            started_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    result = build_overview(db_session, developer_ids=["acc-1"])

    assert len(result["developers"]) == 1
    dev = result["developers"][0]
    assert dev["display_name"] == "Шутов Сергей"
    assert dev["total_issues"] == 1
    assert dev["in_dev"] == 1
    assert dev["fact_hours"] == 9.0
    assert dev["est_hours"] == 6.0

    row = result["issues"][0]
    assert row["key"] == "OS-1"
    assert "over" in row["flags"]
    assert "stale" in row["flags"]
    assert row["fact_by_person"] == [{"name": "Шутов Сергей", "hours": 9.0}]


def test_subtask_does_not_double_count(db_session):
    """Подзадача — декомпозиция: её оценка живёт в родителе, счётчик не растёт."""
    project = _project(db_session)
    emp = _employee(db_session, "acc-1", "Шутов Сергей")
    parent = _issue(
        db_session, project, "OS-10",
        developer_account_id="acc-1",
        developer_display_name="Шутов Сергей",
        dev_est_hours=40.0,
    )
    child = _issue(
        db_session, project, "OS-11",
        issue_type="Подзадача",
        parent_id=parent.id,
        developer_account_id="acc-1",
        developer_display_name="Шутов Сергей",
        dev_est_hours=8.0,
    )
    # Часы списаны в подзадачу — факт всё равно должен приехать к родителю.
    db_session.add(
        Worklog(
            id=str(uuid.uuid4()),
            jira_worklog_id=str(uuid.uuid4()),
            issue_id=child.id,
            employee_id=emp.id,
            hours=5.0,
            time_spent_seconds=5 * 3600,
            started_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    result = build_overview(db_session, developer_ids=["acc-1"])
    dev = result["developers"][0]
    assert dev["total_issues"] == 1
    assert dev["est_hours"] == 40.0
    assert dev["fact_hours"] == 5.0

    rows = {r["key"]: r for r in result["issues"]}
    assert rows["OS-10"]["is_standalone"] is True
    assert rows["OS-10"]["fact_hours"] == 5.0
    assert rows["OS-10"]["fact_by_person"] == [{"name": "Шутов Сергей", "hours": 5.0}]
    assert rows["OS-11"]["is_standalone"] is False
    # у родителя одна подзадача на 8 ч против оценки 40 ч
    assert "childgap" in rows["OS-10"]["flags"]
    assert "decomp" not in rows["OS-10"]["flags"]


def test_subtask_without_parent_in_slice_is_an_error(db_session):
    """Родителя в срезе нет — связь порвана: подзадача считается сама и подсвечена."""
    project = _project(db_session)
    parent = _issue(
        db_session, project, "OS-20", status="ГОТОВО",
        developer_account_id="acc-9",
        developer_display_name="Другой человек",
        dev_est_hours=40.0,
    )
    _issue(
        db_session, project, "OS-21",
        issue_type="Подзадача",
        parent_id=parent.id,
        developer_account_id="acc-1",
        developer_display_name="Шутов Сергей",
        dev_est_hours=8.0,
    )
    db_session.commit()

    result = build_overview(db_session, developer_ids=["acc-1"])
    row = result["issues"][0]

    assert row["key"] == "OS-21"
    assert row["is_standalone"] is True
    assert "orphan" in row["flags"]
    assert result["developers"][0]["total_issues"] == 1
    assert result["developers"][0]["est_hours"] == 8.0


def test_research_issue_taken_by_assignee(db_session):
    project = _project(db_session)
    _issue(
        db_session, project, "OS-20",
        issue_type="Research",
        assignee_account_id="acc-1",
        assignee_display_name="Шутов Сергей",
    )
    db_session.commit()

    result = build_overview(db_session, developer_ids=["acc-1"])
    row = result["issues"][0]

    assert row["is_analysis"] is True
    assert row["developer_name"] == "Шутов Сергей"
    assert "noest" not in row["flags"]


def test_closed_issues_hidden_when_only_open(db_session):
    project = _project(db_session)
    _issue(
        db_session, project, "OS-30", status="ГОТОВО",
        developer_account_id="acc-1", developer_display_name="Шутов Сергей",
        dev_est_hours=4.0,
    )
    db_session.commit()

    assert build_overview(db_session, developer_ids=["acc-1"])["issues"] == []
    full = build_overview(db_session, developer_ids=["acc-1"], only_open=False)
    assert len(full["issues"]) == 1


def test_hidden_statuses_are_not_shown(db_session):
    """Backlog по умолчанию не показывается: задача ещё не взята в работу."""
    project = _project(db_session)
    _issue(
        db_session, project, "OS-50", status="Backlog",
        developer_account_id="acc-1", developer_display_name="Шутов Сергей",
        dev_est_hours=8.0,
    )
    _issue(
        db_session, project, "OS-51", status="К выполнению",
        developer_account_id="acc-1", developer_display_name="Шутов Сергей",
        dev_est_hours=4.0,
    )
    db_session.commit()

    # ни в «открытых сейчас», ни во «всех задачах»
    for only_open in (True, False):
        result = build_overview(db_session, ["acc-1"], only_open=only_open)
        assert [i["key"] for i in result["issues"]] == ["OS-51"]
        assert result["developers"][0]["total_issues"] == 1


def test_reviewed_flag_hidden_until_asked(db_session, seed_user):
    from app.services.team_desk.marks import mark_reviewed

    project = _project(db_session)
    issue = _issue(
        db_session, project, "OS-40",
        developer_account_id="acc-1", developer_display_name="Шутов Сергей",
        dev_est_hours=6.0,
        status_changed_at=datetime.utcnow() - timedelta(days=9),
    )
    db_session.commit()
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment="согласовано", user_id=seed_user.id)

    # Переключатель выключен — признака нет ни в проблемных, ни в просмотренных:
    # приглушённый значок на экране означал бы «показывать просмотренные».
    hidden = build_overview(db_session, developer_ids=["acc-1"])["issues"][0]
    assert "stale" not in hidden["flags"]
    assert hidden["reviewed"] == []

    shown = build_overview(db_session, developer_ids=["acc-1"], show_reviewed=True)
    assert "stale" in shown["issues"][0]["flags"]
    assert shown["issues"][0]["reviewed"][0]["comment"] == "согласовано"
