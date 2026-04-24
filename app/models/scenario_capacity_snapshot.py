"""ScenarioCapacitySnapshot model — per-employee per-month norm at approval time."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision
    from app.models.employee import Employee


class ScenarioCapacitySnapshot(Base, TimestampMixin):
    """Снапшот нормы одного сотрудника за один месяц на момент утверждения сценария.

    Позволяет впоследствии сравнить плановую норму (зафиксированную при утверждении)
    с текущей нормой (с учётом незапланированных отсутствий, добавленных позже).
    employee_name денормализовано на случай удаления сотрудника.
    """

    __tablename__ = "scenario_capacity_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    norm_hours: Mapped[float] = mapped_column(Float, nullable=False)
    available_hours: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="capacity_snapshots")
    employee: Mapped[Optional["Employee"]] = relationship()

    def __repr__(self) -> str:
        return f"<ScenarioCapacitySnapshot emp={self.employee_name} {self.year}-{self.month:02d}>"
