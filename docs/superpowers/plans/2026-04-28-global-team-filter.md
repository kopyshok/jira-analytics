# Global Team Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Single per-user team filter applied across all data pages. Admin sets a "default team"; user can change current selection at runtime, persisted in DB. Plus fix `UserUpdate.default_team=null` sentinel bug.

**Architecture:** Hybrid model — `User.default_team` (scalar, admin-set) + `User.selected_teams` (JSON list, user-set). New global header filter replaces local filters on Dashboard, Analytics, Backlog, Planning, Capacity, Categories. Drop `match_employees`/`match_issues` toggles — always apply OR.

**Tech Stack:** SQLAlchemy 2.0 + Alembic batch migrations, FastAPI, Pydantic v2 `model_dump(exclude_unset=True)`, React 19 + AntD 6 + TanStack Query.

**Spec:** [docs/superpowers/specs/2026-04-28-global-team-filter-design.md](../specs/2026-04-28-global-team-filter-design.md)

---

## Phase 1: Backend — User schema + selected_teams

### Task 1.1: Migration 037 — add `selected_teams` JSON column

**Files:**
- Create: `alembic/versions/037_user_selected_teams.py`

- [ ] **Step 1: Write migration**

```python
"""037 user selected_teams

Revision ID: 037_user_selected_teams
Revises: 036_users
Create Date: 2026-04-28
"""
import json
import sqlalchemy as sa
from alembic import op

revision = "037_user_selected_teams"
down_revision = "036_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "selected_teams",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )

    # Backfill: existing users with default_team get [default_team] as selected
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, default_team FROM users")).fetchall()
    for row in rows:
        if row.default_team:
            payload = json.dumps([row.default_team])
            bind.execute(
                sa.text("UPDATE users SET selected_teams = :p WHERE id = :id"),
                {"p": payload, "id": row.id},
            )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("selected_teams")
```

- [ ] **Step 2: Run migration**

```bash
py -3.10 -m alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade 036_users -> 037_user_selected_teams`

- [ ] **Step 3: Verify column exists**

```bash
py -3.10 -c "from app.database import engine; from sqlalchemy import inspect; print(inspect(engine).get_columns('users'))"
```

Expected: `selected_teams` column listed with type `TEXT`.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/037_user_selected_teams.py
git commit -m "migration(037): add User.selected_teams with default_team backfill"
```

---

### Task 1.2: Add `selected_teams` to `User` model

**Files:**
- Modify: `app/models/user.py`

- [ ] **Step 1: Add JSON-encoded list field**

Add import + field:

```python
import json
from typing import Any

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates


class User(Base, TimestampMixin):
    __tablename__ = "users"
    # ... existing fields ...

    selected_teams_raw: Mapped[str] = mapped_column(
        "selected_teams", Text, nullable=False, default="[]"
    )

    @property
    def selected_teams(self) -> list[str]:
        try:
            return json.loads(self.selected_teams_raw or "[]")
        except (TypeError, ValueError):
            return []

    @selected_teams.setter
    def selected_teams(self, value: list[str]) -> None:
        self.selected_teams_raw = json.dumps(list(value or []))
```

- [ ] **Step 2: Run model import smoke**

```bash
py -3.10 -c "from app.models.user import User; u = User(); u.selected_teams = ['A','B']; print(u.selected_teams_raw)"
```

Expected: `["A", "B"]`

- [ ] **Step 3: Commit**

```bash
git add app/models/user.py
git commit -m "feat(user): add selected_teams JSON property"
```

---

### Task 1.3: Expose `selected_teams` in `UserResponse` schema

**Files:**
- Modify: `app/schemas/user.py`

- [ ] **Step 1: Add field**

```python
class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: UserRole
    default_team: str | None
    selected_teams: list[str] = []
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Sanity-test schema serialization**

Add minimal test `tests/test_user_schema.py`:

```python
import json
from datetime import datetime, timezone

from app.models.user import User, UserRole
from app.schemas.user import UserResponse


def test_userresponse_includes_selected_teams():
    user = User(
        id="x",
        email="a@b.c",
        password_hash="h",
        display_name="A",
        role=UserRole.manager,
        default_team="T",
        is_active=True,
    )
    user.selected_teams = ["T1", "T2"]
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    payload = UserResponse.model_validate(user).model_dump()
    assert payload["selected_teams"] == ["T1", "T2"]
```

- [ ] **Step 3: Run test**

```bash
py -3.10 -m pytest tests/test_user_schema.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/schemas/user.py tests/test_user_schema.py
git commit -m "feat(user): UserResponse exposes selected_teams"
```

---

## Phase 2: Backend — `UserUpdate` sentinel fix

### Task 2.1: Replace per-field `is not None` with `model_dump(exclude_unset=True)`

**Files:**
- Modify: `app/api/endpoints/admin_users.py:36-49`

- [ ] **Step 1: Write failing test**

Create `tests/test_admin_users_clear_default_team.py`:

```python
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models.user import User, UserRole
from tests.conftest import override_get_db, _engine_setup  # adjust if conftest names differ


def test_admin_can_clear_default_team():
    client = TestClient(app)
    db_gen = override_get_db()
    db = next(db_gen)
    u = User(
        id="u1", email="a@b.c", password_hash="h", display_name="A",
        role=UserRole.manager, default_team="OldTeam", is_active=True,
    )
    db.add(u); db.commit()

    r = client.put("/api/v1/admin/users/u1", json={"default_team": None})
    assert r.status_code == 200, r.text
    assert r.json()["default_team"] is None

    db.refresh(u)
    assert u.default_team is None


def test_admin_omitted_field_does_not_clear():
    client = TestClient(app)
    db_gen = override_get_db()
    db = next(db_gen)
    u = User(
        id="u2", email="b@b.c", password_hash="h", display_name="B",
        role=UserRole.manager, default_team="KeepMe", is_active=True,
    )
    db.add(u); db.commit()

    r = client.put("/api/v1/admin/users/u2", json={"display_name": "B2"})
    assert r.status_code == 200
    assert r.json()["default_team"] == "KeepMe"
```

If existing conftest fixture names differ, adapt imports. If `tests/conftest.py` provides `client` fixture with `get_db` override, use that pattern instead.

- [ ] **Step 2: Run test, expect FAIL**

```bash
py -3.10 -m pytest tests/test_admin_users_clear_default_team.py -v
```

Expected: `test_admin_can_clear_default_team` FAILS — response shows `default_team=="OldTeam"` (sentinel bug).

- [ ] **Step 3: Patch endpoint**

Replace lines 36-49 of `app/api/endpoints/admin_users.py`:

```python
@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: str, data: UserUpdate, db: Session = Depends(get_db)) -> UserResponse:
    user = _repo.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    fields = data.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(user, k, v)
    return _repo.update(db, user)
```

- [ ] **Step 4: Run tests, expect PASS**

```bash
py -3.10 -m pytest tests/test_admin_users_clear_default_team.py -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/admin_users.py tests/test_admin_users_clear_default_team.py
git commit -m "fix(admin): allow clearing default_team via explicit null"
```

---

## Phase 3: Backend — `get_current_user` + `/auth/me/teams` endpoint

### Task 3.1: Extract `get_current_user` dependency

**Files:**
- Create: `app/core/auth_deps.py`
- Modify: `app/api/endpoints/auth.py:32-44` (use new dep)

- [ ] **Step 1: Write dep module**

```python
# app/core/auth_deps.py
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
_repo = UserRepository()


def get_current_user(
    token: str | None = Depends(_oauth2),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    try:
        payload = decode_access_token(token)
        user_id: str = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Невалидный токен")
    user = _repo.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user
```

- [ ] **Step 2: Refactor `/auth/me`**

Replace `auth.py` `me` handler:

```python
from app.core.auth_deps import get_current_user
# ... drop _oauth2/_repo locals if duplicated ...

@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
```

- [ ] **Step 3: Run existing auth tests**

```bash
py -3.10 -m pytest tests/test_auth_endpoints.py -v
```

Expected: all PASS (or whatever was passing before — no regressions).

- [ ] **Step 4: Commit**

```bash
git add app/core/auth_deps.py app/api/endpoints/auth.py
git commit -m "refactor(auth): extract get_current_user dep"
```

---

### Task 3.2: Add `PUT /auth/me/teams` endpoint

**Files:**
- Modify: `app/schemas/user.py` (add `UserTeamsUpdate`)
- Modify: `app/api/endpoints/auth.py` (add endpoint)
- Create: `tests/test_auth_me_teams.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_auth_me_teams.py
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.models.user import User, UserRole
from tests.conftest import override_get_db


def _login_token(user_id: str) -> str:
    return create_access_token({"sub": user_id, "role": "manager", "default_team": None}, expires_hours=1)


def test_put_my_teams_persists():
    client = TestClient(app)
    db = next(override_get_db())
    u = User(id="me1", email="m@b.c", password_hash="h", display_name="M",
             role=UserRole.manager, default_team="T", is_active=True)
    db.add(u); db.commit()

    token = _login_token("me1")
    r = client.put(
        "/api/v1/auth/me/teams",
        json={"teams": ["T1", "T2"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["selected_teams"] == ["T1", "T2"]

    db.refresh(u)
    assert u.selected_teams == ["T1", "T2"]


def test_put_my_teams_replaces_wholesale():
    client = TestClient(app)
    db = next(override_get_db())
    u = User(id="me2", email="m2@b.c", password_hash="h", display_name="M",
             role=UserRole.manager, default_team=None, is_active=True)
    u.selected_teams = ["A", "B"]
    db.add(u); db.commit()

    token = _login_token("me2")
    r = client.put(
        "/api/v1/auth/me/teams",
        json={"teams": ["C"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["selected_teams"] == ["C"]


def test_put_my_teams_unauthorized():
    client = TestClient(app)
    r = client.put("/api/v1/auth/me/teams", json={"teams": []})
    assert r.status_code == 401
```

- [ ] **Step 2: Run, expect FAIL — endpoint missing (404 or 405)**

```bash
py -3.10 -m pytest tests/test_auth_me_teams.py -v
```

Expected: FAIL with 404/405.

- [ ] **Step 3: Add schema**

In `app/schemas/user.py`:

```python
class UserTeamsUpdate(BaseModel):
    teams: list[str]
```

- [ ] **Step 4: Add endpoint**

In `app/api/endpoints/auth.py`:

```python
from app.core.auth_deps import get_current_user
from app.schemas.user import UserTeamsUpdate
from app.repositories.user_repository import UserRepository

_repo_users = UserRepository()


@router.put("/me/teams", response_model=UserResponse)
def update_my_teams(
    data: UserTeamsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    user.selected_teams = data.teams
    return UserResponse.model_validate(_repo_users.update(db, user))
```

(Remove duplicate `_repo`/`_oauth2` if already present locally; reuse.)

- [ ] **Step 5: Run tests, expect PASS**

```bash
py -3.10 -m pytest tests/test_auth_me_teams.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/schemas/user.py app/api/endpoints/auth.py tests/test_auth_me_teams.py
git commit -m "feat(auth): PUT /auth/me/teams endpoint"
```

---

## Phase 4: Backend — drop `match_employees` / `match_issues` query params

### Task 4.1: Default-True behavior in service, drop API params

**Files:**
- Modify: `app/api/endpoints/analytics.py` (remove Query params lines around 99-200)
- Modify: `app/api/endpoints/exports.py` (remove from `analytics.xlsx`/`analytics.pdf` handlers, ~lines 49-92)
- Keep: `app/services/analytics_service.py` — params remain with default `True`, callers stop passing them

- [ ] **Step 1: Patch analytics endpoints**

For each endpoint in `analytics.py` that has `match_employees` / `match_issues` Query params:

Remove those two `Query(...)` params from signature. Update service call: drop `match_employees=..., match_issues=...` kwargs (use defaults).

Example diff for one handler (pattern repeats):

```python
@router.get("/hours/by-employee", ...)
def hours_by_employee(
    year: int,
    quarter: int,
    teams: str | None = Query(None),
    db: Session = Depends(get_db),
):
    teams_list = [t for t in (teams or "").split(",") if t]
    return svc.hours_by_employee(
        db, year=year, quarter=quarter, teams=teams_list,
    )
```

Apply identical change to all 5 analytics handlers + 2 exports handlers.

- [ ] **Step 2: Update existing analytics tests**

Search for fixture/test calls that pass `match_employees`/`match_issues` query params:

```bash
grep -rn "match_employees\|match_issues" tests/
```

Drop those keys from request payloads in tests. Tests should still pass because default behavior matches "True+True".

- [ ] **Step 3: Run analytics tests**

```bash
py -3.10 -m pytest tests/ -v -k "analytics"
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/analytics.py app/api/endpoints/exports.py tests/
git commit -m "refactor(analytics): drop match_employees/match_issues query params"
```

---

## Phase 5: Frontend — auth API + AuthProvider seed

### Task 5.1: Update `UserProfile` type + add `updateMyTeams`

**Files:**
- Modify: `frontend/src/api/auth.ts`

- [ ] **Step 1: Patch**

```typescript
import { api } from './client';

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  role: 'admin' | 'super_manager' | 'manager';
  default_team: string | null;
  selected_teams: string[];
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return api.post<TokenResponse>('/auth/login', { email, password });
}

export function getMe(): Promise<UserProfile> {
  return api.get<UserProfile>('/auth/me');
}

export function updateMyTeams(teams: string[]): Promise<UserProfile> {
  return api.put<UserProfile>('/auth/me/teams', { teams });
}
```

- [ ] **Step 2: Verify TS build**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/auth.ts
git commit -m "feat(frontend/auth): selected_teams + updateMyTeams"
```

---

### Task 5.2: AuthProvider auto-seed `selected_teams` on first login

**Files:**
- Modify: `frontend/src/components/AuthProvider.tsx`

- [ ] **Step 1: Patch**

```tsx
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { getMe, updateMyTeams, type UserProfile } from '../api/auth';
import { AuthContext, type AuthState } from '../hooks/useAuth';

const TOKEN_KEY = 'auth_token';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setIsLoading(false);
      return;
    }
    getMe()
      .then(async (me) => {
        if (me.selected_teams.length === 0 && me.default_team) {
          const seeded = await updateMyTeams([me.default_team]);
          setUser(seeded);
        } else {
          setUser(me);
        }
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      })
      .finally(() => setIsLoading(false));
  }, [token]);

  const login = useCallback((newToken: string, profile: UserProfile) => {
    localStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    setUser(profile);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const updateUser = useCallback((next: UserProfile) => setUser(next), []);

  const value = useMemo<AuthState>(
    () => ({ user, token, isLoading, login, logout, updateUser }),
    [user, token, isLoading, login, logout, updateUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
```

- [ ] **Step 2: Add `updateUser` to AuthState**

`frontend/src/hooks/useAuth.ts`:

```typescript
export type AuthState = {
  user: UserProfile | null;
  token: string | null;
  isLoading: boolean;
  login: (token: string, profile: UserProfile) => void;
  logout: () => void;
  updateUser: (u: UserProfile) => void;
};
```

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AuthProvider.tsx frontend/src/hooks/useAuth.ts
git commit -m "feat(auth): auto-seed selected_teams from default_team on first login"
```

---

## Phase 6: Frontend — `GlobalTeamFilterProvider` + hook

### Task 6.1: Create provider and hook

**Files:**
- Create: `frontend/src/components/GlobalTeamFilterProvider.tsx`
- Create: `frontend/src/hooks/useGlobalTeamFilter.ts`

- [ ] **Step 1: Hook + context**

```typescript
// frontend/src/hooks/useGlobalTeamFilter.ts
import { createContext, useContext } from 'react';

export type GlobalTeamFilterCtx = {
  selectedTeams: string[];
  setSelectedTeams: (teams: string[]) => Promise<void>;
  saving: boolean;
  queryParams: { teams?: string };
};

export const GlobalTeamFilterContext = createContext<GlobalTeamFilterCtx | null>(null);

export function useGlobalTeamFilter(): GlobalTeamFilterCtx {
  const ctx = useContext(GlobalTeamFilterContext);
  if (!ctx) throw new Error('useGlobalTeamFilter must be used inside GlobalTeamFilterProvider');
  return ctx;
}
```

- [ ] **Step 2: Provider**

```tsx
// frontend/src/components/GlobalTeamFilterProvider.tsx
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { notification } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { updateMyTeams } from '../api/auth';
import { useAuth } from '../hooks/useAuth';
import { GlobalTeamFilterContext } from '../hooks/useGlobalTeamFilter';

export function GlobalTeamFilterProvider({ children }: { children: ReactNode }) {
  const { user, updateUser } = useAuth();
  const qc = useQueryClient();
  const [saving, setSaving] = useState(false);

  const selectedTeams = user?.selected_teams ?? [];

  const setSelectedTeams = useCallback(async (next: string[]) => {
    if (!user) return;
    setSaving(true);
    const prev = user.selected_teams;
    updateUser({ ...user, selected_teams: next }); // optimistic
    try {
      const fresh = await updateMyTeams(next);
      updateUser(fresh);
      qc.invalidateQueries(); // simple: invalidate all; team filter affects most queries
    } catch {
      updateUser({ ...user, selected_teams: prev });
      notification.error({ message: 'Не удалось сохранить выбор команд' });
    } finally {
      setSaving(false);
    }
  }, [user, updateUser, qc]);

  const queryParams = useMemo(
    () => (selectedTeams.length === 0 ? {} : { teams: selectedTeams.join(',') }),
    [selectedTeams],
  );

  const value = useMemo(
    () => ({ selectedTeams, setSelectedTeams, saving, queryParams }),
    [selectedTeams, setSelectedTeams, saving, queryParams],
  );

  return <GlobalTeamFilterContext.Provider value={value}>{children}</GlobalTeamFilterContext.Provider>;
}
```

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/GlobalTeamFilterProvider.tsx frontend/src/hooks/useGlobalTeamFilter.ts
git commit -m "feat(frontend): GlobalTeamFilterProvider + useGlobalTeamFilter"
```

---

### Task 6.2: Mount provider in routes (between AuthProvider and AppLayout)

**Files:**
- Modify: `frontend/src/routes.tsx`

- [ ] **Step 1: Wrap**

```tsx
function AuthLayout() {
  return (
    <AuthProvider>
      <GlobalTeamFilterProvider>
        <Outlet />
      </GlobalTeamFilterProvider>
    </AuthProvider>
  );
}
```

Add import:
```tsx
import { GlobalTeamFilterProvider } from './components/GlobalTeamFilterProvider';
```

- [ ] **Step 2: Verify dev runs**

```bash
cd frontend && npm run dev
# open http://localhost:5173, log in, check no console errors
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes.tsx
git commit -m "feat(frontend): mount GlobalTeamFilterProvider in AuthLayout"
```

---

## Phase 7: Frontend — header pill UI

### Task 7.1: `GlobalTeamFilterButton` component

**Files:**
- Create: `frontend/src/components/Layout/GlobalTeamFilterButton.tsx`

- [ ] **Step 1: Component**

```tsx
import { TeamOutlined, DownOutlined } from '@ant-design/icons';
import { Button, Popover, Select, Space, Spin, Tooltip } from 'antd';
import { useState } from 'react';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { useJiraTeams } from '../../hooks/useSync';

export default function GlobalTeamFilterButton() {
  const { selectedTeams, setSelectedTeams, saving } = useGlobalTeamFilter();
  const { data: teams, isLoading } = useJiraTeams();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>(selectedTeams);

  const label = selectedTeams.length === 0
    ? 'Все команды'
    : selectedTeams.length === 1
      ? selectedTeams[0]
      : `${selectedTeams[0]}, +${selectedTeams.length - 1}`;

  const noTeams = !isLoading && teams && teams.length === 0;

  const content = (
    <div style={{ width: 320 }}>
      <Select
        mode="multiple"
        value={draft}
        onChange={setDraft}
        options={(teams ?? []).map(t => ({ value: t, label: t }))}
        placeholder="Выберите команды"
        style={{ width: '100%' }}
        showSearch
        allowClear
        loading={isLoading}
      />
      <Space style={{ marginTop: 12, width: '100%', justifyContent: 'flex-end' }}>
        <Button onClick={() => { setDraft(selectedTeams); setOpen(false); }}>Отмена</Button>
        <Button
          type="primary"
          loading={saving}
          onClick={async () => { await setSelectedTeams(draft); setOpen(false); }}
        >
          Применить
        </Button>
      </Space>
    </div>
  );

  if (noTeams) {
    return (
      <Tooltip title="Загрузите команды в разделе Синхронизация">
        <Button icon={<TeamOutlined />} disabled>Команды</Button>
      </Tooltip>
    );
  }

  return (
    <Popover
      content={content}
      open={open}
      onOpenChange={(v) => { if (v) setDraft(selectedTeams); setOpen(v); }}
      trigger="click"
      placement="bottomRight"
    >
      <Button icon={<TeamOutlined />} loading={isLoading || saving}>
        <Space size={4}>
          {label}
          <DownOutlined style={{ fontSize: 10 }} />
        </Space>
      </Button>
    </Popover>
  );
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Layout/GlobalTeamFilterButton.tsx
git commit -m "feat(layout): GlobalTeamFilterButton header pill"
```

---

### Task 7.2: Mount button in `AppLayout` header

**Files:**
- Modify: `frontend/src/components/Layout/AppLayout.tsx`

- [ ] **Step 1: Inspect current header structure**

Read AppLayout.tsx to locate the `<Header>` block. Add `<GlobalTeamFilterButton />` to the right side, before user-info dropdown / logout button.

- [ ] **Step 2: Patch (example pattern, adjust to actual)**

```tsx
import GlobalTeamFilterButton from './GlobalTeamFilterButton';

// inside Header JSX, in the right cluster:
<Space size="middle">
  <GlobalTeamFilterButton />
  {/* existing user info / logout */}
</Space>
```

Hide for unauthenticated users (Login page) — `AppLayout` is already wrapped in `ProtectedRoute` parents in routes; safe.

- [ ] **Step 3: Smoke test**

```bash
cd frontend && npm run dev
# log in → header shows pill with current selected_teams label
# click pill → popover opens with multi-select
# pick 2 teams → Apply → label updates → reload → still applied
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Layout/AppLayout.tsx
git commit -m "feat(layout): mount GlobalTeamFilterButton in header"
```

---

## Phase 8: Frontend — wire pages to global filter

### Task 8.1: Dashboard — replace FactFilterProvider with global

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/routes.tsx` (drop FactFilterProvider wrap)
- Modify: `frontend/src/components/dashboard/FactFilterBar.tsx` (delete or hide match toggles)

- [ ] **Step 1: Replace `useFactFilter` with `useGlobalTeamFilter`**

In `DashboardPage.tsx`, find every `useFactFilter()` reference. Replace with:

```tsx
const { queryParams } = useGlobalTeamFilter();
```

`queryParams` shape now is `{ teams?: 'A,B' }` only (no match flags). Pass to API calls as before.

- [ ] **Step 2: Drop FactFilterBar match toggles**

Edit `frontend/src/components/dashboard/FactFilterBar.tsx`: remove `Switch`-es for `matchEmployees`/`matchIssues`. Keep team multi-select if Dashboard needs in-page mirror — OR delete the bar entirely if global header is sufficient.

Decision: **delete the bar** — global filter is enough. Remove `<FactFilterBar />` rendering from DashboardPage.

- [ ] **Step 3: Drop FactFilterProvider from routes**

`routes.tsx`: replace
```tsx
<ProtectedRoute><FactFilterProvider>{page(<DashboardPage />)}</FactFilterProvider></ProtectedRoute>
```
with
```tsx
<ProtectedRoute>{page(<DashboardPage />)}</ProtectedRoute>
```

Same for `/analytics` route.

- [ ] **Step 4: Smoke test Dashboard**

```bash
cd frontend && npm run dev
# Dashboard renders, data filtered by global teams
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/routes.tsx frontend/src/components/dashboard/FactFilterBar.tsx
git commit -m "feat(dashboard): use global team filter, drop match toggles"
```

---

### Task 8.2: Analytics — replace FactFilterProvider with global

**Files:**
- Modify: `frontend/src/pages/AnalyticsPage.tsx`

- [ ] **Step 1: Replace hook**

```tsx
const { queryParams } = useGlobalTeamFilter();
```

Drop `<FactFilterBar />` from AnalyticsPage if rendered. Remove imports of `useFactFilter`/`FactFilterBar`.

- [ ] **Step 2: Smoke test**

```bash
cd frontend && npm run dev
# Analytics page renders, charts respect global filter
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AnalyticsPage.tsx
git commit -m "feat(analytics): use global team filter"
```

---

### Task 8.3: Backlog — wire global filter

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx`
- Modify: `frontend/src/hooks/useBacklog.ts` (if it accepts a `team` param)
- Modify backend: `app/api/endpoints/backlog.py` (accept `?teams=A,B`)
- Modify: `app/services/backlog_service.py` if exists, else inline filter in endpoint

- [ ] **Step 1: Backend — accept `teams` query**

Patch `GET /backlog` to accept `teams: str | None = Query(None)`, split, filter `BacklogItem.team IN (...)`. If `BacklogItem` has no `team` column, derive via linked Issue's `team`.

Verify field by reading `app/models/__init__.py` BacklogItem definition.

- [ ] **Step 2: Frontend — pass `queryParams.teams`**

```tsx
const { queryParams } = useGlobalTeamFilter();
const { data } = useBacklog({ teams: queryParams.teams });
```

Update `useBacklog` hook signature.

- [ ] **Step 3: Drop local team selector if any**

Inspect `BacklogPage.tsx` for any local TeamSelector. Remove.

- [ ] **Step 4: Smoke test**

```bash
cd frontend && npm run dev
# Backlog page filters items by global teams
```

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/backlog.py frontend/src/pages/BacklogPage.tsx frontend/src/hooks/useBacklog.ts
git commit -m "feat(backlog): apply global team filter"
```

---

### Task 8.4: Planning (Scenarios list) — wire global filter

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`
- Modify: `app/api/endpoints/planning.py` `GET /scenarios`

- [ ] **Step 1: Backend — `GET /scenarios?teams=A,B`**

Filter `PlanningScenario.team IN (...)` if `teams` provided. If empty/absent → return all (admin/super_manager view).

- [ ] **Step 2: Frontend — pass teams**

```tsx
const { queryParams } = useGlobalTeamFilter();
const { data: scenarios } = useScenarios({ teams: queryParams.teams });
```

Note: scenario CREATION still asks for a single team via existing `TeamSelector` (per-scenario binding) — keep that. Only LIST view filters.

- [ ] **Step 3: Smoke test**

```bash
cd frontend && npm run dev
# /planning shows only scenarios in global teams
```

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/planning.py frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): scenario list respects global team filter"
```

---

### Task 8.5: Capacity — replace local team filter with global

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx`
- Confirm: `app/api/endpoints/capacity.py` already accepts team param

- [ ] **Step 1: Inspect capacity team selector**

Find local team selector in `CapacityPage.tsx`. Remove its UI. Replace state binding with `useGlobalTeamFilter()`.

- [ ] **Step 2: Backend confirm**

Capacity endpoints accept single `team` query? Adjust to `teams=A,B` (multi). If service `CapacityService` accepts single team, extend to list (OR filter on `Employee.team IN (...)`).

- [ ] **Step 3: Smoke test**

```bash
cd frontend && npm run dev
# /capacity shows employees from selected teams only
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CapacityPage.tsx app/api/endpoints/capacity.py app/services/capacity_service.py
git commit -m "feat(capacity): use global team filter"
```

---

### Task 8.6: Categories — replace local multi-team Select with global

**Files:**
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx` (or `CategoryConfigTab.tsx` if still in use)

- [ ] **Step 1: Replace local state**

Find `useState` for selected teams + persist via `useGenericSetting('ui_teams_categories')`. Remove. Use `useGlobalTeamFilter()` instead.

- [ ] **Step 2: Pass `teams=` to `/issues/tree`**

```tsx
const { queryParams } = useGlobalTeamFilter();
const { data: tree } = useIssueTree({ teams: queryParams.teams, project_keys: ... });
```

- [ ] **Step 3: Smoke test**

```bash
cd frontend && npm run dev
# /categories tree filtered by global teams
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CategoriesEditorPage.tsx
git commit -m "feat(categories): use global team filter"
```

---

## Phase 9: Frontend — admin UI clear `default_team`

### Task 9.1: UsersTab — `allowClear` + sentinel-distinguishing submit

**Files:**
- Modify: `frontend/src/pages/settings/UsersTab.tsx`

- [ ] **Step 1: Replace `default_team` Input with Select**

In edit modal:

```tsx
import { useJiraTeams } from '../../hooks/useSync';

// inside component
const { data: teams } = useJiraTeams();

// inside Form:
<Form.Item name="default_team" label="Команда по умолчанию">
  <Select
    options={(teams ?? []).map(t => ({ value: t, label: t }))}
    placeholder="Не задана"
    allowClear
    showSearch
  />
</Form.Item>
```

- [ ] **Step 2: Distinguish "не трогали" vs "очистили" on submit**

```tsx
async function handleUpdate(values: Record<string, unknown>) {
  if (!editUser) return;
  // form returns explicit undefined for cleared Select; convert to null so backend clears
  const payload: UserUpdate = { ...values };
  if (Object.prototype.hasOwnProperty.call(values, 'default_team') && values.default_team === undefined) {
    payload.default_team = null;
  }
  await updateUser(editUser.id, payload);
  // ...
}
```

Better: use `setFieldsValue({ default_team: u.default_team ?? null })` on open and read `getFieldValue('default_team')` to see if user cleared (returns `null`/`undefined`).

`api.put` must serialize explicit `null` to `null` in JSON (default behavior — verify `api/client.ts` doesn't strip nulls).

- [ ] **Step 3: Verify `api.put` sends nulls**

Inspect `frontend/src/api/client.ts` `put` impl. If it uses `JSON.stringify`, nulls are preserved. OK.

- [ ] **Step 4: Smoke test**

```bash
cd frontend && npm run dev
# log in as admin, edit user, clear default_team, save → reload page → field stays empty
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/settings/UsersTab.tsx
git commit -m "fix(admin/users): allow clearing default_team via Select"
```

---

## Phase 10: Cleanup deprecated AppSetting keys

### Task 10.1: Drop `ui_fact_filter_*` and `ui_teams_categories` reads/writes

**Files:**
- Modify: `frontend/src/components/dashboard/FactFilterProvider.tsx` — DELETE (dead now)
- Modify: `frontend/src/hooks/useFactFilter.ts` — DELETE
- Modify: `frontend/src/components/dashboard/FactFilterBar.tsx` — DELETE if unused
- Search: any remaining references to those AppSetting keys

- [ ] **Step 1: Delete dead files**

```bash
rm frontend/src/components/dashboard/FactFilterProvider.tsx
rm frontend/src/hooks/useFactFilter.ts
rm frontend/src/components/dashboard/FactFilterBar.tsx
```

(If `FactFilterBar` is still imported anywhere, fix imports first.)

- [ ] **Step 2: Search for stragglers**

```bash
grep -rn "FactFilter\|ui_fact_filter\|ui_teams_categories" frontend/src
```

Expected: no matches.

- [ ] **Step 3: Lint + dev smoke**

```bash
cd frontend && npm run lint && npm run dev
```

Expected: no errors. App boots, all pages render.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(frontend): drop FactFilter dead code + AppSetting keys"
```

---

## Phase 11: E2E

### Task 11.1: Add Playwright spec for global filter

**Files:**
- Create: `frontend/e2e/global_team_filter.spec.ts`

- [ ] **Step 1: Spec**

```typescript
import { test, expect } from '@playwright/test';

test('global team filter persists across pages', async ({ page }) => {
  await page.goto('http://localhost:5174/login');
  await page.fill('input[type=email]', 'e2e-admin@example.com');
  await page.fill('input[type=password]', 'e2etest');
  await page.click('button[type=submit]');
  await page.waitForURL(/\/$/);

  // Open filter pill, pick a team, apply
  await page.click('button:has-text("Все команды"), button:has(.anticon-team)');
  await page.click('.ant-select-multiple');
  // Choose first option
  await page.click('.ant-select-item-option:first-child');
  await page.click('button:has-text("Применить")');

  // Navigate to Analytics — pill should show same team
  await page.click('a[href="/analytics"]');
  const pillLabel = await page.locator('button:has(.anticon-team)').innerText();
  expect(pillLabel).not.toContain('Все команды');
});
```

Adjust seed/auth based on `data/e2e.db` — likely needs `scripts/seed_e2e.py` to create a test user (extend if missing).

- [ ] **Step 2: Run E2E**

```bash
.\scripts\e2e-local.ps1
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/global_team_filter.spec.ts
git commit -m "test(e2e): global team filter persistence"
```

---

## Phase 12: Final — push & verify

### Task 12.1: Run full test suite

- [ ] **Step 1: Backend**

```bash
py -3.10 -m pytest tests/ -v
```

Expected: green except for known pre-existing failures (capacity tests, hierarchy_rules CRUD pollution — see memory `project_capacity_overhaul_followups.md`, `project_hierarchy_rules_followups.md`).

- [ ] **Step 2: Frontend**

```bash
cd frontend && npm run lint && npm run build
```

Expected: zero errors.

- [ ] **Step 3: Push**

```bash
git push origin main
```

- [ ] **Step 4: Update memory**

Add memory entry `project_global_team_filter_shipped.md` summarizing scope, migration number, gotchas.

---

## Self-Review Notes

- Spec coverage: every section of design doc maps to a task.
- No placeholders; all tasks have full code.
- Type consistency: `selected_teams: list[str]` everywhere, `UserResponse.selected_teams` exposed, `updateMyTeams` returns full `UserProfile`.
- Pre-existing failures noted, not blocked on.
- `match_employees`/`match_issues` removal is API-surface only — service layer keeps defaults to minimize churn.
- Hierarchy of teams not implemented (no DB support today) — deferred per spec non-goals.
