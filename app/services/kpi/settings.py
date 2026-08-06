"""Общие настройки раздела KPI. Хранятся в AppSetting, читаются с дефолтами."""
import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

DEFAULT_EXCLUDED_STATUSES = ["Отменено"]

# Способы расчёта срока внесения трудозатрат:
#   hours_from_start — «часов от времени работы», формулировка ТЗ: запись
#       просрочена, если создана позже чем через N часов после времени начала
#       работы, указанного в ней. Производственный календарь не участвует.
#   calendar — «рабочие дни и время отсечки»: не позже указанного времени
#       N-го рабочего дня, выходные и праздники пропускаются.
WORKLOG_DEADLINE_MODES = {"hours_from_start", "calendar"}


@dataclass
class KpiSettings:
    """Общие настройки раздела KPI с дефолтами."""

    excluded_statuses: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDED_STATUSES))
    # По умолчанию — способ из ТЗ (решение заказчика, спека доработок
    # 2026-08-03, раздел 4).
    worklog_deadline_mode: str = "hours_from_start"
    worklog_deadline_hours: int = 18
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
    if rows.get("kpi_worklog_deadline_mode") in WORKLOG_DEADLINE_MODES:
        s.worklog_deadline_mode = rows["kpi_worklog_deadline_mode"]
    if rows.get("kpi_worklog_deadline_hours"):
        try:
            s.worklog_deadline_hours = int(rows["kpi_worklog_deadline_hours"])
        except ValueError:
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
