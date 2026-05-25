"""Feedback endpoints: bugs + ideas (user-facing) + admin moderation."""
import json

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.feedback import FeedbackItem, FeedbackKind
from app.models.user import User
from app.schemas.feedback import (
    AttachmentRef,
    BugCreate,
    FeedbackAuthor,
    FeedbackContext,
    FeedbackRead,
    IdeaCreate,
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
