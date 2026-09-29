"""Утверждение сценария замораживает группу сотрудника.

Именно поэтому истории приписок в реестре не нужно: снапшот помнит,
кто в какой группе был на момент утверждения.
"""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
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
from tests.subgroup_fixtures import share


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
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


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
            EmployeeTeam(id="et-1", employee_id="e-1", team="T1", is_primary=True),
            EmployeeTeam(id="et-2", employee_id="e-2", team="T1", is_primary=True),
        ]
    )
    db_session.add_all([
        share("e-1", "T1", "sg-1"),
        share("e-2", "T1", "sg-2"),
    ])
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
    # Перевод оформлен датированной записью (как сделал бы SubgroupShareService),
    # а не переписыванием базовой строки распределения.
    db_session.add(share("e-1", "T1", "sg-2", valid_from=date(2026, 5, 15)))
    db_session.commit()

    frozen = (
        db_session.query(ScenarioTeamSnapshot)
        .filter_by(revision_id="r-1", employee_id="e-1")
        .one()
    )

    assert frozen.subgroup_name == "Расчёты"


def test_snapshot_records_split_distribution(db_session: Session):
    """Сотрудник разделён между группами весь квартал — подпись с долями."""
    team = Team(id="t-2", name="T2", has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(id="sg-3", team_id="t-2", name="Расчёты", sort_order=1)
    integ = TeamSubgroup(id="sg-4", team_id="t-2", name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    db_session.add(
        Employee(
            id="e-3", jira_account_id="j3", display_name="Сидоров С.",
            role="dev", is_active=True,
        )
    )
    db_session.add(
        EmployeeTeam(id="et-3", employee_id="e-3", team="T2", is_primary=True)
    )
    db_session.add_all([
        share("e-3", "T2", "sg-3", percent=60),
        share("e-3", "T2", "sg-4", percent=40),
    ])
    sc = PlanningScenario(
        id="s-2", name="Q2", year=2026, quarter="Q2", team="T2", status="draft"
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-3", scenario_id="s-2", revision_number=1, approved_at=datetime.utcnow()
    )
    db_session.add(rev)
    db_session.commit()

    SnapshotWriter(db_session).write_team_snapshot(revision=rev, scenario=sc)
    db_session.commit()

    row = (
        db_session.query(ScenarioTeamSnapshot)
        .filter_by(revision_id="r-3", employee_id="e-3")
        .one()
    )
    assert row.subgroup_name == "Расчёты 60% · Интеграции 40%"


def test_capacity_diff_shows_group_divergence_after_transfer(client, db_session, ctx):
    """Перевод после утверждения не меняет сценарий, но виден плашкой расхождения."""
    sc = ctx["scenario"]
    sc.status = "approved"
    db_session.add(share("e-1", "T1", "sg-2", valid_from=date(2026, 5, 15)))
    db_session.commit()

    resp = client.get(f"/api/v1/planning/scenarios/{sc.id}/capacity-diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_changes"] is True
    diff = next(e for e in data["changed_employees"] if e["employee_id"] == "e-1")
    assert diff["subgroup_before"] == "Расчёты"
    assert diff["subgroup_after"] == "Расчёты до 15.05 · Интеграции с 15.05"


def test_capacity_diff_no_group_divergence_when_division_added_after_approval(
    client, db_session
):
    """Деление включили после утверждения — снимок без групп, расхождения нет."""
    team = Team(id="t-3", name="T3", has_subgroups=False)
    db_session.add(team)
    db_session.add(
        Employee(
            id="e-4", jira_account_id="j4", display_name="Кузнецов К.",
            role="dev", is_active=True,
        )
    )
    db_session.add(
        EmployeeTeam(id="et-4", employee_id="e-4", team="T3", is_primary=True)
    )
    sc = PlanningScenario(
        id="s-3", name="Q2", year=2026, quarter="Q2", team="T3", status="approved"
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-4", scenario_id="s-3", revision_number=1, approved_at=datetime.utcnow()
    )
    db_session.add(rev)
    db_session.commit()

    SnapshotWriter(db_session).write_team_snapshot(revision=rev, scenario=sc)
    db_session.commit()

    # Деление включили и перевели сотрудника уже после утверждения.
    team.has_subgroups = True
    sg = TeamSubgroup(id="sg-5", team_id="t-3", name="Группа", sort_order=1)
    db_session.add(sg)
    db_session.flush()
    db_session.add(share("e-4", "T3", "sg-5"))
    db_session.commit()

    resp = client.get(f"/api/v1/planning/scenarios/{sc.id}/capacity-diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_changes"] is False
    assert data["changed_employees"] == []


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
