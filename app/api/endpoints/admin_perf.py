"""Быстродействие сервиса — только для администратора.

Собственные эндпоинты раздела в замеры не попадают (см. `app/core/perf_middleware.py`).
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.services.perf_report import overview, render_markdown, render_xlsx, snapshots_for

router = APIRouter()

Period = Literal["1h", "24h", "7d", "30d"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#: Сколько медленных запросов брать в выгрузки (на экране — 200 последних).
EXPORT_SLOW_LIMIT = 1000

# Сдвиг местного времени от UTC в минутах — браузер знает пояс, сервер нет.
TzOffset = Query(0, ge=-720, le=840)


def _overview(db: Session, period: str, slow_limit: int) -> dict:
    s = get_settings()
    return overview(
        db, period, slow_ms=s.perf_slow_ms, flush_seconds=s.perf_flush_seconds,
        slow_limit=slow_limit,
    )


def _attachment(period: str, ext: str) -> dict[str, str]:
    # Имя файла — только ASCII: кириллица в Content-Disposition ломает часть браузеров.
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    return {"Content-Disposition": f'attachment; filename="perf_{period}_{stamp}.{ext}"'}


@router.get("/overview")
def get_overview(period: Period = Query("24h"), db: Session = Depends(get_db)) -> dict:
    """Итог, ряд для графика, узкие места и медленные запросы за период."""
    return _overview(db, period, slow_limit=200)


@router.get("/report.md")
def get_report(
    period: Period = Query("24h"),
    tz_offset_min: int = TzOffset,
    db: Session = Depends(get_db),
) -> Response:
    """Отчёт для разработки в формате Markdown."""
    text = render_markdown(_overview(db, period, EXPORT_SLOW_LIMIT), tz_offset_min=tz_offset_min)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers=_attachment(period, "md"),
    )


@router.get("/export.xlsx", responses={200: {"content": {XLSX_MIME: {}}}})
def get_xlsx(
    period: Period = Query("24h"),
    tz_offset_min: int = TzOffset,
    db: Session = Depends(get_db),
) -> Response:
    """Excel: узкие места, медленные запросы, снимки сервера."""
    blob = render_xlsx(
        _overview(db, period, EXPORT_SLOW_LIMIT), snapshots_for(db, period),
        tz_offset_min=tz_offset_min,
    )
    return Response(content=blob, media_type=XLSX_MIME, headers=_attachment(period, "xlsx"))
