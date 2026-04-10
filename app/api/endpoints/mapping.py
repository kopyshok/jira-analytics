"""Mapping API endpoints.

Управление категоризацией: пересчёт category_mappings
на основе правил резолвинга.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.mapping_service import MappingService


router = APIRouter()


class MappingResponse(BaseModel):
    status: str
    message: str
    stats: dict


@router.post("/recalculate", response_model=MappingResponse)
async def recalculate_mappings(db: Session = Depends(get_db)):
    """Пересчитать категории для всех задач и worklog.

    Применяет правила резолвинга (override → scope_root → quality → fallback)
    и обновляет таблицу category_mappings и поле Issue.category.
    """
    try:
        service = MappingService(db)
        stats = service.recalculate_all()

        return MappingResponse(
            status="completed",
            message=f"Mapping recalculated in {stats.duration_seconds:.1f}s",
            stats=stats.to_dict(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recalculate/issues", response_model=MappingResponse)
async def recalculate_issue_mappings(db: Session = Depends(get_db)):
    """Пересчитать категории только для задач (без worklog)."""
    try:
        service = MappingService(db)
        service.recalculate_issues()
        service.stats.finish()

        return MappingResponse(
            status="completed",
            message="Issue mappings recalculated",
            stats=service.stats.to_dict(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recalculate/worklogs", response_model=MappingResponse)
async def recalculate_worklog_mappings(db: Session = Depends(get_db)):
    """Пересчитать категории только для worklog."""
    try:
        service = MappingService(db)
        service.recalculate_worklogs()
        service.stats.finish()

        return MappingResponse(
            status="completed",
            message="Worklog mappings recalculated",
            stats=service.stats.to_dict(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
