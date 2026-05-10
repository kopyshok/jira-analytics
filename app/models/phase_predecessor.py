"""PhasePredecessor — связь предшественника фазы внутри инициативы."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.resource_plan_assignment import ResourcePlanAssignment


class PhasePredecessor(Base, TimestampMixin):
    """Связь предшественника фазы внутри инициативы (свободный граф)."""

    __tablename__ = "phase_predecessor"
    __table_args__ = (
        UniqueConstraint(
            "successor_assignment_id",
            "predecessor_assignment_id",
            name="uq_phase_predecessor_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    successor_assignment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("resource_plan_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    predecessor_assignment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("resource_plan_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
