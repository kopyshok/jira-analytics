"""ProjectSummaryService — оркестратор AI-саммари (cache + LLM)."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.models.issue import Issue
from app.models.project_ai_summary import ProjectAISummary
from app.services.confluence_service import ConfluenceService, extract_confluence_urls
from app.services.llm.base import get_llm_provider
from app.services.llm.prompt import build_prompt, current_prompt_version
from app.services.projects_service import ProjectsService


class ProjectSummaryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def get_summary(self, key: str) -> Optional[ProjectAISummary]:
        """Кэш-хит — возвращаем готовый. Кэш-мисс — None."""
        epic = self.db.execute(select(Issue).where(Issue.key == key)).scalar_one_or_none()
        if not epic:
            return None
        return self.db.execute(
            select(ProjectAISummary).where(ProjectAISummary.issue_id == epic.id)
        ).scalar_one_or_none()

    async def regenerate(self, key: str) -> ProjectAISummary:
        """Принудительная регенерация: вызов LLM + апсёрт в кэш."""
        epic = self.db.execute(select(Issue).where(Issue.key == key)).scalar_one_or_none()
        if not epic:
            raise ValueError(f"Issue {key} not found")

        epic_data = await self._build_epic_data_async(epic)
        provider = get_llm_provider(self.db)
        prompt = build_prompt(epic_data, db=self.db)
        prompt_ver = current_prompt_version(self.db)
        summary, meta = await provider.summarize_project(prompt)

        existing = self.db.execute(
            select(ProjectAISummary).where(ProjectAISummary.issue_id == epic.id)
        ).scalar_one_or_none()
        work_breakdown_json = json.dumps(
            [g.model_dump() for g in summary.work_breakdown], ensure_ascii=False
        )
        if existing:
            existing.goals_json = json.dumps(summary.goals, ensure_ascii=False)
            existing.result_flow_json = json.dumps(
                [b.model_dump() for b in summary.result_flow_blocks], ensure_ascii=False)
            existing.result_checklist_json = json.dumps(
                [c.model_dump() for c in summary.result_checklist], ensure_ascii=False)
            existing.status_text = summary.status_text
            existing.workload_summary = summary.workload_summary
            existing.work_breakdown_json = work_breakdown_json
            existing.generated_at = datetime.utcnow()
            existing.model_used = meta.get("model", provider.model)
            existing.input_tokens = meta.get("input_tokens")
            existing.output_tokens = meta.get("output_tokens")
            existing.prompt_version = prompt_ver
        else:
            existing = ProjectAISummary(
                issue_id=epic.id,
                goals_json=json.dumps(summary.goals, ensure_ascii=False),
                result_flow_json=json.dumps(
                    [b.model_dump() for b in summary.result_flow_blocks], ensure_ascii=False),
                result_checklist_json=json.dumps(
                    [c.model_dump() for c in summary.result_checklist], ensure_ascii=False),
                status_text=summary.status_text,
                workload_summary=summary.workload_summary,
                work_breakdown_json=work_breakdown_json,
                generated_at=datetime.utcnow(),
                model_used=meta.get("model", provider.model),
                input_tokens=meta.get("input_tokens"),
                output_tokens=meta.get("output_tokens"),
                prompt_version=prompt_ver,
            )
            self.db.add(existing)
        self.db.commit()
        self.db.refresh(existing)
        return existing

    async def _build_epic_data_async(self, epic: Issue) -> dict:
        """Собрать данные для промпта (async — fetch Confluence)."""
        detail = ProjectsService(self.db).get_project_detail(epic.key)
        if not detail:
            return {"key": epic.key, "summary": epic.summary}

        child_ids = ProjectsService(self.db)._collect_subtree(epic.id)
        child_issues = self.db.execute(
            select(Issue).where(Issue.id.in_(child_ids))
        ).scalars().all()
        child_summaries = [
            {
                "key": i.key,
                "summary": i.summary,
                "status": i.status,
                "is_done": (i.status_category == "done"),
                "description": (i.description or "")[:8000] or None,
                "goal_text": (i.goal_text or "") or None,
                "current_behavior": (i.current_behavior or "") or None,
            }
            for i in child_issues[:30]
        ]

        # Confluence: ссылки из эпика + всех детей
        base = self.db.query(AppSetting).filter(
            AppSetting.key == "jira_base_url"
        ).first()
        base_url = base.value if base and base.value else ""
        all_urls: list[str] = []
        seen: set[str] = set()
        for txt in [epic.description] + [i.description for i in child_issues]:
            for u in extract_confluence_urls(txt, base_url):
                if u not in seen:
                    seen.add(u)
                    all_urls.append(u)
        # лимит 10 страниц на эпик чтобы не раздувать токены
        confluence = await ConfluenceService(self.db).fetch_pages(all_urls[:10])
        confluence_pages = [
            {
                "title": p.title,
                "url": p.source_url,
                "body_text": p.body_text[:8000],
            }
            for p in confluence
        ]

        total_hours = detail.total_hours or 0.0
        return {
            "key": epic.key,
            "summary": epic.summary,
            "description": epic.description or "",
            "status": epic.status,
            "is_done": epic.status_category == "done",
            "child_count": detail.child_count,
            "employee_count": detail.employee_count,
            "total_hours": total_hours,
            "period_start": detail.period_start.date().isoformat() if detail.period_start else None,
            "period_end": detail.period_end.date().isoformat() if detail.period_end else None,
            "categories": [{"label": c.label, "hours": c.hours} for c in detail.categories],
            "employees": [
                {
                    "name": e.name,
                    "hours": e.hours,
                    "pct": round(e.hours / total_hours * 100, 1) if total_hours else 0.0,
                }
                for e in detail.employees
            ],
            "top_issues": [
                {"key": t.key, "summary": t.summary, "hours": t.hours}
                for t in detail.top_issues
            ],
            "child_summaries": child_summaries,
            "confluence_pages": confluence_pages,
        }
