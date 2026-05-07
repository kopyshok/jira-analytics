"""Outlier detection — deterministic rules per theme."""
import pytest
from datetime import date

from app.services.work_type_outlier_detector import (
    detect_outliers_for_theme, OutlierCandidate,
)


def _issue(issue_id: str, *, key: str = "PROJ-1", summary: str = "x",
           hours: float = 4.0, distinct_workers: int = 1,
           days_in_progress: int = 2, reopen_count: int = 0,
           worklog_count: int = 1, is_done: bool = True) -> dict:
    return {
        "issue_id": issue_id, "key": key, "summary": summary,
        "hours": hours, "distinct_workers": distinct_workers,
        "days_in_progress": days_in_progress, "reopen_count": reopen_count,
        "worklog_count": worklog_count, "is_done": is_done,
    }


def test_high_hours_above_p85_and_threshold():
    """Issue with hours > P85 and >= 16h should be an outlier."""
    issues = [_issue(f"i{i}", hours=4.0) for i in range(10)]
    issues.append(_issue("ix", key="PROJ-99", hours=80.0, distinct_workers=3, days_in_progress=10, worklog_count=15))
    out = detect_outliers_for_theme({}, theme_issues=issues)
    keys = [o.issue_key for o in out]
    assert "PROJ-99" in keys
    o99 = next(o for o in out if o.issue_key == "PROJ-99")
    assert o99.reason == "high_hours"
    assert o99.value == 80.0


def test_high_hours_under_16h_threshold_not_flagged():
    """Even if above P85, must be >= 16h to be 'high_hours'."""
    issues = [_issue(f"i{i}", hours=2.0) for i in range(10)]
    issues.append(_issue("ix", key="PROJ-99", hours=8.0))
    out = detect_outliers_for_theme({}, theme_issues=issues)
    assert not any(o.issue_key == "PROJ-99" and o.reason == "high_hours" for o in out)


def test_many_workers_outlier():
    """More than 5 distinct workers triggers many_workers."""
    iss = _issue("i1", key="PROJ-7", distinct_workers=7)
    out = detect_outliers_for_theme({}, theme_issues=[iss])
    assert any(o.issue_key == "PROJ-7" and o.reason == "many_workers" for o in out)


def test_stale_outlier_only_when_not_done():
    """In-progress >14 days AND not done → stale."""
    iss_open = _issue("i1", key="PROJ-OPEN", days_in_progress=20, is_done=False)
    iss_closed = _issue("i2", key="PROJ-CLOSED", days_in_progress=20, is_done=True)
    out = detect_outliers_for_theme({}, theme_issues=[iss_open, iss_closed])
    keys_stale = [o.issue_key for o in out if o.reason == "stale"]
    assert "PROJ-OPEN" in keys_stale
    assert "PROJ-CLOSED" not in keys_stale


def test_reopens_outlier_when_count_ge_3():
    """reopen_count >= 3 triggers many_reopens. (Feature inactive until changelog tracking added.)"""
    iss = _issue("i1", key="PROJ-R", reopen_count=4)
    out = detect_outliers_for_theme({}, theme_issues=[iss])
    assert any(o.issue_key == "PROJ-R" and o.reason == "many_reopens" for o in out)


def test_dedup_and_top_5_limit():
    """Same issue can match multiple rules; dedup by (issue, reason) and cap at 5 by value desc."""
    issues = [
        _issue("a", key="PROJ-A", hours=200.0, distinct_workers=10, days_in_progress=30, is_done=False, reopen_count=5),
    ]
    out = detect_outliers_for_theme({}, theme_issues=issues)
    # a single issue produced 4 reasons; all 4 should appear, deduped by reason
    reasons = sorted(o.reason for o in out)
    assert reasons == ["high_hours", "many_reopens", "many_workers", "stale"]
    # Sorted by value desc → 200 > 30 > 10 > 5
    values = [o.value for o in out]
    assert values == sorted(values, reverse=True)


def test_empty_input_returns_empty():
    out = detect_outliers_for_theme({}, theme_issues=[])
    assert out == []


def test_no_outliers_when_all_quiet():
    issues = [_issue(f"i{i}", hours=4.0) for i in range(10)]
    out = detect_outliers_for_theme({}, theme_issues=issues)
    assert out == []
