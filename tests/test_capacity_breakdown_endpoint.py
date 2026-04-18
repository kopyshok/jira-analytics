from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee


def test_breakdown_endpoint_returns_list(db_session):
    # Pin :memory: SQLite connection so the endpoint sees the same schema.
    db_session.query(Employee).first()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v1/capacity/team/category-breakdown",
            params={"year": 2026, "quarter": 1},
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
