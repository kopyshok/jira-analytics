from app.models import InvolvementDefault
from app.services.involvement_default_service import lookup_involvement


def _add(db, team, role, year, q, val):
    db.add(InvolvementDefault(
        team=team, role=role, effective_year=year, effective_quarter=q, involvement=val,
    ))


def test_lookup_picks_latest_effective_on_or_before(db_session):
    _add(db_session, "A", "analyst", 2026, 1, 0.8)
    _add(db_session, "A", "analyst", 2026, 3, 0.9)
    db_session.commit()
    # Q1, Q2 -> 0.8; Q3, Q4 -> 0.9
    assert lookup_involvement(db_session, "A", "analyst", 2026, 1) == 0.8
    assert lookup_involvement(db_session, "A", "analyst", 2026, 2) == 0.8
    assert lookup_involvement(db_session, "A", "analyst", 2026, 3) == 0.9
    assert lookup_involvement(db_session, "A", "analyst", 2027, 1) == 0.9


def test_lookup_none_before_first_effective(db_session):
    _add(db_session, "A", "analyst", 2026, 3, 0.9)
    db_session.commit()
    assert lookup_involvement(db_session, "A", "analyst", 2026, 1) is None


def test_lookup_team_and_role_isolated(db_session):
    _add(db_session, "A", "analyst", 2026, 1, 0.8)
    db_session.commit()
    assert lookup_involvement(db_session, "B", "analyst", 2026, 1) is None
    assert lookup_involvement(db_session, "A", "dev", 2026, 1) is None
