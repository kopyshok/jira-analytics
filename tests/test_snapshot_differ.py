"""Тесты SnapshotDiffer: сравнение двух ревизий по срезам."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register all models before create_all
from app.database import Base, get_db
from app.main import app
from app.models import (
    PlanningScenario,
    ScenarioAllocationSnapshot,
    ScenarioCapacitySnapshot,
    ScenarioNormSnapshot,
    ScenarioRevision,
    ScenarioRulesSnapshot,
    ScenarioTeamSnapshot,
)
from app.services.snapshot_differ import SnapshotDiffer


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> Session:  # type: ignore[return]
    """In-memory SQLite session backed by StaticPool (shared with TestClient)."""
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
def client(db: Session) -> TestClient:
    """TestClient that shares the same in-memory DB as the `db` fixture."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Shared data fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def two_revs_with_snapshots(db: Session):
    """Сценарий s-1 с двумя ревизиями + allocation/team/rules снапшоты."""
    sc = PlanningScenario(
        id="s-1", name="Q2", year=2026, quarter="Q2", team="T", status="approved"
    )
    db.add(sc)
    rev1 = ScenarioRevision(
        id="r-1", scenario_id="s-1", revision_number=1,
        approved_at=datetime(2026, 4, 1), algo_version="v2",
    )
    rev2 = ScenarioRevision(
        id="r-2", scenario_id="s-1", revision_number=2,
        approved_at=datetime(2026, 4, 15), parent_revision_id="r-1", algo_version="v2",
    )
    db.add_all([rev1, rev2])

    # allocations: b removed, c added, a changed
    db.add(ScenarioAllocationSnapshot(
        revision_id="r-1", allocation_id="a", title="A", estimate_analyst_hours=10.0,
    ))
    db.add(ScenarioAllocationSnapshot(
        revision_id="r-1", allocation_id="b", title="B", estimate_analyst_hours=20.0,
    ))
    db.add(ScenarioAllocationSnapshot(
        revision_id="r-2", allocation_id="a", title="A", estimate_analyst_hours=15.0,
    ))
    db.add(ScenarioAllocationSnapshot(
        revision_id="r-2", allocation_id="c", title="C", estimate_analyst_hours=5.0,
    ))

    # team: e-2 removed, e-3 added, e-1 role changed
    db.add(ScenarioTeamSnapshot(
        revision_id="r-1", employee_id="e-1", display_name="A", role="analyst",
    ))
    db.add(ScenarioTeamSnapshot(
        revision_id="r-1", employee_id="e-2", display_name="B", role="dev",
    ))
    db.add(ScenarioTeamSnapshot(
        revision_id="r-2", employee_id="e-1", display_name="A", role="consultant",
    ))
    db.add(ScenarioTeamSnapshot(
        revision_id="r-2", employee_id="e-3", display_name="C", role="dev",
    ))

    # rules: analyst/wt-1 changed, dev/wt-2 added
    db.add(ScenarioRulesSnapshot(
        revision_id="r-1", role="analyst", work_type_id="wt-1",
        work_type_label="L1", pct_of_norm=30.0,
    ))
    db.add(ScenarioRulesSnapshot(
        revision_id="r-2", role="analyst", work_type_id="wt-1",
        work_type_label="L1", pct_of_norm=35.0,
    ))
    db.add(ScenarioRulesSnapshot(
        revision_id="r-2", role="dev", work_type_id="wt-2",
        work_type_label="L2", pct_of_norm=10.0,
    ))
    db.commit()


# ---------------------------------------------------------------------------
# Task 15: allocations / team / rules
# ---------------------------------------------------------------------------


def test_diff_allocations(db: Session, two_revs_with_snapshots):
    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="r-2", against_revision_id="r-1")

    alloc = diff["allocations"]
    assert sorted(a["allocation_id"] for a in alloc["added"]) == ["c"]
    assert sorted(a["allocation_id"] for a in alloc["removed"]) == ["b"]
    assert len(alloc["changed"]) == 1
    assert alloc["changed"][0]["allocation_id"] == "a"
    assert alloc["changed"][0]["estimate_analyst_hours"] == {"before": 10.0, "after": 15.0}


def test_diff_team(db: Session, two_revs_with_snapshots):
    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="r-2", against_revision_id="r-1")

    team = diff["team"]
    assert sorted(e["employee_id"] for e in team["added"]) == ["e-3"]
    assert sorted(e["employee_id"] for e in team["removed"]) == ["e-2"]
    assert len(team["role_changed"]) == 1
    assert team["role_changed"][0]["employee_id"] == "e-1"
    assert team["role_changed"][0]["role"] == {"before": "analyst", "after": "consultant"}


def test_diff_rules(db: Session, two_revs_with_snapshots):
    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="r-2", against_revision_id="r-1")

    rules = diff["rules"]
    assert len(rules["added"]) == 1
    assert rules["added"][0]["role"] == "dev"
    assert len(rules["changed"]) == 1
    assert rules["changed"][0]["pct_of_norm"] == {"before": 30.0, "after": 35.0}


# ---------------------------------------------------------------------------
# Task 16: external_qa / capacity / endpoint
# ---------------------------------------------------------------------------


def test_diff_external_qa(db: Session):
    sc = PlanningScenario(
        id="s-x", name="X", year=2026, quarter="Q2", team="T",
        status="approved", external_qa_hours=600.0,
    )
    db.add(sc)
    rev1 = ScenarioRevision(
        id="rx-1", scenario_id="s-x", revision_number=1, approved_at=datetime(2026, 4, 1),
    )
    rev2 = ScenarioRevision(
        id="rx-2", scenario_id="s-x", revision_number=2,
        approved_at=datetime(2026, 4, 15), parent_revision_id="rx-1",
    )
    db.add_all([rev1, rev2])
    # rev1: 3 × 70 = 210
    for month in (4, 5, 6):
        db.add(ScenarioNormSnapshot(
            revision_id="rx-1", is_external=True, role="qa",
            year=2026, month=month, work_type_label="L", norm_hours=70.0, employee_name="ext",
        ))
    # rev2: 3 × 105 = 315
    for month in (4, 5, 6):
        db.add(ScenarioNormSnapshot(
            revision_id="rx-2", is_external=True, role="qa",
            year=2026, month=month, work_type_label="L", norm_hours=105.0, employee_name="ext",
        ))
    db.commit()

    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="rx-2", against_revision_id="rx-1")
    assert diff["external_qa_total_hours"] == {"before": 210.0, "after": 315.0}


def test_diff_capacity_per_emp_month(db: Session):
    sc = PlanningScenario(
        id="s-y", name="Y", year=2026, quarter="Q2", team="T", status="approved",
    )
    db.add(sc)
    rev1 = ScenarioRevision(
        id="ry-a", scenario_id="s-y", revision_number=1, approved_at=datetime(2026, 4, 1),
    )
    rev2 = ScenarioRevision(
        id="ry-b", scenario_id="s-y", revision_number=2,
        approved_at=datetime(2026, 4, 15), parent_revision_id="ry-a",
    )
    db.add_all([rev1, rev2])
    db.add(ScenarioCapacitySnapshot(
        revision_id="ry-a", employee_id="e", employee_name="x",
        year=2026, month=4, norm_hours=160, available_hours=160,
        gross_hours=160, absence_hours=0, snapshot_taken_at=datetime.utcnow(),
    ))
    db.add(ScenarioCapacitySnapshot(
        revision_id="ry-b", employee_id="e", employee_name="x",
        year=2026, month=4, norm_hours=160, available_hours=120,
        gross_hours=160, absence_hours=40, snapshot_taken_at=datetime.utcnow(),
    ))
    db.commit()

    differ = SnapshotDiffer(db)
    diff = differ.diff(revision_id="ry-b", against_revision_id="ry-a")
    cap = diff["capacity_changes"]
    assert len(cap) == 1
    assert cap[0]["employee_id"] == "e"
    assert cap[0]["month"] == 4
    assert cap[0]["available_hours"] == {"before": 160.0, "after": 120.0}


def test_diff_endpoint(client: TestClient, db: Session, two_revs_with_snapshots):
    resp = client.get("/api/v1/planning/scenarios/s-1/revisions/r-2/diff")
    assert resp.status_code == 200
    data = resp.json()
    assert "allocations" in data
    assert "team" in data
    assert "rules" in data
    # default against = parent_revision_id (r-1)
    assert any(a["allocation_id"] == "c" for a in data["allocations"]["added"])


def test_diff_endpoint_explicit_against(client: TestClient, db: Session, two_revs_with_snapshots):
    resp = client.get("/api/v1/planning/scenarios/s-1/revisions/r-2/diff?against=r-1")
    assert resp.status_code == 200
