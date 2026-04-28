"""ScenarioAbsenceSnapshot — copy of employee absences at approval time."""
from datetime import date
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision
    from app.models.employee import Employee


class ScenarioAbsenceSnapshot(Base, TimestampMixin):
    """Копия отсутствия сотрудника на момент утверждения сценария.

    Хранит original_absence_id для идентификации отсутствий,
    удалённых или изменённых после утверждения.
    """

    __tablename__ = "scenario_absence_snapshots"

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
    original_absence_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reason_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hours_total: Mapped[float] = mapped_column(Float, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="absence_snapshots")
    employee: Mapped[Optional["Employee"]] = relationship()

    def __repr__(self) -> str:
        return f"<ScenarioAbsenceSnapshot emp={self.employee_name} {self.start_date}–{self.end_date}>"
