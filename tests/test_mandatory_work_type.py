"""Tests for MandatoryWorkType model."""
from app.models import MandatoryWorkType


def test_subtracts_from_pool_default(db_session):
    wt = MandatoryWorkType(code="x", label="X")
    db_session.add(wt)
    db_session.commit()
    assert wt.subtracts_from_pool is True


def test_is_system_default_false(db_session):
    wt = MandatoryWorkType(code="x_default", label="X")
    db_session.add(wt)
    db_session.commit()
    assert wt.is_system is False


def test_is_system_can_be_true(db_session):
    wt = MandatoryWorkType(code="x_system", label="X", is_system=True)
    db_session.add(wt)
    db_session.commit()
    assert wt.is_system is True
