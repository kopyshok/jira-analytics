"""CRUD справочника вовлечённости по ролям."""
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InvolvementDefault, ResourcePlan
from app.models.involvement_default import INVOLVEMENT_ROLES
from app.services.analytics_service import parse_teams_csv
from app.services.capacity_service import QUARTER_MONTHS
from app.services.cross_team_occupancy import quarter_num
from app.services.event_bus import EventBroadcaster, get_event_bus
from app.services.involvement_fact import (
    FactCell, last_completed_quarter, team_facts,
)

router = APIRouter()

_CHANGED = {"type": "entity_changed", "entities": ["planning", "resource_planning"]}


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


def _mark_plans_stale(db: Session, team: str, year: int, quarter: int) -> None:
    """Планы команды с квартала действия записи — «Требуется пересчёт»: фазы уже
    берут новый процент, а сроки фаз посчитаны по старому."""
    for plan in db.query(ResourcePlan).filter(
        ResourcePlan.team == team, ResourcePlan.status == "ready",
    ):
        q = quarter_num(plan.quarter)
        if plan.year is not None and q is not None and (plan.year, q) >= (year, quarter):
            plan.status = "stale"


class FactCellOut(BaseModel):
    """Часы и доли за период; доля ``None`` — делить не на что."""

    project_hours: float
    logged_hours: float
    norm_hours: float
    project_day_hours: float
    project_days: int
    fact: Optional[float]
    logged_of_norm: Optional[float]


class FactMonthOut(FactCellOut):
    month: int


class FactPersonOut(BaseModel):
    employee_id: str
    name: str
    role: str
    months: List[FactMonthOut]
    total: FactCellOut


class FactRoleOut(BaseModel):
    role: str
    people: int
    months: List[FactMonthOut]
    total: FactCellOut


class FactTeamOut(BaseModel):
    team: str
    people: List[FactPersonOut]
    roles: List[FactRoleOut]


class InvolvementFactResponse(BaseModel):
    year: int
    quarter: int
    months: List[int]
    teams: List[FactTeamOut]


def _cell(c: FactCell) -> dict:
    return {
        "project_hours": round(c.project_hours, 1),
        "logged_hours": round(c.logged_hours, 1),
        "norm_hours": round(c.norm_hours, 1),
        "project_day_hours": round(c.project_day_hours, 1),
        "project_days": c.project_days,
        "fact": None if c.fact is None else round(c.fact, 4),
        "logged_of_norm": None if c.logged_of_norm is None else round(c.logged_of_norm, 4),
    }


def _months(cells: Dict[int, FactCell]) -> List[dict]:
    return [{"month": m, **_cell(c)} for m, c in sorted(cells.items())]


@router.get("/fact", response_model=InvolvementFactResponse)
def involvement_fact(
    teams: str = Query(..., description="Команды через запятую"),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    db: Session = Depends(get_db),
):
    """Фактическая вовлечённость аналитиков и разработчиков команд за квартал.
    Без квартала — последний завершённый."""
    team_list = [t.strip() for t in parse_teams_csv(teams) if t.strip()]
    if not team_list:
        raise HTTPException(status_code=422, detail="Не выбрана команда")
    if (year is None) != (quarter is None):
        raise HTTPException(status_code=422, detail="Год и квартал задаются вместе")
    if year is None or quarter is None:
        year, quarter = last_completed_quarter(date.today())
    facts = team_facts(db, team_list, year, quarter)
    return {
        "year": year,
        "quarter": quarter,
        "months": list(QUARTER_MONTHS[quarter]),
        "teams": [
            {
                "team": t.team,
                "people": [
                    {
                        "employee_id": p.employee_id, "name": p.name, "role": p.role,
                        "months": _months(p.months), "total": _cell(p.total),
                    }
                    for p in t.people
                ],
                "roles": [
                    {
                        "role": r.role, "people": r.people,
                        "months": _months(r.months), "total": _cell(r.total),
                    }
                    for r in t.roles
                ],
            }
            for t in facts
        ],
    }


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
async def create_default(
    req: InvolvementDefaultCreate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    def work() -> InvolvementDefault:
        _check_role(req.role)
        _check_clash(db, req.team, req.role, req.effective_year, req.effective_quarter)
        row = InvolvementDefault(**req.model_dump())
        db.add(row)
        _mark_plans_stale(db, row.team, row.effective_year, row.effective_quarter)
        db.commit()
        db.refresh(row)
        return row

    row = await run_in_threadpool(work)
    await event_bus.publish(_CHANGED)
    return row


@router.patch("/{default_id}", response_model=InvolvementDefaultResponse)
async def update_default(
    default_id: str,
    req: InvolvementDefaultUpdate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    def work() -> InvolvementDefault:
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
        # Задеты кварталы и до правки, и после: запись могла сменить команду или начало.
        _mark_plans_stale(db, row.team, row.effective_year, row.effective_quarter)
        for k, v in data.items():
            setattr(row, k, v)
        _mark_plans_stale(db, row.team, row.effective_year, row.effective_quarter)
        db.commit()
        db.refresh(row)
        return row

    row = await run_in_threadpool(work)
    await event_bus.publish(_CHANGED)
    return row


@router.delete("/{default_id}", status_code=204)
async def delete_default(
    default_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    def work() -> None:
        row = db.query(InvolvementDefault).filter(InvolvementDefault.id == default_id).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        _mark_plans_stale(db, row.team, row.effective_year, row.effective_quarter)
        db.delete(row)
        db.commit()

    await run_in_threadpool(work)
    await event_bus.publish(_CHANGED)
    return None
