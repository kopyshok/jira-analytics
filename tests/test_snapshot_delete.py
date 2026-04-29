"""Tests for DELETE /scenarios/{sid}/revisions/{rid} — Tasks 13 + 14."""
import uuid
from datetime import datetime, date as ddate

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    PlanningScenario,
    ScenarioRevision,
    ScenarioRevisionItem,
    ScenarioCapacitySnapshot,
    ScenarioNormSnapshot,
    ScenarioAbsenceSnapshot,
    ScenarioTeamSnapshot,
    ScenarioCalendarSnapshot,
    ScenarioRulesSnapshot,
    ScenarioAllocationSnapshot,
    ScenarioAllocationBreakdownSnapshot,
    ScenarioDictionarySnapshot,
)


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _make_scenario(db: Session, scenario_id: str, status: str = "approved") -> PlanningScenario:
    sc = PlanningScenario(
        id=scenario_id, name="Test", quarter="Q2", year=2026,
        status=status, team="TeamX",
    )
    db.add(sc)
    return sc


def _make_revision(
    db: Session,
    revision_id: str,
    scenario_id: str,
    revision_number: int,
    parent_revision_id: str | None = None,
) -> ScenarioRevision:
    rev = ScenarioRevision(
        id=revision_id,
        scenario_id=scenario_id,
        revision_number=revision_number,
        approved_at=datetime(2026, 4, 1),
        parent_revision_id=parent_revision_id,
    )
    db.add(rev)
    return rev


# ---------------------------------------------------------------------------
# Task 13 tests
# ---------------------------------------------------------------------------

def test_delete_middle_revision_relinks_parent(client, db_session):
    """Delete r-2 from chain r-1→r-2→r-3: r-3.parent_revision_id becomes r-1."""
    sc_id = "sc-del-1"
    r1_id, r2_id, r3_id = "rev-del-1", "rev-del-2", "rev-del-3"

    _make_scenario(db_session, sc_id)
    _make_revision(db_session, r1_id, sc_id, 1, parent_revision_id=None)
    _make_revision(db_session, r2_id, sc_id, 2, parent_revision_id=r1_id)
    _make_revision(db_session, r3_id, sc_id, 3, parent_revision_id=r2_id)
    # r-2 has a capacity snapshot
    db_session.add(ScenarioCapacitySnapshot(
        id=_uid(), revision_id=r2_id,
        employee_name="Alice", year=2026, month=4,
        norm_hours=160.0, available_hours=160.0, backlog_pool_hours=80.0,
        snapshot_taken_at=datetime(2026, 4, 1),
    ))
    db_session.commit()

    resp = client.delete(f"/api/v1/planning/scenarios/{sc_id}/revisions/{r2_id}")
    assert resp.status_code == 204

    db_session.expire_all()

    # r-2 gone
    assert db_session.get(ScenarioRevision, r2_id) is None

    # r-3 now points to r-1
    r3 = db_session.get(ScenarioRevision, r3_id)
    assert r3 is not None
    assert r3.parent_revision_id == r1_id

    # capacity snapshot for r-2 gone
    snap = db_session.query(ScenarioCapacitySnapshot).filter_by(revision_id=r2_id).first()
    assert snap is None


def test_delete_last_remaining_revision_drafts_scenario(client, db_session):
    """Deleting the only revision of an approved scenario → status becomes 'draft'."""
    sc_id = "sc-del-2"
    r_id = "rev-del-only"

    _make_scenario(db_session, sc_id, status="approved")
    _make_revision(db_session, r_id, sc_id, 1)
    db_session.commit()

    resp = client.delete(f"/api/v1/planning/scenarios/{sc_id}/revisions/{r_id}")
    assert resp.status_code == 204

    db_session.expire_all()

    sc = db_session.get(PlanningScenario, sc_id)
    assert sc.status == "draft"


def test_delete_unknown_revision_returns_404(client, db_session):
    """DELETE on a non-existent revision_id returns 404."""
    sc_id = "sc-del-3"
    _make_scenario(db_session, sc_id)
    db_session.commit()

    resp = client.delete(f"/api/v1/planning/scenarios/{sc_id}/revisions/nonexistent-rev")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 14: cascade verification
# ---------------------------------------------------------------------------

def test_delete_cascades_all_v2_snapshot_tables(client, db_session):
    """After DELETE all 9 cascade snapshot tables are empty for that revision_id."""
    sc_id = "sc-del-cascade"
    rev_id = "rev-del-cascade"

    _make_scenario(db_session, sc_id)
    _make_revision(db_session, rev_id, sc_id, 1)

    alloc_snap_id = _uid()

    db_session.add(ScenarioTeamSnapshot(
        id=_uid(), revision_id=rev_id, display_name="TeamX", hours_per_day=8.0,
    ))
    db_session.add(ScenarioCalendarSnapshot(
        id=_uid(), revision_id=rev_id, date=ddate(2026, 4, 1),
        hours=8.0, is_workday=True, kind="regular",
    ))
    db_session.add(ScenarioRulesSnapshot(
        id=_uid(), revision_id=rev_id, work_type_label="Проекты", pct_of_norm=30.0,
    ))
    db_session.add(ScenarioDictionarySnapshot(
        id=_uid(), revision_id=rev_id, kind="role", label="Аналитик",
    ))
    db_session.add(ScenarioAllocationSnapshot(
        id=alloc_snap_id, revision_id=rev_id, title="Initiative A",
    ))
    db_session.add(ScenarioAllocationBreakdownSnapshot(
        id=_uid(), revision_id=rev_id,
        allocation_id=alloc_snap_id, month=4, role="analyst", hours=40.0,
    ))
    db_session.add(ScenarioNormSnapshot(
        id=_uid(), revision_id=rev_id, employee_name="Alice",
        year=2026, month=4, work_type_label="Проекты", norm_hours=160.0,
    ))
    db_session.add(ScenarioAbsenceSnapshot(
        id=_uid(), revision_id=rev_id, employee_name="Alice",
        start_date=ddate(2026, 4, 7), end_date=ddate(2026, 4, 11), hours_total=40.0,
    ))
    db_session.add(ScenarioCapacitySnapshot(
        id=_uid(), revision_id=rev_id,
        employee_name="Alice", year=2026, month=4,
        norm_hours=160.0, available_hours=160.0, backlog_pool_hours=80.0,
        snapshot_taken_at=datetime(2026, 4, 1),
    ))
    db_session.add(ScenarioRevisionItem(
        id=_uid(), revision_id=rev_id,
        backlog_item_name="Initiative A", action="included",
    ))
    db_session.commit()

    resp = client.delete(f"/api/v1/planning/scenarios/{sc_id}/revisions/{rev_id}")
    assert resp.status_code == 204

    db_session.expire_all()

    assert db_session.query(ScenarioTeamSnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioCalendarSnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioRulesSnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioDictionarySnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioAllocationSnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioAllocationBreakdownSnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioNormSnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioAbsenceSnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioCapacitySnapshot).filter_by(revision_id=rev_id).count() == 0
    assert db_session.query(ScenarioRevisionItem).filter_by(revision_id=rev_id).count() == 0
