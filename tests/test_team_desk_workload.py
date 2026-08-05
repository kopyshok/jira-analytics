"""Очередь работы разработчика в часах и рабочих днях."""
import uuid
from datetime import date

from app.models import Absence, AbsenceReason, Employee
from app.services.team_desk.workload import queue_for_developers

# среда — окно из 7 дней даёт 5 рабочих
START = date(2026, 8, 5)


def test_queue_counts_only_queue_statuses(db_session):
    rows = [
        {"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": 8.0},
        {"developer_id": "acc-1", "status": "К выполнению", "est_hours": 4.0},
        {"developer_id": "acc-1", "status": "Ожидает тестирования", "est_hours": 40.0},
        {"developer_id": "acc-1", "status": "ГОТОВО", "est_hours": 16.0},
    ]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 12.0
    assert result["acc-1"]["queue_days"] == 1.5


def test_issues_without_estimate_counted_separately(db_session):
    rows = [
        {"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": None},
        {"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": 6.0},
    ]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 6.0
    assert result["acc-1"]["without_estimate"] == 1


def test_overload_when_queue_exceeds_available(db_session):
    rows = [{"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": 80.0}]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["available_hours"] == 40.0
    assert result["acc-1"]["overloaded"] is True


def test_available_hours_drop_during_absence(db_session):
    reason = AbsenceReason(
        id=str(uuid.uuid4()), code="vacation", label="Отпуск",
        is_planned=True, color="#3b82f6",
    )
    emp = Employee(
        id=str(uuid.uuid4()), jira_account_id="acc-1", display_name="Шутов Сергей"
    )
    db_session.add_all([reason, emp])
    db_session.flush()
    db_session.add(
        Absence(
            id=str(uuid.uuid4()),
            employee_id=emp.id,
            reason_id=reason.id,
            start_date=START,
            end_date=date(2026, 8, 11),
        )
    )
    db_session.commit()

    rows = [{"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": 8.0}]
    result = queue_for_developers(
        db_session, rows, employee_by_account={"acc-1": emp.id}, start=START, days=7
    )
    assert result["acc-1"]["available_hours"] == 0
    assert result["acc-1"]["queue_days"] is None
