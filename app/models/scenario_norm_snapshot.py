"""ScenarioNormSnapshot — per-employee/month/work_type norm at approval time."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision
    from app.models.employee import Employee


class ScenarioNormSnapshot(Base, TimestampMixin):
    """Норма сотрудника по виду работ за месяц на момент утверждения.

    Позволяет читать плановые часы с дашборда без пересчёта и сравнивать
    по ролям/сотрудникам в будущей аналитике.
    """

    __tablename__ = "scenario_norm_snapshots"

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
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    work_type_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    work_type_label: Mapped[str] = mapped_column(String(255), nullable=False)
    norm_hours: Mapped[float] = mapped_column(Float, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="norm_snapshots")
    employee: Mapped[Optional["Employee"]] = relationship()

    def __repr__(self) -> str:
        return f"<ScenarioNormSnapshot emp={self.employee_name} {self.year}-{self.month:02d} wt={self.work_type_label}>"
