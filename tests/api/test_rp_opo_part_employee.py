"""Смена исполнителя одной части ОПЭ без закреплённой даты.

ОПЭ — две параллельные части с одним номером: у аналитика и у разработчика.
Часть различается ролью исполнителя — так её делят расчёт и диаграмма.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, make_employee, make_plan

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


@pytest.fixture
def opo_plan(db_session):
    """Два аналитика и два разработчика; у задачи ОПЭ 8 ч — по 4 ч на часть."""
    an = make_employee(db_session, "Аналитик", "T", role="analyst")
    an2 = make_employee(db_session, "Аналитик 2", "T", role="analyst")
    dev = make_employee(db_session, "Разработчик", "T")
    dev2 = make_employee(db_session, "Разработчик 2", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Запуск", analyst=6, dev=6)
    item.estimate_opo_hours = 8.0
    db_session.commit()
    ResourcePlanningService(db_session).compute_schedule(plan.id)
    return {"plan": plan.id, "analysts": {an.id, an2.id}, "devs": {dev.id, dev2.id}}


def _opo(db_session, plan_id):
    db_session.expire_all()
    return {
        r.employee_id: r
        for r in db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.phase == "opo",
            )
        ).scalars()
    }


@pytest.mark.parametrize("part", ["devs", "analysts"])
def test_change_employee_of_one_opo_part(client, db_session, opo_plan, part):
    """Раньше повторное чтение после пересчёта находило обе части и падало с
    ошибкой сервера, а выбранный человек терялся."""
    t = opo_plan
    parts = _opo(db_session, t["plan"])
    [old] = set(parts) & t[part]
    [other_part_emp] = set(parts) - {old}
    [new] = t[part] - {old}

    r = client.patch(
        f"{BASE}/{t['plan']}/assignments/{parts[old].id}", json={"employee_id": new}
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["phase"], body["employee_id"]) == ("opo", new)
    assert body["pinned_employee"] is True
    after = _opo(db_session, t["plan"])
    assert set(after) == {new, other_part_emp}
    assert after[new].hours_allocated == 4.0
    # Закреп — только у правленой части; вторая осталась за расчётом.
    assert after[other_part_emp].pinned_employee is False
    assert after[other_part_emp].hours_allocated == 4.0


def test_opo_part_pin_survives_next_recompute(client, db_session, opo_plan):
    t = opo_plan
    parts = _opo(db_session, t["plan"])
    [old] = set(parts) & t["devs"]
    [new] = t["devs"] - {old}
    r = client.patch(
        f"{BASE}/{t['plan']}/assignments/{parts[old].id}", json={"employee_id": new}
    )
    assert r.status_code == 200, r.text

    ResourcePlanningService(db_session).compute_schedule(t["plan"])

    after = _opo(db_session, t["plan"])
    assert new in after and after[new].pinned_employee is True
