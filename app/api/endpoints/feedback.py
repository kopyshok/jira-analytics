"""Feedback endpoints: bugs + ideas (user-facing) + admin moderation."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.models.feedback import FeedbackItem, FeedbackKind
from app.models.user import User
from app.schemas.feedback import (
    AttachmentRef,
    BugCreate,
    ExportRequest,
    FeedbackAuthor,
    FeedbackContext,
    FeedbackRead,
    IdeaCreate,
    MarkReadRequest,
)
from app.services.feedback_service import FeedbackService

router = APIRouter()
_service = FeedbackService()


def _to_read(item: FeedbackItem, db: Session) -> FeedbackRead:
    """Serialize a FeedbackItem into FeedbackRead with author + parsed JSON blobs."""
    author = db.get(User, item.author_id)
    return FeedbackRead(
        id=item.id,
        kind=item.kind.value,
        author=FeedbackAuthor(
            id=author.id if author else item.author_id,
            display_name=author.display_name if author else "—",
            email=author.email if author else "—",
        ),
        title=item.title,
        body=item.body,
        page_url=item.page_url,
        read_at=item.read_at,
        read_by=item.read_by,
        steps_to_reproduce=item.steps_to_reproduce,
        expected=item.expected,
        actual=item.actual,
        context=(
            FeedbackContext(**json.loads(item.context_json)) if item.context_json else None
        ),
        attachments=(
            [AttachmentRef(**a) for a in json.loads(item.attachments_json)]
            if item.attachments_json
            else []
        ),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/bugs", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
def create_bug(
    payload: BugCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedbackRead:
    item = _service.create_bug(db, author=user, payload=payload)
    return _to_read(item, db)


@router.post("/ideas", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
def create_idea(
    payload: IdeaCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedbackRead:
    item = _service.create_idea(db, author=user, payload=payload)
    return _to_read(item, db)


@router.get("/my", response_model=list[FeedbackRead])
def list_my(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FeedbackRead]:
    bugs = _service.list_for_user(
        db, author_id=user.id, kind=FeedbackKind.bug, scope="mine"
    )
    ideas = _service.list_for_user(
        db, author_id=user.id, kind=FeedbackKind.idea, scope="mine"
    )
    combined = sorted(bugs + ideas, key=lambda x: x.created_at, reverse=True)
    return [_to_read(it, db) for it in combined]


@router.get("/ideas", response_model=list[FeedbackRead])
def list_ideas_feed(
    scope: str = "all",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FeedbackRead]:
    items = _service.list_for_user(
        db, author_id=user.id, kind=FeedbackKind.idea, scope=scope
    )
    return [_to_read(it, db) for it in items]


@router.get("/admin/bugs", response_model=list[FeedbackRead])
def admin_list_bugs(
    filter: str = "unread",
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[FeedbackRead]:
    items = _service.list_for_admin(db, kind=FeedbackKind.bug, filter_mode=filter)
    return [_to_read(it, db) for it in items]


@router.get("/admin/ideas", response_model=list[FeedbackRead])
def admin_list_ideas(
    filter: str = "unread",
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[FeedbackRead]:
    items = _service.list_for_admin(db, kind=FeedbackKind.idea, filter_mode=filter)
    return [_to_read(it, db) for it in items]


@router.post("/admin/mark-read", status_code=204)
def admin_mark_read(
    payload: MarkReadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Response:
    _service.mark_read(db, ids=payload.ids, reader_id=user.id)
    return Response(status_code=204)


@router.post("/admin/mark-unread", status_code=204)
def admin_mark_unread(
    payload: MarkReadRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    _service.mark_unread(db, ids=payload.ids)
    return Response(status_code=204)


@router.post("/admin/export")
def admin_export(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Response:
    kind = FeedbackKind(payload.kind)
    md = _service.export_markdown(
        db,
        kind=kind,
        ids=payload.ids,
        only_unread=payload.only_unread,
        mark_after=payload.mark_after,
        reader_id=user.id,
    )
    today = datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"feedback-{payload.kind}s-{today}.md"
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/attachments", response_model=AttachmentRef)
async def upload_attachment(
    file: UploadFile,
    _: User = Depends(get_current_user),
) -> AttachmentRef:
    data = await file.read()
    try:
        ref = _service.save_attachment(
            filename=file.filename or "file",
            mime=file.content_type or "application/octet-stream",
            data=data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ref


@router.get("/attachments/{stored_name}")
def download_attachment(
    stored_name: str,
    _: User = Depends(get_current_user),
) -> FileResponse:
    # Минимальная защита: UUID-имена не угадаешь, любой authenticated может скачать.
    path = _service.attachment_full_path(stored_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path)
