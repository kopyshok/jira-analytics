"""«Разработчик» из Jira: поле задачи, иначе самый частый в поддереве."""

from app.models import BacklogItem
from app.services.jira_developer import jira_developers_for_items
from tests.services.xteam_factory import make_employee, make_issue


def _item(db, issue=None):
    it = BacklogItem(title="x", issue_id=issue.id if issue else None)
    db.add(it)
    db.flush()
    return it


def test_own_field_then_most_frequent_child(db_session, sample_project):
    e1 = make_employee(db_session, "Первый", "A", jira_account_id="acc-1")
    e2 = make_employee(db_session, "Второй", "A", jira_account_id="acc-2")
    make_employee(db_session, "Третий", "A", jira_account_id="acc-3")
    make_employee(db_session, "Ушедший", "A", jira_account_id="acc-off",
                  is_active=False)

    r1 = make_issue(db_session, sample_project, "OS-1", developer="acc-1")
    r2 = make_issue(db_session, sample_project, "OS-2")
    epic = make_issue(db_session, sample_project, "OS-3", parent=r2)
    make_issue(db_session, sample_project, "OS-4", developer="acc-2", parent=epic)
    make_issue(db_session, sample_project, "OS-5", developer="acc-2", parent=epic)
    make_issue(db_session, sample_project, "OS-6", developer="acc-3", parent=r2)
    r3 = make_issue(db_session, sample_project, "OS-7", developer="acc-off")

    i1, i2, i3, i4 = _item(db_session, r1), _item(db_session, r2), _item(db_session, r3), _item(db_session)
    db_session.commit()

    got = jira_developers_for_items(db_session, [i1, i2, i3, i4])

    assert got == {i1.id: e1.id, i2.id: e2.id}


def test_tie_broken_by_account(db_session, sample_project):
    make_employee(db_session, "Б", "A", jira_account_id="acc-b")
    ea = make_employee(db_session, "А", "A", jira_account_id="acc-a")
    root = make_issue(db_session, sample_project, "OS-10")
    make_issue(db_session, sample_project, "OS-11", developer="acc-b", parent=root)
    make_issue(db_session, sample_project, "OS-12", developer="acc-a", parent=root)
    it = _item(db_session, root)
    db_session.commit()

    assert jira_developers_for_items(db_session, [it]) == {it.id: ea.id}
