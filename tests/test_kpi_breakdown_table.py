"""Таблица разбора показателя: строка на задачу, колонка на требование метрики.

Смысл раздела в том, чтобы руководитель видел не «18 из 19», а какая именно
задача не зачлась и почему. Поэтому проверяется не только число строк, но и
формулировки: колонки названы полями Jira, а не именами полей базы, и у метрики
с инверсией проблемной считается попавшая в числитель задача, а не выпавшая.
"""
from datetime import date, datetime

from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.issue_link import IssueLink
from app.models.kpi import KpiMetric
from app.models.project import Project
from app.models.worklog import Worklog
from app.services.kpi.breakdown_table import build_table
from app.services.kpi.seed import seed_defaults

TEAM = "Платежи"
ACCOUNT_ID = "acc-table"
BASE_URL = "https://jira.example.com"


def _setup(db):
    seed_defaults(db)
    project = Project(jira_project_id="p-1", key="OS", name="1С")
    emp = Employee(jira_account_id=ACCOUNT_ID, display_name="Аналитик", team=TEAM, role="analyst")
    db.add_all([project, emp])
    db.commit()
    db.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True,
                        joined_at=date(2026, 1, 1)))
    db.commit()
    return project, emp


def _issue(db, project, jid, key, **kw):
    defaults = dict(
        jira_issue_id=jid, key=key, summary="Задача", issue_type="Задача",
        status="ГОТОВО", status_category="done", project_id=project.id, team=TEAM,
        resolution="Done", resolved_at=datetime(2026, 7, 10),
        jira_created_at=datetime(2026, 7, 1),
        reporter_account_id=ACCOUNT_ID,
        goal_text="цель", current_behavior="как сейчас", description="описание",
    )
    defaults.update(kw)
    issue = Issue(**defaults)
    db.add(issue)
    db.commit()
    return issue


def _metric(db, code):
    return db.query(KpiMetric).filter(KpiMetric.code == code).first()


def test_unfilled_field_shows_as_failed_column_on_its_own_row(db_session):
    """Задача с пустым полем — строка с проблемой, колонка называет само поле."""
    project, _ = _setup(db_session)
    _issue(db_session, project, "i-1", "OS-1")
    _issue(db_session, project, "i-2", "OS-2", goal_text=None, current_behavior="   ")

    table = build_table(
        db_session, _metric(db_session, "regulations"), ACCOUNT_ID, 2026, 7, [TEAM], BASE_URL,
    )

    assert table["kind"] == "checks"
    assert [c["label"] for c in table["checks"]] == [
        "Цель задачи", "Описание текущего поведения", "Описание",
    ]
    assert (table["total_count"], table["counted_count"], table["problem_count"]) == (2, 1, 1)

    failed = next(r for r in table["rows"] if r["key"] == "OS-2")
    assert failed["problem"] is True
    assert failed["reasons"] == ["Цель задачи", "Описание текущего поведения"]
    assert failed["checks"] == dict(zip(
        [c["code"] for c in table["checks"]], [False, False, True],
    ))
    assert next(r for r in table["rows"] if r["key"] == "OS-1")["counted"] is True
    # Проблемная строка идёт первой — руководителю не нужно её искать.
    assert table["rows"][0]["key"] == "OS-2"


def test_cancelled_issue_is_listed_as_dropped_before_comparison(db_session):
    """Задача с исключённым статусом не пропадает молча — она в списке отсеянных."""
    project, _ = _setup(db_session)
    _issue(db_session, project, "i-1", "OS-1")
    _issue(db_session, project, "i-2", "OS-2", status="Отменено", resolution="Won't Do")

    table = build_table(
        db_session, _metric(db_session, "regulations"), ACCOUNT_ID, 2026, 7, [TEAM], BASE_URL,
    )

    assert table["total_count"] == 1
    assert [(d["key"], d["reason"]) for d in table["dropped"]] == [("OS-2", "статус «Отменено»")]
    assert table["dropped"][0]["url"] == f"{BASE_URL}/browse/OS-2"


def test_inverted_metric_marks_numerator_row_as_the_problem(db_session):
    """У качества выпуска числитель — баги: проблемная строка та, что в него попала."""
    project, _ = _setup(db_session)
    released = _issue(db_session, project, "i-1", "OS-1")
    bug = _issue(
        db_session, project, "i-2", "OS-2", issue_type="Баг", environment="PROD",
        reporter_account_id="acc-other",
    )
    # Баг ссылается на задачу сотрудника: метрика считает баги, связанные с
    # задачами оцениваемого человека (условие «автор связанной задачи»).
    db_session.add(IssueLink(source_issue_id=bug.id, target_issue_id=released.id,
                             link_type="relates"))
    db_session.commit()

    table = build_table(
        db_session, _metric(db_session, "quality"), ACCOUNT_ID, 2026, 7, [TEAM], BASE_URL,
    )

    assert table["invert"] is True
    problems = [r["key"] for r in table["rows"] if r["problem"]]
    assert problems == ["OS-2"]
    assert next(r for r in table["rows"] if r["key"] == "OS-1")["reasons"] == []


def test_worklog_without_fill_date_explains_why_metric_is_empty(db_session):
    """Записи без даты внесения расчёт не судит — таблица показывает их отдельно."""
    project, emp = _setup(db_session)
    issue = _issue(db_session, project, "i-1", "OS-1")
    db_session.add_all([
        Worklog(jira_worklog_id="w-1", issue_id=issue.id, employee_id=emp.id, hours=2.0,
                time_spent_seconds=7200,
                started_at=datetime(2026, 7, 6, 9, 0), jira_created_at=datetime(2026, 7, 6, 18, 0)),
        Worklog(jira_worklog_id="w-2", issue_id=issue.id, employee_id=emp.id, hours=1.0,
                time_spent_seconds=3600,
                started_at=datetime(2026, 7, 7, 9, 0), jira_created_at=datetime(2026, 7, 20, 9, 0)),
        Worklog(jira_worklog_id="w-3", issue_id=issue.id, employee_id=emp.id, hours=3.0,
                time_spent_seconds=10800,
                started_at=datetime(2026, 7, 8, 9, 0), jira_created_at=None),
    ])
    db_session.commit()

    table = build_table(
        db_session, _metric(db_session, "worklog_timeliness"), ACCOUNT_ID, 2026, 7, [TEAM],
        BASE_URL,
    )

    assert table["kind"] == "worklogs"
    assert (table["total_count"], table["counted_count"], table["problem_count"]) == (2, 1, 1)
    late = table["rows"][0]
    assert late["problem"] is True and late["delay_hours"] == 312.0
    assert [d["reason"] for d in table["dropped"]] == ["нет даты внесения записи"]
