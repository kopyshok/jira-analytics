"""Тесты для RcpspLeveler — пост-CPM выравнивание перегрузок."""

from datetime import date

from app.services.rcpsp_leveler import RcpspLeveler


def test_leveler_empty_assignments_returns_no_events():
    leveler = RcpspLeveler()
    events = leveler.level(assignments=[], availability={}, q_end=date(2026, 6, 30))
    assert events == []
