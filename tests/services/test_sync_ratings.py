"""Sync rating-полей + planned dates из Jira custom fields."""
import pytest
from app.services.sync_service import _to_int_rating, _parse_jira_date
from datetime import datetime


def test_to_int_rating_valid_range():
    assert _to_int_rating(5) == 5
    assert _to_int_rating("4") == 4
    assert _to_int_rating("3.0") == 3
    assert _to_int_rating({"value": "2"}) == 2
    assert _to_int_rating(1) == 1


def test_to_int_rating_out_of_range_returns_none():
    assert _to_int_rating(0) is None
    assert _to_int_rating(6) is None
    assert _to_int_rating("invalid") is None
    assert _to_int_rating(None) is None


def test_parse_jira_date_iso():
    result = _parse_jira_date("2026-02-12")
    assert result is not None
    assert result.year == 2026 and result.month == 2 and result.day == 12


def test_parse_jira_date_empty():
    assert _parse_jira_date(None) is None
    assert _parse_jira_date("") is None
