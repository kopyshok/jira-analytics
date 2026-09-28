# «Первые шаги» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Панель «Первые шаги» в шапке: общий на команду блок настройки с авто-проверками по данным и личный блок знакомства; экскурсии по живым страницам (AntD Tour).

**Architecture:** Сервер хранит только состояние: отметки команды (таблица `team_onboarding_marks`, строка на команду+шаг, защёлка авто-шагов при чтении) и личное состояние пользователя (JSON-поле `users.onboarding`). Тексты шагов, порядок и экскурсии — статичная конфигурация на фронте в `frontend/src/onboarding/`. Экскурсии цепляются к элементам страниц через атрибут `data-tour`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic (batch), pytest; React 19, AntD 6.3 (`Tour`), TanStack Query 5, react-router 7.

Spec: `docs/superpowers/specs/2026-09-28-onboarding-first-steps-design.md`.

Рабочая копия: `D:\ClaudeDev\JiraAnalysis\.worktrees\onboarding` (ветка `feature/onboarding-first-steps`). Все команды — из неё. Windows: `py -3.10 -m pytest`. Прогон всего набора — без `tests/api/test_llm.py` (висит без сети).

---

## File map

Backend:
- Create `app/models/team_onboarding_mark.py` — модель отметки.
- Modify `app/models/__init__.py` — регистрация модели.
- Modify `app/models/user.py` — колонка `onboarding_raw` + свойство `onboarding`.
- Create `alembic/versions/ob01_onboarding.py` — таблица + колонка.
- Create `app/services/onboarding_service.py` — авто-условия, защёлка, сбор статуса.
- Create `app/api/endpoints/onboarding.py` — 3 эндпоинта.
- Modify `app/api/router.py` — подключение роутера.
- Create `tests/api/test_onboarding.py`.

Frontend (`frontend/src/`):
- Create `api/onboarding.ts` — типы + запросы.
- Create `onboarding/steps.ts`, `onboarding/tours.ts` — конфигурация.
- Create `onboarding/OnboardingContext.tsx` — провайдер, хуки.
- Create `onboarding/TourRunner.tsx`, `onboarding/OnboardingDrawer.tsx`, `onboarding/OnboardingButton.tsx`.
- Modify `aurora/shell/AuroraShell.tsx` (провайдер + TourRunner + Drawer), `aurora/shell/AuroraTopbar.tsx` (кнопка),
  `components/Layout/GlobalHelpButton.tsx` + `components/shared/HelpDrawer.tsx` (кнопка «Первые шаги» в шапке справки).
- Modify страницы — только атрибуты `data-tour` и, где нужно, начальная вкладка из адреса.
- Create `frontend/e2e/onboarding.spec.ts`.

---

### Task 1: Модель, поле пользователя, миграция

**Files:**
- Create: `app/models/team_onboarding_mark.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/user.py`
- Create: `alembic/versions/ob01_onboarding.py`

- [ ] **Step 1: Модель отметки**

`app/models/team_onboarding_mark.py`:
```python
"""Отметка шага «Первые шаги» для команды."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class TeamOnboardingMark(Base, TimestampMixin):
    """Шаг настройки команды закрыт: выполнен или пропущен.

    Строка на (команда, шаг). Авто-шаг получает строку ``source=auto`` в момент,
    когда условие впервые выполнилось, и дальше не пересчитывается — новые
    задачи не должны перекрашивать пройденный шаг. Нет строки — шаг не закрыт.
    """

    __tablename__ = "team_onboarding_marks"
    __table_args__ = (UniqueConstraint("team", "step", name="uq_team_onboarding_mark"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)  # done | skipped
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # auto | manual
    marked_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    marked_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
```

- [ ] **Step 2: Регистрация**

В `app/models/__init__.py` рядом со строкой `from app.models.team import Team, TeamSubgroup  # noqa: F401` добавить:
```python
from app.models.team_onboarding_mark import TeamOnboardingMark  # noqa: F401
```
и `"TeamOnboardingMark",` в `__all__` рядом с `"Team",`.

- [ ] **Step 3: Поле пользователя**

В `app/models/user.py` после `team_desk_filter_raw` добавить колонку:
```python
    onboarding_raw: Mapped[str] = mapped_column(
        "onboarding", Text, nullable=False, default="{}", server_default="{}"
    )
```
и в конец класса свойство (по образцу `team_desk_filter`):
```python
    @property
    def onboarding(self) -> dict:
        try:
            return json.loads(self.onboarding_raw or "{}")
        except (TypeError, ValueError):
            return {}

    @onboarding.setter
    def onboarding(self, value: dict) -> None:
        self.onboarding_raw = json.dumps(value or {}, ensure_ascii=False)
```

- [ ] **Step 4: Миграция**

`alembic/versions/ob01_onboarding.py`:
```python
"""«Первые шаги»: отметки шагов команды и личное состояние пользователя

Revision ID: ob01_onboarding
Revises: pq07_assignment_opo_part
Create Date: 2026-09-28

Таблица могла быть создана раньше (create_all в тестах на локальной базе) —
создаётся только если её нет. Самодостаточна: не импортирует код приложения.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ob01_onboarding"
down_revision: Union[str, None] = "pq07_assignment_opo_part"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "team_onboarding_marks" not in inspector.get_table_names():
        op.create_table(
            "team_onboarding_marks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("team", sa.String(length=200), nullable=False),
            sa.Column("step", sa.String(length=50), nullable=False),
            sa.Column("state", sa.String(length=16), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column("marked_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("marked_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["marked_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("team", "step", name="uq_team_onboarding_mark"),
        )
        op.create_index("ix_team_onboarding_marks_team", "team_onboarding_marks", ["team"])

    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "onboarding" not in user_cols:
        with op.batch_alter_table("users") as batch:
            batch.add_column(
                sa.Column("onboarding", sa.Text(), nullable=False, server_default="{}")
            )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("onboarding")
    op.drop_index("ix_team_onboarding_marks_team", table_name="team_onboarding_marks")
    op.drop_table("team_onboarding_marks")
```

> При влитии в main: параллельная ветка добавляет свои миграции после `pq07` — перед влитием поменять `down_revision` на актуальную голову (`alembic heads` должен показать одну).

- [ ] **Step 5: Проверить миграцию на копии базы**

Run: `py -3.10 -c "from app.models import TeamOnboardingMark, User; print('ok')"` → `ok`.
Run (SQLite во временном файле): `$env:DATABASE_URL="sqlite:///./data/ob01_check.db"; alembic upgrade head; alembic downgrade -1; alembic upgrade head; Remove-Item data/ob01_check.db` (PowerShell) — без ошибок.

- [ ] **Step 6: Commit**

```bash
git add app/models/team_onboarding_mark.py app/models/__init__.py app/models/user.py alembic/versions/ob01_onboarding.py
git commit -m "feat(onboarding): отметки шагов команды и личное состояние"
```

---

### Task 2: Сервис статуса + эндпоинты (TDD)

**Files:**
- Create: `tests/api/test_onboarding.py`
- Create: `app/services/onboarding_service.py`
- Create: `app/api/endpoints/onboarding.py`
- Modify: `app/api/router.py`

Условия авто-шагов (из спеки):
- `issues_loaded`: сумма счётчиков `get_tree_counts` > 0.
- `categorization`: `total > 0 and stack / total <= 0.10`.
- `team_roles`: активные участники на сегодня (`team_membership.members_on` + `Employee.is_active`), ≥1 и у всех непустая `Employee.role`.
- `backlog`: неархивная инициатива команды (`Issue.team == team`, либо ручная идея `issue_id IS NULL and BacklogItem.team == team`) с оценкой > 0 хоть по одному из `estimate_hours, estimate_analyst_hours, estimate_dev_hours, estimate_qa_hours, estimate_opo_hours`.
- `scenario_created`: есть `PlanningScenario.team == team`.
- `resource_plan`: есть `ResourcePlan.team == team and computed_at IS NOT NULL`.
Ручные: `absences`, `scenario_rules`, `scenario_involvement`.

- [ ] **Step 1: Тесты**

`tests/api/test_onboarding.py`:
```python
"""«Первые шаги»: статус шагов команды, защёлка, ручные отметки, личное состояние."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    Issue,
    PlanningScenario,
    Project,
    ResourcePlan,
    TeamOnboardingMark,
)

TEAM = "Команда А"


@pytest.fixture
def client(testclient_db_session):
    def _get_db():
        yield testclient_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app), testclient_db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


def _status(tc, team=TEAM):
    resp = tc.get("/api/v1/onboarding/status", params={"team": team})
    assert resp.status_code == 200
    return resp.json()


def _project(db):
    p = Project(id="prj-ob", jira_id="10001", key="OB", name="OB")
    db.add(p)
    db.commit()
    return p


def _issue(db, n, *, verified=False, category=None, team=TEAM):
    i = Issue(
        id=f"iss-ob-{n}", jira_id=f"20{n:03d}", key=f"OB-{n}", summary=f"Задача {n}",
        project_id="prj-ob", team=team, category_verified=verified, assigned_category=category,
    )
    db.add(i)
    db.commit()
    return i


def test_empty_team_all_pending(client):
    tc, _ = client
    data = _status(tc)
    assert data["team"] == TEAM
    assert set(data["steps"]) == {
        "issues_loaded", "categorization", "team_roles", "absences", "backlog",
        "scenario_created", "scenario_rules", "scenario_involvement", "resource_plan",
    }
    assert all(s["state"] == "pending" for s in data["steps"].values())


def test_no_team_no_steps(client):
    tc, _ = client
    resp = tc.get("/api/v1/onboarding/status")
    assert resp.status_code == 200
    assert resp.json()["steps"] == {}


def test_issues_and_categorization(client):
    tc, db = client
    _project(db)
    for n in range(1, 10):
        _issue(db, n, verified=True, category="support")
    _issue(db, 10)  # одна неразобранная из десяти — ровно порог 10%

    steps = _status(tc)["steps"]
    assert steps["issues_loaded"]["state"] == "done"
    assert steps["issues_loaded"]["source"] == "auto"
    assert steps["categorization"]["state"] == "done"


def test_categorization_above_threshold_pending(client):
    tc, db = client
    _project(db)
    for n in range(1, 9):
        _issue(db, n, verified=True, category="support")
    _issue(db, 9)
    _issue(db, 10)  # 20% неразобранных

    assert _status(tc)["steps"]["categorization"]["state"] == "pending"


def test_latch_survives_data_removal(client):
    tc, db = client
    _project(db)
    _issue(db, 1, verified=True, category="support")
    assert _status(tc)["steps"]["issues_loaded"]["state"] == "done"

    db.query(Issue).delete()
    db.commit()
    assert _status(tc)["steps"]["issues_loaded"]["state"] == "done"


def test_team_roles(client):
    tc, db = client
    db.add_all([
        Employee(id="emp-ob-1", jira_account_id="j-ob-1", display_name="Иванов", is_active=True, role="dev"),
        Employee(id="emp-ob-2", jira_account_id="j-ob-2", display_name="Петров", is_active=True, role=None),
        EmployeeTeam(employee_id="emp-ob-1", team=TEAM, is_primary=True),
        EmployeeTeam(employee_id="emp-ob-2", team=TEAM, is_primary=True),
    ])
    db.commit()
    assert _status(tc)["steps"]["team_roles"]["state"] == "pending"

    db.get(Employee, "emp-ob-2").role = "qa"
    db.commit()
    assert _status(tc)["steps"]["team_roles"]["state"] == "done"


def test_team_roles_ignores_left_and_inactive(client):
    tc, db = client
    db.add_all([
        Employee(id="emp-ob-1", jira_account_id="j-ob-1", display_name="Иванов", is_active=True, role="dev"),
        Employee(id="emp-ob-2", jira_account_id="j-ob-2", display_name="Выбыл", is_active=True, role=None),
        Employee(id="emp-ob-3", jira_account_id="j-ob-3", display_name="Выключен", is_active=False, role=None),
        EmployeeTeam(employee_id="emp-ob-1", team=TEAM, is_primary=True),
        EmployeeTeam(employee_id="emp-ob-2", team=TEAM, is_primary=True, left_at=date(2020, 1, 1)),
        EmployeeTeam(employee_id="emp-ob-3", team=TEAM, is_primary=True),
    ])
    db.commit()
    assert _status(tc)["steps"]["team_roles"]["state"] == "done"


def test_backlog_needs_estimate(client):
    tc, db = client
    db.add(BacklogItem(id="bl-ob-1", title="Идея", team=TEAM))
    db.commit()
    assert _status(tc)["steps"]["backlog"]["state"] == "pending"

    db.get(BacklogItem, "bl-ob-1").estimate_dev_hours = 40
    db.commit()
    assert _status(tc)["steps"]["backlog"]["state"] == "done"


def test_backlog_archived_not_counted(client):
    tc, db = client
    db.add(BacklogItem(id="bl-ob-1", title="Идея", team=TEAM, estimate_dev_hours=40,
                       archived_at=datetime(2026, 1, 1)))
    db.commit()
    assert _status(tc)["steps"]["backlog"]["state"] == "pending"


def test_scenario_and_resource_plan(client):
    tc, db = client
    db.add(PlanningScenario(id="sc-ob-1", name="2026 Q4", team=TEAM, quarter="Q4", year=2026))
    db.add(ResourcePlan(id="rp-ob-1", name="План", team=TEAM, quarter="Q4", year=2026))
    db.commit()
    steps = _status(tc)["steps"]
    assert steps["scenario_created"]["state"] == "done"
    assert steps["resource_plan"]["state"] == "pending"

    db.get(ResourcePlan, "rp-ob-1").computed_at = datetime(2026, 9, 1)
    db.commit()
    assert _status(tc)["steps"]["resource_plan"]["state"] == "done"


def test_manual_mark_skip_and_reset(client):
    tc, _ = client
    resp = tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "done"})
    assert resp.status_code == 200
    step = _status(tc)["steps"]["absences"]
    assert step["state"] == "done"
    assert step["source"] == "manual"
    assert step["marked_by"] == "Test User"
    assert step["marked_at"]

    tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "pending"})
    assert _status(tc)["steps"]["absences"]["state"] == "pending"

    tc.put("/api/v1/onboarding/team-steps/backlog", json={"team": TEAM, "state": "skipped"})
    assert _status(tc)["steps"]["backlog"]["state"] == "skipped"


def test_auto_step_cannot_be_marked_done_manually(client):
    tc, _ = client
    resp = tc.put("/api/v1/onboarding/team-steps/backlog", json={"team": TEAM, "state": "done"})
    assert resp.status_code == 400


def test_unknown_step_404(client):
    tc, _ = client
    resp = tc.put("/api/v1/onboarding/team-steps/nope", json={"team": TEAM, "state": "done"})
    assert resp.status_code == 404


def test_marks_are_per_team(client):
    tc, _ = client
    tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "done"})
    assert _status(tc, "Команда Б")["steps"]["absences"]["state"] == "pending"


def test_me_partial_update(client):
    tc, _ = client
    assert _status(tc)["me"] == {"completed_tours": [], "auto_opened": False, "hidden": False}

    resp = tc.put("/api/v1/onboarding/me", json={"auto_opened": True})
    assert resp.status_code == 200
    resp = tc.put("/api/v1/onboarding/me", json={"completed_tours": ["dashboard"]})
    assert resp.json() == {"completed_tours": ["dashboard"], "auto_opened": True, "hidden": False}
    assert _status(tc)["me"]["completed_tours"] == ["dashboard"]


def test_latch_race_is_ignored(client):
    """Строка защёлки уже есть (записал параллельный запрос) — чтение не падает."""
    tc, db = client
    db.add(TeamOnboardingMark(team=TEAM, step="scenario_created", state="done", source="auto"))
    db.commit()
    assert _status(tc)["steps"]["scenario_created"]["state"] == "done"
```

Перед запуском сверить обязательные поля моделей `Project`, `Issue`, `BacklogItem`, `PlanningScenario`, `ResourcePlan` (`nullable=False` без default) и дописать недостающие в фабриках теста — имена полей часто отличаются от очевидных.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/api/test_onboarding.py -q`
Expected: FAIL — 404 на `/api/v1/onboarding/...`.

- [ ] **Step 3: Сервис**

`app/services/onboarding_service.py`:
```python
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
    names = (
        dict(db.query(User.id, User.display_name).filter(User.id.in_(user_ids)).all())
        if user_ids else {}
    )
    result: dict[str, dict] = {}
    for step in ALL_STEPS:
        m = marks.get(step)
        result[step] = {
            "state": m.state if m else "pending",
            "source": m.source if m else None,
            "marked_by": names.get(m.marked_by_user_id) if m else None,
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
```

Если `ScopeProject` не экспортируется из `app.models` — импортировать из `app.models.scope_project`.

- [ ] **Step 4: Эндпоинты**

`app/api/endpoints/onboarding.py`:
```python
"""«Первые шаги»: статус шагов команды и личное состояние пользователя."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models import User
from app.services import onboarding_service as svc

router = APIRouter()


class StepStatePayload(BaseModel):
    team: str
    state: Literal["done", "skipped", "pending"]


class MePayload(BaseModel):
    completed_tours: Optional[list[str]] = None
    auto_opened: Optional[bool] = None
    hidden: Optional[bool] = None


@router.get("/status")
def get_status(
    team: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = svc.me_state(current_user)
    steps = svc.team_steps(db, team) if team else {}
    return {"team": team, "steps": steps, "me": me}


@router.put("/team-steps/{step}")
def put_team_step(
    step: str,
    payload: StepStatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if step not in svc.ALL_STEPS:
        raise HTTPException(status_code=404, detail="Неизвестный шаг")
    if payload.state == "done" and step not in svc.MANUAL_STEPS:
        raise HTTPException(status_code=400, detail="Этот шаг отмечается автоматически")
    user_id = current_user.id
    svc.set_team_step(db, payload.team, step, payload.state, user_id)
    return {"ok": True}


@router.put("/me")
def put_me(
    payload: MePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.get(User, current_user.id) or current_user
    state = svc.me_state(user)
    state.update(payload.model_dump(exclude_none=True))
    user.onboarding = state
    db.commit()
    return state
```

- [ ] **Step 5: Подключить роутер**

В `app/api/router.py`: в импорт `from app.api.endpoints import (...)` добавить `onboarding as onboarding_endpoints,` (по алфавиту), и рядом с остальными `include_router` для авторизованных роутеров:
```python
api_router.include_router(
    onboarding_endpoints.router, prefix="/onboarding", tags=["onboarding"], dependencies=_auth_dep
)
```

- [ ] **Step 6: Тесты зелёные**

Run: `py -3.10 -m pytest tests/api/test_onboarding.py -q` → все PASS.
Run: `ruff check app/ tests/ && mypy app/` → без ошибок.

- [ ] **Step 7: Commit**

```bash
git add app/services/onboarding_service.py app/api/endpoints/onboarding.py app/api/router.py tests/api/test_onboarding.py
git commit -m "feat(onboarding): статус шагов команды с защёлкой и ручные отметки"
```

---

### Task 3: Фронт — API, конфигурация шагов, провайдер, запуск экскурсий

**Files:**
- Create: `frontend/src/api/onboarding.ts`
- Create: `frontend/src/onboarding/steps.ts`
- Create: `frontend/src/onboarding/tours.ts` (здесь — только типы и пустой `TOURS`; содержимое — Task 5)
- Create: `frontend/src/onboarding/OnboardingContext.tsx`
- Create: `frontend/src/onboarding/TourRunner.tsx`

- [ ] **Step 1: API**

`frontend/src/api/onboarding.ts`:
```ts
import { api } from './client';

export type StepState = 'done' | 'skipped' | 'pending';

export interface StepStatus {
  state: StepState;
  source: 'auto' | 'manual' | null;
  marked_by: string | null;
  marked_at: string | null;
}

export interface OnboardingMe {
  completed_tours: string[];
  auto_opened: boolean;
  hidden: boolean;
}

export interface OnboardingStatus {
  team: string | null;
  steps: Record<string, StepStatus>;
  me: OnboardingMe;
}

export const getOnboardingStatus = (team: string | null) =>
  api.get<OnboardingStatus>('/onboarding/status', { team: team ?? undefined });

export const putTeamStep = (step: string, team: string, state: StepState) =>
  api.put<{ ok: boolean }>(`/onboarding/team-steps/${step}`, { team, state });

export const putOnboardingMe = (data: Partial<OnboardingMe>) =>
  api.put<OnboardingMe>('/onboarding/me', data);
```

- [ ] **Step 2: Шаги**

`frontend/src/onboarding/steps.ts`:
```ts
import type { OnboardingStatus } from '../api/onboarding';

export interface SetupStep {
  /** id шага на сервере; у группы — свой id, на сервере его нет. */
  id: string;
  title: string;
  hint: string;
  /** Куда ведёт «Перейти». */
  route?: string;
  /** Какую экскурсию запускает «Показать». */
  tourId?: string;
  /** Ручной шаг отмечается кнопкой «Проверил». */
  manual?: boolean;
  /** Подпункты: шаг закрыт, когда закрыты все. */
  children?: SetupStep[];
}

export interface IntroStep {
  tourId: string;
  title: string;
  hint: string;
}

export const SETUP_STEPS: SetupStep[] = [
  {
    id: 'issues_loaded',
    title: 'Задачи команды загружены из Jira',
    hint: 'Синхронизация общая и идёт по расписанию. Если задач команды нет — обратитесь к администратору.',
    route: '/sync',
  },
  {
    id: 'categorization',
    title: 'Категоризация задач',
    hint: 'Разберите задачи команды по категориям: от категории зависит, куда пойдут часы в отчётах и что попадёт в целевые задачи. Шаг выполнен, когда неразобранных осталось не больше 10%.',
    route: '/categories',
    tourId: 'categories',
  },
  {
    id: 'team_roles',
    title: 'Состав команды и роли',
    hint: 'Проверьте участников и заполните роль у каждого — от роли зависят сценарии и правила загрузки. Дата вступления в команду — в карточке сотрудника.',
    route: '/capacity',
    tourId: 'capacity-team',
  },
  {
    id: 'absences',
    title: 'Отсутствия',
    hint: 'Внесите отпуска, больничные и обучение на квартал. Сервис не отличит «отпусков нет» от «не внесли», поэтому отметьте шаг сами.',
    route: '/capacity',
    tourId: 'capacity-absences',
    manual: true,
  },
  {
    id: 'backlog',
    title: 'Целевые задачи (бэклог)',
    hint: 'Наполняются автоматически из Jira — задачи, отнесённые при категоризации к «Инициативы (на потом)», — и вручную кнопкой «Идея вручную» для идей, которых ещё нет в Jira. Дальше: приоритеты, оценки по ролям, параметры планирования (шестерёнка).',
    route: '/backlog?view=active',
    tourId: 'backlog',
  },
  {
    id: 'scenario',
    title: 'Сценарий квартала',
    hint: 'Сценарий собирает инициативы квартала под ресурс команды.',
    route: '/planning',
    tourId: 'planning',
    children: [
      { id: 'scenario_created', title: 'Сценарий создан', hint: 'Кнопка «Новый сценарий».' },
      {
        id: 'scenario_rules',
        title: 'Нормированные работы проверены',
        hint: 'Вкладка «Правила»: доля времени ролей на сопровождение, встречи, техдолг.',
        manual: true,
      },
      {
        id: 'scenario_involvement',
        title: 'Вовлечённость проверена',
        hint: 'Кнопка «Вовлечённость»: значения по ролям на квартал.',
        manual: true,
      },
    ],
  },
  {
    id: 'resource_plan',
    title: 'Ресурсное планирование',
    hint: 'Выберите утверждённый сценарий и нажмите «Распределить»: сервис разложит фазы по исполнителям и дням.',
    route: '/resource-planning',
    tourId: 'resource-planning',
  },
];

export const INTRO_STEPS: IntroStep[] = [
  { tourId: 'header', title: 'Шапка: команда, период, справка', hint: 'Что настраивается один раз и действует во всех разделах.' },
  { tourId: 'dashboard', title: 'Дашборд', hint: 'Сводка команды за период.' },
  { tourId: 'analytics', title: 'Аналитика', hint: 'Отчёт по часам: команда → роль → сотрудник → категория → задача.' },
  { tourId: 'team-desk', title: 'Стол тимлида', hint: 'Задачи разработчиков: что зависло, что перерасходовано.' },
];

/** Шаг закрыт: выполнен или пропущен. Группа — когда закрыты все подпункты. */
export function isClosed(step: SetupStep, status: OnboardingStatus | undefined): boolean {
  if (step.children) return step.children.every(c => isClosed(c, status));
  const state = status?.steps[step.id]?.state;
  return state === 'done' || state === 'skipped';
}

/** Прогресс для кнопки в шапке: закрытые шаги верхнего уровня обоих блоков. */
export function progress(status: OnboardingStatus | undefined, hasTeam: boolean) {
  const tours = new Set(status?.me.completed_tours ?? []);
  const introDone = INTRO_STEPS.filter(s => tours.has(s.tourId)).length;
  const setupDone = hasTeam ? SETUP_STEPS.filter(s => isClosed(s, status)).length : 0;
  const total = INTRO_STEPS.length + (hasTeam ? SETUP_STEPS.length : 0);
  return { done: introDone + setupDone, total };
}
```

- [ ] **Step 3: Типы экскурсий**

`frontend/src/onboarding/tours.ts` (содержимое `TOURS` добавит Task 5):
```ts
export interface TourStepDef {
  /** Значение атрибута data-tour у элемента; null — окно по центру экрана. */
  target: string | null;
  title: string;
  description: string;
  /** data-tour элемента, по которому кликнуть перед шагом (переключить вкладку). */
  clickFirst?: string;
}

export interface TourDef {
  id: string;
  /** Куда перейти перед экскурсией; нет — остаться на текущей странице. */
  route?: string;
  steps: TourStepDef[];
}

export const TOURS: Record<string, TourDef> = {};
```

- [ ] **Step 4: Провайдер**

`frontend/src/onboarding/OnboardingContext.tsx`:
```tsx
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getOnboardingStatus, putOnboardingMe, putTeamStep,
  type OnboardingMe, type OnboardingStatus, type StepState,
} from '../api/onboarding';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useUnreadReleaseNotes } from '../hooks/useReleaseNotes';

interface OnboardingCtx {
  /** Команда, для которой показан блок настройки; null — в шапке команда не выбрана. */
  team: string | null;
  teamOptions: string[];
  setTeam: (team: string) => void;
  status: OnboardingStatus | undefined;
  panelOpen: boolean;
  openPanel: () => void;
  closePanel: () => void;
  activeTourId: string | null;
  startTour: (id: string) => void;
  endTour: (completed: boolean) => void;
  setStepState: (step: string, state: StepState) => Promise<void>;
  updateMe: (patch: Partial<OnboardingMe>) => Promise<void>;
}

const Ctx = createContext<OnboardingCtx | null>(null);

export function useOnboarding(): OnboardingCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('OnboardingProvider is not mounted');
  return ctx;
}

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { selectedTeams } = useGlobalTeamFilter();
  const [pickedTeam, setPickedTeam] = useState<string | null>(null);
  const team = pickedTeam && selectedTeams.includes(pickedTeam) ? pickedTeam : (selectedTeams[0] ?? null);

  const { data: status, refetch } = useQuery({
    queryKey: ['onboarding', team],
    queryFn: () => getOnboardingStatus(team),
    staleTime: 60_000,
  });

  const [panelOpen, setPanelOpen] = useState(false);
  const [activeTourId, setActiveTourId] = useState<string | null>(null);

  const updateMe = useCallback(async (patch: Partial<OnboardingMe>) => {
    const me = await putOnboardingMe(patch);
    qc.setQueriesData<OnboardingStatus>({ queryKey: ['onboarding'] }, old => (old ? { ...old, me } : old));
  }, [qc]);

  const openPanel = useCallback(() => {
    setPanelOpen(true);
    void refetch();
    if (status?.me.hidden) void updateMe({ hidden: false });
  }, [refetch, status?.me.hidden, updateMe]);

  const closePanel = useCallback(() => setPanelOpen(false), []);

  const startTour = useCallback((id: string) => {
    setPanelOpen(false);
    setActiveTourId(id);
  }, []);

  const endTour = useCallback((completed: boolean) => {
    const id = activeTourId;
    setActiveTourId(null);
    if (!completed || !id) return;
    const done = status?.me.completed_tours ?? [];
    if (!done.includes(id)) void updateMe({ completed_tours: [...done, id] });
  }, [activeTourId, status?.me.completed_tours, updateMe]);

  const setStepState = useCallback(async (step: string, state: StepState) => {
    if (!team) return;
    await putTeamStep(step, team, state);
    await qc.invalidateQueries({ queryKey: ['onboarding', team] });
  }, [qc, team]);

  // Автооткрытие один раз на пользователя. Ждём, пока закроют «Что нового»,
  // чтобы два окна не всплыли разом.
  const { data: unread } = useUnreadReleaseNotes();
  const whatsNewPending = !unread || unread.unread_versions.length > 0;
  useEffect(() => {
    if (!status || status.me.auto_opened || status.me.hidden || whatsNewPending) return;
    setPanelOpen(true);
    void updateMe({ auto_opened: true });
  }, [status, whatsNewPending, updateMe]);

  const value = useMemo<OnboardingCtx>(() => ({
    team, teamOptions: selectedTeams, setTeam: setPickedTeam, status,
    panelOpen, openPanel, closePanel, activeTourId, startTour, endTour, setStepState, updateMe,
  }), [team, selectedTeams, status, panelOpen, openPanel, closePanel, activeTourId, startTour, endTour, setStepState, updateMe]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
```
Если линтер запрещает `setState` внутри эффекта (правило React Compiler) — перенести автооткрытие в обработчик успеха запроса или в `useState`-инициализацию по образцу `WhatsNewGate.tsx`.

- [ ] **Step 5: Запуск экскурсий**

`frontend/src/onboarding/TourRunner.tsx`:
```tsx
import { useEffect, useRef, useState } from 'react';
import { Tour } from 'antd';
import { useLocation, useNavigate } from 'react-router';
import { TOURS, type TourStepDef } from './tours';
import { useOnboarding } from './OnboardingContext';

/** Видимый элемент с атрибутом data-tour. AntD держит скрытые вкладки в DOM — берём видимый. */
export function findTourTarget(id: string): HTMLElement | null {
  const nodes = document.querySelectorAll<HTMLElement>(`[data-tour="${id}"]`);
  for (const el of nodes) if (el.getClientRects().length > 0) return el;
  return null;
}

// ponytail: опрос раз в 150 мс; MutationObserver — если опрос окажется заметен
async function waitForTarget(id: string, timeoutMs = 5000): Promise<HTMLElement | null> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const el = findTourTarget(id);
    if (el) return el;
    await new Promise(r => setTimeout(r, 150));
  }
  return null;
}

/** Подготовить шаг: переключить вкладку и дождаться цели. Цели нет — шаг покажется по центру. */
async function prepareStep(step: TourStepDef): Promise<void> {
  if (step.clickFirst) {
    const tab = await waitForTarget(step.clickFirst);
    tab?.click();
  }
  if (step.target) await waitForTarget(step.target);
}

export default function TourRunner() {
  const { activeTourId, endTour } = useOnboarding();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(0);
  // Номер запуска: экскурсию закрыли, пока ждали цель, — не открывать её.
  const runRef = useRef(0);
  const tour = activeTourId ? TOURS[activeTourId] : undefined;
  const here = location.pathname + location.search;

  useEffect(() => {
    if (!tour) {
      setOpen(false);
      return;
    }
    const run = ++runRef.current;
    if (tour.route && here !== tour.route) navigate(tour.route);
    void prepareStep(tour.steps[0]).then(() => {
      if (runRef.current !== run) return;
      setCurrent(0);
      setOpen(true);
    });
    // Адрес сравнивается только в момент старта экскурсии.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tour, navigate]);

  if (!tour) return null;

  const handleChange = (next: number) => {
    const run = runRef.current;
    void prepareStep(tour.steps[next]).then(() => {
      if (runRef.current === run) setCurrent(next);
    });
  };

  const last = tour.steps.length - 1;
  return (
    <Tour
      open={open}
      current={current}
      onChange={handleChange}
      onClose={() => { runRef.current++; endTour(false); }}
      onFinish={() => { runRef.current++; endTour(true); }}
      steps={tour.steps.map((s, i) => ({
        title: s.title,
        description: s.description,
        target: s.target ? () => findTourTarget(s.target as string) : null,
        nextButtonProps: { children: i === last ? 'Готово' : 'Далее' },
        prevButtonProps: { children: 'Назад' },
      }))}
    />
  );
}
```
Сверить с `frontend/eslint.config.*`: если правило `react-hooks/exhaustive-deps` не подключено — убрать комментарий-отключение. Проверить в браузере: в AntD 6 `onFinish` не должен сопровождаться `onClose` (иначе отметка «пройдено» потеряется — тогда ставить отметку до `endTour(false)`).

- [ ] **Step 6: Проверка**

Run: `cd frontend; npm run lint; npm run build` → без ошибок и предупреждений.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/onboarding.ts frontend/src/onboarding
git commit -m "feat(onboarding): провайдер первых шагов и запуск экскурсий"
```

---

### Task 4: Фронт — панель, кнопка в шапке, вход из справки

**Files:**
- Create: `frontend/src/onboarding/OnboardingDrawer.tsx`
- Create: `frontend/src/onboarding/OnboardingButton.tsx`
- Modify: `frontend/src/components/Layout/AppLayout.tsx`
- Modify: `frontend/src/aurora/shell/AuroraTopbar.tsx`
- Modify: `frontend/src/components/shared/HelpDrawer.tsx`
- Modify: `frontend/src/components/Layout/GlobalHelpButton.tsx`

- [ ] **Step 1: Панель**

`frontend/src/onboarding/OnboardingDrawer.tsx`:
```tsx
import { useState } from 'react';
import { Alert, Button, Drawer, Progress, Select, Space, Typography } from 'antd';
import { CheckCircleFilled, MinusCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router';
import dayjs from 'dayjs';
import { useOnboarding } from './OnboardingContext';
import { INTRO_STEPS, SETUP_STEPS, isClosed, type SetupStep } from './steps';

type RowState = 'done' | 'skipped' | 'pending';

function StatusIcon({ state, index }: { state: RowState; index?: number }) {
  if (state === 'done') return <CheckCircleFilled style={{ color: '#52c41a', fontSize: 18 }} />;
  if (state === 'skipped') return <MinusCircleOutlined style={{ color: 'var(--text-3)', fontSize: 18 }} />;
  return (
    <span style={{
      display: 'inline-grid', placeItems: 'center', width: 18, height: 18, borderRadius: '50%',
      border: '1px solid var(--text-3)', fontSize: 11, color: 'var(--text-2)',
    }}>{index ?? ''}</span>
  );
}

function StepRow({ step, index, nested }: { step: SetupStep; index?: number; nested?: boolean }) {
  const { status, startTour, closePanel, setStepState } = useOnboarding();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const closed = isClosed(step, status);
  const own = step.children ? undefined : status?.steps[step.id];
  const state: RowState = step.children ? (closed ? 'done' : 'pending') : (own?.state ?? 'pending');

  const act = async (next: RowState) => {
    setBusy(true);
    try { await setStepState(step.id, next); } finally { setBusy(false); }
  };

  const note = own && own.state !== 'pending' && own.marked_at
    ? own.source === 'auto'
      ? `Выполнено автоматически · ${dayjs(own.marked_at).format('DD.MM.YYYY')}`
      : `${own.state === 'skipped' ? 'Пропущено' : 'Отмечено'}: ${own.marked_by ?? '—'}, ${dayjs(own.marked_at).format('DD.MM.YYYY')}`
    : null;

  return (
    <div style={{ display: 'flex', gap: 10, padding: nested ? '6px 0' : '10px 0' }} data-testid={`onboarding-step-${step.id}`}>
      <div style={{ paddingTop: 2 }}><StatusIcon state={state} index={index} /></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <Typography.Text strong={!nested} delete={state === 'skipped'}>{step.title}</Typography.Text>
        {!closed && <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{step.hint}</Typography.Text></div>}
        {note && <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{note}</Typography.Text></div>}
        <Space size={4} wrap style={{ marginTop: 6 }}>
          {step.tourId && (
            <Button size="small" type="primary" ghost onClick={() => startTour(step.tourId as string)} data-testid={`tour-start-${step.tourId}`}>
              Показать
            </Button>
          )}
          {step.route && (
            <Button size="small" onClick={() => { closePanel(); navigate(step.route as string); }}>Перейти</Button>
          )}
          {!step.children && state === 'pending' && step.manual && (
            <Button size="small" loading={busy} onClick={() => act('done')}>Проверил</Button>
          )}
          {!step.children && state === 'pending' && (
            <Button size="small" type="text" loading={busy} onClick={() => act('skipped')}>Пропустить</Button>
          )}
          {!step.children && (state === 'skipped' || (state === 'done' && own?.source === 'manual')) && (
            <Button size="small" type="text" loading={busy} onClick={() => act('pending')}>Вернуть</Button>
          )}
        </Space>
        {step.children?.map(c => <StepRow key={c.id} step={c} nested />)}
      </div>
    </div>
  );
}

export default function OnboardingDrawer() {
  const { team, teamOptions, setTeam, status, panelOpen, closePanel, startTour, updateMe } = useOnboarding();
  const [showDoneSetup, setShowDoneSetup] = useState(false);
  const tours = new Set(status?.me.completed_tours ?? []);
  const setupDone = SETUP_STEPS.filter(s => isClosed(s, status)).length;
  const setupComplete = setupDone === SETUP_STEPS.length;

  return (
    <Drawer
      title="Первые шаги"
      open={panelOpen}
      onClose={closePanel}
      placement="right"
      styles={{ wrapper: { width: 'min(520px, 92vw)' } }}
      footer={
        <Button type="link" size="small" onClick={() => { void updateMe({ hidden: true }); closePanel(); }}>
          Больше не показывать (вернуть — кнопкой «Первые шаги» в справке)
        </Button>
      }
    >
      <Typography.Title level={5} style={{ marginTop: 0 }}>Настройка команды</Typography.Title>
      {teamOptions.length === 0 && (
        <Alert type="info" showIcon title="Выберите команду в шапке, чтобы увидеть шаги её настройки." />
      )}
      {teamOptions.length > 1 && (
        <Select
          value={team ?? undefined}
          onChange={setTeam}
          options={teamOptions.map(t => ({ value: t, label: t }))}
          style={{ width: '100%', marginBottom: 8 }}
        />
      )}
      {team && (
        <>
          <Progress
            percent={Math.round((setupDone / SETUP_STEPS.length) * 100)}
            format={() => `${setupDone} из ${SETUP_STEPS.length}`}
          />
          {setupComplete && !showDoneSetup ? (
            <div style={{ padding: '8px 0' }}>
              <Typography.Text>Команда настроена.</Typography.Text>{' '}
              <Button type="link" size="small" onClick={() => setShowDoneSetup(true)}>Показать шаги</Button>
            </div>
          ) : (
            SETUP_STEPS.map((s, i) => <StepRow key={s.id} step={s} index={i + 1} />)
          )}
        </>
      )}

      <Typography.Title level={5} style={{ marginTop: 24 }}>Знакомство с сервисом</Typography.Title>
      {INTRO_STEPS.map(s => (
        <div key={s.tourId} style={{ display: 'flex', gap: 10, padding: '10px 0' }}>
          <div style={{ paddingTop: 2 }}><StatusIcon state={tours.has(s.tourId) ? 'done' : 'pending'} /></div>
          <div style={{ flex: 1 }}>
            <Typography.Text strong>{s.title}</Typography.Text>
            <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{s.hint}</Typography.Text></div>
            <Button size="small" type="primary" ghost style={{ marginTop: 6 }} onClick={() => startTour(s.tourId)} data-testid={`tour-start-${s.tourId}`}>
              {tours.has(s.tourId) ? 'Показать ещё раз' : 'Показать'}
            </Button>
          </div>
        </div>
      ))}
    </Drawer>
  );
}
```
`Alert` в AntD 6.3: сверить по `node_modules/antd/es/alert/Alert.d.ts`, называется ли проп текста `title` или `message` (у `notification` — `title`, память проекта); взять неустаревший.

- [ ] **Step 2: Кнопка в шапке**

`frontend/src/onboarding/OnboardingButton.tsx`:
```tsx
import { Button } from 'antd';
import { FlagOutlined } from '@ant-design/icons';
import { useOnboarding } from './OnboardingContext';
import { progress } from './steps';

export default function OnboardingButton() {
  const { status, team, openPanel } = useOnboarding();
  if (!status || status.me.hidden) return null;
  const { done, total } = progress(status, team !== null);
  if (done >= total) return null;
  return (
    <Button
      type="text"
      size="small"
      icon={<FlagOutlined />}
      onClick={openPanel}
      title="Первые шаги"
      aria-label="Первые шаги"
      data-testid="onboarding-button"
      data-tour="header-onboarding"
      style={{ color: 'rgba(255,255,255,0.55)' }}
    >
      {done}/{total}
    </Button>
  );
}
```
Цвет — как у соседней кнопки справки (`GlobalHelpButton.tsx`); если та в светлой теме берёт другой цвет — взять тот же источник.

- [ ] **Step 3: Подключить в оболочку**

`frontend/src/components/Layout/AppLayout.tsx` — провайдер выше `AuroraShell` (оболочка пересоздаётся при смене темы, состояние экскурсии не должно теряться):
```tsx
import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import { OnboardingProvider } from '../../onboarding/OnboardingContext';
import OnboardingDrawer from '../../onboarding/OnboardingDrawer';
import TourRunner from '../../onboarding/TourRunner';

export default function AppLayout() {
  const { mode } = useAppTheme();
  // key на режиме форсит полный ремоунт при переключении тёмная↔светлая,
  // чтобы инлайновые стили (цвета через Proxy DARK_THEME) перечитали токены.
  return (
    <OnboardingProvider>
      <AuroraShell key={`aurora-${mode}`} />
      <OnboardingDrawer />
      <TourRunner />
    </OnboardingProvider>
  );
}
```
`AppLayout` рендерится внутри `AuthLayout` (`routes.tsx`), который оборачивает всё в `GlobalTeamFilterProvider` (`components/routing/RouteGuards.tsx:11`) — фильтр команд доступен. Проверить, что `AppLayout` не рендерится без вошедшего пользователя (иначе запрос статуса уйдёт без авторизации) — если рендерится, в провайдере включить запрос только при `useAuth().user`.

`frontend/src/aurora/shell/AuroraTopbar.tsx`: импорт `import OnboardingButton from '../../onboarding/OnboardingButton';`; метки для экскурсии «Шапка» и кнопка перед справкой:
```tsx
            <span data-tour="header-team"><GlobalTeamFilterButton /></span>
            <span data-tour="header-period"><GlobalPeriodPicker /></span>
            <OnboardingButton />
            <span data-tour="header-help"><GlobalHelpButton /></span>
```
Если обёртка `span` сбивает выравнивание в шапке — `style={{ display: 'inline-flex' }}`.

- [ ] **Step 4: Вход из справки**

`frontend/src/components/shared/HelpDrawer.tsx`: в `Props` добавить
```ts
  /** Элемент в шапке панели справа от заголовка. */
  extra?: ReactNode;
```
принять `extra` в параметрах компонента и передать `<Drawer extra={extra} ...>`.

`frontend/src/components/Layout/GlobalHelpButton.tsx`: `import { useOnboarding } from '../../onboarding/OnboardingContext';`, в компоненте `const { openPanel } = useOnboarding();`, в `<HelpDrawer ...>`:
```tsx
        extra={
          <Button size="small" onClick={() => { setOpen(false); openPanel(); }}>
            Первые шаги
          </Button>
        }
```
Страница входа использует `HelpDrawer` без `extra` — не меняется.

- [ ] **Step 5: Проверка** — `cd frontend; npm run lint; npm run build` → чисто.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/onboarding frontend/src/components/Layout/AppLayout.tsx frontend/src/aurora/shell/AuroraTopbar.tsx frontend/src/components/shared/HelpDrawer.tsx frontend/src/components/Layout/GlobalHelpButton.tsx
git commit -m "feat(onboarding): панель «Первые шаги» и кнопка в шапке"
```

---

### Task 5: Экскурсии — метки на страницах и тексты

**Files:**
- Modify: `frontend/src/onboarding/tours.ts` — заполнить `TOURS`.
- Modify (только атрибуты `data-tour`, поведение не меняется): `pages/CategoriesEditorPage.tsx`, `pages/CapacityPage.tsx`, `pages/BacklogPage.tsx`, `pages/PlanningPage.tsx`, `components/planning/PlanningCapacityPanel.tsx`, `pages/ResourcePlanningPage.tsx`, `components/resource-planning/GanttChart.tsx`, `pages/DashboardPage.tsx`, `pages/AnalyticsPage.tsx`, `pages/TeamDeskPage.tsx`.

Где ставить метки (строки — на момент разведки, сверять по коду). Элементы AntD (`Button`, `Select`, `Space`, `Card`, `Col`, `Tabs`, `Switch`, `Tag`) пробрасывают `data-*` в DOM. Заголовок колонки таблицы — `onHeaderCell: () => ({ 'data-tour': 'x' })`. Вкладка — `label` узлом: `label: <span data-tour="x">Отсутствия</span>`. Если компонент атрибут не пробрасывает — обернуть в `<div data-tour="...">`.

| data-tour | Файл:строка | Элемент |
|---|---|---|
| `categories-waiting` | CategoriesEditorPage.tsx:1029 | Tag «N ждут разбора» |
| `categories-queues` | CategoriesEditorPage.tsx:1034 | div `.category-queue-summary` |
| `categories-table` | CategoriesEditorPage.tsx:1106 | div `.category-table-wrap` |
| `categories-col-category` | CategoriesEditorPage.tsx:776 / 918-921 | заголовок колонки «Категория»; map на 918-921 переписывает `onHeaderCell` всем колонкам — атрибут добавлять внутри него |
| `categories-bulk` | CategoriesEditorPage.tsx:1097 | «Категория для отмеченных» |
| `capacity-tab-team`, `capacity-tab-absences` | CapacityPage.tsx:810-811 | подписи вкладок |
| `capacity-toolbar` | CapacityPage.tsx:404 | Space с фильтрами |
| `capacity-add-employee` | CapacityPage.tsx:423 | «Добавить сотрудника» |
| `capacity-role` | CapacityPage.tsx:282 | Select роли в строке |
| `capacity-team-table` | CapacityPage.tsx:444 | Table команды |
| `capacity-absence-heatmap` | CapacityPage.tsx:584 | тепловая карта (обернуть в div) |
| `capacity-absence-bulk` | CapacityPage.tsx:591 | «Массовое добавление» |
| `capacity-absence-table` | CapacityPage.tsx:604 | Table отсутствий |
| `backlog-tabs` | BacklogPage.tsx:1168 | Tabs |
| `backlog-manual-idea` | BacklogPage.tsx:1139 | «Идея вручную» |
| `backlog-col-prio` | BacklogPage.tsx:327 | заголовок колонки приоритета |
| `backlog-col-roles` | BacklogPage.tsx:543 | заголовок колонки оценок по ролям |
| `backlog-gear` | BacklogPage.tsx:752, 891, 813 | шестерёнка в строке (все три вида) |
| `backlog-col-inplan` | BacklogPage.tsx:827 | заголовок колонки «В план» |
| `planning-scenario-select` | PlanningPage.tsx:651 | Select сценария |
| `planning-involvement` | PlanningPage.tsx:666 | «Вовлечённость» |
| `planning-new-scenario` | PlanningPage.tsx:670 | «Новый сценарий» |
| `planning-tab-rules` | PlanningPage.tsx:854 | div вкладки правил (`data-tour={\`planning-tab-${key}\`}` с ключом, который означает правила) |
| `planning-rules-card` | PlanningPage.tsx:1004 | Card «Правила обязательных работ» |
| `planning-capacity-panel` | PlanningCapacityPanel.tsx:388 | корень панели «Ресурс команды» |
| `planning-approve` | PlanningPage.tsx:752 | «Утвердить» |
| `rp-scenario-select` | ResourcePlanningPage.tsx:343 | Select сценария |
| `rp-distribute` | ResourcePlanningPage.tsx:356 | «Распределить» |
| `rp-view` | ResourcePlanningPage.tsx:494 | «Вид» |
| `rp-gantt` | GanttChart.tsx:249 | div-карточка диаграммы |
| `rp-load` | ResourcePlanningPage.tsx:601 | «Загрузка по дням» (обернуть в div) |
| `dash-projects`, `dash-normed`, `dash-worklogs`, `dash-balance` | DashboardPage.tsx:30, 36, 42, 48 | `Col` виджетов |
| `analytics-period` | AnalyticsPage.tsx:118 | RangePicker |
| `analytics-hierarchy` | AnalyticsPage.tsx:132 | Space «Иерархия» |
| `analytics-settings` | AnalyticsPage.tsx:137 | «Настройка отчёта» |
| `analytics-filters` | AnalyticsPage.tsx:206 | фильтры (обернуть в div) |
| `analytics-table` | AnalyticsPage.tsx:210 | таблица (обернуть в div) |
| `desk-filters` | TeamDeskPage.tsx:275 | фильтры (обернуть в div) |
| `desk-tabs` | TeamDeskPage.tsx:310 | Tabs раскладок |
| `desk-flags` | TeamDeskPage.tsx:196 | div замечаний и статусов |
| `desk-issues` | TeamDeskPage.tsx:242 | список задач (обернуть в div) |

`ScenarioResourceSummary` не оборачивать (ломает прилипание) — в экскурсиях его нет.

- [ ] **Step 1: Метки** — расставить по таблице.

- [ ] **Step 2: Тексты экскурсий** — в `frontend/src/onboarding/tours.ts` заменить `export const TOURS: Record<string, TourDef> = {};` на:
```ts
const list: TourDef[] = [
  {
    id: 'categories',
    route: '/categories',
    steps: [
      { target: 'categories-waiting', title: 'Сколько ждёт разбора', description: 'Задачи команды без подтверждённой категории. Цель шага — оставить здесь не больше 10% задач.' },
      { target: 'categories-queues', title: 'Очереди', description: '«К разбору» — новые задачи из Jira. Остальные — уже разобранные: в работе, инициативы, архив. Клик переключает очередь.' },
      { target: 'categories-table', title: 'Дерево задач', description: 'Проект → эпик → задача. Категория эпика наследуется задачами ниже.' },
      { target: 'categories-col-category', title: 'Категория', description: 'Выберите категорию — она применится к задаче и её потомкам. Задачи для планирования квартала относите к «Инициативы (на потом)» — они сами появятся в целевых задачах.' },
      { target: 'categories-bulk', title: 'Сразу несколько', description: 'Отметьте строки галочками и назначьте категорию всем разом.' },
    ],
  },
  {
    id: 'capacity-team',
    route: '/capacity',
    steps: [
      { target: 'capacity-tab-team', clickFirst: 'capacity-tab-team', title: 'Вкладка «Команда»', description: 'Состав команды на выбранный квартал и загрузка каждого.' },
      { target: 'capacity-add-employee', title: 'Добавить сотрудника', description: 'Поиск по имени или почте в Jira.' },
      { target: 'capacity-role', title: 'Роль', description: 'У сотрудника одна роль. От неё зависят участие в сценариях и правила загрузки — заполните у каждого.' },
      { target: 'capacity-team-table', title: 'Карточка сотрудника', description: 'Клик по строке открывает карточку: дата вступления в команду («В команде с…») и участие в других командах.' },
      { target: 'capacity-toolbar', title: 'Фильтры', description: 'Поиск сотрудника, факт и проценты, выбывшие и выключенные.' },
    ],
  },
  {
    id: 'capacity-absences',
    route: '/capacity',
    steps: [
      { target: 'capacity-tab-absences', clickFirst: 'capacity-tab-absences', title: 'Вкладка «Отсутствия»', description: 'Отпуска, больничные, обучение — всё, что уменьшает ресурс команды.' },
      { target: 'capacity-absence-heatmap', title: 'Тепловая карта', description: 'Кто и когда отсутствует в квартале.' },
      { target: 'capacity-absence-bulk', title: 'Массовое добавление', description: 'Одно отсутствие сразу нескольким сотрудникам.' },
      { target: 'capacity-absence-table', title: 'По сотрудникам', description: 'В строке сотрудника — «добавить» отсутствие.' },
      { target: null, title: 'Готово?', description: 'Когда внесёте отсутствия на квартал — вернитесь в «Первые шаги» и нажмите «Проверил».' },
    ],
  },
  {
    id: 'backlog',
    route: '/backlog?view=active',
    steps: [
      { target: null, title: 'Откуда берутся целевые задачи', description: 'Автоматически из Jira — задачи, отнесённые при категоризации к «Инициативы (на потом)». И вручную — для идей, которых ещё нет в Jira.' },
      { target: 'backlog-tabs', title: 'Вкладки', description: '«Бэклог» — кандидаты на квартал. «Активные» — в работе или в утверждённом сценарии. «Архив» — отложенные и закрытые.' },
      { target: 'backlog-manual-idea', title: 'Идея вручную', description: 'Черновик без задачи в Jira. Когда задача появится — свяжите её с идеей.' },
      { target: 'backlog-col-prio', title: 'Приоритет', description: 'Меньше число — выше приоритет. В сценарии инициативы идут в этом порядке.' },
      { target: 'backlog-col-roles', title: 'Оценки по ролям', description: 'Часы анализа, разработки, тестирования и ОПЭ. Клик открывает редактор.' },
      { target: 'backlog-gear', title: 'Параметры планирования', description: 'Вовлечённость, длительность и параллельность по фазам — их использует ресурсное планирование.' },
      { target: 'backlog-col-inplan', title: '«В план»', description: 'Галочка включает инициативу в планирование.' },
    ],
  },
  {
    id: 'planning',
    route: '/planning',
    steps: [
      { target: 'planning-scenario-select', title: 'Сценарии команды', description: 'Сценарий — вариант плана квартала. Их может быть несколько, утверждается один.' },
      { target: 'planning-new-scenario', title: 'Новый сценарий', description: 'Квартал, год, команда. Нормированные работы копируются из шаблона.' },
      { target: 'planning-involvement', title: 'Вовлечённость', description: 'Значения по ролям на квартал для команды. Проверьте их и отметьте подпункт в «Первых шагах».' },
      { target: 'planning-tab-rules', clickFirst: 'planning-tab-rules', title: 'Нормированные работы', description: 'Вкладка «Правила»: сопровождение, встречи, техдолг — доля времени роли в процентах. Можно переопределить для конкретного сотрудника.' },
      { target: 'planning-rules-card', title: 'Правила сценария', description: 'Правка сразу пересчитывает ресурс под инициативы.' },
      { target: 'planning-capacity-panel', title: 'Ресурс команды', description: 'Доступно, нормированные работы и остаток под инициативы по ролям.' },
      { target: 'planning-approve', title: 'Утвердить', description: 'Когда план собран — утвердите сценарий. По утверждённому строится ресурсный план.' },
    ],
  },
  {
    id: 'resource-planning',
    route: '/resource-planning',
    steps: [
      { target: 'rp-scenario-select', title: 'Утверждённый сценарий', description: 'План строится по утверждённому сценарию команды.' },
      { target: 'rp-distribute', title: 'Распределить', description: 'Сервис раскладывает фазы инициатив по исполнителям и дням с учётом отсутствий и вовлечённости.' },
      { target: 'rp-view', title: 'Вид', description: 'По задачам или по исполнителям.' },
      { target: 'rp-gantt', title: 'Диаграмма', description: 'Сроки фаз. Клик по полосе открывает подробности и ручную правку.' },
      { target: 'rp-load', title: 'Загрузка по дням', description: 'Перегруз виден сразу.' },
    ],
  },
  {
    id: 'header',
    steps: [
      { target: 'header-team', title: 'Команда', description: 'Фильтр команды действует во всех разделах.' },
      { target: 'header-period', title: 'Период', description: 'Квартал или месяц для отчётов.' },
      { target: 'header-help', title: 'Справка', description: 'Справка по текущему разделу и лента «Что нового».' },
      { target: 'header-onboarding', title: 'Первые шаги', description: 'Сюда можно вернуться в любой момент.' },
    ],
  },
  {
    id: 'dashboard',
    route: '/',
    steps: [
      { target: 'dash-projects', title: 'Проекты квартала', description: 'Над чем команда работает в периоде.' },
      { target: 'dash-normed', title: 'Нормированные работы', description: 'План и факт по ролям.' },
      { target: 'dash-worklogs', title: 'Ворклоги по категориям', description: 'Куда ушли часы команды.' },
      { target: 'dash-balance', title: 'Баланс часов', description: 'Списано против нормы.' },
    ],
  },
  {
    id: 'analytics',
    route: '/analytics',
    steps: [
      { target: 'analytics-period', title: 'Уточнить период', description: 'Даты внутри периода из шапки.' },
      { target: 'analytics-hierarchy', title: 'Иерархия', description: 'Задачи деревом до верхнего родителя.' },
      { target: 'analytics-settings', title: 'Настройка отчёта', description: 'Какие колонки показывать.' },
      { target: 'analytics-filters', title: 'Фильтры', description: 'Роли, сотрудники, категории.' },
      { target: 'analytics-table', title: 'Отчёт', description: 'Команда → роль → сотрудник → вид работ → категория → задача.' },
    ],
  },
  {
    id: 'team-desk',
    route: '/team-desk',
    steps: [
      { target: 'desk-filters', title: 'Фильтры', description: 'Спринт, релиз, пороги замечаний.' },
      { target: 'desk-tabs', title: 'Раскладки', description: 'Светофор, ведомость, проблемы вперёд.' },
      { target: 'desk-flags', title: 'Замечания', description: 'Зависшие и перерасходованные задачи, статусы.' },
      { target: 'desk-issues', title: 'Задачи', description: 'Сгруппированы по разработчикам.' },
    ],
  },
];

export const TOURS: Record<string, TourDef> = Object.fromEntries(list.map(t => [t.id, t]));
```
Описания сверить со справкой раздела (`docs/help/<раздел>.md`): если там сказано иначе — поправить текст экскурсии под справку/код.

- [ ] **Step 3: Проверка** — `cd frontend; npm run lint; npm run build` → чисто.

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(onboarding): экскурсии по разделам настройки и знакомства"
```

---

### Task 6: E2E и живая проверка

**Files:**
- Modify: `scripts/seed_e2e.py`
- Create: `frontend/e2e/onboarding.spec.ts`

- [ ] **Step 1: Сид** — в `User(...)` для `e2e-admin-id` добавить `onboarding_raw='{"auto_opened": true}',` (иначе панель откроется сама и перекроет страницу во всех остальных E2E).

- [ ] **Step 2: Тест** — по образцу `frontend/e2e/dashboard.spec.ts` (тот же способ входа):
```ts
import { test } from '@playwright/test';
import { expectNoBrowserErrors, expectVisible, trackBrowserErrors } from './helpers';

test('first steps panel opens and runs the dashboard tour', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/');
  await page.getByTestId('onboarding-button').click();
  await expectVisible(page.getByText('Знакомство с сервисом', { exact: true }));

  await page.getByTestId('tour-start-dashboard').click();
  await expectVisible(page.locator('.ant-tour').getByText('Проекты квартала', { exact: true }));

  await expectNoBrowserErrors(browserErrors);
});
```

- [ ] **Step 3: Прогон** — `.\scripts\e2e-local.ps1` → новый тест и прежние зелёные.

- [ ] **Step 4: Полный прогон бэкенда** — `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py` → без новых падений.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_e2e.py frontend/e2e/onboarding.spec.ts
git commit -m "test(onboarding): e2e панели первых шагов"
```

- [ ] **Step 6: Живая проверка в браузере** (контроллер, после всех задач): локальный сервер из рабочей копии на копии рабочей базы; войти, выбрать команду, пройти все 10 экскурсий: вкладки переключаются, цели подсвечиваются, «Готово» ставит отметку, крестик — нет; «Проверил» показывает имя и дату.
