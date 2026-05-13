"""Singleton embedding service for theme matching.

Loads `intfloat/multilingual-e5-base` once (via FastAPI lifespan) and reuses.
Returns L2-normalized float32 vectors (cosine = dot product).

E5 family requires `query: ` / `passage: ` prefixes on input. Service applies
them automatically (issue/theme = passage, new task on lookup = query).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Iterable

import numpy as np

logger = logging.getLogger("jira_analytics.embedding")

MODEL_NAME = "intfloat/multilingual-e5-base"
MODEL_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
EMBEDDING_DIM = 768
MODEL_VERSION = f"e5-base-{MODEL_REVISION[:8]}"


class EmbeddingService:
    """Thread-safe singleton. Lazy-loads SentenceTransformer on first use."""

    _instance: "EmbeddingService | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "EmbeddingService":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_done = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_init_done", False):
            return
        self._init_done = True
        self._model = None
        self._model_lock = threading.Lock()

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model
            from sentence_transformers import SentenceTransformer

            cache_folder = os.environ.get("HF_HOME") or None
            logger.info("Loading embedding model %s (rev=%s)", MODEL_NAME, MODEL_REVISION)
            self._model = SentenceTransformer(
                MODEL_NAME,
                revision=MODEL_REVISION,
                cache_folder=cache_folder,
            )
            logger.info("Embedding model loaded")
            return self._model

    def warmup(self) -> None:
        """Eager-load model (used by FastAPI lifespan)."""
        self._ensure_model()
        self.encode_text("warmup")

    def encode_text(self, text: str, *, kind: str = "passage") -> np.ndarray:
        """Encode one text. `kind` ∈ {'passage', 'query'} — e5 prefix."""
        return self.encode_batch([text], kind=kind)[0]

    def encode_batch(self, texts: Iterable[str], *, kind: str = "passage") -> np.ndarray:
        model = self._ensure_model()
        prefix = "query: " if kind == "query" else "passage: "
        prepared = [prefix + (t or "") for t in texts]
        vecs = model.encode(
            prepared,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32, copy=False)
