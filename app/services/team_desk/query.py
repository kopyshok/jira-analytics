"""Срез задач рабочего стола тимлида: выборка, факт, признаки, сводка."""
import statistics
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import Employee, Issue, Worklog
from app.services.team_desk.config import DeskConfig, group_of_status, load_config
from app.services.team_desk.flags import IssueFacts, compute_flags, flag_signature
from app.services.team_desk.marks import active_marks


def _days_in_status(issue: Issue, today: datetime) -> int:
    """Сколько дней задача стоит в текущем статусе."""
    if not issue.status_changed_at:
        return 0
    return max(0, (today - issue.status_changed_at).days)


def _fact_by_issue(db: Session, issue_ids: list[str]) -> dict[str, float]:
    """Часы списаний по задачам. Факт — сумма по всем, кто списывал."""
    if not issue_ids:
        return {}
    rows = (
        db.query(Worklog.issue_id, func.sum(Worklog.hours))
        .filter(Worklog.issue_id.in_(issue_ids))
        .group_by(Worklog.issue_id)
        .all()
    )
    return {issue_id: float(total or 0) for issue_id, total in rows}


def _fact_by_person(db: Session, issue_ids: list[str]) -> dict[str, list[dict]]:
    """Разбивка факта по людям — показывается при раскрытии строки."""
    if not issue_ids:
        return {}
    rows = (
        db.query(Worklog.issue_id, Employee.display_name, func.sum(Worklog.hours))
        .join(Employee, Employee.id == Worklog.employee_id)
        .filter(Worklog.issue_id.in_(issue_ids))
        .group_by(Worklog.issue_id, Employee.display_name)
        .all()
    )
    out: dict[str, list[dict]] = {}
    for issue_id, name, total in rows:
        out.setdefault(issue_id, []).append({"name": name, "hours": float(total or 0)})
    return out


def _select_issues(
    db: Session, cfg: DeskConfig, developer_ids: list[str], only_open: bool
) -> list[Issue]:
    """Задачи, где человек стоит разработчиком, плюс тех. анализ по исполнителю."""
    conditions = [Issue.developer_account_id.in_(developer_ids)]
    if cfg.assignee_types:
        conditions.append(
            and_(
                Issue.issue_type.in_(cfg.assignee_types),
                Issue.assignee_account_id.in_(developer_ids),
            )
        )
    query = db.query(Issue).filter(or_(*conditions))
    if only_open:
        closed = cfg.status_groups.get("done", [])
        if closed:
            query = query.filter(~Issue.status.in_(closed))
    return query.all()


def _child_estimates(db: Session, issue_ids: list[str]) -> tuple[dict, dict]:
    """Сумма оценок и количество подзадач по родителям."""
    if not issue_ids:
        return {}, {}
    rows = (
        db.query(Issue.parent_id, func.sum(Issue.dev_est_hours), func.count(Issue.id))
        .filter(Issue.parent_id.in_(issue_ids))
        .group_by(Issue.parent_id)
        .all()
    )
    est_sum = {parent_id: float(total or 0) for parent_id, total, _ in rows}
    counts = {parent_id: int(count or 0) for parent_id, _, count in rows}
    return est_sum, counts


def build_overview(
    db: Session,
    developer_ids: list[str],
    only_open: bool = True,
    show_reviewed: bool = False,
    today: Optional[datetime] = None,
) -> dict:
    """Всё, что нужно любой из трёх раскладок: задачи, сводка, признаки.

    developer_ids — учётные записи Jira. Состав команды в них разворачивает
    вызывающий код: здесь уже готовый список людей.
    """
    cfg = load_config(db)
    today = today or datetime.utcnow()
    if not developer_ids:
        return {"developers": [], "issues": [], "flag_counts": {}}

    issues = _select_issues(db, cfg, developer_ids, only_open)
    ids = [i.id for i in issues]
    fact_map = _fact_by_issue(db, ids)
    person_map = _fact_by_person(db, ids)
    child_est, child_count = _child_estimates(db, ids)

    rows: list[dict] = []
    signatures: dict[tuple[str, str], str] = {}
    for issue in issues:
        group = group_of_status(cfg, issue.status)
        is_analysis = issue.issue_type in cfg.assignee_types
        facts = IssueFacts(
            key=issue.key,
            status=issue.status,
            group=group,
            est=issue.dev_est_hours,
            fact=fact_map.get(issue.id, 0.0),
            days_in_status=_days_in_status(issue, today),
            child_est_sum=child_est.get(issue.id),
            has_children=child_count.get(issue.id, 0) > 0,
            is_subtask=issue.issue_type in cfg.subtask_types,
            is_analysis=is_analysis,
        )
        flags = compute_flags(facts, cfg)
        for flag in flags:
            signatures[(flag, issue.id)] = flag_signature(flag, facts)

        # У тех. анализа поле «Разработчик» пустое — там владелец это исполнитель.
        owner_id = issue.developer_account_id or (
            issue.assignee_account_id if is_analysis else None
        )
        owner_name = issue.developer_display_name or (
            issue.assignee_display_name if is_analysis else None
        )
        rows.append(
            {
                "id": issue.id,
                "key": issue.key,
                "summary": issue.summary,
                "issue_type": issue.issue_type,
                "status": issue.status,
                "status_group": group,
                "developer_id": owner_id,
                "developer_name": owner_name,
                "parent_id": issue.parent_id,
                "est_hours": issue.dev_est_hours,
                "fact_hours": facts.fact,
                "fact_by_person": person_map.get(issue.id, []),
                "days_in_status": facts.days_in_status,
                "is_analysis": is_analysis,
                "is_subtask": facts.is_subtask,
                "flags": flags,
                "signatures": {f: signatures[(f, issue.id)] for f in flags},
            }
        )

    marks = active_marks(db, ids, signatures)
    for row in rows:
        reviewed = []
        for flag in list(row["flags"]):
            mark = marks.get((row["id"], flag))
            if not mark:
                continue
            if not show_reviewed:
                # Переключатель выключен — признака на экране быть не должно
                # вообще: ни в проблемных, ни приглушённым.
                row["flags"].remove(flag)
                continue
            reviewed.append(
                {
                    "flag": flag,
                    "comment": mark.comment,
                    "marked_at": mark.marked_at.isoformat(),
                }
            )
        row["reviewed"] = reviewed

    flag_counts: dict[str, int] = {}
    for row in rows:
        for flag in row["flags"]:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    return {
        "developers": _summarize(rows, developer_ids),
        "issues": rows,
        "flag_counts": flag_counts,
    }


def _summarize(rows: list[dict], developer_ids: list[str]) -> list[dict]:
    """Сводка на человека: счётчики по группам статусов, часы, точность, признаки."""
    by_dev: dict[str, list[dict]] = {dev_id: [] for dev_id in developer_ids}
    for row in rows:
        by_dev.setdefault(row["developer_id"], []).append(row)

    result = []
    for dev_id, items in by_dev.items():
        if not items:
            continue
        ratios = [
            r["fact_hours"] / r["est_hours"]
            for r in items
            if r["est_hours"] and r["fact_hours"] > 0
        ]
        flag_counts: dict[str, int] = {}
        for row in items:
            for flag in row["flags"]:
                flag_counts[flag] = flag_counts.get(flag, 0) + 1
        result.append(
            {
                "developer_id": dev_id,
                "display_name": items[0]["developer_name"],
                "total_issues": len(items),
                "in_dev": sum(1 for r in items if r["status_group"] == "dev"),
                "waiting": sum(1 for r in items if r["status_group"] == "waiting"),
                "todo": sum(1 for r in items if r["status_group"] == "todo"),
                "est_hours": sum(r["est_hours"] or 0 for r in items),
                "fact_hours": sum(r["fact_hours"] for r in items),
                "accuracy": round(statistics.median(ratios), 2) if ratios else None,
                "flag_counts": flag_counts,
            }
        )
    result.sort(key=lambda d: d["display_name"] or "")
    return result
