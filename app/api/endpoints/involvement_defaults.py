"""CRUD справочника вовлечённости по ролям."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InvolvementDefault
from app.models.involvement_default import INVOLVEMENT_ROLES

router = APIRouter()


class InvolvementDefaultResponse(BaseModel):
    id: str
    team: str
    role: str
    effective_year: int
    effective_quarter: int
    involvement: float

    class Config:
        from_attributes = True


class InvolvementDefaultCreate(BaseModel):
    team: str = Field(min_length=1, max_length=200)
    role: str
    effective_year: int = Field(ge=2000, le=2100)
    effective_quarter: int = Field(ge=1, le=4)
    involvement: float = Field(ge=0, le=1)


class InvolvementDefaultUpdate(BaseModel):
    team: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = None
    effective_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    effective_quarter: Optional[int] = Field(default=None, ge=1, le=4)
    involvement: Optional[float] = Field(default=None, ge=0, le=1)


def _check_role(role: Optional[str]) -> None:
    if role is not None and role not in INVOLVEMENT_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown role {role!r}. Allowed: {list(INVOLVEMENT_ROLES)}",
        )


def _check_clash(db, team, role, year, quarter, exclude_id=None) -> None:
    q = db.query(InvolvementDefault).filter(
        InvolvementDefault.team == team,
        InvolvementDefault.role == role,
        InvolvementDefault.effective_year == year,
        InvolvementDefault.effective_quarter == quarter,
    )
    if exclude_id is not None:
        q = q.filter(InvolvementDefault.id != exclude_id)
    if q.first() is not None:
        raise HTTPException(
            status_code=409,
            detail="Запись для этой команды, роли и квартала уже есть",
        )


@router.get("", response_model=List[InvolvementDefaultResponse])
def list_defaults(team: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(InvolvementDefault)
    if team is not None:
        q = q.filter(InvolvementDefault.team == team)
    return q.order_by(
        InvolvementDefault.team,
        InvolvementDefault.role,
        InvolvementDefault.effective_year,
        InvolvementDefault.effective_quarter,
    ).all()


@router.post("", response_model=InvolvementDefaultResponse, status_code=201)
def create_default(req: InvolvementDefaultCreate, db: Session = Depends(get_db)):
    _check_role(req.role)
    _check_clash(db, req.team, req.role, req.effective_year, req.effective_quarter)
    row = InvolvementDefault(**req.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{default_id}", response_model=InvolvementDefaultResponse)
def update_default(default_id: str, req: InvolvementDefaultUpdate, db: Session = Depends(get_db)):
    row = db.query(InvolvementDefault).filter(InvolvementDefault.id == default_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    data = req.model_dump(exclude_unset=True)
    if "role" in data:
        _check_role(data["role"])
    merged = {
        "team": data.get("team", row.team),
        "role": data.get("role", row.role),
        "year": data.get("effective_year", row.effective_year),
        "quarter": data.get("effective_quarter", row.effective_quarter),
    }
    _check_clash(
        db, merged["team"], merged["role"], merged["year"], merged["quarter"],
        exclude_id=default_id,
    )
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{default_id}", status_code=204)
def delete_default(default_id: str, db: Session = Depends(get_db)):
    row = db.query(InvolvementDefault).filter(InvolvementDefault.id == default_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return None
