"""Map-фаза тематического отчёта: per-issue классификация по словарю.

Кэш per-issue: input_hash + dictionary_version. При совпадении — LLM не дёргается.
"""
import hashlib
from dataclasses import dataclass
from typing import Optional, Protocol
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.worklog import Worklog


PROMPT_VERSION = "wt-classify-v1"


@dataclass
class ClassificationResult:
    theme_id: Optional[str]
    candidate_name: Optional[str]
    contribution_text: Optional[str]
    confidence: float
    nature_tag: Optional[str] = None


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
    """Промпт Map-фазы. Вход: задача + поля + комменты + словарь. Выход: JSON."""
    themes_list = "\n".join(
        f"- {t.id}: «{t.name}»" + (f" — {t.description}" if t.description else "")
        for t in themes
    ) or "(словарь пуст)"
    parts = [
        "Ты — аналитик. Классифицируй задачу-сопровождение по теме из словаря.",
        "Если ни одна тема не подходит — верни theme_id=null и предложи название новой темы в candidate_name.",
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
        "Верни JSON: {theme_id, candidate_name, contribution_text (≤200 chars), confidence (0..1)}.",
        "Не упоминай ФИО.",
    ])
    return "\n".join(parts)


class WorkTypeClassifier:
    """Оркестратор Map-фазы. Кэшируется per-issue, инвалидируется при изменении содержимого или версии словаря."""

    def __init__(self, db: Session, provider: ClassifierProvider) -> None:
        self.db = db
        self.provider = provider

    async def classify_issue(
        self,
        *,
        issue: Issue,
        work_type_id: str,
        themes: list[Theme],
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
    ) -> IssueClassification:
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
        ):
            return existing

        prompt = build_classify_prompt(issue, comments, themes)
        themes_payload = [
            {"id": t.id, "name": t.name, "description": t.description} for t in themes
        ]
        try:
            res, meta = await self.provider.classify_issue(prompt, themes_payload)
        except Exception as e:
            return self._upsert(
                existing,
                issue,
                work_type_id,
                h,
                wt.theme_dict_version,
                failed=True,
                failure_reason=str(e)[:500],
                model_id=getattr(self.provider, "model", None),
            )

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
            model_id=meta.get("model"),
            failed=False,
            failure_reason=None,
        )

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

        if existing:
            existing.input_hash = input_hash
            existing.dictionary_version = dict_version
            existing.prompt_version = PROMPT_VERSION
            existing.updated_at = datetime.utcnow()
            if confidence is not None:
                existing.llm_confidence = confidence
            for k, v in kwargs.items():
                setattr(existing, k, v)
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
        self.db.add(cls)
        self.db.commit()
        self.db.refresh(cls)
        return cls
