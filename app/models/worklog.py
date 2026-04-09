"""Worklog model - the core fact table."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, ForeignKey, DateTime, Float, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SyncedMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.issue import Issue
    from app.models.employee import Employee


class Worklog(Base, SyncedMixin):
    """Worklog entry - actual time spent."""
    
    __tablename__ = "worklogs"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    jira_worklog_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    
    # When the work was done
    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )
    
    # Time spent in hours (converted from Jira seconds)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Original Jira time in seconds
    time_spent_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Worklog comment
    comment_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # References
    issue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("issues.id"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    )
    
    # Relationships
    issue: Mapped["Issue"] = relationship(back_populates="worklogs")
    employee: Mapped["Employee"] = relationship(back_populates="worklogs")
    
    def __repr__(self) -> str:
        return f"<Worklog {self.jira_worklog_id}: {self.hours}h>"
