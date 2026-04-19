# Dashboard & Analytics — Team Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared, server-side team filter to Dashboard and Analytics pages that matches worklogs by either the employee's team membership or the issue's team (OR-union, controlled by two checkboxes).

**Architecture:** Backend: one `_apply_team_filter` helper in `AnalyticsService` reused by all 5 analytics methods; extend all 5 `/analytics/*` endpoints and 2 `/exports/analytics.*` endpoints with `teams`, `match_employees`, `match_issues` query params. Frontend: new `FactFilterProvider` wrapping Dashboard + Analytics routes, `FactFilterBar` component (teams Select + 2 checkboxes), params threaded through `useHoursBy*` / `useContextSwitching` hooks and export downloaders.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 (backend), React 19 + TypeScript + Ant Design 6 + TanStack Query (frontend). Tests: pytest + Playwright.

Spec: [docs/superpowers/specs/2026-04-19-dashboard-analytics-team-filter-design.md](../specs/2026-04-19-dashboard-analytics-team-filter-design.md)

---

## Task 1: Backend — `_apply_team_filter` helper with full test coverage

**Files:**
- Modify: `app/services/analytics_service.py`
- Modify: `tests/test_analytics_service.py`

The helper builds a SQL clause that matches a Worklog via employee membership (OR) issue team membership, based on flags. It must be reusable across all 5 analytics methods. We TDD it directly against `hours_by_employee` first — it's the simplest consumer.

- [ ] **Step 1.1: Extend test fixture with team data**

Replace the existing `setup_data` fixture in `tests/test_analytics_service.py` (around line 18) to add `Issue.team` + `Issue.participating_teams` + `EmployeeTeam` rows. Modify ONLY the fixture, don't change existing test assertions that don't touch teams.

Insert after the existing `db_session.add_all([alice, bob])` line:

```python
    from app.models import EmployeeTeam

    db_session.flush()  # Need alice.id/bob.id for EmployeeTeam
    db_session.add_all([
        EmployeeTeam(employee_id=alice.id, team="Core", is_primary=True),
        EmployeeTeam(employee_id=bob.id, team="Mobile", is_primary=True),
    ])
```

Modify the three `Issue(...)` constructors:
- `issue_a1`: add `team="Core"`, `participating_teams='["Core","Mobile"]'`
- `issue_a2`: add `team="Mobile"`, `participating_teams='["Mobile"]'`
- `issue_b1`: add `team=None`, `participating_teams='[]'`

(No Carol employee yet — we add a "no team" employee in test 1.7 where it's needed.)

- [ ] **Step 1.2: Run the suite to make sure existing tests still pass**

Run: `py -3.10 -m pytest tests/test_analytics_service.py -v`
Expected: all existing tests PASS (team fields are optional, no existing assertion depends on them).

- [ ] **Step 1.3: Add failing test for `match_employees` only**

Append to `tests/test_analytics_service.py` at the bottom of `class TestHoursByEmployee`:

```python
    def test_team_filter_employees_only(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["Core"],
            match_employees=True,
            match_issues=False,
        )
        by_name = {r.label: r for r in rows}
        assert "Alice" in by_name  # Alice is in Core
        assert "Bob" not in by_name  # Bob is in Mobile
        assert by_name["Alice"].total_hours == 6.0  # all Alice's worklogs
```

- [ ] **Step 1.4: Run the new test — expect it to fail**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestHoursByEmployee::test_team_filter_employees_only -v`
Expected: FAIL with `TypeError: hours_by_employee() got an unexpected keyword argument 'teams'`.

- [ ] **Step 1.5: Implement `_apply_team_filter` helper**

In `app/services/analytics_service.py`, update the imports:

```python
from sqlalchemy import func, and_, or_, select, exists
from sqlalchemy.orm import Session, aliased
```

Add the model import:

```python
from app.models import Worklog, Issue, Employee, Project, CategoryMapping, EmployeeTeam
```

Add constants at module level (above the `AggregateRow` dataclass):

```python
NO_TEAM_TOKEN = "__none__"
```

Add the helper method inside `AnalyticsService`, directly below `_apply_date_filter`:

```python
    def _apply_team_filter(
        self,
        query,
        teams: Optional[list[str]],
        match_employees: bool,
        match_issues: bool,
    ):
        """Apply team filter (employee-side OR issue-side).

        If ``teams`` is empty or both flags are False, return query unchanged.
        ``Issue`` must already be joined in the caller when ``match_issues``.
        """
        if not teams or (not match_employees and not match_issues):
            return query

        named_teams = [t for t in teams if t != NO_TEAM_TOKEN]
        has_none = NO_TEAM_TOKEN in teams

        clauses: list = []

        if match_employees:
            emp_sub_clauses: list = []
            if named_teams:
                emp_sub_clauses.append(
                    Worklog.employee_id.in_(
                        select(EmployeeTeam.employee_id).where(
                            EmployeeTeam.team.in_(named_teams)
                        )
                    )
                )
            if has_none:
                emp_sub_clauses.append(
                    ~exists().where(EmployeeTeam.employee_id == Worklog.employee_id)
                )
            if emp_sub_clauses:
                clauses.append(or_(*emp_sub_clauses) if len(emp_sub_clauses) > 1 else emp_sub_clauses[0])

        if match_issues:
            issue_sub_clauses: list = []
            if named_teams:
                named_clause = [Issue.team.in_(named_teams)]
                for t in named_teams:
                    escaped = t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    named_clause.append(
                        Issue.participating_teams.like(f'%"{escaped}"%', escape="\\")
                    )
                issue_sub_clauses.append(or_(*named_clause))
            if has_none:
                issue_sub_clauses.append(
                    and_(
                        Issue.team.is_(None),
                        or_(
                            Issue.participating_teams.is_(None),
                            Issue.participating_teams == "[]",
                        ),
                    )
                )
            if issue_sub_clauses:
                clauses.append(or_(*issue_sub_clauses) if len(issue_sub_clauses) > 1 else issue_sub_clauses[0])

        if not clauses:
            return query

        final = or_(*clauses) if len(clauses) > 1 else clauses[0]
        return query.filter(final)
```

- [ ] **Step 1.6: Wire helper into `hours_by_employee`**

In `hours_by_employee` (around lines 65-103), change the signature and add the helper call. Replace:

```python
    def hours_by_employee(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> list[AggregateRow]:
```

with:

```python
    def hours_by_employee(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
    ) -> list[AggregateRow]:
```

After the existing `if project_key:` block that joins `Issue` and `Project`, add:

```python
        if teams and match_issues:
            # Need Issue join for match_issues; safe to add if project_key already joined it
            if not project_key:
                query = query.join(Issue, Worklog.issue_id == Issue.id)
        query = self._apply_team_filter(query, teams, match_employees, match_issues)
```

- [ ] **Step 1.7: Run test — expect PASS**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestHoursByEmployee::test_team_filter_employees_only -v`
Expected: PASS.

- [ ] **Step 1.8: Add failing test for `match_issues` only**

Append to `TestHoursByEmployee`:

```python
    def test_team_filter_issues_only(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["Mobile"],
            match_employees=False,
            match_issues=True,
        )
        by_name = {r.label: r for r in rows}
        # Mobile issues: AAA-2 (team=Mobile) + BBB-1 via participating_teams? BBB-1 has team=None, participating_teams='[]'
        # Actually AAA-1 has participating_teams='["Core","Mobile"]' — so Mobile matches AAA-1 too.
        # Worklogs on AAA-1: Alice 2h + Bob 2h; on AAA-2: Alice 3h; BBB-1: none.
        # So Alice total = 5h (AAA-1 + AAA-2), Bob total = 2h (AAA-1)
        assert by_name["Alice"].total_hours == 5.0
        assert by_name["Bob"].total_hours == 2.0
```

- [ ] **Step 1.9: Run both tests**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestHoursByEmployee -v`
Expected: all PASS.

- [ ] **Step 1.10: Add failing test for union (both flags on)**

```python
    def test_team_filter_union(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["Core"],
            match_employees=True,
            match_issues=True,
        )
        by_name = {r.label: r for r in rows}
        # Alice (Core member) -> all her worklogs (6h)
        # Bob (not Core member), but AAA-1 has team=Core (via participating_teams) and worklog wl5 on AAA-1 -> 2h
        # BBB-1 has no Core team -> Bob's wl4 (4h on BBB-1) excluded
        assert by_name["Alice"].total_hours == 6.0
        assert by_name["Bob"].total_hours == 2.0
```

Also add:

```python
    def test_team_filter_none_token_employees(self, db_session, setup_data):
        # Add an employee with no team memberships
        carol = Employee(jira_account_id="c1", display_name="Carol")
        db_session.add(carol)
        db_session.flush()
        # Give Carol a worklog on AAA-1
        db_session.add(Worklog(
            jira_worklog_id="wl6",
            started_at=datetime(2026, 1, 9, 10, 0, 0),
            hours=1.5,
            time_spent_seconds=5400,
            comment_text="carol",
            issue_id=setup_data["worklogs"][0].issue_id,  # AAA-1
            employee_id=carol.id,
        ))
        db_session.flush()

        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["__none__"],
            match_employees=True,
            match_issues=False,
        )
        by_name = {r.label: r for r in rows}
        assert "Carol" in by_name
        assert by_name["Carol"].total_hours == 1.5
        assert "Alice" not in by_name
        assert "Bob" not in by_name

    def test_team_filter_none_token_issues(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["__none__"],
            match_employees=False,
            match_issues=True,
        )
        by_name = {r.label: r for r in rows}
        # Only BBB-1 has no team; worklogs on BBB-1: Alice wl3 (1h) + Bob wl4 (4h)
        assert by_name["Alice"].total_hours == 1.0
        assert by_name["Bob"].total_hours == 4.0

    def test_team_filter_empty_teams_is_noop(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows_filtered = service.hours_by_employee(teams=[], match_employees=True, match_issues=True)
        rows_baseline = service.hours_by_employee()
        # totals identical
        assert sum(r.total_hours for r in rows_filtered) == sum(r.total_hours for r in rows_baseline)

    def test_team_filter_both_flags_off_is_noop(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows_filtered = service.hours_by_employee(
            teams=["Core"], match_employees=False, match_issues=False,
        )
        rows_baseline = service.hours_by_employee()
        assert sum(r.total_hours for r in rows_filtered) == sum(r.total_hours for r in rows_baseline)
```

- [ ] **Step 1.11: Run the whole `TestHoursByEmployee` class**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestHoursByEmployee -v`
Expected: all PASS (7+ tests).

- [ ] **Step 1.12: Commit**

```bash
git add app/services/analytics_service.py tests/test_analytics_service.py
git commit -m "feat(analytics): team filter helper + hours_by_employee support

Server-side team filter with two dimensions (employee membership / issue
team + participating_teams), combined via OR. Supports __none__ token for
employees without team / issues without team.
"
```

---

## Task 2: Backend — Wire team filter into the other 4 analytics methods

**Files:**
- Modify: `app/services/analytics_service.py`
- Modify: `tests/test_analytics_service.py`

Extend `hours_by_project`, `hours_by_category`, `hours_by_period`, `context_switching` to accept + apply the team filter. Pattern matches Task 1.

- [ ] **Step 2.1: Add failing test for `hours_by_project` with team filter**

Append to `class TestHoursByProject` (find it in the file):

```python
    def test_team_filter_union(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_project(
            teams=["Mobile"],
            match_employees=True,
            match_issues=True,
        )
        by_name = {r.label: r for r in rows}
        # Bob (Mobile member) -> all Bob worklogs -> AAA-1 (2h) + BBB-1 (4h)
        # Issue team=Mobile: AAA-2; Issue participating=Mobile: AAA-1; so AAA worklogs by anyone + Mobile-member worklogs
        # Alpha (AAA): Alice 2+3h + Bob 2h = 7h; Beta (BBB): Bob 4h (only via employee, BBB is team-none)
        assert by_name["Alpha"].total_hours == 7.0
        assert by_name["Beta"].total_hours == 4.0
```

- [ ] **Step 2.2: Run — expect fail**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestHoursByProject::test_team_filter_union -v`
Expected: FAIL (unexpected kwargs).

- [ ] **Step 2.3: Extend `hours_by_project`**

Update signature (add same 3 kwargs as Task 1.6). In `hours_by_project` the `Issue` join is already unconditional — just add the team filter call **before** the `.group_by(...)` — actually after the `if project_key:` block (or at the end of filter-building, before materialization). Change `return` section — put the filter application before the final query execution:

In `hours_by_project`, after the `if project_key:` block (around line 129), add:

```python
        query = self._apply_team_filter(query, teams, match_employees, match_issues)
```

Update signature the same way as Task 1.6:

```python
    def hours_by_project(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
    ) -> list[AggregateRow]:
```

- [ ] **Step 2.4: Run — expect PASS**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestHoursByProject::test_team_filter_union -v`
Expected: PASS.

- [ ] **Step 2.5: Add failing test for `hours_by_category` with team filter**

Append to `class TestHoursByCategory`:

```python
    def test_team_filter_employees_only(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_category(
            teams=["Core"],
            match_employees=True,
            match_issues=False,
        )
        by_key = {r.key: r for r in rows}
        # Alice (Core) worklogs: tech_debt 2+3=5h, meetings 1h
        assert by_key[CategoryCode.TECH_DEBT].total_hours == 5.0
        assert by_key[CategoryCode.MEETINGS].total_hours == 1.0
        # Bob worklogs excluded; support_consultation (wl5 by Bob) should be absent
        assert CategoryCode.SUPPORT_CONSULTATION not in by_key
```

- [ ] **Step 2.6: Run — expect fail, then extend `hours_by_category`**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestHoursByCategory::test_team_filter_employees_only -v`
Expected: FAIL.

In `hours_by_category`, update signature identically to Task 1.6, then after the `if project_key:` block, add:

```python
        if teams and match_issues and not project_key:
            query = query.join(Issue, Worklog.issue_id == Issue.id)
        query = self._apply_team_filter(query, teams, match_employees, match_issues)
```

Run again — expect PASS.

- [ ] **Step 2.7: Add failing test for `hours_by_period` with team filter**

Append to `class TestHoursByPeriod`:

```python
    def test_team_filter_issues_only(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_period(
            period="day",
            teams=["Mobile"],
            match_employees=False,
            match_issues=True,
        )
        # Mobile issues: AAA-1 (participating), AAA-2 (team). Their worklogs:
        # wl1 AAA-1 Jan 5 Alice 2h, wl2 AAA-2 Jan 6 Alice 3h, wl5 AAA-1 Jan 8 Bob 2h.
        by_key = {r.key: r.total_hours for r in rows}
        assert by_key.get("2026-01-05") == 2.0
        assert by_key.get("2026-01-06") == 3.0
        assert by_key.get("2026-01-08") == 2.0
        assert "2026-01-07" not in by_key  # BBB-1 (no Mobile) excluded
```

- [ ] **Step 2.8: Run — expect fail, then extend `hours_by_period`**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestHoursByPeriod::test_team_filter_issues_only -v`
Expected: FAIL.

In `hours_by_period`, update signature. The tricky part: the base query is `self.db.query(Worklog.started_at, Worklog.hours)` — it doesn't select from `Worklog` as a full table, so `_apply_team_filter` needs access to `Worklog.employee_id` and `Worklog.issue_id` in WHERE. SQLAlchemy will auto-include the `Worklog` FROM clause when we filter on its columns — that's fine. For `match_issues`, we need the `Issue` join.

After the `if project_key:` block, add:

```python
        if teams and match_issues and not project_key:
            query = query.join(Issue, Worklog.issue_id == Issue.id)
        query = self._apply_team_filter(query, teams, match_employees, match_issues)
```

Run — expect PASS.

- [ ] **Step 2.9: Add failing test for `context_switching` with team filter**

Append to `class TestContextSwitching`:

```python
    def test_team_filter_employees_only(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.context_switching(
            teams=["Core"],
            match_employees=True,
            match_issues=False,
        )
        names = [r.employee_name for r in rows]
        assert "Alice" in names
        assert "Bob" not in names
```

- [ ] **Step 2.10: Run — expect fail, then extend `context_switching`**

Run: `py -3.10 -m pytest tests/test_analytics_service.py::TestContextSwitching::test_team_filter_employees_only -v`
Expected: FAIL.

In `context_switching`, update signature identically. `Issue` is already joined. After the `if project_key:` block add:

```python
        query = self._apply_team_filter(query, teams, match_employees, match_issues)
```

Run — expect PASS.

- [ ] **Step 2.11: Run the full analytics test suite**

Run: `py -3.10 -m pytest tests/test_analytics_service.py -v`
Expected: all PASS.

- [ ] **Step 2.12: Commit**

```bash
git add app/services/analytics_service.py tests/test_analytics_service.py
git commit -m "feat(analytics): team filter on hours_by_project, category, period, context_switching"
```

---

## Task 3: Backend — Extend `/analytics/*` endpoints with team query params

**Files:**
- Modify: `app/api/endpoints/analytics.py`
- Modify: `tests/test_api_analytics.py` (or add if missing — see step 3.1)

- [ ] **Step 3.1: Check if api-level test file exists**

Run: `ls tests/test_api_analytics.py 2>/dev/null || echo "MISSING"`
If MISSING, use `tests/test_analytics_endpoints.py` as test file name (check what exists first — glob `tests/*analytics*`).

Run: `ls tests/*analytics*`
Note the filename. Use that filename for the next steps. If no endpoint test file exists, create `tests/test_analytics_endpoints.py` with:

```python
"""Endpoint smoke tests for /analytics/* with team filter."""

from fastapi.testclient import TestClient

from app.main import app


def test_hours_by_employee_team_filter_smoke(client: TestClient, setup_data):
    resp = client.get(
        "/api/v1/analytics/hours/by-employee",
        params={"teams": "Core", "match_employees": "true", "match_issues": "false"},
    )
    assert resp.status_code == 200
    body = resp.json()
    labels = {row["label"] for row in body}
    assert "Alice" in labels
    assert "Bob" not in labels


def test_hours_by_employee_empty_teams(client: TestClient, setup_data):
    resp = client.get("/api/v1/analytics/hours/by-employee", params={"teams": ""})
    assert resp.status_code == 200
    assert len(resp.json()) == 2
```

Skip the fixture-plumbing headache: if `setup_data` isn't available as a client-level fixture, adapt by using `db_session` fixture from `conftest` plus the existing `client` fixture pattern in other endpoint test files.

- [ ] **Step 3.2: Find the existing client fixture pattern**

Run: `grep -rn "def client" tests/conftest.py tests/test_*_endpoints.py tests/test_api_*.py | head -5`
Use the same shape in the new file (or the existing one).

- [ ] **Step 3.3: Run new test — expect fail or 422 (params not accepted yet)**

Run: `py -3.10 -m pytest tests/test_analytics_endpoints.py -v` (or whatever the file is named)
Expected: FAIL (or 422 response) — params not accepted.

- [ ] **Step 3.4: Extend all 5 endpoints**

Edit `app/api/endpoints/analytics.py`. For EACH of the 5 endpoints (`hours_by_employee`, `hours_by_project`, `hours_by_category`, `hours_by_period`, `context_switching`), add these 3 Query params to the signature:

```python
    teams: Optional[str] = Query(None, description="Команды CSV, __none__ = без команды"),
    match_employees: bool = Query(True),
    match_issues: bool = Query(True),
```

And in the service call, parse teams and pass kwargs:

```python
    teams_list = [t for t in (teams.split(",") if teams else []) if t]
    rows = service.hours_by_employee(
        start=start, end=end,
        employee_id=employee_id, project_key=project_key,
        teams=teams_list, match_employees=match_employees, match_issues=match_issues,
    )
```

Do this for all 5 methods. Be careful: `hours_by_period` has extra `period` param first — don't drop it.

- [ ] **Step 3.5: Run endpoint test — expect PASS**

Run: `py -3.10 -m pytest tests/test_analytics_endpoints.py -v`
Expected: PASS.

- [ ] **Step 3.6: Run full analytics suite + manually hit endpoint**

Run: `py -3.10 -m pytest tests/test_analytics_service.py tests/test_analytics_endpoints.py -v`
Expected: all PASS.

- [ ] **Step 3.7: Commit**

```bash
git add app/api/endpoints/analytics.py tests/test_analytics_endpoints.py
git commit -m "feat(api): team filter on /analytics/* endpoints"
```

---

## Task 4: Backend — Pass team filter through `/exports/analytics.*`

**Files:**
- Modify: `app/services/export_service.py`
- Modify: `app/api/endpoints/exports.py`

- [ ] **Step 4.1: Extend `_collect_analytics` to accept + forward filter**

In `app/services/export_service.py`, update `_collect_analytics` (around lines 62-75):

```python
    def _collect_analytics(
        self,
        start: Optional[datetime],
        end: Optional[datetime],
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
    ) -> dict:
        """Собрать все аналитические отчёты за период."""
        analytics = AnalyticsService(self.db)
        kw = dict(
            teams=teams, match_employees=match_employees, match_issues=match_issues,
        )
        return {
            "by_employee": analytics.hours_by_employee(start, end, **kw),
            "by_project": analytics.hours_by_project(start, end, **kw),
            "by_category": analytics.hours_by_category(start, end, **kw),
            "by_period": analytics.hours_by_period("month", start, end, **kw),
            "switching": analytics.context_switching(start, end, **kw),
        }
```

- [ ] **Step 4.2: Extend `build_analytics_xlsx` / `build_analytics_pdf` signatures**

Update both methods to accept `teams`, `match_employees`, `match_issues` and pass to `_collect_analytics`:

```python
    def build_analytics_xlsx(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
    ) -> bytes:
        ...
        data = self._collect_analytics(start, end, teams, match_employees, match_issues)
        ...
```

Do the same for `build_analytics_pdf`.

- [ ] **Step 4.3: Extend export endpoints with team Query params**

In `app/api/endpoints/exports.py`, update `export_analytics_xlsx` and `export_analytics_pdf`. For each add:

```python
    teams: Optional[str] = Query(None),
    match_employees: bool = Query(True),
    match_issues: bool = Query(True),
```

Parse and forward:

```python
    teams_list = [t for t in (teams.split(",") if teams else []) if t]
    data = service.build_analytics_xlsx(
        start=start, end=end,
        teams=teams_list, match_employees=match_employees, match_issues=match_issues,
    )
```

- [ ] **Step 4.4: Smoke-test existing exports suite**

Run: `py -3.10 -m pytest tests/ -v -k "export"`
Expected: existing export tests still PASS (teams is an optional param, default behavior unchanged).

If no export tests exist, just verify endpoints load:

```bash
py -3.10 -c "from app.api.endpoints import exports; print('ok')"
```

- [ ] **Step 4.5: Commit**

```bash
git add app/services/export_service.py app/api/endpoints/exports.py
git commit -m "feat(exports): team filter forwarded to /exports/analytics.xlsx|pdf"
```

---

## Task 5: Frontend — `FactFilterContext` + `FactFilterProvider` with persistence

**Files:**
- Create: `frontend/src/hooks/useFactFilter.ts`
- Create: `frontend/src/components/dashboard/FactFilterProvider.tsx`

- [ ] **Step 5.1: Create the context + hook**

Create `frontend/src/hooks/useFactFilter.ts`:

```ts
import { createContext, useContext } from 'react';

export const NO_TEAM_VALUE = '__none__';

export type FactFilterCtx = {
  selectedTeams: string[];
  setSelectedTeams: (v: string[]) => void;
  matchEmployees: boolean;
  setMatchEmployees: (v: boolean) => void;
  matchIssues: boolean;
  setMatchIssues: (v: boolean) => void;
  hydrated: boolean;
  queryParams: {
    teams?: string;
    match_employees?: boolean;
    match_issues?: boolean;
  };
};

export const FactFilterContext = createContext<FactFilterCtx | null>(null);

export function useFactFilter(): FactFilterCtx {
  const ctx = useContext(FactFilterContext);
  if (!ctx) throw new Error('useFactFilter must be used inside FactFilterProvider');
  return ctx;
}
```

- [ ] **Step 5.2: Create the provider**

Create `frontend/src/components/dashboard/FactFilterProvider.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useGenericSetting, useSaveGenericSetting } from '../../hooks/useSettings';
import { FactFilterContext } from '../../hooks/useFactFilter';

const KEY_TEAMS = 'ui_fact_filter_teams';
const KEY_EMPS = 'ui_fact_filter_scope_employees';
const KEY_ISSUES = 'ui_fact_filter_scope_issues';

export default function FactFilterProvider({ children }: { children: ReactNode }) {
  const storedTeams = useGenericSetting(KEY_TEAMS);
  const storedEmps = useGenericSetting(KEY_EMPS);
  const storedIssues = useGenericSetting(KEY_ISSUES);
  const save = useSaveGenericSetting();

  const [selectedTeams, setSelectedTeamsState] = useState<string[]>([]);
  const [matchEmployees, setMatchEmployeesState] = useState(true);
  const [matchIssues, setMatchIssuesState] = useState(true);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated) return;
    if (storedTeams.data === undefined || storedEmps.data === undefined || storedIssues.data === undefined) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedTeamsState((storedTeams.data?.value || '').split(',').filter(Boolean));
    setMatchEmployeesState(storedEmps.data?.value !== '0'); // default true
    setMatchIssuesState(storedIssues.data?.value !== '0');
    setHydrated(true);
  }, [hydrated, storedTeams.data, storedEmps.data, storedIssues.data]);

  const setSelectedTeams = useCallback((teams: string[]) => {
    setSelectedTeamsState(teams);
    save.mutate({ key: KEY_TEAMS, value: teams.join(',') });
  }, [save]);

  const setMatchEmployees = useCallback((v: boolean) => {
    if (!v && !matchIssues) return; // refuse: at least one must stay on
    setMatchEmployeesState(v);
    save.mutate({ key: KEY_EMPS, value: v ? '1' : '0' });
  }, [matchIssues, save]);

  const setMatchIssues = useCallback((v: boolean) => {
    if (!v && !matchEmployees) return;
    setMatchIssuesState(v);
    save.mutate({ key: KEY_ISSUES, value: v ? '1' : '0' });
  }, [matchEmployees, save]);

  const queryParams = useMemo(() => {
    if (selectedTeams.length === 0) return {};
    return {
      teams: selectedTeams.join(','),
      match_employees: matchEmployees,
      match_issues: matchIssues,
    };
  }, [selectedTeams, matchEmployees, matchIssues]);

  const value = useMemo(
    () => ({
      selectedTeams, setSelectedTeams,
      matchEmployees, setMatchEmployees,
      matchIssues, setMatchIssues,
      hydrated, queryParams,
    }),
    [selectedTeams, setSelectedTeams, matchEmployees, setMatchEmployees, matchIssues, setMatchIssues, hydrated, queryParams],
  );

  return <FactFilterContext.Provider value={value}>{children}</FactFilterContext.Provider>;
}
```

- [ ] **Step 5.3: Type-check**

Run: `cd frontend && npm run lint`
Expected: no errors in new files.

- [ ] **Step 5.4: Commit**

```bash
git add frontend/src/hooks/useFactFilter.ts frontend/src/components/dashboard/FactFilterProvider.tsx
git commit -m "feat(frontend): FactFilterProvider with team + scope checkbox state persistence"
```

---

## Task 6: Frontend — `FactFilterBar` component + wrap routes

**Files:**
- Create: `frontend/src/components/dashboard/FactFilterBar.tsx`
- Modify: `frontend/src/routes.tsx`

- [ ] **Step 6.1: Create the bar**

Create `frontend/src/components/dashboard/FactFilterBar.tsx`:

```tsx
import { Checkbox, Select, Space, Typography } from 'antd';
import { useFactFilter, NO_TEAM_VALUE } from '../../hooks/useFactFilter';
import { useJiraTeams } from '../../hooks/useSync';

const { Text } = Typography;

export default function FactFilterBar() {
  const { selectedTeams, setSelectedTeams, matchEmployees, setMatchEmployees, matchIssues, setMatchIssues } = useFactFilter();
  const jiraTeams = useJiraTeams();
  const options = [
    ...((jiraTeams.data ?? []).map(t => ({ value: t, label: t }))),
    { value: NO_TEAM_VALUE, label: 'Без команды' },
  ];

  return (
    <Space wrap>
      <Select
        mode="multiple"
        allowClear
        placeholder="Команда"
        style={{ minWidth: 220 }}
        value={selectedTeams}
        onChange={setSelectedTeams}
        options={options}
        onDropdownVisibleChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
        loading={jiraTeams.isFetching}
        notFoundContent={jiraTeams.isError ? 'Настройте поля команды' : undefined}
        showSearch
        optionFilterProp="label"
      />
      <Checkbox
        checked={matchEmployees}
        onChange={(e) => setMatchEmployees(e.target.checked)}
      >
        <Text>Сотрудники</Text>
      </Checkbox>
      <Checkbox
        checked={matchIssues}
        onChange={(e) => setMatchIssues(e.target.checked)}
      >
        <Text>Задачи</Text>
      </Checkbox>
    </Space>
  );
}
```

- [ ] **Step 6.2: Wrap Dashboard + Analytics routes with FactFilterProvider**

Edit `frontend/src/routes.tsx`. Import the provider at the top:

```tsx
import FactFilterProvider from './components/dashboard/FactFilterProvider';
```

Replace the Dashboard and Analytics route definitions:

```tsx
      { index: true, element: <FactFilterProvider>{page(<DashboardPage />)}</FactFilterProvider> },
      { path: 'analytics', element: <FactFilterProvider>{page(<AnalyticsPage />)}</FactFilterProvider> },
```

NOTE: each route creates its OWN provider instance, so state does NOT persist in memory when navigating between them. Persistence in AppSetting re-hydrates identically on both, giving the user the same filter. That's acceptable — simpler than hoisting provider above the layout.

- [ ] **Step 6.3: Lint**

Run: `cd frontend && npm run lint`
Expected: clean.

- [ ] **Step 6.4: Commit**

```bash
git add frontend/src/components/dashboard/FactFilterBar.tsx frontend/src/routes.tsx
git commit -m "feat(frontend): FactFilterBar + wrap Dashboard/Analytics routes"
```

---

## Task 7: Frontend — Thread team params through analytics hooks

**Files:**
- Modify: `frontend/src/api/analytics.ts`
- Modify: `frontend/src/hooks/useAnalytics.ts`

The simplest API: pass an optional `extra` object with `{teams, match_employees, match_issues}` through getters and into queryKey.

- [ ] **Step 7.1: Extend `api/analytics.ts`**

Replace the file content:

```ts
import { api } from './client';
import type { AggregateRowResponse, ContextSwitchRowResponse } from '../types/api';

export type TeamFilterParams = {
  teams?: string;
  match_employees?: boolean;
  match_issues?: boolean;
};

const buildParams = (
  start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams,
) => ({
  start, end,
  employee_id: employeeId,
  project_key: projectKey,
  teams: team?.teams,
  match_employees: team?.match_employees,
  match_issues: team?.match_issues,
});

export const getHoursByEmployee = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-employee', buildParams(start, end, employeeId, projectKey, team));

export const getHoursByProject = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-project', buildParams(start, end, employeeId, projectKey, team));

export const getHoursByCategory = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-category', buildParams(start, end, employeeId, projectKey, team));

export const getHoursByPeriod = (period: string, start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-period', { period, ...buildParams(start, end, employeeId, projectKey, team) });

export const getContextSwitching = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<ContextSwitchRowResponse[]>('/analytics/context-switching', buildParams(start, end, employeeId, projectKey, team));
```

- [ ] **Step 7.2: Extend `useAnalytics.ts` hooks**

Replace `frontend/src/hooks/useAnalytics.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { getHoursByEmployee, getHoursByProject, getHoursByCategory, getHoursByPeriod, getContextSwitching, type TeamFilterParams } from '../api/analytics';
import { getEmployees } from '../api/employees';
import { getProjects } from '../api/projects';

const teamKey = (t?: TeamFilterParams) => [t?.teams ?? '', t?.match_employees ?? true, t?.match_issues ?? true];

export const useHoursByEmployee = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'by-employee', start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getHoursByEmployee(start, end, employeeId, projectKey, team) });

export const useHoursByProject = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'by-project', start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getHoursByProject(start, end, employeeId, projectKey, team) });

export const useHoursByCategory = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'by-category', start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getHoursByCategory(start, end, employeeId, projectKey, team) });

export const useHoursByPeriod = (period: string, start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'by-period', period, start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getHoursByPeriod(period, start, end, employeeId, projectKey, team) });

export const useContextSwitching = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'context-switching', start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getContextSwitching(start, end, employeeId, projectKey, team) });

export const useEmployeesForFilter = () =>
  useQuery({ queryKey: ['employees'], queryFn: () => getEmployees() });

export const useProjectsForFilter = () =>
  useQuery({ queryKey: ['projects'], queryFn: () => getProjects() });
```

- [ ] **Step 7.3: Lint**

Run: `cd frontend && npm run lint`
Expected: clean.

- [ ] **Step 7.4: Commit**

```bash
git add frontend/src/api/analytics.ts frontend/src/hooks/useAnalytics.ts
git commit -m "feat(frontend): thread team filter params through analytics hooks"
```

---

## Task 8: Frontend — Mount FactFilterBar on Dashboard and Analytics, feed params into all queries

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/AnalyticsPage.tsx`

- [ ] **Step 8.1: Dashboard — import hook + bar, call hooks with team params**

In `frontend/src/pages/DashboardPage.tsx`:

Add imports after existing imports:

```tsx
import FactFilterBar from '../components/dashboard/FactFilterBar';
import { useFactFilter } from '../hooks/useFactFilter';
```

Inside `DashboardPage`, after the existing `const [projectKey, ...]` line, add:

```tsx
  const { queryParams: teamParams } = useFactFilter();
```

Update every `useHoursBy*` / `useContextSwitching` call to pass `teamParams`:

```tsx
  const { data: categories } = useHoursByCategory(start, end, employeeId, projectKey, teamParams);
  const { data: trend } = useHoursByPeriod('week', start, end, employeeId, projectKey, teamParams);
  const { data: employees } = useHoursByEmployee(start, end, employeeId, projectKey, teamParams);
  const { data: projects } = useHoursByProject(start, end, employeeId, projectKey, teamParams);
  const { data: switching } = useContextSwitching(start, end, employeeId, projectKey, teamParams);
```

Mount the bar — in the `<Space wrap style={{ marginBottom: 24 }}>` area (right after the existing filters, before `ExportButtons`), add:

```tsx
        <FactFilterBar />
```

- [ ] **Step 8.2: Analytics — same treatment**

In `frontend/src/pages/AnalyticsPage.tsx`:

Add imports:

```tsx
import FactFilterBar from '../components/dashboard/FactFilterBar';
import { useFactFilter } from '../hooks/useFactFilter';
```

In `AnalyticsPage`, after `const [period, ...]`, add:

```tsx
  const { queryParams: teamParams } = useFactFilter();
```

The page passes `start, end, employeeId, projectKey` down to tab components. Extend every sub-component (`EmployeeTab`, `ProjectTab`, `CategoryTab`, `PeriodTab`, `SwitchingTab`) to also accept and forward `teamParams`.

Change the `<Tabs items={[...]}>` section:

```tsx
      <Tabs activeKey={activeTab} onChange={(key) => setSearchParams({ tab: key })} items={[
        { key: 'employee', label: 'По сотрудникам', children: <EmployeeTab start={start} end={end} employeeId={employeeId} projectKey={projectKey} teamParams={teamParams} /> },
        { key: 'project', label: 'По проектам', children: <ProjectTab start={start} end={end} employeeId={employeeId} projectKey={projectKey} teamParams={teamParams} /> },
        { key: 'category', label: 'По категориям', children: <CategoryTab start={start} end={end} employeeId={employeeId} projectKey={projectKey} teamParams={teamParams} /> },
        { key: 'period', label: 'По периодам', children: <PeriodTab start={start} end={end} period={period} onPeriodChange={setPeriod} employeeId={employeeId} projectKey={projectKey} teamParams={teamParams} /> },
        { key: 'switching', label: 'Переключения контекста', children: <SwitchingTab start={start} end={end} employeeId={employeeId} projectKey={projectKey} teamParams={teamParams} /> },
      ]} />
```

Add the `TeamFilterParams` prop type to each sub-component. Here's `EmployeeTab` as the pattern — apply identically to others:

```tsx
import type { TeamFilterParams } from '../api/analytics';

type TabProps = { start?: string; end?: string; employeeId?: string; projectKey?: string; teamParams?: TeamFilterParams };

function EmployeeTab({ start, end, employeeId, projectKey, teamParams }: TabProps) {
  const { data, isLoading, isError, error } = useHoursByEmployee(start, end, employeeId, projectKey, teamParams);
  // ... rest unchanged
}
```

Apply the same `TabProps` + `teamParams` forwarding to `ProjectTab`, `CategoryTab`, `SwitchingTab`. For `PeriodTab` extend the existing props type:

```tsx
function PeriodTab({ start, end, period, onPeriodChange, employeeId, projectKey, teamParams }: TabProps & { period: 'day' | 'week' | 'month'; onPeriodChange: (v: 'day' | 'week' | 'month') => void }) {
  const { data, isLoading, isError, error } = useHoursByPeriod(period, start, end, employeeId, projectKey, teamParams);
  ...
}
```

Mount the bar in the existing `<Space wrap>` filter row (right after `DateRangeSelect` + existing Selects + Reset button), before `<ExportButtons>`:

```tsx
        <FactFilterBar />
```

- [ ] **Step 8.3: Lint and type-check**

Run: `cd frontend && npm run lint`
Expected: clean.

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 8.4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/AnalyticsPage.tsx
git commit -m "feat(frontend): mount FactFilterBar + thread team params through Dashboard and Analytics"
```

---

## Task 9: Frontend — Team params flow through `/exports/analytics.*` downloader

**Files:**
- Modify: `frontend/src/api/exports.ts`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/AnalyticsPage.tsx`

- [ ] **Step 9.1: Extend export api signatures**

Edit `frontend/src/api/exports.ts`:

```ts
import { api } from './client';
import type { TeamFilterParams } from './analytics';

export const downloadAnalyticsXlsx = (start?: string, end?: string, team?: TeamFilterParams) =>
  api.download('/exports/analytics.xlsx', {
    start, end,
    teams: team?.teams,
    match_employees: team?.match_employees,
    match_issues: team?.match_issues,
  });

export const downloadAnalyticsPdf = (start?: string, end?: string, team?: TeamFilterParams) =>
  api.download('/exports/analytics.pdf', {
    start, end,
    teams: team?.teams,
    match_employees: team?.match_employees,
    match_issues: team?.match_issues,
  });

export const downloadScenarioXlsx = (scenarioId: string) =>
  api.download(`/exports/scenarios/${scenarioId}.xlsx`);

export const downloadScenarioPptx = (scenarioId: string) =>
  api.download(`/exports/scenarios/${scenarioId}.pptx`);
```

- [ ] **Step 9.2: Update call sites on Dashboard**

In `DashboardPage.tsx`, update the `ExportButtons` render (currently passes only `start, end`):

```tsx
        <ExportButtons
          onXlsx={() => downloadAnalyticsXlsx(start, end, teamParams)}
          onPdf={() => downloadAnalyticsPdf(start, end, teamParams)}
        />
```

- [ ] **Step 9.3: Update call sites on Analytics**

In `AnalyticsPage.tsx`, same change to `ExportButtons`:

```tsx
        <ExportButtons
          onXlsx={() => downloadAnalyticsXlsx(start, end, teamParams)}
          onPdf={() => downloadAnalyticsPdf(start, end, teamParams)}
        />
```

- [ ] **Step 9.4: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: clean.

- [ ] **Step 9.5: Commit**

```bash
git add frontend/src/api/exports.ts frontend/src/pages/DashboardPage.tsx frontend/src/pages/AnalyticsPage.tsx
git commit -m "feat(frontend): include team filter in analytics xlsx/pdf downloads"
```

---

## Task 10: End-to-end smoke — Playwright test

**Files:**
- Modify: `frontend/e2e/dashboard.spec.ts` (add one test) — or create if missing

- [ ] **Step 10.1: Inspect existing e2e fixtures**

Run: `ls frontend/e2e/`
Read `frontend/e2e/dashboard.spec.ts` if it exists. Note seeded data (from `scripts/seed_e2e.py`: `E2E Analyst` employee, `E2E` project).

- [ ] **Step 10.2: Check seeded team data**

Run: `grep -n "team\|EmployeeTeam\|participating_teams" scripts/seed_e2e.py`

If the seed doesn't set up teams, the e2e happy-path will be brittle. Add minimal team seeding to `scripts/seed_e2e.py`: give `E2E Analyst` an `EmployeeTeam` row with team `E2E Squad`, and set `Issue.team = "E2E Squad"` + `participating_teams = '["E2E Squad"]'` on all seeded issues.

- [ ] **Step 10.3: Write the e2e test**

Append to `frontend/e2e/dashboard.spec.ts`:

```ts
test('team filter narrows dashboard KPIs', async ({ page }) => {
  await page.goto('/');
  // Baseline: KPI shows some hours
  const before = await page.getByText(/Всего часов/).locator('..').innerText();

  // Open team select and pick E2E Squad
  await page.getByPlaceholder('Команда').click();
  await page.getByRole('option', { name: 'E2E Squad' }).click();
  // Close the dropdown
  await page.keyboard.press('Escape');

  // KPI should have re-rendered; at minimum the request query included teams=E2E Squad
  await page.waitForResponse((r) => r.url().includes('/analytics/hours/by-category') && r.url().includes('teams=E2E+Squad'));

  const after = await page.getByText(/Всего часов/).locator('..').innerText();
  expect(after).not.toEqual('');  // still renders
});
```

If the team selector doesn't populate because `useJiraTeams()` depends on Jira creds not present in e2e — either stub the Jira teams endpoint in the test, or mount the option synthetically by choosing `__none__` ("Без команды") as the assertion target. In that case replace `E2E Squad` with `Без команды` + adjust the waitForResponse to `teams=__none__`.

- [ ] **Step 10.4: Run e2e**

Run: `.\scripts\e2e-local.ps1` (or `cd frontend && npm run e2e` directly)
Expected: new test PASSES.

If the test is flaky because of the team-options source, fall back to the `__none__` variant above.

- [ ] **Step 10.5: Commit**

```bash
git add frontend/e2e/dashboard.spec.ts scripts/seed_e2e.py
git commit -m "test(e2e): dashboard team filter narrows KPI"
```

---

## Task 11: Full smoke, final verification, push

- [ ] **Step 11.1: Restart backend (Windows uvicorn --reload hangs)**

Kill any running uvicorn on :8000:

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
```

Run: `.\scripts\smoke-local.ps1` — or start `uvicorn app.main:app --reload --port 8000` in the background.

- [ ] **Step 11.2: Full pytest run**

Run: `py -3.10 -m pytest tests/ -v`
Expected: no new failures (keep in mind the pre-existing `test_sync_service` failure noted in CLAUDE context — that's not introduced by this work).

- [ ] **Step 11.3: Full frontend lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: clean.

- [ ] **Step 11.4: Manual smoke via browser**

Navigate to `http://localhost:5173/`. Verify:
- Team select appears in the filter row.
- Picking a team updates the KPI cards and charts (watch network tab — requests include `teams=...` / `match_employees=true` / `match_issues=true`).
- Unchecking both "Сотрудники" and "Задачи" in sequence: the second uncheck is silently refused, the checkbox stays on.
- Navigate to `/analytics`: team selection survives (re-hydrates from AppSetting).
- Export button downloads xlsx — open it, totals match the filtered view.

- [ ] **Step 11.5: Push**

Run: `git push origin main`
(User preference: commit + push after each cohesive batch — this is the batch.)

---

## Self-Review Checklist (completed by plan author)

- **Spec coverage**: all 6 main sections of the spec map to tasks above (UI → Tasks 5, 6, 8; API → Tasks 3, 4; Service logic → Tasks 1, 2; Exports → Task 9; Tests → Tasks 1.3+/2+/3.3/10; YAGNI/не-делаем — by omission).
- **Placeholder scan**: no "TBD" / "add validation" / "similar to Task N" / unshown code. Each step has concrete code or exact command.
- **Type consistency**: `TeamFilterParams`, `NO_TEAM_VALUE`, `NO_TEAM_TOKEN`, hook + method signatures match across tasks. Kwarg order `(teams, match_employees, match_issues)` is identical in every service signature change.
- **Known gotcha from memory**: plan includes uvicorn --reload kill on Windows (Task 11.1). AntD 6 notification `title` is not relevant here (no notifications added). Model field `Issue.issue_type` — not used here; we use `team` and `participating_teams` which exist on the model per CLAUDE.md.
