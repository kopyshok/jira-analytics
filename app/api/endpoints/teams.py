"""Teams API endpoint.

Плоский список команд (`GET /teams`) — быстрый источник для глобального
фильтра в шапке, собирается из `Issue.team` и `EmployeeTeam.team`.

Реестр (`GET /teams/registry`) добавляет к именам настройки: признак деления
на группы и сами группы. Имя команды остаётся ключом — строковые поля в
задачах, участии сотрудников, сценариях и планах не меняются.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth_deps import require_admin
from app.database import get_db
from app.models import EmployeeTeam, Issue, Team
from app.schemas.team import (
    EmployeeSubgroupIn,
    SubgroupIn,
    SubgroupOut,
    SubgroupShareItem,
    SubgroupShareRecordIn,
    SubgroupShareRecordOut,
    TeamOut,
    TeamPatch,
)
from app.services import subgroup_shares as ss
from app.services.subgroup_share_service import SubgroupShareService
from app.services.team_registry_service import TeamRegistryService


router = APIRouter()

# Правка реестра команд и групп — административная операция: экран живёт
# в разделе администратора, а удаление группы снимает её с сотрудников и задач.
_admin_only = [Depends(require_admin)]


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


@router.patch("/registry/{name}", response_model=TeamOut, dependencies=_admin_only)
def patch_registry(name: str, data: TeamPatch, db: Session = Depends(get_db)) -> TeamOut:
    """Включить или выключить деление команды на группы."""
    return _to_out(TeamRegistryService(db).set_has_subgroups(name, data.has_subgroups))


@router.post(
    "/registry/{name}/subgroups",
    response_model=SubgroupOut,
    status_code=201,
    dependencies=_admin_only,
)
def create_subgroup(
    name: str, data: SubgroupIn, db: Session = Depends(get_db)
) -> SubgroupOut:
    try:
        group = TeamRegistryService(db).add_subgroup(name, data.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return SubgroupOut.model_validate(group)


@router.patch(
    "/subgroups/{subgroup_id}", response_model=SubgroupOut, dependencies=_admin_only
)
def rename_subgroup(
    subgroup_id: str, data: SubgroupIn, db: Session = Depends(get_db)
) -> SubgroupOut:
    return SubgroupOut.model_validate(
        TeamRegistryService(db).rename_subgroup(subgroup_id, data.name)
    )


@router.delete("/subgroups/{subgroup_id}", status_code=204, dependencies=_admin_only)
def delete_subgroup(subgroup_id: str, db: Session = Depends(get_db)) -> None:
    """Удалить группу. Приписки сотрудников и задач обнуляются каскадом."""
    TeamRegistryService(db).delete_subgroup(subgroup_id)


@router.put("/employees/{employee_id}/subgroup", status_code=204)
def set_employee_subgroup(
    employee_id: str, data: EmployeeSubgroupIn, db: Session = Depends(get_db)
) -> None:
    """Приписать сотрудника к группе внутри команды."""
    try:
        TeamRegistryService(db).assign_employee(employee_id, data.team, data.subgroup_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _records_out(records: ss.Records) -> List[SubgroupShareRecordOut]:
    return [
        SubgroupShareRecordOut(
            valid_from=r.valid_from,
            shares=[SubgroupShareItem(subgroup_id=g, percent=p) for g, p in r.shares],
        )
        for r in records
    ]


@router.get(
    "/employees/{employee_id}/subgroup-shares",
    response_model=List[SubgroupShareRecordOut],
)
def get_subgroup_shares(
    employee_id: str, team: str = Query(...), db: Session = Depends(get_db)
) -> List[SubgroupShareRecordOut]:
    """История распределения сотрудника по группам команды."""
    return _records_out(SubgroupShareService(db).history(employee_id, team))


@router.put(
    "/employees/{employee_id}/subgroup-shares",
    response_model=List[SubgroupShareRecordOut],
)
def put_subgroup_shares(
    employee_id: str, data: SubgroupShareRecordIn, db: Session = Depends(get_db)
) -> List[SubgroupShareRecordOut]:
    """Перевод или деление с даты. Запись с той же датой заменяется."""
    if len({s.subgroup_id for s in data.shares}) != len(data.shares):
        raise HTTPException(status_code=422, detail="Группа указана дважды")
    try:
        records = SubgroupShareService(db).set_record(
            employee_id,
            data.team,
            data.valid_from,
            {s.subgroup_id: s.percent for s in data.shares},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _records_out(records)


@router.delete(
    "/employees/{employee_id}/subgroup-shares",
    response_model=List[SubgroupShareRecordOut],
)
def delete_subgroup_share(
    employee_id: str,
    team: str = Query(...),
    valid_from: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> List[SubgroupShareRecordOut]:
    """Удалить ошибочную запись. Без даты — базовую «с начала участия»."""
    try:
        records = SubgroupShareService(db).delete_record(employee_id, team, valid_from)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _records_out(records)
