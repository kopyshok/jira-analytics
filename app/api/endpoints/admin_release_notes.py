"""Админ-эндпоинты ленты «Что нового»."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import require_admin
from app.database import get_db
from app.models.release_note import ReleaseNote
from app.models.user import User
from app.schemas.release_note import (
    ReleaseNoteCreate,
    ReleaseNoteResponse,
    ReleaseNoteUpdate,
)
from app.services.release_note_service import ReleaseNoteService

router = APIRouter()


class PublishRequest(BaseModel):
    version: str


class PublishResponse(BaseModel):
    published_count: int
    version: str


@router.get("/drafts", response_model=list[ReleaseNoteResponse])
def list_drafts(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ReleaseNote]:
    return ReleaseNoteService(db).list_drafts()


@router.get("/versions/{version}", response_model=list[ReleaseNoteResponse])
def list_version(
    version: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ReleaseNote]:
    return ReleaseNoteService(db).notes_for_versions([version], include_hidden=True)


@router.post(
    "", response_model=ReleaseNoteResponse, status_code=status.HTTP_201_CREATED
)
def create_note(
    body: ReleaseNoteCreate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReleaseNote:
    try:
        return ReleaseNoteService(db).create_draft(
            note_type=body.note_type,
            section=body.section,
            title=body.title,
            description=body.description,
            help_link=body.help_link,
            created_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{note_id}", response_model=ReleaseNoteResponse)
def update_note(
    note_id: str,
    body: ReleaseNoteUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReleaseNote:
    note = db.query(ReleaseNote).filter_by(id=note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    note = db.query(ReleaseNote).filter_by(id=note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    db.delete(note)
    db.commit()


@router.post("/publish", response_model=PublishResponse)
def publish_drafts(
    body: PublishRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PublishResponse:
    svc = ReleaseNoteService(db)
    try:
        n = svc.publish_drafts(body.version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if n == 0:
        raise HTTPException(
            status_code=400, detail="Нет черновиков для публикации"
        )
    return PublishResponse(published_count=n, version=body.version)


@router.delete("/version/{version}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(
    version: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    notes = db.query(ReleaseNote).filter_by(version=version).all()
    for n in notes:
        n.version = None
    db.commit()
