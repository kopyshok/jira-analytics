"""Виджет «Проекты квартала»: «тишина» у проекта, по которому часов не списывали."""
import uuid

from app.models.backlog_item import BacklogItem
from app.models.issue import Issue
from app.models.planning_scenario import PlanningScenario
from app.models.project import Project
from app.models.scenario_allocation import ScenarioAllocation
from app.services.analytics_service import AnalyticsService


def test_project_without_worklogs_has_no_silence_days(db_session):
    """Списаний не было вовсе — дней тишины нет (а не условные 9999), но проект молчит."""
    db = db_session
    db.add(Project(id="p_sil", jira_project_id="p_sil", key="SIL", name="Silence"))
    db.add(Issue(id="sil_epic", jira_issue_id="sil1", key="SIL-1", summary="Без списаний",
                 issue_type="Epic", status="To Do", project_id="p_sil",
                 status_category="new", include_in_analysis=True))
    item = BacklogItem(id=str(uuid.uuid4()), issue_id="sil_epic", title="Без списаний",
                       estimate_dev_hours=40.0)
    scenario = PlanningScenario(id=str(uuid.uuid4()), name="S", year=2026, quarter="Q4",
                                status="approved", team="T-sil")
    db.add_all([item, scenario])
    db.flush()
    db.add(ScenarioAllocation(id=str(uuid.uuid4()), scenario_id=scenario.id,
                              backlog_item_id=item.id, included_flag=True))
    db.commit()

    resp = AnalyticsService(db).get_dashboard_projects(2026, 4, teams=["T-sil"])

    project = next(p for p in resp.projects if p.issue_key == "SIL-1")
    assert project.silent_days is None
    assert resp.silent_count == 1
