# Auth + Multi-User (Variant A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add email+password auth with JWT, user management UI, and auto-team-filter to turn the single-user app into a shared service for ~6 managers.

**Architecture:** Variant A — frontend-protected. JWT issued on login, stored in `localStorage`, sent as Bearer token in all API calls. Backend `/auth/` and `/admin/users/` endpoints validate tokens only on those routes; all other endpoints remain open (no middleware). Variant B will add `Depends(get_current_user)` to every endpoint as a follow-up.

**Tech Stack:** `python-jose[cryptography]`, `passlib[bcrypt]` (backend); React Context + localStorage, AntD 6 Form/Table/Modal (frontend); Alembic migration `036_users`

**Spec:** `docs/superpowers/specs/2026-04-27-auth-multiuser-design.md`

---

## File Map

**Create (backend):**
- `app/models/user.py` — User model + UserRole enum
- `app/core/__init__.py` — empty (if missing)
- `app/core/security.py` — bcrypt hash/verify + JWT encode/decode
- `app/repositories/user_repository.py` — DB queries for User
- `app/schemas/user.py` — LoginRequest, TokenResponse, UserResponse, UserCreate, UserUpdate, PasswordReset
- `app/api/endpoints/auth.py` — POST /auth/login, GET /auth/me
- `app/api/endpoints/admin_users.py` — CRUD /admin/users/
- `alembic/versions/036_users.py` — create users table
- `scripts/create_admin.py` — seed first admin
- `tests/test_user_model.py`
- `tests/test_security.py`
- `tests/test_user_repository.py`
- `tests/test_auth.py`
- `tests/test_admin_users.py`

**Create (frontend):**
- `frontend/src/hooks/useAuth.ts` — AuthContext + useAuth hook
- `frontend/src/components/AuthProvider.tsx` — wraps app, loads user on startup
- `frontend/src/pages/LoginPage.tsx` — /login page
- `frontend/src/api/auth.ts` — login(), getMe()
- `frontend/src/api/adminUsers.ts` — users CRUD
- `frontend/src/pages/settings/UsersTab.tsx` — admin user management

**Modify:**
- `requirements.txt`
- `app/config.py` — add `jwt_secret_key`, `jwt_expire_hours`, `admin_email`, `admin_password`
- `app/models/__init__.py` — export User
- `app/api/router.py` — add auth + admin/users routers
- `frontend/src/api/client.ts` — add Authorization header
- `frontend/src/routes.tsx` — add /login, wrap all routes with AuthProvider + ProtectedRoute
- `frontend/src/components/Layout/AppLayout.tsx` — user name + logout in header
- `frontend/src/pages/SettingsPage.tsx` — add users tab
- `.env.example`

---

## Task 1: Backend dependencies + config

**Files:** `requirements.txt`, `app/config.py`, `.env.example`

- [ ] **Step 1: Add packages to requirements.txt**

  Find the block with `fastapi`, `sqlalchemy` etc. and add:
  ```
  python-jose[cryptography]==3.3.0
  passlib[bcrypt]==1.7.4
  ```

- [ ] **Step 2: Install**
  ```bash
  pip install "python-jose[cryptography]==3.3.0" "passlib[bcrypt]==1.7.4"
  ```
  Expected: installs without errors.

- [ ] **Step 3: Add fields to Settings in app/config.py**

  Add after the last existing field (e.g. `jira_batch_size`):
  ```python
      # Auth
      jwt_secret_key: str = "dev-secret-change-in-production"
      jwt_expire_hours: int = 8

      # Admin seed (used by scripts/create_admin.py)
      admin_email: str = ""
      admin_password: str = ""
  ```

- [ ] **Step 4: Update .env.example**

  Add:
  ```
  # Auth
  JWT_SECRET_KEY=change-this-to-a-random-secret-in-production
  JWT_EXPIRE_HOURS=8

  # Admin seed (used by scripts/create_admin.py)
  ADMIN_EMAIL=admin@example.com
  ADMIN_PASSWORD=changeme
  ```

- [ ] **Step 5: Commit**
  ```bash
  git add requirements.txt app/config.py .env.example
  git commit -m "chore(auth): add python-jose, passlib; JWT config in Settings"
  ```

---

## Task 2: User model + migration

**Files:** `app/models/user.py`, `app/models/__init__.py`, `alembic/versions/036_users.py`

- [ ] **Step 1: Write failing import test**

  Create `tests/test_user_model.py`:
  ```python
  from app.models.user import User, UserRole

  def test_user_role_values():
      assert UserRole.admin == "admin"
      assert UserRole.super_manager == "super_manager"
      assert UserRole.manager == "manager"
  ```

  Run: `py -3.10 -m pytest tests/test_user_model.py -v`
  Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 2: Create app/models/user.py**
  ```python
  import uuid
  from datetime import datetime
  from enum import Enum as PyEnum

  from sqlalchemy import Boolean, DateTime, Enum, String, func
  from sqlalchemy.orm import Mapped, mapped_column

  from app.models.base import Base


  class UserRole(str, PyEnum):
      admin = "admin"
      super_manager = "super_manager"
      manager = "manager"


  class User(Base):
      __tablename__ = "users"

      id: Mapped[str] = mapped_column(
          String(36), primary_key=True, default=lambda: str(uuid.uuid4())
      )
      email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
      password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
      display_name: Mapped[str] = mapped_column(String(255), nullable=False)
      role: Mapped[UserRole] = mapped_column(
          Enum(UserRole, native_enum=False), nullable=False
      )
      default_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
      is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
      created_at: Mapped[datetime] = mapped_column(
          DateTime, default=func.now(), nullable=False
      )
      updated_at: Mapped[datetime] = mapped_column(
          DateTime, default=func.now(), onupdate=func.now(), nullable=False
      )
  ```

- [ ] **Step 3: Export from app/models/__init__.py**

  Add to existing imports:
  ```python
  from app.models.user import User, UserRole  # noqa: F401
  ```

- [ ] **Step 4: Run test**

  Run: `py -3.10 -m pytest tests/test_user_model.py -v`
  Expected: PASS

- [ ] **Step 5: Create alembic/versions/036_users.py**
  ```python
  """036 users table

  Revision ID: 036_users
  Revises: 035_sync_pipeline
  Create Date: 2026-04-27
  """
  import sqlalchemy as sa
  from alembic import op

  revision = "036_users"
  down_revision = "035_sync_pipeline"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      op.create_table(
          "users",
          sa.Column("id", sa.String(36), nullable=False),
          sa.Column("email", sa.String(255), nullable=False),
          sa.Column("password_hash", sa.String(255), nullable=False),
          sa.Column("display_name", sa.String(255), nullable=False),
          sa.Column(
              "role",
              sa.Enum("admin", "super_manager", "manager", name="userrole", native_enum=False),
              nullable=False,
          ),
          sa.Column("default_team", sa.String(255), nullable=True),
          sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
          sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
          sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
          sa.PrimaryKeyConstraint("id"),
      )
      op.create_index("ix_users_email", "users", ["email"], unique=True)


  def downgrade() -> None:
      op.drop_index("ix_users_email", table_name="users")
      op.drop_table("users")
  ```

- [ ] **Step 6: Apply migration**
  ```bash
  alembic upgrade head
  ```
  Expected: `Running upgrade 035_sync_pipeline -> 036_users`

- [ ] **Step 7: Commit**
  ```bash
  git add app/models/user.py app/models/__init__.py alembic/versions/036_users.py tests/test_user_model.py
  git commit -m "feat(auth): User model + migration 036_users"
  ```

---

## Task 3: Security utilities

**Files:** `app/core/__init__.py`, `app/core/security.py`, `tests/test_security.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/test_security.py`:
  ```python
  import pytest
  from jose import JWTError
  from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


  def test_hash_and_verify():
      hashed = hash_password("mysecret")
      assert hashed != "mysecret"
      assert verify_password("mysecret", hashed)
      assert not verify_password("wrong", hashed)


  def test_create_and_decode_token():
      payload = {"sub": "user-123", "role": "manager", "default_team": "Team A"}
      token = create_access_token(payload, expires_hours=1)
      decoded = decode_access_token(token)
      assert decoded["sub"] == "user-123"
      assert decoded["role"] == "manager"
      assert decoded["default_team"] == "Team A"


  def test_decode_invalid_token_raises():
      with pytest.raises(JWTError):
          decode_access_token("not.a.valid.token")
  ```

  Run: `py -3.10 -m pytest tests/test_security.py -v`
  Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 2: Create app/core/__init__.py** (if missing)
  ```bash
  type nul > app/core/__init__.py
  ```

- [ ] **Step 3: Create app/core/security.py**
  ```python
  from datetime import datetime, timedelta

  from jose import jwt
  from passlib.context import CryptContext

  from app.config import settings

  _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


  def hash_password(password: str) -> str:
      return _pwd_context.hash(password)


  def verify_password(plain: str, hashed: str) -> bool:
      return _pwd_context.verify(plain, hashed)


  def create_access_token(data: dict, expires_hours: int) -> str:
      to_encode = data.copy()
      to_encode["exp"] = datetime.utcnow() + timedelta(hours=expires_hours)
      return jwt.encode(to_encode, settings.jwt_secret_key, algorithm="HS256")


  def decode_access_token(token: str) -> dict:
      """Raises jose.JWTError if token is invalid or expired."""
      return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
  ```

- [ ] **Step 4: Run tests**

  Run: `py -3.10 -m pytest tests/test_security.py -v`
  Expected: 3 PASS

- [ ] **Step 5: Commit**
  ```bash
  git add app/core/__init__.py app/core/security.py tests/test_security.py
  git commit -m "feat(auth): security utils — bcrypt + JWT"
  ```

---

## Task 4: User repository + schemas

**Files:** `app/repositories/user_repository.py`, `app/schemas/user.py`, `tests/test_user_repository.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/test_user_repository.py`:
  ```python
  import uuid
  import pytest
  from sqlalchemy.orm import Session
  from app.core.security import hash_password
  from app.models.user import User, UserRole
  from app.repositories.user_repository import UserRepository


  @pytest.fixture
  def repo():
      return UserRepository()


  def _make(db: Session, email: str, role: UserRole = UserRole.manager) -> User:
      u = User(
          id=str(uuid.uuid4()),
          email=email,
          password_hash=hash_password("secret"),
          display_name="Test",
          role=role,
          is_active=True,
      )
      db.add(u)
      db.commit()
      return u


  def test_get_by_email_found(db_session, repo):
      _make(db_session, "a@x.com")
      found = repo.get_by_email(db_session, "a@x.com")
      assert found is not None
      assert found.email == "a@x.com"


  def test_get_by_email_not_found(db_session, repo):
      assert repo.get_by_email(db_session, "nobody@x.com") is None


  def test_get_by_id(db_session, repo):
      u = _make(db_session, "b@x.com")
      found = repo.get_by_id(db_session, u.id)
      assert found is not None


  def test_list_all(db_session, repo):
      _make(db_session, "c@x.com")
      _make(db_session, "d@x.com")
      assert len(repo.list_all(db_session)) >= 2
  ```

  Run: `py -3.10 -m pytest tests/test_user_repository.py -v`
  Expected: FAIL

- [ ] **Step 2: Create app/repositories/user_repository.py**
  ```python
  from sqlalchemy.orm import Session
  from app.models.user import User


  class UserRepository:
      def get_by_email(self, db: Session, email: str) -> User | None:
          return db.query(User).filter(User.email == email).first()

      def get_by_id(self, db: Session, user_id: str) -> User | None:
          return db.query(User).filter(User.id == user_id).first()

      def list_all(self, db: Session) -> list[User]:
          return db.query(User).order_by(User.created_at).all()

      def create(self, db: Session, user: User) -> User:
          db.add(user)
          db.commit()
          db.refresh(user)
          return user

      def update(self, db: Session, user: User) -> User:
          db.commit()
          db.refresh(user)
          return user
  ```

- [ ] **Step 3: Create app/schemas/user.py**
  ```python
  from __future__ import annotations
  from datetime import datetime
  from pydantic import BaseModel
  from app.models.user import UserRole


  class LoginRequest(BaseModel):
      email: str
      password: str


  class TokenResponse(BaseModel):
      access_token: str
      token_type: str = "bearer"


  class UserResponse(BaseModel):
      id: str
      email: str
      display_name: str
      role: UserRole
      default_team: str | None
      is_active: bool
      created_at: datetime
      updated_at: datetime

      model_config = {"from_attributes": True}


  class UserCreate(BaseModel):
      email: str
      password: str
      display_name: str
      role: UserRole
      default_team: str | None = None


  class UserUpdate(BaseModel):
      display_name: str | None = None
      role: UserRole | None = None
      default_team: str | None = None
      is_active: bool | None = None


  class PasswordReset(BaseModel):
      new_password: str
  ```

- [ ] **Step 4: Run tests**

  Run: `py -3.10 -m pytest tests/test_user_repository.py -v`
  Expected: 4 PASS

- [ ] **Step 5: Commit**
  ```bash
  git add app/repositories/user_repository.py app/schemas/user.py tests/test_user_repository.py
  git commit -m "feat(auth): UserRepository + Pydantic schemas"
  ```

---

## Task 5: Auth endpoints (login + me)

**Files:** `app/api/endpoints/auth.py`, `app/api/router.py`, `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/test_auth.py`:
  ```python
  import uuid
  from fastapi.testclient import TestClient
  from sqlalchemy.orm import Session

  from app.database import get_db
  from app.main import app
  from app.core.security import hash_password
  from app.models.user import User, UserRole


  def _make_client(db: Session) -> TestClient:
      app.dependency_overrides[get_db] = lambda: db
      return TestClient(app)


  def _teardown():
      app.dependency_overrides.clear()


  def _seed(db: Session, email: str, role: UserRole = UserRole.manager,
            team: str | None = "Team A", active: bool = True) -> User:
      u = User(
          id=str(uuid.uuid4()),
          email=email,
          password_hash=hash_password("password123"),
          display_name="Test",
          role=role,
          default_team=team,
          is_active=active,
      )
      db.add(u)
      db.commit()
      return u


  def test_login_success(testclient_db_session):
      _seed(testclient_db_session, "ok@example.com")
      client = _make_client(testclient_db_session)
      try:
          r = client.post("/api/v1/auth/login", json={"email": "ok@example.com", "password": "password123"})
          assert r.status_code == 200
          assert "access_token" in r.json()
          assert r.json()["token_type"] == "bearer"
      finally:
          _teardown()


  def test_login_wrong_password(testclient_db_session):
      _seed(testclient_db_session, "wp@example.com")
      client = _make_client(testclient_db_session)
      try:
          r = client.post("/api/v1/auth/login", json={"email": "wp@example.com", "password": "wrong"})
          assert r.status_code == 401
      finally:
          _teardown()


  def test_login_unknown_email(testclient_db_session):
      client = _make_client(testclient_db_session)
      try:
          r = client.post("/api/v1/auth/login", json={"email": "nope@example.com", "password": "x"})
          assert r.status_code == 401
      finally:
          _teardown()


  def test_login_inactive_user(testclient_db_session):
      _seed(testclient_db_session, "inactive@example.com", active=False)
      client = _make_client(testclient_db_session)
      try:
          r = client.post("/api/v1/auth/login", json={"email": "inactive@example.com", "password": "password123"})
          assert r.status_code == 403
      finally:
          _teardown()


  def test_me_returns_profile(testclient_db_session):
      _seed(testclient_db_session, "me@example.com", team="Team B")
      client = _make_client(testclient_db_session)
      try:
          login_r = client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": "password123"})
          token = login_r.json()["access_token"]
          r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
          assert r.status_code == 200
          assert r.json()["email"] == "me@example.com"
          assert r.json()["default_team"] == "Team B"
      finally:
          _teardown()


  def test_me_invalid_token(testclient_db_session):
      client = _make_client(testclient_db_session)
      try:
          r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token.here"})
          assert r.status_code == 401
      finally:
          _teardown()
  ```

  Run: `py -3.10 -m pytest tests/test_auth.py -v`
  Expected: FAIL — endpoint not found

- [ ] **Step 2: Create app/api/endpoints/auth.py**
  ```python
  from fastapi import APIRouter, Depends, HTTPException
  from fastapi.security import OAuth2PasswordBearer
  from jose import JWTError
  from sqlalchemy.orm import Session

  from app.config import settings
  from app.core.security import create_access_token, decode_access_token, verify_password
  from app.database import get_db
  from app.repositories.user_repository import UserRepository
  from app.schemas.user import LoginRequest, TokenResponse, UserResponse

  router = APIRouter()
  _oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
  _repo = UserRepository()


  @router.post("/login", response_model=TokenResponse)
  def login(data: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
      user = _repo.get_by_email(db, data.email)
      if not user or not verify_password(data.password, user.password_hash):
          raise HTTPException(status_code=401, detail="Неверный email или пароль")
      if not user.is_active:
          raise HTTPException(status_code=403, detail="Пользователь деактивирован")
      token = create_access_token(
          {"sub": user.id, "role": user.role.value, "default_team": user.default_team},
          expires_hours=settings.jwt_expire_hours,
      )
      return TokenResponse(access_token=token)


  @router.get("/me", response_model=UserResponse)
  def me(token: str | None = Depends(_oauth2), db: Session = Depends(get_db)) -> UserResponse:
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
      return UserResponse.model_validate(user)
  ```

- [ ] **Step 3: Register in app/api/router.py**

  Add import near other endpoint imports:
  ```python
  from app.api.endpoints import auth as auth_endpoints
  ```

  Add include before or after the last existing `include_router`:
  ```python
  api_router.include_router(auth_endpoints.router, prefix="/auth", tags=["auth"])
  ```

- [ ] **Step 4: Run tests**

  Run: `py -3.10 -m pytest tests/test_auth.py -v`
  Expected: 6 PASS

- [ ] **Step 5: Commit**
  ```bash
  git add app/api/endpoints/auth.py app/api/router.py tests/test_auth.py
  git commit -m "feat(auth): /auth/login + /auth/me endpoints"
  ```

---

## Task 6: Admin users endpoints

**Files:** `app/api/endpoints/admin_users.py`, `app/api/router.py`, `tests/test_admin_users.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/test_admin_users.py`:
  ```python
  import uuid
  from fastapi.testclient import TestClient
  from sqlalchemy.orm import Session

  from app.database import get_db
  from app.main import app
  from app.core.security import hash_password
  from app.models.user import User, UserRole


  def _make_client(db: Session) -> TestClient:
      app.dependency_overrides[get_db] = lambda: db
      return TestClient(app)


  def _teardown():
      app.dependency_overrides.clear()


  def _seed(db: Session, email: str) -> User:
      u = User(
          id=str(uuid.uuid4()),
          email=email,
          password_hash=hash_password("pass"),
          display_name="User",
          role=UserRole.manager,
          is_active=True,
      )
      db.add(u)
      db.commit()
      return u


  def test_list_users(testclient_db_session):
      _seed(testclient_db_session, "a@x.com")
      _seed(testclient_db_session, "b@x.com")
      client = _make_client(testclient_db_session)
      try:
          r = client.get("/api/v1/admin/users/")
          assert r.status_code == 200
          assert len(r.json()) >= 2
      finally:
          _teardown()


  def test_create_user(testclient_db_session):
      client = _make_client(testclient_db_session)
      try:
          r = client.post("/api/v1/admin/users/", json={
              "email": "new@x.com", "password": "secure123",
              "display_name": "New", "role": "manager", "default_team": "Team C",
          })
          assert r.status_code == 201
          data = r.json()
          assert data["email"] == "new@x.com"
          assert data["default_team"] == "Team C"
          assert "password_hash" not in data
      finally:
          _teardown()


  def test_create_duplicate_email(testclient_db_session):
      _seed(testclient_db_session, "dup@x.com")
      client = _make_client(testclient_db_session)
      try:
          r = client.post("/api/v1/admin/users/", json={
              "email": "dup@x.com", "password": "pass", "display_name": "D", "role": "manager",
          })
          assert r.status_code == 409
      finally:
          _teardown()


  def test_update_user(testclient_db_session):
      u = _seed(testclient_db_session, "upd@x.com")
      client = _make_client(testclient_db_session)
      try:
          r = client.put(f"/api/v1/admin/users/{u.id}", json={"display_name": "Updated"})
          assert r.status_code == 200
          assert r.json()["display_name"] == "Updated"
      finally:
          _teardown()


  def test_reset_password(testclient_db_session):
      u = _seed(testclient_db_session, "pwd@x.com")
      client = _make_client(testclient_db_session)
      try:
          r = client.post(f"/api/v1/admin/users/{u.id}/reset-password", json={"new_password": "newpass123"})
          assert r.status_code == 200
          login_r = client.post("/api/v1/auth/login", json={"email": "pwd@x.com", "password": "newpass123"})
          assert login_r.status_code == 200
      finally:
          _teardown()


  def test_update_not_found(testclient_db_session):
      client = _make_client(testclient_db_session)
      try:
          r = client.put("/api/v1/admin/users/nonexistent", json={"display_name": "X"})
          assert r.status_code == 404
      finally:
          _teardown()
  ```

  Run: `py -3.10 -m pytest tests/test_admin_users.py -v`
  Expected: FAIL

- [ ] **Step 2: Create app/api/endpoints/admin_users.py**
  ```python
  import uuid
  from fastapi import APIRouter, Depends, HTTPException
  from sqlalchemy.orm import Session

  from app.core.security import hash_password
  from app.database import get_db
  from app.models.user import User
  from app.repositories.user_repository import UserRepository
  from app.schemas.user import PasswordReset, UserCreate, UserResponse, UserUpdate

  router = APIRouter()
  _repo = UserRepository()


  @router.get("/", response_model=list[UserResponse])
  def list_users(db: Session = Depends(get_db)) -> list[UserResponse]:
      return _repo.list_all(db)


  @router.post("/", response_model=UserResponse, status_code=201)
  def create_user(data: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
      if _repo.get_by_email(db, data.email):
          raise HTTPException(status_code=409, detail="Email уже используется")
      user = User(
          id=str(uuid.uuid4()),
          email=data.email,
          password_hash=hash_password(data.password),
          display_name=data.display_name,
          role=data.role,
          default_team=data.default_team,
          is_active=True,
      )
      return _repo.create(db, user)


  @router.put("/{user_id}", response_model=UserResponse)
  def update_user(user_id: str, data: UserUpdate, db: Session = Depends(get_db)) -> UserResponse:
      user = _repo.get_by_id(db, user_id)
      if not user:
          raise HTTPException(status_code=404, detail="Пользователь не найден")
      if data.display_name is not None:
          user.display_name = data.display_name
      if data.role is not None:
          user.role = data.role
      if data.default_team is not None:
          user.default_team = data.default_team
      if data.is_active is not None:
          user.is_active = data.is_active
      return _repo.update(db, user)


  @router.post("/{user_id}/reset-password", response_model=UserResponse)
  def reset_password(user_id: str, data: PasswordReset, db: Session = Depends(get_db)) -> UserResponse:
      user = _repo.get_by_id(db, user_id)
      if not user:
          raise HTTPException(status_code=404, detail="Пользователь не найден")
      user.password_hash = hash_password(data.new_password)
      return _repo.update(db, user)
  ```

- [ ] **Step 3: Register in app/api/router.py**

  Add import:
  ```python
  from app.api.endpoints import admin_users as admin_users_endpoints
  ```

  Add include:
  ```python
  api_router.include_router(admin_users_endpoints.router, prefix="/admin/users", tags=["admin"])
  ```

- [ ] **Step 4: Run all new tests**

  Run: `py -3.10 -m pytest tests/test_admin_users.py tests/test_auth.py -v`
  Expected: 12 PASS

- [ ] **Step 5: Run full suite**

  Run: `py -3.10 -m pytest tests/ -v --tb=short -q`
  Expected: pre-existing tests still pass, total count ≥ 523

- [ ] **Step 6: Commit + push**
  ```bash
  git add app/api/endpoints/admin_users.py app/api/router.py tests/test_admin_users.py
  git commit -m "feat(auth): admin users CRUD endpoints"
  git push origin main
  ```

---

## Task 7: Admin seed script

**Files:** `scripts/create_admin.py`

- [ ] **Step 1: Create scripts/create_admin.py**
  ```python
  """Create first admin user. Run once after fresh deployment.

  Usage:
      py -3.10 scripts/create_admin.py
      py -3.10 scripts/create_admin.py --email admin@company.com --password secret
  """
  import argparse
  import sys
  import uuid

  sys.path.insert(0, ".")

  from app.config import settings
  from app.core.security import hash_password
  from app.database import SessionLocal
  from app.models.user import User, UserRole


  def main() -> None:
      parser = argparse.ArgumentParser()
      parser.add_argument("--email", default=settings.admin_email or "admin@example.com")
      parser.add_argument("--password", default=settings.admin_password or "changeme")
      args = parser.parse_args()

      db = SessionLocal()
      try:
          if db.query(User).filter(User.email == args.email).first():
              print(f"User {args.email} already exists. Skipping.")
              return
          user = User(
              id=str(uuid.uuid4()),
              email=args.email,
              password_hash=hash_password(args.password),
              display_name="Admin",
              role=UserRole.admin,
              is_active=True,
          )
          db.add(user)
          db.commit()
          print(f"Admin created: {args.email}")
      finally:
          db.close()


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2: Test the script**
  ```bash
  py -3.10 scripts/create_admin.py --email test-admin@example.com --password testpass123
  ```
  Expected: `Admin created: test-admin@example.com`

  Run again:
  Expected: `User test-admin@example.com already exists. Skipping.`

- [ ] **Step 3: Commit**
  ```bash
  git add scripts/create_admin.py
  git commit -m "feat(auth): create_admin.py seed script"
  ```

---

## Task 8: Frontend — Authorization header in API client

**Files:** `frontend/src/api/client.ts`

- [ ] **Step 1: Add getAuthHeader helper**

  Open `frontend/src/api/client.ts`. Add this function near the top, before `request`:
  ```typescript
  function getAuthHeader(): Record<string, string> {
    const token = localStorage.getItem('auth_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
  ```

- [ ] **Step 2: Use it in the request function**

  Find the existing headers line inside `request`:
  ```typescript
  headers: body ? { 'Content-Type': 'application/json' } : undefined,
  ```

  Replace with:
  ```typescript
  headers: {
    ...getAuthHeader(),
    ...(body ? { 'Content-Type': 'application/json' } : {}),
  },
  ```

- [ ] **Step 3: Type check**
  ```bash
  cd frontend && npx tsc --noEmit
  ```
  Expected: no errors

- [ ] **Step 4: Commit**
  ```bash
  git add frontend/src/api/client.ts
  git commit -m "feat(auth): send Authorization Bearer header from localStorage"
  ```

---

## Task 9: Frontend auth API + AdminUsers API

**Files:** `frontend/src/api/auth.ts`, `frontend/src/api/adminUsers.ts`

- [ ] **Step 1: Create frontend/src/api/auth.ts**
  ```typescript
  import { api } from './client';

  export interface UserProfile {
    id: string;
    email: string;
    display_name: string;
    role: 'admin' | 'super_manager' | 'manager';
    default_team: string | null;
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
  ```

- [ ] **Step 2: Create frontend/src/api/adminUsers.ts**
  ```typescript
  import { api } from './client';
  import type { UserProfile } from './auth';

  export interface UserCreate {
    email: string;
    password: string;
    display_name: string;
    role: 'admin' | 'super_manager' | 'manager';
    default_team?: string | null;
  }

  export interface UserUpdate {
    display_name?: string;
    role?: 'admin' | 'super_manager' | 'manager';
    default_team?: string | null;
    is_active?: boolean;
  }

  export function listUsers(): Promise<UserProfile[]> {
    return api.get<UserProfile[]>('/admin/users/');
  }

  export function createUser(data: UserCreate): Promise<UserProfile> {
    return api.post<UserProfile>('/admin/users/', data);
  }

  export function updateUser(id: string, data: UserUpdate): Promise<UserProfile> {
    return api.put<UserProfile>(`/admin/users/${id}`, data);
  }

  export function resetPassword(id: string, newPassword: string): Promise<UserProfile> {
    return api.post<UserProfile>(`/admin/users/${id}/reset-password`, { new_password: newPassword });
  }
  ```

- [ ] **Step 3: Type check**
  ```bash
  cd frontend && npx tsc --noEmit
  ```
  Expected: no errors

- [ ] **Step 4: Commit**
  ```bash
  git add frontend/src/api/auth.ts frontend/src/api/adminUsers.ts
  git commit -m "feat(auth): frontend auth + adminUsers API modules"
  ```

---

## Task 10: AuthContext + AuthProvider

**Files:** `frontend/src/hooks/useAuth.ts`, `frontend/src/components/AuthProvider.tsx`

- [ ] **Step 1: Create frontend/src/hooks/useAuth.ts**
  ```typescript
  import { createContext, useContext } from 'react';
  import type { UserProfile } from '../api/auth';

  export interface AuthState {
    user: UserProfile | null;
    token: string | null;
    isLoading: boolean;
    login: (token: string, user: UserProfile) => void;
    logout: () => void;
  }

  export const AuthContext = createContext<AuthState | null>(null);

  export function useAuth(): AuthState {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
    return ctx;
  }
  ```

- [ ] **Step 2: Create frontend/src/components/AuthProvider.tsx**
  ```typescript
  import React, { useCallback, useEffect, useMemo, useState } from 'react';
  import { getMe, type UserProfile } from '../api/auth';
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
        .then(setUser)
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

    const value = useMemo<AuthState>(
      () => ({ user, token, isLoading, login, logout }),
      [user, token, isLoading, login, logout],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
  }
  ```

- [ ] **Step 3: Type check**
  ```bash
  cd frontend && npx tsc --noEmit
  ```
  Expected: no errors

- [ ] **Step 4: Commit**
  ```bash
  git add frontend/src/hooks/useAuth.ts frontend/src/components/AuthProvider.tsx
  git commit -m "feat(auth): AuthContext + AuthProvider"
  ```

---

## Task 11: Login page

**Files:** `frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1: Create frontend/src/pages/LoginPage.tsx**
  ```typescript
  import { Button, Form, Input, Typography } from 'antd';
  import { useState } from 'react';
  import { useNavigate } from 'react-router-dom';
  import { getMe, login as apiLogin } from '../api/auth';
  import { useAuth } from '../hooks/useAuth';

  const { Title } = Typography;

  interface LoginForm {
    email: string;
    password: string;
  }

  export default function LoginPage() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function onFinish(values: LoginForm) {
      setLoading(true);
      setError(null);
      try {
        const { access_token } = await apiLogin(values.email, values.password);
        const profile = await getMe();
        login(access_token, profile);
        const redirect =
          profile.role === 'manager' && profile.default_team
            ? `/?teams=${encodeURIComponent(profile.default_team)}`
            : '/';
        navigate(redirect, { replace: true });
      } catch {
        setError('Неверный email или пароль');
      } finally {
        setLoading(false);
      }
    }

    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#141414',
        }}
      >
        <div style={{ width: 360 }}>
          <Title level={3} style={{ textAlign: 'center', marginBottom: 32, color: '#fff' }}>
            Jira Analytics
          </Title>
          <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
            <Form.Item name="email" label="Email" rules={[{ required: true, message: 'Введите email' }]}>
              <Input type="email" size="large" />
            </Form.Item>
            <Form.Item name="password" label="Пароль" rules={[{ required: true, message: 'Введите пароль' }]}>
              <Input.Password size="large" />
            </Form.Item>
            {error && (
              <div style={{ color: '#ff4d4f', marginBottom: 16, textAlign: 'center' }}>
                {error}
              </div>
            )}
            <Form.Item>
              <Button type="primary" htmlType="submit" size="large" block loading={loading}>
                Войти
              </Button>
            </Form.Item>
          </Form>
        </div>
      </div>
    );
  }
  ```

- [ ] **Step 2: Type check**
  ```bash
  cd frontend && npx tsc --noEmit
  ```
  Expected: no errors

- [ ] **Step 3: Commit**
  ```bash
  git add frontend/src/pages/LoginPage.tsx
  git commit -m "feat(auth): LoginPage"
  ```

---

## Task 12: Route protection + App wiring

**Files:** `frontend/src/routes.tsx`

- [ ] **Step 1: Open frontend/src/routes.tsx and read its full content**

  (Required before editing — understand all existing imports and route children.)

- [ ] **Step 2: Add imports**

  Add at top of file:
  ```typescript
  import { Navigate, Outlet } from 'react-router-dom';
  import { AuthProvider } from './components/AuthProvider';
  import { useAuth } from './hooks/useAuth';
  import LoginPage from './pages/LoginPage';
  ```

- [ ] **Step 3: Add AuthLayout + ProtectedRoute components**

  Add before `export const router`:
  ```typescript
  function AuthLayout() {
    return (
      <AuthProvider>
        <Outlet />
      </AuthProvider>
    );
  }

  function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const { user, isLoading } = useAuth();
    if (isLoading) return null;
    if (!user) return <Navigate to="/login" replace />;
    return <>{children}</>;
  }
  ```

- [ ] **Step 4: Restructure createBrowserRouter**

  Change the router to use AuthLayout as root, with `/login` as sibling to `/`:
  ```typescript
  export const router = createBrowserRouter([
    {
      element: <AuthLayout />,
      children: [
        {
          path: '/',
          element: <AppLayout />,
          children: [
            { index: true, element: <ProtectedRoute><FactFilterProvider>{page(<DashboardPage />)}</FactFilterProvider></ProtectedRoute> },
            { path: 'analytics', element: <ProtectedRoute><FactFilterProvider>{page(<AnalyticsPage />)}</FactFilterProvider></ProtectedRoute> },
            // wrap every existing child route in <ProtectedRoute>...</ProtectedRoute>
            // the pattern: replace `element: <X>` with `element: <ProtectedRoute><X></ProtectedRoute>`
          ],
        },
        {
          path: '/login',
          element: <LoginPage />,
        },
      ],
    },
  ]);
  ```

  Wrap every existing child route (`sync`, `capacity`, `backlog`, `planning`, `settings`, etc.) in `<ProtectedRoute>`.

- [ ] **Step 5: Type check + build**
  ```bash
  cd frontend && npx tsc --noEmit && npm run build
  ```
  Expected: no errors, build succeeds

- [ ] **Step 6: Commit**
  ```bash
  git add frontend/src/routes.tsx
  git commit -m "feat(auth): route protection + /login route via AuthLayout"
  ```

---

## Task 13: Header — user name + logout

**Files:** `frontend/src/components/Layout/AppLayout.tsx`

- [ ] **Step 1: Read AppLayout.tsx to find the header JSX structure**

- [ ] **Step 2: Add imports**

  ```typescript
  import { LogoutOutlined } from '@ant-design/icons';
  import { Button } from 'antd';
  import { useNavigate } from 'react-router-dom';
  import { useAuth } from '../../hooks/useAuth';
  ```

- [ ] **Step 3: Add logout handler in component body**
  ```typescript
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate('/login', { replace: true });
  }
  ```

- [ ] **Step 4: Add user info to Header JSX**

  Find the right side of the header (where `SyncIndicator` and `BugReportButton` are). Add after them (or alongside):
  ```tsx
  {user && (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13 }}>
        {user.display_name}
      </span>
      <Button
        type="text"
        size="small"
        icon={<LogoutOutlined />}
        onClick={handleLogout}
        style={{ color: 'rgba(255,255,255,0.35)' }}
        title="Выйти"
      />
    </div>
  )}
  ```

- [ ] **Step 5: Type check + build**
  ```bash
  cd frontend && npx tsc --noEmit && npm run build
  ```
  Expected: no errors

- [ ] **Step 6: Commit**
  ```bash
  git add frontend/src/components/Layout/AppLayout.tsx
  git commit -m "feat(auth): user name + logout button in header"
  ```

---

## Task 14: Admin Users tab in Settings

**Files:** `frontend/src/pages/settings/UsersTab.tsx`, `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Create frontend/src/pages/settings/ directory** (if it doesn't exist)

  Check if `frontend/src/pages/settings/` exists. If not, create it (just create the file in Step 2 — the directory will be created automatically).

- [ ] **Step 2: Create frontend/src/pages/settings/UsersTab.tsx**
  ```typescript
  import { EditOutlined, KeyOutlined, PlusOutlined } from '@ant-design/icons';
  import { Button, Form, Input, Modal, Select, Space, Switch, Table, notification } from 'antd';
  import { useEffect, useState } from 'react';
  import {
    createUser, listUsers, resetPassword, updateUser,
    type UserCreate, type UserUpdate,
  } from '../../api/adminUsers';
  import type { UserProfile } from '../../api/auth';

  const ROLE_OPTIONS = [
    { value: 'admin', label: 'Администратор' },
    { value: 'super_manager', label: 'Руководитель (все команды)' },
    { value: 'manager', label: 'Руководитель' },
  ];
  const ROLE_LABEL: Record<string, string> = Object.fromEntries(
    ROLE_OPTIONS.map((o) => [o.value, o.label]),
  );

  export default function UsersTab() {
    const [users, setUsers] = useState<UserProfile[]>([]);
    const [loading, setLoading] = useState(true);
    const [createOpen, setCreateOpen] = useState(false);
    const [editUser, setEditUser] = useState<UserProfile | null>(null);
    const [resetUser, setResetUser] = useState<UserProfile | null>(null);
    const [form] = Form.useForm();
    const [resetForm] = Form.useForm();

    function refresh() {
      setLoading(true);
      listUsers().then(setUsers).finally(() => setLoading(false));
    }

    useEffect(refresh, []);

    async function handleCreate(values: UserCreate) {
      try {
        await createUser(values);
        refresh();
        setCreateOpen(false);
        form.resetFields();
        notification.success({ message: 'Пользователь создан' });
      } catch {
        notification.error({ message: 'Ошибка при создании' });
      }
    }

    async function handleUpdate(values: UserUpdate) {
      if (!editUser) return;
      try {
        await updateUser(editUser.id, values);
        refresh();
        setEditUser(null);
        notification.success({ message: 'Изменения сохранены' });
      } catch {
        notification.error({ message: 'Ошибка при сохранении' });
      }
    }

    async function handleToggleActive(user: UserProfile) {
      try {
        await updateUser(user.id, { is_active: !user.is_active });
        refresh();
      } catch {
        notification.error({ message: 'Ошибка' });
      }
    }

    async function handleResetPassword(values: { new_password: string }) {
      if (!resetUser) return;
      try {
        await resetPassword(resetUser.id, values.new_password);
        setResetUser(null);
        resetForm.resetFields();
        notification.success({ message: 'Пароль изменён' });
      } catch {
        notification.error({ message: 'Ошибка при сбросе пароля' });
      }
    }

    const columns = [
      { title: 'Имя', dataIndex: 'display_name', key: 'display_name' },
      { title: 'Email', dataIndex: 'email', key: 'email' },
      {
        title: 'Роль', dataIndex: 'role', key: 'role',
        render: (r: string) => ROLE_LABEL[r] ?? r,
      },
      {
        title: 'Команда', dataIndex: 'default_team', key: 'default_team',
        render: (t: string | null) => t ?? <span style={{ color: '#666' }}>—</span>,
      },
      {
        title: 'Активен', dataIndex: 'is_active', key: 'is_active',
        render: (active: boolean, u: UserProfile) => (
          <Switch checked={active} onChange={() => handleToggleActive(u)} />
        ),
      },
      {
        title: '', key: 'actions',
        render: (_: unknown, u: UserProfile) => (
          <Space>
            <Button size="small" icon={<EditOutlined />} onClick={() => {
              setEditUser(u);
              form.setFieldsValue({ display_name: u.display_name, role: u.role, default_team: u.default_team });
            }} />
            <Button size="small" icon={<KeyOutlined />} onClick={() => setResetUser(u)} />
          </Space>
        ),
      },
    ];

    return (
      <div style={{ padding: 16 }}>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            Добавить пользователя
          </Button>
        </div>
        <Table dataSource={users} columns={columns} rowKey="id" loading={loading} size="small" />

        <Modal title="Новый пользователь" open={createOpen}
          onCancel={() => { setCreateOpen(false); form.resetFields(); }}
          onOk={() => form.submit()} okText="Создать">
          <Form form={form} layout="vertical" onFinish={handleCreate}>
            <Form.Item name="display_name" label="Имя" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="email" label="Email" rules={[{ required: true }]}><Input type="email" /></Form.Item>
            <Form.Item name="password" label="Пароль" rules={[{ required: true, min: 8 }]}><Input.Password /></Form.Item>
            <Form.Item name="role" label="Роль" rules={[{ required: true }]}><Select options={ROLE_OPTIONS} /></Form.Item>
            <Form.Item name="default_team" label="Команда по умолчанию">
              <Input placeholder="Пусто для admin/super_manager" />
            </Form.Item>
          </Form>
        </Modal>

        <Modal title="Редактировать" open={!!editUser}
          onCancel={() => setEditUser(null)} onOk={() => form.submit()} okText="Сохранить">
          <Form form={form} layout="vertical" onFinish={handleUpdate}>
            <Form.Item name="display_name" label="Имя"><Input /></Form.Item>
            <Form.Item name="role" label="Роль"><Select options={ROLE_OPTIONS} /></Form.Item>
            <Form.Item name="default_team" label="Команда"><Input /></Form.Item>
          </Form>
        </Modal>

        <Modal title={`Сбросить пароль — ${resetUser?.display_name}`} open={!!resetUser}
          onCancel={() => { setResetUser(null); resetForm.resetFields(); }}
          onOk={() => resetForm.submit()} okText="Сохранить">
          <Form form={resetForm} layout="vertical" onFinish={handleResetPassword}>
            <Form.Item name="new_password" label="Новый пароль" rules={[{ required: true, min: 8 }]}>
              <Input.Password />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    );
  }
  ```

- [ ] **Step 3: Add users tab to SettingsPage**

  Open `frontend/src/pages/SettingsPage.tsx`.

  Add import:
  ```typescript
  import { useAuth } from '../hooks/useAuth';
  import UsersTab from './settings/UsersTab';
  ```

  In `TAB_KEYS`, add `'users'`:
  ```typescript
  const TAB_KEYS = ['connection', 'scope', 'fields', 'hierarchy', 'reasons', 'categories', 'calendar', 'users'] as const;
  ```

  Inside the component, add:
  ```typescript
  const { user } = useAuth();
  ```

  In the `<Tabs>` items array, add the users tab entry (conditional on admin role). Find the existing items definition and add:
  ```typescript
  ...(user?.role === 'admin' ? [{ key: 'users', label: 'Пользователи', children: <UsersTab /> }] : []),
  ```

- [ ] **Step 4: Type check + build**
  ```bash
  cd frontend && npx tsc --noEmit && npm run build
  ```
  Expected: no errors, build succeeds

- [ ] **Step 5: Run full backend test suite**
  ```bash
  py -3.10 -m pytest tests/ -q --tb=short
  ```
  Expected: all tests pass

- [ ] **Step 6: Commit + push**
  ```bash
  git add frontend/src/pages/settings/UsersTab.tsx frontend/src/pages/SettingsPage.tsx
  git commit -m "feat(auth): admin Users tab in Settings (admin only)"
  git push origin main
  ```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ User table with all fields (Task 2)
- ✅ Roles: admin / super_manager / manager (Task 2)
- ✅ bcrypt password hashing (Task 3)
- ✅ JWT 8h access token, no refresh (Task 3, 5)
- ✅ POST /auth/login + GET /auth/me (Task 5)
- ✅ Admin CRUD /admin/users/ (Task 6)
- ✅ Seed script (Task 7)
- ✅ Migration 036_users (Task 2)
- ✅ Frontend Authorization header (Task 8)
- ✅ AuthContext + AuthProvider (Task 10)
- ✅ /login page (Task 11)
- ✅ Route protection (Task 12)
- ✅ User name + logout in header (Task 13)
- ✅ Admin Users tab in Settings (Task 14)
- ✅ Auto team-filter on login for manager role (Task 11 — redirect with `?teams=`)
- ✅ No server-side middleware on other endpoints (Variant A — documented in spec)

**Variant B follow-ups (out of scope):** `Depends(get_current_user)` on all endpoints, refresh tokens, rate limiting on /login.
