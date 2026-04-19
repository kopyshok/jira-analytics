"""EmployeeCapacityOverride — индивидуальное правило на сотрудника × тип работ."""

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class EmployeeCapacityOverride(Base, TimestampMixin):
    """Индивидуальный процент обязательной нагрузки на сотрудника.

    Приоритет выше role_capacity_rules для этого сотрудника и типа работ.
    """

    __tablename__ = "employee_capacity_overrides"
    __table_args__ = (
        UniqueConstraint(
            "year", "quarter", "employee_id", "work_type_id",
            name="uq_employee_capacity_override_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True,
    )
    work_type_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id"), nullable=False,
    )
    percent_of_norm: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<EmployeeCapacityOverride {self.year}Q{self.quarter} emp={self.employee_id} wt={self.work_type_id}: {self.percent_of_norm}%>"
