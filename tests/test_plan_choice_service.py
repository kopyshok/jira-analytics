"""PlanEditService: выбор значения спорной оценки."""
from datetime import datetime

import pytest

from app.models import BacklogItem, Issue, PlanAudit, Project
from app.services.plan_edit_service import PlanEditService
from app.services.plan_sources import (
    MANUAL_SOURCE, candidates_from_json, disputes_for, fingerprint,
)

SOURCES = {"dev": [
    {"source": "customfield_12432", "label": "Разработка (ч)", "value": 100.0},
    {"source": "sum", "label": "Оценка Back + Оценка Front", "value": 80.0},
]}


def _seed(db, manual=None):
    p = Project(id="p-ch", key="CH", jira_project_id="jp-ch", name="CH")
    i = Issue(
        id="i-ch", key="CH-1", jira_issue_id="j-ch", summary="Инициатива",
        issue_type="RFA", status="Open", project_id=p.id,
        category="initiatives_rfa",
        planned_dev_hours_jira=100.0, planned_dev_hours_manual=manual,
        planned_hours_sources=SOURCES,
    )
    b = BacklogItem(id="b-ch", title="Инициатива", issue_id=i.id,
                    estimate_dev_hours=manual if manual is not None else 100.0)
    db.add_all([p, i, b])
    db.commit()
    return i


def test_choose_source_sets_value_choice_audit_and_backlog(db_session):
    _seed(db_session, manual=90.0)
    PlanEditService(db_session).choose_source("i-ch", "dev", "sum", user_id=None)

    issue = db_session.get(Issue, "i-ch")
    assert issue.planned_dev_hours_jira == 80.0
    assert issue.planned_dev_hours_manual is None
    cands = candidates_from_json(issue.planned_hours_sources["dev"])
    assert issue.planned_hours_choice["dev"] == {"source": "sum", "fingerprint": fingerprint(cands)}
    assert disputes_for(issue.planned_hours_sources, issue.planned_hours_choice, set()) == {}

    audit = db_session.query(PlanAudit).filter_by(issue_id="i-ch", source="dispute_choice").one()
    assert audit.value_before == 90.0 and audit.value_after == 80.0
    assert db_session.get(BacklogItem, "b-ch").estimate_dev_hours == 80.0


def test_choose_source_unknown_source_raises(db_session):
    _seed(db_session)
    with pytest.raises(ValueError):
        PlanEditService(db_session).choose_source("i-ch", "dev", "customfield_404")


def test_choose_source_unknown_role_raises(db_session):
    _seed(db_session)
    with pytest.raises(ValueError):
        PlanEditService(db_session).choose_source("i-ch", "boss", "sum")


def test_choose_manual_sets_manual_and_resolves(db_session):
    _seed(db_session)
    PlanEditService(db_session).choose_manual("i-ch", "dev", 95.0, user_id=None)

    issue = db_session.get(Issue, "i-ch")
    assert issue.planned_dev_hours_manual == 95.0
    assert issue.planned_dev_hours_jira == 100.0
    assert issue.planned_hours_choice["dev"]["source"] == MANUAL_SOURCE
    assert disputes_for(issue.planned_hours_sources, issue.planned_hours_choice, {"dev"}) == {}
    assert db_session.get(BacklogItem, "b-ch").estimate_dev_hours == 95.0


def _pending_sync_conflict(db):
    """Синк поменял Jira-значение при ручном — открытый конфликт по роли."""
    db.add(PlanAudit(
        issue_id="i-ch", role="dev", value_before=90.0, value_after=100.0,
        source="jira_sync_conflict", created_at=datetime(2026, 1, 1),
    ))
    db.commit()


def test_choose_source_logs_even_same_value_and_closes_sync_conflict(db_session):
    """Поле с тем же числом, что и ручное: журнал всё равно пишется, иначе
    конфликт синка остаётся последней записью роли и висит открытым,
    хотя ручного значения уже нет."""
    _seed(db_session, manual=80.0)
    _pending_sync_conflict(db_session)
    svc = PlanEditService(db_session)
    assert [c["role"] for c in svc.open_conflicts("i-ch")] == ["dev"]

    svc.choose_source("i-ch", "dev", "sum")  # сумма = 80, как ручное

    assert svc.open_conflicts("i-ch") == []
    audit = db_session.query(PlanAudit).filter_by(issue_id="i-ch", source="dispute_choice").one()
    assert (audit.value_before, audit.value_after) == (80.0, 80.0)


def test_choose_manual_logs_even_same_value_and_closes_sync_conflict(db_session):
    _seed(db_session, manual=95.0)
    _pending_sync_conflict(db_session)
    svc = PlanEditService(db_session)

    svc.choose_manual("i-ch", "dev", 95.0)

    assert svc.open_conflicts("i-ch") == []
    audit = db_session.query(PlanAudit).filter_by(issue_id="i-ch", source="dispute_choice").one()
    assert (audit.value_before, audit.value_after) == (95.0, 95.0)
    assert db_session.get(Issue, "i-ch").planned_dev_hours_manual == 95.0


def test_choose_manual_without_candidates_raises(db_session):
    _seed(db_session)
    with pytest.raises(ValueError):
        PlanEditService(db_session).choose_manual("i-ch", "qa", 10.0)
