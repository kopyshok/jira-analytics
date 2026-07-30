"""Отчёт возвращает людей команды с метриками и итогом, учитывая период участия."""
import json
from datetime import date, datetime

from app.services.kpi.kpi_service import build_report


def test_report_excludes_employees_not_in_team(db_session):
    """Раньше называлось «только участники команды», но в базе был один
    сотрудник и он же в команде — по заявленной причине провалиться не мог.
    Теперь есть второй сотрудник в другой команде — отсев проверяется реально."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam

    member = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                      role="analyst")
    outsider = Employee(jira_account_id="acc-2", display_name="Петров П.", team="Другая команда",
                        role="analyst")
    db_session.add_all([member, outsider])
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=member.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.add(EmployeeTeam(employee_id=outsider.id, team="Другая команда", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    assert [r["employee_name"] for r in report["rows"]] == ["Иванов И."]
    assert "metrics" in report["rows"][0]


def test_employee_in_two_teams_not_duplicated(db_session):
    """ВАЖНО 9: сотрудник, состоящий в двух командах, не задваивается в отчёте на обе."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Другая команда", is_primary=False,
                                joined_at=date(2026, 1, 1)))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи", "Другая команда"], year=2026, month=7)
    assert len(report["rows"]) == 1


def test_mid_month_joiner_excludes_tasks_before_join(db_session, sample_project):
    """ВАЖНО 9: задачи, закрытые до даты вступления в команду, не считаются."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.issue import Issue
    from app.models.kpi import KpiMetric, KpiProfile, KpiProfileMetric

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 7, 15)))

    db_session.add(Issue(
        jira_issue_id="m1", key="OS-500", summary="s", issue_type="Задача",
        status="ГОТОВО", resolution="Готово", resolved_at=datetime(2026, 7, 5),
        project_id=sample_project.id, reporter_account_id="acc-1", team="Платежи",
    ))
    db_session.add(Issue(
        jira_issue_id="m2", key="OS-501", summary="s", issue_type="Задача",
        status="ГОТОВО", resolution="Готово", resolved_at=datetime(2026, 7, 20),
        project_id=sample_project.id, reporter_account_id="acc-1", team="Платежи",
    ))
    db_session.commit()

    cond = json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [{"attr": "issue_type", "op": "in", "value": ["Задача"]}],
    })
    metric = KpiMetric(
        code="count_check", name="Проверка счёта", calc_kind="ratio",
        invert=False, cap_at_100=True, numerator_json=cond, denominator_json=cond,
    )
    profile = KpiProfile(code="test", name="Тест", is_default=True, is_enabled=True, target_pct=80.0)
    db_session.add_all([metric, profile])
    db_session.commit()
    db_session.add(KpiProfileMetric(profile_id=profile.id, metric_id=metric.id, weight=1.0))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    row = report["rows"][0]
    assert row["metrics"][0]["denominator"] == 1


def test_default_profile_used_when_role_unmatched(db_session):
    """ВАЖНО 7: без совпадения по роли подставляется явный профиль по умолчанию, не первый попавшийся."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.kpi import KpiProfile

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                   role="project_manager")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.add(KpiProfile(code="analyst", name="Аналитик", role_code="analyst",
                              is_default=True, is_enabled=True, target_pct=80.0))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    assert report["rows"][0]["profile_code"] == "analyst"


def test_no_default_profile_gives_empty_metrics_row_not_arbitrary_profile(db_session):
    """ВАЖНО 7: без совпадения по роли и без профиля по умолчанию — пустой список метрик, не случайный профиль."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.kpi import KpiProfile

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                   role="project_manager")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    # Профиль есть, но не подходит по роли и не является профилем по умолчанию.
    db_session.add(KpiProfile(code="analyst", name="Аналитик", role_code="analyst",
                              is_default=False, is_enabled=True, target_pct=80.0))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    row = report["rows"][0]
    assert row["profile_code"] is None
    assert row["metrics"] == []


def test_cycle_time_norm_uses_team_at_period_start_not_current_team(db_session, sample_project):
    """BLOCKER ВАЖНО 3: норматив берётся по основной команде на начало периода, не по Employee.team «на сегодня»."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.issue import Issue
    from app.models.kpi import KpiCycleTimeNorm, KpiMetric, KpiProfile, KpiProfileMetric

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Digital", role="analyst")
    db_session.add(emp)
    db_session.commit()
    # В мае — «Платежи», с 1 июня переведён в «Digital» (эта команда и
    # осталась денормализованной в Employee.team — «сегодняшняя»).
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1), left_at=date(2026, 6, 1)))
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Digital", is_primary=True,
                                joined_at=date(2026, 6, 1)))
    db_session.commit()

    db_session.add(Issue(
        jira_issue_id="ct-h", key="OS-600", summary="s", issue_type="ИТ-задача",
        status="ГОТОВО", resolution="Готово", subtype="RFC_STANDARD", cost_type="Change",
        cycle_time_fact=70.0, resolved_at=datetime(2026, 5, 15),
        project_id=sample_project.id, assignee_account_id="acc-1", team="Платежи",
    ))
    db_session.commit()

    metric = KpiMetric(
        code="cycle_time", name="Cycle Time", calc_kind="norm_to_fact",
        invert=False, cap_at_100=True,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "assignee", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["ИТ-задача"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
            ],
        }),
    )
    profile = KpiProfile(code="analyst", name="Аналитик", role_code="analyst",
                         is_default=True, is_enabled=True, target_pct=80.0)
    db_session.add_all([metric, profile])
    db_session.commit()
    db_session.add(KpiProfileMetric(profile_id=profile.id, metric_id=metric.id, weight=1.0))
    # Норматив заведён на историческую команду «Платежи», не на «Digital».
    db_session.add(KpiCycleTimeNorm(team="Платежи", year=2026, quarter=2, norm_value=70.0))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=5)
    row = report["rows"][0]
    assert row["metrics"][0]["has_data"] is True
    assert round(row["metrics"][0]["value"], 1) == 100.0
