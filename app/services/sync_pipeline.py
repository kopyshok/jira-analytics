"""PipelineOrchestrator — единая точка запуска стадий sync.

Стадии описаны как наследники Stage. Оркестратор:
- Запускает их по порядку для выбранного mode
- Перехватывает ошибки: critical → stop+failed, non-critical → warn+partial
- Публикует stage_start/stage_done/stage_failed/pipeline_done в EventBroadcaster
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from app.services.event_bus import EventBroadcaster

logger = logging.getLogger(__name__)


class Stage(ABC):
    name: str = ""
    critical: bool = True

    @abstractmethod
    async def run(self, ctx: dict) -> dict:
        """Выполнить стадию. Возвращает словарь counts для отчёта."""

    def invalidates(self) -> list[str]:
        return []


class PipelineOrchestrator:
    def __init__(self, stages: list[Stage], db, bus: EventBroadcaster) -> None:
        self.stages = stages
        self.db = db
        self.bus = bus

    async def run(
        self,
        *,
        mode: str,
        trigger: str,
        team: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        ctx: dict[str, Any] = {"mode": mode, "team": team, "run_id": run_id}
        stages_report: list[dict] = []
        had_non_critical_failure = False

        await self.bus.publish({"type": "sync_started", "run_id": run_id, "mode": mode, "trigger": trigger})

        for stage in self.stages:
            started = datetime.utcnow()
            await self.bus.publish({"type": "stage_start", "stage": stage.name, "run_id": run_id})
            try:
                counts = await stage.run(ctx)
                finished = datetime.utcnow()
                stages_report.append({
                    "stage": stage.name,
                    "started": started.isoformat(),
                    "finished": finished.isoformat(),
                    "status": "ok",
                    "counts": counts or {},
                })
                await self.bus.publish({
                    "type": "stage_done",
                    "stage": stage.name,
                    "run_id": run_id,
                    "duration_ms": int((finished - started).total_seconds() * 1000),
                    "invalidates": stage.invalidates(),
                })
            except asyncio.CancelledError:
                stages_report.append({
                    "stage": stage.name,
                    "started": started.isoformat(),
                    "status": "cancelled",
                })
                await self.bus.publish({"type": "pipeline_done", "run_id": run_id, "status": "cancelled"})
                return {"status": "cancelled", "stages": stages_report}
            except Exception as exc:
                logger.exception("Pipeline stage %s failed", stage.name)
                stages_report.append({
                    "stage": stage.name,
                    "started": started.isoformat(),
                    "finished": datetime.utcnow().isoformat(),
                    "status": "failed",
                    "error": str(exc),
                })
                await self.bus.publish({
                    "type": "stage_failed",
                    "stage": stage.name,
                    "run_id": run_id,
                    "error": str(exc),
                    "critical": stage.critical,
                })
                if stage.critical:
                    await self.bus.publish({"type": "pipeline_done", "run_id": run_id, "status": "failed"})
                    return {"status": "failed", "stages": stages_report, "error": str(exc)}
                had_non_critical_failure = True

        status = "partial" if had_non_critical_failure else "ok"
        await self.bus.publish({"type": "pipeline_done", "run_id": run_id, "status": status})
        return {"status": status, "stages": stages_report}


# === Stages ===

class CalendarStage(Stage):
    name = "calendar"
    critical = False  # non-critical: при отсутствии откатимся к hours_per_day=8

    def __init__(self, calendar_svc, year: Optional[int] = None) -> None:
        self.svc = calendar_svc
        self.year = year

    async def run(self, ctx: dict) -> dict:
        year = self.year or datetime.utcnow().year
        result = await self.svc.sync_year(year)
        inserted = getattr(result, "inserted", 0) if result is not None else 0
        return {"year": year, "days_inserted": inserted}

    def invalidates(self) -> list[str]:
        return ["production-calendar", "capacity"]


class ProjectsStage(Stage):
    name = "projects"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        count = await self.svc.sync_projects()
        return {"count": count if isinstance(count, int) else 0}

    def invalidates(self) -> list[str]:
        return ["projects"]


class IssuesIncrementalStage(Stage):
    name = "issues"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        result = await self.svc.sync_issues(incremental=True)
        return {"updated": result} if isinstance(result, int) else (result or {})

    def invalidates(self) -> list[str]:
        return ["issues", "tree", "backlog", "planning"]


class IssuesFullStage(Stage):
    name = "issues"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        result = await self.svc.sync_issues(incremental=False)
        return {"updated": result} if isinstance(result, int) else (result or {})

    def invalidates(self) -> list[str]:
        return ["issues", "tree", "backlog", "planning"]


class WorklogsDeltaStage(Stage):
    name = "worklogs"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        from datetime import date, datetime, timedelta, timezone
        fallback_since = date.today() - timedelta(days=7)
        explicit_since = ctx.get("since")

        if explicit_since is not None:
            # Явное значение из PipelineRequest — использовать как есть
            if isinstance(explicit_since, str):
                since = date.fromisoformat(explicit_since)
            else:
                since = explicit_since
        else:
            # Читаем cursor из sync_state
            team_or_empty: str = ctx.get("team") or ""
            cursor_state = self.svc._get_sync_state("worklogs", scope=team_or_empty)
            if cursor_state is not None and cursor_state.last_success_at is not None:
                # Overlap 24h — покрывает back-dated ворклоги за тот же день
                cursor_dt = cursor_state.last_success_at
                if cursor_dt.tzinfo is None:
                    cursor_dt = cursor_dt.replace(tzinfo=timezone.utc)
                overlap_since = (cursor_dt - timedelta(hours=24)).date()
                since = max(overlap_since, fallback_since)
            else:
                since = fallback_since

        kwargs: dict = {"since": since}
        team_or_empty = ctx.get("team") or ""
        if ctx.get("team"):
            kwargs["teams"] = [ctx["team"]]

        # Фиксируем момент начала run — cursor пишется по этой точке,
        # чтобы следующий run не пропустил ворклоги, появившиеся в процессе.
        started_at = datetime.now(tz=timezone.utc)

        result = await self.svc.update_worklogs_v2(**kwargs)

        # Успешно завершились — обновить cursor (scope = team или "")
        self.svc._update_sync_state(
            "worklogs",
            last_success=started_at.replace(tzinfo=None),  # хранится UTC naive
            scope=team_or_empty,
        )

        # result — UpdateStats (dataclass) или dict (в моках)
        if isinstance(result, dict):
            upserted = result.get("worklogs_upserted", 0)
            issue_keys = list(result.get("issue_keys") or [])
        else:
            upserted = getattr(result, "worklogs_upserted", 0)
            issue_keys = list(getattr(result, "touched_issue_keys", None) or [])

        if issue_keys:
            ctx["touched_issue_keys"] = issue_keys

        return {"worklogs_upserted": upserted, "issue_keys_count": len(issue_keys)}

    def invalidates(self) -> list[str]:
        return ["analytics", "capacity", "employees"]


class WorklogsFullStage(Stage):
    name = "worklogs"
    critical = True

    def __init__(self, sync_svc, since=None) -> None:
        self.svc = sync_svc
        self.since = since

    async def run(self, ctx: dict) -> dict:
        from datetime import date, timedelta
        since = self.since or ctx.get("since")
        if since is None:
            since = date.today() - timedelta(days=90)
        elif isinstance(since, str):
            since = date.fromisoformat(since)

        result = await self.svc.reload_worklogs_since(since=since)
        if hasattr(result, "worklogs_inserted"):
            return {
                "deleted": result.deleted,
                "issues_scanned": result.issues_scanned,
                "worklogs_inserted": result.worklogs_inserted,
            }
        return result or {}

    def invalidates(self) -> list[str]:
        return ["analytics", "capacity", "employees"]


class IssuesRefreshByKeysStage(Stage):
    name = "issues_refresh"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        keys = ctx.get("touched_issue_keys") or []
        if not keys:
            return {"refreshed": 0}
        result = await self.svc.refresh_issues_by_keys(jira_keys=keys)
        # refresh_issues_by_keys returns Tuple[int, int] (matched, total)
        if isinstance(result, tuple):
            matched, total = result
            ctx["touched_issue_ids"] = []  # no ids returned in this variant
            return {"refreshed": matched, "total_requested": total}
        elif isinstance(result, dict):
            ctx["touched_issue_ids"] = result.get("issue_ids", [])
            return {"refreshed": result.get("refreshed", len(keys))}
        return {"refreshed": 0}

    def invalidates(self) -> list[str]:
        return ["issues", "tree"]


class MappingStage(Stage):
    name = "mapping"
    critical = False  # mapping recalc — non-critical

    def __init__(self, mapping_svc) -> None:
        self.svc = mapping_svc

    async def run(self, ctx: dict) -> dict:
        ids: list | None = ctx.get("touched_issue_ids")
        if not ids:
            keys: list | None = ctx.get("touched_issue_keys")
            if keys:
                from app.models.issue import Issue
                rows = self.svc.db.query(Issue.id).filter(Issue.key.in_(keys)).all()
                ids = [row[0] for row in rows]

        if ids:
            affected = self.svc.recalculate_for_issues(ids)
        else:
            affected = self.svc.recalculate_all()
        # recalculate_all returns MappingStats, recalculate_for_issues returns int
        if hasattr(affected, "issues_processed"):
            return {"affected": affected.issues_processed}
        return {"affected": affected}

    def invalidates(self) -> list[str]:
        return ["analytics", "categories"]


def build_pipeline(*, mode: str, services: dict, team: Optional[str] = None) -> list[Stage]:
    """Собрать список стадий по режиму. services: {sync, calendar, mapping}."""
    sync = services["sync"]
    calendar = services["calendar"]
    mapping = services["mapping"]

    if mode == "quick":
        return [WorklogsDeltaStage(sync)]
    if mode == "normal":
        return [
            CalendarStage(calendar),
            ProjectsStage(sync),
            IssuesIncrementalStage(sync),
            WorklogsDeltaStage(sync),
            MappingStage(mapping),
        ]
    if mode == "full":
        return [
            CalendarStage(calendar),
            ProjectsStage(sync),
            IssuesFullStage(sync),
            WorklogsFullStage(sync),
            MappingStage(mapping),
        ]
    if mode == "team":
        if not team:
            raise ValueError("team mode requires `team` argument")
        return [
            WorklogsDeltaStage(sync),
            IssuesRefreshByKeysStage(sync),
            MappingStage(mapping),
        ]
    raise ValueError(f"Unknown pipeline mode: {mode}")
