"""Planning scenarios API endpoints.

CRUD для сценариев квартального планирования и их генерация
жадным алгоритмом на основе приоритета и ёмкости команды.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BacklogItem, Employee, PlanningScenario, ScenarioAllocation
from app.repositories.base import BaseRepository
from app.services.capacity_service import CapacityService, ROLE_WHITELIST
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


# === Capacity preview (live per-role calc without persisting a scenario) ===

class CapacityPreviewRequest(BaseModel):
    year: int
    quarter: int = Field(ge=1, le=4)
    backlog_item_ids: List[str] = Field(default_factory=list)
    team_filter: Optional[List[str]] = None


class CapacityPreviewEmployeeRow(BaseModel):
    employee_id: str
    name: str
    role: Optional[str] = None
    raw_hours: float
    mandatory_hours: float
    absence_hours: float
    available_hours: float
    vacation_days: int


class CapacityPreviewResponse(BaseModel):
    capacity_by_role: Dict[str, float]  # {analyst, dev, qa}
    demand_by_role: Dict[str, float]
    total_capacity: float
    total_demand: float
    gross_hours: float
    absence_hours: float
    mandatory_hours: float
    available_hours: float
    per_employee: List[CapacityPreviewEmployeeRow]


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


# === Capacity preview ===

@router.post("/capacity-preview", response_model=CapacityPreviewResponse)
async def capacity_preview(
    body: CapacityPreviewRequest,
    db: Session = Depends(get_db),
):
    """Read-only расчёт ёмкости + spec спроса для UI планирования.

    Возвращает:
    - capacity_by_role: доступные часы per role (analyst/dev/qa);
    - demand_by_role: суммарный спрос от выбранных backlog items;
    - per_employee: детализация по активным сотрудникам (с учётом
      team_filter) для рендера таблицы превью;
    - агрегаты gross/absence/mandatory/available за квартал.

    Не создаёт PlanningScenario и ничего не пишет в БД.
    """
    cap_svc = CapacityService(db)
    try:
        caps = cap_svc.team_role_capacity(
            body.year, body.quarter, body.team_filter
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Per-employee rows
    emp_q = db.query(Employee).filter(Employee.is_active.is_(True))
    if body.team_filter:
        from app.models import EmployeeTeam

        emp_q = (
            emp_q.join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .filter(EmployeeTeam.team.in_(body.team_filter))
            .distinct()
        )

    per_emp: List[CapacityPreviewEmployeeRow] = []
    gross = absence = mand = avail = 0.0
    for emp in emp_q.all():
        row = cap_svc.employee_quarter_breakdown(
            emp.id, body.year, body.quarter
        )
        per_emp.append(
            CapacityPreviewEmployeeRow(
                employee_id=emp.id,
                name=emp.display_name,
                role=emp.role,
                raw_hours=row["raw_hours"],
                mandatory_hours=row["mandatory_hours"],
                absence_hours=row["absence_hours"],
                available_hours=row["available_hours"],
                vacation_days=row["vacation_days"],
            )
        )
        gross += row["raw_hours"]
        absence += row["absence_hours"]
        mand += row["mandatory_hours"]
        avail += row["available_hours"]

    # Demand — sum of per-role demand for the specified backlog items.
    demand = {r: 0.0 for r in ROLE_WHITELIST}
    if body.backlog_item_ids:
        items = (
            db.query(BacklogItem)
            .filter(BacklogItem.id.in_(body.backlog_item_ids))
            .all()
        )
        for item in items:
            for role, hours in PlanningService._demand_by_role(item).items():
                demand[role] += hours

    return CapacityPreviewResponse(
        capacity_by_role=caps,
        demand_by_role=demand,
        total_capacity=sum(caps.values()),
        total_demand=sum(demand.values()),
        gross_hours=gross,
        absence_hours=absence,
        mandatory_hours=mand,
        available_hours=avail,
        per_employee=per_emp,
    )
