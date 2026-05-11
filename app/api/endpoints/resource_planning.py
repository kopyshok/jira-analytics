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
from app.models.user_rp_preferences import UserRpPreferences
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


class UnavailableDay(BaseModel):
    date: date
    type: str  # weekend | holiday | absence | block


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
    pinned_employee: bool = False
    pinned_start: bool = False
    pinned_split: bool = False
    manual_edit_at: Optional[datetime] = None
    predecessor_ids: List[str] = []
    unavailable_days: List[UnavailableDay] = []
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
    employee_name: Optional[str] = None
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


class EmployeeLoadDay(BaseModel):
    date: date
    pct: float


class EmployeeLoadOut(BaseModel):
    employee_id: str
    employee_name: Optional[str]
    employee_role: Optional[str] = None
    days: List[EmployeeLoadDay]


class GanttProjection(BaseModel):
    plan: ResourcePlanOut
    assignments: List[AssignmentOut]
    conflicts: List[ConflictOut]
    pert_projection: List[InitiativePertOut]
    dependencies: List[DependencyOut] = []
    employee_load: List[EmployeeLoadOut] = []


class AssignmentPatch(BaseModel):
    employee_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hours_allocated: Optional[float] = None
    predecessor_ids: Optional[List[str]] = None


class DependencyCreate(BaseModel):
    from_item_id: str
    to_item_id: str
    dep_type: str = "FS"
    lag_days: int = 0


class DependencyPatch(BaseModel):
    dep_type: Optional[str] = None
    lag_days: Optional[int] = None


# ── User RP preferences ─────────────────────────────────────────────────────


class UserRpPrefsSchema(BaseModel):
    hide_weekends: bool = False
    collapsed_initiative_ids: List[str] = []
    view_mode: Optional[str] = None
    show_relay: bool = True


@router.get("/preferences", response_model=UserRpPrefsSchema)
def get_user_rp_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-user настройки страницы /resource-planning."""
    p = db.get(UserRpPreferences, current_user.id)
    if not p:
        return UserRpPrefsSchema()
    return UserRpPrefsSchema(
        hide_weekends=p.hide_weekends,
        collapsed_initiative_ids=p.collapsed_initiative_ids or [],
        view_mode=p.view_mode,
        show_relay=p.show_relay,
    )


@router.patch("/preferences", response_model=UserRpPrefsSchema)
def patch_user_rp_preferences(
    payload: UserRpPrefsSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.get(UserRpPreferences, current_user.id)
    if not p:
        p = UserRpPreferences(user_id=current_user.id)
        db.add(p)
    p.hide_weekends = payload.hide_weekends
    p.collapsed_initiative_ids = list(payload.collapsed_initiative_ids or [])
    p.view_mode = payload.view_mode
    p.show_relay = payload.show_relay
    db.commit()
    db.refresh(p)
    return UserRpPrefsSchema(
        hide_weekends=p.hide_weekends,
        collapsed_initiative_ids=p.collapsed_initiative_ids or [],
        view_mode=p.view_mode,
        show_relay=p.show_relay,
    )


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
    from datetime import timedelta as _td

    from app.models import Absence, ProductionCalendarDay
    from app.models.phase_predecessor import PhasePredecessor
    from app.models.employee_team import EmployeeTeam

    phase_counts: dict[tuple, int] = _Counter(
        (a.backlog_item_id, a.phase) for a in assignments_raw
    )

    # Предшественники по плану.
    pred_rows = (
        db.execute(
            select(PhasePredecessor)
            .join(
                ResourcePlanAssignment,
                PhasePredecessor.successor_assignment_id == ResourcePlanAssignment.id,
            )
            .where(ResourcePlanAssignment.plan_id == plan_id)
        )
        .scalars()
        .all()
    )
    preds_by_succ: dict[str, list[str]] = {}
    for p in pred_rows:
        preds_by_succ.setdefault(p.successor_assignment_id, []).append(
            p.predecessor_assignment_id
        )

    # Календарь и отсутствия для unavailable_days в каждом баре.
    cal_rows = (
        db.execute(select(ProductionCalendarDay)).scalars().all()
    )
    cal_map = {row.date: row.hours for row in cal_rows}

    emp_ids_in_plan = {a.employee_id for a in assignments_raw if a.employee_id}
    absences_by_emp: dict[str, list[Absence]] = {}
    if emp_ids_in_plan:
        absences = (
            db.execute(select(Absence).where(Absence.employee_id.in_(emp_ids_in_plan)))
            .scalars()
            .all()
        )
        for ab in absences:
            absences_by_emp.setdefault(ab.employee_id, []).append(ab)

    def _unavailable_days(a: ResourcePlanAssignment) -> list[UnavailableDay]:
        if not a.start_date or not a.end_date:
            return []
        out: list[UnavailableDay] = []
        d = a.start_date
        emp_absences = absences_by_emp.get(a.employee_id, [])
        while d <= a.end_date:
            cal_h = cal_map.get(d, None)
            kind: Optional[str] = None
            if cal_h is None:
                if d.weekday() >= 5:
                    kind = "weekend"
            else:
                if cal_h == 0:
                    kind = "weekend" if d.weekday() >= 5 else "holiday"
            if a.employee_id and any(
                ab.start_date <= d <= ab.end_date for ab in emp_absences
            ):
                kind = "absence"
            if kind:
                out.append(UnavailableDay(date=d, type=kind))
            d += _td(days=1)
        return out

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
            pinned_employee=a.pinned_employee,
            pinned_start=a.pinned_start,
            pinned_split=a.pinned_split,
            manual_edit_at=a.manual_edit_at,
            predecessor_ids=preds_by_succ.get(a.id, []),
            unavailable_days=_unavailable_days(a),
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

    # Posuточная нагрузка сотрудников команды плана для тепловой карты.
    employee_load: list[EmployeeLoadOut] = []
    if plan.team:
        from app.models import Employee
        from app.services.resource_planning_service import ResourcePlanningService

        plan_employees = (
            db.execute(
                select(Employee)
                .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
                .where(
                    EmployeeTeam.team == plan.team,
                    Employee.is_active == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        if plan_employees:
            svc = ResourcePlanningService(db)
            q_start, q_end = svc._quarter_bounds(plan)
            avail = svc.build_availability(plan_employees, q_start, q_end, [])
            # Часы по дням на сотрудника по фазам (равномерно по диапазону фазы).
            used: dict[str, dict] = {e.id: {} for e in plan_employees}
            for a in assignments_raw:
                if not a.employee_id or not a.start_date or not a.end_date:
                    continue
                if a.employee_id not in used:
                    continue
                total_days = max(1, (a.end_date - a.start_date).days + 1)
                per_day = (a.hours_allocated or 0.0) / total_days
                d = a.start_date
                while d <= a.end_date:
                    used[a.employee_id][d] = used[a.employee_id].get(d, 0.0) + per_day
                    d += _td(days=1)
            for e in plan_employees:
                days_out: list[EmployeeLoadDay] = []
                d = q_start
                while d <= q_end:
                    av = avail.get(e.id, {}).get(d, 0.0)
                    u = used.get(e.id, {}).get(d, 0.0)
                    pct = (u / av * 100.0) if av > 0 else 0.0
                    days_out.append(EmployeeLoadDay(date=d, pct=round(pct, 1)))
                    d += _td(days=1)
                employee_load.append(
                    EmployeeLoadOut(
                        employee_id=e.id,
                        employee_name=e.display_name,
                        employee_role=e.role,
                        days=days_out,
                    )
                )

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
        employee_load=employee_load,
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

    # predecessor_ids — отдельная ветка с проверкой цикла, не пишется в Assignment
    new_predecessor_ids = patch.pop("predecessor_ids", None)

    new_start = patch.get("start_date", a.start_date)
    new_end = patch.get("end_date", a.end_date)

    # Если пользователь сдвигает start_date без явного end_date — двигаем end на ту
    # же дельту, чтобы сохранить длительность фазы.
    if (
        "start_date" in patch
        and "end_date" not in patch
        and a.start_date
        and a.end_date
        and patch["start_date"]
    ):
        delta_days = (patch["start_date"] - a.start_date).days
        if delta_days != 0:
            from datetime import timedelta as _td

            new_end = a.end_date + _td(days=delta_days)
            patch["end_date"] = new_end

    if new_start and new_end and new_end < new_start:
        raise HTTPException(422, "end_date must be >= start_date")

    # Явный выбор сотрудника — закрепить назначение
    if "employee_id" in patch:
        a.pinned_employee = True
        a.manual_edit_at = datetime.utcnow()

    if "start_date" in patch:
        a.pinned_start = True
        a.manual_edit_at = datetime.utcnow()

    for k, v in patch.items():
        setattr(a, k, v)

    if new_predecessor_ids is not None:
        from app.models.phase_predecessor import PhasePredecessor

        # Удалить существующие рёбра у этого назначения и вставить новые с
        # проверкой цикла. Цикл — 400.
        db.execute(
            PhasePredecessor.__table__.delete().where(
                PhasePredecessor.successor_assignment_id == a.id
            )
        )
        db.flush()
        svc_for_cycle = ResourcePlanningService(db)
        try:
            for pid in new_predecessor_ids:
                if pid == a.id:
                    raise HTTPException(400, "cycle: self-reference")
                svc_for_cycle.add_predecessor(successor_id=a.id, predecessor_id=pid)
        except ValueError as e:
            db.rollback()
            raise HTTPException(400, f"cycle: {e}")
        a.manual_edit_at = datetime.utcnow()

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


class SplitRequest(BaseModel):
    parts: List[float]
    cascade: bool = True


def _assignment_to_dict(a: ResourcePlanAssignment) -> dict:
    return {
        "id": a.id,
        "plan_id": a.plan_id,
        "backlog_item_id": a.backlog_item_id,
        "phase": a.phase,
        "employee_id": a.employee_id,
        "part_number": a.part_number,
        "hours_allocated": a.hours_allocated,
        "start_date": a.start_date.isoformat() if a.start_date else None,
        "end_date": a.end_date.isoformat() if a.end_date else None,
        "pinned_employee": a.pinned_employee,
        "pinned_start": a.pinned_start,
        "pinned_split": a.pinned_split,
        "is_pinned": a.is_pinned,
        "manual_edit_at": (
            a.manual_edit_at.isoformat() if a.manual_edit_at else None
        ),
    }


@router.post(
    "/resource-plans/{plan_id}/assignments/{assignment_id}/split",
)
def split_assignment(
    plan_id: str,
    assignment_id: str,
    payload: SplitRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    a = db.get(ResourcePlanAssignment, assignment_id)
    if not a or a.plan_id != plan_id:
        raise HTTPException(404, "Assignment not found")
    svc = ResourcePlanningService(db)
    try:
        parts, cascaded = svc.split_assignment(
            assignment_id, payload.parts, payload.cascade
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "parts": [_assignment_to_dict(p) for p in parts],
        "cascaded": [_assignment_to_dict(c) for c in cascaded],
    }


@router.post(
    "/resource-plans/{plan_id}/assignments/{assignment_id}/merge",
)
def merge_assignment(
    plan_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    a = db.get(ResourcePlanAssignment, assignment_id)
    if not a or a.plan_id != plan_id:
        raise HTTPException(404, "Assignment not found")
    svc = ResourcePlanningService(db)
    try:
        merged = svc.merge_assignment(assignment_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"assignment": _assignment_to_dict(merged)}


@router.delete(
    "/resource-plans/{plan_id}/assignments/{assignment_id}/manual-edit",
)
def clear_manual_edits(
    plan_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    a = db.get(ResourcePlanAssignment, assignment_id)
    if not a or a.plan_id != plan_id:
        raise HTTPException(404, "Assignment not found")
    a.pinned_start = False
    a.pinned_employee = False
    a.pinned_split = False
    a.manual_edit_at = None
    plan = db.get(ResourcePlan, plan_id)
    if plan:
        plan.status = "stale"
    db.commit()
    db.refresh(a)
    return {"assignment": _assignment_to_dict(a)}


def _detect_conflicts(plan, assignments, db):
    """Read persistent conflicts from DB. Detection runs in compute_schedule."""
    from app.models import BacklogItem, Employee, PlanConflict

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

    emp_ids = {r.employee_id for r in rows if r.employee_id}
    emp_names: dict = {}
    if emp_ids:
        emp_rows = (
            db.execute(select(Employee).where(Employee.id.in_(emp_ids)))
            .scalars()
            .all()
        )
        emp_names = {e.id: e.display_name or e.id for e in emp_rows}

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
            employee_name=emp_names.get(r.employee_id) if r.employee_id else None,
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


@router.get("/resource-plans/{plan_id}/conflicts")
def list_conflicts(
    plan_id: str,
    group_by: str = Query("item", pattern="^(item|employee|type)$"),
    severity: Optional[str] = None,
    status: str = "active",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Сгруппированные конфликты плана для конфликт-панели.

    `status='active'` — open + acknowledged; `'all'` — включая muted/resolved;
    либо явный статус (`open`, `muted`, ...).
    `group_by='item'` — по инициативам; `'employee'` — по сотрудникам;
    `'type'` — по типу конфликта.
    """
    from app.models import BacklogItem, Employee, PlanConflict

    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    q = select(PlanConflict).where(PlanConflict.plan_id == plan_id)
    if severity:
        q = q.where(PlanConflict.severity == severity)
    if status == "active":
        q = q.where(PlanConflict.status.in_(["open", "acknowledged"]))
    elif status != "all":
        q = q.where(PlanConflict.status == status)
    rows = db.execute(q).scalars().all()

    if not rows:
        return {"groups": []}

    item_titles: dict[str, str] = {}
    item_ids = {r.backlog_item_id for r in rows if r.backlog_item_id}
    if item_ids:
        for b in db.execute(
            select(BacklogItem).where(BacklogItem.id.in_(item_ids))
        ).scalars():
            item_titles[b.id] = b.title

    employee_names: dict[str, str] = {}
    emp_ids = {r.employee_id for r in rows if r.employee_id}
    if emp_ids:
        for e in db.execute(
            select(Employee).where(Employee.id.in_(emp_ids))
        ).scalars():
            employee_names[e.id] = e.display_name or e.id

    def _to_payload(r) -> dict:
        return {
            "id": r.id,
            "type": r.type,
            "severity": r.severity,
            "status": r.status,
            "backlog_item_id": r.backlog_item_id,
            "backlog_item_title": item_titles.get(r.backlog_item_id)
            if r.backlog_item_id
            else None,
            "employee_id": r.employee_id,
            "employee_name": employee_names.get(r.employee_id)
            if r.employee_id
            else None,
            "assignment_id": r.assignment_id,
            "window_start": r.window_start.isoformat() if r.window_start else None,
            "window_end": r.window_end.isoformat() if r.window_end else None,
            "metric_value": r.metric_value,
            "message": r.message,
        }

    grouped: dict[tuple, list[dict]] = {}
    for r in rows:
        if group_by == "item":
            key = (r.backlog_item_id, item_titles.get(r.backlog_item_id) or "—")
        elif group_by == "employee":
            key = (r.employee_id, employee_names.get(r.employee_id) or "—")
        else:
            key = (r.type, r.type)
        grouped.setdefault(key, []).append(_to_payload(r))

    groups = [
        {"key": k[0], "label": k[1], "conflicts": v}
        for k, v in sorted(grouped.items(), key=lambda kv: kv[0][1] or "")
    ]
    return {"group_by": group_by, "groups": groups}


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


@router.get("/resource-plans/{plan_id}/conflicts/{conflict_id}/explain")
def explain_conflict(
    plan_id: str,
    conflict_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Расчёт конфликта в деталях: доступность сотрудника на проблемный день,
    список перекрывающих назначений с долей часов в день, итог demand vs available.

    Возвращает:
        type, severity, message, date (YYYY-MM-DD), employee_id, employee_name,
        available_hours, demand_hours, overload_pct, contributors[].

    Для не-OVERLOAD_* возвращает базовые поля без contributors.
    """
    from datetime import timedelta as _td
    from app.models import Employee, PlanConflict

    c = db.execute(
        select(PlanConflict).where(
            PlanConflict.id == conflict_id,
            PlanConflict.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Conflict not found")

    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    target_date = c.window_start.date() if c.window_start else None
    emp_name: Optional[str] = None
    if c.employee_id:
        e = db.get(Employee, c.employee_id)
        emp_name = e.display_name if e else None

    base = {
        "id": c.id,
        "type": c.type,
        "severity": c.severity,
        "message": c.message,
        "date": target_date.isoformat() if target_date else None,
        "employee_id": c.employee_id,
        "employee_name": emp_name,
        "available_hours": None,
        "demand_hours": None,
        "overload_pct": None,
        "contributors": [],
    }

    is_overload = c.type.startswith("OVERLOAD_")
    if not is_overload or not target_date or not c.employee_id:
        return base

    # Команда плана — нужна для build_availability (blocks/employees).
    team = plan.team
    employees = (
        db.execute(
            select(Employee).where(
                (Employee.team == team) if team else Employee.id == c.employee_id
            )
        )
        .scalars()
        .all()
    )
    # На всякий случай гарантируем, что виновник попал в выборку.
    if c.employee_id not in {e.id for e in employees}:
        owner = db.get(Employee, c.employee_id)
        if owner:
            employees.append(owner)

    blocks = (
        db.execute(
            select(ScheduledBlock).where(
                (ScheduledBlock.team == team) | (ScheduledBlock.team.is_(None))
            )
            if team
            else select(ScheduledBlock)
        )
        .scalars()
        .all()
    )

    svc = ResourcePlanningService(db)
    availability = svc.build_availability(employees, target_date, target_date, list(blocks))
    avail_map = availability.get(c.employee_id, {})
    available_h = float(avail_map.get(target_date, 0.0))

    assignments = (
        db.execute(
            select(ResourcePlanAssignment)
            .options(joinedload(ResourcePlanAssignment.backlog_item).joinedload(BacklogItem.issue))
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.employee_id == c.employee_id,
            )
        )
        .scalars()
        .unique()
        .all()
    )

    phase_label = {"analyst": "Анализ", "dev": "Разработка", "qa": "Тестирование", "opo": "ОПЭ"}

    # Для распределения часов сегмента по рабочим дням нужна availability
    # сотрудника на весь его горизонт. Считаем по диапазону всех его назначений.
    emp_horizon_start = min(
        (a.start_date for a in assignments if a.start_date), default=target_date
    )
    emp_horizon_end = max(
        (a.end_date for a in assignments if a.end_date), default=target_date
    )
    full_avail = svc.build_availability(
        [e for e in employees if e.id == c.employee_id],
        emp_horizon_start,
        emp_horizon_end,
        list(blocks),
    ).get(c.employee_id, {})

    demand_total = 0.0
    contributors: List[dict] = []
    for a in assignments:
        if not a.start_date or not a.end_date or a.hours_allocated is None:
            continue
        if not (a.start_date <= target_date <= a.end_date):
            continue
        # Часы делятся равномерно по рабочим дням сегмента — тот же подход
        # что и в leveler._detect_overload.
        working_days = 0
        d = a.start_date
        while d <= a.end_date:
            if full_avail.get(d, 0.0) > 0.0:
                working_days += 1
            d += _td(days=1)
        if working_days <= 0:
            continue
        per_day = float(a.hours_allocated) / working_days
        demand_total += per_day
        bi = a.backlog_item
        issue = bi.issue if bi else None
        contributors.append({
            "assignment_id": a.id,
            "backlog_item_id": a.backlog_item_id,
            "item_key": issue.key if issue else None,
            "item_title": bi.title if bi else "",
            "phase": a.phase,
            "phase_label": phase_label.get(a.phase, a.phase),
            "hours_per_day": round(per_day, 2),
            "hours_total": float(a.hours_allocated),
            "start_date": a.start_date.isoformat(),
            "end_date": a.end_date.isoformat(),
            "working_days": working_days,
        })

    contributors.sort(key=lambda x: -x["hours_per_day"])

    overload_pct = (demand_total / available_h * 100.0) if available_h > 0 else None

    base.update({
        "available_hours": round(available_h, 2),
        "demand_hours": round(demand_total, 2),
        "overload_pct": round(overload_pct, 0) if overload_pct is not None else None,
        "contributors": contributors,
    })
    return base


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
