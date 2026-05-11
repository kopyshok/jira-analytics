"""ExecutiveDashboardService — кросс-work-type агрегатор для дашборда руководителя.

Вычисляет:
- KPI: health_index, resource_utilization, critical_risks_count, scenario_plan_fact_pct
- Health trend: 8 недель health_index по неделям
- Modules: per-team health/risk/load
- Queue: issues × issue_type × priority (status NOT done)
- Hours by type trend: worklog × issue_type by week, 8 weeks
- Plan vs fact by role: scenario allocations × BacklogItem.estimate_*_hours vs worklog × Employee.role
- Top risks: outliers с reason/key/explanation
- Capacity by role: средняя загрузка ролей за квартал

LLM не вызывает — это чистая агрегация. Synthesis в отдельном этапе.
"""
import hashlib
import json
import logging
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_allocation import ScenarioAllocation
from app.models.worklog import Worklog
from app.services.allocation_estimates import effective_estimate_hours
from app.services.work_type_outlier_detector import detect_outliers_for_theme

logger = logging.getLogger("jira_analytics.executive")


@dataclass
class ExecutiveFindings:
    """Plain dict-ready aggregates (no LLM synthesis yet)."""

    period: dict
    kpi: dict
    health_trend: list[dict]
    modules: list[dict]
    queue: list[dict]
    hours_by_type_trend: list[dict]
    plan_fact_by_role: list[dict]
    top_risks: list[dict]
    capacity_by_role: list[dict]


def team_set_hash(teams: list[str]) -> str:
    if not teams:
        return "all"
    return hashlib.md5("|".join(sorted(teams)).encode("utf-8")).hexdigest()[:32]


def _quarter_dates(year: int, quarter: int) -> tuple[date, date]:
    q_start = (quarter - 1) * 3 + 1
    end_m = q_start + 2
    return date(year, q_start, 1), date(year, end_m, monthrange(year, end_m)[1])


class ExecutiveDashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def aggregate(self, *, year: int, quarter: int, teams: list[str]) -> ExecutiveFindings:
        start_d, end_d = _quarter_dates(year, quarter)
        end_dt = datetime.combine(end_d, time.max)
        start_dt = datetime.combine(start_d, time.min)

        issues = self._select_issues(start_dt, end_dt, teams)
        issue_ids = [i.id for i in issues]
        worklog_rows = self._select_worklogs(issue_ids, start_dt, end_dt)

        # Считаем тяжёлые отчёты ровно один раз и переиспользуем в _kpi.
        plan_fact = self._plan_fact_by_role(year, quarter, teams)
        cap = self._capacity_by_role(year, quarter, teams)

        kpi = self._kpi(issues, end_dt, plan_fact=plan_fact, capacity=cap)
        health_trend = self._health_trend_8w(end_d, teams)
        modules = self._modules(issues, worklog_rows)
        queue = self._queue(issues)
        hours_trend = self._hours_by_type_trend(end_dt, teams)
        risks = self._top_risks(issues, worklog_rows)

        return ExecutiveFindings(
            period={
                "year": year, "quarter": quarter,
                "start": start_d.isoformat(), "end": end_d.isoformat(),
            },
            kpi=kpi,
            health_trend=health_trend,
            modules=modules,
            queue=queue,
            hours_by_type_trend=hours_trend,
            plan_fact_by_role=plan_fact,
            top_risks=risks,
            capacity_by_role=cap,
        )

    # --- selectors ---

    def _apply_team_filter(self, q, teams: list[str]):
        """OR-логика фильтра команд: Issue.team / participating_teams /
        Worklog.employee_id ∈ EmployeeTeam(team).

        Должна вызываться на запросе, который уже джойнит Worklog —
        иначе ветка по employee_id отвалится.
        """
        if not teams:
            return q
        issue_clauses = [Issue.team.in_(teams)]
        for t in teams:
            t_json = json.dumps(t, ensure_ascii=False)
            escaped = (
                t_json.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            issue_clauses.append(
                Issue.participating_teams.like(f"%{escaped}%", escape="\\"),
            )
        emp_subq = (
            select(EmployeeTeam.employee_id)
            .where(EmployeeTeam.team.in_(teams))
            .scalar_subquery()
        )
        return q.where(or_(or_(*issue_clauses), Worklog.employee_id.in_(emp_subq)))

    def _select_issues(
        self, start_dt: datetime, end_dt: datetime, teams: list[str],
    ) -> list[Issue]:
        q = (
            select(Issue).distinct()
            .join(Worklog, Worklog.issue_id == Issue.id)
            .where(Worklog.started_at >= start_dt, Worklog.started_at <= end_dt)
        )
        q = self._apply_team_filter(q, teams)
        return list(self.db.execute(q).scalars().all())

    def _select_worklogs(
        self, issue_ids: list[str], start_dt: datetime, end_dt: datetime,
    ) -> list:
        if not issue_ids:
            return []
        q = (
            select(
                Worklog.issue_id, Worklog.employee_id, Worklog.hours, Worklog.started_at,
                Employee.display_name, Employee.team, Employee.role,
            )
            .join(Employee, Employee.id == Worklog.employee_id)
            .where(
                Worklog.issue_id.in_(issue_ids),
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
            )
        )
        return list(self.db.execute(q).all())

    # --- aggregators ---

    def _kpi(
        self, issues, end_dt: datetime, *,
        plan_fact: list[dict], capacity: list[dict],
    ) -> dict:
        critical_open = sum(
            1 for i in issues
            if (i.priority or "").lower() in ("critical", "highest", "blocker")
            and (i.status or "").lower() != "done"
        )
        total = len(issues) or 1
        critical_share = critical_open / total

        # Часы возраста считаем относительно конца квартала, а не "сейчас":
        # для исторических квартальных снапшотов utcnow() даёт
        # завышенный возраст (например, Q1 строится в Q3 — все
        # задачи будут "старше 30 дней" → age_score обрушен).
        ref_dt = end_dt
        ages_days = []
        for i in issues:
            if (i.status or "").lower() != "done" and i.created_at:
                ages_days.append((ref_dt - i.created_at).days)
        avg_age = sum(ages_days) / len(ages_days) if ages_days else 0
        age_score = max(0.0, 1.0 - avg_age / 30.0)

        plan_pct = self._scenario_pct_from(plan_fact)
        cap_overload = self._capacity_overload_from(capacity)

        health = (
            35 * (1 - critical_share)
            + 25 * age_score
            + 20 * (plan_pct / 100.0)
            + 20 * (1 - cap_overload)
        )
        health = max(0, min(100, round(health)))

        utilization = self._utilization_pct_from(capacity)

        return {
            "health_index": health,
            "resource_utilization_pct": round(utilization, 1),
            "critical_risks_count": critical_open,
            "scenario_plan_fact_pct": round(plan_pct, 1),
        }

    def _health_trend_8w(self, end_d: date, teams: list[str]) -> list[dict]:
        """Последние 8 недель: упрощённый health (без plan_pct).

        Точка пишется на конец недели.
        """
        out: list[dict] = []
        for w in range(8):
            week_end = end_d - timedelta(weeks=w)
            week_start = week_end - timedelta(days=6)
            start_dt = datetime.combine(week_start, time.min)
            end_dt = datetime.combine(week_end, time.max)
            q = (
                select(Issue).distinct()
                .join(Worklog, Worklog.issue_id == Issue.id)
                .where(Worklog.started_at >= start_dt, Worklog.started_at <= end_dt)
            )
            q = self._apply_team_filter(q, teams)
            iss = list(self.db.execute(q).scalars().all())
            total = len(iss) or 1
            crit = sum(
                1 for i in iss
                if (i.priority or "").lower() in ("critical", "highest", "blocker")
                and (i.status or "").lower() != "done"
            )
            score = round(100 * (1 - crit / total))
            out.append({"w": f"W{8 - w}", "value": score})
        out.reverse()
        return out

    def _modules(self, issues, worklog_rows) -> list[dict]:
        """Команды как «направления». Health: ratio of crit issues. Load: relative."""
        by_team: dict[str, dict] = defaultdict(lambda: {"issues": 0, "crit": 0, "hours": 0.0})
        for i in issues:
            t = i.team or "—"
            by_team[t]["issues"] += 1
            if (
                (i.priority or "").lower() in ("critical", "highest", "blocker")
                and (i.status or "").lower() != "done"
            ):
                by_team[t]["crit"] += 1
        for row in worklog_rows:
            t = row.team or "—"
            by_team[t]["hours"] += float(row.hours or 0)

        out: list[dict] = []
        for team, agg in by_team.items():
            ratio = agg["crit"] / max(agg["issues"], 1)
            if ratio >= 0.05:
                health, risk = "red", "Высокий"
            elif ratio >= 0.02:
                health, risk = "yellow", "Средний"
            else:
                health, risk = "green", "Низкий"
            load = min(100, round(agg["hours"] / max(agg["issues"], 1) * 5))
            note = (
                f"{agg['issues']} задач, {agg['crit']} критичных"
                if agg["crit"] else f"{agg['issues']} задач"
            )
            out.append({
                "name": team, "health": health, "risk": risk,
                "load": f"{load}%", "note": note,
            })
        out.sort(key=lambda m: -int(m["load"].rstrip("%")))
        return out[:8]

    def _queue(self, issues) -> list[dict]:
        """issue_type × priority bucket для open задач."""
        bucket_map = {
            "Инциденты": ("Bug", "Incident"),
            "Доработки": ("Story", "Improvement", "Task"),
            "Консультации": ("Question", "Consultation"),
            "Регламент": ("Sub-task", "Regulatory"),
        }
        out: list[dict] = []
        for label, type_keys in bucket_map.items():
            type_keys_lower = [k.lower() for k in type_keys]
            entry = {"name": label, "critical": 0, "high": 0, "normal": 0}
            for i in issues:
                if (i.status or "").lower() == "done":
                    continue
                if (i.issue_type or "").lower() not in type_keys_lower:
                    continue
                p = (i.priority or "").lower()
                if p in ("critical", "highest", "blocker"):
                    entry["critical"] += 1
                elif p in ("high", "major"):
                    entry["high"] += 1
                else:
                    entry["normal"] += 1
            out.append(entry)
        return out

    def _hours_by_type_trend(self, end_dt: datetime, teams: list[str]) -> list[dict]:
        """8 недель × часы по типам issue."""
        weeks: list[tuple[date, date]] = []
        cur = end_dt.date()
        for _ in range(8):
            ws = cur - timedelta(days=6)
            weeks.append((ws, cur))
            cur = ws - timedelta(days=1)
        weeks.reverse()

        out: list[dict] = []
        for ws, we in weeks:
            sdt = datetime.combine(ws, time.min)
            edt = datetime.combine(we, time.max)
            q = (
                select(Issue.issue_type, func.sum(Worklog.hours))
                .join(Worklog, Worklog.issue_id == Issue.id)
                .where(Worklog.started_at >= sdt, Worklog.started_at <= edt)
                .group_by(Issue.issue_type)
            )
            if teams:
                q = q.where(Issue.team.in_(teams))
            row = {
                "w": ws.strftime("%d.%m"),
                "incidents": 0.0, "improvements": 0.0,
                "consultations": 0.0, "regulatory": 0.0,
            }
            for itype, hrs in self.db.execute(q).all():
                t = (itype or "").lower()
                hrs_f = float(hrs or 0)
                if t in ("bug", "incident"):
                    row["incidents"] += hrs_f
                elif t in ("story", "improvement", "task"):
                    row["improvements"] += hrs_f
                elif t in ("question", "consultation"):
                    row["consultations"] += hrs_f
                else:
                    row["regulatory"] += hrs_f
            for k in ("incidents", "improvements", "consultations", "regulatory"):
                row[k] = round(row[k], 1)
            out.append(row)
        return out

    def _plan_fact_by_role(self, year: int, quarter: int, teams: list[str]) -> list[dict]:
        """Сценарий план vs worklog факт по 4 ролям.

        План: BacklogItem.estimate_*_hours по аллокациям сценария (included_flag=True).
        Сценарий ищется по году + quarter='Q{N}' (PlanningScenario.quarter — строка),
        приоритет approved → draft, последний по updated_at.
        """
        q_label = f"Q{quarter}"
        scen = self.db.execute(
            select(PlanningScenario)
            .where(
                PlanningScenario.year == year,
                PlanningScenario.quarter == q_label,
                PlanningScenario.status.in_(("approved", "draft")),
            )
            .order_by(
                PlanningScenario.status.desc(),
                PlanningScenario.updated_at.desc(),
            )
        ).scalars().first()

        plan: dict[str, float] = defaultdict(float)
        scenario_issue_ids: list[str] = []
        if scen:
            rows = self.db.execute(
                select(ScenarioAllocation, BacklogItem)
                .join(BacklogItem, BacklogItem.id == ScenarioAllocation.backlog_item_id)
                .where(
                    ScenarioAllocation.scenario_id == scen.id,
                    ScenarioAllocation.included_flag.is_(True),
                )
            ).all()
            for alloc, bi in rows:
                coef = (
                    float(alloc.involvement_coefficient)
                    if alloc.involvement_coefficient is not None else 1.0
                )
                eff = effective_estimate_hours(alloc)
                plan["analyst"] += eff["analyst"] * coef
                plan["dev"] += eff["dev"] * coef
                plan["qa"] += eff["qa"] * coef
                plan["ope"] += eff["opo"] * coef
                if bi.issue_id:
                    scenario_issue_ids.append(bi.issue_id)

        # Факт — worklog × employee.role ТОЛЬКО по задачам сценария.
        # Сравнение plan vs fact должно идти по одному и тому же набору задач,
        # иначе fact раздувается на весь квартал и pct ≈ 100%.
        q_start = (quarter - 1) * 3 + 1
        em = q_start + 2
        sdt = datetime.combine(date(year, q_start, 1), time.min)
        edt = datetime.combine(date(year, em, monthrange(year, em)[1]), time.max)

        fact: dict[str, float] = defaultdict(float)
        if scenario_issue_ids:
            q = (
                select(Employee.role, func.sum(Worklog.hours))
                .join(Worklog, Worklog.employee_id == Employee.id)
                .where(
                    Worklog.started_at >= sdt,
                    Worklog.started_at <= edt,
                    Worklog.issue_id.in_(scenario_issue_ids),
                )
                .group_by(Employee.role)
            )
            for role, hrs in self.db.execute(q).all():
                r = (role or "").lower()
                if r == "analyst":
                    fact["analyst"] += float(hrs or 0)
                elif r == "consultant":
                    fact["consultant"] += float(hrs or 0)
                elif r in ("dev", "developer"):
                    fact["dev"] += float(hrs or 0)
                elif r == "qa":
                    fact["qa"] += float(hrs or 0)
                elif r == "lead":
                    fact["lead"] += float(hrs or 0)
                # Прочие роли в fact не попадают: ope — это фаза, не роль.

        # 6 строк: 5 реальных ролей + ОПЭ как фаза (только на стороне плана).
        # На фактической стороне ОПЭ всегда 0 — часы по фазе ОПЭ
        # уже распределены по ролям (analyst/dev), у самой "ОПЭ" роли нет.
        return [
            {"role": "Аналитики", "plan": round(plan["analyst"], 1), "fact": round(fact["analyst"], 1)},
            {"role": "Консультанты", "plan": 0.0, "fact": round(fact["consultant"], 1)},
            {"role": "Разработка", "plan": round(plan["dev"], 1), "fact": round(fact["dev"], 1)},
            {"role": "QA", "plan": round(plan["qa"], 1), "fact": round(fact["qa"], 1)},
            {"role": "Архитектор/тимлид", "plan": 0.0, "fact": round(fact["lead"], 1)},
            {"role": "ОПЭ (фаза)", "plan": round(plan["ope"], 1), "fact": 0.0},
        ]

    def _top_risks(self, issues, worklog_rows) -> list[dict]:
        """Outliers + критичные open задачи. До 5."""
        per_issue: dict[str, dict] = {}
        for i in issues:
            per_issue[i.id] = {
                "issue_id": i.id, "key": i.key, "summary": i.summary,
                "hours": 0.0, "worklog_count": 0,
                "is_done": (i.status or "").lower() == "done",
                "first_log": None, "last_log": None,
                "distinct_workers": set(),
            }
        for row in worklog_rows:
            entry = per_issue.get(row.issue_id)
            if not entry:
                continue
            entry["hours"] += float(row.hours or 0)
            entry["worklog_count"] += 1
            entry["distinct_workers"].add(row.employee_id)
            if entry["first_log"] is None or row.started_at < entry["first_log"]:
                entry["first_log"] = row.started_at
            if entry["last_log"] is None or row.started_at > entry["last_log"]:
                entry["last_log"] = row.started_at

        for e in per_issue.values():
            if e["first_log"] and e["last_log"]:
                e["days_in_progress"] = (e["last_log"] - e["first_log"]).days + 1
            else:
                e["days_in_progress"] = 0
            e["distinct_workers"] = len(e["distinct_workers"])

        theme_issues = [
            {**e, "reopen_count": 0} for e in per_issue.values() if e["hours"] > 0
        ]
        outliers = detect_outliers_for_theme({}, theme_issues=theme_issues)

        risks: list[dict] = []
        red_reasons = {"high_hours", "stale"}
        for o in outliers[:5]:
            risks.append({
                "title": f"{o.issue_key}: {o.reason}",
                "impact": o.context or "Аномалия в треке задачи",
                "owner": "Руководитель сопровождения",
                "action": "Разобрать в ближайшем sync, назначить ответственного",
                "level": "red" if o.reason in red_reasons else "yellow",
                "key": o.issue_key,
            })
        if len(risks) < 3:
            for i in issues:
                if (
                    (i.priority or "").lower() in ("critical", "blocker")
                    and (i.status or "").lower() != "done"
                ):
                    risks.append({
                        "title": f"{i.key}: критичная задача без закрытия",
                        "impact": "Блокирует продолжение работ",
                        "owner": "Руководитель сопровождения",
                        "action": "Эскалировать и назначить дедлайн",
                        "level": "red",
                        "key": i.key,
                    })
                    if len(risks) >= 5:
                        break
        return risks[:5]

    def _capacity_by_role(self, year: int, quarter: int, teams: list[str]) -> list[dict]:
        """Средняя загрузка по 5 ролям за квартал.

        ОПЭ — фаза, не роль, поэтому в этом отчёте не появляется.
        Упрощение MVP: считаем из worklog.hours / 520 (квартал ~520 раб.часов на FTE).
        """
        roles = ["analyst", "consultant", "dev", "qa", "lead"]
        labels = {
            "analyst": "Аналитики", "consultant": "Консультанты",
            "dev": "Разработка", "qa": "QA", "lead": "Архитектор/тимлид",
        }
        out: list[dict] = []
        q_start = (quarter - 1) * 3 + 1
        em = q_start + 2
        sdt = datetime.combine(date(year, q_start, 1), time.min)
        edt = datetime.combine(date(year, em, monthrange(year, em)[1]), time.max)
        for role in roles:
            role_filter = (
                func.lower(Employee.role).in_(("dev", "developer"))
                if role == "dev"
                else func.lower(Employee.role) == role
            )
            q = (
                select(Employee.id, func.sum(Worklog.hours))
                .join(Worklog, Worklog.employee_id == Employee.id)
                .where(
                    Worklog.started_at >= sdt,
                    Worklog.started_at <= edt,
                    role_filter,
                )
                .group_by(Employee.id)
            )
            if teams:
                emp_subq = (
                    select(EmployeeTeam.employee_id)
                    .where(EmployeeTeam.team.in_(teams))
                    .scalar_subquery()
                )
                q = q.where(Employee.id.in_(emp_subq))
            rows = list(self.db.execute(q).all())
            if not rows:
                out.append({"role": labels[role], "utilization_pct": 0})
                continue
            avg_hours = sum(float(h or 0) for _, h in rows) / len(rows)
            pct = min(100, round(avg_hours / 520 * 100))
            out.append({"role": labels[role], "utilization_pct": pct})
        return out

    # --- helpers (operate on precomputed plan_fact/capacity to avoid recomputation) ---

    def _scenario_pct_from(self, plan_fact: list[dict]) -> float:
        plan_total = sum(r["plan"] for r in plan_fact)
        fact_total = sum(r["fact"] for r in plan_fact)
        if plan_total == 0:
            return 0.0
        return min(100.0, fact_total / plan_total * 100)

    def _capacity_overload_from(self, capacity: list[dict]) -> float:
        over = [c for c in capacity if c["utilization_pct"] > 100]
        return min(1.0, len(over) / max(len(capacity), 1))

    def _utilization_pct_from(self, capacity: list[dict]) -> float:
        if not capacity:
            return 0.0
        return sum(c["utilization_pct"] for c in capacity) / len(capacity)
