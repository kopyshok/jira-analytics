"""Тесты агрегатора конфликтов."""

import uuid
from datetime import date, datetime

import pytest

from app.models import Employee
from app.models.employee_team import EmployeeTeam
from app.services.conflict_aggregator import aggregate_conflicts


def test_overload_aggregated_into_date_range(db_session):
    """10 daily OVERLOAD_HIGH → один conflict с window_start..window_end."""
    raw = [
        {
            "type": "OVERLOAD_HIGH",
            "severity": "critical",
            "employee_id": "e1",
            "assignment_id": "a1",
            "metric_value": 130.0,
            "window_start": date(2026, 4, d),
            "window_end": date(2026, 4, d),
        }
        for d in range(1, 11)
    ]
    aggregated = aggregate_conflicts(raw)
    assert len(aggregated) == 1
    assert aggregated[0]["window_start"] == date(2026, 4, 1)
    assert aggregated[0]["window_end"] == date(2026, 4, 10)
    assert aggregated[0]["metric_value"] == 130.0


def test_overload_message_uses_employee_name(db_session):
    """Шаблон сообщения подставляет имя сотрудника + диапазон в человеческом виде."""
    e = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="Шутов Алексей",
        team="T_AGG",
        is_active=True,
        role="analyst",
    )
    db_session.add(e)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=e.id, team="T_AGG", is_primary=True))
    db_session.commit()

    raw = [
        {
            "type": "OVERLOAD_HIGH",
            "severity": "critical",
            "employee_id": e.id,
            "assignment_id": "a1",
            "metric_value": 140.0,
            "window_start": date(2026, 4, 1),
            "window_end": date(2026, 4, 10),
        }
    ]
    out = aggregate_conflicts(raw, db_session=db_session)
    msg = out[0]["message"]
    assert "Шутов" in msg
    assert "1–10 апреля" in msg
    assert "140" in msg


def test_non_consecutive_overload_kept_separate(db_session):
    """Между событиями gap > 1 день → два отдельных конфликта."""
    raw = [
        {
            "type": "OVERLOAD_MED",
            "severity": "warning",
            "employee_id": "e1",
            "assignment_id": "a1",
            "metric_value": 115.0,
            "window_start": date(2026, 4, 1),
            "window_end": date(2026, 4, 1),
        },
        {
            "type": "OVERLOAD_MED",
            "severity": "warning",
            "employee_id": "e1",
            "assignment_id": "a1",
            "metric_value": 115.0,
            "window_start": date(2026, 4, 5),
            "window_end": date(2026, 4, 5),
        },
    ]
    out = aggregate_conflicts(raw)
    assert len(out) == 2


def test_aggregator_handles_datetime_window(db_session):
    """Если window_start/end — datetime, агрегация работает по date."""
    raw = [
        {
            "type": "OVERLOAD_LIGHT",
            "severity": "warning",
            "employee_id": "e1",
            "assignment_id": "a1",
            "metric_value": 105.0,
            "window_start": datetime(2026, 4, 1, 0, 0),
            "window_end": datetime(2026, 4, 1, 0, 0),
        },
        {
            "type": "OVERLOAD_LIGHT",
            "severity": "warning",
            "employee_id": "e1",
            "assignment_id": "a1",
            "metric_value": 108.0,
            "window_start": datetime(2026, 4, 2, 0, 0),
            "window_end": datetime(2026, 4, 2, 0, 0),
        },
    ]
    out = aggregate_conflicts(raw)
    assert len(out) == 1
    assert out[0]["metric_value"] == 108.0
