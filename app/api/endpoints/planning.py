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

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    RoleCapacityRule,
    ScenarioAllocation,
    ScenarioCapacitySnapshot,
    ScenarioRevision,
    ScenarioRevisionItem,
    ScenarioRule,
)
from app.services.capacity_service import CapacityService
from app.services.planning_service import PlanningService
from app.services.resource_base_service import ResourceBaseService
from app.services.event_bus import EventBroadcaster, get_event_bus


router = APIRouter()

QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}


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


class ApproveBody(BaseModel):
    note: Optional[str] = None


class CapacitySnapshotOut(BaseModel):
    employee_id: Optional[str]
    employee_name: str
    year: int
    month: int
    norm_hours: float
    available_hours: float

    class Config:
        from_attributes = True


class RevisionItemOut(BaseModel):
    backlog_item_id: Optional[str]
    backlog_item_name: str
    action: str

    class Config:
        from_attributes = True


class RevisionOut(BaseModel):
    id: str
    revision_number: int
    approved_at: str
    note: Optional[str]
    items: List[RevisionItemOut]
    capacity_snapshots: List[CapacitySnapshotOut]

    class Config:
        from_attributes = True


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
    assignee_employee_id: Optional[str] = None
    assignee_display_name: Optional[str] = None
    assignee_role: Optional[str] = None
    customer: Optional[str] = None
    cost_type: Optional[str] = None
    source_category: Optional[str] = None  # 'initiatives_rfa' | 'quarterly_tasks'


class AllocationAssigneePatch(BaseModel):
    assignee_employee_id: Optional[str] = None


class AllocationsReorderBody(BaseModel):
    """Список allocation.id в желаемом порядке (от верха к низу)."""

    ordered_ids: List[str]


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
    by_role: Dict[str, float]
    by_role_pct: Dict[str, Optional[float]]
    total: float
    subtracts_from_pool: bool


class ResourceSummaryOut(BaseModel):
    year: int
    quarter: int
    team: str
    roles: List[str]
    role_employee_names: Dict[str, List[str]]
    total_by_role: Dict[str, float]
    total: float
    work_type_rows: List[WorkTypeRowOut]
    available_for_backlog_by_role: Dict[str, float]
    available_for_backlog_total: float
    external_qa_hours: Optional[float] = None
    calendar_gross_by_role: Dict[str, float] = {}
    absence_days_by_employee: List[Dict] = []


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
    alloc: ScenarioAllocation,
    item: BacklogItem,
    employee_role_by_name: dict | None = None,
) -> AllocationResponse:
    jira_assignee_name = item.issue.assignee_display_name if item.issue else None
    resolved_role = (
        item.assignee.role if item.assignee
        else (
            employee_role_by_name.get(jira_assignee_name)
            if employee_role_by_name and jira_assignee_name
            else None
        )
    )
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
        assignee_employee_id=item.assignee_employee_id,
        assignee_display_name=(
            jira_assignee_name if jira_assignee_name
            else (item.assignee.display_name if item.assignee else None)
        ),
        assignee_role=resolved_role,
        customer=item.customer,
        cost_type=item.cost_type,
        source_category=item.issue.category if item.issue else None,
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


def _require_draft(scenario: Optional[PlanningScenario]) -> None:
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
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
    teams: Optional[str] = Query(None, description="Comma-separated team codes to filter by"),
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
    teams_list = [t.strip() for t in (teams or "").split(",") if t.strip()]
    if teams_list:
        query = query.filter(PlanningScenario.team.in_(teams_list))
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
    event_bus: EventBroadcaster = Depends(get_event_bus),
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

    items = (
        db.query(BacklogItem)
        .filter(BacklogItem.archived_at.is_(None))
        .order_by(
            BacklogItem.priority.is_(None),
            BacklogItem.priority,
            BacklogItem.title,
        )
        .all()
    )
    for idx, item in enumerate(items, start=1):
        db.add(
            ScenarioAllocation(
                scenario_id=scenario.id,
                backlog_item_id=item.id,
                included_flag=False,
                planned_hours=0,
                sort_order=float(idx),
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
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    db.refresh(scenario)
    return _to_scenario_resp(scenario)


@router.post("/scenarios/{scenario_id}/approve", response_model=ScenarioResponse)
async def approve_scenario(
    scenario_id: str,
    body: ApproveBody = ApproveBody(),
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Зафиксировать сценарий: status='approved'.

    Создаёт запись пересмотра с диффом инициатив и снапшотом нормы команды.
    """
    scenario = db.get(PlanningScenario, scenario_id)
    _require_draft(scenario)

    now = datetime.utcnow()

    # --- Порядковый номер ревизии ---
    prev_count = (
        db.query(ScenarioRevision)
        .filter(ScenarioRevision.scenario_id == scenario_id)
        .count()
    )
    revision_number = prev_count + 1

    # --- Создать запись ревизии ---
    revision = ScenarioRevision(
        scenario_id=scenario_id,
        revision_number=revision_number,
        approved_at=now,
        note=body.note,
    )
    db.add(revision)
    db.flush()

    # --- Дифф инициатив ---
    included_rows = (
        db.query(ScenarioAllocation, BacklogItem)
        .join(BacklogItem, ScenarioAllocation.backlog_item_id == BacklogItem.id)
        .filter(
            ScenarioAllocation.scenario_id == scenario_id,
            ScenarioAllocation.included_flag == True,  # noqa: E712
        )
        .all()
    )
    current_included: dict[str, str] = {
        alloc.backlog_item_id: item.title
        for alloc, item in included_rows
    }

    prev_revision = (
        db.query(ScenarioRevision)
        .filter(
            ScenarioRevision.scenario_id == scenario_id,
            ScenarioRevision.revision_number == revision_number - 1,
        )
        .first()
    )
    if prev_revision:
        prev_items = (
            db.query(ScenarioRevisionItem)
            .filter(
                ScenarioRevisionItem.revision_id == prev_revision.id,
                ScenarioRevisionItem.action == "included",
            )
            .all()
        )
        # Deleted backlog items (backlog_item_id=NULL via SET NULL FK) are silently
        # omitted from prev_included — their exclusion won't appear in this revision's diff.
        prev_included: dict[str, str] = {
            i.backlog_item_id: i.backlog_item_name
            for i in prev_items
            if i.backlog_item_id is not None
        }
        added = {k: v for k, v in current_included.items() if k not in prev_included}
        removed = {k: v for k, v in prev_included.items() if k not in current_included}
    else:
        added = current_included
        removed = {}

    for item_id, item_name in added.items():
        db.add(ScenarioRevisionItem(
            revision_id=revision.id,
            backlog_item_id=item_id,
            backlog_item_name=item_name,
            action="included",
        ))
    for item_id, item_name in removed.items():
        db.add(ScenarioRevisionItem(
            revision_id=revision.id,
            backlog_item_id=item_id,
            backlog_item_name=item_name,
            action="excluded",
        ))

    # --- Снапшот нормы команды ---
    if scenario.team and scenario.year and scenario.quarter:
        q = int(str(scenario.quarter).replace("Q", ""))
        months = QUARTER_MONTHS[q]
        emp_ids = [
            r[0]
            for r in db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team == scenario.team)
            .all()
        ]
        employees = (
            db.query(Employee)
            .filter(Employee.id.in_(emp_ids), Employee.is_active == True)  # noqa: E712
            .all()
        )
        capacity_svc = CapacityService(db)
        for emp in employees:
            for month in months:
                mc = capacity_svc.monthly_capacity(emp.id, scenario.year, month)
                db.add(ScenarioCapacitySnapshot(
                    revision_id=revision.id,
                    employee_id=emp.id,
                    employee_name=emp.display_name,
                    year=scenario.year,
                    month=month,
                    norm_hours=mc.norm_hours,
                    available_hours=mc.available_hours,
                    snapshot_taken_at=now,
                ))

    scenario.status = "approved"
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
    db.refresh(scenario)
    return _to_scenario_resp(scenario)


@router.post(
    "/scenarios/{scenario_id}/revert-to-draft", response_model=ScenarioResponse
)
async def revert_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Вернуть утверждённый сценарий в черновик для редактирования."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario.status = "draft"
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
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
    "/scenarios/{scenario_id}/copy-rules-from-template",
    response_model=List[ScenarioRuleOut],
)
async def copy_rules_from_template(
    scenario_id: str,
    year: int = Query(..., description="Год шаблона"),
    quarter: int = Query(..., ge=1, le=4, description="Квартал шаблона"),
    db: Session = Depends(get_db),
):
    """Заменить правила сценария шаблонными правилами role_capacity_rules за год/квартал."""
    sc = db.get(PlanningScenario, scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    _require_draft(sc)

    template_rules = (
        db.query(RoleCapacityRule)
        .filter(RoleCapacityRule.year == year, RoleCapacityRule.quarter == quarter)
        .all()
    )
    db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario_id).delete()
    for rcr in template_rules:
        db.add(
            ScenarioRule(
                scenario_id=scenario_id,
                role=rcr.role,
                work_type_id=rcr.work_type_id,
                percent_of_norm=rcr.percent_of_norm,
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

    # Новые allocations добавляем в конец списка — PM сам перетащит куда нужно.
    next_order = (
        db.query(func.max(ScenarioAllocation.sort_order))
        .filter(ScenarioAllocation.scenario_id == scenario_id)
        .scalar()
        or 0.0
    ) + 1.0
    for item_id in current_ids - existing_ids:
        db.add(
            ScenarioAllocation(
                scenario_id=scenario_id,
                backlog_item_id=item_id,
                included_flag=False,
                planned_hours=0,
                sort_order=next_order,
            )
        )
        next_order += 1.0
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
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(ScenarioAllocation.scenario_id == scenario_id)
        .order_by(
            # Per-scenario manual order (sort_order). NULL — в конец как fallback.
            ScenarioAllocation.sort_order.is_(None),
            ScenarioAllocation.sort_order,
            BacklogItem.title,
        )
        .all()
    )
    # Lookup для автоматического разрешения роли по имени из Jira, когда
    # assignee_employee_id не заполнен вручную.
    active_employees = db.query(Employee).filter(Employee.is_active == True).all()  # noqa: E712
    emp_role_by_name = {e.display_name: e.role for e in active_employees if e.role}
    return [_to_allocation_resp(alloc, item, emp_role_by_name) for alloc, item in rows]


@router.patch(
    "/scenarios/{scenario_id}/allocations/reorder",
    response_model=List[AllocationResponse],
)
async def reorder_allocations(
    scenario_id: str,
    body: AllocationsReorderBody,
    db: Session = Depends(get_db),
):
    """Перетащили строки мышкой — переписываем ``sort_order`` подряд: 1, 2, 3, …

    Принимает список ``allocation.id`` в желаемом порядке сверху вниз.
    Идентификаторы не из этого сценария игнорируются. Только для draft.
    Объявлен ВЫШЕ ``patch_allocation`` — иначе ``reorder`` ловится как
    ``{alloc_id}`` и не исполняется.
    """
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    _require_draft(scenario)

    allocs = (
        db.query(ScenarioAllocation)
        .filter(ScenarioAllocation.scenario_id == scenario_id)
        .all()
    )
    by_id = {a.id: a for a in allocs}

    pos = 1.0
    seen: set[str] = set()
    for aid in body.ordered_ids:
        a = by_id.get(aid)
        if a is None or aid in seen:
            continue
        a.sort_order = pos
        pos += 1.0
        seen.add(aid)

    # Те, что не упомянуты — оставляем в конце, сохраняя относительный порядок.
    leftover = sorted(
        (a for a in allocs if a.id not in seen),
        key=lambda a: (a.sort_order is None, a.sort_order or 0.0, a.id),
    )
    for a in leftover:
        a.sort_order = pos
        pos += 1.0

    db.commit()
    return await list_scenario_allocations(scenario_id, db)


@router.patch(
    "/scenarios/{scenario_id}/allocations/{alloc_id}",
    response_model=AllocationResponse,
)
async def patch_allocation(
    scenario_id: str,
    alloc_id: str,
    data: AllocationPatch,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
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
        was_included = bool(alloc.included_flag)
        alloc.included_flag = bool(patch["included"])
        if alloc.included_flag:
            if "planned_hours" not in patch and (alloc.planned_hours or 0) <= 0:
                alloc.planned_hours = item.estimate_hours or 0
            # Поднимаем строку в самый верх только при переходе False → True.
            # Снятие галочки оставляет sort_order на месте — строка не прыгает.
            if not was_included:
                current_min = (
                    db.query(func.min(ScenarioAllocation.sort_order))
                    .filter(ScenarioAllocation.scenario_id == scenario_id)
                    .scalar()
                )
                alloc.sort_order = (current_min if current_min is not None else 1.0) - 1.0
        else:
            alloc.planned_hours = 0

    if "planned_hours" in patch:
        alloc.planned_hours = patch["planned_hours"]

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
    # Re-load with issue join for response.
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == alloc.backlog_item_id)
        .first()
    )
    return _to_allocation_resp(alloc, item)


@router.patch(
    "/scenarios/{scenario_id}/allocations/{alloc_id}/assignee",
    response_model=AllocationResponse,
)
async def patch_allocation_assignee(
    scenario_id: str,
    alloc_id: str,
    data: AllocationAssigneePatch,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Сменить исполнителя на конкретной идее в сценарии."""
    alloc = (
        db.query(ScenarioAllocation)
        .filter(
            ScenarioAllocation.id == alloc_id,
            ScenarioAllocation.scenario_id == scenario_id,
        )
        .first()
    )
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")

    scenario = db.get(PlanningScenario, scenario_id)
    _require_draft(scenario)

    backlog_item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == alloc.backlog_item_id)
        .first()
    )
    if not backlog_item:
        raise HTTPException(status_code=404, detail="BacklogItem not found")

    if data.assignee_employee_id is not None:
        emp = db.query(Employee).filter(Employee.id == data.assignee_employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        backlog_item.assignee_employee_id = data.assignee_employee_id
    else:
        backlog_item.assignee_employee_id = None

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    # Reload with relationships after commit.
    backlog_item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == backlog_item.id)
        .first()
    )
    return _to_allocation_resp(alloc, backlog_item)


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
        total_by_role=summary.gross_by_role,
        total=summary.gross_total,
        work_type_rows=[
            WorkTypeRowOut(
                work_type_id=row.work_type_id,
                work_type_label=row.work_type_label,
                by_role=row.hours_by_role,
                by_role_pct=row.pct_by_role,
                total=row.total_hours,
                subtracts_from_pool=row.subtracts_from_pool,
            )
            for row in summary.work_type_rows
        ],
        available_for_backlog_by_role=summary.available_by_role,
        available_for_backlog_total=summary.available_total,
        external_qa_hours=summary.external_qa_hours,
        calendar_gross_by_role=summary.calendar_gross_by_role,
        absence_days_by_employee=summary.absence_days_by_employee,
    )


@router.get(
    "/scenarios/{scenario_id}/revisions",
    response_model=List[RevisionOut],
)
async def list_scenario_revisions(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """История пересмотров сценария: дифф инициатив и снапшот нормы по каждому утверждению."""
    if not db.get(PlanningScenario, scenario_id):
        raise HTTPException(status_code=404, detail="Scenario not found")

    revisions = (
        db.query(ScenarioRevision)
        .filter(ScenarioRevision.scenario_id == scenario_id)
        .order_by(ScenarioRevision.revision_number)
        .all()
    )

    result = []
    for rev in revisions:
        items = (
            db.query(ScenarioRevisionItem)
            .filter(ScenarioRevisionItem.revision_id == rev.id)
            .all()
        )
        snapshots = (
            db.query(ScenarioCapacitySnapshot)
            .filter(ScenarioCapacitySnapshot.revision_id == rev.id)
            .order_by(
                ScenarioCapacitySnapshot.employee_name,
                ScenarioCapacitySnapshot.month,
            )
            .all()
        )
        result.append(RevisionOut(
            id=rev.id,
            revision_number=rev.revision_number,
            approved_at=rev.approved_at.isoformat(),
            note=rev.note,
            items=[
                RevisionItemOut(
                    backlog_item_id=i.backlog_item_id,
                    backlog_item_name=i.backlog_item_name,
                    action=i.action,
                )
                for i in items
            ],
            capacity_snapshots=[
                CapacitySnapshotOut(
                    employee_id=s.employee_id,
                    employee_name=s.employee_name,
                    year=s.year,
                    month=s.month,
                    norm_hours=s.norm_hours,
                    available_hours=s.available_hours,
                )
                for s in snapshots
            ],
        ))
    return result


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
    event_bus: EventBroadcaster = Depends(get_event_bus),
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
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
    return {"status": "deleted", "id": scenario_id}
