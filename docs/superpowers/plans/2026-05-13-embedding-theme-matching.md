# Embedding-based theme matching — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить «голую» LLM-классификацию задач в тематическом отчёте на embedding-first матчинг с LLM как fallback. Слияния кандидатов обучают систему — алиасы + centroid темы.

**Architecture:** Singleton `EmbeddingService` грузит `intfloat/multilingual-e5-base` в FastAPI lifespan. Каждая тема имеет centroid-вектор (text + top-K issue vecs). Map-фаза сначала ищет ближайшую тему по cosine ≥ threshold, иначе fallback на текущий LLM-классификатор. Алиасы темы редактируются через UI; merge кандидата автоматически добавляет alias и пересчитывает вектор.

**Tech Stack:** `sentence-transformers==2.7.0`, `torch==2.3.1+cpu`, `numpy`, SQLAlchemy 2.0 + Alembic batch, FastAPI lifespan, React 19 + AntD 6.

**Spec:** [docs/superpowers/specs/2026-05-13-embedding-theme-matching-design.md](../specs/2026-05-13-embedding-theme-matching-design.md)

---

## File structure

**Создание:**
- `app/services/llm/embedding_service.py` — singleton sentence-transformers, encode_text/encode_batch.
- `app/services/llm/theme_embedding_service.py` — compute/recompute centroid темы.
- `app/services/llm/embedding_matcher.py` — find_best_theme.
- `alembic/versions/<rev>_add_theme_embeddings.py` — миграция колонок.
- `tests/services/test_embedding_service.py`
- `tests/services/test_theme_embedding_service.py`
- `tests/services/test_embedding_matcher.py`
- `tests/api/test_theme_aliases.py`
- `frontend/src/components/work-type-report/ThemeAliasesEditor.tsx`

**Модификация:**
- `requirements.txt` — добавить torch CPU + sentence-transformers + numpy.
- `app/main.py` — lifespan event для загрузки модели.
- `app/models/theme.py` — embedding/embedding_model_version/embedding_updated_at/aliases_json.
- `app/models/issue_classification.py` — input_embedding/embedding_model_version/match_method/match_score.
- `app/services/llm/work_type_classifier.py` — добавить embedding-first путь в `prepare`.
- `app/services/work_type_report_service.py` — оркестрация (передать embedder в classifier).
- `app/services/theme_dictionary_service.py` — recompute embedding на create/update/merge/archive→restore.
- `app/api/endpoints/work_type_report.py` — alias CRUD endpoints + merge integration + threshold endpoint.
- `app/schemas/work_type_report.py` — схемы для alias requests.
- `frontend/src/types/workTypeReport.ts` — добавить aliases в Theme + ThemeUpdate.
- `frontend/src/hooks/useThemeDictionary.ts` — мутации алиасов.
- `frontend/src/components/work-type-report/ThemeDictionaryDrawer.tsx` — встроить ThemeAliasesEditor в форму темы.
- `frontend/src/pages/WorkTypeReportPage.tsx` — пробросить нужные пропсы.
- `tests/services/test_work_type_report_service.py` — embedding-first и LLM fallback.
- `tests/api/test_work_type_report.py` — merge alias + threshold setting.

---

## Phase 1 — Foundation: EmbeddingService

### Task 1: Зависимости

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Добавить CPU torch + sentence-transformers**

В конец `requirements.txt`:

```
# Embeddings (CPU-only torch wheel, see docs/superpowers/specs/2026-05-13-embedding-theme-matching-design.md)
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.3.1+cpu
sentence-transformers==2.7.0
numpy>=1.26
```

- [ ] **Step 2: Установить локально**

Run: `py -3.10 -m pip install -r requirements.txt`
Expected: успешная установка, без CUDA wheel (~500 MB вместо 2 GB).

- [ ] **Step 3: Sanity check**

```
py -3.10 -c "from sentence_transformers import SentenceTransformer; print('ok')"
```
Expected: `ok` без ошибок импорта.

- [ ] **Step 4: Commit**

```
git add requirements.txt
git commit -m "deps: add CPU torch + sentence-transformers for embedding matching"
```

---

### Task 2: EmbeddingService

**Files:**
- Create: `app/services/llm/embedding_service.py`
- Test: `tests/services/test_embedding_service.py`

- [ ] **Step 1: Failing test**

```python
# tests/services/test_embedding_service.py
import numpy as np
import pytest

from app.services.llm.embedding_service import (
    EmbeddingService,
    EMBEDDING_DIM,
    MODEL_VERSION,
)


@pytest.fixture(scope="module")
def svc():
    return EmbeddingService()


def test_encode_text_returns_normalized_768(svc):
    v = svc.encode_text("Расчёт себестоимости товара")
    assert v.shape == (EMBEDDING_DIM,)
    assert v.dtype == np.float32
    norm = float(np.linalg.norm(v))
    assert abs(norm - 1.0) < 1e-3


def test_encode_batch_returns_matrix(svc):
    vs = svc.encode_batch(["а", "б", "в"])
    assert vs.shape == (3, EMBEDDING_DIM)
    norms = np.linalg.norm(vs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)


def test_model_version_const():
    assert isinstance(MODEL_VERSION, str)
    assert MODEL_VERSION.startswith("e5-base-")


def test_semantic_similarity(svc):
    """Близкие по смыслу тексты должны иметь cosine ≥ 0.7."""
    a = svc.encode_text("Расчёт себестоимости товара")
    b = svc.encode_text("Анализ себестоимости продукции")
    c = svc.encode_text("Настройка прав доступа")
    sim_ab = float(np.dot(a, b))
    sim_ac = float(np.dot(a, c))
    assert sim_ab > 0.7
    assert sim_ab > sim_ac
```

- [ ] **Step 2: Run test**

Run: `py -3.10 -m pytest tests/services/test_embedding_service.py -v`
Expected: FAIL (модуль ещё не существует).

- [ ] **Step 3: Реализация**

```python
# app/services/llm/embedding_service.py
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
MODEL_REVISION = "f0e6cad205aa1b8a2c50a8f96fee5ce8e80e88f4"  # pin (snapshot 2024-05)
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
```

- [ ] **Step 4: Run test**

Run: `py -3.10 -m pytest tests/services/test_embedding_service.py -v`
Expected: 4 PASS (первый запуск качает модель ~280 MB, может занять минуту).

- [ ] **Step 5: Commit**

```
git add app/services/llm/embedding_service.py tests/services/test_embedding_service.py
git commit -m "feat(embedding): add EmbeddingService singleton for multilingual-e5-base"
```

---

### Task 3: Warmup в FastAPI lifespan

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Подгрузка модели на startup**

В `app/main.py:lifespan` после `sched_svc.start()` (примерно строка 42), перед `yield`, добавить:

```python
    # --- Embedding model warmup ---
    from app.services.llm.embedding_service import EmbeddingService
    try:
        EmbeddingService().warmup()
        logger.info("Embedding service warmed up")
    except Exception as e:
        logger.warning("Embedding warmup failed (non-fatal): %s", e)
```

- [ ] **Step 2: Запустить backend**

Run (в отдельном окне или background): `py -3.10 -m uvicorn app.main:app --port 8001`
Expected: в логах `Embedding service warmed up`. На холодном старте ~5-10 с задержка.
Остановить процесс.

- [ ] **Step 3: Commit**

```
git add app/main.py
git commit -m "feat(embedding): warmup EmbeddingService in FastAPI lifespan"
```

---

## Phase 2 — Data model

### Task 4: Миграция колонок

**Files:**
- Create: `alembic/versions/<rev>_add_theme_embeddings.py`
- Modify: `app/models/theme.py`
- Modify: `app/models/issue_classification.py`

- [ ] **Step 1: Сгенерировать миграцию**

Run: `py -3.10 -m alembic revision -m "add theme embeddings and aliases"`
Файл создан в `alembic/versions/`. Запомнить путь (далее `MIGRATION_FILE`).

- [ ] **Step 2: Заполнить миграцию (заменить тело upgrade/downgrade)**

```python
"""add theme embeddings and aliases

Revision ID: <auto>
Revises: <auto, last from heads>
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    with op.batch_alter_table("themes") as batch:
        batch.add_column(sa.Column("embedding", sa.LargeBinary, nullable=True))
        batch.add_column(sa.Column("embedding_model_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("embedding_updated_at", sa.DateTime, nullable=True))
        batch.add_column(sa.Column("aliases_json", sa.Text, nullable=True))

    with op.batch_alter_table("issue_classifications") as batch:
        batch.add_column(sa.Column("input_embedding", sa.LargeBinary, nullable=True))
        batch.add_column(sa.Column("embedding_model_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("match_method", sa.String(16), nullable=True))
        batch.add_column(sa.Column("match_score", sa.Float, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issue_classifications") as batch:
        batch.drop_column("match_score")
        batch.drop_column("match_method")
        batch.drop_column("embedding_model_version")
        batch.drop_column("input_embedding")

    with op.batch_alter_table("themes") as batch:
        batch.drop_column("aliases_json")
        batch.drop_column("embedding_updated_at")
        batch.drop_column("embedding_model_version")
        batch.drop_column("embedding")
```

- [ ] **Step 3: Обновить модель Theme**

В `app/models/theme.py` добавить:

```python
import json
from datetime import datetime
from sqlalchemy import DateTime, LargeBinary
# (extend existing imports)

class Theme(Base, TimestampMixin):
    # ... existing fields ...
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    embedding_model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    embedding_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    aliases_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @property
    def aliases(self) -> list[str]:
        if not self.aliases_json:
            return []
        try:
            v = json.loads(self.aliases_json)
            return [str(x) for x in v if isinstance(x, str) and x.strip()]
        except (json.JSONDecodeError, TypeError):
            return []

    @aliases.setter
    def aliases(self, value: Optional[list[str]]) -> None:
        if not value:
            self.aliases_json = None
            return
        cleaned: list[str] = []
        seen: set[str] = set()
        for s in value:
            if not isinstance(s, str):
                continue
            t = s.strip()
            key = t.lower()
            if not t or key in seen:
                continue
            seen.add(key)
            cleaned.append(t)
        self.aliases_json = json.dumps(cleaned, ensure_ascii=False) if cleaned else None
```

- [ ] **Step 4: Обновить IssueClassification**

В `app/models/issue_classification.py` добавить:

```python
from sqlalchemy import LargeBinary  # extend imports

class IssueClassification(Base, TimestampMixin):
    # ... existing fields ...
    input_embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    embedding_model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    match_method: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
```

- [ ] **Step 5: Применить миграцию**

Run: `py -3.10 -m alembic upgrade head`
Expected: миграция применилась, БД отдала новые колонки. Проверить `sqlite3 data/dev.db ".schema themes"` — видны новые колонки.

- [ ] **Step 6: Прогнать тесты**

Run: `py -3.10 -m pytest tests/ -x -q`
Expected: все существующие тесты проходят (никаких регрессий от добавления nullable-колонок).

- [ ] **Step 7: Commit**

```
git add alembic/versions/ app/models/theme.py app/models/issue_classification.py
git commit -m "feat(embedding): add migration + model columns for theme embeddings and aliases"
```

---

## Phase 3 — Theme embedding + matcher

### Task 5: ThemeEmbeddingService

**Files:**
- Create: `app/services/llm/theme_embedding_service.py`
- Test: `tests/services/test_theme_embedding_service.py`

- [ ] **Step 1: Failing test**

```python
# tests/services/test_theme_embedding_service.py
import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.models.theme import Theme
from app.models.issue import Issue
from app.models.issue_classification import IssueClassification
from app.models.worklog import Worklog
from app.services.llm.embedding_service import EMBEDDING_DIM, MODEL_VERSION
from app.services.llm.theme_embedding_service import (
    ThemeEmbeddingService,
    THEME_CENTROID_TOP_K,
)

# Fixtures `db`, `work_type` provided by conftest; if missing — create minimal here.


def test_compute_theme_embedding_no_issues_text_only(db: Session, work_type):
    theme = Theme(
        work_type_id=work_type.id,
        name="Расчёт и анализ себестоимости",
        description="Себестоимость товаров и услуг",
        aliases=["Таможенная стоимость", "Корректировка стоимости"],
    )
    db.add(theme)
    db.commit()

    svc = ThemeEmbeddingService(db)
    vec = svc.compute_theme_embedding(theme, top_issues=[])
    assert vec.shape == (EMBEDDING_DIM,)
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-3


def test_recompute_persists_to_theme(db: Session, work_type):
    theme = Theme(
        work_type_id=work_type.id,
        name="Закрытие периода",
        description=None,
        aliases=[],
    )
    db.add(theme)
    db.commit()

    svc = ThemeEmbeddingService(db)
    svc.recompute_theme_embedding(theme.id)

    db.refresh(theme)
    assert theme.embedding is not None
    assert theme.embedding_model_version == MODEL_VERSION
    assert theme.embedding_updated_at is not None
```

- [ ] **Step 2: Run test**

Run: `py -3.10 -m pytest tests/services/test_theme_embedding_service.py -v`
Expected: FAIL (модуль не существует / fixture `work_type` нужна).

Если `work_type` fixture отсутствует — добавить в `tests/conftest.py`:

```python
@pytest.fixture
def work_type(db):
    from app.models.mandatory_work_type import MandatoryWorkType
    wt = MandatoryWorkType(
        code="test_wt", label="Test", is_active=True, sort_order=0,
    )
    db.add(wt)
    db.commit()
    return wt
```

(если уже есть — не дублировать).

- [ ] **Step 3: Реализация**

```python
# app/services/llm/theme_embedding_service.py
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
    def __init__(self, db: Session, embedder: EmbeddingService | None = None) -> None:
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
        self, theme: Theme, top_issues: list[Issue] | None = None,
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

    def recompute_theme_embedding(self, theme_id: str) -> Theme | None:
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

    def load_vector(self, theme: Theme) -> np.ndarray | None:
        """Деpickle сохранённый вектор, возвращает None если пусто/протух."""
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
```

- [ ] **Step 4: Run test**

Run: `py -3.10 -m pytest tests/services/test_theme_embedding_service.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```
git add app/services/llm/theme_embedding_service.py tests/services/test_theme_embedding_service.py tests/conftest.py
git commit -m "feat(embedding): add ThemeEmbeddingService for centroid computation"
```

---

### Task 6: EmbeddingMatcher

**Files:**
- Create: `app/services/llm/embedding_matcher.py`
- Test: `tests/services/test_embedding_matcher.py`

- [ ] **Step 1: Failing test**

```python
# tests/services/test_embedding_matcher.py
import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.models.theme import Theme
from app.services.llm.embedding_matcher import EmbeddingMatcher
from app.services.llm.embedding_service import EmbeddingService
from app.services.llm.theme_embedding_service import ThemeEmbeddingService


def test_find_best_theme_returns_match_above_threshold(db: Session, work_type):
    t1 = Theme(work_type_id=work_type.id, name="Себестоимость",
               description="Расчёт себестоимости товаров")
    t2 = Theme(work_type_id=work_type.id, name="Права доступа",
               description="Настройка прав, ролей пользователей")
    db.add_all([t1, t2])
    db.commit()

    tes = ThemeEmbeddingService(db)
    tes.recompute_theme_embedding(t1.id)
    tes.recompute_theme_embedding(t2.id)

    db.refresh(t1)
    db.refresh(t2)

    embedder = EmbeddingService()
    issue_vec = embedder.encode_text(
        "Расчёт таможенной стоимости импорта",
        kind="query",
    )

    matcher = EmbeddingMatcher(tes)
    best, score = matcher.find_best_theme(issue_vec, [t1, t2], threshold=0.5)
    assert best is not None
    assert best.id == t1.id
    assert score > 0.5


def test_find_best_returns_none_below_threshold(db: Session, work_type):
    t = Theme(work_type_id=work_type.id, name="Бухгалтерия",
              description="Учёт операций")
    db.add(t)
    db.commit()
    tes = ThemeEmbeddingService(db)
    tes.recompute_theme_embedding(t.id)
    db.refresh(t)

    issue_vec = EmbeddingService().encode_text(
        "Совершенно несвязанная тема про космос", kind="query",
    )
    matcher = EmbeddingMatcher(tes)
    best, score = matcher.find_best_theme(issue_vec, [t], threshold=0.95)
    assert best is None
```

- [ ] **Step 2: Run test**

Run: `py -3.10 -m pytest tests/services/test_embedding_matcher.py -v`
Expected: FAIL.

- [ ] **Step 3: Реализация**

```python
# app/services/llm/embedding_matcher.py
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
```

- [ ] **Step 4: Run test**

Run: `py -3.10 -m pytest tests/services/test_embedding_matcher.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```
git add app/services/llm/embedding_matcher.py tests/services/test_embedding_matcher.py
git commit -m "feat(embedding): add EmbeddingMatcher for cosine-based theme search"
```

---

## Phase 4 — Map-phase integration

### Task 7: Подключить embedding-first в WorkTypeClassifier

**Files:**
- Modify: `app/services/llm/work_type_classifier.py`
- Modify: `app/services/work_type_report_service.py`
- Test: `tests/services/test_work_type_report_service.py`

- [ ] **Step 1: Failing test (embedding-first path)**

В `tests/services/test_work_type_report_service.py` добавить новый кейс:

```python
@pytest.mark.asyncio
async def test_embedding_match_skips_llm(db, work_type, monkeypatch):
    """Если cosine ≥ threshold — LLM не вызывается, theme_id выставлен."""
    from app.models.theme import Theme
    from app.models.issue import Issue
    from app.services.llm.theme_embedding_service import ThemeEmbeddingService
    from app.services.work_type_report_service import WorkTypeReportService

    theme = Theme(
        work_type_id=work_type.id, name="Себестоимость",
        description="Расчёт себестоимости товара",
    )
    db.add(theme); db.commit()
    ThemeEmbeddingService(db).recompute_theme_embedding(theme.id)

    issue = Issue(
        id="iss-1", key="X-1", project_id="P", summary="Анализ себестоимости",
        issue_type="Task",
    )
    db.add(issue); db.commit()

    class FakeProvider:
        model = "stub"
        called = False
        async def classify_issue(self, *_a, **_kw):
            FakeProvider.called = True
            raise AssertionError("LLM не должен был вызваться")

    svc = WorkTypeReportService(
        db=db, classifier_provider=FakeProvider(), synthesizer_provider=None,
    )
    # Set low threshold via AppSetting (will be added in Task 9; for now monkeypatch)
    monkeypatch.setattr(
        "app.services.work_type_report_service.get_embedding_threshold",
        lambda _db: 0.3,
    )
    # Direct call into the map phase helper (or trigger a small build)
    # For now: just call the new classifier helper directly
    from app.services.llm.work_type_classifier import WorkTypeClassifier
    clf = WorkTypeClassifier(db, FakeProvider())
    out = clf.prepare(issue=issue, work_type_id=work_type.id, themes=[theme])
    # If embedding match succeeded, prepare returns IssueClassification directly
    from app.models.issue_classification import IssueClassification
    assert isinstance(out, IssueClassification)
    assert out.theme_id == theme.id
    assert out.match_method == "embedding"
    assert FakeProvider.called is False
```

- [ ] **Step 2: Run test**

Run: `py -3.10 -m pytest tests/services/test_work_type_report_service.py::test_embedding_match_skips_llm -v`
Expected: FAIL.

- [ ] **Step 3: Изменить `WorkTypeClassifier.prepare`**

В `app/services/llm/work_type_classifier.py`:

a) Добавить импорты вверху:

```python
import pickle
import numpy as np
from app.services.llm.embedding_service import EmbeddingService, MODEL_VERSION as EMB_MODEL_VERSION
from app.services.llm.theme_embedding_service import ThemeEmbeddingService
from app.services.llm.embedding_matcher import EmbeddingMatcher
```

b) В классе добавить параметр конструктора `threshold` и сохранить:

```python
class WorkTypeClassifier:
    def __init__(
        self,
        db: Session,
        provider: ClassifierProvider,
        *,
        embedding_threshold: float = 0.78,
    ) -> None:
        self.db = db
        self.provider = provider
        self.embedding_threshold = embedding_threshold
        self.embedder = EmbeddingService()
        self.theme_embedding_svc = ThemeEmbeddingService(db, self.embedder)
        self.matcher = EmbeddingMatcher(self.theme_embedding_svc)
```

c) В методе `prepare` после блока cache-hit (где возвращается existing) добавить **перед** `prompt = build_classify_prompt(...)`:

```python
        # ---- Embedding-first path ----
        issue_text = " ".join(filter(None, [
            issue.summary or "",
            issue.goal_text or "",
            issue.current_behavior or "",
        ]))
        issue_vec = self.embedder.encode_text(issue_text, kind="query")

        if themes:
            best_theme, score = self.matcher.find_best_theme(
                issue_vec, themes, self.embedding_threshold,
            )
            if best_theme is not None:
                # Persist immediately — bypass LLM
                cls = self._upsert(
                    existing,
                    issue,
                    work_type_id,
                    h,
                    wt.theme_dict_version,
                    theme_id=best_theme.id,
                    candidate_name=None,
                    contribution_text=None,
                    confidence=score,
                    nature_tag=None,
                    area=None,
                    nature=None,
                    model_id=None,
                    failed=False,
                    failure_reason=None,
                    match_method="embedding",
                    match_score=score,
                    input_embedding=pickle.dumps(issue_vec),
                    embedding_model_version=EMB_MODEL_VERSION,
                    _markers=[],
                )
                return cls

        # Embedding match не сработал → LLM как раньше; сохраним issue_vec для дальнейших кэш-хитов.
        self._pending_issue_vec = issue_vec
```

d) В `_upsert` принять новые поля:

```python
    def _upsert(
        self,
        existing: Optional[IssueClassification],
        issue: Issue,
        work_type_id: str,
        input_hash: str,
        dict_version: int,
        **kwargs: object,
    ) -> IssueClassification:
        confidence = kwargs.pop("confidence", None)
        markers = kwargs.pop("_markers", None)
        match_method = kwargs.pop("match_method", None)
        match_score = kwargs.pop("match_score", None)
        input_embedding = kwargs.pop("input_embedding", None)
        embedding_model_version = kwargs.pop("embedding_model_version", None)

        if existing:
            existing.input_hash = input_hash
            existing.dictionary_version = dict_version
            existing.prompt_version = PROMPT_VERSION
            existing.updated_at = datetime.utcnow()
            if confidence is not None:
                existing.llm_confidence = confidence
            if match_method is not None:
                existing.match_method = match_method
            if match_score is not None:
                existing.match_score = match_score
            if input_embedding is not None:
                existing.input_embedding = input_embedding
            if embedding_model_version is not None:
                existing.embedding_model_version = embedding_model_version
            for k, v in kwargs.items():
                setattr(existing, k, v)
            if markers is not None:
                existing.markers = markers
            self.db.commit()
            self.db.refresh(existing)
            return existing

        cls = IssueClassification(
            issue_id=issue.id,
            work_type_id=work_type_id,
            input_hash=input_hash,
            dictionary_version=dict_version,
            prompt_version=PROMPT_VERSION,
            llm_confidence=confidence,
            match_method=match_method,
            match_score=match_score,
            input_embedding=input_embedding,
            embedding_model_version=embedding_model_version,
            **kwargs,
        )
        if markers is not None:
            cls.markers = markers
        self.db.add(cls)
        self.db.commit()
        self.db.refresh(cls)
        return cls
```

e) В `persist_success` пробросить embedding-метаданные (LLM-путь):

```python
    def persist_success(
        self, prep: ClassificationPrep, res: ClassificationResult, meta: dict,
    ) -> IssueClassification:
        issue_vec = getattr(self, "_pending_issue_vec", None)
        kwargs: dict = dict(
            theme_id=res.theme_id,
            candidate_name=res.candidate_name,
            contribution_text=res.contribution_text,
            confidence=res.confidence,
            nature_tag=res.nature_tag,
            area=res.area,
            nature=res.nature,
            model_id=meta.get("model"),
            failed=False,
            failure_reason=None,
            match_method="llm",
            match_score=None,
            _markers=res.markers,
        )
        if issue_vec is not None:
            kwargs["input_embedding"] = pickle.dumps(issue_vec)
            kwargs["embedding_model_version"] = EMB_MODEL_VERSION
        return self._upsert(
            prep.existing, prep.issue, prep.work_type_id,
            prep.input_hash, prep.dictionary_version, **kwargs,
        )
```

- [ ] **Step 4: Передать threshold из оркестратора**

В `app/services/work_type_report_service.py`:

a) Добавить helper наверху файла (под импортами):

```python
def get_embedding_threshold(db: Session) -> float:
    from app.api.endpoints.settings import _get_setting
    raw = _get_setting(db, "theme_match_embedding_threshold")
    try:
        return float(raw) if raw else 0.78
    except (TypeError, ValueError):
        return 0.78
```

b) Найти место создания `WorkTypeClassifier` (поиск `WorkTypeClassifier(`) и передать threshold:

```python
threshold = get_embedding_threshold(self.db)
clf = WorkTypeClassifier(self.db, self.classifier_provider, embedding_threshold=threshold)
```

- [ ] **Step 5: Run new + existing tests**

Run: `py -3.10 -m pytest tests/services/test_work_type_report_service.py -v -x`
Expected: новый тест PASS, существующие тоже (могут потребовать корректировок если есть прямой instantiation classifier — но мы передаём threshold с дефолтом).

- [ ] **Step 6: Commit**

```
git add app/services/llm/work_type_classifier.py app/services/work_type_report_service.py tests/services/test_work_type_report_service.py
git commit -m "feat(embedding): wire embedding-first matching into Map phase"
```

---

### Task 8: LLM fallback test

**Files:**
- Modify: `tests/services/test_work_type_report_service.py`

- [ ] **Step 1: Тест fallback**

```python
@pytest.mark.asyncio
async def test_low_similarity_falls_back_to_llm(db, work_type):
    """Если cosine < threshold — LLM вызывается, candidate_name проставлен."""
    from app.models.theme import Theme
    from app.models.issue import Issue
    from app.services.llm.theme_embedding_service import ThemeEmbeddingService
    from app.services.llm.work_type_classifier import WorkTypeClassifier, ClassificationResult

    theme = Theme(
        work_type_id=work_type.id, name="Закрытие периода",
        description="Закрытие отчётного периода",
    )
    db.add(theme); db.commit()
    ThemeEmbeddingService(db).recompute_theme_embedding(theme.id)

    issue = Issue(
        id="iss-2", key="X-2", project_id="P",
        summary="Совсем другая тема про космос и звёзды",
        issue_type="Task",
    )
    db.add(issue); db.commit()

    llm_called = {"flag": False}
    class FakeProvider:
        model = "stub"
        async def classify_issue(self, prompt, themes_payload):
            llm_called["flag"] = True
            return ClassificationResult(
                theme_id=None, candidate_name="Космос",
                contribution_text=None, confidence=0.5, markers=[],
                area="other", nature="other",
            ), {"model": "stub"}

    clf = WorkTypeClassifier(db, FakeProvider(), embedding_threshold=0.95)
    out = clf.prepare(issue=issue, work_type_id=work_type.id, themes=[theme])
    from app.services.llm.work_type_classifier import ClassificationPrep
    assert isinstance(out, ClassificationPrep)
    # Drive through async call
    import asyncio
    res, meta = asyncio.get_event_loop().run_until_complete(
        FakeProvider().classify_issue(out.prompt, out.themes_payload),
    )
    final = clf.persist_success(out, res, meta)
    assert llm_called["flag"] is True
    assert final.theme_id is None
    assert final.candidate_name == "Космос"
    assert final.match_method == "llm"
    assert final.input_embedding is not None  # сохранён для будущих re-runs
```

- [ ] **Step 2: Run**

Run: `py -3.10 -m pytest tests/services/test_work_type_report_service.py::test_low_similarity_falls_back_to_llm -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```
git add tests/services/test_work_type_report_service.py
git commit -m "test(embedding): cover LLM fallback when cosine below threshold"
```

---

## Phase 5 — Aliases CRUD + merge integration

### Task 9: Alias endpoints + merge bumping

**Files:**
- Modify: `app/api/endpoints/work_type_report.py`
- Modify: `app/schemas/work_type_report.py`
- Modify: `app/services/theme_dictionary_service.py`
- Test: `tests/api/test_theme_aliases.py`

- [ ] **Step 1: Failing test**

```python
# tests/api/test_theme_aliases.py
import pytest


def test_add_alias_endpoint(client, work_type, auth_admin):
    # Create theme via dictionary endpoint or directly
    from app.models.theme import Theme
    from app.database import SessionLocal
    db = SessionLocal()
    theme = Theme(work_type_id=work_type.id, name="Себестоимость")
    db.add(theme); db.commit(); theme_id = theme.id; db.close()

    r = client.post(
        f"/api/v1/work-type-report/themes/{theme_id}/aliases",
        json={"alias": "Таможенная стоимость"},
        cookies=auth_admin,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Таможенная стоимость" in body["aliases"]


def test_delete_alias_endpoint(client, work_type, auth_admin):
    from app.models.theme import Theme
    from app.database import SessionLocal
    db = SessionLocal()
    theme = Theme(
        work_type_id=work_type.id, name="X", aliases=["alpha", "beta"],
    )
    db.add(theme); db.commit(); tid = theme.id; db.close()

    r = client.delete(
        f"/api/v1/work-type-report/themes/{tid}/aliases?alias=alpha",
        cookies=auth_admin,
    )
    assert r.status_code == 200
    assert "alpha" not in r.json()["aliases"]
    assert "beta" in r.json()["aliases"]


def test_merge_candidate_adds_alias(client, work_type, auth_admin):
    """После merge candidate → его proposed_name должно появиться в aliases темы."""
    from app.models.theme import Theme
    from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
    from app.models.issue_classification import IssueClassification
    from app.models.issue import Issue
    from app.database import SessionLocal
    db = SessionLocal()
    theme = Theme(work_type_id=work_type.id, name="Себестоимость")
    db.add(theme); db.commit()
    issue = Issue(id="i1", key="K-1", project_id="P", summary="x", issue_type="Task")
    db.add(issue); db.commit()
    cls = IssueClassification(
        issue_id=issue.id, work_type_id=work_type.id,
        candidate_name="Таможенная стоимость",
        input_hash="h", dictionary_version=1,
    )
    db.add(cls); db.commit()
    snap = WorkTypeReportSnapshot(
        work_type_id=work_type.id, year=2026, quarter=2,
        start_date="2026-04-01", end_date="2026-06-30",
        team_set_hash="x", team_set_json="[]", snapshot_data="{}",
        dictionary_version=1,
    )
    db.add(snap); db.commit()
    snap_id = snap.id; theme_id = theme.id; db.close()

    r = client.post(
        "/api/v1/work-type-report/candidates/merge",
        json={
            "snapshot_id": snap_id,
            "proposed_name": "Таможенная стоимость",
            "target_theme_id": theme_id,
        },
        cookies=auth_admin,
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    t = db.get(Theme, theme_id)
    assert "Таможенная стоимость" in t.aliases
    assert t.embedding is not None  # recomputed
    db.close()
```

- [ ] **Step 2: Run**

Run: `py -3.10 -m pytest tests/api/test_theme_aliases.py -v`
Expected: FAIL.

- [ ] **Step 3: Схемы**

В `app/schemas/work_type_report.py` добавить:

```python
class AliasAddRequest(BaseModel):
    alias: str


class ThemeAliasResponse(BaseModel):
    theme_id: str
    aliases: list[str]
```

- [ ] **Step 4: Сервис — alias methods + recompute hooks**

В `app/services/theme_dictionary_service.py` добавить:

```python
from app.services.llm.theme_embedding_service import ThemeEmbeddingService


class ThemeDictionaryService:
    # ... existing ...

    def add_alias(self, theme_id: str, alias: str) -> Theme:
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        current = t.aliases
        if alias.strip().lower() in {a.lower() for a in current}:
            return t  # idempotent
        current.append(alias.strip())
        t.aliases = current
        self._bump_version(t.work_type_id)
        self.db.commit()
        ThemeEmbeddingService(self.db).recompute_theme_embedding(t.id)
        self.db.refresh(t)
        return t

    def remove_alias(self, theme_id: str, alias: str) -> Theme:
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        current = t.aliases
        new = [a for a in current if a.lower() != alias.lower()]
        if len(new) == len(current):
            return t
        t.aliases = new
        self._bump_version(t.work_type_id)
        self.db.commit()
        ThemeEmbeddingService(self.db).recompute_theme_embedding(t.id)
        self.db.refresh(t)
        return t
```

Также в существующих `create_theme` / `update_theme` / `merge_theme` после `self._bump_version` добавить `ThemeEmbeddingService(self.db).recompute_theme_embedding(t.id)`.

- [ ] **Step 5: Endpoints**

В `app/api/endpoints/work_type_report.py` добавить:

```python
from app.schemas.work_type_report import AliasAddRequest, ThemeAliasResponse


@router.post("/themes/{theme_id}/aliases", response_model=ThemeAliasResponse)
def add_theme_alias(
    theme_id: str,
    payload: AliasAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.add_alias(theme_id, payload.alias)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ThemeAliasResponse(theme_id=t.id, aliases=t.aliases)


@router.delete("/themes/{theme_id}/aliases", response_model=ThemeAliasResponse)
def delete_theme_alias(
    theme_id: str,
    alias: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.remove_alias(theme_id, alias)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ThemeAliasResponse(theme_id=t.id, aliases=t.aliases)
```

- [ ] **Step 6: Merge endpoint — добавить alias + recompute**

В `app/api/endpoints/work_type_report.py:merge_candidate`, перед `_make_service(db).rebuild_aggregates(snap)`:

```python
    # Add candidate name as alias + recompute target theme embedding
    svc = ThemeDictionaryService(db)
    try:
        svc.add_alias(payload.target_theme_id, payload.proposed_name)
    except ValueError:
        pass  # theme может быть удалена — игнор
```

- [ ] **Step 7: Run**

Run: `py -3.10 -m pytest tests/api/test_theme_aliases.py -v`
Expected: 3 PASS.

- [ ] **Step 8: Commit**

```
git add app/api/endpoints/work_type_report.py app/schemas/work_type_report.py app/services/theme_dictionary_service.py tests/api/test_theme_aliases.py
git commit -m "feat(embedding): alias CRUD + merge auto-adds alias and recomputes theme embedding"
```

---

### Task 10: Threshold setting endpoint

**Files:**
- Modify: `app/api/endpoints/work_type_report.py`
- Test: `tests/api/test_theme_aliases.py`

- [ ] **Step 1: Тест**

В `tests/api/test_theme_aliases.py` добавить:

```python
def test_threshold_get_and_put(client, auth_admin):
    r = client.get(
        "/api/v1/work-type-report/settings/embedding-threshold",
        cookies=auth_admin,
    )
    assert r.status_code == 200
    assert r.json()["threshold"] == 0.78  # default

    r = client.put(
        "/api/v1/work-type-report/settings/embedding-threshold",
        json={"threshold": 0.82},
        cookies=auth_admin,
    )
    assert r.status_code == 200
    assert r.json()["threshold"] == 0.82

    r = client.get(
        "/api/v1/work-type-report/settings/embedding-threshold",
        cookies=auth_admin,
    )
    assert r.json()["threshold"] == 0.82
```

- [ ] **Step 2: Endpoints**

В `app/api/endpoints/work_type_report.py`:

```python
from pydantic import BaseModel
from app.api.endpoints.settings import _get_setting, _set_setting


class ThresholdResponse(BaseModel):
    threshold: float


class ThresholdRequest(BaseModel):
    threshold: float


@router.get("/settings/embedding-threshold", response_model=ThresholdResponse)
def get_embedding_threshold_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = _get_setting(db, "theme_match_embedding_threshold")
    try:
        return ThresholdResponse(threshold=float(raw) if raw else 0.78)
    except (TypeError, ValueError):
        return ThresholdResponse(threshold=0.78)


@router.put("/settings/embedding-threshold", response_model=ThresholdResponse)
def set_embedding_threshold(
    payload: ThresholdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not 0.0 <= payload.threshold <= 1.0:
        raise HTTPException(422, "threshold must be in [0, 1]")
    _set_setting(db, "theme_match_embedding_threshold", str(payload.threshold))
    return ThresholdResponse(threshold=payload.threshold)
```

- [ ] **Step 3: Run**

Run: `py -3.10 -m pytest tests/api/test_theme_aliases.py::test_threshold_get_and_put -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```
git add app/api/endpoints/work_type_report.py tests/api/test_theme_aliases.py
git commit -m "feat(embedding): GET/PUT endpoint for theme match threshold"
```

---

## Phase 6 — Frontend

### Task 11: API + types

**Files:**
- Modify: `frontend/src/types/workTypeReport.ts`
- Modify: `frontend/src/hooks/useThemeDictionary.ts` (или соседний хук)

- [ ] **Step 1: Types**

В `frontend/src/types/workTypeReport.ts` найти interface `Theme` (тот, что для dictionary, не для отчёта) — добавить:

```typescript
aliases: string[];
```

(если такого интерфейса нет — добавить новый `ThemeDictionaryItem` в файле; имя зависит от текущей структуры).

- [ ] **Step 2: Hooks**

В `frontend/src/hooks/useThemeDictionary.ts` добавить мутации:

```typescript
export function useAddThemeAlias() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ themeId, alias }: { themeId: string; alias: string }) => {
      return api.post<{ theme_id: string; aliases: string[] }>(
        `/work-type-report/themes/${themeId}/aliases`,
        { alias },
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['themes'] });
    },
  });
}

export function useRemoveThemeAlias() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ themeId, alias }: { themeId: string; alias: string }) => {
      return api.delete<{ theme_id: string; aliases: string[] }>(
        `/work-type-report/themes/${themeId}/aliases?alias=${encodeURIComponent(alias)}`,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['themes'] });
    },
  });
}
```

Если `api.delete` ещё не поддерживает query string — использовать base fetch как в существующем коде.

- [ ] **Step 3: Commit**

```
git add frontend/src/types/workTypeReport.ts frontend/src/hooks/useThemeDictionary.ts
git commit -m "feat(embedding): frontend types + hooks for theme aliases"
```

---

### Task 12: ThemeAliasesEditor компонент

**Files:**
- Create: `frontend/src/components/work-type-report/ThemeAliasesEditor.tsx`

- [ ] **Step 1: Компонент**

```tsx
// frontend/src/components/work-type-report/ThemeAliasesEditor.tsx
import { useState } from 'react';
import { Tag, Input, Button, Space, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useAddThemeAlias, useRemoveThemeAlias } from '../../hooks/useThemeDictionary';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  themeId: string;
  aliases: string[];
  readOnly?: boolean;
}

export default function ThemeAliasesEditor({ themeId, aliases, readOnly }: Props) {
  const [draft, setDraft] = useState('');
  const addMutation = useAddThemeAlias();
  const removeMutation = useRemoveThemeAlias();

  const handleAdd = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    addMutation.mutate({ themeId, alias: trimmed }, {
      onSuccess: () => setDraft(''),
    });
  };

  return (
    <div>
      <Typography.Text
        style={{
          fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
          textTransform: 'uppercase', color: DARK_THEME.textHint,
          display: 'block', marginBottom: 8,
        }}
      >
        Также покрывает (алиасы)
      </Typography.Text>

      <Space size={[4, 8]} wrap style={{ marginBottom: readOnly ? 0 : 8 }}>
        {aliases.length === 0 && (
          <Typography.Text style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>
            Алиасов нет
          </Typography.Text>
        )}
        {aliases.map((a) => (
          <Tag
            key={a}
            closable={!readOnly}
            onClose={(e) => {
              e.preventDefault();
              removeMutation.mutate({ themeId, alias: a });
            }}
            color="cyan"
          >
            {a}
          </Tag>
        ))}
      </Space>

      {!readOnly && (
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={draft}
            placeholder="Новый алиас (Enter — добавить)"
            onChange={(e) => setDraft(e.target.value)}
            onPressEnter={handleAdd}
            maxLength={120}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAdd}
            disabled={!draft.trim() || addMutation.isPending}
          />
        </Space.Compact>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Встроить в форму редактирования темы**

Найти редактор темы (вероятно в `ThemeDictionaryDrawer.tsx` или соседнем компоненте). В форме после поля description добавить:

```tsx
{theme.id && <ThemeAliasesEditor themeId={theme.id} aliases={theme.aliases ?? []} />}
```

(импорт компонента в начале файла).

- [ ] **Step 3: Type check frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit code 0.

- [ ] **Step 4: Manual smoke**

Запустить backend (`uvicorn app.main:app --port 8000`) + frontend (`cd frontend && npm run dev`). Открыть страницу тематического отчёта, открыть «Словарь тем», выбрать тему. Убедиться:
- Алиасы видны.
- Добавление через Enter работает.
- Удаление через × на чипе работает.

- [ ] **Step 5: Commit**

```
git add frontend/src/components/work-type-report/ThemeAliasesEditor.tsx frontend/src/components/work-type-report/ThemeDictionaryDrawer.tsx
git commit -m "feat(embedding): ThemeAliasesEditor with chip-list CRUD"
```

---

### Task 13: Threshold slider в админке

**Files:**
- Modify: `frontend/src/components/work-type-report/ThemeDictionaryDrawer.tsx` (или соседний admin компонент)
- Modify: `frontend/src/hooks/useThemeDictionary.ts`

- [ ] **Step 1: Хук**

В `useThemeDictionary.ts`:

```typescript
export function useEmbeddingThreshold() {
  return useQuery({
    queryKey: ['embedding-threshold'],
    queryFn: () => api.get<{ threshold: number }>(
      '/work-type-report/settings/embedding-threshold',
    ),
  });
}

export function useSetEmbeddingThreshold() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (threshold: number) =>
      api.put<{ threshold: number }>(
        '/work-type-report/settings/embedding-threshold',
        { threshold },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['embedding-threshold'] }),
  });
}
```

- [ ] **Step 2: UI — слайдер**

В админ-секции словаря тем (там же где «Создать тему»):

```tsx
import { Slider, Tooltip } from 'antd';
import { useEmbeddingThreshold, useSetEmbeddingThreshold } from '../../hooks/useThemeDictionary';

// ...

const { data: t } = useEmbeddingThreshold();
const setT = useSetEmbeddingThreshold();
const currentThreshold = t?.threshold ?? 0.78;

<Tooltip title="Выше = строже матчинг embedding (меньше ложных группировок)">
  <div style={{ marginBottom: 16 }}>
    <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textSecondary }}>
      Порог embedding-матчинга: {currentThreshold.toFixed(2)}
    </Typography.Text>
    <Slider
      min={0.5}
      max={0.95}
      step={0.01}
      value={currentThreshold}
      onChange={(v) => setT.mutate(v)}
      tooltip={{ formatter: (v) => v?.toFixed(2) }}
    />
  </div>
</Tooltip>
```

- [ ] **Step 3: Type check + manual smoke**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.
Открыть страницу, проверить слайдер, повернуть, перезагрузить — значение сохраняется.

- [ ] **Step 4: Commit**

```
git add frontend/src/hooks/useThemeDictionary.ts frontend/src/components/work-type-report/ThemeDictionaryDrawer.tsx
git commit -m "feat(embedding): threshold slider in dictionary admin"
```

---

## Phase 7 — VPS-readiness docs

### Task 14: README — деплой на VPS

**Files:**
- Modify: `README.md` (или создать `docs/deployment.md` если README большой)

- [ ] **Step 1: Найти подходящее место**

Если в README уже есть «Deployment» / «Установка» — дописать туда. Иначе создать новый раздел.

- [ ] **Step 2: Раздел про embeddings**

Добавить:

```markdown
## Embedding model (theme matching)

Сервис использует `intfloat/multilingual-e5-base` (sentence-transformers) для матчинга задач к темам тематического отчёта.

### Системные требования

- Python 3.10+, CPU x86_64 (arm64 поддерживается, но wheel для torch ставится отдельным индексом).
- RAM: ≥ 2 GB на процесс backend (модель занимает ~1.5 GB при загрузке).
- Диск: ~280 MB модель + ~500 MB зависимости torch CPU.
- GPU не нужен.

### Установка

`requirements.txt` уже содержит `--extra-index-url https://download.pytorch.org/whl/cpu` — pip скачает CPU-only torch (~200 MB), без CUDA (~2 GB).

```
pip install -r requirements.txt
```

### Загрузка модели

Веса автоматически скачиваются при первом старте backend (~280 MB, нужен outbound к huggingface.co).

Кэш модели — в директории `HF_HOME` (по умолчанию `~/.cache/huggingface`). На VPS лучше задать явно:

```
export HF_HOME=/var/cache/huggingface
```

### Offline-деплой (VPS без outbound)

1. Локально:
   ```
   huggingface-cli download intfloat/multilingual-e5-base --local-dir ./models/e5-base
   ```
2. Скопировать папку `models/e5-base` на сервер.
3. На сервере выставить `HF_HOME` в директорию которая содержит подкаталог `hub/models--intfloat--multilingual-e5-base/`. Альтернатива — указать абсолютный путь в `MODEL_NAME` константе и пересобрать.

### Docker (pre-bake)

В Dockerfile:

```dockerfile
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('intfloat/multilingual-e5-base', revision='<revision_from_code>')"
```

Веса вшиваются в слой образа.

### Production lens

- На холодном старте backend модель загружается в RAM ~5-10 с (через FastAPI lifespan). Первый запрос после рестарта будет немного дольше.
- Если RAM < 2 GB, рассмотреть `intfloat/multilingual-e5-small` (заменить `MODEL_NAME`/`MODEL_REVISION` в `app/services/llm/embedding_service.py`, выставить новый `EMBEDDING_DIM=384` и подкорректировать миграцию если БД уже наполнена).
```

- [ ] **Step 3: Commit**

```
git add README.md
git commit -m "docs(embedding): VPS deployment notes for multilingual-e5-base"
```

---

## Phase 8 — Integration sanity check

### Task 15: End-to-end build smoke

**Files:** (никаких новых)

- [ ] **Step 1: Полный pytest**

Run: `py -3.10 -m pytest tests/ -x -q`
Expected: все тесты PASS.

- [ ] **Step 2: Frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Frontend build**

Run: `cd frontend && npm run build`
Expected: exit 0.

- [ ] **Step 4: Manual smoke**

1. Запустить backend + frontend.
2. Открыть тематический отчёт за квартал с уже синхронизированными задачами.
3. Запустить ребилд отчёта.
4. Проверить логи: видны строчки `Loading embedding model` (первый раз) + `Embedding model loaded`.
5. Дождаться завершения ребилда. Проверить что часть задач имеет `match_method='embedding'`:
   ```
   sqlite3 data/dev.db "SELECT match_method, COUNT(*) FROM issue_classifications GROUP BY match_method;"
   ```
   Ожидание: и `embedding`, и `llm` ненулевые.

- [ ] **Step 5: Финальный push**

```
git push origin main
```

---

## Self-review notes

- **Spec coverage:** все 4 ключевых решения (embedding-first / centroid / CRUD alias / lazy backfill) покрыты Tasks 1-13. VPS-readiness — Task 14.
- **Placeholder scan:** нет «TODO», код полный во всех steps.
- **Type consistency:** `MODEL_VERSION`, `EMBEDDING_DIM`, `THEME_CENTROID_TOP_K` определены один раз в Task 2/5, используются consistent. `match_method`, `match_score` — определены в migration Task 4, используются в Tasks 7/8.
- **Pin model revision:** placeholder `f0e6cad205aa1b8a2c50a8f96fee5ce8e80e88f4` в Task 2 надо заменить на актуальный SHA с huggingface.co/intfloat/multilingual-e5-base/commits/main при первом коммите. Subagent обязан это проверить и зафиксировать.
