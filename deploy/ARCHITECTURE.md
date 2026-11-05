# Server Deployment & Release Pipeline Design

**Date:** 2026-05-16
**Status:** Draft — awaiting infra decisions from sysadmin (server class, TLS, network access)
**Scope:** Migration from local SQLite-based development setup to internal company server with PostgreSQL, Dockerized deployment, and versioned release pipeline.

---

## 1. Goals

1. Run JiraAnalysis on an internal company server, available to ~10-30 employees concurrently.
2. Switch persistent storage from SQLite (`data/jira_analytics.db`) to PostgreSQL.
3. Ship updates in **batches** (multiple fixes/features per release) instead of per-commit deploys.
4. Migrate existing local database content without forcing a full from-scratch reconfiguration.
5. Make releases reproducible via Docker images built in CI.

## 2. Non-Goals

- High availability / horizontal scaling (single backend replica is the explicit target — see §5.2).
- Zero-downtime deploys (a maintenance window per release is acceptable).
- Multi-region / geo-distribution.
- Kubernetes or managed PaaS — explicitly out of scope; deployment is `docker compose` on a single host.

## 3. Open Questions (require sysadmin input before implementation)

These items block parts of the plan and must be resolved before deployment:

1. **Server class** — VM or bare metal? CPU/RAM/disk specs?
   - Recommended floor: 4 vCPU / 16 GB RAM / 100 GB SSD.
2. **TLS termination** — corporate CA-issued certificate? External load balancer terminating TLS? Or Caddy + Let's Encrypt (requires outbound internet)?
3. **Reverse proxy choice** — Caddy / nginx / already present on a corporate balancer?
4. **Internal domain** — what hostname routes to the server (e.g. `jira-analytics.company.local`)?
5. **Outbound internet access from server** — required for: GHCR (image pull), Jira Cloud (sync), LLM APIs (Gemini, OpenRouter). HuggingFace not needed (model baked into image).
6. **VM snapshot policy** — frequency, retention, has restore been tested?
7. **Uptime monitoring** — internal tool available? Alert channel (Telegram/email)?
8. **Operator access** — ~~do I get sudo on the server?~~ **ANSWERED 2026-05-16: No operator SSH access. Sysadmin runs all docker commands.** Consequence: docker-compose files must be self-contained and correct; a sysadmin runbook (`deploy/SYSADMIN.md`) must cover every operation end-to-end.
9. **Firewall** — outbound ports open? Inbound: only 443?
10. **Corporate password manager** — somewhere to store a backup copy of `JWT_SECRET_KEY` and database password?

Defaults assumed below where a decision is not blocking; defaults are marked.

## 4. Decisions Recorded From Brainstorm

| # | Topic | Decision |
|---|-------|----------|
| 1 | Hosting class | Internal company server, exact class TBD |
| 2 | Release cadence | On-demand, SemVer |
| 3 | Initial data | Migrate operator's existing SQLite DB |
| 4 | Background tasks & SSE | Single backend replica, vertical scaling |
| 5 | Migration trigger | Manual `alembic upgrade head` before container swap |
| 6 | Image registry | GHCR (revisit later if needed) |
| 7 | Deployment trigger | Manual SSH from operator's machine |
| 8 | Staging | Second compose stack on the same server |
| 9 | Database backups | Sysadmin-managed VM snapshots |
| 10 | Secrets storage | `.env` file (chmod 600) + Jira credentials in `AppSetting` table |
| 11 | TLS / proxy | Deferred — sysadmin decides (§3) |
| 12 | Embedding model | Baked into Docker image |
| 13 | Frontend packaging | Multi-stage build, served from backend image |
| 14 | Test matrix | Pytest runs twice in CI — SQLite (fast) and Postgres (correctness) |
| 15 | Monitoring | Docker healthcheck + restart policy + external uptime monitor |
| 16 | Data migration | Hybrid: structure tables via script, facts via Jira re-sync |
| 17 | Rollback | Backward-compatible migrations + VM snapshot before each release |

## 5. Architecture

### 5.1 Topology

```
Internet / Internal network
      │
      ▼
┌─────────────────────────────────────────────┐
│  Server (single VM)                         │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │  Reverse proxy (TLS, static, /api)   │   │
│  └────────────┬─────────────────────────┘   │
│               │                             │
│        ┌──────┴──────┐                      │
│        ▼             ▼                      │
│  ┌──────────┐  ┌──────────┐                 │
│  │ backend  │  │ backend  │                 │
│  │ (prod)   │  │(staging) │                 │
│  └────┬─────┘  └────┬─────┘                 │
│       │             │                       │
│  ┌────▼──────┐  ┌───▼───────┐               │
│  │ postgres  │  │ postgres  │               │
│  │ (prod)    │  │ (staging) │               │
│  └───────────┘  └───────────┘               │
│                                             │
│  pgdata-prod, pgdata-staging, app-data-*    │
└─────────────────────────────────────────────┘
```

Single host. Prod and staging are two independent compose stacks (separate networks, volumes, ports).

### 5.2 Why one backend replica

- APScheduler runs in-process — multiple replicas would duplicate scheduled jobs.
- SSE `EventBroadcaster` keeps subscribers in memory — multiple replicas miss cross-replica events.
- Expected load (~30 users, mostly read-heavy) is well within a single FastAPI/asyncio process.

When the cap is reached, the refactor path is: external scheduler (Redis-locked) + Redis pub/sub for SSE + multi-replica backend. Out of current scope.

### 5.3 Container layout (per stack)

| Service | Image | Restart policy |
|---------|-------|----------------|
| `postgres` | `postgres:16-alpine` | `unless-stopped` |
| `backend` | `ghcr.io/<org>/jira-analytics:<tag>` | `unless-stopped` |
| `proxy` | Caddy or nginx (TBD per §3) | `unless-stopped` |

Volumes:
- `pgdata-<env>` → `/var/lib/postgresql/data`
- `app-data-<env>` → `/app/data` (file outputs, generated exports)
- `proxy-config-<env>` → proxy configuration

### 5.4 Docker image (multi-stage)

```
# Stage 1: frontend build
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build  # produces dist/

# Stage 2: python deps + embedding model
FROM python:3.10-slim AS python-builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('intfloat/multilingual-e5-base')"
# Model now cached at $HF_HOME (~/.cache layout under /opt/hf-cache)

# Stage 3: runtime
FROM python:3.10-slim AS runtime
WORKDIR /app
COPY --from=python-builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
COPY --from=python-builder /usr/local/bin /usr/local/bin
COPY --from=python-builder /opt/hf-cache /opt/hf-cache
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/
COPY --from=frontend-builder /build/dist ./app/static/
ENV HF_HOME=/opt/hf-cache
ENV TZ=Europe/Moscow
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health/ready || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Approximate image size: 2-2.5 GB (torch + embedding model dominate). Layer cache keeps incremental updates light: only the `app/`, `alembic/`, `scripts/`, and `app/static/` layers change between releases when dependencies are unchanged.

Embedding model is pre-cached during image build to `/opt/hf-cache` using HuggingFace's `HF_HOME` convention. The runtime container sets `HF_HOME=/opt/hf-cache`, and `app/services/llm/embedding_service.py` already reads `HF_HOME` via its `cache_folder` parameter — no code change required. First `SentenceTransformer(...)` call at runtime finds the cached snapshot and skips the network fetch.

## 6. Release Pipeline

### 6.1 Versioning

- SemVer: `vMAJOR.MINOR.PATCH`.
- Start at `v1.0.0` upon first production deployment.
- MAJOR: breaking API changes or migrations without downgrade.
- MINOR: backward-compatible features.
- PATCH: bug fixes.
- Conventional Commits (`feat:`, `fix:`, `chore:`) are already in use — keep them; they drive the changelog generator.

### 6.2 Release flow

1. Operator accumulates merged changes on `main` (already standard practice).
2. Locally run `make release VERSION=v1.2.3`:
   - Updates `app_version` in `app/config.py`.
   - Updates `version` in `frontend/package.json`.
   - Commits the version bump.
   - Creates annotated git tag `v1.2.3`.
   - Pushes commit and tag to `origin`.
3. GitHub Actions tag workflow:
   - Builds the Docker image.
   - Pushes to GHCR with tags `v1.2.3` and `latest`.
   - Generates changelog entry from Conventional Commits since previous tag (e.g. `git-cliff`).
   - Creates GitHub Release with the changelog.
4. Operator deploys (§6.3).

### 6.3 Deployment procedure (manual, per release)

Pre-deployment:
1. SSH to server.
2. Ask sysadmin to take a VM snapshot (or note that the most recent nightly snapshot is acceptable).
3. Pull new image into staging: `cd /opt/jira-analytics/staging && docker compose pull`.
4. Run migrations on staging: `docker compose run --rm backend alembic upgrade head`.
5. Restart staging: `docker compose up -d`.
6. Smoke-test staging via browser (login, dashboard, one scenario, one analytics page).

Production:
7. `cd /opt/jira-analytics/prod`.
8. Edit `.env` (or `docker-compose.yml`) to set image tag to `v1.2.3`.
9. `docker compose pull`.
10. `docker compose run --rm backend alembic upgrade head` — **manual gate** (see §6.4).
11. `docker compose up -d` — recreates `backend` with new image. Postgres and proxy stay running.
12. `curl https://<domain>/health/ready` — confirm 200.
13. Spot-check UI.

If anything fails: roll back per §6.5.

### 6.4 Migration safety rules

**All Alembic migrations must be backward-compatible** with the immediately previous version's code. This means:
- Adding a column: OK (old code ignores it).
- Adding a table: OK.
- Renaming a column: NOT in a single release. Two-step: add new column → release N copies into new column → release N+1 reads from new column → release N+2 drops old column.
- Dropping a column or table: only after the code that used it has been deployed and proven stable for at least one release.

This rule unlocks rollback (§6.5) and makes the "manual `alembic upgrade head` before `up -d`" gate safe — if the new code starts and fails, the old image still works against the new schema.

### 6.5 Rollback

If new image is broken:
1. Edit `.env` / `docker-compose.yml` to revert image tag to previous version.
2. `docker compose up -d`.
3. Old code runs against new (forward-compatible) schema. Works because of §6.4.
4. Fix forward in next patch release.

If a migration corrupted data:
1. Stop the prod stack.
2. Ask sysadmin to restore the VM snapshot taken before the release.
3. Confirm DB integrity post-restore.

`alembic downgrade` is not part of the standard rollback procedure — not all migrations have working downgrades, and forward-fixes are simpler.

### 6.6 CI changes

Current `.github/workflows/ci.yml` runs pytest (SQLite) + frontend build + Playwright on every push/PR. Additions:

1. **Postgres pytest matrix** — second pytest job that brings up `postgres:16-alpine` as a service and points `DATABASE_URL` at it. Runs on PRs and `main` pushes.
2. **Release workflow** (`release.yml`) — triggered on tag `v*`:
   - Build Docker image (`docker/build-push-action`).
   - Push to GHCR with `:vX.Y.Z` and `:latest`.
   - Generate changelog (`orhun/git-cliff-action` or similar).
   - Create GitHub Release.

## 7. Data Migration

### 7.1 Strategy

Hybrid: **structure tables** are copied from the local SQLite to the new Postgres instance via a Python script; **fact tables** (issues, worklogs, history) are populated by running a fresh full sync from Jira against the empty Postgres.

Rationale: fact tables are large (~115k issues, millions of worklogs) and already exist authoritatively in Jira. Structure tables encode user-curated data (categories, scenarios, rules, AI summaries) that cannot be reconstructed and is small enough to copy directly.

### 7.2 Tables to copy via script

Listed approximately in FK-dependency order. Final list verified against `app/models/` at implementation time.

**Tier 1 — no FK dependencies:**
- `users`, `user_rp_preferences`, `user_appearance_settings`
- `app_settings` (includes Jira credentials)
- `categories`
- `work_types`
- `roles`
- `production_calendar`
- `hierarchy_rules`

**Tier 2:**
- `employees`
- `employee_teams`
- `absences`
- `backlog_items` (including archived)
- `scenarios` (draft + approved)

**Tier 3:**
- `scenario_allocations`
- `scenario_team_rules`
- `scenario_revision_history`
- `scenario_norm_snapshot`, `scenario_absence_snapshot`, `scenario_capacity_drift_ack`
- `allocation_overrides`

**Tier 4:**
- `resource_plans`
- `resource_plan_assignments`
- `plan_item_dependencies`
- `plan_conflicts`
- `scheduled_blocks`
- `phase_predecessor`

**Tier 5 — caches (optional, but expensive to recompute):**
- `theme_embeddings`
- `theme_aliases`
- `project_ai_summary` (with `work_breakdown`)
- `confluence_page_cache`
- `executive_snapshot`

**Excluded** (recreated by Jira sync):
- `issues`, `worklogs`, `issue_history`, `issue_participating_teams`, `issue_goals`, `issue_status_changed_at`, custom field caches, sync state tables.

### 7.3 Migration script

`scripts/migrate_to_postgres.py`:

1. CLI: `python scripts/migrate_to_postgres.py --source <sqlite-path> --target <postgres-url> [--tables tier1,tier2,...] [--resume-from <table>]`.
2. Open two SQLAlchemy sessions (source bind = SQLite file, target bind = Postgres URL).
3. Pre-flight checks:
   - Target schema is at HEAD revision (`alembic current` matches `alembic heads`).
   - Target tables for the requested tiers are empty (or `--force` flag).
   - Source has all expected tables.
4. For each table, in dependency order:
   - Fetch all rows from source via ORM.
   - `bulk_insert_mappings` into target in batches of 1000.
   - Compare row counts; log mismatch as warning.
5. Verification phase:
   - Per-table count summary.
   - Spot-check a few high-value rows (one approved scenario, one user, one category).
6. Exit non-zero on any error so it can be rerun with `--resume-from`.

JSON columns: the script does not transform JSON values — SQLAlchemy's `JSON` type already roundtrips through both backends. If any model uses `Text` columns with manual `json.dumps` (audit during implementation), those columns are migrated as text and require no special handling.

Binary columns (`theme_embeddings.embedding` is `LargeBinary`): SQLAlchemy maps `bytes` ↔ `bytea` transparently.

### 7.4 Cutover plan

| T | Action | Duration |
|---|--------|----------|
| -1 day | Final dry-run of migration script against staging Postgres on the server | 1-2 h |
| 0:00 | Stop local backend; take a fresh copy of `data/jira_analytics.db` | 5 min |
| 0:05 | SCP SQLite file to server | 5-15 min depending on size |
| 0:20 | Run `migrate_to_postgres.py` against prod Postgres (empty schema, just `alembic upgrade head`) | 5-20 min |
| 0:40 | Trigger full Jira sync via the `/sync` hub | 15-30 min (current baseline ~11:30 per `project_full_sync_perf_shipped`) |
| 1:15 | Spot-check data, run admin smoke test (login, key pages) | 30 min |
| 1:45 | Operator switches over personal use to the server; share access with the team | — |

The original SQLite file stays untouched and serves as a fallback. If the server cutover fails, local development continues as-is until the issue is resolved.

### 7.5 Embedding recomputation

If `theme_embeddings` is migrated (Tier 5), it's reused directly. If skipped, the embedding service recomputes on demand — first user request per theme triggers ~50ms model inference; bulk pre-compute can run as a background job after cutover.

## 8. Environments

### 8.1 Layout

```
/opt/jira-analytics/
├── prod/
│   ├── docker-compose.yml
│   ├── .env             (chmod 600, owner: appuser)
│   └── proxy/
│       └── <proxy-config>
└── staging/
    ├── docker-compose.yml
    ├── .env             (chmod 600, owner: appuser)
    └── proxy/
        └── <proxy-config>
```

### 8.2 Isolation

- Separate Docker networks per stack (compose default — one network per project).
- Separate Postgres containers, separate databases (`jira_analytics_prod`, `jira_analytics_staging`), separate users.
- Separate volumes (`pgdata-prod`, `pgdata-staging`, etc).
- Different `JWT_SECRET_KEY` per environment — staging tokens never validate against prod.
- Different cookie scope (different hostnames or path).

### 8.3 Staging refresh

Once per week (or on demand):
1. `pg_dump` from prod Postgres container.
2. Drop and recreate staging database.
3. `pg_restore` into staging.
4. Optionally scrub staging — overwrite Jira credentials with a read-only token so staging cannot mutate Jira.

### 8.4 Resource budget (single 16 GB / 4 vCPU server)

| Service | RAM | CPU |
|---------|-----|-----|
| postgres-prod | 2-4 GB | 1 vCPU |
| backend-prod | 4-6 GB (embedding model + torch) | 2 vCPU |
| postgres-staging | 512 MB | shared |
| backend-staging | 2 GB | shared |
| proxy | 128 MB | shared |
| OS + headroom | 2 GB | — |

Tight but workable on 16 GB. Bump to 32 GB if the embedding pipeline grows.

## 9. Security

### 9.1 Secrets layout

Production `.env` keys:

```
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=postgresql://app:<password>@postgres:5432/jira_analytics_prod
CORS_ORIGINS=https://<prod-domain>
JWT_SECRET_KEY=<32 bytes hex, generated once, persisted forever>
JWT_EXPIRE_HOURS=8
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
GEMINI_API_KEY=<...>
OPENROUTER_API_KEY=<...>
ADMIN_EMAIL=<initial-admin>
ADMIN_PASSWORD=<temporary, cleared after first login>
TZ=Europe/Moscow
```

`JIRA_*` env vars are intentionally absent: Jira credentials live in the `app_settings` table and are migrated by the script in §7. The existing fallback chain in `app/config.py` (AppSetting → env) keeps working.

### 9.2 Secret rotation and backup

- `JWT_SECRET_KEY` is generated once with `python -c "import secrets; print(secrets.token_hex(32))"`. It is **not** rotated routinely — rotating invalidates all active sessions.
- Operator stores a backup of the secret locally (password manager) and in a second encrypted location (USB / corporate password manager if available — see Open Question #10).
- Postgres password is stored alongside `JWT_SECRET_KEY`.
- LLM API keys can be rotated as needed (zero-downtime: edit `.env`, `docker compose up -d backend`).

### 9.3 Admin bootstrap on a fresh server

1. After first `docker compose up -d` and successful migration:
   ```
   docker compose exec backend python scripts/create_admin.py
   ```
2. Script reads `ADMIN_EMAIL` / `ADMIN_PASSWORD` from env, inserts a User row with admin role.
3. Operator logs in via UI, changes the password.
4. Operator removes `ADMIN_PASSWORD` from `.env` and reloads (`docker compose up -d backend`).

### 9.4 Login rate limit

Add an in-process rate limiter on `POST /auth/login`: max 5 failed attempts per IP per 5 minutes, then 429 with `Retry-After`. Single-process — no Redis needed.

If/when the architecture moves to multiple replicas, this needs to move to Redis or a similar shared store.

### 9.5 Other hardening

- `AUTH_COOKIE_SECURE=true` (already enforced by `_enforce_jwt_secret` validator when `DEBUG=false`).
- `CORS_ORIGINS` limited to the single prod domain.
- Log scrubbing: confirm no middleware/dependency logs Authorization headers or cookie values. Audit during implementation.
- Postgres user `app` does not get superuser; migrations run as the same user (Alembic doesn't need superuser).

## 10. Operations

### 10.1 Logs

- All containers log to stdout/stderr.
- Docker `json-file` driver with `max-size=50m`, `max-file=5` per container.
- Log access during incident: `docker compose logs -f backend --tail=200`.
- No log files on disk inside the backend container.

### 10.2 Healthchecks

Two endpoints:
- `GET /health` — returns `{"status":"ok"}` without touching the database. Used by external uptime monitor.
- `GET /health/ready` — runs `SELECT 1` against the database. Used by Docker healthcheck (so the container is restarted if DB connectivity is lost).

### 10.3 Uptime monitor

Default: UptimeRobot free tier — 50 checks, 5-minute interval, email alerts.
If a corporate uptime tool is available (Open Question #7), use that.

### 10.4 Backups

Sysadmin operates VM snapshots. Recommended policy:
- Daily snapshot, 14-day retention.
- Tested restore at least once before production cutover.
- One extra snapshot manually triggered immediately before each release deploy.

### 10.5 Timezone

`TZ=Europe/Moscow` set in compose env for all services. Postgres `timezone='Europe/Moscow'`. Production calendar logic assumes Moscow time.

### 10.6 Database maintenance

- `pg_stat_statements` extension enabled at first deployment.
- Weekly informal review of top slow queries (manual, via `psql`).
- Autovacuum at Postgres defaults — revisit if bloat shows up.

## 11. Test strategy changes

### 11.1 Postgres test matrix

`.github/workflows/ci.yml` gains a second pytest job:

```yaml
postgres-pytest:
  services:
    postgres:
      image: postgres:16-alpine
      env: { POSTGRES_PASSWORD: test }
      ports: ['5432:5432']
      options: --health-cmd pg_isready
  env:
    DATABASE_URL: postgresql://postgres:test@localhost:5432/test_db
  steps:
    - alembic upgrade head
    - pytest tests/ -v
```

Runs on every PR and main push, alongside the existing SQLite-based job.

### 11.2 Local development

SQLite stays the local default for speed. Operator can opt into Postgres locally via Docker if debugging a Postgres-only issue:

```
docker run --rm -d --name pg-dev -e POSTGRES_PASSWORD=dev -p 5432:5432 postgres:16-alpine
DATABASE_URL=postgresql://postgres:dev@localhost:5432/postgres pytest tests/
```

### 11.3 Pre-existing test failures

Per the project memory notes, there is a pre-existing failure in `test_sync_service` and intermittent Playwright flakes. These are tracked separately and not blockers for this design, but the Postgres job will likely surface additional issues at first run — those become PR-sized fixes before the production cutover.

## 12. Implementation phases (high-level)

The detailed task breakdown belongs in the implementation plan, not this spec. High-level sequence:

1. **Phase 1 — Postgres compatibility.** Add Postgres job to CI, fix anything that breaks. Run locally against Postgres at least once end-to-end.
2. **Phase 2 — Dockerization.** Write `Dockerfile`, `docker-compose.yml` for prod and staging, healthcheck endpoints, `EMBEDDING_MODEL_PATH` env var.
3. **Phase 3 — Release pipeline.** GitHub Actions release workflow, `make release` target, changelog generator config.
4. **Phase 4 — Migration tooling.** `scripts/migrate_to_postgres.py`, tested against a staging Postgres locally.
5. **Phase 5 — Server bring-up.** Coordinate with sysadmin on Open Questions, install Docker on server, configure proxy, deploy staging stack.
6. **Phase 6 — Cutover.** Execute §7.4. Open team access after smoke passes.
7. **Phase 7 — Post-cutover hardening.** Rate limit on login, log scrubbing audit, uptime monitor config, first restore drill.

## 13. Out of scope (explicitly deferred)

- Redis / multi-replica scaling.
- Kubernetes / managed services.
- Public internet exposure.
- Automated deployment from CI (currently manual SSH per §6.3).
- Zero-downtime deploys.
- WAL archiving / point-in-time recovery (sysadmin snapshots are the chosen safety net).
- Centralized log aggregation (Loki, ELK, etc.).
- Application performance monitoring (Sentry, New Relic, etc.).
