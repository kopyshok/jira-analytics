"""pq01: существующие служебные эпики получают «не в плане» и уходят из черновиков."""
import importlib.util
from pathlib import Path

from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation


def _load_migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "pq01_service_epic_off_plan.py"
    spec = importlib.util.spec_from_file_location("migration_pq01", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _BindOp:
    """Подмена alembic.op: миграции нужен только get_bind()."""

    def __init__(self, connection):
        self._connection = connection

    def get_bind(self):
        return self._connection


def _seed(db, *, rule_enabled: bool) -> None:
    db.add_all([
        HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                      require_parent=True, is_container=False, is_enabled=rule_enabled, description="svc"),
        HierarchyRule(priority=10, project_key="RFA", issue_type=None, require_no_parent=False,
                      require_parent=False, is_container=True, is_enabled=True),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa"),
        Issue(id="i-story", key="RFA-3", jira_issue_id="j3", summary="История", issue_type="История",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa"),
        PlanningScenario(id="s-draft", name="d", year=2026, quarter="Q4", status="draft"),
        PlanningScenario(id="s-appr", name="a", year=2026, quarter="Q3", status="approved"),
    ])
    db.flush()
    db.add_all([
        BacklogItem(id="bi-rfa", issue_id="i-rfa", title="RFA"),
        BacklogItem(id="bi-disc", issue_id="i-disc", title="Дискавери"),
        BacklogItem(id="bi-story", issue_id="i-story", title="История"),
    ])
    db.flush()
    db.add_all([
        ScenarioAllocation(scenario_id="s-draft", backlog_item_id="bi-disc", included_flag=False,
                           planned_hours=0, sort_order=1.0),
        ScenarioAllocation(scenario_id="s-appr", backlog_item_id="bi-disc", included_flag=True,
                           planned_hours=0, sort_order=1.0),
    ])
    db.commit()


def _run_upgrade(db) -> None:
    module = _load_migration()
    module.op = _BindOp(db.connection())
    module.upgrade()
    db.commit()
    db.expire_all()


def test_upgrade_switches_off_service_epics_only(db_session):
    _seed(db_session, rule_enabled=True)
    _run_upgrade(db_session)
    assert db_session.get(BacklogItem, "bi-disc").included_in_planning is False
    assert db_session.get(BacklogItem, "bi-rfa").included_in_planning is True
    assert db_session.get(BacklogItem, "bi-story").included_in_planning is True
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-draft").count() == 0
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-appr").count() == 1


def test_upgrade_noop_when_rule_disabled(db_session):
    _seed(db_session, rule_enabled=False)
    _run_upgrade(db_session)
    assert db_session.get(BacklogItem, "bi-disc").included_in_planning is True
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-draft").count() == 1
