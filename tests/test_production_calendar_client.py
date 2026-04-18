"""Тесты клиента производственного календаря xmlcalendar.ru."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.connectors.production_calendar_client import (
    CalendarDayRaw,
    ProductionCalendarClient,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "xmlcalendar_2026.json"


@pytest.mark.asyncio
async def test_fetch_year_parses_fixture():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    class _Resp:
        def json(self):
            return fixture

        def raise_for_status(self):
            return None

    with patch(
        "app.connectors.production_calendar_client.httpx.AsyncClient.get",
        new=AsyncMock(return_value=_Resp()),
    ):
        client = ProductionCalendarClient()
        days = await client.fetch_year(2026)

    assert all(isinstance(d, CalendarDayRaw) for d in days)

    # Jan 1 is always a holiday / non-working
    jan_1 = next(d for d in days if d.date.month == 1 and d.date.day == 1)
    assert jan_1.is_workday is False
    assert jan_1.kind == "holiday"

    # Jan 9 2026 carries "+" — weekend moved here, non-working
    jan_9 = next(d for d in days if d.date.month == 1 and d.date.day == 9)
    assert jan_9.is_workday is False
    assert jan_9.kind == "weekend"

    # Apr 30 2026 carries "*" — shortened pre-holiday workday (still working)
    apr_30 = next(d for d in days if d.date.month == 4 and d.date.day == 30)
    assert apr_30.is_workday is True
    assert apr_30.kind == "preholiday"


@pytest.mark.asyncio
async def test_fetch_year_handles_years_wrapper():
    """Некоторые источники оборачивают в {"years": [...]}. Парсер должен это переварить."""

    wrapped = {
        "years": [
            {
                "year": 2030,
                "months": [
                    {"month": 1, "days": "1,2,3"},
                ],
            }
        ]
    }

    class _Resp:
        def json(self):
            return wrapped

        def raise_for_status(self):
            return None

    with patch(
        "app.connectors.production_calendar_client.httpx.AsyncClient.get",
        new=AsyncMock(return_value=_Resp()),
    ):
        client = ProductionCalendarClient()
        days = await client.fetch_year(2030)

    assert len(days) == 3
    assert all(d.is_workday is False and d.kind == "holiday" for d in days)


def test_parse_skips_malformed_tokens():
    payload = {
        "year": 2026,
        "months": [{"month": 1, "days": "1,abc,,2+,x*,3"}],
    }
    days = list(ProductionCalendarClient._parse(2026, payload))
    # 1, 2+, 3 — three valid tokens; "abc", "", "x*" dropped
    assert {(d.date.day, d.kind) for d in days} == {
        (1, "holiday"),
        (2, "weekend"),
        (3, "holiday"),
    }


def test_parse_handles_apostrophe_as_preholiday():
    """Апостроф — исторический маркер сокращённого предпраздничного дня."""
    payload = {
        "year": 2026,
        "months": [{"month": 12, "days": "31'"}],
    }
    days = list(ProductionCalendarClient._parse(2026, payload))
    assert len(days) == 1
    assert days[0].is_workday is True
    assert days[0].kind == "preholiday"
