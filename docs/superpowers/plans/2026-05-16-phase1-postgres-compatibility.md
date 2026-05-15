# Phase 1 — Postgres Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the backend (ORM, migrations, tests) verifiably work against PostgreSQL 16, in addition to SQLite, so that the eventual server cutover does not surface vendor-specific bugs.

**Architecture:** Keep SQLite as the default for local development speed. Add a second CI job that runs the full test suite against a real Postgres service container. Make `tests/conftest.py` honor a `TEST_DATABASE_URL` env var so the same suite runs on both backends. Provide a one-command local Docker recipe so the operator can reproduce CI failures locally. Fix any code/migration that breaks under Postgres along the way.

**Tech Stack:** Python 3.10, SQLAlchemy 2.0, Alembic, pytest, PostgreSQL 16, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-05-16-server-deployment-design.md` §11.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tests/conftest.py` | Modify | Read `TEST_DATABASE_URL` env var; pick SQLite-specific options only when URL is SQLite. |
| `tests/CLAUDE.md` | Modify | Document local Postgres testing recipe. |
| `docker-compose.test.yml` | Create | One-command local Postgres for test runs. |
| `.github/workflows/ci.yml` | Modify | Add `test-backend-postgres` job alongside existing `test-backend` job. |
| `scripts/run_tests_postgres.ps1` | Create | Windows convenience wrapper that starts the Postgres container, exports `TEST_DATABASE_URL`, runs pytest, tears down. |
| `scripts/run_tests_postgres.sh` | Create | Same wrapper for bash. |
| `app/models/*.py` | Modify (as needed) | Fix any column-type / default issue that breaks on Postgres. Unknown set — enumerated only after first PG test run. |
| `alembic/versions/*.py` | Modify (as needed) | Same — only files that fail. |

No new application code is created in Phase 1. All changes are test-infrastructure + reactive fixes.

---

### Task 1: Make conftest.py honor `TEST_DATABASE_URL`

**Files:**
- Modify: `tests/conftest.py:63-83`

**Why:** Current code hard-codes `sqlite:///:memory:`. We need the same suite to run against a real Postgres URL when provided.

- [ ] **Step 1: Read current `engine` fixture**

Already in context. The fixture at lines 63-83 creates an SQLite `:memory:` engine and applies `connect_args={"check_same_thread": False}`. We will:
- Read URL from `os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")`.
- Only apply `check_same_thread` connect_arg when URL is SQLite.
- Keep `StaticPool` for SQLite `:memory:` only (Postgres has its own pool).

- [ ] **Step 2: Write the failing test**

Create `tests/test_postgres_compat.py`:

```python
"""Test that conftest engine respects TEST_DATABASE_URL."""
import os
from sqlalchemy.engine import make_url


def test_engine_uses_test_database_url(monkeypatch, request):
    """The session-scoped engine fixture must read TEST_DATABASE_URL."""
    # Engine fixture is already created at session scope, so we test the
    # helper logic by importing it directly.
    from tests.conftest import _resolve_test_database_url
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://user:pw@localhost/db")
    assert _resolve_test_database_url() == "postgresql://user:pw@localhost/db"


def test_engine_defaults_to_sqlite_memory(monkeypatch):
    from tests.conftest import _resolve_test_database_url
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert _resolve_test_database_url() == "sqlite:///:memory:"
```

- [ ] **Step 3: Run the failing test**

Run: `py -3.10 -m pytest tests/test_postgres_compat.py -v`
Expected: `ImportError: cannot import name '_resolve_test_database_url'` or similar.

- [ ] **Step 4: Implement the helper and rewire fixtures**

Replace lines 63-83 of `tests/conftest.py` with:

```python
def _resolve_test_database_url() -> str:
    """Return the database URL for tests.

    Reads TEST_DATABASE_URL (CI sets it to a Postgres URL); falls back to
    SQLite :memory: for fast local runs.
    """
    return os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


def _is_sqlite(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


@pytest.fixture(scope="session")
def test_settings():
    """Test settings; database URL comes from env."""
    return Settings(
        database_url=_resolve_test_database_url(),
        debug=True,
        log_level="DEBUG",
    )


@pytest.fixture(scope="session")
def engine(test_settings):
    """Create test database engine.

    For SQLite we share a single in-memory connection via StaticPool so
    concurrent test threads see the same schema. For Postgres we rely on
    the default pool but ensure each session starts with a clean schema.
    """
    url = test_settings.database_url
    kwargs: dict = {}
    if _is_sqlite(url):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    # Drop first so reruns against a persistent Postgres start clean.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
```

Also add the import at top of file:
```python
from sqlalchemy.engine import make_url
```

(`StaticPool` already imported.)

- [ ] **Step 5: Run the new tests and verify pass**

Run: `py -3.10 -m pytest tests/test_postgres_compat.py -v`
Expected: 2 passed.

- [ ] **Step 6: Run the full suite on SQLite to verify no regression**

Run: `py -3.10 -m pytest tests/ -q`
Expected: same pass/fail counts as before this task (pre-existing failures are tracked elsewhere).

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/test_postgres_compat.py
git commit -m "test: allow TEST_DATABASE_URL to override test backend"
```

---

### Task 2: Local Postgres docker-compose for tests

**Files:**
- Create: `docker-compose.test.yml`

**Why:** Single command to start the same Postgres image CI uses.

- [ ] **Step 1: Create `docker-compose.test.yml` at repo root**

```yaml
services:
  postgres-test:
    image: postgres:16-alpine
    container_name: jira-analytics-test-pg
    environment:
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
      POSTGRES_DB: jira_analytics_test
    ports:
      - "55432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d jira_analytics_test"]
      interval: 2s
      timeout: 5s
      retries: 30
    tmpfs:
      - /var/lib/postgresql/data
```

Notes:
- Port `55432` to avoid colliding with a host Postgres if one exists.
- `tmpfs` storage = ephemeral, fast, no cleanup needed.
- Healthcheck so dependent steps wait properly.

- [ ] **Step 2: Verify it starts**

Run: `docker compose -f docker-compose.test.yml up -d`
Wait until healthy: `docker compose -f docker-compose.test.yml ps`
Expected: `jira-analytics-test-pg` status `(healthy)`.

- [ ] **Step 3: Verify it accepts connections**

Run: `docker exec jira-analytics-test-pg pg_isready -U test`
Expected: `accepting connections`.

- [ ] **Step 4: Tear down**

Run: `docker compose -f docker-compose.test.yml down`

- [ ] **Step 5: Commit**

```bash
git add docker-compose.test.yml
git commit -m "build: docker-compose for local Postgres testing"
```

---

### Task 3: Convenience scripts (PowerShell + Bash)

**Files:**
- Create: `scripts/run_tests_postgres.ps1`
- Create: `scripts/run_tests_postgres.sh`

**Why:** Operator runs Windows + PowerShell; CI runs Linux + Bash. Both wrappers do the same thing: start container, wait healthy, run pytest, stop container.

- [ ] **Step 1: Create `scripts/run_tests_postgres.ps1`**

```powershell
#!/usr/bin/env pwsh
# Run the backend test suite against a local Postgres container.
$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot ".." "docker-compose.test.yml"

docker compose -f $composeFile up -d
try {
    # Wait for healthcheck
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $status = docker inspect -f '{{.State.Health.Status}}' jira-analytics-test-pg 2>$null
        if ($status -eq "healthy") { break }
        Start-Sleep -Seconds 1
    }
    if ($status -ne "healthy") {
        throw "Postgres test container did not become healthy"
    }

    $env:TEST_DATABASE_URL = "postgresql://test:test@localhost:55432/jira_analytics_test"
    py -3.10 -m pytest tests/ -q
    $exitCode = $LASTEXITCODE
}
finally {
    docker compose -f $composeFile down
}
exit $exitCode
```

- [ ] **Step 2: Create `scripts/run_tests_postgres.sh`**

```bash
#!/usr/bin/env bash
# Run the backend test suite against a local Postgres container.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose_file="$script_dir/../docker-compose.test.yml"

docker compose -f "$compose_file" up -d

cleanup() {
    docker compose -f "$compose_file" down
}
trap cleanup EXIT

# Wait for healthcheck
for _ in $(seq 1 60); do
    status=$(docker inspect -f '{{.State.Health.Status}}' jira-analytics-test-pg 2>/dev/null || echo "starting")
    if [ "$status" = "healthy" ]; then break; fi
    sleep 1
done
if [ "$status" != "healthy" ]; then
    echo "Postgres test container did not become healthy" >&2
    exit 1
fi

export TEST_DATABASE_URL="postgresql://test:test@localhost:55432/jira_analytics_test"
python -m pytest tests/ -q
```

Make executable bit explicit via Git later (`git update-index --chmod=+x` if needed on Linux side).

- [ ] **Step 3: Smoke-run the PowerShell wrapper**

Run: `.\scripts\run_tests_postgres.ps1`
Expected: pytest output starts; the run will probably surface failures that Phase 1 Task 5 will fix. **For this step, just verify the wrapper itself works** (container starts, env var passed, pytest launches, container torn down on exit). Pass/fail of tests at this point is informational.

If the wrapper itself fails (container won't start, env var not propagated): fix the wrapper before continuing.

- [ ] **Step 4: Add `psycopg2-binary` to requirements**

Postgres driver is not yet in `requirements.txt`. Add at the bottom of the Database block (after `alembic>=1.13.0`):

```
psycopg2-binary>=2.9,<3.0
```

Run: `pip install -r requirements.txt`
Expected: psycopg2-binary installed.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_tests_postgres.ps1 scripts/run_tests_postgres.sh requirements.txt
git commit -m "test: scripts to run pytest against local Postgres"
```

---

### Task 4: Add Postgres CI matrix job

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add new job after `test-backend`**

Insert this job block after the `test-backend` job (before `lint-build`):

```yaml
  test-backend-postgres:
    needs: changes
    if: needs.changes.outputs.backend == 'true' || needs.changes.outputs.workflow == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: jira_analytics_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql://test:test@localhost:5432/jira_analytics_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -q
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: no exception.

- [ ] **Step 3: Commit and push to a feature branch (not main yet)**

```bash
git checkout -b feature/phase1-postgres-ci
git add .github/workflows/ci.yml
git commit -m "ci: add Postgres test matrix"
git push -u origin feature/phase1-postgres-ci
```

- [ ] **Step 4: Wait for CI run**

GitHub UI: navigate to Actions tab, open the run for branch `feature/phase1-postgres-ci`.

Expected: `test-backend` passes (SQLite), `test-backend-postgres` likely **fails** with one or more issues. **Capture the failure list** — input to Task 5.

If `test-backend-postgres` happens to pass on first try (best case): skip Task 5, jump to Task 6.

---

### Task 5: Fix Postgres-specific failures (iterative)

**Files:** depends on what fails. Likely candidates based on code audit:
- `app/models/issue.py` — `participating_teams` is `Text` holding JSON; should still work but verify.
- `app/services/capacity_service.py:435` — `extract("month", Worklog.started_at)` works on both backends via SQLAlchemy.
- Any place that uses raw string SQL via `text(...)` — none found in current audit; verify.
- Any migration that uses `op.batch_alter_table` — only required for SQLite; the same code is no-op on Postgres because batch mode is transparent.

**Strategy:** Each distinct failure becomes a sub-task. Fix, run, commit, repeat. Sub-tasks below are templates — adapt to actual failures.

- [ ] **Step 1: List failures**

From the CI output of Task 4 Step 4, copy the test failure summary into a working notes file (`/tmp/pg-failures.txt` or just a scratch buffer). Group by root cause, not by individual test name — one root cause may break many tests.

- [ ] **Step 2: For each root cause, repeat the TDD loop**

Template for one fix cycle:

  - [ ] **Sub-step a: Reproduce locally**

  Run `.\scripts\run_tests_postgres.ps1 -- -k <failing_test_name> -v` (or the bash equivalent).
  Expected: same failure as in CI.

  - [ ] **Sub-step b: Read the error and identify root cause**

  Typical Postgres-vs-SQLite differences to look for:
  - **Boolean coercion**: SQLite stores booleans as 0/1; Postgres requires `True`/`False`. SQLAlchemy handles this if columns are declared `Boolean()` — but watch for `String` columns holding `"true"`/`"false"`.
  - **Default values**: `server_default="[]"` works on both; `server_default=0` for a Boolean column fails on Postgres.
  - **Case sensitivity**: SQLite `LIKE` is case-insensitive by default; Postgres `LIKE` is case-sensitive. Code already uses `ilike` where needed.
  - **NULL ordering**: Postgres puts NULL last in ASC by default, SQLite puts NULL first. Tests asserting order on nullable columns may fail.
  - **UNIQUE constraint partial indexes**: SQLite doesn't support partial unique indexes; the project enforces "one primary per employee" in `EmployeeTeamService` rather than the DB. Should not break.
  - **Reserved words**: `user`, `order`, `group` etc. need quoting in Postgres. SQLAlchemy quotes automatically if column/table names match.

  - [ ] **Sub-step c: Write or adjust a test that pins the expected behavior**

  If the failing test is correct and the code is wrong: keep the test, fix code.
  If the failing test was relying on SQLite-specific behavior: rewrite test to be backend-agnostic.

  - [ ] **Sub-step d: Make the fix**

  Edit the model / service / migration to be portable. Show the diff in your commit.

  - [ ] **Sub-step e: Verify both backends pass**

  Run on Postgres: `.\scripts\run_tests_postgres.ps1`
  Run on SQLite: `py -3.10 -m pytest tests/ -q`
  Expected: same test passes on both, no new regressions.

  - [ ] **Sub-step f: Commit**

  ```bash
  git add <files>
  git commit -m "fix(<area>): <root cause> compat with Postgres"
  ```

- [ ] **Step 3: When zero Postgres failures remain, push and confirm CI green**

```bash
git push
```

Open the latest run for the branch in GitHub Actions. Both `test-backend` and `test-backend-postgres` jobs must pass.

If the Postgres test job exposes pre-existing SQLite-only failures (e.g. `test_sync_service` per project memory): leave them. They're tracked separately and out of Phase 1 scope.

---

### Task 6: Verify Alembic migrations apply to a fresh Postgres

**Files:** read-only inspection of `alembic/versions/*.py` + run `alembic upgrade head` against a fresh container.

**Why:** Tests run against `Base.metadata.create_all`, not against the migration chain. We need separate confirmation that the migration chain itself works on Postgres — Phase 4 (data migration) and §6.3 prod deploys depend on this.

- [ ] **Step 1: Start a clean Postgres**

Run: `docker compose -f docker-compose.test.yml up -d`
Wait healthy.

- [ ] **Step 2: Run upgrade head**

In PowerShell:

```powershell
$env:DATABASE_URL = "postgresql://test:test@localhost:55432/jira_analytics_test"
py -3.10 -m alembic upgrade head
```

Expected: each revision applies; final line `INFO ... Running upgrade ... -> <head>` for the latest revision.

- [ ] **Step 3: If a migration fails, fix the migration**

Common Alembic-Postgres pitfalls:
- `op.batch_alter_table` with mode `recreate=always` on tables that have data — Postgres can do ALTER COLUMN directly. Refactor to a plain `op.alter_column` guarded by dialect detection if needed.
- `sa.Boolean()` server_default `"0"` or `"1"` — Postgres needs `sa.text("false")` / `sa.text("true")`.
- `op.create_index` with `if_not_exists=True` — supported in newer Alembic; verify version.

For each failing migration:
- Read the migration file.
- Identify the offending statement.
- Patch the migration so it is portable (use `op.get_bind().dialect.name` for branching only when truly necessary).
- Drop the database, re-run `upgrade head` from scratch:

  ```powershell
  docker compose -f docker-compose.test.yml down
  docker compose -f docker-compose.test.yml up -d
  py -3.10 -m alembic upgrade head
  ```

Commit one fix per migration:

```bash
git add alembic/versions/<file>.py
git commit -m "fix(migration): make <revision> Postgres-compatible"
```

- [ ] **Step 4: Tear down**

```powershell
docker compose -f docker-compose.test.yml down
Remove-Item Env:DATABASE_URL
```

- [ ] **Step 5: Verify downgrade chain still works on SQLite**

```powershell
$env:DATABASE_URL = "sqlite:///./data/migration-test.db"
py -3.10 -m alembic upgrade head
py -3.10 -m alembic downgrade base
Remove-Item ./data/migration-test.db
Remove-Item Env:DATABASE_URL
```

Expected: clean run both ways. (Some legacy migrations may have empty `downgrade()` — note them but don't fix unless they fail.)

---

### Task 7: Document local Postgres testing in tests/CLAUDE.md

**Files:**
- Modify: `tests/CLAUDE.md`

- [ ] **Step 1: Add a new section after the existing "Команды" section**

Append:

```markdown
## Прогон против Postgres локально

CI гоняет тесты дважды: SQLite (быстро) и Postgres 16 (проверка совместимости). Локально по умолчанию используется SQLite. Если нужно воспроизвести Postgres-фейл с CI:

```powershell
# Windows
.\scripts\run_tests_postgres.ps1
```

```bash
# Linux / WSL
./scripts/run_tests_postgres.sh
```

Скрипт поднимает Postgres 16 в Docker (`docker-compose.test.yml`), экспортирует `TEST_DATABASE_URL`, гоняет pytest, останавливает контейнер.

Один тест против Postgres:

```powershell
docker compose -f docker-compose.test.yml up -d
$env:TEST_DATABASE_URL = "postgresql://test:test@localhost:55432/jira_analytics_test"
py -3.10 -m pytest tests/test_capacity_service.py -v
docker compose -f docker-compose.test.yml down
```
```

- [ ] **Step 2: Commit**

```bash
git add tests/CLAUDE.md
git commit -m "docs(tests): local Postgres test recipe"
```

---

### Task 8: Open PR, get merge

- [ ] **Step 1: Open PR**

```bash
gh pr create --title "Phase 1: Postgres test matrix + ORM compat fixes" --body "$(cat <<'EOF'
## Summary
- Add `test-backend-postgres` CI job (Postgres 16 service container)
- Make `tests/conftest.py` honor `TEST_DATABASE_URL`
- Add `docker-compose.test.yml` + wrapper scripts for local Postgres runs
- Fix all ORM/migration issues surfaced by running the suite on Postgres

## Test plan
- [x] `test-backend` (SQLite) green
- [x] `test-backend-postgres` (Postgres 16) green
- [x] `alembic upgrade head` succeeds on a fresh Postgres
- [x] `alembic upgrade head` then `downgrade base` succeeds on SQLite

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Wait for CI to be all-green on the PR**

Expected: both pytest jobs pass, lint-build passes, e2e passes (or is skipped per existing rules).

- [ ] **Step 3: Merge to main**

User-driven decision — operator approves the merge.

---

## Out of scope for Phase 1

- Dockerfile / production compose — Phase 2.
- Release pipeline / GHCR / tags — Phase 3.
- Data migration script — Phase 4.
- Healthcheck endpoints / rate limit on login — Phase 4 (bundled with migration tooling because they ride into the same image).

---

## Self-Review Checklist (run before handing off)

1. **Spec coverage:** every item from spec §11 is covered:
   - §11.1 Postgres test matrix → Task 4.
   - §11.2 Local development recipe → Tasks 2, 3, 7.
   - §11.3 Pre-existing failures noted → Task 5 Step 3 says to leave them.
2. **Placeholder scan:** no TBD/TODO in steps. Task 5 is intentionally template-shaped because the exact failures are unknown until CI runs.
3. **Type consistency:** `_resolve_test_database_url`, `_is_sqlite`, `TEST_DATABASE_URL` used consistently throughout.
4. **All commands shown:** every step has an exact command and expected output.
