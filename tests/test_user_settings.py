"""Model-level tests for User.selected_period and User.analytics_columns."""

import pytest
from app.models.user import User, UserRole


@pytest.fixture
def user(db_session):
    u = User(
        email="test_settings@example.com",
        password_hash="hashed",
        display_name="Test User",
        role=UserRole.manager,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_selected_period_default_and_roundtrip(db_session, user):
    # Defaults
    assert user.selected_period == {}
    assert user.analytics_columns == []

    # Set and commit
    user.selected_period = {"year": 2026, "quarter": 2, "month": 4}
    user.analytics_columns = ["employee", "hours", "category"]
    db_session.commit()
    db_session.refresh(user)

    # Verify persistence
    assert user.selected_period == {"year": 2026, "quarter": 2, "month": 4}
    assert user.analytics_columns == ["employee", "hours", "category"]
