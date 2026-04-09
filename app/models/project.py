"""Project model - represents Jira projects."""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SyncedMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.issue import Issue


class Project(Base, SyncedMixin):
    """Jira project model."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    jira_project_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    key: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Analytics fields
    is_active: Mapped[bool] = mapped_column(default=True)

    # Relationships
    issues: Mapped[List["Issue"]] = relationship(back_populates="project")

    def __repr__(self) -> str:
        return f"<Project {self.key}: {self.name}>"
