"""MandatoryWorkType model — справочник обязательных работ."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class MandatoryWorkType(Base, TimestampMixin):
    """Тип работы (обязательная либо служебная вроде «Прочие/Чужие»).

    Системные строки (`is_system=True`) нельзя удалять и менять `code`;
    label остаётся редактируемым.
    """

    __tablename__ = "mandatory_work_types"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subtracts_from_pool: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    theme_dict_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    def __repr__(self) -> str:
        return f"<MandatoryWorkType {self.code}>"
