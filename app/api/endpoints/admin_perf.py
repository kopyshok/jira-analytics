"""Быстродействие сервиса — только для администратора.

Собственные эндпоинты раздела в замеры не попадают (см. `app/core/perf_middleware.py`).
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.services.perf_report import overview

router = APIRouter()

Period = Literal["1h", "24h", "7d", "30d"]


@router.get("/overview")
def get_overview(
    period: Period = Query("24h"),
    db: Session = Depends(get_db),
) -> dict:
    """Итог, ряд для графика, узкие места и медленные запросы за период."""
    settings = get_settings()
    return overview(
        db, period, slow_ms=settings.perf_slow_ms, flush_seconds=settings.perf_flush_seconds,
    )
