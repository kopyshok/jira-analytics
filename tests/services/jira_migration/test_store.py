"""Отчёт пробного прогона и решения администратора в базе."""
from datetime import datetime, timedelta

import pytest

from app.models.jira_migration import JiraMigrationDecision, JiraMigrationReport
from app.services.jira_migration import store

NOW = datetime(2026, 10, 14, 12, 0)


def test_decision_upsert_and_delete(db_session):
    store.set_decision(db_session, store.KIND_FIELD, "customfield_11526",
                       {"dc_field_id": "customfield_11092"}, "Админ")
    store.set_decision(db_session, store.KIND_FIELD, "customfield_11526",
                       {"dc_field_id": None}, "Админ")
    assert store.get_decisions(db_session, store.KIND_FIELD) == {
        "customfield_11526": {"dc_field_id": None}
    }
    store.set_decision(db_session, store.KIND_FIELD, "customfield_11526", None, "Админ")
    assert store.get_decisions(db_session, store.KIND_FIELD) == {}


def test_concurrent_insert_falls_back_to_update(db_session, monkeypatch):
    """Строку успели вставить между проверкой и записью — повтор обновляет её."""
    store.set_decision(db_session, store.KIND_FIELD, "customfield_11526",
                       {"dc_field_id": "customfield_1"}, "Первый")
    real_find = store._find_decision
    calls = []

    def find_missing_once(db, kind, item_key):
        calls.append(item_key)
        return None if len(calls) == 1 else real_find(db, kind, item_key)

    monkeypatch.setattr(store, "_find_decision", find_missing_once)

    store.set_decision(db_session, store.KIND_FIELD, "customfield_11526",
                       {"dc_field_id": "customfield_2"}, "Второй")

    assert len(calls) == 2
    assert store.get_decisions(db_session, store.KIND_FIELD) == {
        "customfield_11526": {"dc_field_id": "customfield_2"}
    }
    assert db_session.query(JiraMigrationDecision).count() == 1
    assert db_session.query(JiraMigrationDecision).one().decided_by == "Второй"


def test_decisions_are_separated_by_kind(db_session):
    store.set_decision(db_session, store.KIND_ISSUE, "OS-1", {"action": "keep"}, "Админ")
    store.set_decision(db_session, store.KIND_PERSON, "emp-1", {"action": "unbind"}, "Админ")
    assert store.get_decisions(db_session, store.KIND_ISSUE) == {"OS-1": {"action": "keep"}}
    assert store.get_decisions(db_session, store.KIND_PERSON) == {"emp-1": {"action": "unbind"}}


@pytest.mark.parametrize("kind, decision", [
    ("field", {"dc_field_id": ""}),
    ("field", {"field": "customfield_1"}),
    ("issue", {"action": "archive"}),
    ("person", {"action": "bind"}),
    ("person", {"action": "bind", "key": "JIRAUSER1"}),
    ("person", {"action": "unbind", "key": "JIRAUSER1"}),
    ("project", {"action": "keep"}),
])
def test_invalid_decisions_rejected(kind, decision):
    with pytest.raises(ValueError):
        store.validate_decision(kind, decision)


def test_valid_decisions_accepted():
    store.validate_decision("field", {"dc_field_id": None})
    store.validate_decision("field", {"dc_field_id": "customfield_11092"})
    store.validate_decision("issue", {"action": "delete"})
    store.validate_decision("issue", None)
    store.validate_decision("person", {"action": "unbind"})
    store.validate_decision("person", {"action": "bind", "key": "JIRAUSER1",
                                       "name": None, "display_name": "Иванов Иван"})


def test_new_report_replaces_old_ones_but_keeps_decisions(db_session):
    store.set_decision(db_session, store.KIND_ISSUE, "OS-1", {"action": "keep"}, "Админ")
    first = store.start_report(db_session, NOW)
    store.finish_report(db_session, first, {"probe": []}, {"issues": {}}, NOW)

    second = store.start_report(db_session, NOW + timedelta(minutes=5))

    assert db_session.query(JiraMigrationReport).count() == 1
    row = store.latest_report(db_session)
    assert row.id == second
    assert row.status == store.STATUS_RUNNING
    assert store.get_decisions(db_session, store.KIND_ISSUE) == {"OS-1": {"action": "keep"}}


def test_finish_fail_and_extras(db_session):
    report_id = store.start_report(db_session, NOW)
    store.finish_report(db_session, report_id, {"offset_hours": 3},
                        {"issues": {"OS-1": "258783"}}, NOW + timedelta(minutes=30))
    row = store.latest_report(db_session)
    assert row.status == store.STATUS_DONE
    assert store.report_data(row) == {"offset_hours": 3}
    assert store.report_maps(row) == {"issues": {"OS-1": "258783"}}

    store.set_sync_run(db_session, report_id, "run-1")
    store.save_post_check(db_session, report_id, {"rows": []})
    row = store.latest_report(db_session)
    assert row.sync_run_id == "run-1"
    assert store.post_check_data(row) == {"rows": []}
    assert store.apply_summary(row) is None

    store.fail_report(db_session, report_id, "сбой", NOW, report={"probe": [1]})
    row = store.latest_report(db_session)
    assert row.status == store.STATUS_FAILED
    assert row.error == "сбой"
    assert store.report_data(row) == {"probe": [1]}


def test_fail_report_without_row_is_noop(db_session):
    store.fail_report(db_session, None, "сбой", NOW)
    assert store.latest_report(db_session) is None
