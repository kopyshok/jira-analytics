# Thematic report — markers-based grouping (Variant B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить flat `candidate_name`-кластеризацию на группировку по контролируемому словарю `markers` + `area`, чтобы тематический отчёт перестал генерировать кандидатов «1-к-1 = заголовку задачи».

**Architecture:**
- Map-фаза дополняется структурными полями: `markers` (массив snake_case-меток, 2-5 шт), `area` (нормализованная область), `nature` (контролируемый enum).
- Cluster-фаза получает кандидатов с агрегатом markers по группам и группирует их по пересечению markers, а не по эвристике сходства строк. LLM только присваивает имя кластеру.
- Существующий cache (`input_hash + dictionary_version + prompt_version`) самоинвалидируется при смене PROMPT_VERSION; повторная классификация неизбежна и ожидаема.
- SQLite-совместимость: новые поля как TEXT (JSON-строка для массивов).

**Tech Stack:** SQLAlchemy 2.0 (batch_alter_table для SQLite), Alembic, FastAPI, Pydantic, OpenRouter JSON Schema, pytest-asyncio.

---

## Files

**Create:**
- `alembic/versions/0a1b2c3d4e5f_thematic_markers.py` — миграция: 3 новые колонки в `issue_classifications`.

**Modify:**
- `app/models/issue_classification.py` — добавить поля `markers`, `area`, `nature`.
- `app/services/llm/work_type_classifier.py` — новый промпт + расширенный `ClassificationResult` + сохранение новых полей.
- `app/services/llm/openrouter.py` — расширить JSON-схему `classify_issue` и парсинг.
- `app/services/llm/work_type_clusterer.py` — переписать алгоритм: группировка по markers, LLM только именует.
- `app/services/work_type_report_service.py` — собирать markers/area из IssueClassification, передавать в clusterer.
- `tests/test_work_type_classifier.py` — новые поля.
- `tests/test_work_type_clusterer.py` — новый алгоритм.
- `tests/test_work_type_report_service.py` — markers в pipeline (если уже стоит на classifications).

---

### Task 1: Миграция — добавить markers/area/nature в issue_classifications

**Files:**
- Create: `alembic/versions/0a1b2c3d4e5f_thematic_markers.py`

- [ ] **Step 1: Получить актуальный head Alembic**

```bash
py -3.10 -m alembic heads
```

Запомнить текущий head, использовать как `down_revision`.

- [ ] **Step 2: Создать миграцию через autogenerate ИЛИ вручную (рекомендуется вручную из-за SQLite batch)**

Содержимое файла `alembic/versions/0a1b2c3d4e5f_thematic_markers.py`:

```python
"""thematic_markers

Adds markers (JSON), area (string), nature (string) columns to
issue_classifications. Bumps prompt cache via PROMPT_VERSION change in code.

Revision ID: 0a1b2c3d4e5f
Revises: e97b35c021a7
Create Date: 2026-05-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0a1b2c3d4e5f'
down_revision: Union[str, None] = 'e97b35c021a7'  # fix to current head from Step 1
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issue_classifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('markers_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('area', sa.String(120), nullable=True))
        batch_op.add_column(sa.Column('nature', sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('issue_classifications', schema=None) as batch_op:
        batch_op.drop_column('nature')
        batch_op.drop_column('area')
        batch_op.drop_column('markers_json')
```

- [ ] **Step 3: Проверить корректность down_revision**

Подставить актуальный head из Step 1 вместо `e97b35c021a7`, если он другой.

- [ ] **Step 4: Применить миграцию локально**

```bash
py -3.10 -m alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> 0a1b2c3d4e5f, thematic_markers`.

- [ ] **Step 5: Проверить downgrade**

```bash
py -3.10 -m alembic downgrade -1
py -3.10 -m alembic upgrade head
```

Expected: оба прогона проходят без ошибок.

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/0a1b2c3d4e5f_thematic_markers.py
git commit -m "migration(thematic): add markers/area/nature to issue_classifications"
```

---

### Task 2: Расширить модель IssueClassification

**Files:**
- Modify: `app/models/issue_classification.py`

- [ ] **Step 1: Добавить поля в модель**

Заменить класс целиком на:

```python
"""IssueClassification — Map-phase cache (per issue × work type)."""
import json
from typing import Optional
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class IssueClassification(Base, TimestampMixin):
    __tablename__ = "issue_classifications"
    __table_args__ = (UniqueConstraint("issue_id", "work_type_id", name="uq_classifications_issue_wt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False)
    theme_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True, index=True)
    candidate_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contribution_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    nature_tag: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    llm_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dictionary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    markers_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    area: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    nature: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    @property
    def markers(self) -> list[str]:
        """Десериализация markers_json. Пустой список при отсутствии/ошибке."""
        if not self.markers_json:
            return []
        try:
            v = json.loads(self.markers_json)
            return [str(x) for x in v if isinstance(x, str)]
        except (json.JSONDecodeError, TypeError):
            return []

    @markers.setter
    def markers(self, value: Optional[list[str]]) -> None:
        if not value:
            self.markers_json = None
            return
        cleaned = [s for s in value if isinstance(s, str) and s.strip()]
        self.markers_json = json.dumps(cleaned, ensure_ascii=False) if cleaned else None

    def __repr__(self) -> str:
        return f"<IssueClassification issue={self.issue_id} wt={self.work_type_id} theme={self.theme_id}>"
```

- [ ] **Step 2: Прогнать существующие тесты модели**

```bash
py -3.10 -m pytest tests/test_thematic_models.py -v
```

Expected: PASS (новые поля nullable, существующие тесты не должны сломаться).

- [ ] **Step 3: Commit**

```bash
git add app/models/issue_classification.py
git commit -m "model(thematic): add markers/area/nature to IssueClassification"
```

---

### Task 3: Расширить ClassificationResult и Map-промпт

**Files:**
- Modify: `app/services/llm/work_type_classifier.py`

- [ ] **Step 1: Обновить `ClassificationResult` и `ClassifierProvider` Protocol**

Заменить блок `@dataclass class ClassificationResult` ... и `class ClassifierProvider(Protocol)` на:

```python
@dataclass
class ClassificationResult:
    theme_id: Optional[str]
    candidate_name: Optional[str]
    contribution_text: Optional[str]
    confidence: float
    nature_tag: Optional[str] = None
    markers: list[str] = field(default_factory=list)
    area: Optional[str] = None
    nature: Optional[str] = None


class ClassifierProvider(Protocol):
    model: str

    async def classify_issue(self, prompt: str, themes_payload: list[dict]) -> tuple[ClassificationResult, dict]: ...
```

И добавить импорт в начале файла:

```python
from dataclasses import dataclass, field
```

- [ ] **Step 2: Поднять `PROMPT_VERSION` для инвалидации кэша**

Заменить:

```python
PROMPT_VERSION = "wt-classify-v1"
```

на:

```python
PROMPT_VERSION = "wt-classify-v2-markers"
```

- [ ] **Step 3: Переписать `build_classify_prompt` — markers/area/nature**

Заменить функцию `build_classify_prompt` целиком на:

```python
def build_classify_prompt(issue: Issue, worklog_comments: list[str], themes: list[Theme]) -> str:
    """Map-промпт. Возвращает структуру с markers/area/nature/candidate_name."""
    themes_list = "\n".join(
        f"- {t.id}: «{t.name}»" + (f" — {t.description}" if t.description else "")
        for t in themes
    ) or "(словарь пуст)"
    parts = [
        "Ты — аналитик службы сопровождения. Анализируй задачу и возвращай СТРУКТУРИРОВАННЫЕ метаданные для группировки.",
        "Если задача попадает в одну из тем словаря — укажи theme_id. Иначе — оставь theme_id=null и предложи короткое имя кандидата.",
        "",
        "ОБЯЗАТЕЛЬНЫЕ поля для группировки (это самое важное):",
        "- markers: 2-5 коротких snake_case-меток повторяющихся симптомов/паттернов задачи. ИМЕННО ПО НИМ задачи будут группироваться, поэтому пиши обобщённо, не пересказывай заголовок.",
        "  Примеры markers: obmen_dannyh, oshibka_provedeniya, zakrytie_perioda, prava_dostupa, dorabotka_otcheta,",
        "  raschet_sebestoimosti, integraciya_erp, korrekcia_dannyh, konsultaciya_polzovatelya, reglament_obnovlenia,",
        "  pechatnaya_forma, otchetnost_fns, integraciya_bankclient, regdannye_nsi, dvizheniya_registra.",
        "- area: одно слово/фраза — нормализованная область (например «обмен_данных», «учёт_себестоимости», «закрытие_периода», «права», «отчётность», «нси», «интеграция»). НЕ пиши сюда название задачи.",
        "- nature: ровно ОДНО из enum: bug, enhancement, consultation, regulatory, data_fix, integration, access_request, other.",
        "",
        "candidate_name (только если theme_id=null): 2-4 слова, обобщённая ТЕМА (НЕ описание задачи). Например «Обмены данными» а не «Обмен Розница–ЕРП: Консолидированная передача».",
        "",
        f"Задача [{issue.key}] [{issue.issue_type}]: {issue.summary}",
    ]
    if issue.goal_text:
        parts.append(f"Цель: {issue.goal_text[:2000]}")
    if issue.current_behavior:
        parts.append(f"Текущее поведение: {issue.current_behavior[:2000]}")
    if issue.description:
        parts.append(f"Описание: {issue.description[:3000]}")
    if worklog_comments:
        parts.append("Комментарии ворклогов:")
        for c in worklog_comments[:30]:
            parts.append(f"  • {c[:500]}")
    parts.extend([
        "",
        "Словарь тем:",
        themes_list,
        "",
        "Верни строго JSON следующей формы:",
        "{",
        '  "theme_id": <id из словаря или null>,',
        '  "candidate_name": <строка ≤80 символов или null>,',
        '  "contribution_text": <строка ≤200 символов или null>,',
        '  "confidence": <число 0..1>,',
        '  "markers": [<2-5 snake_case строк>],',
        '  "area": <строка>,',
        '  "nature": <"bug"|"enhancement"|"consultation"|"regulatory"|"data_fix"|"integration"|"access_request"|"other">',
        "}",
        "ОБЯЗАТЕЛЬНО: markers и area никогда не пустые. Не упоминай ФИО.",
    ])
    return "\n".join(parts)
```

- [ ] **Step 4: Сохранять новые поля в `_upsert`**

В методе `WorkTypeClassifier.classify_issue` после успешного вызова провайдера передавать новые поля. Заменить второй `return self._upsert(...)` (success branch) на:

```python
        return self._upsert(
            existing,
            issue,
            work_type_id,
            h,
            wt.theme_dict_version,
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
            _markers=res.markers,
        )
```

И обновить `_upsert` — он должен принимать `_markers` отдельно (т.к. это property, не колонка):

Заменить метод `_upsert` целиком на:

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

        if existing:
            existing.input_hash = input_hash
            existing.dictionary_version = dict_version
            existing.prompt_version = PROMPT_VERSION
            existing.updated_at = datetime.utcnow()
            if confidence is not None:
                existing.llm_confidence = confidence
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
            **kwargs,
        )
        if markers is not None:
            cls.markers = markers
        self.db.add(cls)
        self.db.commit()
        self.db.refresh(cls)
        return cls
```

- [ ] **Step 5: Прогнать существующие тесты классификатора**

```bash
py -3.10 -m pytest tests/test_work_type_classifier.py -v
```

Expected: возможны падения по тестам, проверяющим mock provider — обновить их в Task 5 ниже. Если падения связаны только с тем, что mock не возвращает `markers/area/nature` — это ожидаемо, продолжаем.

- [ ] **Step 6: Commit**

```bash
git add app/services/llm/work_type_classifier.py
git commit -m "feat(thematic): map phase emits markers/area/nature for grouping"
```

---

### Task 4: Расширить OpenRouter classify_issue схему

**Files:**
- Modify: `app/services/llm/openrouter.py`

- [ ] **Step 1: Обновить JSON-схему и парсинг в `classify_issue`**

Заменить тело метода `classify_issue` на:

```python
    async def classify_issue(self, prompt: str, themes_payload: list[dict]) -> tuple["ClassificationResult", dict]:
        """Map-фаза тематического отчёта. См. WorkTypeClassifier.

        Возвращает ClassificationResult + meta. Использует fallback-цепочку.
        """
        from app.services.llm.work_type_classifier import ClassificationResult

        nature_enum = [
            "bug", "enhancement", "consultation", "regulatory",
            "data_fix", "integration", "access_request", "other",
        ]
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "theme_id": {"type": ["string", "null"]},
                "candidate_name": {"type": ["string", "null"]},
                "contribution_text": {"type": ["string", "null"], "maxLength": 200},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "markers": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 60},
                    "maxItems": 8,
                },
                "area": {"type": ["string", "null"], "maxLength": 120},
                "nature": {"type": ["string", "null"], "enum": [*nature_enum, None]},
            },
            "required": ["theme_id", "confidence"],
        }
        valid_ids = {t["id"] for t in themes_payload}
        chain = [self.model] + [m for m in self.fallback_models if m and m != self.model]
        last_exc: Exception | None = None
        for model_id in chain:
            try:
                obj, meta = await self._call_json(model_id, prompt, schema)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_STATUSES:
                    logger.warning("OpenRouter %s → HTTP %s, fallback", model_id, e.response.status_code)
                    last_exc = e
                    continue
                raise
            except (LLMResponseError, httpx.TimeoutException) as e:
                logger.warning("OpenRouter %s classify_issue → %s, fallback", model_id, e)
                last_exc = e
                continue

            tid = obj.get("theme_id")
            if tid and tid not in valid_ids:
                tid = None

            raw_markers = obj.get("markers") or []
            markers = [
                m.strip().lower().replace(" ", "_")[:60]
                for m in raw_markers
                if isinstance(m, str) and m.strip()
            ][:8]

            nature = obj.get("nature")
            if nature not in nature_enum:
                nature = None

            return ClassificationResult(
                theme_id=tid,
                candidate_name=(obj.get("candidate_name") or "").strip()[:255] or None,
                contribution_text=(obj.get("contribution_text") or "").strip()[:200] or None,
                confidence=float(obj.get("confidence") or 0.0),
                nature_tag=None,
                markers=markers,
                area=(obj.get("area") or "").strip()[:120] or None,
                nature=nature,
            ), meta
        if last_exc is not None:
            raise last_exc
        raise LLMResponseError("classify_issue: пустая цепочка моделей")
```

- [ ] **Step 2: Прогнать smoke-тест endpoint /work_types/.../themes/build (если возможно без LLM-ключа — пропустить)**

Сделать только статический lint:

```bash
py -3.10 -m ruff check app/services/llm/openrouter.py
```

Expected: 0 ошибок.

- [ ] **Step 3: Commit**

```bash
git add app/services/llm/openrouter.py
git commit -m "feat(thematic): openrouter classify_issue returns markers/area/nature"
```

---

### Task 5: Обновить Map-тесты — учесть markers/area/nature

**Files:**
- Modify: `tests/test_work_type_classifier.py`

- [ ] **Step 1: Прочитать существующий файл**

```bash
py -3.10 -m pytest tests/test_work_type_classifier.py -v --co
```

Получить список тестов. Каждый тест, где есть mock `classify_issue`, должен возвращать `ClassificationResult` с непустым `markers` (например `["obmen_dannyh", "oshibka_provedeniya"]`), `area="обмен_данных"`, `nature="bug"`.

- [ ] **Step 2: Найти все mock-возвраты ClassificationResult и обновить**

Грепнуть `ClassificationResult(`:

```bash
grep -n "ClassificationResult(" tests/test_work_type_classifier.py
```

Для каждого вхождения добавить kwargs `markers=["..."], area="...", nature="..."`. Например:

```python
ClassificationResult(
    theme_id=None,
    candidate_name="Обмены данными",
    contribution_text="...",
    confidence=0.8,
    markers=["obmen_dannyh", "integraciya_erp"],
    area="обмен_данных",
    nature="enhancement",
)
```

- [ ] **Step 3: Добавить новый тест на сериализацию markers**

В конец файла добавить:

```python
@pytest.mark.asyncio
async def test_classifier_persists_markers_and_area(db_session, work_type_factory, issue_factory):
    """Маркеры и area сохраняются и читаются обратно."""
    wt = work_type_factory()
    issue = issue_factory()

    fake_provider = AsyncMock()
    fake_provider.model = "test-model"
    fake_provider.classify_issue = AsyncMock(return_value=(
        ClassificationResult(
            theme_id=None,
            candidate_name="Обмены",
            contribution_text=None,
            confidence=0.8,
            markers=["obmen_dannyh", "integraciya_erp"],
            area="обмен_данных",
            nature="integration",
        ),
        {"model": "test-model"},
    ))

    clf = WorkTypeClassifier(db_session, fake_provider)
    res = await clf.classify_issue(
        issue=issue,
        work_type_id=wt.id,
        themes=[],
    )
    assert res.markers == ["obmen_dannyh", "integraciya_erp"]
    assert res.area == "обмен_данных"
    assert res.nature == "integration"
```

ПРИМЕЧАНИЕ: имена фикстур `work_type_factory`, `issue_factory`, `db_session` использовать те же, которые уже есть в файле. Если их нет — посмотреть фикстуры в начале файла и адаптировать тест к существующему стилю (создание Issue/MandatoryWorkType вручную через db.add).

- [ ] **Step 4: Прогнать тесты**

```bash
py -3.10 -m pytest tests/test_work_type_classifier.py -v
```

Expected: PASS (включая новый тест).

- [ ] **Step 5: Commit**

```bash
git add tests/test_work_type_classifier.py
git commit -m "test(thematic): cover markers/area/nature persistence in classifier"
```

---

### Task 6: Переписать WorkTypeClusterer — группировка по markers

**Files:**
- Modify: `app/services/llm/work_type_clusterer.py`

- [ ] **Step 1: Заменить файл целиком**

```python
"""Cluster-фаза тематического отчёта: группировка по markers/area, не по строкам.

После Map-фазы у каждой записи есть markers (контролируемый словарь). Здесь:
1. Считаем частотность всех markers по выборке.
2. Передаём LLM ТОЛЬКО список топ-markers + примеры candidate_names при них.
3. LLM возвращает {cluster_name → [markers]}.
4. Каждой задаче назначаем кластер по принципу "у которого больше всего пересечений с её markers".

Если LLM падает — fallback: одна задача = один кластер по top-marker.
"""
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from app.models.issue_classification import IssueClassification


logger = logging.getLogger("jira_analytics.thematic")
PROMPT_VERSION = "wt-cluster-v2-markers"


class ClustererProvider(Protocol):
    model: str

    async def cluster_candidates(self, prompt: str) -> tuple[dict, dict]: ...


@dataclass
class _Candidate:
    issue_id: str
    candidate_name: str
    markers: list[str]
    area: str | None
    hours: float
    jira_key: str | None


def build_cluster_prompt(
    *,
    marker_to_examples: dict[str, list[str]],
    marker_freq: Counter,
    target_clusters: int,
) -> str:
    """Промпт: входы — markers + примеры. Выход — {cluster_name → [markers]}.

    marker_to_examples: до 5 candidate_name примеров на каждый marker.
    marker_freq: счётчик задач, в которых встречался marker.
    """
    lines = [
        "Ты — старший аналитик. Тебе дан список markers (контролируемых меток) с примерами тем задач при них.",
        "",
        f"Цель: сгруппировать markers в {target_clusters} широких кластеров и дать каждому короткое русское имя (2-4 слова).",
        "",
        "СТРОГИЕ ПРАВИЛА:",
        "1. Имя кластера: 2-4 слова, на русском, БЕЗ упоминания конкретных систем (УПП, ЕРП, Розница) — обобщай.",
        "2. Имя кластера — это широкая ТЕМА. Например «Обмены данными», «Закрытие периода», «Учёт себестоимости».",
        "3. Каждый marker должен войти РОВНО В ОДИН кластер.",
        "4. Не выдумывай новых markers, не пропускай ни один из списка.",
        "5. Группируй по смыслу markers, ИГНОРИРУЯ фразы из примеров (примеры — для контекста, не для имени).",
        "",
        "Markers (количество задач | примеры тем):",
    ]
    for marker, freq in marker_freq.most_common():
        examples = marker_to_examples.get(marker, [])[:3]
        ex_str = " | ".join(examples) if examples else "—"
        lines.append(f"- {marker} ({freq} задач) — {ex_str}")
    lines.extend([
        "",
        'Верни JSON: {"clusters": [{"name": "<2-4 слова>", "markers": ["m1", "m2", ...]}, ...]}',
        f"Целевое количество кластеров: ~{target_clusters}.",
    ])
    return "\n".join(lines)


class WorkTypeClusterer:
    """Группирует кандидатов по контролируемому словарю markers."""

    def __init__(self, provider: ClustererProvider) -> None:
        self.provider = provider

    async def cluster(
        self,
        classifications: list[IssueClassification],
        *,
        hours_by_issue: dict[str, float] | None = None,
        key_by_issue: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Возвращает маппинг {candidate_name → cluster_name}.

        Алгоритм:
        1. Извлекаем markers с каждой записи.
        2. LLM группирует markers в N кластеров с именами.
        3. Для каждой записи: выбираем кластер с максимальным пересечением её markers.
        4. Маппим candidate_name → cluster_name.
        Fallback при ошибке LLM: identity-mapping.
        """
        hours_by_issue = hours_by_issue or {}
        key_by_issue = key_by_issue or {}

        cands: list[_Candidate] = []
        for c in classifications:
            if not c.candidate_name:
                continue
            cands.append(_Candidate(
                issue_id=c.issue_id,
                candidate_name=c.candidate_name,
                markers=list(c.markers),
                area=c.area,
                hours=hours_by_issue.get(c.issue_id, 0.0),
                jira_key=key_by_issue.get(c.issue_id),
            ))

        if len(cands) < 2:
            return {}

        unique_names = {c.candidate_name for c in cands}
        identity = {n: n for n in unique_names}

        # Соберём markers по частотности и примеры candidate_name на каждый marker
        marker_freq: Counter = Counter()
        marker_to_examples: dict[str, list[str]] = {}
        for cand in cands:
            for m in cand.markers:
                marker_freq[m] += 1
                lst = marker_to_examples.setdefault(m, [])
                if cand.candidate_name not in lst and len(lst) < 5:
                    lst.append(cand.candidate_name)

        if not marker_freq:
            logger.info("WorkTypeClusterer: no markers, returning identity mapping")
            return identity

        target_clusters = max(4, min(12, len(marker_freq) // 3))
        prompt = build_cluster_prompt(
            marker_to_examples=marker_to_examples,
            marker_freq=marker_freq,
            target_clusters=target_clusters,
        )

        try:
            obj, meta = await self.provider.cluster_candidates(prompt)
        except Exception as e:
            logger.warning("WorkTypeClusterer: LLM call failed, identity mapping: %s", e)
            return identity

        raw_clusters = obj.get("clusters") or []
        if not isinstance(raw_clusters, list) or not raw_clusters:
            logger.warning("WorkTypeClusterer: empty clusters, identity mapping")
            return identity

        # Построим marker → cluster_name маппинг
        marker_to_cluster: dict[str, str] = {}
        for cl in raw_clusters:
            cluster_name = (cl.get("name") or "").strip()
            if not cluster_name:
                continue
            for m in cl.get("markers") or []:
                if isinstance(m, str) and m in marker_freq:
                    marker_to_cluster[m] = cluster_name

        # Для каждого candidate_name выбираем кластер с максимумом голосов от его markers
        # (агрегируем по уникальным candidate_name, т.к. один candidate_name может встретиться в N задачах
        # с разными markers — берём маркеры всех его задач)
        cand_markers: dict[str, Counter] = {}
        for cand in cands:
            counter = cand_markers.setdefault(cand.candidate_name, Counter())
            for m in cand.markers:
                counter[m] += 1

        mapping: dict[str, str] = {}
        for name, marker_counter in cand_markers.items():
            cluster_votes: Counter = Counter()
            for m, freq in marker_counter.items():
                cn = marker_to_cluster.get(m)
                if cn:
                    cluster_votes[cn] += freq
            if cluster_votes:
                mapping[name] = cluster_votes.most_common(1)[0][0]
            else:
                mapping[name] = name  # fallback identity

        n_clusters = len({v for v in mapping.values()})
        logger.info(
            "WorkTypeClusterer: %d candidates → %d clusters via %d markers (model=%s)",
            len(cand_markers), n_clusters, len(marker_freq), meta.get("model"),
        )
        if n_clusters >= len(cand_markers) * 0.7:
            logger.warning(
                "WorkTypeClusterer: %d clusters from %d candidates (>=70%%) — markers may be too task-specific.",
                n_clusters, len(cand_markers),
            )
        return mapping
```

- [ ] **Step 2: Lint**

```bash
py -3.10 -m ruff check app/services/llm/work_type_clusterer.py
```

Expected: 0 ошибок.

- [ ] **Step 3: Commit**

```bash
git add app/services/llm/work_type_clusterer.py
git commit -m "feat(thematic): cluster phase groups by markers, not free text"
```

---

### Task 7: Расширить OpenRouter cluster_candidates схему

**Files:**
- Modify: `app/services/llm/openrouter.py`

- [ ] **Step 1: Обновить схему `cluster_candidates`**

Заменить значение `schema` в `cluster_candidates` на:

```python
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "clusters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "maxLength": 80},
                            "markers": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["name", "markers"],
                    },
                }
            },
            "required": ["clusters"],
        }
```

- [ ] **Step 2: Lint**

```bash
py -3.10 -m ruff check app/services/llm/openrouter.py
```

Expected: 0 ошибок.

- [ ] **Step 3: Commit**

```bash
git add app/services/llm/openrouter.py
git commit -m "feat(thematic): openrouter cluster schema accepts markers array"
```

---

### Task 8: Обновить тесты кластерера

**Files:**
- Modify: `tests/test_work_type_clusterer.py`

- [ ] **Step 1: Заменить файл целиком**

```python
"""WorkTypeClusterer — группировка по markers."""
import pytest
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import AsyncMock

from app.services.llm.work_type_clusterer import (
    WorkTypeClusterer, build_cluster_prompt,
)


@dataclass
class _FakeCls:
    issue_id: str
    candidate_name: Optional[str]
    markers: list[str] = field(default_factory=list)
    area: Optional[str] = None
    theme_id: Optional[str] = None
    failed: bool = False


def _make_cls(issue_id: str, candidate_name: str, markers: list[str], area: str = "обмен_данных") -> _FakeCls:
    return _FakeCls(issue_id=issue_id, candidate_name=candidate_name, markers=markers, area=area)


@pytest.mark.asyncio
async def test_cluster_empty_returns_empty():
    provider = AsyncMock()
    clusterer = WorkTypeClusterer(provider=provider)
    result = await clusterer.cluster([])
    assert result == {}
    provider.cluster_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_single_candidate_returns_empty():
    provider = AsyncMock()
    clusterer = WorkTypeClusterer(provider=provider)
    result = await clusterer.cluster([_make_cls("i1", "Ошибки обмена", ["obmen_dannyh"])])
    assert result == {}
    provider.cluster_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_groups_by_marker_overlap():
    """5 кандидатов с разными candidate_name, но общими markers → 2 кластера."""
    cands = [
        _make_cls("i0", "Обмен Розница–ЕРП", ["obmen_dannyh", "integraciya_erp"]),
        _make_cls("i1", "Выгрузка правил УПП", ["obmen_dannyh", "regdannye_nsi"]),
        _make_cls("i2", "Ошибки регистров себестоимости", ["raschet_sebestoimosti", "dvizheniya_registra"]),
        _make_cls("i3", "Корректировка себестоимости металлов", ["raschet_sebestoimosti", "korrekcia_dannyh"]),
        _make_cls("i4", "Обмены передачи товаров", ["obmen_dannyh"]),
    ]

    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(return_value=(
        {
            "clusters": [
                {"name": "Обмены данными", "markers": ["obmen_dannyh", "integraciya_erp", "regdannye_nsi"]},
                {"name": "Себестоимость", "markers": ["raschet_sebestoimosti", "dvizheniya_registra", "korrekcia_dannyh"]},
            ]
        },
        {"model": "test-model"},
    ))

    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(cands)

    assert mapping["Обмен Розница–ЕРП"] == "Обмены данными"
    assert mapping["Выгрузка правил УПП"] == "Обмены данными"
    assert mapping["Обмены передачи товаров"] == "Обмены данными"
    assert mapping["Ошибки регистров себестоимости"] == "Себестоимость"
    assert mapping["Корректировка себестоимости металлов"] == "Себестоимость"


@pytest.mark.asyncio
async def test_cluster_provider_exception_returns_identity():
    """LLM падает → identity mapping."""
    cands = [
        _make_cls("i0", "А", ["m1"]),
        _make_cls("i1", "Б", ["m2"]),
    ]
    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(side_effect=RuntimeError("boom"))
    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(cands)
    assert mapping["А"] == "А"
    assert mapping["Б"] == "Б"


@pytest.mark.asyncio
async def test_cluster_no_markers_returns_identity():
    """Если у всех записей markers пустые → identity mapping (не звать LLM)."""
    cands = [
        _make_cls("i0", "А", []),
        _make_cls("i1", "Б", []),
    ]
    fake_provider = AsyncMock()
    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(cands)
    assert mapping["А"] == "А"
    assert mapping["Б"] == "Б"
    fake_provider.cluster_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_uncovered_marker_keeps_identity_for_that_candidate():
    """Если LLM не покрыл marker задачи — она остаётся под своим candidate_name."""
    cands = [
        _make_cls("i0", "А", ["m1"]),
        _make_cls("i1", "Б", ["m2"]),
        _make_cls("i2", "В", ["m_unknown"]),
    ]
    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(return_value=(
        {"clusters": [{"name": "АБ", "markers": ["m1", "m2"]}]},
        {"model": "test"},
    ))
    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(cands)
    assert mapping["А"] == "АБ"
    assert mapping["Б"] == "АБ"
    assert mapping["В"] == "В"


def test_build_cluster_prompt_structure():
    """Промпт содержит markers с частотностью и примерами."""
    prompt = build_cluster_prompt(
        marker_to_examples={
            "m1": ["Тема 1", "Тема 2"],
            "m2": ["Тема 3"],
        },
        marker_freq=Counter({"m1": 5, "m2": 2}),
        target_clusters=3,
    )
    assert "m1 (5 задач)" in prompt
    assert "m2 (2 задач)" in prompt
    assert "Тема 1" in prompt
    assert 'РОВНО В ОДИН кластер' in prompt
    assert "clusters" in prompt
```

- [ ] **Step 2: Прогнать**

```bash
py -3.10 -m pytest tests/test_work_type_clusterer.py -v
```

Expected: PASS на всех тестах.

- [ ] **Step 3: Commit**

```bash
git add tests/test_work_type_clusterer.py
git commit -m "test(thematic): clusterer groups by markers"
```

---

### Task 9: Проверить и адаптировать report_service

**Files:**
- Modify: `app/services/work_type_report_service.py` (если нужно)

- [ ] **Step 1: Проверить, что новые сигнатуры совместимы**

```bash
grep -n "cluster" app/services/work_type_report_service.py
```

Найти участок с вызовом `WorkTypeClusterer(provider=...).cluster(unclassified, hours_by_issue=..., key_by_issue=...)`. Убедиться что подпись метода `cluster` не менялась — она осталась `(classifications, *, hours_by_issue, key_by_issue) -> dict[candidate_name → cluster_name]`. Это совместимо.

- [ ] **Step 2: Прогнать тесты сервиса**

```bash
py -3.10 -m pytest tests/test_work_type_report_service.py -v
```

Expected: все тесты PASS. Если падают — посмотреть, не используется ли старая сигнатура mock cluster_candidates (которая возвращала `candidate_names` вместо `markers`). Если да — обновить mocks в этом файле теми же изменениями, что в Task 8.

- [ ] **Step 3 (если сервис требует правок): обновить и закоммитить**

Если правки потребовались, закоммитить:

```bash
git add tests/test_work_type_report_service.py app/services/work_type_report_service.py
git commit -m "fix(thematic): adapt report_service tests to markers cluster contract"
```

Если ничего не правилось — пропустить commit.

---

### Task 10: End-to-end smoke

**Files:** none (manual run)

- [ ] **Step 1: Прогнать весь тестовый набор тематического отчёта**

```bash
py -3.10 -m pytest tests/test_work_type_classifier.py tests/test_work_type_clusterer.py tests/test_work_type_report_service.py tests/test_work_type_report_endpoints.py tests/test_work_type_synthesizer.py tests/test_thematic_models.py -v
```

Expected: все PASS.

- [ ] **Step 2: Прогнать lint**

```bash
py -3.10 -m ruff check app/services/llm/ app/services/work_type_report_service.py app/models/issue_classification.py
```

Expected: 0 ошибок.

- [ ] **Step 3: Запустить backend локально и пересобрать тематический отчёт через UI**

```bash
# Kill existing on :8000 (Windows)
# Затем перезапустить
```

В UI: Тематический отчёт → выбрать вид работ с >50 кандидатов → кнопка «Пересчёт». Дождаться завершения SSE.

Ожидание (acceptance criteria):
- На вкладке «Кандидаты» количество строк значимо меньше прежнего (с 62 → ~10-20).
- Имена кандидатов — обобщённые («Обмены данными», «Учёт себестоимости», «Закрытие периода»), а не «Анализ и исправление ошибок при закрытии месяца».
- В логах backend строка `WorkTypeClusterer: N candidates → M clusters via K markers`.

- [ ] **Step 4: Зафиксировать результаты в memory**

Если acceptance criteria выполнены — сохранить project-memory:
```
project_thematic_markers_grouping_shipped.md:
"2026-05-08: Map-фаза получает markers/area/nature; Cluster группирует по пересечению markers
вместо строкового сходства. Кандидатов было 62 → стало ~N после пересчёта."
```

Если acceptance criteria НЕ выполнены — сохранить followups + не закрывать задачу.

- [ ] **Step 5: Push**

```bash
git push origin main
```

---

## Self-Review Notes

- Bumped `PROMPT_VERSION` инвалидирует кэш Map — все задачи будут переклассифицированы при первом «Пересчёте» после деплоя. Это ожидаемо и необходимо.
- Существующие записи `issue_classifications` останутся в БД с `markers_json=NULL` до следующего пересчёта; новый clusterer корректно обработает их (попадут в identity-mapping или будут пропущены при `if not c.markers`).
- Frontend изменений не требуется: `candidate_name` возвращается из API как и раньше, просто их меньше и имена обобщённые.
- Faithfulness validator из Reduce-фазы (`app/services/llm/faithfulness_validator.py`) не трогается — markers не уходят в синтезатор, только к кластереру.
- Frontend bundle/cache: после деплоя пользователь увидит изменения только после нажатия «Пересчёт» (т.к. snapshot закеширован под старой `dictionary_version`); это OK.
