"""Исполнитель строки из Jira — если его не выбрали в сценарии вручную."""

from types import SimpleNamespace

from app.models import BacklogItem
from app.services.backlog_service import apply_jira_assignee

EMPS = {"acc-1": SimpleNamespace(id="e1"), "acc-2": SimpleNamespace(id="e2")}


def _item(**kw) -> BacklogItem:
    return BacklogItem(title="x", **kw)


def test_not_manual_follows_jira():
    item = _item(assignee_employee_id=None, assignee_manual=False)

    apply_jira_assignee(item, "acc-1", EMPS)

    assert item.assignee_employee_id == "e1"


def test_unknown_or_empty_jira_assignee_clears():
    item = _item(assignee_employee_id="e1", assignee_manual=False)
    apply_jira_assignee(item, "acc-x", EMPS)
    assert item.assignee_employee_id is None

    item.assignee_employee_id = "e1"
    apply_jira_assignee(item, None, EMPS)
    assert item.assignee_employee_id is None


def test_manual_choice_kept_while_jira_unchanged():
    item = _item(assignee_employee_id="e9", assignee_manual=True,
                 assignee_jira_account_at_choice="acc-1")

    apply_jira_assignee(item, "acc-1", EMPS)

    assert item.assignee_employee_id == "e9"
    assert item.assignee_manual is True


def test_manual_clear_kept_while_jira_unchanged():
    item = _item(assignee_employee_id=None, assignee_manual=True,
                 assignee_jira_account_at_choice="acc-1")

    apply_jira_assignee(item, "acc-1", EMPS)

    assert item.assignee_employee_id is None


def test_manual_choice_dropped_when_jira_assignee_changes():
    item = _item(assignee_employee_id="e9", assignee_manual=True,
                 assignee_jira_account_at_choice="acc-1")

    apply_jira_assignee(item, "acc-2", EMPS)

    assert item.assignee_employee_id == "e2"
    assert item.assignee_manual is False
    assert item.assignee_jira_account_at_choice is None
