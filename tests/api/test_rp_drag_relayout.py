"""Перетаскивание фазы: часы раскладываются с новой даты по свободным окнам."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

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


def test_drag_onto_other_team_work_lands_on_free_days(client, db_session):
    """Шутов состоит в A и B; B занимает его 05–06.01. Фазу плана A тянут
    на 05.01 — часы ложатся на 07–08.01: поверх чужой работы нельзя."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=12), e,
         {"2026-01-05": 6.0, "2026-01-06": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    item = add_item(db_session, sc_a, "Работа A", dev=12)
    row = book(db_session, plan_a, item, e, {"2026-01-12": 6.0, "2026-01-13": 6.0})
    db_session.commit()

    r = client.patch(
        f"{BASE}/{plan_a.id}/assignments/{row.id}",
        json={"start_date": "2026-01-05", "end_date": "2026-01-06"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["daily_hours"] == {"2026-01-07": 6.0, "2026-01-08": 6.0}
    assert (body["start_date"], body["end_date"]) == ("2026-01-07", "2026-01-08")
    assert body["pinned_start"] is True


def test_drag_one_opo_part_keeps_the_other(client, db_session):
    """ОПЭ — две параллельные части (аналитик и разработчик). Перетащили часть
    разработчика — часть аналитика остаётся в плане со своими часами."""
    from sqlalchemy import select

    from app.models import PlanConflict, ResourcePlanAssignment
    from app.services.resource_planning_service import ResourcePlanningService

    an = make_employee(db_session, "Аналитик", "T", role="analyst")
    dev = make_employee(db_session, "Разработчик", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Запуск", analyst=6, dev=6)
    item.estimate_opo_hours = 8.0
    db_session.commit()
    ResourcePlanningService(db_session).compute_schedule(plan.id)

    def _opo():
        db_session.expire_all()
        return {
            r.employee_id: r
            for r in db_session.execute(
                select(ResourcePlanAssignment).where(
                    ResourcePlanAssignment.plan_id == plan.id,
                    ResourcePlanAssignment.phase == "opo",
                )
            ).scalars()
        }

    dev_part = _opo()[dev.id]
    r = client.patch(
        f"{BASE}/{plan.id}/assignments/{dev_part.id}", json={"start_date": "2026-01-20"}
    )

    assert r.status_code == 200, r.text
    assert r.json()["daily_hours"] == {"2026-01-20": 4.0}
    parts = _opo()
    assert set(parts) == {an.id, dev.id}
    assert parts[an.id].pinned_start is False
    assert parts[an.id].hours_allocated == 4.0
    assert db_session.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan.id, PlanConflict.type == "UNPLACED_HOURS"
        )
    ).scalars().all() == []
