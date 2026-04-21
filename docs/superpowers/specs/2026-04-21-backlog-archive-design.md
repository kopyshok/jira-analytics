# Archive lifecycle for backlog initiatives

**Date:** 2026-04-21
**Scope:** Backlog page, `BacklogService`, `/backlog` endpoints, Alembic migration

## Problem

PM reported a bug: after re-categorising a Jira issue from «Инициативы и RFA» to «Архив» via CategoryConfigTab, the initiative stayed on the Backlog page — it only lost its Jira link. Root cause is `BacklogService.sync_from_issue`: when the linked `Issue.category` leaves `initiatives_rfa` and at least one `ScenarioAllocation` references the `BacklogItem`, the service **soft-unlinks** (sets `issue_id = NULL`). The row survives and renders as a «ручная идея», which contradicts the PM's mental model of archive = gone from backlog.

Beyond the bug, the domain lacks an explicit concept of «inициатива взята в работу». Initiatives that already sit in an approved scenario currently still appear in the backlog as allocable candidates — they should drop out until work on them stops.

## Domain model

A `BacklogItem` has three computed states. They are derived — not stored as a single enum — because the inputs change independently.

| State | Rule | Where it's visible |
|---|---|---|
| **Активная** | `archived_at IS NULL` AND not allocated to any approved scenario | Backlog → «Активные» tab |
| **В работе** | `archived_at IS NULL` AND allocated to ≥1 approved scenario | Backlog → «В работе» tab (read-only); scenario page |
| **Архивная** | `archived_at IS NOT NULL` | Backlog → «Архив» tab |

Display precedence when states overlap (theoretically impossible case of archived + in-work): Архив > В работе > Активная.

## Transitions

| Transition | Trigger | Effect |
|---|---|---|
| Активная → В работе | Allocation added to scenario that is `approved` (or scenario `draft → approved`) | No row mutation — filter recomputes |
| В работе → Активная | Last approved allocation removed OR scenario `approved → draft` | No row mutation — filter recomputes |
| Активная → Архивная | «Архивировать» button on Backlog row | `archived_at = now()` |
| Активная → Архивная | `Issue.category` leaves `initiatives_rfa` (CategoryConfigTab batch/single, or «Обновить с Jira» refresh) | `archived_at = now()`, `issue_id` preserved |
| Архивная → Активная | «Восстановить» button on Архив row | `archived_at = NULL` (requires linked `Issue.category == initiatives_rfa` if linked) |
| Архивная → Активная | `Issue.category` returns to `initiatives_rfa` | `archived_at = NULL` — Jira is source of truth |
| В работе → Архивная via «Архивировать» button | User action on in-work item | **Blocked** with HTTP 422 — PM must first drop the approved allocation |
| В работе → Архивная via Jira category flip | Automatic sync | Allowed — `archived_at` set, `issue_id` and approved allocation preserved. User's rule says this is «theoretically impossible»; this branch is a safe fallback. |
| Any → deleted | 🗑️ button | Existing rule preserved: HTTP 409 if any approved allocation references the item |

**Removed behaviour:** `BacklogService.sync_from_issue` no longer performs soft-unlink or auto-delete. It only flips `archived_at` and preserves `issue_id`. The bug report traces directly to this change.

## Backend changes

### Alembic migration
```
ALTER TABLE backlog_items ADD COLUMN archived_at DATETIME NULL;
```
No index — the table is small and `archived_at IS NULL` is cheap.

### `BacklogService.sync_from_issue`
Rewrite the tail:

- `issue.category == 'initiatives_rfa'`:
  - create-or-update (unchanged)
  - set `archived_at = None` — auto-restore on Jira category flip
- `issue.category != 'initiatives_rfa'`:
  - if existing `BacklogItem` present → set `archived_at = now()`, keep `issue_id`
  - if no `BacklogItem` → no-op (unchanged)

Return value becomes a structured counter the caller can surface: `{action: 'created' | 'updated' | 'archived' | 'restored' | 'noop'}`. Refresh endpoint aggregates.

### `GET /backlog`
New query param `view`, default `active`:
- `view=active` — `archived_at IS NULL AND NOT EXISTS (approved allocation)`
- `view=archived` — `archived_at IS NOT NULL`
- `view=in_work` — `archived_at IS NULL AND EXISTS (approved allocation)`

`BacklogItemResponse` gains:
- `archived_at: datetime | null`
- `in_work: bool` (precomputed per row via joined-load of allocations)
- `approved_scenarios: [{id: str, name: str}]` — non-empty only when `in_work=true`

### New endpoints
- `POST /backlog/{id}/archive` — `archived_at = now()`. Returns 422 if item is `in_work`. Idempotent for already-archived (200 + no-op).
- `POST /backlog/{id}/restore` — `archived_at = NULL`. Returns 409 if linked `Issue.category != 'initiatives_rfa'` (message: «В Jira категория архивная — смените категорию в Jira/CategoryConfigTab»). Idempotent for already-active.

### `POST /backlog/refresh-from-jira`
Response schema extended:
```python
class RefreshResponse(BaseModel):
    created: int
    updated: int
    removed: int            # kept for backward compat — will read 0 under new logic
    archived: int           # NEW
    restored: int           # NEW
    jira_refreshed: int
```
`removed` stays at 0 once soft-delete is gone; kept so old frontend builds do not break.

### `PlanningService`
When a draft scenario attempts to allocate a new `BacklogItem`:
- if `archived_at IS NOT NULL` → HTTP 422 «Инициатива в архиве, сначала восстановите».

Existing allocations are not touched — if a scenario already holds an archived item (historical), it stays as-is and is visible in the scenario.

### Legacy data
Current soft-unlinked rows (`issue_id = NULL` but previously linked) are indistinguishable from manual ideas. Migration does nothing with them — they stay as active «ручные идеи» and the PM can archive/relink them via UI. Auto-healing would require title-matching guesses and is not worth the risk.

## Frontend changes

### `BacklogPage`
Replace single table with AntD `Tabs`:

| Tab | Filter | Row actions (linked) | Row actions (manual) |
|---|---|---|---|
| Активные (N) | `view=active` | Unlink, **Archive**, Delete | Edit, Link, **Archive**, Delete |
| В работе (N) | `view=in_work` | — (read-only) + link to scenario | — (read-only) + link to scenario |
| Архив (N) | `view=archived` | **Restore**, Delete | Edit, **Restore**, Delete |

Active tab persisted in URL (`?view=active`). `dnd` drag-and-drop and inline edits stay on «Активные» only.

### `useBacklog` hooks
- `useBacklogItems(view: 'active' | 'archived' | 'in_work' = 'active')` — query key `['backlog', view]`.
- `useArchiveBacklogItem()` — `POST /backlog/{id}/archive`.
- `useRestoreBacklogItem()` — `POST /backlog/{id}/restore`.
- All mutations invalidate all three `['backlog', *]` keys so tab counts refresh without reload.

### Confirmation dialogs
- **Archive:** Popconfirm «Убрать из активного бэклога? Инициатива попадёт в раздел Архив, связь с Jira сохраняется».
- **Restore:** Popconfirm «Вернуть в активный бэклог?». On 409, `notification.error` with the server message.

### «Обновить с Jira» notification
Extended: «Перечитано из Jira: K · Создано: X · Обновлено: Y · Архивировано: Z · Восстановлено: W».

## Tests

### Backend (`pytest`)
`tests/test_backlog_service.py`:
- Category flip `initiatives_rfa → archive` → `archived_at` set, `issue_id` preserved, allocations untouched.
- Category flip `archive → initiatives_rfa` → `archived_at = None` (auto-restore).
- Category flip on item with approved allocation → archived_at set, allocation preserved (no 409 — this is category-driven, not user-initiated delete).

`tests/test_api_backlog.py`:
- `GET /backlog?view=active` excludes archived and approved-allocated rows.
- `GET /backlog?view=archived` returns only archived.
- `GET /backlog?view=in_work` returns only rows with approved allocations, `approved_scenarios` populated.
- `POST /backlog/{id}/archive` on active → 200, `archived_at` set.
- `POST /backlog/{id}/archive` on in_work → 422.
- `POST /backlog/{id}/restore` on archived with `Issue.category='initiatives_rfa'` → 200.
- `POST /backlog/{id}/restore` on archived with `Issue.category='archive'` → 409.
- `POST /backlog/refresh-from-jira` with a category flip → response contains `archived` / `restored` counts.

Existing tests asserting soft-unlink / auto-delete behaviour are updated to new archive contract.

### Frontend (Playwright)
Extend `backlog` E2E spec:
- Archive an active initiative → leaves Активные, appears in Архив, tab counts update.
- Restore an archived initiative → leaves Архив, returns to Активные.
- Approved allocation hides item from Активные and surfaces it on «В работе» with scenario link.

## Backward compatibility

- `GET /backlog` without `view` defaults to `active` — existing frontend builds keep working.
- `RefreshResponse` keeps `created/updated/removed/jira_refreshed`; `archived/restored` are additive.
- Legacy soft-unlinked rows remain in active backlog as manual ideas (see «Legacy data»).

## Out of scope

- Auto-repair of legacy soft-unlinked rows (would require title-matching heuristics).
- «Ручная архивация» of an item that is currently `in_work` — blocked by design; PM must edit the scenario first.
- Cascade archive of subtree when an epic is archived — epics, stories and tasks are categorised independently, so each individual initiative gets its own archive/restore flow.
