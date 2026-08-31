"""Teams API endpoint.

Плоский список команд (`GET /teams`) — быстрый источник для глобального
фильтра в шапке, собирается из `Issue.team` и `EmployeeTeam.team`.

Реестр (`GET /teams/registry`) добавляет к именам настройки: признак деления
на группы и сами группы. Имя команды остаётся ключом — строковые поля в
задачах, участии сотрудников, сценариях и планах не меняются.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmployeeTeam, Issue, Team
from app.schemas.team import (
    EmployeeSubgroupIn,
    SubgroupIn,
    SubgroupOut,
    TeamOut,
    TeamPatch,
)
from app.services.team_registry_service import TeamRegistryService


router = APIRouter()


@router.get("", response_model=List[str])
def list_teams(db: Session = Depends(get_db)) -> List[str]:
    """Уникальные имена команд из локальной БД (issues + employee memberships)."""
    issue_rows = db.query(Issue.team).filter(Issue.team.isnot(None)).distinct().all()
    membership_rows = db.query(EmployeeTeam.team).distinct().all()

    merged: set[str] = set()
    for (value,) in issue_rows + membership_rows:
        if value:
            merged.add(value)

    return sorted(merged)


def _to_out(team: Team) -> TeamOut:
    return TeamOut(
        name=team.name,
        has_subgroups=team.has_subgroups,
        subgroups=[SubgroupOut.model_validate(g) for g in team.subgroups],
    )


@router.get("/registry", response_model=List[TeamOut])
def list_registry(db: Session = Depends(get_db)) -> List[TeamOut]:
    """Реестр команд. Перед выдачей подтягивает имена, появившиеся в данных."""
    TeamRegistryService(db).sync_names()
    return [_to_out(t) for t in db.query(Team).order_by(Team.name).all()]


@router.patch("/registry/{name}", response_model=TeamOut)
def patch_registry(name: str, data: TeamPatch, db: Session = Depends(get_db)) -> TeamOut:
    """Включить или выключить деление команды на группы."""
    return _to_out(TeamRegistryService(db).set_has_subgroups(name, data.has_subgroups))


@router.post("/registry/{name}/subgroups", response_model=SubgroupOut, status_code=201)
def create_subgroup(
    name: str, data: SubgroupIn, db: Session = Depends(get_db)
) -> SubgroupOut:
    try:
        group = TeamRegistryService(db).add_subgroup(name, data.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return SubgroupOut.model_validate(group)


@router.patch("/subgroups/{subgroup_id}", response_model=SubgroupOut)
def rename_subgroup(
    subgroup_id: str, data: SubgroupIn, db: Session = Depends(get_db)
) -> SubgroupOut:
    return SubgroupOut.model_validate(
        TeamRegistryService(db).rename_subgroup(subgroup_id, data.name)
    )


@router.delete("/subgroups/{subgroup_id}", status_code=204)
def delete_subgroup(subgroup_id: str, db: Session = Depends(get_db)) -> None:
    """Удалить группу. Приписки сотрудников и задач обнуляются каскадом."""
    TeamRegistryService(db).delete_subgroup(subgroup_id)


@router.put("/employees/{employee_id}/subgroup", status_code=204)
def set_employee_subgroup(
    employee_id: str, data: EmployeeSubgroupIn, db: Session = Depends(get_db)
) -> None:
    """Приписать сотрудника к группе внутри команды."""
    TeamRegistryService(db).assign_employee(employee_id, data.team, data.subgroup_id)
