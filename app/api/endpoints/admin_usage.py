"""Admin-only endpoints для usage аналитики."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.usage_service import UsageService

router = APIRouter()


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    return UsageService(db).query_overview()


@router.get("/users")
def users(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[dict]:
    return UsageService(db).query_users(days=days)


@router.get("/pages")
def pages(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[dict]:
    return UsageService(db).query_pages(days=days)


@router.get("/matrix")
def matrix(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> dict:
    return UsageService(db).query_matrix(days=days)


@router.get("/timeline")
def timeline(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[dict]:
    return UsageService(db).query_timeline(days=days)


@router.get("/actions")
def actions(days: int = Query(30, ge=1, le=90), db: Session = Depends(get_db)) -> list[dict]:
    return UsageService(db).query_actions(days=days)
