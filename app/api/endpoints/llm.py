"""LLM administration: test connection."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.llm.base import ConfigurationError, get_llm_provider


router = APIRouter()


@router.post("/test")
async def test_connection(db: Session = Depends(get_db)):
    """Проверка соединения с настроенным LLM-провайдером."""
    try:
        provider = get_llm_provider(db)
    except ConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ok = await provider.healthcheck()
    return {"ok": ok, "provider": provider.name, "model": provider.model}
