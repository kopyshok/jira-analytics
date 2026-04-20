"""AbsenceReason model — редактируемый справочник причин отсутствия."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class AbsenceReason(Base, TimestampMixin):
    """Тип отсутствия с флагом ``is_planned`` (отпуск vs внеплановое)."""

    __tablename__ = "absence_reasons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_planned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<AbsenceReason {self.code}>"
