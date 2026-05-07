"""Deterministic outlier detection per theme — no LLM.

Правила сейчас:
- high_hours: часы > P85 темы и при этом ≥ 16 ч (фильтр шума на маленьких задачах).
- many_reopens: reopen_count ≥ 3. Сейчас в БД нет таблицы changelog/transition,
  поэтому reopen_count всегда 0 — правило логически живо, но не срабатывает.
  TODO: подключить, когда появится сбор changelog (см. план следующей итерации).
- many_workers: distinct_workers > 5 — задача собрала много разных людей.
- stale: days_in_progress > 14 и задача не закрыта.

Возвращаем top-5 по value desc после dedup по (issue_id, reason).
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class OutlierCandidate:
    issue_id: str
    issue_key: str
    summary: str
    reason: str   # "high_hours" | "many_reopens" | "many_workers" | "stale"
    value: float
    context: str


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(pct * (len(s) - 1))
    return s[idx]


def detect_outliers_for_theme(
    findings_payload: dict,
    *,
    theme_issues: list[dict],
    theme_p85: Optional[float] = None,
) -> list[OutlierCandidate]:
    """Detect outliers for one theme.

    theme_issues: per-issue dicts with keys:
      issue_id, key, summary, hours, distinct_workers, days_in_progress,
      reopen_count, worklog_count (optional), is_done.
    theme_p85: precomputed 85th percentile of hours for the theme. If None — derived from theme_issues.
    """
    if not theme_issues:
        return []

    hours_values = [float(i.get("hours", 0)) for i in theme_issues]
    if theme_p85 is None:
        theme_p85 = _percentile(hours_values, 0.85)

    out: list[OutlierCandidate] = []
    for it in theme_issues:
        hours = float(it.get("hours", 0))
        distinct = int(it.get("distinct_workers", 0))
        days = int(it.get("days_in_progress", 0))
        reopens = int(it.get("reopen_count", 0))
        worklog_count = int(it.get("worklog_count", 0))
        is_done = bool(it.get("is_done", False))

        if theme_p85 and hours >= theme_p85 and hours >= 16:
            out.append(OutlierCandidate(
                issue_id=it["issue_id"], issue_key=it["key"], summary=it["summary"],
                reason="high_hours", value=hours,
                context=f"{distinct} сотрудников · {worklog_count} ворклогов · {days} дней",
            ))
        if reopens >= 3:
            out.append(OutlierCandidate(
                issue_id=it["issue_id"], issue_key=it["key"], summary=it["summary"],
                reason="many_reopens", value=float(reopens),
                context=f"переоткрыта {reopens}×",
            ))
        if distinct > 5:
            out.append(OutlierCandidate(
                issue_id=it["issue_id"], issue_key=it["key"], summary=it["summary"],
                reason="many_workers", value=float(distinct),
                context=f"{distinct} разных сотрудников",
            ))
        if days > 14 and not is_done:
            out.append(OutlierCandidate(
                issue_id=it["issue_id"], issue_key=it["key"], summary=it["summary"],
                reason="stale", value=float(days),
                context=f"в работе {days} дней",
            ))

    # dedup by (issue_id, reason); top-5 by value desc
    seen: set[tuple[str, str]] = set()
    deduped: list[OutlierCandidate] = []
    for o in sorted(out, key=lambda x: -x.value):
        k = (o.issue_id, o.reason)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(o)
        if len(deduped) >= 5:
            break
    return deduped
