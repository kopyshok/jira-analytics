"""Export API endpoints.

Экспорт отчётов в xlsx / pdf / pptx. Все эндпоинты возвращают
`Response` с готовыми байтами и правильным `Content-Disposition`,
чтобы файл скачался по клику в UI или Swagger.
"""

import re
from urllib.parse import quote

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
    # Заголовки HTTP — только latin-1: русское имя сценария роняло ответ в 500.
    # ASCII-запасное имя + полное UTF-8 имя по RFC 5987.
    fallback = filename.encode("ascii", "replace").decode().replace("?", "_")
    return {
        "Content-Disposition": (
            f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename)}'
        )
    }


_BAD_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def scenario_file_name(name: str | None, ext: str) -> str:
    """Имя файла выгрузки сценария: название сценария без символов,
    недопустимых в именах файлов Windows; не длиннее 150 знаков."""
    clean = _BAD_FILENAME_CHARS.sub("_", name or "")
    clean = clean.strip(" ")[:150].strip(" ").rstrip(". ")
    return f"{clean or 'scenario'}.{ext}"


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
    fn = scenario_file_name(scenario.name if scenario else None, "xlsx")
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
    scenario = db.get(PlanningScenario, scenario_id)
    fn = scenario_file_name(scenario.name if scenario else None, "pptx")
    return Response(
        content=data,
        media_type=PPTX_MIME,
        headers=_attachment_headers(fn),
    )
