"""Capacity API endpoints.

Управление отпусками и правилами обязательных работ, а также
расчёт доступной ёмкости сотрудников на месяц/квартал.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MonthlyCapacityRule, Vacation
from app.repositories.base import BaseRepository
from app.services.capacity_service import (
    CapacityService,
    MonthlyCapacity,
    QuarterCapacity,
)


router = APIRouter()


# === Schemas: vacations ===

class VacationCreate(BaseModel):
    employee_id: str
    start_date: date
    end_date: date
    hours_total: Optional[float] = None


class VacationResponse(BaseModel):
    id: str
    employee_id: str
    start_date: date
    end_date: date
    hours_total: Optional[float] = None

    class Config:
        from_attributes = True


# === Schemas: monthly capacity rules ===

class CapacityRuleCreate(BaseModel):
    year: int
    month: int = Field(ge=1, le=12)
    percent_of_norm: float = Field(ge=0, le=100)


class CapacityRuleResponse(BaseModel):
    id: str
    year: int
    month: int
    percent_of_norm: float

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
        )


# === Vacations CRUD ===

@router.get("/vacations", response_model=List[VacationResponse])
async def list_vacations(
    employee_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Список отпусков (опционально — по сотруднику)."""
    query = db.query(Vacation)
    if employee_id:
        query = query.filter(Vacation.employee_id == employee_id)
    return query.order_by(Vacation.start_date).all()


@router.post("/vacations", response_model=VacationResponse, status_code=201)
async def create_vacation(
    data: VacationCreate,
    db: Session = Depends(get_db),
):
    """Добавить отпуск."""
    if data.end_date < data.start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be >= start_date",
        )
    repo = BaseRepository(Vacation, db)
    vacation = repo.create(data.model_dump())
    db.commit()
    return vacation


@router.delete("/vacations/{vacation_id}")
async def delete_vacation(
    vacation_id: str,
    db: Session = Depends(get_db),
):
    """Удалить отпуск."""
    repo = BaseRepository(Vacation, db)
    existing = repo.get(vacation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Vacation not found")
    repo.delete(existing)
    db.commit()
    return {"status": "deleted", "id": vacation_id}


# === Monthly capacity rules CRUD ===

@router.get("/rules", response_model=List[CapacityRuleResponse])
async def list_capacity_rules(
    year: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Список правил обязательных работ (опционально — по году)."""
    query = db.query(MonthlyCapacityRule)
    if year is not None:
        query = query.filter(MonthlyCapacityRule.year == year)
    return query.order_by(
        MonthlyCapacityRule.year, MonthlyCapacityRule.month
    ).all()


@router.post("/rules", response_model=CapacityRuleResponse, status_code=201)
async def upsert_capacity_rule(
    data: CapacityRuleCreate,
    db: Session = Depends(get_db),
):
    """Создать или обновить правило процента обязательных работ на месяц."""
    existing = (
        db.query(MonthlyCapacityRule)
        .filter(
            MonthlyCapacityRule.year == data.year,
            MonthlyCapacityRule.month == data.month,
        )
        .one_or_none()
    )
    if existing:
        existing.percent_of_norm = data.percent_of_norm
        db.commit()
        db.refresh(existing)
        return existing

    rule = MonthlyCapacityRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}")
async def delete_capacity_rule(
    rule_id: str,
    db: Session = Depends(get_db),
):
    """Удалить правило."""
    repo = BaseRepository(MonthlyCapacityRule, db)
    existing = repo.get(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    repo.delete(existing)
    db.commit()
    return {"status": "deleted", "id": rule_id}


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
