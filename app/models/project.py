"""Project model."""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SyncedMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.issue import Issue


class Project(Base, SyncedMixin):
    """Jira project."""
    
    __tablename__ = "projects"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    jira_project_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    project_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # Relationships
    issues: Mapped[List["Issue"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Project {self.key}>"
