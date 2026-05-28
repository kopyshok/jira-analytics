"""Client-facing endpoint для записи usage-событий."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.usage import UsageBatchResult, UsageEventBatchIn
from app.services.usage_service import UsageService

router = APIRouter()


@router.post("/events", response_model=UsageBatchResult)
def post_events(
    payload: UsageEventBatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UsageBatchResult:
    svc = UsageService(db)
    res = svc.record_events(
        user_id=user.id,
        events=[e.model_dump() for e in payload.events],
    )
    return UsageBatchResult(**res)
