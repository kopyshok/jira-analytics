import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


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


def test_crud_involvement_defaults(client):
    r = client.post("/api/v1/planning/involvement-defaults", json={
        "team": "A", "role": "analyst",
        "effective_year": 2026, "effective_quarter": 1, "involvement": 0.8,
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    r = client.get("/api/v1/planning/involvement-defaults?team=A")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.patch(f"/api/v1/planning/involvement-defaults/{rid}", json={"involvement": 0.9})
    assert r.status_code == 200
    assert r.json()["involvement"] == 0.9

    # дубль scope -> 409
    r = client.post("/api/v1/planning/involvement-defaults", json={
        "team": "A", "role": "analyst",
        "effective_year": 2026, "effective_quarter": 1, "involvement": 0.5,
    })
    assert r.status_code == 409

    r = client.delete(f"/api/v1/planning/involvement-defaults/{rid}")
    assert r.status_code == 204
    r = client.get("/api/v1/planning/involvement-defaults?team=A")
    assert r.json() == []


def test_reject_unknown_role(client):
    r = client.post("/api/v1/planning/involvement-defaults", json={
        "team": "A", "role": "wizard",
        "effective_year": 2026, "effective_quarter": 1, "involvement": 0.8,
    })
    assert r.status_code == 422
