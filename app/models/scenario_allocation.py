"""ScenarioAllocation model - allocations within a planning scenario."""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.planning_scenario import PlanningScenario
    from app.models.backlog_item import BacklogItem


class ScenarioAllocation(Base, TimestampMixin):
    """Результат распределения задач в сценарии планирования.

    Определяет, какие элементы бэклога вошли в квартал
    и с каким объёмом запланированных часов.
    """

    __tablename__ = "scenario_allocations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_scenarios.id"), nullable=False, index=True
    )
    backlog_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id"), nullable=False, index=True
    )
    planned_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    included_flag: Mapped[bool] = mapped_column(Boolean, default=True)
    involvement_coefficient: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Per-scenario override per-role estimates. NULL = inherit from BacklogItem.
    # Если ВСЕ 4 NULL → берём BacklogItem.estimate_*.
    # Если хотя бы один не-NULL → берём 4 цифры из override (NULL = 0.0).
    override_estimate_analyst_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_estimate_dev_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_estimate_qa_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_estimate_opo_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Per-scenario manual ordering: чек поднимает строку наверх (min-1.0),
    # снятие галочки — НЕ меняет позицию. Drag&drop переписывает в 1, 2, 3, ...
    sort_order: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=False)

    # Relationships
    scenario: Mapped["PlanningScenario"] = relationship(back_populates="allocations")
    backlog_item: Mapped["BacklogItem"] = relationship(back_populates="allocations")

    def __repr__(self) -> str:
        return f"<ScenarioAllocation scenario={self.scenario_id} item={self.backlog_item_id}>"
