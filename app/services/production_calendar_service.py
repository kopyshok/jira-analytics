"""Сервис производственного календаря РФ.

Источник данных — таблица ``production_calendar_day``. Неуказанные дни
интерпретируются как обычные (будни по правилу ``weekday() < 5``).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.connectors.production_calendar_client import ProductionCalendarClient
from app.models import ProductionCalendarDay


@dataclass
class SyncStats:
    inserted: int
    updated: int
    skipped_manual: int


def default_hours(kind: str, is_workday: bool) -> float:
    """Норма часов по правилу: Пн–Пт — 8, предпраздничный — 7, выходной — 0."""
    if kind == "preholiday":
        return 7.0
    if kind in ("workday", "workday_moved"):
        return 8.0
    return 8.0 if is_workday else 0.0


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

    def hours_in_range_map(self, start: date, end: date) -> dict[date, float]:
        """Норма рабочих часов за каждый день в интервале (если есть в БД)."""
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
        return {r.date: float(r.hours) for r in rows}

    async def sync_year(
        self, year: int, overwrite_manual: bool = False
    ) -> SyncStats:
        """Заполнить таблицу календаря на весь год.

        Аномалии (праздники, переносы, сокращённые) берутся из xmlcalendar.ru;
        остальные дни достраиваются: Пн–Пт → ``workday``, Сб/Вс → ``weekend``.
        Ручные правки (``source='manual'``) сохраняются, если не задан
        ``overwrite_manual``.
        """
        days = await self.client.fetch_year(year)
        source_map = {d.date: d for d in days}

        inserted = updated = skipped_manual = 0
        current = date(year, 1, 1)
        end = date(year, 12, 31)

        while current <= end:
            existing = self.db.get(ProductionCalendarDay, current)
            if existing and existing.source == "manual" and not overwrite_manual:
                skipped_manual += 1
                current += timedelta(days=1)
                continue

            raw = source_map.get(current)
            if raw is not None:
                is_wd, kind, note = raw.is_workday, raw.kind, raw.note
            elif current.weekday() < 5:
                is_wd, kind, note = True, "workday", None
            else:
                is_wd, kind, note = False, "weekend", None

            hours = default_hours(kind, is_wd)
            if existing is None:
                self.db.add(ProductionCalendarDay(
                    date=current,
                    is_workday=is_wd,
                    kind=kind,
                    hours=hours,
                    note=note,
                    source="xmlcalendar",
                    synced_at=datetime.utcnow(),
                ))
                inserted += 1
            else:
                existing.is_workday = is_wd
                existing.kind = kind
                existing.hours = hours
                existing.note = note
                existing.source = "xmlcalendar"
                existing.synced_at = datetime.utcnow()
                updated += 1
            current += timedelta(days=1)

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
        self,
        d: date,
        is_workday: bool,
        kind: str,
        note: Optional[str] = None,
        hours: Optional[float] = None,
    ) -> ProductionCalendarDay:
        """Ручная правка дня. ``hours=None`` → пересчитать по правилу."""
        resolved_hours = hours if hours is not None else default_hours(kind, is_workday)
        row = self.db.get(ProductionCalendarDay, d)
        if row is None:
            row = ProductionCalendarDay(
                date=d,
                is_workday=is_workday,
                kind=kind,
                hours=resolved_hours,
                note=note,
                source="manual",
                synced_at=datetime.utcnow(),
            )
            self.db.add(row)
        else:
            row.is_workday = is_workday
            row.kind = kind
            row.hours = resolved_hours
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
