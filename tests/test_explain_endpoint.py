"""Tests for /explain endpoint — Task 9+10 extended shape."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def tc_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(tc_session):
    def _override():
        yield tc_session

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def base_data(tc_session):
    """Создать Employee + BacklogItem + ResourcePlan + 1 назначение и вернуть их ID."""
    from app.models import BacklogItem, Employee, ResourcePlan, ResourcePlanAssignment
    from app.models.employee_team import EmployeeTeam

    e = Employee(
        jira_account_id="jira-exp-1",
        display_name="Аналитик",
        role="analyst",
        team="T1",
        is_active=True,
    )
    tc_session.add(e)
    tc_session.commit()
    tc_session.add(EmployeeTeam(employee_id=e.id, team="T1", is_primary=True))
    tc_session.commit()

    item = BacklogItem(
        title="Инициатива А",
        estimate_analyst_hours=16,
        involvement_analyst=1.0,
        parallel_count_analyst=1,
        duration_analyst_days=2,
    )
    tc_session.add(item)
    tc_session.commit()

    plan = ResourcePlan(team="T1", quarter="Q2", year=2026, status="ready")
    tc_session.add(plan)
    tc_session.commit()

    daily = json.dumps({"2026-04-01": 4.0, "2026-04-02": 4.0})
    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="analyst",
        employee_id=e.id,
        hours_allocated=8.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        is_on_critical_path=False,
        out_of_quarter=False,
        daily_hours_json=daily,
    )
    tc_session.add(a)
    tc_session.commit()

    return plan.id, a.id, e.id, item.id


def test_explain_returns_assignment_with_daily_hours(client, base_data):
    """Ответ /explain содержит поле assignment.daily_hours из JSON-колонки."""
    plan_id, assignment_id, _, _ = base_data
    r = client.get(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}/explain"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "assignment" in body
    assert "daily_hours" in body["assignment"]
    dh = body["assignment"]["daily_hours"]
    assert dh is not None
    assert abs(dh["2026-04-01"] - 4.0) < 0.01
    assert abs(dh["2026-04-02"] - 4.0) < 0.01


def test_explain_algorithm_log_mentions_quarter_for_analyst_phase(client, base_data):
    """algorithm_log для фазы analyst упоминает квартал."""
    plan_id, assignment_id, _, _ = base_data
    r = client.get(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}/explain"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    log = body.get("algorithm_log", [])
    assert isinstance(log, list)
    assert any("квартал" in entry.lower() or "Q2" in entry for entry in log), (
        f"Ожидался лог со ссылкой на квартал, получено: {log}"
    )


def test_explain_daily_breakdown_marks_blocked_by_other(client, tc_session):
    """Если у сотрудника два назначения с пересекающимися датами, одно из них
    получает status='blocked_by_other' для дней, занятых другим."""
    from app.models import BacklogItem, Employee, ResourcePlan, ResourcePlanAssignment
    from app.models.employee_team import EmployeeTeam

    e = Employee(
        jira_account_id="jira-block-test",
        display_name="Разраб",
        role="developer",
        team="BT",
        is_active=True,
    )
    tc_session.add(e)
    tc_session.commit()
    tc_session.add(EmployeeTeam(employee_id=e.id, team="BT", is_primary=True))
    tc_session.commit()

    item1 = BacklogItem(title="Задача 1", estimate_dev_hours=8)
    item2 = BacklogItem(title="Задача 2", estimate_dev_hours=8)
    tc_session.add_all([item1, item2])
    tc_session.commit()

    plan = ResourcePlan(team="BT", quarter="Q2", year=2026, status="ready")
    tc_session.add(plan)
    tc_session.commit()

    # Назначение 1: занимает 2026-04-07 полностью
    a1 = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item1.id,
        phase="dev",
        employee_id=e.id,
        hours_allocated=8.0,
        start_date=date(2026, 4, 7),
        end_date=date(2026, 4, 7),
        daily_hours_json=json.dumps({"2026-04-07": 8.0}),
    )
    # Назначение 2: тот же день 2026-04-07, нет часов за тот день → будет blocked_by_other
    a2 = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item2.id,
        phase="dev",
        employee_id=e.id,
        hours_allocated=8.0,
        start_date=date(2026, 4, 7),
        end_date=date(2026, 4, 8),
        daily_hours_json=json.dumps({"2026-04-08": 8.0}),
    )
    tc_session.add_all([a1, a2])
    tc_session.commit()

    def _override():
        yield tc_session

    app.dependency_overrides[get_db] = _override
    try:
        c = TestClient(app)
        r = c.get(
            f"/api/v1/resource-planning/resource-plans/{plan.id}/assignments/{a2.id}/explain"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        breakdown = body.get("daily_breakdown", [])
        # Находим запись для 2026-04-07
        day_07 = next((d for d in breakdown if d["date"] == "2026-04-07"), None)
        assert day_07 is not None, f"Нет записи для 2026-04-07, breakdown={breakdown}"
        assert day_07["status"] == "blocked_by_other", (
            f"Ожидался blocked_by_other для 2026-04-07, получено: {day_07['status']}"
        )
        assert day_07["blocker_assignment_id"] == a1.id
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_explain_pre_start_shift_due_to_absence(client, tc_session):
    """Если фаза «Разработка» сдвинута из-за отпуска исполнителя, /explain
    должен:
    - вернуть pre-start строки в daily_breakdown (is_pre_start=True) с
      причиной отсутствия;
    - указать сдвиг и группу причин в algorithm_log.
    """
    from app.models import (
        Absence,
        AbsenceReason,
        BacklogItem,
        Employee,
        ResourcePlan,
        ResourcePlanAssignment,
    )
    from app.models.employee_team import EmployeeTeam

    e = Employee(
        jira_account_id="jira-vac",
        display_name="Пак Илья",
        role="developer",
        team="DT",
        is_active=True,
    )
    tc_session.add(e)
    tc_session.commit()
    tc_session.add(EmployeeTeam(employee_id=e.id, team="DT", is_primary=True))
    tc_session.commit()

    reason = AbsenceReason(code="vacation", label="Отпуск", sort_order=1, is_active=True)
    tc_session.add(reason)
    tc_session.commit()

    item = BacklogItem(
        title="ITL-342", estimate_analyst_hours=8, estimate_dev_hours=20,
        involvement_dev=0.9,
    )
    tc_session.add(item)
    tc_session.commit()

    plan = ResourcePlan(team="DT", quarter="Q2", year=2026, status="ready")
    tc_session.add(plan)
    tc_session.commit()

    # Анализ закончился 06.04.2026 (понедельник)
    a_analyst = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="analyst",
        employee_id=e.id,
        hours_allocated=8.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 6),
        daily_hours_json=json.dumps({"2026-04-06": 8.0}),
    )
    # Разработка должна была 07.04, по факту 13.04 (понедельник)
    a_dev = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=e.id,
        hours_allocated=20.0,
        start_date=date(2026, 4, 13),
        end_date=date(2026, 4, 15),
        daily_hours_json=json.dumps({
            "2026-04-13": 7.2, "2026-04-14": 7.2, "2026-04-15": 5.6,
        }),
    )
    tc_session.add_all([a_analyst, a_dev])
    tc_session.commit()

    # Отпуск 30.03–12.04 — перекрывает 07-10.04 = pre-start окно dev
    absence = Absence(
        employee_id=e.id,
        reason_id=reason.id,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 12),
    )
    tc_session.add(absence)
    tc_session.commit()

    def _override():
        yield tc_session

    app.dependency_overrides[get_db] = _override
    try:
        c = TestClient(app)
        r = c.get(
            f"/api/v1/resource-planning/resource-plans/{plan.id}/assignments/{a_dev.id}/explain"
        )
        assert r.status_code == 200, r.text
        body = r.json()

        breakdown = body.get("daily_breakdown", [])
        pre_dates = [d["date"] for d in breakdown if d.get("is_pre_start")]
        # 07-10 апреля — будни в отпуске, 11-12 — выходные
        assert "2026-04-07" in pre_dates, f"07.04 должна быть pre-start: {pre_dates}"
        assert "2026-04-10" in pre_dates, f"10.04 должна быть pre-start: {pre_dates}"
        absence_rows = [
            d for d in breakdown
            if d.get("is_pre_start") and d["status"] == "absence"
        ]
        assert absence_rows, "Хотя бы одна pre-start строка должна быть отпуском"
        assert any(d.get("absence_reason") == "Отпуск" for d in absence_rows), (
            f"absence_reason должен быть 'Отпуск': {absence_rows}"
        )

        log = body.get("algorithm_log", [])
        assert any("Сдвиг" in entry for entry in log), (
            f"Лог должен упомянуть сдвиг: {log}"
        )
        assert any("Отпуск" in entry for entry in log), (
            f"Лог должен упомянуть причину сдвига 'Отпуск': {log}"
        )
        assert any("Фактический старт" in entry for entry in log), (
            f"Лог должен упомянуть фактический старт: {log}"
        )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_explain_absences_in_window_includes_holidays(client, tc_session):
    """ProductionCalendarDay с is_workday=False и kind='holiday' попадает в absences_in_window."""
    from app.models import BacklogItem, Employee, ResourcePlan, ResourcePlanAssignment, ProductionCalendarDay
    from app.models.employee_team import EmployeeTeam
    from datetime import date

    e = Employee(
        jira_account_id="jira-hol-test",
        display_name="Тестер",
        role="qa",
        team="HT",
        is_active=True,
    )
    tc_session.add(e)
    tc_session.commit()
    tc_session.add(EmployeeTeam(employee_id=e.id, team="HT", is_primary=True))
    tc_session.commit()

    item = BacklogItem(title="QA-задача", estimate_qa_hours=24)
    tc_session.add(item)
    tc_session.commit()

    plan = ResourcePlan(team="HT", quarter="Q2", year=2026, status="ready")
    tc_session.add(plan)
    tc_session.commit()

    # Праздник 2026-05-09 (День Победы)
    holiday = ProductionCalendarDay(
        date=date(2026, 5, 9),
        is_workday=False,
        kind="holiday",
        hours=0,
    )
    tc_session.add(holiday)
    tc_session.commit()

    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="qa",
        employee_id=e.id,
        hours_allocated=24.0,
        start_date=date(2026, 5, 6),
        end_date=date(2026, 5, 12),
    )
    tc_session.add(a)
    tc_session.commit()

    def _override():
        yield tc_session

    app.dependency_overrides[get_db] = _override
    try:
        c = TestClient(app)
        r = c.get(
            f"/api/v1/resource-planning/resource-plans/{plan.id}/assignments/{a.id}/explain"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        absences = body.get("absences_in_window", [])
        holiday_entries = [x for x in absences if x.get("is_holiday")]
        assert len(holiday_entries) >= 1, f"Ожидался праздник в absences_in_window: {absences}"
        dates = [x["date_start"] for x in holiday_entries]
        assert "2026-05-09" in dates, f"Праздник 2026-05-09 не найден: {dates}"
    finally:
        app.dependency_overrides.pop(get_db, None)
