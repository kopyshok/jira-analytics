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
    RoleCapacityRule,
    ScenarioAllocation,
    ScenarioRule,
)
from app.services.planning_service import PlanningService
from app.services.resource_base_service import ResourceBaseService


router = APIRouter()


# === Schemas ===

class ScenarioCreate(BaseModel):
    name: str
    year: int
    quarter: int = Field(ge=1, le=4)
    team: Optional[str] = None
    external_qa_hours: Optional[float] = None


class ScenarioUpdate(BaseModel):
    name: Optional[str] = None
    team: Optional[str] = None
    external_qa_hours: Optional[float] = None


class ScenarioResponse(BaseModel):
    id: str
    name: str
    quarter: Optional[str] = None
    year: Optional[int] = None
    status: str
    team: Optional[str] = None
    external_qa_hours: Optional[float] = None

    class Config:
        from_attributes = True


class ScenarioRuleOut(BaseModel):
    id: str
    role: Optional[str] = None
    work_type_id: str
    percent_of_norm: float

    class Config:
        from_attributes = True


class ScenarioRuleInput(BaseModel):
    role: Optional[str] = None
    work_type_id: str
    percent_of_norm: float


class ScenarioRulesReplaceBody(BaseModel):
    rules: List[ScenarioRuleInput]


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


# === Resource base schemas ===

class ResourceBaseDayOut(BaseModel):
    date: str  # ISO "YYYY-MM-DD"
    hours: float


class ResourceBaseEmployeeOut(BaseModel):
    employee_id: str
    display_name: str
    role: Optional[str] = None
    total_hours: float
    days: List[ResourceBaseDayOut]


class ResourceBaseOut(BaseModel):
    year: int
    quarter: int
    team: str
    employees: List[ResourceBaseEmployeeOut]
    role_totals: Dict[str, float]
    external_qa_hours: Optional[float] = None


class WorkTypeRowOut(BaseModel):
    work_type_id: str
    work_type_label: str
    hours_by_role: Dict[str, float]
    pct_by_role: Dict[str, Optional[float]]
    total_hours: float


class ResourceSummaryOut(BaseModel):
    year: int
    quarter: int
    team: str
    roles: List[str]
    role_employee_names: Dict[str, List[str]]
    gross_by_role: Dict[str, float]
    gross_total: float
    work_type_rows: List[WorkTypeRowOut]
    available_by_role: Dict[str, float]
    available_total: float
    external_qa_hours: Optional[float] = None


# === Helpers ===

def _to_scenario_resp(s: PlanningScenario) -> ScenarioResponse:
    return ScenarioResponse(
        id=s.id,
        name=s.name,
        quarter=s.quarter,
        year=s.year,
        status=s.status,
        team=s.team,
        external_qa_hours=s.external_qa_hours,
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


def _resource_to_response(base) -> ResourceBaseOut:
    return ResourceBaseOut(
        year=base.year,
        quarter=base.quarter,
        team=base.team,
        employees=[
            ResourceBaseEmployeeOut(
                employee_id=e.employee_id,
                display_name=e.display_name,
                role=e.role,
                total_hours=e.total_hours,
                days=[
                    ResourceBaseDayOut(date=d.date.isoformat(), hours=d.hours)
                    for d in e.days
                ],
            )
            for e in base.employees
        ],
        role_totals=base.role_totals,
        external_qa_hours=base.external_qa_hours,
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
        team=data.team,
        external_qa_hours=data.external_qa_hours,
    )
    db.add(scenario)
    db.flush()

    items = db.query(BacklogItem).filter(BacklogItem.archived_at.is_(None)).all()
    for item in items:
        db.add(
            ScenarioAllocation(
                scenario_id=scenario.id,
                backlog_item_id=item.id,
                included_flag=False,
                planned_hours=0,
            )
        )

    # Копировать правила из role_capacity_rules для указанного квартала.
    template_rules = (
        db.query(RoleCapacityRule)
        .filter(
            RoleCapacityRule.year == data.year,
            RoleCapacityRule.quarter == data.quarter,
        )
        .all()
    )
    for rcr in template_rules:
        db.add(
            ScenarioRule(
                scenario_id=scenario.id,
                role=rcr.role,
                work_type_id=rcr.work_type_id,
                percent_of_norm=rcr.percent_of_norm,
            )
        )

    db.commit()
    db.refresh(scenario)
    return _to_scenario_resp(scenario)


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


@router.get("/scenarios/{scenario_id}/rules", response_model=List[ScenarioRuleOut])
async def get_scenario_rules(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Список правил обязательных работ для сценария."""
    if not db.get(PlanningScenario, scenario_id):
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    return db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario_id).all()


@router.put("/scenarios/{scenario_id}/rules", response_model=List[ScenarioRuleOut])
async def replace_scenario_rules(
    scenario_id: str,
    body: ScenarioRulesReplaceBody,
    db: Session = Depends(get_db),
):
    """Атомарно заменить правила обязательных работ сценария."""
    if not db.get(PlanningScenario, scenario_id):
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario_id).delete()
    for r in body.rules:
        db.add(
            ScenarioRule(
                scenario_id=scenario_id,
                role=r.role,
                work_type_id=r.work_type_id,
                percent_of_norm=r.percent_of_norm,
            )
        )
    db.commit()
    return db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario_id).all()


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
    current_ids = {
        i.id for i in db.query(BacklogItem.id)
        .filter(BacklogItem.archived_at.is_(None))
        .all()
    }

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


# === Scenario resource base ===

@router.get("/scenarios/{scenario_id}/resource", response_model=ResourceBaseOut)
async def scenario_resource(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Посуточная база ресурса команды для сценария.

    Возвращает доступные проектные часы по каждому сотруднику на каждый
    рабочий день квартала (с учётом отсутствий и обязательных работ).
    """
    sc = db.get(PlanningScenario, scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    if not sc.team:
        raise HTTPException(status_code=400, detail="Команда у сценария не выбрана")
    if not sc.year or not sc.quarter:
        raise HTTPException(status_code=400, detail="Год/квартал у сценария не заданы")
    base = ResourceBaseService(db).compute(sc)
    return _resource_to_response(base)


@router.get("/scenarios/{scenario_id}/resource-summary", response_model=ResourceSummaryOut)
async def scenario_resource_summary(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Разбивка ресурса команды: норма-часы → обязательные работы → доступно на бэклог."""
    sc = db.get(PlanningScenario, scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    if not sc.team:
        raise HTTPException(status_code=400, detail="Команда у сценария не выбрана")
    if not sc.year or not sc.quarter:
        raise HTTPException(status_code=400, detail="Год/квартал у сценария не заданы")

    summary = ResourceBaseService(db).compute_summary(sc)
    return ResourceSummaryOut(
        year=summary.year,
        quarter=summary.quarter,
        team=summary.team,
        roles=summary.roles,
        role_employee_names=summary.role_employee_names,
        gross_by_role=summary.gross_by_role,
        gross_total=summary.gross_total,
        work_type_rows=[
            WorkTypeRowOut(
                work_type_id=row.work_type_id,
                work_type_label=row.work_type_label,
                hours_by_role=row.hours_by_role,
                pct_by_role=row.pct_by_role,
                total_hours=row.total_hours,
            )
            for row in summary.work_type_rows
        ],
        available_by_role=summary.available_by_role,
        available_total=summary.available_total,
        external_qa_hours=summary.external_qa_hours,
    )


# === Generic scenario CRUD routes (must come last) ===


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
    """Обновить сценарий: имя, команда, внешние часы QA (разрешено и для approved)."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    patch = data.model_dump(exclude_unset=True)
    if "name" in patch:
        scenario.name = patch["name"]
    if "team" in patch:
        scenario.team = patch["team"]
    if "external_qa_hours" in patch:
        scenario.external_qa_hours = patch["external_qa_hours"]
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
