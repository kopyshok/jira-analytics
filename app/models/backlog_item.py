"""BacklogItem model - quarterly backlog items."""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import Float, Integer, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.scenario_allocation import ScenarioAllocation


class BacklogItem(Base, TimestampMixin):
    """Элемент квартального бэклога.

    Задача берётся в квартал целиком. Используется при формировании
    сценариев квартального планирования.
    """

    __tablename__ = "backlog_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )
    quarter: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # e.g., "Q1", "Q2"
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimate_hours: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    project: Mapped[Optional["Project"]] = relationship(back_populates="backlog_items")
    allocations: Mapped[List["ScenarioAllocation"]] = relationship(
        back_populates="backlog_item"
    )

    def __repr__(self) -> str:
        return f"<BacklogItem {self.title[:30]}>"
