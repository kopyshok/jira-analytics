"""HTTP-эндпоинты производственного календаря."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.production_calendar_service import ProductionCalendarService


router = APIRouter()


class CalendarDayResponse(BaseModel):
    date: date
    is_workday: bool
    kind: str
    note: str | None
    source: str

    model_config = {"from_attributes": True}


class CalendarDayUpsertRequest(BaseModel):
    date: date
    is_workday: bool
    kind: str
    note: str | None = None


class CalendarSyncResponse(BaseModel):
    inserted: int
    updated: int
    skipped_manual: int


@router.get("", response_model=list[CalendarDayResponse])
def list_year(year: int = Query(...), db: Session = Depends(get_db)):
    svc = ProductionCalendarService(db)
    rows = svc.list_year(year)
    return [CalendarDayResponse.model_validate(r) for r in rows]


@router.put("", response_model=CalendarDayResponse)
def upsert_manual(
    req: CalendarDayUpsertRequest, db: Session = Depends(get_db)
):
    svc = ProductionCalendarService(db)
    row = svc.upsert_manual(req.date, req.is_workday, req.kind, req.note)
    return CalendarDayResponse.model_validate(row)


@router.delete("/{d}")
def delete_manual(d: date, db: Session = Depends(get_db)):
    svc = ProductionCalendarService(db)
    ok = svc.delete_manual(d)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Can only delete rows with source='manual'.",
        )
    return {"ok": True}


@router.post("/sync", response_model=CalendarSyncResponse)
async def sync_year(
    year: int = Query(...),
    overwrite_manual: bool = Query(False),
    db: Session = Depends(get_db),
):
    svc = ProductionCalendarService(db)
    stats = await svc.sync_year(year, overwrite_manual=overwrite_manual)
    return CalendarSyncResponse(
        inserted=stats.inserted,
        updated=stats.updated,
        skipped_manual=stats.skipped_manual,
    )
