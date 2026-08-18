"""Очередь работы разработчика в часах и рабочих днях."""
import uuid
from datetime import date

from app.models import Absence, AbsenceReason, Employee
from app.services.team_desk.workload import queue_for_developers

# среда — окно из 7 дней даёт 5 рабочих
START = date(2026, 8, 5)


def _row(status, est, fact=0.0, standalone=True, dev="acc-1"):
    return {
        "developer_id": dev,
        "status": status,
        "est_hours": est,
        "fact_hours": fact,
        "is_standalone": standalone,
    }


def test_queue_counts_only_queue_statuses(db_session):
    rows = [
        _row("В РАБОТЕ", 8.0),
        _row("К выполнению", 4.0),
        _row("Ожидает тестирования", 40.0),
        _row("ГОТОВО", 16.0),
    ]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 12.0
    assert result["acc-1"]["queue_days"] == 1.5


def test_subtasks_do_not_inflate_queue(db_session):
    """Подзадача — декомпозиция родителя, её оценка в очередь второй раз не идёт."""
    rows = [
        _row("К выполнению", 40.0),
        _row("К выполнению", 8.0, standalone=False),
        _row("К выполнению", 8.0, standalone=False),
    ]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 40.0


def test_queue_takes_remainder_of_started_issue(db_session):
    """Задача в работе даёт остаток: оценка минус уже списанные часы."""
    rows = [
        _row("В РАБОТЕ", 40.0, fact=30.0),
        _row("В РАБОТЕ", 8.0, fact=20.0),   # перерасход в минус не уводит
    ]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 10.0


def test_issues_without_estimate_counted_separately(db_session):
    rows = [
        _row("В РАБОТЕ", None),
        _row("В РАБОТЕ", 6.0),
    ]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 6.0
    assert result["acc-1"]["without_estimate"] == 1


def test_overload_when_queue_exceeds_available(db_session):
    rows = [_row("В РАБОТЕ", 80.0)]
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

    rows = [_row("В РАБОТЕ", 8.0)]
    result = queue_for_developers(
        db_session, rows, employee_by_account={"acc-1": emp.id}, start=START, days=7
    )
    assert result["acc-1"]["available_hours"] == 0
    assert result["acc-1"]["queue_days"] is None


def _queue_row(status, est, fact=0.0, assigned=True, rate=None, dev="acc-1"):
    row = _row(status, est, fact, dev=dev)
    row["assigned_to_owner"] = assigned
    row["daily_rate"] = rate
    return row


def test_assigned_line_counts_only_own_assignee(db_session):
    """Задача на РП висит в общей очереди, но не в очереди к выполнению."""
    rows = [
        _queue_row("К выполнению", 10.0, assigned=True),
        _queue_row("К выполнению", 6.0, assigned=False),
    ]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 16.0
    assert result["acc-1"]["assigned_hours"] == 10.0
    assert result["acc-1"]["assigned_days"] == 1.2


def test_without_estimate_counted_per_line(db_session):
    rows = [
        _queue_row("К выполнению", None, assigned=True),
        _queue_row("К выполнению", None, assigned=False),
    ]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["without_estimate"] == 2
    assert result["acc-1"]["assigned_without_estimate"] == 1


def test_rubber_issue_takes_daily_rate_for_window(db_session):
    """Резиновая задача: норма в день × дней настройки, а не весь остаток."""
    rows = [_queue_row("В РАБОТЕ", 80.0, rate=2.0)]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 10.0
    assert result["acc-1"]["assigned_hours"] == 10.0


def test_rubber_issue_never_exceeds_remainder(db_session):
    """Остаток меньше нормы за период — в очередь идёт остаток."""
    rows = [_queue_row("В РАБОТЕ", 80.0, fact=76.0, rate=2.0)]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 4.0


def test_rubber_days_setting_changes_queue(db_session):
    """Настройка «дней в очередь» меняет вклад резиновой задачи."""
    from app.services.team_desk.config import defaults, save_config

    cfg = defaults()
    cfg.thresholds["rubber_days"] = 2
    save_config(db_session, cfg)
    rows = [_queue_row("В РАБОТЕ", 80.0, rate=2.0)]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 4.0


def test_rubber_issue_without_estimate_uses_daily_rate(db_session):
    """У длинной задачи общей оценки обычно нет — вклад задаёт дневная норма."""
    rows = [_queue_row("К выполнению", None, fact=20.0, rate=5.0)]
    result = queue_for_developers(
        db_session, rows, employee_by_account={}, start=START, days=7
    )
    assert result["acc-1"]["queue_hours"] == 25.0
    # Норма задана — задача уже даёт часы, во «без оценки» её считать нельзя.
    assert result["acc-1"]["without_estimate"] == 0
