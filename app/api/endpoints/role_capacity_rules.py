"""CRUD endpoints for role × work_type capacity rules."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EMPLOYEE_ROLES, MandatoryWorkType, RoleCapacityRule
from app.services.capacity_service import CapacityService, RulesConflict

router = APIRouter()


class RoleRuleResponse(BaseModel):
    id: str
    year: int
    quarter: int
    role: Optional[str]
    work_type_id: str
    percent_of_norm: float

    class Config:
        from_attributes = True


class RoleRuleCreate(BaseModel):
    year: int
    quarter: int = Field(ge=1, le=4)
    role: Optional[str] = None
    work_type_id: str
    percent_of_norm: float = Field(ge=0, le=100)


class RoleRuleUpdate(BaseModel):
    percent_of_norm: Optional[float] = Field(default=None, ge=0, le=100)


class CopyRulesRequest(BaseModel):
    from_year: int
    from_quarter: int = Field(ge=1, le=4)
    to_year: int
    to_quarter: int = Field(ge=1, le=4)


class CopyRulesResponse(BaseModel):
    created: int


def _validate_role(role: Optional[str]) -> None:
    if role is not None and role not in EMPLOYEE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown role {role!r}. Allowed: {list(EMPLOYEE_ROLES) + [None]}",
        )


def _validate_work_type(db: Session, work_type_id: str) -> None:
    exists = (
        db.query(MandatoryWorkType)
        .filter(MandatoryWorkType.id == work_type_id)
        .first()
    )
    if exists is None:
        raise HTTPException(status_code=404, detail=f"Work type {work_type_id!r} not found")


@router.get("", response_model=List[RoleRuleResponse])
def list_rules(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    return (
        db.query(RoleCapacityRule)
        .filter(RoleCapacityRule.year == year, RoleCapacityRule.quarter == quarter)
        .all()
    )


@router.post("", response_model=RoleRuleResponse, status_code=201)
def create_rule(req: RoleRuleCreate, db: Session = Depends(get_db)):
    _validate_role(req.role)
    _validate_work_type(db, req.work_type_id)
    existing = (
        db.query(RoleCapacityRule)
        .filter(
            RoleCapacityRule.year == req.year,
            RoleCapacityRule.quarter == req.quarter,
            RoleCapacityRule.role.is_(req.role) if req.role is None else RoleCapacityRule.role == req.role,
            RoleCapacityRule.work_type_id == req.work_type_id,
        )
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Rule for this (year, quarter, role, work_type) already exists",
        )
    rule = RoleCapacityRule(**req.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RoleRuleResponse)
def update_rule(rule_id: str, req: RoleRuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(RoleCapacityRule).filter(RoleCapacityRule.id == rule_id).one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = db.query(RoleCapacityRule).filter(RoleCapacityRule.id == rule_id).one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return None


@router.post("/copy-to-quarter", response_model=CopyRulesResponse, status_code=201)
def copy_rules(req: CopyRulesRequest, db: Session = Depends(get_db)):
    svc = CapacityService(db)
    try:
        created = svc.copy_role_rules_to_quarter(
            req.from_year, req.from_quarter, req.to_year, req.to_quarter,
        )
    except RulesConflict as exc:
        raise HTTPException(status_code=409, detail={"conflicts": exc.conflicts})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return CopyRulesResponse(created=created)
