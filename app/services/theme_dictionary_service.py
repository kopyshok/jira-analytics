"""ThemeDictionaryService — CRUD словаря тем + слияние + архивация.

Любая мутация словаря поднимает MandatoryWorkType.theme_dict_version,
что инвалидирует кэш классификации задач при следующем построении.
"""
import logging
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.mandatory_work_type import MandatoryWorkType

logger = logging.getLogger("jira_analytics.thematic")


class ThemeDictionaryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_active(self, work_type_id: str) -> list[Theme]:
        """Вернуть активные (не архивированные) темы для вида работ."""
        q = (
            select(Theme)
            .where(Theme.work_type_id == work_type_id, Theme.is_archived.is_(False))
            .order_by(Theme.sort_order, Theme.name)
        )
        return list(self.db.execute(q).scalars().all())

    def list_all(self, work_type_id: str) -> list[Theme]:
        """Вернуть все темы (включая архивированные) для вида работ."""
        q = (
            select(Theme)
            .where(Theme.work_type_id == work_type_id)
            .order_by(Theme.is_archived, Theme.sort_order, Theme.name)
        )
        return list(self.db.execute(q).scalars().all())

    def get(self, theme_id: str) -> Optional[Theme]:
        """Найти тему по идентификатору."""
        return self.db.get(Theme, theme_id)

    def create_theme(
        self,
        *,
        work_type_id: str,
        name: str,
        description: Optional[str] = None,
        color: str = "#00c9c8",
        sort_order: int = 0,
        created_by: Optional[str] = None,
    ) -> Theme:
        """Создать новую тему и поднять версию словаря."""
        existing = self.db.execute(
            select(Theme).where(
                Theme.work_type_id == work_type_id,
                Theme.name == name,
                Theme.is_archived.is_(False),
            )
        ).scalar_one_or_none()
        if existing:
            raise ValueError(f"Theme '{name}' already exists for work_type={work_type_id}")
        t = Theme(
            work_type_id=work_type_id,
            name=name,
            description=description,
            color=color,
            sort_order=sort_order,
            created_by=created_by,
        )
        self.db.add(t)
        self._bump_version(work_type_id)
        self.db.commit()
        self.db.refresh(t)
        self._recompute_embedding_silent(t.id)
        self.db.refresh(t)
        return t

    def update_theme(
        self,
        *,
        theme_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> Theme:
        """Обновить тему. None в любом параметре = «не менять»."""
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        changed = False
        if name is not None and name != t.name:
            dup = self.db.execute(
                select(Theme).where(
                    Theme.work_type_id == t.work_type_id,
                    Theme.name == name,
                    Theme.id != t.id,
                    Theme.is_archived.is_(False),
                )
            ).scalar_one_or_none()
            if dup:
                raise ValueError(f"Theme '{name}' already exists")
            t.name = name
            changed = True
        if description is not None:
            t.description = description
            changed = True
        if color is not None:
            t.color = color
            changed = True
        if sort_order is not None:
            t.sort_order = sort_order
            changed = True
        if changed:
            self._bump_version(t.work_type_id)
        self.db.commit()
        self.db.refresh(t)
        if changed:
            self._recompute_embedding_silent(t.id)
            self.db.refresh(t)
        return t

    def archive_theme(self, theme_id: str) -> Theme:
        """Архивировать тему; поднять версию словаря."""
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        if not t.is_archived:
            t.is_archived = True
            self._bump_version(t.work_type_id)
        self.db.commit()
        self.db.refresh(t)
        return t

    def restore_theme(self, theme_id: str) -> Theme:
        """Восстановить тему из архива; поднять версию словаря."""
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        if t.is_archived:
            t.is_archived = False
            self._bump_version(t.work_type_id)
        self.db.commit()
        self.db.refresh(t)
        return t

    def merge_theme(self, *, src_id: str, dst_id: str) -> Theme:
        """Перенести все классификации из src в dst, src архивировать."""
        src = self.db.get(Theme, src_id)
        dst = self.db.get(Theme, dst_id)
        if not src or not dst:
            raise ValueError("Source or destination theme not found")
        if src.work_type_id != dst.work_type_id:
            raise ValueError("Cannot merge themes across different work types")
        self.db.execute(
            update(IssueClassification)
            .where(IssueClassification.theme_id == src_id)
            .values(theme_id=dst_id)
        )
        src.is_archived = True
        self._bump_version(src.work_type_id)
        self.db.commit()
        self.db.refresh(dst)
        self._recompute_embedding_silent(dst.id)
        self.db.refresh(dst)
        return dst

    def add_alias(self, theme_id: str, alias: str) -> Theme:
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        current = t.aliases
        normalized = alias.strip()
        if not normalized:
            return t
        if normalized.lower() in {a.lower() for a in current}:
            return t  # idempotent
        current.append(normalized)
        t.aliases = current
        self._bump_version(t.work_type_id)
        self.db.commit()
        self.db.refresh(t)
        self._recompute_embedding_silent(t.id)
        self.db.refresh(t)
        return t

    def remove_alias(self, theme_id: str, alias: str) -> Theme:
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        current = t.aliases
        new = [a for a in current if a.lower() != alias.lower()]
        if len(new) == len(current):
            return t  # ничего не нашли — no-op
        t.aliases = new
        self._bump_version(t.work_type_id)
        self.db.commit()
        self.db.refresh(t)
        self._recompute_embedding_silent(t.id)
        self.db.refresh(t)
        return t

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bump_version(self, work_type_id: str) -> None:
        """Инкрементировать theme_dict_version для вида работ."""
        wt = self.db.get(MandatoryWorkType, work_type_id)
        if not wt:
            raise ValueError(f"MandatoryWorkType {work_type_id} not found")
        wt.theme_dict_version = (wt.theme_dict_version or 0) + 1

    def _recompute_embedding_silent(self, theme_id: str) -> None:
        """Перепосчитать centroid темы; не валим вызывающий код при сбое модели."""
        try:
            from app.services.llm.theme_embedding_service import ThemeEmbeddingService
            ThemeEmbeddingService(self.db).recompute_theme_embedding(theme_id)
        except Exception as e:
            logger.warning("Theme embedding recompute failed (theme=%s): %s", theme_id, e)
