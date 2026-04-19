"""Export API endpoints.

Экспорт отчётов в xlsx / pdf / pptx. Все эндпоинты возвращают
`Response` с готовыми байтами и правильным `Content-Disposition`,
чтобы файл скачался по клику в UI или Swagger.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.analytics_service import NO_TEAM_TOKEN, parse_teams_csv
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


# === Analytics ===

@router.get(
    "/analytics.xlsx",
    responses={200: {"content": {XLSX_MIME: {}}}},
)
async def export_analytics_xlsx(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    teams: Optional[str] = Query(
        None, description=f"Команды CSV, {NO_TEAM_TOKEN} = без команды"
    ),
    match_employees: bool = Query(True, description="Фильтр по команде сотрудника"),
    match_issues: bool = Query(True, description="Фильтр по команде задачи"),
    db: Session = Depends(get_db),
) -> Response:
    """Скачать xlsx с аналитическими отчётами за период."""
    service = ExportService(db)
    teams_list = parse_teams_csv(teams)
    data = service.build_analytics_xlsx(
        start=start,
        end=end,
        teams=teams_list,
        match_employees=match_employees,
        match_issues=match_issues,
    )
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers=_attachment_headers("analytics.xlsx"),
    )


@router.get(
    "/analytics.pdf",
    responses={200: {"content": {PDF_MIME: {}}}},
)
async def export_analytics_pdf(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    teams: Optional[str] = Query(
        None, description=f"Команды CSV, {NO_TEAM_TOKEN} = без команды"
    ),
    match_employees: bool = Query(True, description="Фильтр по команде сотрудника"),
    match_issues: bool = Query(True, description="Фильтр по команде задачи"),
    db: Session = Depends(get_db),
) -> Response:
    """Скачать PDF-отчёт с аналитикой за период."""
    service = ExportService(db)
    teams_list = parse_teams_csv(teams)
    data = service.build_analytics_pdf(
        start=start,
        end=end,
        teams=teams_list,
        match_employees=match_employees,
        match_issues=match_issues,
    )
    return Response(
        content=data,
        media_type=PDF_MIME,
        headers=_attachment_headers("analytics.pdf"),
    )


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
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers=_attachment_headers(f"scenario-{scenario_id}.xlsx"),
    )


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
