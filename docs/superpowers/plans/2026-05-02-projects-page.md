# Projects Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать `/projects` master-detail страницу анализа отдельного проекта с двумя режимами (Анализ/Презентация), AI-саммари через Gemini, оценкой заказчика и PDF-экспортом.

**Architecture:** Backend — миграции для 3 rating-полей и таблицы AI-кэша, LLM-адаптер с факторизацией под мульти-провайдеров, APScheduler ночной job + manual refresh endpoint. Frontend — master-detail layout с virtual scroll списком слева и переключаемыми Compact/Presentation видами справа, drill-in из Dashboard/Analytics/Backlog, клиентский PDF через `window.print()`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic batch migrations + APScheduler + httpx (Gemini), React 19 + TypeScript + AntD 6 + TanStack Query + Recharts.

**Spec:** [docs/superpowers/specs/2026-05-02-projects-page-design.md](../specs/2026-05-02-projects-page-design.md)

---

## File Structure

### Backend — создаются

- `alembic/versions/<hash>_add_rating_fields_to_issues.py` — миграция: 3 rating-колонки + 2 planned date колонки
- `alembic/versions/<hash>_create_project_ai_summary.py` — миграция: таблица AI-кэша
- `app/models/project_ai_summary.py` — модель `ProjectAISummary`
- `app/services/llm/__init__.py` — пакет
- `app/services/llm/types.py` — Pydantic-схемы (`ProjectSummary`, `FlowBlock`, `ChecklistItem`)
- `app/services/llm/base.py` — Protocol `LLMProvider` + factory
- `app/services/llm/gemini.py` — `GeminiProvider`
- `app/services/llm/prompt.py` — промпт-конструктор + `PROMPT_VERSION`
- `app/services/project_summary_service.py` — orchestrator (cache hit/miss + refresh)
- `app/services/projects_service.py` — list + detail aggregation
- `app/api/endpoints/llm.py` — `/llm/test`, `/llm/regenerate-all`
- `app/jobs/__init__.py` — пакет
- `app/jobs/regenerate_summaries.py` — APScheduler job
- `tests/services/llm/test_gemini.py`
- `tests/services/test_project_summary_service.py`
- `tests/services/test_projects_service.py`
- `tests/api/test_projects.py`
- `tests/api/test_llm.py`

### Backend — модифицируются

- `app/models/issue.py` — добавить 3 rating-колонки + 2 planned date колонки
- `app/models/__init__.py` — добавить `ProjectAISummary`
- `app/services/sync_service.py` — добавить sync 3 rating-полей и 2 planned-date полей
- `app/api/endpoints/projects.py` — расширить (список с метриками + detail + summary)
- `app/api/endpoints/settings.py` — `JIRA_FIELD_KEYS` дополнить, добавить `LLM_*` ключи
- `app/api/router.py` — register `llm.router`
- `app/main.py` — startup hook регистрирует APScheduler job

### Frontend — создаются

```
frontend/src/pages/ProjectsPage.tsx                     master-detail контейнер

frontend/src/api/projects.ts                            API клиент
frontend/src/api/llm.ts                                 LLM endpoints
frontend/src/hooks/useProjects.ts                       list + detail
frontend/src/hooks/useProjectSummary.ts                 AI summary + regenerate
frontend/src/types/projects.ts                          TS-типы

frontend/src/components/projects/ProjectsList.tsx
frontend/src/components/projects/ProjectListCard.tsx
frontend/src/components/projects/ProjectListFilters.tsx
frontend/src/components/projects/ProjectDetailPanel.tsx
frontend/src/components/projects/ProjectAnalysisView.tsx
frontend/src/components/projects/ProjectPresentationView.tsx
frontend/src/components/projects/ProjectHeader.tsx
frontend/src/components/projects/cards/ProjectGoalsCard.tsx
frontend/src/components/projects/cards/ProjectResultCard.tsx
frontend/src/components/projects/cards/ProjectStatusCard.tsx
frontend/src/components/projects/cards/ProjectCategoriesCard.tsx
frontend/src/components/projects/cards/ProjectEmployeesCard.tsx
frontend/src/components/projects/cards/ProjectKeyBlocksCard.tsx
frontend/src/components/projects/cards/ProjectRatingsCard.tsx
frontend/src/components/projects/cards/ProjectTopIssuesCard.tsx
frontend/src/components/projects/presentation/ProjectHero.tsx
frontend/src/components/projects/presentation/ProjectStorySection.tsx
frontend/src/components/projects/shared/StarRating.tsx
frontend/src/components/projects/shared/FlowDiagram.tsx
frontend/src/components/projects/shared/DonutChart.tsx
frontend/src/components/settings/AITab.tsx
frontend/src/styles/print.css

frontend/e2e/projects.spec.ts
```

### Frontend — модифицируются

- `frontend/src/main.tsx` — добавить `react-router` lazy роуты `/projects` и `/projects/:key`
- `frontend/src/pages/lazyPages.tsx` — `ProjectsPage` lazy export
- `frontend/src/components/MainLayout.tsx` — sidebar item «Проекты»
- `frontend/src/pages/SettingsPage.tsx` — добавить таб «AI»
- `frontend/src/components/dashboard/ProjectsWidget.tsx` — клик по строке → drill в `/projects/:key`
- `frontend/src/components/analytics/AnalyticsTable.tsx` (или по факту) — клик по проекту → drill в `/projects/:key`
- `frontend/src/components/backlog/BacklogList.tsx` (или эквивалент) — клик по карточке → drill

---

## Phase 1: Backend — Данные

### Task 1.1: Migration — rating columns + planned dates

**Files:**
- Create: `alembic/versions/<hash>_add_rating_fields_to_issues.py`

- [ ] **Step 1: Generate migration shell**

Run: `py -3.10 -m alembic revision -m "add_rating_fields_to_issues"`

- [ ] **Step 2: Fill in migration body**

```python
"""add_rating_fields_to_issues

Revision ID: <auto>
Revises: e97b35c021a7
Create Date: 2026-05-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<auto>'
down_revision: Union[str, None] = 'e97b35c021a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rating_quality', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rating_speed', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rating_result', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('planned_start_date', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('planned_end_date', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('planned_end_date')
        batch_op.drop_column('planned_start_date')
        batch_op.drop_column('rating_result')
        batch_op.drop_column('rating_speed')
        batch_op.drop_column('rating_quality')
```

- [ ] **Step 3: Run migration**

Run: `py -3.10 -m alembic upgrade head`
Expected: `Running upgrade e97b35c021a7 -> <hash>, add_rating_fields_to_issues`

- [ ] **Step 4: Update `app/models/issue.py`**

Add after `due_date` column:

```python
    # Customer ratings (Jira custom fields, 1-5 шкала)
    rating_quality: Mapped[Optional[int]] = mapped_column(nullable=True)
    rating_speed: Mapped[Optional[int]] = mapped_column(nullable=True)
    rating_result: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Plan dates (зарезервированы под будущий инструмент планирования)
    planned_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    planned_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 5: Commit**

```bash
git add app/models/issue.py alembic/versions/
git commit -m "feat(projects): миграция и поля рейтинга/плановых дат на Issue"
```

### Task 1.2: Migration — project_ai_summary table

**Files:**
- Create: `alembic/versions/<hash>_create_project_ai_summary.py`
- Create: `app/models/project_ai_summary.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Generate migration**

Run: `py -3.10 -m alembic revision -m "create_project_ai_summary"`

- [ ] **Step 2: Fill migration body**

```python
"""create_project_ai_summary

Revision ID: <auto>
Revises: <previous hash>
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '<auto>'
down_revision: Union[str, None] = '<rating_fields hash>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'project_ai_summaries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('issue_id', sa.String(36), sa.ForeignKey('issues.id', ondelete='CASCADE'),
                  nullable=False, unique=True, index=True),
        sa.Column('goals_json', sa.Text(), nullable=False),
        sa.Column('result_flow_json', sa.Text(), nullable=False),
        sa.Column('result_checklist_json', sa.Text(), nullable=False),
        sa.Column('status_text', sa.Text(), nullable=False),
        sa.Column('workload_summary', sa.Text(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('model_used', sa.String(64), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('prompt_version', sa.String(32), nullable=False, server_default='v1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('project_ai_summaries')
```

- [ ] **Step 3: Create model file**

`app/models/project_ai_summary.py`:
```python
"""ProjectAISummary — кэш AI-саммари по проекту (parent issue)."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import generate_uuid

if TYPE_CHECKING:
    from app.models.issue import Issue


class ProjectAISummary(Base):
    """AI-саммари проекта. Один на parent issue."""

    __tablename__ = "project_ai_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )
    goals_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_flow_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_checklist_json: Mapped[str] = mapped_column(Text, nullable=False)
    status_text: Mapped[str] = mapped_column(Text, nullable=False)
    workload_summary: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )

    issue: Mapped["Issue"] = relationship("Issue", lazy="joined")
```

- [ ] **Step 4: Register in `app/models/__init__.py`**

Add to imports (in alphabetical block):
```python
from app.models.project_ai_summary import ProjectAISummary
```
And to `__all__` list.

- [ ] **Step 5: Run migration**

Run: `py -3.10 -m alembic upgrade head`

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/ app/models/
git commit -m "feat(projects): таблица project_ai_summaries для AI-кэша"
```

### Task 1.3: Sync — pull rating fields

**Files:**
- Modify: `app/services/sync_service.py`

- [ ] **Step 1: Write failing test**

Create `tests/services/test_sync_ratings.py`:
```python
"""Sync 3 rating custom fields из Jira."""
import pytest
from unittest.mock import MagicMock

from app.models.issue import Issue
from app.models.app_setting import AppSetting
from app.services.sync_service import SyncService


def test_sync_pulls_ratings(test_db_session):
    """sync_issues пишет rating_quality/speed/result из custom fields."""
    db = test_db_session
    db.add(AppSetting(key="jira_rating_quality_field_id", value="customfield_99001"))
    db.add(AppSetting(key="jira_rating_speed_field_id", value="customfield_99002"))
    db.add(AppSetting(key="jira_rating_result_field_id", value="customfield_99003"))
    db.commit()

    service = SyncService(db)
    issue_data = MagicMock()
    issue_data.fields._extra = {
        "customfield_99001": 5,
        "customfield_99002": 4,
        "customfield_99003": 5,
    }
    issue_data.key = "PRJ-100"
    # ... full mock setup omitted for brevity, see existing test_sync_service.py patterns
    # Stub calls to verify Issue.rating_quality == 5 etc.
```

- [ ] **Step 2: Add rating field keys to sync_service**

In `app/services/sync_service.py` near existing `_PLANNED_NUMERIC_SETTING_KEYS`:
```python
_RATING_SETTING_KEYS = [
    "jira_rating_quality_field_id",
    "jira_rating_speed_field_id",
    "jira_rating_result_field_id",
]
_PLANNED_DATE_SETTING_KEYS = [
    "jira_planned_start_date_field_id",
    "jira_planned_end_date_field_id",
]
_ALL_PLANNED_KEYS = (
    _PLANNED_NUMERIC_SETTING_KEYS + _PLANNED_STRING_SETTING_KEYS
    + _RATING_SETTING_KEYS + _PLANNED_DATE_SETTING_KEYS
)
```

- [ ] **Step 3: Extract values in `_upsert_issue`**

Find existing block that reads `_extra` and adds plan fields. Add:
```python
# Customer ratings (1-5)
for field_key, attr in (
    ("jira_rating_quality_field_id", "rating_quality"),
    ("jira_rating_speed_field_id", "rating_speed"),
    ("jira_rating_result_field_id", "rating_result"),
):
    field_id = settings_map.get(field_key)
    if not field_id:
        continue
    raw = (extra or {}).get(field_id)
    parsed = _to_int_rating(raw)
    setattr(issue, attr, parsed)

# Plan dates
for field_key, attr in (
    ("jira_planned_start_date_field_id", "planned_start_date"),
    ("jira_planned_end_date_field_id", "planned_end_date"),
):
    field_id = settings_map.get(field_key)
    if not field_id:
        continue
    raw = (extra or {}).get(field_id)
    setattr(issue, attr, _parse_jira_date(raw))
```

- [ ] **Step 4: Add helper `_to_int_rating`**

In `app/services/sync_service.py` рядом с `_to_float`:
```python
def _to_int_rating(raw: Any) -> Optional[int]:
    """Coerce Jira rating field (str or number) → int 1-5 или None."""
    if raw is None:
        return None
    try:
        # Support shapes: 5, "5", "5.0", {"value": "5"}
        if isinstance(raw, dict):
            raw = raw.get("value")
        val = int(float(str(raw)))
        return val if 1 <= val <= 5 else None
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 5: Run test**

Run: `py -3.10 -m pytest tests/services/test_sync_ratings.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/sync_service.py tests/services/
git commit -m "feat(projects): sync рейтинговых полей и плановых дат из Jira"
```

### Task 1.4: Settings — register new field keys

**Files:**
- Modify: `app/api/endpoints/settings.py`

- [ ] **Step 1: Find `JIRA_FIELD_KEYS` constant or `jira_*_field_id` allow-list**

Likely in `settings.py` around `_get_setting`/`_set_setting` validation.

- [ ] **Step 2: Add 5 new field IDs to allow-list**

```python
JIRA_FIELD_KEYS = (
    # ... existing keys
    "jira_rating_quality_field_id",
    "jira_rating_speed_field_id",
    "jira_rating_result_field_id",
    "jira_planned_start_date_field_id",
    "jira_planned_end_date_field_id",
)
```

If validation uses pattern `key.startswith("jira_") and key.endswith("_field_id")` — already covered, no change needed. **Verify** by reading the validation code.

- [ ] **Step 3: Commit (если были изменения)**

```bash
git add app/api/endpoints/settings.py
git commit -m "feat(projects): allow-list для новых jira-field-id ключей"
```

### Task 1.5: ProjectsService — list with metrics

**Files:**
- Create: `app/services/projects_service.py`
- Create: `tests/services/test_projects_service.py`

- [ ] **Step 1: Write failing test**

`tests/services/test_projects_service.py`:
```python
"""ProjectsService.list_projects: фильтрация и метрики."""
import pytest
from datetime import datetime

from app.models.issue import Issue
from app.models.project import Project
from app.models.worklog import Worklog
from app.models.employee import Employee
from app.services.projects_service import ProjectsService


def test_list_projects_filters_by_quarterly_categories(test_db_session):
    db = test_db_session
    proj = Project(id="p1", key="PRJ", name="Project")
    db.add(proj)
    epic_quarterly = Issue(
        id="i1", jira_issue_id="1", key="PRJ-1", summary="A", issue_type="Epic",
        status="Done", project_id="p1", category="quarterly_tasks",
    )
    epic_archive = Issue(
        id="i2", jira_issue_id="2", key="PRJ-2", summary="B", issue_type="Epic",
        status="Done", project_id="p1", category="archive_target",
    )
    epic_other = Issue(
        id="i3", jira_issue_id="3", key="PRJ-3", summary="C", issue_type="Epic",
        status="Done", project_id="p1", category="tech_debt",
    )
    db.add_all([epic_quarterly, epic_archive, epic_other])
    db.commit()

    svc = ProjectsService(db)
    items = svc.list_projects(team_filter=None)
    keys = {item.key for item in items}
    assert keys == {"PRJ-1", "PRJ-2"}


def test_list_projects_includes_period_and_hours(test_db_session):
    db = test_db_session
    # ... setup parent issue + child + worklogs
    # assert item.period_start == min worklog, item.period_end == max worklog, item.total_hours == sum
```

Run: `py -3.10 -m pytest tests/services/test_projects_service.py -v` — FAIL (`projects_service` not found)

- [ ] **Step 2: Implement service skeleton**

`app/services/projects_service.py`:
```python
"""Сервис для страницы анализа проектов.

Проект = parent issue с категорией quarterly_tasks или archive_target.
Метрики: период (min/max worklog), часы, кол-во дочерних задач, участников,
оценки заказчика.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.worklog import Worklog
from app.models.employee import Employee


PROJECT_CATEGORY_CODES = ("quarterly_tasks", "archive_target")


@dataclass
class ProjectListItem:
    key: str
    summary: str
    status: str
    status_category: Optional[str]
    category: str
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    total_hours: float
    child_count: int
    employee_count: int
    rating_quality: Optional[int]
    rating_speed: Optional[int]
    rating_result: Optional[int]


class ProjectsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_projects(
        self,
        team_filter: Optional[list[str]] = None,
        category: Optional[str] = None,
        status_category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[ProjectListItem]:
        """Список проектов с агрегатами.

        team_filter — список команд из глобального фильтра. Проект попадает,
        если хотя бы один worklog принадлежит сотруднику этих команд.
        """
        # ... см. реализацию ниже
```

Implementation body для `list_projects`:
```python
        q = (
            select(Issue)
            .where(Issue.category.in_(PROJECT_CATEGORY_CODES))
            .where(Issue.include_in_analysis == True)
        )
        if category in PROJECT_CATEGORY_CODES:
            q = q.where(Issue.category == category)
        if status_category:
            q = q.where(Issue.status_category == status_category)
        if search:
            like = f"%{search.lower()}%"
            q = q.where(
                func.lower(Issue.summary).like(like) | func.lower(Issue.key).like(like)
            )
        epics = self.db.execute(q).scalars().all()

        items: list[ProjectListItem] = []
        for epic in epics:
            child_ids = self._collect_subtree(epic.id)
            all_ids = [epic.id, *child_ids]
            wl_query = select(Worklog).where(Worklog.issue_id.in_(all_ids))
            worklogs = self.db.execute(wl_query).scalars().all()

            if team_filter:
                emp_ids = {w.employee_id for w in worklogs}
                emps = self.db.execute(
                    select(Employee).where(Employee.id.in_(emp_ids))
                ).scalars().all()
                emp_teams = {e.id: e.team for e in emps}
                if not any(emp_teams.get(eid) in team_filter for eid in emp_ids):
                    continue

            total_hours = sum(w.hours or 0 for w in worklogs)
            employee_count = len({w.employee_id for w in worklogs})
            period_start = min((w.started_at for w in worklogs), default=None)
            period_end = max((w.started_at for w in worklogs), default=None)

            items.append(ProjectListItem(
                key=epic.key,
                summary=epic.summary,
                status=epic.status,
                status_category=epic.status_category,
                category=epic.category,
                period_start=period_start,
                period_end=period_end,
                total_hours=round(total_hours, 1),
                child_count=len(child_ids),
                employee_count=employee_count,
                rating_quality=epic.rating_quality,
                rating_speed=epic.rating_speed,
                rating_result=epic.rating_result,
            ))
        return items

    def _collect_subtree(self, issue_id: str) -> list[str]:
        """Все дочерние issue_id (рекурсивно)."""
        result: list[str] = []
        frontier = [issue_id]
        while frontier:
            children = self.db.execute(
                select(Issue.id).where(Issue.parent_id.in_(frontier))
            ).scalars().all()
            if not children:
                break
            result.extend(children)
            frontier = list(children)
        return result
```

- [ ] **Step 3: Run test, expect PASS**

Run: `py -3.10 -m pytest tests/services/test_projects_service.py -v`

- [ ] **Step 4: Commit**

```bash
git add app/services/projects_service.py tests/services/test_projects_service.py
git commit -m "feat(projects): ProjectsService.list_projects с метриками"
```

### Task 1.6: ProjectsService — detail aggregation

**Files:**
- Modify: `app/services/projects_service.py`
- Modify: `tests/services/test_projects_service.py`

- [ ] **Step 1: Write failing test**

```python
def test_get_project_detail_aggregates(test_db_session):
    db = test_db_session
    # setup parent + 3 children + 5 worklogs across 2 employees + 2 categories
    svc = ProjectsService(db)
    detail = svc.get_project_detail("PRJ-1")
    assert detail is not None
    assert detail.key == "PRJ-1"
    assert len(detail.categories) == 2
    assert len(detail.employees) == 2
    assert detail.top_issues[0].hours >= detail.top_issues[1].hours
```

- [ ] **Step 2: Implement `get_project_detail`**

Add dataclasses and method:
```python
@dataclass
class CategoryBreakdown:
    code: str
    label: str
    color: Optional[str]
    hours: float
    pct: float


@dataclass
class EmployeeBreakdown:
    employee_id: str
    name: str
    hours: float
    pct: float


@dataclass
class TopIssue:
    key: str
    summary: str
    hours: float


@dataclass
class ProjectDetail:
    key: str
    summary: str
    description: Optional[str]
    status: str
    status_category: Optional[str]
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    planned_start_date: Optional[datetime]
    planned_end_date: Optional[datetime]
    total_hours: float
    weeks: float
    child_count: int
    employee_count: int
    categories: list[CategoryBreakdown]
    employees: list[EmployeeBreakdown]
    top_issues: list[TopIssue]
    rating_quality: Optional[int]
    rating_speed: Optional[int]
    rating_result: Optional[int]


class ProjectsService:
    # ... existing methods

    def get_project_detail(self, key: str) -> Optional[ProjectDetail]:
        epic = self.db.execute(
            select(Issue).where(Issue.key == key)
        ).scalar_one_or_none()
        if not epic or epic.category not in PROJECT_CATEGORY_CODES:
            return None

        child_ids = self._collect_subtree(epic.id)
        all_ids = [epic.id, *child_ids]
        worklogs = self.db.execute(
            select(Worklog).where(Worklog.issue_id.in_(all_ids))
        ).scalars().all()

        total_hours = sum(w.hours or 0 for w in worklogs)
        period_start = min((w.started_at for w in worklogs), default=None)
        period_end = max((w.started_at for w in worklogs), default=None)
        weeks = ((period_end - period_start).days / 7.0) if period_start and period_end else 0.0

        # Categories breakdown — категория worklog'а наследуется от issue
        from app.models.category import Category
        cats = self.db.execute(select(Category)).scalars().all()
        cat_map = {c.code: c for c in cats}
        cat_hours: dict[str, float] = {}
        issue_cat = {
            i.id: i.category for i in
            self.db.execute(select(Issue).where(Issue.id.in_(all_ids))).scalars().all()
        }
        for w in worklogs:
            code = issue_cat.get(w.issue_id) or "uncategorized"
            cat_hours[code] = cat_hours.get(code, 0) + (w.hours or 0)
        categories = [
            CategoryBreakdown(
                code=code,
                label=cat_map[code].label if code in cat_map else code,
                color=cat_map[code].color if code in cat_map else None,
                hours=round(h, 1),
                pct=round((h / total_hours * 100) if total_hours else 0, 1),
            )
            for code, h in sorted(cat_hours.items(), key=lambda x: -x[1])
        ]

        # Employees breakdown
        emp_hours: dict[str, float] = {}
        for w in worklogs:
            emp_hours[w.employee_id] = emp_hours.get(w.employee_id, 0) + (w.hours or 0)
        emp_map = {
            e.id: e for e in
            self.db.execute(
                select(Employee).where(Employee.id.in_(emp_hours))
            ).scalars().all()
        }
        employees = [
            EmployeeBreakdown(
                employee_id=eid,
                name=emp_map[eid].display_name if eid in emp_map else eid,
                hours=round(h, 1),
                pct=round((h / total_hours * 100) if total_hours else 0, 1),
            )
            for eid, h in sorted(emp_hours.items(), key=lambda x: -x[1])
        ]

        # Top issues
        issue_hours: dict[str, float] = {}
        for w in worklogs:
            issue_hours[w.issue_id] = issue_hours.get(w.issue_id, 0) + (w.hours or 0)
        issue_map = {
            i.id: i for i in
            self.db.execute(select(Issue).where(Issue.id.in_(issue_hours))).scalars().all()
        }
        top = sorted(issue_hours.items(), key=lambda x: -x[1])[:5]
        top_issues = [
            TopIssue(
                key=issue_map[iid].key,
                summary=issue_map[iid].summary,
                hours=round(h, 1),
            )
            for iid, h in top if iid in issue_map
        ]

        return ProjectDetail(
            key=epic.key,
            summary=epic.summary,
            description=epic.description,
            status=epic.status,
            status_category=epic.status_category,
            period_start=period_start,
            period_end=period_end,
            planned_start_date=epic.planned_start_date,
            planned_end_date=epic.planned_end_date,
            total_hours=round(total_hours, 1),
            weeks=round(weeks, 1),
            child_count=len(child_ids),
            employee_count=len(emp_hours),
            categories=categories,
            employees=employees,
            top_issues=top_issues,
            rating_quality=epic.rating_quality,
            rating_speed=epic.rating_speed,
            rating_result=epic.rating_result,
        )
```

- [ ] **Step 3: Run test, expect PASS**

Run: `py -3.10 -m pytest tests/services/test_projects_service.py -v`

- [ ] **Step 4: Commit**

```bash
git add app/services/projects_service.py tests/services/
git commit -m "feat(projects): get_project_detail с агрегатами"
```

### Task 1.7: API endpoints — replace `/projects` with full router

**Files:**
- Modify: `app/api/endpoints/projects.py`
- Create: `tests/api/test_projects.py`

- [ ] **Step 1: Write failing tests**

`tests/api/test_projects.py`:
```python
"""API /projects: list + detail."""
from datetime import datetime
from app.models.issue import Issue
from app.models.project import Project


def test_list_projects_returns_only_quarterly(test_client, test_db_session):
    db = test_db_session
    db.add(Project(id="p1", key="PRJ", name="P"))
    db.add(Issue(id="i1", jira_issue_id="1", key="PRJ-1", summary="Q", issue_type="Epic",
                 status="Done", project_id="p1", category="quarterly_tasks"))
    db.add(Issue(id="i2", jira_issue_id="2", key="PRJ-2", summary="X", issue_type="Epic",
                 status="Done", project_id="p1", category="tech_debt"))
    db.commit()

    r = test_client.get("/api/v1/projects")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()}
    assert keys == {"PRJ-1"}


def test_get_project_detail_404_for_non_quarterly(test_client, test_db_session):
    # ... setup non-quarterly epic
    r = test_client.get("/api/v1/projects/PRJ-99")
    assert r.status_code == 404
```

- [ ] **Step 2: Replace projects.py implementation**

```python
"""Projects API — список и detail для страницы анализа проектов."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.projects_service import ProjectsService


router = APIRouter()


class ProjectListItemSchema(BaseModel):
    key: str
    summary: str
    status: str
    status_category: Optional[str]
    category: str
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    total_hours: float
    child_count: int
    employee_count: int
    rating_quality: Optional[int]
    rating_speed: Optional[int]
    rating_result: Optional[int]


class CategoryBreakdownSchema(BaseModel):
    code: str
    label: str
    color: Optional[str]
    hours: float
    pct: float


class EmployeeBreakdownSchema(BaseModel):
    employee_id: str
    name: str
    hours: float
    pct: float


class TopIssueSchema(BaseModel):
    key: str
    summary: str
    hours: float


class ProjectDetailSchema(BaseModel):
    key: str
    summary: str
    description: Optional[str]
    status: str
    status_category: Optional[str]
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    planned_start_date: Optional[datetime]
    planned_end_date: Optional[datetime]
    total_hours: float
    weeks: float
    child_count: int
    employee_count: int
    categories: List[CategoryBreakdownSchema]
    employees: List[EmployeeBreakdownSchema]
    top_issues: List[TopIssueSchema]
    rating_quality: Optional[int]
    rating_speed: Optional[int]
    rating_result: Optional[int]


@router.get("", response_model=List[ProjectListItemSchema])
def list_projects(
    teams: Optional[str] = Query(None, description="comma-separated team names"),
    category: Optional[str] = Query(None),
    status_category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Список проектов с метриками."""
    team_filter = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    items = ProjectsService(db).list_projects(
        team_filter=team_filter,
        category=category,
        status_category=status_category,
        search=search,
    )
    return [ProjectListItemSchema(**item.__dict__) for item in items]


@router.get("/{key}", response_model=ProjectDetailSchema)
def get_project(key: str, db: Session = Depends(get_db)):
    """Detail-блок для страницы проекта."""
    detail = ProjectsService(db).get_project_detail(key)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetailSchema(
        **{k: v for k, v in detail.__dict__.items()
           if k not in ("categories", "employees", "top_issues")},
        categories=[CategoryBreakdownSchema(**c.__dict__) for c in detail.categories],
        employees=[EmployeeBreakdownSchema(**e.__dict__) for e in detail.employees],
        top_issues=[TopIssueSchema(**t.__dict__) for t in detail.top_issues],
    )
```

**Note:** существующий `ProjectResponse` GET-list для list синхронизированных проектов СОХРАНИТЬ, переименовать роут в `/sync-projects` или новый prefix. Проверить какие фронтенд-места используют старый `/projects` — мигрировать.

Используй Grep `from.*api.*projects\|/projects` чтобы найти потребителей.

- [ ] **Step 3: Migrate existing consumers**

Найди вызовы старого `/projects` (вероятно в `frontend/src/api/client.ts` или хуках). Если используется old shape — добавь endpoint `/projects/legacy-list` с прежним телом или перенеси на новый `/sync-projects`. Решение принимается в момент миграции.

- [ ] **Step 4: Run tests**

Run: `py -3.10 -m pytest tests/api/test_projects.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/projects.py tests/api/test_projects.py
git commit -m "feat(projects): API /projects list + detail с агрегатами"
```

---

## Phase 2: LLM Infrastructure

### Task 2.1: LLM types + Protocol

**Files:**
- Create: `app/services/llm/__init__.py` (пустой)
- Create: `app/services/llm/types.py`
- Create: `app/services/llm/base.py`

- [ ] **Step 1: Pydantic schemas**

`app/services/llm/types.py`:
```python
"""Pydantic-схемы AI-результата."""
from typing import Literal
from pydantic import BaseModel, Field


class FlowBlock(BaseModel):
    label: str
    status: Literal["source", "flow", "done"] = "flow"


class ChecklistItem(BaseModel):
    label: str
    done: bool = True


class ProjectSummary(BaseModel):
    goals: list[str] = Field(min_length=1, max_length=5)
    result_flow_blocks: list[FlowBlock] = Field(min_length=1, max_length=6)
    result_checklist: list[ChecklistItem] = Field(min_length=0, max_length=6)
    status_text: str
    workload_summary: str
```

- [ ] **Step 2: Protocol + factory**

`app/services/llm/base.py`:
```python
"""LLM-провайдер интерфейс + factory.

Старт: только Gemini. DeepSeek/Anthropic/OpenAI — заглушки на будущее.
"""
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.api.endpoints.settings import _get_setting
from app.services.llm.types import ProjectSummary


class ConfigurationError(Exception):
    """Провайдер не сконфигурирован (нет ключа)."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    async def summarize_project(self, prompt: str, *, expect_json: bool = True) -> tuple[ProjectSummary, dict]:
        """Возвращает (parsed, meta) где meta содержит input_tokens/output_tokens."""
        ...

    async def healthcheck(self) -> bool:
        """Проверка соединения."""
        ...


def get_llm_provider(db: Session) -> LLMProvider:
    """Factory по AppSetting.llm_provider."""
    provider_name = (_get_setting(db, "llm_provider") or "gemini").lower()
    if provider_name == "gemini":
        from app.services.llm.gemini import GeminiProvider
        api_key = _get_setting(db, "llm_gemini_api_key")
        if not api_key:
            raise ConfigurationError("Gemini API key not configured")
        return GeminiProvider(api_key=api_key)
    raise ConfigurationError(f"LLM provider '{provider_name}' not supported")
```

- [ ] **Step 3: Commit**

```bash
git add app/services/llm/
git commit -m "feat(llm): протокол LLMProvider + types"
```

### Task 2.2: GeminiProvider

**Files:**
- Create: `app/services/llm/gemini.py`
- Create: `tests/services/llm/test_gemini.py`

- [ ] **Step 1: Write failing test**

`tests/services/llm/test_gemini.py`:
```python
"""GeminiProvider — структурированный JSON ответ через httpx-мок."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.llm.gemini import GeminiProvider
from app.services.llm.types import ProjectSummary


@pytest.mark.asyncio
async def test_summarize_returns_parsed_summary():
    provider = GeminiProvider(api_key="fake")
    fake_resp = {
        "candidates": [{
            "content": {"parts": [{"text": '{"goals":["g1","g2","g3"],'
                                          '"result_flow_blocks":[{"label":"A","status":"source"}],'
                                          '"result_checklist":[{"label":"x","done":true}],'
                                          '"status_text":"OK","workload_summary":"WS"}'}]},
        }],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
    }
    with patch.object(provider, "_post", AsyncMock(return_value=fake_resp)):
        summary, meta = await provider.summarize_project("test prompt")

    assert isinstance(summary, ProjectSummary)
    assert summary.goals == ["g1", "g2", "g3"]
    assert meta["input_tokens"] == 100
    assert meta["output_tokens"] == 50
```

- [ ] **Step 2: Implement provider**

`app/services/llm/gemini.py`:
```python
"""Google Gemini 2.0 Flash через AI Studio API.

Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
Free tier: 15 RPM, 1M токенов/день.
"""
import json
import logging
from typing import Any, Optional

import httpx

from app.services.llm.types import ProjectSummary


logger = logging.getLogger("jira_analytics.llm")


GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "goals": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
        "result_flow_blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "status": {"type": "string", "enum": ["source", "flow", "done"]},
                },
                "required": ["label", "status"],
            },
            "minItems": 1, "maxItems": 6,
        },
        "result_checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "done": {"type": "boolean"},
                },
                "required": ["label", "done"],
            },
            "minItems": 0, "maxItems": 6,
        },
        "status_text": {"type": "string"},
        "workload_summary": {"type": "string"},
    },
    "required": ["goals", "result_flow_blocks", "result_checklist", "status_text", "workload_summary"],
}


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model
        self._base = "https://generativelanguage.googleapis.com/v1beta/models"

    async def summarize_project(self, prompt: str, *, expect_json: bool = True) -> tuple[ProjectSummary, dict]:
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        if expect_json:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = GEMINI_RESPONSE_SCHEMA

        url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
        resp = await self._post(url, body)

        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Gemini вернул не-JSON. Fallback на text-mode не реализован.")
            raise

        meta = {
            "input_tokens": resp.get("usageMetadata", {}).get("promptTokenCount"),
            "output_tokens": resp.get("usageMetadata", {}).get("candidatesTokenCount"),
            "model": self.model,
        }
        return ProjectSummary.model_validate(data), meta

    async def healthcheck(self) -> bool:
        try:
            url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
            await self._post(url, {"contents": [{"parts": [{"text": "ping"}]}]})
            return True
        except Exception as e:
            logger.warning("Gemini healthcheck failed: %s", e)
            return False

    async def _post(self, url: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            return r.json()
```

- [ ] **Step 3: Run test, expect PASS**

Run: `py -3.10 -m pytest tests/services/llm/test_gemini.py -v`

- [ ] **Step 4: Commit**

```bash
git add app/services/llm/ tests/services/llm/
git commit -m "feat(llm): GeminiProvider с structured JSON output"
```

### Task 2.3: Settings — register LLM keys + AI tab endpoints

**Files:**
- Modify: `app/api/endpoints/settings.py`
- Create: `app/api/endpoints/llm.py`
- Modify: `app/api/router.py`

- [ ] **Step 1: Allow new keys**

In `app/api/endpoints/settings.py` validation/allowlist:
```python
LLM_KEYS = (
    "llm_provider",
    "llm_gemini_api_key",
    "llm_deepseek_api_key",
    "llm_anthropic_api_key",
    "llm_openai_api_key",
)
```
Update `_set_setting` validation to allow keys in `LLM_KEYS` (mirror jira_*_field_id pattern).

- [ ] **Step 2: Create LLM router**

`app/api/endpoints/llm.py`:
```python
"""LLM administration: test connection, regenerate-all."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.llm.base import ConfigurationError, get_llm_provider


router = APIRouter()


@router.post("/test")
async def test_connection(db: Session = Depends(get_db)):
    """Проверка соединения с настроенным провайдером."""
    try:
        provider = get_llm_provider(db)
    except ConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ok = await provider.healthcheck()
    return {"ok": ok, "provider": provider.name, "model": provider.model}
```

- [ ] **Step 3: Register router**

In `app/api/router.py`:
```python
from app.api.endpoints import llm as llm_endpoints
# ...
api_router.include_router(llm_endpoints.router, prefix="/llm", tags=["llm"])
```

- [ ] **Step 4: Test endpoint**

`tests/api/test_llm.py`:
```python
def test_llm_test_returns_400_without_key(test_client):
    r = test_client.post("/api/v1/llm/test")
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"]
```

Run: `py -3.10 -m pytest tests/api/test_llm.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/ app/api/router.py tests/api/test_llm.py
git commit -m "feat(llm): /llm/test endpoint + AppSetting LLM keys"
```

---

## Phase 3: AI Generation

### Task 3.1: Prompt builder

**Files:**
- Create: `app/services/llm/prompt.py`

- [ ] **Step 1: Implement prompt builder**

`app/services/llm/prompt.py`:
```python
"""Конструктор промпта для саммари проекта."""
from typing import Any


PROMPT_VERSION = "v1"


SYSTEM_INSTRUCTION = """\
Ты — аналитик проектов. На вход получаешь данные по Jira-эпику и его дочерним
задачам: описание, ключевые задачи, ворклоги по сотрудникам и категориям,
статус. Твоя задача — выдать краткое саммари ПОЛЬЗОВАТЕЛЯМ-PM на русском языке.

Формат строго JSON со следующими полями:
- goals: массив 3 строк, цели проекта (на основе описания эпика и задач). Максимум 80 символов на пункт.
- result_flow_blocks: массив 3-5 объектов {label, status}. Это интеграционный/процессный flow проекта. status ∈ ["source", "flow", "done"]. Первый — обычно "source", последний — "done" если проект готов, иначе "flow".
- result_checklist: массив 3-5 объектов {label, done}. Чек-лист достижений (например "11 дочерних задач", "полный контур").
- status_text: 1-2 предложения о текущем статусе проекта.
- workload_summary: 1 предложение о распределении нагрузки между сотрудниками.

Пиши лаконично, без воды. Не повторяй сами цифры из данных дословно.
"""


def build_prompt(epic_data: dict[str, Any]) -> str:
    """Build user prompt из агрегированных данных по эпику.

    epic_data ожидается в форме:
    {
        "key": "PRJ-1", "summary": "...", "description": "...",
        "status": "Done", "is_done": True,
        "child_count": 11, "employee_count": 7, "total_hours": 187.4,
        "period_start": "2026-02-12", "period_end": "2026-03-25",
        "categories": [{"label": "Аналитика", "hours": 57}, ...],
        "employees": [{"name": "Копышков Н.", "hours": 70.5, "pct": 37.6}, ...],
        "top_issues": [{"key": "PMD-1", "summary": "...", "hours": 49.5}, ...],
        "child_summaries": ["...", "..."]  # max 30 элементов
    }
    """
    parts: list[str] = [SYSTEM_INSTRUCTION, "", "ВХОДНЫЕ ДАННЫЕ:"]
    parts.append(f"Проект: {epic_data['summary']} ({epic_data['key']})")
    if epic_data.get("description"):
        desc = epic_data["description"][:1500]
        parts.append(f"Описание: {desc}")
    parts.append(f"Статус: {epic_data['status']} (закрыт: {epic_data.get('is_done', False)})")
    parts.append(
        f"Период: {epic_data.get('period_start')} → {epic_data.get('period_end')} "
        f"(всего {epic_data.get('total_hours', 0)} ч, {epic_data.get('child_count', 0)} задач, "
        f"{epic_data.get('employee_count', 0)} участников)"
    )

    parts.append("\nКатегории трудозатрат:")
    for c in epic_data.get("categories", [])[:8]:
        parts.append(f"  • {c['label']}: {c['hours']} ч")

    parts.append("\nУчастники:")
    for e in epic_data.get("employees", [])[:10]:
        parts.append(f"  • {e['name']}: {e['hours']} ч ({e.get('pct', 0)}%)")

    parts.append("\nТоп-задачи:")
    for t in epic_data.get("top_issues", [])[:5]:
        parts.append(f"  • {t['key']} — {t['summary']} ({t['hours']} ч)")

    summaries = epic_data.get("child_summaries", [])[:30]
    if summaries:
        parts.append("\nКраткий список дочерних задач:")
        for s in summaries:
            parts.append(f"  • {s}")

    parts.append("\nВЫДАЙ JSON РЕЗУЛЬТАТ.")
    return "\n".join(parts)
```

- [ ] **Step 2: Commit**

```bash
git add app/services/llm/prompt.py
git commit -m "feat(llm): конструктор промпта v1"
```

### Task 3.2: ProjectSummaryService — orchestrator

**Files:**
- Create: `app/services/project_summary_service.py`
- Create: `tests/services/test_project_summary_service.py`

- [ ] **Step 1: Write failing test**

```python
"""ProjectSummaryService: cache hit/miss + force regenerate."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from app.models.project_ai_summary import ProjectAISummary
from app.services.project_summary_service import ProjectSummaryService
from app.services.llm.types import ProjectSummary, FlowBlock, ChecklistItem


@pytest.mark.asyncio
async def test_cache_hit_returns_existing(test_db_session):
    db = test_db_session
    # ... setup epic + ProjectAISummary row
    svc = ProjectSummaryService(db)
    result = await svc.get_summary("PRJ-1")
    assert result.status_text == "Existing"


@pytest.mark.asyncio
async def test_force_regenerate_calls_llm(test_db_session):
    db = test_db_session
    # ... setup epic
    fake_summary = ProjectSummary(
        goals=["a", "b", "c"],
        result_flow_blocks=[FlowBlock(label="X", status="source")],
        result_checklist=[ChecklistItem(label="ok", done=True)],
        status_text="ST",
        workload_summary="WS",
    )
    with patch("app.services.project_summary_service.get_llm_provider") as gp:
        gp.return_value.summarize_project = AsyncMock(return_value=(fake_summary, {"input_tokens": 100, "output_tokens": 50, "model": "gemini-2.0-flash"}))
        result = await svc.regenerate("PRJ-1")
    assert result.status_text == "ST"
    saved = db.query(ProjectAISummary).first()
    assert saved.input_tokens == 100
```

- [ ] **Step 2: Implement service**

```python
"""ProjectSummaryService — оркестратор AI-саммари (cache + LLM)."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.project_ai_summary import ProjectAISummary
from app.services.llm.base import get_llm_provider
from app.services.llm.prompt import build_prompt, PROMPT_VERSION
from app.services.llm.types import ProjectSummary
from app.services.projects_service import ProjectsService


class ProjectSummaryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def get_summary(self, key: str) -> Optional[ProjectAISummary]:
        """Кэш-хит — возвращаем готовый. Кэш-мисс — None."""
        epic = self.db.execute(select(Issue).where(Issue.key == key)).scalar_one_or_none()
        if not epic:
            return None
        return self.db.execute(
            select(ProjectAISummary).where(ProjectAISummary.issue_id == epic.id)
        ).scalar_one_or_none()

    async def regenerate(self, key: str) -> ProjectAISummary:
        """Принудительная регенерация: вызов LLM + апсёрт в кэш."""
        epic = self.db.execute(select(Issue).where(Issue.key == key)).scalar_one_or_none()
        if not epic:
            raise ValueError(f"Issue {key} not found")

        epic_data = self._build_epic_data(epic)
        provider = get_llm_provider(self.db)
        prompt = build_prompt(epic_data)
        summary, meta = await provider.summarize_project(prompt)

        existing = self.db.execute(
            select(ProjectAISummary).where(ProjectAISummary.issue_id == epic.id)
        ).scalar_one_or_none()
        if existing:
            existing.goals_json = json.dumps(summary.goals, ensure_ascii=False)
            existing.result_flow_json = json.dumps(
                [b.model_dump() for b in summary.result_flow_blocks], ensure_ascii=False)
            existing.result_checklist_json = json.dumps(
                [c.model_dump() for c in summary.result_checklist], ensure_ascii=False)
            existing.status_text = summary.status_text
            existing.workload_summary = summary.workload_summary
            existing.generated_at = datetime.utcnow()
            existing.model_used = meta.get("model", provider.model)
            existing.input_tokens = meta.get("input_tokens")
            existing.output_tokens = meta.get("output_tokens")
            existing.prompt_version = PROMPT_VERSION
        else:
            existing = ProjectAISummary(
                issue_id=epic.id,
                goals_json=json.dumps(summary.goals, ensure_ascii=False),
                result_flow_json=json.dumps(
                    [b.model_dump() for b in summary.result_flow_blocks], ensure_ascii=False),
                result_checklist_json=json.dumps(
                    [c.model_dump() for c in summary.result_checklist], ensure_ascii=False),
                status_text=summary.status_text,
                workload_summary=summary.workload_summary,
                generated_at=datetime.utcnow(),
                model_used=meta.get("model", provider.model),
                input_tokens=meta.get("input_tokens"),
                output_tokens=meta.get("output_tokens"),
                prompt_version=PROMPT_VERSION,
            )
            self.db.add(existing)
        self.db.commit()
        self.db.refresh(existing)
        return existing

    def _build_epic_data(self, epic: Issue) -> dict:
        """Собрать данные для промпта."""
        detail = ProjectsService(self.db).get_project_detail(epic.key)
        if not detail:
            return {"key": epic.key, "summary": epic.summary}

        # Пройдём по дочерним задачам и снимем краткие саммари (top-30)
        from app.services.projects_service import PROJECT_CATEGORY_CODES
        child_ids = ProjectsService(self.db)._collect_subtree(epic.id)
        child_issues = self.db.execute(
            select(Issue).where(Issue.id.in_(child_ids))
        ).scalars().all()
        child_summaries = [f"{i.key}: {i.summary}" for i in child_issues[:30]]

        return {
            "key": epic.key,
            "summary": epic.summary,
            "description": epic.description or "",
            "status": epic.status,
            "is_done": epic.status_category == "done",
            "child_count": detail.child_count,
            "employee_count": detail.employee_count,
            "total_hours": detail.total_hours,
            "period_start": detail.period_start.date().isoformat() if detail.period_start else None,
            "period_end": detail.period_end.date().isoformat() if detail.period_end else None,
            "categories": [{"label": c.label, "hours": c.hours} for c in detail.categories],
            "employees": [
                {"name": e.name, "hours": e.hours, "pct": e.pct}
                for e in detail.employees
            ],
            "top_issues": [
                {"key": t.key, "summary": t.summary, "hours": t.hours}
                for t in detail.top_issues
            ],
            "child_summaries": child_summaries,
        }
```

- [ ] **Step 3: Run tests, fix to PASS**

Run: `py -3.10 -m pytest tests/services/test_project_summary_service.py -v`

- [ ] **Step 4: Commit**

```bash
git add app/services/project_summary_service.py tests/services/
git commit -m "feat(llm): ProjectSummaryService — кэш + регенерация"
```

### Task 3.3: API endpoints — summary + regenerate

**Files:**
- Modify: `app/api/endpoints/projects.py`

- [ ] **Step 1: Add schemas + endpoints**

В projects.py:
```python
import json
from app.services.project_summary_service import ProjectSummaryService


class ProjectSummarySchema(BaseModel):
    goals: List[str]
    result_flow_blocks: List[dict]
    result_checklist: List[dict]
    status_text: str
    workload_summary: str
    generated_at: datetime
    model_used: str


def _serialize_summary(row) -> ProjectSummarySchema:
    return ProjectSummarySchema(
        goals=json.loads(row.goals_json),
        result_flow_blocks=json.loads(row.result_flow_json),
        result_checklist=json.loads(row.result_checklist_json),
        status_text=row.status_text,
        workload_summary=row.workload_summary,
        generated_at=row.generated_at,
        model_used=row.model_used,
    )


@router.get("/{key}/summary", response_model=Optional[ProjectSummarySchema])
async def get_summary(key: str, db: Session = Depends(get_db)):
    row = await ProjectSummaryService(db).get_summary(key)
    return _serialize_summary(row) if row else None


@router.post("/{key}/regenerate-summary", response_model=ProjectSummarySchema)
async def regenerate_summary(key: str, db: Session = Depends(get_db)):
    try:
        row = await ProjectSummaryService(db).regenerate(key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # SSE event
    from app.services.event_broadcaster import publish
    publish("project_summary_generated", {"key": key})
    return _serialize_summary(row)
```

- [ ] **Step 2: Add tests**

`tests/api/test_projects.py`:
```python
def test_summary_returns_null_when_no_cache(test_client, test_db_session):
    # setup epic
    r = test_client.get("/api/v1/projects/PRJ-1/summary")
    assert r.status_code == 200
    assert r.json() is None
```

Run: `py -3.10 -m pytest tests/api/test_projects.py -v`

- [ ] **Step 3: Commit**

```bash
git add app/api/endpoints/projects.py tests/api/test_projects.py
git commit -m "feat(projects): /projects/{key}/summary + regenerate-summary"
```

### Task 3.4: APScheduler nightly job

**Files:**
- Create: `app/jobs/__init__.py`
- Create: `app/jobs/regenerate_summaries.py`
- Modify: `app/main.py`

- [ ] **Step 1: Implement job function**

`app/jobs/regenerate_summaries.py`:
```python
"""Ежедневный job: регенерация устаревших AI-саммари."""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.issue import Issue
from app.models.project_ai_summary import ProjectAISummary
from app.models.worklog import Worklog
from app.services.llm.prompt import PROMPT_VERSION
from app.services.project_summary_service import ProjectSummaryService
from app.services.projects_service import PROJECT_CATEGORY_CODES


logger = logging.getLogger("jira_analytics.jobs")
THROTTLE_SECONDS = 5  # rate-limit Gemini free tier (15 RPM)


async def regenerate_outdated_summaries() -> dict:
    """Регенерит саммари если worklogs изменились с последней генерации
    или изменилась версия промпта.

    Returns: {processed, regenerated, skipped, errors}
    """
    db = SessionLocal()
    try:
        epics = db.execute(
            select(Issue).where(Issue.category.in_(PROJECT_CATEGORY_CODES))
        ).scalars().all()

        stats = {"processed": 0, "regenerated": 0, "skipped": 0, "errors": 0}
        svc = ProjectSummaryService(db)

        for epic in epics:
            stats["processed"] += 1
            existing = db.execute(
                select(ProjectAISummary).where(ProjectAISummary.issue_id == epic.id)
            ).scalar_one_or_none()

            if not _needs_regeneration(db, epic, existing):
                stats["skipped"] += 1
                continue

            try:
                await svc.regenerate(epic.key)
                stats["regenerated"] += 1
                await asyncio.sleep(THROTTLE_SECONDS)
            except Exception as e:
                logger.exception("Regen failed for %s: %s", epic.key, e)
                stats["errors"] += 1

        logger.info("Nightly regen: %s", stats)
        return stats
    finally:
        db.close()


def _needs_regeneration(db: Session, epic: Issue, existing) -> bool:
    if existing is None:
        return True
    if existing.prompt_version != PROMPT_VERSION:
        return True
    # Любой worklog по эпику или его детям обновлялся после generated_at?
    from app.services.projects_service import ProjectsService
    child_ids = ProjectsService(db)._collect_subtree(epic.id)
    all_ids = [epic.id, *child_ids]
    last_wl = db.execute(
        select(Worklog.updated_at).where(Worklog.issue_id.in_(all_ids))
        .order_by(Worklog.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    if last_wl and last_wl > existing.generated_at:
        return True
    return False
```

- [ ] **Step 2: Register in startup**

In `app/main.py` найти существующий APScheduler init (sync consolidation memory) и добавить:
```python
from apscheduler.triggers.cron import CronTrigger
from app.jobs.regenerate_summaries import regenerate_outdated_summaries


@app.on_event("startup")
async def _start_scheduler():
    # ... existing scheduler setup
    scheduler.add_job(
        regenerate_outdated_summaries,
        trigger=CronTrigger(hour=3, minute=0),
        id="regenerate_summaries",
        replace_existing=True,
        max_instances=1,
    )
```

- [ ] **Step 3: Test job (smoke)**

`tests/jobs/test_regenerate_summaries.py`:
```python
import pytest
from unittest.mock import patch, AsyncMock
from app.jobs.regenerate_summaries import regenerate_outdated_summaries


@pytest.mark.asyncio
async def test_skips_when_cache_fresh():
    with patch("app.jobs.regenerate_summaries.SessionLocal") as session:
        # ... mock empty DB
        result = await regenerate_outdated_summaries()
    assert result["processed"] == 0
```

- [ ] **Step 4: Commit**

```bash
git add app/jobs/ app/main.py tests/jobs/
git commit -m "feat(llm): ночной cron регенерации устаревших AI-саммари"
```

### Task 3.5: Bulk regenerate endpoint

**Files:**
- Modify: `app/api/endpoints/llm.py`

- [ ] **Step 1: Add endpoint**

```python
from fastapi import BackgroundTasks
from app.jobs.regenerate_summaries import regenerate_outdated_summaries


@router.post("/regenerate-all")
async def regenerate_all(background: BackgroundTasks, db: Session = Depends(get_db)):
    """Запускает в background регенерацию всех устаревших саммари."""
    background.add_task(regenerate_outdated_summaries)
    return {"started": True}
```

- [ ] **Step 2: Commit**

```bash
git add app/api/endpoints/llm.py
git commit -m "feat(llm): /llm/regenerate-all для ручного запуска batch-регенерации"
```

---

## Phase 4: Frontend — каркас

### Task 4.1: Routing + sidebar

**Files:**
- Create: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/pages/lazyPages.tsx`
- Modify: `frontend/src/main.tsx` (или router file)
- Modify: `frontend/src/components/MainLayout.tsx`

- [ ] **Step 1: Create empty ProjectsPage**

```tsx
// frontend/src/pages/ProjectsPage.tsx
import React from 'react';

const ProjectsPage: React.FC = () => {
  return <div style={{ padding: 16 }}>Projects page (under construction)</div>;
};

export default ProjectsPage;
```

- [ ] **Step 2: Add lazy export**

In `frontend/src/pages/lazyPages.tsx`:
```tsx
export const ProjectsPage = lazy(() => import('./ProjectsPage'));
```

- [ ] **Step 3: Register routes**

In router config:
```tsx
{ path: '/projects', element: <ProjectsPage /> },
{ path: '/projects/:key', element: <ProjectsPage /> },
```

- [ ] **Step 4: Add sidebar item**

In `MainLayout.tsx` найти navigation items array (между Dashboard и Analytics) и добавить:
```tsx
{ key: '/projects', icon: <ProjectOutlined />, label: 'Проекты' },
```

- [ ] **Step 5: Verify route loads**

Run dev server, navigate to `/projects` → видна страница `Projects page (under construction)`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): /projects route + sidebar item"
```

### Task 4.2: API client + hooks

**Files:**
- Create: `frontend/src/api/projects.ts`
- Create: `frontend/src/hooks/useProjects.ts`
- Create: `frontend/src/hooks/useProjectSummary.ts`
- Create: `frontend/src/types/projects.ts`

- [ ] **Step 1: Types**

`frontend/src/types/projects.ts`:
```ts
export interface ProjectListItem {
  key: string;
  summary: string;
  status: string;
  status_category: 'new' | 'indeterminate' | 'done' | null;
  category: string;
  period_start: string | null;
  period_end: string | null;
  total_hours: number;
  child_count: number;
  employee_count: number;
  rating_quality: number | null;
  rating_speed: number | null;
  rating_result: number | null;
}

export interface CategoryBreakdown {
  code: string;
  label: string;
  color: string | null;
  hours: number;
  pct: number;
}

export interface EmployeeBreakdown {
  employee_id: string;
  name: string;
  hours: number;
  pct: number;
}

export interface TopIssue {
  key: string;
  summary: string;
  hours: number;
}

export interface ProjectDetail {
  key: string;
  summary: string;
  description: string | null;
  status: string;
  status_category: 'new' | 'indeterminate' | 'done' | null;
  period_start: string | null;
  period_end: string | null;
  planned_start_date: string | null;
  planned_end_date: string | null;
  total_hours: number;
  weeks: number;
  child_count: number;
  employee_count: number;
  categories: CategoryBreakdown[];
  employees: EmployeeBreakdown[];
  top_issues: TopIssue[];
  rating_quality: number | null;
  rating_speed: number | null;
  rating_result: number | null;
}

export interface FlowBlock {
  label: string;
  status: 'source' | 'flow' | 'done';
}

export interface ChecklistItem {
  label: string;
  done: boolean;
}

export interface ProjectSummary {
  goals: string[];
  result_flow_blocks: FlowBlock[];
  result_checklist: ChecklistItem[];
  status_text: string;
  workload_summary: string;
  generated_at: string;
  model_used: string;
}
```

- [ ] **Step 2: API client**

`frontend/src/api/projects.ts`:
```ts
import { api } from './client';
import type { ProjectListItem, ProjectDetail, ProjectSummary } from '../types/projects';

export const projectsApi = {
  list: (params: { teams?: string; category?: string; status_category?: string; search?: string }, signal?: AbortSignal) =>
    api.get<ProjectListItem[]>('/projects', params, signal),

  detail: (key: string, signal?: AbortSignal) =>
    api.get<ProjectDetail>(`/projects/${encodeURIComponent(key)}`, undefined, signal),

  summary: (key: string, signal?: AbortSignal) =>
    api.get<ProjectSummary | null>(`/projects/${encodeURIComponent(key)}/summary`, undefined, signal),

  regenerateSummary: (key: string) =>
    api.post<ProjectSummary>(`/projects/${encodeURIComponent(key)}/regenerate-summary`),
};
```

- [ ] **Step 3: Hooks**

`frontend/src/hooks/useProjects.ts`:
```ts
import { useQuery } from '@tanstack/react-query';
import { projectsApi } from '../api/projects';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';

export function useProjectsList(filters: { category?: string; status_category?: string; search?: string }) {
  const { selectedTeams } = useGlobalTeamFilter();
  return useQuery({
    queryKey: ['projects', selectedTeams, filters],
    queryFn: ({ signal }) =>
      projectsApi.list({
        teams: selectedTeams.join(',') || undefined,
        ...filters,
      }, signal),
    staleTime: 30_000,
  });
}

export function useProjectDetail(key: string | null) {
  return useQuery({
    queryKey: ['project-detail', key],
    queryFn: ({ signal }) => projectsApi.detail(key!, signal),
    enabled: !!key,
    staleTime: 30_000,
  });
}
```

`frontend/src/hooks/useProjectSummary.ts`:
```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../api/projects';

export function useProjectSummary(key: string | null) {
  return useQuery({
    queryKey: ['project-summary', key],
    queryFn: ({ signal }) => projectsApi.summary(key!, signal),
    enabled: !!key,
    staleTime: 60_000,
  });
}

export function useRegenerateSummary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => projectsApi.regenerateSummary(key),
    onSuccess: (_data, key) => {
      qc.invalidateQueries({ queryKey: ['project-summary', key] });
    },
  });
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/ frontend/src/hooks/ frontend/src/types/
git commit -m "feat(frontend): API + hooks для /projects"
```

### Task 4.3: Master-detail layout + ProjectsList

**Files:**
- Modify: `frontend/src/pages/ProjectsPage.tsx`
- Create: `frontend/src/components/projects/ProjectsList.tsx`
- Create: `frontend/src/components/projects/ProjectListCard.tsx`
- Create: `frontend/src/components/projects/ProjectListFilters.tsx`
- Create: `frontend/src/components/projects/ProjectDetailPanel.tsx`

- [ ] **Step 1: ProjectsList с virtual scroll**

`ProjectsList.tsx` (с использованием `react-virtual` либо `ant-design Virtual List`):
```tsx
import React from 'react';
import { Spin, Empty } from 'antd';
import { useProjectsList } from '../../hooks/useProjects';
import { ProjectListFilters, type Filters } from './ProjectListFilters';
import { ProjectListCard } from './ProjectListCard';
import type { ProjectListItem } from '../../types/projects';

interface Props {
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export const ProjectsList: React.FC<Props> = ({ selectedKey, onSelect }) => {
  const [filters, setFilters] = React.useState<Filters>({ statusFilter: 'all', categoryFilter: 'all', search: '' });
  const { data, isLoading } = useProjectsList({
    category: filters.categoryFilter === 'quarterly' ? 'quarterly_tasks'
            : filters.categoryFilter === 'archive'   ? 'archive_target' : undefined,
    status_category: filters.statusFilter === 'done' ? 'done'
                   : filters.statusFilter === 'active' ? 'indeterminate'
                   : undefined,
    search: filters.search || undefined,
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <ProjectListFilters value={filters} onChange={setFilters} />
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px' }}>
        {isLoading ? <Spin /> : (data?.length ?? 0) === 0 ? <Empty description="Нет проектов" /> :
          data!.map((item) => (
            <ProjectListCard
              key={item.key}
              item={item}
              selected={item.key === selectedKey}
              onClick={() => onSelect(item.key)}
            />
          ))
        }
      </div>
    </div>
  );
};
```

- [ ] **Step 2: ProjectListCard**

```tsx
// ProjectListCard.tsx — компактная карточка проекта
import React from 'react';
import type { ProjectListItem } from '../../types/projects';
import { StarRating } from './shared/StarRating';

const STATUS_BAR_COLOR: Record<string, string> = {
  done: '#67d68d',
  indeterminate: '#00c9c8',
  new: '#7e94b8',
};

interface Props {
  item: ProjectListItem;
  selected: boolean;
  onClick: () => void;
}

export const ProjectListCard: React.FC<Props> = ({ item, selected, onClick }) => {
  const period = item.period_start && item.period_end
    ? `${formatShortDate(item.period_start)}—${formatShortDate(item.period_end)}`
    : '—';
  return (
    <div
      onClick={onClick}
      style={{
        position: 'relative',
        background: selected ? 'rgba(0,201,200,0.12)' : '#0f2340',
        border: selected ? '1px solid #00c9c8' : '1px solid transparent',
        borderRadius: 6, padding: '10px 12px 10px 16px', marginBottom: 6, cursor: 'pointer',
      }}
    >
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
        background: STATUS_BAR_COLOR[item.status_category ?? 'new'] ?? '#7e94b8',
        borderRadius: '6px 0 0 6px',
      }} />
      <div style={{ color: '#7e94b8', fontSize: 11 }}>{item.key}</div>
      <div style={{ color: '#fff', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {item.summary}
      </div>
      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#7e94b8', marginTop: 4 }}>
        <span>{period}</span>
        <span>{item.total_hours}ч</span>
        <span>{item.child_count}з</span>
        <span>{item.employee_count}у</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
        <span style={{ fontSize: 11, color: '#cfd8e5' }}>{item.status}</span>
        {item.rating_quality && (
          <StarRating size={10} value={Math.round(((item.rating_quality + (item.rating_speed ?? 0) + (item.rating_result ?? 0)) / 3))} />
        )}
      </div>
    </div>
  );
};

function formatShortDate(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
}
```

- [ ] **Step 3: Filters component**

```tsx
// ProjectListFilters.tsx
import React from 'react';
import { Input, Radio, Select } from 'antd';

export interface Filters {
  statusFilter: 'all' | 'active' | 'done' | 'overdue';
  categoryFilter: 'all' | 'quarterly' | 'archive';
  search: string;
  sort?: 'period' | 'hours' | 'name';
}

export const ProjectListFilters: React.FC<{ value: Filters; onChange: (f: Filters) => void; }> = ({ value, onChange }) => (
  <div style={{ padding: 8, borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
    <Input.Search
      placeholder="Поиск по проекту..."
      allowClear
      value={value.search}
      onChange={(e) => onChange({ ...value, search: e.target.value })}
      style={{ marginBottom: 6 }}
    />
    <Radio.Group
      size="small"
      value={value.statusFilter}
      onChange={(e) => onChange({ ...value, statusFilter: e.target.value })}
      style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}
    >
      <Radio.Button value="all">Все</Radio.Button>
      <Radio.Button value="active">В работе</Radio.Button>
      <Radio.Button value="done">Готов</Radio.Button>
    </Radio.Group>
    <Radio.Group
      size="small"
      value={value.categoryFilter}
      onChange={(e) => onChange({ ...value, categoryFilter: e.target.value })}
      style={{ display: 'flex', gap: 4, marginTop: 6 }}
    >
      <Radio.Button value="all">Все</Radio.Button>
      <Radio.Button value="quarterly">Квартальные</Radio.Button>
      <Radio.Button value="archive">Архив</Radio.Button>
    </Radio.Group>
  </div>
);
```

- [ ] **Step 4: ProjectsPage master-detail**

```tsx
// ProjectsPage.tsx
import React from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';

const ProjectsPage: React.FC = () => {
  const { key } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 64px)' }}>
      <div style={{ width: 360, borderRight: '1px solid rgba(255,255,255,0.06)' }}>
        <ProjectsList
          selectedKey={key ?? null}
          onSelect={(k) => navigate(`/projects/${encodeURIComponent(k)}?${params.toString()}`)}
        />
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {key ? <ProjectDetailPanel projectKey={key} /> : <EmptyState />}
      </div>
    </div>
  );
};

const EmptyState: React.FC = () => (
  <div style={{ padding: 32, color: '#7e94b8', textAlign: 'center' }}>Выберите проект слева</div>
);

export default ProjectsPage;
```

- [ ] **Step 5: ProjectDetailPanel skeleton**

```tsx
// ProjectDetailPanel.tsx
import React from 'react';
import { useSearchParams } from 'react-router';
import { useProjectDetail } from '../../hooks/useProjects';
import { useProjectSummary } from '../../hooks/useProjectSummary';
import { ProjectAnalysisView } from './ProjectAnalysisView';
import { ProjectPresentationView } from './ProjectPresentationView';
import { ProjectHeader } from './ProjectHeader';
import { Spin } from 'antd';

export const ProjectDetailPanel: React.FC<{ projectKey: string }> = ({ projectKey }) => {
  const { data: detail, isLoading } = useProjectDetail(projectKey);
  const { data: summary } = useProjectSummary(projectKey);
  const [params, setParams] = useSearchParams();
  const view = params.get('view') === 'presentation' ? 'presentation' : 'analysis';

  const setView = (v: 'analysis' | 'presentation') => {
    if (v === 'presentation') params.set('view', 'presentation');
    else params.delete('view');
    setParams(params);
  };

  if (isLoading || !detail) return <Spin />;

  return (
    <div>
      <ProjectHeader detail={detail} summary={summary ?? null} view={view} onViewChange={setView} />
      {view === 'analysis'
        ? <ProjectAnalysisView detail={detail} summary={summary ?? null} />
        : <ProjectPresentationView detail={detail} summary={summary ?? null} />
      }
    </div>
  );
};
```

- [ ] **Step 6: Stub все views**

Создать `ProjectAnalysisView`, `ProjectPresentationView`, `ProjectHeader` как пустые placeholders — naполняем в Phase 5/6.

```tsx
// ProjectAnalysisView.tsx
export const ProjectAnalysisView: React.FC<{detail:any; summary:any}> = () =>
  <div style={{ padding: 16 }}>Analysis view</div>;
```

(аналогично для остальных)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): master-detail layout /projects + ProjectsList"
```

### Task 4.4: Shared components — StarRating, FlowDiagram, DonutChart

**Files:**
- Create: `frontend/src/components/projects/shared/StarRating.tsx`
- Create: `frontend/src/components/projects/shared/FlowDiagram.tsx`
- Create: `frontend/src/components/projects/shared/DonutChart.tsx`

- [ ] **Step 1: StarRating**

```tsx
// StarRating.tsx
import React from 'react';

interface Props { value: number; max?: number; size?: number; }

export const StarRating: React.FC<Props> = ({ value, max = 5, size = 18 }) => (
  <div style={{ display: 'inline-flex', gap: 2 }}>
    {Array.from({ length: max }).map((_, i) => (
      <svg key={i} width={size} height={size} viewBox="0 0 24 24" fill={i < value ? '#00c9c8' : '#2a3a5c'}>
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
      </svg>
    ))}
  </div>
);
```

- [ ] **Step 2: FlowDiagram**

```tsx
// FlowDiagram.tsx
import React from 'react';
import type { FlowBlock } from '../../../types/projects';

const BG: Record<FlowBlock['status'], string> = {
  source: '#0f2340',
  flow: '#0f2340',
  done: 'rgba(103, 214, 141, 0.16)',
};
const BORDER: Record<FlowBlock['status'], string> = {
  source: '#378ADD',
  flow: '#7e94b8',
  done: '#67d68d',
};

export const FlowDiagram: React.FC<{ blocks: FlowBlock[] }> = ({ blocks }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
    {blocks.map((b, i) => (
      <React.Fragment key={i}>
        <div style={{
          padding: '8px 14px', borderRadius: 6, background: BG[b.status],
          border: `1px solid ${BORDER[b.status]}`, color: '#fff', fontSize: 13, fontWeight: 500,
          whiteSpace: 'nowrap',
        }}>{b.label}</div>
        {i < blocks.length - 1 && <span style={{ color: '#7e94b8' }}>→</span>}
      </React.Fragment>
    ))}
  </div>
);
```

- [ ] **Step 3: DonutChart**

```tsx
// DonutChart.tsx — основан на Recharts PieChart
import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface Slice { code: string; label: string; hours: number; color: string; }

interface Props {
  slices: Slice[];
  centerValue?: string;
  centerLabel?: string;
  size?: number;
  onSliceClick?: (slice: Slice) => void;
}

export const DonutChart: React.FC<Props> = ({ slices, centerValue, centerLabel, size = 180, onSliceClick }) => (
  <div style={{ width: size, height: size, position: 'relative' }}>
    <ResponsiveContainer>
      <PieChart>
        <Pie
          data={slices}
          dataKey="hours"
          innerRadius={size * 0.35}
          outerRadius={size * 0.48}
          paddingAngle={1}
          stroke="none"
        >
          {slices.map((s, i) => (
            <Cell
              key={i}
              fill={s.color}
              onClick={onSliceClick ? () => onSliceClick(s) : undefined}
              style={onSliceClick ? { cursor: 'pointer' } : undefined}
            />
          ))}
        </Pie>
      </PieChart>
    </ResponsiveContainer>
    {centerValue && (
      <div style={{
        position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
      }}>
        <div style={{ fontSize: size * 0.18, fontWeight: 700, color: '#fff' }}>{centerValue}</div>
        {centerLabel && <div style={{ fontSize: 11, color: '#7e94b8' }}>{centerLabel}</div>}
      </div>
    )}
  </div>
);
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/projects/shared/
git commit -m "feat(frontend): shared StarRating + FlowDiagram + DonutChart"
```

---

## Phase 5: Compact view карточки

### Task 5.1: ProjectHeader

**Files:**
- Modify: `frontend/src/components/projects/ProjectHeader.tsx`

- [ ] **Step 1: Sticky header c toggle и кнопками**

```tsx
import React from 'react';
import { Button, Dropdown, Tag } from 'antd';
import { FilePdfOutlined, ReloadOutlined, MoreOutlined } from '@ant-design/icons';
import { useRegenerateSummary } from '../../hooks/useProjectSummary';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';

interface Props {
  detail: ProjectDetail;
  summary: ProjectSummary | null;
  view: 'analysis' | 'presentation';
  onViewChange: (v: 'analysis' | 'presentation') => void;
}

export const ProjectHeader: React.FC<Props> = ({ detail, summary, view, onViewChange }) => {
  const regen = useRegenerateSummary();
  const onPdf = () => {
    onViewChange('presentation');
    setTimeout(() => window.print(), 300);
  };
  return (
    <div style={{ position: 'sticky', top: 0, zIndex: 5, background: '#0d1c33',
                  borderBottom: '1px solid rgba(255,255,255,0.06)', padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 600, color: '#fff' }}>{detail.summary}</div>
          <div style={{ fontSize: 12, color: '#7e94b8', marginTop: 4 }}>
            <a href={`https://example.atlassian.net/browse/${detail.key}`} target="_blank" rel="noreferrer" style={{ color: '#00c9c8' }}>
              {detail.key}
            </a>
            {' · '}
            {formatPeriod(detail.period_start, detail.period_end)}
            {' · '}
            <Tag color={statusTagColor(detail.status_category)}>{detail.status}</Tag>
          </div>
          {summary && (
            <div style={{ fontSize: 11, color: '#7e94b8', marginTop: 4 }}>
              AI-резюме обновлено {new Date(summary.generated_at).toLocaleString('ru')}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Button.Group>
            <Button type={view === 'analysis' ? 'primary' : 'default'} onClick={() => onViewChange('analysis')}>Анализ</Button>
            <Button type={view === 'presentation' ? 'primary' : 'default'} onClick={() => onViewChange('presentation')}>Презентация</Button>
          </Button.Group>
          <Button icon={<ReloadOutlined />} loading={regen.isPending} onClick={() => regen.mutate(detail.key)}>
            Обновить AI
          </Button>
          <Button icon={<FilePdfOutlined />} onClick={onPdf}>PDF</Button>
          <Dropdown menu={{ items: [{ key: 'jira', label: 'Открыть в Jira' }] }}>
            <Button icon={<MoreOutlined />} />
          </Dropdown>
        </div>
      </div>
    </div>
  );
};

function formatPeriod(start: string | null, end: string | null): string {
  if (!start || !end) return 'без периода';
  return `${new Date(start).toLocaleDateString('ru')} — ${new Date(end).toLocaleDateString('ru')}`;
}

function statusTagColor(cat: string | null): string {
  if (cat === 'done') return 'green';
  if (cat === 'indeterminate') return 'cyan';
  return 'default';
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/projects/ProjectHeader.tsx
git commit -m "feat(frontend): ProjectHeader с toggle Анализ/Презентация и PDF"
```

### Task 5.2: ProjectAnalysisView — 2-column grid

**Files:**
- Modify: `frontend/src/components/projects/ProjectAnalysisView.tsx`

- [ ] **Step 1: 2-column grid с placeholder cards**

```tsx
import React from 'react';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';
import { ProjectGoalsCard } from './cards/ProjectGoalsCard';
import { ProjectCategoriesCard } from './cards/ProjectCategoriesCard';
import { ProjectEmployeesCard } from './cards/ProjectEmployeesCard';
import { ProjectResultCard } from './cards/ProjectResultCard';
import { ProjectStatusCard } from './cards/ProjectStatusCard';
import { ProjectKeyBlocksCard } from './cards/ProjectKeyBlocksCard';
import { ProjectRatingsCard } from './cards/ProjectRatingsCard';
import { ProjectTopIssuesCard } from './cards/ProjectTopIssuesCard';

interface Props { detail: ProjectDetail; summary: ProjectSummary | null; }

export const ProjectAnalysisView: React.FC<Props> = ({ detail, summary }) => (
  <div style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <ProjectGoalsCard summary={summary} description={detail.description} />
      <ProjectCategoriesCard categories={detail.categories} totalHours={detail.total_hours} weeks={detail.weeks} projectKey={detail.key} />
      <ProjectEmployeesCard employees={detail.employees} projectKey={detail.key} />
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <ProjectResultCard summary={summary} childCount={detail.child_count} employeeCount={detail.employee_count} />
      <ProjectStatusCard summary={summary} detail={detail} />
      <ProjectKeyBlocksCard categories={detail.categories} projectKey={detail.key} />
      <ProjectRatingsCard detail={detail} summary={summary} />
      <ProjectTopIssuesCard topIssues={detail.top_issues} projectKey={detail.key} />
    </div>
  </div>
);
```

- [ ] **Step 2: Создать пустые stub'ы для каждой карточки**

8 файлов в `cards/`. Например:
```tsx
// ProjectGoalsCard.tsx (заглушка)
export const ProjectGoalsCard: React.FC<{ summary: any; description: any }> = ({ summary }) =>
  <div className="card-stub">Goals: {summary?.goals?.length ?? 0}</div>;
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/projects/
git commit -m "feat(frontend): ProjectAnalysisView 2-col grid + stub карточки"
```

### Task 5.3: ProjectGoalsCard

**Files:**
- Modify: `frontend/src/components/projects/cards/ProjectGoalsCard.tsx`

- [ ] **Step 1: Реализация**

```tsx
import React from 'react';
import { Card, Empty } from 'antd';
import type { ProjectSummary } from '../../../types/projects';

const MARKER_COLORS = ['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', '#ff4d4f'];

export const ProjectGoalsCard: React.FC<{ summary: ProjectSummary | null; description: string | null }> = ({ summary, description }) => (
  <Card title="Цели проекта" size="small">
    {summary?.goals.length ? (
      <ol style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
        {summary.goals.map((g, i) => (
          <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
            <span style={{
              flexShrink: 0, width: 24, height: 24, borderRadius: '50%',
              background: MARKER_COLORS[i % MARKER_COLORS.length], color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 700,
            }}>{i + 1}</span>
            <span style={{ color: '#cfd8e5', fontSize: 13 }}>{g}</span>
          </li>
        ))}
      </ol>
    ) : description ? (
      <div style={{ color: '#cfd8e5', fontSize: 13, whiteSpace: 'pre-wrap' }}>{description.slice(0, 600)}</div>
    ) : (
      <Empty description="AI-цели генерируются" />
    )}
  </Card>
);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/projects/cards/ProjectGoalsCard.tsx
git commit -m "feat(frontend): ProjectGoalsCard"
```

### Task 5.4: ProjectCategoriesCard (donut + список)

**Files:**
- Modify: `frontend/src/components/projects/cards/ProjectCategoriesCard.tsx`

- [ ] **Step 1: Реализация**

```tsx
import React from 'react';
import { Card } from 'antd';
import { useNavigate } from 'react-router';
import { DonutChart } from '../shared/DonutChart';
import type { CategoryBreakdown } from '../../../types/projects';

interface Props {
  categories: CategoryBreakdown[];
  totalHours: number;
  weeks: number;
  projectKey: string;
}

export const ProjectCategoriesCard: React.FC<Props> = ({ categories, totalHours, weeks, projectKey }) => {
  const navigate = useNavigate();
  const slices = categories.map(c => ({ code: c.code, label: c.label, hours: c.hours, color: c.color || '#7e94b8' }));
  const onClick = (slice: any) =>
    navigate(`/analytics?category=${encodeURIComponent(slice.code)}&project=${encodeURIComponent(projectKey)}`);

  return (
    <Card title="Структура трудозатрат" size="small">
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <DonutChart
          slices={slices}
          centerValue={`${totalHours} ч`}
          centerLabel={weeks ? `~${weeks} нед` : undefined}
          size={160}
          onSliceClick={onClick}
        />
        <div style={{ flex: 1 }}>
          {categories.map(c => (
            <div key={c.code} onClick={() => onClick(c)}
                 style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0',
                          fontSize: 13, color: '#cfd8e5', cursor: 'pointer' }}>
              <span>
                <span style={{
                  display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                  background: c.color || '#7e94b8', marginRight: 8,
                }} />
                {c.label}
              </span>
              <span><b>{c.hours}</b> ч <span style={{ color: '#7e94b8' }}>({c.pct}%)</span></span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/projects/cards/ProjectCategoriesCard.tsx
git commit -m "feat(frontend): ProjectCategoriesCard donut + drill"
```

### Task 5.5: ProjectEmployeesCard

**Files:**
- Modify: `frontend/src/components/projects/cards/ProjectEmployeesCard.tsx`

- [ ] **Step 1: Реализация**

```tsx
import React from 'react';
import { Card } from 'antd';
import { useNavigate } from 'react-router';
import type { EmployeeBreakdown } from '../../../types/projects';

interface Props { employees: EmployeeBreakdown[]; projectKey: string; }

const COLORS = ['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', '#7e94b8', '#7e94b8', '#7e94b8'];

export const ProjectEmployeesCard: React.FC<Props> = ({ employees, projectKey }) => {
  const navigate = useNavigate();
  const max = Math.max(1, employees[0]?.hours ?? 1);
  return (
    <Card title="Участники" size="small">
      {employees.map((e, i) => (
        <div key={e.employee_id} onClick={() => navigate(`/analytics?employee=${encodeURIComponent(e.employee_id)}&project=${encodeURIComponent(projectKey)}`)}
             style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', cursor: 'pointer' }}>
          <div style={{ width: 28, height: 28, borderRadius: '50%', background: COLORS[i % COLORS.length],
                        color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 11, fontWeight: 700 }}>
            {initials(e.name)}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, color: '#cfd8e5' }}>{e.name}</div>
            <div style={{ height: 4, background: 'rgba(255,255,255,0.05)', borderRadius: 2, marginTop: 2 }}>
              <div style={{ width: `${(e.hours / max) * 100}%`, height: '100%', background: COLORS[i % COLORS.length], borderRadius: 2 }} />
            </div>
          </div>
          <div style={{ width: 80, textAlign: 'right', fontSize: 13 }}>
            <b>{e.hours}</b> ч <span style={{ color: '#7e94b8' }}>({e.pct}%)</span>
          </div>
        </div>
      ))}
    </Card>
  );
};

function initials(name: string): string {
  const parts = name.split(/\s+/);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase();
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/projects/cards/ProjectEmployeesCard.tsx
git commit -m "feat(frontend): ProjectEmployeesCard"
```

### Task 5.6: ProjectResultCard, ProjectStatusCard, ProjectKeyBlocksCard, ProjectRatingsCard, ProjectTopIssuesCard

**Files:** все 5 файлов в `cards/`

- [ ] **Step 1: ProjectResultCard**

```tsx
import { Card, Empty } from 'antd';
import { CheckCircleFilled } from '@ant-design/icons';
import { FlowDiagram } from '../shared/FlowDiagram';
import type { ProjectSummary } from '../../../types/projects';

export const ProjectResultCard: React.FC<{ summary: ProjectSummary | null; childCount: number; employeeCount: number }> = ({ summary, childCount, employeeCount }) => (
  <Card title="Основной результат" size="small">
    {!summary ? <Empty description="AI-резюме генерируется" /> : (
      <>
        <FlowDiagram blocks={summary.result_flow_blocks} />
        <div style={{ marginTop: 12, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {summary.result_checklist.map((c, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#cfd8e5' }}>
              <CheckCircleFilled style={{ color: c.done ? '#67d68d' : '#7e94b8' }} />
              {c.label}
            </div>
          ))}
        </div>
      </>
    )}
  </Card>
);
```

- [ ] **Step 2: ProjectStatusCard**

```tsx
export const ProjectStatusCard: React.FC<{ summary: ProjectSummary | null; detail: ProjectDetail }> = ({ summary, detail }) => (
  <Card title="Статус проекта" size="small">
    {summary && <div style={{ color: '#67d68d', marginBottom: 12, fontSize: 13 }}>{summary.status_text}</div>}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
      <Tile value={detail.child_count} label="Задач" />
      <Tile value={detail.total_hours} label="Часов" valueColor="#faad14" />
      <Tile value={detail.employee_count} label="Участников" />
      <Tile value={detail.weeks} label="Недель" />
    </div>
  </Card>
);

const Tile: React.FC<{ value: number; label: string; valueColor?: string }> = ({ value, label, valueColor }) => (
  <div style={{ background: '#091527', borderRadius: 4, padding: '10px 12px', textAlign: 'center' }}>
    <div style={{ fontSize: 22, fontWeight: 700, color: valueColor ?? '#fff' }}>{value}</div>
    <div style={{ fontSize: 11, color: '#7e94b8', textTransform: 'uppercase' }}>{label}</div>
  </div>
);
```

- [ ] **Step 3: ProjectKeyBlocksCard**

Top-3 категории как progress-bars.

```tsx
export const ProjectKeyBlocksCard: React.FC<{ categories: CategoryBreakdown[]; projectKey: string }> = ({ categories, projectKey }) => {
  const navigate = useNavigate();
  const top = categories.slice(0, 3);
  const max = Math.max(1, top[0]?.hours ?? 1);
  return (
    <Card title="Ключевые блоки" size="small">
      {top.map(c => (
        <div key={c.code} onClick={() => navigate(`/analytics?category=${encodeURIComponent(c.code)}&project=${encodeURIComponent(projectKey)}`)}
             style={{ marginBottom: 10, cursor: 'pointer' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
            <span style={{ color: '#cfd8e5' }}>{c.label}</span>
            <span style={{ color: '#fff' }}><b>{c.hours}</b> ч</span>
          </div>
          <div style={{ height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3 }}>
            <div style={{ width: `${(c.hours / max) * 100}%`, height: '100%', background: c.color || '#7e94b8', borderRadius: 3 }} />
          </div>
        </div>
      ))}
    </Card>
  );
};
```

- [ ] **Step 4: ProjectRatingsCard**

```tsx
export const ProjectRatingsCard: React.FC<{ detail: ProjectDetail; summary: ProjectSummary | null }> = ({ detail, summary }) => {
  if (!detail.rating_quality && !detail.rating_speed && !detail.rating_result) return null;
  return (
    <Card title="Оценка заказчика" size="small">
      <RatingRow label="Качество" value={detail.rating_quality} />
      <RatingRow label="Скорость" value={detail.rating_speed} />
      <RatingRow label="Результат" value={detail.rating_result} />
      {summary?.workload_summary && (
        <div style={{ marginTop: 12, padding: 8, background: '#091527', borderRadius: 4, fontSize: 12, color: '#cfd8e5' }}>
          {summary.workload_summary}
        </div>
      )}
    </Card>
  );
};

const RatingRow: React.FC<{ label: string; value: number | null }> = ({ label, value }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0' }}>
    <span style={{ color: '#cfd8e5', fontSize: 13 }}>{label}</span>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <StarRating value={value ?? 0} size={18} />
      <span style={{ color: '#fff', fontSize: 13 }}><b>{value ?? '—'}</b>/5</span>
    </div>
  </div>
);
```

- [ ] **Step 5: ProjectTopIssuesCard**

```tsx
export const ProjectTopIssuesCard: React.FC<{ topIssues: TopIssue[]; projectKey: string }> = ({ topIssues, projectKey }) => {
  const navigate = useNavigate();
  return (
    <Card title="Топ-3 задачи по трудозатратам" size="small">
      {topIssues.slice(0, 3).map((t, i) => (
        <div key={t.key} onClick={() => navigate(`/analytics?issue=${encodeURIComponent(t.key)}`)}
             style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', cursor: 'pointer' }}>
          <span style={{ color: '#cfd8e5', fontSize: 13 }}>
            <span style={{ color: '#7e94b8', marginRight: 8 }}>{i + 1}.</span>
            <span style={{ color: '#00c9c8', marginRight: 8 }}>{t.key}</span>
            {t.summary}
          </span>
          <span style={{ color: '#fff', fontSize: 13 }}><b>{t.hours}</b> ч</span>
        </div>
      ))}
    </Card>
  );
};
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/projects/cards/
git commit -m "feat(frontend): остальные карточки Compact view (Result/Status/KeyBlocks/Ratings/TopIssues)"
```

---

## Phase 6: Presentation view + PDF

### Task 6.1: ProjectPresentationView (Story layout)

**Files:**
- Modify: `frontend/src/components/projects/ProjectPresentationView.tsx`
- Create: `frontend/src/components/projects/presentation/ProjectHero.tsx`
- Create: `frontend/src/components/projects/presentation/ProjectStorySection.tsx`

- [ ] **Step 1: ProjectHero**

```tsx
import React from 'react';
import { Tag } from 'antd';
import { StarRating } from '../shared/StarRating';
import type { ProjectDetail } from '../../../types/projects';

export const ProjectHero: React.FC<{ detail: ProjectDetail }> = ({ detail }) => (
  <div style={{ padding: '32px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
    <div style={{ fontSize: 11, color: '#7e94b8', letterSpacing: 1, textTransform: 'uppercase' }}>
      Проект {detail.key}
    </div>
    <h1 style={{ margin: '8px 0 16px', fontSize: 36, fontWeight: 700, color: '#fff' }}>{detail.summary}</h1>
    <div style={{ fontSize: 13, color: '#cfd8e5', marginBottom: 20 }}>
      {formatPeriod(detail.period_start, detail.period_end)}
      {' · '}
      <Tag color={statusTagColor(detail.status_category)}>{detail.status}</Tag>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
      <BigTile value={detail.total_hours} label="Часов" sub={`~${detail.weeks} нед`} />
      <BigTile value={detail.child_count} label="Задач" />
      <BigTile value={detail.employee_count} label="Участников" />
    </div>
  </div>
);

const BigTile: React.FC<{ value: number | string; label: string; sub?: string }> = ({ value, label, sub }) => (
  <div style={{ background: '#0f2340', borderRadius: 8, padding: '20px 24px', textAlign: 'center' }}>
    <div style={{ fontSize: 36, fontWeight: 700, color: '#fff' }}>{value}</div>
    <div style={{ fontSize: 12, color: '#7e94b8', textTransform: 'uppercase', marginTop: 4 }}>{label}</div>
    {sub && <div style={{ fontSize: 11, color: '#7e94b8', marginTop: 2 }}>{sub}</div>}
  </div>
);

function formatPeriod(s: string | null, e: string | null) {
  if (!s || !e) return 'без периода';
  return `${new Date(s).toLocaleDateString('ru')} — ${new Date(e).toLocaleDateString('ru')}`;
}
function statusTagColor(c: string | null) {
  if (c === 'done') return 'green';
  if (c === 'indeterminate') return 'cyan';
  return 'default';
}
```

- [ ] **Step 2: ProjectStorySection**

```tsx
export const ProjectStorySection: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="story-section" style={{ padding: '32px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
    <h2 style={{ fontSize: 28, fontWeight: 600, color: '#fff', marginBottom: 16 }}>{title}</h2>
    {children}
  </section>
);
```

- [ ] **Step 3: ProjectPresentationView**

```tsx
import React from 'react';
import { ProjectHero } from './presentation/ProjectHero';
import { ProjectStorySection } from './presentation/ProjectStorySection';
import { FlowDiagram } from './shared/FlowDiagram';
import { DonutChart } from './shared/DonutChart';
import { StarRating } from './shared/StarRating';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';

export const ProjectPresentationView: React.FC<{ detail: ProjectDetail; summary: ProjectSummary | null }> = ({ detail, summary }) => (
  <div className="presentation-view" style={{ maxWidth: 960, margin: '0 auto' }}>
    <ProjectHero detail={detail} />

    {summary && (
      <ProjectStorySection title="Что мы делали">
        <ol style={{ paddingLeft: 0, listStyle: 'none' }}>
          {summary.goals.map((g, i) => (
            <li key={i} style={{ display: 'flex', gap: 16, marginBottom: 16, fontSize: 16, color: '#cfd8e5' }}>
              <span style={{ flexShrink: 0, fontSize: 28, fontWeight: 700, color: '#00c9c8', lineHeight: 1 }}>{i + 1}</span>
              <span>{g}</span>
            </li>
          ))}
        </ol>
        {detail.description && <p style={{ marginTop: 16, color: '#7e94b8', whiteSpace: 'pre-wrap' }}>{detail.description.slice(0, 800)}</p>}
      </ProjectStorySection>
    )}

    {summary && (
      <ProjectStorySection title="Какой результат">
        <FlowDiagram blocks={summary.result_flow_blocks} />
        <p style={{ marginTop: 16, fontSize: 16, color: '#67d68d' }}>{summary.status_text}</p>
      </ProjectStorySection>
    )}

    <ProjectStorySection title="Кто работал">
      {detail.employees.map((e, i) => {
        const max = Math.max(1, detail.employees[0]?.hours ?? 1);
        return (
          <div key={e.employee_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0' }}>
            <div style={{ flex: 1, fontSize: 14, color: i < 2 ? '#fff' : '#cfd8e5' }}>{e.name}</div>
            <div style={{ flex: 2, height: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 4 }}>
              <div style={{ width: `${(e.hours / max) * 100}%`, height: '100%', background: '#00c9c8', borderRadius: 4 }} />
            </div>
            <div style={{ width: 100, textAlign: 'right', fontSize: 14 }}>
              <b>{e.hours}</b> ч ({e.pct}%)
            </div>
          </div>
        );
      })}
    </ProjectStorySection>

    <ProjectStorySection title="На что ушло время">
      <div style={{ display: 'flex', gap: 32 }}>
        <DonutChart slices={detail.categories.map(c => ({ code: c.code, label: c.label, hours: c.hours, color: c.color || '#7e94b8' }))}
                    centerValue={`${detail.total_hours} ч`} centerLabel={`~${detail.weeks} нед`} size={240} />
        <div style={{ flex: 1 }}>
          {detail.categories.map(c => (
            <div key={c.code} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                <span style={{ color: '#cfd8e5' }}>{c.label}</span>
                <span style={{ color: '#fff' }}><b>{c.hours}</b> ч ({c.pct}%)</span>
              </div>
              <div style={{ height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3, marginTop: 4 }}>
                <div style={{ width: `${c.pct}%`, height: '100%', background: c.color || '#7e94b8', borderRadius: 3 }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      <h3 style={{ marginTop: 24, fontSize: 18, color: '#fff' }}>Топ-3 задачи</h3>
      {detail.top_issues.slice(0, 3).map((t, i) => (
        <div key={t.key} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: 14 }}>
          <span style={{ color: '#cfd8e5' }}>
            <span style={{ color: '#7e94b8', marginRight: 8 }}>{i + 1}.</span>
            <span style={{ color: '#00c9c8', marginRight: 8 }}>{t.key}</span>
            {t.summary}
          </span>
          <span><b>{t.hours}</b> ч</span>
        </div>
      ))}
    </ProjectStorySection>

    {(detail.rating_quality || detail.rating_speed || detail.rating_result) && (
      <ProjectStorySection title="Как оценили">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>
          {[
            { label: 'Качество', value: detail.rating_quality },
            { label: 'Скорость', value: detail.rating_speed },
            { label: 'Результат', value: detail.rating_result },
          ].map((r, i) => (
            <div key={i} style={{ background: '#0f2340', borderRadius: 8, padding: 24, textAlign: 'center' }}>
              <div style={{ fontSize: 14, color: '#7e94b8', marginBottom: 12 }}>{r.label}</div>
              <StarRating value={r.value ?? 0} size={32} />
              <div style={{ fontSize: 22, fontWeight: 700, color: '#fff', marginTop: 8 }}>{r.value ?? '—'} / 5</div>
            </div>
          ))}
        </div>
        {summary?.workload_summary && <p style={{ marginTop: 24, fontSize: 14, color: '#cfd8e5' }}>{summary.workload_summary}</p>}
      </ProjectStorySection>
    )}
  </div>
);
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/projects/
git commit -m "feat(frontend): ProjectPresentationView (Story режим)"
```

### Task 6.2: Print CSS

**Files:**
- Create: `frontend/src/styles/print.css`
- Modify: `frontend/src/components/projects/ProjectPresentationView.tsx` (импорт)

- [ ] **Step 1: print.css**

```css
@media print {
  body { background: #fff !important; color: #000 !important; }
  .ant-layout-sider, .ant-layout-header, .header-actions, .ant-tabs-nav { display: none !important; }
  .presentation-view { max-width: 100% !important; padding: 0 !important; }
  .story-section { page-break-inside: avoid; padding: 24px 0 !important; }
  .ant-card, .presentation-view * {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  @page { size: A4 portrait; margin: 12mm; }
}
```

- [ ] **Step 2: Импорт в ProjectsPage или PresentationView**

В ProjectsPage.tsx или main.tsx:
```tsx
import './styles/print.css';
```

- [ ] **Step 3: Test print preview**

Откой DevTools → "More tools → Rendering → Emulate CSS media type → print". Проверить что sidebar скрыт, секции читаются.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/print.css frontend/src/
git commit -m "feat(frontend): print CSS для PDF-экспорта Презентации"
```

---

## Phase 7: AI Settings tab + drill-in из других страниц

### Task 7.1: AI Settings tab

**Files:**
- Create: `frontend/src/components/settings/AITab.tsx`
- Create: `frontend/src/api/llm.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: API client**

```tsx
// frontend/src/api/llm.ts
import { api } from './client';

export const llmApi = {
  test: () => api.post<{ ok: boolean; provider: string; model: string }>('/llm/test'),
  regenerateAll: () => api.post('/llm/regenerate-all'),
};
```

- [ ] **Step 2: AITab компонент**

```tsx
import React from 'react';
import { Button, Card, Form, Input, Select, message } from 'antd';
import { llmApi } from '../../api/llm';
import { settingsApi } from '../../api/settings';  // adapt to existing helper

export const AITab: React.FC = () => {
  const [form] = Form.useForm();
  // Load existing AppSetting values via settingsApi.getGeneric('llm_provider'), etc.
  const onTest = async () => {
    try {
      const r = await llmApi.test();
      message[r.ok ? 'success' : 'warning'](`${r.provider} ${r.model}: ${r.ok ? 'OK' : 'FAIL'}`);
    } catch (e: any) {
      message.error(e.message || 'Ошибка');
    }
  };
  const onRegenAll = async () => {
    await llmApi.regenerateAll();
    message.info('Регенерация запущена в фоне');
  };
  const onSave = async (values: any) => {
    await settingsApi.setGeneric('llm_provider', values.provider);
    await settingsApi.setGeneric('llm_gemini_api_key', values.gemini_key);
    message.success('Сохранено');
  };
  return (
    <Card title="AI-провайдер" extra={<Button onClick={onRegenAll}>Перегенерировать все саммари</Button>}>
      <Form form={form} layout="vertical" onFinish={onSave}>
        <Form.Item label="Провайдер" name="provider" initialValue="gemini">
          <Select options={[
            { value: 'gemini', label: 'Google Gemini 2.0 Flash (рекомендуется)' },
            { value: 'deepseek', label: 'DeepSeek V3 (заглушка)', disabled: true },
            { value: 'anthropic', label: 'Anthropic Claude (заглушка)', disabled: true },
            { value: 'openai', label: 'OpenAI GPT (заглушка)', disabled: true },
          ]} />
        </Form.Item>
        <Form.Item label="API key (Gemini)" name="gemini_key">
          <Input.Password placeholder="AIza..." />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">Сохранить</Button>
          <Button onClick={onTest} style={{ marginLeft: 8 }}>Проверить подключение</Button>
        </Form.Item>
      </Form>
    </Card>
  );
};
```

- [ ] **Step 3: Register tab**

В `SettingsPage.tsx` добавить элемент в массив `tabs`:
```tsx
{ key: 'ai', label: 'AI', children: <AITab /> }
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings/AITab.tsx frontend/src/api/llm.ts frontend/src/pages/SettingsPage.tsx
git commit -m "feat(settings): таб AI с конфигурацией Gemini"
```

### Task 7.2: Drill-in из Dashboard ProjectsWidget

**Files:**
- Modify: `frontend/src/components/dashboard/ProjectsWidget.tsx`

- [ ] **Step 1: Найти row-render и добавить onClick**

Поиск по файлу: `<tr` или `onRowClick` или эквивалент. Добавить:
```tsx
onClick={() => navigate(`/projects/${encodeURIComponent(project.key)}`)}
style={{ cursor: 'pointer' }}
```

Учесть: `useNavigate` уже импортирован (см. начало файла).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/dashboard/ProjectsWidget.tsx
git commit -m "feat(frontend): drill из Dashboard ProjectsWidget на /projects/:key"
```

### Task 7.3: Drill-in из Analytics

**Files:**
- Modify: соответствующий компонент Analytics (см. `pages/AnalyticsPage.tsx`)

- [ ] **Step 1: Найти render строки-проекта в Analytics-дереве**

Найти где renderится строка с `issue.issue_type === 'Epic'` или категория = quarterly/archive_target.

- [ ] **Step 2: Добавить кнопку drill**

```tsx
{(item.category === 'quarterly_tasks' || item.category === 'archive_target') && (
  <Button size="small" type="link" onClick={() => navigate(`/projects/${item.key}`)}>
    Открыть проект
  </Button>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(analytics): drill из Analytics в /projects/:key"
```

### Task 7.4: Drill-in из Backlog

**Files:**
- Modify: `frontend/src/components/backlog/*` (точное место найти Grep'ом)

- [ ] **Step 1: Найти карточку backlog-item с Jira-ключом**

Поиск: `BacklogItem` rendering.

- [ ] **Step 2: Добавить link**

```tsx
{item.jira_key && (
  <Button size="small" onClick={() => navigate(`/projects/${item.jira_key}`)}>
    Открыть
  </Button>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(backlog): drill из Backlog на /projects/:key"
```

---

## Phase 8: Tests + Polish

### Task 8.1: Frontend component tests

**Files:**
- Create: `frontend/src/components/projects/__tests__/ProjectsList.test.tsx`
- Create: `frontend/src/components/projects/__tests__/ProjectAnalysisView.test.tsx`

- [ ] **Step 1: ProjectsList тест**

(Если в проекте используется Vitest или RTL — смотри существующие тесты в `frontend/src/components/__tests__/`. Если их нет — пропустить.)

```tsx
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProjectsList } from '../ProjectsList';

// mock useProjectsList to return fixed list
test('renders project cards', () => {
  // ...
});
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/projects/__tests__/
git commit -m "test(frontend): unit тесты ProjectsList и AnalysisView"
```

### Task 8.2: E2E test

**Files:**
- Create: `frontend/e2e/projects.spec.ts`

- [ ] **Step 1: Playwright spec**

```ts
import { test, expect } from '@playwright/test';

test('open projects page and select project', async ({ page }) => {
  await page.goto('http://localhost:5174/projects');
  await expect(page.getByText('Выберите проект слева')).toBeVisible();
  // Если в e2e.db есть seeded epic с категорией quarterly_tasks — клик
  const firstCard = page.locator('[data-testid="project-card"]').first();
  if (await firstCard.count() > 0) {
    await firstCard.click();
    await expect(page.locator('[data-testid="project-header"]')).toBeVisible();
  }
});

test('toggle Анализ ↔ Презентация', async ({ page }) => {
  await page.goto('http://localhost:5174/projects/PRJ-1');
  await page.getByRole('button', { name: 'Презентация' }).click();
  await expect(page).toHaveURL(/view=presentation/);
});
```

Добавить `data-testid` атрибуты в ProjectListCard и ProjectHeader для тест-селекторов.

- [ ] **Step 2: Run E2E**

Run: `npm run e2e -- --project=projects`

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/projects.spec.ts frontend/src/
git commit -m "test(e2e): /projects страница навигация и режимы"
```

### Task 8.3: Polish — empty states, error toasts, AI loading

**Files:**
- Различные компоненты

- [ ] **Step 1: Empty state на пустом списке**

Уже есть в ProjectsList, проверить визуал.

- [ ] **Step 2: Error toast при regenerate failure**

В `useRegenerateSummary`:
```tsx
onError: (e: any) => message.error(`Регенерация не удалась: ${e.message}`)
```

- [ ] **Step 3: Skeleton при первой загрузке summary**

В `ProjectGoalsCard` и `ProjectResultCard` — `{!summary && isFetching && <Skeleton active />}`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "polish(projects): empty states + error toasts + skeleton"
```

### Task 8.4: Final manual smoke test

- [ ] **Step 1: Запустить backend + frontend**

```bash
py -3.10 scripts/local_smoke.py
```

- [ ] **Step 2: Manual checklist**

- [ ] Открыть `/projects` — список загружается
- [ ] Поиск/фильтры работают
- [ ] Клик по карточке → выбран проект, URL обновился
- [ ] В правой панели рендерится Анализ
- [ ] Toggle «Презентация» → URL `?view=presentation`, layout сменился
- [ ] Кнопка «Скачать PDF» → переключилась в Презентация → открылся print dialog
- [ ] Кнопка «Обновить AI» (с настроенным Gemini ключом) → крутится спиннер → обновился timestamp
- [ ] Без Gemini ключа: кнопка возвращает 400 с понятной ошибкой
- [ ] `/settings → AI`: сохранение ключа + кнопка «Проверить» → success/fail toast
- [ ] Drill из Dashboard ProjectsWidget → правильный проект
- [ ] Drill из Analytics → правильный проект
- [ ] Глобальный team filter ограничивает список

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat(projects): MVP завершён, smoke-тесты passed"
```

---

## Self-Review Notes

**Spec coverage:** все 8 фаз спеки покрыты. URL routing — Task 4.1. List + filters — 4.3. Compact view — Phase 5. Presentation + PDF — Phase 6. AI infrastructure — Phase 2-3. Ratings — Task 1.1, 1.3, 1.4. Period — Task 1.5, 1.6. Drill-in — Phase 7.

**Type consistency:** `ProjectListItem` / `ProjectDetail` / `ProjectSummary` / `FlowBlock` / `ChecklistItem` — единые имена backend dataclass ↔ Pydantic ↔ TS interface. `result_flow_blocks`, `result_checklist`, `goals_json` — snake_case в БД и API, snake_case в TS (без преобразования). `PROJECT_CATEGORY_CODES` — единый источник в `projects_service.py`.

**Risks flagged in spec:** Gemini rate limit (throttle 5с в job), JSON parsing fallback (raise — без fallback в MVP), multi-user concurrency на cron + manual (max_instances=1 в job, manual идёт через API не блокируя), PDF качество (Chrome/Edge OK, Firefox compromise).

**Что в плане НЕ покрыто (deferred to post-MVP):**
- Серверный playwright PDF-рендер
- DeepSeek/Anthropic/OpenAI providers (только заглушки)
- Toast/SSE-уведомление о завершении ночного cron
- Fallback на text-mode для Gemini если schema не сработала
- Advisory lock на issue_id для concurrency cron+manual

Эти пункты — задел в спеке, не блокируют MVP.
