"""CRUD endpoints for AbsenceReason directory."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Absence, AbsenceReason

router = APIRouter()


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


@router.get("", response_model=List[AbsenceReasonResponse])
def list_reasons(db: Session = Depends(get_db)):
    return (
        db.query(AbsenceReason)
        .order_by(AbsenceReason.sort_order, AbsenceReason.code)
        .all()
    )


@router.post("", response_model=AbsenceReasonResponse, status_code=201)
def create_reason(req: AbsenceReasonCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(AbsenceReason).filter(AbsenceReason.code == req.code).one_or_none()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Code {req.code!r} exists")
    r = AbsenceReason(**req.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.patch("/{reason_id}", response_model=AbsenceReasonResponse)
def update_reason(
    reason_id: str, req: AbsenceReasonUpdate, db: Session = Depends(get_db),
):
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


@router.delete("/{reason_id}", status_code=204)
def delete_reason(reason_id: str, db: Session = Depends(get_db)):
    r = db.query(AbsenceReason).filter(AbsenceReason.id == reason_id).one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Reason not found")
    used = (
        db.query(Absence).filter(Absence.reason_id == reason_id).count()
    )
    if used > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Reason is referenced by {used} absence(s); reassign or remove them first",
        )
    db.delete(r)
    db.commit()
    return None


@router.post("/reorder", response_model=List[AbsenceReasonResponse])
def reorder(req: ReorderRequest, db: Session = Depends(get_db)):
    rows = (
        db.query(AbsenceReason)
        .filter(AbsenceReason.id.in_(req.ids))
        .all()
    )
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
