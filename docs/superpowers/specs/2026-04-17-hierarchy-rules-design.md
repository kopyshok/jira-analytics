# Hierarchy Rules + `/settings` Page — Design Spec

> Status: design, awaiting user review before implementation plan.
> Author: session 2026-04-17.

## Goal

Let the PM configure how root-level Jira issues classify into "containers" (stay as tree roots) vs "leaf operational tasks" (collapse into the `__operations__` virtual group). Today it's hardcoded in `app/api/endpoints/issue_config.py` as `CONTAINER_ISSUE_TYPES = {"Эпик", "Epic", "Инициатива", "История", ...}` — new user requirements (e.g. "ITL without RFA parent should be a container") can't be expressed without code changes. Make it a user-editable table of rules with first-match-wins evaluation, seeded with current behaviour + the pending ITL/RFA/PRJ requests.

As part of the same drop, extract admin surfaces from `/sync` into a dedicated `/settings` page — so daily triage (`CategoryConfigTab` + `SyncControls`) stays lean and infrequent admin (Jira creds, scope, field IDs, hierarchy rules) lives apart.

## Non-Goals

- Full predicate engine (no boolean composition, no regex, no per-team overrides).
- Reshaping the tree by detaching Jira-side `parent_id` relationships. Rules only affect the root-vs-operations classification; children under explicit parents continue to nest normally.
- Migrating the Category table CRUD UI (out of scope — categories remain seed-managed).
- Multi-user authn/authz or audit log (explicitly deferred — see "Production Readiness Follow-ups").

## User Flow

1. User opens `/settings` from Sider. Lands on the Rules tab by default (or remembers last tab).
2. Sees a table of rules: `priority | project | issue type | no parent | is container | enabled | description | actions`.
3. Can add a rule via "+ Правило". Empty `project`/`issue_type` fields mean "any". Priority defaults to `100` (lower than seed defaults).
4. Can edit any row inline — changes are staged locally; "Сохранить" writes the batch.
5. Can drag rows to reorder (updates `priority` in 10-step increments).
6. Can toggle `is_enabled` to mute a rule without deleting.
7. On save, subsequent loads of `/issues/tree` use the new rules immediately.

## Architecture

### Data Model

New table `hierarchy_rule`:

| column | type | notes |
|---|---|---|
| `id` | String(36) PK | uuid |
| `priority` | Integer, not null, indexed | lower = evaluated first; ties broken by `created_at` |
| `project_key` | String(32), nullable | `NULL` = any project |
| `issue_type` | String(128), nullable | `NULL` = any type |
| `require_no_parent` | Boolean, not null, default false | when true, rule matches only issues without `parent_id` |
| `is_container` | Boolean, not null | rule's verdict when it matches |
| `is_enabled` | Boolean, not null, default true | disabled rules are skipped during evaluation |
| `description` | String(255), nullable | optional human note ("ITL без RFA — контейнер") |
| `created_at`, `updated_at` | DateTime, not null | standard timestamps |

No composite unique — multiple rules with the same `(priority, project_key, issue_type)` are allowed (user may want variations on `require_no_parent`).

### Rule Evaluator

Module: `app/services/hierarchy_rules.py`.

```python
@dataclass(frozen=True)
class EvaluationInput:
    project_key: str
    issue_type: str
    has_parent: bool

def load_rules(db: Session) -> list[HierarchyRule]:
    """Enabled rules, ordered by (priority ASC, created_at ASC)."""

def classify(rules: list[HierarchyRule], input_: EvaluationInput) -> bool:
    """Return is_container. First-match-wins. Default False when no rule matches."""
    for rule in rules:
        if rule.project_key and rule.project_key != input_.project_key:
            continue
        if rule.issue_type and rule.issue_type != input_.issue_type:
            continue
        if rule.require_no_parent and input_.has_parent:
            continue
        return rule.is_container
    return False
```

Rules are loaded once per `/issues/tree` request (small table, no caching complexity).

### Endpoint Changes

**Tree endpoint** (`app/api/endpoints/issue_config.py`):

- Remove `CONTAINER_ISSUE_TYPES` constant.
- In the "split top-level" block (currently lines 186-211), replace:
  ```python
  is_container = r.issue_type in CONTAINER_ISSUE_TYPES
  ```
  with:
  ```python
  is_container = classify(rules, EvaluationInput(
      project_key=r.project_key,
      issue_type=r.issue_type,
      has_parent=False,  # we're only iterating roots here
  ))
  ```
- `has_parent=False` is correct here — the root-splitting loop only looks at items that already landed in `roots` (no parent in current tree). The `require_no_parent` switch is what distinguishes "ITL always root" from "ITL root only if truly parentless in Jira".

**New CRUD endpoints** (`app/api/endpoints/hierarchy_rules.py`):

| method | path | body | response |
|---|---|---|---|
| GET | `/hierarchy-rules` | — | `List[HierarchyRuleResponse]` (ordered by priority) |
| POST | `/hierarchy-rules` | `HierarchyRuleCreate` | `HierarchyRuleResponse` |
| PATCH | `/hierarchy-rules/{id}` | `HierarchyRuleUpdate` (all fields optional) | `HierarchyRuleResponse` |
| DELETE | `/hierarchy-rules/{id}` | — | `{status: "deleted"}` |
| POST | `/hierarchy-rules/reorder` | `{ids: [uuid1, uuid2, ...]}` | `List[HierarchyRuleResponse]` |

Reorder writes new `priority` values in steps of 10 starting at 10, preserving the submitted order.

### Seed

Migration 014 inserts the baseline. Existing install runs migration and immediately gets current behaviour preserved:

| priority | project | type | no_parent | is_container | description |
|---|---|---|---|---|---|
| 10 | ITL | — | ✓ | true | ITL без родителя — контейнер |
| 10 | RFA | — | — | true | RFA всегда контейнер |
| 10 | PRJ | — | — | true | PRJ всегда контейнер |
| 50 | — | Эпик | — | true | (was CONTAINER_ISSUE_TYPES) |
| 50 | — | Epic | — | true | |
| 50 | — | Инициатива | — | true | |
| 50 | — | Инициатива (E-com) | — | true | |
| 50 | — | Инициатива (Ритейл) | — | true | |
| 50 | — | Инициатива (Финансы) | — | true | |
| 50 | — | История | — | true | |
| 50 | — | Story | — | true | |
| 50 | — | Цель | — | true | |

Downgrade drops the table and restores the constant — harmless because code changes are reverted together.

### Frontend

#### Routing

- Add route `/settings` (lazy-loaded `SettingsPage.tsx`).
- Sider menu: new item "⚙ Настройки" above "Синхронизация".
- `/scope` redirect to `/sync` stays as-is.

#### `SettingsPage.tsx`

Four tabs (Ant Design `Tabs`) — tab key survives via URL hash (`/settings#hierarchy`):

1. **Подключение к Jira** (`connection`) — existing `ConnectionCard` extracted from `frontend/src/pages/SyncPage.tsx` into `frontend/src/components/ConnectionCard.tsx` so `SettingsPage` and any legacy consumer can import it.
2. **Проекты в scope** (`scope`) — existing `ScopeOverview` + `TaskSectionsTab` extracted from `SyncPage.tsx` into `frontend/src/components/ScopeAdmin.tsx`; scope summary on top, project browser below.
3. **Поля Jira** (`fields`) — new minimal form for `jira_team_field_id`, `jira_participating_teams_field_id`, `jira_goals_field_id`. Reads via `useGenericSetting`, writes via `useSaveGenericSetting` (both exist). Dropdown populated by `useJiraFields` (already wired).
4. **Правила иерархии** (`hierarchy`) — new `HierarchyRulesTab` component; see below.

#### `HierarchyRulesTab`

- Table with up/down reorder buttons per row for priority shifting. Drag-and-drop reorder is a deliberate follow-up — AntD v6 + React 19 ecosystem for row drag is fragmented (see [react-dnd + antd v6 thread](https://github.com/ant-design/ant-design/issues/44944)); shipping with buttons avoids a dependency risk and is perfectly adequate for a rule list that's rarely reordered.
- Columns: `↕ (drag handle)`, `Приоритет`, `Проект`, `Тип задачи`, `Без родителя`, `Контейнер`, `Активно`, `Описание`, `Удалить`.
- Inline editing: click-to-edit pattern via `Form.Item` per cell, or open row-level drawer. For the MVP go with a drawer to avoid multi-cell-edit conflicts.
- Above the table:
  - "+ Правило" button (opens drawer in create mode).
  - Status pill: "Синхронизировано" | "Несохранённые изменения: N".
  - "Сохранить" button visible when there are local changes; batches all dirty rows into sequential PATCHes.

Validation:
- `priority` must be integer ≥ 0.
- If both `project_key` and `issue_type` are null/empty → warn but allow (it's a catch-all rule).
- Duplicate `(priority, project_key, issue_type, require_no_parent)` across rules → warn but allow.

#### `/sync` after migration

Two tabs only:
1. `Категоризация задач` (renamed from `categories`) — current `CategoryConfigTab`.
2. `Синхронизация` (renamed from implicit third tab) — current `SyncControls`.

`ConnectionCard` and `ScopeOverview` are removed from `SyncPage.tsx` top area.

## Data Flow

```
User edits rule in /settings#hierarchy
        │
        ▼
HierarchyRulesTab stages changes locally
        │  «Сохранить»
        ▼
POST/PATCH/DELETE /hierarchy-rules
        │
        ▼
hierarchy_rule rows updated
        │
        ▼
Next /issues/tree request loads rules via load_rules()
        │
        ▼
classify() runs per root issue
        │
        ▼
Tree response has roots correctly split between real roots and __operations__
```

## Error Handling

- **Invalid rule payload** (e.g., `priority` < 0, both project+type null+explicit "catch-all")
  → 422 with field-level error; UI shows inline on the drawer.
- **Missing rule** on PATCH/DELETE → 404.
- **Classify with empty rules table** → all roots go to `__operations__`. This is the defined default, but would wipe the tree structure on a fresh install. Mitigation: migration 014 always seeds; if user manually truncates, they'll see empty tree and be prompted (future: `POST /hierarchy-rules/restore-defaults` — out of scope for this spec).
- **Race condition on reorder** (two tabs open): last write wins. No optimistic locking — mass-user impact is low since admin edits are rare.

## Testing

- `tests/test_hierarchy_rules_service.py`:
  - `classify` with empty rules → False.
  - First-match-wins by priority.
  - `project_key=NULL` wildcard matches all projects.
  - `issue_type=NULL` wildcard matches all types.
  - `require_no_parent=True` excludes issues with parent.
  - `is_container=False` rule correctly overrides a later `True` rule (explicit exception case).
  - Disabled rules skipped.
- `tests/test_hierarchy_rules_endpoints.py`:
  - CRUD happy path.
  - Reorder returns fresh order.
  - Validation: priority < 0 → 422.
- `tests/test_issue_tree_endpoint.py` (extend existing if present):
  - Tree with only seeded rules → behaviour matches pre-014 (backward compat).
  - After disabling all rules → all non-container roots go to operations group.
  - After adding `ITL` rule → ITL leaf roots stay as roots.
- Frontend: no new E2E — the hierarchy tab is admin surface, covered by unit-level logic tests.

## Production Readiness Follow-ups (deferred)

Not in this spec, worth tracking:

- **Audit log** — record who/when edited which rule; relevant when multiple PMs share a deployment.
- **Per-user or per-team rules** — today rules are global. Multi-team tenants may want scoping.
- **`POST /hierarchy-rules/restore-defaults`** — one-click re-seed if user deletes everything.
- **Import/export rules as JSON** — for sharing between installations.
- **`GET /issues/tree` full subtree count** (separate memory entry `project_full_subtree_count_planned.md`) — related but independent.

## Open Questions (resolved during brainstorming)

- Q: ITL "когда нет родителя RFA" — interpret conservatively or restructure tree? → Conservative (variant C in discussion): ITL without any parent is a root; with parent it naturally nests. No tree rewriting.
- Q: Hardcode vs configurable? → Configurable (rule table).
- Q: UI placement? → `/settings` page (full admin migration).
- Q: Matching semantics? → First-match-wins by priority ASC; `is_container=false` rules allowed for overrides.

## Rollout

Single PR, single commit after plan execution. No feature flag — the migration seeds and the endpoint swap happen atomically. Rollback = `alembic downgrade -1` + revert code.
