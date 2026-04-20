"""Category model — user-configurable work categories."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.mandatory_work_type import MandatoryWorkType


class Category(Base, TimestampMixin):
    """Управленческая категория работ."""

    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    code: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    work_type_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("mandatory_work_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    work_type: Mapped[Optional["MandatoryWorkType"]] = relationship()

    def __repr__(self) -> str:
        return f"<Category {self.code}>"
