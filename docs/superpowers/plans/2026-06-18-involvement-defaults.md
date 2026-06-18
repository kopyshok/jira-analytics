# Справочник вовлечённости — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development или superpowers:executing-plans. Шаги отмечены чекбоксами.

**Goal:** Отдельный справочник вовлечённости по ролям (команда + роль + квартал начала действия), значения которого при утверждении сценария вписываются в пустые поля вовлечённости целевых задач.

**Architecture:** Новая таблица `involvement_defaults` с темпоральным поиском (последняя запись с началом ≤ квартала). CRUD-роутер под `/planning/involvement-defaults`. Хук в `approve_scenario` заполняет пустые `BacklogItem.involvement_*` по команде+кварталу сценария. Фронт — drawer с таблицей на странице «Сценарии».

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic batch; React 19 + AntD 6 + TanStack Query.

**Роли справочника → поля задачи:** `analyst→involvement_analyst`, `dev→involvement_dev`, `qa→involvement_qa`, `opo→involvement_launch`.

---

## Task 1: Модель InvolvementDefault

**Files:**
- Create: `app/models/involvement_default.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Создать модель**

`app/models/involvement_default.py`:
```python
"""InvolvementDefault — справочник вовлечённости по ролям с датой начала действия."""
from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

INVOLVEMENT_ROLES = ("analyst", "dev", "qa", "opo")


class InvolvementDefault(Base, TimestampMixin):
    """Значение вовлечённости для (команда, роль), действующее с указанного
    квартала и до следующей записи по той же паре с более поздним началом."""

    __tablename__ = "involvement_defaults"
    __table_args__ = (
        UniqueConstraint(
            "team", "role", "effective_year", "effective_quarter",
            name="uq_involvement_default_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_year: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    involvement: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<InvolvementDefault {self.team}/{self.role} "
            f"с {self.effective_year}Q{self.effective_quarter}: {self.involvement}>"
        )
```

- [ ] **Step 2: Зарегистрировать в `app/models/__init__.py`**

Добавить импорт после строки `from app.models.employee_capacity_override import EmployeeCapacityOverride`:
```python
from app.models.involvement_default import InvolvementDefault
```
И в список `__all__` после `"EmployeeCapacityOverride",`:
```python
    "InvolvementDefault",
```

- [ ] **Step 3: Проверить импорт**

Run: `py -3.10 -c "from app.models import InvolvementDefault; print(InvolvementDefault.__tablename__)"`
Expected: `involvement_defaults`

- [ ] **Step 4: Commit**

```bash
git add app/models/involvement_default.py app/models/__init__.py
git commit -m "feat(planning): модель справочника вовлечённости"
```

---

## Task 2: Миграция

**Files:**
- Create: `alembic/versions/<auto>_involvement_defaults.py`

- [ ] **Step 1: Сгенерировать миграцию**

Run: `alembic revision --autogenerate -m "involvement_defaults"`

- [ ] **Step 2: Проверить тело миграции**

Открыть созданный файл. `upgrade()` должен содержать `op.create_table("involvement_defaults", ...)` со столбцами id, team, role, effective_year, effective_quarter, involvement, created_at, updated_at + unique constraint `uq_involvement_default_scope` + index по team. Если autogenerate не подхватил — заменить на ручной батч:
```python
def upgrade() -> None:
    op.create_table(
        "involvement_defaults",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("effective_year", sa.Integer(), nullable=False),
        sa.Column("effective_quarter", sa.Integer(), nullable=False),
        sa.Column("involvement", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team", "role", "effective_year", "effective_quarter",
                            name="uq_involvement_default_scope"),
    )
    op.create_index("ix_involvement_defaults_team", "involvement_defaults", ["team"])


def downgrade() -> None:
    op.drop_index("ix_involvement_defaults_team", table_name="involvement_defaults")
    op.drop_table("involvement_defaults")
```

- [ ] **Step 3: Применить**

Run: `alembic upgrade head`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions
git commit -m "feat(planning): миграция таблицы involvement_defaults"
```

---

## Task 3: Сервис поиска значения

**Files:**
- Create: `app/services/involvement_default_service.py`
- Test: `tests/services/test_involvement_default_service.py`

- [ ] **Step 1: Написать падающий тест**

`tests/services/test_involvement_default_service.py`:
```python
from app.models import InvolvementDefault
from app.services.involvement_default_service import lookup_involvement


def _add(db, team, role, year, q, val):
    db.add(InvolvementDefault(
        team=team, role=role, effective_year=year, effective_quarter=q, involvement=val,
    ))


def test_lookup_picks_latest_effective_on_or_before(db_session):
    _add(db_session, "A", "analyst", 2026, 1, 0.8)
    _add(db_session, "A", "analyst", 2026, 3, 0.9)
    db_session.commit()
    # Q1, Q2 -> 0.8; Q3, Q4 -> 0.9
    assert lookup_involvement(db_session, "A", "analyst", 2026, 1) == 0.8
    assert lookup_involvement(db_session, "A", "analyst", 2026, 2) == 0.8
    assert lookup_involvement(db_session, "A", "analyst", 2026, 3) == 0.9
    assert lookup_involvement(db_session, "A", "analyst", 2027, 1) == 0.9


def test_lookup_none_before_first_effective(db_session):
    _add(db_session, "A", "analyst", 2026, 3, 0.9)
    db_session.commit()
    assert lookup_involvement(db_session, "A", "analyst", 2026, 1) is None


def test_lookup_team_and_role_isolated(db_session):
    _add(db_session, "A", "analyst", 2026, 1, 0.8)
    db_session.commit()
    assert lookup_involvement(db_session, "B", "analyst", 2026, 1) is None
    assert lookup_involvement(db_session, "A", "dev", 2026, 1) is None
```

- [ ] **Step 2: Запустить — падает**

Run: `py -3.10 -m pytest tests/services/test_involvement_default_service.py -v`
Expected: FAIL (ModuleNotFoundError / ImportError).

- [ ] **Step 3: Реализовать сервис**

`app/services/involvement_default_service.py`:
```python
"""Справочник вовлечённости: поиск действующего значения и запись в задачи."""
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import BacklogItem, InvolvementDefault

# role справочника -> поле BacklogItem
_ROLE_FIELD = {
    "analyst": "involvement_analyst",
    "dev": "involvement_dev",
    "qa": "involvement_qa",
    "opo": "involvement_launch",
}


def lookup_involvement(
    db: Session, team: str, role: str, year: int, quarter: int,
) -> Optional[float]:
    """Значение вовлечённости для (team, role), действующее на (year, quarter):
    последняя запись с началом действия не позже (year, quarter). Иначе None."""
    row = (
        db.query(InvolvementDefault)
        .filter(
            InvolvementDefault.team == team,
            InvolvementDefault.role == role,
            or_(
                InvolvementDefault.effective_year < year,
                and_(
                    InvolvementDefault.effective_year == year,
                    InvolvementDefault.effective_quarter <= quarter,
                ),
            ),
        )
        .order_by(
            InvolvementDefault.effective_year.desc(),
            InvolvementDefault.effective_quarter.desc(),
        )
        .first()
    )
    return row.involvement if row else None


def fill_empty_involvement(
    db: Session, items: list[BacklogItem], team: str, year: int, quarter: int,
) -> int:
    """Заполнить пустые поля вовлечённости целевых задач значениями справочника.
    Возвращает число заполненных полей. Непустые значения не трогает."""
    filled = 0
    cache: dict[str, Optional[float]] = {}
    for role, field in _ROLE_FIELD.items():
        if role not in cache:
            cache[role] = lookup_involvement(db, team, role, year, quarter)
        val = cache[role]
        if val is None:
            continue
        for item in items:
            if getattr(item, field) is None:
                setattr(item, field, val)
                filled += 1
    return filled
```

- [ ] **Step 4: Запустить — проходит**

Run: `py -3.10 -m pytest tests/services/test_involvement_default_service.py -v`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add app/services/involvement_default_service.py tests/services/test_involvement_default_service.py
git commit -m "feat(planning): поиск и запись вовлечённости из справочника"
```

---

## Task 4: CRUD-эндпоинты справочника

**Files:**
- Create: `app/api/endpoints/involvement_defaults.py`
- Modify: `app/api/router.py`
- Test: `tests/api/test_involvement_defaults_api.py`

- [ ] **Step 1: Написать падающий тест**

`tests/api/test_involvement_defaults_api.py`:
```python
def test_crud_involvement_defaults(client):
    # создать
    r = client.post("/api/v1/planning/involvement-defaults", json={
        "team": "A", "role": "analyst",
        "effective_year": 2026, "effective_quarter": 1, "involvement": 0.8,
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    # список с фильтром по команде
    r = client.get("/api/v1/planning/involvement-defaults?team=A")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # правка
    r = client.patch(f"/api/v1/planning/involvement-defaults/{rid}", json={"involvement": 0.9})
    assert r.status_code == 200
    assert r.json()["involvement"] == 0.9

    # дубль scope -> 409
    r = client.post("/api/v1/planning/involvement-defaults", json={
        "team": "A", "role": "analyst",
        "effective_year": 2026, "effective_quarter": 1, "involvement": 0.5,
    })
    assert r.status_code == 409

    # удалить
    r = client.delete(f"/api/v1/planning/involvement-defaults/{rid}")
    assert r.status_code == 204
    r = client.get("/api/v1/planning/involvement-defaults?team=A")
    assert r.json() == []


def test_reject_unknown_role(client):
    r = client.post("/api/v1/planning/involvement-defaults", json={
        "team": "A", "role": "wizard",
        "effective_year": 2026, "effective_quarter": 1, "involvement": 0.8,
    })
    assert r.status_code == 422
```

- [ ] **Step 2: Запустить — падает**

Run: `py -3.10 -m pytest tests/api/test_involvement_defaults_api.py -v`
Expected: FAIL (404 — роутер не подключён).

- [ ] **Step 3: Создать роутер**

`app/api/endpoints/involvement_defaults.py`:
```python
"""CRUD справочника вовлечённости по ролям."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InvolvementDefault
from app.models.involvement_default import INVOLVEMENT_ROLES

router = APIRouter()


class InvolvementDefaultResponse(BaseModel):
    id: str
    team: str
    role: str
    effective_year: int
    effective_quarter: int
    involvement: float

    class Config:
        from_attributes = True


class InvolvementDefaultCreate(BaseModel):
    team: str = Field(min_length=1, max_length=200)
    role: str
    effective_year: int = Field(ge=2000, le=2100)
    effective_quarter: int = Field(ge=1, le=4)
    involvement: float = Field(ge=0, le=1)


class InvolvementDefaultUpdate(BaseModel):
    team: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = None
    effective_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    effective_quarter: Optional[int] = Field(default=None, ge=1, le=4)
    involvement: Optional[float] = Field(default=None, ge=0, le=1)


def _check_role(role: Optional[str]) -> None:
    if role is not None and role not in INVOLVEMENT_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown role {role!r}. Allowed: {list(INVOLVEMENT_ROLES)}",
        )


def _check_clash(db: Session, team, role, year, quarter, exclude_id=None) -> None:
    q = db.query(InvolvementDefault).filter(
        InvolvementDefault.team == team,
        InvolvementDefault.role == role,
        InvolvementDefault.effective_year == year,
        InvolvementDefault.effective_quarter == quarter,
    )
    if exclude_id is not None:
        q = q.filter(InvolvementDefault.id != exclude_id)
    if q.first() is not None:
        raise HTTPException(
            status_code=409,
            detail="Запись для этой команды, роли и квартала уже есть",
        )


@router.get("", response_model=List[InvolvementDefaultResponse])
def list_defaults(team: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(InvolvementDefault)
    if team is not None:
        q = q.filter(InvolvementDefault.team == team)
    return q.order_by(
        InvolvementDefault.team,
        InvolvementDefault.role,
        InvolvementDefault.effective_year,
        InvolvementDefault.effective_quarter,
    ).all()


@router.post("", response_model=InvolvementDefaultResponse, status_code=201)
def create_default(req: InvolvementDefaultCreate, db: Session = Depends(get_db)):
    _check_role(req.role)
    _check_clash(db, req.team, req.role, req.effective_year, req.effective_quarter)
    row = InvolvementDefault(**req.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{default_id}", response_model=InvolvementDefaultResponse)
def update_default(default_id: str, req: InvolvementDefaultUpdate, db: Session = Depends(get_db)):
    row = db.query(InvolvementDefault).filter(InvolvementDefault.id == default_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    data = req.model_dump(exclude_unset=True)
    if "role" in data:
        _check_role(data["role"])
    merged = {
        "team": data.get("team", row.team),
        "role": data.get("role", row.role),
        "year": data.get("effective_year", row.effective_year),
        "quarter": data.get("effective_quarter", row.effective_quarter),
    }
    _check_clash(db, merged["team"], merged["role"], merged["year"], merged["quarter"], exclude_id=default_id)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{default_id}", status_code=204)
def delete_default(default_id: str, db: Session = Depends(get_db)):
    row = db.query(InvolvementDefault).filter(InvolvementDefault.id == default_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return None
```

- [ ] **Step 4: Подключить роутер в `app/api/router.py`**

В блок импортов из `app.api.endpoints` (рядом с `planning,`) добавить:
```python
    involvement_defaults as involvement_defaults_endpoints,
```
В секции authenticated routers (после include planning.router) добавить:
```python
api_router.include_router(
    involvement_defaults_endpoints.router,
    prefix="/planning/involvement-defaults",
    tags=["planning"],
    dependencies=_auth_dep,
)
```

- [ ] **Step 5: Запустить — проходит**

Run: `py -3.10 -m pytest tests/api/test_involvement_defaults_api.py -v`
Expected: PASS (2 теста).

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/involvement_defaults.py app/api/router.py tests/api/test_involvement_defaults_api.py
git commit -m "feat(planning): CRUD эндпоинты справочника вовлечённости"
```

---

## Task 5: Запись вовлечённости при утверждении

**Files:**
- Modify: `app/api/endpoints/planning.py` (функция `approve_scenario`, ~631–826)
- Test: `tests/test_involvement_default_on_approve.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_involvement_default_on_approve.py`:
```python
from app.models import (
    BacklogItem, InvolvementDefault, PlanningScenario, ScenarioAllocation,
)


def _scenario_with_item(db, team="A", year=2026, quarter="Q1",
                        involvement_analyst=None):
    sc = PlanningScenario(name="S", team=team, year=year, quarter=quarter, status="draft")
    db.add(sc)
    item = BacklogItem(title="I", team=team, involvement_analyst=involvement_analyst)
    db.add(item)
    db.flush()
    db.add(ScenarioAllocation(
        scenario_id=sc.id, backlog_item_id=item.id, included_flag=True,
    ))
    db.commit()
    return sc, item


def test_approve_fills_empty_involvement(client, db_session):
    sc, item = _scenario_with_item(db_session, involvement_analyst=None)
    db_session.add(InvolvementDefault(
        team="A", role="analyst", effective_year=2026, effective_quarter=1, involvement=0.8,
    ))
    db_session.commit()

    r = client.post(f"/api/v1/planning/scenarios/{sc.id}/approve")
    assert r.status_code == 200, r.text

    db_session.refresh(item)
    assert item.involvement_analyst == 0.8


def test_approve_does_not_overwrite_existing(client, db_session):
    sc, item = _scenario_with_item(db_session, involvement_analyst=0.5)
    db_session.add(InvolvementDefault(
        team="A", role="analyst", effective_year=2026, effective_quarter=1, involvement=0.8,
    ))
    db_session.commit()

    r = client.post(f"/api/v1/planning/scenarios/{sc.id}/approve")
    assert r.status_code == 200, r.text

    db_session.refresh(item)
    assert item.involvement_analyst == 0.5


def test_revert_keeps_written_value(client, db_session):
    sc, item = _scenario_with_item(db_session, involvement_analyst=None)
    db_session.add(InvolvementDefault(
        team="A", role="analyst", effective_year=2026, effective_quarter=1, involvement=0.8,
    ))
    db_session.commit()
    client.post(f"/api/v1/planning/scenarios/{sc.id}/approve")
    client.post(f"/api/v1/planning/scenarios/{sc.id}/revert-to-draft")

    db_session.refresh(item)
    assert item.involvement_analyst == 0.8
```

- [ ] **Step 2: Запустить — падает**

Run: `py -3.10 -m pytest tests/test_involvement_default_on_approve.py -v`
Expected: FAIL (involvement_analyst остаётся None).

- [ ] **Step 3: Встроить запись в approve_scenario**

В `app/api/endpoints/planning.py` добавить импорт рядом с другими сервис-импортами:
```python
from app.services.involvement_default_service import fill_empty_involvement
```
В `approve_scenario`, сразу после блока, формирующего `included_rows` (после `.all()` на ~639), вставить:
```python
    # Заполнить пустую вовлечённость целевых задач из справочника
    # (по команде и кварталу сценария). Непустые значения не трогаем.
    if scenario.team and scenario.year and scenario.quarter:
        q_int = int(str(scenario.quarter).replace("Q", ""))
        fill_empty_involvement(
            db,
            [item for _alloc, item in included_rows],
            scenario.team,
            scenario.year,
            q_int,
        )
```

- [ ] **Step 4: Запустить — проходит**

Run: `py -3.10 -m pytest tests/test_involvement_default_on_approve.py -v`
Expected: PASS (3 теста).

- [ ] **Step 5: Прогнать соседние тесты планирования**

Run: `py -3.10 -m pytest tests/ -k "approve or planning" -q`
Expected: без новых падений.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_involvement_default_on_approve.py
git commit -m "feat(planning): запись вовлечённости из справочника при утверждении"
```

---

## Task 6: Фронт — API-хуки

**Files:**
- Create: `frontend/src/hooks/useInvolvementDefaults.ts`
- Modify: `frontend/src/types/api.ts` (добавить тип)

- [ ] **Step 1: Тип ответа в `frontend/src/types/api.ts`**

Добавить:
```typescript
export interface InvolvementDefault {
  id: string;
  team: string;
  role: string;
  effective_year: number;
  effective_quarter: number;
  involvement: number;
}
```

- [ ] **Step 2: Хуки в `frontend/src/hooks/useInvolvementDefaults.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { InvolvementDefault } from '../types/api';

const KEY = 'involvement-defaults';

export function useInvolvementDefaults(team: string | null | undefined) {
  return useQuery({
    queryKey: [KEY, team ?? null],
    queryFn: () =>
      api.get<InvolvementDefault[]>(
        '/planning/involvement-defaults',
        team ? { team } : undefined,
      ),
    enabled: !!team,
  });
}

type CreateBody = Omit<InvolvementDefault, 'id'>;

export function useCreateInvolvementDefault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateBody) =>
      api.post<InvolvementDefault>('/planning/involvement-defaults', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}

export function useUpdateInvolvementDefault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<CreateBody> }) =>
      api.patch<InvolvementDefault>(`/planning/involvement-defaults/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}

export function useDeleteInvolvementDefault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.delete(`/planning/involvement-defaults/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}
```

ПЕРЕД написанием сверить сигнатуры `api.get/post/patch/delete` в `frontend/src/api/client.ts` и подогнать (например, `api.get(path, params)` vs `api.get(path, {params})`).

- [ ] **Step 3: Проверить типизацию**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок в новых файлах.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useInvolvementDefaults.ts frontend/src/types/api.ts
git commit -m "feat(planning): фронт-хуки справочника вовлечённости"
```

---

## Task 7: Фронт — drawer со справочником

**Files:**
- Create: `frontend/src/components/planning/InvolvementDefaultsDrawer.tsx`

- [ ] **Step 1: Компонент**

`frontend/src/components/planning/InvolvementDefaultsDrawer.tsx`:
```tsx
import { useState } from 'react';
import {
  App, Button, Drawer, InputNumber, Popconfirm, Select, Space, Table,
} from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import {
  useInvolvementDefaults,
  useCreateInvolvementDefault,
  useDeleteInvolvementDefault,
} from '../../hooks/useInvolvementDefaults';

const ROLE_LABELS: Record<string, string> = {
  analyst: 'Анализ',
  dev: 'Разработка',
  qa: 'Тестирование',
  opo: 'ОПЭ',
};
const ROLE_OPTIONS = Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }));
const QUARTER_OPTIONS = [1, 2, 3, 4].map((q) => ({ value: q, label: `Q${q}` }));

export default function InvolvementDefaultsDrawer({
  open, onClose, team,
}: {
  open: boolean;
  onClose: () => void;
  team: string | null;
}) {
  const { notification } = App.useApp();
  const { data = [], isLoading } = useInvolvementDefaults(team);
  const create = useCreateInvolvementDefault();
  const del = useDeleteInvolvementDefault();

  const now = new Date();
  const [role, setRole] = useState('analyst');
  const [year, setYear] = useState<number>(now.getFullYear());
  const [quarter, setQuarter] = useState<number>(1);
  const [value, setValue] = useState<number | null>(0.8);

  const handleAdd = () => {
    if (!team || value == null) return;
    create.mutate(
      { team, role, effective_year: year, effective_quarter: quarter, involvement: value },
      {
        onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
      },
    );
  };

  const columns = [
    { title: 'Роль', dataIndex: 'role', render: (r: string) => ROLE_LABELS[r] ?? r },
    {
      title: 'Действует с',
      key: 'eff',
      render: (_: unknown, row: { effective_quarter: number; effective_year: number }) =>
        `Q${row.effective_quarter} ${row.effective_year}`,
    },
    { title: 'Вовлечённость', dataIndex: 'involvement' },
    {
      title: '',
      key: 'act',
      width: 48,
      render: (_: unknown, row: { id: string }) => (
        <Popconfirm title="Удалить?" onConfirm={() => del.mutate(row.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={560}
      title={`Справочник вовлечённости${team ? ` · ${team}` : ''}`}
    >
      {!team ? (
        <div>Выберите команду сценария.</div>
      ) : (
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <Space wrap>
            <Select style={{ width: 150 }} value={role} onChange={setRole} options={ROLE_OPTIONS} />
            <Select style={{ width: 90 }} value={quarter} onChange={setQuarter} options={QUARTER_OPTIONS} />
            <InputNumber style={{ width: 100 }} value={year} onChange={(v) => setYear(v ?? year)} min={2000} max={2100} />
            <InputNumber style={{ width: 110 }} value={value} onChange={setValue} min={0} max={1} step={0.05} placeholder="0–1" />
            <Button type="primary" icon={<PlusOutlined />} loading={create.isPending} onClick={handleAdd}>
              Добавить
            </Button>
          </Space>
          <Table
            rowKey="id"
            size="small"
            loading={isLoading}
            dataSource={data}
            columns={columns}
            pagination={false}
          />
        </Space>
      )}
    </Drawer>
  );
}
```

ПЕРЕД написанием сверить пропс `Space` — в этом проекте используется `orientation="vertical"` (см. PlanningPage.tsx). Если в установленной AntD это `direction` — заменить.

- [ ] **Step 2: Проверить типизацию**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/planning/InvolvementDefaultsDrawer.tsx
git commit -m "feat(planning): drawer справочника вовлечённости"
```

---

## Task 8: Фронт — кнопка на странице «Сценарии»

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 1: Импорт + состояние**

Добавить импорт:
```tsx
import InvolvementDefaultsDrawer from '../components/planning/InvolvementDefaultsDrawer';
```
Рядом с прочими `useState` в `PlanningPage`:
```tsx
  const [involvementOpen, setInvolvementOpen] = useState(false);
```

- [ ] **Step 2: Кнопка в actions хедера**

В `PageHeader` `actions` (рядом с кнопкой «Сравнить») добавить:
```tsx
            <Button onClick={() => setInvolvementOpen(true)}>
              Вовлечённость
            </Button>
```

- [ ] **Step 3: Drawer в конце JSX**

Перед `<ApproveCelebration ... />`:
```tsx
      <InvolvementDefaultsDrawer
        open={involvementOpen}
        onClose={() => setInvolvementOpen(false)}
        team={scenario?.team ?? null}
      />
```

- [ ] **Step 4: Проверить типизацию + сборку**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: успешная сборка.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): кнопка справочника вовлечённости на странице сценариев"
```

---

## Task 9: Финальная проверка

- [ ] **Step 1: Бэкенд-тесты целиком**

Run: `py -3.10 -m pytest tests/ -q`
Expected: новые тесты зелёные, старые не сломаны (учесть известные pre-existing падения).

- [ ] **Step 2: Lint бэкенда**

Run: `ruff check app/ tests/`
Expected: чисто на новых файлах.

- [ ] **Step 3: Release note**

Run: `py -3.10 scripts/release_note.py add` — черновик: «Справочник вовлечённости по ролям в разделе Сценарии: задаётся по команде с квартала начала действия; при утверждении сценария пустая вовлечённость целевых задач заполняется автоматически».

- [ ] **Step 4: Commit + push**

```bash
git add docs
git commit -m "docs(planning): release note справочника вовлечённости"
git push origin main
```
