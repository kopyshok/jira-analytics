"""Тесты модели WorkDesk (рабочий стол аналитика)."""
from app.models.employee import Employee
from app.models.user import User, UserRole
from app.models.work_desk import WorkDesk


def _make_employee(db_session) -> Employee:
    emp = Employee(
        id="emp-1",
        jira_account_id="acc-1",
        display_name="Аналитик",
    )
    db_session.add(emp)
    return emp


def _make_user(db_session) -> User:
    user = User(
        id="usr-1",
        email="creator@example.com",
        password_hash="x",
        display_name="Создатель",
        role=UserRole.admin,
        is_active=True,
        selected_teams_raw="[]",
        selected_period_raw="{}",
        analytics_columns_raw="[]",
        analytics_layout_raw="{}",
        appearance_settings_raw="{}",
    )
    db_session.add(user)
    return user


def test_work_desk_defaults(db_session):
    _make_employee(db_session)
    _make_user(db_session)
    desk = WorkDesk(employee_id="emp-1", token="tok-abc", created_by_user_id="usr-1")
    db_session.add(desk)
    db_session.commit()
    assert desk.id is not None
    assert desk.revoked_at is None
    assert desk.enabled_widgets == []
    assert desk.is_active is True


def test_enabled_widgets_roundtrip(db_session):
    _make_employee(db_session)
    _make_user(db_session)
    desk = WorkDesk(employee_id="emp-1", token="tok-xyz", created_by_user_id="usr-1")
    desk.enabled_widgets = ["w1", "w2"]
    db_session.add(desk)
    db_session.commit()
    assert desk.enabled_widgets == ["w1", "w2"]
    assert desk.enabled_widgets_raw == '["w1", "w2"]'
