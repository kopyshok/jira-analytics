"""ScenarioRevision model — one record per scenario approval event."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.planning_scenario import PlanningScenario
    from app.models.scenario_revision_item import ScenarioRevisionItem
    from app.models.scenario_capacity_snapshot import ScenarioCapacitySnapshot


class ScenarioRevision(Base, TimestampMixin):
    """Запись об одном утверждении сценария.

    Создаётся при каждом POST /scenarios/{id}/approve. Хранит порядковый
    номер, момент утверждения, необязательный комментарий PM и ссылки на
    дифф инициатив и снапшот ресурсов.
    """

    __tablename__ = "scenario_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_scenarios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scenario: Mapped["PlanningScenario"] = relationship(back_populates="revisions")
    items: Mapped[List["ScenarioRevisionItem"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    capacity_snapshots: Mapped[List["ScenarioCapacitySnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ScenarioRevision scenario={self.scenario_id} rev={self.revision_number}>"
