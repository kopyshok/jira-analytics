"""Проектный срез плана: план/факт по видам работ, задачи, таймлайн.

Отличие от рабочих столов: там персональная доля одного сотрудника, здесь —
проект целиком, со всеми исполнителями. Формулы общие, живут в plan_common.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.plan_common import (
    DISPLAY_ROLES,
    PHASE_LABEL,
    jira_url,
    plan_ids_for_issues,
    quarter_bounds,
    role_breakdown,
    subtree_ids,
    team_member_ids,
)

if TYPE_CHECKING:
    from app.models.issue import Issue


class ProjectPlanService:
    """Агрегаты вкладки «План и сроки» и сводного экрана портфеля."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Один проект
    # ------------------------------------------------------------------

    def get_plan(self, key: str, *, year: int, quarter: int) -> Optional[dict]:
        """Контракт вкладки «План и сроки». None — задача с таким ключом не найдена."""
        from app.models import Issue

        root = self._db.execute(select(Issue).where(Issue.key == key)).scalars().first()
        if root is None:
            return None

        q_start, q_end = quarter_bounds(year, quarter)
        subtree = subtree_ids(self._db, [root.id])
        plan_ids = plan_ids_for_issues(self._db, [root.id])
        team_ids = self._team_ids_for_project(self._project_teams(root, plan_ids))
        bd = role_breakdown(
            self._db, plan_ids, [root.id], subtree, q_end, team_ids
        )[root.id]

        work_types, total_plan, total_fact = _project_work_types(bd)
        return {
            "key": root.key,
            "work_types": work_types,
            "external_hours": round(bd["info"], 1),
            "total_plan": total_plan,
            "total_fact": total_fact,
            "total_pct": _pct(total_fact, total_plan),
            "timeline": self._timeline(plan_ids, [root.id], q_start, q_end),
            "children": self._children(root.id, q_end),
        }

    # ------------------------------------------------------------------
    # Портфель
    # ------------------------------------------------------------------

    SILENT_DAYS = 14
    LAGGING_GAP_PP = 15

    def get_portfolio(self, keys: Sequence[str], *, year: int, quarter: int) -> dict:
        """Сводка по набору проектов — тому же, что видно в списке слева."""
        from app.models import Issue

        empty = {
            "project_count": 0,
            "work_types": [
                {"code": r, "label": PHASE_LABEL[r], "plan_hours": 0.0,
                 "fact_hours": 0.0, "pct": None}
                for r in DISPLAY_ROLES
            ],
            "external_hours": 0.0,
            "total_plan": None,
            "total_fact": 0.0,
            "total_pct": None,
            "timeline": {"start": None, "end": None, "rows": [],
                         "quarter_start": quarter_bounds(year, quarter)[0].isoformat(),
                         "quarter_end": quarter_bounds(year, quarter)[1].isoformat()},
            "signals": [],
        }
        wanted = [k for k in keys if k]
        if not wanted:
            return empty

        roots = (
            self._db.execute(select(Issue).where(Issue.key.in_(wanted))).scalars().all()
        )
        if not roots:
            return empty

        q_start, q_end = quarter_bounds(year, quarter)
        root_ids = [r.id for r in roots]
        subtree = subtree_ids(self._db, root_ids)
        plan_ids = plan_ids_for_issues(self._db, root_ids)

        # Состав команды считаем по каждому проекту отдельно: аналитик чужой
        # команды на одном проекте не должен портить цифры остальным (спека
        # §3.3). role_breakdown принимает словарь «корень → свой набор» и
        # считает все проекты за один проход (без цикла с отдельным запросом
        # назначений и ворклогов на каждый проект), а сам состав команды
        # каждого проекта собирается батчем в _team_ids_by_root — без цикла
        # запросов членства/QA на каждый проект.
        team_ids_by_root = self._team_ids_by_root(roots, plan_ids)
        per_project = role_breakdown(
            self._db, plan_ids, root_ids, subtree, q_end, team_ids_by_root
        )

        totals: Dict[str, Dict[str, float]] = {
            "plan": {r: 0.0 for r in DISPLAY_ROLES},
            "fact": {r: 0.0 for r in DISPLAY_ROLES},
        }
        info_hours = 0.0
        project_pcts: Dict[str, Optional[int]] = {}
        for root in roots:
            bd = per_project[root.id]
            wt, total_plan, total_fact = _project_work_types(bd)
            for w in wt:
                totals["plan"][w["code"]] += w["plan_hours"]
                totals["fact"][w["code"]] += w["fact_hours"]
            info_hours += bd["info"]
            project_pcts[root.key] = _pct(total_fact, total_plan)

        work_types: List[dict] = [
            {
                "code": r,
                "label": PHASE_LABEL[r],
                "plan_hours": round(totals["plan"][r], 1),
                "fact_hours": round(totals["fact"][r], 1),
                "pct": _pct(totals["fact"][r], totals["plan"][r] or None),
            }
            for r in DISPLAY_ROLES
        ]
        total_plan_raw = round(sum(w["plan_hours"] for w in work_types), 1)
        total_plan = total_plan_raw if total_plan_raw > 0 else None
        total_fact = round(sum(w["fact_hours"] for w in work_types), 1)
        total_pct = _pct(total_fact, total_plan)

        return {
            "project_count": len(roots),
            "work_types": work_types,
            "external_hours": round(info_hours, 1),
            "total_plan": total_plan,
            "total_fact": total_fact,
            "total_pct": total_pct,
            "timeline": self._timeline(plan_ids, root_ids, q_start, q_end),
            "signals": self._signals(roots, subtree, project_pcts, work_types, total_pct, q_end),
        }

    def _signals(
        self,
        roots: Sequence["Issue"],
        subtree: Dict[str, set],
        project_pcts: Dict[str, Optional[int]],
        work_types: List[dict],
        total_pct: Optional[int],
        fact_until: date,
    ) -> List[dict]:
        """Короткие подсказки «куда смотреть». Пустой список — полосу не рисуем."""
        from app.models import Worklog

        out: List[dict] = []

        overloaded = [k for k, p in project_pcts.items() if p is not None and p > 100]
        if overloaded:
            out.append({
                "kind": "overload",
                "text": f"{len(overloaded)} {_plural_projects(len(overloaded))} > 100% плана",
                "severity": "warn",
            })

        all_ids = {i for ids in subtree.values() for i in ids}
        last_rows = (
            self._db.query(Worklog.issue_id, func.max(Worklog.started_at).label("last"))
            .filter(Worklog.issue_id.in_(all_ids))
            .group_by(Worklog.issue_id)
            .all()
        )
        last_by_issue = {r.issue_id: r.last for r in last_rows}
        # Для текущего (незавершённого) квартала молчание меряем от сегодня,
        # а не от конца квартала — иначе почти любой активный проект выглядел
        # бы молчащим большую часть квартала. Для уже закрытого квартала
        # today > fact_until, min() берёт fact_until — поведение не меняется.
        cutoff = datetime.combine(min(date.today(), fact_until), time.max)
        silent = 0
        for root in roots:
            stamps = [last_by_issue[i] for i in subtree[root.id] if last_by_issue.get(i)]
            if not stamps:
                continue  # ещё не начинали — это не «замолчал»
            if (cutoff - max(stamps)).days > self.SILENT_DAYS:
                silent += 1
        if silent:
            out.append({
                "kind": "silent",
                "text": f"{silent} {_plural_projects(silent)} без списаний "
                        f"{self.SILENT_DAYS}+ дней",
                "severity": "warn",
            })

        if total_pct is not None:
            lagging = [
                w for w in work_types
                if w["pct"] is not None and total_pct - w["pct"] > self.LAGGING_GAP_PP
            ]
            if lagging:
                worst = min(lagging, key=lambda w: w["pct"])
                out.append({
                    "kind": "lagging",
                    "text": f"{worst['label']} отстаёт: {worst['pct']}% "
                            f"при {total_pct}% общей",
                    "severity": "info",
                })
        return out

    # ------------------------------------------------------------------
    # Внутреннее
    # ------------------------------------------------------------------

    def _project_teams(self, root, plan_ids: Sequence[str]) -> List[str]:
        """Команда проекта: поле задачи, иначе команда плана, иначе пусто."""
        if root.team:
            return [root.team]
        if plan_ids:
            from app.models import ResourcePlan

            teams = (
                self._db.execute(
                    select(ResourcePlan.team).where(ResourcePlan.id.in_(list(plan_ids)))
                )
                .scalars()
                .all()
            )
            return [t for t in dict.fromkeys(teams) if t]
        return []

    def _team_ids_for_project(self, teams: List[str]) -> set[str]:
        """Состав команды проекта для отсечения «внешних» авторов.

        Если команду определить не удалось (у эпика нет поля «Команда» и нет
        ни одного ресурсного плана с назначениями этого проекта) — считаем
        внутренними всех сотрудников. `team_member_ids` при пустом списке
        команд вернула бы только QA (общий ресурс на любую команду), а все
        остальные авторы ошибочно уехали бы во «Внешние» — раз команда
        проекта не определена, объявлять всех её авторов чужими некорректно
        (спека §3.3).
        """
        if teams:
            return team_member_ids(self._db, teams)
        from app.models import Employee

        return {r[0] for r in self._db.query(Employee.id).all()}

    def _team_ids_by_root(
        self, roots: Sequence["Issue"], plan_ids: Sequence[str]
    ) -> Dict[str, set]:
        """Состав «своей» команды для каждого проекта портфеля — без цикла запросов.

        Семантически то же самое, что вызвать
        ``_team_ids_for_project(_project_teams(root, plan_ids))`` на каждый
        root по отдельности (см. ``get_plan`` — там ровно так, но для одного
        проекта запросов и не нужно экономить). Для портфеля из N проектов
        по кругу такой цикл стоил бы до 2×N запросов (членство в командах +
        QA — оба одинаковые для любого проекта той же команды, а QA вообще
        не зависит от команды). Тут все походы в БД вынесены за пределы
        цикла по проектам:

        - ``_project_teams`` при пустом ``Issue.team`` шлёт запрос по
          ``plan_ids`` — а ``plan_ids`` общий на весь портфель, значит и
          результат одинаков для всех таких проектов; считаем один раз;
        - членство в командах — один запрос по объединению команд всех
          проектов, дальше раскладывается по командам в памяти;
        - QA (общий ресурс, к команде не привязан) — один запрос вместо N
          одинаковых, и только если он вообще нужен;
        - «команда не определена → все свои» (см. ``_team_ids_for_project``)
          — тоже один запрос на всех сотрудников, и только если он нужен
          хотя бы одному проекту.
        """
        from app.models import Employee
        from app.models.employee_team import EmployeeTeam

        # Команда каждого проекта — как в _project_teams, но фолбэк-запрос
        # по plan_ids не зависит от root, поэтому выполняется максимум раз.
        plan_teams: Optional[List[str]] = None
        root_teams: Dict[str, List[str]] = {}
        for root in roots:
            if root.team:
                root_teams[root.id] = [root.team]
                continue
            if plan_teams is None:
                plan_teams = self._project_teams(root, plan_ids)
            root_teams[root.id] = plan_teams

        all_teams = {t for teams in root_teams.values() for t in teams}
        members_by_team: Dict[str, set] = {}
        if all_teams:
            rows = (
                self._db.query(EmployeeTeam.team, EmployeeTeam.employee_id)
                .filter(EmployeeTeam.team.in_(all_teams))
                .all()
            )
            for team, emp_id in rows:
                members_by_team.setdefault(team, set()).add(emp_id)

        qa_ids: Optional[set] = None
        all_employee_ids: Optional[set] = None

        result: Dict[str, set] = {}
        for root in roots:
            teams = root_teams[root.id]
            if not teams:
                if all_employee_ids is None:
                    all_employee_ids = {r[0] for r in self._db.query(Employee.id).all()}
                result[root.id] = all_employee_ids
                continue
            if qa_ids is None:
                qa_ids = {
                    r[0] for r in self._db.query(Employee.id).filter(Employee.role == "qa").all()
                }
            ids: set = set()
            for t in teams:
                ids |= members_by_team.get(t, set())
            result[root.id] = ids | qa_ids
        return result

    def _children(self, root_id: str, fact_until: date) -> List[dict]:
        """Прямые дети проекта; часы — по поддереву каждого ребёнка."""
        from app.models import Issue, Worklog

        rows = (
            self._db.query(Issue.id, Issue.key, Issue.summary, Issue.status)
            .filter(Issue.parent_id == root_id)
            .all()
        )
        if not rows:
            return []
        child_ids = [r.id for r in rows]
        sub = subtree_ids(self._db, child_ids)
        all_ids = {i for ids in sub.values() for i in ids}
        end_dt = datetime.combine(fact_until, time.max)
        hours_rows = (
            self._db.query(
                Worklog.issue_id,
                func.coalesce(func.sum(Worklog.hours), 0.0).label("hours"),
            )
            .filter(Worklog.issue_id.in_(all_ids), Worklog.started_at <= end_dt)
            .group_by(Worklog.issue_id)
            .all()
        )
        by_issue = {r.issue_id: float(r.hours or 0.0) for r in hours_rows}
        out = [
            {
                "key": r.key,
                "title": r.summary,
                "status": r.status,
                "jira_url": jira_url(r.key),
                "hours": round(sum(by_issue.get(i, 0.0) for i in sub.get(r.id, ())), 1),
            }
            for r in rows
        ]
        out.sort(key=lambda c: (-c["hours"], c["key"] or ""))
        return out

    def _timeline(
        self,
        plan_ids: Sequence[str],
        root_ids: Sequence[str],
        q_start: date,
        q_end: date,
    ) -> dict:
        """Полосы фаз по проектам. Шкала — от первой до последней даты назначений."""
        from app.models import BacklogItem, Issue, ResourcePlanAssignment

        rows: List[tuple] = []
        if plan_ids and root_ids:
            rows = (
                self._db.query(ResourcePlanAssignment, BacklogItem.issue_id, Issue.key,
                               Issue.summary, Issue.status)
                .join(BacklogItem, BacklogItem.id == ResourcePlanAssignment.backlog_item_id)
                .join(Issue, Issue.id == BacklogItem.issue_id)
                .filter(
                    ResourcePlanAssignment.plan_id.in_(list(plan_ids)),
                    BacklogItem.issue_id.in_(list(root_ids)),
                    ResourcePlanAssignment.start_date.is_not(None),
                    ResourcePlanAssignment.end_date.is_not(None),
                )
                .order_by(ResourcePlanAssignment.start_date)
                .all()
            )

        by_issue: Dict[str, dict] = {}
        starts: List[date] = []
        ends: List[date] = []
        for a, issue_id, key, summary, status in rows:
            row = by_issue.setdefault(
                issue_id, {"key": key, "title": summary, "status": status, "bars": []}
            )
            row["bars"].append(
                {
                    "phase": a.phase,
                    "label": PHASE_LABEL.get(a.phase, a.phase or "—"),
                    "start_date": a.start_date.isoformat(),
                    "end_date": a.end_date.isoformat(),
                }
            )
            starts.append(a.start_date)
            ends.append(a.end_date)

        return {
            "start": min(starts).isoformat() if starts else None,
            "end": max(ends).isoformat() if ends else None,
            "quarter_start": q_start.isoformat(),
            "quarter_end": q_end.isoformat(),
            "rows": list(by_issue.values()),
        }


# ----------------------------------------------------------------------
# Чистые функции
# ----------------------------------------------------------------------

def _pct(fact: float, plan: Optional[float]) -> Optional[int]:
    if plan is None or plan <= 0:
        return None
    return round(fact / plan * 100)


def _project_work_types(bd: dict) -> tuple[List[dict], Optional[float], float]:
    """Из разбивки — список видов работ + итоги. total_plan=None если плана нет."""
    work_types: List[dict] = []
    for role in DISPLAY_ROLES:
        plan = round(bd["plan"].get(role, 0.0), 1)
        fact = round(bd["fact"].get(role, 0.0), 1)
        work_types.append(
            {
                "code": role,
                "label": PHASE_LABEL[role],
                "plan_hours": plan,
                "fact_hours": fact,
                "pct": _pct(fact, plan),
            }
        )
    total_plan_raw = round(sum(w["plan_hours"] for w in work_types), 1)
    total_fact = round(sum(w["fact_hours"] for w in work_types), 1)
    return work_types, (total_plan_raw if total_plan_raw > 0 else None), total_fact


def _plural_projects(n: int) -> str:
    """Склонение слова «проект» для чисел в подсказках."""
    if 11 <= n % 100 <= 14:
        return "проектов"
    return {1: "проект", 2: "проекта", 3: "проекта", 4: "проекта"}.get(n % 10, "проектов")
