"""Themes API — словарь тем для тематических отчётов."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth_deps import get_current_user
from app.models.user import User
from app.schemas.work_type_report import (
    ThemeCreateRequest,
    ThemeUpdateRequest,
    ThemeMergeRequest,
    ThemeOut,
    ThemeListResponse,
)
from app.services.theme_dictionary_service import ThemeDictionaryService


router = APIRouter()


@router.get("", response_model=ThemeListResponse)
def list_themes(
    work_type_id: str = Query(...),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    themes = svc.list_all(work_type_id) if include_archived else svc.list_active(work_type_id)
    return ThemeListResponse(
        themes=[ThemeOut.model_validate(t) for t in themes],
        candidates=[],  # populated in later task
    )


@router.post("", response_model=ThemeOut, status_code=201)
def create_theme(
    payload: ThemeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.create_theme(
            work_type_id=payload.work_type_id,
            name=payload.name,
            description=payload.description,
            color=payload.color,
            sort_order=payload.sort_order,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ThemeOut.model_validate(t)


@router.patch("/{theme_id}", response_model=ThemeOut)
def update_theme(
    theme_id: str,
    payload: ThemeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.update_theme(theme_id=theme_id, **payload.model_dump(exclude_unset=True))
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(409, msg)
    return ThemeOut.model_validate(t)


@router.post("/{theme_id}/archive", response_model=ThemeOut)
def archive_theme(
    theme_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.archive_theme(theme_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ThemeOut.model_validate(t)


@router.post("/{theme_id}/restore", response_model=ThemeOut)
def restore_theme(
    theme_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.restore_theme(theme_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ThemeOut.model_validate(t)


@router.post("/{theme_id}/merge", response_model=ThemeOut)
def merge_theme(
    theme_id: str,
    payload: ThemeMergeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        dst = svc.merge_theme(src_id=theme_id, dst_id=payload.target_theme_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return ThemeOut.model_validate(dst)
