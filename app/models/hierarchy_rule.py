"""Hierarchy rule — project/type-based classification for root-vs-operations split."""

from typing import Optional

from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class HierarchyRule(Base, TimestampMixin):
    """Rule for classifying a root-level issue as container vs operational.

    Evaluation: rules ordered by ``priority`` ASC, ``created_at`` ASC; first
    rule whose predicates all pass decides ``is_container``. If no rule
    matches, default is ``False`` (task goes to the ``__operations__`` group).

    Predicates:
    - ``project_key`` (None = any project)
    - ``issue_type`` (None = any type)
    - ``require_no_parent`` (True = only matches issues with no parent_id)
    """

    __tablename__ = "hierarchy_rule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, index=True, default=100)
    project_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    issue_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    require_no_parent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_container: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<HierarchyRule {self.priority} "
            f"project={self.project_key!r} type={self.issue_type!r} "
            f"container={self.is_container}>"
        )
