"""Предпросмотр метрики: воронка отбора и проверка конкретной задачи."""
import json
from datetime import date, datetime

from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.kpi import KpiMetric
from app.services.kpi.preview import explain_issue, preview_metric

CALENDAR_BUFFER_DAYS = 7


def _metric() -> KpiMetric:
    cond = json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [
            {"attr": "issue_type", "op": "in", "value": ["Баг"]},
            {"attr": "environment", "op": "in", "value": ["PROD"]},
        ],
    })
    den = json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [{"attr": "issue_type", "op": "in", "value": ["Задача", "Баг"]}],
    })
    return KpiMetric(
        code="quality_preview", name="Качество выпуска", calc_kind="ratio",
        invert=True, cap_at_100=True, numerator_json=cond, denominator_json=den,
    )


def _setup(db_session, sample_project):
    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                   role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.add_all([
        # Баг на проде — попадает в числитель.
        Issue(jira_issue_id="p1", key="OS-1", summary="баг прод", issue_type="Баг",
              environment="PROD", status="ГОТОВО", resolution="Done",
              resolved_at=datetime(2026, 7, 10), project_id=sample_project.id,
              reporter_account_id="acc-1", team="Платежи"),
        # Баг на тесте — отсеивается шагом «Окружение».
        Issue(jira_issue_id="p2", key="OS-2", summary="баг тест", issue_type="Баг",
              environment="TEST", status="ГОТОВО", resolution="Done",
              resolved_at=datetime(2026, 7, 11), project_id=sample_project.id,
              reporter_account_id="acc-1", team="Платежи"),
        # Задача — только в знаменателе.
        Issue(jira_issue_id="p3", key="OS-3", summary="задача", issue_type="Задача",
              status="ГОТОВО", resolution="Done", resolved_at=datetime(2026, 7, 12),
              project_id=sample_project.id, reporter_account_id="acc-1", team="Платежи"),
    ])
    db_session.commit()
    return emp


def test_funnel_shows_where_issues_are_dropped(db_session, sample_project):
    _setup(db_session, sample_project)

    result = preview_metric(
        db_session, _metric(), team="Платежи", year=2026, month=7, account_id=None,
        direction=None, base_url="https://jira.example", calendar_buffer_days=CALENDAR_BUFFER_DAYS,
    )
    funnel = result["numerator_funnel"]
    assert funnel[0]["remaining"] == 3
    # Шаг «Тип задачи» оставляет два бага, «Окружение» — один.
    assert [s["remaining"] for s in funnel][1:3] == [2, 1]
    # Сумма отсеянного сходится с исходным числом.
    dropped = sum(s["dropped"] or 0 for s in funnel)
    assert funnel[0]["remaining"] - funnel[-1]["remaining"] == dropped
    assert result["rows"][0]["numerator"] == 1
    assert result["rows"][0]["denominator"] == 3


def test_preview_narrowed_to_one_employee_returns_task_lists(db_session, sample_project):
    _setup(db_session, sample_project)

    result = preview_metric(
        db_session, _metric(), team="Платежи", year=2026, month=7, account_id="acc-1",
        direction=None, base_url="https://jira.example", calendar_buffer_days=CALENDAR_BUFFER_DAYS,
    )
    assert [i["key"] for i in result["items"]["numerator"]] == ["OS-1"]
    assert result["items"]["denominator_count"] == 3
    assert result["items"]["numerator"][0]["url"] == "https://jira.example/browse/OS-1"


def test_explain_issue_names_the_step_that_dropped_it(db_session, sample_project):
    _setup(db_session, sample_project)

    result = explain_issue(
        db_session, _metric(), side="numerator", issue_key="OS-2", team="Платежи",
        year=2026, month=7, account_id="acc-1", direction=None,
        calendar_buffer_days=CALENDAR_BUFFER_DAYS,
    )
    assert result["found"] is True
    assert result["passed"] is False
    assert "Окружение" in result["failed_step"]


def test_explain_issue_confirms_a_matching_task(db_session, sample_project):
    _setup(db_session, sample_project)

    result = explain_issue(
        db_session, _metric(), side="numerator", issue_key="os-1", team="Платежи",
        year=2026, month=7, account_id="acc-1", direction=None,
        calendar_buffer_days=CALENDAR_BUFFER_DAYS,
    )
    assert result["passed"] is True
    assert result["failed_step"] is None


def test_explain_unknown_issue_key(db_session, sample_project):
    _setup(db_session, sample_project)

    result = explain_issue(
        db_session, _metric(), side="numerator", issue_key="OS-999", team="Платежи",
        year=2026, month=7, account_id="acc-1", direction=None,
        calendar_buffer_days=CALENDAR_BUFFER_DAYS,
    )
    assert result["found"] is False
