"""Виджет «Проекты квартала»: группы кольца не пересекаются и в сумме дают все проекты."""
import uuid
from collections import Counter
from datetime import datetime, timedelta

from app.models.backlog_item import BacklogItem
from app.models.issue import Issue
from app.models.planning_scenario import PlanningScenario
from app.models.project import Project
from app.models.scenario_allocation import ScenarioAllocation
from app.services.analytics_service import AnalyticsService


def test_overdue_projects_are_not_counted_twice(db_session):
    """Просроченный проект — только в «Просрочены», а не ещё и в «В работе»/«Не начаты»."""
    db = db_session
    past = datetime.now() - timedelta(days=10)
    future = datetime.now() + timedelta(days=30)
    db.add(Project(id="p_cnt", jira_project_id="p_cnt", key="CNT", name="Counters"))
    cases = [
        ("cnt_wip_late", "indeterminate", past),
        ("cnt_new_late", "new", past),
        ("cnt_wip", "indeterminate", future),
        ("cnt_new", "new", None),
        ("cnt_done_late", "done", past),
    ]
    scenario = PlanningScenario(id=str(uuid.uuid4()), name="S", year=2026, quarter="Q4",
                                status="approved", team="T-cnt")
    db.add(scenario)
    for n, (issue_id, category, due) in enumerate(cases, start=1):
        db.add(Issue(id=issue_id, jira_issue_id=issue_id, key=f"CNT-{n}", summary=issue_id,
                     issue_type="Epic", status="—", project_id="p_cnt",
                     status_category=category, due_date=due, include_in_analysis=True))
        item = BacklogItem(id=str(uuid.uuid4()), issue_id=issue_id, title=issue_id,
                           estimate_dev_hours=8.0)
        db.add(item)
        db.flush()
        db.add(ScenarioAllocation(id=str(uuid.uuid4()), scenario_id=scenario.id,
                                  backlog_item_id=item.id, included_flag=True))
    db.commit()

    resp = AnalyticsService(db).get_dashboard_projects(2026, 4, teams=["T-cnt"])

    assert resp.total == 5
    assert (resp.done, resp.in_progress, resp.overdue, resp.not_started) == (1, 1, 2, 1)
    assert resp.done + resp.in_progress + resp.overdue + resp.not_started == resp.total
    # Счётчики совпадают со статусами строк таблицы под кольцом.
    by_status = Counter(p.status_category for p in resp.projects)
    assert by_status == {"done": 1, "indeterminate": 1, "overdue": 2, "new": 1}
