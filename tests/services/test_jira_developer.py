"""«Разработчик» из Jira: поле задачи, иначе самый частый в поддереве."""

from datetime import date

from app.models import BacklogItem
from app.models.employee_team import EmployeeTeam
from app.services.jira_developer import jira_developers_for_items
from tests.services.xteam_factory import make_employee, make_issue

Q1 = (date(2026, 1, 1), date(2026, 3, 31))


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

    got = jira_developers_for_items(db_session, [i1, i2, i3, i4], *Q1)

    assert got == {i1.id: e1.id, i2.id: e2.id}


def test_tie_broken_by_account(db_session, sample_project):
    make_employee(db_session, "Б", "A", jira_account_id="acc-b")
    ea = make_employee(db_session, "А", "A", jira_account_id="acc-a")
    root = make_issue(db_session, sample_project, "OS-10")
    make_issue(db_session, sample_project, "OS-11", developer="acc-b", parent=root)
    make_issue(db_session, sample_project, "OS-12", developer="acc-a", parent=root)
    it = _item(db_session, root)
    db_session.commit()

    assert jira_developers_for_items(db_session, [it], *Q1) == {it.id: ea.id}


def test_only_developers_or_blank_role_are_nominated(db_session, sample_project):
    """Аналитик в поле «Разработчик» не подставляется; сотрудник без роли — годится."""
    make_employee(db_session, "Аналитик", "A", role="analyst", jira_account_id="acc-an")
    blank = make_employee(db_session, "Без роли", "A", role=None, jira_account_id="acc-blank")
    dev = make_employee(db_session, "Разработчик", "A", role="Разработчик",
                        jira_account_id="acc-dev")

    r1 = make_issue(db_session, sample_project, "OS-20", developer="acc-an")
    make_issue(db_session, sample_project, "OS-21", developer="acc-dev", parent=r1)
    r2 = make_issue(db_session, sample_project, "OS-22", developer="acc-blank")
    r3 = make_issue(db_session, sample_project, "OS-23")
    make_issue(db_session, sample_project, "OS-24", developer="acc-an", parent=r3)
    i1, i2, i3 = _item(db_session, r1), _item(db_session, r2), _item(db_session, r3)
    db_session.commit()

    got = jira_developers_for_items(db_session, [i1, i2, i3], *Q1)

    assert got == {i1.id: dev.id, i2.id: blank.id}


def test_closed_subtasks_do_not_nominate(db_session, sample_project):
    """Закрытые и отменённые подзадачи не голосуют за «Разработчика»."""
    make_employee(db_session, "Закрывший", "A", jira_account_id="acc-a")
    b = make_employee(db_session, "Открытый", "A", jira_account_id="acc-b")
    root = make_issue(db_session, sample_project, "OS-30")
    for key in ("OS-31", "OS-32"):
        make_issue(db_session, sample_project, key, developer="acc-a",
                   parent=root).status_category = "done"
    make_issue(db_session, sample_project, "OS-33", developer="acc-a",
               parent=root).status = "Отменено"
    make_issue(db_session, sample_project, "OS-34", developer="acc-b", parent=root)
    it = _item(db_session, root)
    db_session.commit()

    assert jira_developers_for_items(db_session, [it], *Q1) == {it.id: b.id}


def test_nobody_outside_teams_in_quarter_is_nominated(db_session, sample_project):
    """Бот и выбывший до квартала «Разработчиком» не подставляются — только состоящие в команде."""
    make_employee(db_session, "CEDO_BOT", None, jira_account_id="acc-bot", member=False)
    gone = make_employee(db_session, "Ушедший", "A", jira_account_id="acc-gone",
                         member=False)
    db_session.add(EmployeeTeam(employee_id=gone.id, team="A", is_primary=True,
                                left_at=date(2025, 12, 1)))
    dev = make_employee(db_session, "Разработчик", "A", jira_account_id="acc-dev")

    r1 = make_issue(db_session, sample_project, "OS-40", developer="acc-bot")
    make_issue(db_session, sample_project, "OS-41", developer="acc-dev", parent=r1)
    r2 = make_issue(db_session, sample_project, "OS-42", developer="acc-gone")
    i1, i2 = _item(db_session, r1), _item(db_session, r2)
    db_session.commit()

    assert jira_developers_for_items(db_session, [i1, i2], *Q1) == {i1.id: dev.id}
