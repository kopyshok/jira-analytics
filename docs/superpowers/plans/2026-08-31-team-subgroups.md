# Группы внутри команды — план внедрения (первый выпуск)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ввести виртуальное деление команды на группы, включаемое признаком на команде, и довести его до ёмкости, сценариев, ресурсного планирования и стопки разбора.

**Architecture:** появляется реестр команд (`teams`) и группы (`team_subgroups`). Приписка сотрудника живёт на строке участия в команде (`employee_teams.subgroup_id`). У задачи группа разрешается лесенкой (явно → от родителя → предположение по исполнителю) отдельным резолвером-соседом `CategoryResolver`. Строковые имена команд на существующих таблицах не трогаем — реестр адресуется по тому же имени. При выключенном признаке весь новый код возвращает пустой разрез, и поведение сервиса идентично текущему.

**Tech Stack:** Python 3.10 (`py -3.10`), FastAPI, SQLAlchemy 2.0, Alembic (batch mode для SQLite), pytest; React 19 + TS + AntD 6, TanStack Query.

**Спека:** `docs/superpowers/specs/2026-08-31-team-subgroups-design.md`

**Ветка:** `feature/team-subgroups`

---

## Что сознательно не входит в первый выпуск

Правило «факт — по группе задачи, ёмкость — по группе человека» в этом выпуске
доводится **только до ёмкости**. Разложение фактических часов по группам и
строка «переток внутри команды» живут в витринах — дашборд, аналитика, KPI,
Executive, проекты, стол тимлида, экспорты, бэклог — и переносятся во второй
выпуск. До него витрины показывают команду целиком: не врут, просто не
детализируют.

Нормированные работы не трогаются вовсе: они привязаны к человеку, а у человека
группа есть всегда.

Критерий приёмки №4 из спеки (часы разработчика из чужой группы) проверяется во
втором выпуске. В первом проверяется его половина — расход ёмкости.

---

## Структура файлов

**Создаются (backend):**
- `app/models/team.py` — `Team` (реестр) и `TeamSubgroup` (группа).
- `app/services/team_registry_service.py` — наполнение реестра именами, CRUD групп, приписка сотрудников.
- `app/services/subgroup_resolver.py` — лесенка разрешения группы у задачи.
- `alembic/versions/<rev>_team_subgroups.py` — миграция.
- `tests/services/test_team_registry_service.py`
- `tests/services/test_subgroup_resolver.py`
- `tests/api/test_teams_registry.py`
- `tests/test_capacity_subgroup.py`
- `tests/test_subgroups_disabled_regression.py` — главный тест «команда без групп ведёт себя как раньше».

**Изменяются (backend):**
- `app/models/employee_team.py` — `subgroup_id`.
- `app/models/issue.py` — `assigned_subgroup_id`, `subgroup_verified`.
- `app/models/user.py` — `selected_subgroups`.
- `app/models/__init__.py` — экспорт новых моделей.
- `app/api/endpoints/teams.py` — реестр и группы.
- `app/api/endpoints/auth.py`, `app/schemas/user.py` — выбор групп в шапке.
- `app/services/capacity_service.py` — разрез ёмкости по группам.
- `app/services/planning_service.py` — разбивка сценария по группам.
- `app/services/snapshot_writer.py` — группа сотрудника в снапшоте состава.
- `app/api/endpoints/issue_config.py` — подтверждение группы в стопке.

**Изменяются (frontend):**
- `frontend/src/api/teams.ts` (создаётся) — работа с реестром.
- `frontend/src/hooks/useTeamRegistry.ts` (создаётся).
- `frontend/src/components/settings/TeamsRegistryTab.tsx` (создаётся) — раздел настроек.
- `frontend/src/pages/SettingsPage.tsx` — пункт «Команды и группы».
- `frontend/src/components/GlobalTeamFilterProvider.tsx`, `frontend/src/hooks/useGlobalTeamFilter.ts`, `frontend/src/components/Layout/GlobalTeamFilterButton.tsx` — второй уровень фильтра.
- `frontend/src/pages/CategoriesEditorPage.tsx` — колонка «Группа» в стопке.
- `frontend/src/pages/CapacityPage.tsx` — приписка сотрудника + ёмкость по группам.
- `frontend/src/components/planning/*` — секции по группам в сценарии.
- `frontend/src/components/resource-planning/GanttRows.tsx` — секции по группам.

---

## Фаза 1 — фундамент

### Task 1: Модели реестра и групп

**Files:**
- Create: `app/models/team.py`
- Modify: `app/models/__init__.py`
- Test: `tests/services/test_team_registry_service.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/services/test_team_registry_service.py
from app.models import Team, TeamSubgroup


def test_team_defaults_to_no_subgroups(db_session):
    team = Team(name="Команда 1С (Бухгалтерия)")
    db_session.add(team)
    db_session.commit()

    assert team.has_subgroups is False
    assert team.subgroups == []


def test_subgroups_are_ordered_and_cascade(db_session):
    team = Team(name="Команда 1С (Бухгалтерия)", has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2),
        TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1),
    ])
    db_session.commit()
    db_session.refresh(team)

    assert [s.name for s in team.subgroups] == ["Расчёты", "Интеграции"]

    db_session.delete(team)
    db_session.commit()
    assert db_session.query(TeamSubgroup).count() == 0
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `py -3.10 -m pytest tests/services/test_team_registry_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'Team'`

- [ ] **Step 3: Написать модели**

```python
# app/models/team.py
"""Реестр команд и групп внутри команды.

Имя команды по-прежнему хранится строкой в задачах, участии сотрудников,
сценариях и планах. Реестр адресуется по тому же имени и добавляет к нему
настройки — в первую очередь признак деления на группы.
"""

from typing import List

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class Team(Base, TimestampMixin):
    """Команда. Строка реестра, наполняется автоматически именами из данных."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    has_subgroups: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    subgroups: Mapped[List["TeamSubgroup"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="TeamSubgroup.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Team {self.name}{' *groups' if self.has_subgroups else ''}>"


class TeamSubgroup(Base, TimestampMixin):
    """Группа внутри команды. Виртуальное деление, в Jira его нет."""

    __tablename__ = "team_subgroups"
    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_team_subgroup_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    team: Mapped["Team"] = relationship(back_populates="subgroups")

    def __repr__(self) -> str:
        return f"<TeamSubgroup {self.name}>"
```

В `app/models/__init__.py` добавить импорт и записи в `__all__`:

```python
from app.models.team import Team, TeamSubgroup
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `py -3.10 -m pytest tests/services/test_team_registry_service.py -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/models/team.py app/models/__init__.py tests/services/test_team_registry_service.py
git commit -m "feat(teams): реестр команд и группы внутри команды"
```

---

### Task 2: Поля приписки и группы у задачи

**Files:**
- Modify: `app/models/employee_team.py`, `app/models/issue.py`, `app/models/user.py`
- Test: `tests/services/test_team_registry_service.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/services/test_team_registry_service.py`:

```python
def test_membership_carries_subgroup(db_session):
    from app.models import Employee, EmployeeTeam

    team = Team(name="Команда 1С (Бухгалтерия)", has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    group = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    db_session.add(group)
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(
        employee_id=emp.id, team=team.name, is_primary=True, subgroup_id=group.id,
    ))
    db_session.commit()

    row = db_session.query(EmployeeTeam).one()
    assert row.subgroup_id == group.id


def test_issue_subgroup_defaults(db_session):
    from app.models import Issue

    issue = Issue(
        jira_issue_id="10001", key="OS-1", summary="x",
        issue_type="Task", status="Open", project_id="p1",
    )
    assert issue.assigned_subgroup_id is None
    assert issue.subgroup_verified is True
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `py -3.10 -m pytest tests/services/test_team_registry_service.py -v`
Expected: FAIL — `TypeError: 'subgroup_id' is an invalid keyword argument`

- [ ] **Step 3: Добавить поля**

В `app/models/employee_team.py` после `is_primary` (импортировать `ForeignKey` уже есть):

```python
    subgroup_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("team_subgroups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

В `app/models/issue.py` рядом с `category_verified` (строка 131):

```python
    # Группа внутри команды. Разрешается лесенкой в SubgroupResolver:
    # assigned_subgroup_id → группа ближайшего предка → группа исполнителя.
    assigned_subgroup_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("team_subgroups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subgroup_verified: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
```

В `app/models/user.py` рядом с `selected_teams_raw` (строка 31):

```python
    selected_subgroups_raw: Mapped[str] = mapped_column(
        "selected_subgroups", Text, nullable=False, default="[]", server_default="[]"
    )

    @property
    def selected_subgroups(self) -> list[str]:
        try:
            return json.loads(self.selected_subgroups_raw or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @selected_subgroups.setter
    def selected_subgroups(self, value: list[str]) -> None:
        self.selected_subgroups_raw = json.dumps(list(value or []))
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `py -3.10 -m pytest tests/services/test_team_registry_service.py -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/models/employee_team.py app/models/issue.py app/models/user.py tests/services/test_team_registry_service.py
git commit -m "feat(teams): приписка сотрудника к группе и группа у задачи"
```

---

### Task 3: Миграция

**Files:**
- Create: `alembic/versions/<rev>_team_subgroups.py`

- [ ] **Step 1: Сгенерировать миграцию**

Run: `py -3.10 -m alembic revision --autogenerate -m "team subgroups"`

- [ ] **Step 2: Проверить содержимое**

В файле должны быть: создание `teams` и `team_subgroups`, `add_column` в `employee_teams`, `issues`, `users`. Все `add_column` — через `op.batch_alter_table` (SQLite). У новых булевых колонок обязателен `server_default`, иначе миграция упадёт на непустой базе.

Миграция **не должна** импортировать сервисы приложения — только `sqlalchemy` и `alembic.op`. Это грабли выпуска v1.6.1: миграция, звавшая живой код, ломала установку с нуля.

- [ ] **Step 3: Прогнать вверх и вниз**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m alembic downgrade -1
py -3.10 -m alembic upgrade head
```
Expected: обе стороны отрабатывают без ошибок

- [ ] **Step 4: Коммит**

```bash
git add alembic/versions
git commit -m "feat(teams): миграция под реестр команд и группы"
```

---

### Task 4: Наполнение реестра именами команд

**Files:**
- Create: `app/services/team_registry_service.py`
- Test: `tests/services/test_team_registry_service.py`

- [ ] **Step 1: Написать падающий тест**

```python
def test_sync_names_picks_up_teams_from_data(db_session):
    from app.models import Employee, EmployeeTeam, Issue, Project
    from app.services.team_registry_service import TeamRegistryService

    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    db_session.add(Issue(
        jira_issue_id="10001", key="OS-1", summary="x", issue_type="Task",
        status="Open", project_id="p1", team="Команда А",
    ))
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Команда Б", is_primary=True))
    db_session.commit()

    created = TeamRegistryService(db_session).sync_names()

    assert created == 2
    assert {t.name for t in db_session.query(Team).all()} == {"Команда А", "Команда Б"}

    assert TeamRegistryService(db_session).sync_names() == 0
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `py -3.10 -m pytest tests/services/test_team_registry_service.py::test_sync_names_picks_up_teams_from_data -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.team_registry_service'`

- [ ] **Step 3: Написать сервис**

```python
# app/services/team_registry_service.py
"""Реестр команд: наполнение именами и настройки групп."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmployeeTeam, Issue, Team, TeamSubgroup


class TeamRegistryService:
    """Работа с реестром команд и группами внутри них."""

    def __init__(self, db: Session):
        self.db = db

    def sync_names(self) -> int:
        """Завести в реестре команды, встречающиеся в данных. Вернуть число новых."""
        known = {name for (name,) in self.db.query(Team.name).all()}

        found: set[str] = set()
        for (value,) in self.db.query(Issue.team).filter(Issue.team.isnot(None)).distinct():
            if value:
                found.add(value)
        for (value,) in self.db.query(EmployeeTeam.team).distinct():
            if value:
                found.add(value)

        new_names = sorted(found - known)
        for name in new_names:
            self.db.add(Team(name=name))
        if new_names:
            self.db.commit()
        return len(new_names)

    def get(self, name: str) -> Optional[Team]:
        return self.db.query(Team).filter(Team.name == name).first()

    def set_has_subgroups(self, name: str, enabled: bool) -> Team:
        """Включить или выключить деление команды на группы.

        Выключение группы не удаляет: признак снят — разрезы скрыты, данные
        целы, включение возвращает всё как было. Это и есть путь отката.
        """
        team = self.get(name)
        if team is None:
            team = Team(name=name)
            self.db.add(team)
        team.has_subgroups = enabled
        self.db.commit()
        return team

    def add_subgroup(self, name: str, subgroup_name: str) -> TeamSubgroup:
        team = self.get(name)
        if team is None:
            raise ValueError(f"Команда не найдена: {name}")
        order = len(team.subgroups) + 1
        group = TeamSubgroup(team_id=team.id, name=subgroup_name, sort_order=order)
        self.db.add(group)
        self.db.commit()
        return group

    def rename_subgroup(self, subgroup_id: str, subgroup_name: str) -> TeamSubgroup:
        group = self.db.query(TeamSubgroup).filter(TeamSubgroup.id == subgroup_id).one()
        group.name = subgroup_name
        self.db.commit()
        return group

    def delete_subgroup(self, subgroup_id: str) -> None:
        """Удалить группу. Приписки сотрудников и задач обнуляются каскадом."""
        group = self.db.query(TeamSubgroup).filter(TeamSubgroup.id == subgroup_id).one()
        self.db.delete(group)
        self.db.commit()

    def assign_employee(self, employee_id: str, team: str, subgroup_id: Optional[str]) -> None:
        """Приписать сотрудника к группе во всех его строках участия в команде."""
        rows = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .all()
        )
        for row in rows:
            row.subgroup_id = subgroup_id
        self.db.commit()
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `py -3.10 -m pytest tests/services/test_team_registry_service.py -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/services/team_registry_service.py tests/services/test_team_registry_service.py
git commit -m "feat(teams): сервис реестра команд"
```

---

### Task 5: Резолвер группы у задачи

**Files:**
- Create: `app/services/subgroup_resolver.py`
- Test: `tests/services/test_subgroup_resolver.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/services/test_subgroup_resolver.py
"""Лесенка разрешения группы: явно → от родителя → по исполнителю."""

import pytest

from app.models import Employee, EmployeeTeam, Issue, Project, Team, TeamSubgroup
from app.services.subgroup_resolver import SubgroupResolver, SubgroupSource


@pytest.fixture
def setup(db_session):
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    team = Team(name="Команда 1С (Бухгалтерия)", has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(
        employee_id=emp.id, team=team.name, is_primary=True, subgroup_id=integ.id,
    ))
    db_session.commit()
    return {"team": team, "calc": calc, "integ": integ, "emp": emp}


def _issue(db_session, key, **kw):
    issue = Issue(
        jira_issue_id=key, key=key, summary=key, issue_type="Task",
        status="Open", project_id="p1", team="Команда 1С (Бухгалтерия)", **kw,
    )
    db_session.add(issue)
    db_session.commit()
    return issue


def test_explicit_wins(db_session, setup):
    issue = _issue(db_session, "OS-1", assigned_subgroup_id=setup["calc"].id,
                   assignee_account_id="acc-1")

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id == setup["calc"].id
    assert res.source == SubgroupSource.ASSIGNED


def test_inherited_from_parent(db_session, setup):
    parent = _issue(db_session, "OS-10", assigned_subgroup_id=setup["calc"].id)
    child = _issue(db_session, "OS-11", parent_id=parent.id, assignee_account_id="acc-1")

    res = SubgroupResolver(db_session).resolve_for_issue(child)

    assert res.subgroup_id == setup["calc"].id
    assert res.source == SubgroupSource.INHERITED


def test_guess_from_assignee(db_session, setup):
    issue = _issue(db_session, "OS-2", assignee_account_id="acc-1")

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id == setup["integ"].id
    assert res.source == SubgroupSource.GUESS


def test_nothing_to_guess(db_session, setup):
    issue = _issue(db_session, "OS-3")

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE


def test_team_without_subgroups_resolves_to_nothing(db_session, setup):
    setup["team"].has_subgroups = False
    db_session.commit()
    issue = _issue(db_session, "OS-4", assigned_subgroup_id=setup["calc"].id,
                   assignee_account_id="acc-1")

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/services/test_subgroup_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.subgroup_resolver'`

- [ ] **Step 3: Написать резолвер**

```python
# app/services/subgroup_resolver.py
"""Определение группы внутри команды для задачи.

Приоритет:
1. Проставлено явно на задаче (assigned_subgroup_id);
2. Ближайший предок с явно проставленной группой;
3. Предположение по исполнителю — группа, к которой он приписан в этой команде.

Команды без включённого признака деления всегда дают пустой результат:
именно это гарантирует, что для них ничего не меняется.

Резолвер сознательно не встроен в CategoryResolver: другая лесенка, другой
источник данных, общего кода нет.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Employee, EmployeeTeam, Issue, Team


class SubgroupSource:
    ASSIGNED = "assigned"      # проставлено человеком
    INHERITED = "inherited"    # от родителя
    GUESS = "guess"            # предположение по исполнителю
    NONE = "none"


@dataclass
class SubgroupResolution:
    subgroup_id: Optional[str]
    source: str
    source_entity_key: Optional[str] = None


class SubgroupResolver:
    """Резолвер группы. Кэши живут на время экземпляра."""

    def __init__(self, db: Session):
        self.db = db
        self._enabled_teams: Optional[set[str]] = None
        self._subgroup_team: dict[str, str] = {}           # subgroup_id -> имя команды
        self._by_account: dict[tuple[str, str], str] = {}  # (account_id, команда) -> subgroup_id

    def _load(self) -> None:
        if self._enabled_teams is not None:
            return

        teams = self.db.query(Team).filter(Team.has_subgroups.is_(True)).all()
        self._enabled_teams = {t.name for t in teams}
        for t in teams:
            for g in t.subgroups:
                self._subgroup_team[g.id] = t.name

        rows = (
            self.db.query(EmployeeTeam.team, EmployeeTeam.subgroup_id, Employee.jira_account_id)
            .join(Employee, Employee.id == EmployeeTeam.employee_id)
            .filter(EmployeeTeam.subgroup_id.isnot(None))
            .all()
        )
        for team_name, subgroup_id, account_id in rows:
            if account_id:
                self._by_account[(account_id, team_name)] = subgroup_id

    def _valid(self, subgroup_id: Optional[str], team: str) -> bool:
        """Группа годится, только если принадлежит команде задачи."""
        if not subgroup_id:
            return False
        return self._subgroup_team.get(subgroup_id) == team

    def resolve_for_issue(self, issue: Issue) -> SubgroupResolution:
        self._load()
        empty = SubgroupResolution(subgroup_id=None, source=SubgroupSource.NONE)

        team = issue.team
        if not team or team not in (self._enabled_teams or set()):
            return empty

        # 1. Явно на задаче
        if self._valid(issue.assigned_subgroup_id, team):
            return SubgroupResolution(
                subgroup_id=issue.assigned_subgroup_id,
                source=SubgroupSource.ASSIGNED,
                source_entity_key=issue.key,
            )

        # 2. Ближайший предок с явной группой
        current: Optional[Issue] = issue.parent
        visited: set[str] = {issue.id}
        while current is not None and current.id not in visited:
            visited.add(current.id)
            if self._valid(current.assigned_subgroup_id, team):
                return SubgroupResolution(
                    subgroup_id=current.assigned_subgroup_id,
                    source=SubgroupSource.INHERITED,
                    source_entity_key=current.key,
                )
            current = current.parent

        # 3. Предположение по исполнителю
        guess = self._by_account.get((issue.assignee_account_id or "", team))
        if self._valid(guess, team):
            return SubgroupResolution(subgroup_id=guess, source=SubgroupSource.GUESS)

        return empty
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `py -3.10 -m pytest tests/services/test_subgroup_resolver.py -v`
Expected: 5 passed

- [ ] **Step 5: Коммит**

```bash
git add app/services/subgroup_resolver.py tests/services/test_subgroup_resolver.py
git commit -m "feat(teams): резолвер группы у задачи"
```

---

### Task 6: API реестра

**Files:**
- Modify: `app/api/endpoints/teams.py`
- Create: `app/schemas/team.py`
- Test: `tests/api/test_teams_registry.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/api/test_teams_registry.py
def _seed_team(db_session, name="Команда А"):
    from app.models import Employee, EmployeeTeam

    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=name, is_primary=True))
    db_session.commit()


def test_registry_lists_teams_with_groups(client, db_session):
    _seed_team(db_session)

    resp = client.get("/api/v1/teams/registry")

    assert resp.status_code == 200
    assert resp.json() == [{"name": "Команда А", "has_subgroups": False, "subgroups": []}]


def test_enable_and_add_subgroup(client, db_session):
    _seed_team(db_session)
    client.get("/api/v1/teams/registry")

    resp = client.patch("/api/v1/teams/registry/Команда А", json={"has_subgroups": True})
    assert resp.status_code == 200
    assert resp.json()["has_subgroups"] is True

    resp = client.post("/api/v1/teams/registry/Команда А/subgroups", json={"name": "Расчёты"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Расчёты"


def test_plain_team_list_unchanged(client, db_session):
    """Плоский список остаётся — на нём висит фильтр в шапке."""
    _seed_team(db_session)

    resp = client.get("/api/v1/teams")

    assert resp.status_code == 200
    assert resp.json() == ["Команда А"]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/api/test_teams_registry.py -v`
Expected: FAIL — 404 на `/teams/registry`

- [ ] **Step 3: Написать схемы и ручки**

```python
# app/schemas/team.py
from typing import List, Optional

from pydantic import BaseModel, Field


class SubgroupOut(BaseModel):
    id: str
    name: str
    sort_order: int

    model_config = {"from_attributes": True}


class TeamOut(BaseModel):
    name: str
    has_subgroups: bool
    subgroups: List[SubgroupOut] = []


class TeamPatch(BaseModel):
    has_subgroups: bool


class SubgroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class EmployeeSubgroupIn(BaseModel):
    team: str
    subgroup_id: Optional[str] = None
```

В `app/api/endpoints/teams.py` дописать (существующий `GET ""` не трогать):

```python
def _to_out(team: Team) -> TeamOut:
    return TeamOut(
        name=team.name,
        has_subgroups=team.has_subgroups,
        subgroups=[SubgroupOut.model_validate(g) for g in team.subgroups],
    )


@router.get("/registry", response_model=List[TeamOut])
def list_registry(db: Session = Depends(get_db)) -> List[TeamOut]:
    """Реестр команд. Перед выдачей подтягивает имена, появившиеся в данных."""
    TeamRegistryService(db).sync_names()
    return [_to_out(t) for t in db.query(Team).order_by(Team.name).all()]


@router.patch("/registry/{name}", response_model=TeamOut)
def patch_registry(name: str, data: TeamPatch, db: Session = Depends(get_db)) -> TeamOut:
    return _to_out(TeamRegistryService(db).set_has_subgroups(name, data.has_subgroups))


@router.post("/registry/{name}/subgroups", response_model=SubgroupOut, status_code=201)
def create_subgroup(name: str, data: SubgroupIn, db: Session = Depends(get_db)) -> SubgroupOut:
    try:
        group = TeamRegistryService(db).add_subgroup(name, data.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return SubgroupOut.model_validate(group)


@router.patch("/subgroups/{subgroup_id}", response_model=SubgroupOut)
def rename_subgroup(
    subgroup_id: str, data: SubgroupIn, db: Session = Depends(get_db)
) -> SubgroupOut:
    return SubgroupOut.model_validate(
        TeamRegistryService(db).rename_subgroup(subgroup_id, data.name)
    )


@router.delete("/subgroups/{subgroup_id}", status_code=204)
def delete_subgroup(subgroup_id: str, db: Session = Depends(get_db)) -> None:
    TeamRegistryService(db).delete_subgroup(subgroup_id)


@router.put("/employees/{employee_id}/subgroup", status_code=204)
def set_employee_subgroup(
    employee_id: str, data: EmployeeSubgroupIn, db: Session = Depends(get_db)
) -> None:
    TeamRegistryService(db).assign_employee(employee_id, data.team, data.subgroup_id)
```

Дописать импорты в шапке: `HTTPException` из `fastapi`, `Team` из `app.models`, `TeamRegistryService`, схемы из `app.schemas.team`.

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `py -3.10 -m pytest tests/api/test_teams_registry.py -v`
Expected: 3 passed

- [ ] **Step 5: Коммит**

```bash
git add app/api/endpoints/teams.py app/schemas/team.py tests/api/test_teams_registry.py
git commit -m "feat(teams): API реестра команд и групп"
```

---

## Фаза 2 — ёмкость и сценарии

### Task 7: Ёмкость в разрезе групп

**Files:**
- Modify: `app/services/capacity_service.py`
- Test: `tests/test_capacity_subgroup.py`

Фикстуры `subgroup_setup` и `plain_team_setup` собрать в `tests/conftest.py` по образцу `tests/test_capacity_role.py:19` (`productive_setup`): производственный календарь на квартал, сотрудники с ролью `dev`, участие в команде, приписка к группам. `plain_team_setup` — та же команда, но `has_subgroups=False` и без приписок.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_capacity_subgroup.py
"""Ёмкость команды, разложенная по группам."""

from app.services.capacity_service import CapacityService


def test_capacity_splits_by_subgroup(db_session, subgroup_setup):
    """Двое в разных группах — их часы не смешиваются."""
    out = CapacityService(db_session).team_role_capacity_by_subgroup(
        year=2026, quarter=2, team="Команда 1С (Бухгалтерия)",
    )

    assert set(out.keys()) == {subgroup_setup["calc"].id, subgroup_setup["integ"].id}
    assert out[subgroup_setup["calc"].id]["dev"] > 0
    assert out[subgroup_setup["integ"].id]["dev"] > 0


def test_sum_of_subgroups_equals_team_total(db_session, subgroup_setup):
    svc = CapacityService(db_session)

    by_group = svc.team_role_capacity_by_subgroup(2026, 2, "Команда 1С (Бухгалтерия)")
    total = svc.team_role_capacity(2026, 2, team_filter=["Команда 1С (Бухгалтерия)"])

    summed = sum(bucket["dev"] for bucket in by_group.values())
    assert abs(summed - total["dev"]) < 0.01


def test_unassigned_employee_goes_to_none_bucket(db_session, subgroup_setup_with_unassigned):
    out = CapacityService(db_session).team_role_capacity_by_subgroup(
        year=2026, quarter=2, team="Команда 1С (Бухгалтерия)",
    )

    assert None in out
    assert out[None]["dev"] > 0


def test_team_without_subgroups_returns_empty(db_session, plain_team_setup):
    """Признак выключен — разреза нет, вызывающий код идёт общим путём."""
    out = CapacityService(db_session).team_role_capacity_by_subgroup(
        year=2026, quarter=2, team="Команда без групп",
    )

    assert out == {}
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_capacity_subgroup.py -v`
Expected: FAIL — `AttributeError: 'CapacityService' object has no attribute 'team_role_capacity_by_subgroup'`

- [ ] **Step 3: Написать метод**

Дописать в `app/services/capacity_service.py` сразу после `team_role_capacity`:

```python
    def team_role_capacity_by_subgroup(
        self,
        year: int,
        quarter: int,
        team: str,
    ) -> dict[Optional[str], dict[str, float]]:
        """Ёмкость одной команды, разложенная по группам и ролям.

        Ключ ``None`` — сотрудники команды, не приписанные ни к одной группе.
        Пустой словарь — у команды выключен признак деления; вызывающий код
        в этом случае показывает команду целиком, как раньше.
        """
        if quarter not in QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1..4, got {quarter}")

        from app.models import EmployeeTeam, Team
        from app.services import team_membership as _tm

        registry = self.db.query(Team).filter(Team.name == team).first()
        if registry is None or not registry.has_subgroups:
            return {}

        months = QUARTER_MONTHS[quarter]
        q_start = date(year, months[0], 1)
        q_end = date(year, months[-1], monthrange(year, months[-1])[1])

        rows = (
            self.db.query(Employee, EmployeeTeam.subgroup_id)
            .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .filter(
                Employee.is_active.is_(True),
                EmployeeTeam.team == team,
                *_tm.overlaps_clause(q_start, q_end),
            )
            .distinct()
            .all()
        )

        out: dict[Optional[str], dict[str, float]] = {}
        for emp, subgroup_id in rows:
            role = (emp.role or "").strip().lower()
            if role not in ROLE_WHITELIST:
                continue
            bucket = out.setdefault(subgroup_id, {r: 0.0 for r in ROLE_WHITELIST})
            bucket[role] += self.employee_quarter_capacity(emp.id, year, quarter)
        return out
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `py -3.10 -m pytest tests/test_capacity_subgroup.py tests/test_capacity_role.py -v`
Expected: все зелёные — существующие тесты ёмкости не должны сдвинуться

- [ ] **Step 5: Коммит**

```bash
git add app/services/capacity_service.py tests/test_capacity_subgroup.py tests/conftest.py
git commit -m "feat(capacity): ёмкость команды в разрезе групп"
```

---

### Task 8: Группа сотрудника в снапшоте сценария

**Files:**
- Modify: `app/models/scenario_team_snapshot.py`, `app/services/snapshot_writer.py`
- Test: `tests/test_scenario_subgroup_snapshot.py`

Фикстура `approved_scenario_ctx` — сценарий на команду с двумя группами и двумя сотрудниками (`emp_calc` в «Расчётах», `emp_integ` в «Интеграциях»), утверждённый через существующий путь утверждения.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_scenario_subgroup_snapshot.py
"""Утверждение сценария замораживает группу сотрудника.

Именно поэтому истории приписок в реестре не нужно: снапшот помнит,
кто в какой группе был на момент утверждения.
"""

from app.models import EmployeeTeam, ScenarioTeamSnapshot


def test_snapshot_freezes_subgroup(db_session, approved_scenario_ctx):
    rows = (
        db_session.query(ScenarioTeamSnapshot)
        .filter(ScenarioTeamSnapshot.scenario_id == approved_scenario_ctx["scenario"].id)
        .all()
    )

    assert rows
    assert {r.subgroup_name for r in rows} == {"Расчёты", "Интеграции"}


def test_snapshot_survives_employee_move(db_session, approved_scenario_ctx):
    row = (
        db_session.query(EmployeeTeam)
        .filter(EmployeeTeam.employee_id == approved_scenario_ctx["emp_calc"].id)
        .one()
    )
    row.subgroup_id = approved_scenario_ctx["integ"].id
    db_session.commit()

    frozen = (
        db_session.query(ScenarioTeamSnapshot)
        .filter(
            ScenarioTeamSnapshot.scenario_id == approved_scenario_ctx["scenario"].id,
            ScenarioTeamSnapshot.employee_id == approved_scenario_ctx["emp_calc"].id,
        )
        .one()
    )
    assert frozen.subgroup_name == "Расчёты"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_scenario_subgroup_snapshot.py -v`
Expected: FAIL — у `ScenarioTeamSnapshot` нет `subgroup_name`

- [ ] **Step 3: Добавить поле и заполнение**

В `app/models/scenario_team_snapshot.py`:

```python
    # Имя группы на момент утверждения — строкой, чтобы переименование или
    # удаление группы не переписывало историю утверждённого сценария.
    subgroup_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
```

В `app/services/snapshot_writer.py` при формировании строк состава команды подставить имя группы из активной строки участия сотрудника в команде сценария; группа не проставлена — `None`.

Сгенерировать миграцию:

Run: `py -3.10 -m alembic revision --autogenerate -m "scenario team snapshot subgroup"`

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `py -3.10 -m pytest tests/test_scenario_subgroup_snapshot.py -v`
Expected: 2 passed

- [ ] **Step 5: Коммит**

```bash
git add app/models/scenario_team_snapshot.py app/services/snapshot_writer.py alembic/versions tests/test_scenario_subgroup_snapshot.py
git commit -m "feat(scenario): снапшот состава помнит группу сотрудника"
```

---

### Task 9: Разбивка сценария по группам в ответе API

**Files:**
- Modify: `app/services/planning_service.py`, `app/api/endpoints/planning.py`
- Test: `tests/test_planning_subgroups.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_planning_subgroups.py
def test_scenario_capacity_carries_subgroup_breakdown(client, scenario_with_subgroups):
    resp = client.get(f"/api/v1/planning/scenarios/{scenario_with_subgroups.id}/capacity")

    assert resp.status_code == 200
    body = resp.json()
    assert {row["subgroup_name"] for row in body["by_subgroup"]} == {"Расчёты", "Интеграции"}

    total_dev = sum(row["roles"]["dev"] for row in body["by_subgroup"])
    assert abs(total_dev - body["roles"]["dev"]) < 0.01


def test_scenario_without_subgroups_has_empty_breakdown(client, scenario_plain):
    resp = client.get(f"/api/v1/planning/scenarios/{scenario_plain.id}/capacity")

    assert resp.status_code == 200
    assert resp.json()["by_subgroup"] == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_planning_subgroups.py -v`
Expected: FAIL — `KeyError: 'by_subgroup'`

- [ ] **Step 3: Реализовать**

В `PlanningService` собрать разбивку через `CapacityService.team_role_capacity_by_subgroup` и отдать полем:

```python
by_subgroup: list[dict] = []
for subgroup_id, roles in capacity_service.team_role_capacity_by_subgroup(
    year, quarter, scenario.team
).items():
    by_subgroup.append({
        "subgroup_id": subgroup_id,
        "subgroup_name": names.get(subgroup_id, "Без группы"),
        "roles": roles,
    })
```

где `names` — словарь `id → имя` из `TeamSubgroup` команды сценария. Пустой список означает выключенный признак.

Итог по команде считается по-старому и **не** пересчитывается из групп — именно это делает проверку сходимости в тесте осмысленной.

Добавить `by_subgroup` в схему ответа в `app/api/endpoints/planning.py` со значением по умолчанию `[]`.

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `py -3.10 -m pytest tests/test_planning_subgroups.py -v && py -3.10 -m pytest tests/ -k planning -v`
Expected: все зелёные

- [ ] **Step 5: Коммит**

```bash
git add app/services/planning_service.py app/api/endpoints/planning.py tests/test_planning_subgroups.py
git commit -m "feat(scenario): разбивка ёмкости по группам"
```

---

## Фаза 3 — стопка разбора

### Task 10: Подтверждение группы у задачи

**Files:**
- Modify: `app/api/endpoints/issue_config.py`
- Test: `tests/api/test_issue_subgroup.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/api/test_issue_subgroup.py
def test_confirm_subgroup_marks_verified(client, issue_with_guess):
    issue, calc_id = issue_with_guess

    resp = client.put(
        f"/api/v1/issue-config/{issue.key}/subgroup",
        json={"subgroup_id": calc_id},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "key": issue.key,
        "subgroup_id": calc_id,
        "source": "assigned",
        "verified": True,
    }


def test_parent_move_resets_subgroup_verification(client, db_session, issue_with_parent):
    child, other_parent = issue_with_parent

    resp = client.put(
        f"/api/v1/issue-config/{child.key}/parent",
        json={"parent_key": other_parent.key},
    )

    assert resp.status_code == 200
    db_session.refresh(child)
    assert child.subgroup_verified is False
    assert child.category_verified is False
```

Точный путь ручки смены родителя взять из существующего кода `app/api/endpoints/issue_config.py` — тест должен звать тот же путь, который уже сбрасывает `category_verified`.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/api/test_issue_subgroup.py -v`
Expected: FAIL — 404 на `/subgroup`

- [ ] **Step 3: Реализовать**

Ручка `PUT /issue-config/{key}/subgroup` пишет `assigned_subgroup_id`, ставит `subgroup_verified = True` и возвращает результат резолвера.

В существующей обработке смены родителя (там, где сбрасывается `category_verified`) рядом дописать `issue.subgroup_verified = False`: группа наследуется от родителя ровно так же, как категория, значит и переподтверждать её надо по тому же поводу.

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `py -3.10 -m pytest tests/api/test_issue_subgroup.py -v`
Expected: 2 passed

- [ ] **Step 5: Коммит**

```bash
git add app/api/endpoints/issue_config.py tests/api/test_issue_subgroup.py
git commit -m "feat(triage): подтверждение группы и сброс при переезде задачи"
```

---

### Task 11: Регрессия — команда без групп

**Files:**
- Create: `tests/test_subgroups_disabled_regression.py`

Главный тест выпуска. Ловит основной риск: правка сквозная, а обязана быть незаметной для команд без групп.

- [ ] **Step 1: Написать тест**

```python
# tests/test_subgroups_disabled_regression.py
"""Команда без включённого признака ведёт себя как до правки."""

from app.services.capacity_service import CapacityService
from app.services.subgroup_resolver import SubgroupResolver


def test_capacity_identical_without_subgroups(db_session, plain_team_setup):
    svc = CapacityService(db_session)
    before = svc.team_role_capacity(2026, 2, team_filter=["Команда без групп"])

    assert svc.team_role_capacity_by_subgroup(2026, 2, "Команда без групп") == {}
    assert svc.team_role_capacity(2026, 2, team_filter=["Команда без групп"]) == before


def test_resolver_silent_without_subgroups(db_session, plain_issue):
    res = SubgroupResolver(db_session).resolve_for_issue(plain_issue)

    assert res.subgroup_id is None


def test_scenario_payload_has_empty_breakdown(client, scenario_plain):
    body = client.get(f"/api/v1/planning/scenarios/{scenario_plain.id}/capacity").json()

    assert body["by_subgroup"] == []


def test_plain_team_endpoint_unchanged(client, plain_team_setup):
    resp = client.get("/api/v1/teams")

    assert resp.status_code == 200
    assert all(isinstance(x, str) for x in resp.json())
```

- [ ] **Step 2: Прогнать**

Run: `py -3.10 -m pytest tests/test_subgroups_disabled_regression.py -v`
Expected: 4 passed

- [ ] **Step 3: Прогнать весь бэкенд**

Run: `py -3.10 -m pytest tests/ --ignore=tests/api/test_llm.py -q`
Expected: зелено. Тесты LLM исключаются — они висят без сети, это известное поведение стенда.

- [ ] **Step 4: Коммит**

```bash
git add tests/test_subgroups_disabled_regression.py
git commit -m "test(teams): регрессия — команда без групп не меняет поведение"
```

---

## Фаза 4 — интерфейс

### Task 12: Раздел настроек «Команды и группы»

**Files:**
- Create: `frontend/src/api/teams.ts`, `frontend/src/hooks/useTeamRegistry.ts`, `frontend/src/components/settings/TeamsRegistryTab.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Слой API**

```ts
// frontend/src/api/teams.ts
import { api } from './client';

export type Subgroup = { id: string; name: string; sort_order: number };
export type TeamRegistryRow = { name: string; has_subgroups: boolean; subgroups: Subgroup[] };

export const getTeamRegistry = () =>
  api.get<TeamRegistryRow[]>('/teams/registry').then((r) => r.data);

export const setTeamHasSubgroups = (name: string, has_subgroups: boolean) =>
  api
    .patch<TeamRegistryRow>(`/teams/registry/${encodeURIComponent(name)}`, { has_subgroups })
    .then((r) => r.data);

export const addSubgroup = (team: string, name: string) =>
  api
    .post<Subgroup>(`/teams/registry/${encodeURIComponent(team)}/subgroups`, { name })
    .then((r) => r.data);

export const renameSubgroup = (id: string, name: string) =>
  api.patch<Subgroup>(`/teams/subgroups/${id}`, { name }).then((r) => r.data);

export const deleteSubgroup = (id: string) => api.delete(`/teams/subgroups/${id}`);

export const setEmployeeSubgroup = (employeeId: string, team: string, subgroupId: string | null) =>
  api.put(`/teams/employees/${employeeId}/subgroup`, { team, subgroup_id: subgroupId });
```

Импорт клиента взять такой же, как в соседних файлах `frontend/src/api/*.ts`.

- [ ] **Step 2: Хуки**

`useTeamRegistry.ts` — `useQuery(['teams','registry'], getTeamRegistry)` плюс мутации на каждую операцию. Все инвалидируют `['teams','registry']`; мутация признака дополнительно инвалидирует `['teams']`, чтобы фильтр в шапке подхватил изменение.

- [ ] **Step 3: Экран**

`TeamsRegistryTab.tsx` — таблица команд: имя, переключатель «Делится на группы», под ним раскрывающийся список групп с добавлением, переименованием и удалением. Группы показываются только у команд с включённым переключателем.

Подсказка под таблицей: «Группы — деление внутри команды. В Jira его нет, оно живёт только здесь. Выключение переключателя скрывает разрезы, но ничего не удаляет.»

Уведомления AntD 6 — через `title`, не `message`.

- [ ] **Step 4: Пункт в навигации настроек**

В `frontend/src/pages/SettingsPage.tsx` в группу справочников (рядом со строками 70–77):

```tsx
{ key: 'teams', label: 'Команды и группы', render: () => <TeamsRegistryTab /> },
```

- [ ] **Step 5: Проверить сборку и закоммитить**

```bash
cd frontend && npm run lint && npm run build
```
Expected: без ошибок

```bash
git add frontend/src/api/teams.ts frontend/src/hooks/useTeamRegistry.ts frontend/src/components/settings/TeamsRegistryTab.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat(settings): раздел «Команды и группы»"
```

---

### Task 13: Приписка сотрудника к группе

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 1: Колонка в составе команды**

В таблице сотрудников команды добавить колонку «Группа» — выпадающий список групп выбранной команды плюс пункт «Без группы». Колонка отрисовывается, только если у команды включён признак (данные из `useTeamRegistry`).

- [ ] **Step 2: Сохранение**

Выбор сразу шлёт `setEmployeeSubgroup` и инвалидирует запросы ёмкости.

- [ ] **Step 3: Ёмкость по группам**

Таблица доступных часов группируется по группам, снизу — итог по команде. Строка «Без группы» — последняя.

- [ ] **Step 4: Проверить сборку и закоммитить**

```bash
cd frontend && npm run build
git add frontend/src/pages/CapacityPage.tsx
git commit -m "feat(capacity): приписка сотрудника к группе и ёмкость по группам"
```

---

### Task 14: Второй уровень фильтра в шапке

**Files:**
- Modify: `app/api/endpoints/auth.py`, `app/schemas/user.py`, `frontend/src/hooks/useGlobalTeamFilter.ts`, `frontend/src/components/GlobalTeamFilterProvider.tsx`, `frontend/src/components/Layout/GlobalTeamFilterButton.tsx`
- Test: `tests/api/test_user_subgroup_filter.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/api/test_user_subgroup_filter.py
def test_user_stores_selected_subgroups(client, auth_headers):
    resp = client.put(
        "/api/v1/auth/me/teams",
        json={"teams": ["Команда 1С (Бухгалтерия)"], "subgroups": ["sg-1"]},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["selected_subgroups"] == ["sg-1"]


def test_subgroups_default_to_empty(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)

    assert resp.json()["selected_subgroups"] == []
```

Точный путь ручки сохранения выбора команд взять из `app/api/endpoints/auth.py:68`.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `py -3.10 -m pytest tests/api/test_user_subgroup_filter.py -v`
Expected: FAIL — `KeyError: 'selected_subgroups'`

- [ ] **Step 3: Бэкенд**

В `app/schemas/user.py` добавить `selected_subgroups: list[str] = []` в схему выдачи (рядом со строкой 63) и `subgroups: list[str] = []` в схему запроса. В `app/api/endpoints/auth.py:68` рядом с `user.selected_teams = data.teams` дописать `user.selected_subgroups = data.subgroups`.

- [ ] **Step 4: Фронтенд**

`GlobalTeamFilterCtx` дополняется `selectedSubgroups`, `setSelectedSubgroups` и `queryParams.subgroups`.

В `GlobalTeamFilterButton` второй список рисуется, **только если** среди выбранных команд есть хотя бы одна с включённым признаком; список групп берётся из `getTeamRegistry`. Команда без групп второй уровень не показывает вовсе.

Смена набора команд отбрасывает выбранные группы, не принадлежащие оставшимся командам.

- [ ] **Step 5: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/api/test_user_subgroup_filter.py -v
cd frontend && npm run build
```

```bash
git add app/api/endpoints/auth.py app/schemas/user.py frontend/src/hooks/useGlobalTeamFilter.ts frontend/src/components/GlobalTeamFilterProvider.tsx frontend/src/components/Layout/GlobalTeamFilterButton.tsx tests/api/test_user_subgroup_filter.py
git commit -m "feat(filter): второй уровень фильтра — группы"
```

---

### Task 15: Колонка «Группа» в стопке разбора

**Files:**
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx`

- [ ] **Step 1: Колонка**

Рядом с колонкой категории — колонка «Группа». Проставленное вручную рисуется обычным цветом, унаследованное и предположение — приглушённым, как уже сделано для категории. Подсказка при наведении говорит, откуда взялось: «от задачи OS-10» или «по исполнителю».

- [ ] **Step 2: Подтверждение**

Выбор значения шлёт `PUT /issue-config/{key}/subgroup`. Задачи с неподтверждённой группой попадают в тот же фильтр «требует подтверждения», что и категории.

- [ ] **Step 3: Скрытие**

Колонка не рисуется, если ни у одной команды в текущей выборке не включён признак.

- [ ] **Step 4: Проверить сборку и закоммитить**

```bash
cd frontend && npm run build
git add frontend/src/pages/CategoriesEditorPage.tsx
git commit -m "feat(triage): колонка «Группа» в стопке разбора"
```

---

### Task 16: Секции по группам в сценарии и ресурсном планировании

**Files:**
- Modify: `frontend/src/components/planning/*`, `frontend/src/components/resource-planning/GanttRows.tsx`

- [ ] **Step 1: Сценарий**

Таблица ролей группируется по `by_subgroup` из ответа сервера, снизу — итог по команде. Пустой `by_subgroup` — таблица рисуется как сейчас, без секций.

- [ ] **Step 2: Ресурсное планирование**

Строки группируются заголовками групп; строка «Без группы» — последняя. Фильтр групп из шапки здесь **игнорируется**: план всегда показывает команду целиком, иначе ломается контроль занятости человека и авто-распределение перестаёт видеть соседей.

Полосы занятости по дням и авто-распределение **не трогать**: они считают по сотруднику и уже видят все группы. Любая правка здесь — регресс.

- [ ] **Step 3: Проверить сборку и закоммитить**

```bash
cd frontend && npm run build
git add frontend/src/components/planning frontend/src/components/resource-planning
git commit -m "feat(planning): секции по группам в сценарии и плане"
```

---

### Task 17: Справка и заметка к релизу

**Files:**
- Modify: `docs/help/settings.md`, `docs/help/planning.md`

- [ ] **Step 1: Справка**

В раздел настроек — описание «Команды и группы»: зачем, как включить, что выключение ничего не удаляет. В раздел планирования — как читать секции по группам и куда попадают часы при работе на соседнюю группу.

- [ ] **Step 2: Заметка к релизу**

Категория «Новое». Без технических терминов: команду можно разделить на группы, каждая планируется отдельно, а работа на соседнюю группу видна как внутренний переток, а не как помощь извне.

- [ ] **Step 3: Коммит**

```bash
git add docs/help
git commit -m "docs(help): команды и группы"
```

---

## Приёмка выпуска

- [ ] `py -3.10 -m pytest tests/ --ignore=tests/api/test_llm.py -q` — зелено
- [ ] `ruff check app/ tests/` и `mypy app/` — чисто
- [ ] `cd frontend && npm run lint && npm run build` — чисто
- [ ] `py -3.10 -m alembic upgrade head` на пустой базе — проходит
- [ ] Ручная проверка на команде без групп: стопка, ёмкость, сценарий, план выглядят как до правки
- [ ] Ручная проверка на «Команда 1С (Бухгалтерия)» с тремя группами: разрезы есть, суммы сходятся, человек не перегружен задачами из разных групп
