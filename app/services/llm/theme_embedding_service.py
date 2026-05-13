"""Compute and persist theme centroid embeddings.

Theme centroid = L2-normalize(text_vec * 1.0 + sum(issue_vec * 0.5))

`text_vec` is embedding of theme.name + description + aliases.
`issue_vec`s are embeddings of top-K issue summaries (by total worklog hours).

Centroid is recomputed:
- On lazy access (theme.embedding is NULL or model_version mismatch).
- On theme save (name/description/aliases changed) — via ThemeDictionaryService.
- On candidate merge/accept — via work_type_report endpoints.
"""
from __future__ import annotations

import logging
import pickle
from datetime import datetime
from typing import Optional

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.issue_classification import IssueClassification
from app.models.theme import Theme
from app.models.worklog import Worklog
from app.services.llm.embedding_service import (
    EMBEDDING_DIM,
    EmbeddingService,
    MODEL_VERSION,
)

logger = logging.getLogger("jira_analytics.embedding")

THEME_CENTROID_TOP_K = 20
ISSUE_WEIGHT = 0.5


class ThemeEmbeddingService:
    def __init__(self, db: Session, embedder: Optional[EmbeddingService] = None) -> None:
        self.db = db
        self.embedder = embedder or EmbeddingService()

    def _theme_text(self, theme: Theme) -> str:
        parts = [theme.name or ""]
        if theme.description:
            parts.append(theme.description)
        aliases = theme.aliases
        if aliases:
            parts.append("Также покрывает: " + ", ".join(aliases))
        return ". ".join(p for p in parts if p)

    def _load_top_issues(self, theme: Theme) -> list[Issue]:
        """Top-K привязанных к теме задач по часам (за всё время)."""
        q = (
            select(Issue, func.coalesce(func.sum(Worklog.hours), 0.0).label("hrs"))
            .join(IssueClassification, IssueClassification.issue_id == Issue.id)
            .outerjoin(Worklog, Worklog.issue_id == Issue.id)
            .where(IssueClassification.theme_id == theme.id)
            .group_by(Issue.id)
            .order_by(func.coalesce(func.sum(Worklog.hours), 0.0).desc())
            .limit(THEME_CENTROID_TOP_K)
        )
        return [row[0] for row in self.db.execute(q).all()]

    def compute_theme_embedding(
        self,
        theme: Theme,
        top_issues: Optional[list[Issue]] = None,
    ) -> np.ndarray:
        if top_issues is None:
            top_issues = self._load_top_issues(theme)

        text_vec = self.embedder.encode_text(self._theme_text(theme), kind="passage")
        accum = text_vec.astype(np.float32).copy()

        if top_issues:
            issue_texts = [(it.summary or "") for it in top_issues]
            issue_vecs = self.embedder.encode_batch(issue_texts, kind="passage")
            accum = accum + issue_vecs.sum(axis=0) * ISSUE_WEIGHT

        norm = float(np.linalg.norm(accum))
        if norm > 0:
            accum = accum / norm
        return accum.astype(np.float32)

    def recompute_theme_embedding(self, theme_id: str) -> Optional[Theme]:
        theme = self.db.get(Theme, theme_id)
        if not theme:
            return None
        vec = self.compute_theme_embedding(theme)
        theme.embedding = pickle.dumps(vec)
        theme.embedding_model_version = MODEL_VERSION
        theme.embedding_updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(theme)
        return theme

    def load_vector(self, theme: Theme) -> Optional[np.ndarray]:
        """Деpickle сохранённый вектор. Возвращает None если пусто или модель не та."""
        if not theme.embedding:
            return None
        if theme.embedding_model_version != MODEL_VERSION:
            return None
        try:
            v = pickle.loads(theme.embedding)
        except Exception:
            return None
        if not isinstance(v, np.ndarray) or v.shape != (EMBEDDING_DIM,):
            return None
        return v
