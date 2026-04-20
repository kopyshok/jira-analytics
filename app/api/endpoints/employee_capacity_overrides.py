"""Batch endpoint for per-employee capacity overrides (v3)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, EmployeeCapacityOverride, MandatoryWorkType

router = APIRouter()

TOLERANCE = 0.01


class OverrideResponse(BaseModel):
    id: str
    year: int
    quarter: int
    employee_id: str
    work_type_id: str
    percent_of_norm: float

    class Config:
        from_attributes = True


class EmployeeRuleIn(BaseModel):
    work_type_id: str
    percent_of_norm: float = Field(ge=0, le=100)


class EmployeeRulesIn(BaseModel):
    employee_id: str
    rules: List[EmployeeRuleIn]


class BatchEmployeeRequest(BaseModel):
    employee_rules: List[EmployeeRulesIn]


class BatchValidationError(BaseModel):
    employee_id: str
    sum: float
    expected: float = 100.0


@router.get("", response_model=List[OverrideResponse])
def list_overrides(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    employee_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(EmployeeCapacityOverride).filter(
        EmployeeCapacityOverride.year == year,
        EmployeeCapacityOverride.quarter == quarter,
    )
    if employee_id is not None:
        q = q.filter(EmployeeCapacityOverride.employee_id == employee_id)
    return q.all()


@router.put("/batch", response_model=List[OverrideResponse])
def save_batch(
    req: BatchEmployeeRequest,
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    emp_ids = {e.employee_id for e in req.employee_rules}
    if emp_ids:
        known = {
            x.id
            for x in db.query(Employee).filter(Employee.id.in_(emp_ids)).all()
        }
        unknown = emp_ids - known
        if unknown:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown employee_id(s): {sorted(unknown)}",
            )

    wt_ids = {
        r.work_type_id
        for e in req.employee_rules
        for r in e.rules
    }
    if wt_ids:
        known_wt = {
            x.id
            for x in db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.id.in_(wt_ids))
            .all()
        }
        missing = wt_ids - known_wt
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown work_type_id(s): {sorted(missing)}",
            )

    errors: list[BatchValidationError] = []
    for e in req.employee_rules:
        seen: set[str] = set()
        for r in e.rules:
            if r.work_type_id in seen:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Duplicate rule for employee {e.employee_id!r} "
                        f"work_type_id={r.work_type_id!r}"
                    ),
                )
            seen.add(r.work_type_id)
        if e.rules:
            s = sum(r.percent_of_norm for r in e.rules)
            if abs(s - 100.0) > TOLERANCE:
                errors.append(BatchValidationError(employee_id=e.employee_id, sum=s))
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": [e.model_dump() for e in errors]},
        )

    touched_emp_ids = list(emp_ids)
    if touched_emp_ids:
        db.query(EmployeeCapacityOverride).filter(
            EmployeeCapacityOverride.year == year,
            EmployeeCapacityOverride.quarter == quarter,
            EmployeeCapacityOverride.employee_id.in_(touched_emp_ids),
        ).delete(synchronize_session=False)

    created: list[EmployeeCapacityOverride] = []
    for e in req.employee_rules:
        for r in e.rules:
            ov = EmployeeCapacityOverride(
                year=year, quarter=quarter,
                employee_id=e.employee_id,
                work_type_id=r.work_type_id,
                percent_of_norm=r.percent_of_norm,
            )
            db.add(ov)
            created.append(ov)
    db.commit()
    for c in created:
        db.refresh(c)
    return created
