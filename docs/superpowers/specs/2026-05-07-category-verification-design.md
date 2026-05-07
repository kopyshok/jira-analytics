# Category Verification — Design Spec
Date: 2026-05-07

## Problem

After Jira sync, new issues are auto-categorized by inheriting their parent's `assigned_category` via `CategoryResolver`. They immediately appear in "Активный стек" / "Архив" tabs without any human review. PM cannot verify that the auto-assignment is correct before the issue is treated as categorized.

## Goal

Add a lightweight verification step: all newly synced issues land in "Стек задач к разбору" (already exists as a tab). PM reviews, optionally corrects the category, clicks "Подтвердить" → issue moves to the correct tab.

---

## Data Model Changes

### `Issue` — two new fields

```
category_verified:          Boolean, NOT NULL, DEFAULT TRUE
require_child_verification: Boolean, NOT NULL, DEFAULT FALSE
```

**`category_verified`**
- `TRUE` on existing rows (migration default) — treated as already verified
- `FALSE` on every newly synced issue (set by sync service when creating a new Issue row)
- Setting `TRUE` is the confirmation action

**`require_child_verification`**
- Per-issue flag, only semantically meaningful on parent issues (epics, tasks with subtasks)
- `FALSE` (default): when a new child appears under an already-verified parent, the child is also auto-verified (inherits trust from parent)
- `TRUE`: new children always land in the stack regardless of parent's verified state
- Stored on the parent issue; checked during sync when creating child issues

### Migration

Single Alembic migration (batch mode for SQLite):
```
ALTER TABLE issues ADD COLUMN category_verified BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE issues ADD COLUMN require_child_verification BOOLEAN NOT NULL DEFAULT FALSE;
```

Existing issues get `category_verified = TRUE` → no disruption to current data.

---

## Sync Behavior Changes

In `SyncService` (or wherever Issue rows are created/upserted):

When creating a **new** Issue (not previously in DB):
1. Look up parent's `category_verified` and `require_child_verification`
2. If parent exists AND `category_verified = TRUE` AND `require_child_verification = FALSE`:
   → Set `category_verified = TRUE` on child (auto-trust)
3. Otherwise (no parent, parent unverified, or `require_child_verification = TRUE`):
   → Set `category_verified = FALSE` on child → lands in stack

When **updating** an existing Issue (already in DB): do NOT touch `category_verified`.

---

## Tab Routing Change

Currently `matchesTab()` in `SyncPage.tsx` uses `effective` (computed) category to route issues.

New rule: **`category_verified = FALSE` overrides all routing → always stack tab**, regardless of category value.

```typescript
// pseudo-code
function matchesTab(effective: string | null, verified: boolean, tab: InnerTab): boolean {
  if (!verified) return tab === 'stack';
  // existing logic unchanged
  switch (tab) {
    case 'stack': return effective === null;
    case 'active': return effective !== null && !ARCHIVE_CODES.has(effective) && effective !== INITIATIVES_CODE;
    ...
  }
}
```

The "Стек задач к разбору" badge count = unverified issues + currently-null-category issues.

---

## New API Endpoint

```
POST /issues/{issue_id}/verify
Body: {
  require_child_verification: bool   // saves to this issue's flag
  cascade: bool                      // if true, also verify all unverified descendants
}
Response: {
  ok: true,
  verified_count: int                // 1 + number of cascaded children
}
```

Side effects:
- Sets `category_verified = TRUE` on the issue
- Sets `require_child_verification` on the issue
- If `cascade = TRUE`: sets `category_verified = TRUE` on all descendant issues where `category_verified = FALSE`
- Publishes `entity_changed` event for UI invalidation

Category change before confirm: still uses existing `PUT /issues/{issue_id}/category` or `PUT /issues/batch-category`. No new endpoint needed for that.

---

## Frontend Changes

### "Стек задач к разбору" tab

New columns added to the issue table in this tab:

**Column: "Категория"** (already exists — editable `Select`)
- No change to existing functionality
- Child rows with inherited category show `↑ Тех долг` in muted style
- Child rows with PM-overridden category show full select widget + "изменено PM" hint

**Column: "Верифиц. детей"** (new)
- Toggle (AntD `Switch`) — only rendered for parent rows (issues that have children)
- Child rows show `—`
- Default: OFF (`require_child_verification = FALSE`)
- Toggling saves optimistically; persists on "Подтвердить"

**Column: "Действие"** (new)
- Parent rows: primary button **"Подтвердить +N дочерних"** (N = count of unverified children)
  - Calls `POST /issues/{id}/verify` with `{ cascade: true, require_child_verification: <toggle state> }`
- Child rows: ghost button **"Подтвердить"**
  - Calls `POST /issues/{id}/verify` with `{ cascade: false, require_child_verification: false }`

**Bulk action bar** (already has selection mechanism):
- When rows selected: shows "Подтвердить выбранные" button
- Calls `POST /verify` for each selected issue individually, no cascade
- Note: bulk does NOT cascade (user selects what to confirm explicitly)

### Other tabs (Активный стек, Архив, etc.)

No change. Verified issues behave exactly as before.

---

## Cascade Logic Detail

"Cascade" on parent confirm:
1. Find all descendant issues where `category_verified = FALSE`
2. Set `category_verified = TRUE` on all of them
3. Do NOT override their categories — they keep whatever `category` / `assigned_category` they already have

This means: if a child had its category corrected by PM before the parent was confirmed, the correction is preserved.

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| Parent synced as unverified, child synced later | Child is also unverified (parent unverified → `require_child_verification` check fails at step 1) |
| Parent verified with toggle OFF, new child appears in next sync | Child auto-verified (parent `require_child_verification = FALSE`) |
| Parent verified with toggle ON, new child appears in next sync | Child goes to stack |
| PM changes child's category before confirming parent | Cascade sets `category_verified = TRUE` on child; category change is preserved |
| Issue has `assigned_category = NULL` and `category_verified = FALSE` | Goes to stack (unverified takes priority) |
| Issue has `assigned_category = NULL` and `category_verified = TRUE` | Goes to stack (existing behavior: null effective category) |

---

## What Does NOT Change

- `CategoryResolver` logic — unchanged
- `MappingService.recalculate_all()` — unchanged
- All existing category CRUD endpoints — unchanged
- Existing "Стек задач к разбору" behavior for null-category issues — unchanged (they stay there; verified = TRUE but effective = null)
- All other tabs — unchanged
- "Активный стек" / "Архив" tabs don't get a verify column — only the stack tab

---

## Visual Style

Matches existing AntD 6 dark theme. Primary color `#177ddc`, ghost buttons with `#434343` border.
Toggle: AntD `Switch` component. Parent confirm button: `type="primary"`. Child confirm: `type="default"`.
