"""Tests for Role registry model."""

from app.models import Role


def test_role_defaults(db_session):
    role = Role(code="consultant", label="Консультант")
    db_session.add(role)
    db_session.commit()
    fetched = db_session.query(Role).filter_by(code="consultant").one()
    assert fetched.is_active is True
    assert fetched.counts_in_planning is True
    assert fetched.color == "#888780"
    assert fetched.sort_order == 0
