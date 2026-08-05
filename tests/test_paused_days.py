"""Дни простоя задачи в статусе паузы — расчёт по истории статусов Jira."""

from datetime import datetime

from app.services.sync_service import paused_days_from_changes


def test_one_pause_counts_days_between_transitions():
    changes = [
        ("2026-02-19T15:31:32.242+0300", "В РАБОТЕ"),
        ("2026-03-10T10:48:44.826+0300", "Приостановлено"),
        ("2026-04-13T14:35:44.409+0300", "В РАБОТЕ"),
        ("2026-05-28T09:00:32.565+0300", "Завершен"),
    ]
    assert paused_days_from_changes(changes) == 34.0


def test_no_pause_gives_zero():
    changes = [
        ("2026-02-19T15:31:32.242+0300", "В РАБОТЕ"),
        ("2026-03-02T10:00:00.000+0300", "Завершен"),
    ]
    assert paused_days_from_changes(changes) == 0.0


def test_two_pauses_sum_up():
    changes = [
        ("2026-01-01T10:00:00.000+0300", "Приостановлено"),
        ("2026-01-03T10:00:00.000+0300", "В РАБОТЕ"),
        ("2026-02-01T10:00:00.000+0300", "Приостановлено"),
        ("2026-02-06T10:00:00.000+0300", "Завершен"),
    ]
    assert paused_days_from_changes(changes) == 7.0


def test_open_pause_counts_until_now():
    changes = [("2026-05-01T10:00:00.000+0300", "Приостановлено")]
    assert paused_days_from_changes(changes, now=datetime(2026, 5, 11, 7, 0)) == 10.0
