"""Срез задач рабочего стола тимлида: выборка, факт, признаки, сводка."""
import statistics
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import Employee, Issue, TeamDeskDailyRate, Worklog
from app.services.team_desk.config import DeskConfig, group_of_status, load_config
from app.services.team_desk.flags import IssueFacts, compute_flags, flag_signature
from app.services.team_desk.marks import active_marks


def _days_in_status(issue: Issue, today: datetime) -> int:
    """Сколько дней задача стоит в текущем статусе."""
    if not issue.status_changed_at:
        return 0
    return max(0, (today - issue.status_changed_at).days)


def _hours_by_person(
    db: Session, issue_ids: list[str]
) -> tuple[dict[str, list[tuple]], dict[str, list[tuple]]]:
    """Часы по людям: (списанные в саму задачу, списанные в её подзадачи).

    Каждая запись — кортеж «учётная запись, имя, роль, часы». Роль нужна, чтобы
    отделить работу разработчика от часов тестировщиков и аналитиков: раздел про
    работу программистов, остальные часы в нём не участвуют вовсе.
    """
    if not issue_ids:
        return {}, {}
    own_rows = (
        db.query(
            Worklog.issue_id,
            Employee.jira_account_id,
            Employee.display_name,
            Employee.role,
            func.sum(Worklog.hours),
        )
        .join(Employee, Employee.id == Worklog.employee_id)
        .filter(Worklog.issue_id.in_(issue_ids))
        .group_by(
            Worklog.issue_id, Employee.jira_account_id,
            Employee.display_name, Employee.role,
        )
        .all()
    )
    child_rows = (
        db.query(
            Issue.parent_id,
            Employee.jira_account_id,
            Employee.display_name,
            Employee.role,
            func.sum(Worklog.hours),
        )
        .join(Worklog, Worklog.issue_id == Issue.id)
        .join(Employee, Employee.id == Worklog.employee_id)
        .filter(Issue.parent_id.in_(issue_ids))
        .group_by(
            Issue.parent_id, Employee.jira_account_id,
            Employee.display_name, Employee.role,
        )
        .all()
    )

    def _group(rows) -> dict[str, list[tuple]]:
        out: dict[str, list[tuple]] = {}
        for issue_id, account_id, name, role, total in rows:
            out.setdefault(issue_id, []).append(
                (account_id, name, role, float(total or 0))
            )
        return out

    return _group(own_rows), _group(child_rows)


def _owner_conditions(cfg: DeskConfig, developer_ids: list[str]) -> list:
    """Чьи задачи берём: поле «Разработчик» плюс тех. анализ по исполнителю."""
    conditions = [Issue.developer_account_id.in_(developer_ids)]
    if cfg.assignee_types:
        conditions.append(
            and_(
                Issue.issue_type.in_(cfg.assignee_types),
                Issue.assignee_account_id.in_(developer_ids),
            )
        )
    return conditions


def _select_issues(
    db: Session,
    cfg: DeskConfig,
    developer_ids: list[str],
    only_open: bool,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> list[Issue]:
    """Задачи, где человек стоит разработчиком, плюс тех. анализ по исполнителю.

    Окно периода задано — к открытым добавляются задачи, созданные или закрытые
    внутри окна: старая задача в работе занимает разработчика в этом периоде
    независимо от того, когда её завели.
    """
    query = db.query(Issue).filter(or_(*_owner_conditions(cfg, developer_ids)))
    if cfg.hidden_statuses:
        # Задача ещё не взята в работу — тимлиду смотреть на неё нечего,
        # и в счётчики она попадать не должна.
        query = query.filter(~Issue.status.in_(cfg.hidden_statuses))
    closed = cfg.status_groups.get("done", [])
    if only_open and closed:
        is_open = ~Issue.status.in_(closed)
        if period_start and period_end:
            start = datetime.combine(period_start, time.min)
            end = datetime.combine(period_end, time.max)
            query = query.filter(
                or_(
                    is_open,
                    Issue.jira_created_at.between(start, end),
                    Issue.resolved_at.between(start, end),
                )
            )
        else:
            query = query.filter(is_open)
    return query.all()


def _done_subtasks(
    db: Session, cfg: DeskConfig, developer_ids: list[str], parent_ids: list[str]
) -> list[Issue]:
    """Закрытые подзадачи под уже показанными родителями — справочно.

    Родитель в работе, вся декомпозиция закрыта — без этого добора он выглядит
    неразбитым. В счётчики и часы такие строки не идут: подзадача не
    самостоятельна, а её часы давно приплюсованы к родителю.
    """
    closed = cfg.status_groups.get("done", [])
    if not parent_ids or not closed or not cfg.subtask_types:
        return []
    query = db.query(Issue).filter(
        Issue.parent_id.in_(parent_ids),
        Issue.issue_type.in_(cfg.subtask_types),
        Issue.status.in_(closed),
        # Свой же состав: иначе в сводке всплывёт карточка постороннего
        # человека с нулём задач.
        or_(*_owner_conditions(cfg, developer_ids)),
    )
    if cfg.hidden_statuses:
        query = query.filter(~Issue.status.in_(cfg.hidden_statuses))
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


def _daily_rates(db: Session, issue_ids: list[str]) -> dict[str, float]:
    """Дневные нормы «резиновых» задач: задача → часов в день."""
    if not issue_ids:
        return {}
    rows = (
        db.query(TeamDeskDailyRate.issue_id, TeamDeskDailyRate.hours)
        .filter(TeamDeskDailyRate.issue_id.in_(issue_ids))
        .all()
    )
    return {issue_id: float(hours) for issue_id, hours in rows if hours}


def build_overview(
    db: Session,
    developer_ids: list[str],
    only_open: bool = True,
    show_reviewed: bool = False,
    show_done_subtasks: bool = True,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
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

    issues = _select_issues(
        db, cfg, developer_ids, only_open, period_start, period_end
    )
    if only_open and show_done_subtasks:
        # Фильтр статуса вообще применялся — значит закрытая декомпозиция
        # выпала и её нужно вернуть. В режиме «все задачи» она и так на месте.
        known = {i.id for i in issues}
        extra = _done_subtasks(db, cfg, developer_ids, [i.id for i in issues])
        issues += [i for i in extra if i.id not in known]
    ids = [i.id for i in issues]
    id_set = set(ids)
    own_hours, child_hours = _hours_by_person(db, ids)
    child_est, child_count = _child_estimates(db, ids)
    daily_rates = _daily_rates(db, ids)
    queue_statuses = set(cfg.queue_statuses)
    dev_roles = set(cfg.developer_roles)

    rows: list[dict] = []
    signatures: dict[tuple[str, str], str] = {}
    for issue in issues:
        group = group_of_status(cfg, issue.status)
        is_analysis = issue.issue_type in cfg.assignee_types
        is_subtask = issue.issue_type in cfg.subtask_types
        is_orphan = is_subtask and (
            not issue.parent_id or issue.parent_id not in id_set
        )
        # У тех. анализа поле «Разработчик» пустое — там владелец это исполнитель.
        owner_id = issue.developer_account_id or (
            issue.assignee_account_id if is_analysis else None
        )
        owner_name = issue.developer_display_name or (
            issue.assignee_display_name if is_analysis else None
        )

        # Факт — часы ВЛАДЕЛЬЦА: в самой задаче и в её подзадачах. Часы
        # тестировщиков и аналитиков в разделе не участвуют вовсе — тимлид
        # смотрит работу программистов, а оценка в задаче тоже только на неё.
        rows_own = own_hours.get(issue.id, [])
        fact = sum(
            hours
            for account_id, _, _, hours in rows_own + child_hours.get(issue.id, [])
            if owner_id and account_id == owner_id
        )
        # Часы другого разработчика в задаче — ошибка: работу двигает владелец,
        # а списанное коллегой попадёт в его собственную оценку не туда.
        alien = [
            {"name": name, "hours": round(hours, 1)}
            for account_id, name, role, hours in rows_own
            if account_id != owner_id and role in dev_roles
        ]
        alien_hours = sum(item["hours"] for item in alien)
        by_person = ([{"name": owner_name, "hours": round(fact, 1)}] if fact else [])
        by_person += alien

        facts = IssueFacts(
            key=issue.key,
            status=issue.status,
            group=group,
            est=issue.dev_est_hours,
            fact=fact,
            alien_hours=alien_hours,
            days_in_status=_days_in_status(issue, today),
            child_est_sum=child_est.get(issue.id),
            has_children=child_count.get(issue.id, 0) > 0,
            is_subtask=is_subtask,
            is_analysis=is_analysis,
            is_orphan=is_orphan,
        )
        flags = compute_flags(facts, cfg)
        for flag in flags:
            signatures[(flag, issue.id)] = flag_signature(flag, facts)

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
                "fact_by_person": by_person,
                # Часы других разработчиков — в факт не идут, показываются
                # подсказкой и подсвечиваются замечанием.
                "alien_hours": round(alien_hours, 1),
                "days_in_status": facts.days_in_status,
                "is_analysis": is_analysis,
                "is_subtask": facts.is_subtask,
                # Самостоятельная задача = не подзадача либо подзадача-сирота.
                # Только такие идут в счётчики, часы и очередь: оценка подзадачи
                # уже сидит в родителе и задваивать её нельзя.
                "is_standalone": not facts.is_subtask or is_orphan,
                # Исполнитель в Jira: пока задача на РП или тимлиде, работать
                # по ней разработчик ещё не может — вторая строка очереди
                # считает только те, где исполнитель он сам.
                "assigned_to_owner": bool(
                    owner_id and issue.assignee_account_id == owner_id
                ),
                # Задача формирует очередь — по ней же строится расшифровка
                # по клику на плитке.
                "in_queue": (
                    issue.status in queue_statuses
                    and bool(owner_id)
                    and (not facts.is_subtask or is_orphan)
                ),
                # Дневная норма «резиновой» задачи; пусто — обычная задача.
                "daily_rate": daily_rates.get(issue.id),
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
        "developers": _summarize(rows, developer_ids, cfg.wip_statuses),
        "issues": rows,
        "flag_counts": flag_counts,
    }


def _summarize(
    rows: list[dict], developer_ids: list[str], wip_statuses: Optional[list[str]] = None
) -> list[dict]:
    """Сводка на человека: счётчики по группам статусов, часы, точность, признаки.

    Счётчики и часы считаются по самостоятельным задачам: подзадача — это
    декомпозиция, её оценка уже учтена в родителе, а часы подтянуты туда же.
    Признаки — по всем строкам: проблема на подзадаче остаётся проблемой.

    Разбивка по конкретным статусам (`status_counts`) считается по тому же
    составу, что и `total_issues`, — их сумма обязана совпадать, иначе на экране
    придётся объяснять расхождение. Отдаётся целиком: какие статусы показать,
    решает интерфейс.

    `in_progress` — задачи, которые человек делает руками прямо сейчас
    (`wip_statuses`). Это не то же, что `in_dev`: группа «у разработчика» шире и
    держит за ним ещё код-ревью и ожидание помещения, а в лимите одновременной
    работы такие задачи считать нельзя.
    """
    wip = set(wip_statuses or [])
    by_dev: dict[str, list[dict]] = {dev_id: [] for dev_id in developer_ids}
    for row in rows:
        by_dev.setdefault(row["developer_id"], []).append(row)

    result = []
    for dev_id, items in by_dev.items():
        if not items:
            continue
        main = [r for r in items if r["is_standalone"]]
        ratios = [
            r["fact_hours"] / r["est_hours"]
            for r in main
            if r["est_hours"] and r["fact_hours"] > 0
        ]
        flag_counts: dict[str, int] = {}
        for row in items:
            for flag in row["flags"]:
                flag_counts[flag] = flag_counts.get(flag, 0) + 1
        status_counts: dict[str, int] = {}
        for row in main:
            status = row["status"] or "—"
            status_counts[status] = status_counts.get(status, 0) + 1
        result.append(
            {
                "developer_id": dev_id,
                "display_name": items[0]["developer_name"],
                "total_issues": len(main),
                "in_dev": sum(1 for r in main if r["status_group"] == "dev"),
                "in_progress": sum(1 for r in main if r["status"] in wip),
                "waiting": sum(1 for r in main if r["status_group"] == "waiting"),
                "todo": sum(1 for r in main if r["status_group"] == "todo"),
                "est_hours": sum(r["est_hours"] or 0 for r in main),
                "fact_hours": sum(r["fact_hours"] for r in main),
                "accuracy": round(statistics.median(ratios), 2) if ratios else None,
                "flag_counts": flag_counts,
                "status_counts": status_counts,
            }
        )
    result.sort(key=lambda d: d["display_name"] or "")
    return result
