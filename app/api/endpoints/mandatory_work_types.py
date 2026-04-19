"""CRUD endpoints for mandatory work type directory."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    EmployeeCapacityOverride,
    MandatoryWorkType,
    RoleCapacityRule,
)

router = APIRouter()


class WorkTypeResponse(BaseModel):
    id: str
    code: str
    label: str
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class WorkTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    is_active: bool = True
    sort_order: int = 0


class WorkTypeUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ReorderRequest(BaseModel):
    ids: List[str]


@router.get("", response_model=List[WorkTypeResponse])
def list_work_types(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    q = db.query(MandatoryWorkType)
    if is_active is not None:
        q = q.filter(MandatoryWorkType.is_active.is_(is_active))
    return (
        q.order_by(MandatoryWorkType.sort_order, MandatoryWorkType.label).all()
    )


@router.post("", response_model=WorkTypeResponse, status_code=201)
def create_work_type(req: WorkTypeCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(MandatoryWorkType)
        .filter(MandatoryWorkType.code == req.code)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"code {req.code!r} already exists")
    wt = MandatoryWorkType(**req.model_dump())
    db.add(wt)
    db.commit()
    db.refresh(wt)
    return wt


@router.patch("/{wt_id}", response_model=WorkTypeResponse)
def update_work_type(wt_id: str, req: WorkTypeUpdate, db: Session = Depends(get_db)):
    wt = db.query(MandatoryWorkType).filter(MandatoryWorkType.id == wt_id).one_or_none()
    if wt is None:
        raise HTTPException(status_code=404, detail="Work type not found")
    data = req.model_dump(exclude_unset=True)
    if "code" in data and data["code"] != wt.code:
        conflict = (
            db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.code == data["code"])
            .one_or_none()
        )
        if conflict is not None:
            raise HTTPException(status_code=409, detail=f"code {data['code']!r} already exists")
    for k, v in data.items():
        setattr(wt, k, v)
    db.commit()
    db.refresh(wt)
    return wt


@router.delete("/{wt_id}", status_code=204)
def delete_work_type(wt_id: str, db: Session = Depends(get_db)):
    wt = db.query(MandatoryWorkType).filter(MandatoryWorkType.id == wt_id).one_or_none()
    if wt is None:
        raise HTTPException(status_code=404, detail="Work type not found")
    has_rules = (
        db.query(RoleCapacityRule)
        .filter(RoleCapacityRule.work_type_id == wt_id)
        .first()
        is not None
    )
    has_overrides = (
        db.query(EmployeeCapacityOverride)
        .filter(EmployeeCapacityOverride.work_type_id == wt_id)
        .first()
        is not None
    )
    if has_rules or has_overrides:
        raise HTTPException(
            status_code=409,
            detail="Work type is referenced by rules/overrides; deactivate it instead.",
        )
    db.delete(wt)
    db.commit()
    return None


@router.post("/reorder", response_model=List[WorkTypeResponse])
def reorder_work_types(req: ReorderRequest, db: Session = Depends(get_db)):
    """Переписать sort_order = позиция в списке ids."""
    by_id = {
        wt.id: wt
        for wt in db.query(MandatoryWorkType)
        .filter(MandatoryWorkType.id.in_(req.ids))
        .all()
    }
    missing = set(req.ids) - set(by_id)
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown ids: {sorted(missing)}")
    for pos, wt_id in enumerate(req.ids):
        by_id[wt_id].sort_order = pos
    db.commit()
    return (
        db.query(MandatoryWorkType)
        .order_by(MandatoryWorkType.sort_order, MandatoryWorkType.label)
        .all()
    )
