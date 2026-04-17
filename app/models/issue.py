"""Issue model - represents Jira issues/tasks."""

from typing import Optional, List, TYPE_CHECKING

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SyncedMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.worklog import Worklog
    from app.models.comment import Comment


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
    # Jira statusCategory.key: 'new' | 'indeterminate' | 'done' (nullable for
    # older installs). Нужна чтобы красить бейджи в то же, что показывает Jira.
    status_category: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
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

    # User-configurable fields
    team: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    participating_teams: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Jira custom «Цели» (customfield_11421 by default) — напр. «3кв25».
    # Тянется через AppSetting.jira_goals_field_id, сохраняется плоской
    # строкой (comma-joined для multi-select).
    goals: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assigned_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    include_in_analysis: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=True)

    # Jira metadata for triage (e.g. «какие Done висят давно — в архив»)
    status_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="issues")
    parent: Mapped[Optional["Issue"]] = relationship(
        "Issue",
        remote_side=[id],
        backref="children",
    )
    worklogs: Mapped[List["Worklog"]] = relationship(back_populates="issue")
    comments: Mapped[List["Comment"]] = relationship(back_populates="issue")

    def __repr__(self) -> str:
        return f"<Issue {self.key}: {self.summary[:30]}>"
