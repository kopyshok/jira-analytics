"""Рабочий стол тимлида: срез задач, настройки раздела, отметки «просмотрено»."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models import Employee, User
from app.schemas.team_desk import DeskSettings, MarkRequest
from app.services.team_desk.config import DeskConfig, load_config, save_config
from app.services.team_desk.flags import FLAG_LABELS, FLAG_ORDER
from app.services.team_desk.marks import mark_reviewed, unmark
from app.services.team_desk.query import build_overview
from app.services.team_desk.workload import queue_for_developers
from app.services.team_membership import members_on

router = APIRouter()


def _split(raw: Optional[str]) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Пороги подсветки, группы статусов и типы задач раздела."""
    return load_config(db).to_dict()


@router.put("/settings")
def put_settings(
    payload: DeskSettings,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Сохранить настройки раздела целиком."""
    save_config(
        db,
        DeskConfig(
            status_groups=payload.status_groups,
            queue_statuses=payload.queue_statuses,
            hidden_statuses=payload.hidden_statuses,
            thresholds=payload.thresholds,
            subtask_types=payload.subtask_types,
            assignee_types=payload.assignee_types,
            developer_roles=payload.developer_roles,
        ),
    )
    return load_config(db).to_dict()


@router.get("/flags")
def get_flag_dictionary(_: User = Depends(get_current_user)):
    """Справочник признаков — подписи для интерфейса."""
    return [{"code": code, "label": FLAG_LABELS[code]} for code in FLAG_ORDER]


@router.get("/overview")
def get_overview(
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    developers: Optional[str] = Query(None, description="Учётные записи через запятую"),
    only_open: bool = Query(True),
    show_reviewed: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Задачи, сводка по разработчикам, очередь работы и счётчики признаков."""
    cfg = load_config(db)
    team_list = _split(teams)
    account_ids = set(_split(developers))

    # Раздел — про разработчиков: аналитики, РП и консультанты в срез не идут,
    # даже если задача назначена на них.
    def _developers_only(query):
        if cfg.developer_roles:
            query = query.filter(Employee.role.in_(cfg.developer_roles))
        return query

    employees: list[Employee] = []
    if team_list:
        # Состав команды на сегодня — только через team_membership, иначе
        # выбывшие попадут в расчёт задним числом.
        member_ids = members_on(db, team_list, date.today())
        if member_ids:
            employees = _developers_only(
                db.query(Employee).filter(Employee.id.in_(member_ids))
            ).all()
            account_ids.update(e.jira_account_id for e in employees if e.jira_account_id)

    known_accounts = {e.jira_account_id for e in employees if e.jira_account_id}
    missing = account_ids - known_accounts
    if missing:
        employees += _developers_only(
            db.query(Employee).filter(Employee.jira_account_id.in_(missing))
        ).all()
    account_ids &= {e.jira_account_id for e in employees if e.jira_account_id}

    employee_by_account = {e.jira_account_id: e.id for e in employees if e.jira_account_id}

    result = build_overview(
        db,
        developer_ids=sorted(account_ids),
        only_open=only_open,
        show_reviewed=show_reviewed,
    )
    result["workload"] = queue_for_developers(
        db,
        [
            {
                "developer_id": row["developer_id"],
                "status": row["status"],
                "est_hours": row["est_hours"],
            }
            for row in result["issues"]
        ],
        employee_by_account=employee_by_account,
        start=date.today(),
        days=7,
    )
    result["employee_ids"] = employee_by_account

    # Команда человека — подпись под именем в сводке. Тот, кого добрали
    # точечно поверх команд, помечается отдельно.
    picked = set(_split(developers))
    team_by_account = {
        e.jira_account_id: ("добран точечно" if e.jira_account_id in picked else e.team)
        for e in employees
        if e.jira_account_id
    }
    for row in result["developers"]:
        row["team"] = team_by_account.get(row["developer_id"])
    return result


@router.post("/issues/{issue_id}/mark")
def post_mark(
    issue_id: str,
    payload: MarkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отметить признак просмотренным — он перестаёт считаться проблемой."""
    if payload.flag not in FLAG_ORDER:
        raise HTTPException(status_code=422, detail="Неизвестный признак")
    row = mark_reviewed(
        db, issue_id, payload.flag, payload.signature, payload.comment, user.id
    )
    marked_at = row.marked_at.isoformat()
    return {"issue_id": issue_id, "flag": payload.flag, "marked_at": marked_at}


@router.delete("/issues/{issue_id}/mark")
def delete_mark(
    issue_id: str,
    flag: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Снять отметку — признак снова считается проблемным."""
    unmark(db, issue_id, flag)
    return {"issue_id": issue_id, "flag": flag}
