"""Лесенка разрешения группы: явно -> от родителя -> по исполнителю."""

from datetime import date, datetime

import pytest

from app.models import Employee, EmployeeTeam, Issue, Project, Team, TeamSubgroup
from app.services.subgroup_resolver import SubgroupResolver, SubgroupSource
from tests.subgroup_fixtures import share

TEAM = "Команда 1С (Бухгалтерия)"


@pytest.fixture
def setup(db_session):
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    team = Team(name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True))
    db_session.add(share(emp.id, TEAM, integ.id))
    db_session.commit()
    return {"team": team, "calc": calc, "integ": integ, "emp": emp}


def _issue(db_session, key, **kw):
    issue = Issue(
        jira_issue_id=key,
        key=key,
        summary=key,
        issue_type="Task",
        status="Open",
        project_id="p1",
        team=TEAM,
        **kw,
    )
    db_session.add(issue)
    db_session.commit()
    return issue


def test_explicit_wins(db_session, setup):
    issue = _issue(
        db_session, "OS-1", assigned_subgroup_id=setup["calc"].id,
        assignee_account_id="acc-1",
    )

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id == setup["calc"].id
    assert res.source == SubgroupSource.ASSIGNED


def test_inherited_from_parent(db_session, setup):
    parent = _issue(db_session, "OS-10", assigned_subgroup_id=setup["calc"].id)
    child = _issue(db_session, "OS-11", parent_id=parent.id, assignee_account_id="acc-1")

    res = SubgroupResolver(db_session).resolve_for_issue(child)

    assert res.subgroup_id == setup["calc"].id
    assert res.source == SubgroupSource.INHERITED
    assert res.source_entity_key == "OS-10"


def test_guess_from_assignee(db_session, setup):
    issue = _issue(db_session, "OS-2", assignee_account_id="acc-1")

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id == setup["integ"].id
    assert res.source == SubgroupSource.GUESS


def test_nothing_to_guess(db_session, setup):
    issue = _issue(db_session, "OS-3")

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE


def test_team_without_subgroups_resolves_to_nothing(db_session, setup):
    setup["team"].has_subgroups = False
    db_session.commit()
    issue = _issue(
        db_session, "OS-4", assigned_subgroup_id=setup["calc"].id,
        assignee_account_id="acc-1",
    )

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE


def test_group_of_another_team_is_ignored(db_session, setup):
    """Группа чужой команды не может утечь в задачу через переезд."""
    other = Team(name="Команда Б", has_subgroups=True)
    db_session.add(other)
    db_session.flush()
    alien = TeamSubgroup(team_id=other.id, name="Расчёты", sort_order=1)
    db_session.add(alien)
    db_session.commit()
    issue = _issue(db_session, "OS-5", assigned_subgroup_id=alien.id)

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE


# --- Группа исполнителя на дату -------------------------------------------

TODAY = date(2026, 12, 1)


def _employee(db_session, account_id, *shares):
    """Сотрудник команды с записями распределения ``(группа, процент, с даты)``."""
    emp = Employee(jira_account_id=account_id, display_name=account_id)
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True))
    for subgroup, percent, valid_from in shares:
        db_session.add(share(emp.id, TEAM, subgroup.id, percent, valid_from))
    db_session.commit()
    return emp


def test_guess_takes_group_on_resolution_date(db_session, setup):
    """Закрытая задача — группа исполнителя на дату закрытия, открытая — на сегодня."""
    _employee(
        db_session, "acc-moved",
        (setup["calc"], 100, None),
        (setup["integ"], 100, date(2026, 11, 15)),
    )
    closed = _issue(
        db_session, "OS-20", assignee_account_id="acc-moved",
        status_category="done", resolved_at=datetime(2026, 11, 1, 12, 0),
    )
    open_ = _issue(db_session, "OS-21", assignee_account_id="acc-moved")

    resolver = SubgroupResolver(db_session, today=TODAY)

    assert resolver.resolve_for_issue(closed).subgroup_id == setup["calc"].id
    assert resolver.resolve_for_issue(open_).subgroup_id == setup["integ"].id
    assert resolver.resolve_for_issue(open_).source == SubgroupSource.GUESS


def test_closed_without_resolved_at_uses_status_changed_at(db_session, setup):
    """Закрытая по статусу задача без ``resolved_at`` — берём дату смены статуса."""
    _employee(
        db_session, "acc-moved",
        (setup["calc"], 100, None),
        (setup["integ"], 100, date(2026, 11, 15)),
    )
    closed = _issue(
        db_session, "OS-24", assignee_account_id="acc-moved",
        status_category="done", resolved_at=None,
        status_changed_at=datetime(2026, 11, 10, 9, 0),
    )

    res = SubgroupResolver(db_session, today=TODAY).resolve_for_issue(closed)

    assert res.subgroup_id == setup["calc"].id


def test_open_task_with_resolved_at_still_uses_today(db_session, setup):
    """Не закрытая по статусу задача не считается закрытой, даже если дата резолюции есть."""
    _employee(
        db_session, "acc-moved",
        (setup["calc"], 100, None),
        (setup["integ"], 100, date(2026, 11, 15)),
    )
    reopened = _issue(
        db_session, "OS-25", assignee_account_id="acc-moved",
        status_category="indeterminate", resolved_at=datetime(2026, 11, 1, 12, 0),
    )

    res = SubgroupResolver(db_session, today=TODAY).resolve_for_issue(reopened)

    assert res.subgroup_id == setup["integ"].id


def test_closed_exactly_on_transfer_date_gets_new_group(db_session, setup):
    """Задача, закрытая ровно в день перевода, получает новую группу."""
    _employee(
        db_session, "acc-moved",
        (setup["calc"], 100, None),
        (setup["integ"], 100, date(2026, 11, 15)),
    )
    closed = _issue(
        db_session, "OS-26", assignee_account_id="acc-moved",
        status_category="done", resolved_at=datetime(2026, 11, 15, 0, 30),
    )

    res = SubgroupResolver(db_session, today=TODAY).resolve_for_issue(closed)

    assert res.subgroup_id == setup["integ"].id


def test_future_transfer_does_not_move_open_task_yet(db_session, setup):
    """Перевод с будущей даты двигает открытые задачи только после её наступления."""
    _employee(
        db_session, "acc-moved",
        (setup["calc"], 100, None),
        (setup["integ"], 100, date(2026, 11, 15)),
    )
    open_ = _issue(db_session, "OS-22", assignee_account_id="acc-moved")

    res = SubgroupResolver(db_session, today=date(2026, 11, 14)).resolve_for_issue(open_)

    assert res.subgroup_id == setup["calc"].id


def test_shared_assignee_gives_no_guess(db_session, setup):
    """Поделённый между группами исполнитель группу задаче не даёт."""
    _employee(
        db_session, "acc-shared",
        (setup["calc"], 60, None),
        (setup["integ"], 40, None),
    )
    issue = _issue(db_session, "OS-23", assignee_account_id="acc-shared")

    res = SubgroupResolver(db_session, today=TODAY).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE


def test_record_without_membership_is_ignored(db_session, setup):
    """Участие в команде удалили как ошибку ввода, а запись распределения
    осталась — группу по такому исполнителю не угадываем."""
    orphan = Employee(jira_account_id="acc-orphan", display_name="Сирота")
    db_session.add(orphan)
    db_session.flush()
    db_session.add(share(orphan.id, TEAM, setup["calc"].id))
    db_session.commit()
    issue = _issue(db_session, "OS-30", assignee_account_id="acc-orphan")

    resolver = SubgroupResolver(db_session, today=TODAY)
    res = resolver.resolve_for_issue(issue)
    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE

    resolver.recompute_effective(TEAM)
    db_session.refresh(issue)
    assert issue.effective_subgroup_id is None
