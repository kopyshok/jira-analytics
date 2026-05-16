# Data Migration Runbook — SQLite → PostgreSQL

**Date:** 2026-05-16
**Status:** Ready for cutover (Phase 6)
**Related:**
- Spec: `docs/superpowers/specs/2026-05-16-server-deployment-design.md` §7
- Script: `scripts/migrate_to_postgres.py`
- Sysadmin reference: `deploy/SYSADMIN.md`

## What this runbook covers

A one-shot copy of the operator's local SQLite database (`data/jira_analytics.db`) into the new server's PostgreSQL instance. After the copy, an incremental Jira sync brings the new DB up to current state.

## What is copied vs skipped

The script iterates `Base.metadata.sorted_tables` in FK-dependency order. **All tables are copied** except these defaults (caches / sync history that regenerate on the new server):

- `sync_state`
- `sync_run`
- `confluence_page_cache`
- `executive_dashboard_snapshots`

Issues and worklogs **are copied** (despite the spec's earlier suggestion to re-sync from Jira). Reason: re-syncing assigns new local UUIDs to all rows, which orphans every FK from `backlog_items.issue_id`, `comments.issue_id`, etc. Copying preserves UUIDs; the subsequent incremental sync upserts by `jira_issue_id` and keeps them stable.

Approximate dataset size (as of 2026-05-16): ~444k rows total, dominated by `category_mappings` (~239k), `issues` (~120k), `worklogs` (~79k).

## Prerequisites

On the server (sysadmin):

1. Postgres container running (`docker compose ps` in `/opt/jira-analytics/prod`).
2. Schema applied: `docker compose run --rm backend alembic upgrade head`.
3. Backend container can run Python scripts: `docker compose run --rm backend python --version`.

On the operator's workstation:

1. Stop the local backend (`uvicorn` on :8000) so the SQLite file is not being written to.
2. Optionally copy the live database to a snapshot path to be safe:
   ```powershell
   Copy-Item data\jira_analytics.db data\jira_analytics_cutover.db
   ```

## Cutover sequence

> Estimated duration: 60–90 minutes for 444k rows + incremental Jira sync.

| T (min) | Step | Who |
|---|---|---|
| 0 | Stop local backend; take SQLite snapshot | Operator |
| 0 | Verify snapshot integrity: `python -c "import sqlite3; c=sqlite3.connect('data/jira_analytics_cutover.db'); print(c.execute('select count(*) from issues').fetchone())"` | Operator |
| 5 | SCP snapshot to server: `scp data/jira_analytics_cutover.db sysadmin@host:/tmp/cutover.db` (or ask sysadmin to upload via internal file share) | Operator / sysadmin |
| 10 | Copy file into backend container working dir (or mount /tmp): place at `/app/data/cutover.db` (the `app-data-prod` volume) | Sysadmin |
| 15 | Dry-run from inside backend container: see §"Dry run" below | Sysadmin |
| 25 | Real run with `--force` (empty target): see §"Run" | Sysadmin |
| 45 | Bring backend up: `docker compose up -d backend` | Sysadmin |
| 50 | Operator logs in via UI, confirms users + scenarios are present | Operator |
| 55 | Trigger incremental Jira sync via `/sync` hub — picks up anything that changed in Jira since the snapshot | Operator |
| 80 | Spot-check: dashboard, one project page, one approved scenario | Operator |
| 90 | Open access to the rest of the team | Operator |

If anything fails before the team is notified, the local SQLite file is untouched and local development can resume immediately.

## Dry run

Always run a dry-run first to confirm table counts:

```bash
docker compose run --rm backend \
    python scripts/migrate_to_postgres.py \
    --source /app/data/cutover.db \
    --target "$DATABASE_URL" \
    --dry-run
```

Expected output: ~50 tables listed with row counts, total ~444k.
If a critical table shows 0 rows in source — stop and investigate before proceeding.

## Run

```bash
docker compose run --rm backend \
    python scripts/migrate_to_postgres.py \
    --source /app/data/cutover.db \
    --target "$DATABASE_URL" \
    --force
```

`--force` truncates target tables first (they should already be empty on a fresh deploy, but `--force` is a no-op in that case).

Successful run ends with:

```
Summary:
  Table                                              Source     Copied
  ...
  TOTAL                                              444544     444544
```

Any line ending with `MISMATCH` or `FAIL` means a table did not copy cleanly. Halt and contact the developer with the full output.

## After successful copy

1. **Bring backend up:** `docker compose up -d backend`. Healthcheck (`/health/ready`) should turn green within 60–90 s.

2. **Operator login check** — verify the admin account in the SQLite snapshot works against the new Postgres. If not, run `python scripts/create_admin.py` inside the container with `ADMIN_EMAIL`/`ADMIN_PASSWORD` env vars (these stay valid even when other accounts copied across).

3. **Incremental Jira sync** — from the UI go to `/sync` and run the standard sync. The script copies everything as of the snapshot timestamp; this catches up to *now*. Duration: ~5–15 min depending on activity.

4. **Remove the snapshot** from the server:
   ```bash
   docker compose exec backend rm /app/data/cutover.db
   ```

## Failure modes and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `alembic revision mismatch` | Target schema not at HEAD | `docker compose run --rm backend alembic upgrade head` |
| `target tables not empty` | Previous attempt left data | Re-run with `--force`, or `docker compose down -v` to drop the volume entirely then re-init |
| `MISMATCH` on one table | Source had rows but inserts failed (FK constraint?) | Run `--only <tablename>` to retry; inspect the error message |
| `psycopg2 OperationalError: too many parameters` | A single batch exceeded Postgres's 65535 param limit | Reduce `--batch-size` (default 1000) |
| Connection drop mid-copy | Network blip | The script is restart-safe with `--force` (truncates then re-copies). For partial recovery, use `--only` |

## Rollback

The local SQLite file is never modified. To roll back the cutover:

1. Stop the prod stack: `docker compose down`
2. Ask the sysadmin to restore the VM snapshot taken before the deployment, or `docker compose down -v` to wipe Postgres volumes.
3. Operator resumes local development as before.

## Verification spot-checks

After the copy, confirm a few high-value rows exist in Postgres:

```bash
docker compose exec postgres psql -U app -d jira_analytics_prod -c "
    select count(*) as users from users;
    select count(*) as approved_scenarios from planning_scenarios where status='approved';
    select count(*) as backlog from backlog_items where archived_at is null;
    select count(*) as issues from issues;
"
```

Counts should match the dry-run output (modulo whatever Jira changed during the cutover window).
