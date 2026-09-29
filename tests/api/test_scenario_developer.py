"""Разработчик строки сценария: ручной выбор, только в черновике, не тот же, что аналитик."""

from app.models import BacklogItem
from tests.api import test_scenario_assignee as _assignee
from tests.api.test_scenario_assignee import PLANNING

# Фикстуры строки сценария — общие с тестами исполнителя.
client = _assignee.client
row = _assignee.row


def _choose_dev(client, row, employee_id):
    return client.patch(
        f"{PLANNING}/{row.sc.id}/allocations/{row.alloc.id}/developer",
        json={"developer_employee_id": employee_id},
    )


def test_set_and_clear_developer(client, db_session, row):
    r = _choose_dev(client, row, row.own.id)
    assert r.status_code == 200, r.text
    assert r.json()["developer_employee_id"] == row.own.id
    assert r.json()["developer_display_name"] == "Свой B"
    db_session.expire_all()
    assert db_session.get(BacklogItem, row.item.id).developer_employee_id == row.own.id

    r = _choose_dev(client, row, None)
    assert r.status_code == 200, r.text
    assert r.json()["developer_employee_id"] is None
    assert r.json()["developer_display_name"] is None


def test_allocations_list_shows_developer(client, db_session, row):
    assert _choose_dev(client, row, row.own.id).status_code == 200

    r = client.get(f"{PLANNING}/{row.sc.id}/allocations")

    assert r.status_code == 200, r.text
    [a] = [a for a in r.json() if a["id"] == row.alloc.id]
    assert a["developer_employee_id"] == row.own.id
    assert a["developer_display_name"] == "Свой B"


def test_developer_same_as_assignee_is_422(client, row):
    r = _choose_dev(client, row, row.jira.id)  # row.jira — исполнитель строки
    assert r.status_code == 422, r.text


def test_assignee_same_as_developer_is_422(client, row):
    assert _choose_dev(client, row, row.own.id).status_code == 200
    r = client.patch(
        f"{PLANNING}/{row.sc.id}/allocations/{row.alloc.id}/assignee",
        json={"assignee_employee_id": row.own.id},
    )
    assert r.status_code == 422, r.text


def test_developer_unknown_employee_is_404(client, row):
    assert _choose_dev(client, row, "nope").status_code == 404


def test_developer_in_approved_scenario_is_rejected(client, db_session, row):
    row.sc.status = "approved"
    db_session.commit()
    r = _choose_dev(client, row, row.own.id)
    assert r.status_code == 409, r.text  # как _require_draft у исполнителя


def test_dev_candidates_jira_group_is_jira_developer(client, db_session, row):
    row.issue.developer_account_id = "acc-chosen"  # «Выбранный», команда C
    db_session.commit()
    r = client.get(
        f"{PLANNING}/{row.sc.id}/assignee-candidates",
        params={"backlog_item_id": row.item.id, "phase": "dev"},
    )
    assert r.status_code == 200, r.text
    groups = {g["key"]: g for g in r.json()}
    assert [c["employee_id"] for c in groups["jira"]["employees"]] == [row.chosen.id]
