"""WorkTypeReportLayout — per-user saved pivot/columns layout."""
from typing import Optional
from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class WorkTypeReportLayout(Base, TimestampMixin):
    __tablename__ = "work_type_report_layouts"
    __table_args__ = (
        Index("ix_layouts_user_wt", "user_id", "work_type_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    grouping_dims_json: Mapped[str] = mapped_column(Text, nullable=False)
    visible_columns_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<WorkTypeReportLayout user={self.user_id} wt={self.work_type_id} name={self.name!r}>"
