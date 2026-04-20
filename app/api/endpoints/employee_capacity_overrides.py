"""CRUD endpoints for per-employee capacity overrides."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, EmployeeCapacityOverride, MandatoryWorkType

router = APIRouter()


class OverrideResponse(BaseModel):
    id: str
    year: int
    quarter: int
    employee_id: str
    work_type_id: str
    percent_of_norm: float

    class Config:
        from_attributes = True


class OverrideCreate(BaseModel):
    year: int
    quarter: int = Field(ge=1, le=4)
    employee_id: str
    work_type_id: str
    percent_of_norm: float = Field(ge=0, le=100)


class OverrideUpdate(BaseModel):
    percent_of_norm: Optional[float] = Field(default=None, ge=0, le=100)


def _check_employee(db: Session, employee_id: str) -> None:
    if db.query(Employee).filter(Employee.id == employee_id).first() is None:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id!r} not found")


def _check_work_type(db: Session, wt_id: str) -> None:
    if (
        db.query(MandatoryWorkType)
        .filter(MandatoryWorkType.id == wt_id)
        .first()
        is None
    ):
        raise HTTPException(status_code=404, detail=f"Work type {wt_id!r} not found")


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


@router.post("", response_model=OverrideResponse, status_code=201)
def create_override(req: OverrideCreate, db: Session = Depends(get_db)):
    _check_employee(db, req.employee_id)
    _check_work_type(db, req.work_type_id)
    existing = (
        db.query(EmployeeCapacityOverride)
        .filter(
            EmployeeCapacityOverride.year == req.year,
            EmployeeCapacityOverride.quarter == req.quarter,
            EmployeeCapacityOverride.employee_id == req.employee_id,
            EmployeeCapacityOverride.work_type_id == req.work_type_id,
        )
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Override for this (year, quarter, employee, work_type) already exists",
        )
    ov = EmployeeCapacityOverride(**req.model_dump())
    db.add(ov)
    db.commit()
    db.refresh(ov)
    return ov


@router.patch("/{override_id}", response_model=OverrideResponse)
def update_override(override_id: str, req: OverrideUpdate, db: Session = Depends(get_db)):
    ov = (
        db.query(EmployeeCapacityOverride)
        .filter(EmployeeCapacityOverride.id == override_id)
        .one_or_none()
    )
    if ov is None:
        raise HTTPException(status_code=404, detail="Override not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(ov, k, v)
    db.commit()
    db.refresh(ov)
    return ov


@router.delete("/{override_id}", status_code=204)
def delete_override(override_id: str, db: Session = Depends(get_db)):
    ov = (
        db.query(EmployeeCapacityOverride)
        .filter(EmployeeCapacityOverride.id == override_id)
        .one_or_none()
    )
    if ov is None:
        raise HTTPException(status_code=404, detail="Override not found")
    db.delete(ov)
    db.commit()
    return None
