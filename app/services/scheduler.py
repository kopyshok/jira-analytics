"""SchedulerService — обёртка над APScheduler для автозапуска sync pipeline.

scheduled_pipeline_runner — функция, которую SchedulerService вызывает по cron.
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from croniter import croniter

from app.connectors.jira_client import JiraClient  # noqa: F401 — for patch target in tests

logger = logging.getLogger(__name__)


class SchedulerService:
    """Управляет APScheduler: регистрирует cron-задания из SyncSchedule."""

    def __init__(
        self,
        scheduler: Optional[AsyncIOScheduler] = None,
        trigger_runner: Optional[Callable] = None,
    ) -> None:
        self.scheduler = scheduler or AsyncIOScheduler()
        self._trigger_runner = trigger_runner

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def is_valid_cron(expr: str) -> bool:
        """Проверить валидность cron-выражения (5 полей)."""
        try:
            croniter(expr)
            return True
        except Exception:
            return False

    @staticmethod
    def next_run_at(expr: str) -> Optional[datetime]:
        """Вернуть следующий момент срабатывания cron (UTC). None если выражение невалидно."""
        try:
            itr = croniter(expr, datetime.now(tz=timezone.utc))
            nxt = itr.get_next(datetime)
            return nxt
        except Exception:
            return None

    @staticmethod
    def next_runs(expr: str, count: int = 3) -> list[datetime]:
        """Получить ``count`` ближайших времён срабатывания cron в локальной таймзоне.

        Возвращает пустой список если выражение невалидно. Datetime'ы tz-aware.
        Используется фронтом для preview расписания.
        """
        if not SchedulerService.is_valid_cron(expr):
            return []
        try:
            now_local = datetime.now(tz=timezone.utc).astimezone()
            itr = croniter(expr, now_local)
            return [itr.get_next(datetime) for _ in range(count)]
        except Exception:
            return []

    @staticmethod
    def humanize_cron(cron_expr: str) -> str:
        """Преобразовать cron-выражение в человекочитаемое описание на русском.

        Поддерживает шаблоны: ``*/N * * * *`` (минуты), ``0 */N * * *`` (часы),
        ``M H * * *`` (ежедневно), ``M H * * 1-5`` или ``M H * * 1,2,3,4,5``
        (будни), ``M H * * 0,6`` (выходные), ``M H * * D1,D2,...`` (дни),
        ``M H * * D`` (еженедельно). Для не распознанных выражений возвращает
        ``По cron-выражению: <expr>``.
        """
        import re

        DAY_NAMES = {0: "вс", 1: "пн", 2: "вт", 3: "ср", 4: "чт", 5: "пт", 6: "сб"}
        DAY_NOMINATIVE = {
            0: "воскресенье",
            1: "понедельник",
            2: "вторник",
            3: "среду",
            4: "четверг",
            5: "пятницу",
            6: "субботу",
        }

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return f"По cron-выражению: {cron_expr}"
        minute, hour, dom, month, dow = parts

        # Каждые N минут: */N * * * *
        if month == "*" and dom == "*" and dow == "*" and hour == "*":
            m = re.fullmatch(r"\*/(\d+)", minute)
            if m:
                n = int(m.group(1))
                if n == 1:
                    return "Каждую минуту"
                return f"Каждые {n} минут"

        # Каждые N часов: 0 */N * * *
        if month == "*" and dom == "*" and dow == "*" and minute == "0":
            m = re.fullmatch(r"\*/(\d+)", hour)
            if m:
                n = int(m.group(1))
                if n == 1:
                    return "Каждый час"
                if 2 <= n <= 4:
                    return f"Каждые {n} часа"
                return f"Каждые {n} часов"

        # Точное время M H ... — ежедневно или по дням недели
        if minute.isdigit() and hour.isdigit() and month == "*" and dom == "*":
            time_str = f"{int(hour):02d}:{int(minute):02d}"
            if dow == "*":
                return f"Каждый день в {time_str}"

            days = _parse_dow(dow)
            if days is None:
                return f"По cron-выражению: {cron_expr}"

            if days == {1, 2, 3, 4, 5}:
                return f"По будням (пн-пт) в {time_str}"
            if days == {0, 6}:
                return f"По выходным (сб-вс) в {time_str}"
            if len(days) == 1:
                d = next(iter(days))
                return f"Каждую {DAY_NOMINATIVE[d]} в {time_str}"

            names = ", ".join(DAY_NAMES[d] for d in sorted(days))
            return f"По дням: {names} в {time_str}"

        return f"По cron-выражению: {cron_expr}"

    # ------------------------------------------------------------------
    # Job-management
    # ------------------------------------------------------------------

    def register_jobs(self, schedules: list) -> None:
        """Убрать все текущие job-ы и зарегистрировать по одному для каждого enabled расписания."""
        self.scheduler.remove_all_jobs()
        if self._trigger_runner is None:
            return

        for sched in schedules:
            if not sched.enabled:
                continue
            try:
                cron_fields = _parse_cron(sched.cron_expr)
                self.scheduler.add_job(
                    self._trigger_runner,
                    trigger="cron",
                    id=sched.id,
                    kwargs={
                        "schedule_id": sched.id,
                        "mode": sched.mode,
                        "team": sched.team,
                    },
                    replace_existing=True,
                    **cron_fields,
                )
            except Exception:
                logger.exception("scheduler: failed to register job for schedule %s", sched.id)

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_dow(dow: str) -> Optional[set]:
    """Распарсить day-of-week часть cron в множество 0-6 (0=вс..6=сб).

    Поддерживает: ``*`` → все, ``1-5`` → диапазон, ``0,6`` → перечисление,
    ``3`` → один день. Возвращает ``None`` если формат не распознан.
    """
    if dow == "*":
        return set(range(7))
    if "-" in dow:
        bounds = dow.split("-")
        if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
            start, end = int(bounds[0]), int(bounds[1])
            if 0 <= start <= 6 and 0 <= end <= 6 and start <= end:
                return set(range(start, end + 1))
        return None
    if "," in dow:
        try:
            days = {int(x) for x in dow.split(",")}
        except ValueError:
            return None
        if all(0 <= d <= 6 for d in days):
            return days
        return None
    if dow.isdigit():
        d = int(dow)
        if 0 <= d <= 6:
            return {d}
    return None


def _parse_cron(expr: str) -> dict:
    """Преобразовать 5-польное cron-выражение в kwargs для APScheduler CronTrigger."""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 fields): {expr!r}")
    minute, hour, day, month, day_of_week = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }


# ------------------------------------------------------------------
# scheduled_pipeline_runner (T20)
# ------------------------------------------------------------------

async def scheduled_pipeline_runner(*, schedule_id: str, mode: str, team: Optional[str] = None) -> None:
    """Async-коллбек, вызываемый APScheduler по расписанию.

    Открывает собственную DB-сессию, проверяет lock (skip-if-running),
    создаёт SyncRun, прогоняет pipeline и финализирует run.
    """
    from app.repositories.sync_run import SyncRunRepository
    from app.repositories.sync_schedule import SyncScheduleRepository
    from app.services.sync_lock import SyncLock

    db = _get_db_session()
    try:
        lock = SyncLock(db)
        run_repo = SyncRunRepository(db)

        # skip-if-running
        if lock.current_run_id() and not lock.is_stale():
            run = run_repo.create(
                mode=mode,
                trigger="scheduled",
                team=team,
                schedule_id=schedule_id,
            )
            run_repo.finalize(run.id, status="skipped", stages=[], error_text="previous_running")
            logger.info("scheduled_pipeline_runner: skipped (lock held) schedule=%s", schedule_id)
            return

        run = run_repo.create(
            mode=mode,
            trigger="scheduled",
            team=team,
            schedule_id=schedule_id,
        )
        if not lock.acquire(run.id):
            run_repo.finalize(run.id, status="skipped", stages=[], error_text="previous_running")
            return

        try:
            async with JiraClient.from_db(db) as jira:
                orch = _build_orchestrator_local(db, jira, mode=mode, team=team)
                result = await orch.run(
                    mode=mode,
                    trigger="scheduled",
                    team=team,
                    run_id=run.id,
                )
            run_repo.finalize(
                run.id,
                status=result["status"],
                stages=result.get("stages", []),
                error_text=result.get("error"),
            )
            # Обновить next_run_at в расписании
            sched_repo = SyncScheduleRepository(db)
            schedule = sched_repo.get(schedule_id)
            if schedule:
                nxt = SchedulerService.next_run_at(schedule.cron_expr)
                sched_repo.set_last_run(schedule_id, run.id, nxt)
        except Exception:
            logger.exception("scheduled_pipeline_runner: pipeline failed for schedule=%s", schedule_id)
            try:
                run_repo.finalize(run.id, status="failed", stages=[], error_text="unhandled exception")
            except Exception:
                pass
            raise
        finally:
            lock.release()
    finally:
        db.close()


def _get_db_session():
    """Открыть новую DB-сессию (не зависит от FastAPI DI)."""
    from app.database import SessionLocal
    return SessionLocal()


def _build_orchestrator_local(db, jira, *, mode: str, team: Optional[str] = None) -> "PipelineOrchestrator":
    """Собрать оркестратор для scheduled_pipeline_runner (дублирует логику из sync.py)."""
    from app.services.sync_pipeline import PipelineOrchestrator, build_pipeline
    from app.services.mapping_service import MappingService
    from app.services.production_calendar_service import ProductionCalendarService
    from app.services.sync_service import SyncService
    from app.services.event_bus import get_event_bus

    sync_svc = SyncService(db, jira)
    calendar_svc = ProductionCalendarService(db)
    mapping_svc = MappingService(db)
    stages = build_pipeline(
        mode=mode,
        services={"sync": sync_svc, "calendar": calendar_svc, "mapping": mapping_svc},
        team=team,
    )
    return PipelineOrchestrator(stages=stages, db=db, bus=get_event_bus())
