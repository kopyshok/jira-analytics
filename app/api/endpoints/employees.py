"""Employees API endpoints.

Список сотрудников для использования во фронтенде (выпадающие списки и т.п.).
"""

from datetime import datetime
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, EMPLOYEE_ROLES, EmployeeTeam
from app.services.employee_team_service import EmployeeTeamService


router = APIRouter()


class EmployeeTeamItem(BaseModel):
    team: str
    is_primary: bool

    model_config = {"from_attributes": True}


class EmployeeResponse(BaseModel):
    id: str
    jira_account_id: str
    display_name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    role: Optional[str] = None  # код роли из EMPLOYEE_ROLES
    team: Optional[str] = None  # legacy: имя primary team
    teams: Optional[List[EmployeeTeamItem]] = None  # присутствует только если with_teams=true

    model_config = {"from_attributes": True}


class EmployeePatchRequest(BaseModel):
    """Частичное обновление сотрудника (пока только role)."""

    role: Optional[str] = None  # None → сбросить роль


class EmployeeFromJiraRequest(BaseModel):
    jira_account_id: str
    display_name: str
    email: Optional[str] = None
    is_active: bool = True
    avatar_url: Optional[str] = None


class RecalcActiveResponse(BaseModel):
    activated: int
    deactivated: int
    total_active: int


@router.get("", response_model=List[EmployeeResponse])
def list_employees(
    is_active: Optional[bool] = Query(None),
    with_teams: bool = Query(False, description="Включить M:N teams в ответ"),
    db: Session = Depends(get_db),
):
    """Список сотрудников."""
    query = db.query(Employee).order_by(Employee.display_name)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    employees = query.all()

    result: List[EmployeeResponse] = []
    for e in employees:
        payload = EmployeeResponse.model_validate(e)
        if with_teams:
            # Отсортировать: primary первым, потом по имени.
            teams = sorted(
                e.teams,
                key=lambda t: (not t.is_primary, t.team),
            )
            payload.teams = [EmployeeTeamItem.model_validate(t) for t in teams]
        else:
            payload.teams = None  # не утекать ORM-relationship когда не запрошено
        result.append(payload)
    return result


@router.post("/from-jira", response_model=EmployeeResponse)
def employee_from_jira(
    req: EmployeeFromJiraRequest,
    db: Session = Depends(get_db),
):
    """Явное добавление сотрудника из Jira (автокомплит на фронте)."""
    existing = (
        db.query(Employee)
        .filter(Employee.jira_account_id == req.jira_account_id)
        .one_or_none()
    )
    if existing is None:
        existing = Employee(
            id=str(uuid.uuid4()),
            jira_account_id=req.jira_account_id,
            display_name=req.display_name,
            email=req.email,
            avatar_url=req.avatar_url,
            is_active=True,
            synced_at=datetime.utcnow(),
        )
        db.add(existing)
    else:
        existing.display_name = req.display_name
        existing.email = req.email
        existing.avatar_url = req.avatar_url
        existing.is_active = True
        existing.synced_at = datetime.utcnow()

    db.flush()
    # Snapshot before commit — commit expires attrs and a subsequent read
    # may hit a thread-rotated connection (see CLAUDE.md ORM caveat).
    response = EmployeeResponse.model_validate(existing)
    response.teams = None  # endpoint does not expose multi-team
    db.commit()
    return response


@router.post("/recalc-active", response_model=RecalcActiveResponse)
def recalc_active(db: Session = Depends(get_db)):
    """Пересчитать is_active для всех сотрудников на основе worklog'ов
    на задачи с категориями «Активный стек» ∪ «Архив квартальных задач»."""
    from app.services.employee_service import EmployeeService

    stats = EmployeeService(db).recalc_active_by_categories()
    return RecalcActiveResponse(
        activated=stats.activated,
        deactivated=stats.deactivated,
        total_active=stats.total_active,
    )


class AutoDetectResponse(BaseModel):
    assigned: int
    skipped: int
    details: List[dict]


@router.post("/auto-detect-teams", response_model=AutoDetectResponse)
def auto_detect_teams(db: Session = Depends(get_db)):
    """Массово проставить Employee.team по ворклогам (для сотрудников с team=NULL)."""
    summary = EmployeeTeamService(db).auto_detect_all_missing()
    return AutoDetectResponse(
        assigned=summary.assigned,
        skipped=summary.skipped,
        details=summary.details,
    )


# ─── Partial update (role, …) ───


@router.patch("/{employee_id}", response_model=EmployeeResponse)
def patch_employee(
    employee_id: str,
    req: EmployeePatchRequest,
    db: Session = Depends(get_db),
):
    """Частично обновить поля сотрудника. Сейчас поддерживается `role`."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    data = req.model_dump(exclude_unset=True)
    if "role" in data:
        role = data["role"]
        if role is not None and role not in EMPLOYEE_ROLES:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown role {role!r}. Allowed: {list(EMPLOYEE_ROLES)}",
            )
        emp.role = role

    # Snapshot before commit — see CLAUDE.md ORM caveat.
    response = EmployeeResponse.model_validate(emp)
    response.teams = None
    db.commit()
    return response


# ─── Legacy single-team endpoint (deprecated, kept for compat) ───

class TeamUpdateRequest(BaseModel):
    team: Optional[str] = None


@router.put(
    "/{employee_id}/team",
    response_model=EmployeeResponse,
    deprecated=True,
    description="Deprecated — используйте /teams endpoints для multi-team",
)
def set_team_legacy(
    employee_id: str,
    req: TeamUpdateRequest,
    db: Session = Depends(get_db),
):
    """Заменяет все membership одной командой и делает её primary.
    Пустое значение = очистить все membership."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    svc = EmployeeTeamService(db)
    if req.team:
        svc.replace_teams(employee_id, [req.team], primary=req.team)
    else:
        svc.replace_teams(employee_id, [])
    db.refresh(emp)
    response = EmployeeResponse.model_validate(emp)
    response.teams = None  # legacy endpoint does not expose multi-team
    return response


# ─── New M:N team endpoints ───

class AddTeamRequest(BaseModel):
    team: str
    is_primary: bool = False


class ReplaceTeamsRequest(BaseModel):
    teams: List[str]
    primary: Optional[str] = None


class SetPrimaryRequest(BaseModel):
    team: str


@router.get("/{employee_id}/teams", response_model=List[EmployeeTeamItem])
def get_teams(employee_id: str, db: Session = Depends(get_db)):
    """Список команд сотрудника."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    rows = EmployeeTeamService(db).list_teams(employee_id)
    return [EmployeeTeamItem.model_validate(r) for r in rows]


@router.post("/{employee_id}/teams", response_model=EmployeeTeamItem)
def post_team(
    employee_id: str,
    req: AddTeamRequest,
    db: Session = Depends(get_db),
):
    """Добавить команду сотруднику."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    row = EmployeeTeamService(db).add_team(
        employee_id, req.team, is_primary=req.is_primary,
    )
    return EmployeeTeamItem.model_validate(row)


@router.put("/{employee_id}/teams/primary", response_model=List[EmployeeTeamItem])
def put_primary(
    employee_id: str,
    req: SetPrimaryRequest,
    db: Session = Depends(get_db),
):
    """Сменить primary-команду сотрудника."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    svc = EmployeeTeamService(db)
    try:
        svc.set_primary(employee_id, req.team)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Employee not in team {req.team!r}")
    rows = svc.list_teams(employee_id)
    return [EmployeeTeamItem.model_validate(r) for r in rows]


@router.put("/{employee_id}/teams", response_model=List[EmployeeTeamItem])
def put_teams(
    employee_id: str,
    req: ReplaceTeamsRequest,
    db: Session = Depends(get_db),
):
    """Заменить весь набор команд сотрудника."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    rows = EmployeeTeamService(db).replace_teams(
        employee_id, req.teams, primary=req.primary,
    )
    return [EmployeeTeamItem.model_validate(r) for r in rows]


@router.delete("/{employee_id}/teams/{team}", status_code=204)
def delete_team(
    employee_id: str,
    team: str,
    db: Session = Depends(get_db),
):
    """Удалить команду у сотрудника."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    EmployeeTeamService(db).remove_team(employee_id, team)
    return Response(status_code=204)
