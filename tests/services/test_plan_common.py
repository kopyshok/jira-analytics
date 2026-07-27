"""plan_common: общие расчёты плана."""
import uuid
from datetime import date, datetime

from app.models.backlog_item import BacklogItem
from app.models.issue import Issue
from app.models.project import Project
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.services.plan_common import plan_ids_for_issues, quarter_bounds


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
