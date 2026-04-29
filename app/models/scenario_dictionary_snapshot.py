"""ScenarioDictionarySnapshot — снимки справочников (work_types, roles, absence_reasons).

Хранит копии labels/sort_order/extra_json чтобы ревизия оставалась читаемой
после удаления/переименования оригинальной записи справочника.
"""
from typing import Any, Optional, TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioDictionarySnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_dictionary_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    original_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="dictionary_snapshots")
