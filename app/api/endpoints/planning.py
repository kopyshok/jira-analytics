"""Planning scenarios API endpoints.

CRUD сценариев квартального планирования.

Flow:
1. PM создаёт сценарий: `POST /scenarios` с `{name, year, quarter}` →
   создаётся draft, в allocations кладутся ВСЕ текущие BacklogItem
   c `included_flag=False, planned_hours=0`.
2. PM отмечает нужные задачи: `PATCH /scenarios/{id}/allocations/{alloc_id}`
   с `{included: true|false}`. Сервер сам подставляет
   `planned_hours = backlog_item.estimate_hours` при включении, сбрасывает
   в 0 при выключении.
3. Утверждение: `POST /scenarios/{id}/approve` → status='approved'.
   Откат: `POST /scenarios/{id}/revert-to-draft` → status='draft'.

Утверждённые сценарии редактировать нельзя (409) — сначала revert.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    BacklogItem,
    Employee,
    PlanningScenario,
    ScenarioAllocation,
)
from app.services.capacity_service import CapacityService, ROLE_WHITELIST
from app.services.planning_service import PlanningService


router = APIRouter()


# === Schemas ===

class ScenarioCreate(BaseModel):
    name: str
    year: int
    quarter: int = Field(ge=1, le=4)


class ScenarioUpdate(BaseModel):
    name: Optional[str] = None


class ScenarioResponse(BaseModel):
    id: str
    name: str
    quarter: Optional[str] = None
    year: Optional[int] = None
    status: str

    class Config:
        from_attributes = True


class AllocationPatch(BaseModel):
    included: Optional[bool] = None
    planned_hours: Optional[float] = Field(default=None, ge=0)


class AllocationResponse(BaseModel):
    """Allocation + денормализованные поля BacklogItem для рендера таблицы."""

    id: str
    scenario_id: str
    backlog_item_id: str
    included: bool
    planned_hours: Optional[float] = None

    # Denormalised BacklogItem fields.
    title: str
    jira_key: Optional[str] = None
    priority: Optional[int] = None
    estimate_hours: Optional[float] = None
    estimate_analyst_hours: Optional[float] = None
    estimate_dev_hours: Optional[float] = None
    estimate_qa_hours: Optional[float] = None
    estimate_opo_hours: Optional[float] = None
    opo_analyst_ratio: Optional[float] = None
    impact: Optional[str] = None
    risk: Optional[str] = None


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
    capacity_by_role: Dict[str, float]
    demand_by_role: Dict[str, float]
    total_capacity: float
    total_demand: float
    gross_hours: float
    absence_hours: float
    mandatory_hours: float
    available_hours: float
    per_employee: List[CapacityPreviewEmployeeRow]


# === Helpers ===

def _to_scenario_resp(s: PlanningScenario) -> ScenarioResponse:
    return ScenarioResponse(
        id=s.id,
        name=s.name,
        quarter=s.quarter,
        year=s.year,
        status=s.status,
    )


def _to_allocation_resp(
    alloc: ScenarioAllocation, item: BacklogItem
) -> AllocationResponse:
    return AllocationResponse(
        id=alloc.id,
        scenario_id=alloc.scenario_id,
        backlog_item_id=alloc.backlog_item_id,
        included=bool(alloc.included_flag),
        planned_hours=alloc.planned_hours,
        title=item.title,
        jira_key=item.issue.key if item.issue else None,
        priority=item.priority,
        estimate_hours=item.estimate_hours,
        estimate_analyst_hours=item.estimate_analyst_hours,
        estimate_dev_hours=item.estimate_dev_hours,
        estimate_qa_hours=item.estimate_qa_hours,
        estimate_opo_hours=item.estimate_opo_hours,
        opo_analyst_ratio=item.opo_analyst_ratio,
        impact=item.impact,
        risk=item.risk,
    )


def _require_draft(scenario: PlanningScenario) -> None:
    if scenario.status != "draft":
        raise HTTPException(
            status_code=409,
            detail=(
                "Scenario is approved; revert to draft before editing"
            ),
        )


# === Scenarios CRUD ===

@router.get("/scenarios", response_model=List[ScenarioResponse])
async def list_scenarios(
    year: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    status: Optional[str] = Query(None, pattern="^(draft|approved)$"),
    db: Session = Depends(get_db),
):
    """Список сценариев планирования (опционально по году/кварталу/статусу)."""
    query = db.query(PlanningScenario)
    if year is not None:
        query = query.filter(PlanningScenario.year == year)
    if quarter is not None:
        query = query.filter(PlanningScenario.quarter == f"Q{quarter}")
    if status is not None:
        query = query.filter(PlanningScenario.status == status)
    rows = query.order_by(
        PlanningScenario.year.desc(),
        PlanningScenario.quarter,
        PlanningScenario.name,
    ).all()
    return [_to_scenario_resp(s) for s in rows]


@router.post("/scenarios", response_model=ScenarioResponse, status_code=201)
async def create_scenario(
    data: ScenarioCreate,
    db: Session = Depends(get_db),
):
    """Создать draft-сценарий. В allocations кладутся ВСЕ текущие BacklogItem
    c ``included_flag=False, planned_hours=0`` — PM отмечает нужные галочками.
    """
    scenario = PlanningScenario(
        name=data.name,
        year=data.year,
        quarter=f"Q{data.quarter}",
        status="draft",
    )
    db.add(scenario)
    db.flush()

    items = db.query(BacklogItem).all()
    for item in items:
        db.add(
            ScenarioAllocation(
                scenario_id=scenario.id,
                backlog_item_id=item.id,
                included_flag=False,
                planned_hours=0,
            )
        )
    db.commit()
    db.refresh(scenario)
    return _to_scenario_resp(scenario)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Получить сценарий по id."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _to_scenario_resp(scenario)


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def update_scenario(
    scenario_id: str,
    data: ScenarioUpdate,
    db: Session = Depends(get_db),
):
    """Переименовать сценарий (разрешено и для approved)."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if data.name is not None:
        scenario.name = data.name
    db.commit()
    db.refresh(scenario)
    return _to_scenario_resp(scenario)


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


@router.post("/scenarios/{scenario_id}/approve", response_model=ScenarioResponse)
async def approve_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Зафиксировать сценарий: status='approved'. Используется как вход в аналитику."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario.status = "approved"
    db.commit()
    db.refresh(scenario)
    return _to_scenario_resp(scenario)


@router.post(
    "/scenarios/{scenario_id}/revert-to-draft", response_model=ScenarioResponse
)
async def revert_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Вернуть утверждённый сценарий в черновик для редактирования."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario.status = "draft"
    db.commit()
    db.refresh(scenario)
    return _to_scenario_resp(scenario)


@router.post(
    "/scenarios/{scenario_id}/sync-backlog",
    response_model=List[AllocationResponse],
)
async def sync_backlog(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Досоздать allocations для новых BacklogItem, которых не было при
    создании сценария. Удалённые из бэклога — подчистить.

    Только для draft-сценариев.
    """
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    _require_draft(scenario)

    existing_ids = {
        a.backlog_item_id
        for a in db.query(ScenarioAllocation)
        .filter(ScenarioAllocation.scenario_id == scenario_id)
        .all()
    }
    current_ids = {i.id for i in db.query(BacklogItem.id).all()}

    # Добавить новые.
    for item_id in current_ids - existing_ids:
        db.add(
            ScenarioAllocation(
                scenario_id=scenario_id,
                backlog_item_id=item_id,
                included_flag=False,
                planned_hours=0,
            )
        )
    # Убрать allocations для удалённых из бэклога записей.
    if existing_ids - current_ids:
        db.query(ScenarioAllocation).filter(
            ScenarioAllocation.scenario_id == scenario_id,
            ScenarioAllocation.backlog_item_id.in_(existing_ids - current_ids),
        ).delete(synchronize_session=False)

    db.commit()

    return await list_scenario_allocations(scenario_id, db)


@router.get(
    "/scenarios/{scenario_id}/allocations",
    response_model=List[AllocationResponse],
)
async def list_scenario_allocations(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Список раскладок сценария c денормализованными полями бэклога.

    Сортировка — по priority (nulls last), затем по title.
    """
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    rows = (
        db.query(ScenarioAllocation, BacklogItem)
        .join(BacklogItem, ScenarioAllocation.backlog_item_id == BacklogItem.id)
        .options(joinedload(BacklogItem.issue))
        .filter(ScenarioAllocation.scenario_id == scenario_id)
        .all()
    )
    resp = [_to_allocation_resp(alloc, item) for alloc, item in rows]
    resp.sort(
        key=lambda r: (
            r.priority is None,
            r.priority if r.priority is not None else 0,
            r.title or "",
        )
    )
    return resp


@router.patch(
    "/scenarios/{scenario_id}/allocations/{alloc_id}",
    response_model=AllocationResponse,
)
async def patch_allocation(
    scenario_id: str,
    alloc_id: str,
    data: AllocationPatch,
    db: Session = Depends(get_db),
):
    """Обновить одну раскладку: toggle ``included`` и/или задать ``planned_hours``.

    При ``included=True`` и пустом planned_hours — автоматически подставляется
    ``backlog_item.estimate_hours``. При ``included=False`` — planned_hours → 0.
    Разрешено только для draft-сценариев.
    """
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    _require_draft(scenario)

    alloc = db.get(ScenarioAllocation, alloc_id)
    if not alloc or alloc.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="Allocation not found")

    item = db.get(BacklogItem, alloc.backlog_item_id)
    if item is None:
        raise HTTPException(status_code=500, detail="Allocation references missing backlog item")

    patch = data.model_dump(exclude_unset=True)

    if "included" in patch:
        alloc.included_flag = bool(patch["included"])
        if alloc.included_flag:
            if "planned_hours" not in patch and (alloc.planned_hours or 0) <= 0:
                alloc.planned_hours = item.estimate_hours or 0
        else:
            alloc.planned_hours = 0

    if "planned_hours" in patch:
        alloc.planned_hours = patch["planned_hours"]

    db.commit()
    # Re-load with issue join for response.
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.id == alloc.backlog_item_id)
        .first()
    )
    return _to_allocation_resp(alloc, item)


# === Capacity preview ===

@router.post("/capacity-preview", response_model=CapacityPreviewResponse)
async def capacity_preview(
    body: CapacityPreviewRequest,
    db: Session = Depends(get_db),
):
    """Read-only расчёт ёмкости + spec спроса для UI планирования.

    Возвращает capacity/demand по ролям (analyst/dev/qa) и разбивку
    по активным сотрудникам за выбранный квартал.
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
