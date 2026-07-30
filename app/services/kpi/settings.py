"""Общие настройки раздела KPI. Хранятся в AppSetting, читаются с дефолтами."""
import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

DEFAULT_EXCLUDED_STATUSES = ["Отменено"]


@dataclass
class KpiSettings:
    """Общие настройки раздела KPI с дефолтами."""

    excluded_statuses: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDED_STATUSES))
    worklog_deadline_days: int = 1
    worklog_deadline_time: str = "12:00"
    empty_policy: str = "redistribute"


def read_kpi_settings(db: Session) -> KpiSettings:
    """Прочитать настройки KPI из AppSetting, недостающие ключи — по дефолту."""
    rows = {
        r.key: r.value
        for r in db.query(AppSetting).filter(AppSetting.key.like("kpi_%")).all()
    }
    s = KpiSettings()
    raw_statuses = rows.get("kpi_excluded_statuses")
    if raw_statuses:
        try:
            parsed = json.loads(raw_statuses)
            if isinstance(parsed, list):
                s.excluded_statuses = [str(x) for x in parsed]
        except json.JSONDecodeError:
            pass
    if rows.get("kpi_worklog_deadline_days"):
        try:
            s.worklog_deadline_days = int(rows["kpi_worklog_deadline_days"])
        except ValueError:
            pass
    if rows.get("kpi_worklog_deadline_time"):
        s.worklog_deadline_time = rows["kpi_worklog_deadline_time"]
    if rows.get("kpi_empty_policy") in {"redistribute", "full", "zero"}:
        s.empty_policy = rows["kpi_empty_policy"]
    return s
