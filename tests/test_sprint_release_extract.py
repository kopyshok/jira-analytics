"""Спринт и релиз задачи: какой спринт считается последним."""
from app.services.sync_service import _extract_release, _extract_sprints


def test_active_sprint_wins_over_later_closed():
    extra = {
        "cf": [
            {"name": "S1", "state": "closed", "startDate": "2026-01-01T00:00:00.000Z"},
            {"name": "S2", "state": "active", "startDate": "2026-02-01T00:00:00.000Z"},
        ]
    }
    assert _extract_sprints(extra, "cf") == ("S2", ["S1", "S2"])


def test_without_active_takes_latest_by_start_date():
    extra = {
        "cf": [
            {"name": "S2", "state": "closed", "startDate": "2026-02-01T00:00:00.000Z"},
            {"name": "S1", "state": "closed", "startDate": "2026-01-01T00:00:00.000Z"},
        ]
    }
    assert _extract_sprints(extra, "cf") == ("S2", ["S1", "S2"])


def test_no_field_or_empty():
    assert _extract_sprints({}, None) == (None, [])
    assert _extract_sprints({"cf": []}, "cf") == (None, [])


def test_release_is_first_fix_version():
    assert _extract_release({"fixVersions": [{"name": "MFO OS| 30.09.26"}]}) == "MFO OS| 30.09.26"
    assert _extract_release({"fixVersions": []}) is None
    assert _extract_release({}) is None
