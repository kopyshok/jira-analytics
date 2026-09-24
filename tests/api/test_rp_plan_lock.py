"""Пересчёты одного плана идут по очереди: каждый сначала берёт строку плана
«на запись» (на PostgreSQL — блокировка строки до конца транзакции; на SQLite
такой блокировки нет, запрос идёт без неё).

Без очереди два одновременных пересчёта удаляли и вставляли одни и те же
назначения: на PostgreSQL — взаимная блокировка или задвоенные строки.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql

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
def plan(db_session):
    make_employee(db_session, "Аналитик", "T", role="analyst")
    make_employee(db_session, "Разработчик", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    add_item(db_session, sc, "Задача", analyst=6, dev=6)
    db_session.commit()
    ResourcePlanningService(db_session).compute_schedule(plan.id)
    return plan.id


@pytest.fixture
def statements(db_session):
    """SQL запросов сессии в порядке выполнения — как их видит PostgreSQL."""
    seen: list[tuple[str, dict]] = []

    def _on(state):
        compiled = state.statement.compile(dialect=postgresql.dialect())
        seen.append((str(compiled), compiled.params))

    event.listen(db_session, "do_orm_execute", _on)
    yield seen
    event.remove(db_session, "do_orm_execute", _on)


def _is_plan_lock(statement: tuple[str, dict], plan_id: str) -> bool:
    sql, params = statement
    return (
        "FROM resource_plans" in sql
        and "FOR UPDATE" in sql
        and plan_id in params.values()
    )


def _assignment(db_session, plan_id, phase):
    return db_session.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            ResourcePlanAssignment.phase == phase,
        )
    ).scalars().first()


def test_compute_schedule_locks_plan_first(db_session, plan, statements):
    ResourcePlanningService(db_session).compute_schedule(plan)

    assert _is_plan_lock(statements[0], plan)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda c, p, a: c.post(f"{BASE}/{p}/compute"), id="compute"),
        pytest.param(
            lambda c, p, a: c.put(
                f"{BASE}/{p}/assignments/{a}/involvement", json={"involvement_pct": 50}
            ),
            id="involvement",
        ),
        pytest.param(
            lambda c, p, a: c.patch(
                f"{BASE}/{p}/assignments/{a}", json={"start_date": "2026-01-12"}
            ),
            id="drag",
        ),
        pytest.param(
            lambda c, p, a: c.post(f"{BASE}/{p}/bulk-clear", json={"mode": "all"}),
            id="bulk-clear",
        ),
    ],
)
def test_recompute_endpoints_lock_plan_first(client, db_session, plan, statements, call):
    a_id = _assignment(db_session, plan, "dev").id
    statements.clear()

    r = call(client, plan, a_id)

    assert r.status_code == 200, r.text
    assert _is_plan_lock(statements[0], plan), statements[:3]
