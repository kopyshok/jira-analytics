"""«Первые шаги»: состояние шагов настройки команды и личное состояние пользователя.

Авто-шаги проверяются по данным команды. Как только условие выполнилось,
пишется отметка ``source=auto`` и шаг больше не пересчитывается (защёлка):
пройденная настройка не должна краснеть от новых задач. Ручные шаги сервис
проверить не может («отпусков нет» неотличимо от «не внесли») — их отмечает
пользователь.
"""
from datetime import date, datetime
from typing import Callable

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.endpoints.issue_config import get_tree_counts
from app.models import (
    BacklogItem,
    Employee,
    Issue,
    PlanningScenario,
    ResourcePlan,
    ScopeProject,
    TeamOnboardingMark,
    User,
)
from app.services import team_membership
from app.services.backlog_service import CANCEL_STATUSES, QUARTERLY_TASKS_CATEGORY

CATEGORIZATION_MAX_STACK_SHARE = 0.10

MANUAL_STEPS = ("absences", "scenario_rules", "scenario_involvement")


def _tree_counts(db: Session, team: str) -> dict:
    keys = ",".join(k for (k,) in db.query(ScopeProject.jira_project_key).all())
    return get_tree_counts(project_keys=keys or None, teams=team, db=db).model_dump()


def _counts_issues_loaded(counts: dict) -> bool:
    return sum(counts.values()) > 0


def _counts_categorization(counts: dict) -> bool:
    total = sum(counts.values())
    return total > 0 and counts["stack"] / total <= CATEGORIZATION_MAX_STACK_SHARE


def _issues_loaded(db: Session, team: str) -> bool:
    return _counts_issues_loaded(_tree_counts(db, team))


def _categorization(db: Session, team: str) -> bool:
    return _counts_categorization(_tree_counts(db, team))


def _team_roles(db: Session, team: str) -> bool:
    member_ids = team_membership.members_on(db, [team], date.today())
    if not member_ids:
        return False
    roles = (
        db.query(Employee.role)
        .filter(Employee.id.in_(member_ids), Employee.is_active.is_(True))
        .all()
    )
    return bool(roles) and all(r for (r,) in roles)


def _backlog(db: Session, team: str) -> bool:
    """Есть ли в бэклоге команды хоть одна не архивная инициатива с оценкой.

    «Не архивная» — как во вкладке «Архив» бэклога (app/api/endpoints/backlog.py):
    не отправлена в архив вручную, не отменена/отклонена в Jira, не выполнена
    (квартальные задачи в архив по статусу done не уходят).
    """
    estimates = (
        BacklogItem.estimate_hours,
        BacklogItem.estimate_analyst_hours,
        BacklogItem.estimate_dev_hours,
        BacklogItem.estimate_qa_hours,
        BacklogItem.estimate_opo_hours,
    )
    jira_archived = and_(
        BacklogItem.issue_id.isnot(None),
        or_(
            Issue.status.in_(list(CANCEL_STATUSES)),
            and_(
                func.coalesce(Issue.status_category, "") == "done",
                func.coalesce(Issue.category, "") != QUARTERLY_TASKS_CATEGORY,
                func.coalesce(Issue.assigned_category, "") != QUARTERLY_TASKS_CATEGORY,
            ),
        ),
    )
    row = (
        db.query(BacklogItem.id)
        .outerjoin(Issue, BacklogItem.issue_id == Issue.id)
        .filter(
            BacklogItem.archived_at.is_(None),
            ~jira_archived,
            or_(
                Issue.team == team,
                and_(BacklogItem.issue_id.is_(None), BacklogItem.team == team),
            ),
            or_(*[col > 0 for col in estimates]),
        )
        .first()
    )
    return row is not None


def _scenario_created(db: Session, team: str) -> bool:
    return db.query(PlanningScenario.id).filter(PlanningScenario.team == team).first() is not None


def _resource_plan(db: Session, team: str) -> bool:
    row = (
        db.query(ResourcePlan.id)
        .filter(ResourcePlan.team == team, ResourcePlan.computed_at.isnot(None))
        .first()
    )
    return row is not None


AUTO_STEPS: dict[str, Callable[[Session, str], bool]] = {
    "issues_loaded": _issues_loaded,
    "categorization": _categorization,
    "team_roles": _team_roles,
    "backlog": _backlog,
    "scenario_created": _scenario_created,
    "resource_plan": _resource_plan,
}

ALL_STEPS = (
    "issues_loaded", "categorization", "team_roles", "absences", "backlog",
    "scenario_created", "scenario_rules", "scenario_involvement", "resource_plan",
)

assert set(ALL_STEPS) == set(AUTO_STEPS) | set(MANUAL_STEPS), "ALL_STEPS разошёлся со списком авто/ручных шагов"


def _latch(db: Session, team: str, step: str) -> None:
    """Записать авто-отметку. Параллельный запрос мог успеть раньше — тогда просто
    откатываемся: марки для ответа читаются заново после всех защёлок и уже
    подхватят чужую строку.
    """
    db.add(TeamOnboardingMark(team=team, step=step, state="done", source="auto"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def team_steps(db: Session, team: str) -> dict[str, dict]:
    """Состояние всех шагов команды: done | skipped | pending."""
    closed_steps = {
        step for (step,) in db.query(TeamOnboardingMark.step).filter(TeamOnboardingMark.team == team).all()
    }

    # issues_loaded и categorization оба читают дерево категорий — считаем один раз.
    counts_cache: dict[str, dict] = {}

    def counts() -> dict:
        if "value" not in counts_cache:
            counts_cache["value"] = _tree_counts(db, team)
        return counts_cache["value"]

    for step, check in AUTO_STEPS.items():
        if step in closed_steps:
            continue
        if step == "issues_loaded":
            ok = _counts_issues_loaded(counts())
        elif step == "categorization":
            ok = _counts_categorization(counts())
        else:
            ok = check(db, team)
        if ok:
            _latch(db, team, step)

    # Марки грузим один раз и только сейчас, после всех защёлок: объекты,
    # загруженные до commit/rollback в _latch (expire_on_commit), протухают —
    # обращение к ним упало бы с ObjectDeletedError, если параллельный запрос
    # успел удалить/заменить строку.
    marks = {
        m.step: m
        for m in db.query(TeamOnboardingMark).filter(TeamOnboardingMark.team == team).all()
    }

    user_ids = {m.marked_by_user_id for m in marks.values() if m.marked_by_user_id}
    names: dict[str, str] = (
        {uid: name for uid, name in db.query(User.id, User.display_name).filter(User.id.in_(user_ids)).all()}
        if user_ids else {}
    )
    result: dict[str, dict] = {}
    for step in ALL_STEPS:
        m = marks.get(step)
        result[step] = {
            "state": m.state if m else "pending",
            "source": m.source if m else None,
            "marked_by": names.get(m.marked_by_user_id or "") if m else None,
            "marked_at": m.marked_at.isoformat() if m else None,
        }
    return result


def set_team_step(db: Session, team: str, step: str, state: str, user_id: str) -> None:
    """Ручная отметка / пропуск / возврат (``pending`` удаляет отметку).

    На PostgreSQL два параллельных запроса на одну (команда, шаг) могут оба
    не найти строку на удаление и попытаться вставить новую — второй commit
    упадёт на уникальном индексе (то же самое при гонке с авто-защёлкой).
    Один повтор устраняет реальную гонку.
    """
    for attempt in range(2):
        db.query(TeamOnboardingMark).filter(
            TeamOnboardingMark.team == team, TeamOnboardingMark.step == step
        ).delete()
        if state != "pending":
            db.add(TeamOnboardingMark(
                team=team, step=step, state=state, source="manual",
                marked_by_user_id=user_id, marked_at=datetime.utcnow(),
            ))
        try:
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise


def me_state(user: User) -> dict:
    stored = user.onboarding
    return {
        "completed_tours": list(stored.get("completed_tours", [])),
        "auto_opened": bool(stored.get("auto_opened", False)),
        "hidden": bool(stored.get("hidden", False)),
    }
