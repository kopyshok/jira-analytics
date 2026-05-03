"""Capacity rule endpoints: role rules, employee overrides, absence reasons."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Absence,
    AbsenceReason,
    Employee,
    EmployeeCapacityOverride,
    MandatoryWorkType,
    Role,
    RoleCapacityRule,
)
from app.services.capacity_service import CapacityService, RulesConflict

TOLERANCE = 0.01

# ---------------------------------------------------------------------------
# Role capacity rules
# ---------------------------------------------------------------------------

role_rules_router = APIRouter()


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


class _RoleBatchValidationError(BaseModel):
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


@role_rules_router.get("", response_model=List[RoleRuleResponse])
def list_role_rules(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    return (
        db.query(RoleCapacityRule)
        .filter(RoleCapacityRule.year == year, RoleCapacityRule.quarter == quarter)
        .all()
    )


@role_rules_router.put("/batch", response_model=List[RoleRuleResponse])
def save_role_rules_batch(
    req: BatchSaveRequest,
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
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
            raise HTTPException(status_code=422, detail=f"Unknown work_type_id(s): {sorted(missing)}")

    by_role: dict[Optional[str], list[RoleRuleIn]] = {}
    for r in req.rules:
        by_role.setdefault(r.role, []).append(r)

    errors: list[_RoleBatchValidationError] = []
    for role, group in by_role.items():
        s = sum(x.percent_of_norm for x in group)
        if abs(s - 100.0) > TOLERANCE and len(group) > 0:
            errors.append(_RoleBatchValidationError(role=role, sum=s))
    if errors:
        raise HTTPException(status_code=422, detail={"errors": [e.model_dump() for e in errors]})

    seen: set[tuple[Optional[str], str]] = set()
    for r in req.rules:
        key = (r.role, r.work_type_id)
        if key in seen:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate rule for role={r.role!r} work_type_id={r.work_type_id!r}",
            )
        seen.add(key)

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
    for c in created:
        db.refresh(c)
    return created


@role_rules_router.post("/copy-to-quarter", response_model=CopyRulesResponse, status_code=201)
def copy_role_rules(req: CopyRulesRequest, db: Session = Depends(get_db)):
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


# ---------------------------------------------------------------------------
# Employee capacity overrides
# ---------------------------------------------------------------------------

employee_overrides_router = APIRouter()


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


class _EmpBatchValidationError(BaseModel):
    employee_id: str
    sum: float
    expected: float = 100.0


@employee_overrides_router.get("", response_model=List[OverrideResponse])
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


@employee_overrides_router.put("/batch", response_model=List[OverrideResponse])
def save_employee_overrides_batch(
    req: BatchEmployeeRequest,
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    emp_ids = {e.employee_id for e in req.employee_rules}
    if emp_ids:
        known = {x.id for x in db.query(Employee).filter(Employee.id.in_(emp_ids)).all()}
        unknown = emp_ids - known
        if unknown:
            raise HTTPException(status_code=404, detail=f"Unknown employee_id(s): {sorted(unknown)}")

    wt_ids = {r.work_type_id for e in req.employee_rules for r in e.rules}
    if wt_ids:
        known_wt = {
            x.id
            for x in db.query(MandatoryWorkType).filter(MandatoryWorkType.id.in_(wt_ids)).all()
        }
        missing = wt_ids - known_wt
        if missing:
            raise HTTPException(status_code=422, detail=f"Unknown work_type_id(s): {sorted(missing)}")

    errors: list[_EmpBatchValidationError] = []
    for e in req.employee_rules:
        seen_wt: set[str] = set()
        for r in e.rules:
            if r.work_type_id in seen_wt:
                raise HTTPException(
                    status_code=422,
                    detail=f"Duplicate rule for employee {e.employee_id!r} work_type_id={r.work_type_id!r}",
                )
            seen_wt.add(r.work_type_id)
        if e.rules:
            s = sum(r.percent_of_norm for r in e.rules)
            if abs(s - 100.0) > TOLERANCE:
                errors.append(_EmpBatchValidationError(employee_id=e.employee_id, sum=s))
    if errors:
        raise HTTPException(status_code=422, detail={"errors": [e.model_dump() for e in errors]})

    if emp_ids:
        db.query(EmployeeCapacityOverride).filter(
            EmployeeCapacityOverride.year == year,
            EmployeeCapacityOverride.quarter == quarter,
            EmployeeCapacityOverride.employee_id.in_(list(emp_ids)),
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


# ---------------------------------------------------------------------------
# Absence reasons (reference directory)
# ---------------------------------------------------------------------------

absence_reasons_router = APIRouter()


class AbsenceReasonResponse(BaseModel):
    id: str
    code: str
    label: str
    is_planned: bool
    color: Optional[str]
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class AbsenceReasonCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    is_planned: bool = False
    color: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class AbsenceReasonUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_planned: Optional[bool] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ReorderRequest(BaseModel):
    ids: List[str]


@absence_reasons_router.get("", response_model=List[AbsenceReasonResponse])
def list_reasons(db: Session = Depends(get_db)):
    return (
        db.query(AbsenceReason)
        .order_by(AbsenceReason.sort_order, AbsenceReason.code)
        .all()
    )


@absence_reasons_router.post("", response_model=AbsenceReasonResponse, status_code=201)
def create_reason(req: AbsenceReasonCreate, db: Session = Depends(get_db)):
    existing = db.query(AbsenceReason).filter(AbsenceReason.code == req.code).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Code {req.code!r} exists")
    r = AbsenceReason(**req.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@absence_reasons_router.patch("/{reason_id}", response_model=AbsenceReasonResponse)
def update_reason(reason_id: str, req: AbsenceReasonUpdate, db: Session = Depends(get_db)):
    r = db.query(AbsenceReason).filter(AbsenceReason.id == reason_id).one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Reason not found")
    data = req.model_dump(exclude_unset=True)
    if "code" in data and data["code"] != r.code:
        clash = (
            db.query(AbsenceReason)
            .filter(AbsenceReason.code == data["code"], AbsenceReason.id != reason_id)
            .one_or_none()
        )
        if clash is not None:
            raise HTTPException(status_code=409, detail=f"Code {data['code']!r} taken")
    for k, v in data.items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r


@absence_reasons_router.delete("/{reason_id}", status_code=204)
def delete_reason(reason_id: str, db: Session = Depends(get_db)):
    r = db.query(AbsenceReason).filter(AbsenceReason.id == reason_id).one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Reason not found")
    used = db.query(Absence).filter(Absence.reason_id == reason_id).count()
    if used > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Reason is referenced by {used} absence(s); reassign or remove them first",
        )
    db.delete(r)
    db.commit()
    return None


@absence_reasons_router.post("/reorder", response_model=List[AbsenceReasonResponse])
def reorder_reasons(req: ReorderRequest, db: Session = Depends(get_db)):
    rows = db.query(AbsenceReason).filter(AbsenceReason.id.in_(req.ids)).all()
    by_id = {r.id: r for r in rows}
    missing = [i for i in req.ids if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown id(s): {missing}")
    for idx, rid in enumerate(req.ids):
        by_id[rid].sort_order = idx
    db.commit()
    return (
        db.query(AbsenceReason)
        .order_by(AbsenceReason.sort_order, AbsenceReason.code)
        .all()
    )
