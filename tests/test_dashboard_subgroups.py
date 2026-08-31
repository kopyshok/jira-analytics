"""Дашборд и Аналитика в разрезе групп внутри команды.

Главное, что проверяем: сумма по группам сходится с показателем команды,
а часы разработчика из соседней группы остаются у группы-заказчика.
"""

from datetime import date, datetime

import pytest

from app.models import (
    Category,
    Employee,
    EmployeeTeam,
    Issue,
    Project,
    Team,
    TeamSubgroup,
    Worklog,
)
from app.services.analytics_service import AnalyticsService
from app.services.subgroup_filter import NO_SUBGROUP_TOKEN
from app.services.subgroup_resolver import SubgroupResolver

TEAM = "Команда 1С (Бухгалтерия)"
YEAR, QUARTER = 2026, 3
DAY = datetime(2026, 8, 5, 10, 0)


@pytest.fixture
def data(db_session):
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    db_session.add(Category(code="development", label="Разработка", color="#123456"))
    team = Team(name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    db_session.flush()

    # Разработчик группы «Расчёты» и разработчик группы «Интеграции».
    a = Employee(jira_account_id="acc-a", display_name="Алексеев", is_active=True, role="dev")
    b = Employee(jira_account_id="acc-b", display_name="Борисов", is_active=True, role="dev")
    db_session.add_all([a, b])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(
            employee_id=a.id, team=TEAM, is_primary=True, subgroup_id=calc.id,
            joined_at=date(2020, 1, 1),
        ),
        EmployeeTeam(
            employee_id=b.id, team=TEAM, is_primary=True, subgroup_id=integ.id,
            joined_at=date(2020, 1, 1),
        ),
    ])

    def issue(key, subgroup):
        it = Issue(
            jira_issue_id=key, key=key, summary=key, issue_type="Task",
            status="Open", project_id="p1", team=TEAM, category="development",
            assigned_subgroup_id=subgroup.id if subgroup else None,
        )
        db_session.add(it)
        return it

    calc_issue = issue("OS-1", calc)
    integ_issue = issue("OS-2", integ)
    loose_issue = issue("OS-3", None)
    db_session.flush()

    # 5 ч своей группы, 3 ч перетока (человек «Расчётов» на задаче «Интеграций»),
    # 2 ч на задаче без группы.
    db_session.add_all([
        Worklog(jira_worklog_id="w1", issue_id=calc_issue.id, employee_id=a.id,
                started_at=DAY, time_spent_seconds=5 * 3600, hours=5.0),
        Worklog(jira_worklog_id="w2", issue_id=integ_issue.id, employee_id=a.id,
                started_at=DAY, time_spent_seconds=3 * 3600, hours=3.0),
        Worklog(jira_worklog_id="w3", issue_id=loose_issue.id, employee_id=b.id,
                started_at=DAY, time_spent_seconds=2 * 3600, hours=2.0),
    ])
    db_session.commit()
    SubgroupResolver(db_session).recompute_effective()
    return {"calc": calc, "integ": integ, "a": a, "b": b}


def _hours(resp) -> float:
    return round(sum(i.hours for i in resp.items), 2)


def test_categories_sum_over_groups_equals_team(db_session, data):
    svc = AnalyticsService(db_session)
    whole = svc.get_dashboard_categories(year=YEAR, quarter=QUARTER, teams=[TEAM])

    parts = sum(
        _hours(
            svc.get_dashboard_categories(
                year=YEAR, quarter=QUARTER, teams=[TEAM], subgroups=[g]
            )
        )
        for g in [data["calc"].id, data["integ"].id, NO_SUBGROUP_TOKEN]
    )

    assert _hours(whole) == 10.0
    assert round(parts, 2) == _hours(whole)


def test_fact_follows_issue_group_not_employee(db_session, data):
    """Часы «чужака» видны у группы-заказчика."""
    svc = AnalyticsService(db_session)

    calc_hours = _hours(
        svc.get_dashboard_categories(
            year=YEAR, quarter=QUARTER, teams=[TEAM], subgroups=[data["calc"].id]
        )
    )
    integ_hours = _hours(
        svc.get_dashboard_categories(
            year=YEAR, quarter=QUARTER, teams=[TEAM], subgroups=[data["integ"].id]
        )
    )

    assert calc_hours == 5.0
    assert integ_hours == 3.0   # это часы человека из «Расчётов»


def test_report_sum_over_groups_equals_team(db_session, data):
    svc = AnalyticsService(db_session)
    whole = svc.get_hierarchical_report(year=YEAR, quarter=QUARTER, teams=[TEAM])

    parts = sum(
        svc.get_hierarchical_report(
            year=YEAR, quarter=QUARTER, teams=[TEAM], subgroups=[g]
        ).grand_totals.fact_hours
        for g in [data["calc"].id, data["integ"].id, NO_SUBGROUP_TOKEN]
    )

    assert whole.grand_totals.fact_hours == 10.0
    assert round(parts, 2) == whole.grand_totals.fact_hours


def test_team_without_groups_unchanged(db_session, data):
    """Пустой фильтр групп не меняет ответ ни на байт."""
    svc = AnalyticsService(db_session)

    a = svc.get_dashboard_categories(year=YEAR, quarter=QUARTER, teams=[TEAM])
    b = svc.get_dashboard_categories(
        year=YEAR, quarter=QUARTER, teams=[TEAM], subgroups=[]
    )

    assert a.model_dump() == b.model_dump()
