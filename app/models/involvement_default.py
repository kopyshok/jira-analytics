"""InvolvementDefault — справочник вовлечённости по ролям с датой начала действия."""
from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

INVOLVEMENT_ROLES = ("analyst", "dev", "qa", "opo")


class InvolvementDefault(Base, TimestampMixin):
    """Значение вовлечённости для (команда, роль), действующее с указанного
    квартала и до следующей записи по той же паре с более поздним началом."""

    __tablename__ = "involvement_defaults"
    __table_args__ = (
        UniqueConstraint(
            "team", "role", "effective_year", "effective_quarter",
            name="uq_involvement_default_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_year: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    involvement: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<InvolvementDefault {self.team}/{self.role} "
            f"с {self.effective_year}Q{self.effective_quarter}: {self.involvement}>"
        )
