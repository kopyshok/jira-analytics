"""Запись распределения сотрудника по группам."""

from datetime import date

import pytest

from app.models import Employee, EmployeeTeam, Team, TeamSubgroup
from app.services import subgroup_shares as ss
from app.services.subgroup_share_service import SubgroupShareService
from app.services.team_registry_service import TeamRegistryService

A, B, OTHER = "g-a", "g-b", "g-x"


@pytest.fixture
def team(db_session):
    db_session.add_all([
        Team(id="t1", name="T", has_subgroups=True),
        Team(id="t2", name="Other", has_subgroups=True),
    ])
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(id=A, team_id="t1", name="A", sort_order=1),
        TeamSubgroup(id=B, team_id="t1", name="B", sort_order=2),
        TeamSubgroup(id=OTHER, team_id="t2", name="X", sort_order=1),
        Employee(id="e1", jira_account_id="acc-1", display_name="Иванов", is_active=True),
    ])
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id="e1", team="T", is_primary=True))
    db_session.commit()


def test_set_record_and_history(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", None, {A: 100})
    history = svc.set_record("e1", "T", date(2026, 11, 15), {A: 60, B: 40})
    assert [(r.valid_from, r.shares) for r in history] == [
        (None, ((A, 100),)),
        (date(2026, 11, 15), ((A, 60), (B, 40))),
    ]


def test_same_date_replaces_record(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", date(2026, 11, 15), {A: 60, B: 40})
    history = svc.set_record("e1", "T", date(2026, 11, 15), {B: 100})
    assert [(r.valid_from, r.shares) for r in history] == [(date(2026, 11, 15), ((B, 100),))]


@pytest.mark.parametrize("shares,message", [
    ({}, "хотя бы одну"),
    ({A: 60, B: 30}, "100"),
    ({A: 0, B: 100}, "от 1 до 100"),
    ({OTHER: 100}, "не из этой команды"),
])
def test_set_record_validation(db_session, team, shares, message):
    with pytest.raises(ValueError, match=message):
        SubgroupShareService(db_session).set_record("e1", "T", None, shares)


def test_set_record_requires_division(db_session, team):
    db_session.add(Team(id="t3", name="NoDiv", has_subgroups=False))
    db_session.add(
        Employee(id="e3", jira_account_id="acc-3", display_name="Сидоров", is_active=True)
    )
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id="e3", team="NoDiv", is_primary=True))
    db_session.commit()
    with pytest.raises(ValueError, match="нет деления"):
        SubgroupShareService(db_session).set_record("e3", "NoDiv", None, {A: 100})


def test_set_record_requires_membership(db_session, team):
    db_session.add(Employee(id="e2", jira_account_id="acc-2", display_name="Петров", is_active=True))
    db_session.commit()
    with pytest.raises(ValueError, match="не состоит"):
        SubgroupShareService(db_session).set_record("e2", "T", None, {A: 100})


def test_delete_record(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", None, {A: 100})
    svc.set_record("e1", "T", date(2026, 11, 15), {B: 100})
    history = svc.delete_record("e1", "T", date(2026, 11, 15))
    assert [r.valid_from for r in history] == [None]
    with pytest.raises(LookupError):
        svc.delete_record("e1", "T", date(2026, 12, 1))


def test_assign_employee_sets_base_record(db_session, team):
    TeamRegistryService(db_session).assign_employee("e1", "T", A)
    assert ss.load_team(db_session, "T")["e1"] == [ss.ShareRecord(None, ((A, 100),))]
    TeamRegistryService(db_session).assign_employee("e1", "T", None)
    assert ss.load_team(db_session, "T") == {}


def test_delete_subgroup_drops_whole_records(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", None, {A: 100})
    svc.set_record("e1", "T", date(2026, 11, 15), {A: 60, B: 40})
    TeamRegistryService(db_session).delete_subgroup(B)
    assert [r.valid_from for r in ss.load_team(db_session, "T")["e1"]] == [None]
