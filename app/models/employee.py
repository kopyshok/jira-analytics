"""Employee model - represents Jira users."""

from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SyncedMixin, generate_uuid
from app.database import Base


class Employee(Base, SyncedMixin):
    """Employee/Jira user model.
    
    Maps to Jira user accounts. Created automatically during sync
    when users are encountered (issue creators, worklog authors).
    """

    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    jira_account_id: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Analytics fields (populated later)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # developer, analyst, tester, pm
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    worklogs = relationship("Worklog", back_populates="employee")

    def __repr__(self) -> str:
        return f"<Employee {self.display_name}>"
