"""AI status endpoint — публичный (auth) флаг включён/выключен."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.llm.base import is_ai_enabled


router = APIRouter()


class AIStatusResponse(BaseModel):
    enabled: bool


@router.get("", response_model=AIStatusResponse)
def get_ai_status(db: Session = Depends(get_db)) -> AIStatusResponse:
    """Возвращает текущее состояние AI-рубильника."""
    return AIStatusResponse(enabled=is_ai_enabled(db))
