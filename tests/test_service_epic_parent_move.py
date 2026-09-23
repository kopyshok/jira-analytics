"""Эпик, переехавший под RFA и ставший служебным (Дискавери), выключается из плана.

Синк видит, что до переезда задача служебным эпиком не была, а после — стала:
галочка «В план» снимается, черновые распределения убираются. Переезд между
RFA (служебным был и остаётся) выбор PM не трогает.
"""
from unittest.mock import MagicMock

from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation
from app.repositories.base import BaseRepository
from app.services.sync_service import SyncService


def _svc(db) -> SyncService:
    svc = SyncService.__new__(SyncService)
    svc.db = db
    svc.issue_repo = BaseRepository(Issue, db)
    svc.connector = MagicMock()
    svc.project_repo = MagicMock()
    svc.worklog_repo = MagicMock()
    svc.employee_repo = MagicMock()
    svc._settings_cache = {}
    return svc


def _jira(jira_id: str, key: str, issue_type: str, parent_key):
    ji = MagicMock()
    ji.id = jira_id
    ji.key = key
    ji.fields.summary = "Эпик"
    ji.fields.description_text = None
    ji.fields.issuetype.name = issue_type
    ji.fields.status.name = "Open"
    ji.fields.status.statusCategory = None
    ji.fields.priority = None
    ji.fields.statuscategorychangedate = None
    ji.fields.updated = None
    ji.fields.duedate = None
    ji.fields.resolution = None
    ji.fields.resolutiondate = None
    ji.fields.assignee = None
    ji.fields.creator = None
    ji.fields.reporter = None
    ji.fields.parent_key = parent_key
    ji.fields._extra = {}
    return ji


def _seed(db, *, epic_parent_id):
    db.add_all([
        HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                      require_parent=True, is_container=False, is_enabled=True, description="svc"),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-rfa2", key="RFA-3", jira_issue_id="j3", summary="RFA 2", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-epic", key="RFA-2", jira_issue_id="j2", summary="Эпик", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id=epic_parent_id,
              category="initiatives_rfa", team="T1"),
        PlanningScenario(id="s-draft", name="d", year=2026, quarter="Q4", status="draft", team="T1"),
        PlanningScenario(id="s-appr", name="a", year=2026, quarter="Q3", status="approved", team="T1"),
    ])
    db.flush()
    db.add(BacklogItem(id="bi-epic", issue_id="i-epic", title="Эпик", included_in_planning=True))
    db.flush()
    db.add_all([
        ScenarioAllocation(scenario_id="s-draft", backlog_item_id="bi-epic", included_flag=False,
                           planned_hours=0, sort_order=1.0),
        ScenarioAllocation(scenario_id="s-appr", backlog_item_id="bi-epic", included_flag=True,
                           planned_hours=0, sort_order=1.0),
    ])
    db.commit()


def test_root_epic_moved_under_rfa_is_switched_off(db_session):
    _seed(db_session, epic_parent_id=None)
    _svc(db_session)._upsert_issue(_jira("j2", "RFA-2", "Эпик", "RFA-1"), "p-rfa", parent_id="i-rfa")
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(BacklogItem, "bi-epic").included_in_planning is False
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-draft").count() == 0
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-appr").count() == 1


def test_parent_pending_second_pass_still_detected(db_session):
    """Родитель новый и ещё не в базе: parent_id пуст, но ключ родителя есть."""
    _seed(db_session, epic_parent_id=None)
    _svc(db_session)._upsert_issue(_jira("j2", "RFA-2", "Эпик", "RFA-99"), "p-rfa", parent_id=None)
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(BacklogItem, "bi-epic").included_in_planning is False


def test_move_between_rfas_keeps_pm_choice(db_session):
    _seed(db_session, epic_parent_id="i-rfa")
    _svc(db_session)._upsert_issue(_jira("j2", "RFA-2", "Эпик", "RFA-3"), "p-rfa", parent_id="i-rfa2")
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(BacklogItem, "bi-epic").included_in_planning is True
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-draft").count() == 1
