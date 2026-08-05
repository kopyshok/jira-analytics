"""Признаки-проблемы задачи. Чистые функции: ORM сюда не заходит."""
from dataclasses import dataclass
from typing import Optional

from app.services.team_desk.config import DeskConfig

# Порядок важен: значки в интерфейсе идут в этом порядке.
FLAG_ORDER = ["over", "under", "decomp", "childgap", "noest", "nospent", "stale"]

FLAG_LABELS = {
    "over": "Перерасход",
    "under": "Недорасход",
    "decomp": "Без декомпозиции",
    "childgap": "Подзадачи недооценены",
    "noest": "Нет оценки",
    "nospent": "Нет списаний",
    "stale": "Зависла",
}


@dataclass
class IssueFacts:
    """Всё, что нужно для признаков одной задачи. Собирается в query.py."""

    key: str
    status: Optional[str]
    group: str                      # dev | waiting | todo | done | unassigned
    est: Optional[float]            # оценка разработки, ч
    fact: float                     # часы из списаний
    days_in_status: int
    child_est_sum: Optional[float]  # сумма оценок подзадач
    has_children: bool
    is_subtask: bool
    is_analysis: bool               # задача технического анализа


def compute_flags(f: IssueFacts, cfg: DeskConfig) -> list[str]:
    """Коды признаков задачи в порядке FLAG_ORDER."""
    t = cfg.thresholds
    closed = f.group == "done"
    found: set[str] = set()

    if f.est is None:
        # У технического анализа оценки разработки нет по определению —
        # признак «нет оценки» на нём был бы шумом.
        if not f.is_analysis:
            found.add("noest")
    else:
        if f.fact > f.est * (1 + t["overrun_pct"] / 100):
            found.add("over")
        if closed and f.fact < f.est * (t["underrun_pct"] / 100):
            found.add("under")
        if not closed and f.fact == 0:
            found.add("nospent")
        if not f.is_subtask and not f.is_analysis:
            if f.est > t["decomposition_hours"] and not f.has_children:
                found.add("decomp")
            if f.has_children and (f.child_est_sum or 0) < f.est * (
                1 - t["child_gap_pct"] / 100
            ):
                found.add("childgap")

    if not closed and f.days_in_status >= t["stale_days"]:
        found.add("stale")

    return [code for code in FLAG_ORDER if code in found]


def flag_signature(flag: str, f: IssueFacts) -> str:
    """Подпись причины, по которой признак загорелся.

    Отметка «просмотрено» сгорает, когда подпись перестаёт совпадать: задача
    сменила статус, вырос факт, поменялась оценка. Иначе отметка навсегда
    прятала бы реальную проблему.
    """
    est = "-" if f.est is None else f"{f.est:g}"
    fact = f"{round(f.fact, 1):g}"
    if flag == "stale":
        return f"{f.status}"
    if flag in ("over", "under"):
        return f"{est}:{fact}"
    if flag == "decomp":
        return est
    if flag == "childgap":
        child = "-" if f.child_est_sum is None else f"{f.child_est_sum:g}"
        return f"{est}:{child}"
    # noest / nospent гаснут сами, как только появляется оценка или часы.
    return ""
