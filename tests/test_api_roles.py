"""Тесты API /roles."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import Employee, Role

ROLES_SEED = [
    ("analyst",    "Аналитик",    "#4db8e8", True,  0),
    ("dev",        "Программист", "#00c9c8", True,  1),
    ("qa",         "Тестировщик", "#EF9F27", True,  2),
    ("consultant", "Консультант", "#7F77DD", True,  3),
    ("other",      "Другое",      "#888780", False, 4),
]


@pytest.fixture
def db_session():
    """StaticPool in-memory DB so TestClient thread shares the same connection."""
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
def seeded_roles(db_session):
    """Seed the roles table like migration 025 does in production."""
    import uuid
    roles = []
    for code, label, color, counts, order in ROLES_SEED:
        r = Role(
            id=str(uuid.uuid4()),
            code=code,
            label=label,
            color=color,
            counts_in_planning=counts,
            is_active=True,
            sort_order=order,
        )
        db_session.add(r)
        roles.append(r)
    db_session.commit()
    return {r.code: r for r in roles}


def test_list_roles_returns_seeds(client, seeded_roles):
    r = client.get("/api/v1/roles")
    assert r.status_code == 200
    codes = [x["code"] for x in r.json()]
    assert "consultant" in codes and "analyst" in codes


def test_create_role(client, seeded_roles):
    r = client.post("/api/v1/roles", json={"code": "devops", "label": "DevOps"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "devops"


def test_patch_role_label(client, seeded_roles):
    r = client.get("/api/v1/roles").json()
    rid = [x["id"] for x in r if x["code"] == "consultant"][0]
    resp = client.patch(f"/api/v1/roles/{rid}", json={"label": "Эксперт-консультант"})
    assert resp.status_code == 200
    assert resp.json()["label"] == "Эксперт-консультант"


def test_delete_role_in_use_rejected(client, db_session, seeded_roles):
    db_session.add(
        Employee(jira_account_id="a1", display_name="X", role="consultant")
    )
    db_session.commit()
    r = client.get("/api/v1/roles").json()
    rid = [x["id"] for x in r if x["code"] == "consultant"][0]
    resp = client.delete(f"/api/v1/roles/{rid}")
    assert resp.status_code == 409
    assert "используется" in resp.json()["detail"].lower()


def test_reorder_roles(client, seeded_roles):
    r = client.get("/api/v1/roles").json()
    ids = [x["id"] for x in r]
    resp = client.post("/api/v1/roles/reorder", json={"ids": list(reversed(ids))})
    assert resp.status_code == 200


def test_create_role_duplicate_code_rejected(client, seeded_roles):
    r = client.post("/api/v1/roles", json={"code": "analyst", "label": "Аналитик 2"})
    assert r.status_code == 409


def test_patch_role_not_found(client, seeded_roles):
    resp = client.patch("/api/v1/roles/nonexistent-id", json={"label": "X"})
    assert resp.status_code == 404


def test_delete_role_not_in_use(client, seeded_roles):
    r = client.get("/api/v1/roles").json()
    # "other" role has counts_in_planning=False and no employees
    rid = [x["id"] for x in r if x["code"] == "other"][0]
    resp = client.delete(f"/api/v1/roles/{rid}")
    assert resp.status_code == 204


def test_delete_role_not_found(client, seeded_roles):
    resp = client.delete("/api/v1/roles/nonexistent-id")
    assert resp.status_code == 404
