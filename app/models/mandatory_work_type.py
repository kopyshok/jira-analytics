"""MandatoryWorkType model — справочник обязательных работ."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class MandatoryWorkType(Base, TimestampMixin):
    """Тип обязательной работы (организационные вопросы, тех. долг и т.д.).

    Справочник для правил ёмкости. Пополняется пользователем вручную.
    """

    __tablename__ = "mandatory_work_types"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<MandatoryWorkType {self.code}>"
