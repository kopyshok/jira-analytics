"""Отсечка ОПЭ: с какого квартала этап «Запуск (ОПЭ)» больше не планируется.

Настройка хранится строкой вида ``2026Q4`` (пусто — ОПЭ планируем всегда).
Начиная с указанного квартала фаза ОПЭ не создаётся, а её часы вливаются в
Анализ и Разработку по доле ``BacklogItem.opo_analyst_ratio``. Часы не теряются,
поэтому ёмкость команды остаётся прежней, а история старых кварталов —
нетронутой.
"""
from typing import Optional, Union

from sqlalchemy.orm import Session

from app.models import AppSetting

SETTING_KEY = "planning_opo_cutoff"
DEFAULT_ANALYST_RATIO = 0.5


def _quarter_num(quarter: Union[int, str, None]) -> Optional[int]:
    """Квартал из ``4`` / ``"4"`` / ``"Q4"`` в число, иначе None."""
    if quarter is None:
        return None
    try:
        return int(str(quarter).upper().lstrip("Q"))
    except ValueError:
        return None


def get_cutoff(db: Session) -> Optional[tuple[int, int]]:
    """(год, квартал) отсечки или None, если ОПЭ учитываем всегда."""
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).one_or_none()
    raw = (row.value or "").strip() if row else ""
    if "Q" not in raw.upper():
        return None
    year_part, _, quarter_part = raw.upper().partition("Q")
    quarter = _quarter_num(quarter_part)
    try:
        year = int(year_part)
    except ValueError:
        return None
    if quarter is None or not 1 <= quarter <= 4:
        return None
    return year, quarter


def is_off(db: Session, year: Optional[int], quarter: Union[int, str, None]) -> bool:
    """Выключен ли ОПЭ для этого квартала (квартал не раньше отсечки)."""
    cutoff = get_cutoff(db)
    q = _quarter_num(quarter)
    if cutoff is None or year is None or q is None:
        return False
    return (int(year), q) >= cutoff


def fold(hours: dict, ratio: Optional[float]) -> dict:
    """Влить часы ОПЭ в Анализ и Разработку по доле аналитика."""
    r = DEFAULT_ANALYST_RATIO if ratio is None else float(ratio)
    opo = float(hours.get("opo") or 0.0)
    out = {k: float(v or 0.0) for k, v in hours.items()}
    out["analyst"] = float(hours.get("analyst") or 0.0) + opo * r
    out["dev"] = float(hours.get("dev") or 0.0) + opo * (1.0 - r)
    out["opo"] = 0.0
    return out
