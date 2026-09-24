"""«Доступно» в посуточной разбивке фазы — дневной потолок планировщика:
не больше дня календаря и не больше 8 ч × вовлечённость × параллельность."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from tests.services.xteam_factory import add_item, book, make_employee, make_plan

BASE = "/api/v1/resource-planning/resource-plans"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    "involvement, parallel, available",
    [
        (None, None, 6.0),  # день календаря
        (0.5, None, 4.0),  # 8 × 0.5, а не 6 × 0.5
        (0.9, None, 6.0),  # 8 × 0.9 = 7.2 — больше дня календаря
        (0.5, 2, 6.0),  # 8 × 0.5 × 2 = 8 — больше дня календаря
    ],
)
def test_explain_available_is_planner_day_cap(
    client, db_session, involvement, parallel, available
):
    e = make_employee(db_session, "Разработчик", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Работа", dev=12)
    item.involvement_dev = involvement
    item.parallel_count_dev = parallel
    row = book(db_session, plan, item, e, {"2026-01-05": 4.0, "2026-01-06": 4.0,
                                          "2026-01-07": 4.0})
    db_session.commit()

    r = client.get(f"{BASE}/{plan.id}/assignments/{row.id}/explain")

    assert r.status_code == 200, r.text
    days = {d["date"]: d for d in r.json()["daily_breakdown"]}
    assert days["2026-01-05"]["available_hours"] == available
