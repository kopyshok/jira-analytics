"""FastAPI dependency: глобальный AI-рубильник."""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.llm.base import is_ai_enabled


def require_ai_enabled(db: Session = Depends(get_db)) -> None:
    """503 если ИИ выключен администратором."""
    if not is_ai_enabled(db):
        raise HTTPException(status_code=503, detail="AI disabled by administrator")
