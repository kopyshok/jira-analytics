import calendar
from datetime import date

_QUARTER_MONTHS: dict[int, tuple[int, int, int]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}


def quarter_to_dates(year: int, quarter: int, month: int | None = None) -> tuple[date, date]:
    """Конвертирует год/квартал (и опционально месяц) в начальную и конечную даты."""
    if quarter not in _QUARTER_MONTHS:
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    q_months = _QUARTER_MONTHS[quarter]
    if month is not None:
        if month not in q_months:
            raise ValueError(f"month {month} is not in Q{quarter} (months: {q_months})")
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
    else:
        start = date(year, q_months[0], 1)
        last_month = q_months[-1]
        end = date(year, last_month, calendar.monthrange(year, last_month)[1])
    return start, end


def current_quarter() -> tuple[int, int]:
    """Возвращает (year, quarter) для текущей даты."""
    today = date.today()
    for q, months in _QUARTER_MONTHS.items():
        if today.month in months:
            return today.year, q
    raise RuntimeError("unreachable")
