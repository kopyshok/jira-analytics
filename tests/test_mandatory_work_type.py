"""Tests for MandatoryWorkType model."""
from app.models import MandatoryWorkType


def test_subtracts_from_pool_default(db_session):
    wt = MandatoryWorkType(code="x", label="X")
    db_session.add(wt)
    db_session.commit()
    assert wt.subtracts_from_pool is True
