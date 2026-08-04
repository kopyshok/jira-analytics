"""Отчёт возвращает людей команды с метриками и итогом, учитывая период участия."""
import json
from datetime import date, datetime

from app.services.kpi.kpi_service import build_report


def _profile_for_role(db_session, role_code="analyst", code="test", **kwargs):
    """Профиль, привязанный к роли — без привязки сотрудник в отчёт не попадает."""
    from app.models.kpi import KpiProfile, KpiProfileRole

    profile = KpiProfile(code=code, name=kwargs.pop("name", "Тест"), is_enabled=True,
                         target_pct=kwargs.pop("target_pct", 80.0), **kwargs)
    db_session.add(profile)
    db_session.commit()
    db_session.add(KpiProfileRole(profile_id=profile.id, role_code=role_code))
    db_session.commit()
    return profile


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
    _profile_for_role(db_session)

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    assert [r["employee_name"] for r in report["rows"]] == ["Иванов И."]
    assert "metrics" in report["rows"][0]


def test_employee_in_two_teams_not_duplicated(db_session):
    """ВАЖНО 9: сотрудник, состоящий в двух командах, не задваивается в отчёте на обе."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                   role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Другая команда", is_primary=False,
                                joined_at=date(2026, 1, 1)))
    db_session.commit()
    _profile_for_role(db_session)

    report = build_report(db_session, teams=["Платежи", "Другая команда"], year=2026, month=7)
    assert len(report["rows"]) == 1


def test_mid_month_joiner_excludes_tasks_before_join(db_session, sample_project):
    """ВАЖНО 9: задачи, закрытые до даты вступления в команду, не считаются."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.issue import Issue
    from app.models.kpi import KpiMetric, KpiProfileMetric

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                   role="analyst")
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
    db_session.add(metric)
    db_session.commit()
    profile = _profile_for_role(db_session)
    db_session.add(KpiProfileMetric(profile_id=profile.id, metric_id=metric.id, weight=1.0))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    row = report["rows"][0]
    assert row["metrics"][0]["denominator"] == 1


def test_profile_covers_several_roles(db_session):
    """Один профиль оценивает и аналитиков, и руководителей проектов."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.kpi import KpiProfileRole

    analyst = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                       role="analyst")
    manager = Employee(jira_account_id="acc-2", display_name="Петров П.", team="Платежи",
                       role="RP")
    db_session.add_all([analyst, manager])
    db_session.commit()
    for emp in (analyst, manager):
        db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                    joined_at=date(2026, 1, 1)))
    db_session.commit()
    profile = _profile_for_role(db_session, code="analyst", name="Аналитик")
    db_session.add(KpiProfileRole(profile_id=profile.id, role_code="RP"))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    assert {r["profile_code"] for r in report["rows"]} == {"analyst"}
    assert len(report["rows"]) == 2


def test_employee_with_unmatched_role_not_in_report(db_session):
    """Роль не привязана ни к одному профилю — сотрудника в ведомости нет вообще.

    Раньше его подхватывал профиль «по умолчанию», из-за чего в ведомость
    попадали программисты и тестировщики (спека доработок, раздел 2).
    """
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam

    analyst = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                       role="analyst")
    developer = Employee(jira_account_id="acc-2", display_name="Петров П.", team="Платежи",
                         role="dev")
    no_role = Employee(jira_account_id="acc-3", display_name="Сидоров С.", team="Платежи")
    db_session.add_all([analyst, developer, no_role])
    db_session.commit()
    for emp in (analyst, developer, no_role):
        db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                    joined_at=date(2026, 1, 1)))
    db_session.commit()
    _profile_for_role(db_session)

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    assert [r["employee_name"] for r in report["rows"]] == ["Иванов И."]
    # Молча терять людей нельзя — отсеявшиеся отдаются поимённо, с ролью:
    # по одному числу руководитель не поймёт, кого именно он не видит.
    assert report["skipped_no_profile"] == 2
    skipped = {s["employee_name"]: s for s in report["skipped"]}
    assert set(skipped) == {"Петров П.", "Сидоров С."}
    assert skipped["Петров П."]["role_code"] == "dev"
    assert skipped["Сидоров С."]["role_label"] == "Роль не заполнена"


def test_cycle_time_norm_uses_team_at_period_start_not_current_team(db_session, sample_project):
    """BLOCKER ВАЖНО 3: норматив берётся по основной команде на начало периода, не по Employee.team «на сегодня»."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.issue import Issue
    from app.models.kpi import KpiCycleTimeNorm, KpiMetric, KpiProfileMetric

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
    db_session.add(metric)
    db_session.commit()
    profile = _profile_for_role(db_session, code="analyst", name="Аналитик")
    db_session.add(KpiProfileMetric(profile_id=profile.id, metric_id=metric.id, weight=1.0))
    # Норматив заведён на историческую команду «Платежи», не на «Digital».
    db_session.add(KpiCycleTimeNorm(team="Платежи", year=2026, quarter=2, norm_value=70.0))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=5)
    row = report["rows"][0]
    assert row["metrics"][0]["has_data"] is True
    assert round(row["metrics"][0]["value"], 1) == 100.0
    # ВАЖНО 5: строка отчёта помечена исторической командой периода, а не
    # «сегодняшней» Employee.team — иначе сотрудник группировался бы под
    # чужой командой (или вовсе без команды) в ведомости.
    assert row["team"] == "Платежи"


def test_report_row_team_falls_back_when_no_membership_matches_filter(db_session):
    """Сотрудник без исторического участия ни в одной из запрошенных команд —
    строка помечена его текущей Employee.team, а не падает с ошибкой."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                   role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.commit()
    _profile_for_role(db_session)

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    assert report["rows"][0]["team"] == "Платежи"
