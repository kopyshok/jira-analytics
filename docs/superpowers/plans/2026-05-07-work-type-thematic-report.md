# Work-Type Thematic Report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PM-facing thematic analysis of one work type (e.g. "Сопровождение и консультация") — AI clusters tasks into themes, builds hour distribution, narrative per theme, top outliers, recommendation. UI + XLSX + PDF.

**Architecture:** Map-reduce LLM pipeline. Map: per-issue classification with cache (input hash + dictionary version). Reduce: synthesis from aggregated findings JSON only (no raw access). Faithfulness validator. Snapshot per `(work_type, period, team_set_hash)` mirroring `ProjectAISummary` pattern. UI: master-detail page with preset+pivot grouping and saved layouts.

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2 / Alembic batch / pytest / React 19 / TS 6 / Vite 8 / AntD 6 / TanStack Query

**Spec:** [docs/superpowers/specs/2026-05-07-work-type-thematic-report-design.md](../specs/2026-05-07-work-type-thematic-report-design.md)

---

## File Map

### Backend

| File | Action | Responsibility |
|---|---|---|
| `alembic/versions/XXX_work_type_thematic_report.py` | Create | 4 new tables + `theme_dict_version` column on `mandatory_work_types` |
| `app/models/theme.py` | Create | `Theme` model |
| `app/models/issue_classification.py` | Create | `IssueClassification` model (Map cache) |
| `app/models/work_type_report_snapshot.py` | Create | `WorkTypeReportSnapshot` model |
| `app/models/work_type_report_layout.py` | Create | `WorkTypeReportLayout` model |
| `app/models/mandatory_work_type.py` | Modify | Add `theme_dict_version` |
| `app/schemas/work_type_report.py` | Create | Pydantic schemas (request/response/snapshot data) |
| `app/services/theme_dictionary_service.py` | Create | CRUD + merge + version bump |
| `app/services/llm/work_type_classifier.py` | Create | Map phase: per-issue prompt + parser |
| `app/services/llm/work_type_synthesizer.py` | Create | Reduce phase: synthesis prompt + parser |
| `app/services/llm/faithfulness_validator.py` | Create | Number/key/PII regex check |
| `app/services/work_type_report_service.py` | Create | Orchestrator: build/get/refresh snapshot |
| `app/services/work_type_outlier_detector.py` | Create | Deterministic outlier rules (no LLM) |
| `app/services/work_type_report_xlsx.py` | Create | XLSX export |
| `app/api/endpoints/themes.py` | Create | `/themes` CRUD |
| `app/api/endpoints/work_type_report.py` | Create | `/work-type-report/*` endpoints |
| `app/api/router.py` | Modify | Wire 2 new routers |
| `tests/test_theme_dictionary_service.py` | Create | Service unit tests |
| `tests/test_work_type_classifier.py` | Create | Map-phase tests with fake provider |
| `tests/test_work_type_synthesizer.py` | Create | Reduce-phase tests with fake provider |
| `tests/test_faithfulness_validator.py` | Create | Validator rules |
| `tests/test_work_type_outlier_detector.py` | Create | Outlier rules |
| `tests/test_work_type_report_service.py` | Create | End-to-end build/cache |
| `tests/test_themes_endpoints.py` | Create | Theme CRUD endpoints |
| `tests/test_work_type_report_endpoints.py` | Create | Report endpoints |

### Frontend

| File | Action | Responsibility |
|---|---|---|
| `frontend/src/types/workTypeReport.ts` | Create | TS types |
| `frontend/src/api/themes.ts` | Create | Theme API client |
| `frontend/src/api/workTypeReport.ts` | Create | Report API client |
| `frontend/src/hooks/useThemeDictionary.ts` | Create | Theme queries+mutations |
| `frontend/src/hooks/useWorkTypeReport.ts` | Create | Report queries |
| `frontend/src/hooks/useWorkTypeReportLayouts.ts` | Create | Saved layouts |
| `frontend/src/pages/WorkTypeReportPage.tsx` | Create | Page shell |
| `frontend/src/components/work-type-report/Toolbar.tsx` | Create | Top filters + actions |
| `frontend/src/components/work-type-report/AiHeadline.tsx` | Create | AI headline card |
| `frontend/src/components/work-type-report/KpiRow.tsx` | Create | 4 KPI cards |
| `frontend/src/components/work-type-report/ThemeDistribution.tsx` | Create | Donut + horizontal bars |
| `frontend/src/components/work-type-report/HierarchyTable.tsx` | Create | Tree with grouping |
| `frontend/src/components/work-type-report/GroupingControl.tsx` | Create | Presets + chips + saved |
| `frontend/src/components/work-type-report/ThemeNarrativeRow.tsx` | Create | Inline AI narrative under theme |
| `frontend/src/components/work-type-report/OutliersPanel.tsx` | Create | Right-panel outliers |
| `frontend/src/components/work-type-report/RecommendationCard.tsx` | Create | Right-panel recommendation |
| `frontend/src/components/work-type-report/CandidatesPanel.tsx` | Create | Right-panel + drawer |
| `frontend/src/components/work-type-report/ThemeDictionaryDrawer.tsx` | Create | Dictionary management |
| `frontend/src/components/work-type-report/IssueDrillDownDrawer.tsx` | Create | Issue details + classification |
| `frontend/src/components/work-type-report/ManualReviewBlock.tsx` | Create | Failed-classification tasks |
| `frontend/src/components/work-type-report/EmptyState.tsx` | Create | First-run prompt |
| `frontend/src/components/work-type-report/PrintView.tsx` | Create | PDF print layout |
| `frontend/src/router.tsx` | Modify | Add `/analytics/work-type-report` route |
| `frontend/src/components/Layout/AppSidebar.tsx` | Modify | Add nav link under Analytics |
| `frontend/src/pages/DashboardPage.tsx` | Modify | Click on work-type row → deep-link |
| `frontend/e2e/work-type-report.spec.ts` | Create | Smoke E2E |

---

## Phase 1 — Foundation: DB + Theme Dictionary

### Task 1: Migration + models for themes / classification / snapshot / layout

**Files:**
- Create: `alembic/versions/XXX_work_type_thematic_report.py`
- Create: `app/models/theme.py`, `app/models/issue_classification.py`, `app/models/work_type_report_snapshot.py`, `app/models/work_type_report_layout.py`
- Modify: `app/models/mandatory_work_type.py` (+`theme_dict_version` column)
- Modify: `app/models/__init__.py` (re-export)
- Test: `tests/test_thematic_models.py`

- [ ] **Step 1: Generate migration**

```bash
alembic revision -m "work_type_thematic_report"
```
Note the generated `<hash>` and current head revision.

- [ ] **Step 2: Write migration content**

Set `down_revision = 'e97b35c021a7'` (or whatever current head is — check with `alembic current` first). Use `op.batch_alter_table` for SQLite compatibility.

```python
"""work_type_thematic_report

Adds:
- themes: dictionary per work_type
- issue_classifications: Map cache
- work_type_report_snapshots: full report cache
- work_type_report_layouts: per-user saved pivot layouts
- mandatory_work_types.theme_dict_version: bumped on dict CRUD
"""
from alembic import op
import sqlalchemy as sa

revision = '<hash>'
down_revision = '<head>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'themes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_type_id', sa.String(36), sa.ForeignKey('mandatory_work_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(7), nullable=False, server_default='#00c9c8'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('work_type_id', 'name', name='uq_themes_work_type_name'),
    )
    op.create_index('ix_themes_work_type_active', 'themes', ['work_type_id', 'is_archived'])

    op.create_table(
        'issue_classifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('issue_id', sa.String(36), sa.ForeignKey('issues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('work_type_id', sa.String(36), sa.ForeignKey('mandatory_work_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('theme_id', sa.String(36), sa.ForeignKey('themes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('candidate_name', sa.String(255), nullable=True),
        sa.Column('contribution_text', sa.String(500), nullable=True),
        sa.Column('nature_tag', sa.String(32), nullable=True),
        sa.Column('llm_confidence', sa.Float(), nullable=True),
        sa.Column('model_id', sa.String(120), nullable=True),
        sa.Column('prompt_version', sa.String(32), nullable=True),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('dictionary_version', sa.Integer(), nullable=False),
        sa.Column('failed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('failure_reason', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('issue_id', 'work_type_id', name='uq_classifications_issue_wt'),
    )
    op.create_index('ix_classifications_theme', 'issue_classifications', ['theme_id'])

    op.create_table(
        'work_type_report_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_type_id', sa.String(36), sa.ForeignKey('mandatory_work_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('team_set_hash', sa.String(32), nullable=False),
        sa.Column('team_set_json', sa.Text(), nullable=False),
        sa.Column('snapshot_data', sa.Text(), nullable=False),
        sa.Column('dictionary_version', sa.Integer(), nullable=False),
        sa.Column('model_id', sa.String(120), nullable=True),
        sa.Column('prompt_version', sa.String(32), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('work_type_id', 'year', 'quarter', 'month', 'team_set_hash', name='uq_wt_report_key'),
    )

    op.create_table(
        'work_type_report_layouts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('work_type_id', sa.String(36), sa.ForeignKey('mandatory_work_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('grouping_dims_json', sa.Text(), nullable=False),
        sa.Column('visible_columns_json', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_layouts_user_wt', 'work_type_report_layouts', ['user_id', 'work_type_id'])

    with op.batch_alter_table('mandatory_work_types', schema=None) as batch_op:
        batch_op.add_column(sa.Column('theme_dict_version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('mandatory_work_types', schema=None) as batch_op:
        batch_op.drop_column('theme_dict_version')
    op.drop_index('ix_layouts_user_wt', table_name='work_type_report_layouts')
    op.drop_table('work_type_report_layouts')
    op.drop_table('work_type_report_snapshots')
    op.drop_index('ix_classifications_theme', table_name='issue_classifications')
    op.drop_table('issue_classifications')
    op.drop_index('ix_themes_work_type_active', table_name='themes')
    op.drop_table('themes')
```

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```
Expected: no errors, `themes`, `issue_classifications`, `work_type_report_snapshots`, `work_type_report_layouts` exist; `mandatory_work_types.theme_dict_version` defaults to 1.

- [ ] **Step 4: Add `Theme` model**

Create `app/models/theme.py`:
```python
"""Theme — dictionary entry per work type for thematic reports."""
from typing import Optional
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid


class Theme(Base):
    __tablename__ = "themes"
    __table_args__ = (UniqueConstraint("work_type_id", "name", name="uq_themes_work_type_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#00c9c8")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Theme {self.name} (wt={self.work_type_id})>"
```

- [ ] **Step 5: Add `IssueClassification` model**

Create `app/models/issue_classification.py`:
```python
"""IssueClassification — Map-phase cache (per issue × work type)."""
from typing import Optional
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid


class IssueClassification(Base):
    __tablename__ = "issue_classifications"
    __table_args__ = (UniqueConstraint("issue_id", "work_type_id", name="uq_classifications_issue_wt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False)
    theme_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True, index=True)
    candidate_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contribution_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    nature_tag: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    llm_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dictionary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 6: Add `WorkTypeReportSnapshot` model**

Create `app/models/work_type_report_snapshot.py`:
```python
"""WorkTypeReportSnapshot — full thematic report cache."""
from typing import Optional
from datetime import datetime, date
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid


class WorkTypeReportSnapshot(Base):
    __tablename__ = "work_type_report_snapshots"
    __table_args__ = (UniqueConstraint("work_type_id", "year", "quarter", "month", "team_set_hash", name="uq_wt_report_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    team_set_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    team_set_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_data: Mapped[str] = mapped_column(Text, nullable=False)
    dictionary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

- [ ] **Step 7: Add `WorkTypeReportLayout` model**

Create `app/models/work_type_report_layout.py`:
```python
"""WorkTypeReportLayout — per-user saved pivot/columns layout."""
from typing import Optional
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid


class WorkTypeReportLayout(Base):
    __tablename__ = "work_type_report_layouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    grouping_dims_json: Mapped[str] = mapped_column(Text, nullable=False)
    visible_columns_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 8: Add `theme_dict_version` to MandatoryWorkType model**

Edit `app/models/mandatory_work_type.py` — add field after existing columns:
```python
    theme_dict_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
```
Also add `from sqlalchemy import Integer` to imports if missing.

- [ ] **Step 9: Re-export models**

Edit `app/models/__init__.py` — add:
```python
from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
from app.models.work_type_report_layout import WorkTypeReportLayout
```

- [ ] **Step 10: Smoke test for models**

Create `tests/test_thematic_models.py`:
```python
"""Sanity: тематические модели создаются и связи работают."""
from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
from app.models.work_type_report_layout import WorkTypeReportLayout
from app.models.mandatory_work_type import MandatoryWorkType
import json
from datetime import date


def test_theme_create(db_session):
    wt = MandatoryWorkType(code="t1", label="T1", sort_order=1)
    db_session.add(wt)
    db_session.commit()
    t = Theme(work_type_id=wt.id, name="Тест", color="#00c9c8")
    db_session.add(t)
    db_session.commit()
    assert t.id and t.is_archived is False


def test_theme_unique_per_work_type(db_session):
    wt = MandatoryWorkType(code="t2", label="T2", sort_order=1)
    db_session.add(wt); db_session.commit()
    db_session.add(Theme(work_type_id=wt.id, name="Тема"))
    db_session.commit()
    db_session.add(Theme(work_type_id=wt.id, name="Тема"))
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_snapshot_unique_key(db_session):
    wt = MandatoryWorkType(code="t3", label="T3", sort_order=1)
    db_session.add(wt); db_session.commit()
    s = WorkTypeReportSnapshot(
        work_type_id=wt.id, year=2026, quarter=2, month=4,
        start_date=date(2026,4,1), end_date=date(2026,4,30),
        team_set_hash="abc", team_set_json=json.dumps([]),
        snapshot_data=json.dumps({}), dictionary_version=1,
    )
    db_session.add(s); db_session.commit()
    assert s.id


def test_work_type_has_dict_version(db_session):
    wt = MandatoryWorkType(code="t4", label="T4", sort_order=1)
    db_session.add(wt); db_session.commit()
    db_session.refresh(wt)
    assert wt.theme_dict_version == 1
```

- [ ] **Step 11: Run tests**

```bash
py -3.10 -m pytest tests/test_thematic_models.py -v
```
Expected: 4 passed.

- [ ] **Step 12: Commit**

```bash
git add alembic/versions/*work_type_thematic_report.py app/models/theme.py app/models/issue_classification.py app/models/work_type_report_snapshot.py app/models/work_type_report_layout.py app/models/mandatory_work_type.py app/models/__init__.py tests/test_thematic_models.py
git commit -m "feat(thematic): add theme/classification/snapshot/layout models + migration"
```

---

### Task 2: ThemeDictionaryService — CRUD, merge, archive, version bump

**Files:**
- Create: `app/services/theme_dictionary_service.py`
- Test: `tests/test_theme_dictionary_service.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_theme_dictionary_service.py`:
```python
"""ThemeDictionaryService: CRUD, merge, archive, version bumps."""
import pytest
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.issue import Issue
from app.models.project import Project
from app.services.theme_dictionary_service import ThemeDictionaryService


@pytest.fixture
def wt(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопр", sort_order=1)
    db_session.add(wt); db_session.commit()
    return wt


def test_create_theme_bumps_version(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    v0 = wt.theme_dict_version
    t = svc.create_theme(work_type_id=wt.id, name="Ошибки обмена", description="...", color="#00c9c8")
    db_session.refresh(wt)
    assert t.id and t.name == "Ошибки обмена"
    assert wt.theme_dict_version == v0 + 1


def test_rename_theme_bumps_version(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    t = svc.create_theme(work_type_id=wt.id, name="A")
    v_after_create = wt.theme_dict_version
    svc.update_theme(theme_id=t.id, name="B")
    db_session.refresh(wt)
    assert wt.theme_dict_version == v_after_create + 1


def test_archive_theme_bumps_version(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    t = svc.create_theme(work_type_id=wt.id, name="A")
    v = wt.theme_dict_version
    svc.archive_theme(t.id)
    db_session.refresh(wt); db_session.refresh(t)
    assert t.is_archived is True
    assert wt.theme_dict_version == v + 1


def test_merge_theme_reassigns_classifications(db_session, wt):
    """Merge T_src into T_dst → classifications re-pointed, T_src archived."""
    svc = ThemeDictionaryService(db_session)
    proj = Project(jira_project_id="P1", key="PROJ", name="Proj")
    db_session.add(proj); db_session.commit()
    issue = Issue(jira_issue_id="i1", key="PROJ-1", summary="x", issue_type="Task", status="Open", project_id=proj.id)
    db_session.add(issue); db_session.commit()

    t_src = svc.create_theme(work_type_id=wt.id, name="Src")
    t_dst = svc.create_theme(work_type_id=wt.id, name="Dst")
    cls = IssueClassification(issue_id=issue.id, work_type_id=wt.id, theme_id=t_src.id, input_hash="h", dictionary_version=1)
    db_session.add(cls); db_session.commit()

    svc.merge_theme(src_id=t_src.id, dst_id=t_dst.id)
    db_session.refresh(cls); db_session.refresh(t_src)
    assert cls.theme_id == t_dst.id
    assert t_src.is_archived is True


def test_unique_name_per_work_type(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    svc.create_theme(work_type_id=wt.id, name="Dup")
    with pytest.raises(ValueError, match="exists"):
        svc.create_theme(work_type_id=wt.id, name="Dup")


def test_list_active_excludes_archived(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    a = svc.create_theme(work_type_id=wt.id, name="A")
    b = svc.create_theme(work_type_id=wt.id, name="B")
    svc.archive_theme(b.id)
    active = svc.list_active(wt.id)
    assert [t.id for t in active] == [a.id]
```

- [ ] **Step 2: Run test (should fail — service missing)**

```bash
py -3.10 -m pytest tests/test_theme_dictionary_service.py -v
```
Expected: ImportError or AttributeError.

- [ ] **Step 3: Implement service**

Create `app/services/theme_dictionary_service.py`:
```python
"""ThemeDictionaryService — CRUD словаря тем + слияние + архивация.

Любая мутация словаря поднимает MandatoryWorkType.theme_dict_version,
что инвалидирует кэш классификации задач при следующем построении.
"""
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.mandatory_work_type import MandatoryWorkType


class ThemeDictionaryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_active(self, work_type_id: str) -> list[Theme]:
        q = select(Theme).where(
            Theme.work_type_id == work_type_id,
            Theme.is_archived.is_(False),
        ).order_by(Theme.sort_order, Theme.name)
        return list(self.db.execute(q).scalars().all())

    def list_all(self, work_type_id: str) -> list[Theme]:
        q = select(Theme).where(Theme.work_type_id == work_type_id).order_by(Theme.is_archived, Theme.sort_order, Theme.name)
        return list(self.db.execute(q).scalars().all())

    def get(self, theme_id: str) -> Optional[Theme]:
        return self.db.get(Theme, theme_id)

    def create_theme(self, *, work_type_id: str, name: str, description: Optional[str] = None,
                     color: str = "#00c9c8", sort_order: int = 0, created_by: Optional[str] = None) -> Theme:
        existing = self.db.execute(
            select(Theme).where(Theme.work_type_id == work_type_id, Theme.name == name)
        ).scalar_one_or_none()
        if existing:
            raise ValueError(f"Theme '{name}' already exists for work_type={work_type_id}")
        t = Theme(work_type_id=work_type_id, name=name, description=description, color=color,
                  sort_order=sort_order, created_by=created_by)
        self.db.add(t)
        self._bump_version(work_type_id)
        self.db.commit()
        self.db.refresh(t)
        return t

    def update_theme(self, *, theme_id: str, name: Optional[str] = None,
                     description: Optional[str] = None, color: Optional[str] = None,
                     sort_order: Optional[int] = None) -> Theme:
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        changed = False
        if name is not None and name != t.name:
            dup = self.db.execute(
                select(Theme).where(Theme.work_type_id == t.work_type_id, Theme.name == name, Theme.id != t.id)
            ).scalar_one_or_none()
            if dup:
                raise ValueError(f"Theme '{name}' already exists")
            t.name = name; changed = True
        if description is not None:
            t.description = description; changed = True
        if color is not None:
            t.color = color; changed = True
        if sort_order is not None:
            t.sort_order = sort_order; changed = True
        if changed:
            self._bump_version(t.work_type_id)
        self.db.commit()
        self.db.refresh(t)
        return t

    def archive_theme(self, theme_id: str) -> Theme:
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        if not t.is_archived:
            t.is_archived = True
            self._bump_version(t.work_type_id)
        self.db.commit()
        self.db.refresh(t)
        return t

    def restore_theme(self, theme_id: str) -> Theme:
        t = self.db.get(Theme, theme_id)
        if not t:
            raise ValueError(f"Theme {theme_id} not found")
        if t.is_archived:
            t.is_archived = False
            self._bump_version(t.work_type_id)
        self.db.commit()
        self.db.refresh(t)
        return t

    def merge_theme(self, *, src_id: str, dst_id: str) -> None:
        """Перенести все классификации из src в dst, src архивировать."""
        src = self.db.get(Theme, src_id)
        dst = self.db.get(Theme, dst_id)
        if not src or not dst:
            raise ValueError("Source or destination theme not found")
        if src.work_type_id != dst.work_type_id:
            raise ValueError("Cannot merge themes across different work types")
        self.db.execute(
            update(IssueClassification)
            .where(IssueClassification.theme_id == src_id)
            .values(theme_id=dst_id)
        )
        src.is_archived = True
        self._bump_version(src.work_type_id)
        self.db.commit()

    def _bump_version(self, work_type_id: str) -> None:
        wt = self.db.get(MandatoryWorkType, work_type_id)
        if wt:
            wt.theme_dict_version = (wt.theme_dict_version or 0) + 1
```

- [ ] **Step 4: Run tests**

```bash
py -3.10 -m pytest tests/test_theme_dictionary_service.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/theme_dictionary_service.py tests/test_theme_dictionary_service.py
git commit -m "feat(thematic): theme dictionary service (CRUD + merge + version bumps)"
```

---

### Task 3: Themes API endpoints

**Files:**
- Create: `app/schemas/work_type_report.py` (theme schemas part)
- Create: `app/api/endpoints/themes.py`
- Modify: `app/api/router.py`
- Test: `tests/test_themes_endpoints.py`

- [ ] **Step 1: Write failing endpoint tests**

Create `tests/test_themes_endpoints.py`:
```python
"""Themes API: list active, create, update, archive, restore, merge, candidates."""
import pytest
from app.models.mandatory_work_type import MandatoryWorkType


@pytest.fixture
def wt(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопр", sort_order=1)
    db_session.add(wt); db_session.commit()
    return wt


def test_list_themes_empty(client_authed, wt):
    r = client_authed.get(f"/api/v1/themes?work_type_id={wt.id}")
    assert r.status_code == 200
    assert r.json() == {"themes": [], "candidates": []}


def test_create_and_list(client_authed, wt):
    r = client_authed.post("/api/v1/themes", json={
        "work_type_id": wt.id, "name": "Ошибки обмена", "description": "", "color": "#00c9c8"
    })
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    r = client_authed.get(f"/api/v1/themes?work_type_id={wt.id}")
    assert r.status_code == 200
    themes = r.json()["themes"]
    assert len(themes) == 1 and themes[0]["id"] == tid


def test_update_rename(client_authed, wt):
    r = client_authed.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Old"})
    tid = r.json()["id"]
    r = client_authed.patch(f"/api/v1/themes/{tid}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


def test_archive_then_restore(client_authed, wt):
    r = client_authed.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "X"})
    tid = r.json()["id"]
    assert client_authed.post(f"/api/v1/themes/{tid}/archive").status_code == 200
    listing = client_authed.get(f"/api/v1/themes?work_type_id={wt.id}").json()
    assert listing["themes"] == []  # archived hidden from default list
    listing_all = client_authed.get(f"/api/v1/themes?work_type_id={wt.id}&include_archived=true").json()
    assert any(t["id"] == tid for t in listing_all["themes"])
    assert client_authed.post(f"/api/v1/themes/{tid}/restore").status_code == 200


def test_merge(client_authed, wt):
    r1 = client_authed.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Src"})
    r2 = client_authed.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Dst"})
    sid, did = r1.json()["id"], r2.json()["id"]
    r = client_authed.post(f"/api/v1/themes/{sid}/merge", json={"target_theme_id": did})
    assert r.status_code == 200


def test_duplicate_name_409(client_authed, wt):
    client_authed.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Dup"})
    r = client_authed.post("/api/v1/themes", json={"work_type_id": wt.id, "name": "Dup"})
    assert r.status_code == 409
```

- [ ] **Step 2: Add Pydantic schemas**

Create `app/schemas/work_type_report.py` (start with theme part — extend in later tasks):
```python
"""Pydantic schemas for thematic work-type report."""
from datetime import date, datetime
from typing import Any, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---- Themes ----

class ThemeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    color: str = Field(default="#00c9c8", pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: int = 0


class ThemeCreateRequest(ThemeBase):
    work_type_id: str


class ThemeUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: Optional[int] = None


class ThemeMergeRequest(BaseModel):
    target_theme_id: str


class ThemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    work_type_id: str
    name: str
    description: Optional[str]
    color: str
    sort_order: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ThemeCandidate(BaseModel):
    """Кандидат в словарь — из ведра «Другое» свежего снапшота."""
    proposed_name: str
    issues_count: int
    hours: float
    sample_keys: list[str]
    snapshot_id: str


class ThemeListResponse(BaseModel):
    themes: list[ThemeOut]
    candidates: list[ThemeCandidate]
```

- [ ] **Step 3: Implement endpoints**

Create `app/api/endpoints/themes.py`:
```python
"""Themes API — словарь тем для тематических отчётов."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.schemas.work_type_report import (
    ThemeCreateRequest, ThemeUpdateRequest, ThemeMergeRequest,
    ThemeOut, ThemeListResponse,
)
from app.services.theme_dictionary_service import ThemeDictionaryService


router = APIRouter()


@router.get("", response_model=ThemeListResponse)
def list_themes(
    work_type_id: str = Query(...),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    themes = svc.list_all(work_type_id) if include_archived else svc.list_active(work_type_id)
    return ThemeListResponse(
        themes=[ThemeOut.model_validate(t) for t in themes],
        candidates=[],  # populated in Task 11
    )


@router.post("", response_model=ThemeOut, status_code=201)
def create_theme(
    payload: ThemeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.create_theme(
            work_type_id=payload.work_type_id,
            name=payload.name, description=payload.description,
            color=payload.color, sort_order=payload.sort_order,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ThemeOut.model_validate(t)


@router.patch("/{theme_id}", response_model=ThemeOut)
def update_theme(
    theme_id: str,
    payload: ThemeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.update_theme(theme_id=theme_id, **payload.model_dump(exclude_unset=True))
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(409, msg)
    return ThemeOut.model_validate(t)


@router.post("/{theme_id}/archive", response_model=ThemeOut)
def archive_theme(theme_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.archive_theme(theme_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ThemeOut.model_validate(t)


@router.post("/{theme_id}/restore", response_model=ThemeOut)
def restore_theme(theme_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.restore_theme(theme_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ThemeOut.model_validate(t)


@router.post("/{theme_id}/merge")
def merge_theme(theme_id: str, payload: ThemeMergeRequest,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    svc = ThemeDictionaryService(db)
    try:
        svc.merge_theme(src_id=theme_id, dst_id=payload.target_theme_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
```

- [ ] **Step 4: Wire router**

Edit `app/api/router.py` — add:
```python
from app.api.endpoints import themes as themes_endpoints
api_router.include_router(themes_endpoints.router, prefix="/themes", tags=["themes"])
```

- [ ] **Step 5: Run endpoint tests**

```bash
py -3.10 -m pytest tests/test_themes_endpoints.py -v
```
Expected: 6 passed. If `client_authed` fixture missing — check `tests/conftest.py` for existing pattern (project has auth in test setup).

- [ ] **Step 6: Commit**

```bash
git add app/schemas/work_type_report.py app/api/endpoints/themes.py app/api/router.py tests/test_themes_endpoints.py
git commit -m "feat(thematic): themes API (list/create/update/archive/restore/merge)"
```

---

## Phase 2 — LLM Pipeline (Map + Reduce)

### Task 4: WorkTypeClassifier (Map phase)

**Files:**
- Create: `app/services/llm/work_type_classifier.py`
- Test: `tests/test_work_type_classifier.py`

- [ ] **Step 1: Write tests with fake provider**

Create `tests/test_work_type_classifier.py`:
```python
"""WorkTypeClassifier — Map-фаза: разметка задач по словарю + ведро Другое."""
import json
import pytest
from unittest.mock import AsyncMock

from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.models.issue import Issue
from app.models.project import Project
from app.models.worklog import Worklog
from app.models.employee import Employee
from app.models.issue_classification import IssueClassification
from app.services.llm.work_type_classifier import (
    WorkTypeClassifier, ClassificationResult, build_input_hash,
)


@pytest.fixture
def fixture_setup(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопр", sort_order=1)
    db_session.add(wt); db_session.commit()
    proj = Project(jira_project_id="P", key="PROJ", name="Proj")
    db_session.add(proj); db_session.commit()
    issue = Issue(jira_issue_id="i1", key="PROJ-1",
                  summary="Ошибка обмена", description="d",
                  goal_text="g", current_behavior="b",
                  issue_type="Task", status="Done", project_id=proj.id)
    db_session.add(issue); db_session.commit()
    return {"wt": wt, "issue": issue}


def test_input_hash_stable(fixture_setup, db_session):
    issue = fixture_setup["issue"]
    h1 = build_input_hash(issue, worklog_comments=["c1", "c2"])
    h2 = build_input_hash(issue, worklog_comments=["c1", "c2"])
    assert h1 == h2 and len(h1) == 64


def test_input_hash_changes_on_summary_edit(fixture_setup, db_session):
    issue = fixture_setup["issue"]
    h1 = build_input_hash(issue, worklog_comments=[])
    issue.summary = "Другое"
    h2 = build_input_hash(issue, worklog_comments=[])
    assert h1 != h2


@pytest.mark.asyncio
async def test_classify_creates_classification(fixture_setup, db_session):
    wt, issue = fixture_setup["wt"], fixture_setup["issue"]
    theme = Theme(work_type_id=wt.id, name="Ошибки обмена")
    db_session.add(theme); db_session.commit()

    fake_provider = AsyncMock()
    fake_provider.model = "test-model"
    fake_provider.classify_issue = AsyncMock(return_value=(
        ClassificationResult(theme_id=theme.id, candidate_name=None,
                             contribution_text="разбор сбоев", confidence=0.9, nature_tag=None),
        {"model": "test-model", "input_tokens": 100, "output_tokens": 30},
    ))

    clf = WorkTypeClassifier(db_session, provider=fake_provider)
    cls = await clf.classify_issue(issue=issue, work_type_id=wt.id, themes=[theme])
    assert cls.theme_id == theme.id and cls.contribution_text == "разбор сбоев"
    assert cls.input_hash and cls.dictionary_version == wt.theme_dict_version


@pytest.mark.asyncio
async def test_classify_cached_skips_llm(fixture_setup, db_session):
    wt, issue = fixture_setup["wt"], fixture_setup["issue"]
    theme = Theme(work_type_id=wt.id, name="X")
    db_session.add(theme); db_session.commit()

    fake_provider = AsyncMock(); fake_provider.model = "m"; fake_provider.classify_issue = AsyncMock()
    clf = WorkTypeClassifier(db_session, provider=fake_provider)

    # Pre-seed classification
    h = build_input_hash(issue, worklog_comments=[])
    db_session.add(IssueClassification(
        issue_id=issue.id, work_type_id=wt.id, theme_id=theme.id,
        contribution_text="cached", input_hash=h, dictionary_version=wt.theme_dict_version,
    ))
    db_session.commit()

    cls = await clf.classify_issue(issue=issue, work_type_id=wt.id, themes=[theme])
    assert cls.contribution_text == "cached"
    fake_provider.classify_issue.assert_not_called()


@pytest.mark.asyncio
async def test_dictionary_version_change_invalidates_cache(fixture_setup, db_session):
    wt, issue = fixture_setup["wt"], fixture_setup["issue"]
    theme = Theme(work_type_id=wt.id, name="X")
    db_session.add(theme); db_session.commit()
    h = build_input_hash(issue, worklog_comments=[])
    db_session.add(IssueClassification(
        issue_id=issue.id, work_type_id=wt.id, theme_id=theme.id,
        input_hash=h, dictionary_version=wt.theme_dict_version - 1,  # stale
    ))
    db_session.commit()

    fake_provider = AsyncMock(); fake_provider.model = "m"
    fake_provider.classify_issue = AsyncMock(return_value=(
        ClassificationResult(theme_id=theme.id, candidate_name=None,
                             contribution_text="fresh", confidence=0.8, nature_tag=None),
        {"model": "m"},
    ))
    clf = WorkTypeClassifier(db_session, provider=fake_provider)
    cls = await clf.classify_issue(issue=issue, work_type_id=wt.id, themes=[theme])
    assert cls.contribution_text == "fresh"


@pytest.mark.asyncio
async def test_classify_failure_marks_failed_not_raise(fixture_setup, db_session):
    wt, issue = fixture_setup["wt"], fixture_setup["issue"]
    fake = AsyncMock(); fake.model = "m"
    fake.classify_issue = AsyncMock(side_effect=RuntimeError("LLM down"))
    clf = WorkTypeClassifier(db_session, provider=fake)
    cls = await clf.classify_issue(issue=issue, work_type_id=wt.id, themes=[])
    assert cls.failed is True and cls.failure_reason
```

- [ ] **Step 2: Implement classifier**

Create `app/services/llm/work_type_classifier.py`:
```python
"""Map-фаза тематического отчёта: per-issue классификация по словарю.

Кэш per-issue: input_hash + dictionary_version. При совпадении — LLM не дёргается.
"""
import hashlib
from dataclasses import dataclass
from typing import Optional, Protocol
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.worklog import Worklog


PROMPT_VERSION = "wt-classify-v1"


@dataclass
class ClassificationResult:
    theme_id: Optional[str]
    candidate_name: Optional[str]
    contribution_text: Optional[str]
    confidence: float
    nature_tag: Optional[str] = None


class ClassifierProvider(Protocol):
    model: str
    async def classify_issue(self, prompt: str, themes_payload: list[dict]) -> tuple[ClassificationResult, dict]: ...


def build_input_hash(issue: Issue, worklog_comments: list[str]) -> str:
    parts = [
        issue.summary or "", issue.goal_text or "",
        issue.current_behavior or "", issue.description or "",
        "\n".join(worklog_comments or []),
    ]
    h = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return h


def collect_worklog_comments(db: Session, issue_id: str, start_date, end_date) -> list[str]:
    q = select(Worklog.comment).where(
        Worklog.issue_id == issue_id,
        Worklog.started_at >= start_date,
        Worklog.started_at < end_date,
    ).order_by(Worklog.started_at)
    return [c for c in db.execute(q).scalars().all() if c]


def build_classify_prompt(issue: Issue, worklog_comments: list[str], themes: list[Theme]) -> str:
    """Промпт Map-фазы. Вход: задача + поля + комменты + словарь. Выход: JSON-схема."""
    themes_list = "\n".join(
        f"- {t.id}: «{t.name}»" + (f" — {t.description}" if t.description else "")
        for t in themes
    ) or "(словарь пуст)"
    parts = [
        "Ты — аналитик. Классифицируй задачу-сопровождение по теме из словаря.",
        "Если ни одна тема не подходит — верни theme_id=null и предложи название новой темы.",
        "",
        f"Задача [{issue.key}] [{issue.issue_type}]: {issue.summary}",
    ]
    if issue.goal_text:
        parts.append(f"Цель: {issue.goal_text[:2000]}")
    if issue.current_behavior:
        parts.append(f"Текущее поведение: {issue.current_behavior[:2000]}")
    if issue.description:
        parts.append(f"Описание: {issue.description[:3000]}")
    if worklog_comments:
        parts.append("Комментарии ворклогов:")
        for c in worklog_comments[:30]:
            parts.append(f"  • {c[:500]}")
    parts.extend(["", "Словарь тем:", themes_list, "",
                  "Верни JSON: {theme_id, candidate_name, contribution_text (≤200 chars), confidence (0..1)}.",
                  "Не упоминай ФИО."])
    return "\n".join(parts)


class WorkTypeClassifier:
    def __init__(self, db: Session, provider: ClassifierProvider) -> None:
        self.db = db
        self.provider = provider

    async def classify_issue(
        self, *, issue: Issue, work_type_id: str, themes: list[Theme],
        period_start=None, period_end=None,
    ) -> IssueClassification:
        wt = self.db.get(MandatoryWorkType, work_type_id)
        if not wt:
            raise ValueError(f"Work type {work_type_id} not found")
        comments = collect_worklog_comments(self.db, issue.id, period_start, period_end) if period_start else []
        h = build_input_hash(issue, comments)
        existing = self.db.execute(
            select(IssueClassification).where(
                IssueClassification.issue_id == issue.id,
                IssueClassification.work_type_id == work_type_id,
            )
        ).scalar_one_or_none()
        if existing and existing.input_hash == h and existing.dictionary_version == wt.theme_dict_version:
            return existing

        prompt = build_classify_prompt(issue, comments, themes)
        themes_payload = [{"id": t.id, "name": t.name, "description": t.description} for t in themes]
        try:
            res, meta = await self.provider.classify_issue(prompt, themes_payload)
        except Exception as e:
            return self._upsert(existing, issue, work_type_id, h, wt.theme_dict_version,
                                failed=True, failure_reason=str(e)[:500])

        return self._upsert(existing, issue, work_type_id, h, wt.theme_dict_version,
                            theme_id=res.theme_id, candidate_name=res.candidate_name,
                            contribution_text=res.contribution_text, confidence=res.confidence,
                            nature_tag=res.nature_tag, model_id=meta.get("model"))

    def _upsert(self, existing, issue, work_type_id, input_hash, dict_version, **kwargs) -> IssueClassification:
        if existing:
            existing.input_hash = input_hash
            existing.dictionary_version = dict_version
            existing.updated_at = datetime.utcnow()
            for k, v in kwargs.items():
                setattr(existing, "llm_confidence" if k == "confidence" else k, v)
            existing.prompt_version = PROMPT_VERSION
            self.db.commit(); self.db.refresh(existing)
            return existing
        cls = IssueClassification(
            issue_id=issue.id, work_type_id=work_type_id,
            input_hash=input_hash, dictionary_version=dict_version,
            prompt_version=PROMPT_VERSION,
            llm_confidence=kwargs.pop("confidence", None),
            **kwargs,
        )
        self.db.add(cls); self.db.commit(); self.db.refresh(cls)
        return cls
```

- [ ] **Step 3: Run tests**

```bash
py -3.10 -m pytest tests/test_work_type_classifier.py -v
```
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add app/services/llm/work_type_classifier.py tests/test_work_type_classifier.py
git commit -m "feat(thematic): Map-phase classifier (per-issue + cache + dict version)"
```

---

### Task 5: ClassifierProvider implementation (OpenRouter / Gemini wiring)

**Files:**
- Modify: `app/services/llm/openrouter.py` (+ `classify_issue` method)
- Modify: `app/services/llm/gemini.py` (+ `classify_issue` method)
- Modify: `app/services/llm/base.py` (factory adds classifier-capable providers)
- Test: `tests/test_classifier_provider.py`

- [ ] **Step 1: Read existing provider patterns**

Read `app/services/llm/openrouter.py` and `app/services/llm/gemini.py` fully — understand `summarize_project()` structure (HTTP call, JSON parsing, fallback chain). The new `classify_issue()` mirrors this.

- [ ] **Step 2: Add `classify_issue` to OpenRouterProvider**

Append method to `OpenRouterProvider` in `app/services/llm/openrouter.py`:
```python
async def classify_issue(self, prompt: str, themes_payload: list[dict]) -> tuple["ClassificationResult", dict]:
    """Map-фаза тематического отчёта.

    Вход: prompt (build_classify_prompt) + themes_payload (для validation).
    Выход: ClassificationResult + meta. Использует ту же fallback-цепочку.
    """
    from app.services.llm.work_type_classifier import ClassificationResult
    schema = {
        "type": "object",
        "properties": {
            "theme_id": {"type": ["string", "null"]},
            "candidate_name": {"type": ["string", "null"]},
            "contribution_text": {"type": ["string", "null"], "maxLength": 200},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["theme_id", "confidence"],
    }
    valid_ids = {t["id"] for t in themes_payload}
    chain = [self.model] + [m for m in self.fallback_models if m and m != self.model]
    last_exc = None
    for model_id in chain:
        try:
            obj, meta = await self._call_json(model_id, prompt, schema)
            tid = obj.get("theme_id")
            if tid and tid not in valid_ids:
                tid = None  # AI invented a theme id — treat as candidate
            return ClassificationResult(
                theme_id=tid,
                candidate_name=(obj.get("candidate_name") or "").strip()[:255] or None,
                contribution_text=(obj.get("contribution_text") or "").strip()[:200] or None,
                confidence=float(obj.get("confidence") or 0.0),
                nature_tag=None,
            ), meta
        except Exception as e:
            last_exc = e; continue
    raise last_exc or LLMResponseError("classify_issue: all models failed")
```
If `_call_json(model_id, prompt, schema)` doesn't exist yet, factor it out from existing `summarize_project` code: a helper that POSTs to chat/completions with `response_format={"type":"json_schema","json_schema":{...}}` and returns `(parsed_dict, meta_dict)`. Keep existing `summarize_project` untouched — make it call the helper.

- [ ] **Step 3: Add `classify_issue` to GeminiProvider**

Mirror in `app/services/llm/gemini.py`. Use Gemini's `responseSchema` to enforce JSON.

- [ ] **Step 4: Provider tests with stubbed HTTP**

Create `tests/test_classifier_provider.py` — use `httpx.MockTransport` to feed a JSON response and assert the result is parsed into `ClassificationResult` correctly. Cover: valid theme_id, null theme_id with candidate_name, invalid theme_id (AI hallucinated → forced to null), 429 fallback to second model.

```python
"""Provider-level classify_issue: parsing + fallback + invalid theme_id handling."""
import httpx, pytest
from app.services.llm.openrouter import OpenRouterProvider
from app.services.llm.work_type_classifier import ClassificationResult


def _make_response(payload: dict, status: int = 200, model: str = "test-model") -> httpx.Response:
    body = {
        "choices": [{"message": {"content": __import__("json").dumps(payload)}}],
        "model": model,
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    return httpx.Response(status, json=body)


@pytest.mark.asyncio
async def test_valid_theme_id_passes_through(monkeypatch):
    transport = httpx.MockTransport(lambda req: _make_response(
        {"theme_id": "T1", "candidate_name": None, "contribution_text": "x", "confidence": 0.9}
    ))
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}))
    p = OpenRouterProvider(api_key="k", model="m1", fallback_models=[])
    res, meta = await p.classify_issue("prompt", [{"id": "T1", "name": "X", "description": None}])
    assert res.theme_id == "T1" and res.confidence == 0.9


@pytest.mark.asyncio
async def test_invalid_theme_id_becomes_null(monkeypatch):
    transport = httpx.MockTransport(lambda req: _make_response(
        {"theme_id": "ZZZ-not-in-payload", "candidate_name": "Новая тема", "contribution_text": "y", "confidence": 0.5}
    ))
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}))
    p = OpenRouterProvider(api_key="k", model="m1", fallback_models=[])
    res, _ = await p.classify_issue("prompt", [{"id": "T1", "name": "X", "description": None}])
    assert res.theme_id is None and res.candidate_name == "Новая тема"


@pytest.mark.asyncio
async def test_429_falls_back_to_second_model(monkeypatch):
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "rate"})
        return _make_response({"theme_id": None, "candidate_name": None,
                               "contribution_text": "ok", "confidence": 0.5}, model="m2")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}))
    p = OpenRouterProvider(api_key="k", model="m1", fallback_models=["m2"])
    res, meta = await p.classify_issue("prompt", [])
    assert res.contribution_text == "ok" and meta.get("model") == "m2"
```

- [ ] **Step 5: Run tests**

```bash
py -3.10 -m pytest tests/test_classifier_provider.py -v
```

- [ ] **Step 6: Commit**

```bash
git add app/services/llm/openrouter.py app/services/llm/gemini.py tests/test_classifier_provider.py
git commit -m "feat(thematic): provider-level classify_issue (OpenRouter+Gemini, fallback, invalid-id guard)"
```

---

### Task 6: Outlier detector (deterministic, no LLM)

**Files:**
- Create: `app/services/work_type_outlier_detector.py`
- Test: `tests/test_work_type_outlier_detector.py`

- [ ] **Step 1: Tests**

Create `tests/test_work_type_outlier_detector.py`. Build small fixtures with 10 issues, varying hours, then assert detector returns top-N by:
- hours > P85 of theme,
- reopen count ≥ 3 (use `Issue.status_category` transitions or proxy: count of "Done"→other transitions in changelog if available; if not, use `category_verified` history table — read existing repo for transition signals before implementing),
- distinct workers > 5 (count distinct `Worklog.employee_id`),
- in-progress > 14 days (today − issue.updated_at, status not Done).

Each rule has a unit test with a small dataset.

- [ ] **Step 2: Implement detector**

```python
"""Deterministic outlier detection per theme — no LLM."""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.worklog import Worklog


@dataclass
class OutlierCandidate:
    issue_id: str
    issue_key: str
    summary: str
    reason: str   # "high_hours" | "many_reopens" | "many_workers" | "stale"
    value: float
    context: str


def detect_outliers_for_theme(db: Session, *, theme_issues: list[dict],
                              theme_p85: float | None = None,
                              today: date | None = None) -> list[OutlierCandidate]:
    """theme_issues: [{issue_id, key, summary, hours, distinct_workers, days_in_progress, reopen_count}, ...]
    p85: precomputed 85th percentile of hours for theme.
    Returns up to top-5 by severity."""
    today = today or date.today()
    out: list[OutlierCandidate] = []
    if theme_p85 is None and theme_issues:
        sorted_h = sorted(i["hours"] for i in theme_issues)
        idx = int(0.85 * (len(sorted_h) - 1))
        theme_p85 = sorted_h[idx] if sorted_h else 0
    for it in theme_issues:
        if theme_p85 and it["hours"] > theme_p85 and it["hours"] >= 16:
            out.append(OutlierCandidate(
                issue_id=it["issue_id"], issue_key=it["key"], summary=it["summary"],
                reason="high_hours", value=it["hours"],
                context=f"{it['distinct_workers']} сотрудников · {it.get('worklog_count',0)} ворклогов · {it['days_in_progress']} дней",
            ))
        if it.get("reopen_count", 0) >= 3:
            out.append(OutlierCandidate(it["issue_id"], it["key"], it["summary"],
                                        "many_reopens", float(it["reopen_count"]),
                                        f"переоткрыта {it['reopen_count']}×"))
        if it.get("distinct_workers", 0) > 5:
            out.append(OutlierCandidate(it["issue_id"], it["key"], it["summary"],
                                        "many_workers", float(it["distinct_workers"]),
                                        f"{it['distinct_workers']} разных сотрудников"))
        if it.get("days_in_progress", 0) > 14 and not it.get("is_done"):
            out.append(OutlierCandidate(it["issue_id"], it["key"], it["summary"],
                                        "stale", float(it["days_in_progress"]),
                                        f"в работе {it['days_in_progress']} дней"))
    # dedup by (issue_id, reason); top-5 by value
    seen = set(); deduped = []
    for o in sorted(out, key=lambda x: -x.value):
        k = (o.issue_id, o.reason)
        if k in seen: continue
        seen.add(k); deduped.append(o)
        if len(deduped) >= 5: break
    return deduped
```

(Reopen count needs a real source — if `IssueChangelog` table exists in repo, read it; else compute from `IssueStatusHistory`. Inspect the codebase before implementing this part. If neither exists, mark `reopen_count=0` for now and note it as a follow-up in the snapshot data.)

- [ ] **Step 3: Run tests**

```bash
py -3.10 -m pytest tests/test_work_type_outlier_detector.py -v
```

- [ ] **Step 4: Commit**

```bash
git add app/services/work_type_outlier_detector.py tests/test_work_type_outlier_detector.py
git commit -m "feat(thematic): deterministic outlier detector (hours/reopens/workers/stale)"
```

---

### Task 7: WorkTypeSynthesizer (Reduce phase) + faithfulness validator

**Files:**
- Create: `app/services/llm/faithfulness_validator.py`
- Create: `app/services/llm/work_type_synthesizer.py`
- Test: `tests/test_faithfulness_validator.py`, `tests/test_work_type_synthesizer.py`

- [ ] **Step 1: Faithfulness validator tests**

```python
"""FaithfulnessValidator — числа и ключи задач должны быть в findings."""
from app.services.llm.faithfulness_validator import (
    validate_synthesis, FaithfulnessReport,
)


def test_clean_passes():
    findings = {"totals": {"hours": 540}, "themes": [{"hours": 173, "pct": 32, "name": "X", "evidence_keys": ["PROJ-321"]}]}
    output = {"headline": "540 ч; X — 32% (PROJ-321)", "themes_narratives": [], "outliers_explanations": [], "recommendation": {"text": "x", "expected_impact": "y"}}
    rep = validate_synthesis(output, findings, employee_names={"Иванов И."})
    assert rep.ok and not rep.errors


def test_unknown_number_fails():
    findings = {"totals": {"hours": 540}, "themes": []}
    output = {"headline": "999 ч", "themes_narratives": [], "outliers_explanations": [], "recommendation": {"text":"","expected_impact":""}}
    rep = validate_synthesis(output, findings, employee_names=set())
    assert not rep.ok and any("999" in e for e in rep.errors)


def test_unknown_key_fails():
    findings = {"totals": {"hours": 540}, "themes": [{"evidence_keys": ["PROJ-1"]}]}
    output = {"headline": "ok", "themes_narratives": [{"theme_id":"t","narrative":"see PROJ-9999 broken","evidence_keys":[]}], "outliers_explanations": [], "recommendation": {"text":"","expected_impact":""}}
    rep = validate_synthesis(output, findings, employee_names=set())
    assert not rep.ok


def test_employee_name_in_text_fails():
    findings = {"totals": {"hours": 100}, "themes": []}
    output = {"headline": "Иванов И. сделал больше всех", "themes_narratives": [], "outliers_explanations": [], "recommendation": {"text":"","expected_impact":""}}
    rep = validate_synthesis(output, findings, employee_names={"Иванов И.", "Петров П."})
    assert not rep.ok and any("Иванов" in e for e in rep.errors)


def test_rounding_within_10_pct_ok():
    findings = {"totals": {"hours": 540}, "themes": [{"pct": 32}]}
    output = {"headline": "около 30%", "themes_narratives": [], "outliers_explanations": [], "recommendation": {"text":"","expected_impact":""}}
    rep = validate_synthesis(output, findings, employee_names=set())
    # 30 ≈ 32 within 10% tolerance → pass
    assert rep.ok
```

- [ ] **Step 2: Implement validator**

Create `app/services/llm/faithfulness_validator.py`:
```python
"""Faithfulness validator — числа и ключи задач из narrative должны быть в findings.

Защита от галлюцинаций LLM на Reduce-фазе.
"""
import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class FaithfulnessReport:
    ok: bool
    errors: list[str] = field(default_factory=list)


_NUM = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_KEY = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")


def _collect_numbers(findings: dict) -> set[float]:
    nums: set[float] = set()
    def walk(o):
        if isinstance(o, dict):
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif isinstance(o, (int, float)):
            nums.add(float(o))
    walk(findings)
    return nums


def _collect_keys(findings: dict) -> set[str]:
    keys: set[str] = set()
    def walk(o):
        if isinstance(o, str):
            for m in _KEY.findall(o): keys.add(m)
        elif isinstance(o, dict):
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(findings)
    return keys


def _extract_text(output: dict) -> str:
    parts: list[str] = []
    if h := output.get("headline"):
        parts.append(h)
    for tn in output.get("themes_narratives", []) or []:
        if t := tn.get("narrative"):
            parts.append(t)
    for oe in output.get("outliers_explanations", []) or []:
        if t := oe.get("explanation"):
            parts.append(t)
    rec = output.get("recommendation") or {}
    parts.append(rec.get("text", "") or "")
    parts.append(rec.get("expected_impact", "") or "")
    return "\n".join(parts)


def validate_synthesis(output: dict, findings: dict, employee_names: Iterable[str]) -> FaithfulnessReport:
    text = _extract_text(output)
    errors: list[str] = []
    known_nums = _collect_numbers(findings)
    known_keys = _collect_keys(findings)

    for n_str in _NUM.findall(text):
        n = float(n_str.replace(",", "."))
        # rounding tolerance ±10%
        if not any(abs(n - kn) <= max(0.5, 0.10 * max(abs(n), abs(kn))) for kn in known_nums):
            errors.append(f"Unknown number {n_str} not in findings")

    for k in _KEY.findall(text):
        if k not in known_keys:
            errors.append(f"Unknown issue key {k} not in findings")

    for name in employee_names:
        if not name: continue
        # Check by surname + first initial pattern
        surname = name.split()[0]
        if len(surname) > 3 and surname in text:
            errors.append(f"Employee name '{surname}' present in narrative (forbidden)")

    return FaithfulnessReport(ok=not errors, errors=errors)
```

- [ ] **Step 3: Run validator tests**

```bash
py -3.10 -m pytest tests/test_faithfulness_validator.py -v
```

- [ ] **Step 4: Synthesizer tests**

`tests/test_work_type_synthesizer.py` — covers:
1. Happy path: provider returns valid JSON → output produced.
2. Faithfulness fails twice → fallback narrative used.
3. Empty findings → minimal output (no themes, just headline).

- [ ] **Step 5: Implement synthesizer**

Create `app/services/llm/work_type_synthesizer.py`:
```python
"""Reduce-фаза тематического отчёта: синтез из агрегированных findings.

LLM не видит сырых описаний/комментов — только агрегаты.
"""
from dataclasses import dataclass
from typing import Optional, Protocol
import json
import logging

from app.services.llm.faithfulness_validator import validate_synthesis

logger = logging.getLogger("jira_analytics.thematic")
PROMPT_VERSION = "wt-synthesize-v1"


@dataclass
class SynthesisOutput:
    headline: str
    themes_narratives: list[dict]
    outliers_explanations: list[dict]
    recommendation: dict
    is_fallback: bool = False


class SynthesizerProvider(Protocol):
    model: str
    async def synthesize_work_type_report(self, prompt: str) -> tuple[dict, dict]: ...


def build_synthesis_prompt(findings: dict) -> str:
    """findings = {totals, themes:[{id,name,hours,pct,top_tasks:[{key,summary,hours,contribution}], by_employee, by_team}], outliers:[{key,reason,value,context}]}."""
    return "\n".join([
        "Ты — старший аналитик. Пишешь executive-сводку для PM.",
        "Используй ТОЛЬКО числа и ключи задач из FINDINGS. Не выдумывай.",
        "Никаких сравнений конкретных людей. Никаких ФИО.",
        "Стиль: короткий, фактический. Без воды.",
        "",
        "FINDINGS:",
        json.dumps(findings, ensure_ascii=False, indent=2),
        "",
        "Верни JSON со схемой:",
        "{",
        '  "headline": str (≤180 chars),',
        '  "themes_narratives": [{theme_id, narrative (≤2 предложения), evidence_keys: [...]}],',
        '  "outliers_explanations": [{key, explanation (1 предложение)}],',
        '  "recommendation": {text (1 действие), expected_impact (оценка эффекта)}',
        "}",
    ])


def _fallback_output(findings: dict) -> SynthesisOutput:
    totals = findings.get("totals", {})
    return SynthesisOutput(
        headline=f"AI-сводка недоступна. Всего {totals.get('hours', 0)} ч / {totals.get('tasks', 0)} задач.",
        themes_narratives=[],
        outliers_explanations=[],
        recommendation={"text": "Просмотрите данные ниже.", "expected_impact": ""},
        is_fallback=True,
    )


class WorkTypeSynthesizer:
    def __init__(self, provider: SynthesizerProvider) -> None:
        self.provider = provider

    async def synthesize(self, findings: dict, *, employee_names: set[str]) -> tuple[SynthesisOutput, dict]:
        prompt = build_synthesis_prompt(findings)
        for attempt in range(2):  # one retry
            try:
                obj, meta = await self.provider.synthesize_work_type_report(prompt)
            except Exception as e:
                logger.warning("Synthesizer call failed: %s", e)
                return _fallback_output(findings), {"failure": str(e)[:200]}
            rep = validate_synthesis(obj, findings, employee_names)
            if rep.ok:
                return SynthesisOutput(
                    headline=obj.get("headline", ""),
                    themes_narratives=obj.get("themes_narratives", []) or [],
                    outliers_explanations=obj.get("outliers_explanations", []) or [],
                    recommendation=obj.get("recommendation", {"text":"","expected_impact":""}),
                ), meta
            logger.warning("Faithfulness failed (attempt %d): %s", attempt + 1, rep.errors[:3])
            prompt += f"\n\nPREVIOUS_FAILED_VALIDATION: {rep.errors[:3]}"
        return _fallback_output(findings), {"validation_errors": rep.errors[:5]}
```

- [ ] **Step 6: Run synthesizer tests**

```bash
py -3.10 -m pytest tests/test_work_type_synthesizer.py -v
```

- [ ] **Step 7: Add `synthesize_work_type_report` to providers**

Mirror Task 5 pattern: add method to `OpenRouterProvider` and `GeminiProvider` that POSTs the prompt and returns `(parsed_dict, meta)`. Use the same `_call_json` helper from Task 5.

- [ ] **Step 8: Commit**

```bash
git add app/services/llm/faithfulness_validator.py app/services/llm/work_type_synthesizer.py app/services/llm/openrouter.py app/services/llm/gemini.py tests/test_faithfulness_validator.py tests/test_work_type_synthesizer.py
git commit -m "feat(thematic): Reduce-phase synthesizer + faithfulness validator + provider methods"
```

---

## Phase 3 — Orchestrator + Snapshot + API

### Task 8: WorkTypeReportService — orchestrator

**Files:**
- Create: `app/services/work_type_report_service.py`
- Test: `tests/test_work_type_report_service.py`

- [ ] **Step 1: Tests covering build / cached-fetch / freshness**

`tests/test_work_type_report_service.py` covers:
1. `build()` with empty dictionary — all classifications go to candidates; snapshot saved.
2. `get_or_build()` returns cached snapshot if dictionary version unchanged.
3. `get_or_build()` invalidates when dictionary version bumped.
4. Multi-team filtering — `team_set_hash` differs → separate snapshots.
5. Failed classifications appear in `manual_review_required` block.

Use fake `ClassifierProvider` and `SynthesizerProvider` to avoid real LLM calls.

- [ ] **Step 2: Implement service skeleton**

```python
"""WorkTypeReportService — оркестратор: Map → aggregate → Reduce → snapshot."""
import hashlib, json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.models.issue import Issue
from app.models.issue_classification import IssueClassification
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
from app.models.worklog import Worklog
from app.models.employee import Employee
from app.models.category import Category
from app.services.theme_dictionary_service import ThemeDictionaryService
from app.services.work_type_outlier_detector import detect_outliers_for_theme
from app.services.llm.work_type_classifier import (
    WorkTypeClassifier, ClassifierProvider, collect_worklog_comments,
)
from app.services.llm.work_type_synthesizer import (
    WorkTypeSynthesizer, SynthesizerProvider, SynthesisOutput,
)


def _team_set_hash(teams: list[str]) -> str:
    """md5 of sorted team list. Empty list → 'all'."""
    if not teams:
        return "all"
    return hashlib.md5("|".join(sorted(teams)).encode("utf-8")).hexdigest()[:32]


def _resolve_period(year: int, quarter: int, month: Optional[int]) -> tuple[date, date]:
    if month:
        from calendar import monthrange
        end_d = monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, end_d)
    q_start = (quarter - 1) * 3 + 1
    from calendar import monthrange
    end_m = q_start + 2
    return date(year, q_start, 1), date(year, end_m, monthrange(year, end_m)[1])


class WorkTypeReportService:
    def __init__(self, db: Session,
                 classifier_provider: Optional[ClassifierProvider] = None,
                 synthesizer_provider: Optional[SynthesizerProvider] = None) -> None:
        self.db = db
        self.classifier_provider = classifier_provider
        self.synthesizer_provider = synthesizer_provider

    async def get_or_build(
        self, *, work_type_id: str, year: int, quarter: int, month: Optional[int],
        teams: list[str], force_refresh: bool, user_id: Optional[str],
    ) -> WorkTypeReportSnapshot:
        wt = self.db.get(MandatoryWorkType, work_type_id)
        if not wt:
            raise ValueError(f"Work type {work_type_id} not found")
        team_hash = _team_set_hash(teams)
        existing = self._find_existing(work_type_id, year, quarter, month, team_hash)
        if existing and not force_refresh and self._is_fresh(existing, wt):
            return existing
        return await self._build(work_type_id=work_type_id, wt=wt,
                                 year=year, quarter=quarter, month=month,
                                 teams=teams, team_hash=team_hash, user_id=user_id,
                                 existing=existing)

    def _find_existing(self, work_type_id, year, quarter, month, team_hash):
        return self.db.execute(
            select(WorkTypeReportSnapshot).where(
                WorkTypeReportSnapshot.work_type_id == work_type_id,
                WorkTypeReportSnapshot.year == year,
                WorkTypeReportSnapshot.quarter == quarter,
                WorkTypeReportSnapshot.month == month,
                WorkTypeReportSnapshot.team_set_hash == team_hash,
            )
        ).scalar_one_or_none()

    def _is_fresh(self, snap: WorkTypeReportSnapshot, wt: MandatoryWorkType) -> bool:
        # 1. Dictionary version stable?
        if snap.dictionary_version != wt.theme_dict_version:
            return False
        # 2. Any issue/worklog changed since snapshot?
        # Use Issue.updated_at and Worklog.updated_at filtered by snapshot period.
        # Conservative: if max(updated_at) > snap.generated_at → stale.
        max_issue = self.db.execute(
            select(func.max(Issue.updated_at)).where(
                Issue.updated_at >= snap.generated_at,
            )
        ).scalar()
        return max_issue is None or max_issue <= snap.generated_at

    async def _build(self, *, work_type_id, wt, year, quarter, month,
                     teams, team_hash, user_id, existing) -> WorkTypeReportSnapshot:
        start_d, end_d = _resolve_period(year, quarter, month)
        # 1. Find all issues in scope: Categories with work_type_id == this WT,
        #    issues having those categories, with worklogs in period & team in filter.
        issues = self._select_scope_issues(work_type_id, start_d, end_d, teams)
        themes = ThemeDictionaryService(self.db).list_active(work_type_id)

        # 2. Map phase
        classifier = WorkTypeClassifier(self.db, self.classifier_provider) if self.classifier_provider else None
        classifications: dict[str, IssueClassification] = {}
        if classifier:
            for issue in issues:
                cls = await classifier.classify_issue(
                    issue=issue, work_type_id=work_type_id, themes=themes,
                    period_start=start_d, period_end=end_d,
                )
                classifications[issue.id] = cls

        # 3. Aggregate findings (deterministic)
        findings, manual_review = self._aggregate_findings(
            issues, classifications, themes, start_d, end_d, teams)

        # 4. Reduce phase
        synth_meta = {}
        synthesis: SynthesisOutput
        if self.synthesizer_provider and findings.get("themes"):
            synth = WorkTypeSynthesizer(self.synthesizer_provider)
            employee_names = {e for e in findings.get("_employee_names", set())}
            synthesis, synth_meta = await synth.synthesize(findings, employee_names=employee_names)
        else:
            synthesis = SynthesisOutput(
                headline=f"Всего {findings['totals']['hours']} ч / {findings['totals']['tasks']} задач.",
                themes_narratives=[], outliers_explanations=[],
                recommendation={"text":"","expected_impact":""}, is_fallback=True,
            )

        # 5. Build snapshot data
        data = self._build_snapshot_data(findings, synthesis, manual_review)

        # 6. Persist
        snap = existing or WorkTypeReportSnapshot(
            work_type_id=work_type_id, year=year, quarter=quarter, month=month,
            start_date=start_d, end_date=end_d,
            team_set_hash=team_hash, team_set_json=json.dumps(teams, ensure_ascii=False),
            snapshot_data="", dictionary_version=wt.theme_dict_version,
        )
        snap.snapshot_data = json.dumps(data, ensure_ascii=False)
        snap.dictionary_version = wt.theme_dict_version
        snap.team_set_json = json.dumps(teams, ensure_ascii=False)
        snap.start_date, snap.end_date = start_d, end_d
        snap.model_id = synth_meta.get("model")
        snap.prompt_version = "wt-synthesize-v1"
        snap.generated_at = datetime.utcnow()
        snap.created_by = user_id
        if not existing:
            self.db.add(snap)
        self.db.commit(); self.db.refresh(snap)
        return snap

    def _select_scope_issues(self, work_type_id, start_d, end_d, teams) -> list[Issue]:
        # Categories belonging to this work type
        cat_ids = self.db.execute(
            select(Category.id).where(Category.work_type_id == work_type_id)
        ).scalars().all()
        # Issues which: have a worklog in period; and are in those categories;
        # and (no team filter) or (Issue.team in teams)
        q = (
            select(Issue).distinct()
            .join(Worklog, Worklog.issue_id == Issue.id)
            .where(
                Worklog.started_at >= start_d, Worklog.started_at <= end_d,
                Issue.assigned_category.in_([self.db.get(Category, cid).code for cid in cat_ids]) if cat_ids else False,
            )
        )
        if teams:
            q = q.where(Issue.team.in_(teams))
        return list(self.db.execute(q).scalars().all())

    def _aggregate_findings(self, issues, classifications, themes, start_d, end_d, teams) -> tuple[dict, list]:
        """Deterministic aggregation: hours per theme, top tasks, employees, outliers."""
        # ... (full implementation: group worklogs by issue, compute hours per (issue,employee,team),
        # group classifications by theme_id (or candidate_name for "Other"), compute totals,
        # build theme.top_tasks (sorted by hours desc, top 5), call detect_outliers_for_theme.
        # Return findings dict + list of issues that failed classification (manual_review).
        # See spec for findings JSON shape.
        raise NotImplementedError("Implement aggregation per spec section 'Reduce phase'")

    def _build_snapshot_data(self, findings, synthesis: SynthesisOutput, manual_review) -> dict:
        """Combine findings + synthesis text into snapshot data per spec."""
        return {
            "headline": synthesis.headline,
            "totals": findings["totals"],
            "themes": [
                {**t, "narrative": next((n["narrative"] for n in synthesis.themes_narratives if n.get("theme_id") == t.get("theme_id")), "")}
                for t in findings["themes"]
            ],
            "candidates": findings.get("candidates", []),
            "outliers": [
                {**o, "explanation": next((e["explanation"] for e in synthesis.outliers_explanations if e.get("key") == o["key"]), "")}
                for o in findings.get("outliers", [])
            ],
            "recommendation": synthesis.recommendation,
            "manual_review_required": manual_review,
            "is_fallback_narrative": synthesis.is_fallback,
        }
```

This task contains an explicit `NotImplementedError` for `_aggregate_findings`. The implementing subagent must **fully implement** it per the spec's findings JSON shape — that's part of this task. Reference `app/services/analytics_service.py` for similar aggregation patterns in this codebase.

- [ ] **Step 3: Run tests**

```bash
py -3.10 -m pytest tests/test_work_type_report_service.py -v
```

- [ ] **Step 4: Commit**

```bash
git add app/services/work_type_report_service.py tests/test_work_type_report_service.py
git commit -m "feat(thematic): orchestrator service (Map → aggregate → Reduce → snapshot)"
```

---

### Task 9: Report API endpoints + schemas

**Files:**
- Modify: `app/schemas/work_type_report.py` (add report-level schemas)
- Create: `app/api/endpoints/work_type_report.py`
- Modify: `app/api/router.py`
- Test: `tests/test_work_type_report_endpoints.py`

- [ ] **Step 1: Add report schemas**

Append to `app/schemas/work_type_report.py`:
```python
# ---- Report ----

class WorkTypeReportRequest(BaseModel):
    work_type_id: str
    year: int = Field(..., ge=2020, le=2100)
    quarter: int = Field(..., ge=1, le=4)
    month: Optional[int] = Field(None, ge=1, le=12)
    teams: list[str] = []
    force_refresh: bool = False


class WorkTypeReportResponse(BaseModel):
    snapshot_id: str
    work_type_id: str
    year: int; quarter: int; month: Optional[int]
    start_date: date; end_date: date
    team_set: list[str]
    generated_at: datetime
    model_id: Optional[str]
    prompt_version: Optional[str]
    dictionary_version: int
    is_stale: bool
    data: dict[str, Any]


class CandidateAcceptRequest(BaseModel):
    snapshot_id: str
    proposed_name: str
    new_theme_name: Optional[str] = None
    color: str = "#00c9c8"


class CandidateMergeRequest(BaseModel):
    snapshot_id: str
    proposed_name: str
    target_theme_id: str


class CandidateIgnoreRequest(BaseModel):
    snapshot_id: str
    proposed_name: str


class ManualClassifyRequest(BaseModel):
    issue_id: str
    work_type_id: str
    theme_id: Optional[str]   # null = mark as ignored (stays in "Other")
    contribution_text: Optional[str] = None


# ---- Layouts ----

class LayoutBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    grouping_dims: list[Literal["theme", "team", "role", "employee", "project", "issue"]]
    visible_columns: Optional[list[str]] = None
    is_default: bool = False


class LayoutCreateRequest(LayoutBase):
    work_type_id: str


class LayoutOut(LayoutBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    work_type_id: str
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 2: Endpoint tests**

`tests/test_work_type_report_endpoints.py` covers:
- `POST /work-type-report` builds & returns snapshot.
- `GET /work-type-report?...` returns cached if not stale.
- `POST /work-type-report/candidates/accept` creates theme + reclassifies.
- `POST /work-type-report/manual-classify` updates classification.
- `GET /work-type-report/layouts?work_type_id=...` returns user's layouts.
- `POST /work-type-report/layouts` creates a layout.

- [ ] **Step 3: Implement endpoints**

Create `app/api/endpoints/work_type_report.py` with routes:
- `POST /` → `WorkTypeReportService.get_or_build(force_refresh=True)` → `WorkTypeReportResponse`
- `GET /` (query params for the same key) → `get_or_build(force_refresh=False)`
- `POST /candidates/accept` → call `ThemeDictionaryService.create_theme(...)` and reassign matching `IssueClassification.candidate_name` → bump dict version. Trigger background re-build.
- `POST /candidates/merge` → reassign `IssueClassification.theme_id` for matching `candidate_name` → set `candidate_name=None`.
- `POST /candidates/ignore` → no-op (just informational).
- `POST /manual-classify` → set theme_id on a single classification (mark `failed=False`, `llm_confidence=1.0`, `prompt_version="manual"`).
- `GET /layouts?work_type_id=...` → list user's layouts.
- `POST /layouts` → create layout (enforce single is_default per user×work_type).
- `PATCH /layouts/{id}`, `DELETE /layouts/{id}`.

Use `Depends(get_current_user)` everywhere.

- [ ] **Step 4: Wire router**

Edit `app/api/router.py`:
```python
from app.api.endpoints import work_type_report as wtr_endpoints
api_router.include_router(wtr_endpoints.router, prefix="/work-type-report", tags=["work-type-report"])
```

- [ ] **Step 5: Run endpoint tests**

```bash
py -3.10 -m pytest tests/test_work_type_report_endpoints.py -v
```

- [ ] **Step 6: Commit**

```bash
git add app/schemas/work_type_report.py app/api/endpoints/work_type_report.py app/api/router.py tests/test_work_type_report_endpoints.py
git commit -m "feat(thematic): report endpoints (build/get/candidates/manual-classify/layouts)"
```

---

### Task 10: XLSX export

**Files:**
- Create: `app/services/work_type_report_xlsx.py`
- Modify: `app/api/endpoints/work_type_report.py` (+ `/export/xlsx`)
- Test: `tests/test_work_type_report_xlsx.py`

- [ ] **Step 1: Test**

Test produces 3-sheet workbook (Темы / Задачи / Текст) from a fixture snapshot. Asserts column headers, row count, and that AI text appears on Текст sheet.

- [ ] **Step 2: Implement** (use `openpyxl`, mirror `app/services/scenario_xlsx_export.py` style — read it first).

```python
"""XLSX export — Темы / Задачи / Текст."""
from io import BytesIO
import json
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

from app.models.work_type_report_snapshot import WorkTypeReportSnapshot


def export_snapshot_to_xlsx(snap: WorkTypeReportSnapshot) -> bytes:
    data = json.loads(snap.snapshot_data)
    wb = Workbook()
    # Sheet 1: Темы
    ws1 = wb.active; ws1.title = "Темы"
    ws1.append(["Тема", "Часов", "Доля, %", "Задач", "Сотрудников"])
    for t in data.get("themes", []):
        tot = t.get("totals", {})
        ws1.append([t.get("name"), tot.get("hours", 0), tot.get("pct", 0),
                    tot.get("tasks_count", 0), tot.get("employees_count", 0)])

    # Sheet 2: Задачи
    ws2 = wb.create_sheet("Задачи")
    ws2.append(["Тема", "Ключ", "Заголовок", "Сотрудник", "Роль", "Команда", "Часы", "Что делали"])
    for t in data.get("themes", []):
        for i in t.get("issues", []):
            for emp_row in i.get("employee_breakdown", [{"name": "", "role": "", "team": "", "hours": i.get("hours", 0)}]):
                ws2.append([t.get("name"), i.get("key"), i.get("summary"),
                            emp_row.get("name"), emp_row.get("role"), emp_row.get("team"),
                            emp_row.get("hours"), i.get("contribution")])

    # Sheet 3: Текст
    ws3 = wb.create_sheet("Текст")
    ws3.append(["AI-заголовок"])
    ws3.append([data.get("headline", "")])
    ws3.append([])
    ws3.append(["Нарративы по темам"])
    for t in data.get("themes", []):
        ws3.append([t.get("name"), t.get("narrative", "")])
    ws3.append([])
    rec = data.get("recommendation", {})
    ws3.append(["Рекомендация", rec.get("text", "")])
    ws3.append(["Ожидаемый эффект", rec.get("expected_impact", "")])

    buf = BytesIO(); wb.save(buf); return buf.getvalue()
```

- [ ] **Step 3: Endpoint** — add to `work_type_report.py`:
```python
from fastapi.responses import Response
from app.services.work_type_report_xlsx import export_snapshot_to_xlsx

@router.get("/export/xlsx/{snapshot_id}")
def export_xlsx(snapshot_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    snap = db.get(WorkTypeReportSnapshot, snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    blob = export_snapshot_to_xlsx(snap)
    fname = f"thematic-{snap.year}q{snap.quarter}{f'-m{snap.month}' if snap.month else ''}-{snap.work_type_id[:8]}.xlsx"
    return Response(content=blob,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
```

- [ ] **Step 4: Tests + commit**

```bash
py -3.10 -m pytest tests/test_work_type_report_xlsx.py -v
git add app/services/work_type_report_xlsx.py app/api/endpoints/work_type_report.py tests/test_work_type_report_xlsx.py
git commit -m "feat(thematic): xlsx export (3 sheets: Темы / Задачи / Текст)"
```

---

## Phase 4 — Frontend

### Task 11: TS types, API clients, hooks

**Files:**
- Create: `frontend/src/types/workTypeReport.ts`
- Create: `frontend/src/api/themes.ts`
- Create: `frontend/src/api/workTypeReport.ts`
- Create: `frontend/src/hooks/useThemeDictionary.ts`
- Create: `frontend/src/hooks/useWorkTypeReport.ts`
- Create: `frontend/src/hooks/useWorkTypeReportLayouts.ts`

- [ ] **Step 1: TS types**

`frontend/src/types/workTypeReport.ts` — mirror Pydantic `WorkTypeReportResponse`, `ThemeOut`, `LayoutOut`, plus snapshot data shape (`Theme`, `ThemeWithIssues`, `Outlier`, `Recommendation`, `Candidate`, `ManualReviewIssue`).

- [ ] **Step 2: API clients**

Mirror `frontend/src/api/issues.ts` style. Use existing `apiClient` (axios with auth interceptor).

- [ ] **Step 3: TanStack Query hooks**

Mirror `useProjectSummary.ts` pattern. Hooks:
- `useThemeList(workTypeId, includeArchived)`
- `useCreateTheme()`, `useUpdateTheme()`, `useArchiveTheme()`, `useRestoreTheme()`, `useMergeThemes()`
- `useWorkTypeReport(params, { enabled })` — GET (cached)
- `useBuildWorkTypeReport()` — POST (force refresh)
- `useAcceptCandidate()`, `useMergeCandidate()`, `useIgnoreCandidate()`, `useManualClassify()`
- `useLayoutList(workTypeId)`, `useCreateLayout()`, `useUpdateLayout()`, `useDeleteLayout()`

Invalidation rules:
- Theme mutations → invalidate `theme-list`, `work-type-report`.
- Candidate mutations → invalidate `theme-list`, `work-type-report`.
- Layout mutations → invalidate `layout-list`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/workTypeReport.ts frontend/src/api/themes.ts frontend/src/api/workTypeReport.ts frontend/src/hooks/useThemeDictionary.ts frontend/src/hooks/useWorkTypeReport.ts frontend/src/hooks/useWorkTypeReportLayouts.ts
git commit -m "feat(thematic-fe): types + api clients + tanstack hooks"
```

---

### Task 12: Page shell + Toolbar + AI headline + KPI row

**Files:**
- Create: `frontend/src/pages/WorkTypeReportPage.tsx`
- Create: `frontend/src/components/work-type-report/Toolbar.tsx`
- Create: `frontend/src/components/work-type-report/AiHeadline.tsx`
- Create: `frontend/src/components/work-type-report/KpiRow.tsx`
- Create: `frontend/src/components/work-type-report/EmptyState.tsx`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/Layout/AppSidebar.tsx`

- [ ] **Step 1: Add route** `/analytics/work-type-report` in `router.tsx`.

- [ ] **Step 2: Sidebar nav link** under "Аналитика" group.

- [ ] **Step 3: Page shell** — container, fetches `useThemeList` + `useWorkTypeReport`, branches:
- if `themes.length === 0 && !report` → render `<EmptyState />`
- else → render `<Toolbar />`, `<AiHeadline />`, `<KpiRow />`, then placeholders for next tasks' components.

- [ ] **Step 4: Toolbar** — work-type radio (from `useMandatoryWorkTypes`), team multi-select (overlay over `useGlobalTeamFilter`), period picker (overlay over `useGlobalPeriod`), snapshot freshness pill, buttons: `↻ Пересчитать`, `⤓ XLSX`, `⤓ PDF для руководства`.

- [ ] **Step 5: AiHeadline** — gradient card with cyan left border, 1-line headline + meta row (model id, data scale, prompt version, confidence pill).

- [ ] **Step 6: KpiRow** — 4 cards (часы / тем / задач / сотрудников). MVP: no sparkline (placeholder div).

- [ ] **Step 7: EmptyState** — full-screen invitation, "Построить первый отчёт" button calling `useBuildWorkTypeReport`.

- [ ] **Step 8: E2E smoke** — navigate to page, see `EmptyState` for fresh DB, click button, see report.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/WorkTypeReportPage.tsx frontend/src/components/work-type-report/ frontend/src/router.tsx frontend/src/components/Layout/AppSidebar.tsx
git commit -m "feat(thematic-fe): page shell + toolbar + headline + KPI + empty state"
```

---

### Task 13: Theme distribution + Hierarchy table + Grouping control

**Files:**
- Create: `frontend/src/components/work-type-report/ThemeDistribution.tsx`
- Create: `frontend/src/components/work-type-report/HierarchyTable.tsx`
- Create: `frontend/src/components/work-type-report/GroupingControl.tsx`
- Create: `frontend/src/components/work-type-report/ThemeNarrativeRow.tsx`

- [ ] **Step 1: ThemeDistribution** — donut (use existing chart lib — repo uses Recharts; check existing `dashboard/` components first) + horizontal bars list. Top 5 + "Другое" rollup. Click on theme → scroll/highlight in HierarchyTable.

- [ ] **Step 2: GroupingControl** — preset chips ("По темам", "По сотрудникам", "По командам", "По ролям", "По проектам") + "★ saved" chips from `useLayoutList`. Below: pivot chip-row with drag-and-drop reorder (use `@dnd-kit/core` if available, else simple click-to-cycle). "★ Сохранить как..." button opens AntD `Modal` with name input.

- [ ] **Step 3: HierarchyTable** — tree built from snapshot data based on `groupingDims`. Use AntD `Table` with `expandable` + `defaultExpandedRowKeys`. Each level computes its rows by grouping the flat issue list. Theme rows: cyan color, bold; under each — `<ThemeNarrativeRow />` with italic AI text + clickable issue keys (`PROJ-XXX` → opens `IssueDrillDownDrawer`). New themes: yellow `★ новая` tag. Low-confidence themes: yellow `low confidence` tag.

- [ ] **Step 4: ThemeNarrativeRow** — full-width row spanning all columns, `background: rgba(0,201,200,0.03)`, italic, key-substring detection regex highlights `PROJ-XXX` as clickable.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/work-type-report/ThemeDistribution.tsx frontend/src/components/work-type-report/HierarchyTable.tsx frontend/src/components/work-type-report/GroupingControl.tsx frontend/src/components/work-type-report/ThemeNarrativeRow.tsx
git commit -m "feat(thematic-fe): theme distribution + hierarchy tree + grouping pivot"
```

---

### Task 14: Outliers + Recommendation + Drill-down + Manual review

**Files:**
- Create: `frontend/src/components/work-type-report/OutliersPanel.tsx`
- Create: `frontend/src/components/work-type-report/RecommendationCard.tsx`
- Create: `frontend/src/components/work-type-report/IssueDrillDownDrawer.tsx`
- Create: `frontend/src/components/work-type-report/ManualReviewBlock.tsx`

- [ ] **Step 1: OutliersPanel** — list of cards: key, summary, reason badge with red text, meta line. Click → `IssueDrillDownDrawer`.

- [ ] **Step 2: RecommendationCard** — yellow outlined card, action text + expected impact.

- [ ] **Step 3: IssueDrillDownDrawer** — AntD `Drawer` (right side, width 600). Sections:
- Header: key + status + "Open in Jira" link.
- Goal / Behavior / Description (collapsible if long).
- Worklog comments list.
- Classification: theme name, confidence, contribution_text. If failed → manual classify dropdown calling `useManualClassify`.

- [ ] **Step 4: ManualReviewBlock** — collapsible section at bottom of HierarchyTable. Lists tasks with `failed=true`. Each row: key, summary, hours, [Theme dropdown to assign] [Retry button].

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/work-type-report/OutliersPanel.tsx frontend/src/components/work-type-report/RecommendationCard.tsx frontend/src/components/work-type-report/IssueDrillDownDrawer.tsx frontend/src/components/work-type-report/ManualReviewBlock.tsx
git commit -m "feat(thematic-fe): outliers + recommendation + drill-down drawer + manual review"
```

---

### Task 15: Candidates panel + Theme dictionary drawer

**Files:**
- Create: `frontend/src/components/work-type-report/CandidatesPanel.tsx`
- Create: `frontend/src/components/work-type-report/ThemeDictionaryDrawer.tsx`

- [ ] **Step 1: CandidatesPanel** — right-column block: header "★ N кандидатов", list of cards (proposed name, hours, count, sample keys). Click "Просмотреть" → opens `ThemeDictionaryDrawer` on Candidates tab.

- [ ] **Step 2: ThemeDictionaryDrawer** — AntD `Drawer` (right, width 720). 3 tabs:
- *Активные*: AntD `Table` with edit-in-place (or open mini-modal): name, description, color picker, sort_order. Actions: archive, merge (opens "Слить в..." dropdown).
- *Архивные*: same table, "Восстановить" button.
- *Кандидаты*: list of all candidates. Per candidate: [Принять] (opens dialog: editable name, color), [Слить с] (theme dropdown), [Игнорировать]. Confirmation modal on accept/merge.

- [ ] **Step 3: Mutations rebuild report** — after any candidate action, invalidate `work-type-report` query → triggers rebuild.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/work-type-report/CandidatesPanel.tsx frontend/src/components/work-type-report/ThemeDictionaryDrawer.tsx
git commit -m "feat(thematic-fe): candidates panel + theme dictionary drawer (3 tabs)"
```

---

### Task 16: PDF print view + cross-navigation from Dashboard

**Files:**
- Create: `frontend/src/components/work-type-report/PrintView.tsx`
- Modify: `frontend/src/pages/WorkTypeReportPage.tsx` (route `/print` variant)
- Modify: `frontend/src/pages/DashboardPage.tsx` (click on work-type row → deep-link)

- [ ] **Step 1: PrintView** — separate component, fetches snapshot, renders simplified executive layout: AI-headline (large), donut + bars, top-3 themes with narratives, top-5 outliers, recommendation. Light theme. Print CSS: `@media print { body { background: white; color: black; } ... }`. Mirror `frontend/src/pages/projects/ProjectPrintView.tsx` if exists.

- [ ] **Step 2: Route** — add `/analytics/work-type-report/print?...` to router. PDF button in Toolbar opens this in new tab → user runs Ctrl+P.

- [ ] **Step 3: Dashboard cross-nav** — find work-type row in dashboard widget; on click navigate to `/analytics/work-type-report?work_type_id=...&teams=...&year=...&quarter=...&month=...` (parse current global filters into URL).

- [ ] **Step 4: Existing analytics cross-nav** — in `frontend/src/components/analytics/AnalyticsTable.tsx`, add a small `→` button on each work-type group header that navigates to the thematic report.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/work-type-report/PrintView.tsx frontend/src/pages/WorkTypeReportPage.tsx frontend/src/pages/DashboardPage.tsx frontend/src/router.tsx frontend/src/components/analytics/AnalyticsTable.tsx
git commit -m "feat(thematic-fe): PDF print view + cross-nav from dashboard and analytics"
```

---

### Task 17: E2E smoke + polish

**Files:**
- Create: `frontend/e2e/work-type-report.spec.ts`

- [ ] **Step 1: E2E test**

Smoke covering:
1. Login → navigate to `/analytics/work-type-report`.
2. Empty state visible (uses seeded test DB without themes).
3. Click "Построить первый отчёт" → wait for completion → see KPI row populated.
4. Open dictionary drawer → see candidates → accept one.
5. Verify report rebuilds, accepted theme appears in list.
6. Click PDF button → new tab opens with print view.

Use Playwright. Mirror `frontend/e2e/crud-flows.spec.ts` style. Ensure `scripts/seed_e2e.py` seeds at least 5 issues with `Сопровождение` category and worklogs in a known period.

- [ ] **Step 2: Run E2E**

```bash
.\scripts\e2e-local.ps1
```
Expected: pass.

- [ ] **Step 3: Lint + typecheck**

```bash
cd frontend && pnpm lint && pnpm tsc --noEmit
ruff check app/ tests/
mypy app/
```
Fix any errors.

- [ ] **Step 4: Final commit**

```bash
git add frontend/e2e/work-type-report.spec.ts
git commit -m "test(thematic): E2E smoke for empty-state → first build → candidate accept → PDF"
```

---

## Self-Review Checklist (run before dispatching subagents)

- [ ] All MVP (★) features from spec are covered by at least one task above.
- [ ] No "TBD"/"TODO" in tasks (one explicit `NotImplementedError` in Task 8 is intentional and called out).
- [ ] File paths exist or are unambiguously creatable.
- [ ] Method signatures consistent across tasks (e.g. `WorkTypeClassifier.classify_issue(...)` matches between Task 4 + Task 8).
- [ ] Test commands use `py -3.10` per CLAUDE.md.
- [ ] Migration uses `op.batch_alter_table` for SQLite compatibility.
- [ ] No raw SQL — all SQLAlchemy ORM.
- [ ] Frontend matches AntD 6.3 conventions (`title` for notifications, not `message`).
- [ ] Each task ends with a commit step.
- [ ] Faithfulness validator wired into synthesizer with retry-then-fallback.

## Out-of-Scope for This Plan (◇ second iteration / · future)

Per spec — do not build:
- Sparkline trends in KPI/themes (needs ≥2 snapshots; defer until natural data accumulation).
- "vs предыдущий период" comparison block.
- `nature_tag` (systemic/one_off/...) propagation through UI.
- Cross-thematic correlation hints in narrative.
- Cost-in-rubles column.
- Stacked area chart of theme history.
- Per-theme PM notes.
- Local LLM model option in settings.
- SLA per-theme, burn-rate prognosis, heatmap, reporter breakdown, "Create Jira improvement task" button, scheduled snapshots, multi-work-type comparison.

Each is explicitly marked in the spec's "Вторая итерация" / "На будущее" sections.
