"""Capacity API endpoints.

Управление отпусками и правилами обязательных работ, а также
расчёт доступной ёмкости сотрудников на месяц/квартал.
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Absence, Employee, EmployeeTeam
from app.repositories.base import BaseRepository
from app.services.capacity_service import (
    CapacityService,
    MonthlyCapacity,
    QuarterCapacity,
)
from app.services.event_bus import EventBroadcaster, get_event_bus


router = APIRouter()


# === Schemas: absences ===


class AbsenceCreate(BaseModel):
    employee_id: str
    start_date: date
    end_date: date
    reason_id: str
    hours_total: Optional[float] = None


class AbsenceResponse(BaseModel):
    id: str
    employee_id: str
    start_date: date
    end_date: date
    reason_id: str
    reason_code: str
    reason_label: str
    reason_is_planned: bool
    reason_color: Optional[str] = None
    hours_total: Optional[float] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_absence(cls, a) -> "AbsenceResponse":
        return cls(
            id=a.id,
            employee_id=a.employee_id,
            start_date=a.start_date,
            end_date=a.end_date,
            reason_id=a.reason_id,
            reason_code=a.reason.code,
            reason_label=a.reason.label,
            reason_is_planned=a.reason.is_planned,
            reason_color=a.reason.color,
            hours_total=a.hours_total,
        )


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
    query = db.query(Absence).options(joinedload(Absence.reason))
    if employee_id:
        query = query.filter(Absence.employee_id == employee_id)
    rows = query.order_by(Absence.start_date).all()
    return [AbsenceResponse.from_absence(a) for a in rows]


@router.post("/absences", response_model=AbsenceResponse, status_code=201)
async def create_absence(
    data: AbsenceCreate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Добавить отсутствие."""
    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    from app.models import AbsenceReason
    reason = (
        db.query(AbsenceReason)
        .filter(AbsenceReason.id == data.reason_id, AbsenceReason.is_active.is_(True))
        .one_or_none()
    )
    if reason is None:
        raise HTTPException(status_code=422, detail=f"Unknown or inactive reason_id {data.reason_id!r}")

    absence = Absence(**data.model_dump())
    db.add(absence)
    db.commit()
    db.refresh(absence)
    await event_bus.publish({"type": "entity_changed", "entities": ["capacity"]})
    # Snapshot for thread-safe return (see CLAUDE.md DB caveat).
    return AbsenceResponse.from_absence(absence)


class AbsenceBatchCreate(BaseModel):
    employee_ids: List[str]
    start_date: date
    end_date: date
    reason_id: str
    hours_total: Optional[float] = None


@router.post("/absences/batch", response_model=List[AbsenceResponse], status_code=201)
async def create_absences_batch(
    data: AbsenceBatchCreate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Массовое создание отсутствий — одна запись на каждого employee_id."""
    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    if not data.employee_ids:
        raise HTTPException(status_code=400, detail="employee_ids must be non-empty")

    from app.models import AbsenceReason, Employee

    reason = (
        db.query(AbsenceReason)
        .filter(AbsenceReason.id == data.reason_id, AbsenceReason.is_active.is_(True))
        .one_or_none()
    )
    if reason is None:
        raise HTTPException(status_code=422, detail=f"Unknown or inactive reason_id {data.reason_id!r}")

    known = {
        e.id
        for e in db.query(Employee).filter(Employee.id.in_(data.employee_ids)).all()
    }
    unknown = set(data.employee_ids) - known
    if unknown:
        raise HTTPException(status_code=404, detail=f"Unknown employee_id(s): {sorted(unknown)}")

    created = []
    for emp_id in data.employee_ids:
        a = Absence(
            employee_id=emp_id,
            start_date=data.start_date,
            end_date=data.end_date,
            reason_id=data.reason_id,
            hours_total=data.hours_total,
        )
        db.add(a)
        created.append(a)
    db.commit()
    for a in created:
        db.refresh(a)
    await event_bus.publish({"type": "entity_changed", "entities": ["capacity"]})
    return [AbsenceResponse.from_absence(a) for a in created]


@router.delete("/absences/{absence_id}")
async def delete_absence(
    absence_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Удалить отсутствие."""
    repo = BaseRepository(Absence, db)
    existing = repo.get(absence_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Absence not found")
    repo.delete(existing)
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["capacity"]})
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


def _resolve_teams(team: Optional[str], teams: Optional[str]) -> Optional[List[str]]:
    """Разрешает параметры фильтра команд в список.

    Новый параметр ``teams`` (comma-separated) имеет приоритет над старым
    ``team`` (single). Возвращает ``None`` если фильтр не задан.
    """
    if teams:
        parsed = [t for t in teams.split(",") if t]
        if parsed:
            return parsed
    if team:
        return [team]
    return None


@router.get("/team", response_model=List[QuarterCapacityResponse])
async def get_team_quarter_capacity(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    team: Optional[str] = Query(None, description="Команда (одна, устаревший параметр)"),
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    db: Session = Depends(get_db),
):
    """Ёмкость команды на квартал. Фильтр: teams=A,B или team=A (backward compat)."""
    teams_list = _resolve_teams(team, teams)
    service = CapacityService(db)
    results = service.team_quarter_capacity(year, quarter, employee_ids=None, teams_filter=teams_list)
    return [QuarterCapacityResponse.from_dataclass(r) for r in results]


@router.post("/team/recalc")
async def recalc_team(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    team: str = Query(...),
    db: Session = Depends(get_db),
):
    """Сигнал «пересчитать часы по команде».

    Capacity вычисляется on-demand — этот endpoint возвращает счётчик
    затронутых сотрудников и отметку времени, чтобы фронтенд мог
    инвалидировать кэш и подтвердить обновление.
    """
    emp_count = (
        db.query(Employee)
        .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
        .filter(EmployeeTeam.team == team, Employee.is_active == True)
        .count()
    )
    return {
        "updated_employees": emp_count,
        "year": year,
        "quarter": quarter,
        "team": team,
        "recalculated_at": datetime.utcnow().isoformat(),
    }
