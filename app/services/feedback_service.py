"""FeedbackService — баги и идеи от пользователей."""
import json

from sqlalchemy.orm import Session

from app.models.feedback import FeedbackItem, FeedbackKind
from app.models.user import User
from app.schemas.feedback import BugCreate, IdeaCreate


class FeedbackService:
    def create_bug(
        self, db: Session, *, author: User, payload: BugCreate
    ) -> FeedbackItem:
        item = FeedbackItem(
            kind=FeedbackKind.bug,
            author_id=author.id,
            title=payload.title,
            body=payload.body,
            page_url=payload.page_url,
            steps_to_reproduce=payload.steps_to_reproduce,
            expected=payload.expected,
            actual=payload.actual,
            context_json=(
                json.dumps(payload.context.model_dump()) if payload.context else None
            ),
            attachments_json=(
                json.dumps([a.model_dump() for a in payload.attachments])
                if payload.attachments
                else None
            ),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def create_idea(
        self, db: Session, *, author: User, payload: IdeaCreate
    ) -> FeedbackItem:
        item = FeedbackItem(
            kind=FeedbackKind.idea,
            author_id=author.id,
            title=payload.title,
            body=payload.body,
            page_url=payload.page_url,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
