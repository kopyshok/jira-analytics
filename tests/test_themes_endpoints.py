"""Themes API: list active, create, update, archive, restore, merge."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.mandatory_work_type import MandatoryWorkType


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


@pytest.fixture
def wt(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопр", sort_order=1)
    db_session.add(wt)
    db_session.commit()
    return wt


def test_list_themes_empty(client, wt):
    r = client.get(f"/api/v1/themes?work_type_id={wt.id}")
    assert r.status_code == 200
    assert r.json() == {"themes": [], "candidates": []}


def test_create_and_list(client, wt):
    r = client.post("/api/v1/themes", json={
        "work_type_id": wt.id, "name": "Ошибки обмена", "description": "", "color": "#00c9c8",
    })
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    r = client.get(f"/api/v1/themes?work_type_id={wt.id}")
    assert r.status_code == 200
    themes = r.json()["themes"]
    assert len(themes) == 1 and themes[0]["id"] == tid


def test_update_rename(client, wt):
    r = client.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Old"})
    tid = r.json()["id"]
    r = client.patch(f"/api/v1/themes/{tid}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


def test_archive_then_restore(client, wt):
    r = client.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "X"})
    tid = r.json()["id"]
    assert client.post(f"/api/v1/themes/{tid}/archive").status_code == 200
    listing = client.get(f"/api/v1/themes?work_type_id={wt.id}").json()
    assert listing["themes"] == []  # archived hidden from default list
    listing_all = client.get(f"/api/v1/themes?work_type_id={wt.id}&include_archived=true").json()
    assert any(t["id"] == tid for t in listing_all["themes"])
    assert client.post(f"/api/v1/themes/{tid}/restore").status_code == 200


def test_merge(client, wt):
    r1 = client.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Src"})
    r2 = client.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Dst"})
    sid, did = r1.json()["id"], r2.json()["id"]
    r = client.post(f"/api/v1/themes/{sid}/merge", json={"target_theme_id": did})
    assert r.status_code == 200
    assert r.json()["id"] == did


def test_duplicate_name_409(client, wt):
    client.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Dup"})
    r = client.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Dup"})
    assert r.status_code == 409
