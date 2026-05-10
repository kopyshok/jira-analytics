from app.models import UserRpPreferences, User, UserRole


def test_prefs_roundtrip(db_session):
    user = User(
        id="u-prefs-1",
        email="prefs1@test.local",
        password_hash="x",
        display_name="Prefs One",
        role=UserRole.manager,
    )
    db_session.add(user)
    db_session.commit()

    p = UserRpPreferences(
        user_id="u-prefs-1",
        hide_weekends=True,
        collapsed_initiative_ids=["i-1", "i-2"],
        view_mode="week",
        show_relay=False,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    assert p.hide_weekends is True
    assert p.collapsed_initiative_ids == ["i-1", "i-2"]
    assert p.view_mode == "week"
    assert p.show_relay is False


def test_prefs_defaults(db_session):
    """Defaults: hide_weekends=False, show_relay=True, ids=[], view_mode=None."""
    user = User(
        id="u-prefs-2",
        email="prefs2@test.local",
        password_hash="x",
        display_name="Prefs Two",
        role=UserRole.manager,
    )
    db_session.add(user)
    db_session.commit()
    p = UserRpPreferences(user_id="u-prefs-2")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    assert p.hide_weekends is False
    assert p.show_relay is True
    assert p.collapsed_initiative_ids == []
    assert p.view_mode is None
