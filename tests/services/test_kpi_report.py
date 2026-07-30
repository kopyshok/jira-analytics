"""Отчёт возвращает людей команды с метриками и итогом, учитывая период участия."""
from datetime import date

from app.services.kpi.kpi_service import build_report


def test_report_lists_only_team_members(db_session):
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                   role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    assert [r["employee_name"] for r in report["rows"]] == ["Иванов И."]
    assert "metrics" in report["rows"][0]
