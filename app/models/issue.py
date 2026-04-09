"""Issue model - represents Jira issues/tasks."""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SyncedMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.worklog import Worklog


class Issue(Base, SyncedMixin):
    """Jira issue model.
    
    Represents tasks, bugs, stories, epics, and subtasks.
    Supports parent-child hierarchy (epics -> stories -> subtasks).
    """

    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    jira_issue_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    key: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Task, Bug, Story, Epic
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Foreign keys
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("issues.id"), nullable=True, index=True
    )
    
    # Analytics fields (populated during mapping phase)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # development, testing, management, etc.
    estimated_hours: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="issues")
    parent: Mapped[Optional["Issue"]] = relationship(
        "Issue",
        remote_side=[id],
        backref="children",
    )
    worklogs: Mapped[List["Worklog"]] = relationship(back_populates="issue")

    def __repr__(self) -> str:
        return f"<Issue {self.key}: {self.summary[:30]}>"
