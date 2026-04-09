"""CategoryMapping model - maps entities to work categories."""

from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class CategoryMapping(Base, TimestampMixin):
    """Связь сущностей (эпиков, задач, проектов) с управленческими категориями.

    Категории: сопровождение, анализ/развитие, встречи,
    административные потери, внутренние коммуникации,
    технический долг, незаполненные worklog.
    """

    __tablename__ = "category_mappings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # issue, project, epic
    entity_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    subcategory: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    source_rule: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # manual, inherited, quality_rule

    def __repr__(self) -> str:
        return f"<CategoryMapping {self.entity_type}:{self.entity_id} -> {self.category}>"
