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

import calendar
from datetime import date, datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Absence,
    AbsenceReason,
    BacklogItem,
    Employee,
    EmployeeTeam,
    Issue,
    PlanningScenario,
    RoleCapacityRule,
    ScenarioAbsenceSnapshot,
    ScenarioAllocation,
    ScenarioAllocationBreakdownSnapshot,
    ScenarioCapacitySnapshot,
    ScenarioRevision,
    ScenarioRevisionItem,
    ScenarioRule,
)
from app.schemas.capacity_diff import (
    AbsenceChange,
    CapacityDiffResponse,
    EmployeeDiff,
    MonthDiff,
)
from app.services.capacity_service import CapacityService
from app.services.resource_base_service import ResourceBaseService
from app.services.snapshot_writer import SnapshotWriter
from app.services.event_bus import EventBroadcaster, get_event_bus
from app.services.backlog_service import BacklogService, BACKLOG_CATEGORY
from app.services.category_resolver import CategoryResolver


router = APIRouter()

QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}


def _resolve_absence_hours(absence: Absence, capacity_svc: CapacityService) -> float:
    """Часы отсутствия: явное значение либо расчёт по производственному календарю."""
    if absence.hours_total is not None:
        return float(absence.hours_total)
    return capacity_svc._norm_hours_in_range(absence.start_date, absence.end_date)


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
    backlog_pool_hours: Optional[float] = None

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


class RevisionDiffItem(BaseModel):
    backlog_item_id: Optional[str]
    backlog_item_name: str


class RevisionDiffMonth(BaseModel):
    year: int
    month: int
    r1_norm_hours: float
    r1_available_hours: float
    r2_norm_hours: float
    r2_available_hours: float
    delta_norm_hours: float
    delta_available_hours: float


class RevisionDiffEmployee(BaseModel):
    employee_id: Optional[str]
    employee_name: str
    months: List[RevisionDiffMonth]
    delta_total_norm_hours: float
    delta_total_available_hours: float


class RevisionDiffSide(BaseModel):
    revision_number: int
    approved_at: str
    note: Optional[str]
    included_count: int


class RevisionDiffResponse(BaseModel):
    r1: RevisionDiffSide
    r2: RevisionDiffSide
    added: List[RevisionDiffItem]
    removed: List[RevisionDiffItem]
    kept: List[RevisionDiffItem]
    capacity: List[RevisionDiffEmployee]


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

    # --- Предыдущая ревизия (нужна до создания новой) ---
    prev_revision = (
        db.query(ScenarioRevision)
        .filter(
            ScenarioRevision.scenario_id == scenario_id,
            ScenarioRevision.revision_number == revision_number - 1,
        )
        .first()
    )

    # --- Создать запись ревизии ---
    revision = ScenarioRevision(
        scenario_id=scenario_id,
        revision_number=revision_number,
        approved_at=now,
        note=body.note,
        parent_revision_id=prev_revision.id if prev_revision else None,
        algo_version="v2",
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

    # --- Снапшоты ревизии (v2) ---
    writer = SnapshotWriter(db)
    writer.write_team_snapshot(revision, scenario)
    writer.write_calendar_snapshot(revision, scenario)
    writer.write_rules_snapshot(revision, scenario)
    writer.write_dictionary_snapshot(revision)
    writer.write_capacity_snapshot(revision, scenario)
    writer.write_norm_snapshot(revision, scenario)
    writer.write_allocation_snapshot(revision, scenario)
    writer.write_allocation_breakdown(revision, scenario)

    # --- Снапшот отсутствий команды (inline, будет перенесён в SnapshotWriter позже) ---
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
        quarter_start = date(scenario.year, months[0], 1)
        last_day = calendar.monthrange(scenario.year, months[-1])[1]
        quarter_end = date(scenario.year, months[-1], last_day)

        absences = (
            db.query(Absence)
            .filter(
                Absence.employee_id.in_([emp.id for emp in employees]),
                Absence.start_date <= quarter_end,
                Absence.end_date >= quarter_start,
            )
            .all()
        )

        reason_ids = list({a.reason_id for a in absences if a.reason_id})
        reasons: dict[str, str] = {}
        if reason_ids:
            reasons = {
                r.id: r.label
                for r in db.query(AbsenceReason).filter(AbsenceReason.id.in_(reason_ids)).all()
            }
        emp_names = {emp.id: emp.display_name for emp in employees}

        for ab in absences:
            db.add(ScenarioAbsenceSnapshot(
                revision_id=revision.id,
                employee_id=ab.employee_id,
                employee_name=emp_names.get(ab.employee_id, ""),
                original_absence_id=ab.id,
                start_date=ab.start_date,
                end_date=ab.end_date,
                reason_id=ab.reason_id,
                reason_label=reasons.get(ab.reason_id) if ab.reason_id else None,
                hours_total=_resolve_absence_hours(ab, capacity_svc),
            ))

    scenario.status = "approved"

    # Помечаем существующие ResourcePlan этого сценария как stale —
    # утверждение могло изменить состав инициатив, нужно пересчитать.
    from app.models import ResourcePlan
    plans_to_stale = db.query(ResourcePlan).filter(
        ResourcePlan.scenario_id == scenario_id,
        ResourcePlan.status != "stale",
    ).all()
    for p in plans_to_stale:
        p.status = "stale"

    db.commit()
    entities = ["planning", "backlog"]
    if plans_to_stale:
        entities.append("resource_planning")
    await event_bus.publish({"type": "entity_changed", "entities": entities})
    db.refresh(scenario)
    return _to_scenario_resp(scenario)


@router.get("/scenarios/{scenario_id}/capacity-diff")
async def get_capacity_diff(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Сравнивает текущие отсутствия с данными на момент утверждения."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario or scenario.status != "approved":
        raise HTTPException(status_code=404, detail="Approved scenario not found")

    revision = (
        db.query(ScenarioRevision)
        .filter(ScenarioRevision.scenario_id == scenario_id)
        .order_by(ScenarioRevision.revision_number.desc())
        .first()
    )
    if not revision:
        return CapacityDiffResponse(has_changes=False, changed_employees=[])

    # Load absence snapshots
    snaps = (
        db.query(ScenarioAbsenceSnapshot)
        .filter(ScenarioAbsenceSnapshot.revision_id == revision.id)
        .all()
    )
    # Load capacity snapshots for available_hours comparison
    cap_snaps: dict[tuple, float] = {
        (s.employee_id, s.year, s.month): s.available_hours
        for s in db.query(ScenarioCapacitySnapshot)
        .filter(ScenarioCapacitySnapshot.revision_id == revision.id)
        .all()
    }

    emp_ids = list(
        {s.employee_id for s in snaps if s.employee_id}
        | {k[0] for k in cap_snaps if k[0]}
    )
    if not emp_ids:
        return CapacityDiffResponse(has_changes=False, changed_employees=[])

    # Quarter date range
    q_num = int(str(scenario.quarter).replace("Q", ""))
    q_months = QUARTER_MONTHS[q_num]
    import calendar as cal_mod
    from datetime import date as date_t
    quarter_start = date_t(scenario.year, q_months[0], 1)
    quarter_end = date_t(scenario.year, q_months[-1],
                         cal_mod.monthrange(scenario.year, q_months[-1])[1])

    # Current absences
    current_absences = (
        db.query(Absence)
        .filter(
            Absence.employee_id.in_(emp_ids),
            Absence.start_date <= quarter_end,
            Absence.end_date >= quarter_start,
        )
        .all()
    )

    # Load reason labels for current absences
    reason_ids = list({a.reason_id for a in current_absences if a.reason_id})
    reasons: dict[str, str] = {}
    if reason_ids:
        reasons = {
            r.id: r.label
            for r in db.query(AbsenceReason).filter(AbsenceReason.id.in_(reason_ids)).all()
        }

    employees = {e.id: e for e in db.query(Employee).filter(Employee.id.in_(emp_ids)).all()}

    # Build snap index
    snap_by_emp: dict[str, list] = {}
    for s in snaps:
        snap_by_emp.setdefault(s.employee_id, []).append(s)

    current_by_emp: dict[str, list] = {}
    for a in current_absences:
        current_by_emp.setdefault(a.employee_id, []).append(a)

    capacity_svc = CapacityService(db)
    changed_employees: list[EmployeeDiff] = []

    for emp_id in emp_ids:
        month_diffs: list[MonthDiff] = []
        snapped_by_orig_id = {
            s.original_absence_id: s
            for s in snap_by_emp.get(emp_id, [])
            if s.original_absence_id
        }
        current_ids = {a.id for a in current_by_emp.get(emp_id, [])}

        for month in q_months:
            snap_avail = cap_snaps.get((emp_id, scenario.year, month))
            if snap_avail is None:
                continue
            # TODO: monthly_capacity computes fact_hours unnecessarily here; refactor to available_hours_for_month
            mc = capacity_svc.monthly_capacity(emp_id, scenario.year, month)
            current_avail = mc.available_hours
            delta = round(current_avail - snap_avail, 2)

            absence_changes: list[AbsenceChange] = []
            # Removed: in snapshot but not in current
            for orig_id, snap_ab in snapped_by_orig_id.items():
                if orig_id not in current_ids:
                    if (snap_ab.start_date.month == month and snap_ab.start_date.year == scenario.year) \
                       or (snap_ab.end_date.month == month and snap_ab.end_date.year == scenario.year):
                        absence_changes.append(AbsenceChange(
                            type="removed",
                            start_date=snap_ab.start_date,
                            end_date=snap_ab.end_date,
                            reason=snap_ab.reason_label,
                            hours=snap_ab.hours_total if snap_ab.hours_total is not None else 0.0,
                        ))
            # Added: in current but not in snapshot
            for cur_ab in current_by_emp.get(emp_id, []):
                if cur_ab.id not in snapped_by_orig_id:
                    if (cur_ab.start_date.month == month and cur_ab.start_date.year == scenario.year) \
                       or (cur_ab.end_date.month == month and cur_ab.end_date.year == scenario.year):
                        absence_changes.append(AbsenceChange(
                            type="added",
                            start_date=cur_ab.start_date,
                            end_date=cur_ab.end_date,
                            reason=reasons.get(cur_ab.reason_id) if cur_ab.reason_id else None,
                            hours=_resolve_absence_hours(cur_ab, capacity_svc),
                        ))

            if abs(delta) > 0.1 or absence_changes:
                month_diffs.append(MonthDiff(
                    year=scenario.year,
                    month=month,
                    snapshot_available_hours=snap_avail,
                    current_available_hours=current_avail,
                    delta_hours=delta,
                    absence_changes=absence_changes,
                ))

        if month_diffs:
            emp = employees.get(emp_id)
            changed_employees.append(EmployeeDiff(
                employee_id=emp_id,
                employee_name=emp.display_name if emp else emp_id,
                months=month_diffs,
            ))

    return CapacityDiffResponse(
        has_changes=len(changed_employees) > 0,
        changed_employees=changed_employees,
    )


@router.patch("/scenarios/{scenario_id}/acknowledge-drift", response_model=dict)
async def acknowledge_capacity_drift(
    scenario_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Пометить изменения доступности как просмотренные."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if scenario.status != "approved":
        raise HTTPException(status_code=400, detail="Only approved scenarios can acknowledge drift")
    scenario.capacity_drift_acknowledged_at = datetime.utcnow()
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    return {"ok": True}


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

    query = (
        db.query(ScenarioAllocation, BacklogItem)
        .join(BacklogItem, ScenarioAllocation.backlog_item_id == BacklogItem.id)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(ScenarioAllocation.scenario_id == scenario_id)
    )

    if scenario.status == "draft":
        allowed_issue_ids = (
            db.query(Issue.id)
            .filter(
                Issue.category == BACKLOG_CATEGORY,
                Issue.parent_id.is_(None),
            )
            .scalar_subquery()
        )
        query = query.filter(
            or_(
                BacklogItem.issue_id.is_(None),
                BacklogItem.issue_id.in_(allowed_issue_ids),
            )
        )

    rows = (
        query.order_by(
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
                    backlog_pool_hours=s.backlog_pool_hours,
                )
                for s in snapshots
            ],
        ))
    return result


@router.delete(
    "/scenarios/{scenario_id}/revisions/{revision_id}",
    status_code=204,
)
async def delete_revision(
    scenario_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Удалить ревизию: каскад на все snapshot-таблицы + перепривязка parent."""
    rev = db.query(ScenarioRevision).filter_by(id=revision_id, scenario_id=scenario_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")

    parent_id = rev.parent_revision_id

    # Re-link children to deleted revision's parent
    db.query(ScenarioRevision).filter(
        ScenarioRevision.parent_revision_id == revision_id
    ).update(
        {"parent_revision_id": parent_id},
        synchronize_session=False,
    )

    db.delete(rev)
    db.flush()

    # If approved scenario has no remaining revisions → revert to draft
    remaining = db.query(ScenarioRevision).filter_by(scenario_id=scenario_id).count()
    if remaining == 0:
        scenario = db.get(PlanningScenario, scenario_id)
        if scenario and scenario.status == "approved":
            scenario.status = "draft"

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    return None


def _state_at_revision(scenario_id: str, revision_number: int, db: Session) -> dict[str, str]:
    """Восстановить набор включённых инициатив на момент ревизии N.

    RevisionItem хранит инкрементальную дельту: action='included' (добавлено),
    action='excluded' (исключено) относительно предыдущей ревизии. Состояние на
    ревизии N = сумма дельт по всем ревизиям ≤ N.
    """
    revisions = (
        db.query(ScenarioRevision)
        .filter(
            ScenarioRevision.scenario_id == scenario_id,
            ScenarioRevision.revision_number <= revision_number,
        )
        .order_by(ScenarioRevision.revision_number)
        .all()
    )
    state: dict[str, str] = {}
    for rev in revisions:
        items = (
            db.query(ScenarioRevisionItem)
            .filter(ScenarioRevisionItem.revision_id == rev.id)
            .all()
        )
        for item in items:
            key = item.backlog_item_id or f"__deleted__{item.id}"
            if item.action == "included":
                state[key] = item.backlog_item_name
            elif item.action == "excluded":
                state.pop(key, None)
    return state


@router.get(
    "/scenarios/{scenario_id}/revisions/diff",
    response_model=RevisionDiffResponse,
)
async def diff_scenario_revisions(
    scenario_id: str,
    r1: int = Query(..., ge=1, description="Базовая ревизия"),
    r2: int = Query(..., ge=1, description="Сравниваемая ревизия"),
    db: Session = Depends(get_db),
):
    """Сравнить две ревизии одного сценария: состав инициатив + capacity дельта."""
    if not db.get(PlanningScenario, scenario_id):
        raise HTTPException(status_code=404, detail="Scenario not found")
    if r1 == r2:
        raise HTTPException(status_code=400, detail="r1 and r2 must differ")

    rev1 = (
        db.query(ScenarioRevision)
        .filter(
            ScenarioRevision.scenario_id == scenario_id,
            ScenarioRevision.revision_number == r1,
        )
        .first()
    )
    rev2 = (
        db.query(ScenarioRevision)
        .filter(
            ScenarioRevision.scenario_id == scenario_id,
            ScenarioRevision.revision_number == r2,
        )
        .first()
    )
    if not rev1 or not rev2:
        raise HTTPException(status_code=404, detail="Revision not found")

    state1 = _state_at_revision(scenario_id, r1, db)
    state2 = _state_at_revision(scenario_id, r2, db)

    added = [
        RevisionDiffItem(
            backlog_item_id=k if not k.startswith("__deleted__") else None,
            backlog_item_name=v,
        )
        for k, v in state2.items() if k not in state1
    ]
    removed = [
        RevisionDiffItem(
            backlog_item_id=k if not k.startswith("__deleted__") else None,
            backlog_item_name=v,
        )
        for k, v in state1.items() if k not in state2
    ]
    kept = [
        RevisionDiffItem(
            backlog_item_id=k if not k.startswith("__deleted__") else None,
            backlog_item_name=v,
        )
        for k, v in state2.items() if k in state1
    ]
    added.sort(key=lambda x: x.backlog_item_name)
    removed.sort(key=lambda x: x.backlog_item_name)
    kept.sort(key=lambda x: x.backlog_item_name)

    snaps1 = (
        db.query(ScenarioCapacitySnapshot)
        .filter(ScenarioCapacitySnapshot.revision_id == rev1.id)
        .all()
    )
    snaps2 = (
        db.query(ScenarioCapacitySnapshot)
        .filter(ScenarioCapacitySnapshot.revision_id == rev2.id)
        .all()
    )
    by1: dict[tuple[str, int, int], ScenarioCapacitySnapshot] = {
        (s.employee_id, s.year, s.month): s for s in snaps1
    }
    by2: dict[tuple[str, int, int], ScenarioCapacitySnapshot] = {
        (s.employee_id, s.year, s.month): s for s in snaps2
    }
    emp_names: dict[str, str] = {}
    for s in snaps1 + snaps2:
        emp_names[s.employee_id] = s.employee_name

    keys_by_emp: dict[str, list[tuple[int, int]]] = {}
    for emp_id, year, month in set(by1.keys()) | set(by2.keys()):
        keys_by_emp.setdefault(emp_id, []).append((year, month))

    capacity: list[RevisionDiffEmployee] = []
    for emp_id, ym_list in keys_by_emp.items():
        ym_list.sort()
        months_out: list[RevisionDiffMonth] = []
        total_norm = 0.0
        total_avail = 0.0
        for year, month in ym_list:
            s1 = by1.get((emp_id, year, month))
            s2 = by2.get((emp_id, year, month))
            r1_norm = s1.norm_hours if s1 else 0.0
            r1_avail = s1.available_hours if s1 else 0.0
            r2_norm = s2.norm_hours if s2 else 0.0
            r2_avail = s2.available_hours if s2 else 0.0
            d_norm = round(r2_norm - r1_norm, 2)
            d_avail = round(r2_avail - r1_avail, 2)
            if abs(d_norm) < 0.01 and abs(d_avail) < 0.01:
                continue
            total_norm += d_norm
            total_avail += d_avail
            months_out.append(RevisionDiffMonth(
                year=year, month=month,
                r1_norm_hours=r1_norm, r1_available_hours=r1_avail,
                r2_norm_hours=r2_norm, r2_available_hours=r2_avail,
                delta_norm_hours=d_norm, delta_available_hours=d_avail,
            ))
        if months_out:
            capacity.append(RevisionDiffEmployee(
                employee_id=emp_id,
                employee_name=emp_names.get(emp_id, emp_id),
                months=months_out,
                delta_total_norm_hours=round(total_norm, 2),
                delta_total_available_hours=round(total_avail, 2),
            ))
    capacity.sort(key=lambda e: e.employee_name)

    return RevisionDiffResponse(
        r1=RevisionDiffSide(
            revision_number=rev1.revision_number,
            approved_at=rev1.approved_at.isoformat(),
            note=rev1.note,
            included_count=len(state1),
        ),
        r2=RevisionDiffSide(
            revision_number=rev2.revision_number,
            approved_at=rev2.approved_at.isoformat(),
            note=rev2.note,
            included_count=len(state2),
        ),
        added=added,
        removed=removed,
        kept=kept,
        capacity=capacity,
    )


@router.get("/scenarios/{scenario_id}/revisions/{revision_id}/diff")
async def diff_revision(
    scenario_id: str,
    revision_id: str,
    against: Optional[str] = Query(
        None, description="ID ревизии для сравнения; по умолчанию parent_revision_id"
    ),
    db: Session = Depends(get_db),
):
    """Diff между двумя ревизиями того же сценария по snapshot-таблицам."""
    rev = db.query(ScenarioRevision).filter_by(id=revision_id, scenario_id=scenario_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    against_id = against or rev.parent_revision_id
    if not against_id:
        return {
            "allocations": {"added": [], "removed": [], "changed": []},
            "team": {"added": [], "removed": [], "role_changed": []},
            "rules": {"added": [], "removed": [], "changed": []},
            "external_qa_total_hours": {"before": 0.0, "after": 0.0},
            "capacity_changes": [],
        }
    against_rev = db.query(ScenarioRevision).filter_by(
        id=against_id, scenario_id=scenario_id
    ).first()
    if not against_rev:
        raise HTTPException(
            status_code=404, detail="Against revision not found in same scenario"
        )
    from app.services.snapshot_differ import SnapshotDiffer
    return SnapshotDiffer(db).diff(revision_id=revision_id, against_revision_id=against_id)


@router.get("/scenarios/{scenario_id}/revisions/{revision_id}/breakdown")
async def get_revision_breakdown(
    scenario_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
):
    """Debug-view помесячного breakdown allocation по ролям и сотрудникам."""
    rev = db.query(ScenarioRevision).filter_by(id=revision_id, scenario_id=scenario_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    rows = (
        db.query(ScenarioAllocationBreakdownSnapshot)
        .filter_by(revision_id=revision_id)
        .order_by(
            ScenarioAllocationBreakdownSnapshot.allocation_id,
            ScenarioAllocationBreakdownSnapshot.month,
            ScenarioAllocationBreakdownSnapshot.role,
        )
        .all()
    )
    return {
        "revision_id": revision_id,
        "algo_version": rev.algo_version,
        "rows": [
            {
                "allocation_id": r.allocation_id,
                "month": r.month,
                "role": r.role,
                "employee_id": r.employee_id,
                "is_external": r.is_external,
                "hours": r.hours,
            }
            for r in rows
        ],
    }


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
