"""Применение переезда: перепривязка базы к новой Jira одной транзакцией.

Внутренние UUID не меняются — переписываются только id Jira. Порядок:
захват (состояние ``pending`` → ``applying`` одной записью: второй запуск
получает отказ) → настройки полей → ворклоги и комментарии (у задач,
получающих id новой Jira, и у удаляемых — удаляются: ворклоги вернёт
полная синхронизация, комментарии синк не загружает; у задач, остающихся
с облачным id, — сохраняются с префиксом) → проекты → задачи (удаление по решениям, затем всем id префикс
«cloud:» и новые id по ключу — так новый id, совпавший со старым id другой
задачи, не упирается в уникальность) → кандидаты оценки → сотрудники (тот
же приём) → id людей в задачах, бэклоге, фильтре стола тимлида и снимках
KPI → scope → состояние «переезд завершён». Ошибка на любом шаге — откат,
база остаётся как была (и состояние снова ``pending``).

Без пары в новой Jira id остаётся со старым значением под префиксом
«cloud:»: оставленные по решению задачи и их ворклоги и комментарии, задачи
и сами проекты, которых нет в новой Jira, сотрудники без привязки (и их id
в задачах, бэклоге, фильтрах и снимках KPI). Префикс гарантирует, что
такое значение не совпадёт с id новой Jira: синк их не узнаёт и не
перезаписывает.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy import case, delete, literal, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    BacklogItem,
    CategoryMapping,
    Comment,
    Employee,
    Issue,
    IssueClassification,
    IssueLink,
    KpiApproval,
    PlanAudit,
    Project,
    ProjectAISummary,
    ScopeProject,
    ScopeRoot,
    TeamDeskDailyRate,
    TeamDeskMark,
    User,
    Worklog,
)
from app.services.jira_migration import store
from app.services.jira_migration.fields import (
    AUTO_CACHE_KEYS,
    load_field_snapshot,
    remap_plan_sources,
    rewrite_setting_value,
)
from app.services.jira_migration.issues import chunks
from app.services.jira_migration.resolution import (
    BLOCK_DONE,
    BLOCK_NO_REPORT,
    Resolution,
    collect_blockers,
    resolve,
)
from app.services.jira_migration.state import (
    CLOUD_PREFIX,
    MIGRATION_STATE_KEY,
    STATE_DONE,
    STATE_PENDING,
    get_migration_state,
    set_migration_state,
)

logger = logging.getLogger(__name__)

BULK = 1000
_NO_SYNC = {"synchronize_session": False}
# Состояние на время транзакции применения. Не ``done`` — синк остаётся запрещён;
# снаружи транзакции не видно никогда: фиксируется только вместе с ``done``.
STATE_APPLYING = "applying"
BLOCK_CLAIMED = "Переезд уже применяется или применён — обновите страницу"


class ApplyRefused(Exception):
    """Предусловия не выполнены — причины в ``blockers``. База не тронута."""

    def __init__(self, blockers: list[str]) -> None:
        super().__init__("; ".join(blockers))
        self.blockers = blockers


def apply_migration(db: Session, *, now: datetime, backup_confirmed: bool) -> dict[str, Any]:
    """Перепривязать базу к новой Jira и поставить «переезд завершён». Коммитит один раз.

    Предусловия проверяются заново внутри той же транзакции (свежий отчёт,
    нет нерешённых пунктов, копия базы, состояние ``pending``). Любая ошибка
    после первой записи — откат и исключение наружу.
    """
    if get_migration_state(db) == STATE_DONE:
        # Сопоставления отчёта построены по старым id — по перепривязанной базе их не считаем.
        raise ApplyRefused([BLOCK_DONE])
    res = resolve(db)
    blockers = collect_blockers(
        db, now=now, backup_confirmed=backup_confirmed, job_running=False, resolution=res,
    )
    if blockers:
        raise ApplyRefused(blockers)
    if res is None:
        raise ApplyRefused([BLOCK_NO_REPORT])
    row = res.row
    maps = store.report_maps(row)
    issue_map: Mapping[str, str] = maps.get("issues", {})
    delete_keys = res.issues_to_delete()
    try:
        _claim(db)
        summary: dict[str, Any] = {"settings": _apply_fields(db, res)}
        summary.update(_settle_worklogs_and_comments(db, issue_map, delete_keys))
        summary["projects"] = _rebind_projects(db, maps.get("projects", {}))
        summary["issues_deleted"] = _delete_issues(db, delete_keys)
        summary["issues_rebound"] = _rebind_issues(db, issue_map)
        summary["plan_sources"], summary["choices_dropped"] = _remap_plan_sources(db, res.fields.mapping)
        people_map, bound, unbound = _rebind_employees(db, res)
        summary["employees_bound"] = bound
        summary["employees_unbound"] = unbound
        summary["people_refs"], summary["kpi_payload_skipped"] = _rewrite_people_refs(db, people_map)
        _rebind_scope(db, maps)
        set_migration_state(db, STATE_DONE)
        # Отчёт удалён параллельно — фиксация упадёт на обновлении строки и всё откатит.
        row.applied_at = now
        row.apply_summary_json = json.dumps(summary, ensure_ascii=False)
        db.commit()
    except ApplyRefused:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Применение переезда не удалось — изменения откатаны")
        raise
    logger.info("Переезд на новую Jira применён: %s", summary)
    return summary


def _rowcount(result: Any) -> int:
    return cast(CursorResult[Any], result).rowcount or 0


def _claim(db: Session) -> None:
    """Первая запись применения: ``pending`` → ``applying`` одним условным UPDATE.

    Второй одновременный запуск упирается в блокировку строки состояния, а
    после фиксации первого не находит ``pending`` — отказ. Откат первого
    возвращает ``pending``, и второй может пройти.
    """
    claimed = _rowcount(db.execute(
        update(AppSetting)
        .where(AppSetting.key == MIGRATION_STATE_KEY, AppSetting.value == STATE_PENDING)
        .values(value=STATE_APPLYING)
        .execution_options(**_NO_SYNC)
    ))
    if claimed != 1:
        raise ApplyRefused([BLOCK_CLAIMED])


def _apply_fields(db: Session, res: Resolution) -> int:
    """Настройки полей из облачного снимка → поля новой Jira; автокэши без поля удаляются."""
    snapshot = load_field_snapshot(db)
    written = 0
    for key, old_value in snapshot.items():
        new_value = rewrite_setting_value(old_value, res.fields.mapping, res.fields.names)
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if key in AUTO_CACHE_KEYS and not new_value:
            if row is not None:
                db.delete(row)
            continue
        if row is None:
            db.add(AppSetting(key=key, value=new_value))
        else:
            row.value = new_value
        written += 1
    leftover = sorted(AUTO_CACHE_KEYS - set(snapshot))
    if leftover:
        db.execute(delete(AppSetting).where(AppSetting.key.in_(leftover)).execution_options(**_NO_SYNC))
    db.flush()
    return written


def _settle_worklogs_and_comments(
    db: Session, issue_map: Mapping[str, str], delete_keys: Sequence[str],
) -> dict[str, int]:
    """Ворклоги и комментарии: удалить у перепривязанных и удаляемых задач, сохранить у остальных.

    Задачи, получающие id новой Jira, синхронизируются заново со всеми
    ворклогами (id в новой Jira другие) — их строки удаляются; комментарии
    тоже удаляются: со старыми id они не годятся, а синк их не загружает.
    Удаляемые задачи — тоже (внешний ключ). Задачи, остающиеся с
    облачным id (оставленные по решению, проекты, которых нет в новой Jira),
    синк не тронет: их часы и комментарии сохраняются, а id получают префикс
    «cloud:», чтобы не совпасть с id новой Jira.

    Категории удалённых ворклогов удаляются: пересчёт категорий только
    добавляет строки, старые остались бы сиротами.
    """
    deleted = set(delete_keys)
    kept_ids = [
        pk for pk, key in db.query(Issue.id, Issue.key).all()
        if key not in issue_map and key not in deleted
    ]
    worklogs_kept = comments_kept = 0
    for chunk in chunks(kept_ids):
        worklogs_kept += _rowcount(db.execute(
            update(Worklog).where(Worklog.issue_id.in_(chunk))
            .values(jira_worklog_id=literal(CLOUD_PREFIX) + Worklog.jira_worklog_id)
            .execution_options(**_NO_SYNC)
        ))
        comments_kept += _rowcount(db.execute(
            update(Comment).where(Comment.issue_id.in_(chunk))
            .values(jira_comment_id=literal(CLOUD_PREFIX) + Comment.jira_comment_id)
            .execution_options(**_NO_SYNC)
        ))
    worklogs_deleted = _rowcount(db.execute(
        delete(Worklog).where(~Worklog.jira_worklog_id.startswith(CLOUD_PREFIX)).execution_options(**_NO_SYNC)
    ))
    comments_deleted = _rowcount(db.execute(
        delete(Comment).where(~Comment.jira_comment_id.startswith(CLOUD_PREFIX)).execution_options(**_NO_SYNC)
    ))
    db.execute(
        delete(CategoryMapping)
        .where(CategoryMapping.entity_type == "worklog", CategoryMapping.entity_id.not_in(select(Worklog.id)))
        .execution_options(**_NO_SYNC)
    )
    return {
        "worklogs_deleted": worklogs_deleted,
        "worklogs_kept": worklogs_kept,
        "comments_deleted": comments_deleted,
        "comments_kept": comments_kept,
    }


def _rebind_projects(db: Session, project_ids: Mapping[str, str]) -> int:
    """Префикс «cloud:» всем проектам, затем новые id по ключу."""
    db.execute(
        update(Project)
        .values(jira_project_id=literal(CLOUD_PREFIX) + Project.jira_project_id)
        .execution_options(**_NO_SYNC)
    )
    params = [
        {"id": pk, "jira_project_id": project_ids[key]}
        for pk, key in db.query(Project.id, Project.key).all() if key in project_ids
    ]
    if params:
        db.execute(update(Project), params)
    return len(params)


def _delete_issues(db: Session, keys: Sequence[str]) -> int:
    """Удалить задачи с их строками сервиса. Каскады не полагаются на настройки базы."""
    ids: list[str] = []
    for chunk in chunks(list(dict.fromkeys(keys))):
        ids.extend(pk for (pk,) in db.query(Issue.id).filter(Issue.key.in_(chunk)).all())
    if not ids:
        return 0
    # Сначала все ссылки (иначе Postgres откажет по внешнему ключу), потом сами задачи.
    for chunk in chunks(ids):
        db.execute(
            delete(IssueLink)
            .where(or_(IssueLink.source_issue_id.in_(chunk), IssueLink.target_issue_id.in_(chunk)))
            .execution_options(**_NO_SYNC)
        )
        for model in (IssueClassification, PlanAudit, ProjectAISummary, TeamDeskMark, TeamDeskDailyRate):
            db.execute(delete(model).where(model.issue_id.in_(chunk)).execution_options(**_NO_SYNC))
        db.execute(
            update(BacklogItem).where(BacklogItem.issue_id.in_(chunk)).values(issue_id=None)
            .execution_options(**_NO_SYNC)
        )
        db.execute(
            update(Issue).where(Issue.parent_id.in_(chunk)).values(parent_id=None)
            .execution_options(**_NO_SYNC)
        )
        db.execute(
            delete(CategoryMapping)
            .where(CategoryMapping.entity_type == "issue", CategoryMapping.entity_id.in_(chunk))
            .execution_options(**_NO_SYNC)
        )
    for chunk in chunks(ids):
        db.execute(delete(Issue).where(Issue.id.in_(chunk)).execution_options(**_NO_SYNC))
    return len(ids)


def _rebind_issues(db: Session, issue_ids: Mapping[str, str]) -> int:
    """Префикс «cloud:» всем, затем новые id по ключу. Оставленные без пары сохраняют префикс."""
    db.execute(
        update(Issue)
        .values(jira_issue_id=literal(CLOUD_PREFIX) + Issue.jira_issue_id)
        .execution_options(**_NO_SYNC)
    )
    params = [
        {"id": pk, "jira_issue_id": issue_ids[key]}
        for pk, key in db.query(Issue.id, Issue.key).all() if key in issue_ids
    ]
    for chunk in chunks(params, BULK):
        db.execute(update(Issue), list(chunk))
    return len(params)


def _remap_plan_sources(db: Session, mapping: Mapping[str, Optional[str]]) -> tuple[int, int]:
    """Кандидаты оценки и выбор при споре — на поля новой Jira.

    Возвращает (задач изменено, задач со сброшенным выбором оценки). Удалённые
    задачи к этому шагу уже удалены — в счёт не попадают.
    """
    rows = (
        db.query(Issue.id, Issue.planned_hours_sources, Issue.planned_hours_choice)
        .filter(or_(Issue.planned_hours_sources.isnot(None), Issue.planned_hours_choice.isnot(None)))
        .all()
    )
    params = []
    dropped = 0
    for pk, sources, choice in rows:
        new_sources, new_choice, choice_dropped = remap_plan_sources(sources, choice, mapping)
        if choice_dropped:
            dropped += 1
        if new_sources != sources or new_choice != choice:
            params.append({"id": pk, "planned_hours_sources": new_sources, "planned_hours_choice": new_choice})
    for chunk in chunks(params, BULK):
        db.execute(update(Issue), list(chunk))
    return len(params), dropped


def _rebind_employees(db: Session, res: Resolution) -> tuple[dict[str, str], int, int]:
    """Сотрудники отчёта: префикс всем, затем ``key`` и логин новой Jira привязанным.

    Возвращает (старый облачный id → новое значение, привязано, без привязки).
    Без привязки сотрудник сохраняет старый id с префиксом «cloud:» и в синке
    не участвует.
    """
    report_ids = [row["employee_id"] for row in res.report.get("people", [])]
    current: dict[str, str] = {}
    for chunk in chunks(report_ids):
        current.update({
            pk: account
            for pk, account in db.query(Employee.id, Employee.jira_account_id).filter(Employee.id.in_(chunk))
        })
    for chunk in chunks(list(current)):
        db.execute(
            update(Employee)
            .where(Employee.id.in_(chunk))
            .values(jira_account_id=literal(CLOUD_PREFIX) + Employee.jira_account_id)
            .execution_options(**_NO_SYNC)
        )
    people_map: dict[str, str] = {}
    params: list[dict[str, Any]] = []
    bound = unbound = 0
    for employee_id, old_account in current.items():
        outcome = res.people.get(employee_id)
        if outcome is not None and outcome.key:
            params.append({"id": employee_id, "jira_account_id": outcome.key, "jira_username": outcome.name})
            people_map[old_account] = outcome.key
            bound += 1
        else:
            people_map[old_account] = CLOUD_PREFIX + old_account
            unbound += 1
    for chunk in chunks(params, BULK):
        db.execute(update(Employee), list(chunk))
    return people_map, bound, unbound


def _remap_column(db: Session, model: Any, column: str, people_map: Mapping[str, str]) -> int:
    """Облачные id людей в колонке → новые значения. Возвращает число переписанных строк.

    Каждая строка переписывается один раз: ``CASE col WHEN старый THEN новый``
    по порциям до 500 id — новое значение всегда выводится из исходного.
    Пары, где новое значение совпадает со старым id другого сотрудника
    (цепочка X→Y, Y→Z), идут одной первой порцией: иначе следующая порция
    переписала бы уже переписанное. Без привязки новое значение — старый id
    с префиксом «cloud:», как у самого сотрудника.
    """
    table = model.__table__
    col = table.c[column]
    olds, news = set(people_map), set(people_map.values())
    linked = {old: new for old, new in people_map.items() if old in news or new in olds}
    batches: list[Sequence[tuple[str, str]]] = [list(linked.items())] if linked else []
    batches.extend(chunks([(old, new) for old, new in people_map.items() if old not in linked]))
    rows = 0
    for batch in batches:
        mapping = dict(batch)
        rows += _rowcount(db.execute(
            update(table).where(col.in_(list(mapping))).values({col: case(mapping, value=col, else_=col)})
        ))
    return rows


def _replace_account_ids(node: Any, mapping: Mapping[str, str]) -> bool:
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "account_id" and isinstance(value, str) and value in mapping:
                node[key] = mapping[value]
                changed = True
            elif isinstance(value, (dict, list)):
                changed = _replace_account_ids(value, mapping) or changed
    elif isinstance(node, list):
        for item in node:
            changed = _replace_account_ids(item, mapping) or changed
    return changed


def _rewrite_people_refs(db: Session, people_map: Mapping[str, str]) -> tuple[dict[str, int], int]:
    """Облачные id людей → новые во всех местах, где они хранятся.

    Возвращает (счётчики по местам, снимков KPI с нечитаемым содержимым —
    пропущены, применение из-за них не останавливается).
    """
    counts = {
        "issues_assignee": _remap_column(db, Issue, "assignee_account_id", people_map),
        "issues_reporter": _remap_column(db, Issue, "reporter_account_id", people_map),
        "issues_developer": _remap_column(db, Issue, "developer_account_id", people_map),
        "backlog_assignee_at_choice": _remap_column(
            db, BacklogItem, "assignee_jira_account_at_choice", people_map,
        ),
    }
    users = 0
    for user in db.query(User).all():
        team_desk = user.team_desk_filter
        developers = team_desk.get("developers") if isinstance(team_desk, dict) else None
        if isinstance(developers, list) and any(d in people_map for d in developers):
            team_desk["developers"] = [people_map.get(d, d) for d in developers]
            user.team_desk_filter = team_desk
            users += 1
    counts["users_team_desk_filter"] = users
    approvals = skipped = 0
    for approval in db.query(KpiApproval).all():
        try:
            payload = json.loads(approval.payload_json)
        except (TypeError, ValueError):
            logger.warning(
                "Снимок KPI %s (%s, %s кв. %s) не читается — id людей в нём не переписаны",
                approval.id, approval.team, approval.year, approval.quarter,
            )
            skipped += 1
            continue
        if _replace_account_ids(payload, people_map):
            approval.payload_json = json.dumps(payload, ensure_ascii=False)
            approvals += 1
    counts["kpi_approvals"] = approvals
    db.flush()
    return counts, skipped


def _rebind_scope(db: Session, maps: Mapping[str, Any]) -> None:
    """id проектов и корней категорий в scope — по ключу; без пары в новой Jira — пусто."""
    projects = maps.get("projects", {})
    issues = maps.get("issues", {})
    for scope_project in db.query(ScopeProject).all():
        scope_project.jira_project_id = projects.get(scope_project.jira_project_key)
    for root in db.query(ScopeRoot).all():
        root.jira_issue_id = issues.get(root.jira_issue_key)
    db.flush()
