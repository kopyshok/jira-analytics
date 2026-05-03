# Tech Debt Audit — JiraAnalysis

Generated: 2026-05-03
Branch: main, head: 4086d87
Repo: ~63k LOC source (backend Python 3.10 + React 19 / TS 6 SPA), 768 commits last 6 months, 27 API routers, 41 ORM models, 8 frontend pages.

## Executive summary

1. **Backend auth is missing on 25 of 27 routers.** Only `/auth` and `/users` use `Depends(get_current_user)`. `/admin/users` (create/list/update/reset_password), `/sync`, `/planning`, `/exports`, `/settings`, `/analytics`, `/capacity`, `/backlog` — all reachable without a token. Frontend `AuthLayout` is cosmetic. For a stated multi-user production target this is the single most important finding.
2. **`require_admin` does not exist** in the codebase, even though admin-only routes are described in the design doc and frontend memory. `app/core/auth_deps.py` only defines `get_current_user`.
3. **`python-jose==3.3.0`** has 4 known CVEs (PYSEC-2024-232, PYSEC-2024-233). Used to sign and verify JWTs. Fixed in 3.4.0.
4. **JWT secret silently defaults** to `"dev-secret-change-in-production"` in `app/config.py:40`. No fail-fast in production.
5. **Five god files concentrate most churn:** `sync_service.py` (1659 LOC, 34 commits), `planning.py` endpoint (1635 LOC, 30+ routes, 37 commits), `analytics_service.py` (1576 LOC, 40 commits), `SyncPage.tsx` (1150 LOC, 47 commits), `PlanningPage.tsx` (1013 LOC, 49 commits). All five are at the intersection of largest × most-modified.
6. **Frontend has 8 unused source files**, including `src/App.tsx` itself (entry was moved to `routes.tsx` and `App.tsx` is no longer imported).
7. **`@ant-design/icons` is imported by 31 files but is not declared** in `frontend/package.json` — works only via the antd transitive dep, brittle on antd upgrades.
8. **108 ruff errors**, 80 auto-fixable; one F821 forward-ref in `scheduler.py:191` is a false positive but blocks `make lint` for the rest. F841 unused locals indicate test fixtures used as side-effects rather than data.
9. **5 bare `except Exception: pass` in `scheduler.py`** silence scheduled-pipeline failures. `backlog.py:514` does the same during multi-field refresh — DB write errors are swallowed without log.
10. **Documentation drift:** root `CLAUDE.md` claims "21 routers", actual count is 27. `app/api/CLAUDE.md` table lists 21 routers, but `auth`, `users`, `admin/users`, `events`, `llm`, `teams` are missing from the table.

## Architectural mental model

JiraAnalysis is a 4-layer FastAPI + SQLAlchemy app: `connectors/jira_client.py` (httpx, async, rate-limited) → `services/*` (business logic, commits internally — see `app/services/CLAUDE.md`) → `repositories/*` (thin wrappers; mostly pass-through) → SQLite via `database.py`. Frontend is a TanStack-Query-driven React SPA with no client-side state store; `api/client.ts` reads `localStorage` JWT but no backend dependency enforces it.

Two large refactor waves dominate recent history. M9 (capacity overhaul, ~2026-04-18) introduced `ResourceBaseService` + `MandatoryWorkType` + per-day pool subtraction; M10 (sync consolidation + global team filter, ~2026-04-27) merged 18 sync buttons into `/sync` hub + APScheduler + an event bus + `selected_teams` per user. The post-M10 churn (Auth Variant A, dashboard redesign, projects page, full sync perf) all sit on top of M10 plumbing. The model is mostly clean; the pain is in three god files (`sync_service`, `analytics_service`, `planning.py` endpoint) where each successive feature added a method without splitting. The README + per-directory `CLAUDE.md` files do a good job of describing intent — the gap between docs and code is small. The bigger gap is between **frontend protection** (route gating + AuthLayout) and **backend protection** (none).

## Findings

| ID | Category | File:Line | Severity | Effort | Description | Recommendation |
|----|----------|-----------|----------|--------|-------------|----------------|
| F001 | Security hygiene | app/api/endpoints/admin_users.py:1-end | Critical | M | All four admin user endpoints (`list_users`, `create_user`, `update_user`, `reset_password`) use only `Depends(get_db)`. Anyone reachable on the network can list emails, create admins, reset passwords. | Add `Depends(require_admin)` to every route in this file before any other change. |
| F002 | Security hygiene | app/api/router.py:62-112 | Critical | L | 25 of 27 routers (analytics, sync, scope, mapping, capacity + 3 sub-routers, backlog, planning, exports, settings, categories, issues, hierarchy-rules, production-calendar, mandatory-work-types, role_capacity_rules, employee_capacity_overrides, absence_reasons, roles, events, projects, employees, teams, llm) are mounted without auth. No router-level dependency, no per-endpoint `Depends(get_current_user)`. | Add `dependencies=[Depends(get_current_user)]` to `api_router.include_router(...)` for every business router. Whitelist `/health`, `/auth/login`. |
| F003 | Security hygiene | app/core/auth_deps.py | Critical | S | `require_admin` is referenced in design notes and memory (`project_auth_multiuser_shipped`) but does not exist in the file. Only `get_current_user` is defined. Admin protection is structurally absent. | Add `def require_admin(user: User = Depends(get_current_user)) -> User: if user.role != UserRole.ADMIN: raise HTTPException(403)` and apply to admin-only routes (admin_users, settings/jira PUT, hierarchy-rules CRUD per memory). |
| F004 | Dependency & config debt | requirements.txt:24 | Critical | S | `python-jose==3.3.0` pinned — PYSEC-2024-232 and PYSEC-2024-233 (algorithm confusion / DoS in JWT verification). | Bump to `python-jose[cryptography]>=3.4.0` and run the auth tests. |
| F005 | Security hygiene | app/config.py:40 | High | S | `jwt_secret_key: str = "dev-secret-change-in-production"`. Silent default — if `JWT_SECRET_KEY` is missing in prod, the app boots and signs tokens with a public string. | Make the default `None`, add a `model_post_init`/`@field_validator` that raises if `debug=False` and the value is missing or equals the dev placeholder. |
| F006 | Security hygiene | app/main.py:60-66 | High | S | `allow_methods=["*"]`, `allow_headers=["*"]` with `allow_credentials=True`. Browsers refuse the wildcard combo, but this also implies the developer wanted everything open — easy to widen accidentally. | Restrict methods to actually-used ones (`GET, POST, PUT, PATCH, DELETE`) and headers to `Authorization, Content-Type`. |
| F007 | Architectural decay | app/services/sync_service.py:1-1659 | High | L | Single file holds projects sync, issues sync (+ targeted refresh), worklog buckets A and B, employee auto-create, parallel-per-project iteration, custom-field extraction. Hottest backend file (34 commits/6mo). | Split: `sync_service/projects.py`, `sync_service/issues.py`, `sync_service/worklogs.py` (buckets A/B), `sync_service/fields.py` (extract helpers + custom-field cache). Keep `SyncService` as a façade. |
| F008 | Architectural decay | app/api/endpoints/planning.py:1-1635 | High | L | 30+ route handlers in one file: scenarios CRUD, allocations CRUD + reorder + assignee patch, rules, revisions, capacity-diff, breakdown, resource-summary, sync-backlog, copy-rules, approve, revert, acknowledge-drift. 37 commits/6mo. | Split per resource: `planning/scenarios.py`, `planning/allocations.py`, `planning/rules.py`, `planning/revisions.py`. Move `_state_at_revision`, `_to_scenario_resp`, `_resolve_absence_hours` to `planning_service.py`. |
| F009 | Architectural decay | app/services/analytics_service.py:1-1576 | High | L | Hours-by-{employee/project/category/period} + dashboard widgets (3) + context-switching + hierarchical report + filter logic + plan-per-emp_wt all in one class. 40 commits/6mo. | Split into `analytics/dashboard_service.py` (widgets), `analytics/report_service.py` (hierarchical), `analytics/aggregation.py` (low-level group-by). Filter logic into a separate `FilterContext`. |
| F010 | Architectural decay | frontend/src/pages/SyncPage.tsx:1-1150 | High | L | 1150 LOC + 47 commits/6mo. Holds three nested tabs (TaskSections, CategoryConfig, SyncControls) plus shared state. Already partially extracted but page still drives a large state machine. | Extract `useSyncTabState` hook, move tab UI into `components/sync/{TaskSections,CategoryConfig,SyncControls}.tsx` (already split — finish the migration; remove residual page-level handlers). |
| F011 | Architectural decay | frontend/src/pages/PlanningPage.tsx:1-1013 | High | L | 1013 LOC + 49 commits/6mo. Mixes scenario list, allocation table, capacity panel, rules editor, revisions modal. | Each tab (scenarios list, scenario detail) becomes its own page-level component; allocations table is already extracted, revisions modal can be extracted. |
| F012 | Type & contract debt | frontend/src/types/api.ts:1-943 | High | L | 943 LOC, 51 commits/6mo, 15 unused exported types (knip). One file is the entire frontend ↔ backend contract. | Split per-domain: `types/scenarios.ts`, `types/capacity.ts`, `types/analytics.ts`, etc. Drop the 15 unused types. |
| F013 | Architectural decay | frontend/src/App.tsx:1-5 | High | S | `App.tsx` re-exports `<AppLayout />` but `main.tsx` directly renders `RouterProvider` from `routes.tsx` — `App.tsx` is never imported. Confirmed by knip. | Delete `App.tsx`. |
| F014 | Error handling | app/services/scheduler.py:39,49,79,172,176 | High | S | Five bare `except Exception: pass` in scheduled-job wiring (start/shutdown/job_error/replace_existing). Failures vanish silently. | Replace with `logger.exception("...")` + re-raise where appropriate. APScheduler has `EVENT_JOB_ERROR` — wire that. |
| F015 | Error handling | app/api/endpoints/backlog.py:514 | High | S | `except Exception: pass # best-effort` swallows DB write failures inside the multi-field refresh loop after `db.commit()`. Inconsistent state goes silently. | Log the exception with context (`backlog_id`, `field_name`); continue with the next item but surface failed count in response. |
| F016 | Dependency & config debt | frontend/package.json:14-29 | High | S | `@ant-design/icons` is imported by 31 source files but is not in `dependencies` or `devDependencies` (knip flags 31 unlisted-dep occurrences). It resolves only via antd's own dep graph — invisible breaking change on next antd minor. | `npm i -S @ant-design/icons`. |
| F017 | Test debt | tests/test_sync_service_reload.py:49,112 | High | S | Vulture (100% conf): unreachable code after `return`/`raise` — branches that never run. Tests pass without exercising the asserted paths. | Read both functions, decide whether the `return`/`raise` is wrong or the trailing assertion is — fix or delete. |
| F018 | Test debt | tests/test_sync_service_delete_diff.py:142,165, test_sync_service_update.py:91,185,227,251 | High | S | Vulture (100% conf): six unsatisfiable `if` conditions across two files. The branches inside never execute, the assertions inside never run. | Same — read each branch, decide which side of the `if` is the live one, drop the dead branch. |
| F019 | Documentation drift | CLAUDE.md (root) line ~13 + app/api/CLAUDE.md table | Medium | S | Root CLAUDE.md says "21 routers"; actual count is 27 (added: auth, users, admin/users, llm, teams, events, roles). `app/api/CLAUDE.md` table also missing those rows. | Refresh both. The api/CLAUDE.md table is the canonical source — add the missing six rows. |
| F020 | Architectural decay | app/api/endpoints/sync.py:1-1061 | Medium | L | Single file holds: trigger endpoints, `/jira-projects/epics/fields/teams/issuetypes` browse, SSE streams (worklogs reload + worklogs update), targeted issue refresh, sync schedule CRUD, sync history. The CLAUDE.md note "Sync consolidation shipped (M10)" reflects merging UI buttons; the file behind those buttons remained one. | Split: `sync/triggers.py`, `sync/jira_browse.py` (with `jira_router`), `sync/streams.py`, `sync/schedule.py`, `sync/history.py`. |
| F021 | Architectural decay | app/services/scenario_xlsx_export.py:1-1187 | Medium | M | One module renders four xlsx sheets (Сводка/Включено/Не вошло/Справочник). 13 `# type: ignore[import-untyped]` for openpyxl alone — module is doing layout + styling + data assembly. | Split per sheet (`_build_summary_sheet`, `_build_included_sheet`, `_build_excluded_sheet`, `_build_reference_sheet`) into one file each under `services/scenario_xlsx/`. Move `_Style` palette to a constants file. |
| F022 | Architectural decay | app/services/snapshot_writer.py:1-702 | Medium | M | One class holds 8 `write_*` methods (team, calendar, rules, dictionary, capacity, norm, allocation, allocation_breakdown). Each method is non-trivial; allocation_breakdown does proportional split per role × month. | Keep `SnapshotWriter` as façade; move per-snapshot logic into `snapshot/{team,calendar,rules,...}_writer.py` modules called from the façade. Same shape as services CLAUDE.md describes. |
| F023 | Architectural decay | frontend/src/pages/CapacityPage.tsx:720, BacklogPage.tsx:712 | Medium | M | Both pages > 700 LOC. Each holds tab dispatch + filter state + table + drawer + heatmap (for capacity) — pages have outgrown the "page is just routing" model. | Move tab content into `components/capacity/{TeamTab,RolesTab,...}.tsx` (RolesTab exists; finish the move) and `components/backlog/{Active,Working,Archive}Tab.tsx`. |
| F024 | Architectural decay | frontend/src/components/planning/ScenarioResourceSummary.tsx:661 | Medium | M | Single component renders the whole role × work-type breakdown table including totals + edit-in-place + tooltips. | Extract `ResourceSummaryTable`, `ResourceSummaryRow`, keep this file as wiring. |
| F025 | Consistency rot | frontend/src/api + frontend/src/hooks | Medium | M | knip reports 17 unused exports across `api/{capacity,client,employees,exports,sync,syncRuns}.ts` and `hooks/{useBacklog,useCapacity,useIssueTree,usePlanning,useScope,useSync}.ts`. The full M9-era CRUD of `RoleCapacityRule`/`EmployeeCapacityOverride` (`createRoleCapacityRule`, `updateRoleCapacityRule`, `deleteRoleCapacityRule`, ditto for employee) is dead code on the frontend. | Delete unused exports. The role/employee rule CRUD probably moved to batch PUT after capacity v3 — confirm endpoints first, then remove the dead client + hook code. |
| F026 | Architectural decay | frontend unused files: ScopePage.tsx, KpiCard.tsx, QuarterPicker.tsx, QuarterYearSelect.tsx, DateRangeSelect.tsx, ExportButtons.tsx, ProjectKeyBlocksCard.tsx | Medium | S | Knip flags eight unused source files. `ScopePage` is referenced in router as `/scope → /sync` redirect (memory note), but the page component itself is no longer rendered. The other six are leftovers from previous KPI/picker iterations. | Delete the seven non-`App.tsx` files; verify routes.tsx redirect uses a `<Navigate>` not `<ScopePage>`. |
| F027 | Type & contract debt | frontend/src/components/planning, capacity, dashboard, sync, projects, settings, analytics + 8 pages | Medium | S | `@ant-design/icons` is unlisted (F016) — same severity flag as F016 but listed here as the consistency-rot symptom. | Fix once at F016 closes this. |
| F028 | Test debt | tests/conftest.py:76 | Medium | S | F811 — `app.models` redefined here after line 15. The test conftest imports the same module twice. | Drop the duplicate import. |
| F029 | Test debt | 23 test files with F401 unused imports / F841 unused locals | Medium | S | 80 of the 108 ruff errors are auto-fixable, mostly `import pytest` unused or unused fixture-result vars (tests use the fixture for side effects only). | Run `ruff check tests/ --fix`. For `F841 _unused = fixture()`, prefer using the fixture as a function arg without binding. |
| F030 | Error handling | app/main.py:22-24,49 | Medium | S | `print()` for lifecycle logging — bypasses the configured `log_level`. | Use `logging.getLogger(__name__).info(...)` and configure logging in `main.py` from `settings.log_level`. |
| F031 | Error handling | app/api/endpoints/backlog.py:127 | Medium | S | `except Exception: return None` inside `_discover_field_id` — masks transport errors as "field not found". User sees no signal. | Catch only `httpx.HTTPError` / `JiraApiError`; let pydantic / programmer errors crash. Log on the caught path. |
| F032 | Performance & resource hygiene | app/services/analytics_service.py:712,1232,1283 | Medium | M | `EmployeeTeam.employee_id.in_([e.id for e in employees])` — three separate queries that each rebuild the same employee-id list. Not strictly N+1 but the 1576-LOC file suggests other repeated fan-outs nearby. Capacity service has the same pattern. | Hoist `employee_ids` once per request, reuse. Profile this on the largest team (~115k issues per memory) before changing. |
| F033 | Architectural decay | app/api/endpoints/{role_capacity_rules.py, employee_capacity_overrides.py, absence_reasons.py} mounted under /capacity | Medium | M | One logical resource ("capacity rules") spans three sibling files mounted at three sub-prefixes of `/capacity`. The reason is historical (capacity v2 → v3 split). Discoverability suffers; callers must know which sub-prefix holds which CRUD. | Either merge into `capacity_rules.py` with three sub-routers internally, or document the boundary in `app/api/CLAUDE.md` (currently mentioned but not justified). |
| F034 | Dependency & config debt | requirements.txt:1-34 | Medium | S | Most pins are `>=` with no upper bound. `pydantic>=2.5.0` includes any 3.x, `httpx>=0.26.0` includes 1.x when released. `apscheduler>=3.10,<4.0` is the right shape. | Add `<` upper bounds for the libs that have published breaking 1.0 / next-major (`pydantic<3`, `httpx<1`, `sqlalchemy<3`, `fastapi<1`). Or move to `uv`/`poetry` lock. |
| F035 | Dependency & config debt | app/config.py:43-45 | Medium | S | `admin_email: str = ""`, `admin_password: str = ""` — used by `scripts/create_admin.py`. Empty-string default fails late and confusingly. | Use `Optional[str] = None`; let `create_admin.py` print "set ADMIN_EMAIL and ADMIN_PASSWORD" and exit if missing. |
| F036 | Documentation drift | docs/superpowers/plans/2026-04-27-cross-sectional-reactivity.md, 2026-05-01-other-foreign-tasks.md, docs/superpowers/specs/2026-04-27-cross-sectional-reactivity-design.md, scripts/count_loc.py | Low | S | Four untracked design files in `git status` — workflow leakage; not committed yet but already referenced by recent commits (`reactivity_shipped` memory). | Decide: commit, or add to `.gitignore`. Don't leave on disk forever. |
| F037 | Documentation drift | app/api/CLAUDE.md table "21 routers" | Low | S | Table lists 21 entries; actual count 27. Auth, users, admin/users, llm, teams, events, roles missing. | Add the six rows. |
| F038 | Test debt | tests/test_capacity_service.py:351-353 (E402) | Low | S | `import` after non-import code. Either a deliberate late-load to escape a circular issue or oversight. | Read context — if circular, document with a comment; if oversight, hoist. |
| F039 | Type & contract debt | app/services/sync_service.py:1 + app/services/scenario_xlsx_export.py:12-14 | Low | S | 14 `# type: ignore`. Of these, 13 are `# type: ignore[import-untyped]` for openpyxl — legitimate (openpyxl ships no `py.typed`). One in `sync_service.py:1` is on the module-level docstring/import — likely stale. | Inspect `sync_service.py:1` ignore; remove if stale. The openpyxl ignores are fine. |
| F040 | Performance & resource hygiene | app/main.py:36-42 + app/services/scheduler.py | Low | S | Lifespan hard-codes a cron job for `regenerate_outdated_summaries` (3 AM) inline. Also adds APScheduler triggers from DB. Two scheduling paths in one place. | Move both into `SchedulerService.register_default_jobs()`; lifespan only calls it. Lets `make test` introspect what jobs are configured. |
| F041 | Test debt | tests/test_scenario_rule_model.py:5-8 (E702) | Low | S | Five "multiple statements on one line" warnings — `import; import; import` style. Cosmetic but noisy in `make lint`. | One import per line. |
| F042 | Performance & resource hygiene | app/services/sync_service.py + connectors/jira_client.py | Low | M | Memory note `project_full_sync_perf_shipped` says full sync went 60→11 min via bulk worklog API + WAL + parallel projects (commits c9ecbea, 41810d7, a6bfd1c). The WAL pragma is in `database.py:73 except Exception: pass` — best-effort, no fail-open log. | Log on WAL failure; consider `journal_mode=WAL` set in `connect_args` instead of post-connect pragma. |
| F043 | Consistency rot | app/api/endpoints — mix of sync (`def`) and async (`async def`) handlers | Low | S | `admin_users.py` uses sync `def` for all four routes; rest of the codebase is `async def` even where the body is sync. FastAPI handles both, but readers will assume a pattern. | Pick one in `app/api/CLAUDE.md` and stick to it. The current convention seems to be `async def` even for sync bodies — flip admin_users.py to match. |
| F044 | Architectural decay | frontend/src/components/analytics/AnalyticsTable.tsx:580 + IssueContextBlock.tsx:443 + dashboard/ProjectsWidget.tsx:520 | Low | M | Three large components (>440 LOC each) under `components/`. None are flagged by knip — they're imported. Just large. | Each can be split into table-row / cell components when next touched, but no reason to prophylactically refactor. Note for next analytics churn. |
| F045 | Dependency & config debt | frontend/package.json devDependencies has `madge` + `depcheck` flagged unused by knip itself | Low | S | Knip says `madge` and `depcheck` are unused devDeps. They were just installed for this audit. | Either keep them as `make audit` tooling (add a script) or drop after audits run. |
| F046 | Performance & resource hygiene | (graphviz `dot` missing on host) | Low | S | `pydeps app --show-cycles` failed: "Graphviz 'dot' produced empty output". Cannot generate cycle graph without it. | Install Graphviz on Windows (`choco install graphviz` or `winget install graphviz`) for pydeps; not a code finding but worth installing if you want to repeat-run this audit cleanly. |

## Top 5 — if you fix nothing else, fix these

### 1. Lock the backend behind auth (F001 + F002 + F003)

The single biggest production risk. Three pieces, one PR.

```python
# app/core/auth_deps.py — add
def require_admin(user: User = Depends(get_current_user)) -> User:
    from app.models.user import UserRole
    if user.role != UserRole.ADMIN:
        raise HTTPException(403, "Admin only")
    return user

# app/api/router.py — wrap every business router
api_router.include_router(
    employees.router, prefix="/employees", tags=["employees"],
    dependencies=[Depends(get_current_user)],
)
# repeat for projects, teams, sync, scope, analytics, mapping, capacity,
# backlog, planning, exports, settings, categories, issues,
# hierarchy_rules, production_calendar, mandatory_work_types,
# role_capacity_rules, employee_capacity_overrides, absence_reasons,
# roles, events, llm

# Admin-only routers: dependencies=[Depends(require_admin)]
api_router.include_router(
    admin_users_endpoints.router, prefix="/admin/users",
    dependencies=[Depends(require_admin)],
)
# Likely also: hierarchy_rules, settings (PUT /jira), production_calendar
```

Whitelist `/auth/login` (and `/auth/me`, since it itself depends on the token to discover the user). Test with the existing E2E `crud-flows.spec.ts` — if any spec breaks because the user isn't seeded, that means the spec was relying on the unauthenticated hole.

### 2. Fix the JWT CVE chain (F004 + F005)

```diff
# requirements.txt
-python-jose[cryptography]==3.3.0
+python-jose[cryptography]>=3.4.0,<4.0
```

```python
# app/config.py
-    jwt_secret_key: str = "dev-secret-change-in-production"
+    jwt_secret_key: Optional[str] = None
@@
+    @model_validator(mode="after")
+    def _enforce_jwt_secret(self):
+        if not self.debug and (
+            not self.jwt_secret_key
+            or self.jwt_secret_key == "dev-secret-change-in-production"
+        ):
+            raise ValueError("JWT_SECRET_KEY must be set in non-debug mode")
+        return self
```

This pair lands in one PR; both are small.

### 3. Split sync_service.py (F007)

Highest-churn backend file. Each commit currently risks merge conflicts with a different feature branch touching the same 1659-line file. Sketch:

```
app/services/sync_service/
  __init__.py        # re-exports SyncService façade
  projects.py        # sync_projects + dependency on SyncState
  issues.py          # sync_issues + targeted refresh + custom-field extraction
  worklogs.py        # bucket A (issue-centric) + bucket B (employee-centric)
  fields.py          # _extract_team_values, _parse_jira_datetime, _to_float, etc.
```

`SyncService` becomes a thin façade composing the four. Tests in `tests/test_sync_service_*.py` keep the same import path because `__init__.py` re-exports. Worklog buckets in particular deserve their own file: bucket B has unique semantics (out-of-scope auto-create) that gets lost when read inside the larger file.

### 4. Split planning.py endpoint (F008)

30+ routes, 1635 LOC, 37 commits/6mo — every scenario feature touches this file. Sketch:

```
app/api/endpoints/planning/
  __init__.py        # router = APIRouter(); router.include_router(scenarios_router); ...
  scenarios.py       # CRUD + approve + revert + acknowledge-drift
  allocations.py     # list + reorder + patch + patch-assignee
  rules.py           # get/replace/copy-from-template
  revisions.py       # list + delete + diff + breakdown
  resource.py        # GET resource + resource-summary
```

Helpers (`_to_scenario_resp`, `_to_allocation_resp`, `_resource_to_response`, `_state_at_revision`) move to `app/services/planning_service.py` (already a "thin helper" per `app/services/CLAUDE.md` — it can absorb these without changing intent).

### 5. Frontend cleanup wave (F013 + F016 + F025 + F026)

One PR, lands in an afternoon, removes the most visible noise:

- `npm i -S @ant-design/icons` (closes F016, F027)
- `git rm src/App.tsx src/pages/ScopePage.tsx src/components/shared/{KpiCard,QuarterPicker,QuarterYearSelect,DateRangeSelect,ExportButtons}.tsx src/components/projects/cards/ProjectKeyBlocksCard.tsx`
- Delete the 17 unused exports + 15 unused exported types listed in knip output
- Verify `routes.tsx` `/scope` redirect uses `<Navigate to="/sync" />`, not `<ScopePage>`
- `npx knip` should drop to zero unused-files / zero unlisted-deps

After this, `npx knip` becomes a useful CI signal again instead of noise.

## Quick wins

- [ ] F003: Add `require_admin` dep (3 lines).
- [ ] F004: Bump `python-jose` to `>=3.4.0`.
- [ ] F013: Delete `frontend/src/App.tsx`.
- [ ] F016: `npm i -S @ant-design/icons`.
- [ ] F019 + F037: Refresh router count in `CLAUDE.md` and `app/api/CLAUDE.md`.
- [ ] F028: Drop duplicate `app.models` import in `tests/conftest.py:76`.
- [ ] F029: `ruff check tests/ --fix` (closes 80 lint errors).
- [ ] F030: Replace `print()` in `app/main.py` with `logging`.
- [ ] F036: Decide on the four untracked `docs/superpowers/*.md` + `scripts/count_loc.py` (commit or `.gitignore`).
- [ ] F041: One import per line in `tests/test_scenario_rule_model.py:5-8`.

## Things that look bad but are actually fine

- **`vulture` flags every FastAPI route handler in `planning.py` (lines 383, 410, 476, ...) as "unused function".** Vulture cannot see the `@router.get/post/...` decorator registering the handler. False positives — ignore. Same applies to all endpoint files; do not trust vulture confidence < 80% for FastAPI routes.

- **`vulture` flags pydantic-schema fields like `r1_norm_hours`, `from_attributes`, `Config` class as "unused".** These are pydantic v2 model attributes / config classes; vulture doesn't understand pydantic introspection. Ignore at 60% confidence.

- **13 `# type: ignore[import-untyped]` in `scenario_xlsx_export.py`.** openpyxl does not ship a `py.typed` marker, so mypy treats every import as `Any`. The `type: ignore` is the documented escape hatch. Don't chase these — chase #1 in F039 (the lone one in `sync_service.py`).

- **`scheduler.py:191` declares `_build_orchestrator_local(...) -> "PipelineOrchestrator":` and ruff F821s it** because the import is inside the function. The forward-reference string evaluates lazily; F821 is wrong here. The right fix is `from __future__ import annotations` at the top of `scheduler.py`, but the runtime is correct — leave as-is until you do that import-style cleanup project-wide.

- **`tests/services/test_sync_pipeline_stages.py:16: F401 unused import 'WorklogsFullStage'.**` Looks like dead code, but the test file may be using it as a fixture-discovery side-effect. Read once before deleting; if it's only there for `__all__` regression coverage, document and ignore.

- **Bare `except Exception: pass` in `app/services/sync_lock.py:33`.** This is a lock-release path that must never raise back to the caller — silent swallow is intentional. Don't add re-raise. Adding a log line is fine (and useful).

- **`AnalyticsService` in-list construction `EmployeeTeam.employee_id.in_([e.id for e in employees])`** looks like an N+1 trigger but is the **correct bulk** form — one SQL query, IN clause. F032 is about hoisting the comprehension across three call sites in the same file, not about N+1.

- **`extra="ignore"` in `app/config.py:87`.** Hides unknown env vars. Looks lax, but the alternative — `extra="forbid"` — would crash on every CI/host that has unrelated `PATH`-style env vars. Pydantic-settings reads `env_file` plus the whole environment; ignore is correct.

- **27 routers vs. CLAUDE.md's "21".** Looks like a major doc rot, but the 6 missing routers (auth, users, admin/users, events, llm, teams + roles partial) are recent additions (~M10 + post-M10). The doc isn't wrong about the architecture; it's just behind. F019 covers the fix; not a structural issue.

- **`scripts/count_loc.py` untracked.** Looks like a one-off experiment but it's referenced in your loc tracking (used recently, judging by file modification). Decide commit-or-gitignore in F036; not a code problem.

- **Frontend `staleTime: 30_000` hard-coded in `main.tsx:27`** with no override path. Looks rigid, but every page can override per-`useQuery`, and 30s default is sane for an SSE-driven app. Don't make it configurable.

## Open questions for the maintainer

1. **Is the missing backend auth a known gap or oversight?** Memory `project_auth_multiuser_shipped` (2026-04-27, Variant A) describes login/me/admin endpoints; the same memory says "Variant B (server-side middleware) — следующий этап". So this is **known**. Confirm the timeline — if Variant B is weeks away, the production deploy needs to wait or sit behind a VPN.

2. **Is the `/scope` route intentionally a redirect-only?** `ScopePage.tsx` exists but is unused; `routes.tsx` mentions `/scope → /sync`. Should the file be deleted (F026) or kept for an upcoming feature?

3. **`tests/test_sync_service_delete_diff.py` and `tests/test_sync_service_update.py` have unsatisfiable conditions and unreachable code (F017 + F018).** These look like tests that mock-drifted away from the real service signature (consistent with memory `project_ci_red_pre_existing` mentioning sync mock drift). Are they **expected-broken** waiting on a sync_service rewrite, or did you forget?

4. **Three-file fragmentation under `/capacity` (role_capacity_rules, employee_capacity_overrides, absence_reasons)** — historical from the v2 → v3 capacity refactor. Worth merging now (one logical concern) or is this layout intentional for code-owner separation?

5. **The four untracked docs in `docs/superpowers/` + `scripts/count_loc.py`** — commit them or gitignore? They're already cited in your memory as work artifacts.

6. **`requirements.txt` upper-bound policy (F034)** — your CI is locked to Python 3.10 (`py -3.10` per CLAUDE.md). Do you want strict pinning + Renovate/Dependabot, or stay with the current loose bounds? Multi-user prod argues for the former.

7. **The `RoleCapacityRule`/`EmployeeCapacityOverride` frontend CRUD that knip flags (F025) as dead** — was it deprecated by the batch-PUT endpoints, or is the API client wired but no UI calls it yet? The endpoints (`role_capacity_rules.router`, `employee_capacity_overrides.router`) still exist in `router.py`.
