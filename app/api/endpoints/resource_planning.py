"""Resource Planning API — ScheduledBlocks + ResourcePlan + Gantt projection."""

from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models import (
    BacklogItem,
    ResourcePlan,
    ResourcePlanAssignment,
    ScheduledBlock,
    ScheduledBlockEmployee,
    ScheduledBlockRole,
)
from app.models.user import User
from app.services.plan_quality_service import PlanQualityService
from app.services.resource_planning_service import ResourcePlanningService

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────


class ScheduledBlockCreate(BaseModel):
    team: Optional[str] = None
    role_ids: List[str] = []
    employee_ids: List[str] = []
    start_date: date
    end_date: date
    reason: str


class ScheduledBlockUpdate(BaseModel):
    team: Optional[str] = None
    role_ids: Optional[List[str]] = None
    employee_ids: Optional[List[str]] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reason: Optional[str] = None


class ScheduledBlockOut(BaseModel):
    id: str
    team: Optional[str]
    role_ids: List[str]
    employee_ids: List[str]
    start_date: date
    end_date: date
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


def _block_to_out(block: ScheduledBlock) -> "ScheduledBlockOut":
    return ScheduledBlockOut(
        id=block.id,
        team=block.team,
        role_ids=[r.role_id for r in block.roles],
        employee_ids=[e.employee_id for e in block.employees],
        start_date=block.start_date,
        end_date=block.end_date,
        reason=block.reason,
        created_at=block.created_at,
    )


class ResourcePlanCreate(BaseModel):
    scenario_id: Optional[str] = None
    team: str
    quarter: str
    year: int


class ResourcePlanOut(BaseModel):
    id: str
    scenario_id: Optional[str]
    team: Optional[str]
    quarter: Optional[str]
    year: Optional[int]
    status: str
    computed_at: Optional[datetime]
    created_at: datetime
    parent_plan_id: Optional[str]
    is_baseline: bool
    label: Optional[str]

    model_config = {"from_attributes": True}


class AssignmentOut(BaseModel):
    id: str
    backlog_item_id: str
    backlog_item_key: Optional[str] = None  # Jira issue key
    backlog_item_title: str
    phase: str
    employee_id: Optional[str]
    employee_name: Optional[str]
    employee_role: Optional[str] = None  # для аватарок-цвета
    part_number: int
    hours_allocated: Optional[float]
    start_date: Optional[date]
    end_date: Optional[date]
    is_on_critical_path: bool
    slack_days: Optional[float]
    is_pinned: bool = False
    # Главный исполнитель инициативы из утверждённого сценария
    # (BacklogItem.assignee_employee_id). Используется фронтом для
    # группировки/сортировки задач на Gantt.
    scenario_assignee_employee_id: Optional[str] = None
    scenario_assignee_name: Optional[str] = None
    # Приоритет инициативы (BacklogItem.priority). Чем выше число — тем выше
    # приоритет, фронт сортирует задачи по этому полю внутри одного исполнителя.
    priority: Optional[int] = None
    # Авто-сплит отключён, поля сохранены для обратной совместимости с фронтом.
    chunk_index: Optional[int] = None
    chunks_total: Optional[int] = None

    model_config = {"from_attributes": True}


class ConflictOut(BaseModel):
    id: str
    type: str
    severity: str
    status: str
    backlog_item_id: Optional[str]
    backlog_item_title: Optional[str]
    employee_id: Optional[str]
    assignment_id: Optional[str]
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    metric_value: Optional[float]
    message: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InitiativePertOut(BaseModel):
    backlog_item_id: str
    backlog_item_title: str
    most_likely_finish: Optional[date]
    p50_finish: Optional[date]
    p90_finish: Optional[date]
    sigma_days: float
    on_critical_path_only: bool


class DependencyOut(BaseModel):
    id: str
    plan_id: str
    from_item_id: str
    to_item_id: str
    dep_type: str
    lag_days: int
    source: str

    model_config = {"from_attributes": True}


class GanttProjection(BaseModel):
    plan: ResourcePlanOut
    assignments: List[AssignmentOut]
    conflicts: List[ConflictOut]
    pert_projection: List[InitiativePertOut]
    dependencies: List[DependencyOut] = []


class AssignmentPatch(BaseModel):
    employee_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hours_allocated: Optional[float] = None


class DependencyCreate(BaseModel):
    from_item_id: str
    to_item_id: str
    dep_type: str = "FS"
    lag_days: int = 0


class DependencyPatch(BaseModel):
    dep_type: Optional[str] = None
    lag_days: Optional[int] = None


# ── ScheduledBlocks ────────────────────────────────────────────────────────


@router.get("/scheduled-blocks", response_model=List[ScheduledBlockOut])
def list_scheduled_blocks(
    team: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(ScheduledBlock).order_by(ScheduledBlock.start_date)
    if team:
        q = q.where(ScheduledBlock.team == team)
    return [_block_to_out(b) for b in db.execute(q).scalars().all()]


@router.post("/scheduled-blocks", response_model=ScheduledBlockOut, status_code=201)
def create_scheduled_block(
    data: ScheduledBlockCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if data.end_date < data.start_date:
        raise HTTPException(422, "end_date must be >= start_date")
    block = ScheduledBlock(
        team=data.team,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
    )
    block.roles = [ScheduledBlockRole(role_id=r) for r in data.role_ids]
    block.employees = [ScheduledBlockEmployee(employee_id=e) for e in data.employee_ids]
    db.add(block)
    db.commit()
    db.refresh(block)
    return _block_to_out(block)


@router.patch("/scheduled-blocks/{block_id}", response_model=ScheduledBlockOut)
def update_scheduled_block(
    block_id: str,
    data: ScheduledBlockUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    block = db.get(ScheduledBlock, block_id)
    if not block:
        raise HTTPException(404, "ScheduledBlock not found")
    patch = data.model_dump(exclude_unset=True)
    role_ids = patch.pop("role_ids", None)
    employee_ids = patch.pop("employee_ids", None)
    for k, v in patch.items():
        setattr(block, k, v)
    if block.end_date < block.start_date:
        raise HTTPException(422, "end_date must be >= start_date")
    if role_ids is not None:
        block.roles = [ScheduledBlockRole(role_id=r) for r in role_ids]
    if employee_ids is not None:
        block.employees = [ScheduledBlockEmployee(employee_id=e) for e in employee_ids]
    db.commit()
    db.refresh(block)
    return _block_to_out(block)


@router.delete("/scheduled-blocks/{block_id}", status_code=204)
def delete_scheduled_block(
    block_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    block = db.get(ScheduledBlock, block_id)
    if not block:
        raise HTTPException(404, "ScheduledBlock not found")
    db.delete(block)
    db.commit()


# ── ResourcePlans ──────────────────────────────────────────────────────────


@router.get("/resource-plans", response_model=List[ResourcePlanOut])
def list_plans(
    team: Optional[str] = Query(None),
    include_forks: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Список планов. По умолчанию: один план на сценарий (latest), форки скрыты.

    Форки доступны через `include_forks=true` или через явный GET /resource-plans/{id}.
    """
    q = select(ResourcePlan).order_by(ResourcePlan.created_at.desc())
    if team:
        q = q.where(ResourcePlan.team == team)
    if not include_forks:
        q = q.where(ResourcePlan.parent_plan_id.is_(None))
    rows = db.execute(q).scalars().all()
    if include_forks:
        return rows
    # Дедуп: один план на (scenario_id, team, quarter, year). При коллизии — latest.
    seen: dict = {}
    for p in rows:
        key = (p.scenario_id, p.team, p.quarter, p.year)
        if key not in seen:
            seen[key] = p
    return list(seen.values())


@router.post("/resource-plans", response_model=ResourcePlanOut, status_code=201)
def create_plan(
    data: ResourcePlanCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = ResourcePlan(**data.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/resource-plans/{plan_id}", response_model=ResourcePlanOut)
def get_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "ResourcePlan not found")
    return plan


@router.delete("/resource-plans/{plan_id}", status_code=204)
def delete_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404)
    db.delete(plan)
    db.commit()


@router.post("/resource-plans/{plan_id}/compute", response_model=ResourcePlanOut)
def compute_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "ResourcePlan not found")
    plan.status = "computing"
    db.commit()
    svc = ResourcePlanningService(db)
    svc.compute_schedule(plan_id)
    db.refresh(plan)
    return plan


def _compute_pert_projection(plan, assignments, db):
    """PERT P50/P90 finish per initiative based on critical-path phases."""
    from collections import defaultdict
    from datetime import timedelta as _td

    from app.models import BacklogItem
    from app.services.pert_calculator import aggregate_path_pert, p_quantile_finish

    by_item: dict = defaultdict(list)
    for a in assignments:
        if a.is_on_critical_path and a.start_date and a.end_date:
            by_item[a.backlog_item_id].append(a)

    item_ids = list(by_item.keys())
    if not item_ids:
        return []
    items = (
        db.execute(select(BacklogItem).where(BacklogItem.id.in_(item_ids)))
        .scalars()
        .all()
    )
    items_by_id = {i.id: i for i in items}

    result = []
    for item_id, phases_assigns in by_item.items():
        bi = items_by_id.get(item_id)
        if not bi:
            continue
        opt = bi.optimistic_multiplier or 0.7
        pess = bi.pessimistic_multiplier or 1.5
        triples = []
        most_likely_finish = max(a.end_date for a in phases_assigns)
        for a in phases_assigns:
            days = (a.end_date - a.start_date).days + 1
            triples.append((days * opt, float(days), days * pess))
        mean, sigma = aggregate_path_pert(triples)
        first_start = min(a.start_date for a in phases_assigns)
        p50 = first_start + _td(days=int(round(p_quantile_finish(mean, sigma, 0.5))))
        p90 = first_start + _td(days=int(round(p_quantile_finish(mean, sigma, 0.9))))
        result.append(
            InitiativePertOut(
                backlog_item_id=item_id,
                backlog_item_title=bi.title,
                most_likely_finish=most_likely_finish,
                p50_finish=p50,
                p90_finish=p90,
                sigma_days=sigma,
                on_critical_path_only=True,
            )
        )
    return result


@router.get("/resource-plans/{plan_id}/gantt", response_model=GanttProjection)
def get_gantt(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404)

    assignments_raw = (
        db.execute(
            select(ResourcePlanAssignment)
            .options(
                joinedload(ResourcePlanAssignment.backlog_item)
                .joinedload(BacklogItem.issue)
            )
            .options(
                joinedload(ResourcePlanAssignment.backlog_item)
                .joinedload(BacklogItem.assignee)
            )
            .options(joinedload(ResourcePlanAssignment.employee))
            .where(ResourcePlanAssignment.plan_id == plan_id)
            .order_by(ResourcePlanAssignment.start_date)
        )
        .scalars()
        .unique()
        .all()
    )

    # Вычисляем chunks_total per (backlog_item_id, phase): если строк > 1 — это сплит.
    from collections import Counter as _Counter
    phase_counts: dict[tuple, int] = _Counter(
        (a.backlog_item_id, a.phase) for a in assignments_raw
    )

    assignments = [
        AssignmentOut(
            id=a.id,
            backlog_item_id=a.backlog_item_id,
            backlog_item_key=(a.backlog_item.issue.key if a.backlog_item and a.backlog_item.issue else None),
            backlog_item_title=a.backlog_item.title if a.backlog_item else "",
            phase=a.phase,
            employee_id=a.employee_id,
            employee_name=a.employee.display_name if a.employee else None,
            employee_role=(a.employee.role if a.employee else None),
            part_number=a.part_number,
            hours_allocated=a.hours_allocated,
            start_date=a.start_date,
            end_date=a.end_date,
            is_on_critical_path=a.is_on_critical_path,
            slack_days=a.slack_days,
            is_pinned=a.is_pinned,
            scenario_assignee_employee_id=(
                a.backlog_item.assignee_employee_id if a.backlog_item else None
            ),
            scenario_assignee_name=(
                a.backlog_item.assignee.display_name
                if a.backlog_item and a.backlog_item.assignee
                else None
            ),
            priority=(a.backlog_item.priority if a.backlog_item else None),
            chunk_index=(a.part_number - 1) if phase_counts.get((a.backlog_item_id, a.phase), 1) > 1 else None,
            chunks_total=phase_counts.get((a.backlog_item_id, a.phase)) if phase_counts.get((a.backlog_item_id, a.phase), 1) > 1 else None,
        )
        for a in assignments_raw
    ]

    conflicts = _detect_conflicts(plan, assignments_raw, db)
    pert_projection = _compute_pert_projection(plan, assignments_raw, db)

    from app.models import PlanItemDependency

    deps_raw = (
        db.execute(
            select(PlanItemDependency).where(PlanItemDependency.plan_id == plan_id)
        )
        .scalars()
        .all()
    )
    deps = [
        DependencyOut(
            id=d.id,
            plan_id=d.plan_id,
            from_item_id=d.from_item_id,
            to_item_id=d.to_item_id,
            dep_type=d.dep_type,
            lag_days=d.lag_days,
            source=d.source,
        )
        for d in deps_raw
    ]

    return GanttProjection(
        plan=plan,
        assignments=assignments,
        conflicts=conflicts,
        pert_projection=pert_projection,
        dependencies=deps,
    )


@router.patch(
    "/resource-plans/{plan_id}/assignments/{assignment_id}",
    response_model=AssignmentOut,
)
def patch_assignment(
    plan_id: str,
    assignment_id: str,
    data: AssignmentPatch,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    a = db.execute(
        select(ResourcePlanAssignment)
        .options(
            joinedload(ResourcePlanAssignment.backlog_item).joinedload(BacklogItem.issue)
        )
        .options(joinedload(ResourcePlanAssignment.employee))
        .where(
            ResourcePlanAssignment.id == assignment_id,
            ResourcePlanAssignment.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Assignment not found")

    patch = data.model_dump(exclude_unset=True)
    new_start = patch.get("start_date", a.start_date)
    new_end = patch.get("end_date", a.end_date)
    if new_start and new_end and new_end < new_start:
        raise HTTPException(422, "end_date must be >= start_date")

    # Явный выбор сотрудника — закрепить назначение
    if "employee_id" in patch:
        a.pinned_employee = True

    for k, v in patch.items():
        setattr(a, k, v)

    plan = db.get(ResourcePlan, plan_id)
    if plan:
        plan.status = "stale"

    # Snapshot values before commit (SQLite session expire caveat)
    a_id = a.id
    a_backlog_item_id = a.backlog_item_id
    a_backlog_item_key = (a.backlog_item.issue.key if a.backlog_item and a.backlog_item.issue else None)
    a_backlog_item_title = a.backlog_item.title if a.backlog_item else ""
    a_phase = a.phase
    a_part_number = a.part_number
    a_hours_allocated = a.hours_allocated
    a_start_date = a.start_date
    a_end_date = a.end_date
    a_is_on_critical_path = a.is_on_critical_path
    a_slack_days = a.slack_days
    a_employee_id = a.employee_id
    a_employee_role = a.employee.role if a.employee else None
    a_is_pinned = a.is_pinned
    a_priority = a.backlog_item.priority if a.backlog_item else None

    db.commit()
    db.refresh(a)

    emp_name = a.employee.display_name if a.employee else None

    return AssignmentOut(
        id=a_id,
        backlog_item_id=a_backlog_item_id,
        backlog_item_key=a_backlog_item_key,
        backlog_item_title=a_backlog_item_title,
        phase=a_phase,
        employee_id=a_employee_id,
        employee_name=emp_name,
        employee_role=a_employee_role,
        part_number=a_part_number,
        hours_allocated=a_hours_allocated,
        start_date=a_start_date,
        end_date=a_end_date,
        is_on_critical_path=a_is_on_critical_path,
        slack_days=a_slack_days,
        is_pinned=a_is_pinned,
        priority=a_priority,
    )


def _detect_conflicts(plan, assignments, db):
    """Read persistent conflicts from DB. Detection runs in compute_schedule."""
    from app.models import PlanConflict, BacklogItem

    rows = (
        db.execute(select(PlanConflict).where(PlanConflict.plan_id == plan.id))
        .scalars()
        .all()
    )

    item_ids = {r.backlog_item_id for r in rows if r.backlog_item_id}
    titles: dict = {}
    if item_ids:
        bi_rows = (
            db.execute(select(BacklogItem).where(BacklogItem.id.in_(item_ids)))
            .scalars()
            .all()
        )
        titles = {b.id: b.title for b in bi_rows}

    return [
        ConflictOut(
            id=r.id,
            type=r.type,
            severity=r.severity,
            status=r.status,
            backlog_item_id=r.backlog_item_id,
            backlog_item_title=titles.get(r.backlog_item_id)
            if r.backlog_item_id
            else None,
            employee_id=r.employee_id,
            assignment_id=r.assignment_id,
            window_start=r.window_start,
            window_end=r.window_end,
            metric_value=r.metric_value,
            message=r.message,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


class ConflictPatch(BaseModel):
    status: str  # acknowledged | muted | open | resolved


@router.patch(
    "/resource-plans/{plan_id}/conflicts/{conflict_id}",
    response_model=ConflictOut,
)
def patch_conflict(
    plan_id: str,
    conflict_id: str,
    data: ConflictPatch,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models import PlanConflict, BacklogItem

    valid = {"open", "acknowledged", "muted", "resolved"}
    if data.status not in valid:
        raise HTTPException(422, f"status must be one of {sorted(valid)}")

    c = db.execute(
        select(PlanConflict).where(
            PlanConflict.id == conflict_id,
            PlanConflict.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Conflict not found")

    c.status = data.status

    title = None
    if c.backlog_item_id:
        b = db.get(BacklogItem, c.backlog_item_id)
        title = b.title if b else None
    snap = {
        "id": c.id,
        "type": c.type,
        "severity": c.severity,
        "status": c.status,
        "backlog_item_id": c.backlog_item_id,
        "backlog_item_title": title,
        "employee_id": c.employee_id,
        "assignment_id": c.assignment_id,
        "window_start": c.window_start,
        "window_end": c.window_end,
        "metric_value": c.metric_value,
        "message": c.message,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }

    db.commit()
    return ConflictOut(**snap)


# ── Diff ───────────────────────────────────────────────────────────────────


class PlanDiffOut(BaseModel):
    baseline_id: str
    scenario_id: str
    assignment_shifts: List[dict]
    baseline_metrics: dict
    scenario_metrics: dict


@router.get(
    "/resource-plans/{scenario_id}/diff/{baseline_id}",
    response_model=PlanDiffOut,
)
def get_plan_diff(
    scenario_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.services.plan_diff import diff_plans

    try:
        return diff_plans(db, baseline_id, scenario_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Fork ───────────────────────────────────────────────────────────────────


class ForkRequest(BaseModel):
    label: Optional[str] = None


@router.post(
    "/resource-plans/{plan_id}/fork",
    response_model=ResourcePlanOut,
    status_code=201,
)
def fork_plan(
    plan_id: str,
    data: ForkRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models import PlanItemDependency

    src = db.get(ResourcePlan, plan_id)
    if not src:
        raise HTTPException(404, "ResourcePlan not found")

    new_plan = ResourcePlan(
        scenario_id=src.scenario_id,
        team=src.team,
        quarter=src.quarter,
        year=src.year,
        status=src.status,
        parent_plan_id=src.id,
        is_baseline=False,
        label=data.label,
    )
    db.add(new_plan)
    db.flush()

    src_assignments = (
        db.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == src.id
            )
        )
        .scalars()
        .all()
    )
    for a in src_assignments:
        db.add(
            ResourcePlanAssignment(
                plan_id=new_plan.id,
                backlog_item_id=a.backlog_item_id,
                phase=a.phase,
                employee_id=a.employee_id,
                part_number=a.part_number,
                hours_allocated=a.hours_allocated,
                start_date=a.start_date,
                end_date=a.end_date,
                is_on_critical_path=a.is_on_critical_path,
                slack_days=a.slack_days,
            )
        )

    src_deps = (
        db.execute(
            select(PlanItemDependency).where(PlanItemDependency.plan_id == src.id)
        )
        .scalars()
        .all()
    )
    for d in src_deps:
        db.add(
            PlanItemDependency(
                plan_id=new_plan.id,
                from_item_id=d.from_item_id,
                to_item_id=d.to_item_id,
                dep_type=d.dep_type,
                lag_days=d.lag_days,
                source=d.source,
            )
        )

    # Conflicts intentionally NOT cloned (forks start clean)

    snap = {
        "id": new_plan.id,
        "scenario_id": new_plan.scenario_id,
        "team": new_plan.team,
        "quarter": new_plan.quarter,
        "year": new_plan.year,
        "status": new_plan.status,
        "computed_at": new_plan.computed_at,
        "created_at": new_plan.created_at,
        "parent_plan_id": new_plan.parent_plan_id,
        "is_baseline": new_plan.is_baseline,
        "label": new_plan.label,
    }
    db.commit()
    return ResourcePlanOut(**snap)


@router.get(
    "/resource-plans/{plan_id}/dependencies",
    response_model=List[DependencyOut],
)
def list_dependencies(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models import PlanItemDependency

    if not db.get(ResourcePlan, plan_id):
        raise HTTPException(404, "ResourcePlan not found")
    rows = db.execute(
        select(PlanItemDependency).where(PlanItemDependency.plan_id == plan_id)
    ).scalars().all()
    return [
        DependencyOut(
            id=d.id,
            plan_id=d.plan_id,
            from_item_id=d.from_item_id,
            to_item_id=d.to_item_id,
            dep_type=d.dep_type,
            lag_days=d.lag_days,
            source=d.source,
        )
        for d in rows
    ]


@router.post(
    "/resource-plans/{plan_id}/dependencies",
    response_model=DependencyOut,
    status_code=201,
)
def create_dependency(
    plan_id: str,
    data: DependencyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models import PlanItemDependency

    if not db.get(ResourcePlan, plan_id):
        raise HTTPException(404, "ResourcePlan not found")
    if data.from_item_id == data.to_item_id:
        raise HTTPException(422, "Cannot create self-dependency")
    if data.dep_type not in ("FS", "SS", "FF", "SF"):
        raise HTTPException(422, "dep_type must be one of FS|SS|FF|SF")
    dep = PlanItemDependency(
        plan_id=plan_id,
        from_item_id=data.from_item_id,
        to_item_id=data.to_item_id,
        dep_type=data.dep_type,
        lag_days=data.lag_days,
        source="manual",
    )
    db.add(dep)
    plan = db.get(ResourcePlan, plan_id)
    if plan:
        plan.status = "stale"
    snap = DependencyOut(
        id=dep.id,
        plan_id=plan_id,
        from_item_id=dep.from_item_id,
        to_item_id=dep.to_item_id,
        dep_type=dep.dep_type,
        lag_days=dep.lag_days,
        source=dep.source,
    )
    db.commit()
    return snap


@router.patch(
    "/resource-plans/{plan_id}/dependencies/{dep_id}",
    response_model=DependencyOut,
)
def patch_dependency(
    plan_id: str,
    dep_id: str,
    data: DependencyPatch,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models import PlanItemDependency

    dep = db.execute(
        select(PlanItemDependency).where(
            PlanItemDependency.id == dep_id,
            PlanItemDependency.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not dep:
        raise HTTPException(404, "Dependency not found")
    patch = data.model_dump(exclude_unset=True)
    if "dep_type" in patch and patch["dep_type"] not in ("FS", "SS", "FF", "SF"):
        raise HTTPException(422, "dep_type must be one of FS|SS|FF|SF")
    for k, v in patch.items():
        setattr(dep, k, v)
    plan = db.get(ResourcePlan, plan_id)
    if plan:
        plan.status = "stale"
    snap = DependencyOut(
        id=dep.id,
        plan_id=plan_id,
        from_item_id=dep.from_item_id,
        to_item_id=dep.to_item_id,
        dep_type=dep.dep_type,
        lag_days=dep.lag_days,
        source=dep.source,
    )
    db.commit()
    return snap


@router.delete(
    "/resource-plans/{plan_id}/dependencies/{dep_id}",
    status_code=204,
)
def delete_dependency(
    plan_id: str,
    dep_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models import PlanItemDependency

    dep = db.execute(
        select(PlanItemDependency).where(
            PlanItemDependency.id == dep_id,
            PlanItemDependency.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not dep:
        raise HTTPException(404, "Dependency not found")
    db.delete(dep)
    plan = db.get(ResourcePlan, plan_id)
    if plan:
        plan.status = "stale"
    db.commit()
    return None


class QualityMetricSchema(BaseModel):
    plan_id: str
    overload_days_pct: float
    late_count: int
    mean_utilization_pct: float
    computed_at: datetime


@router.get(
    "/resource-plans/{plan_id}/quality",
    response_model=QualityMetricSchema,
)
def get_plan_quality(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> QualityMetricSchema:
    """Метрика качества плана: % перегрузок, просрочки, использование ёмкости."""
    try:
        metric = PlanQualityService(db).compute(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return QualityMetricSchema(
        plan_id=metric["plan_id"],
        overload_days_pct=metric["overload_days_pct"],
        late_count=metric["late_count"],
        mean_utilization_pct=metric["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )
