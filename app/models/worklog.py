"""Worklog model - the core fact table for time tracking."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SyncedMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.issue import Issue


class Worklog(Base, SyncedMixin):
    """Worklog model - time logged by employees on issues.
    
    This is the primary fact table for analytics. Each row represents
    a single time entry from Jira.
    """

    __tablename__ = "worklogs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    jira_worklog_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    
    # Time tracking
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Optional comment
    comment_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Foreign keys
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )

    # Relationships
    issue: Mapped["Issue"] = relationship(back_populates="worklogs")
    employee: Mapped["Employee"] = relationship(back_populates="worklogs")

    def __repr__(self) -> str:
        return f"<Worklog {self.hours}h on {self.started_at.date()}>"
