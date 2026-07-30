"""Условия отбора превращаются в запрос к задачам."""
import json
from datetime import date, datetime

from app.models.issue import Issue
from app.services.kpi.conditions import ConditionSet, build_issue_query


def _make_issue(db, project, **kw):
    defaults = dict(
        jira_issue_id=kw.pop("jid", "1"), key=kw.pop("key", "OS-1"), summary="s",
        issue_type="Задача", status="ГОТОВО", status_category="done",
        project_id=project.id,
    )
    defaults.update(kw)
    issue = Issue(**defaults)
    db.add(issue)
    return issue


def test_filters_by_project_type_resolution(db_session, sample_project):
    _make_issue(db_session, sample_project, jid="1", key="OS-1", issue_type="Баг",
                resolution="Готово", environment="PROD", reporter_account_id="acc-1",
                resolved_at=datetime(2026, 7, 10))
    _make_issue(db_session, sample_project, jid="2", key="OS-2", issue_type="Баг",
                resolution="Отменено", environment="PROD", reporter_account_id="acc-1",
                resolved_at=datetime(2026, 7, 11))
    db_session.commit()

    cs = ConditionSet.from_json(json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [
            {"attr": "issue_type", "op": "in", "value": ["Баг"]},
            {"attr": "resolution", "op": "in", "value": ["Готово"]},
            {"attr": "environment", "op": "eq", "value": "PROD"},
        ],
    }))
    q = build_issue_query(
        db_session, cs, account_id="acc-1",
        period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
        excluded_statuses=["Отменено"], teams=None,
    )
    keys = sorted(i.key for i in q.all())
    assert keys == ["OS-1"]


def test_field_filled_requires_all_fields(db_session, sample_project):
    _make_issue(db_session, sample_project, jid="3", key="OS-3", reporter_account_id="acc-1",
                resolution="Готово", resolved_at=datetime(2026, 7, 10),
                goal_text="цель", current_behavior="как сейчас", description="описание")
    _make_issue(db_session, sample_project, jid="4", key="OS-4", reporter_account_id="acc-1",
                resolution="Готово", resolved_at=datetime(2026, 7, 10),
                goal_text="цель", current_behavior=None, description="описание")
    db_session.commit()

    cs = ConditionSet.from_json(json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [{"attr": "field_filled", "op": "all",
                        "value": ["goal_text", "current_behavior", "description"]}],
    }))
    q = build_issue_query(db_session, cs, account_id="acc-1",
                          period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
                          excluded_statuses=[], teams=None)
    assert [i.key for i in q.all()] == ["OS-3"]
