"""Resource Planning API — ScheduledBlocks + ResourcePlan + Gantt projection."""

import json as _json
from datetime import date, datetime, timedelta as _timedelta, timezone
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
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


def _parse_daily_hours(daily_hours_json: Optional[str]) -> Optional[Dict[str, float]]:
    """Разобрать JSON-строку daily_hours_json в словарь {date_str: hours}."""
    if not daily_hours_json:
        return None
    try:
        return _json.loads(daily_hours_json)
    except _json.JSONDecodeError:
        return None


def _compute_unavailable_days_for_assignment(
    db: Session, a: "ResourcePlanAssignment"
) -> List["UnavailableDay"]:
    """Посчитать недоступные дни для одной фазы (выходные/праздники/отпуска/блокировки ОПЭ).

    Использует ту же логику, что и батч-функция в get_gantt, но точечным
    запросом — для случаев, когда нужно вернуть актуальное состояние одного
    назначения (например, после PATCH).
    """
    from app.models import Absence, ProductionCalendarDay
    from app.services.resource_planning_service import PREEMPTING_PHASES

    if not a.start_date or not a.end_date:
        return []

    cal_rows = (
        db.execute(
            select(ProductionCalendarDay).where(
                ProductionCalendarDay.date >= a.start_date,
                ProductionCalendarDay.date <= a.end_date,
            )
        )
        .scalars()
        .all()
    )
    cal_map = {row.date: row.hours for row in cal_rows}

    emp_absences: list = []
    emp_preempts: list = []
    if a.employee_id:
        emp_absences = (
            db.execute(
                select(Absence).where(
                    Absence.employee_id == a.employee_id,
                    Absence.end_date >= a.start_date,
                    Absence.start_date <= a.end_date,
                )
            )
            .scalars()
            .all()
        )
        preempts = (
            db.execute(
                select(ResourcePlanAssignment).where(
                    ResourcePlanAssignment.plan_id == a.plan_id,
                    ResourcePlanAssignment.employee_id == a.employee_id,
                    ResourcePlanAssignment.id != a.id,
                    ResourcePlanAssignment.phase.in_(PREEMPTING_PHASES),
                )
            )
            .scalars()
            .all()
        )
        emp_preempts = [
            (p.id, p.start_date, p.end_date)
            for p in preempts
            if p.start_date
            and p.end_date
            and not (p.end_date < a.start_date or p.start_date > a.end_date)
        ]

    out: List[UnavailableDay] = []
    d = a.start_date
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
        if a.phase not in PREEMPTING_PHASES and any(
            ss <= d <= se for _sid, ss, se in emp_preempts
        ):
            kind = "block"
        if kind:
            out.append(UnavailableDay(date=d, type=kind))
        d += _timedelta(days=1)
    return out


def _assignment_to_out(
    a: "ResourcePlanAssignment",
    *,
    predecessor_ids: Optional[List[str]] = None,
    unavailable_days: Optional[List["UnavailableDay"]] = None,
    chunk_index: Optional[int] = None,
    chunks_total: Optional[int] = None,
    worklog_hours_actual: float = 0.0,
) -> "AssignmentOut":
    """Конвертировать ORM-объект ResourcePlanAssignment в AssignmentOut."""
    bi = a.backlog_item
    issue = bi.issue if bi else None
    emp = a.employee
    return AssignmentOut(
        id=a.id,
        backlog_item_id=a.backlog_item_id,
        backlog_item_key=issue.key if issue else None,
        backlog_item_title=bi.title if bi else "",
        phase=a.phase,
        employee_id=a.employee_id,
        employee_name=emp.display_name if emp else None,
        employee_role=emp.role if emp else None,
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
        predecessor_ids=predecessor_ids or [],
        unavailable_days=unavailable_days or [],
        scenario_assignee_employee_id=bi.assignee_employee_id if bi else None,
        scenario_assignee_name=(
            bi.assignee.display_name if bi and bi.assignee else None
        ),
        priority=bi.priority if bi else None,
        chunk_index=chunk_index,
        chunks_total=chunks_total,
        out_of_quarter=a.out_of_quarter,
        daily_hours=_parse_daily_hours(a.daily_hours_json),
        worklog_hours_actual=worklog_hours_actual,
    )


def _compute_worklog_hours_actual(
    db: Session,
    assignments: List["ResourcePlanAssignment"],
) -> Dict[str, float]:
    """Вернуть {assignment_id: часы из Worklog} для окна [start_date..end_date].

    Один батч-запрос группирует worklog часы по (employee_id, issue_id, дата),
    затем питон-сторона раскладывает по assignment'ам. N+1 устранён.
    """
    from datetime import datetime as _dt, timedelta as _td2
    from sqlalchemy import func
    from app.models.worklog import Worklog as _Worklog

    out: Dict[str, float] = {a.id: 0.0 for a in assignments}
    if not assignments:
        return out

    # Собрать кандидатов: assignment'ы с emp + датами + связанной Jira issue.
    # backlog_item уже подгружен (joinedload в /gantt), issue_id берём напрямую.
    valid: list[tuple["ResourcePlanAssignment", str, str]] = []
    emp_ids: set[str] = set()
    issue_ids: set[str] = set()
    for a in assignments:
        bi = getattr(a, "backlog_item", None)
        issue_id = getattr(bi, "issue_id", None) if bi else None
        if (
            a.employee_id and a.start_date and a.end_date and issue_id
        ):
            valid.append((a, a.employee_id, issue_id))
            emp_ids.add(a.employee_id)
            issue_ids.add(issue_id)
    if not valid:
        return out

    # Глобальный диапазон, ограничивающий выборку (минимум start, максимум end).
    min_start = min(a.start_date for a, _, _ in valid)
    max_end = max(a.end_date for a, _, _ in valid)
    start_dt = _dt(min_start.year, min_start.month, min_start.day)
    end_dt = _dt(max_end.year, max_end.month, max_end.day) + _td2(days=1)

    # Один SQL: per-day часы для каждой пары (employee, issue).
    started_date = func.date(_Worklog.started_at)
    rows = db.execute(
        select(
            _Worklog.employee_id,
            _Worklog.issue_id,
            started_date.label("d"),
            func.sum(_Worklog.hours).label("h"),
        ).where(
            _Worklog.employee_id.in_(emp_ids),
            _Worklog.issue_id.in_(issue_ids),
            _Worklog.started_at >= start_dt,
            _Worklog.started_at < end_dt,
        ).group_by(_Worklog.employee_id, _Worklog.issue_id, started_date)
    ).all()

    # Index: {(emp_id, issue_id): {date_str: hours}}
    buckets: Dict[tuple[str, str], Dict[str, float]] = {}
    for emp_id, issue_id, d_raw, h in rows:
        d_str = d_raw if isinstance(d_raw, str) else d_raw.isoformat()
        buckets.setdefault((emp_id, issue_id), {})[d_str] = float(h or 0.0)

    # Распределить по assignment'ам.
    for a, emp_id, issue_id in valid:
        bucket = buckets.get((emp_id, issue_id), {})
        if not bucket:
            continue
        total = 0.0
        d = a.start_date
        while d <= a.end_date:
            total += bucket.get(d.isoformat(), 0.0)
            d += _td2(days=1)
        out[a.id] = total
    return out


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
    # Новые поля (Task 10)
    out_of_quarter: bool = False
    daily_hours: Optional[Dict[str, float]] = None  # {"YYYY-MM-DD": hours}
    worklog_hours_actual: float = 0.0  # Task 23 — фактически отработанные часы из Worklog

    model_config = {"from_attributes": True}


class DailyBreakdownItem(BaseModel):
    date: date
    available_hours: float
    used_hours: float
    status: Literal["work", "absence", "holiday", "weekend", "blocked_by_other"]
    blocker_assignment_id: Optional[str] = None
    blocker_item_key: Optional[str] = None
    blocker_phase_label: Optional[str] = None


class AbsenceWindowItem(BaseModel):
    date_start: date
    date_end: date
    reason_label: str
    is_holiday: bool = False


class PhaseCalcDetails(BaseModel):
    duration_days_jira: Optional[int] = None
    involvement_pct: Optional[int] = None
    parallel_count: int = 1
    role_pct: Optional[int] = None
    daily_capacity_hours: float


class HoursSummary(BaseModel):
    total: float
    used: float
    remaining: float
    workdays: int
    blocked_days: int


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
    # При смене employee_id фронт сначала запрашивает /preview-employee-change.
    # Если есть пересечения с отпусками или потенциальные перегрузки —
    # фронт показывает модалку «всё равно сохранить?» и при подтверждении
    # ставит force=True, что разрешает применить смену + запустить локальный
    # пересдвиг текущей фазы и leveling на остальных назначениях этого
    # сотрудника в плане.
    force: bool = False


class EmployeeChangePreviewRequest(BaseModel):
    employee_id: str


class EmployeeAbsenceConflict(BaseModel):
    start_date: date
    end_date: date
    reason: Optional[str] = None
    overlap_days: int


class EmployeeOverloadConflict(BaseModel):
    date: date
    other_assignment_id: str
    other_phase: str
    other_backlog_item_key: Optional[str] = None
    other_backlog_item_title: str
    hours_on_day: float


class EmployeeChangePreviewResponse(BaseModel):
    new_employee_id: str
    new_employee_name: Optional[str] = None
    absences: List[EmployeeAbsenceConflict] = []
    overloads: List[EmployeeOverloadConflict] = []
    has_conflicts: bool


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
    detail_sections_visible: Dict[str, bool] = {}
    detail_sections_collapsed: Dict[str, bool] = {}
    fill_intensity_pct: int = 50
    fill_contrast_pct: int = 50
    pulse_highlighted_employee: bool = True
    pulse_critical_path: bool = True
    out_of_quarter_months: int = 1
    hide_weekend_stripes_week_mode: bool = True


def _prefs_to_schema(p: UserRpPreferences) -> UserRpPrefsSchema:
    return UserRpPrefsSchema(
        hide_weekends=p.hide_weekends,
        collapsed_initiative_ids=p.collapsed_initiative_ids or [],
        view_mode=p.view_mode,
        show_relay=p.show_relay,
        detail_sections_visible=p.detail_sections_visible or {},
        detail_sections_collapsed=p.detail_sections_collapsed or {},
        fill_intensity_pct=p.fill_intensity_pct,
        fill_contrast_pct=p.fill_contrast_pct,
        pulse_highlighted_employee=p.pulse_highlighted_employee,
        pulse_critical_path=p.pulse_critical_path,
        out_of_quarter_months=p.out_of_quarter_months,
        hide_weekend_stripes_week_mode=p.hide_weekend_stripes_week_mode,
    )


@router.get("/preferences", response_model=UserRpPrefsSchema)
def get_user_rp_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-user настройки страницы /resource-planning."""
    p = db.get(UserRpPreferences, current_user.id)
    if not p:
        return UserRpPrefsSchema()
    return _prefs_to_schema(p)


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
    p.detail_sections_visible = dict(payload.detail_sections_visible or {})
    p.detail_sections_collapsed = dict(payload.detail_sections_collapsed or {})
    p.fill_intensity_pct = max(0, min(100, payload.fill_intensity_pct))
    p.fill_contrast_pct = max(0, min(100, payload.fill_contrast_pct))
    p.pulse_highlighted_employee = payload.pulse_highlighted_employee
    p.pulse_critical_path = payload.pulse_critical_path
    p.out_of_quarter_months = max(0, min(3, payload.out_of_quarter_months))
    p.hide_weekend_stripes_week_mode = payload.hide_weekend_stripes_week_mode
    db.commit()
    db.refresh(p)
    return _prefs_to_schema(p)


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
    try:
        svc.compute_schedule(plan_id)
    except Exception:
        # Не оставлять план в `computing` если расчёт упал — иначе UI
        # бесконечно показывает «Считается…» и блокирует кнопку.
        db.rollback()
        plan2 = db.get(ResourcePlan, plan_id)
        if plan2 and plan2.status == "computing":
            plan2.status = "stale"
            db.commit()
        raise
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

    # preempt windows per employee: дни занятые preempting-фазами (ОПЭ).
    # Бар обычной фазы того же сотрудника, попадающий в эти дни, получает
    # штриховку "block" — визуальный разрыв при сохранении одной полосы.
    from app.services.resource_planning_service import PREEMPTING_PHASES
    preempt_windows_by_emp: dict[str, list[tuple] ] = {}
    for x in assignments_raw:
        if (
            x.phase in PREEMPTING_PHASES
            and x.employee_id
            and x.start_date
            and x.end_date
        ):
            preempt_windows_by_emp.setdefault(x.employee_id, []).append(
                (x.id, x.start_date, x.end_date)
            )

    def _unavailable_days(a: ResourcePlanAssignment) -> list[UnavailableDay]:
        if not a.start_date or not a.end_date:
            return []
        out: list[UnavailableDay] = []
        d = a.start_date
        emp_absences = absences_by_emp.get(a.employee_id, [])
        emp_preempts = [
            (sid, ss, se) for sid, ss, se in preempt_windows_by_emp.get(a.employee_id, [])
            if sid != a.id and not (se < a.start_date or ss > a.end_date)
        ]
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
            # Preempt-overlap: обычная фаза идёт через ОПЭ-день того же сотрудника.
            # ОПЭ-фаза не помечает свои собственные дни как block (sid != a.id выше).
            if a.phase not in PREEMPTING_PHASES and any(
                ss <= d <= se for _sid, ss, se in emp_preempts
            ):
                kind = "block"
            if kind:
                out.append(UnavailableDay(date=d, type=kind))
            d += _td(days=1)
        return out

    worklog_map = _compute_worklog_hours_actual(db, assignments_raw)

    assignments = [
        _assignment_to_out(
            a,
            predecessor_ids=preds_by_succ.get(a.id, []),
            unavailable_days=_unavailable_days(a),
            chunk_index=(a.part_number - 1) if phase_counts.get((a.backlog_item_id, a.phase), 1) > 1 else None,
            chunks_total=phase_counts.get((a.backlog_item_id, a.phase)) if phase_counts.get((a.backlog_item_id, a.phase), 1) > 1 else None,
            worklog_hours_actual=worklog_map.get(a.id, 0.0),
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


def _detect_employee_change_conflicts(
    db: Session,
    a: ResourcePlanAssignment,
    new_employee_id: str,
) -> tuple[List["EmployeeAbsenceConflict"], List["EmployeeOverloadConflict"]]:
    """Найти пересечения с отпусками и потенциальные перегрузки в плане.

    Используется и в preview-endpoint (показать модалку), и в PATCH с
    force=False (вернуть 409). Не мутирует.
    """
    from app.models import Absence, AbsenceReason

    if not a.start_date or not a.end_date:
        return [], []

    # 1. Отпуска нового сотрудника в окне фазы
    absences_raw = (
        db.execute(
            select(Absence)
            .options(joinedload(Absence.reason))
            .where(
                Absence.employee_id == new_employee_id,
                Absence.end_date >= a.start_date,
                Absence.start_date <= a.end_date,
            )
        )
        .scalars()
        .all()
    )
    absences_out: List[EmployeeAbsenceConflict] = []
    for ab in absences_raw:
        overlap_start = max(ab.start_date, a.start_date)
        overlap_end = min(ab.end_date, a.end_date)
        overlap_days = (overlap_end - overlap_start).days + 1
        absences_out.append(
            EmployeeAbsenceConflict(
                start_date=ab.start_date,
                end_date=ab.end_date,
                reason=(ab.reason.label if ab.reason else None),
                overlap_days=max(0, overlap_days),
            )
        )

    # 2. Другие назначения этого сотрудника в плане, перекрывающие окно фазы.
    #    Дневная нагрузка > 8ч на одном дне — потенциальная перегрузка.
    overlapping = (
        db.execute(
            select(ResourcePlanAssignment)
            .options(
                joinedload(ResourcePlanAssignment.backlog_item).joinedload(
                    BacklogItem.issue
                )
            )
            .where(
                ResourcePlanAssignment.plan_id == a.plan_id,
                ResourcePlanAssignment.employee_id == new_employee_id,
                ResourcePlanAssignment.id != a.id,
                ResourcePlanAssignment.start_date.is_not(None),
                ResourcePlanAssignment.end_date.is_not(None),
                ResourcePlanAssignment.end_date >= a.start_date,
                ResourcePlanAssignment.start_date <= a.end_date,
            )
        )
        .scalars()
        .all()
    )
    overloads_out: List[EmployeeOverloadConflict] = []
    # Часы фазы-кандидата по дням
    cand_daily = _parse_daily_hours(a.daily_hours_json) or {}
    if not cand_daily and a.hours_allocated and a.start_date and a.end_date:
        days_count = max(1, (a.end_date - a.start_date).days + 1)
        per = a.hours_allocated / days_count
        d = a.start_date
        while d <= a.end_date:
            cand_daily[d.isoformat()] = per
            d += _timedelta(days=1)
    for other in overlapping:
        other_daily = _parse_daily_hours(other.daily_hours_json) or {}
        if not other_daily and other.hours_allocated and other.start_date and other.end_date:
            days_count = max(1, (other.end_date - other.start_date).days + 1)
            per = other.hours_allocated / days_count
            d = other.start_date
            while d <= other.end_date:
                other_daily[d.isoformat()] = per
                d += _timedelta(days=1)
        for d_iso, cand_h in cand_daily.items():
            other_h = other_daily.get(d_iso, 0.0)
            total = cand_h + other_h
            if total > 8.0:
                bi = other.backlog_item
                overloads_out.append(
                    EmployeeOverloadConflict(
                        date=date.fromisoformat(d_iso),
                        other_assignment_id=other.id,
                        other_phase=other.phase,
                        other_backlog_item_key=(
                            bi.issue.key if bi and bi.issue else None
                        ),
                        other_backlog_item_title=(bi.title if bi else ""),
                        hours_on_day=total,
                    )
                )
                # достаточно одного дня на каждое перекрывающее назначение
                break

    return absences_out, overloads_out


def _shift_phase_to_skip_absences(
    db: Session,
    a: ResourcePlanAssignment,
    q_end: date,
) -> bool:
    """Локально сдвинуть фазу за окно отпусков нового сотрудника.

    Простая стратегия: если первый день фазы попадает в отпуск, двигаем
    start_date на день после окончания отпуска, end_date на ту же дельту.
    Возвращает True если сдвиг был применён. Ограничения: не выходим за
    конец квартала (extended); если не помещается — оставляем как есть.
    """
    from app.models import Absence

    if not a.start_date or not a.end_date or not a.employee_id:
        return False

    max_iterations = 12  # защита от бесконечного цикла на странных данных
    shifted = False
    for _ in range(max_iterations):
        absences = (
            db.execute(
                select(Absence).where(
                    Absence.employee_id == a.employee_id,
                    Absence.end_date >= a.start_date,
                    Absence.start_date <= a.end_date,
                )
            )
            .scalars()
            .all()
        )
        # Найти отпуск, перекрывающий start_date или ближайший к нему
        blocking = [ab for ab in absences if ab.start_date <= a.start_date <= ab.end_date]
        if not blocking:
            return shifted
        # Сдвинуть за самый поздний из перекрывающих start_date
        skip_to = max(ab.end_date for ab in blocking) + _timedelta(days=1)
        delta = (skip_to - a.start_date).days
        if delta <= 0:
            return shifted
        new_end = a.end_date + _timedelta(days=delta)
        if new_end > q_end:
            # вылазит за квартал — оставить как есть, пусть пользователь решает
            return shifted
        a.start_date = skip_to
        a.end_date = new_end
        shifted = True
    return shifted


@router.post(
    "/resource-plans/{plan_id}/assignments/{assignment_id}/preview-employee-change",
    response_model=EmployeeChangePreviewResponse,
)
def preview_employee_change(
    plan_id: str,
    assignment_id: str,
    body: EmployeeChangePreviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Превью смены сотрудника: показывает отпуска и потенциальные перегрузки.

    Фронт вызывает перед PATCH; если есть конфликты — показывает модалку
    «всё равно сохранить?» и при подтверждении ставит force=True в PATCH.
    """
    from app.models import Employee

    a = db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.id == assignment_id,
            ResourcePlanAssignment.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Assignment not found")
    new_emp = db.get(Employee, body.employee_id)
    if not new_emp:
        raise HTTPException(404, "Employee not found")

    absences, overloads = _detect_employee_change_conflicts(db, a, body.employee_id)
    return EmployeeChangePreviewResponse(
        new_employee_id=body.employee_id,
        new_employee_name=new_emp.display_name,
        absences=absences,
        overloads=overloads,
        has_conflicts=bool(absences) or bool(overloads),
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
    # force — флаг подтверждения смены сотрудника при наличии конфликтов.
    # Не атрибут модели, обрабатываем отдельно.
    force = bool(patch.pop("force", False))

    # При смене сотрудника без force — проверить конфликты и вернуть 409.
    if (
        "employee_id" in patch
        and patch["employee_id"]
        and patch["employee_id"] != a.employee_id
        and not force
    ):
        absences, overloads = _detect_employee_change_conflicts(
            db, a, patch["employee_id"]
        )
        if absences or overloads:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "employee_change_conflicts",
                    "message": "Новый сотрудник недоступен в окне фазы. Используйте force=true для подтверждения.",
                    "absences": [ab.model_dump(mode="json") for ab in absences],
                    "overloads": [o.model_dump(mode="json") for o in overloads],
                },
            )

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

        # Пометить, что пользователь явно отредактировал список
        # предшественников. _ensure_default_predecessors не будет
        # перевосстанавливать дефолтную цепочку для этой инициативы.
        a.predecessors_user_set = True
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

    # При force-смене сотрудника — запустить полный пересчёт плана.
    # pinned_employee=True гарантирует, что этот выбор сохранится; остальные
    # фазы этого же сотрудника пройдут через leveler и сдвинутся, чтобы
    # разрулить новые перегрузки и обойти отпуска.
    if "employee_id" in patch and force and plan:
        # Запомнить логический ключ ДО compute: employee-only pinned rows
        # удаляются и пересоздаются с новым id, поэтому после пересчёта
        # ищем по (backlog_item_id, phase, part_number).
        target_item_id = a.backlog_item_id
        target_phase = a.phase
        target_part_number = a.part_number
        db.flush()  # зафиксировать pinned_employee + новый employee_id
        try:
            ResourcePlanningService(db).compute_schedule(plan_id)
        except ValueError as e:
            raise HTTPException(409, f"reschedule_failed: {e}")
        # compute_schedule сам коммитит. Перечитать назначение по логическому
        # ключу — id мог смениться при пересоздании employee-only-pin строки.
        a = db.execute(
            select(ResourcePlanAssignment)
            .options(
                joinedload(ResourcePlanAssignment.backlog_item).joinedload(
                    BacklogItem.issue
                )
            )
            .options(joinedload(ResourcePlanAssignment.employee))
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.backlog_item_id == target_item_id,
                ResourcePlanAssignment.phase == target_phase,
                ResourcePlanAssignment.part_number == target_part_number,
            )
        ).scalar_one_or_none()
        if not a:
            raise HTTPException(404, "Assignment vanished after reschedule")

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
    a_pinned_employee = a.pinned_employee
    a_pinned_start = a.pinned_start
    a_pinned_split = a.pinned_split
    a_manual_edit_at = a.manual_edit_at
    a_priority = a.backlog_item.priority if a.backlog_item else None
    a_scenario_assignee_id = a.backlog_item.assignee_employee_id if a.backlog_item else None
    a_scenario_assignee_name = (
        a.backlog_item.assignee.display_name if a.backlog_item and a.backlog_item.assignee else None
    )
    a_out_of_quarter = a.out_of_quarter
    a_daily_hours = _parse_daily_hours(a.daily_hours_json)

    # Подтянуть predecessor_ids и unavailable_days, чтобы фронт после PATCH
    # видел актуальное состояние без полного рефетча (нужно для корректного
    # отображения связей в сайдбаре сразу после смены сотрудника/дат).
    from app.models.phase_predecessor import PhasePredecessor as _PP
    a_predecessor_ids = [
        row[0]
        for row in db.execute(
            select(_PP.predecessor_assignment_id).where(
                _PP.successor_assignment_id == a_id
            )
        ).all()
    ]
    a_unavailable_days = _compute_unavailable_days_for_assignment(db, a)

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
        pinned_employee=a_pinned_employee,
        pinned_start=a_pinned_start,
        pinned_split=a_pinned_split,
        manual_edit_at=a_manual_edit_at,
        priority=a_priority,
        scenario_assignee_employee_id=a_scenario_assignee_id,
        scenario_assignee_name=a_scenario_assignee_name,
        out_of_quarter=a_out_of_quarter,
        daily_hours=a_daily_hours,
        worklog_hours_actual=0.0,
        predecessor_ids=a_predecessor_ids,
        unavailable_days=a_unavailable_days,
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


# ── /explain helpers (Task 9) ──────────────────────────────────────────────


def _build_algorithm_log(
    a: "ResourcePlanAssignment",
    plan: "ResourcePlan",
    all_emp_assignments: List["ResourcePlanAssignment"],
) -> List[str]:
    """Текст «откуда дата старта» для боковой панели."""
    log: List[str] = []
    phase_ru = {"analyst": "Анализ", "dev": "Разработка", "qa": "Тестирование", "opo": "ОПЭ"}
    if a.phase == "analyst":
        log.append(f"Старт фазы = начало квартала ({plan.quarter} {plan.year}).")
    else:
        prev_phase = {"dev": "analyst", "qa": "dev", "opo": "qa"}.get(a.phase)
        if prev_phase:
            prev = [
                x for x in all_emp_assignments
                if x.phase == prev_phase and x.backlog_item_id == a.backlog_item_id
            ]
            if prev:
                p = max(prev, key=lambda x: x.end_date or date.min)
                if p.end_date:
                    log.append(
                        f"Старт фазы = следующий рабочий день после фактического окончания "
                        f"фазы «{phase_ru[prev_phase]}» ({p.end_date.isoformat()})."
                    )
    if a.out_of_quarter:
        log.append("Фаза выходит за пределы квартала — часов не хватает в окне.")
    if a.is_on_critical_path:
        log.append(f"На критическом пути. Резерв: {a.slack_days or 0:.0f} д.")
    return log


def _build_daily_breakdown(
    a: "ResourcePlanAssignment",
    avail_map: Dict[date, float],
    other_assignments: List["ResourcePlanAssignment"],
    absences: list,
    calendar_map: dict,
) -> List[DailyBreakdownItem]:
    if not a.start_date or not a.end_date:
        return []
    daily_used: Dict[date, float] = {}
    if a.daily_hours_json:
        try:
            raw = _json.loads(a.daily_hours_json)
            daily_used = {date.fromisoformat(k): float(v) for k, v in raw.items()}
        except (_json.JSONDecodeError, ValueError):
            pass
    items: List[DailyBreakdownItem] = []
    phase_label = {"analyst": "Анализ", "dev": "Разработка", "qa": "Тестирование", "opo": "ОПЭ"}
    d = a.start_date
    while d <= a.end_date:
        cal = calendar_map.get(d)
        avail_h = avail_map.get(d, 0.0)
        used_h = daily_used.get(d, 0.0)
        if cal and not cal.is_workday and cal.kind in ("holiday", "preholiday"):
            status: str = "holiday"
        elif d.weekday() >= 5 and (not cal or not cal.is_workday):
            status = "weekend"
        elif any(ab.start_date <= d <= ab.end_date for ab in absences):
            status = "absence"
        elif used_h == 0 and avail_h > 0:
            # Заблокирован другим назначением того же сотрудника в этот день?
            blocker = next(
                (
                    x for x in other_assignments
                    if x.id != a.id
                    and x.employee_id == a.employee_id
                    and x.start_date and x.end_date
                    and x.start_date <= d <= x.end_date
                ),
                None,
            )
            if blocker:
                bi = blocker.backlog_item
                issue = bi.issue if bi else None
                items.append(DailyBreakdownItem(
                    date=d,
                    available_hours=avail_h,
                    used_hours=0.0,
                    status="blocked_by_other",
                    blocker_assignment_id=blocker.id,
                    blocker_item_key=issue.key if issue else None,
                    blocker_phase_label=phase_label.get(blocker.phase, blocker.phase),
                ))
                d += _timedelta(days=1)
                continue
            status = "work"
        else:
            status = "work"
        items.append(DailyBreakdownItem(
            date=d, available_hours=avail_h, used_hours=used_h, status=status,
        ))
        d += _timedelta(days=1)
    return items


def _build_absences_in_window(
    a: "ResourcePlanAssignment",
    absences: list,
    calendar_map: dict,
) -> List[AbsenceWindowItem]:
    if not a.start_date or not a.end_date:
        return []
    items: List[AbsenceWindowItem] = [
        AbsenceWindowItem(
            date_start=max(ab.start_date, a.start_date),
            date_end=min(ab.end_date, a.end_date),
            reason_label=ab.reason.label if ab.reason else "Отсутствие",
            is_holiday=False,
        )
        for ab in absences
    ]
    # Праздники в окне из карты календаря
    for cal_date, cal_row in calendar_map.items():
        if not cal_row.is_workday and cal_row.kind in ("holiday", "preholiday"):
            items.append(AbsenceWindowItem(
                date_start=cal_date,
                date_end=cal_date,
                reason_label="Праздник РФ",
                is_holiday=True,
            ))
    return items


def _build_phase_calc(
    a: "ResourcePlanAssignment",
    db: Session,
) -> Optional[PhaseCalcDetails]:
    bi = db.get(BacklogItem, a.backlog_item_id) if a.backlog_item_id else None
    if not bi:
        return None
    phase = a.phase
    dur_field = {
        "analyst": "duration_analyst_days",
        "dev": "duration_dev_days",
        "qa": "duration_qa_days",
        "opo": "duration_launch_days",
    }.get(phase)
    inv_field = {
        "analyst": "involvement_analyst",
        "dev": "involvement_dev",
        "qa": "involvement_qa",
        "opo": "involvement_launch",
    }.get(phase)
    par_field = {
        "analyst": "parallel_count_analyst",
        "dev": "parallel_count_dev",
        "qa": "parallel_count_qa",
        "opo": None,
    }.get(phase)
    if dur_field is None or inv_field is None:
        return None
    duration = getattr(bi, dur_field, None)
    inv = getattr(bi, inv_field, None)
    parallel = getattr(bi, par_field, None) if par_field else None
    inv_pct = int(inv * 100) if inv else None
    daily_cap = 8.0 * (inv or 1.0) * (parallel or 1)
    return PhaseCalcDetails(
        duration_days_jira=int(duration) if duration else None,
        involvement_pct=inv_pct,
        parallel_count=int(parallel or 1),
        role_pct=None,
        daily_capacity_hours=round(daily_cap, 2),
    )


def _build_hours_summary(
    a: "ResourcePlanAssignment",
    avail_map: Dict[date, float],
) -> Optional[HoursSummary]:
    if not a.start_date or not a.end_date or a.hours_allocated is None:
        return None
    daily_used: Dict[date, float] = {}
    if a.daily_hours_json:
        try:
            raw = _json.loads(a.daily_hours_json)
            daily_used = {date.fromisoformat(k): float(v) for k, v in raw.items()}
        except (_json.JSONDecodeError, ValueError):
            pass
    used = sum(daily_used.values()) if daily_used else float(a.hours_allocated)
    total = float(a.hours_allocated)
    workdays = 0
    blocked = 0
    d = a.start_date
    while d <= a.end_date:
        if d in daily_used:
            workdays += 1
        elif avail_map.get(d, 0.0) > 0.0:
            blocked += 1
        d += _timedelta(days=1)
    return HoursSummary(
        total=round(total, 2),
        used=round(used, 2),
        remaining=round(max(0.0, total - used), 2),
        workdays=workdays,
        blocked_days=blocked,
    )


@router.get("/resource-plans/{plan_id}/assignments/{assignment_id}/explain")
def explain_assignment(
    plan_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Расчёт всех конфликтов, связанных с конкретным назначением.

    Используется боковой панелью при клике на фазе: показать почему бар «красный».
    Для каждого PlanConflict, у которого `assignment_id == aid` или
    `employee_id == assignment.employee_id` и окно пересекает [start, end],
    возвращается breakdown (как в /conflicts/{cid}/explain).

    Также возвращает расширенные поля (Task 9):
    - algorithm_log: текстовое объяснение откуда взялась дата старта
    - daily_breakdown: посуточная разбивка usage/availability/статус
    - absences_in_window: отсутствия и праздники в окне фазы
    - phase_calc: параметры расчёта фазы из бэклога
    - hours_summary: сводка часов фазы
    """
    from app.models import Absence, Employee, PlanConflict, ProductionCalendarDay

    a = db.execute(
        select(ResourcePlanAssignment)
        .options(
            joinedload(ResourcePlanAssignment.backlog_item).joinedload(BacklogItem.issue),
            joinedload(ResourcePlanAssignment.backlog_item),
            joinedload(ResourcePlanAssignment.employee),
        )
        .where(
            ResourcePlanAssignment.id == assignment_id,
            ResourcePlanAssignment.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Assignment not found")
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    emp_name: Optional[str] = a.employee.display_name if a.employee else None

    # Сохранить legacy summary для обратной совместимости (frontend Task 14 переключится на новый shape)
    summary = {
        "assignment_id": a.id,
        "phase": a.phase,
        "employee_id": a.employee_id,
        "employee_name": emp_name,
        "start_date": a.start_date.isoformat() if a.start_date else None,
        "end_date": a.end_date.isoformat() if a.end_date else None,
        "hours_allocated": float(a.hours_allocated) if a.hours_allocated is not None else None,
        "is_on_critical_path": bool(a.is_on_critical_path),
        "slack_days": float(a.slack_days) if a.slack_days is not None else None,
    }

    # Конфликты, привязанные к этому назначению.
    rows = (
        db.execute(
            select(PlanConflict).where(
                PlanConflict.plan_id == plan_id,
                PlanConflict.assignment_id == assignment_id,
                PlanConflict.status.in_(["open", "acknowledged"]),
            )
        )
        .scalars()
        .all()
    )

    team = plan.team
    employees = (
        db.execute(
            select(Employee).where(Employee.team == team)
            if team
            else select(Employee)
        )
        .scalars()
        .all()
    )
    if a.employee_id and a.employee_id not in {e.id for e in employees}:
        owner = db.get(Employee, a.employee_id)
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
    phase_label = {"analyst": "Анализ", "dev": "Разработка", "qa": "Тестирование", "opo": "ОПЭ"}

    # Кэш availability сотрудника на горизонте плана.
    all_emp_assignments = (
        db.execute(
            select(ResourcePlanAssignment)
            .options(joinedload(ResourcePlanAssignment.backlog_item).joinedload(BacklogItem.issue))
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.employee_id == a.employee_id,
            )
        )
        .scalars()
        .unique()
        .all()
        if a.employee_id
        else []
    )
    horizon_start = min((x.start_date for x in all_emp_assignments if x.start_date), default=a.start_date)
    horizon_end = max((x.end_date for x in all_emp_assignments if x.end_date), default=a.end_date)
    full_avail: Dict[date, float] = {}
    if a.employee_id and horizon_start and horizon_end:
        full_avail = svc.build_availability(
            [e for e in employees if e.id == a.employee_id],
            horizon_start,
            horizon_end,
            list(blocks),
        ).get(a.employee_id, {})

    # Calendar map для окна фазы
    calendar_map: Dict[date, "ProductionCalendarDay"] = {}
    if a.start_date and a.end_date:
        cal_rows = (
            db.execute(
                select(ProductionCalendarDay).where(
                    ProductionCalendarDay.date >= a.start_date,
                    ProductionCalendarDay.date <= a.end_date,
                )
            )
            .scalars()
            .all()
        )
        calendar_map = {row.date: row for row in cal_rows}

    # Коэффициент вовлечённости для текущей фазы (из BacklogItem).
    # «Доступно» в детализации = календарь × involvement, чтобы единообразно
    # для всех фаз (Анализ/Разработка/Тестирование/ОПЭ) показывать сколько
    # часов реально может уйти на этот проект, а не голый календарь.
    _bi_for_inv = db.get(BacklogItem, a.backlog_item_id) if a.backlog_item_id else None
    _inv_field = {
        "analyst": "involvement_analyst",
        "dev": "involvement_dev",
        "qa": "involvement_qa",
        "opo": "involvement_launch",
    }.get(a.phase)
    _inv_value = (
        float(getattr(_bi_for_inv, _inv_field) or 1.0)
        if _bi_for_inv and _inv_field and getattr(_bi_for_inv, _inv_field, None) is not None
        else 1.0
    )

    # QA — внешний ресурс без сотрудника. Доступность по дням = 8ч × involvement_qa
    # на рабочих днях, 0 на выходных/праздниках.
    if a.phase == "qa" and not full_avail and a.start_date and a.end_date:
        qa_daily = 8.0 * _inv_value
        d_iter = a.start_date
        while d_iter <= a.end_date:
            cal = calendar_map.get(d_iter)
            if cal is not None:
                is_workday = cal.is_workday
            else:
                is_workday = d_iter.weekday() < 5
            full_avail[d_iter] = qa_daily if is_workday else 0.0
            d_iter += _timedelta(days=1)
    elif a.phase != "qa" and full_avail and _inv_value != 1.0:
        # Для не-QA фаз full_avail уже построен build_availability как сырой
        # календарь минус отсутствия. Применяем коэф. вовлечённости поверх,
        # чтобы детализация показывала ту же ёмкость, которую использует
        # планировщик (_daily_role_capacity внутри compute_schedule).
        full_avail = {d: h * _inv_value for d, h in full_avail.items()}

    # Отсутствия сотрудника в окне фазы
    absences_in_window_raw: List["Absence"] = []
    if a.employee_id and a.start_date and a.end_date:
        absences_in_window_raw = (
            db.execute(
                select(Absence)
                .options(joinedload(Absence.reason))
                .where(
                    Absence.employee_id == a.employee_id,
                    Absence.start_date <= a.end_date,
                    Absence.end_date >= a.start_date,
                )
            )
            .scalars()
            .all()
        )

    conflicts_out: List[dict] = []
    for c in rows:
        target_date = c.window_start.date() if c.window_start else None
        item: dict = {
            "id": c.id,
            "type": c.type,
            "severity": c.severity,
            "message": c.message,
            "date": target_date.isoformat() if target_date else None,
            "available_hours": None,
            "demand_hours": None,
            "overload_pct": None,
            "contributors": [],
        }
        is_overload = c.type.startswith("OVERLOAD_")
        if is_overload and target_date and c.employee_id:
            avail = float(full_avail.get(target_date, 0.0))
            demand_total = 0.0
            contribs: List[dict] = []
            for x in all_emp_assignments:
                if not x.start_date or not x.end_date or x.hours_allocated is None:
                    continue
                if not (x.start_date <= target_date <= x.end_date):
                    continue
                # Per-day часы: из daily_hours_json или fallback равномерное распределение
                per_day_actual = 0.0
                if x.daily_hours_json:
                    try:
                        dh = _json.loads(x.daily_hours_json)
                        per_day_actual = float(dh.get(target_date.isoformat(), 0.0))
                    except (_json.JSONDecodeError, ValueError):
                        pass
                if per_day_actual <= 0:
                    # fallback (legacy равномерное распределение)
                    wd = 0
                    d = x.start_date
                    while d <= x.end_date:
                        if full_avail.get(d, 0.0) > 0.0:
                            wd += 1
                        d += _timedelta(days=1)
                    if wd <= 0:
                        continue
                    per_day_actual = float(x.hours_allocated) / wd
                if per_day_actual <= 0:
                    continue
                demand_total += per_day_actual
                bi = x.backlog_item
                issue = bi.issue if bi else None
                # working_days для отображения (легаси fallback)
                wd_display = 0
                d2 = x.start_date
                while d2 <= x.end_date:
                    if full_avail.get(d2, 0.0) > 0.0:
                        wd_display += 1
                    d2 += _timedelta(days=1)
                contribs.append({
                    "assignment_id": x.id,
                    "backlog_item_id": x.backlog_item_id,
                    "item_key": issue.key if issue else None,
                    "item_title": bi.title if bi else "",
                    "phase": x.phase,
                    "phase_label": phase_label.get(x.phase, x.phase),
                    "hours_per_day": round(per_day_actual, 2),
                    "hours_total": float(x.hours_allocated),
                    "start_date": x.start_date.isoformat(),
                    "end_date": x.end_date.isoformat(),
                    "working_days": wd_display,
                })
            contribs.sort(key=lambda r: -r["hours_per_day"])
            pct = (demand_total / avail * 100.0) if avail > 0 else None
            item.update({
                "available_hours": round(avail, 2),
                "demand_hours": round(demand_total, 2),
                "overload_pct": round(pct, 0) if pct is not None else None,
                "contributors": contribs,
            })
        conflicts_out.append(item)

    _phase_calc = _build_phase_calc(a, db)
    _hours_summary = _build_hours_summary(a, full_avail)

    return {
        # Новый shape (Task 9)
        "assignment": _assignment_to_out(a).model_dump(mode="json"),
        "conflicts": conflicts_out,
        "algorithm_log": _build_algorithm_log(a, plan, all_emp_assignments),
        "daily_breakdown": [
            item.model_dump(mode="json")
            for item in _build_daily_breakdown(
                a, full_avail, all_emp_assignments, absences_in_window_raw, calendar_map
            )
        ],
        "absences_in_window": [
            item.model_dump(mode="json")
            for item in _build_absences_in_window(a, absences_in_window_raw, calendar_map)
        ],
        "phase_calc": _phase_calc.model_dump(mode="json") if _phase_calc is not None else None,
        "hours_summary": _hours_summary.model_dump(mode="json") if _hours_summary is not None else None,
        # Legacy back-compat (будет удалён в Task 14)
        "summary": summary,
    }


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
