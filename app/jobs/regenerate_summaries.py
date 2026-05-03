"""Ежедневный job: регенерация устаревших AI-саммари."""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.issue import Issue
from app.models.project_ai_summary import ProjectAISummary
from app.models.worklog import Worklog
from app.services.llm.prompt import current_prompt_version
from app.services.project_summary_service import ProjectSummaryService
from app.services.projects_service import PROJECT_CATEGORY_CODES


logger = logging.getLogger("jira_analytics.jobs")
THROTTLE_SECONDS = 5  # rate-limit Gemini free tier (15 RPM)


async def regenerate_outdated_summaries() -> dict:
    """Регенерит саммари если worklogs изменились с последней генерации
    или изменилась версия промпта.

    Returns: {processed, regenerated, skipped, errors}
    """
    db = SessionLocal()
    try:
        epics = db.execute(
            select(Issue).where(Issue.category.in_(PROJECT_CATEGORY_CODES))
        ).scalars().all()

        stats = {"processed": 0, "regenerated": 0, "skipped": 0, "errors": 0}
        svc = ProjectSummaryService(db)
        prompt_ver = current_prompt_version(db)

        for epic in epics:
            stats["processed"] += 1
            existing = db.execute(
                select(ProjectAISummary).where(ProjectAISummary.issue_id == epic.id)
            ).scalar_one_or_none()

            if not _needs_regeneration(db, epic, existing, prompt_ver):
                stats["skipped"] += 1
                continue

            try:
                await svc.regenerate(epic.key)
                stats["regenerated"] += 1
                await asyncio.sleep(THROTTLE_SECONDS)
            except Exception as e:
                logger.exception("Regen failed for %s: %s", epic.key, e)
                stats["errors"] += 1

        logger.info("Nightly regen: %s", stats)
        return stats
    finally:
        db.close()


def _needs_regeneration(db: Session, epic: Issue, existing, prompt_ver: str) -> bool:
    """Проверить нужна ли регенерация для данного эпика."""
    if existing is None:
        return True
    if existing.prompt_version != prompt_ver:
        return True
    # Любой worklog по эпику или его детям обновлялся после generated_at?
    from app.services.projects_service import ProjectsService
    child_ids = ProjectsService(db)._collect_subtree(epic.id)
    all_ids = list(child_ids)
    last_wl = db.execute(
        select(Worklog.updated_at).where(Worklog.issue_id.in_(all_ids))
        .order_by(Worklog.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    if last_wl and last_wl > existing.generated_at:
        return True
    return False
