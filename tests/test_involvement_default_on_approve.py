import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem, InvolvementDefault, PlanningScenario, ScenarioAllocation,
)
from app.services.involvement_default_service import effective_for_phase, team_defaults


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
        app.dependency_overrides.pop(get_db, None)


def _scenario_with_item(db, team="A", year=2026, quarter="Q1",
                        involvement_analyst=None):
    sc = PlanningScenario(name="S", team=team, year=year, quarter=quarter, status="draft")
    db.add(sc)
    item = BacklogItem(title="I", team=team, involvement_analyst=involvement_analyst)
    db.add(item)
    db.flush()
    db.add(ScenarioAllocation(
        scenario_id=sc.id, backlog_item_id=item.id, included_flag=True,
    ))
    db.commit()
    return sc, item


def test_approve_does_not_write_reference_into_task(client, db_session):
    """Утверждение не вписывает справочник в задачу: записанный процент стал бы
    «своим» у задачи и перекрыл бы последующие правки справочника."""
    sc, item = _scenario_with_item(db_session, involvement_analyst=None)
    db_session.add(InvolvementDefault(
        team="A", role="analyst", effective_year=2026, effective_quarter=1, involvement=0.8,
    ))
    db_session.commit()

    r = client.post(f"/api/v1/planning/scenarios/{sc.id}/approve")
    assert r.status_code == 200, r.text

    db_session.refresh(item)
    assert item.involvement_analyst is None


def test_approve_does_not_overwrite_existing(client, db_session):
    sc, item = _scenario_with_item(db_session, involvement_analyst=0.5)
    db_session.add(InvolvementDefault(
        team="A", role="analyst", effective_year=2026, effective_quarter=1, involvement=0.8,
    ))
    db_session.commit()

    r = client.post(f"/api/v1/planning/scenarios/{sc.id}/approve")
    assert r.status_code == 200, r.text

    db_session.refresh(item)
    assert item.involvement_analyst == 0.5


def test_reference_change_after_approve_reaches_phase(client, db_session):
    """Правка справочника после утверждения доходит до фазы задачи."""
    sc, item = _scenario_with_item(db_session, involvement_analyst=None)
    ref = InvolvementDefault(
        team="A", role="analyst", effective_year=2026, effective_quarter=1, involvement=0.7,
    )
    db_session.add(ref)
    db_session.commit()
    client.post(f"/api/v1/planning/scenarios/{sc.id}/approve")

    r = client.patch(f"/api/v1/planning/involvement-defaults/{ref.id}", json={"involvement": 0.9})
    assert r.status_code == 200, r.text

    db_session.refresh(item)
    defaults = team_defaults(db_session, "A", 2026, 1)
    assert effective_for_phase(item, "analyst", defaults) == 0.9
