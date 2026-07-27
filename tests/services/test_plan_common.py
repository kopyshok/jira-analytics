"""plan_common: общие расчёты плана."""
import uuid
from datetime import date, datetime

from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.issue import Issue
from app.models.project import Project
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.worklog import Worklog
from app.services.plan_common import plan_ids_for_issues, quarter_bounds, role_breakdown


def _uid() -> str:
    return str(uuid.uuid4())


def test_quarter_bounds_q3():
    assert quarter_bounds(2026, 3) == (date(2026, 7, 1), date(2026, 9, 30))


def test_plan_ids_for_issues_keeps_freshest_plan_per_quarter(db_session):
    db = db_session
    db.add(Project(id="p1", jira_project_id="p1", key="PRJ", name="Project"))
    db.add(Issue(id="i1", jira_issue_id="1", key="PRJ-1", summary="Epic",
                 issue_type="Epic", status="В работе", project_id="p1",
                 category="quarterly_tasks", include_in_analysis=True))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Epic", issue_id="i1"))

    # Два плана одного квартала (форк) + один плана следующего квартала.
    stale_id, fresh_id, next_q_id = _uid(), _uid(), _uid()
    db.add(ResourcePlan(id=stale_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 1)))
    db.add(ResourcePlan(id=fresh_id, team="T", year=2026, quarter="3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlan(id=next_q_id, team="T", year=2026, quarter="Q4",
                        computed_at=datetime(2026, 10, 1)))
    for pid in (stale_id, fresh_id, next_q_id):
        db.add(ResourcePlanAssignment(id=_uid(), plan_id=pid, backlog_item_id=item_id,
                                      phase="analyst", hours_allocated=10.0))
    db.commit()

    got = set(plan_ids_for_issues(db, ["i1"]))
    assert got == {fresh_id, next_q_id}, "форк того же квартала должен отсеяться"


def test_plan_ids_for_issues_empty_input(db_session):
    assert plan_ids_for_issues(db_session, []) == []


def test_plan_ids_for_issues_computed_at_none_prefers_computed_over_fresher_draft(db_session):
    """Не посчитанный план (computed_at=None) не должен побеждать посчитанный,
    даже если сам создан позже — свежесть считается прежде всего по computed_at.
    """
    db = db_session
    db.add(Project(id="p2", jira_project_id="p2", key="PRJ2", name="Project 2"))
    db.add(Issue(id="i2", jira_issue_id="2", key="PRJ2-1", summary="Epic 2",
                 issue_type="Epic", status="В работе", project_id="p2"))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Epic 2", issue_id="i2"))

    draft_id, computed_id = _uid(), _uid()
    # Черновик: ещё не считался, но создан позже посчитанного плана.
    db.add(ResourcePlan(id=draft_id, team="T2", year=2026, quarter="Q3",
                        computed_at=None, created_at=datetime(2026, 7, 25)))
    # Посчитан раньше по created_at, зато у него есть computed_at.
    db.add(ResourcePlan(id=computed_id, team="T2", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 10), created_at=datetime(2026, 7, 1)))
    for pid in (draft_id, computed_id):
        db.add(ResourcePlanAssignment(id=_uid(), plan_id=pid, backlog_item_id=item_id,
                                      phase="analyst", hours_allocated=10.0))
    db.commit()

    got = plan_ids_for_issues(db, ["i2"])
    assert got == [computed_id]


def test_plan_ids_for_issues_two_teams_same_quarter_both_kept(db_session):
    """Дедуп по (команда, год, квартал) не должен схлопывать разные команды."""
    db = db_session
    db.add(Project(id="p3", jira_project_id="p3", key="PRJ3", name="Project 3"))
    db.add(Issue(id="i3", jira_issue_id="3", key="PRJ3-1", summary="Epic 3",
                 issue_type="Epic", status="В работе", project_id="p3"))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Epic 3", issue_id="i3"))

    t1_id, t2_id = _uid(), _uid()
    db.add(ResourcePlan(id=t1_id, team="T1", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 10)))
    db.add(ResourcePlan(id=t2_id, team="T2", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 10)))
    for pid in (t1_id, t2_id):
        db.add(ResourcePlanAssignment(id=_uid(), plan_id=pid, backlog_item_id=item_id,
                                      phase="analyst", hours_allocated=10.0))
    db.commit()

    got = set(plan_ids_for_issues(db, ["i3"]))
    assert got == {t1_id, t2_id}


def test_plan_ids_for_issues_no_assignments_returns_empty(db_session):
    """Задача существует и привязана к бэклогу, но назначений по ней нет ни в одном плане."""
    db = db_session
    db.add(Project(id="p5", jira_project_id="p5", key="PRJ5", name="Project 5"))
    db.add(Issue(id="i5", jira_issue_id="5", key="PRJ5-1", summary="Epic 5",
                 issue_type="Epic", status="В работе", project_id="p5"))
    db.add(BacklogItem(id=_uid(), title="Epic 5", issue_id="i5"))
    db.commit()

    assert plan_ids_for_issues(db, ["i5"]) == []


def test_role_breakdown_sums_across_multiple_plans_and_splits_opo(db_session):
    """План суммируется по всем переданным планам; ОПЭ расходится в analyst/dev."""
    db = db_session
    db.add(Project(id="p4", jira_project_id="p4", key="PRJ4", name="Project 4"))
    db.add(Issue(id="i4", jira_issue_id="4", key="PRJ4-1", summary="Epic 4",
                 issue_type="Epic", status="В работе", project_id="p4"))
    item_id = _uid()
    # Коэффициент нарочно отличается от дефолта 0.5 — иначе тест не отличит
    # «код прочитал реальное значение» от «код всегда берёт дефолт».
    db.add(BacklogItem(id=item_id, title="Epic 4", issue_id="i4", opo_analyst_ratio=0.3))

    plan_q3_id, plan_q4_id = _uid(), _uid()
    db.add(ResourcePlan(id=plan_q3_id, team="T4", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 10)))
    db.add(ResourcePlan(id=plan_q4_id, team="T4", year=2026, quarter="Q4",
                        computed_at=datetime(2026, 10, 10)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_q3_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=40.0))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_q3_id, backlog_item_id=item_id,
                                  phase="opo", hours_allocated=30.0))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_q4_id, backlog_item_id=item_id,
                                  phase="qa", hours_allocated=20.0))
    db.commit()

    subtree = {"i4": {"i4"}}
    result = role_breakdown(
        db, [plan_q3_id, plan_q4_id], ["i4"], subtree, date(2026, 12, 31), set()
    )

    bd = result["i4"]
    # 40 (Q3 analyst) + доля ОПЭ по коэффициенту (30 * 0.3) = 49.
    assert bd["plan"]["analyst"] == 49.0
    # Остаток ОПЭ (30 * 0.7).
    assert bd["plan"]["dev"] == 21.0
    # 20 (Q4 qa) — план из другого квартала тоже учтён.
    assert bd["plan"]["qa"] == 20.0
    assert "opo" not in bd["plan"]
    assert "opo" not in bd["fact"]


def test_role_breakdown_accepts_mapping_of_team_ids_per_root(db_session):
    """team_ids как Mapping «корень → набор» — за один вызов считаем сразу
    несколько корней с разным составом «своей» команды (нужно сводке
    портфеля, чтобы не звать role_breakdown в цикле по проектам — см.
    ProjectPlanService.get_portfolio).
    """
    db = db_session
    db.add(Project(id="pm", jira_project_id="pm", key="PRM", name="Project M"))
    db.add(Issue(id="ra", jira_issue_id="ra1", key="PRM-1", summary="Root A",
                 issue_type="Epic", status="В работе", project_id="pm"))
    db.add(Issue(id="rb", jira_issue_id="rb1", key="PRM-2", summary="Root B",
                 issue_type="Epic", status="В работе", project_id="pm"))
    emp_a, emp_b = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Employee(id=emp_a, jira_account_id=emp_a, display_name="A", role="analyst"))
    db.add(Employee(id=emp_b, jira_account_id=emp_b, display_name="B", role="analyst"))
    # emp_a — свой на A, гость на B. emp_b — свой на B, гость на A.
    db.add(Worklog(id=_uid(), jira_worklog_id=_uid(), issue_id="ra", employee_id=emp_a,
                   hours=10.0, time_spent_seconds=36000, started_at=datetime(2026, 7, 10)))
    db.add(Worklog(id=_uid(), jira_worklog_id=_uid(), issue_id="ra", employee_id=emp_b,
                   hours=4.0, time_spent_seconds=14400, started_at=datetime(2026, 7, 11)))
    db.add(Worklog(id=_uid(), jira_worklog_id=_uid(), issue_id="rb", employee_id=emp_b,
                   hours=6.0, time_spent_seconds=21600, started_at=datetime(2026, 7, 12)))
    db.commit()

    subtree = {"ra": {"ra"}, "rb": {"rb"}}
    team_ids = {"ra": {emp_a}, "rb": {emp_b}}
    result = role_breakdown(db, [], ["ra", "rb"], subtree, date(2026, 7, 31), team_ids)

    assert result["ra"]["fact"]["analyst"] == 10.0
    assert result["ra"]["info"] == 4.0, "emp_b чужой для root A — во «Внешние»"
    assert result["rb"]["fact"]["analyst"] == 6.0
    assert result["rb"]["info"] == 0.0


def test_role_breakdown_mapping_missing_root_treats_all_as_external(db_session):
    """Корня нет в словаре team_ids → пустой набор по умолчанию, все часы во «внешние»."""
    db = db_session
    db.add(Project(id="pm2", jira_project_id="pm2", key="PRM2", name="Project M2"))
    db.add(Issue(id="rc", jira_issue_id="rc1", key="PRM2-1", summary="Root C",
                 issue_type="Epic", status="В работе", project_id="pm2"))
    emp = str(uuid.uuid4())
    db.add(Employee(id=emp, jira_account_id=emp, display_name="C", role="analyst"))
    db.add(Worklog(id=_uid(), jira_worklog_id=_uid(), issue_id="rc", employee_id=emp,
                   hours=5.0, time_spent_seconds=18000, started_at=datetime(2026, 7, 10)))
    db.commit()

    result = role_breakdown(db, [], ["rc"], {"rc": {"rc"}}, date(2026, 7, 31), {})

    assert result["rc"]["fact"]["analyst"] == 0.0
    assert result["rc"]["info"] == 5.0
