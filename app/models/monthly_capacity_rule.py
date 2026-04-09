"""MonthlyCapacityRule model - monthly capacity norms."""

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class MonthlyCapacityRule(Base, TimestampMixin):
    """Норматив обязательных работ на месяц.

    Процентный вычет от нормы часов — используется для расчёта
    доступной ёмкости при квартальном планировании.
    """

    __tablename__ = "monthly_capacity_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    percent_of_norm: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<MonthlyCapacityRule {self.year}-{self.month:02d}: {self.percent_of_norm}%>"
