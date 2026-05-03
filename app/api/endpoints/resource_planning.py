"""Resource Planning API — ScheduledBlocks + ResourcePlan + Gantt projection."""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models import (
    ResourcePlan,
    ResourcePlanAssignment,
    ScheduledBlock,
)
from app.models.user import User
from app.services.resource_planning_service import ResourcePlanningService

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────

class ScheduledBlockCreate(BaseModel):
    team: Optional[str] = None
    role_id: Optional[str] = None
    employee_id: Optional[str] = None
    start_date: date
    end_date: date
    reason: str


class ScheduledBlockOut(BaseModel):
    id: str
    team: Optional[str]
    role_id: Optional[str]
    employee_id: Optional[str]
    start_date: date
    end_date: date
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


class AssignmentOut(BaseModel):
    id: str
    backlog_item_id: str
    backlog_item_title: str
    phase: str
    employee_id: Optional[str]
    employee_name: Optional[str]
    part_number: int
    hours_allocated: Optional[float]
    start_date: Optional[date]
    end_date: Optional[date]
    is_on_critical_path: bool
    slack_days: Optional[float]

    model_config = {"from_attributes": True}


class ConflictOut(BaseModel):
    type: str
    severity: str
    backlog_item_id: Optional[str]
    backlog_item_title: Optional[str]
    employee_id: Optional[str]
    message: str


class GanttProjection(BaseModel):
    plan: ResourcePlanOut
    assignments: List[AssignmentOut]
    conflicts: List[ConflictOut]


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
    return db.execute(q).scalars().all()


@router.post("/scheduled-blocks", response_model=ScheduledBlockOut, status_code=201)
def create_scheduled_block(
    data: ScheduledBlockCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if data.end_date < data.start_date:
        raise HTTPException(422, "end_date must be >= start_date")
    block = ScheduledBlock(**data.model_dump())
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.patch("/scheduled-blocks/{block_id}", response_model=ScheduledBlockOut)
def update_scheduled_block(
    block_id: str,
    data: ScheduledBlockCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    block = db.get(ScheduledBlock, block_id)
    if not block:
        raise HTTPException(404, "ScheduledBlock not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(block, k, v)
    db.commit()
    db.refresh(block)
    return block


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
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(ResourcePlan).order_by(ResourcePlan.created_at.desc())
    if team:
        q = q.where(ResourcePlan.team == team)
    return db.execute(q).scalars().all()


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


@router.get("/resource-plans/{plan_id}/gantt", response_model=GanttProjection)
def get_gantt(
    plan_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404)

    assignments_raw = db.execute(
        select(ResourcePlanAssignment)
        .options(joinedload(ResourcePlanAssignment.backlog_item))
        .options(joinedload(ResourcePlanAssignment.employee))
        .where(ResourcePlanAssignment.plan_id == plan_id)
        .order_by(ResourcePlanAssignment.start_date)
    ).scalars().all()

    assignments = [
        AssignmentOut(
            id=a.id,
            backlog_item_id=a.backlog_item_id,
            backlog_item_title=a.backlog_item.title if a.backlog_item else "",
            phase=a.phase,
            employee_id=a.employee_id,
            employee_name=a.employee.display_name if a.employee else None,
            part_number=a.part_number,
            hours_allocated=a.hours_allocated,
            start_date=a.start_date,
            end_date=a.end_date,
            is_on_critical_path=a.is_on_critical_path,
            slack_days=a.slack_days,
        )
        for a in assignments_raw
    ]

    conflicts = _detect_conflicts(plan, assignments_raw, db)

    return GanttProjection(plan=plan, assignments=assignments, conflicts=conflicts)


def _detect_conflicts(plan, assignments, db):
    conflicts = []
    svc = ResourcePlanningService(db)
    q_start, q_end = svc._quarter_bounds(plan)
    for a in assignments:
        if a.phase == "opo" and a.end_date and a.end_date > q_end:
            conflicts.append(ConflictOut(
                type="QUARTER_OVERFLOW",
                severity="critical",
                backlog_item_id=a.backlog_item_id,
                backlog_item_title=a.backlog_item.title if a.backlog_item else "",
                employee_id=None,
                message=f"Инициатива не вмещается в квартал: ОПЭ заканчивается {a.end_date}",
            ))
    return conflicts
