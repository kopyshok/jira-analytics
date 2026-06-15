"""Тесты WorkDeskService — токены и жизненный цикл рабочих столов."""

from datetime import datetime

import pytest

from app.models import Employee
from app.services.work_desk_service import WorkDeskService

svc = WorkDeskService()


@pytest.fixture
def seed_employee(db_session):
    emp = Employee(
        id="emp-desk-1",
        jira_account_id="acc-desk-1",
        display_name="Стол Аналитик",
        is_active=True,
        synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.commit()
    return emp


def test_create_generates_unique_token(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    assert len(desk.token) >= 32
    assert desk.enabled_widgets == ["hours_balance"]


def test_create_revokes_previous_active(db_session, seed_employee):
    first = svc.create(db_session, seed_employee.id, [], "usr-1")
    second = svc.create(db_session, seed_employee.id, [], "usr-1")
    db_session.refresh(first)
    assert first.revoked_at is not None
    assert second.is_active


def test_get_active_by_employee(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, [], "usr-1")
    active = svc.get_active_by_employee(db_session, seed_employee.id)
    assert active is not None
    assert active.id == desk.id


def test_get_by_token_skips_revoked(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, [], "usr-1")
    svc.revoke(db_session, desk.id)
    assert svc.get_by_token(db_session, desk.token) is None


def test_regenerate_changes_token(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, [], "usr-1")
    old = desk.token
    new = svc.regenerate(db_session, desk.id)
    assert new.token != old
    assert svc.get_by_token(db_session, old) is None


def test_regenerate_keeps_widgets_and_employee(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, ["hours_balance", "calendar"], "usr-1")
    new = svc.regenerate(db_session, desk.id)
    assert new.enabled_widgets == ["hours_balance", "calendar"]
    assert new.employee_id == seed_employee.id
    assert new.created_by_user_id == "usr-1"
    assert new.is_active


def test_set_widgets(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, [], "usr-1")
    updated = svc.set_widgets(db_session, desk.id, ["hours_balance"])
    assert updated.enabled_widgets == ["hours_balance"]
    db_session.refresh(desk)
    assert desk.enabled_widgets == ["hours_balance"]
