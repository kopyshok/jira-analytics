"""Публичный endpoint рабочего стола аналитика — доступ по токену, без авторизации."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.work_desk import WorkDesk
from app.schemas.work_desk import DeskEmployee, DeskMeta, DeskPeriod
from app.services.work_desk_service import WorkDeskService
from app.services.work_desk_widgets import WIDGET_KEYS, dispatch

router = APIRouter()


def _current_period() -> tuple[int, int]:
    """Текущий (год, квартал) — единый источник для meta и виджетов."""
    today = date.today()
    return today.year, (today.month - 1) // 3 + 1


def get_desk_by_token(token: str, db: Session = Depends(get_db)) -> WorkDesk:
    desk = WorkDeskService().get_by_token(db, token)
    if desk is None:
        raise HTTPException(status_code=404, detail="Стол не найден")
    return desk


@router.get("/{token}", response_model=DeskMeta)
def get_desk_meta(
    desk: WorkDesk = Depends(get_desk_by_token),
    db: Session = Depends(get_db),
) -> DeskMeta:
    """Метаданные стола: сотрудник, команды, виджеты, текущий период."""
    employee = desk.employee
    # Снимок полей до commit — после commit сессия expire-ит атрибуты
    # (ORM caveat: reload на потенциально другом соединении → DetachedInstanceError).
    emp_meta = DeskEmployee(
        id=employee.id,
        display_name=employee.display_name,
        avatar_url=employee.avatar_url,
    )
    teams = [t.team for t in employee.teams]
    enabled_widgets = desk.enabled_widgets

    year, quarter = _current_period()
    period = DeskPeriod(year=year, quarter=quarter)

    desk.last_viewed_at = datetime.utcnow()
    db.commit()

    return DeskMeta(
        employee=emp_meta,
        teams=teams,
        enabled_widgets=enabled_widgets,
        period=period,
    )


@router.get("/{token}/widget/{key}")
def get_desk_widget(
    key: str,
    desk: WorkDesk = Depends(get_desk_by_token),
    db: Session = Depends(get_db),
) -> dict:
    """Данные одного виджета стола. Публичный доступ по токену."""
    if key not in WIDGET_KEYS:
        raise HTTPException(status_code=404, detail="Неизвестный виджет")
    if key not in desk.enabled_widgets:
        raise HTTPException(status_code=403, detail="Виджет выключен")
    year, quarter = _current_period()
    return dispatch(db, desk, key, year, quarter)
