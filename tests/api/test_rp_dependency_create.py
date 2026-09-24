"""Связь между задачами ресурсного плана создаётся и возвращает свой id."""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import PlanItemDependency
from tests.services.xteam_factory import add_item, make_plan


def test_create_dependency_returns_saved_link(testclient_db_session):
    db = testclient_db_session
    sc, plan = make_plan(db, "T")
    first = add_item(db, sc, "Первая", dev=6)
    second = add_item(db, sc, "Вторая", dev=6)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post(
            f"/api/v1/resource-planning/resource-plans/{plan.id}/dependencies",
            json={"from_item_id": first.id, "to_item_id": second.id},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 201, r.text
    assert db.get(PlanItemDependency, r.json()["id"]) is not None
