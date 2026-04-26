import pytest
from datetime import date
from app.utils.period import quarter_to_dates

def test_full_quarter():
    start, end = quarter_to_dates(2026, 2)
    assert start == date(2026, 4, 1)
    assert end == date(2026, 6, 30)

def test_quarter_with_month():
    start, end = quarter_to_dates(2026, 2, month=5)
    assert start == date(2026, 5, 1)
    assert end == date(2026, 5, 31)

def test_q1():
    start, end = quarter_to_dates(2026, 1)
    assert start == date(2026, 1, 1)
    assert end == date(2026, 3, 31)

def test_q4():
    start, end = quarter_to_dates(2026, 4)
    assert start == date(2026, 10, 1)
    assert end == date(2026, 12, 31)

def test_invalid_month_raises():
    with pytest.raises(ValueError):
        quarter_to_dates(2026, 2, month=1)  # январь не в Q2
