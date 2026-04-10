"""Planning scenarios API endpoints.

CRUD для сценариев квартального планирования и их генерация
жадным алгоритмом на основе приоритета и ёмкости команды.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PlanningScenario, ScenarioAllocation
from app.repositories.base import BaseRepository
from app.services.planning_service import (
    AllocationEntry,
    PlanningResult,
    PlanningService,
)


router = APIRouter()


# === Schemas ===

class ScenarioCreate(BaseModel):
    name: str
    year: int
    quarter: int = Field(ge=1, le=4)
    backlog_item_ids: Optional[List[str]] = None


class ScenarioResponse(BaseModel):
    id: str
    name: str
    quarter: Optional[str] = None
    year: Optional[int] = None

    class Config:
        from_attributes = True


class AllocationResponse(BaseModel):
    backlog_item_id: str
    title: str
    priority: Optional[int] = None
    estimate_hours: float
    planned_hours: float
    included: bool
    reason: str

    @classmethod
    def from_entry(cls, entry: AllocationEntry) -> "AllocationResponse":
        return cls(**entry.__dict__)


class PlanningResultResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    year: int
    quarter: int
    total_capacity_hours: float
    total_planned_hours: float
    leftover_capacity_hours: float
    included_count: int
    skipped_count: int
    allocations: List[AllocationResponse]

    @classmethod
    def from_result(cls, result: PlanningResult) -> "PlanningResultResponse":
        return cls(
            scenario_id=result.scenario_id,
            scenario_name=result.scenario_name,
            year=result.year,
            quarter=result.quarter,
            total_capacity_hours=result.total_capacity_hours,
            total_planned_hours=result.total_planned_hours,
            leftover_capacity_hours=result.leftover_capacity_hours,
            included_count=result.included_count,
            skipped_count=result.skipped_count,
            allocations=[
                AllocationResponse.from_entry(a) for a in result.allocations
            ],
        )


class StoredAllocationResponse(BaseModel):
    id: str
    scenario_id: str
    backlog_item_id: str
    planned_hours: Optional[float] = None
    included_flag: bool

    class Config:
        from_attributes = True


# === Scenarios CRUD ===

@router.get("/scenarios", response_model=List[ScenarioResponse])
async def list_scenarios(
    year: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    db: Session = Depends(get_db),
):
    """Список сценариев планирования (опционально по году/кварталу)."""
    query = db.query(PlanningScenario)
    if year is not None:
        query = query.filter(PlanningScenario.year == year)
    if quarter is not None:
        query = query.filter(PlanningScenario.quarter == f"Q{quarter}")
    return query.order_by(
        PlanningScenario.year.desc(),
        PlanningScenario.quarter,
        PlanningScenario.name,
    ).all()


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Получить сценарий по id."""
    repo = BaseRepository(PlanningScenario, db)
    scenario = repo.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Удалить сценарий вместе со всеми его раскладками."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    db.query(ScenarioAllocation).filter(
        ScenarioAllocation.scenario_id == scenario_id
    ).delete()
    db.delete(scenario)
    db.commit()
    return {"status": "deleted", "id": scenario_id}


@router.get(
    "/scenarios/{scenario_id}/allocations",
    response_model=List[StoredAllocationResponse],
)
async def list_scenario_allocations(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Список сохранённых раскладок по сценарию."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    service = PlanningService(db)
    return service.get_scenario_allocations(scenario_id)


# === Generation ===

@router.post(
    "/scenarios/generate",
    response_model=PlanningResultResponse,
    status_code=201,
)
async def generate_scenario(
    data: ScenarioCreate,
    db: Session = Depends(get_db),
):
    """Сгенерировать новый сценарий жадной раскладкой по приоритету.

    Берёт кандидатов из бэклога (либо по явному списку id, либо по
    year+quarter), считает ёмкость команды и упаковывает задачи целиком
    по приоритету, пока хватает часов.
    """
    service = PlanningService(db)
    try:
        result = service.generate_scenario(
            name=data.name,
            year=data.year,
            quarter=data.quarter,
            backlog_item_ids=data.backlog_item_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PlanningResultResponse.from_result(result)
