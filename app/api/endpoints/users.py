from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import AppearanceSettings

router = APIRouter()


class PeriodPayload(BaseModel):
    year: int | None = None
    quarter: int | None = None
    month: int | None = None


class ColumnsPayload(BaseModel):
    columns: list[str]


class ThemePayload(BaseModel):
    theme: str


@router.get("/me/period")
def get_my_period(current_user: User = Depends(get_current_user)):
    return current_user.selected_period


@router.put("/me/period")
def set_my_period(
    payload: PeriodPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.selected_period = payload.model_dump(exclude_none=True)
    db.commit()
    return {"ok": True}


@router.get("/me/analytics-columns")
def get_my_columns(current_user: User = Depends(get_current_user)):
    return {"columns": current_user.analytics_columns}


@router.put("/me/analytics-columns")
def set_my_columns(
    payload: ColumnsPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.analytics_columns = payload.columns
    db.commit()
    return {"ok": True}


# В продукте остались только две темы Aurora. Прежние значения приходить
# больше не должны; фронт сводит их к «aurora-dark» при входе.
VALID_THEMES = {
    "aurora-dark",
    "aurora-light",
}


@router.get("/me/theme")
def get_my_theme(current_user: User = Depends(get_current_user)):
    return {"theme": current_user.selected_theme}


@router.put("/me/theme")
def set_my_theme(
    payload: ThemePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.theme not in VALID_THEMES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Неизвестная тема: {payload.theme}")
    current_user.selected_theme = payload.theme
    db.commit()
    return {"ok": True, "theme": payload.theme}


_DEFAULT_APPEARANCE = AppearanceSettings()


@router.get("/me/appearance", response_model=AppearanceSettings)
def get_my_appearance(current_user: User = Depends(get_current_user)):
    """Возвращает пользовательские настройки внешнего вида планировщика."""
    stored = current_user.appearance_settings
    if not stored:
        return _DEFAULT_APPEARANCE
    return AppearanceSettings(**{**_DEFAULT_APPEARANCE.model_dump(), **stored})


@router.put("/me/appearance", response_model=AppearanceSettings)
def set_my_appearance(
    payload: AppearanceSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сохраняет настройки внешнего вида планировщика для текущего пользователя."""
    current_user.appearance_settings = payload.model_dump()
    db.commit()
    return payload


class TeamDeskFilterPayload(BaseModel):
    """Шапка рабочего стола тимлида целиком: состав, режим среза, переключатели.

    Тимлид настроил вид один раз — при следующем заходе он должен увидеть тот же
    экран, и с любого компьютера. Поэтому не localStorage, а профиль.
    """

    teams: list[str] = []
    developers: list[str] = []
    mode: Literal["open", "period", "all"] = "open"
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    show_reviewed: bool = False
    show_done_subtasks: bool = True


@router.get("/me/team-desk-filter", response_model=TeamDeskFilterPayload)
def get_my_team_desk_filter(current_user: User = Depends(get_current_user)):
    return TeamDeskFilterPayload(**current_user.team_desk_filter)


@router.put("/me/team-desk-filter", response_model=TeamDeskFilterPayload)
def set_my_team_desk_filter(
    payload: TeamDeskFilterPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # mode="json" — даты в хранилище должны лечь строками.
    current_user.team_desk_filter = payload.model_dump(mode="json")
    db.commit()
    return payload


class AnalyticsLayoutPayload(BaseModel):
    layout: dict


@router.get("/me/analytics-layout")
def get_my_analytics_layout(current_user: User = Depends(get_current_user)):
    return {"layout": current_user.analytics_layout}


@router.put("/me/analytics-layout")
def set_my_analytics_layout(
    payload: AnalyticsLayoutPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.analytics_layout = payload.layout
    db.commit()
    return {"ok": True}
