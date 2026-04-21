"""Batch endpoint for role × work_type capacity rules (v3).

Atomic replace for (year, quarter). Server-side validation:
each role group (including role=NULL fallback) must have Σ percent = 100
or be empty (0 rules). Deviations from 100 return HTTP 422 with detail.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MandatoryWorkType, Role, RoleCapacityRule
from app.services.capacity_service import CapacityService, RulesConflict

router = APIRouter()

TOLERANCE = 0.01


class RoleRuleResponse(BaseModel):
    id: str
    year: int
    quarter: int
    role: Optional[str]
    work_type_id: str
    percent_of_norm: float

    class Config:
        from_attributes = True


class RoleRuleIn(BaseModel):
    role: Optional[str] = None
    work_type_id: str
    percent_of_norm: float = Field(ge=0, le=100)


class BatchSaveRequest(BaseModel):
    rules: List[RoleRuleIn]


class BatchValidationError(BaseModel):
    role: Optional[str]
    sum: float
    expected: float = 100.0


class CopyRulesRequest(BaseModel):
    from_year: int
    from_quarter: int = Field(ge=1, le=4)
    to_year: int
    to_quarter: int = Field(ge=1, le=4)


class CopyRulesResponse(BaseModel):
    created: int


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


@router.put("/batch", response_model=List[RoleRuleResponse])
def save_batch(
    req: BatchSaveRequest,
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    # Validate roles + work_types.
    valid_codes = {
        r.code for r in db.query(Role).filter(Role.is_active.is_(True)).all()
    }
    for r in req.rules:
        if r.role is not None and r.role not in valid_codes:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown role {r.role!r}. Allowed: {sorted(valid_codes) + [None]}",
            )
    wt_ids = {r.work_type_id for r in req.rules}
    if wt_ids:
        found = {
            x.id
            for x in db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.id.in_(wt_ids))
            .all()
        }
        missing = wt_ids - found
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown work_type_id(s): {sorted(missing)}",
            )

    # Group by role and validate Σ = 100 per non-empty group.
    by_role: dict[Optional[str], list[RoleRuleIn]] = {}
    for r in req.rules:
        by_role.setdefault(r.role, []).append(r)

    errors: list[BatchValidationError] = []
    for role, group in by_role.items():
        s = sum(x.percent_of_norm for x in group)
        if abs(s - 100.0) > TOLERANCE and len(group) > 0:
            errors.append(BatchValidationError(role=role, sum=s))
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": [e.model_dump() for e in errors]},
        )

    # Detect duplicate (role, work_type_id) entries inside the payload.
    seen: set[tuple[Optional[str], str]] = set()
    for r in req.rules:
        key = (r.role, r.work_type_id)
        if key in seen:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate rule for role={r.role!r} work_type_id={r.work_type_id!r}",
            )
        seen.add(key)

    # Atomic replace.
    db.query(RoleCapacityRule).filter(
        RoleCapacityRule.year == year, RoleCapacityRule.quarter == quarter,
    ).delete(synchronize_session=False)

    created: list[RoleCapacityRule] = []
    for r in req.rules:
        rule = RoleCapacityRule(
            year=year, quarter=quarter,
            role=r.role,
            work_type_id=r.work_type_id,
            percent_of_norm=r.percent_of_norm,
        )
        db.add(rule)
        created.append(rule)
    db.commit()
    # Refresh to get ids post-commit. Snapshot fields to avoid expired-attr reload
    # on worker-thread re-read (see CLAUDE.md DB caveat).
    for c in created:
        db.refresh(c)
    return created


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
