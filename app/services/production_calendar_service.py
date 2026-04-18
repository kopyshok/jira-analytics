"""Сервис производственного календаря РФ.

Источник данных — таблица ``production_calendar_day``. Неуказанные дни
интерпретируются как обычные (будни по правилу ``weekday() < 5``).
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.connectors.production_calendar_client import ProductionCalendarClient
from app.models import ProductionCalendarDay


@dataclass
class SyncStats:
    inserted: int
    updated: int
    skipped_manual: int


class ProductionCalendarService:
    """Чтение и обновление производственного календаря."""

    def __init__(
        self,
        db: Session,
        client: Optional[ProductionCalendarClient] = None,
    ) -> None:
        self.db = db
        self.client = client or ProductionCalendarClient()

    def is_workday(self, d: date) -> bool:
        row = self.db.get(ProductionCalendarDay, d)
        if row is not None:
            return bool(row.is_workday)
        return d.weekday() < 5

    def workdays_in_range_map(self, start: date, end: date) -> dict[date, bool]:
        if end < start:
            return {}
        rows = (
            self.db.query(ProductionCalendarDay)
            .filter(
                ProductionCalendarDay.date >= start,
                ProductionCalendarDay.date <= end,
            )
            .all()
        )
        return {r.date: bool(r.is_workday) for r in rows}

    async def sync_year(
        self, year: int, overwrite_manual: bool = False
    ) -> SyncStats:
        days = await self.client.fetch_year(year)
        inserted = updated = skipped_manual = 0

        for raw in days:
            existing = self.db.get(ProductionCalendarDay, raw.date)
            if existing and existing.source == "manual" and not overwrite_manual:
                skipped_manual += 1
                continue
            if existing is None:
                self.db.add(ProductionCalendarDay(
                    date=raw.date,
                    is_workday=raw.is_workday,
                    kind=raw.kind,
                    note=raw.note,
                    source="xmlcalendar",
                    synced_at=datetime.utcnow(),
                ))
                inserted += 1
            else:
                existing.is_workday = raw.is_workday
                existing.kind = raw.kind
                existing.note = raw.note
                existing.source = "xmlcalendar"
                existing.synced_at = datetime.utcnow()
                updated += 1

        self.db.commit()
        return SyncStats(
            inserted=inserted, updated=updated, skipped_manual=skipped_manual
        )

    def list_year(self, year: int) -> list[ProductionCalendarDay]:
        return (
            self.db.query(ProductionCalendarDay)
            .filter(
                ProductionCalendarDay.date >= date(year, 1, 1),
                ProductionCalendarDay.date <= date(year, 12, 31),
            )
            .order_by(ProductionCalendarDay.date)
            .all()
        )

    def upsert_manual(
        self, d: date, is_workday: bool, kind: str, note: Optional[str] = None
    ) -> ProductionCalendarDay:
        row = self.db.get(ProductionCalendarDay, d)
        if row is None:
            row = ProductionCalendarDay(
                date=d, is_workday=is_workday, kind=kind, note=note,
                source="manual", synced_at=datetime.utcnow(),
            )
            self.db.add(row)
        else:
            row.is_workday = is_workday
            row.kind = kind
            row.note = note
            row.source = "manual"
            row.synced_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_manual(self, d: date) -> bool:
        row = self.db.get(ProductionCalendarDay, d)
        if row is None or row.source != "manual":
            return False
        self.db.delete(row)
        self.db.commit()
        return True
