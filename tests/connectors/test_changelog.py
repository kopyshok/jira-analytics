"""История изменений Jira DC: смены статуса, смена категории, полнота."""
from app.connectors.changelog import (
    category_changed_at,
    is_complete,
    status_changes,
    status_only,
)

CATEGORIES = {"1": "new", "3": "indeterminate", "10205": "indeterminate", "10001": "done"}


def _status(frm: str, to: str, frm_name: str = "", to_name: str = "") -> dict:
    return {"field": "status", "fieldtype": "jira", "from": frm, "fromString": frm_name,
            "to": to, "toString": to_name}


def _history(created: str, *items: dict) -> dict:
    return {"id": created, "created": created, "items": list(items)}


T1 = "2026-09-12T08:00:00.000+0000"
T2 = "2026-09-20T10:00:00.000+0000"
T3 = "2026-10-01T12:30:00.000+0000"


def test_status_changes_sorted_by_time():
    changelog = {"total": 3, "histories": [
        _history(T3, _status("10205", "10001", "Тестирование", "Готово")),
        _history(T1, _status("1", "3", "Открыт", "В работе")),
        _history(T2, {"field": "assignee", "from": "a", "to": "b"}),
    ]}
    assert status_changes(changelog) == [(T1, "В работе"), (T3, "Готово")]


def test_category_change_ignores_move_inside_category():
    changelog = {"total": 2, "histories": [
        _history(T1, _status("1", "3", "Открыт", "В работе")),
        _history(T2, _status("3", "10205", "В работе", "Тестирование")),
    ]}
    assert category_changed_at(changelog, CATEGORIES) == T1


def test_category_change_takes_last_one():
    changelog = {"total": 3, "histories": [
        _history(T3, _status("10205", "10001")),
        _history(T1, _status("1", "3")),
        _history(T2, _status("3", "10205")),
    ]}
    assert category_changed_at(changelog, CATEGORIES) == T3


def test_unknown_status_counts_as_change():
    changelog = {"total": 1, "histories": [_history(T2, _status("3", "777"))]}
    assert category_changed_at(changelog, CATEGORIES) == T2
    assert category_changed_at(changelog, None) == T2


def test_no_status_history_gives_none():
    changelog = {"total": 1, "histories": [_history(T1, {"field": "assignee", "from": "a", "to": "b"})]}
    assert category_changed_at(changelog, CATEGORIES) is None
    assert category_changed_at(None, CATEGORIES) is None
    assert status_changes(None) == []


def test_is_complete():
    assert is_complete({"total": 3, "histories": [_history(T1), _history(T2), _history(T3)]}) is True
    assert is_complete({"total": 5, "histories": [_history(T1)]}) is False
    assert is_complete({"histories": [_history(T1)]}) is True
    assert is_complete(None) is True


def test_mixed_offsets_ordered_by_real_time():
    early = "2026-09-20T12:00:00.000+0300"  # 09:00 UTC
    late = "2026-09-20T10:00:00.000+0000"  # 10:00 UTC, но строка меньше
    changelog = {"total": 2, "histories": [
        _history(late, _status("3", "10001", "", "Готово")),
        _history(early, _status("1", "3", "", "В работе")),
    ]}
    assert status_changes(changelog) == [(early, "В работе"), (late, "Готово")]
    assert category_changed_at(changelog, CATEGORIES) == late


def test_missing_or_bad_created_never_last():
    changelog = {"total": 3, "histories": [
        {"items": [_status("3", "10001")]},
        _history("мусор", _status("3", "10001")),
        _history(T1, _status("1", "3")),
    ]}
    assert category_changed_at(changelog, CATEGORIES) == T1


def test_items_none_and_non_dict_item():
    changelog = {"total": 2, "histories": [
        {"created": T1, "items": None},
        _history(T2, "x", None, _status("1", "3", "", "В работе")),
    ]}
    assert status_changes(changelog) == [(T2, "В работе")]
    assert category_changed_at(changelog, CATEGORIES) == T2


def test_status_only_keeps_entries_and_counts():
    other = {"field": "assignee", "from": "a", "to": "b"}
    changelog = {"startAt": 0, "maxResults": 2, "total": 5, "histories": [
        {**_history(T1, other, _status("1", "3", "Открыт", "В работе")), "author": {"key": "U1"}},
        _history(T2, other),
    ]}
    trimmed = status_only(changelog)
    assert trimmed == {"startAt": 0, "maxResults": 2, "total": 5, "histories": [
        {"created": T1, "items": [_status("1", "3", "Открыт", "В работе")]},
        {"created": T2, "items": []},
    ]}
    # Записи истории не выброшены — неполнота по-прежнему видна.
    assert is_complete(trimmed) is False
    assert status_only(None) is None
