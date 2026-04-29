"""Тесты SnapshotWriter: создание снапшотов при approve сценария."""
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Employee,
    EmployeeTeam,
    PlanningScenario,
    ScenarioRevision,
    ScenarioTeamSnapshot,
)
from app.services.snapshot_writer import SnapshotWriter


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
def team_setup(db_session: Session):
    """Команда из 2 активных сотрудников + сценарий + одна ревизия."""
    e1 = Employee(
        id="e-1", jira_account_id="j1", display_name="Иванов И.",
        role="analyst", is_active=True,
    )
    e2 = Employee(
        id="e-2", jira_account_id="j2", display_name="Петров П.",
        role="dev", is_active=True,
    )
    db_session.add_all([e1, e2])
    db_session.add_all([
        EmployeeTeam(id="et-1", employee_id="e-1", team="T1", is_primary=True),
        EmployeeTeam(id="et-2", employee_id="e-2", team="T1", is_primary=True),
    ])
    sc = PlanningScenario(
        id="s-1", name="Q2", year=2026, quarter="Q2", team="T1",
        status="draft", external_qa_hours=None,
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-1", scenario_id="s-1", revision_number=1,
        approved_at=datetime.utcnow(),
    )
    db_session.add(rev)
    db_session.commit()
    return {"scenario": sc, "revision": rev}


def test_write_team_snapshot_copies_active_team_members(
    db_session: Session, team_setup
):
    """write_team_snapshot копирует display_name/role/is_active каждого сотрудника команды."""
    writer = SnapshotWriter(db_session)
    writer.write_team_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    rows = (
        db_session.query(ScenarioTeamSnapshot)
        .filter_by(revision_id="r-1")
        .order_by(ScenarioTeamSnapshot.display_name)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].display_name == "Иванов И."
    assert rows[0].role == "analyst"
    assert rows[1].display_name == "Петров П."
    assert rows[1].role == "dev"
    assert all(r.is_active for r in rows)


def test_write_team_snapshot_no_team_does_nothing(db_session: Session):
    """Сценарий без team → ничего не записывается."""
    sc = PlanningScenario(
        id="s-x", name="X", year=2026, quarter="Q2", team=None,
        status="draft",
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-x", scenario_id="s-x", revision_number=1,
        approved_at=datetime.utcnow(),
    )
    db_session.add(rev)
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_team_snapshot(revision=rev, scenario=sc)
    db_session.commit()

    rows = db_session.query(ScenarioTeamSnapshot).filter_by(revision_id="r-x").all()
    assert rows == []


def test_write_team_snapshot_empty_team_does_nothing(db_session: Session):
    """Команда без членов → ничего не записывается."""
    sc = PlanningScenario(
        id="s-y", name="Y", year=2026, quarter="Q2", team="EmptyTeam",
        status="draft",
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-y", scenario_id="s-y", revision_number=1,
        approved_at=datetime.utcnow(),
    )
    db_session.add(rev)
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_team_snapshot(revision=rev, scenario=sc)
    db_session.commit()

    rows = db_session.query(ScenarioTeamSnapshot).filter_by(revision_id="r-y").all()
    assert rows == []
