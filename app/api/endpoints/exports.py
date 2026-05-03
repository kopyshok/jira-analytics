"""Export API endpoints.

Экспорт отчётов в xlsx / pdf / pptx. Все эндпоинты возвращают
`Response` с готовыми байтами и правильным `Content-Disposition`,
чтобы файл скачался по клику в UI или Swagger.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PlanningScenario
from app.services.export_service import ExportService


router = APIRouter()


XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
PDF_MIME = "application/pdf"
PPTX_MIME = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


def _attachment_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


# === Capacity ===

@router.get(
    "/capacity.xlsx",
    responses={200: {"content": {XLSX_MIME: {}}}},
)
async def export_capacity_xlsx(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
) -> Response:
    """Capacity квартала в xlsx, группировка по командам."""
    blob = ExportService(db).export_capacity_xlsx(year, quarter)
    return Response(
        content=blob,
        media_type=XLSX_MIME,
        headers=_attachment_headers(f"capacity_Q{quarter}_{year}.xlsx"),
    )


# === Planning scenarios ===

@router.get(
    "/scenarios/{scenario_id}.xlsx",
    responses={200: {"content": {XLSX_MIME: {}}}},
)
async def export_scenario_xlsx(
    scenario_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Скачать xlsx со сводкой и раскладкой сценария."""
    service = ExportService(db)
    try:
        data = service.build_scenario_xlsx(scenario_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    scenario = db.get(PlanningScenario, scenario_id)
    slug = "".join(
        c if c.isalnum() else "-" for c in (scenario.name or "scenario")
    ).lower().strip("-")[:40]
    fn = (
        f"scenario_{scenario.quarter or 'Q'}"
        f"_{scenario.year or 'YYYY'}"
        f"_{slug}"
        f"_{datetime.utcnow():%Y-%m-%d}.xlsx"
    )
    return Response(content=data, media_type=XLSX_MIME, headers=_attachment_headers(fn))


@router.get(
    "/scenarios/{scenario_id}.pptx",
    responses={200: {"content": {PPTX_MIME: {}}}},
)
async def export_scenario_pptx(
    scenario_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Скачать презентацию со сводкой сценария."""
    service = ExportService(db)
    try:
        data = service.build_scenario_pptx(scenario_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=data,
        media_type=PPTX_MIME,
        headers=_attachment_headers(f"scenario-{scenario_id}.pptx"),
    )
