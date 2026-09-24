"""Кандидаты в исполнители: общая функция для фазы плана и строки сценария."""

from datetime import date

from app.models.employee_team import EmployeeTeam
from app.services.assignee_candidates import candidate_groups, jira_assignee_id
from tests.services.xteam_factory import add_item, book, make_employee, make_issue, make_plan

D = date.fromisoformat
Q1 = dict(start=D("2026-01-01"), end=D("2026-03-31"), year=2026, quarter=1)


def test_three_groups_with_quarter_load(db_session):
    e = make_employee(db_session, "Пряничников", "A")
    own = make_employee(db_session, "Свой B", "B")
    other = make_employee(db_session, "Посторонний", "C")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=12), e,
         {"2026-01-05": 6.0, "2026-01-06": 6.0})
    db_session.commit()

    groups = candidate_groups(db_session, team="B", jira_employee_id=e.id, **Q1)

    by_key = {g.key: g for g in groups}
    assert [g.key for g in groups] == ["jira", "team", "other"]
    assert by_key["jira"].label == "Из Jira"
    assert [c.employee_id for c in by_key["jira"].employees] == [e.id]
    assert [c.employee_id for c in by_key["team"].employees] == [own.id]
    assert [c.employee_id for c in by_key["other"].employees] == [other.id]
    assert by_key["jira"].employees[0].team == "A"
    assert 0 < by_key["jira"].employees[0].load_pct < 10  # 12 ч из 384
    assert by_key["team"].employees[0].load_pct == 0.0


def test_people_outside_teams_and_empty_groups_skipped(db_session):
    own = make_employee(db_session, "Свой B", "B")
    make_employee(db_session, "Automation for Jira", None, member=False)
    gone = make_employee(db_session, "Ушедший", "C", member=False)
    db_session.add(EmployeeTeam(employee_id=gone.id, team="C", is_primary=True,
                                left_at=D("2025-12-01")))
    db_session.commit()

    groups = candidate_groups(db_session, team="B", jira_employee_id=gone.id, **Q1)

    assert [(g.key, [c.employee_id for c in g.employees]) for g in groups] == [
        ("team", [own.id])
    ]


def test_member_borders_inside_quarter(db_session):
    leaving = make_employee(db_session, "Выбывает", "B", member=False)
    db_session.add(EmployeeTeam(employee_id=leaving.id, team="B", is_primary=True,
                                left_at=D("2026-02-11")))
    db_session.commit()

    [team] = candidate_groups(db_session, team="B", jira_employee_id=None, **Q1)

    assert team.employees[0].member_from is None
    assert team.employees[0].member_to == D("2026-02-10")


def test_jira_assignee_found_by_account(db_session, sample_project):
    e = make_employee(db_session, "Из Jira", "A", jira_account_id="acc-j")
    issue = make_issue(db_session, sample_project, "RFA-7")
    issue.assignee_account_id = "acc-j"
    db_session.commit()

    assert jira_assignee_id(db_session, issue) == e.id
    issue.assignee_account_id = None
    assert jira_assignee_id(db_session, issue) is None
    assert jira_assignee_id(db_session, None) is None
