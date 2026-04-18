from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.connectors.production_calendar_client import CalendarDayRaw
from app.models import ProductionCalendarDay
from app.services.production_calendar_service import ProductionCalendarService


def test_is_workday_falls_back_to_weekday(db_session):
    svc = ProductionCalendarService(db_session)
    assert svc.is_workday(date(2026, 6, 15)) is True    # Monday
    assert svc.is_workday(date(2026, 6, 20)) is False   # Saturday


def test_is_workday_uses_db_when_present(db_session):
    db_session.add(ProductionCalendarDay(
        date=date(2026, 1, 1), is_workday=False, kind="holiday",
        note="НГ", source="xmlcalendar",
    ))
    db_session.commit()
    svc = ProductionCalendarService(db_session)
    assert svc.is_workday(date(2026, 1, 1)) is False


def test_workdays_in_range_map_accounts_for_holidays(db_session):
    db_session.add(ProductionCalendarDay(
        date=date(2026, 1, 1), is_workday=False, kind="holiday",
        note="НГ", source="xmlcalendar",
    ))
    db_session.commit()
    svc = ProductionCalendarService(db_session)
    m = svc.workdays_in_range_map(date(2026, 1, 1), date(2026, 1, 2))
    assert m[date(2026, 1, 1)] is False


@pytest.mark.asyncio
async def test_sync_year_skips_manual_rows(db_session):
    db_session.add(ProductionCalendarDay(
        date=date(2026, 5, 9), is_workday=True, kind="manual_note",
        note="user edit", source="manual",
    ))
    db_session.commit()

    fake_days = [
        CalendarDayRaw(date=date(2026, 5, 9), is_workday=False, kind="holiday"),
        CalendarDayRaw(date=date(2026, 1, 1), is_workday=False, kind="holiday"),
    ]
    with patch(
        "app.connectors.production_calendar_client.ProductionCalendarClient.fetch_year",
        new=AsyncMock(return_value=fake_days),
    ):
        svc = ProductionCalendarService(db_session)
        stats = await svc.sync_year(2026, overwrite_manual=False)

    assert stats.skipped_manual == 1
    db_session.expire_all()
    row = db_session.query(ProductionCalendarDay).filter_by(
        date=date(2026, 5, 9)
    ).one()
    assert row.source == "manual"
    assert row.is_workday is True
