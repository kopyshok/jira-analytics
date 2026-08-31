"""Выбор групп в шапке хранится у пользователя.

Через HTTP не проверяем: conftest подменяет текущего пользователя заглушкой,
не привязанной к сессии. Проверяем модель и то, что ручка присваивает поле.
"""

from app.api.endpoints.auth import update_my_teams
from app.models.user import User, UserRole
from app.schemas.user import UserTeamsUpdate


def _user(db) -> User:
    u = User(
        email="subgroup_filter@example.com",
        password_hash="hashed",
        display_name="Filter Tester",
        role=UserRole.manager,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_selected_subgroups_default_empty(db_session):
    assert _user(db_session).selected_subgroups == []


def test_selected_subgroups_roundtrip(db_session):
    user = _user(db_session)

    user.selected_subgroups = ["sg-1", "sg-2"]
    db_session.commit()
    db_session.refresh(user)

    assert user.selected_subgroups == ["sg-1", "sg-2"]


def test_update_my_teams_saves_subgroups(db_session):
    user = _user(db_session)

    update_my_teams(
        UserTeamsUpdate(teams=["Команда А"], subgroups=["sg-1"]), user=user, db=db_session
    )

    assert user.selected_teams == ["Команда А"]
    assert user.selected_subgroups == ["sg-1"]


def test_old_client_without_subgroups_clears_selection(db_session):
    """Старый клиент шлёт только команды — выбор групп сбрасывается."""
    user = _user(db_session)
    user.selected_subgroups = ["sg-1"]
    db_session.commit()

    update_my_teams(UserTeamsUpdate(teams=["Команда А"]), user=user, db=db_session)

    assert user.selected_subgroups == []
