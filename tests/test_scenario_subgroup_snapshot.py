"""Утверждение сценария замораживает группу сотрудника.

Именно поэтому истории приписок в реестре не нужно: снапшот помнит,
кто в какой группе был на момент утверждения.
"""

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
    Team,
    TeamSubgroup,
)
from app.services.snapshot_writer import SnapshotWriter


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def ctx(db_session: Session):
    """Команда с двумя группами: по человеку в каждой + сценарий с ревизией."""
    team = Team(id="t-1", name="T1", has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(id="sg-1", team_id="t-1", name="Расчёты", sort_order=1)
    integ = TeamSubgroup(id="sg-2", team_id="t-1", name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    db_session.add_all(
        [
            Employee(
                id="e-1", jira_account_id="j1", display_name="Иванов И.",
                role="dev", is_active=True,
            ),
            Employee(
                id="e-2", jira_account_id="j2", display_name="Петров П.",
                role="dev", is_active=True,
            ),
        ]
    )
    db_session.add_all(
        [
            EmployeeTeam(
                id="et-1", employee_id="e-1", team="T1", is_primary=True,
                subgroup_id="sg-1",
            ),
            EmployeeTeam(
                id="et-2", employee_id="e-2", team="T1", is_primary=True,
                subgroup_id="sg-2",
            ),
        ]
    )
    sc = PlanningScenario(
        id="s-1", name="Q2", year=2026, quarter="Q2", team="T1", status="draft"
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-1", scenario_id="s-1", revision_number=1, approved_at=datetime.utcnow()
    )
    db_session.add(rev)
    db_session.commit()

    SnapshotWriter(db_session).write_team_snapshot(revision=rev, scenario=sc)
    db_session.commit()
    return {"scenario": sc, "revision": rev, "calc": calc, "integ": integ}


def test_snapshot_freezes_subgroup(db_session: Session, ctx):
    rows = (
        db_session.query(ScenarioTeamSnapshot).filter_by(revision_id="r-1").all()
    )

    assert {r.subgroup_name for r in rows} == {"Расчёты", "Интеграции"}


def test_snapshot_survives_employee_move(db_session: Session, ctx):
    row = db_session.query(EmployeeTeam).filter_by(employee_id="e-1").one()
    row.subgroup_id = "sg-2"
    db_session.commit()

    frozen = (
        db_session.query(ScenarioTeamSnapshot)
        .filter_by(revision_id="r-1", employee_id="e-1")
        .one()
    )

    assert frozen.subgroup_name == "Расчёты"


def test_team_without_subgroups_leaves_snapshot_empty(db_session: Session, ctx):
    """Признак выключен — снапшот выглядит как до правки."""
    db_session.query(Team).filter_by(id="t-1").one().has_subgroups = False
    rev2 = ScenarioRevision(
        id="r-2", scenario_id="s-1", revision_number=2, approved_at=datetime.utcnow()
    )
    db_session.add(rev2)
    db_session.commit()

    SnapshotWriter(db_session).write_team_snapshot(
        revision=rev2, scenario=ctx["scenario"]
    )
    db_session.commit()

    rows = db_session.query(ScenarioTeamSnapshot).filter_by(revision_id="r-2").all()
    assert len(rows) == 2
    assert all(r.subgroup_name is None for r in rows)
