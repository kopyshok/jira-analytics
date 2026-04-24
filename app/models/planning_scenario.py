"""PlanningScenario model - quarterly planning scenarios."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_allocation import ScenarioAllocation
    from app.models.scenario_revision import ScenarioRevision


class PlanningScenario(Base, TimestampMixin):
    """Сценарий квартального планирования.

    Хранение нескольких расчётов квартального набора задач
    с возможностью сравнения.
    """

    __tablename__ = "planning_scenarios"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quarter: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # e.g., "Q1", "Q2"
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # "draft" — PM правит отметки; "approved" — зафиксирован для аналитики.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    external_qa_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    allocations: Mapped[List["ScenarioAllocation"]] = relationship(
        back_populates="scenario"
    )
    revisions: Mapped[List["ScenarioRevision"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan",
        order_by="ScenarioRevision.revision_number",
    )

    def __repr__(self) -> str:
        return f"<PlanningScenario {self.name}>"
