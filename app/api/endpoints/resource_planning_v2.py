"""Resource Planning v2 endpoints — solver optimize + quality metric."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.resource_planning_v2 import OptimizeResponse, QualityMetricSchema
from app.services.plan_quality_service import PlanQualityService

router = APIRouter()


@router.get("/{plan_id}/quality", response_model=QualityMetricSchema)
def get_plan_quality(plan_id: str, db: Session = Depends(get_db)) -> QualityMetricSchema:
    """Метрика качества плана: % перегрузок, просрочки, использование ёмкости."""
    try:
        metric = PlanQualityService(db).compute(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return QualityMetricSchema(
        plan_id=metric["plan_id"],
        overload_days_pct=metric["overload_days_pct"],
        late_count=metric["late_count"],
        mean_utilization_pct=metric["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )


@router.post("/{plan_id}/optimize", response_model=OptimizeResponse)
def optimize_plan(plan_id: str, db: Session = Depends(get_db)) -> OptimizeResponse:
    """PyJobShop-оптимизация: создаёт форк плана с новыми ассайнами + датами.

    Реализация в Task 8.
    """
    raise HTTPException(status_code=501, detail="Not implemented yet")
