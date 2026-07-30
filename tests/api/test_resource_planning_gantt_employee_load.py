"""Тепловая карта «Загрузка сотрудников по дням» обязана читать реальную
раскладку планировщика (`daily_hours_json`), а не размазывать часы задачи
поровну по всей длине бара.

Регресс: у бара 01.07–31.07 планировщик мог поставить работу только на первые
дни, а карта показывала одинаковый процент во все дни месяца — и там, где
рядом стоял второй бар, суммарно вылезала фантомная перегрузка.
"""

import json
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    ResourcePlan,
    ResourcePlanAssignment,
)
from app.models.employee_team import EmployeeTeam

TEAM = "T_LOAD"


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


DAY_HOURS = 6.0  # DEFAULT_HOURS_PER_DAY в планировщике, календарь в тесте пуст


def _seed(db_session, daily: dict | None) -> tuple[str, str]:
    """План Q3 2026 с одним разработчиком и одним баром 01.07–31.07 на 12ч."""
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="Load-dev",
        team=TEAM,
        is_active=True,
        role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True))

    item = BacklogItem(title="load-item", priority=1, estimate_dev_hours=12.0)
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team=TEAM, quarter="Q3", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    db_session.add(
        ResourcePlanAssignment(
            plan_id=plan.id,
            backlog_item_id=item.id,
            phase="dev",
            employee_id=emp.id,
            hours_allocated=12.0,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            daily_hours_json=json.dumps(daily) if daily else None,
        )
    )
    db_session.commit()
    return plan.id, emp.id


def _pct_by_date(body: dict, employee_id: str) -> dict[str, float]:
    row = next(r for r in body["employee_load"] if r["employee_id"] == employee_id)
    return {d["date"]: d["pct"] for d in row["days"]}


def test_load_follows_scheduler_daily_hours(client, db_session):
    """12ч разложены планировщиком на 01–02.07 → 100% там и 0% в остальные дни."""
    plan_id, emp_id = _seed(db_session, {"2026-07-01": 6.0, "2026-07-02": 6.0})
    resp = client.get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    assert resp.status_code == 200, resp.text
    pct = _pct_by_date(resp.json(), emp_id)

    assert pct["2026-07-01"] == pytest.approx(100.0)
    assert pct["2026-07-02"] == pytest.approx(100.0)
    # Дни внутри бара, на которые планировщик работу НЕ ставил.
    assert pct["2026-07-15"] == 0.0
    assert pct["2026-07-31"] == 0.0


def test_membership_window_reported_for_leaver(client, db_session):
    """Выбывший в середине квартала остаётся в составе, но с границей участия:
    панель фазы по ней и подписывает кандидата, и предупреждает о выходе за неё."""
    plan_id, emp_id = _seed(db_session, None)
    row = (
        db_session.query(EmployeeTeam)
        .filter(EmployeeTeam.employee_id == emp_id, EmployeeTeam.team == TEAM)
        .one()
    )
    row.left_at = date(2026, 7, 20)  # первый день ВНЕ команды
    db_session.commit()

    resp = client.get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    assert resp.status_code == 200, resp.text
    load = next(r for r in resp.json()["employee_load"] if r["employee_id"] == emp_id)
    assert load["member_from"] is None  # квартал начался, когда он уже в команде
    assert load["member_to"] == "2026-07-19"  # последний день участия


def test_legacy_bar_without_daily_spreads_over_working_days(client, db_session):
    """Легаси-бар без раскладки: 12ч поровну по 23 рабочим дням июля, не по 31
    календарному — выходные не съедают часы."""
    plan_id, emp_id = _seed(db_session, None)
    resp = client.get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    assert resp.status_code == 200, resp.text
    pct = _pct_by_date(resp.json(), emp_id)

    per_day = 12.0 / 23  # июль 2026: 23 рабочих дня
    assert pct["2026-07-15"] == pytest.approx(per_day / DAY_HOURS * 100, abs=0.1)
    assert pct["2026-07-04"] == 0.0  # суббота
