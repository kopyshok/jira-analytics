"""Управление рабочими столами аналитиков — выпуск/отзыв/перевыпуск токенов.

Скоупинг по командам пользователя (`selected_teams`): менеджер управляет
столами только тех сотрудников, что входят в его выбранные команды. Пустой
выбор команд = доступ ко всем командам (та же логика, что у глобального
фильтра команд — пустой список означает «без фильтра»).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.user import User
from app.models.work_desk import WorkDesk
from app.schemas.work_desk import (
    DeskEmployee,
    WorkDeskCreate,
    WorkDeskCreated,
    WorkDeskListItem,
    WorkDeskWidgetsUpdate,
)
from app.services.work_desk_service import WorkDeskService

router = APIRouter()

# NOTE: валидация enabled_widgets против разрешённых ключей виджетов появится
# в Phase 3 (app/services/work_desk_widgets.py с WIDGET_KEYS). Пока принимаем
# любой list[str].


def _employee_in_user_teams(db: Session, user: User, employee_id: str) -> bool:
    """Состоит ли сотрудник хотя бы в одной из команд пользователя.

    Пустой `selected_teams` = доступ ко всем командам.
    """
    teams = user.selected_teams
    if not teams:
        return db.get(Employee, employee_id) is not None
    row = db.execute(
        select(EmployeeTeam.id).where(
            EmployeeTeam.employee_id == employee_id,
            EmployeeTeam.team.in_(teams),
        )
    ).first()
    return row is not None


def _assert_employee_in_user_teams(db: Session, user: User, employee_id: str) -> None:
    if not _employee_in_user_teams(db, user, employee_id):
        raise HTTPException(status_code=403, detail="Сотрудник вне ваших команд")


def _created_payload(desk: WorkDesk) -> WorkDeskCreated:
    # Снимок полей до возможного expire (ORM caveat).
    return WorkDeskCreated(
        id=desk.id,
        token=desk.token,
        employee_id=desk.employee_id,
        enabled_widgets=desk.enabled_widgets,
    )


@router.get("", response_model=list[WorkDeskListItem])
def list_desks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkDeskListItem]:
    """Активные столы сотрудников из команд пользователя."""
    teams = user.selected_teams
    stmt = (
        select(WorkDesk)
        .join(Employee, Employee.id == WorkDesk.employee_id)
        .where(WorkDesk.revoked_at.is_(None))
    )
    if teams:
        stmt = stmt.join(
            EmployeeTeam, EmployeeTeam.employee_id == Employee.id
        ).where(EmployeeTeam.team.in_(teams)).distinct()
    desks = db.execute(stmt).scalars().unique().all()

    items: list[WorkDeskListItem] = []
    for desk in desks:
        emp = desk.employee
        items.append(
            WorkDeskListItem(
                id=desk.id,
                employee=DeskEmployee(
                    id=emp.id,
                    display_name=emp.display_name,
                    avatar_url=emp.avatar_url,
                ),
                status="active",
                token=desk.token,
                enabled_widgets=desk.enabled_widgets,
                desk_url_path=f"/desk/{desk.token}",
            )
        )
    return items


@router.post("", response_model=WorkDeskCreated, status_code=201)
def create_desk(
    payload: WorkDeskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkDeskCreated:
    """Выпустить новый стол для сотрудника (отзывает предыдущий активный)."""
    _assert_employee_in_user_teams(db, user, payload.employee_id)
    desk = WorkDeskService().create(
        db, payload.employee_id, payload.enabled_widgets, user.id
    )
    return _created_payload(desk)


@router.patch("/{desk_id}", response_model=WorkDeskCreated)
def update_widgets(
    desk_id: str,
    payload: WorkDeskWidgetsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkDeskCreated:
    """Обновить набор виджетов стола."""
    desk = db.get(WorkDesk, desk_id)
    if desk is None:
        raise HTTPException(status_code=404, detail="Стол не найден")
    _assert_employee_in_user_teams(db, user, desk.employee_id)
    desk = WorkDeskService().set_widgets(db, desk_id, payload.enabled_widgets)
    return _created_payload(desk)


@router.post("/{desk_id}/revoke", status_code=200)
def revoke_desk(
    desk_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Отозвать стол."""
    desk = db.get(WorkDesk, desk_id)
    if desk is None:
        raise HTTPException(status_code=404, detail="Стол не найден")
    _assert_employee_in_user_teams(db, user, desk.employee_id)
    WorkDeskService().revoke(db, desk_id)
    return {"status": "revoked"}


@router.post("/{desk_id}/regenerate", response_model=WorkDeskCreated)
def regenerate_desk(
    desk_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkDeskCreated:
    """Перевыпустить токен стола (старая ссылка перестаёт работать)."""
    desk = db.get(WorkDesk, desk_id)
    if desk is None:
        raise HTTPException(status_code=404, detail="Стол не найден")
    _assert_employee_in_user_teams(db, user, desk.employee_id)
    new_desk = WorkDeskService().regenerate(db, desk_id)
    return _created_payload(new_desk)
