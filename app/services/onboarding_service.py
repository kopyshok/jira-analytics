"""«Первые шаги»: состояние шагов настройки команды и личное состояние пользователя.

Авто-шаги проверяются по данным команды. Как только условие выполнилось,
пишется отметка ``source=auto`` и шаг больше не пересчитывается (защёлка):
пройденная настройка не должна краснеть от новых задач. Ручные шаги сервис
проверить не может («отпусков нет» неотличимо от «не внесли») — их отмечает
пользователь.
"""
from datetime import date, datetime
from typing import Callable, Optional

from sqlalchemy import and_, or_
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

CATEGORIZATION_MAX_STACK_SHARE = 0.10

MANUAL_STEPS = ("absences", "scenario_rules", "scenario_involvement")


def _tree_counts(db: Session, team: str) -> dict:
    keys = ",".join(k for (k,) in db.query(ScopeProject.jira_project_key).all())
    return get_tree_counts(project_keys=keys or None, teams=team, db=db).model_dump()


def _issues_loaded(db: Session, team: str) -> bool:
    return sum(_tree_counts(db, team).values()) > 0


def _categorization(db: Session, team: str) -> bool:
    counts = _tree_counts(db, team)
    total = sum(counts.values())
    return total > 0 and counts["stack"] / total <= CATEGORIZATION_MAX_STACK_SHARE


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
    estimates = (
        BacklogItem.estimate_hours,
        BacklogItem.estimate_analyst_hours,
        BacklogItem.estimate_dev_hours,
        BacklogItem.estimate_qa_hours,
        BacklogItem.estimate_opo_hours,
    )
    row = (
        db.query(BacklogItem.id)
        .outerjoin(Issue, BacklogItem.issue_id == Issue.id)
        .filter(
            BacklogItem.archived_at.is_(None),
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


def _latch(db: Session, team: str, step: str) -> Optional[TeamOnboardingMark]:
    """Записать авто-отметку. Параллельный запрос мог успеть раньше — тогда берём его строку."""
    mark = TeamOnboardingMark(team=team, step=step, state="done", source="auto")
    db.add(mark)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return (
            db.query(TeamOnboardingMark)
            .filter(TeamOnboardingMark.team == team, TeamOnboardingMark.step == step)
            .first()
        )
    return mark


def team_steps(db: Session, team: str) -> dict[str, dict]:
    """Состояние всех шагов команды: done | skipped | pending."""
    marks = {
        m.step: m
        for m in db.query(TeamOnboardingMark).filter(TeamOnboardingMark.team == team).all()
    }
    for step, check in AUTO_STEPS.items():
        if step not in marks and check(db, team):
            latched = _latch(db, team, step)
            if latched is not None:
                marks[step] = latched

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
    """Ручная отметка / пропуск / возврат (``pending`` удаляет отметку)."""
    db.query(TeamOnboardingMark).filter(
        TeamOnboardingMark.team == team, TeamOnboardingMark.step == step
    ).delete()
    if state != "pending":
        db.add(TeamOnboardingMark(
            team=team, step=step, state=state, source="manual",
            marked_by_user_id=user_id, marked_at=datetime.utcnow(),
        ))
    db.commit()


def me_state(user: User) -> dict:
    stored = user.onboarding
    return {
        "completed_tours": list(stored.get("completed_tours", [])),
        "auto_opened": bool(stored.get("auto_opened", False)),
        "hidden": bool(stored.get("hidden", False)),
    }
