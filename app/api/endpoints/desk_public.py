"""Публичный endpoint рабочего стола аналитика — доступ по токену, без авторизации."""

from datetime import date, datetime

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.work_desk import WorkDesk
from app.schemas.work_desk import DeskEmployee, DeskMeta, DeskPeriod, DeskSummary
from app.services.work_desk_service import WorkDeskService
from app.services.work_desk_widgets import WIDGET_KEYS, desk_summary, dispatch

router = APIRouter()


def _current_period() -> tuple[int, int]:
    """Текущий (год, квартал) — единый источник для meta и виджетов."""
    today = date.today()
    return today.year, (today.month - 1) // 3 + 1


# Насколько далеко от текущего квартала можно листать стол.
MAX_QUARTER_SHIFT = 4


def resolve_period(
    year: Optional[int] = Query(None, ge=2000, le=2100, description="Год квартала"),
    quarter: Optional[int] = Query(None, ge=1, le=4, description="Квартал 1..4"),
) -> tuple[int, int]:
    """Квартал стола: без параметров — текущий; иначе не дальше ±4 кварталов от сегодня.

    Год и квартал задаются только вместе (одно без другого неоднозначно) — иначе 422.
    """
    cur_year, cur_quarter = _current_period()
    if year is None and quarter is None:
        return cur_year, cur_quarter
    if year is None or quarter is None:
        raise HTTPException(status_code=422, detail="Укажите год и квартал вместе")
    shift = (year * 4 + quarter) - (cur_year * 4 + cur_quarter)
    if abs(shift) > MAX_QUARTER_SHIFT:
        raise HTTPException(
            status_code=422,
            detail=f"Квартал не дальше {MAX_QUARTER_SHIFT} кварталов от текущего",
        )
    return year, quarter


def get_desk_by_token(token: str, db: Session = Depends(get_db)) -> WorkDesk:
    desk = WorkDeskService().get_by_token(db, token)
    if desk is None:
        raise HTTPException(status_code=404, detail="Стол не найден")
    return desk


@router.get("/{token}", response_model=DeskMeta)
def get_desk_meta(
    desk: WorkDesk = Depends(get_desk_by_token),
    db: Session = Depends(get_db),
    period_ym: tuple[int, int] = Depends(resolve_period),
) -> DeskMeta:
    """Метаданные стола: сотрудник, команды, виджеты, выбранный (по умолчанию текущий) период."""
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

    year, quarter = period_ym
    period = DeskPeriod(year=year, quarter=quarter)

    # Считаем до commit — после commit сессия expire-ит атрибуты desk/employee.
    summary = DeskSummary(**desk_summary(db, desk, year, quarter))

    desk.last_viewed_at = datetime.utcnow()
    db.commit()

    return DeskMeta(
        employee=emp_meta,
        teams=teams,
        enabled_widgets=enabled_widgets,
        period=period,
        summary=summary,
    )


@router.get("/{token}/widget/{key}")
def get_desk_widget(
    key: str,
    desk: WorkDesk = Depends(get_desk_by_token),
    db: Session = Depends(get_db),
    period_ym: tuple[int, int] = Depends(resolve_period),
) -> dict:
    """Данные одного виджета стола. Публичный доступ по токену."""
    if key not in WIDGET_KEYS:
        raise HTTPException(status_code=404, detail="Неизвестный виджет")
    if key not in desk.enabled_widgets:
        raise HTTPException(status_code=403, detail="Виджет выключен")
    year, quarter = period_ym
    return dispatch(db, desk, key, year, quarter)
