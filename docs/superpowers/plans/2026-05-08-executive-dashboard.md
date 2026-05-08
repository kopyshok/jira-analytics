# Executive Dashboard сопровождения 1С

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Новый раздел `/executive` — кросс-work-type дашборд для руководителя с KPI, тренд здоровья, очередь, риски, capacity, AI-summary в 3 секции (что улучшилось / где риск / что делать).

**Architecture:**
- Бэк: `ExecutiveDashboardService` агрегирует имеющиеся источники (Issues, Worklogs, Capacity v3, Scenario, outliers) → JSON snapshot. AI-summary через отдельный метод провайдера `synthesize_executive_summary`. Кэш-ключ: `period + team_set_hash`.
- Фронт: `/executive` страница на recharts по мокапу. KPI cards, area/bar/line/horizontal-bar charts. AI-summary 3-card. Manual refresh.
- Замены блоков (по решению PM): убраны SLA и релизы. Вместо: «Загрузка ресурса %», «Выполнение плана сценария %», «Тренд часов по типам» (stacked area), «План/факт по ролям» (bar).

**Tech Stack:** SQLAlchemy 2.0 + Alembic batch, FastAPI, recharts 3.8 (уже в deps), AntD 6, framer-motion (если нужен fade-in).

---

## Files

**Create (backend):**
- `alembic/versions/1b2c3d4e5f60_executive_snapshot.py`
- `app/models/executive_snapshot.py`
- `app/services/executive_dashboard_service.py`
- `app/services/llm/executive_synthesizer.py`
- `app/api/endpoints/executive.py`
- `tests/test_executive_dashboard_service.py`
- `tests/test_executive_synthesizer.py`
- `tests/test_executive_endpoint.py`

**Modify (backend):**
- `app/services/llm/openrouter.py` — добавить `synthesize_executive_summary`
- `app/services/llm/gemini.py` — добавить `synthesize_executive_summary`
- `app/services/llm/base.py` — расширить `LLMProvider` Protocol
- `app/api/router.py` — подключить новый router

**Create (frontend):**
- `frontend/src/pages/ExecutiveDashboardPage.tsx`
- `frontend/src/components/executive/KpiCard.tsx`
- `frontend/src/components/executive/AISummary.tsx`
- `frontend/src/components/executive/ModuleHealth.tsx`
- `frontend/src/components/executive/RiskList.tsx`
- `frontend/src/api/executive.ts`

**Modify (frontend):**
- `frontend/src/AppRouter.tsx` (или эквивалент) — маршрут `/executive`
- `frontend/src/components/AppLayout.tsx` (или nav-компонент) — пункт меню

---

## Phase A: DB + Snapshot Model

### Task 1: Миграция `executive_dashboard_snapshots`

**Files:**
- Create: `alembic/versions/1b2c3d4e5f60_executive_snapshot.py`

- [ ] **Step 1: Создать миграцию**

```python
"""executive_snapshot

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-05-08 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '1b2c3d4e5f60'
down_revision: Union[str, None] = '0a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'executive_dashboard_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=False),
        sa.Column('team_set_hash', sa.String(32), nullable=False),
        sa.Column('team_set_json', sa.Text(), nullable=False),
        sa.Column('snapshot_data', sa.Text(), nullable=False),
        sa.Column('model_id', sa.String(120), nullable=True),
        sa.Column('prompt_version', sa.String(32), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('year', 'quarter', 'team_set_hash', name='uq_exec_snap_period_team'),
    )


def downgrade() -> None:
    op.drop_table('executive_dashboard_snapshots')
```

- [ ] **Step 2: Применить миграцию**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m alembic downgrade -1
py -3.10 -m alembic upgrade head
```

Expected: оба прохода чистые.

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/1b2c3d4e5f60_executive_snapshot.py
git commit -m "migration(executive): add executive_dashboard_snapshots"
```

### Task 2: Модель ExecutiveSnapshot

**Files:**
- Create: `app/models/executive_snapshot.py`

- [ ] **Step 1: Создать модель**

```python
"""ExecutiveSnapshot — кэш кросс-work-type дашборда руководителя."""
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid
from datetime import datetime


class ExecutiveSnapshot(Base):
    __tablename__ = "executive_dashboard_snapshots"
    __table_args__ = (
        UniqueConstraint("year", "quarter", "team_set_hash", name="uq_exec_snap_period_team"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    team_set_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    team_set_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_data: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<ExecutiveSnapshot {self.year}Q{self.quarter} team={self.team_set_hash[:8]}>"
```

- [ ] **Step 2: Прогнать импорт**

```bash
py -3.10 -c "from app.models.executive_snapshot import ExecutiveSnapshot; print(ExecutiveSnapshot)"
```

Expected: имя класса напечатано без ошибки.

- [ ] **Step 3: Commit**

```bash
git add app/models/executive_snapshot.py
git commit -m "model(executive): add ExecutiveSnapshot"
```

---

## Phase B: Aggregation Service

### Task 3: ExecutiveDashboardService — агрегатор всех KPI

**Files:**
- Create: `app/services/executive_dashboard_service.py`

- [ ] **Step 1: Создать сервис**

```python
"""ExecutiveDashboardService — кросс-work-type агрегатор для дашборда руководителя.

Вычисляет:
- KPI: health_index, resource_utilization, critical_risks_count, scenario_plan_fact_pct
- Health trend: 8 недель health_index по неделям
- Modules: per-team health/risk/load
- Queue: issues × issue_type × priority (status NOT done)
- Hours by type trend: worklog × issue_type by week, 8 weeks
- Plan vs fact by role: scenario allocations vs worklog × employee.role
- Top risks: outliers с reason/key/explanation
- Capacity by role: средняя загрузка ролей за квартал

LLM не вызывает — это чистая агрегация. Synthesis в отдельном этапе.
"""
import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.scenario import Scenario, ScenarioAllocation
from app.models.worklog import Worklog
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
    from calendar import monthrange
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

        issues = self._select_issues(start_d, end_d, teams)
        issue_ids = [i.id for i in issues]
        worklog_rows = self._select_worklogs(issue_ids, start_dt, end_dt)

        kpi = self._kpi(issues, worklog_rows, start_dt, end_dt, year, quarter, teams)
        health_trend = self._health_trend_8w(end_d, teams)
        modules = self._modules(issues, worklog_rows, teams)
        queue = self._queue(issues)
        hours_trend = self._hours_by_type_trend(start_dt, end_dt, teams)
        plan_fact = self._plan_fact_by_role(year, quarter, teams)
        risks = self._top_risks(issues, worklog_rows)
        cap = self._capacity_by_role(year, quarter, teams)

        return ExecutiveFindings(
            period={"year": year, "quarter": quarter, "start": start_d.isoformat(), "end": end_d.isoformat()},
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

    def _select_issues(self, start_d: date, end_d: date, teams: list[str]) -> list[Issue]:
        end_dt = datetime.combine(end_d, time.max)
        start_dt = datetime.combine(start_d, time.min)
        q = (
            select(Issue).distinct()
            .join(Worklog, Worklog.issue_id == Issue.id)
            .where(Worklog.started_at >= start_dt, Worklog.started_at <= end_dt)
        )
        if teams:
            issue_clauses = [Issue.team.in_(teams)]
            import json as _json
            for t in teams:
                t_json = _json.dumps(t, ensure_ascii=False)
                escaped = t_json.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                issue_clauses.append(Issue.participating_teams.like(f"%{escaped}%", escape="\\"))
            emp_subq = (
                select(EmployeeTeam.employee_id).where(EmployeeTeam.team.in_(teams)).scalar_subquery()
            )
            q = q.where(or_(or_(*issue_clauses), Worklog.employee_id.in_(emp_subq)))
        return list(self.db.execute(q).scalars().all())

    def _select_worklogs(self, issue_ids: list[str], start_dt: datetime, end_dt: datetime):
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

    def _kpi(self, issues, worklog_rows, start_dt, end_dt, year, quarter, teams) -> dict:
        # health_index — взвешенная сумма (см. plan)
        critical_open = sum(
            1 for i in issues
            if (i.priority or "").lower() in ("critical", "highest", "blocker")
            and (i.status or "").lower() != "done"
        )
        total = len(issues) or 1
        critical_share = critical_open / total

        # средний возраст open / 30 дней (норма)
        now_dt = datetime.utcnow()
        ages_days = []
        for i in issues:
            if (i.status or "").lower() != "done" and i.created_at:
                ages_days.append((now_dt - i.created_at).days)
        avg_age = sum(ages_days) / len(ages_days) if ages_days else 0
        age_score = max(0.0, 1.0 - avg_age / 30.0)

        # plan_fact из сценария
        plan_pct = self._scenario_pct(year, quarter, teams)

        # capacity overload — если средняя загрузка >100% по ролям → штраф
        cap_overload = self._capacity_overload(year, quarter, teams)

        health = (
            35 * (1 - critical_share)
            + 25 * age_score
            + 20 * (plan_pct / 100.0)
            + 20 * (1 - cap_overload)
        )
        health = max(0, min(100, round(health)))

        # resource_utilization — средняя загрузка ресурса по кварталу
        utilization = self._utilization_pct(year, quarter, teams)

        return {
            "health_index": health,
            "resource_utilization_pct": round(utilization, 1),
            "critical_risks_count": critical_open,
            "scenario_plan_fact_pct": round(plan_pct, 1),
        }

    def _health_trend_8w(self, end_d: date, teams: list[str]) -> list[dict]:
        """Последние 8 недель: для каждой недели — упрощённый health (без plan_pct,
        который недельно нерелевантен). Пишем точку на конец недели."""
        out: list[dict] = []
        for w in range(8):
            week_end = end_d - timedelta(weeks=w)
            week_start = week_end - timedelta(days=6)
            start_dt = datetime.combine(week_start, time.min)
            end_dt = datetime.combine(week_end, time.max)
            q = select(Issue).distinct().join(Worklog, Worklog.issue_id == Issue.id).where(
                Worklog.started_at >= start_dt, Worklog.started_at <= end_dt,
            )
            if teams:
                q = q.where(Issue.team.in_(teams))
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

    def _modules(self, issues, worklog_rows, teams: list[str]) -> list[dict]:
        """Команды как «направления». Health: ratio of crit issues. Load: utilization. Note: text."""
        by_team: dict[str, dict] = defaultdict(lambda: {"issues": 0, "crit": 0, "hours": 0.0})
        for i in issues:
            t = i.team or "—"
            by_team[t]["issues"] += 1
            if (i.priority or "").lower() in ("critical", "highest", "blocker") and (i.status or "").lower() != "done":
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
            load = min(100, round(agg["hours"] / max(agg["issues"], 1) * 5))  # rough
            note = f"{agg['issues']} задач, {agg['crit']} критичных" if agg["crit"] else f"{agg['issues']} задач"
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

    def _hours_by_type_trend(self, start_dt: datetime, end_dt: datetime, teams: list[str]) -> list[dict]:
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
            q = select(Issue.issue_type, func.sum(Worklog.hours)).join(
                Worklog, Worklog.issue_id == Issue.id,
            ).where(Worklog.started_at >= sdt, Worklog.started_at <= edt).group_by(Issue.issue_type)
            if teams:
                q = q.where(Issue.team.in_(teams))
            row = {"w": ws.strftime("%d.%m"), "incidents": 0, "improvements": 0, "consultations": 0, "regulatory": 0}
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
        """Сценарий план vs worklog факт по 4 ролям."""
        scen = self.db.execute(
            select(Scenario).where(
                Scenario.year == year, Scenario.quarter == quarter,
                Scenario.status.in_(("approved", "draft")),
            ).order_by(Scenario.status.desc(), Scenario.updated_at.desc())
        ).scalars().first()

        plan: dict[str, float] = defaultdict(float)
        if scen:
            allocs = self.db.execute(
                select(ScenarioAllocation).where(ScenarioAllocation.scenario_id == scen.id)
            ).scalars().all()
            for a in allocs:
                plan["analyst"] += float(getattr(a, "analyst_hours", 0) or 0)
                plan["dev"] += float(getattr(a, "dev_hours", 0) or 0)
                plan["qa"] += float(getattr(a, "qa_hours", 0) or 0)
                plan["ope"] += float(getattr(a, "ope_hours", 0) or 0)

        # Факт — worklog × employee.role в квартале
        from calendar import monthrange
        q_start = (quarter - 1) * 3 + 1
        em = q_start + 2
        sdt = datetime.combine(date(year, q_start, 1), time.min)
        edt = datetime.combine(date(year, em, monthrange(year, em)[1]), time.max)

        fact: dict[str, float] = defaultdict(float)
        q = select(Employee.role, func.sum(Worklog.hours)).join(
            Worklog, Worklog.employee_id == Employee.id,
        ).where(Worklog.started_at >= sdt, Worklog.started_at <= edt).group_by(Employee.role)
        if teams:
            q = q.join(Issue, Issue.id == Worklog.issue_id).where(Issue.team.in_(teams))
        for role, hrs in self.db.execute(q).all():
            r = (role or "").lower()
            if r == "analyst":
                fact["analyst"] += float(hrs or 0)
            elif r in ("dev", "developer"):
                fact["dev"] += float(hrs or 0)
            elif r == "qa":
                fact["qa"] += float(hrs or 0)
            else:
                fact["ope"] += float(hrs or 0)

        labels = {"analyst": "Аналитики", "dev": "Разработка", "qa": "QA", "ope": "ОПЭ"}
        return [
            {"role": labels[k], "plan": round(plan[k], 1), "fact": round(fact[k], 1)}
            for k in ("analyst", "dev", "qa", "ope")
        ]

    def _top_risks(self, issues, worklog_rows) -> list[dict]:
        """Outliers + критичные open задачи. До 5."""
        per_issue: dict[str, dict] = {}
        for i in issues:
            per_issue[i.id] = {
                "issue_id": i.id, "key": i.key, "summary": i.summary,
                "hours": 0.0, "worklog_count": 0, "is_done": (i.status or "").lower() == "done",
                "first_log": None, "last_log": None, "distinct_workers": set(),
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
        for o in outliers[:5]:
            risks.append({
                "title": f"{o.issue_key}: {o.reason}",
                "impact": o.context or "Аномалия в треке задачи",
                "owner": "Руководитель сопровождения",
                "action": "Разобрать в ближайшем sync, назначить ответственного",
                "level": "red" if o.reason in ("hours_exceed", "long_running") else "yellow",
                "key": o.issue_key,
            })
        if len(risks) < 3:
            for i in issues:
                if (i.priority or "").lower() in ("critical", "blocker") and (i.status or "").lower() != "done":
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
        """Средняя загрузка по ролям за квартал. Использует ResourceBaseService если доступно,
        иначе — упрощение через worklog/норматив."""
        roles = ["analyst", "dev", "qa", "lead"]
        labels = {"analyst": "Консультанты 1С", "dev": "Разработчики 1С",
                  "qa": "QA", "lead": "Архитектор / тимлид"}
        out: list[dict] = []
        # Упрощение MVP: считаем из worklog.hours / 520 (квартал ~520 раб.часов на FTE)
        from calendar import monthrange
        q_start = (quarter - 1) * 3 + 1
        em = q_start + 2
        sdt = datetime.combine(date(year, q_start, 1), time.min)
        edt = datetime.combine(date(year, em, monthrange(year, em)[1]), time.max)
        for role in roles:
            q = select(Employee.id, func.sum(Worklog.hours)).join(
                Worklog, Worklog.employee_id == Employee.id,
            ).where(
                Worklog.started_at >= sdt, Worklog.started_at <= edt,
                func.lower(Employee.role) == role if role != "dev"
                else func.lower(Employee.role).in_(("dev", "developer")),
            ).group_by(Employee.id)
            if teams:
                q = q.join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id).where(
                    EmployeeTeam.team.in_(teams),
                )
            rows = list(self.db.execute(q).all())
            if not rows:
                out.append({"role": labels[role], "utilization_pct": 0})
                continue
            avg_hours = sum(float(h or 0) for _, h in rows) / len(rows)
            pct = min(100, round(avg_hours / 520 * 100))
            out.append({"role": labels[role], "utilization_pct": pct})
        return out

    # --- helpers ---

    def _scenario_pct(self, year: int, quarter: int, teams: list[str]) -> float:
        rows = self._plan_fact_by_role(year, quarter, teams)
        plan_total = sum(r["plan"] for r in rows)
        fact_total = sum(r["fact"] for r in rows)
        if plan_total == 0:
            return 0.0
        return min(100.0, fact_total / plan_total * 100)

    def _capacity_overload(self, year: int, quarter: int, teams: list[str]) -> float:
        cap = self._capacity_by_role(year, quarter, teams)
        over = [c for c in cap if c["utilization_pct"] > 100]
        return min(1.0, len(over) / max(len(cap), 1))

    def _utilization_pct(self, year: int, quarter: int, teams: list[str]) -> float:
        cap = self._capacity_by_role(year, quarter, teams)
        if not cap:
            return 0.0
        return sum(c["utilization_pct"] for c in cap) / len(cap)
```

- [ ] **Step 2: Lint**

```bash
py -3.10 -m ruff check app/services/executive_dashboard_service.py
```

Expected: 0 ошибок (или только не-блокирующие предупреждения; критичные исправить).

- [ ] **Step 3: Commit**

```bash
git add app/services/executive_dashboard_service.py
git commit -m "feat(executive): aggregation service with health/queue/plan-fact/risks/capacity"
```

### Task 4: Тесты ExecutiveDashboardService

**Files:**
- Create: `tests/test_executive_dashboard_service.py`

- [ ] **Step 1: Создать тест-файл**

Минимум: 4 теста (kpi base, modules health colors, queue distribution, plan_fact). Использовать существующие фикстуры из `tests/conftest.py`. Если их нет под нужный объект — создавать вручную через `db.add(...)`.

```python
"""ExecutiveDashboardService — aggregation tests."""
from datetime import date, datetime
import pytest

from app.models.employee import Employee
from app.models.issue import Issue
from app.models.worklog import Worklog
from app.services.executive_dashboard_service import (
    ExecutiveDashboardService, team_set_hash,
)


def test_team_set_hash_stable():
    h1 = team_set_hash(["A", "B"])
    h2 = team_set_hash(["B", "A"])
    assert h1 == h2 != "all"
    assert team_set_hash([]) == "all"


def test_kpi_zero_when_no_issues(db_session):
    svc = ExecutiveDashboardService(db_session)
    f = svc.aggregate(year=2026, quarter=2, teams=[])
    assert f.kpi["critical_risks_count"] == 0
    assert f.kpi["scenario_plan_fact_pct"] == 0.0


def test_queue_buckets_count_open_issues_only(db_session):
    """Open bug+critical → critical bucket. Done bug → не считается."""
    issue_open = Issue(
        id="i-open", key="P-1", summary="open bug",
        issue_type="Bug", priority="Critical", status="In Progress",
        team="T1", created_at=datetime(2026, 4, 5),
    )
    issue_done = Issue(
        id="i-done", key="P-2", summary="closed bug",
        issue_type="Bug", priority="Critical", status="Done",
        team="T1", created_at=datetime(2026, 4, 5),
    )
    db_session.add_all([issue_open, issue_done])
    emp = Employee(id="e1", display_name="X", team="T1", role="analyst", active=True)
    db_session.add(emp)
    db_session.add(Worklog(
        id="w1", issue_id="i-open", employee_id="e1", hours=2.0,
        started_at=datetime(2026, 4, 10),
    ))
    db_session.add(Worklog(
        id="w2", issue_id="i-done", employee_id="e1", hours=2.0,
        started_at=datetime(2026, 4, 10),
    ))
    db_session.commit()

    svc = ExecutiveDashboardService(db_session)
    f = svc.aggregate(year=2026, quarter=2, teams=["T1"])
    incidents = next(b for b in f.queue if b["name"] == "Инциденты")
    assert incidents["critical"] == 1  # only open
```

(Дополнить ещё 1-2 тестами в том же стиле.)

- [ ] **Step 2: Прогнать**

```bash
py -3.10 -m pytest tests/test_executive_dashboard_service.py -v
```

Expected: PASS. При ошибках — поправить тесты или сервис, не fudge.

- [ ] **Step 3: Commit**

```bash
git add tests/test_executive_dashboard_service.py
git commit -m "test(executive): aggregation service basic coverage"
```

---

## Phase C: AI Synthesizer

### Task 5: Executive Synthesizer + промпт

**Files:**
- Create: `app/services/llm/executive_synthesizer.py`

- [ ] **Step 1: Создать synthesizer**

```python
"""ExecutiveSynthesizer — Reduce-фаза для дашборда руководителя.

3 секции: improved (зелёная), risk (жёлтая), action (серая).
Faithfulness-проверка не такая строгая как в WorkTypeSynthesizer (нет ФИО/ключей задач
в обязательном выводе), но всё равно валидируем JSON структуру.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger("jira_analytics.executive")
PROMPT_VERSION = "exec-synth-v1"


@dataclass
class ExecutiveSynthesis:
    improved: str
    risk: str
    action: str
    is_fallback: bool = False


class ExecutiveSynthesizerProvider(Protocol):
    model: str
    async def synthesize_executive_summary(self, prompt: str) -> tuple[dict, dict]: ...


def build_executive_prompt(findings: dict) -> str:
    return "\n".join([
        "Ты — старший аналитик службы сопровождения 1С. Готовишь короткую сводку для руководителя.",
        "Используй ТОЛЬКО переданные числа и факты. Не выдумывай.",
        "Никаких ФИО. Никаких сравнений конкретных людей.",
        "Стиль: деловой, фактический, без воды. На русском.",
        "",
        "FINDINGS:",
        json.dumps(findings, ensure_ascii=False, indent=2),
        "",
        "Верни JSON со схемой:",
        "{",
        '  "improved": "<2-3 предложения о том, что улучшилось за период>",',
        '  "risk": "<2-3 предложения о ключевом риске сейчас>",',
        '  "action": "<2-3 предложения о конкретном действии на ближайшие 1-2 недели>"',
        "}",
        "Каждая секция — самостоятельная, без отсылок к другим секциям.",
    ])


def _fallback(findings: dict) -> ExecutiveSynthesis:
    kpi = findings.get("kpi") or {}
    return ExecutiveSynthesis(
        improved=f"Индекс здоровья: {kpi.get('health_index', '—')}/100. AI-сводка недоступна.",
        risk=f"Критичных рисков: {kpi.get('critical_risks_count', 0)}.",
        action="Просмотрите блоки дашборда вручную.",
        is_fallback=True,
    )


class ExecutiveSynthesizer:
    def __init__(self, provider: ExecutiveSynthesizerProvider) -> None:
        self.provider = provider

    async def synthesize(self, findings: dict) -> tuple[ExecutiveSynthesis, dict]:
        prompt = build_executive_prompt(findings)
        try:
            obj, meta = await self.provider.synthesize_executive_summary(prompt)
        except Exception as e:
            logger.warning("ExecutiveSynthesizer failed: %s", e)
            return _fallback(findings), {"failure": str(e)[:200]}

        improved = (obj.get("improved") or "").strip()
        risk = (obj.get("risk") or "").strip()
        action = (obj.get("action") or "").strip()

        if not (improved and risk and action):
            logger.warning("ExecutiveSynthesizer: incomplete output, fallback")
            return _fallback(findings), {**meta, "incomplete": True}

        return ExecutiveSynthesis(improved=improved, risk=risk, action=action), meta
```

- [ ] **Step 2: Lint**

```bash
py -3.10 -m ruff check app/services/llm/executive_synthesizer.py
```

- [ ] **Step 3: Commit**

```bash
git add app/services/llm/executive_synthesizer.py
git commit -m "feat(executive): AI synthesizer 3-section (improved/risk/action)"
```

### Task 6: Provider methods (Gemini + OpenRouter + base Protocol)

**Files:**
- Modify: `app/services/llm/base.py`, `app/services/llm/openrouter.py`, `app/services/llm/gemini.py`

- [ ] **Step 1: Расширить `LLMProvider` Protocol в `base.py`**

В `app/services/llm/base.py` после метода `cluster_candidates` добавить:

```python
    async def synthesize_executive_summary(self, prompt: str) -> tuple[dict, dict]:
        """Executive dashboard reduce-phase. Возвращает (data_dict, meta)."""
        ...
```

- [ ] **Step 2: Реализовать в OpenRouter (`openrouter.py`)**

В конец класса `OpenRouterProvider`, перед `healthcheck`, добавить:

```python
    async def synthesize_executive_summary(self, prompt: str) -> tuple[dict, dict]:
        """Executive dashboard. JSON со схемой improved/risk/action."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "improved": {"type": "string", "maxLength": 600},
                "risk": {"type": "string", "maxLength": 600},
                "action": {"type": "string", "maxLength": 600},
            },
            "required": ["improved", "risk", "action"],
        }
        chain = [self.model] + [m for m in self.fallback_models if m and m != self.model]
        last_exc: Exception | None = None
        for model_id in chain:
            try:
                return await self._call_json(model_id, prompt, schema)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_STATUSES:
                    last_exc = e
                    continue
                raise
            except (LLMResponseError, httpx.TimeoutException) as e:
                last_exc = e
                continue
        if last_exc is not None:
            raise last_exc
        raise LLMResponseError("synthesize_executive_summary: пустая цепочка моделей")
```

- [ ] **Step 3: Реализовать в Gemini (`gemini.py`)**

В конец класса `GeminiProvider`, перед `healthcheck`, добавить:

```python
    async def synthesize_executive_summary(self, prompt: str) -> tuple[dict, dict]:
        schema = {
            "type": "object",
            "properties": {
                "improved": {"type": "string"},
                "risk": {"type": "string"},
                "action": {"type": "string"},
            },
            "required": ["improved", "risk", "action"],
        }
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
        resp = await self._post(url, body)
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)
        meta = {
            "input_tokens": resp.get("usageMetadata", {}).get("promptTokenCount"),
            "output_tokens": resp.get("usageMetadata", {}).get("candidatesTokenCount"),
            "model": self.model,
        }
        return data, meta
```

- [ ] **Step 4: Прогнать lint**

```bash
py -3.10 -m ruff check app/services/llm/
```

- [ ] **Step 5: Commit**

```bash
git add app/services/llm/base.py app/services/llm/openrouter.py app/services/llm/gemini.py
git commit -m "feat(executive): providers expose synthesize_executive_summary"
```

### Task 7: Тест executive synthesizer

**Files:**
- Create: `tests/test_executive_synthesizer.py`

- [ ] **Step 1: Создать тесты**

```python
"""ExecutiveSynthesizer tests."""
import pytest
from unittest.mock import AsyncMock

from app.services.llm.executive_synthesizer import (
    ExecutiveSynthesizer, build_executive_prompt,
)


@pytest.mark.asyncio
async def test_synthesizer_happy_path():
    provider = AsyncMock()
    provider.model = "test"
    provider.synthesize_executive_summary = AsyncMock(return_value=(
        {"improved": "SLA вырос", "risk": "Очередь растёт", "action": "Усилить 1ю линию"},
        {"model": "test"},
    ))
    s = ExecutiveSynthesizer(provider)
    out, meta = await s.synthesize({"kpi": {"health_index": 80}})
    assert out.improved == "SLA вырос"
    assert out.risk == "Очередь растёт"
    assert out.action == "Усилить 1ю линию"
    assert not out.is_fallback


@pytest.mark.asyncio
async def test_synthesizer_provider_failure_falls_back():
    provider = AsyncMock()
    provider.model = "test"
    provider.synthesize_executive_summary = AsyncMock(side_effect=RuntimeError("boom"))
    s = ExecutiveSynthesizer(provider)
    out, meta = await s.synthesize({"kpi": {"health_index": 60, "critical_risks_count": 3}})
    assert out.is_fallback
    assert "60" in out.improved
    assert "3" in out.risk


@pytest.mark.asyncio
async def test_synthesizer_incomplete_output_falls_back():
    provider = AsyncMock()
    provider.model = "test"
    provider.synthesize_executive_summary = AsyncMock(return_value=(
        {"improved": "ok", "risk": "", "action": "do"}, {"model": "test"},
    ))
    s = ExecutiveSynthesizer(provider)
    out, _ = await s.synthesize({"kpi": {}})
    assert out.is_fallback


def test_prompt_contains_findings():
    prompt = build_executive_prompt({"kpi": {"health_index": 86}, "modules": []})
    assert "86" in prompt
    assert "improved" in prompt
    assert "risk" in prompt
    assert "action" in prompt
```

- [ ] **Step 2: Прогнать**

```bash
py -3.10 -m pytest tests/test_executive_synthesizer.py -v
```

Expected: PASS все.

- [ ] **Step 3: Commit**

```bash
git add tests/test_executive_synthesizer.py
git commit -m "test(executive): synthesizer fallback + happy path"
```

---

## Phase D: Endpoint

### Task 8: REST endpoint `/executive/dashboard`

**Files:**
- Create: `app/api/endpoints/executive.py`
- Modify: `app/api/router.py`

- [ ] **Step 1: Создать endpoint**

```python
"""Executive dashboard endpoint.

GET  /executive/dashboard?year&quarter&teams[]    — return cached or 404
POST /executive/dashboard/build                   — recompute + LLM synth, return snapshot
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.executive_snapshot import ExecutiveSnapshot
from app.models.user import User
from app.services.executive_dashboard_service import (
    ExecutiveDashboardService, team_set_hash,
)
from app.services.llm.base import get_llm_provider
from app.services.llm.executive_synthesizer import (
    ExecutiveSynthesizer, PROMPT_VERSION as EXEC_PROMPT_VERSION,
)

logger = logging.getLogger("jira_analytics.executive")
router = APIRouter()


class ExecutiveBuildRequest(BaseModel):
    year: int
    quarter: int = Field(ge=1, le=4)
    teams: list[str] = Field(default_factory=list)


class ExecutiveDashboardResponse(BaseModel):
    year: int
    quarter: int
    team_set: list[str]
    generated_at: datetime
    model_id: Optional[str]
    prompt_version: Optional[str]
    data: dict


def _make_response(snap: ExecutiveSnapshot) -> ExecutiveDashboardResponse:
    return ExecutiveDashboardResponse(
        year=snap.year,
        quarter=snap.quarter,
        team_set=json.loads(snap.team_set_json),
        generated_at=snap.generated_at,
        model_id=snap.model_id,
        prompt_version=snap.prompt_version,
        data=json.loads(snap.snapshot_data),
    )


@router.get("/dashboard", response_model=ExecutiveDashboardResponse)
def get_dashboard(
    year: int,
    quarter: int,
    teams: list[str] = [],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return cached snapshot. 404 if none built yet."""
    th = team_set_hash(teams)
    snap = db.execute(
        select(ExecutiveSnapshot).where(
            ExecutiveSnapshot.year == year,
            ExecutiveSnapshot.quarter == quarter,
            ExecutiveSnapshot.team_set_hash == th,
        )
    ).scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not built yet")
    return _make_response(snap)


@router.post("/dashboard/build", response_model=ExecutiveDashboardResponse)
async def build_dashboard(
    payload: ExecutiveBuildRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate fresh + run LLM synthesis + persist snapshot."""
    svc = ExecutiveDashboardService(db)
    findings = svc.aggregate(year=payload.year, quarter=payload.quarter, teams=payload.teams)

    findings_dict = {
        "period": findings.period,
        "kpi": findings.kpi,
        "health_trend": findings.health_trend,
        "modules": findings.modules,
        "queue": findings.queue,
        "hours_by_type_trend": findings.hours_by_type_trend,
        "plan_fact_by_role": findings.plan_fact_by_role,
        "top_risks": findings.top_risks,
        "capacity_by_role": findings.capacity_by_role,
    }

    try:
        provider = get_llm_provider(db)
    except Exception as e:
        logger.warning("LLM provider unavailable: %s", e)
        provider = None

    model_id = None
    if provider:
        synth = ExecutiveSynthesizer(provider)
        synthesis, meta = await synth.synthesize(findings_dict)
        findings_dict["ai_summary"] = {
            "improved": synthesis.improved,
            "risk": synthesis.risk,
            "action": synthesis.action,
            "is_fallback": synthesis.is_fallback,
        }
        model_id = meta.get("model")
    else:
        findings_dict["ai_summary"] = {
            "improved": "Провайдер LLM не настроен.",
            "risk": "AI-сводка недоступна.",
            "action": "Настройте провайдер в /settings.",
            "is_fallback": True,
        }

    th = team_set_hash(payload.teams)
    existing = db.execute(
        select(ExecutiveSnapshot).where(
            ExecutiveSnapshot.year == payload.year,
            ExecutiveSnapshot.quarter == payload.quarter,
            ExecutiveSnapshot.team_set_hash == th,
        )
    ).scalar_one_or_none()

    if existing:
        existing.snapshot_data = json.dumps(findings_dict, ensure_ascii=False)
        existing.team_set_json = json.dumps(payload.teams, ensure_ascii=False)
        existing.model_id = model_id
        existing.prompt_version = EXEC_PROMPT_VERSION
        existing.generated_at = datetime.utcnow()
        existing.created_by = current_user.id
        snap = existing
    else:
        snap = ExecutiveSnapshot(
            year=payload.year,
            quarter=payload.quarter,
            team_set_hash=th,
            team_set_json=json.dumps(payload.teams, ensure_ascii=False),
            snapshot_data=json.dumps(findings_dict, ensure_ascii=False),
            model_id=model_id,
            prompt_version=EXEC_PROMPT_VERSION,
            created_by=current_user.id,
        )
        db.add(snap)
    db.commit()
    db.refresh(snap)
    return _make_response(snap)
```

- [ ] **Step 2: Подключить router в `app/api/router.py`**

В блок импортов добавить:

```python
from app.api.endpoints import (
    ...,
    executive as executive_endpoints,
)
```

И в блок authenticated routers:

```python
api_router.include_router(
    executive_endpoints.router, prefix="/executive", tags=["executive"], dependencies=_auth_dep,
)
```

- [ ] **Step 3: Lint**

```bash
py -3.10 -m ruff check app/api/endpoints/executive.py app/api/router.py
```

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/executive.py app/api/router.py
git commit -m "feat(executive): GET dashboard + POST build endpoint"
```

### Task 9: Тест endpoint

**Files:**
- Create: `tests/test_executive_endpoint.py`

- [ ] **Step 1: Создать тест**

```python
"""Executive dashboard endpoint tests."""
import pytest
from unittest.mock import AsyncMock, patch


def test_get_dashboard_404_when_no_snapshot(authed_client):
    r = authed_client.get("/api/v1/executive/dashboard?year=2026&quarter=2")
    assert r.status_code == 404


def test_post_build_then_get_returns_snapshot(authed_client, db_session):
    """POST /build создаёт snapshot, GET его читает."""
    with patch("app.api.endpoints.executive.get_llm_provider", side_effect=Exception("no LLM")):
        r = authed_client.post(
            "/api/v1/executive/dashboard/build",
            json={"year": 2026, "quarter": 2, "teams": []},
        )
    assert r.status_code == 200
    data = r.json()["data"]
    assert "kpi" in data
    assert "ai_summary" in data
    assert data["ai_summary"]["is_fallback"] is True

    r2 = authed_client.get("/api/v1/executive/dashboard?year=2026&quarter=2")
    assert r2.status_code == 200
    assert r2.json()["data"]["kpi"] == data["kpi"]
```

ПРИМЕЧАНИЕ: имя фикстуры `authed_client` подобрать под существующий стиль (см. `tests/conftest.py` или другие endpoint-тесты).

- [ ] **Step 2: Прогнать**

```bash
py -3.10 -m pytest tests/test_executive_endpoint.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_executive_endpoint.py
git commit -m "test(executive): endpoint GET/POST coverage"
```

---

## Phase E: Frontend

### Task 10: API client + типы

**Files:**
- Create: `frontend/src/api/executive.ts`

- [ ] **Step 1: Создать клиент**

```typescript
import { apiClient } from "./client";

export interface ExecutiveKpi {
  health_index: number;
  resource_utilization_pct: number;
  critical_risks_count: number;
  scenario_plan_fact_pct: number;
}

export interface ExecutiveModule {
  name: string;
  health: "green" | "yellow" | "red";
  risk: string;
  load: string;
  note: string;
}

export interface ExecutiveQueue {
  name: string;
  critical: number;
  high: number;
  normal: number;
}

export interface ExecutiveTrendPoint {
  w: string;
  value: number;
}

export interface ExecutiveHoursTrend {
  w: string;
  incidents: number;
  improvements: number;
  consultations: number;
  regulatory: number;
}

export interface ExecutivePlanFact {
  role: string;
  plan: number;
  fact: number;
}

export interface ExecutiveRisk {
  title: string;
  impact: string;
  owner: string;
  action: string;
  level: "red" | "yellow" | "green";
  key?: string;
}

export interface ExecutiveCapacity {
  role: string;
  utilization_pct: number;
}

export interface ExecutiveAiSummary {
  improved: string;
  risk: string;
  action: string;
  is_fallback: boolean;
}

export interface ExecutiveDashboardData {
  period: { year: number; quarter: number; start: string; end: string };
  kpi: ExecutiveKpi;
  health_trend: ExecutiveTrendPoint[];
  modules: ExecutiveModule[];
  queue: ExecutiveQueue[];
  hours_by_type_trend: ExecutiveHoursTrend[];
  plan_fact_by_role: ExecutivePlanFact[];
  top_risks: ExecutiveRisk[];
  capacity_by_role: ExecutiveCapacity[];
  ai_summary: ExecutiveAiSummary;
}

export interface ExecutiveDashboardResponse {
  year: number;
  quarter: number;
  team_set: string[];
  generated_at: string;
  model_id: string | null;
  prompt_version: string | null;
  data: ExecutiveDashboardData;
}

export async function getDashboard(
  year: number, quarter: number, teams: string[],
): Promise<ExecutiveDashboardResponse | null> {
  try {
    const r = await apiClient.get<ExecutiveDashboardResponse>("/executive/dashboard", {
      params: { year, quarter, teams },
    });
    return r.data;
  } catch (e: any) {
    if (e.response?.status === 404) return null;
    throw e;
  }
}

export async function buildDashboard(
  year: number, quarter: number, teams: string[],
): Promise<ExecutiveDashboardResponse> {
  const r = await apiClient.post<ExecutiveDashboardResponse>("/executive/dashboard/build", {
    year, quarter, teams,
  });
  return r.data;
}
```

ПРИМЕЧАНИЕ: импорт `apiClient` адаптировать под существующий стиль фронта (`from "./client"` или `from "@/api/axios"` — посмотреть в соседних файлах `frontend/src/api/`).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/executive.ts
git commit -m "feat(fe-executive): typed API client"
```

### Task 11: Виджеты

**Files:**
- Create: `frontend/src/components/executive/KpiCard.tsx`
- Create: `frontend/src/components/executive/AISummary.tsx`
- Create: `frontend/src/components/executive/ModuleHealth.tsx`
- Create: `frontend/src/components/executive/RiskList.tsx`

Каждый компонент — мелкий, переиспользуемый. Используй AntD `Card` (если в проекте принят стиль AntD) или Tailwind. Посмотри `frontend/src/pages/DashboardPage.tsx` чтобы понять стиль.

- [ ] **Step 1: KpiCard.tsx**

Принимает `{ icon, title, value, delta, status: 'good'|'warn'|'bad', detail }`. Один div с иконкой + заголовок + большое число + delta-бейдж + детали. См. мокап.

- [ ] **Step 2: AISummary.tsx**

Принимает `{ improved, risk, action, isFallback }`. 3 цветные секции (зелёная/жёлтая/серая) в grid-3.

- [ ] **Step 3: ModuleHealth.tsx**

Принимает `modules: ExecutiveModule[]`. Список строк с dot (зелёный/жёлтый/красный) + name + risk + bar load + note.

- [ ] **Step 4: RiskList.tsx**

Принимает `risks: ExecutiveRisk[]`. Каждый элемент — карточка с title, impact, owner, action, level dot.

- [ ] **Step 5: Lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/executive/
git commit -m "feat(fe-executive): KPI/AI summary/modules/risks widgets"
```

### Task 12: Page + recharts графики

**Files:**
- Create: `frontend/src/pages/ExecutiveDashboardPage.tsx`

- [ ] **Step 1: Создать страницу**

Структура повторяет мокап (но без SLA/релизов; вместо — UtilCard + ScenarioPctCard + HoursTrend + PlanFactByRole). Использует:
- `useState` для year/quarter (default — текущий квартал)
- Глобальный team filter из контекста
- `useQuery` (TanStack) для GET → если 404 показывает «Постройте дашборд», для POST через mutation
- Кнопка «Построить» / «Пересчёт» в header
- recharts: AreaChart (health_trend), BarChart stacked vertical (queue), AreaChart stacked (hours_by_type_trend), BarChart (plan_fact_by_role)

Для краткости: читай существующий `WorkTypeReportPage.tsx` чтобы повторить паттерн SSE-loading / error / mutation. Для executive — без SSE, обычный POST.

- [ ] **Step 2: Lint + сборка**

```bash
cd frontend && npm run lint && npm run build
```

Expected: 0 ошибок, build успешен.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ExecutiveDashboardPage.tsx
git commit -m "feat(fe-executive): dashboard page with KPI/charts/AI summary"
```

### Task 13: Routing + nav

**Files:**
- Modify: `frontend/src/AppRouter.tsx` (или эквивалент)
- Modify: `frontend/src/components/AppLayout.tsx` (или nav-компонент)

- [ ] **Step 1: Зарегистрировать маршрут**

Добавить в роутер `/executive` → `ExecutiveDashboardPage`. Использовать lazy-импорт (`React.lazy`) если в проекте принято — посмотри `frontend/src/pages/lazyPages.tsx`.

- [ ] **Step 2: Добавить пункт меню**

В навигацию добавить пункт «Executive» (или «Сводка для руководителя») перед/после «Тематический отчёт».

- [ ] **Step 3: Lint + build**

```bash
cd frontend && npm run lint && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(fe-executive): route /executive + nav entry"
```

---

## Phase F: Smoke

### Task 14: End-to-end smoke

**Files:** none

- [ ] **Step 1: Прогнать все backend-тесты**

```bash
py -3.10 -m pytest tests/test_executive_dashboard_service.py tests/test_executive_synthesizer.py tests/test_executive_endpoint.py -v
```

Expected: все PASS.

- [ ] **Step 2: Прогнать full lint**

```bash
py -3.10 -m ruff check app/services/executive_dashboard_service.py app/services/llm/executive_synthesizer.py app/api/endpoints/executive.py
cd frontend && npm run lint
```

- [ ] **Step 3: Frontend build**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Запустить локально**

Перезапустить backend (kill `:8000` + uvicorn). Перейти на `/executive`, выбрать текущий квартал, нажать «Построить». Проверить:
- KPI cards заполнены числами (не «—»).
- AI summary 3 секции (если LLM настроен).
- Charts отрисовываются.
- Модули показывают команды с health-цветами.
- Top risks непустые (если есть outliers).

- [ ] **Step 5: Push**

```bash
git push origin main
```

---

## Self-Review Notes

- 14 tasks, ~20 commits.
- Не используем SSE для build — endpoint синхронный, ~3-10 секунд (1 LLM call). Если медленно — потом добавим SSE.
- Health index формула — простая, можно править после feedback PM.
- Outliers переиспользуют `detect_outliers_for_theme` без модификаций — surgical change.
- Plan/Fact по ролям читает только `approved` или `draft` сценарий текущего квартала, последний по updated_at.
- Capacity по ролям использует упрощённый расчёт (worklog/520). Проверить с PM нужна ли точная база из ResourceBaseService.
- AI summary 3 секции — отдельная схема, не конфликтует с тематическим synthesizer.
- Кэш-ключ: `year + quarter + team_set_hash`. Если PM захочет ежемесячный — добавим month nullable.
- Frontend: не трогаем существующие страницы, только добавляем `/executive`.
