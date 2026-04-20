"""CRUD endpoints for Role directory."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, Role

router = APIRouter()


class RoleOut(BaseModel):
    id: str
    code: str
    label: str
    color: str
    is_active: bool
    counts_in_planning: bool
    sort_order: int

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    code: str
    label: str
    color: str = "#888780"
    counts_in_planning: bool = True
    is_active: bool = True


class RolePatch(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    counts_in_planning: Optional[bool] = None
    is_active: Optional[bool] = None


class ReorderBody(BaseModel):
    ids: List[str]


@router.get("", response_model=List[RoleOut])
def list_roles(db: Session = Depends(get_db)):
    return db.query(Role).order_by(Role.sort_order, Role.label).all()


@router.post("", response_model=RoleOut, status_code=201)
def create_role(body: RoleCreate, db: Session = Depends(get_db)):
    if db.query(Role).filter(Role.code == body.code).one_or_none():
        raise HTTPException(409, f"Роль с кодом {body.code!r} уже существует")
    max_order = db.query(Role).count()
    r = Role(
        code=body.code,
        label=body.label,
        color=body.color,
        counts_in_planning=body.counts_in_planning,
        is_active=body.is_active,
        sort_order=max_order,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.patch("/{role_id}", response_model=RoleOut)
def patch_role(role_id: str, body: RolePatch, db: Session = Depends(get_db)):
    r = db.query(Role).filter(Role.id == role_id).one_or_none()
    if r is None:
        raise HTTPException(404, "Роль не найдена")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(r, f, v)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{role_id}", status_code=204)
def delete_role(role_id: str, db: Session = Depends(get_db)):
    r = db.query(Role).filter(Role.id == role_id).one_or_none()
    if r is None:
        raise HTTPException(404, "Роль не найдена")
    in_use = db.query(Employee).filter(Employee.role == r.code).count()
    if in_use > 0:
        raise HTTPException(409, f"Роль используется {in_use} сотрудниками")
    db.delete(r)
    db.commit()
    return None


@router.post("/reorder", status_code=200)
def reorder(body: ReorderBody, db: Session = Depends(get_db)):
    for idx, rid in enumerate(body.ids):
        r = db.query(Role).filter(Role.id == rid).one_or_none()
        if r is not None:
            r.sort_order = idx
    db.commit()
    return {"ok": True}
