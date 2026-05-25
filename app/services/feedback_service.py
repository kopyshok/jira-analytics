"""FeedbackService — баги и идеи от пользователей."""
import json
from datetime import datetime

from sqlalchemy import select
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

    def list_for_admin(
        self,
        db: Session,
        *,
        kind: FeedbackKind,
        filter_mode: str = "unread",
        limit: int = 200,
        offset: int = 0,
    ) -> list[FeedbackItem]:
        stmt = select(FeedbackItem).where(FeedbackItem.kind == kind)
        if filter_mode == "unread":
            stmt = stmt.where(FeedbackItem.read_at.is_(None))
        elif filter_mode == "read":
            stmt = stmt.where(FeedbackItem.read_at.is_not(None))
        stmt = stmt.order_by(FeedbackItem.created_at.desc()).limit(limit).offset(offset)
        return list(db.execute(stmt).scalars())

    def list_for_user(
        self,
        db: Session,
        *,
        author_id: str,
        kind: FeedbackKind,
        scope: str = "mine",
        limit: int = 200,
        offset: int = 0,
    ) -> list[FeedbackItem]:
        stmt = select(FeedbackItem).where(FeedbackItem.kind == kind)
        if scope == "mine" or kind == FeedbackKind.bug:
            # Юзер видит только свои баги — чужие баги admin-only.
            stmt = stmt.where(FeedbackItem.author_id == author_id)
        stmt = stmt.order_by(FeedbackItem.created_at.desc()).limit(limit).offset(offset)
        return list(db.execute(stmt).scalars())

    def mark_read(self, db: Session, *, ids: list[str], reader_id: str) -> int:
        now = datetime.utcnow()
        items = list(
            db.execute(select(FeedbackItem).where(FeedbackItem.id.in_(ids))).scalars()
        )
        for item in items:
            if item.read_at is None:
                item.read_at = now
                item.read_by = reader_id
        db.commit()
        return len(items)

    def mark_unread(self, db: Session, *, ids: list[str]) -> int:
        items = list(
            db.execute(select(FeedbackItem).where(FeedbackItem.id.in_(ids))).scalars()
        )
        for item in items:
            item.read_at = None
            item.read_by = None
        db.commit()
        return len(items)
