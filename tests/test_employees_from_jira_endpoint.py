from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee


def test_from_jira_creates_employee(db_session):
    db_session.query(Employee).first()  # pin connection for in-memory SQLite

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/employees/from-jira",
            json={
                "jira_account_id": "a_new",
                "display_name": "Новый",
                "email": "new@example.com",
                "is_active": True,
                "avatar_url": "https://example.com/new.png",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["jira_account_id"] == "a_new"
    assert body["is_active"] is True
    assert db_session.query(Employee).filter_by(jira_account_id="a_new").count() == 1


def test_from_jira_reactivates_existing(db_session):
    existing = Employee(
        id="e1", jira_account_id="a_old", display_name="Old",
        email="o@example.com", is_active=False,
    )
    db_session.add(existing)
    db_session.commit()
    db_session.query(Employee).first()  # pin connection for in-memory SQLite

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/employees/from-jira",
            json={
                "jira_account_id": "a_old",
                "display_name": "Old Renamed",
                "email": "o@example.com",
                "is_active": True,
                "avatar_url": None,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    db_session.query(Employee).first()  # re-pin after endpoint commit
    db_session.refresh(existing)
    assert existing.is_active is True
    assert existing.display_name == "Old Renamed"
