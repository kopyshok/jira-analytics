"""Pick best theme for an issue vector via cosine similarity."""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.models.theme import Theme
from app.services.llm.theme_embedding_service import ThemeEmbeddingService


class EmbeddingMatcher:
    def __init__(self, theme_embedding_service: ThemeEmbeddingService) -> None:
        self.tes = theme_embedding_service

    def find_best_theme(
        self,
        issue_vec: np.ndarray,
        themes: list[Theme],
        threshold: float,
    ) -> tuple[Optional[Theme], float]:
        """Возвращает (best_theme | None, best_score).

        Если у темы нет валидного embedding — лениво пересчитываем.
        """
        best: Optional[Theme] = None
        best_score: float = -1.0
        for theme in themes:
            tvec = self.tes.load_vector(theme)
            if tvec is None:
                self.tes.recompute_theme_embedding(theme.id)
                self.tes.db.refresh(theme)
                tvec = self.tes.load_vector(theme)
                if tvec is None:
                    continue
            score = float(np.dot(issue_vec, tvec))
            if score > best_score:
                best_score = score
                best = theme
        if best is None or best_score < threshold:
            return None, max(best_score, 0.0)
        return best, best_score
