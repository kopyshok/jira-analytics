# Global Team Filter + UserUpdate sentinel fix

**Date:** 2026-04-28
**Status:** Approved
**Author:** akim4ik

## Goal

Single per-user team filter applied across all data pages. Admin sets a "default team" for each user; user can change current selection at runtime. Selection persists across devices via DB.

Plus: fix `UserUpdate.default_team=null` sentinel bug — admin currently cannot clear a user's default team via the admin UI because `None` means both "field omitted" and "set to null" in the request body.

## Non-Goals

- Server-side authorization / data isolation per role (Variant B concern, separate effort).
- Hierarchy of teams (no team-parent relations exist in DB; filter is flat multi-select).
- Replacement of admin-only sync/scope filters (Sync, Settings retain their own selectors).

## Decisions (from brainstorm)

1. **Hybrid model:** `User.default_team` (scalar, admin-set) + `User.selected_teams` (list, user-set, persisted).
2. **Persistence:** DB per-user — both fields on `users` table.
3. **Scope:** Dashboard, Analytics, Backlog, Planning, Capacity, Categories. Sync + Settings unaffected.
4. **Roles UX:** unified — manager defaults to `default_team`, admin/super_manager default to empty (= all teams). No UI restrictions on which teams can be picked.
5. **UI placement:** header (top-right, near user name + logout). Multi-select pill with popover.
6. **Drop FactFilter toggles:** `match_employees`/`match_issues` removed from UI. Backend always applies OR (employee.team OR issue.team) on Dashboard/Analytics.

## Architecture

### Data Model

Migration `037_user_selected_teams.py`:
- `users.selected_teams` — JSON column (SQLite + PostgreSQL compatible), default `[]`, NOT NULL.
- `users.default_team` already exists.

### Backend

**Schemas (`app/schemas/user.py`):**
- `UserResponse` — add `selected_teams: list[str]`.
- `UserUpdate` — keep current fields. Adopt `model_dump(exclude_unset=True)` semantics in handler.
- New `UserTeamsUpdate` — `{teams: list[str]}`.

**Endpoints:**
- `PUT /admin/users/{id}` — replace per-field `if is not None` with `data.model_dump(exclude_unset=True)`. Allows clearing `default_team` via explicit `null`.
- `PUT /auth/me/teams` — body `{teams: [...]}`, replaces `current_user.selected_teams` wholesale, returns updated `UserResponse`.

**Auth dependency:** `get_current_user` already exists for `/auth/me`. Reuse for `/auth/me/teams`.

**Login init logic:** on `GET /auth/me`, if `selected_teams == []` AND `default_team is not None`, do NOT auto-fill on backend — frontend handles initial seeding once on login (see Frontend below). Backend keeps state honest.

**Existing analytics endpoints:** already accept `?teams=A,B`. Drop `match_employees`/`match_issues` query params — always OR. Update:
- `/analytics/*`
- `/issues/tree`
- `/backlog`
- `/planning/scenarios/*`
- `/capacity/*`

Endpoints that already use `?teams=A,B` keep the contract; just remove the two boolean params.

### Frontend

**New: `GlobalTeamFilterProvider`** at app-root level (above `AppLayout`).
- State: `selectedTeams: string[]` (hydrated from `useAuth().user.selected_teams`).
- On change: `PUT /auth/me/teams` + optimistic local update + invalidate all team-scoped queries.
- Exposes `useGlobalTeamFilter()` hook returning `{selectedTeams, setSelectedTeams, queryParams: {teams: 'A,B' | undefined}}`.

**Login seeding:** in `AuthProvider`, after login, if `user.selected_teams.length === 0` && `user.default_team`, call `PUT /auth/me/teams` with `[default_team]` once.

**Header component:** `GlobalTeamFilterButton` in `AppLayout` header row.
- Display: pill button with first team + count (`«Аналитика, +2»` or `«Все команды»` if empty).
- On click: popover with multi-select Search-Select listing all teams from `useJiraTeams`.
- Edge case: empty list → disabled with tooltip «Загрузите команды в разделе Синхронизация».

**Migration of existing filters:**
- **Dashboard, Analytics:** delete `FactFilterProvider`, replace with `useGlobalTeamFilter()`. Delete match toggles in UI. Delete `ui_fact_filter_*` AppSetting keys (one-time cleanup migration; not load-bearing).
- **Backlog:** if it has its own team filter, replace with global.
- **Planning (scenarios):** scenario CRUD already takes a single `team` field on creation — keep that (per-scenario team is independent of view filter). Scenario list view, however, filters by global filter.
- **Capacity:** replace local team selector with global filter input.
- **Categories (`/categories`):** replace local multi-team Select with global filter. Drop `ui_teams_categories` AppSetting key.

**TanStack Query keys:** all team-scoped queries include `selectedTeams` in their queryKey to ensure cache invalidation on filter change.

### Admin UI changes

**Settings → Пользователи tab (`UsersTab.tsx`):**
- Edit modal: `default_team` field accepts empty (`null`) to clear. AntD Select with `allowClear`.
- On submit: send `{default_team: null}` explicitly when cleared (not `undefined`). Use a discriminator state to distinguish "не трогали" from "очистили".

## Data Flow

### User opens app

1. Frontend boots, `AuthProvider` calls `GET /auth/me`.
2. If `selected_teams === [] && default_team !== null`, call `PUT /auth/me/teams [default_team]`. (Auto-seed once.)
3. `GlobalTeamFilterProvider` hydrates from `user.selected_teams`.
4. Header pill renders.

### User changes filter

1. Click pill → popover opens with multi-select.
2. User picks/unpicks teams → on close, frontend calls `PUT /auth/me/teams` with new list.
3. Provider state updates.
4. All team-scoped queries refetch (queryKey includes `selectedTeams`).
5. Cross-device sync next time user logs in elsewhere.

### Admin changes user's default

1. Admin opens user edit modal.
2. Sets/clears `default_team` field → submit.
3. `PUT /admin/users/{id}` with `model_dump(exclude_unset=True)`. Cleared = `null` in body. Omitted = absent in body.
4. User's `selected_teams` is NOT touched by admin action — admin only changes the "starting point" for the next login if user's selected_teams ever becomes empty.

## Error Handling

- `PUT /auth/me/teams` invalid team name → 400 (validate against `useJiraTeams`).
- Network failure on filter change → revert local state, show toast «Не удалось сохранить выбор команд».
- Admin edits non-existent user → 404 (already handled).
- Empty `default_team` for `manager` role → allow (manager just sees no data until admin assigns or user picks). No 422.

## Testing

**Backend:**
- `tests/test_admin_users.py` — `default_team` cleared via `null`, omitted via missing key. Both cases verified.
- `tests/test_auth_endpoints.py` — `PUT /auth/me/teams` happy path, validation, persistence.
- `tests/test_user_repository.py` — `selected_teams` JSON serialization round-trip.
- Migration test — `037` upgrade/downgrade.
- Existing analytics tests — drop `match_employees`/`match_issues` query params from fixtures.

**Frontend:**
- Manual: login as manager with `default_team = "Аналитика"` and empty `selected_teams` → verify auto-seed.
- Manual: change filter on Dashboard → reload page → filter persists.
- Manual: admin clears user's `default_team` → user's existing `selected_teams` unchanged.
- E2E (`frontend/e2e/global_filter.spec.ts`): seed user with default team, verify pill shows team, filter applies on Dashboard.

## Migration & Rollout

1. Migration `037`: add `selected_teams` column with default `[]`. Backfill existing users with `[default_team]` if `default_team is not None` (so they don't have to re-pick on first login post-deploy).
2. Deploy backend.
3. Deploy frontend (new header pill + filter provider).
4. Old AppSetting keys (`ui_fact_filter_teams`, `ui_fact_filter_scope_employees`, `ui_fact_filter_scope_issues`, `ui_teams_categories`) cleaned up in a follow-up commit (no functional impact, just cleanup).

## Open follow-ups (post-implementation)

- Variant B server-side auth: enforce `selected_teams` server-side per request (currently any client could send any `?teams=` param).
- Hierarchy: when team-parent table arrives, filter pill shows tree-mode select.
- Per-page filter override: «временно показать другую команду на этой странице, не меняя глобальный выбор» — not in scope now.
