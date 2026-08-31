"""Проекты и Бэклог в разрезе групп внутри команды."""

from datetime import datetime

import pytest

from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    Issue,
    Project,
    Team,
    TeamSubgroup,
    Worklog,
)
from app.services import subgroup_filter as sgf
from app.services.projects_service import ProjectsService
from app.services.subgroup_resolver import SubgroupResolver

TEAM = "Команда 1С (Бухгалтерия)"
DAY = datetime(2026, 8, 5, 10, 0)


@pytest.fixture
def data(db_session):
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    team = Team(name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    emp = Employee(jira_account_id="acc-1", display_name="Иванов", is_active=True, role="dev")
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True))

    def issue(key, *, parent=None, subgroup=None, category=None):
        it = Issue(
            jira_issue_id=key, key=key, summary=key, issue_type="Task",
            status="Open", status_category="indeterminate", project_id="p1",
            team=TEAM, category=category,
            parent_id=parent.id if parent else None,
            assigned_subgroup_id=subgroup.id if subgroup else None,
        )
        db_session.add(it)
        db_session.flush()
        return it

    # Две инициативы: под первой работа «Расчётов», под второй — «Интеграций».
    rfa_a = issue("OS-100", category="quarterly_tasks")
    rfa_b = issue("OS-200", category="quarterly_tasks")
    rfa_new = issue("OS-300", category="quarterly_tasks")  # без работ вообще
    task_a = issue("OS-101", parent=rfa_a, subgroup=calc)
    task_b = issue("OS-201", parent=rfa_b, subgroup=integ)

    db_session.add_all([
        Worklog(jira_worklog_id="w1", issue_id=task_a.id, employee_id=emp.id,
                started_at=DAY, time_spent_seconds=4 * 3600, hours=4.0),
        Worklog(jira_worklog_id="w2", issue_id=task_b.id, employee_id=emp.id,
                started_at=DAY, time_spent_seconds=6 * 3600, hours=6.0),
    ])
    db_session.commit()
    SubgroupResolver(db_session).recompute_effective()
    return {
        "calc": calc, "integ": integ, "emp": emp,
        "rfa_a": rfa_a, "rfa_b": rfa_b, "rfa_new": rfa_new,
    }


def test_projects_list_narrowed_by_group(db_session, data):
    svc = ProjectsService(db_session)

    whole = {p.key for p in svc.list_projects()}
    only_calc = svc.list_projects(subgroups=[data["calc"].id])

    assert {"OS-100", "OS-200", "OS-300"} <= whole
    assert [p.key for p in only_calc] == ["OS-100"]
    assert only_calc[0].total_hours == 4.0


def test_backlog_roots_keep_untouched_initiatives(db_session, data):
    """Инициатива без проставленных групп видна при любом выборе."""
    keep = sgf.roots_matching(
        db_session,
        [data["rfa_a"].id, data["rfa_b"].id, data["rfa_new"].id],
        [data["calc"].id],
    )

    assert data["rfa_a"].id in keep       # под ней работа «Расчётов»
    assert data["rfa_b"].id not in keep    # только «Интеграции»
    assert data["rfa_new"].id in keep      # групп под ней нет вовсе


def test_manual_backlog_idea_never_hidden(db_session, data):
    """У ручной идеи нет задачи Jira, значит и группы — фильтр её не трогает."""
    idea = BacklogItem(title="Идея без Jira", team=TEAM)
    db_session.add(idea)
    db_session.commit()

    keep = sgf.roots_matching(db_session, [], [data["calc"].id])

    assert keep is None  # нечего сужать — список корней пуст
    assert idea.issue_id is None
