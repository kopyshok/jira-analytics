"""Capacity API endpoints.

Управление отпусками и правилами обязательных работ, а также
расчёт доступной ёмкости сотрудников на месяц/квартал.
"""

from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Absence
from app.repositories.base import BaseRepository
from app.services.capacity_service import (
    CapacityService,
    MonthlyCapacity,
    QuarterCapacity,
)


# === Schemas: category breakdown ===

class CategoryBreakdownResponse(BaseModel):
    employee_id: str
    employee_name: str
    by_bucket: dict[str, float]
    total_hours: float


router = APIRouter()


# === Schemas: absences ===

AbsenceReason = Literal["vacation", "sick", "day_off", "other"]


class AbsenceCreate(BaseModel):
    employee_id: str
    start_date: date
    end_date: date
    reason: AbsenceReason = "vacation"
    hours_total: Optional[float] = None


class AbsenceResponse(BaseModel):
    id: str
    employee_id: str
    start_date: date
    end_date: date
    reason: AbsenceReason
    hours_total: Optional[float] = None

    class Config:
        from_attributes = True


# === Schemas: capacity reports ===

class MonthlyCapacityResponse(BaseModel):
    employee_id: str
    employee_name: str
    year: int
    month: int
    workdays: int
    norm_hours: float
    vacation_hours: float
    mandatory_hours: float
    available_hours: float
    fact_hours: float = 0.0

    @classmethod
    def from_dataclass(cls, data: MonthlyCapacity) -> "MonthlyCapacityResponse":
        return cls(**data.__dict__)


class QuarterCapacityResponse(BaseModel):
    employee_id: str
    employee_name: str
    year: int
    quarter: int
    months: List[MonthlyCapacityResponse]
    total_norm_hours: float
    total_vacation_hours: float
    total_mandatory_hours: float
    total_available_hours: float
    total_fact_hours: float = 0.0
    team: Optional[str] = None

    @classmethod
    def from_dataclass(cls, data: QuarterCapacity) -> "QuarterCapacityResponse":
        return cls(
            employee_id=data.employee_id,
            employee_name=data.employee_name,
            year=data.year,
            quarter=data.quarter,
            months=[
                MonthlyCapacityResponse.from_dataclass(m) for m in data.months
            ],
            total_norm_hours=data.total_norm_hours,
            total_vacation_hours=data.total_vacation_hours,
            total_mandatory_hours=data.total_mandatory_hours,
            total_available_hours=data.total_available_hours,
            total_fact_hours=data.total_fact_hours,
            team=data.team,
        )


# === Absences CRUD ===

@router.get("/absences", response_model=List[AbsenceResponse])
async def list_absences(
    employee_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Список отсутствий (опционально — по сотруднику)."""
    query = db.query(Absence)
    if employee_id:
        query = query.filter(Absence.employee_id == employee_id)
    return query.order_by(Absence.start_date).all()


@router.post("/absences", response_model=AbsenceResponse, status_code=201)
async def create_absence(
    data: AbsenceCreate,
    db: Session = Depends(get_db),
):
    """Добавить отсутствие (отпуск / больничный / отгул / прочее)."""
    if data.end_date < data.start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be >= start_date",
        )
    repo = BaseRepository(Absence, db)
    absence = repo.create(data.model_dump())
    # Snapshot before commit — avoid expired-attribute reload on worker thread
    absence_id = absence.id
    employee_id = absence.employee_id
    start_date = absence.start_date
    end_date = absence.end_date
    reason = absence.reason
    hours_total = absence.hours_total
    db.commit()
    return AbsenceResponse(
        id=absence_id,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        hours_total=hours_total,
    )


@router.delete("/absences/{absence_id}")
async def delete_absence(
    absence_id: str,
    db: Session = Depends(get_db),
):
    """Удалить отсутствие."""
    repo = BaseRepository(Absence, db)
    existing = repo.get(absence_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Absence not found")
    repo.delete(existing)
    db.commit()
    return {"status": "deleted", "id": absence_id}


# === Capacity reports ===

@router.get(
    "/monthly/{employee_id}",
    response_model=MonthlyCapacityResponse,
)
async def get_monthly_capacity(
    employee_id: str,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    """Ёмкость сотрудника на месяц."""
    service = CapacityService(db)
    try:
        result = service.monthly_capacity(employee_id, year, month)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return MonthlyCapacityResponse.from_dataclass(result)


@router.get(
    "/quarter/{employee_id}",
    response_model=QuarterCapacityResponse,
)
async def get_quarter_capacity(
    employee_id: str,
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    """Ёмкость сотрудника на квартал."""
    service = CapacityService(db)
    try:
        result = service.quarter_capacity(employee_id, year, quarter)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return QuarterCapacityResponse.from_dataclass(result)


@router.get("/team", response_model=List[QuarterCapacityResponse])
async def get_team_quarter_capacity(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    """Ёмкость всей активной команды на квартал."""
    service = CapacityService(db)
    results = service.team_quarter_capacity(year, quarter)
    return [QuarterCapacityResponse.from_dataclass(r) for r in results]


@router.get(
    "/team/category-breakdown",
    response_model=List[CategoryBreakdownResponse],
)
def team_category_breakdown(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    """Факт-часы команды за квартал по 5 бакетам категорий."""
    svc = CapacityService(db)
    rows = svc.category_breakdown(year, quarter)
    return [
        CategoryBreakdownResponse(
            employee_id=r.employee_id,
            employee_name=r.employee_name,
            by_bucket=r.by_bucket,
            total_hours=r.total_hours,
        )
        for r in rows
    ]
