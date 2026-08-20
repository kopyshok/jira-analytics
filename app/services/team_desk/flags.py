"""Признаки-проблемы задачи. Чистые функции: ORM сюда не заходит."""
from dataclasses import dataclass
from typing import Optional

from app.services.team_desk.config import DeskConfig

# Порядок важен: значки в интерфейсе идут в этом порядке.
FLAG_ORDER = [
    "over", "under", "decomp", "childgap", "orphan", "alien",
    "noest", "nospent", "idlespent", "stale",
]

FLAG_LABELS = {
    "over": "Перерасход",
    "under": "Недорасход",
    "decomp": "Без декомпозиции",
    "childgap": "Подзадачи недооценены",
    "orphan": "Подзадача без родителя",
    "alien": "Часы другого разработчика",
    "noest": "Нет оценки",
    "nospent": "Нет списаний",
    "idlespent": "Часы в неначатой",
    "stale": "Зависла",
}


# Порог, который обслуживает только один признак. Признак выключен — порог
# незачем показывать и незачем объяснять: интерфейс прячет его по этой карте.
FLAG_THRESHOLDS = {
    "over": "overrun_pct",
    "under": "underrun_pct",
    "decomp": "decomposition_hours",
    "childgap": "child_gap_pct",
    "stale": "stale_days",
}


@dataclass
class IssueFacts:
    """Всё, что нужно для признаков одной задачи. Собирается в query.py."""

    key: str
    status: Optional[str]
    group: str                      # dev | waiting | todo | done | unassigned
    est: Optional[float]            # оценка разработки, ч
    fact: float                     # часы владельца задачи (свои + свои в подзадачах)
    days_in_status: int
    child_est_sum: Optional[float]  # сумма оценок подзадач
    has_children: bool
    is_subtask: bool
    is_analysis: bool               # задача технического анализа
    is_orphan: bool = False         # подзадача, родителя которой нет в срезе
    alien_hours: float = 0.0        # часы других разработчиков в этой задаче


def compute_flags(f: IssueFacts, cfg: DeskConfig) -> list[str]:
    """Коды признаков задачи в порядке FLAG_ORDER. Выключенные не возвращаются."""
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

    # Подзадача — декомпозиция родителя, её оценка живёт в родителе. Родителя
    # в срезе нет — значит связь порвана: часы такой подзадачи считать не с чем,
    # и она идёт в расчёты как самостоятельная. Это ошибка данных, не норма.
    if f.is_orphan:
        found.add("orphan")

    # В задачу списался другой разработчик. Работу двигает владелец: чужие часы
    # либо списаны не туда, либо задачу делают вдвоём без декомпозиции — и в
    # обоих случаях оценка владельца перестаёт что-то значить.
    if f.alien_hours > 0:
        found.add("alien")

    # Часы списаны, а задача так и стоит в «не начатых». Статус готовности
    # к работе означает, что работа не идёт: раз есть часы — статус врёт.
    if f.group == "todo" and f.fact > 0:
        found.add("idlespent")

    if not closed and f.days_in_status >= t["stale_days"]:
        found.add("stale")

    off = set(cfg.disabled_flags)
    return [code for code in FLAG_ORDER if code in found and code not in off]


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
    if flag == "idlespent":
        # Отметка сгорает, когда задачу сдвинули по статусу или дописали часы.
        return f"{f.status}:{fact}"
    if flag in ("over", "under"):
        return f"{est}:{fact}"
    if flag == "alien":
        # Отметка сгорает, когда чужих часов стало больше или меньше.
        return f"{round(f.alien_hours, 1):g}"
    if flag == "decomp":
        return est
    if flag == "childgap":
        child = "-" if f.child_est_sum is None else f"{f.child_est_sum:g}"
        return f"{est}:{child}"
    # noest / nospent гаснут сами, как только появляется оценка или часы.
    return ""
