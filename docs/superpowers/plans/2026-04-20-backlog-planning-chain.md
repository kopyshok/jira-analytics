# Backlog → Scenarios Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Наполнить «Бэклог инициатив» автоматически из Jira-задач категории `initiatives_backlog` с оценками по ролям (analyst/dev/qa/opo); переделать страницу `/planning` под прототип с интерактивным расчётом capacity по ролям; поддержать ручные записи с последующей привязкой к RFA/ITL.

**Architecture:** Одна миграция добавляет поля оценок на `issues` и `backlog_items`, seed-категория `initiatives_backlog`, новые AppSetting ключи для customfield IDs. `sync_service` расширяется извлечением планов из Jira. `BacklogService.sync_from_issue` авто-создаёт/обновляет записи бэклога. `CapacityService.team_role_capacity` + `PlanningService.generate_scenario` считают demand/capacity по 3 ролям; ОПЭ-часы делятся через `BacklogItem.opo_analyst_ratio`. Frontend: меню reorder, JiraFieldsCard расширен, BacklogPage получает новые колонки + manual modal + link-to-jira, PlanningPage полностью переписывается под дизайн-прототип.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic (batch mode for SQLite), pytest, React 19 + TypeScript + Ant Design 6 + TanStack Query + Playwright.

**Spec:** [docs/superpowers/specs/2026-04-20-backlog-planning-chain-design.md](../specs/2026-04-20-backlog-planning-chain-design.md)

---

## File Map

### Backend — create
- `alembic/versions/022_backlog_planning_chain.py`
- `app/services/backlog_service.py` (new file)
- `tests/test_backlog_sync.py`
- `tests/test_api_backlog_link.py`
- `tests/test_capacity_role.py`
- `tests/test_planning_role_allocation.py`

### Backend — modify
- `app/models/issue.py` — add 4 planned_hours + 4 involvement + 4 duration + impact + risk columns
- `app/models/backlog_item.py` — add issue_id FK + 4 estimate_hours + opo_analyst_ratio + impact + risk
- `app/services/sync_service.py` — extend `_list_custom_field_ids`, `_upsert_issue` extraction
- `app/services/capacity_service.py` — add `team_role_capacity`
- `app/services/planning_service.py` — per-role greedy allocation
- `app/api/endpoints/backlog.py` — extend CRUD; add link-jira/unlink-jira/refresh
- `app/api/endpoints/planning.py` — add `/capacity-preview`
- `app/api/endpoints/issue_config.py` — trigger BacklogService after category change
- `app/schemas/backlog.py` — extend request/response
- `app/schemas/planning.py` — add capacity-preview schemas
- `tests/test_sync_service.py` — new customfields tests
- `tests/test_api_planning.py` — new endpoint tests

### Frontend — create
- `frontend/src/components/backlog/BacklogManualModal.tsx`
- `frontend/src/components/backlog/BacklogLinkJiraModal.tsx`
- `frontend/src/components/planning/PlanningCapacityPanel.tsx`
- `frontend/src/components/planning/PlanningBacklogList.tsx`
- `frontend/src/components/planning/RoleCapacityBar.tsx`

### Frontend — modify
- `frontend/src/components/Layout/SideMenu.tsx` — reorder groups
- `frontend/src/components/JiraFieldsCard.tsx` — add 14 new fields
- `frontend/src/pages/EmployeesPage.tsx` — role dropdown
- `frontend/src/pages/BacklogPage.tsx` — redesign columns
- `frontend/src/pages/PlanningPage.tsx` — full rewrite under prototype
- `frontend/src/utils/constants.ts` — ROLE_COLORS, ROLE_LABELS, ROLE_SHORT
- `frontend/src/api/backlog.ts` — link/unlink/refresh
- `frontend/src/api/planning.ts` — capacity-preview
- `frontend/src/hooks/useBacklog.ts` — link/unlink mutations
- `frontend/src/hooks/usePlanning.ts` — capacity-preview query
- `frontend/src/types/backlog.ts` — new fields
- `frontend/src/types/planning.ts` — capacity-preview types
- `frontend/e2e/crud-flows.spec.ts` — manual-item E2E

---

## Batch 1 — Data model + Jira sync extraction (backend)

### Task 1: Alembic migration 022 — schema changes

**Files:**
- Create: `alembic/versions/022_backlog_planning_chain.py`

- [ ] **Step 1: Write migration file**

```python
"""Backlog→Scenarios chain: issue planned hours, backlog item roles, seed category.

Revision ID: 022_backlog_planning_chain
Revises: 021_capacity_v3
Create Date: 2026-04-20
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "022_backlog_planning_chain"
down_revision: Union[str, None] = "021_capacity_v3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_CATEGORY = (
    "initiatives_backlog",
    "Бэклог инициатив",
    "#7F77DD",
    22,
    True,  # is_system
)

NEW_SETTING_KEYS = [
    "jira_planned_analyst_hours_field_id",
    "jira_planned_dev_hours_field_id",
    "jira_planned_qa_hours_field_id",
    "jira_planned_opo_hours_field_id",
    "jira_involvement_analyst_field_id",
    "jira_involvement_dev_field_id",
    "jira_involvement_qa_field_id",
    "jira_involvement_launch_field_id",
    "jira_duration_analyst_field_id",
    "jira_duration_dev_field_id",
    "jira_duration_qa_field_id",
    "jira_duration_launch_field_id",
    "jira_impact_field_id",
    "jira_risk_field_id",
]


def upgrade() -> None:
    # --- Issue columns ---
    with op.batch_alter_table("issues") as b:
        b.add_column(sa.Column("planned_analyst_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("planned_dev_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("planned_qa_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("planned_opo_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("involvement_analyst", sa.Float(), nullable=True))
        b.add_column(sa.Column("involvement_dev", sa.Float(), nullable=True))
        b.add_column(sa.Column("involvement_qa", sa.Float(), nullable=True))
        b.add_column(sa.Column("involvement_launch", sa.Float(), nullable=True))
        b.add_column(sa.Column("duration_analyst_days", sa.Float(), nullable=True))
        b.add_column(sa.Column("duration_dev_days", sa.Float(), nullable=True))
        b.add_column(sa.Column("duration_qa_days", sa.Float(), nullable=True))
        b.add_column(sa.Column("duration_launch_days", sa.Float(), nullable=True))
        b.add_column(sa.Column("impact", sa.String(20), nullable=True))
        b.add_column(sa.Column("risk", sa.String(20), nullable=True))

    # --- BacklogItem columns ---
    with op.batch_alter_table("backlog_items") as b:
        b.add_column(sa.Column("issue_id", sa.String(36), nullable=True))
        b.add_column(sa.Column("estimate_analyst_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("estimate_dev_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("estimate_qa_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("estimate_opo_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("opo_analyst_ratio", sa.Float(), nullable=True, server_default="0.5"))
        b.add_column(sa.Column("impact", sa.String(20), nullable=True))
        b.add_column(sa.Column("risk", sa.String(20), nullable=True))
        b.create_foreign_key(
            "fk_backlog_items_issue_id", "issues", ["issue_id"], ["id"], ondelete="SET NULL"
        )
        b.create_index("ix_backlog_items_issue_id", ["issue_id"], unique=True)

    # --- Seed category ---
    cats = sa.Table(
        "categories",
        sa.MetaData(),
        sa.Column("id", sa.String(36)),
        sa.Column("code", sa.String(50)),
        sa.Column("label", sa.String(100)),
        sa.Column("color", sa.String(20)),
        sa.Column("sort_order", sa.Integer),
        sa.Column("is_system", sa.Boolean),
        sa.Column("is_active", sa.Boolean),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    code, label, color, sort_order, is_system = SEED_CATEGORY
    existing = op.get_bind().execute(
        sa.text("SELECT id FROM categories WHERE code = :c"), {"c": code}
    ).fetchone()
    if not existing:
        now = datetime.utcnow()
        op.get_bind().execute(
            cats.insert().values(
                id=str(uuid.uuid4()),
                code=code,
                label=label,
                color=color,
                sort_order=sort_order,
                is_system=is_system,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )

    # --- Seed AppSetting keys with empty value ---
    app_settings = sa.Table(
        "app_settings",
        sa.MetaData(),
        sa.Column("key", sa.String),
        sa.Column("value", sa.Text),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    bind = op.get_bind()
    for k in NEW_SETTING_KEYS:
        found = bind.execute(
            sa.text("SELECT key FROM app_settings WHERE key = :k"), {"k": k}
        ).fetchone()
        if not found:
            now = datetime.utcnow()
            bind.execute(
                app_settings.insert().values(key=k, value="", created_at=now, updated_at=now)
            )


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as b:
        b.drop_index("ix_backlog_items_issue_id")
        b.drop_constraint("fk_backlog_items_issue_id", type_="foreignkey")
        for col in [
            "risk", "impact", "opo_analyst_ratio",
            "estimate_opo_hours", "estimate_qa_hours",
            "estimate_dev_hours", "estimate_analyst_hours", "issue_id",
        ]:
            b.drop_column(col)

    with op.batch_alter_table("issues") as b:
        for col in [
            "risk", "impact",
            "duration_launch_days", "duration_qa_days",
            "duration_dev_days", "duration_analyst_days",
            "involvement_launch", "involvement_qa",
            "involvement_dev", "involvement_analyst",
            "planned_opo_hours", "planned_qa_hours",
            "planned_dev_hours", "planned_analyst_hours",
        ]:
            b.drop_column(col)

    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM categories WHERE code = 'initiatives_backlog'"))
    for k in [
        "jira_planned_analyst_hours_field_id", "jira_planned_dev_hours_field_id",
        "jira_planned_qa_hours_field_id", "jira_planned_opo_hours_field_id",
        "jira_involvement_analyst_field_id", "jira_involvement_dev_field_id",
        "jira_involvement_qa_field_id", "jira_involvement_launch_field_id",
        "jira_duration_analyst_field_id", "jira_duration_dev_field_id",
        "jira_duration_qa_field_id", "jira_duration_launch_field_id",
        "jira_impact_field_id", "jira_risk_field_id",
    ]:
        bind.execute(sa.text("DELETE FROM app_settings WHERE key = :k"), {"k": k})
```

- [ ] **Step 2: Run migration + verify**

```bash
alembic upgrade head
```

Expected: no errors, new tables inspected via `sqlite3 data/analysis.db '.schema issues'` show new columns.

- [ ] **Step 3: Run downgrade/upgrade roundtrip**

```bash
alembic downgrade -1 && alembic upgrade head
```

Expected: both succeed.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/022_backlog_planning_chain.py
git commit -m "feat(backlog): migration 022 — planned hours, backlog roles, initiatives_backlog category"
```

---

### Task 2: Issue model — new columns

**Files:**
- Modify: `app/models/issue.py`

- [ ] **Step 1: Add columns after `goals` (line 64)**

Insert these lines in `Issue` class definition, grouped sensibly (after `goals`, before `assigned_category`):

```python
    # Planned effort (from Jira "Плановые трудозатраты" tab)
    planned_analyst_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    planned_dev_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    planned_qa_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    planned_opo_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # For future calendar planning — synced, currently unused
    involvement_analyst: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    involvement_dev: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    involvement_qa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    involvement_launch: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_analyst_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_dev_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_qa_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_launch_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Prioritization (normalized: low | medium | high)
    impact: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
```

Also add `Float` to the existing `sqlalchemy` import line if not present.

- [ ] **Step 2: Verify import by running test file collection**

```bash
py -3.10 -m pytest tests/ --collect-only 2>&1 | tail -5
```

Expected: 0 collection errors.

- [ ] **Step 3: Commit**

```bash
git add app/models/issue.py
git commit -m "feat(issue): add planned hours/involvement/duration/impact/risk columns"
```

---

### Task 3: BacklogItem model — new columns + Issue FK

**Files:**
- Modify: `app/models/backlog_item.py`

- [ ] **Step 1: Rewrite file**

```python
"""BacklogItem model - quarterly backlog items."""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import Float, Integer, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.issue import Issue
    from app.models.scenario_allocation import ScenarioAllocation


class BacklogItem(Base, TimestampMixin):
    """Элемент квартального бэклога.

    Может быть привязан к Jira-задаче (issue_id) — тогда оценки синкаются из
    Issue.planned_*_hours; либо создан вручную (issue_id=NULL) — PM вводит
    оценки сам и позже привязывает к созданной в Jira RFA/ITL.
    """

    __tablename__ = "backlog_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )
    issue_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="SET NULL"),
        nullable=True, unique=True, index=True,
    )

    quarter: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Legacy aggregate (computed by service on write from per-role estimates)
    estimate_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Per-role estimates (source: Issue.planned_*_hours when linked, else manual)
    estimate_analyst_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_dev_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_qa_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_opo_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Share of ОПЭ hours that go to analyst; rest goes to dev. 0.0..1.0; default 0.5
    opo_analyst_ratio: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.5, server_default="0.5",
    )

    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    impact: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Relationships
    project: Mapped[Optional["Project"]] = relationship(back_populates="backlog_items")
    issue: Mapped[Optional["Issue"]] = relationship("Issue")
    allocations: Mapped[List["ScenarioAllocation"]] = relationship(
        back_populates="backlog_item"
    )

    def __repr__(self) -> str:
        return f"<BacklogItem {self.title[:30]}>"
```

- [ ] **Step 2: Verify collection**

```bash
py -3.10 -m pytest tests/ --collect-only 2>&1 | tail -5
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add app/models/backlog_item.py
git commit -m "feat(backlog): add issue_id FK, per-role estimates, opo ratio, impact/risk"
```

---

### Task 4: sync_service — test for new customfield extraction

**Files:**
- Modify: `tests/test_sync_service.py`

- [ ] **Step 1: Read existing test file to understand fixture pattern**

```bash
head -80 tests/test_sync_service.py
```

- [ ] **Step 2: Add new test for planned-hours extraction**

Append to `tests/test_sync_service.py`:

```python
def test_upsert_issue_extracts_planned_hours_from_customfields(db_session):
    """When customfield IDs are configured in AppSetting, sync should populate
    Issue.planned_*_hours, impact, risk."""
    from app.models import AppSetting, Project
    from app.services.sync_service import SyncService

    db_session.add(AppSetting(key="jira_planned_analyst_hours_field_id", value="customfield_12001"))
    db_session.add(AppSetting(key="jira_planned_dev_hours_field_id", value="customfield_12002"))
    db_session.add(AppSetting(key="jira_planned_qa_hours_field_id", value="customfield_12003"))
    db_session.add(AppSetting(key="jira_planned_opo_hours_field_id", value="customfield_12004"))
    db_session.add(AppSetting(key="jira_impact_field_id", value="customfield_12010"))
    db_session.add(AppSetting(key="jira_risk_field_id", value="customfield_12011"))
    proj = Project(id="p1", key="RFA", name="RFA", is_active=True)
    db_session.add(proj)
    db_session.commit()

    svc = SyncService(db_session, connector=None)  # connector not used in _upsert_issue
    raw = {
        "id": "10001", "key": "RFA-123",
        "fields": {
            "summary": "Test",
            "issuetype": {"name": "RFA"},
            "status": {"name": "Open", "statusCategory": {"key": "new"}},
            "project": {"key": "RFA"},
            "created": "2026-04-01T00:00:00.000+0000",
            "updated": "2026-04-10T00:00:00.000+0000",
            "customfield_12001": 40,
            "customfield_12002": "40",
            "customfield_12003": 20.5,
            "customfield_12004": 20,
            "customfield_12010": "Высокий",
            "customfield_12011": "Низкий",
        },
    }
    issue = svc._upsert_issue(raw, project=proj)
    db_session.commit()
    assert issue.planned_analyst_hours == 40.0
    assert issue.planned_dev_hours == 40.0
    assert issue.planned_qa_hours == 20.5
    assert issue.planned_opo_hours == 20.0
    assert issue.impact == "high"
    assert issue.risk == "low"


def test_upsert_issue_skips_unset_customfields(db_session):
    """If customfield ID not configured, Issue.planned_* stays NULL."""
    from app.models import Project
    from app.services.sync_service import SyncService

    proj = Project(id="p2", key="RFA", name="RFA", is_active=True)
    db_session.add(proj)
    db_session.commit()

    svc = SyncService(db_session, connector=None)
    raw = {
        "id": "10002", "key": "RFA-124",
        "fields": {
            "summary": "Test2",
            "issuetype": {"name": "RFA"},
            "status": {"name": "Open", "statusCategory": {"key": "new"}},
            "project": {"key": "RFA"},
            "created": "2026-04-01T00:00:00.000+0000",
            "updated": "2026-04-10T00:00:00.000+0000",
        },
    }
    issue = svc._upsert_issue(raw, project=proj)
    db_session.commit()
    assert issue.planned_analyst_hours is None
    assert issue.impact is None
```

- [ ] **Step 3: Run test — expect fail**

```bash
py -3.10 -m pytest tests/test_sync_service.py::test_upsert_issue_extracts_planned_hours_from_customfields -v
```

Expected: FAIL (extraction not implemented yet).

---

### Task 5: sync_service — implement customfield extraction

**Files:**
- Modify: `app/services/sync_service.py`

- [ ] **Step 1: Read `_list_custom_field_ids` and `_upsert_issue`**

```bash
py -3.10 -c "import app.services.sync_service as s; print(s.__file__)"
```

Then open the file and locate:
- `_list_custom_field_ids` (around the team/participating/goals block)
- `_upsert_issue` (after the team extraction block)

- [ ] **Step 2: Extend `_list_custom_field_ids`**

Add a constant `_PLANNED_SETTING_KEYS` near the top of the service module:

```python
_PLANNED_NUMERIC_SETTING_KEYS = [
    "jira_planned_analyst_hours_field_id",
    "jira_planned_dev_hours_field_id",
    "jira_planned_qa_hours_field_id",
    "jira_planned_opo_hours_field_id",
    "jira_involvement_analyst_field_id",
    "jira_involvement_dev_field_id",
    "jira_involvement_qa_field_id",
    "jira_involvement_launch_field_id",
    "jira_duration_analyst_field_id",
    "jira_duration_dev_field_id",
    "jira_duration_qa_field_id",
    "jira_duration_launch_field_id",
]
_PLANNED_STRING_SETTING_KEYS = [
    "jira_impact_field_id",
    "jira_risk_field_id",
]
_ALL_PLANNED_KEYS = _PLANNED_NUMERIC_SETTING_KEYS + _PLANNED_STRING_SETTING_KEYS
```

In `_list_custom_field_ids` (or wherever team/participating/goals IDs are gathered to append to `fields=`), append values for `_ALL_PLANNED_KEYS` where not empty.

- [ ] **Step 3: Add helper functions at module level**

```python
def _to_float(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


_LEVEL_MAP = {
    "high": "high", "высокий": "high", "critical": "high", "major": "high",
    "medium": "medium", "средний": "medium", "normal": "medium",
    "low": "low", "низкий": "low", "minor": "low", "trivial": "low",
}


def _normalize_level(raw):
    if raw is None:
        return None
    # Jira select fields come as {"value": "...", "id": "..."} or plain str
    value = raw.get("value") if isinstance(raw, dict) else raw
    if not isinstance(value, str):
        return None
    return _LEVEL_MAP.get(value.strip().lower())
```

- [ ] **Step 4: Extend `_upsert_issue`**

After the existing team-extraction block (where `_extract_team_values` is called), add:

```python
# Planned effort (RFA/ITL "Плановые трудозатраты" tab)
planned_ids = {
    k: _get_setting(self.db, k) for k in _ALL_PLANNED_KEYS
}

def _fld_float(key):
    fid = planned_ids.get(key)
    if not fid:
        return None
    return _to_float((extra or {}).get(fid))

def _fld_level(key):
    fid = planned_ids.get(key)
    if not fid:
        return None
    return _normalize_level((extra or {}).get(fid))

issue.planned_analyst_hours   = _fld_float("jira_planned_analyst_hours_field_id")
issue.planned_dev_hours       = _fld_float("jira_planned_dev_hours_field_id")
issue.planned_qa_hours        = _fld_float("jira_planned_qa_hours_field_id")
issue.planned_opo_hours       = _fld_float("jira_planned_opo_hours_field_id")
issue.involvement_analyst     = _fld_float("jira_involvement_analyst_field_id")
issue.involvement_dev         = _fld_float("jira_involvement_dev_field_id")
issue.involvement_qa          = _fld_float("jira_involvement_qa_field_id")
issue.involvement_launch      = _fld_float("jira_involvement_launch_field_id")
issue.duration_analyst_days   = _fld_float("jira_duration_analyst_field_id")
issue.duration_dev_days       = _fld_float("jira_duration_dev_field_id")
issue.duration_qa_days        = _fld_float("jira_duration_qa_field_id")
issue.duration_launch_days    = _fld_float("jira_duration_launch_field_id")
issue.impact                  = _fld_level("jira_impact_field_id")
issue.risk                    = _fld_level("jira_risk_field_id")
```

Use `_get_setting(self.db, key)` — existing helper in `app/api/endpoints/settings.py`. If not importable cleanly, replicate a small local function:

```python
def _get_setting(db, key):
    from app.models import AppSetting
    row = db.query(AppSetting).filter_by(key=key).first()
    return row.value if row and row.value else None
```

- [ ] **Step 5: Run tests**

```bash
py -3.10 -m pytest tests/test_sync_service.py -v
```

Expected: all pass including the two new tests.

- [ ] **Step 6: Commit**

```bash
git add app/services/sync_service.py tests/test_sync_service.py
git commit -m "feat(sync): extract planned hours/involvement/duration/impact/risk from Jira customfields"
```

---

## Batch 2 — BacklogService + API

### Task 6: BacklogService — test for sync_from_issue (create)

**Files:**
- Create: `tests/test_backlog_sync.py`

- [ ] **Step 1: Write test file**

```python
"""Tests for BacklogService.sync_from_issue — auto-populate backlog from
Issue with category='initiatives_backlog'."""

import pytest
from app.models import BacklogItem, Issue, Project


@pytest.fixture
def proj(db_session):
    p = Project(id="p1", key="RFA", name="RFA", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


def _make_issue(db, proj, key, category, **planned):
    i = Issue(
        id=key,
        key=key,
        summary=f"Epic {key}",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category=category,
        **planned,
    )
    db.add(i)
    db.commit()
    return i


def test_sync_creates_backlog_item_when_category_matches(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session, proj, "RFA-1", "initiatives_backlog",
        planned_analyst_hours=40, planned_dev_hours=40,
        planned_qa_hours=20, planned_opo_hours=20,
        impact="high", risk="medium",
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.issue_id == issue.id
    assert item.title == "Epic RFA-1"
    assert item.project_id == proj.id
    assert item.estimate_analyst_hours == 40
    assert item.estimate_dev_hours == 40
    assert item.estimate_qa_hours == 20
    assert item.estimate_opo_hours == 20
    assert item.estimate_hours == 120  # sum
    assert item.impact == "high"
    assert item.risk == "medium"
    assert item.opo_analyst_ratio == 0.5  # default


def test_sync_updates_existing_backlog_item(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session, proj, "RFA-2", "initiatives_backlog",
        planned_analyst_hours=10, planned_dev_hours=10,
        planned_qa_hours=0, planned_opo_hours=0,
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item.estimate_hours == 20

    issue.planned_dev_hours = 50
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.estimate_dev_hours == 50
    assert item.estimate_hours == 60


def test_sync_preserves_local_fields(db_session, proj):
    """priority, opo_analyst_ratio, year, quarter — locals, Jira sync does not overwrite."""
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session, proj, "RFA-3", "initiatives_backlog",
        planned_opo_hours=10,
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    item.priority = 5
    item.opo_analyst_ratio = 0.7
    item.year = 2026
    item.quarter = "Q2"
    db_session.commit()

    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.priority == 5
    assert item.opo_analyst_ratio == 0.7
    assert item.year == 2026
    assert item.quarter == "Q2"


def test_sync_deletes_item_when_category_changes_away(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-4", "initiatives_backlog")
    svc = BacklogService(db_session)
    svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 1

    issue.category = "initiatives_rfa"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0


def test_sync_soft_unlinks_item_referenced_in_scenario(db_session, proj):
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-5", "initiatives_backlog")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    scenario = PlanningScenario(id="s1", name="Q2 draft", year=2026, quarter="Q2")
    db_session.add(scenario)
    db_session.add(ScenarioAllocation(
        id="a1", scenario_id=scenario.id, backlog_item_id=item.id,
        included_flag=True, planned_hours=0,
    ))
    db_session.commit()

    issue.category = None
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.issue_id is None
    assert item.id is not None  # not deleted


def test_sync_ignores_issue_without_backlog_category(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-6", "development")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item is None
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0
```

- [ ] **Step 2: Run tests — expect fail**

```bash
py -3.10 -m pytest tests/test_backlog_sync.py -v
```

Expected: FAIL (BacklogService does not exist).

---

### Task 7: BacklogService — implement sync_from_issue

**Files:**
- Create: `app/services/backlog_service.py`

- [ ] **Step 1: Write service**

```python
"""BacklogService — auto-population of BacklogItem from Issue with category
`initiatives_backlog`."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, Issue, ScenarioAllocation


BACKLOG_CATEGORY = "initiatives_backlog"


def _get_default_quarter_year(db: Session):
    """Read backlog defaults from AppSetting if set."""
    from app.models import AppSetting
    year = db.query(AppSetting).filter_by(key="backlog_default_year").first()
    quarter = db.query(AppSetting).filter_by(key="backlog_default_quarter").first()
    y = int(year.value) if year and year.value and year.value.isdigit() else None
    q = quarter.value if quarter and quarter.value else None
    return y, q


class BacklogService:
    def __init__(self, db: Session):
        self.db = db

    def sync_from_issue(self, issue: Issue) -> Optional[BacklogItem]:
        """Idempotent: aligns BacklogItem with Issue based on current category.

        - Category == 'initiatives_backlog': create-or-update.
        - Otherwise: if BacklogItem exists and is not used in any scenario — delete.
          If used — soft-unlink (issue_id = NULL).
        """
        existing = self.db.query(BacklogItem).filter_by(issue_id=issue.id).one_or_none()

        if issue.category == BACKLOG_CATEGORY:
            if existing is None:
                existing = BacklogItem(issue_id=issue.id)
                self.db.add(existing)
                # Defaults: only set on create
                y, q = _get_default_quarter_year(self.db)
                existing.year = y
                existing.quarter = q
                existing.opo_analyst_ratio = 0.5
            # Jira-sourced fields (always overwrite)
            existing.title = issue.summary
            existing.project_id = issue.project_id
            existing.estimate_analyst_hours = issue.planned_analyst_hours
            existing.estimate_dev_hours = issue.planned_dev_hours
            existing.estimate_qa_hours = issue.planned_qa_hours
            existing.estimate_opo_hours = issue.planned_opo_hours
            existing.impact = issue.impact
            existing.risk = issue.risk
            # Derived aggregate
            existing.estimate_hours = sum(
                v or 0 for v in (
                    existing.estimate_analyst_hours,
                    existing.estimate_dev_hours,
                    existing.estimate_qa_hours,
                    existing.estimate_opo_hours,
                )
            ) or None
            self.db.flush()
            return existing

        # Category no longer matches — cleanup
        if existing is None:
            return None
        has_alloc = (
            self.db.query(ScenarioAllocation)
            .filter_by(backlog_item_id=existing.id)
            .first()
            is not None
        )
        if has_alloc:
            existing.issue_id = None
            self.db.flush()
        else:
            self.db.delete(existing)
            self.db.flush()
        return None
```

- [ ] **Step 2: Run tests — expect pass**

```bash
py -3.10 -m pytest tests/test_backlog_sync.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/services/backlog_service.py tests/test_backlog_sync.py
git commit -m "feat(backlog): BacklogService.sync_from_issue for auto-populated backlog items"
```

---

### Task 8: Trigger sync_from_issue on category change

**Files:**
- Modify: `app/api/endpoints/issue_config.py`

- [ ] **Step 1: Add test first in `tests/test_api_issue_endpoints.py` or create new test file**

Create `tests/test_api_issue_category_backlog_trigger.py`:

```python
"""When PM sets Issue.category=initiatives_backlog via API, BacklogItem is
auto-created."""

from fastapi.testclient import TestClient

from app.main import app


def test_set_single_issue_category_triggers_backlog_sync(db_session, monkeypatch):
    from app.models import Issue, Project, Category, BacklogItem

    # Ensure category seed exists
    cat = db_session.query(Category).filter_by(code="initiatives_backlog").first()
    if not cat:
        cat = Category(
            id="cat-ib", code="initiatives_backlog", label="Бэклог инициатив",
            color="#7F77DD", sort_order=22, is_system=True, is_active=True,
        )
        db_session.add(cat)
    proj = Project(id="p-ib", key="RFA", name="RFA", is_active=True)
    issue = Issue(
        id="i1", key="RFA-1", summary="Epic", issue_type="RFA", status="Open",
        project_id=proj.id, category="development",
        planned_analyst_hours=10, planned_dev_hours=20,
    )
    db_session.add_all([proj, issue])
    db_session.commit()

    # Override get_db — common pattern; see tests/test_api_hierarchy_rules.py
    from app.api.dependencies import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        r = client.put(f"/api/v1/issues/{issue.id}/category", json={"category_code": "initiatives_backlog"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()

    item = db_session.query(BacklogItem).filter_by(issue_id=issue.id).first()
    assert item is not None
    assert item.estimate_analyst_hours == 10
    assert item.estimate_dev_hours == 20
```

- [ ] **Step 2: Run — expect fail**

```bash
py -3.10 -m pytest tests/test_api_issue_category_backlog_trigger.py -v
```

Expected: FAIL (trigger not wired).

- [ ] **Step 3: Wire trigger in issue_config endpoints**

Open `app/api/endpoints/issue_config.py`. Find `set_issue_category` and `batch_category` endpoints. After each successful commit, add:

```python
from app.services.backlog_service import BacklogService
BacklogService(db).sync_from_issue(issue)
db.commit()
```

For `batch_category`, loop over updated issues.

Be careful of the ORM caveat from CLAUDE.md: snapshot fields into locals before commit when the code later reads attributes.

- [ ] **Step 4: Run tests — expect pass**

```bash
py -3.10 -m pytest tests/test_api_issue_category_backlog_trigger.py tests/test_backlog_sync.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_api_issue_category_backlog_trigger.py
git commit -m "feat(backlog): auto-sync BacklogItem on Issue category change"
```

---

### Task 9: API /backlog/{id}/link-jira + /unlink-jira — tests

**Files:**
- Create: `tests/test_api_backlog_link.py`

- [ ] **Step 1: Write tests**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_db


def _override(db):
    app.dependency_overrides[get_db] = lambda: db


def test_link_jira_pulls_estimates_from_issue(db_session):
    from app.models import BacklogItem, Issue, Project, Category

    cat = Category(id="cat-ib", code="initiatives_backlog", label="Бэклог инициатив",
                   color="#7F77DD", sort_order=22, is_system=True, is_active=True)
    proj = Project(id="p1", key="RFA", name="RFA", is_active=True)
    issue = Issue(id="i1", key="RFA-42", summary="Real epic", issue_type="RFA",
                  status="Open", project_id=proj.id, category="initiatives_backlog",
                  planned_analyst_hours=8, planned_dev_hours=16,
                  planned_qa_hours=4, planned_opo_hours=2)
    manual = BacklogItem(id="m1", title="Manual idea",
                         estimate_analyst_hours=1, estimate_hours=1, priority=3)
    db_session.add_all([cat, proj, issue, manual])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{manual.id}/link-jira",
                        json={"jira_key": "RFA-42"})
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(manual)
    assert manual.issue_id == issue.id
    assert manual.estimate_analyst_hours == 8
    assert manual.estimate_dev_hours == 16
    assert manual.estimate_qa_hours == 4
    assert manual.estimate_opo_hours == 2
    assert manual.estimate_hours == 30


def test_link_jira_unknown_key_returns_404(db_session):
    from app.models import BacklogItem
    manual = BacklogItem(id="m2", title="Idea")
    db_session.add(manual)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{manual.id}/link-jira",
                        json={"jira_key": "NOPE-999"})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_unlink_jira_nulls_issue_id(db_session):
    from app.models import BacklogItem, Issue, Project

    proj = Project(id="p2", key="RFA", name="RFA", is_active=True)
    issue = Issue(id="i2", key="RFA-100", summary="X", issue_type="RFA",
                  status="Open", project_id=proj.id, category="initiatives_backlog")
    item = BacklogItem(id="m3", title="X", issue_id=issue.id,
                       estimate_analyst_hours=10, estimate_hours=10)
    db_session.add_all([proj, issue, item])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/unlink-jira")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    assert item.issue_id is None
    # estimates retained (user may want to edit afterwards)
    assert item.estimate_analyst_hours == 10


def test_refresh_from_jira_pulls_all_matching(db_session):
    from app.models import BacklogItem, Issue, Project, Category
    cat = Category(id="cat-ib2", code="initiatives_backlog", label="Бэклог",
                   color="#7F77DD", sort_order=22, is_system=True, is_active=True)
    proj = Project(id="p3", key="RFA", name="RFA", is_active=True)
    # Two issues in category, no backlog items yet
    for i, (k, h) in enumerate([("RFA-1", 10), ("RFA-2", 20)]):
        db_session.add(Issue(
            id=f"i{i}", key=k, summary=k, issue_type="RFA", status="Open",
            project_id=proj.id, category="initiatives_backlog",
            planned_analyst_hours=h,
        ))
    db_session.add_all([cat, proj])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/refresh-from-jira")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 2
    finally:
        app.dependency_overrides.clear()

    assert db_session.query(BacklogItem).count() == 2
```

- [ ] **Step 2: Run — expect fail**

```bash
py -3.10 -m pytest tests/test_api_backlog_link.py -v
```

Expected: FAIL (endpoints not implemented).

---

### Task 10: API /backlog — implement link/unlink/refresh + extended CRUD

**Files:**
- Modify: `app/api/endpoints/backlog.py`, `app/schemas/backlog.py`

- [ ] **Step 1: Extend schemas**

In `app/schemas/backlog.py`, update or add:

```python
from typing import Optional
from pydantic import BaseModel, Field

class BacklogItemBase(BaseModel):
    title: str
    project_id: Optional[str] = None
    year: Optional[int] = None
    quarter: Optional[str] = None
    priority: Optional[int] = None
    estimate_analyst_hours: Optional[float] = None
    estimate_dev_hours: Optional[float] = None
    estimate_qa_hours: Optional[float] = None
    estimate_opo_hours: Optional[float] = None
    opo_analyst_ratio: Optional[float] = Field(None, ge=0.0, le=1.0)
    impact: Optional[str] = None
    risk: Optional[str] = None


class BacklogItemCreate(BacklogItemBase):
    pass


class BacklogItemUpdate(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    year: Optional[int] = None
    quarter: Optional[str] = None
    priority: Optional[int] = None
    estimate_analyst_hours: Optional[float] = None
    estimate_dev_hours: Optional[float] = None
    estimate_qa_hours: Optional[float] = None
    estimate_opo_hours: Optional[float] = None
    opo_analyst_ratio: Optional[float] = Field(None, ge=0.0, le=1.0)
    impact: Optional[str] = None
    risk: Optional[str] = None


class BacklogItemResponse(BacklogItemBase):
    id: str
    issue_id: Optional[str] = None
    jira_key: Optional[str] = None
    estimate_hours: Optional[float] = None  # derived sum
    class Config:
        from_attributes = True


class LinkJiraRequest(BaseModel):
    jira_key: str


class RefreshResponse(BaseModel):
    created: int
    updated: int
    removed: int
```

- [ ] **Step 2: Extend endpoints**

In `app/api/endpoints/backlog.py`:

a) In `GET /backlog` and single-item responses — join with Issue to denormalize `jira_key`:

```python
from sqlalchemy.orm import joinedload
items = db.query(BacklogItem).options(joinedload(BacklogItem.issue)).all()
# In response_model or serialization, include item.issue.key if present.
```

Add a helper to build responses:

```python
def _to_response(item: BacklogItem) -> BacklogItemResponse:
    return BacklogItemResponse(
        id=item.id, title=item.title, project_id=item.project_id,
        issue_id=item.issue_id,
        jira_key=item.issue.key if item.issue else None,
        year=item.year, quarter=item.quarter, priority=item.priority,
        estimate_analyst_hours=item.estimate_analyst_hours,
        estimate_dev_hours=item.estimate_dev_hours,
        estimate_qa_hours=item.estimate_qa_hours,
        estimate_opo_hours=item.estimate_opo_hours,
        opo_analyst_ratio=item.opo_analyst_ratio,
        impact=item.impact, risk=item.risk,
        estimate_hours=item.estimate_hours,
    )
```

b) In create/update, after writing per-role estimates, recompute `estimate_hours`:

```python
def _recompute_total(item: BacklogItem):
    total = sum(v or 0 for v in (
        item.estimate_analyst_hours, item.estimate_dev_hours,
        item.estimate_qa_hours, item.estimate_opo_hours,
    ))
    item.estimate_hours = total or None
```

c) Add new endpoints:

```python
@router.post("/{item_id}/link-jira", response_model=BacklogItemResponse)
def link_jira(item_id: str, body: LinkJiraRequest, db: Session = Depends(get_db)):
    from app.models import Issue
    from app.services.backlog_service import BacklogService

    item = db.query(BacklogItem).get(item_id)
    if item is None:
        raise HTTPException(404, "Backlog item not found")
    issue = db.query(Issue).filter_by(key=body.jira_key).first()
    if issue is None:
        raise HTTPException(404, f"Issue {body.jira_key} not found locally — run sync first")
    # Ensure one-to-one constraint not violated
    other = db.query(BacklogItem).filter(
        BacklogItem.issue_id == issue.id, BacklogItem.id != item.id
    ).first()
    if other is not None:
        raise HTTPException(409, f"Issue {body.jira_key} is already linked to another backlog item")
    item.issue_id = issue.id
    # Pull estimates from issue (overwrite local values)
    item.title = issue.summary
    item.project_id = issue.project_id
    item.estimate_analyst_hours = issue.planned_analyst_hours
    item.estimate_dev_hours = issue.planned_dev_hours
    item.estimate_qa_hours = issue.planned_qa_hours
    item.estimate_opo_hours = issue.planned_opo_hours
    item.impact = issue.impact
    item.risk = issue.risk
    _recompute_total(item)
    db.commit()
    db.refresh(item)
    return _to_response(item)


@router.post("/{item_id}/unlink-jira", response_model=BacklogItemResponse)
def unlink_jira(item_id: str, db: Session = Depends(get_db)):
    item = db.query(BacklogItem).get(item_id)
    if item is None:
        raise HTTPException(404)
    item.issue_id = None
    db.commit()
    db.refresh(item)
    return _to_response(item)


@router.post("/refresh-from-jira", response_model=RefreshResponse)
def refresh_from_jira(db: Session = Depends(get_db)):
    from app.models import Issue
    from app.services.backlog_service import BacklogService, BACKLOG_CATEGORY

    svc = BacklogService(db)
    created = updated = 0
    existing_ids = {i.issue_id for i in db.query(BacklogItem).filter(BacklogItem.issue_id.isnot(None)).all()}
    issues = db.query(Issue).filter_by(category=BACKLOG_CATEGORY).all()
    for issue in issues:
        was = issue.id in existing_ids
        svc.sync_from_issue(issue)
        if was:
            updated += 1
        else:
            created += 1
    # Cleanup — remove items whose issue lost the category
    stale = (
        db.query(BacklogItem)
        .join(Issue, BacklogItem.issue_id == Issue.id)
        .filter(Issue.category != BACKLOG_CATEGORY)
        .all()
    )
    removed = 0
    for item in stale:
        svc.sync_from_issue(item.issue)
        removed += 1
    db.commit()
    return RefreshResponse(created=created, updated=updated, removed=removed)
```

- [ ] **Step 3: Run tests**

```bash
py -3.10 -m pytest tests/test_api_backlog_link.py -v
```

Expected: all 4 pass.

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/backlog.py app/schemas/backlog.py tests/test_api_backlog_link.py
git commit -m "feat(backlog): /link-jira, /unlink-jira, /refresh-from-jira endpoints + per-role schema"
```

---

## Batch 3 — Capacity + Planning (per-role)

### Task 11: CapacityService.team_role_capacity — test

**Files:**
- Create: `tests/test_capacity_role.py`

- [ ] **Step 1: Write test**

```python
"""team_role_capacity groups available hours by Employee.role."""

import pytest
from datetime import date
from app.models import Employee, ProductionCalendarDay
from app.services.capacity_service import CapacityService


@pytest.fixture
def full_calendar_q2(db_session):
    """Seed minimal calendar: 22 workdays in April 2026 × 8h = 176h/month."""
    for m in (4, 5, 6):
        for d in range(1, 23):  # 22 workdays
            db_session.add(ProductionCalendarDay(date=date(2026, m, d), hours=8.0))
    db_session.commit()


def test_role_capacity_groups_by_employee_role(db_session, full_calendar_q2):
    db_session.add_all([
        Employee(id="e1", display_name="A1", account_id="a1", is_active=True, role="analyst"),
        Employee(id="e2", display_name="D1", account_id="a2", is_active=True, role="dev"),
        Employee(id="e3", display_name="D2", account_id="a3", is_active=True, role="dev"),
        Employee(id="e4", display_name="Q1", account_id="a4", is_active=True, role="qa"),
    ])
    db_session.commit()

    svc = CapacityService(db_session)
    caps = svc.team_role_capacity(year=2026, quarter=2)
    # Each employee: 3 months × 22 days × 8h = 528h raw, no absences, no mandatory
    assert caps["analyst"] == pytest.approx(528.0, abs=1.0)
    assert caps["dev"] == pytest.approx(1056.0, abs=1.0)
    assert caps["qa"] == pytest.approx(528.0, abs=1.0)


def test_role_capacity_skips_unknown_role(db_session, full_calendar_q2):
    db_session.add_all([
        Employee(id="e1", display_name="A", account_id="a1", is_active=True, role="analyst"),
        Employee(id="e5", display_name="PM", account_id="a5", is_active=True, role="manager"),
        Employee(id="e6", display_name="X", account_id="a6", is_active=True, role=None),
    ])
    db_session.commit()

    svc = CapacityService(db_session)
    caps = svc.team_role_capacity(year=2026, quarter=2)
    assert caps["analyst"] == pytest.approx(528.0, abs=1.0)
    assert caps["dev"] == 0
    assert caps["qa"] == 0


def test_role_capacity_respects_team_filter(db_session, full_calendar_q2):
    from app.models import EmployeeTeam
    e1 = Employee(id="e1", display_name="A", account_id="a1", is_active=True, role="analyst")
    e2 = Employee(id="e2", display_name="B", account_id="a2", is_active=True, role="analyst")
    db_session.add_all([
        e1, e2,
        EmployeeTeam(id="t1", employee_id="e1", team="Alpha", is_primary=True),
        EmployeeTeam(id="t2", employee_id="e2", team="Beta",  is_primary=True),
    ])
    db_session.commit()

    svc = CapacityService(db_session)
    caps = svc.team_role_capacity(year=2026, quarter=2, team_filter=["Alpha"])
    assert caps["analyst"] == pytest.approx(528.0, abs=1.0)
```

- [ ] **Step 2: Run — expect fail**

```bash
py -3.10 -m pytest tests/test_capacity_role.py -v
```

---

### Task 12: CapacityService.team_role_capacity — implement

**Files:**
- Modify: `app/services/capacity_service.py`

- [ ] **Step 1: Add method to `CapacityService`**

```python
ROLE_WHITELIST = ("analyst", "dev", "qa")


def team_role_capacity(self, year: int, quarter: int, team_filter: list[str] | None = None) -> dict:
    """Available hours (norm − absence − mandatory) grouped by Employee.role.

    Roles not in {analyst, dev, qa} are skipped. Returns a dict with all three
    keys (0 if no employees of that role).
    """
    out = {r: 0.0 for r in ROLE_WHITELIST}
    q = self.db.query(Employee).filter(Employee.is_active.is_(True))
    if team_filter:
        from app.models import EmployeeTeam
        q = q.join(EmployeeTeam).filter(EmployeeTeam.team.in_(team_filter))
    for emp in q.all():
        role = (emp.role or "").strip().lower()
        if role not in out:
            continue
        avail = self.employee_quarter_capacity(emp.id, year, quarter)
        out[role] += avail
    return out


def employee_quarter_capacity(self, employee_id: str, year: int, quarter: int) -> float:
    """Sum of monthly `available_hours` for the 3 months of the quarter.

    Reuses the existing monthly_capacity / v3 formula.
    """
    months = {1: (1,2,3), 2: (4,5,6), 3: (7,8,9), 4: (10,11,12)}[quarter]
    total = 0.0
    for m in months:
        row = self.employee_monthly_capacity(employee_id, year, m)
        total += (row.get("available_hours") or 0)
    return total
```

If `employee_monthly_capacity` doesn't exist with that exact name, wrap the existing monthly aggregator. Verify by reading the file.

- [ ] **Step 2: Run tests**

```bash
py -3.10 -m pytest tests/test_capacity_role.py -v
```

- [ ] **Step 3: Commit**

```bash
git add app/services/capacity_service.py tests/test_capacity_role.py
git commit -m "feat(capacity): team_role_capacity aggregates by Employee.role"
```

---

### Task 13: PlanningService.generate_scenario — per-role allocation test

**Files:**
- Create: `tests/test_planning_role_allocation.py`

- [ ] **Step 1: Write test**

```python
"""PlanningService.generate_scenario allocates backlog items respecting per-role
capacity; ОПЭ hours split via opo_analyst_ratio."""

import pytest
from datetime import date


@pytest.fixture
def q2_calendar(db_session):
    from app.models import ProductionCalendarDay
    for m in (4, 5, 6):
        for d in range(1, 23):
            db_session.add(ProductionCalendarDay(date=date(2026, m, d), hours=8.0))
    db_session.commit()


def test_allocation_includes_items_until_any_role_exhausted(db_session, q2_calendar):
    from app.models import Employee, BacklogItem
    from app.services.planning_service import PlanningService

    # 1 analyst, 1 dev, 1 qa → each 528h capacity
    db_session.add_all([
        Employee(id="e1", display_name="A", account_id="a1", is_active=True, role="analyst"),
        Employee(id="e2", display_name="D", account_id="a2", is_active=True, role="dev"),
        Employee(id="e3", display_name="Q", account_id="a3", is_active=True, role="qa"),
    ])
    # 3 items, priorities 1..3, each smaller than capacity
    db_session.add_all([
        BacklogItem(id="b1", title="T1", year=2026, quarter="Q2", priority=1,
                    estimate_analyst_hours=200, estimate_dev_hours=200,
                    estimate_qa_hours=100, estimate_opo_hours=0,
                    estimate_hours=500),
        BacklogItem(id="b2", title="T2", year=2026, quarter="Q2", priority=2,
                    estimate_analyst_hours=200, estimate_dev_hours=200,
                    estimate_qa_hours=200, estimate_opo_hours=0,
                    estimate_hours=600),
        BacklogItem(id="b3", title="T3", year=2026, quarter="Q2", priority=3,
                    estimate_analyst_hours=50, estimate_dev_hours=50,
                    estimate_qa_hours=50, estimate_opo_hours=0,
                    estimate_hours=150),
    ])
    db_session.commit()

    svc = PlanningService(db_session)
    scenario = svc.generate_scenario(name="Q2 draft", year=2026, quarter=2)

    # qa capacity = 528. Item b1 takes 100. b2 would need 200 more → 300 ≤ 528 OK.
    # But analyst after b1+b2 = 400/528 remaining 128, so b3 analyst=50 fits.
    # dev after b1+b2 = 400/528 remaining 128, b3 dev=50 fits.
    # qa after b1+b2 = 300/528 remaining 228, b3 qa=50 fits.
    allocations = {a.backlog_item_id: a for a in scenario.allocations}
    assert allocations["b1"].included_flag is True
    assert allocations["b2"].included_flag is True
    assert allocations["b3"].included_flag is True


def test_allocation_rejects_item_when_any_role_overcapacity(db_session, q2_calendar):
    from app.models import Employee, BacklogItem
    from app.services.planning_service import PlanningService

    db_session.add_all([
        Employee(id="e1", display_name="A", account_id="a1", is_active=True, role="analyst"),
        Employee(id="e2", display_name="D", account_id="a2", is_active=True, role="dev"),
        Employee(id="e3", display_name="Q", account_id="a3", is_active=True, role="qa"),
    ])
    # Item 1 fits. Item 2 overflows qa only.
    db_session.add_all([
        BacklogItem(id="b1", title="T1", year=2026, quarter="Q2", priority=1,
                    estimate_analyst_hours=100, estimate_dev_hours=100,
                    estimate_qa_hours=500, estimate_opo_hours=0,
                    estimate_hours=700),
        BacklogItem(id="b2", title="T2", year=2026, quarter="Q2", priority=2,
                    estimate_analyst_hours=50, estimate_dev_hours=50,
                    estimate_qa_hours=100, estimate_opo_hours=0,
                    estimate_hours=200),
    ])
    db_session.commit()

    svc = PlanningService(db_session)
    scenario = svc.generate_scenario(name="Q2 draft", year=2026, quarter=2)

    a = {x.backlog_item_id: x for x in scenario.allocations}
    assert a["b1"].included_flag is True
    assert a["b2"].included_flag is False  # qa remaining 28, b2 needs 100


def test_opo_hours_split_between_analyst_and_dev(db_session, q2_calendar):
    from app.models import Employee, BacklogItem
    from app.services.planning_service import PlanningService

    db_session.add_all([
        Employee(id="e1", display_name="A", account_id="a1", is_active=True, role="analyst"),
        Employee(id="e2", display_name="D", account_id="a2", is_active=True, role="dev"),
        Employee(id="e3", display_name="Q", account_id="a3", is_active=True, role="qa"),
    ])
    # opo=100, ratio=0.7 → analyst +70, dev +30
    db_session.add_all([
        BacklogItem(id="b1", title="T1", year=2026, quarter="Q2", priority=1,
                    estimate_analyst_hours=400, estimate_dev_hours=400,
                    estimate_qa_hours=100, estimate_opo_hours=100,
                    opo_analyst_ratio=0.7,
                    estimate_hours=1000),
    ])
    db_session.commit()

    svc = PlanningService(db_session)
    scenario = svc.generate_scenario(name="Q2 draft", year=2026, quarter=2)

    # analyst demand = 400 + 100*0.7 = 470 ≤ 528 OK
    # dev     demand = 400 + 100*0.3 = 430 ≤ 528 OK
    # qa      demand = 100 ≤ 528 OK
    a = {x.backlog_item_id: x for x in scenario.allocations}
    assert a["b1"].included_flag is True
```

- [ ] **Step 2: Run — expect fail**

```bash
py -3.10 -m pytest tests/test_planning_role_allocation.py -v
```

---

### Task 14: PlanningService — rewrite generate_scenario for per-role

**Files:**
- Modify: `app/services/planning_service.py`

- [ ] **Step 1: Rewrite allocation logic**

Read the existing `generate_scenario` method. Replace the allocation loop with:

```python
from app.services.capacity_service import CapacityService

def generate_scenario(self, name: str, year: int, quarter, backlog_item_ids=None) -> PlanningScenario:
    # quarter may be int 1..4 or "Q1".."Q4" — normalize
    if isinstance(quarter, str):
        q_int = int(quarter.replace("Q", "")) if quarter.startswith("Q") else int(quarter)
        q_str = quarter
    else:
        q_int = int(quarter)
        q_str = f"Q{q_int}"

    capacity = CapacityService(self.db).team_role_capacity(year, q_int)
    remaining = dict(capacity)

    q = self.db.query(BacklogItem).filter_by(year=year, quarter=q_str)
    if backlog_item_ids:
        q = q.filter(BacklogItem.id.in_(backlog_item_ids))
    items = sorted(
        q.all(),
        key=lambda i: (
            i.priority if i.priority is not None else 99999,
            i.estimate_hours or 0,
            i.title,
        ),
    )

    scenario = PlanningScenario(
        id=str(uuid.uuid4()), name=name, year=year, quarter=q_str,
    )
    self.db.add(scenario)
    self.db.flush()

    for item in items:
        demand = self._demand_by_role(item)
        fits = all(remaining.get(r, 0) >= h for r, h in demand.items())
        included = fits
        if included:
            for r, h in demand.items():
                remaining[r] -= h
        alloc = ScenarioAllocation(
            id=str(uuid.uuid4()), scenario_id=scenario.id, backlog_item_id=item.id,
            included_flag=included,
            planned_hours=(item.estimate_hours or 0.0) if included else 0.0,
        )
        self.db.add(alloc)

    self.db.commit()
    self.db.refresh(scenario)
    return scenario


@staticmethod
def _demand_by_role(item: BacklogItem) -> dict:
    ea = item.estimate_analyst_hours or 0
    ed = item.estimate_dev_hours or 0
    eq = item.estimate_qa_hours or 0
    eo = item.estimate_opo_hours or 0
    r = item.opo_analyst_ratio if item.opo_analyst_ratio is not None else 0.5
    return {
        "analyst": ea + eo * r,
        "dev":     ed + eo * (1 - r),
        "qa":      eq,
    }
```

If the existing method has additional responsibilities (e.g., writing reasons), keep them but overlay per-role logic.

- [ ] **Step 2: Run tests**

```bash
py -3.10 -m pytest tests/test_planning_role_allocation.py tests/test_api_planning.py -v
```

If existing planning tests fail due to hour-only allocation assumptions, update them to use the new per-role fixtures (or widen capacity so allocation is unchanged).

- [ ] **Step 3: Commit**

```bash
git add app/services/planning_service.py tests/test_planning_role_allocation.py
git commit -m "feat(planning): per-role greedy allocation with ОПЭ split"
```

---

### Task 15: /planning/capacity-preview endpoint

**Files:**
- Modify: `app/api/endpoints/planning.py`, `app/schemas/planning.py`

- [ ] **Step 1: Write test** in `tests/test_api_planning.py`:

```python
def test_capacity_preview_returns_per_role_demand(db_session, q2_calendar):
    from app.models import Employee, BacklogItem, Project
    from app.main import app
    from app.api.dependencies import get_db
    from fastapi.testclient import TestClient

    proj = Project(id="p1", key="RFA", name="RFA", is_active=True)
    db_session.add(proj)
    db_session.add_all([
        Employee(id="e1", display_name="A", account_id="a1", is_active=True, role="analyst"),
        Employee(id="e2", display_name="D", account_id="a2", is_active=True, role="dev"),
        Employee(id="e3", display_name="Q", account_id="a3", is_active=True, role="qa"),
    ])
    db_session.add_all([
        BacklogItem(id="b1", title="T1", year=2026, quarter="Q2", priority=1,
                    estimate_analyst_hours=40, estimate_dev_hours=80,
                    estimate_qa_hours=20, estimate_opo_hours=0,
                    estimate_hours=140),
    ])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        r = client.post("/api/v1/planning/capacity-preview", json={
            "year": 2026, "quarter": 2, "backlog_item_ids": ["b1"],
        })
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["demand_by_role"]["analyst"] == 40
    assert body["demand_by_role"]["dev"] == 80
    assert body["demand_by_role"]["qa"] == 20
    assert body["capacity_by_role"]["analyst"] > 0
    assert len(body["per_employee"]) == 3
```

- [ ] **Step 2: Add schemas**

In `app/schemas/planning.py`:

```python
from pydantic import BaseModel
from typing import Optional

class CapacityPreviewRequest(BaseModel):
    year: int
    quarter: int
    backlog_item_ids: list[str] = []
    team_filter: Optional[list[str]] = None

class CapacityPreviewEmployeeRow(BaseModel):
    employee_id: str
    name: str
    role: Optional[str]
    raw_hours: float
    mandatory_hours: float
    absence_hours: float
    available_hours: float
    vacation_days: int

class CapacityPreviewResponse(BaseModel):
    capacity_by_role: dict  # {analyst, dev, qa}
    demand_by_role: dict
    total_capacity: float
    total_demand: float
    gross_hours: float
    absence_hours: float
    mandatory_hours: float
    available_hours: float
    per_employee: list[CapacityPreviewEmployeeRow]
```

- [ ] **Step 3: Implement endpoint**

```python
@router.post("/capacity-preview", response_model=CapacityPreviewResponse)
def capacity_preview(body: CapacityPreviewRequest, db: Session = Depends(get_db)):
    from app.models import Employee, BacklogItem, Absence
    from app.services.capacity_service import CapacityService, ROLE_WHITELIST
    from app.services.planning_service import PlanningService

    cap_svc = CapacityService(db)
    caps = cap_svc.team_role_capacity(body.year, body.quarter, body.team_filter)

    # Per-employee breakdown
    q = db.query(Employee).filter(Employee.is_active.is_(True))
    if body.team_filter:
        from app.models import EmployeeTeam
        q = q.join(EmployeeTeam).filter(EmployeeTeam.team.in_(body.team_filter))
    per_emp = []
    gross = absence = mand = avail = 0.0
    for emp in q.all():
        row = cap_svc.employee_quarter_breakdown(emp.id, body.year, body.quarter)
        per_emp.append(CapacityPreviewEmployeeRow(
            employee_id=emp.id, name=emp.display_name, role=emp.role,
            raw_hours=row["raw_hours"],
            mandatory_hours=row["mandatory_hours"],
            absence_hours=row["absence_hours"],
            available_hours=row["available_hours"],
            vacation_days=row.get("vacation_days", 0),
        ))
        gross += row["raw_hours"]
        absence += row["absence_hours"]
        mand += row["mandatory_hours"]
        avail += row["available_hours"]

    items = db.query(BacklogItem).filter(BacklogItem.id.in_(body.backlog_item_ids)).all() if body.backlog_item_ids else []
    demand = {r: 0.0 for r in ROLE_WHITELIST}
    for item in items:
        for r, h in PlanningService._demand_by_role(item).items():
            demand[r] += h

    return CapacityPreviewResponse(
        capacity_by_role=caps,
        demand_by_role=demand,
        total_capacity=sum(caps.values()),
        total_demand=sum(demand.values()),
        gross_hours=gross, absence_hours=absence,
        mandatory_hours=mand, available_hours=avail,
        per_employee=per_emp,
    )
```

**Note:** `employee_quarter_breakdown` method needs to exist on CapacityService. If not present, add:

```python
def employee_quarter_breakdown(self, employee_id: str, year: int, quarter: int) -> dict:
    months = {1:(1,2,3), 2:(4,5,6), 3:(7,8,9), 4:(10,11,12)}[quarter]
    raw = absence = mandatory = available = 0.0
    vacation_days = 0
    for m in months:
        row = self.employee_monthly_capacity(employee_id, year, m)
        raw += row.get("norm_hours", 0)
        absence += row.get("absence_hours", 0)
        mandatory += row.get("mandatory_hours", 0)
        available += row.get("available_hours", 0)
        vacation_days += row.get("absence_days", 0)  # best effort
    return {
        "raw_hours": raw, "absence_hours": absence,
        "mandatory_hours": mandatory, "available_hours": available,
        "vacation_days": vacation_days,
    }
```

- [ ] **Step 4: Run tests**

```bash
py -3.10 -m pytest tests/test_api_planning.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/planning.py app/schemas/planning.py tests/test_api_planning.py
git commit -m "feat(planning): /capacity-preview endpoint for live UI calc"
```

---

## Batch 4 — Frontend

### Task 16: Menu reorder

**Files:**
- Modify: `frontend/src/components/Layout/SideMenu.tsx`

- [ ] **Step 1: Move ПЛАНИРОВАНИЕ group above ДАННЫЕ**

Rearrange `items` array so order is: overview → planning → data.

- [ ] **Step 2: Verify in dev server**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/` — sidebar shows ОБЗОР → ПЛАНИРОВАНИЕ → ДАННЫЕ.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Layout/SideMenu.tsx
git commit -m "feat(ui): reorder menu — planning group above data"
```

---

### Task 17: Constants — role colors/labels

**Files:**
- Modify: `frontend/src/utils/constants.ts`

- [ ] **Step 1: Append**

```typescript
export const ROLE_COLORS = {
  analyst: '#4db8e8',
  dev:     '#00c9c8',
  qa:      '#EF9F27',
  opo:     '#7F77DD',
} as const;

export const ROLE_LABELS = {
  analyst: 'Аналитик',
  dev:     'Программист',
  qa:      'Тестировщик',
  opo:     'Запуск (ОПЭ)',
} as const;

export const ROLE_SHORT = {
  analyst: 'АН',
  dev:     'ПР',
  qa:      'ТС',
  opo:     'ОПЭ',
} as const;

export type PlanningRole = keyof typeof ROLE_COLORS;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/utils/constants.ts
git commit -m "feat(ui): role colors/labels for planning page"
```

---

### Task 18: Settings — Jira fields card extension

**Files:**
- Modify: `frontend/src/components/JiraFieldsCard.tsx`

- [ ] **Step 1: Extend fields list**

Group into 3 sections (Collapse panels of AntD):

- **Плановые трудозатраты (часы):** 4 inputs (analyst/dev/qa/opo)
- **Вовлеченность и длительности:** 8 inputs (collapsed by default, subtitle «Для будущего календарного планирования»)
- **Приоритизация:** 2 inputs (impact, risk)

Each input saves via existing `PUT /settings/generic/{key}` pattern (already used for team/participating/goals). Add state and form handlers mirroring existing code.

Key labels:
```
jira_planned_analyst_hours_field_id → "Анализ (часы)"
jira_planned_dev_hours_field_id     → "Разработка (часы)"
jira_planned_qa_hours_field_id      → "Тестирование (часы)"
jira_planned_opo_hours_field_id     → "ОПЭ (часы)"
jira_involvement_analyst_field_id   → "Вовлеченность аналитика"
...
jira_impact_field_id                → "Impact"
jira_risk_field_id                  → "Risk"
```

- [ ] **Step 2: Verify in dev**

Open `/settings` → tab «Поля Jira». All 14 inputs visible.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/JiraFieldsCard.tsx
git commit -m "feat(settings): 14 Jira customfield IDs for planned hours/impact/risk"
```

---

### Task 19: Employee role dropdown

**Files:**
- Modify: `frontend/src/pages/EmployeesPage.tsx` (or the specific form component)

- [ ] **Step 1: Add Select for role**

Find the employee edit form (modal or inline). Replace free-text role input with:

```tsx
<Form.Item name="role" label="Роль">
  <Select allowClear placeholder="Не задана">
    <Select.Option value="analyst">Аналитик</Select.Option>
    <Select.Option value="dev">Программист</Select.Option>
    <Select.Option value="qa">Тестировщик</Select.Option>
    <Select.Option value="other">Другое</Select.Option>
  </Select>
</Form.Item>
```

Existing free-text values in DB remain unaffected; UI just offers a fixed set.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/EmployeesPage.tsx
git commit -m "feat(employees): role dropdown for planning compatibility"
```

---

### Task 20: Backlog API typings + hooks

**Files:**
- Modify: `frontend/src/types/backlog.ts`, `frontend/src/api/backlog.ts`, `frontend/src/hooks/useBacklog.ts`

- [ ] **Step 1: Update types**

```typescript
export interface BacklogItem {
  id: string;
  title: string;
  project_id: string | null;
  issue_id: string | null;
  jira_key: string | null;
  year: number | null;
  quarter: string | null;
  priority: number | null;
  estimate_hours: number | null;
  estimate_analyst_hours: number | null;
  estimate_dev_hours: number | null;
  estimate_qa_hours: number | null;
  estimate_opo_hours: number | null;
  opo_analyst_ratio: number | null;
  impact: 'low' | 'medium' | 'high' | null;
  risk: 'low' | 'medium' | 'high' | null;
}
```

- [ ] **Step 2: Add API calls**

```typescript
// frontend/src/api/backlog.ts
export const linkJira = (id: string, jira_key: string) =>
  api.post<BacklogItem>(`/backlog/${id}/link-jira`, { jira_key });
export const unlinkJira = (id: string) =>
  api.post<BacklogItem>(`/backlog/${id}/unlink-jira`);
export const refreshFromJira = () =>
  api.post<{ created: number; updated: number; removed: number }>(`/backlog/refresh-from-jira`);
```

- [ ] **Step 3: Add hooks**

```typescript
// frontend/src/hooks/useBacklog.ts (extend)
export const useLinkJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, jira_key }: { id: string; jira_key: string }) =>
      linkJira(id, jira_key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }),
  });
};
// similar for useUnlinkJira, useRefreshFromJira
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/backlog.ts frontend/src/api/backlog.ts frontend/src/hooks/useBacklog.ts
git commit -m "feat(ui): backlog link/unlink/refresh API + typings"
```

---

### Task 21: BacklogPage redesign

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx`
- Create: `frontend/src/components/backlog/BacklogManualModal.tsx`
- Create: `frontend/src/components/backlog/BacklogLinkJiraModal.tsx`

- [ ] **Step 1: Build ManualModal**

Modal with form: title, project_id (Select), year, quarter, estimate_analyst/dev/qa/opo_hours, opo_analyst_ratio (default 0.5), impact (Select low/medium/high), risk (same), priority. On submit: `POST /backlog` with those fields. `issue_id = NULL`.

- [ ] **Step 2: Build LinkJiraModal**

Simple form: input `jira_key` (placeholder «RFA-123»). On submit: `useLinkJira.mutate({ id, jira_key })`. Show warning: «Локальные оценки часов будут заменены значениями из Jira».

- [ ] **Step 3: Redesign page columns**

Extend `columns` in the table:

```tsx
[
  { title: '#', dataIndex: 'priority' },
  { title: 'Идея', dataIndex: 'title', render: (v, r) => (
      <div>
        <div>{v}</div>
        {r.jira_key && (
          <a href={`${jiraBaseUrl}/browse/${r.jira_key}`} target="_blank">{r.jira_key}</a>
        )}
      </div>
    )},
  { title: 'АН ч', dataIndex: 'estimate_analyst_hours', width: 70,
    render: (v, r) => r.issue_id ? v ?? '—' : <InlineEditNumber ... /> },
  // ... same pattern for dev/qa/opo
  { title: 'ОПЭ→АН', dataIndex: 'opo_analyst_ratio',
    render: (v, r) => <InlineEditNumber value={v ?? 0.5} min={0} max={1} step={0.05}/> },
  { title: 'Impact', dataIndex: 'impact',
    render: (v, r) => r.issue_id ? v ?? '—' : <Select value={v} onChange={...}/> },
  { title: 'Risk', dataIndex: 'risk', ... },
  { title: 'Проект', dataIndex: 'project_id', ... },
  { title: 'Q', render: (r) => `${r.year} ${r.quarter}` },
  { title: 'Действия', render: (r) => (
      r.issue_id
        ? <Button size="small" onClick={() => unlink(r.id)}>Отвязать</Button>
        : <Button size="small" onClick={() => openLinkModal(r)}>Связать с Jira</Button>
    )},
]
```

Plus in the page header: `[+ Идея вручную]` and `[Обновить с Jira]` buttons.

- [ ] **Step 4: Verify in dev**

Create manual item → it shows up → click «Связать с Jira» → enter existing Jira-synced issue key → fields get overwritten.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/BacklogPage.tsx frontend/src/components/backlog/
git commit -m "feat(backlog-page): per-role estimates, impact/risk, manual + link-to-jira"
```

---

### Task 22: PlanningPage types + API

**Files:**
- Modify: `frontend/src/types/planning.ts`, `frontend/src/api/planning.ts`, `frontend/src/hooks/usePlanning.ts`

- [ ] **Step 1: Add types**

```typescript
// frontend/src/types/planning.ts
export interface CapacityPreviewRequest {
  year: number;
  quarter: number;
  backlog_item_ids: string[];
  team_filter?: string[];
}

export interface EmployeeCapacityRow {
  employee_id: string;
  name: string;
  role: 'analyst' | 'dev' | 'qa' | string | null;
  raw_hours: number;
  mandatory_hours: number;
  absence_hours: number;
  available_hours: number;
  vacation_days: number;
}

export interface CapacityPreviewResponse {
  capacity_by_role: { analyst: number; dev: number; qa: number };
  demand_by_role:   { analyst: number; dev: number; qa: number };
  total_capacity: number;
  total_demand: number;
  gross_hours: number;
  absence_hours: number;
  mandatory_hours: number;
  available_hours: number;
  per_employee: EmployeeCapacityRow[];
}
```

- [ ] **Step 2: Add API wrapper**

```typescript
// frontend/src/api/planning.ts
export const capacityPreview = (body: CapacityPreviewRequest) =>
  api.post<CapacityPreviewResponse>('/planning/capacity-preview', body);
```

- [ ] **Step 3: Hook**

```typescript
// frontend/src/hooks/usePlanning.ts
export const useCapacityPreview = (req: CapacityPreviewRequest) =>
  useQuery({
    queryKey: ['planning', 'capacity-preview', req],
    queryFn: () => capacityPreview(req),
    staleTime: 10_000,
    enabled: !!req.year && !!req.quarter,
  });
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/planning.ts frontend/src/api/planning.ts frontend/src/hooks/usePlanning.ts
git commit -m "feat(ui): capacity-preview query + typings"
```

---

### Task 23: PlanningPage — shared components

**Files:**
- Create: `frontend/src/components/planning/RoleCapacityBar.tsx`
- Create: `frontend/src/components/planning/PlanningBacklogList.tsx`
- Create: `frontend/src/components/planning/PlanningCapacityPanel.tsx`

- [ ] **Step 1: RoleCapacityBar** — mirror prototype lines 1444-1491

```tsx
import { Card } from 'antd';
import { ROLE_COLORS, ROLE_LABELS, ROLE_SHORT, PlanningRole } from '@/utils/constants';

interface Props {
  role: PlanningRole;
  demand: number;
  capacity: number;
  employeeCount: number;
}
export const RoleCapacityBar: React.FC<Props> = ({ role, demand, capacity, employeeCount }) => {
  const over = demand > capacity;
  const pct = capacity > 0 ? Math.min(100, (demand/capacity)*100) : 0;
  const overflowPct = over ? Math.min(40, ((demand-capacity)/capacity)*100) : 0;
  return (
    <div>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline'}}>
        <div style={{display:'flex', alignItems:'center', gap:8}}>
          <span style={{width:10, height:10, borderRadius:2, background:ROLE_COLORS[role]}}/>
          <span>{ROLE_LABELS[role]}</span>
          <span style={{opacity:0.6}}>· {employeeCount} чел.</span>
        </div>
        <span style={{color: over ? '#EF9F27' : undefined, fontFamily:'monospace'}}>
          {Math.round(demand)} / {Math.round(capacity)} ч
        </span>
      </div>
      <div style={{position:'relative', height:10, background:'#0a2a44', borderRadius:5, marginTop:6}}>
        <div style={{position:'absolute', left:0, width:`${pct}%`, height:10,
                     background:ROLE_COLORS[role], borderRadius:5}}/>
        {over && (
          <div style={{position:'absolute', left:'100%', top:-2, bottom:-2,
                       width:`${overflowPct}%`, background:'#EF9F27', borderRadius:'0 5px 5px 0',
                       borderLeft:'2px solid #0f2340'}}/>
        )}
        <div style={{position:'absolute', left:'100%', top:-3, bottom:-3, width:2, background:'#c5d8ee'}}/>
      </div>
      <div style={{display:'flex', justifyContent:'space-between', marginTop:4, fontSize:10, opacity:0.7}}>
        <span>{over ? `перегруз +${Math.round(demand-capacity)} ч` : `запас ${Math.round(capacity-demand)} ч`}</span>
        <span>загрузка {Math.round((demand/capacity)*100 || 0)}%</span>
      </div>
    </div>
  );
};
```

- [ ] **Step 2: PlanningBacklogList** — mirror prototype lines 1343-1417

Props: `{ items: BacklogItem[], selected: Set<string>, onToggle(id), demandByRole, capacityByRole }`. Renders header-row + list-row per prototype.

- [ ] **Step 3: PlanningCapacityPanel** — mirror prototype lines 1420-1566

Sticky wrapper with the 4 cards + 2 buttons. Takes full `CapacityPreviewResponse` as prop plus callbacks for Save/Export.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/planning/
git commit -m "feat(planning): components RoleCapacityBar, PlanningBacklogList, PlanningCapacityPanel"
```

---

### Task 24: PlanningPage — assemble

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 1: Rewrite page**

Structure:

```tsx
export const PlanningPage: React.FC = () => {
  const { year, quarter } = useQuarterYear();
  const quarterInt = quarterToInt(quarter);
  const { data: backlog } = useBacklog(year, quarter);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useEffect(() => {
    // initial selection: all items (or none — design shows some pre-selected;
    // match prototype's b.selected approach: default all)
    if (backlog) setSelected(new Set(backlog.map(b => b.id)));
  }, [backlog]);
  const { data: preview } = useCapacityPreview({
    year, quarter: quarterInt,
    backlog_item_ids: Array.from(selected),
  });
  const saveMutation = useSaveScenario();
  const toggle = (id: string) => setSelected(s => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  return (
    <div style={{display:'grid', gridTemplateColumns:'1fr 460px', gap:16}}>
      <PlanningBacklogList
        items={backlog ?? []}
        selected={selected}
        onToggle={toggle}
        demandByRole={preview?.demand_by_role ?? {analyst:0,dev:0,qa:0}}
        capacityByRole={preview?.capacity_by_role ?? {analyst:0,dev:0,qa:0}}
      />
      <PlanningCapacityPanel
        preview={preview}
        onSave={() => saveMutation.mutate({
          year, quarter: quarterInt,
          backlog_item_ids: Array.from(selected),
          name: `Q${quarterInt} ${year} draft`,
        })}
      />
    </div>
  );
};
```

- [ ] **Step 2: Verify in dev**

Open `/planning`. Toggle checkboxes → capacity panel updates. Click «Сохранить сценарий» → toast + scenario created.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning-page): redesign under prototype — checkboxes + live per-role capacity"
```

---

### Task 25: E2E — manual item + link-to-jira

**Files:**
- Modify: `frontend/e2e/crud-flows.spec.ts`

- [ ] **Step 1: Append spec**

```typescript
test('backlog — manual item creation and link-to-jira flow', async ({ page }) => {
  await page.goto('/backlog');
  await page.getByRole('button', { name: /Идея вручную/ }).click();
  await page.getByLabel('Название').fill('Новая идея Q2');
  await page.getByLabel('АН ч').fill('10');
  await page.getByLabel('ПР ч').fill('20');
  await page.getByRole('button', { name: 'Сохранить' }).click();

  await expect(page.getByText('Новая идея Q2')).toBeVisible();

  // Ensure a seeded Jira-synced issue exists in e2e.db as prerequisite
  await page.getByRole('row', { name: /Новая идея Q2/ })
    .getByRole('button', { name: /Связать с Jira/ }).click();
  await page.getByLabel('Jira key').fill('E2E-1');
  await page.getByRole('button', { name: /Связать/ }).click();

  // After link, estimates should come from Jira (different from manual 10/20)
  // ... assert based on seed data
});

test('planning — toggle checkbox updates capacity panel', async ({ page }) => {
  await page.goto('/planning');
  const initialCapacity = await page.getByTestId('capacity-analyst-demand').textContent();
  await page.getByRole('checkbox').first().click();
  await expect(page.getByTestId('capacity-analyst-demand')).not.toHaveText(initialCapacity!);
});
```

Requires adding `data-testid="capacity-analyst-demand"` etc. to `RoleCapacityBar`.

- [ ] **Step 2: Run**

```bash
cd frontend && npm run e2e
```

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/crud-flows.spec.ts frontend/src/components/planning/RoleCapacityBar.tsx
git commit -m "test(e2e): manual backlog + planning capacity update flow"
```

---

## Final Task: Integration QA

- [ ] **Step 1: Run full backend test suite**

```bash
py -3.10 -m pytest tests/ -v --tb=short
```

Expected: all pass (may need to fix pre-existing failures documented in memory — leave those untouched if they're not caused by this change).

- [ ] **Step 2: Run frontend lint + build**

```bash
cd frontend && npm run lint && npm run build
```

- [ ] **Step 3: Local smoke**

```bash
py -3.10 scripts/local_smoke.py
```

- [ ] **Step 4: Run full e2e**

```bash
.\scripts\e2e-local.ps1
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

- [ ] **Step 6: Memory update**

Append to memory:
- `project_backlog_planning_chain_shipped.md` — shipped 2026-04-20, batches 1-4, commit range, any deviations.

---

## Self-Review

**Spec coverage:**
- ✅ Category seed (T1) → `initiatives_backlog`
- ✅ Issue planned columns (T2)
- ✅ BacklogItem role columns + FK (T3)
- ✅ Customfield extraction (T4-T5)
- ✅ BacklogService.sync_from_issue (T6-T7)
- ✅ Category-change trigger (T8)
- ✅ Link/unlink/refresh API (T9-T10)
- ✅ team_role_capacity (T11-T12)
- ✅ Per-role greedy allocation (T13-T14)
- ✅ /capacity-preview endpoint (T15)
- ✅ Menu reorder (T16)
- ✅ Role constants (T17)
- ✅ JiraFieldsCard extension (T18)
- ✅ Employee role dropdown (T19)
- ✅ Backlog types/API/hooks (T20)
- ✅ BacklogPage redesign + manual + link (T21)
- ✅ Planning types/API/hooks (T22)
- ✅ Planning components (T23)
- ✅ PlanningPage assembly (T24)
- ✅ E2E (T25)
- ✅ Integration QA (Final)

**Type consistency:** `ROLE_COLORS/LABELS/SHORT` defined in T17 used consistently in T23; `BacklogItem` TS type in T20 matches Python schema in T10; `CapacityPreviewResponse` matches T15 and T22.

**Placeholder scan:** no TBDs. All code blocks are complete; exact file paths given. Edge case in T8 (snapshot fields before commit) documented with reference to CLAUDE.md.
