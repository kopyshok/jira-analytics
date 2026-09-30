"""iv01: утверждение сценария вписывало процент справочника в задачу, и дальше
он перекрывал правки справочника. Миграция убирает такие записи — фазы снова
берут справочник. Значения из Jira, кварталы без справочника, черновики и
невключённые задачи не трогаются."""
import importlib.util
from datetime import datetime
from pathlib import Path

from app.models import (
    BacklogItem, InvolvementDefault, Issue, PlanningScenario, Project,
    ScenarioAllocation, ScenarioRevision,
)


def _load_migration_module():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "iv01_clear_frozen_involvement.py"
    spec = importlib.util.spec_from_file_location("migration_iv01_clear_frozen_involvement", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RealBindOp:
    def __init__(self, connection):
        self._connection = connection

    def get_bind(self):
        return self._connection


def _scenario(db, quarter, approved=True, team="A"):
    sc = PlanningScenario(name=f"S {quarter}", team=team, year=2026, quarter=quarter,
                          status="approved" if approved else "draft")
    db.add(sc)
    db.flush()
    if approved:
        db.add(ScenarioRevision(scenario_id=sc.id, revision_number=1, approved_at=datetime(2026, 9, 28)))
    return sc


def _item(db, sc, included=True, issue=None, **involvement):
    item = BacklogItem(title="I", team=sc.team, issue_id=issue.id if issue else None, **involvement)
    db.add(item)
    db.flush()
    db.add(ScenarioAllocation(scenario_id=sc.id, backlog_item_id=item.id, included_flag=included))
    return item


def test_upgrade_clears_only_values_written_by_approval(db_session):
    db = db_session
    db.add(Project(id="p1", jira_project_id="j-p1", key="PRJ", name="P", is_active=True))
    jira = Issue(id="i1", jira_issue_id="j1", key="PRJ-1", summary="S", issue_type="Task",
                 status="Open", project_id="p1", involvement_analyst=0.6)
    db.add(jira)
    db.add(InvolvementDefault(team="A", role="analyst", effective_year=2026,
                              effective_quarter=4, involvement=0.9))
    q4 = _scenario(db, "Q4")
    frozen = _item(db, q4, involvement_analyst=0.7, involvement_dev=0.9)
    from_jira = _item(db, q4, issue=jira, involvement_analyst=0.6)
    excluded = _item(db, q4, included=False, involvement_analyst=0.5)
    before_ref = _item(db, _scenario(db, "Q3"), involvement_analyst=0.7)
    in_draft = _item(db, _scenario(db, "Q4", approved=False), involvement_analyst=0.5)
    db.commit()

    module = _load_migration_module()
    module.op = _RealBindOp(db.connection())
    module.upgrade()
    db.commit()

    for item in (frozen, from_jira, excluded, before_ref, in_draft):
        db.refresh(item)
    assert frozen.involvement_analyst is None
    assert frozen.involvement_dev == 0.9  # у разработки справочника нет — не трогаем
    assert from_jira.involvement_analyst == 0.6
    assert excluded.involvement_analyst == 0.5
    assert before_ref.involvement_analyst == 0.7
    assert in_draft.involvement_analyst == 0.5
