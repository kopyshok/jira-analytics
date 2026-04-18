# Capacity Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the Capacity feature: dated worklog reload, recalc-able active employee set, Jira-user add-flow, Russian production calendar, and historical fact (plan/fact/% plus per-category breakdown).

**Architecture:** Backend additions follow the existing Connector → Service → Endpoint pattern with one new connector (xmlcalendar.ru), one new service (`ProductionCalendarService`), one new model (`production_calendar_day`), and targeted extensions to `SyncService`, `CapacityService`, and `JiraClient`. Frontend additions extend `SyncPage`, `CapacityPage`, and `SettingsPage` with new tabs/columns/modals; state stays in TanStack Query.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic, httpx, React 19, TypeScript, Ant Design 6, TanStack Query. Tests: pytest (backend), Playwright (E2E).

**Reference spec:** [docs/superpowers/specs/2026-04-18-capacity-overhaul-design.md](../specs/2026-04-18-capacity-overhaul-design.md)

---

## Phase 1 — Worklog reload by `started_at`

### Task 1.1: `SyncService.reload_worklogs_since` — skeleton + delete path

**Files:**
- Modify: `app/services/sync_service.py` (add method; `_upsert_worklog` is at ~line 702)
- Create: `tests/test_sync_service_reload.py`

- [ ] **Step 1: Write failing test for delete path**

Create `tests/test_sync_service_reload.py`:

```python
"""Тесты точечной перезагрузки worklog'ов по дате starts."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService, ReloadStats


@pytest.fixture
def sample_data(db_session):
    project = Project(id="p1", jira_project_id="100", key="PRJ", name="PRJ")
    employee = Employee(
        id="e1", jira_account_id="a1", display_name="Иванов",
        email="ivanov@example.com", is_active=True,
    )
    issue = Issue(
        id="i1", jira_issue_id="1001", key="PRJ-1", summary="x",
        project_id=project.id, issuetype="Task", status="В работе",
    )
    db_session.add_all([project, employee, issue])
    db_session.flush()

    old = Worklog(
        id="w_old", jira_worklog_id="10",
        issue_id=issue.id, employee_id=employee.id,
        started_at=datetime(2025, 12, 15, 10, 0),
        hours=4.0, time_spent_seconds=14400,
    )
    new = Worklog(
        id="w_new", jira_worklog_id="20",
        issue_id=issue.id, employee_id=employee.id,
        started_at=datetime(2026, 1, 5, 10, 0),
        hours=3.0, time_spent_seconds=10800,
    )
    db_session.add_all([old, new])
    db_session.commit()
    return {"project": project, "employee": employee, "issue": issue,
            "old": old, "new": new}


def test_reload_deletes_only_rows_at_or_after_since(db_session, sample_data):
    jira = MagicMock()
    jira.iter_issues = AsyncMock(return_value=iter([]))  # no new data
    service = SyncService(db_session, jira_client=jira)

    stats = service.reload_worklogs_since(date(2026, 1, 1))

    assert isinstance(stats, ReloadStats)
    assert stats.deleted == 1
    remaining_ids = {w.jira_worklog_id for w in db_session.query(Worklog).all()}
    assert remaining_ids == {"10"}
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
py -3.10 -m pytest tests/test_sync_service_reload.py::test_reload_deletes_only_rows_at_or_after_since -v
```
Expected: FAIL with `ImportError: cannot import name 'ReloadStats' from 'app.services.sync_service'` or similar (method doesn't exist).

- [ ] **Step 3: Implement minimal delete path**

Add near the top of `app/services/sync_service.py` (after existing imports / dataclasses):

```python
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class ReloadStats:
    """Результат жёсткой перезагрузки worklog'ов по periods."""

    deleted: int = 0
    issues_scanned: int = 0
    worklogs_inserted: int = 0
```

Add a method on `SyncService` (paste inside the class, at the end):

```python
    def reload_worklogs_since(self, since: date) -> ReloadStats:
        """Удаляет worklog'и с ``started_at >= since`` и перечитывает их
        из Jira, бьющийся по JQL ``worklogDate >= since``.

        Идемпотентно; не трогает ``sync_state.last_sync``.
        """
        since_dt = datetime.combine(since, datetime.min.time())
        deleted = (
            self.db.query(Worklog)
            .filter(Worklog.started_at >= since_dt)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return ReloadStats(deleted=deleted)
```

- [ ] **Step 4: Run test — verify PASS**

```bash
py -3.10 -m pytest tests/test_sync_service_reload.py::test_reload_deletes_only_rows_at_or_after_since -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_service.py tests/test_sync_service_reload.py
git commit -m "Add SyncService.reload_worklogs_since delete path"
```

---

### Task 1.2: `reload_worklogs_since` — re-pull from Jira

**Files:**
- Modify: `app/services/sync_service.py` — flesh out reload method
- Modify: `tests/test_sync_service_reload.py`

- [ ] **Step 1: Write failing test for re-pull path**

Append to `tests/test_sync_service_reload.py`:

```python
def test_reload_repulls_and_inserts_new_rows(db_session, sample_data):
    """Удалили пост-since → перечитали issue'ы из JQL → вставили новые worklog'и."""
    from datetime import timezone

    jira_issue_payload = MagicMock()
    jira_issue_payload.id = "1001"
    jira_issue_payload.key = "PRJ-1"

    worklog_payload = MagicMock()
    worklog_payload.id = "30"
    worklog_payload.started = datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc)
    worklog_payload.time_spent_seconds = 7200
    worklog_payload.author.account_id = "a1"
    worklog_payload.author.display_name = "Иванов"
    worklog_payload.author.email_address = "ivanov@example.com"
    worklog_payload.author.active = True
    worklog_payload.comment = "fix"

    async def iter_issues_mock(jql, **_):
        assert "worklogDate" in jql
        yield jira_issue_payload

    async def iter_worklogs_mock(_):
        yield worklog_payload

    jira = MagicMock()
    jira.iter_issues = iter_issues_mock
    jira.iter_worklogs_for_issue = iter_worklogs_mock

    service = SyncService(db_session, jira_client=jira)
    stats = service.reload_worklogs_since(date(2026, 1, 1))

    assert stats.issues_scanned == 1
    assert stats.worklogs_inserted == 1
    keys = {w.jira_worklog_id for w in db_session.query(Worklog).all()}
    assert keys == {"10", "30"}  # old kept, new inserted


def test_reload_skips_unknown_issues(db_session, sample_data):
    """Если Jira вернула issue, которой нет в локальной БД — пропускаем."""
    jira_issue_payload = MagicMock()
    jira_issue_payload.id = "9999"  # not in DB
    jira_issue_payload.key = "UNK-1"

    async def iter_issues_mock(jql, **_):
        yield jira_issue_payload

    async def iter_worklogs_mock(_):
        raise AssertionError("should not be called for unknown issue")
        yield  # pragma: no cover

    jira = MagicMock()
    jira.iter_issues = iter_issues_mock
    jira.iter_worklogs_for_issue = iter_worklogs_mock

    service = SyncService(db_session, jira_client=jira)
    stats = service.reload_worklogs_since(date(2026, 1, 1))

    assert stats.issues_scanned == 0  # unknown not counted
    assert stats.worklogs_inserted == 0
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
py -3.10 -m pytest tests/test_sync_service_reload.py -v
```
Expected: the delete test passes; the two new tests FAIL (method doesn't iterate / insert).

- [ ] **Step 3: Implement re-pull path**

Replace the `reload_worklogs_since` method body in `app/services/sync_service.py`:

```python
    def reload_worklogs_since(self, since: date) -> ReloadStats:
        """Удаляет worklog'и с ``started_at >= since`` и перечитывает их
        из Jira по JQL ``worklogDate >= since``.

        Перебирает только те issue, что уже есть в локальной БД: незнакомые
        пропускаются, чтобы не расширять scope молча.
        """
        import asyncio

        since_dt = datetime.combine(since, datetime.min.time())
        deleted = (
            self.db.query(Worklog)
            .filter(Worklog.started_at >= since_dt)
            .delete(synchronize_session=False)
        )
        self.db.commit()

        stats = ReloadStats(deleted=deleted)
        jql = f'worklogDate >= "{since.isoformat()}"'

        async def run() -> None:
            async for jira_issue in self.jira_client.iter_issues(
                jql,
                fields=["summary", "issuetype", "status", "project"],
                batch_size=100,
            ):
                local = (
                    self.db.query(Issue)
                    .filter(Issue.jira_issue_id == jira_issue.id)
                    .one_or_none()
                )
                if local is None:
                    continue
                stats.issues_scanned += 1
                async for wl in self.jira_client.iter_worklogs_for_issue(
                    jira_issue.id
                ):
                    started = self._to_naive_utc(wl.started)
                    if started < since_dt:
                        continue
                    author = wl.author
                    emp, _ = self._upsert_employee_from_worklog_author(author)
                    _, inserted = self._upsert_worklog(local, emp, wl)
                    if inserted:
                        stats.worklogs_inserted += 1
                self.db.commit()

        asyncio.run(run())
        return stats
```

If `_upsert_employee_from_worklog_author` and `_to_naive_utc` don't exist under those exact names, use whatever helper the existing worklog sync uses (check `sync_service.py` around line 762 for the worklog author upsert pattern and reuse the same call). If the existing code creates the employee inline, extract the block into a helper with the same name as above first, then call it from both places.

If `_upsert_worklog` doesn't return `(obj, inserted)` — check its existing signature and adapt. Fall back to "if row didn't exist before upsert, count it".

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_sync_service_reload.py -v
```
Expected: all three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_service.py tests/test_sync_service_reload.py
git commit -m "SyncService.reload_worklogs_since re-pulls from Jira with worklogDate JQL"
```

---

### Task 1.3: `POST /sync/worklogs/reload` endpoint + AppSetting

**Files:**
- Modify: `app/api/endpoints/sync.py`
- Create: `tests/test_sync_reload_endpoint.py`

- [ ] **Step 1: Write failing endpoint test**

Create `tests/test_sync_reload_endpoint.py`:

```python
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import AppSetting


def test_post_reload_persists_since_and_returns_stats(db_session):
    client = TestClient(app)

    with patch(
        "app.services.sync_service.SyncService.reload_worklogs_since",
        return_value=__import__(
            "app.services.sync_service", fromlist=["ReloadStats"]
        ).ReloadStats(deleted=5, issues_scanned=3, worklogs_inserted=7),
    ):
        resp = client.post(
            "/api/v1/sync/worklogs/reload", json={"since": "2026-01-01"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"deleted": 5, "issues_scanned": 3, "worklogs_inserted": 7}

    setting = (
        db_session.query(AppSetting)
        .filter(AppSetting.key == "worklog_reload_since_date")
        .one_or_none()
    )
    assert setting is not None
    assert setting.value == "2026-01-01"


def test_post_reload_rejects_invalid_date(db_session):
    client = TestClient(app)
    resp = client.post(
        "/api/v1/sync/worklogs/reload", json={"since": "not-a-date"}
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
py -3.10 -m pytest tests/test_sync_reload_endpoint.py -v
```
Expected: 404 on first test (endpoint missing), 422 already works for bad date only if route exists.

- [ ] **Step 3: Add endpoint + schema**

Add to `app/api/endpoints/sync.py` (near existing schema block):

```python
from datetime import date

class WorklogReloadRequest(BaseModel):
    since: date


class WorklogReloadResponse(BaseModel):
    deleted: int
    issues_scanned: int
    worklogs_inserted: int
```

Add endpoint handler (near other sync routes):

```python
@router.post("/worklogs/reload", response_model=WorklogReloadResponse)
async def reload_worklogs(
    req: WorklogReloadRequest,
    db: Session = Depends(get_db),
):
    """Жёсткая перезагрузка worklog'ов с указанной даты по ``started_at``.

    Удаляет все записи, у которых ``started_at >= since`` и перечитывает их
    из Jira через JQL ``worklogDate >= since``. Сохраняет дату в AppSetting
    ``worklog_reload_since_date``.
    """
    from app.api.endpoints.settings import _set_setting  # reuse helper
    from app.services.sync_service import SyncService
    from app.connectors.jira_client import build_jira_client_from_db

    async with build_jira_client_from_db(db) as jira:
        service = SyncService(db, jira_client=jira)
        stats = service.reload_worklogs_since(req.since)

    _set_setting(db, "worklog_reload_since_date", req.since.isoformat())
    db.commit()
    return WorklogReloadResponse(
        deleted=stats.deleted,
        issues_scanned=stats.issues_scanned,
        worklogs_inserted=stats.worklogs_inserted,
    )
```

If `build_jira_client_from_db` doesn't exist, use the same Jira client construction pattern as the nearby `POST /sync` handler (probably `JiraClient(...)` with credentials loaded via `_get_setting`).

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_sync_reload_endpoint.py -v
```
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/sync.py tests/test_sync_reload_endpoint.py
git commit -m "POST /sync/worklogs/reload with AppSetting persistence"
```

---

### Task 1.4: Frontend — reload control on Sync page

**Files:**
- Modify: `frontend/src/api/sync.ts`
- Modify: `frontend/src/hooks/useSync.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/SyncPage.tsx`

- [ ] **Step 1: Add API method + types**

Append to `frontend/src/types/api.ts`:

```typescript
export interface WorklogReloadRequest {
  since: string;   // YYYY-MM-DD
}

export interface WorklogReloadResponse {
  deleted: number;
  issues_scanned: number;
  worklogs_inserted: number;
}
```

Append to `frontend/src/api/sync.ts`:

```typescript
import type { WorklogReloadRequest, WorklogReloadResponse } from '../types/api';

export const reloadWorklogs = (req: WorklogReloadRequest) =>
  api.post<WorklogReloadResponse>('/sync/worklogs/reload', req);
```

- [ ] **Step 2: Add hook**

Append to `frontend/src/hooks/useSync.ts`:

```typescript
import { reloadWorklogs } from '../api/sync';
import type { WorklogReloadRequest, WorklogReloadResponse } from '../types/api';

export const useReloadWorklogs = () => {
  const qc = useQueryClient();
  return useMutation<WorklogReloadResponse, Error, WorklogReloadRequest>({
    mutationFn: reloadWorklogs,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};
```

- [ ] **Step 3: Add UI control on Sync page**

In `frontend/src/pages/SyncPage.tsx`, locate the `SyncControls` function (it holds the incremental / full sync buttons). Add a new block right after the existing controls:

```tsx
import { DatePicker } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useReloadWorklogs } from '../hooks/useSync';

// …inside SyncControls()…
const reloadSince = useGenericSetting('worklog_reload_since_date');
const saveReloadSince = useSaveGenericSetting();
const reload = useReloadWorklogs();

const initialSince: Dayjs = reloadSince.data?.value
  ? dayjs(reloadSince.data.value)
  : dayjs('2026-01-01');
const [sinceDate, setSinceDate] = useState<Dayjs>(initialSince);

useEffect(() => {
  if (reloadSince.data?.value) setSinceDate(dayjs(reloadSince.data.value));
}, [reloadSince.data?.value]);

const handleReload = () => {
  const iso = sinceDate.format('YYYY-MM-DD');
  reload.mutate({ since: iso }, {
    onSuccess: (stats) => {
      notification.success({
        message: 'Worklog\'и перезагружены',
        description: `Удалено: ${stats.deleted}, issues: ${stats.issues_scanned}, вставлено: ${stats.worklogs_inserted}`,
      });
      saveReloadSince.mutate({ key: 'worklog_reload_since_date', value: iso });
    },
    onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
  });
};
```

Render (wrap existing sync buttons row, add below):

```tsx
<Space wrap>
  <DatePicker
    value={sinceDate}
    onChange={(d) => d && setSinceDate(d)}
    format="DD.MM.YYYY"
  />
  <Popconfirm
    title={`Удалить все worklog'и с ${sinceDate.format('DD.MM.YYYY')} и перечитать?`}
    onConfirm={handleReload}
  >
    <Button loading={reload.isPending} icon={<ReloadOutlined />}>
      Перезагрузить worklog'и с даты
    </Button>
  </Popconfirm>
</Space>
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: build passes, no TS errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sync.ts frontend/src/hooks/useSync.ts frontend/src/types/api.ts frontend/src/pages/SyncPage.tsx
git commit -m "Dated worklog reload control on Sync page"
git push origin main
```

---

## Phase 2 — Employee `recalc-active` + Team filter

### Task 2.1: `EmployeeService.recalc_active_by_categories`

**Files:**
- Create: `app/services/employee_service.py`
- Create: `tests/test_employee_service.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_employee_service.py`:

```python
"""Тесты EmployeeService.recalc_active_by_categories."""

from datetime import datetime

import pytest

from app.models import Category, Employee, Issue, Project, Worklog
from app.services.employee_service import EmployeeService, RecalcStats


@pytest.fixture
def seed_categories(db_session):
    cats = [
        Category(id="c1", code="active_1", name="Active1", is_builtin=False),
        Category(id="c2", code="archive", name="Archive", is_builtin=True),
        Category(id="c3", code="archive_target", name="Archive target", is_builtin=True),
        Category(id="c4", code="initiatives_rfa", name="Initiatives", is_builtin=True),
    ]
    db_session.add_all(cats)
    db_session.commit()
    return cats


@pytest.fixture
def make_fixture(db_session, seed_categories):
    def _mk(employee_code: str, issue_category: str | None) -> tuple[Employee, Issue]:
        proj = Project(id=f"p_{employee_code}", jira_project_id=f"10{employee_code}",
                       key=f"P{employee_code}", name="P")
        emp = Employee(
            id=f"e_{employee_code}", jira_account_id=f"a_{employee_code}",
            display_name=f"Name {employee_code}", is_active=False,
        )
        issue = Issue(
            id=f"i_{employee_code}", jira_issue_id=f"200{employee_code}",
            key=f"K-{employee_code}", summary="x",
            project_id=proj.id, issuetype="Task", status="В работе",
            assigned_category=issue_category,
        )
        db_session.add_all([proj, emp, issue])
        db_session.flush()
        wl = Worklog(
            id=f"w_{employee_code}", jira_worklog_id=f"30{employee_code}",
            issue_id=issue.id, employee_id=emp.id,
            started_at=datetime(2026, 2, 1, 10, 0),
            hours=1.0, time_spent_seconds=3600,
        )
        db_session.add(wl)
        db_session.commit()
        return emp, issue
    return _mk


def test_active_when_logged_on_active_stack(db_session, make_fixture):
    emp, _ = make_fixture("A", "active_1")
    service = EmployeeService(db_session)
    stats = service.recalc_active_by_categories()
    assert isinstance(stats, RecalcStats)
    db_session.refresh(emp)
    assert emp.is_active is True


def test_active_when_logged_on_archive_target(db_session, make_fixture):
    emp, _ = make_fixture("B", "archive_target")
    EmployeeService(db_session).recalc_active_by_categories()
    db_session.refresh(emp)
    assert emp.is_active is True


def test_inactive_when_only_archive(db_session, make_fixture):
    emp, _ = make_fixture("C", "archive")
    EmployeeService(db_session).recalc_active_by_categories()
    db_session.refresh(emp)
    assert emp.is_active is False


def test_inactive_when_only_initiatives_rfa(db_session, make_fixture):
    emp, _ = make_fixture("D", "initiatives_rfa")
    EmployeeService(db_session).recalc_active_by_categories()
    db_session.refresh(emp)
    assert emp.is_active is False


def test_inactive_when_no_worklogs(db_session, seed_categories):
    emp = Employee(
        id="e_noop", jira_account_id="a_noop", display_name="Noop", is_active=True,
    )
    db_session.add(emp)
    db_session.commit()
    EmployeeService(db_session).recalc_active_by_categories()
    db_session.refresh(emp)
    assert emp.is_active is False


def test_idempotent(db_session, make_fixture):
    emp, _ = make_fixture("E", "active_1")
    svc = EmployeeService(db_session)
    a = svc.recalc_active_by_categories()
    b = svc.recalc_active_by_categories()
    assert a.total_active == b.total_active == 1
    assert b.activated == 0 and b.deactivated == 0
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
py -3.10 -m pytest tests/test_employee_service.py -v
```
Expected: `ImportError: cannot import name 'EmployeeService'`.

- [ ] **Step 3: Implement service**

Create `app/services/employee_service.py`:

```python
"""Сервис операций над таблицей employees.

Сейчас содержит только пересчёт ``is_active`` на основе categorisation активных
задач. Набор сотрудников, имеющих worklog'и на задачи с категориями
«Активный стек» и «Архив квартальных задач», становится активным; все остальные
помечаются неактивными.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Category, Employee, Issue, Worklog


# Коды категорий, исключаемые из «активного» набора.
EXCLUDED_CODES: set[str] = {"archive", "initiatives_rfa"}


@dataclass
class RecalcStats:
    """Сводка пересчёта активных сотрудников."""

    activated: int
    deactivated: int
    total_active: int


class EmployeeService:
    """Сервис операций над employees."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _target_category_codes(self) -> set[str]:
        """Коды, относящиеся к «Активный стек» ∪ «Архив квартальных задач».

        Совпадают с определением матчера вкладок на фронте: всё, что не
        ``archive`` и не ``initiatives_rfa``.
        """
        all_codes = {c.code for c in self.db.query(Category).all()}
        return all_codes - EXCLUDED_CODES

    def recalc_active_by_categories(self) -> RecalcStats:
        target = self._target_category_codes()

        active_ids = {
            row[0]
            for row in self.db.query(Worklog.employee_id)
            .join(Issue, Worklog.issue_id == Issue.id)
            .filter(Issue.assigned_category.in_(target))
            .distinct()
            .all()
        }

        before = {
            e.id: e.is_active for e in self.db.query(Employee).all()
        }

        activated = 0
        deactivated = 0
        for emp_id, was_active in before.items():
            target_state = emp_id in active_ids
            if target_state == was_active:
                continue
            self.db.query(Employee).filter(Employee.id == emp_id).update(
                {"is_active": target_state},
                synchronize_session=False,
            )
            if target_state:
                activated += 1
            else:
                deactivated += 1

        self.db.commit()
        return RecalcStats(
            activated=activated,
            deactivated=deactivated,
            total_active=len(active_ids),
        )
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_employee_service.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/employee_service.py tests/test_employee_service.py
git commit -m "EmployeeService.recalc_active_by_categories"
```

---

### Task 2.2: `POST /employees/recalc-active` endpoint

**Files:**
- Modify: `app/api/endpoints/employees.py`
- Create: `tests/test_employees_recalc_endpoint.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_employees_recalc_endpoint.py`:

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import Category


def test_post_recalc_active_returns_stats(db_session):
    db_session.add_all([
        Category(id="c1", code="active_1", name="Active1", is_builtin=False),
        Category(id="c2", code="archive", name="Archive", is_builtin=True),
    ])
    db_session.commit()

    client = TestClient(app)
    resp = client.post("/api/v1/employees/recalc-active")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"activated", "deactivated", "total_active"}
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
py -3.10 -m pytest tests/test_employees_recalc_endpoint.py -v
```
Expected: 404 (route not defined).

- [ ] **Step 3: Add endpoint**

In `app/api/endpoints/employees.py`, add schema + route:

```python
class RecalcActiveResponse(BaseModel):
    activated: int
    deactivated: int
    total_active: int


@router.post("/recalc-active", response_model=RecalcActiveResponse)
def recalc_active(db: Session = Depends(get_db)):
    """Пересчитать is_active для всех сотрудников на основе worklog'ов
    на задачи с категориями «Активный стек» ∪ «Архив квартальных задач»."""
    from app.services.employee_service import EmployeeService

    stats = EmployeeService(db).recalc_active_by_categories()
    return RecalcActiveResponse(
        activated=stats.activated,
        deactivated=stats.deactivated,
        total_active=stats.total_active,
    )
```

- [ ] **Step 4: Run test — verify PASS**

```bash
py -3.10 -m pytest tests/test_employees_recalc_endpoint.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/employees.py tests/test_employees_recalc_endpoint.py
git commit -m "POST /employees/recalc-active endpoint"
```

---

### Task 2.3: Frontend — "Пересчитать состав" button + filter on Team tab

**Files:**
- Modify: `frontend/src/api/employees.ts`
- Modify: `frontend/src/hooks/useCapacity.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 1: Add API + types**

Append to `frontend/src/types/api.ts`:

```typescript
export interface RecalcActiveResponse {
  activated: number;
  deactivated: number;
  total_active: number;
}
```

Append to `frontend/src/api/employees.ts`:

```typescript
import type { RecalcActiveResponse } from '../types/api';

export const recalcActiveEmployees = () =>
  api.post<RecalcActiveResponse>('/employees/recalc-active', {});
```

- [ ] **Step 2: Add hook**

Append to `frontend/src/hooks/useCapacity.ts`:

```typescript
import { recalcActiveEmployees } from '../api/employees';
import type { RecalcActiveResponse } from '../types/api';

export const useRecalcActiveEmployees = () => {
  const qc = useQueryClient();
  return useMutation<RecalcActiveResponse, Error, void>({
    mutationFn: recalcActiveEmployees,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};
```

- [ ] **Step 3: Add employee-filter + recalc button to Team tab**

In `frontend/src/pages/CapacityPage.tsx`, replace the `TeamTab` function with:

```tsx
function TeamTab() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useTeamCapacity(year, quarter);
  const { data: employees } = useEmployees();
  const recalc = useRecalcActiveEmployees();

  const stored = useGenericSetting('ui_capacity_team_filter');
  const saveStored = useSaveGenericSetting();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated || stored.data === undefined) return;
    const val = stored.data?.value;
    if (val) setSelectedIds(val.split(',').filter(Boolean));
    setHydrated(true);
  }, [hydrated, stored.data]);

  const handleFilterChange = (val: string[]) => {
    setSelectedIds(val);
    saveStored.mutate({ key: 'ui_capacity_team_filter', value: val.join(',') });
  };

  const months = QUARTER_MONTHS[Number(quarter)] || [];
  const visibleData = selectedIds.length === 0
    ? data
    : data?.filter(r => selectedIds.includes(r.employee_id));

  const columns = [
    { title: 'Сотрудник', dataIndex: 'employee_name', fixed: 'left' as const, width: 200 },
    ...months.map((m) => ({
      title: MONTH_NAMES[m],
      key: `m${m}`,
      render: (_: unknown, r: QuarterCapacityResponse) => {
        const mc = r.months.find((x) => x.month === m);
        return mc ? formatHours(mc.available_hours) : '—';
      },
    })),
    { title: 'Итого', dataIndex: 'total_available_hours', render: formatHours },
  ];

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Select
          mode="multiple"
          allowClear
          placeholder="Фильтр по сотруднику"
          style={{ minWidth: 260 }}
          value={selectedIds}
          onChange={handleFilterChange}
          showSearch
          optionFilterProp="label"
          options={(employees ?? [])
            .filter(e => e.is_active)
            .map(e => ({ value: e.id, label: e.display_name }))}
        />
        <Popconfirm
          title="Пересчитать состав по worklog'ам активных задач?"
          onConfirm={() => recalc.mutate(undefined, {
            onSuccess: (s) => notification.success({
              message: 'Состав обновлён',
              description: `Активировано: ${s.activated}, деактивировано: ${s.deactivated}, всего активных: ${s.total_active}`,
            }),
            onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
          })}
        >
          <Button loading={recalc.isPending}>Пересчитать состав</Button>
        </Popconfirm>
      </Space>
      <Table<QuarterCapacityResponse>
        dataSource={visibleData}
        rowKey="employee_id"
        loading={isLoading}
        columns={columns}
        pagination={false}
        size="small"
        scroll={{ x: 800 }}
      />
    </Space>
  );
}
```

Add missing imports at the top:

```tsx
import { useEffect, useState } from 'react';
import { Popconfirm } from 'antd';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useRecalcActiveEmployees } from '../hooks/useCapacity';
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/employees.ts frontend/src/hooks/useCapacity.ts frontend/src/types/api.ts frontend/src/pages/CapacityPage.tsx
git commit -m "Employee filter + Recalc active button on Capacity Team tab"
git push origin main
```

---

## Phase 3 — Jira user search + "Add employee"

### Task 3.1: `JiraClient.search_users`

**Files:**
- Modify: `app/connectors/jira_client.py`
- Create: `tests/test_jira_client_search_users.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_jira_client_search_users.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.connectors.jira_client import JiraClient


@pytest.mark.asyncio
async def test_search_users_parses_response():
    fake_response = [
        {
            "accountId": "a1",
            "displayName": "Иванов",
            "emailAddress": "ivanov@example.com",
            "active": True,
            "avatarUrls": {"48x48": "https://example.com/a.png"},
        },
        {
            "accountId": "a2",
            "displayName": "Петров",
            "emailAddress": None,
            "active": False,
            "avatarUrls": {"48x48": "https://example.com/b.png"},
        },
    ]

    client = JiraClient(
        base_url="https://x.atlassian.net", email="e", api_token="t"
    )
    client._request = AsyncMock(return_value=fake_response)

    users = await client.search_users("ив")
    assert len(users) == 2
    assert users[0].jira_account_id == "a1"
    assert users[0].display_name == "Иванов"
    assert users[0].is_active is True
    assert users[1].email is None
    client._request.assert_awaited_once()
    call_args = client._request.await_args
    assert "/user/search" in call_args.args[1] or call_args.kwargs.get("url", "").endswith("/user/search")
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
py -3.10 -m pytest tests/test_jira_client_search_users.py -v
```
Expected: `AttributeError: 'JiraClient' object has no attribute 'search_users'`.

- [ ] **Step 3: Implement method**

In `app/connectors/jira_client.py`, add alongside the existing `get_users` / `iter_users`:

```python
    async def search_users(
        self, query: str, max_results: int = 20
    ) -> list["JiraUserSchema"]:
        """Поиск пользователей Jira по имени/e-mail.

        Использует ``/rest/api/3/user/search`` (не путать с
        ``/rest/api/3/users/search`` — возвращает ВСЕХ пользователей,
        включая ботов и inactive). Для UI-автокомплита нужен именно query-based.
        """
        params = {"query": query, "maxResults": max_results}
        raw = await self._request("GET", "/rest/api/3/user/search", params=params)
        return [JiraUserSchema.model_validate(item) for item in raw]
```

If existing methods call `_request` with different signature — adapt to match the project's pattern (e.g., `self._get(path, params=...)` or `self._client.get(...)`). Use whatever the neighbouring `get_users` uses.

- [ ] **Step 4: Run test — verify PASS**

```bash
py -3.10 -m pytest tests/test_jira_client_search_users.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/connectors/jira_client.py tests/test_jira_client_search_users.py
git commit -m "JiraClient.search_users (query-based autocomplete)"
```

---

### Task 3.2: `GET /jira/users/search` endpoint

**Files:**
- Modify: `app/api/endpoints/sync.py` (or a new `jira.py` if sync.py is already crowded — choose based on existing structure)
- Create: `tests/test_jira_users_search_endpoint.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_jira_users_search_endpoint.py`:

```python
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.connectors.schemas import JiraUserSchema
from app.main import app


def test_search_rejects_short_query(db_session):
    client = TestClient(app)
    resp = client.get("/api/v1/jira/users/search", params={"query": "a"})
    assert resp.status_code == 422


def test_search_returns_users(db_session):
    fake = [
        JiraUserSchema(
            jira_account_id="a1",
            display_name="Иванов",
            email="i@example.com",
            is_active=True,
            avatar_url=None,
        )
    ]
    with patch(
        "app.connectors.jira_client.JiraClient.search_users",
        new=AsyncMock(return_value=fake),
    ), patch(
        "app.api.endpoints.sync.build_jira_client_from_db",
        return_value=AsyncMock(),
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/jira/users/search", params={"query": "ив"})

    assert resp.status_code == 200
    assert resp.json() == [
        {"jira_account_id": "a1", "display_name": "Иванов",
         "email": "i@example.com", "is_active": True, "avatar_url": None}
    ]
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
py -3.10 -m pytest tests/test_jira_users_search_endpoint.py -v
```
Expected: 404 on both.

- [ ] **Step 3: Add endpoint**

In `app/api/endpoints/sync.py` (near existing `/jira-*` prefixes), add:

```python
class JiraUserResponse(BaseModel):
    jira_account_id: str
    display_name: str
    email: str | None
    is_active: bool
    avatar_url: str | None


@router.get("/jira/users/search", response_model=list[JiraUserResponse])
async def search_jira_users(
    query: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
):
    """Поиск пользователей Jira по подстроке (минимум 2 символа).

    Возвращает до 20 совпадений без записи в БД.
    """
    async with build_jira_client_from_db(db) as jira:
        users = await jira.search_users(query, max_results=20)
    return [
        JiraUserResponse(
            jira_account_id=u.jira_account_id,
            display_name=u.display_name,
            email=u.email,
            is_active=u.is_active,
            avatar_url=u.avatar_url,
        )
        for u in users
    ]
```

If the project's router for `/jira-*` paths lives elsewhere (check neighbouring `/sync/jira-projects`) — put this endpoint in the same file.

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_jira_users_search_endpoint.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/sync.py tests/test_jira_users_search_endpoint.py
git commit -m "GET /jira/users/search endpoint"
```

---

### Task 3.3: `POST /employees/from-jira` endpoint

**Files:**
- Modify: `app/api/endpoints/employees.py`
- Create: `tests/test_employees_from_jira_endpoint.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_employees_from_jira_endpoint.py`:

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import Employee


def test_from_jira_creates_employee(db_session):
    client = TestClient(app)
    resp = client.post(
        "/api/v1/employees/from-jira",
        json={
            "jira_account_id": "a_new",
            "display_name": "Новый",
            "email": "new@example.com",
            "is_active": True,
            "avatar_url": "https://example.com/new.png",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["jira_account_id"] == "a_new"
    assert body["is_active"] is True
    assert db_session.query(Employee).filter_by(jira_account_id="a_new").count() == 1


def test_from_jira_reactivates_existing(db_session):
    existing = Employee(
        id="e1", jira_account_id="a_old", display_name="Old",
        email="o@example.com", is_active=False,
    )
    db_session.add(existing)
    db_session.commit()

    client = TestClient(app)
    resp = client.post(
        "/api/v1/employees/from-jira",
        json={
            "jira_account_id": "a_old",
            "display_name": "Old Renamed",
            "email": "o@example.com",
            "is_active": True,
            "avatar_url": None,
        },
    )
    assert resp.status_code == 200
    db_session.refresh(existing)
    assert existing.is_active is True
    assert existing.display_name == "Old Renamed"
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
py -3.10 -m pytest tests/test_employees_from_jira_endpoint.py -v
```
Expected: 404 on both.

- [ ] **Step 3: Add endpoint**

In `app/api/endpoints/employees.py`, add request schema + route:

```python
from datetime import datetime
import uuid

class EmployeeFromJiraRequest(BaseModel):
    jira_account_id: str
    display_name: str
    email: str | None = None
    is_active: bool = True
    avatar_url: str | None = None


@router.post("/from-jira", response_model=EmployeeResponse)
def employee_from_jira(
    req: EmployeeFromJiraRequest,
    db: Session = Depends(get_db),
):
    """Явное добавление сотрудника из Jira (автокомплит на фронте)."""
    from app.models import Employee

    existing = (
        db.query(Employee)
        .filter(Employee.jira_account_id == req.jira_account_id)
        .one_or_none()
    )
    if existing is None:
        existing = Employee(
            id=str(uuid.uuid4()),
            jira_account_id=req.jira_account_id,
            display_name=req.display_name,
            email=req.email,
            avatar_url=req.avatar_url,
            is_active=True,   # явное добавление → активный
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            synced_at=datetime.utcnow(),
        )
        db.add(existing)
    else:
        existing.display_name = req.display_name
        existing.email = req.email
        existing.avatar_url = req.avatar_url
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
        existing.synced_at = datetime.utcnow()

    db.commit()
    db.refresh(existing)
    return EmployeeResponse.model_validate(existing)
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_employees_from_jira_endpoint.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/employees.py tests/test_employees_from_jira_endpoint.py
git commit -m "POST /employees/from-jira with reactivation"
```

---

### Task 3.4: Frontend — "Добавить сотрудника" modal

**Files:**
- Modify: `frontend/src/api/sync.ts` (search)
- Modify: `frontend/src/api/employees.ts` (from-jira)
- Modify: `frontend/src/hooks/useCapacity.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 1: Add API + types**

Append to `frontend/src/types/api.ts`:

```typescript
export interface JiraUserSearchResult {
  jira_account_id: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  avatar_url: string | null;
}

export interface EmployeeFromJiraRequest {
  jira_account_id: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  avatar_url: string | null;
}
```

Append to `frontend/src/api/sync.ts`:

```typescript
import type { JiraUserSearchResult } from '../types/api';

export const searchJiraUsers = (query: string) =>
  api.get<JiraUserSearchResult[]>('/jira/users/search', { query });
```

Append to `frontend/src/api/employees.ts`:

```typescript
import type { EmployeeFromJiraRequest, EmployeeResponse } from '../types/api';

export const addEmployeeFromJira = (req: EmployeeFromJiraRequest) =>
  api.post<EmployeeResponse>('/employees/from-jira', req);
```

- [ ] **Step 2: Add hooks**

Append to `frontend/src/hooks/useCapacity.ts`:

```typescript
import { searchJiraUsers } from '../api/sync';
import { addEmployeeFromJira } from '../api/employees';
import type {
  EmployeeFromJiraRequest, JiraUserSearchResult, EmployeeResponse,
} from '../types/api';

export const useSearchJiraUsers = (query: string) =>
  useQuery({
    queryKey: ['jira', 'users', 'search', query],
    queryFn: () => searchJiraUsers(query),
    enabled: query.length >= 2,
    staleTime: 60_000,
  });

export const useAddEmployeeFromJira = () => {
  const qc = useQueryClient();
  return useMutation<EmployeeResponse, Error, EmployeeFromJiraRequest>({
    mutationFn: addEmployeeFromJira,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};
```

- [ ] **Step 3: Add modal to Team tab**

In `frontend/src/pages/CapacityPage.tsx`, inside `TeamTab()` (or extract as `<AddEmployeeButton />`), add below the filter Select:

```tsx
const [addOpen, setAddOpen] = useState(false);
const [query, setQuery] = useState('');
const [debouncedQuery, setDebouncedQuery] = useState('');
useEffect(() => {
  const t = setTimeout(() => setDebouncedQuery(query), 300);
  return () => clearTimeout(t);
}, [query]);

const searchRes = useSearchJiraUsers(debouncedQuery);
const addMut = useAddEmployeeFromJira();

const handlePick = (user: JiraUserSearchResult) => {
  addMut.mutate({
    jira_account_id: user.jira_account_id,
    display_name: user.display_name,
    email: user.email,
    is_active: true,
    avatar_url: user.avatar_url,
  }, {
    onSuccess: () => {
      notification.success({ message: `Добавлен: ${user.display_name}` });
      setAddOpen(false);
      setQuery('');
    },
    onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
  });
};
```

Render the button alongside filter + recalc:

```tsx
<Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
  Добавить сотрудника
</Button>
<Modal
  title="Добавить сотрудника из Jira"
  open={addOpen}
  onCancel={() => setAddOpen(false)}
  footer={null}
>
  <AutoComplete
    style={{ width: '100%' }}
    value={query}
    onChange={setQuery}
    placeholder="Имя или e-mail (от 2 символов)"
    options={(searchRes.data ?? []).map(u => ({
      value: u.jira_account_id,
      label: `${u.display_name}${u.email ? ` · ${u.email}` : ''}`,
      user: u,
    }))}
    onSelect={(_, opt) => handlePick((opt as { user: JiraUserSearchResult }).user)}
  />
  {searchRes.isFetching && <Text type="secondary">Ищу…</Text>}
</Modal>
```

Add imports: `AutoComplete`, `Modal`, `Typography.Text`, `useSearchJiraUsers`, `useAddEmployeeFromJira`, `PlusOutlined`, `JiraUserSearchResult`.

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ frontend/src/hooks/useCapacity.ts frontend/src/types/api.ts frontend/src/pages/CapacityPage.tsx
git commit -m "Add employee from Jira (autocomplete modal)"
git push origin main
```

---

## Phase 4 — Production calendar (RU)

### Task 4.1: `ProductionCalendarDay` model + migration

**Files:**
- Create: `app/models/production_calendar_day.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/016_production_calendar.py`

- [ ] **Step 1: Create model**

Create `app/models/production_calendar_day.py`:

```python
"""Модель особых дней российского производственного календаря.

Хранит только аномалии: праздники, перенесённые рабочие дни и сокращённые дни.
Обычные будни (weekday < 5) и обычные выходные без правок в таблицу не
кладутся — для них сервис возвращает дефолт.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, String

from app.models.base import Base


class ProductionCalendarDay(Base):
    __tablename__ = "production_calendar_day"

    date = Column(Date, primary_key=True)
    is_workday = Column(Boolean, nullable=False)
    kind = Column(String(32), nullable=False)
    note = Column(String(255), nullable=True)
    source = Column(String(16), nullable=False, default="xmlcalendar")
    synced_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
```

- [ ] **Step 2: Register model**

In `app/models/__init__.py`, add:

```python
from app.models.production_calendar_day import ProductionCalendarDay  # noqa: F401

__all__ = [..., "ProductionCalendarDay"]  # append
```

- [ ] **Step 3: Create migration**

Create `alembic/versions/016_production_calendar.py`:

```python
"""Production calendar — особые дни РФ.

Revision ID: 016_production_calendar
Revises: 015_main_box_container_rule
Create Date: 2026-04-18
"""

import sqlalchemy as sa
from alembic import op


revision = "016_production_calendar"
down_revision = "015_main_box_container_rule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_calendar_day",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("is_workday", sa.Boolean(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("production_calendar_day")
```

Verify the `down_revision` matches the real prior migration filename — `ls alembic/versions/` and use the `revision = "..."` string from the latest file, not the filename.

- [ ] **Step 4: Apply migration**

```bash
alembic upgrade head
```
Expected: creates `production_calendar_day` table.

- [ ] **Step 5: Commit**

```bash
git add app/models/production_calendar_day.py app/models/__init__.py alembic/versions/016_production_calendar.py
git commit -m "Add production_calendar_day model + migration 016"
```

---

### Task 4.2: `ProductionCalendarClient` (xmlcalendar.ru)

**Files:**
- Create: `app/connectors/production_calendar_client.py`
- Create: `tests/test_production_calendar_client.py`
- Create: `tests/fixtures/xmlcalendar_2026.json` (recorded response)

- [ ] **Step 1: Record a fixture**

Create `tests/fixtures/xmlcalendar_2026.json` with a minimal representative payload. The real schema at `https://xmlcalendar.ru/data/ru/2026/calendar.json` is:

```json
{
  "years": [{
    "year": 2026,
    "months": [
      {"month": 1, "days": "1*,2*,3+,4+,5,6,7,8,9*,10+,11+"},
      {"month": 2, "days": "21+,22+,23+"}
    ],
    "transitions": []
  }]
}
```

Suffix semantics (from xmlcalendar docs):
- `*` — non-working holiday
- `+` — weekend
- no suffix — plain workday (not usually included)

A simpler normalised representation may be available; in that case adapt the parser below.

Paste the above content into `tests/fixtures/xmlcalendar_2026.json` verbatim.

- [ ] **Step 2: Write failing test**

Create `tests/test_production_calendar_client.py`:

```python
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.connectors.production_calendar_client import (
    CalendarDayRaw, ProductionCalendarClient,
)


@pytest.mark.asyncio
async def test_fetch_year_parses_fixture():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/xmlcalendar_2026.json").read_text(
            encoding="utf-8"
        )
    )
    with patch(
        "app.connectors.production_calendar_client.httpx.AsyncClient.get",
        new=AsyncMock(return_value=type("R", (), {
            "json": lambda self: fixture,
            "raise_for_status": lambda self: None,
        })()),
    ):
        client = ProductionCalendarClient()
        days = await client.fetch_year(2026)

    assert all(isinstance(d, CalendarDayRaw) for d in days)
    jan = [d for d in days if d.date.month == 1]
    assert any(d.date.day == 1 and d.is_workday is False and d.kind == "holiday" for d in jan)
    assert any(d.date.day == 3 and d.is_workday is False and d.kind == "weekend" for d in jan)
```

- [ ] **Step 3: Run test — verify FAIL**

```bash
py -3.10 -m pytest tests/test_production_calendar_client.py -v
```
Expected: `ImportError` (module missing).

- [ ] **Step 4: Implement client**

Create `app/connectors/production_calendar_client.py`:

```python
"""Клиент производственного календаря РФ (xmlcalendar.ru).

Тянет JSON по году, парсит маркеры дней в плоский список ``CalendarDayRaw``.
Возвращаются только «особые» дни — обычные будни в результат не попадают.
"""

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import httpx


XMLCALENDAR_URL = "https://xmlcalendar.ru/data/ru/{year}/calendar.json"


@dataclass
class CalendarDayRaw:
    """Один особый день, возвращённый источником."""

    date: date
    is_workday: bool
    kind: str           # "holiday" | "weekend" | "preholiday" | "workday_moved"
    note: str | None = None


class ProductionCalendarClient:
    """HTTP-клиент к xmlcalendar.ru."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    async def fetch_year(self, year: int) -> list[CalendarDayRaw]:
        url = XMLCALENDAR_URL.format(year=year)
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            payload = resp.json()
        return list(self._parse(year, payload))

    @staticmethod
    def _parse(year: int, payload: dict) -> Iterable[CalendarDayRaw]:
        years = payload.get("years") or []
        block = next((y for y in years if y.get("year") == year), None)
        if block is None:
            return []
        for month_block in block.get("months", []):
            month = int(month_block["month"])
            for token in str(month_block.get("days", "")).split(","):
                token = token.strip()
                if not token:
                    continue
                if token.endswith("*"):
                    day, kind, is_wd = int(token[:-1]), "holiday", False
                elif token.endswith("+"):
                    day, kind, is_wd = int(token[:-1]), "weekend", False
                elif token.endswith("'"):
                    day, kind, is_wd = int(token[:-1]), "preholiday", True
                else:
                    day, kind, is_wd = int(token), "workday_moved", True
                yield CalendarDayRaw(
                    date=date(year, month, day),
                    is_workday=is_wd,
                    kind=kind,
                )
```

- [ ] **Step 5: Run test — verify PASS**

```bash
py -3.10 -m pytest tests/test_production_calendar_client.py -v
```
Expected: PASS. If the real xmlcalendar format differs from the fixture you recorded, adjust `_parse` — the tests will tell you.

- [ ] **Step 6: Commit**

```bash
git add app/connectors/production_calendar_client.py tests/test_production_calendar_client.py tests/fixtures/xmlcalendar_2026.json
git commit -m "ProductionCalendarClient parsing xmlcalendar.ru JSON"
```

---

### Task 4.3: `ProductionCalendarService`

**Files:**
- Create: `app/services/production_calendar_service.py`
- Create: `tests/test_production_calendar_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_production_calendar_service.py`:

```python
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.connectors.production_calendar_client import CalendarDayRaw
from app.models import ProductionCalendarDay
from app.services.production_calendar_service import ProductionCalendarService


def test_is_workday_falls_back_to_weekday(db_session):
    svc = ProductionCalendarService(db_session)
    assert svc.is_workday(date(2026, 6, 15)) is True    # Monday
    assert svc.is_workday(date(2026, 6, 20)) is False   # Saturday


def test_is_workday_uses_db_when_present(db_session):
    db_session.add(ProductionCalendarDay(
        date=date(2026, 1, 1), is_workday=False, kind="holiday",
        note="НГ", source="xmlcalendar",
    ))
    db_session.commit()
    svc = ProductionCalendarService(db_session)
    assert svc.is_workday(date(2026, 1, 1)) is False    # Thursday but holiday


def test_workdays_in_range_map_accounts_for_holidays(db_session):
    db_session.add(ProductionCalendarDay(
        date=date(2026, 1, 1), is_workday=False, kind="holiday",
        note="НГ", source="xmlcalendar",
    ))
    db_session.commit()
    svc = ProductionCalendarService(db_session)
    m = svc.workdays_in_range_map(date(2026, 1, 1), date(2026, 1, 2))
    assert m[date(2026, 1, 1)] is False


@pytest.mark.asyncio
async def test_sync_year_skips_manual_rows(db_session):
    db_session.add(ProductionCalendarDay(
        date=date(2026, 5, 9), is_workday=True, kind="manual_note",
        note="user edit", source="manual",
    ))
    db_session.commit()

    fake_days = [
        CalendarDayRaw(date=date(2026, 5, 9), is_workday=False, kind="holiday"),
        CalendarDayRaw(date=date(2026, 1, 1), is_workday=False, kind="holiday"),
    ]
    with patch(
        "app.connectors.production_calendar_client.ProductionCalendarClient.fetch_year",
        new=AsyncMock(return_value=fake_days),
    ):
        svc = ProductionCalendarService(db_session)
        stats = await svc.sync_year(2026, overwrite_manual=False)

    assert stats.skipped_manual == 1
    db_session.expire_all()
    row = db_session.query(ProductionCalendarDay).filter_by(
        date=date(2026, 5, 9)
    ).one()
    assert row.source == "manual"
    assert row.is_workday is True
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
py -3.10 -m pytest tests/test_production_calendar_service.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement service**

Create `app/services/production_calendar_service.py`:

```python
"""Сервис производственного календаря РФ.

Источник данных — таблица ``production_calendar_day``. Неуказанные дни
интерпретируются как обычные (будни по правилу ``weekday() < 5``).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.connectors.production_calendar_client import ProductionCalendarClient
from app.models import ProductionCalendarDay


@dataclass
class SyncStats:
    inserted: int
    updated: int
    skipped_manual: int


class ProductionCalendarService:
    """Чтение и обновление производственного календаря."""

    def __init__(
        self,
        db: Session,
        client: Optional[ProductionCalendarClient] = None,
    ) -> None:
        self.db = db
        self.client = client or ProductionCalendarClient()

    def is_workday(self, d: date) -> bool:
        row = self.db.get(ProductionCalendarDay, d)
        if row is not None:
            return bool(row.is_workday)
        return d.weekday() < 5

    def workdays_in_range_map(self, start: date, end: date) -> dict[date, bool]:
        """Возвращает карту ``date -> is_workday`` только для тех дат в
        диапазоне ``[start, end]``, для которых в таблице есть запись.

        Используется ``CapacityService._workdays_in_range`` для O(1) lookup'а
        вместо per-day запроса.
        """
        if end < start:
            return {}
        rows = (
            self.db.query(ProductionCalendarDay)
            .filter(
                ProductionCalendarDay.date >= start,
                ProductionCalendarDay.date <= end,
            )
            .all()
        )
        return {r.date: bool(r.is_workday) for r in rows}

    async def sync_year(
        self, year: int, overwrite_manual: bool = False
    ) -> SyncStats:
        days = await self.client.fetch_year(year)
        inserted = updated = skipped_manual = 0

        for raw in days:
            existing = self.db.get(ProductionCalendarDay, raw.date)
            if existing and existing.source == "manual" and not overwrite_manual:
                skipped_manual += 1
                continue
            if existing is None:
                self.db.add(ProductionCalendarDay(
                    date=raw.date,
                    is_workday=raw.is_workday,
                    kind=raw.kind,
                    note=raw.note,
                    source="xmlcalendar",
                    synced_at=datetime.utcnow(),
                ))
                inserted += 1
            else:
                existing.is_workday = raw.is_workday
                existing.kind = raw.kind
                existing.note = raw.note
                existing.source = "xmlcalendar"
                existing.synced_at = datetime.utcnow()
                updated += 1

        self.db.commit()
        return SyncStats(
            inserted=inserted, updated=updated, skipped_manual=skipped_manual
        )

    def list_year(self, year: int) -> list[ProductionCalendarDay]:
        return (
            self.db.query(ProductionCalendarDay)
            .filter(
                ProductionCalendarDay.date >= date(year, 1, 1),
                ProductionCalendarDay.date <= date(year, 12, 31),
            )
            .order_by(ProductionCalendarDay.date)
            .all()
        )

    def upsert_manual(
        self, d: date, is_workday: bool, kind: str, note: Optional[str] = None
    ) -> ProductionCalendarDay:
        row = self.db.get(ProductionCalendarDay, d)
        if row is None:
            row = ProductionCalendarDay(
                date=d, is_workday=is_workday, kind=kind, note=note,
                source="manual", synced_at=datetime.utcnow(),
            )
            self.db.add(row)
        else:
            row.is_workday = is_workday
            row.kind = kind
            row.note = note
            row.source = "manual"
            row.synced_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_manual(self, d: date) -> bool:
        row = self.db.get(ProductionCalendarDay, d)
        if row is None or row.source != "manual":
            return False
        self.db.delete(row)
        self.db.commit()
        return True
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_production_calendar_service.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/production_calendar_service.py tests/test_production_calendar_service.py
git commit -m "ProductionCalendarService (sync + fallback + manual)"
```

---

### Task 4.4: Integrate calendar into `CapacityService._workdays_in_range`

**Files:**
- Modify: `app/services/capacity_service.py`
- Modify: `tests/test_capacity_service.py` (or add new)

- [ ] **Step 1: Write failing test**

Append to `tests/test_capacity_service.py` (create `TestWorkdayCalendarIntegration` class):

```python
from datetime import date, timedelta

from app.models import ProductionCalendarDay
from app.services.capacity_service import CapacityService


def _naive_weekday_count(start: date, end: date) -> int:
    """Baseline: count of weekday <5 days in [start, end]."""
    n, d = 0, start
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


class TestWorkdayCalendarIntegration:
    def test_holidays_reduce_workday_count(self, db_session, employee):
        # 2026-01-01..08 — holidays. Some are weekdays, some weekends.
        holiday_dates = [date(2026, 1, d) for d in range(1, 9)]
        for d in holiday_dates:
            db_session.add(ProductionCalendarDay(
                date=d, is_workday=False, kind="holiday",
                note="НГ", source="xmlcalendar",
            ))
        db_session.commit()

        svc = CapacityService(db_session)
        got = svc._workdays_in_range(date(2026, 1, 1), date(2026, 1, 31))

        # Expected: naive count minus the holidays that fall on weekdays.
        baseline = _naive_weekday_count(date(2026, 1, 1), date(2026, 1, 31))
        weekday_holidays = sum(1 for d in holiday_dates if d.weekday() < 5)
        assert got == baseline - weekday_holidays

    def test_weekend_overridden_to_workday(self, db_session, employee):
        # 2026-03-07 is Saturday; override to workday via "перенос"
        db_session.add(ProductionCalendarDay(
            date=date(2026, 3, 7), is_workday=True,
            kind="workday_moved", note="перенос", source="xmlcalendar",
        ))
        db_session.commit()
        svc = CapacityService(db_session)
        got = svc._workdays_in_range(date(2026, 3, 7), date(2026, 3, 7))
        assert got == 1
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
py -3.10 -m pytest tests/test_capacity_service.py::TestWorkdayCalendarIntegration -v
```
Expected: both tests FAIL — current service ignores `ProductionCalendarDay`.

- [ ] **Step 3: Modify `CapacityService`**

In `app/services/capacity_service.py`:

Add import at top:

```python
from typing import Optional
from app.services.production_calendar_service import ProductionCalendarService
```

Update `__init__`:

```python
    def __init__(
        self,
        db: Session,
        hours_per_day: float = DEFAULT_HOURS_PER_DAY,
        production_calendar: Optional[ProductionCalendarService] = None,
    ):
        self.db = db
        self.hours_per_day = hours_per_day
        self.production_calendar = (
            production_calendar or ProductionCalendarService(db)
        )
```

Replace `_workdays_in_range`:

```python
    def _workdays_in_range(self, start: date, end: date) -> int:
        if end < start:
            return 0
        overrides = self.production_calendar.workdays_in_range_map(start, end)
        days, current = 0, start
        while current <= end:
            is_wd = overrides.get(current, current.weekday() < 5)
            if is_wd:
                days += 1
            current += timedelta(days=1)
        return days
```

Remove the `@staticmethod` decorator on `_workdays_in_range` if present.

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_capacity_service.py -v
```
Expected: all capacity tests (old + new) PASS. Older tests that used `_workdays_in_range` without seeding production_calendar still pass because absent rows fall back to `weekday < 5`.

- [ ] **Step 5: Commit**

```bash
git add app/services/capacity_service.py tests/test_capacity_service.py
git commit -m "CapacityService uses ProductionCalendarService for workday count"
```

---

### Task 4.5: Production calendar API

**Files:**
- Create: `app/api/endpoints/production_calendar.py`
- Modify: `app/api/router.py`
- Create: `tests/test_production_calendar_endpoints.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_production_calendar_endpoints.py`:

```python
from datetime import date
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import ProductionCalendarDay


def test_list_year_returns_sorted(db_session):
    db_session.add_all([
        ProductionCalendarDay(date=date(2026, 5, 9), is_workday=False,
                              kind="holiday", source="xmlcalendar"),
        ProductionCalendarDay(date=date(2026, 1, 1), is_workday=False,
                              kind="holiday", source="xmlcalendar"),
    ])
    db_session.commit()
    client = TestClient(app)
    resp = client.get("/api/v1/production-calendar", params={"year": 2026})
    assert resp.status_code == 200
    dates = [row["date"] for row in resp.json()]
    assert dates == ["2026-01-01", "2026-05-09"]


def test_upsert_manual(db_session):
    client = TestClient(app)
    resp = client.put(
        "/api/v1/production-calendar",
        json={"date": "2026-12-31", "is_workday": False, "kind": "holiday",
              "note": "NY eve"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "manual"
    assert body["note"] == "NY eve"


def test_delete_manual_only(db_session):
    db_session.add(ProductionCalendarDay(
        date=date(2026, 5, 9), is_workday=False, kind="holiday",
        source="xmlcalendar",
    ))
    db_session.commit()
    client = TestClient(app)
    resp = client.delete("/api/v1/production-calendar/2026-05-09")
    assert resp.status_code == 400   # source=xmlcalendar, not deletable


def test_sync_year_calls_service():
    from app.services.production_calendar_service import SyncStats
    with patch(
        "app.services.production_calendar_service.ProductionCalendarService.sync_year",
        new=AsyncMock(return_value=SyncStats(inserted=10, updated=0, skipped_manual=1)),
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/production-calendar/sync", params={"year": 2026})
    assert resp.status_code == 200
    assert resp.json() == {"inserted": 10, "updated": 0, "skipped_manual": 1}
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
py -3.10 -m pytest tests/test_production_calendar_endpoints.py -v
```
Expected: 404 on all.

- [ ] **Step 3: Implement endpoints**

Create `app/api/endpoints/production_calendar.py`:

```python
"""HTTP-эндпоинты производственного календаря."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.production_calendar_service import ProductionCalendarService


router = APIRouter()


class CalendarDayResponse(BaseModel):
    date: date
    is_workday: bool
    kind: str
    note: str | None
    source: str


class CalendarDayUpsertRequest(BaseModel):
    date: date
    is_workday: bool
    kind: str
    note: str | None = None


class CalendarSyncResponse(BaseModel):
    inserted: int
    updated: int
    skipped_manual: int


@router.get("", response_model=list[CalendarDayResponse])
def list_year(year: int = Query(...), db: Session = Depends(get_db)):
    svc = ProductionCalendarService(db)
    rows = svc.list_year(year)
    return [CalendarDayResponse.model_validate(r, from_attributes=True) for r in rows]


@router.put("", response_model=CalendarDayResponse)
def upsert_manual(
    req: CalendarDayUpsertRequest, db: Session = Depends(get_db)
):
    svc = ProductionCalendarService(db)
    row = svc.upsert_manual(req.date, req.is_workday, req.kind, req.note)
    return CalendarDayResponse.model_validate(row, from_attributes=True)


@router.delete("/{d}")
def delete_manual(d: date, db: Session = Depends(get_db)):
    svc = ProductionCalendarService(db)
    ok = svc.delete_manual(d)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Can only delete rows with source='manual'.",
        )
    return {"ok": True}


@router.post("/sync", response_model=CalendarSyncResponse)
async def sync_year(
    year: int = Query(...),
    overwrite_manual: bool = Query(False),
    db: Session = Depends(get_db),
):
    svc = ProductionCalendarService(db)
    stats = await svc.sync_year(year, overwrite_manual=overwrite_manual)
    return CalendarSyncResponse(
        inserted=stats.inserted,
        updated=stats.updated,
        skipped_manual=stats.skipped_manual,
    )
```

Wire in `app/api/router.py`:

```python
from app.api.endpoints import production_calendar
api_router.include_router(
    production_calendar.router,
    prefix="/production-calendar",
    tags=["production_calendar"],
)
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_production_calendar_endpoints.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/production_calendar.py app/api/router.py tests/test_production_calendar_endpoints.py
git commit -m "Production calendar HTTP endpoints"
```

---

### Task 4.6: Frontend — Production calendar tab on Settings page

**Files:**
- Create: `frontend/src/api/productionCalendar.ts`
- Create: `frontend/src/hooks/useProductionCalendar.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add API + types**

Append to `frontend/src/types/api.ts`:

```typescript
export interface ProductionCalendarDayResponse {
  date: string;         // YYYY-MM-DD
  is_workday: boolean;
  kind: string;
  note: string | null;
  source: 'xmlcalendar' | 'manual';
}

export interface ProductionCalendarUpsertRequest {
  date: string;
  is_workday: boolean;
  kind: string;
  note: string | null;
}

export interface ProductionCalendarSyncResponse {
  inserted: number;
  updated: number;
  skipped_manual: number;
}
```

Create `frontend/src/api/productionCalendar.ts`:

```typescript
import { api } from './client';
import type {
  ProductionCalendarDayResponse,
  ProductionCalendarUpsertRequest,
  ProductionCalendarSyncResponse,
} from '../types/api';

export const listProductionCalendarYear = (year: number) =>
  api.get<ProductionCalendarDayResponse[]>('/production-calendar', { year });

export const upsertProductionCalendarDay = (req: ProductionCalendarUpsertRequest) =>
  api.put<ProductionCalendarDayResponse>('/production-calendar', req);

export const deleteProductionCalendarDay = (date: string) =>
  api.del<{ ok: boolean }>(`/production-calendar/${date}`);

export const syncProductionCalendarYear = (year: number) =>
  api.post<ProductionCalendarSyncResponse>(
    '/production-calendar/sync', {}, { year }
  );
```

Adjust `api.post(...)` signature if the existing helper doesn't accept a third query-params argument — use whatever pattern neighbouring API files use for POST + query.

- [ ] **Step 2: Add hooks**

Create `frontend/src/hooks/useProductionCalendar.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listProductionCalendarYear, upsertProductionCalendarDay,
  deleteProductionCalendarDay, syncProductionCalendarYear,
} from '../api/productionCalendar';
import type {
  ProductionCalendarDayResponse, ProductionCalendarUpsertRequest,
  ProductionCalendarSyncResponse,
} from '../types/api';

export const useProductionCalendarYear = (year: number) =>
  useQuery({
    queryKey: ['production-calendar', year],
    queryFn: () => listProductionCalendarYear(year),
    staleTime: 60_000,
  });

export const useUpsertProductionCalendarDay = () => {
  const qc = useQueryClient();
  return useMutation<
    ProductionCalendarDayResponse, Error, ProductionCalendarUpsertRequest
  >({
    mutationFn: upsertProductionCalendarDay,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['production-calendar'] }),
  });
};

export const useDeleteProductionCalendarDay = () => {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean }, Error, string>({
    mutationFn: deleteProductionCalendarDay,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['production-calendar'] }),
  });
};

export const useSyncProductionCalendarYear = () => {
  const qc = useQueryClient();
  return useMutation<ProductionCalendarSyncResponse, Error, number>({
    mutationFn: syncProductionCalendarYear,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['production-calendar'] }),
  });
};
```

- [ ] **Step 3: Add Settings tab**

In `frontend/src/pages/SettingsPage.tsx`, add a new tab entry `{ key: 'calendar', label: 'Производственный календарь', children: <ProductionCalendarTab /> }`.

Create `<ProductionCalendarTab />` in the same file (inline):

```tsx
function ProductionCalendarTab() {
  const { notification } = App.useApp();
  const [year, setYear] = useState<number>(dayjs().year());
  const q = useProductionCalendarYear(year);
  const sync = useSyncProductionCalendarYear();
  const upsert = useUpsertProductionCalendarDay();
  const del = useDeleteProductionCalendarDay();
  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm();

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <InputNumber
          value={year}
          min={2020}
          max={2035}
          onChange={(v) => v && setYear(v)}
        />
        <Popconfirm
          title={`Загрузить ${year} из xmlcalendar.ru?`}
          onConfirm={() => sync.mutate(year, {
            onSuccess: (s) => notification.success({
              message: 'Календарь обновлён',
              description: `Добавлено: ${s.inserted}, обновлено: ${s.updated}, ручных пропущено: ${s.skipped_manual}`,
            }),
            onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
          })}
        >
          <Button loading={sync.isPending} icon={<CloudDownloadOutlined />}>
            Загрузить с xmlcalendar.ru
          </Button>
        </Popconfirm>
        <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
          Добавить день
        </Button>
      </Space>
      <Table<ProductionCalendarDayResponse>
        dataSource={q.data}
        rowKey="date"
        loading={q.isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Дата', dataIndex: 'date',
            render: (v: string) => dayjs(v).format('DD.MM.YYYY') },
          { title: 'Тип', dataIndex: 'kind' },
          { title: 'Рабочий?', dataIndex: 'is_workday',
            render: (v: boolean) => (v ? 'да' : 'нет') },
          { title: 'Примечание', dataIndex: 'note' },
          { title: 'Источник', dataIndex: 'source' },
          {
            title: '', width: 80,
            render: (_, r) => r.source === 'manual' ? (
              <Popconfirm title="Удалить?" onConfirm={() =>
                del.mutate(r.date, {
                  onError: (e) => notification.error({
                    message: 'Ошибка', description: e.message,
                  }),
                })
              }>
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ) : null,
          },
        ]}
      />
      <Modal
        title="Добавить/изменить день"
        open={addOpen}
        onCancel={() => { setAddOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={(vals) => {
          upsert.mutate({
            date: vals.date.format('YYYY-MM-DD'),
            is_workday: vals.is_workday,
            kind: vals.kind,
            note: vals.note ?? null,
          }, {
            onSuccess: () => {
              setAddOpen(false);
              form.resetFields();
              notification.success({ message: 'Сохранено' });
            },
            onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
          });
        }}>
          <Form.Item name="date" label="Дата" rules={[{ required: true }]}>
            <DatePicker format="DD.MM.YYYY" />
          </Form.Item>
          <Form.Item name="is_workday" label="Рабочий?" valuePropName="checked"
                     initialValue={false}>
            <Switch />
          </Form.Item>
          <Form.Item name="kind" label="Тип" initialValue="holiday"
                     rules={[{ required: true }]}>
            <Select options={[
              { value: 'holiday', label: 'Праздник' },
              { value: 'weekend', label: 'Выходной' },
              { value: 'preholiday', label: 'Предпраздничный' },
              { value: 'workday_moved', label: 'Перенесённый рабочий' },
            ]} />
          </Form.Item>
          <Form.Item name="note" label="Примечание"><Input /></Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
```

Add imports: `InputNumber`, `Switch`, `Input`, `CloudDownloadOutlined`, `PlusOutlined`, `DeleteOutlined`, hooks, types.

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/productionCalendar.ts frontend/src/hooks/useProductionCalendar.ts frontend/src/types/api.ts frontend/src/pages/SettingsPage.tsx
git commit -m "Production calendar tab on Settings page"
git push origin main
```

---

## Phase 5 — Plan / Fact / % columns

### Task 5.1: `MonthlyCapacity.fact_hours` + `CapacityService.monthly_capacity`

**Files:**
- Modify: `app/services/capacity_service.py`
- Modify: `tests/test_capacity_service.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_capacity_service.py`:

```python
from datetime import datetime

from app.models import Issue, Project, Worklog


class TestMonthlyCapacityFact:
    def test_fact_hours_sums_worklogs_in_month(self, db_session, employee):
        proj = Project(id="p", jira_project_id="10", key="P", name="P")
        issue = Issue(id="i", jira_issue_id="1", key="P-1", summary="x",
                      project_id=proj.id, issuetype="Task", status="В работе")
        db_session.add_all([proj, issue])
        db_session.flush()
        db_session.add_all([
            Worklog(id="w1", jira_worklog_id="1", issue_id=issue.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 1, 15, 10, 0),
                    hours=4.0, time_spent_seconds=14400),
            Worklog(id="w2", jira_worklog_id="2", issue_id=issue.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 1, 20, 10, 0),
                    hours=3.0, time_spent_seconds=10800),
            Worklog(id="w3", jira_worklog_id="3", issue_id=issue.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 2, 1, 10, 0),
                    hours=2.0, time_spent_seconds=7200),
        ])
        db_session.commit()

        svc = CapacityService(db_session)
        mc = svc.monthly_capacity(employee.id, 2026, 1)
        assert mc.fact_hours == 7.0

    def test_fact_hours_zero_when_no_worklogs(self, db_session, employee):
        svc = CapacityService(db_session)
        mc = svc.monthly_capacity(employee.id, 2026, 3)
        assert mc.fact_hours == 0.0

    def test_quarter_fact_sums_months(self, db_session, employee):
        proj = Project(id="pp", jira_project_id="20", key="PP", name="PP")
        issue = Issue(id="ii", jira_issue_id="2", key="PP-1", summary="x",
                      project_id=proj.id, issuetype="Task", status="В работе")
        db_session.add_all([proj, issue])
        db_session.flush()
        for month, day, h in [(1, 10, 5.0), (2, 10, 4.0), (3, 10, 3.0)]:
            db_session.add(Worklog(
                id=f"w{month}", jira_worklog_id=f"k{month}",
                issue_id=issue.id, employee_id=employee.id,
                started_at=datetime(2026, month, day, 10, 0),
                hours=h, time_spent_seconds=int(h * 3600),
            ))
        db_session.commit()

        svc = CapacityService(db_session)
        qc = svc.quarter_capacity(employee.id, 2026, 1)
        assert qc.total_fact_hours == 12.0
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
py -3.10 -m pytest tests/test_capacity_service.py::TestMonthlyCapacityFact -v
```
Expected: `AttributeError: 'MonthlyCapacity' object has no attribute 'fact_hours'`.

- [ ] **Step 3: Extend dataclasses + method**

In `app/services/capacity_service.py`:

Add field to `MonthlyCapacity`:

```python
@dataclass
class MonthlyCapacity:
    # ... existing fields ...
    fact_hours: float = 0.0
```

Add field to `QuarterCapacity`:

```python
@dataclass
class QuarterCapacity:
    # ... existing fields ...
    total_fact_hours: float = 0.0
```

In `monthly_capacity()`, compute fact before returning:

```python
        from sqlalchemy import func
        from app.models import Worklog

        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)

        fact = self.db.query(
            func.coalesce(func.sum(Worklog.hours), 0.0)
        ).filter(
            Worklog.employee_id == employee_id,
            Worklog.started_at >= datetime.combine(
                month_start, datetime.min.time()
            ),
            Worklog.started_at < datetime.combine(
                next_month_start, datetime.min.time()
            ),
        ).scalar() or 0.0
```

Set it in the returned dataclass (`fact_hours=float(fact)`).

In `quarter_capacity()`, after the loop accumulating `total_*`:

```python
result.total_fact_hours = sum(m.fact_hours for m in result.months)
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
py -3.10 -m pytest tests/test_capacity_service.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/capacity_service.py tests/test_capacity_service.py
git commit -m "CapacityService: fact_hours in MonthlyCapacity + QuarterCapacity totals"
```

---

### Task 5.2: Update response schemas + frontend types

**Files:**
- Modify: `app/api/endpoints/capacity.py`
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Write failing integration test**

Append to existing capacity endpoint test file (or create):

```python
def test_team_endpoint_returns_fact_hours(db_session, employee):
    # ... seed a worklog for (2026, 1, employee) ...
    client = TestClient(app)
    resp = client.get("/api/v1/capacity/team", params={"year": 2026, "quarter": 1})
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["employee_id"] == employee.id)
    jan = next(m for m in row["months"] if m["month"] == 1)
    assert "fact_hours" in jan
    assert "total_fact_hours" in row
```

- [ ] **Step 2: Run test — FAIL**

Expected: KeyError or missing field.

- [ ] **Step 3: Extend response schemas**

In `app/api/endpoints/capacity.py`, find `MonthCapacityResponse` and `QuarterCapacityResponse`. Add:

```python
class MonthCapacityResponse(BaseModel):
    # ... existing ...
    fact_hours: float = 0.0


class QuarterCapacityResponse(BaseModel):
    # ... existing ...
    total_fact_hours: float = 0.0
```

Ensure the mapper from dataclass to schema (`from_attributes=True` or explicit) picks up the new fields. If the mapper is manual — add the field there.

Update `frontend/src/types/api.ts`:

```typescript
export interface MonthCapacityResponse {
  // ... existing ...
  fact_hours: number;
}

export interface QuarterCapacityResponse {
  // ... existing ...
  total_fact_hours: number;
}
```

- [ ] **Step 4: Run tests — PASS**

```bash
py -3.10 -m pytest tests/ -v -k capacity
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/capacity.py frontend/src/types/api.ts tests/
git commit -m "Expose fact_hours in /capacity/team response"
```

---

### Task 5.3: Frontend — grouped columns in Team tab

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 1: Replace Team tab columns with grouped structure**

In `CapacityPage.tsx`, replace the existing `columns` array in `TeamTab()`:

```tsx
const pctColor = (plan: number, fact: number): string | undefined => {
  if (plan <= 0) return undefined;
  const pct = (fact / plan) * 100;
  if (pct >= 100) return 'var(--ant-color-success, #52c41a)';
  if (pct < 50) return 'var(--ant-color-text-secondary, #999)';
  return undefined;
};

const pctText = (plan: number, fact: number): string => {
  if (plan <= 0) return '—';
  return `${Math.round((fact / plan) * 100)}%`;
};

const monthGroup = (m: number) => ({
  title: MONTH_NAMES[m],
  children: [
    {
      title: 'План',
      key: `m${m}_plan`,
      width: 80,
      render: (_: unknown, r: QuarterCapacityResponse) => {
        const mc = r.months.find((x) => x.month === m);
        return mc ? formatHours(mc.available_hours) : '—';
      },
    },
    {
      title: 'Факт',
      key: `m${m}_fact`,
      width: 80,
      render: (_: unknown, r: QuarterCapacityResponse) => {
        const mc = r.months.find((x) => x.month === m);
        return mc ? formatHours(mc.fact_hours) : '—';
      },
    },
    {
      title: '%',
      key: `m${m}_pct`,
      width: 60,
      render: (_: unknown, r: QuarterCapacityResponse) => {
        const mc = r.months.find((x) => x.month === m);
        if (!mc) return '—';
        return (
          <span style={{ color: pctColor(mc.available_hours, mc.fact_hours) }}>
            {pctText(mc.available_hours, mc.fact_hours)}
          </span>
        );
      },
    },
  ],
});

const columns = [
  { title: 'Сотрудник', dataIndex: 'employee_name', fixed: 'left' as const, width: 200 },
  ...months.map(monthGroup),
  {
    title: 'Итого',
    children: [
      { title: 'План', dataIndex: 'total_available_hours', render: formatHours, width: 90 },
      { title: 'Факт', dataIndex: 'total_fact_hours', render: formatHours, width: 90 },
      {
        title: '%', width: 70,
        render: (_: unknown, r: QuarterCapacityResponse) => (
          <span style={{ color: pctColor(r.total_available_hours, r.total_fact_hours) }}>
            {pctText(r.total_available_hours, r.total_fact_hours)}
          </span>
        ),
      },
    ],
  },
];
```

Bump `scroll.x` on the `Table` to `1400` (to fit more columns).

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/CapacityPage.tsx
git commit -m "Plan/Fact/% grouped columns on Capacity Team tab"
git push origin main
```

---

## Phase 6 — Category breakdown

### Task 6.1: `CapacityService.category_breakdown`

**Files:**
- Modify: `app/services/capacity_service.py`
- Modify: `tests/test_capacity_service.py` (or new file)

- [ ] **Step 1: Write failing test**

Append to `tests/test_capacity_service.py`:

```python
class TestCategoryBreakdown:
    def test_breakdown_buckets(self, db_session, employee):
        from app.models import Category
        db_session.add_all([
            Category(id="c1", code="active_1", name="Active", is_builtin=False),
            Category(id="c2", code="archive", name="Archive", is_builtin=True),
            Category(id="c3", code="archive_target", name="ArchTarget", is_builtin=True),
            Category(id="c4", code="initiatives_rfa", name="Init", is_builtin=True),
        ])
        proj = Project(id="px", jira_project_id="30", key="X", name="X")
        issue_act = Issue(id="i_act", jira_issue_id="7001", key="X-1", summary="x",
                          project_id=proj.id, issuetype="Task", status="В работе",
                          assigned_category="active_1")
        issue_arch_t = Issue(id="i_atg", jira_issue_id="7002", key="X-2", summary="x",
                             project_id=proj.id, issuetype="Task", status="В работе",
                             assigned_category="archive_target")
        issue_null = Issue(id="i_nul", jira_issue_id="7003", key="X-3", summary="x",
                           project_id=proj.id, issuetype="Task", status="В работе",
                           assigned_category=None)
        db_session.add_all([proj, issue_act, issue_arch_t, issue_null])
        db_session.flush()
        db_session.add_all([
            Worklog(id=f"wa", jira_worklog_id="a", issue_id=issue_act.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 1, 10, 10, 0),
                    hours=10.0, time_spent_seconds=36000),
            Worklog(id=f"wt", jira_worklog_id="t", issue_id=issue_arch_t.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 2, 10, 10, 0),
                    hours=5.0, time_spent_seconds=18000),
            Worklog(id=f"wn", jira_worklog_id="n", issue_id=issue_null.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 3, 10, 10, 0),
                    hours=2.0, time_spent_seconds=7200),
        ])
        db_session.commit()

        svc = CapacityService(db_session)
        rows = svc.category_breakdown(2026, 1)
        row = next(r for r in rows if r.employee_id == employee.id)
        assert row.by_bucket == {
            "active_stack": 10.0,
            "initiatives": 0.0,
            "archive_target": 5.0,
            "archive_other": 0.0,
            "uncategorized": 2.0,
        }
        assert row.total_hours == 17.0
```

- [ ] **Step 2: Run test — FAIL**

```bash
py -3.10 -m pytest tests/test_capacity_service.py::TestCategoryBreakdown -v
```
Expected: `AttributeError: 'CapacityService' object has no attribute 'category_breakdown'`.

- [ ] **Step 3: Implement breakdown**

In `app/services/capacity_service.py`, append:

```python
from dataclasses import dataclass as _dc

BUCKETS = ("active_stack", "initiatives", "archive_target",
           "archive_other", "uncategorized")


@_dc
class EmployeeCategoryBreakdown:
    employee_id: str
    employee_name: str
    by_bucket: dict[str, float]
    total_hours: float


def _bucket_for(code: str | None) -> str:
    if code is None:
        return "uncategorized"
    if code == "archive":
        return "archive_other"
    if code == "archive_target":
        return "archive_target"
    if code == "initiatives_rfa":
        return "initiatives"
    return "active_stack"


# in CapacityService class:
    def category_breakdown(
        self, year: int, quarter: int
    ) -> list["EmployeeCategoryBreakdown"]:
        from sqlalchemy import func
        from app.models import Employee, Issue, Worklog

        if quarter not in QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1..4, got {quarter}")
        months = QUARTER_MONTHS[quarter]
        start = date(year, months[0], 1)
        if months[-1] == 12:
            end_exclusive = date(year + 1, 1, 1)
        else:
            end_exclusive = date(year, months[-1] + 1, 1)

        rows = (
            self.db.query(
                Employee.id, Employee.display_name,
                Issue.assigned_category,
                func.coalesce(func.sum(Worklog.hours), 0.0).label("h"),
            )
            .join(Worklog, Worklog.employee_id == Employee.id)
            .join(Issue, Worklog.issue_id == Issue.id)
            .filter(
                Employee.is_active.is_(True),
                Worklog.started_at >= datetime.combine(start, datetime.min.time()),
                Worklog.started_at <  datetime.combine(end_exclusive, datetime.min.time()),
            )
            .group_by(Employee.id, Employee.display_name, Issue.assigned_category)
            .all()
        )

        per_employee: dict[str, EmployeeCategoryBreakdown] = {}
        for emp_id, name, code, hours in rows:
            row = per_employee.setdefault(
                emp_id,
                EmployeeCategoryBreakdown(
                    employee_id=emp_id, employee_name=name,
                    by_bucket={b: 0.0 for b in BUCKETS},
                    total_hours=0.0,
                ),
            )
            bucket = _bucket_for(code)
            row.by_bucket[bucket] += float(hours)
            row.total_hours += float(hours)

        return list(per_employee.values())
```

- [ ] **Step 4: Run test — PASS**

```bash
py -3.10 -m pytest tests/test_capacity_service.py::TestCategoryBreakdown -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/capacity_service.py tests/test_capacity_service.py
git commit -m "CapacityService.category_breakdown (5 buckets)"
```

---

### Task 6.2: `GET /capacity/team/category-breakdown`

**Files:**
- Modify: `app/api/endpoints/capacity.py`
- Create: `tests/test_capacity_breakdown_endpoint.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_capacity_breakdown_endpoint.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_breakdown_endpoint_returns_rows(db_session, employee):
    # Minimal seed: employee with no worklogs -> empty list
    client = TestClient(app)
    resp = client.get(
        "/api/v1/capacity/team/category-breakdown",
        params={"year": 2026, "quarter": 1},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run test — FAIL**

Expected: 404.

- [ ] **Step 3: Add endpoint**

In `app/api/endpoints/capacity.py`, add schemas + route:

```python
class CategoryBreakdownResponse(BaseModel):
    employee_id: str
    employee_name: str
    by_bucket: dict[str, float]
    total_hours: float


@router.get(
    "/team/category-breakdown", response_model=list[CategoryBreakdownResponse]
)
def team_category_breakdown(
    year: int = Query(...),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    svc = CapacityService(db)
    rows = svc.category_breakdown(year, quarter)
    return [
        CategoryBreakdownResponse(
            employee_id=r.employee_id,
            employee_name=r.employee_name,
            by_bucket=r.by_bucket,
            total_hours=r.total_hours,
        )
        for r in rows
    ]
```

- [ ] **Step 4: Run test — PASS**

```bash
py -3.10 -m pytest tests/test_capacity_breakdown_endpoint.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/capacity.py tests/test_capacity_breakdown_endpoint.py
git commit -m "GET /capacity/team/category-breakdown"
```

---

### Task 6.3: Frontend — "Распределение" tab

**Files:**
- Modify: `frontend/src/api/capacity.ts`
- Modify: `frontend/src/hooks/useCapacity.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 1: Add API + types**

Append to `frontend/src/types/api.ts`:

```typescript
export interface CategoryBreakdownResponse {
  employee_id: string;
  employee_name: string;
  by_bucket: {
    active_stack: number;
    initiatives: number;
    archive_target: number;
    archive_other: number;
    uncategorized: number;
  };
  total_hours: number;
}
```

Append to `frontend/src/api/capacity.ts`:

```typescript
import type { CategoryBreakdownResponse } from '../types/api';

export const getCategoryBreakdown = (year: number, quarter: number) =>
  api.get<CategoryBreakdownResponse[]>(
    '/capacity/team/category-breakdown', { year, quarter }
  );
```

- [ ] **Step 2: Add hook**

Append to `frontend/src/hooks/useCapacity.ts`:

```typescript
import { getCategoryBreakdown } from '../api/capacity';
import type { CategoryBreakdownResponse } from '../types/api';

export const useCategoryBreakdown = (year: number, quarter: number) =>
  useQuery({
    queryKey: ['capacity', 'breakdown', year, quarter],
    queryFn: () => getCategoryBreakdown(year, quarter),
    staleTime: 30_000,
  });
```

- [ ] **Step 3: Add tab**

In `frontend/src/pages/CapacityPage.tsx`:

```tsx
function BreakdownTab() {
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useCategoryBreakdown(year, Number(quarter));
  return (
    <Table<CategoryBreakdownResponse>
      dataSource={data}
      rowKey="employee_id"
      loading={isLoading}
      pagination={false}
      size="small"
      columns={[
        { title: 'Сотрудник', dataIndex: 'employee_name', fixed: 'left' as const, width: 200 },
        { title: 'Активный стек',
          render: (_, r) => formatHours(r.by_bucket.active_stack) },
        { title: 'Инициативы',
          render: (_, r) => formatHours(r.by_bucket.initiatives) },
        { title: 'Архив квартальных',
          render: (_, r) => formatHours(r.by_bucket.archive_target) },
        { title: 'Архив прочих',
          render: (_, r) => formatHours(r.by_bucket.archive_other) },
        { title: 'Без категории',
          render: (_, r) => formatHours(r.by_bucket.uncategorized) },
        { title: 'Итого', dataIndex: 'total_hours', render: formatHours },
      ]}
    />
  );
}
```

Add to the `Tabs` items in `CapacityPage` default export:

```tsx
{ key: 'breakdown', label: 'Распределение', children: <BreakdownTab /> },
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/capacity.ts frontend/src/hooks/useCapacity.ts frontend/src/types/api.ts frontend/src/pages/CapacityPage.tsx
git commit -m "Capacity page: Распределение tab (per-bucket fact)"
git push origin main
```

---

## Final verification

After all 6 phases are complete:

- [ ] **Full test suite:**
```bash
py -3.10 -m pytest tests/ -v
```
Expected: all PASS.

- [ ] **Full frontend build + lint:**
```bash
cd frontend && npm run lint && npm run build
```
Expected: both PASS.

- [ ] **Manual smoke (optional but recommended):**

```bash
py -3.10 scripts/local_smoke.py
```

Open `http://localhost:5173`:
1. `/sync` → see worklog-reload DatePicker+button; click through with a past date.
2. `/capacity` → Team tab shows filter, recalc button, add-employee button, plan/fact/% columns.
3. `/capacity` → Распределение tab renders with per-bucket totals.
4. `/settings` → Производственный календарь tab: load 2026, see table populate.

## Rollback notes

Each phase commits independently. Reverting a single phase means `git revert <sha>` on its commits. The migration in Phase 4 (`016_production_calendar`) is the only schema change — its `downgrade()` drops the table cleanly.
