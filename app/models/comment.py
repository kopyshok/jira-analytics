"""Comment model - Jira issue comments."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SyncedMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.issue import Issue
    from app.models.employee import Employee


class Comment(Base, SyncedMixin):
    """Комментарий к задаче Jira.

    Используется для вспомогательного анализа и контекста.
    """

    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    jira_comment_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Foreign keys
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id"), nullable=False, index=True
    )
    author_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=True, index=True
    )

    # Relationships
    issue: Mapped["Issue"] = relationship(back_populates="comments")
    author: Mapped[Optional["Employee"]] = relationship(back_populates="comments")

    def __repr__(self) -> str:
        return f"<Comment {self.jira_comment_id}>"
