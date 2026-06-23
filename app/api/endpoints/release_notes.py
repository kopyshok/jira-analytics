"""Пользовательские эндпоинты ленты «Что нового»."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.release_note import (
    MarkSeenRequest,
    ReleaseNoteResponse,
    UnreadResponse,
    VersionFeed,
)
from app.services.release_note_seed import seed_from_files
from app.services.release_note_service import ReleaseNoteService, _ver_key


router = APIRouter()


def _build_feeds(svc: ReleaseNoteService, versions: list[str]) -> list[VersionFeed]:
    if not versions:
        return []
    notes = svc.notes_for_versions(versions)
    by_version: dict[str, list] = {v: [] for v in versions}
    for n in notes:
        by_version.setdefault(n.version, []).append(
            ReleaseNoteResponse.model_validate(n)
        )
    versions_desc = sorted(versions, key=_ver_key, reverse=True)
    return [VersionFeed(version=v, notes=by_version.get(v, [])) for v in versions_desc]


@router.get("/unread", response_model=UnreadResponse)
def get_unread(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadResponse:
    svc = ReleaseNoteService(db)
    unread = svc.unread_versions_for(user)
    if not unread:
        return UnreadResponse(unread_versions=[], feeds=[])
    return UnreadResponse(unread_versions=unread, feeds=_build_feeds(svc, unread))


@router.get("/all", response_model=UnreadResponse)
def get_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadResponse:
    svc = ReleaseNoteService(db)
    all_versions = svc.list_published_versions()
    return UnreadResponse(
        unread_versions=svc.unread_versions_for(user),
        feeds=_build_feeds(svc, all_versions),
    )


@router.post("/mark-seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_seen(
    body: MarkSeenRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = ReleaseNoteService(db)
    svc.mark_user_seen(user, body.version)


@router.post("/reseed")
def reseed(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Повторно применить release_notes/*.json к БД без перезапуска сервиса.

    Тот же сидер, что и при старте (идемпотентен по version+title). Кнопка в
    админке «Что нового» — страховка на случай, если деплой прошёл без рестарта.
    """
    return seed_from_files(db)
