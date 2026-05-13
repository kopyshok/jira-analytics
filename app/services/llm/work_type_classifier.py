"""Map-фаза тематического отчёта: per-issue классификация по словарю.

Кэш per-issue: input_hash + dictionary_version. При совпадении — LLM не дёргается.

Фаза разделена на три синхронных DB-шага (`prepare`, `persist_success`,
`persist_failure`) и один асинхронный LLM-вызов. Это позволяет оркестратору
гонять LLM concurrent (под семафором), а DB-операции сериализовать в одной
SQLAlchemy сессии (потокобезопасность не требуется — асинхронный однопоточный
event loop, важен лишь порядок коммитов).
"""
import hashlib
import pickle
from dataclasses import dataclass, field
from typing import Optional, Protocol
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.worklog import Worklog
from app.services.llm.embedding_matcher import EmbeddingMatcher
from app.services.llm.embedding_service import (
    MODEL_VERSION as EMB_MODEL_VERSION,
    EmbeddingService,
)
from app.services.llm.theme_embedding_service import ThemeEmbeddingService


PROMPT_VERSION = "wt-classify-v3-generic"


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


@dataclass
class ClassificationPrep:
    """Результат `prepare` для cache-miss: всё нужное чтобы вызвать LLM и upsert."""
    issue: Issue
    work_type_id: str
    themes_payload: list[dict]
    prompt: str
    input_hash: str
    dictionary_version: int
    existing: Optional[IssueClassification]


class ClassifierProvider(Protocol):
    model: str

    async def classify_issue(self, prompt: str, themes_payload: list[dict]) -> tuple[ClassificationResult, dict]: ...


def build_input_hash(issue: Issue, worklog_comments: list[str]) -> str:
    """Хэш по содержимому задачи + комментариям ворклогов.

    Меняется при правке любого из текстовых полей задачи или появлении/правке комментов.
    """
    parts = [
        issue.summary or "",
        issue.goal_text or "",
        issue.current_behavior or "",
        issue.description or "",
        "\n".join(worklog_comments or []),
    ]
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()


def collect_worklog_comments(
    db: Session,
    issue_id: str,
    period_start: Optional[date],
    period_end: Optional[date],
) -> list[str]:
    """Собрать комменты ворклогов задачи за период (упорядочены по started_at)."""
    q = select(Worklog.comment_text).where(Worklog.issue_id == issue_id)
    if period_start is not None:
        q = q.where(Worklog.started_at >= period_start)
    if period_end is not None:
        q = q.where(Worklog.started_at <= period_end)
    q = q.order_by(Worklog.started_at)
    return [c for c in db.execute(q).scalars().all() if c]


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
        "- markers: 2-5 коротких snake_case-меток повторяющихся СИМПТОМОВ/ПАТТЕРНОВ задачи. ИМЕННО ПО НИМ задачи группируются — пиши обобщённо.",
        "  Примеры markers: obmen_dannyh, oshibka_provedeniya, zakrytie_perioda, prava_dostupa, dorabotka_otcheta,",
        "  raschet_sebestoimosti, korrekcia_dannyh, konsultaciya_polzovatelya, reglament_obnovlenia,",
        "  pechatnaya_forma, otchetnost_fns, regdannye_nsi, dvizheniya_registra.",
        "- area: одно слово/фраза — обобщённая ОБЛАСТЬ («обмен_данных», «учёт_себестоимости», «закрытие_периода», «права», «отчётность», «нси», «интеграция»).",
        "- nature: ровно ОДНО из enum: bug, enhancement, consultation, regulatory, data_fix, integration, access_request, other.",
        "",
        "ЖЁСТКИЙ ЗАПРЕТ для markers и area:",
        "  Не вставляй конкретные имена систем, продуктов, модулей, контрагентов, проектов, брендов, аббревиатуры систем (любых имён собственных).",
        "  Если пишешь «обмен» — пиши `obmen_dannyh`, а НЕ `obmen_X_Y` где X/Y — имена систем.",
        "  Если пишешь «интеграция» — пиши `integraciya`, а НЕ `integraciya_X`.",
        "  Конкретные сущности (имена систем, модулей, контрагентов и пр.) — место только в `contribution_text` или `candidate_name`.",
        "",
        "candidate_name (только если theme_id=null): 2-4 слова, обобщённая ТЕМА (НЕ описание конкретной задачи). Здесь имена систем уместны, но коротко.",
        "Например «Обмены данными», «Закрытие периода», а не «Обмен Розница–ЕРП: Консолидированная передача регистров».",
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


class WorkTypeClassifier:
    """Оркестратор Map-фазы.

    Two-tier классификация:
    1. Embedding-first — для каждой задачи считаем вектор и ищем ближайшую тему
       по cosine ≥ ``embedding_threshold``. Если матч — LLM не вызывается.
    2. LLM fallback — если embedding не нашёл темы с достаточной близостью,
       идём в текущий LLM-классификатор.

    Кэш per-issue, инвалидируется при изменении содержимого или версии словаря.
    """

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
        self._pending_issue_vec: dict[str, bytes] = {}

    def _build_issue_text(self, issue: Issue) -> str:
        return " ".join(filter(None, [
            issue.summary or "",
            issue.goal_text or "",
            issue.current_behavior or "",
        ]))

    def prepare(
        self,
        *,
        issue: Issue,
        work_type_id: str,
        themes: list[Theme],
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
    ) -> "ClassificationPrep | IssueClassification":
        """Sync prep: возвращает кэш-хит, embedding-match ИЛИ ClassificationPrep на LLM."""
        wt = self.db.get(MandatoryWorkType, work_type_id)
        if not wt:
            raise ValueError(f"Work type {work_type_id} not found")

        comments = collect_worklog_comments(self.db, issue.id, period_start, period_end)
        h = build_input_hash(issue, comments)

        existing = self.db.execute(
            select(IssueClassification).where(
                IssueClassification.issue_id == issue.id,
                IssueClassification.work_type_id == work_type_id,
            )
        ).scalar_one_or_none()

        if (
            existing
            and existing.input_hash == h
            and existing.dictionary_version == wt.theme_dict_version
            and existing.prompt_version == PROMPT_VERSION
        ):
            return existing

        # ---- Embedding-first path ----
        issue_text = self._build_issue_text(issue)
        issue_vec = self.embedder.encode_text(issue_text, kind="query")
        issue_vec_blob = pickle.dumps(issue_vec)

        if themes:
            best_theme, score = self.matcher.find_best_theme(
                issue_vec, themes, self.embedding_threshold,
            )
            if best_theme is not None:
                return self._upsert(
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
                    input_embedding=issue_vec_blob,
                    embedding_model_version=EMB_MODEL_VERSION,
                    _markers=[],
                )

        # Embedding не сработал — сохраним вектор для последующего persist_success
        self._pending_issue_vec[issue.id] = issue_vec_blob

        prompt = build_classify_prompt(issue, comments, themes)
        themes_payload = [
            {"id": t.id, "name": t.name, "description": t.description} for t in themes
        ]
        return ClassificationPrep(
            issue=issue,
            work_type_id=work_type_id,
            themes_payload=themes_payload,
            prompt=prompt,
            input_hash=h,
            dictionary_version=wt.theme_dict_version,
            existing=existing,
        )

    def persist_success(
        self, prep: ClassificationPrep, res: ClassificationResult, meta: dict,
    ) -> IssueClassification:
        """Sync upsert успешного результата LLM-классификатора."""
        issue_vec_blob = self._pending_issue_vec.pop(prep.issue.id, None)
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
        if issue_vec_blob is not None:
            kwargs["input_embedding"] = issue_vec_blob
            kwargs["embedding_model_version"] = EMB_MODEL_VERSION
        return self._upsert(
            prep.existing,
            prep.issue,
            prep.work_type_id,
            prep.input_hash,
            prep.dictionary_version,
            **kwargs,
        )

    def persist_failure(
        self, prep: ClassificationPrep, exc: BaseException,
    ) -> IssueClassification:
        """Sync upsert провала LLM."""
        issue_vec_blob = self._pending_issue_vec.pop(prep.issue.id, None)
        kwargs: dict = dict(
            failed=True,
            failure_reason=str(exc)[:500],
            model_id=getattr(self.provider, "model", None),
        )
        if issue_vec_blob is not None:
            kwargs["input_embedding"] = issue_vec_blob
            kwargs["embedding_model_version"] = EMB_MODEL_VERSION
        return self._upsert(
            prep.existing,
            prep.issue,
            prep.work_type_id,
            prep.input_hash,
            prep.dictionary_version,
            **kwargs,
        )

    async def classify_issue(
        self,
        *,
        issue: Issue,
        work_type_id: str,
        themes: list[Theme],
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
    ) -> IssueClassification:
        """Backward-compat wrapper: prepare → LLM → persist в одной корутине."""
        out = self.prepare(
            issue=issue, work_type_id=work_type_id, themes=themes,
            period_start=period_start, period_end=period_end,
        )
        if isinstance(out, IssueClassification):
            return out
        try:
            res, meta = await self.provider.classify_issue(out.prompt, out.themes_payload)
        except Exception as e:
            return self.persist_failure(out, e)
        return self.persist_success(out, res, meta)

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

