# KPI аналитиков — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Раздел «KPI» считает коэффициент эффективности сотрудника как взвешенную сумму шести настраиваемых метрик и показывает результат руководителю с расшифровкой до задач.

**Architecture:** Метрики хранятся как данные (два набора условий отбора в JSON), а не как код. Кодом реализованы три способа расчёта: доля, норматив к факту, средний балл к максимуму. Условия транслируются в фильтры SQLAlchemy общим транслятором. Расчёт помесячный и живой; утверждение месяца пишет снимок. Раздел живёт в ветке `feature/kpi`, в меню скрыт через существующий механизм «Видимость разделов».

**Tech Stack:** Python 3.10 (`py -3.10`), FastAPI, SQLAlchemy 2.0, Alembic (batch mode), pytest; React 19 + TS + Vite + AntD 6, Aurora theme.

**Спека:** [docs/superpowers/specs/2026-07-30-kpi-analysts-design.md](../specs/2026-07-30-kpi-analysts-design.md)

---

## Структура файлов

**Backend — новое:**
- `app/models/issue_link.py` — связи задач Jira
- `app/models/kpi.py` — метрика, профиль, вес метрики в профиле, норматив Cycle Time, утверждение месяца
- `app/services/kpi/__init__.py`
- `app/services/kpi/conditions.py` — трансляция условий отбора в фильтры SQLAlchemy
- `app/services/kpi/calculators.py` — три способа расчёта
- `app/services/kpi/timeliness.py` — срок внесения трудозатрат по производственному календарю
- `app/services/kpi/kpi_service.py` — расчёт по сотруднику/команде/периоду, веса, снимки
- `app/services/kpi/seed.py` — шесть метрик и профиль «Аналитик» по умолчанию
- `app/api/endpoints/kpi.py` — отчёт, расшифровка, утверждение, выгрузка
- `app/api/endpoints/kpi_settings.py` — CRUD справочников

**Backend — изменяемое:**
- `app/models/issue.py` — резолюция, дата резолюции, окружение, подтип, тип затрат, фактический Cycle Time, направление
- `app/models/worklog.py` — дата внесения записи
- `app/services/sync_service.py` — новые сопоставляемые поля, дата внесения, связи задач
- `app/api/router.py` — регистрация двух роутеров
- `app/models/__init__.py` — экспорт новых моделей

**Frontend — новое:**
- `frontend/src/api/kpi.ts`
- `frontend/src/pages/KpiPage.tsx`
- `frontend/src/components/kpi/KpiLedger.tsx`
- `frontend/src/components/kpi/KpiEmployeeCard.tsx`
- `frontend/src/components/kpi/KpiBreakdownModal.tsx`
- `frontend/src/components/settings/kpi/KpiSettingsTab.tsx` (+ `MetricEditor.tsx`, `ProfileEditor.tsx`, `CycleTimeNorms.tsx`, `GeneralRules.tsx`)

**Frontend — изменяемое:**
- `frontend/src/routes.tsx`, `frontend/src/pages/lazyPages.ts`, `frontend/src/aurora/shell/AuroraSidebar.tsx`, `frontend/src/pages/SettingsPage.tsx`

---

## Фаза 1 — данные из Jira

### Task 1: Дата внесения записи о трудозатратах

Схема ответа Jira уже содержит поле `created` (`app/connectors/schemas.py:183`), оно просто не сохраняется.

**Files:**
- Modify: `app/models/worklog.py`
- Create: `alembic/versions/k01a_kpi_worklog_created.py`
- Modify: `app/services/sync_service.py` (метод upsert ворклога)
- Test: `tests/test_kpi_worklog_created.py`

- [ ] **Step 1: Написать падающий тест**

```python
"""Дата внесения записи о трудозатратах сохраняется при синке."""
from datetime import datetime

from app.models.worklog import Worklog


def test_worklog_has_created_at(db_session, sample_issue, sample_employee):
    wl = Worklog(
        jira_worklog_id="w-1",
        issue_id=sample_issue.id,
        employee_id=sample_employee.id,
        started_at=datetime(2026, 7, 24, 10, 0),
        jira_created_at=datetime(2026, 7, 27, 9, 30),
        hours=4.0,
        time_spent_seconds=14400,
    )
    db_session.add(wl)
    db_session.commit()

    loaded = db_session.query(Worklog).filter_by(jira_worklog_id="w-1").one()
    assert loaded.jira_created_at == datetime(2026, 7, 27, 9, 30)
```

Фикстуры `db_session`, `sample_issue`, `sample_employee` — посмотреть в `tests/conftest.py`; если нужных нет, создать issue и employee прямо в тесте и удалить в конце (инвариант очистки таблиц — см. `tests/CLAUDE.md`).

- [ ] **Step 2: Убедиться, что тест падает**

Run: `py -3.10 -m pytest tests/test_kpi_worklog_created.py -v`
Expected: FAIL, `TypeError: 'jira_created_at' is an invalid keyword argument`

- [ ] **Step 3: Добавить колонку в модель**

В `app/models/worklog.py` рядом с `started_at`:

```python
    jira_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
```

`Optional` и `DateTime` уже импортированы в файле; если нет — добавить.

- [ ] **Step 4: Миграция**

`alembic/versions/k01a_kpi_worklog_created.py`:

```python
"""kpi: дата внесения записи о трудозатратах

Revision ID: k01a_kpi_worklog_created
Revises: f4b2c8d1e7a3
"""
import sqlalchemy as sa
from alembic import op

revision = "k01a_kpi_worklog_created"
down_revision = "f4b2c8d1e7a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("worklogs") as batch:
        batch.add_column(sa.Column("jira_created_at", sa.DateTime(), nullable=True))
    op.create_index("ix_worklogs_jira_created_at", "worklogs", ["jira_created_at"])


def downgrade() -> None:
    op.drop_index("ix_worklogs_jira_created_at", table_name="worklogs")
    with op.batch_alter_table("worklogs") as batch:
        batch.drop_column("jira_created_at")
```

- [ ] **Step 5: Прогнать миграцию и тест**

Run: `py -3.10 -m alembic upgrade head && py -3.10 -m pytest tests/test_kpi_worklog_created.py -v`
Expected: PASS

- [ ] **Step 6: Заполнять поле при синке**

В `app/services/sync_service.py` найти место, где создаётся/обновляется `Worklog` из `JiraWorklogSchema` (искать `jira_worklog_id=`). Добавить в оба ветки (создание и обновление):

```python
        worklog.jira_created_at = wl.created_datetime()
```

`created_datetime()` — свойство схемы; если его нет у `JiraWorklogSchema`, добавить по образцу `JiraCommentSchema.created_datetime` (`app/connectors/schemas.py:253`):

```python
    @property
    def created_datetime(self) -> Optional[datetime]:
        """Распарсить created из Jira."""
        if not self.created:
            return None
        return _parse_jira_datetime(self.created)
```

- [ ] **Step 7: Тест на синк**

Дописать в `tests/test_kpi_worklog_created.py`:

```python
def test_sync_stores_worklog_created(monkeypatch, db_session):
    """upsert ворклога переносит created из ответа Jira."""
    from app.connectors.schemas import JiraWorklogSchema

    payload = JiraWorklogSchema.model_validate({
        "id": "w-2",
        "started": "2026-07-24T10:00:00.000+0300",
        "created": "2026-07-27T09:30:00.000+0300",
        "timeSpentSeconds": 14400,
        "author": {"accountId": "acc-1", "displayName": "Иванов И."},
    })
    assert payload.created_datetime is not None
    assert payload.created_datetime.hour == 6  # 09:30 +03:00 → 06:30 UTC
```

Точное ожидаемое значение проверить по поведению `_parse_jira_datetime` в `app/connectors/schemas.py` — она приводит к naive UTC. Если приведения нет, ожидать 9.

- [ ] **Step 8: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/test_kpi_worklog_created.py -v
git add app/models/worklog.py app/connectors/schemas.py app/services/sync_service.py alembic/versions/k01a_kpi_worklog_created.py tests/test_kpi_worklog_created.py
git commit -m "feat(kpi): сохранять дату внесения записи о трудозатратах"
```

---

### Task 2: Резолюция и дата резолюции задачи

Сейчас различить «Готово» и «Отменено» невозможно: у обоих категория статуса `done`, отменённых задач около 18 тысяч.

**Files:**
- Modify: `app/models/issue.py`
- Create: `alembic/versions/k02a_kpi_issue_resolution.py`
- Modify: `app/services/sync_service.py` (`_upsert_issue`), `app/connectors/schemas.py`
- Test: `tests/test_kpi_issue_resolution.py`

- [ ] **Step 1: Написать падающий тест**

```python
"""Резолюция задачи и дата резолюции сохраняются отдельно от статуса."""
from datetime import datetime

from app.models.issue import Issue


def test_issue_resolution_fields(db_session, sample_project):
    issue = Issue(
        jira_issue_id="10001",
        key="OS-1",
        summary="Тест",
        issue_type="Задача",
        status="ГОТОВО",
        status_category="done",
        resolution="Готово",
        resolved_at=datetime(2026, 7, 20, 12, 0),
        project_id=sample_project.id,
    )
    db_session.add(issue)
    db_session.commit()

    loaded = db_session.query(Issue).filter_by(key="OS-1").one()
    assert loaded.resolution == "Готово"
    assert loaded.resolved_at == datetime(2026, 7, 20, 12, 0)
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_kpi_issue_resolution.py -v`
Expected: FAIL, `'resolution' is an invalid keyword argument`

- [ ] **Step 3: Колонки в модели**

В `app/models/issue.py` рядом со `status_category`:

```python
    resolution: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
```

- [ ] **Step 4: Миграция**

`alembic/versions/k02a_kpi_issue_resolution.py`, `down_revision = "k01a_kpi_worklog_created"`:

```python
def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("resolution", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("resolved_at", sa.DateTime(), nullable=True))
    op.create_index("ix_issues_resolution", "issues", ["resolution"])
    op.create_index("ix_issues_resolved_at", "issues", ["resolved_at"])


def downgrade() -> None:
    op.drop_index("ix_issues_resolved_at", table_name="issues")
    op.drop_index("ix_issues_resolution", table_name="issues")
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("resolved_at")
        batch.drop_column("resolution")
```

- [ ] **Step 5: Забирать из Jira**

В `app/connectors/schemas.py`, класс `JiraIssueFieldsSchema`, добавить поля:

```python
    resolution: Optional[dict] = None
    resolutiondate: Optional[str] = None
```

и добавить `"resolution"`, `"resolutiondate"` в список известных ключей в `__init__` (строка ~113, где перечислены `"project", "parent", "creator", ...`), иначе они уедут в `_extra`.

В `app/services/sync_service.py`, `_upsert_issue`, рядом с присвоением `status_category`:

```python
    issue.resolution = (fields.resolution or {}).get("name") if fields.resolution else None
    issue.resolved_at = _parse_jira_datetime(fields.resolutiondate) if fields.resolutiondate else None
```

Имя функции разбора даты взять то же, что уже используется в `_upsert_issue` для `statuscategorychangedate`.

Добавить `resolution,resolutiondate` в строку запрашиваемых полей `fields=` там же, где перечисляются `summary,issuetype,status,project`.

- [ ] **Step 6: Прогнать миграцию и тесты**

Run: `py -3.10 -m alembic upgrade head && py -3.10 -m pytest tests/test_kpi_issue_resolution.py tests/test_sync_service.py -v`
Expected: PASS

- [ ] **Step 7: Коммит**

```bash
git add app/models/issue.py app/connectors/schemas.py app/services/sync_service.py alembic/versions/k02a_kpi_issue_resolution.py tests/test_kpi_issue_resolution.py
git commit -m "feat(kpi): резолюция и дата резолюции задачи"
```

---

### Task 3: Пять новых сопоставляемых полей Jira

Окружение, подтип, тип затрат, фактический Cycle Time, продуктовое направление. Механизм тот же, что для оценок заказчика: ключ настройки `jira_<имя>_field_id`, чтение из `_extra`.

**Files:**
- Modify: `app/models/issue.py`, `app/services/sync_service.py`
- Create: `alembic/versions/k03a_kpi_issue_custom_fields.py`
- Test: `tests/test_kpi_issue_custom_fields.py`

- [ ] **Step 1: Тест на извлечение значений**

```python
"""Пять новых полей Jira попадают в задачу по сопоставлению из настроек."""
from app.models.app_setting import AppSetting
from app.services.sync_service import _extract_single_value


def test_extract_single_value_handles_three_shapes():
    assert _extract_single_value({"cf1": {"value": "PROD"}}, "cf1") == "PROD"
    assert _extract_single_value({"cf1": [{"value": "PROD"}]}, "cf1") == "PROD"
    assert _extract_single_value({"cf1": "PROD"}, "cf1") == "PROD"
    assert _extract_single_value({}, "cf1") is None
    assert _extract_single_value({"cf1": None}, "cf1") is None


def test_issue_custom_field_columns(db_session, sample_project):
    from app.models.issue import Issue

    issue = Issue(
        jira_issue_id="10002", key="OS-2", summary="Тест", issue_type="Задача",
        status="ГОТОВО", project_id=sample_project.id,
        environment="PROD", subtype="RFC_STANDARD", cost_type="Change",
        cycle_time_fact=64.0, direction="Финансовые операции",
    )
    db_session.add(issue)
    db_session.commit()
    loaded = db_session.query(Issue).filter_by(key="OS-2").one()
    assert loaded.environment == "PROD"
    assert loaded.cycle_time_fact == 64.0
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_kpi_issue_custom_fields.py -v`
Expected: FAIL

- [ ] **Step 3: Колонки в модели**

В `app/models/issue.py`:

```python
    # KPI: поля, приходящие из Jira по сопоставлению в настройках
    environment: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    subtype: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    cost_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    cycle_time_fact: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
```

- [ ] **Step 4: Миграция**

`alembic/versions/k03a_kpi_issue_custom_fields.py`, `down_revision = "k02a_kpi_issue_resolution"`, добавляет пять колонок и индексы на `environment`, `subtype`, `cost_type`, `direction` по образцу Task 2.

- [ ] **Step 5: Извлечение при синке**

В `app/services/sync_service.py` рядом с существующим `_extract_team_values` добавить:

```python
def _extract_single_value(extra: dict, field_id: Optional[str]) -> Optional[str]:
    """Одно значение select-поля Jira. Три формы: {'value': X}, [{'value': X}], 'X'."""
    if not field_id:
        return None
    raw = extra.get(field_id)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("value") or raw.get("name")
    if isinstance(raw, list):
        if not raw:
            return None
        first = raw[0]
        return first.get("value") or first.get("name") if isinstance(first, dict) else str(first)
    return str(raw)
```

В том же файле, где читаются ключи `jira_rating_quality_field_id` и т. п. (строки ~149-155), добавить чтение пяти новых ключей: `jira_environment_field_id`, `jira_subtype_field_id`, `jira_cost_type_field_id`, `jira_cycle_time_field_id`, `jira_direction_field_id`. Они должны попадать в список запрашиваемых `fields=` там же, где остальные сопоставленные поля.

В `_upsert_issue`:

```python
    issue.environment = _extract_single_value(extra, env_field_id)
    issue.subtype = _extract_single_value(extra, subtype_field_id)
    issue.cost_type = _extract_single_value(extra, cost_type_field_id)
    issue.direction = _extract_single_value(extra, direction_field_id)
    ct_raw = _extract_single_value(extra, cycle_time_field_id)
    try:
        issue.cycle_time_fact = float(ct_raw) if ct_raw not in (None, "") else None
    except (TypeError, ValueError):
        issue.cycle_time_fact = None
```

- [ ] **Step 6: Прогнать и закоммитить**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m pytest tests/test_kpi_issue_custom_fields.py tests/test_sync_extra_fields.py -v
git add -A app/models/issue.py app/services/sync_service.py alembic/versions/k03a_kpi_issue_custom_fields.py tests/test_kpi_issue_custom_fields.py
git commit -m "feat(kpi): окружение, подтип, тип затрат, cycle time, направление из Jira"
```

---

### Task 4: Связи задач

Нужны, чтобы найти автора задачи, к которой привязан баг.

**Files:**
- Create: `app/models/issue_link.py`, `alembic/versions/k04a_kpi_issue_links.py`
- Modify: `app/models/__init__.py`, `app/connectors/schemas.py`, `app/services/sync_service.py`
- Test: `tests/test_kpi_issue_links.py`

- [ ] **Step 1: Написать падающий тест**

```python
"""Связи задач сохраняются и позволяют найти автора связанной задачи."""
from app.models.issue_link import IssueLink


def test_issue_link_roundtrip(db_session, sample_project):
    from app.models.issue import Issue

    task = Issue(jira_issue_id="1", key="OS-10", summary="Задача", issue_type="Задача",
                 status="ГОТОВО", project_id=sample_project.id, reporter_account_id="acc-1")
    bug = Issue(jira_issue_id="2", key="OS-11", summary="Баг", issue_type="Баг",
                status="ГОТОВО", project_id=sample_project.id)
    db_session.add_all([task, bug])
    db_session.commit()

    db_session.add(IssueLink(
        source_issue_id=bug.id, target_issue_id=task.id, link_type="Relates",
    ))
    db_session.commit()

    linked = (
        db_session.query(Issue)
        .join(IssueLink, IssueLink.target_issue_id == Issue.id)
        .filter(IssueLink.source_issue_id == bug.id)
        .one()
    )
    assert linked.reporter_account_id == "acc-1"
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_kpi_issue_links.py -v`
Expected: FAIL, `No module named 'app.models.issue_link'`

- [ ] **Step 3: Модель**

`app/models/issue_link.py`:

```python
"""Связь между задачами Jira. Нужна KPI: баг привязан к задаче, автор которой оценивается."""
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class IssueLink(Base, TimestampMixin):
    """Направленная связь: source → target, тип из Jira ('Relates', 'Blocks', ...)."""

    __tablename__ = "issue_links"
    __table_args__ = (
        UniqueConstraint(
            "source_issue_id", "target_issue_id", "link_type", name="uq_issue_link"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<IssueLink {self.source_issue_id} -{self.link_type}-> {self.target_issue_id}>"
```

Добавить экспорт в `app/models/__init__.py` рядом с остальными.

- [ ] **Step 4: Миграция**

`alembic/versions/k04a_kpi_issue_links.py`, `down_revision = "k03a_kpi_issue_custom_fields"`:

```python
def upgrade() -> None:
    op.create_table(
        "issue_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_issue_id", sa.String(length=36),
                  sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_issue_id", sa.String(length=36),
                  sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_issue_id", "target_issue_id", "link_type",
                            name="uq_issue_link"),
    )
    op.create_index("ix_issue_links_source", "issue_links", ["source_issue_id"])
    op.create_index("ix_issue_links_target", "issue_links", ["target_issue_id"])
    op.create_index("ix_issue_links_type", "issue_links", ["link_type"])


def downgrade() -> None:
    op.drop_table("issue_links")
```

Точные имена колонок `created_at` / `updated_at` и их `server_default` сверить с любой существующей миграцией, создающей таблицу с `TimestampMixin`, например `alembic/versions/048_confluence_page_cache.py`.

- [ ] **Step 5: Выгрузка связей**

В `app/connectors/schemas.py`, `JiraIssueFieldsSchema`, добавить `issuelinks: Optional[list] = None` и внести `"issuelinks"` в список известных ключей.

В `app/services/sync_service.py` добавить `issuelinks` в запрашиваемые `fields=` и после `_upsert_issue` вызывать:

```python
def _sync_issue_links(db, issue, raw_links: list) -> None:
    """Пересобрать связи задачи. Ссылки на неизвестные локально задачи пропускаем."""
    from app.models.issue_link import IssueLink

    db.query(IssueLink).filter(IssueLink.source_issue_id == issue.id).delete()
    if not raw_links:
        return
    for link in raw_links:
        link_type = (link.get("type") or {}).get("name") or "Relates"
        other = link.get("outwardIssue") or link.get("inwardIssue")
        if not other:
            continue
        target = db.query(Issue).filter(Issue.jira_issue_id == str(other.get("id"))).first()
        if target is None:
            continue
        db.add(IssueLink(
            source_issue_id=issue.id, target_issue_id=target.id, link_type=link_type,
        ))
```

Связи собираются вторым проходом после того, как все задачи батча сохранены, иначе цель ещё не существует локально. Вызвать `_sync_issue_links` в конце обработки батча, пройдя по сохранённым задачам ещё раз.

- [ ] **Step 6: Прогнать и закоммитить**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m pytest tests/test_kpi_issue_links.py -v
git add app/models/issue_link.py app/models/__init__.py app/connectors/schemas.py app/services/sync_service.py alembic/versions/k04a_kpi_issue_links.py tests/test_kpi_issue_links.py
git commit -m "feat(kpi): выгрузка связей задач из Jira"
```

---

## Фаза 2 — справочники KPI

### Task 5: Модели справочников

**Files:**
- Create: `app/models/kpi.py`, `alembic/versions/k05a_kpi_dictionaries.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_kpi_models.py`

Формат условий отбора (JSON, хранится в колонке `Text`):

```json
{
  "unit": "issues",
  "person_field": "author",
  "period_window": "closed_in",
  "conditions": [
    {"attr": "project_key", "op": "in", "value": ["OS"]},
    {"attr": "issue_type", "op": "in", "value": ["Баг"]},
    {"attr": "resolution", "op": "in", "value": ["Готово"]},
    {"attr": "environment", "op": "eq", "value": "PROD"},
    {"attr": "field_filled", "op": "all", "value": ["goal_text", "current_behavior", "description"]},
    {"attr": "resolved_on_time", "op": "is_true"}
  ]
}
```

- `unit` — `issues` или `worklogs`
- `person_field` — `author`, `assignee`, `linked_issue_author`, `worklog_author`
- `period_window` — `closed_in` или `created_and_closed_in`
- `attr` — один из: `project_key`, `issue_type`, `subtype`, `status`, `resolution`, `environment`, `cost_type`, `direction`, `field_filled`, `resolved_on_time`, `has_linked_bug`
- `op` — `in`, `not_in`, `eq`, `ne`, `all`, `is_true`

- [ ] **Step 1: Написать падающий тест**

```python
"""Справочники KPI: метрика, профиль, вес, норматив, утверждение."""
import json

from app.models.kpi import KpiMetric, KpiProfile, KpiProfileMetric, KpiCycleTimeNorm


def test_metric_and_profile(db_session):
    metric = KpiMetric(
        code="quality",
        name="Качество выпуска",
        description="Обратная доля багов на проде",
        calc_kind="ratio",
        numerator_json=json.dumps({"unit": "issues", "person_field": "linked_issue_author",
                                   "period_window": "closed_in", "conditions": []}),
        denominator_json=json.dumps({"unit": "issues", "person_field": "author",
                                     "period_window": "closed_in", "conditions": []}),
        invert=True,
        cap_at_100=True,
    )
    profile = KpiProfile(code="analyst", name="Аналитик", role_code="analyst", target_pct=80.0)
    db_session.add_all([metric, profile])
    db_session.commit()

    db_session.add(KpiProfileMetric(profile_id=profile.id, metric_id=metric.id, weight=0.2))
    db_session.add(KpiCycleTimeNorm(team="Платежи", year=2026, quarter=3, norm_value=70.0))
    db_session.commit()

    loaded = db_session.query(KpiProfile).filter_by(code="analyst").one()
    assert loaded.target_pct == 80.0
    assert len(loaded.metrics) == 1
    assert loaded.metrics[0].weight == 0.2
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_kpi_models.py -v`
Expected: FAIL, `No module named 'app.models.kpi'`

- [ ] **Step 3: Модели**

`app/models/kpi.py`:

```python
"""Справочники раздела KPI. Метрики хранятся как данные, а не как код."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class KpiMetric(Base, TimestampMixin):
    """Определение метрики. calc_kind: ratio | norm_to_fact | score_to_max."""

    __tablename__ = "kpi_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    calc_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # ratio: оба набора; norm_to_fact и score_to_max: только numerator_json
    numerator_json: Mapped[str] = mapped_column(Text, nullable=False)
    denominator_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # norm_to_fact: имя поля задачи с фактом; score_to_max: список полей и максимум
    fact_field: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    score_fields: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cap_at_100: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class KpiProfile(Base, TimestampMixin):
    """Набор метрик с весами, привязанный к роли сотрудника."""

    __tablename__ = "kpi_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    target_pct: Mapped[float] = mapped_column(Float, nullable=False, default=80.0)
    warn_band_pct: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    metrics: Mapped[list["KpiProfileMetric"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )


class KpiProfileMetric(Base, TimestampMixin):
    """Вес метрики внутри профиля. Сумма весов профиля обязана равняться 1."""

    __tablename__ = "kpi_profile_metrics"
    __table_args__ = (UniqueConstraint("profile_id", "metric_id", name="uq_profile_metric"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kpi_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kpi_metrics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    profile: Mapped["KpiProfile"] = relationship(back_populates="metrics")
    metric: Mapped["KpiMetric"] = relationship(lazy="selectin")


class KpiCycleTimeNorm(Base, TimestampMixin):
    """Плановый Cycle Time на команду и квартал."""

    __tablename__ = "kpi_cycle_time_norms"
    __table_args__ = (UniqueConstraint("team", "year", "quarter", name="uq_kpi_ct_norm"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    norm_value: Mapped[float] = mapped_column(Float, nullable=False)


class KpiApproval(Base, TimestampMixin):
    """Снимок утверждённого месяца: результат вместе с весами и правилами на тот момент."""

    __tablename__ = "kpi_approvals"
    __table_args__ = (UniqueConstraint("team", "year", "month", name="uq_kpi_approval"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 4: Миграция**

`alembic/versions/k05a_kpi_dictionaries.py`, `down_revision = "k04a_kpi_issue_links"` — пять таблиц ровно по определениям выше, с уникальными ограничениями и индексами.

- [ ] **Step 5: Прогнать и закоммитить**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m pytest tests/test_kpi_models.py -v
git add app/models/kpi.py app/models/__init__.py alembic/versions/k05a_kpi_dictionaries.py tests/test_kpi_models.py
git commit -m "feat(kpi): справочники метрик, профилей, нормативов и утверждений"
```

---

### Task 6: Общие настройки раздела

Ключи в существующем хранилище настроек: `kpi_excluded_statuses` (JSON-массив, по умолчанию `["Отменено"]`), `kpi_worklog_deadline_days` (по умолчанию `1`), `kpi_worklog_deadline_time` (по умолчанию `"12:00"`), `kpi_empty_policy` (`redistribute` | `full` | `zero`, по умолчанию `redistribute`).

**Files:**
- Create: `app/services/kpi/__init__.py`, `app/services/kpi/settings.py`
- Test: `tests/services/test_kpi_settings.py`

- [ ] **Step 1: Тест**

```python
"""Общие настройки KPI читаются с дефолтами и переопределяются из базы."""
from app.models.app_setting import AppSetting
from app.services.kpi.settings import read_kpi_settings


def test_defaults_when_db_empty(db_session):
    s = read_kpi_settings(db_session)
    assert s.excluded_statuses == ["Отменено"]
    assert s.worklog_deadline_days == 1
    assert s.worklog_deadline_time == "12:00"
    assert s.empty_policy == "redistribute"


def test_overrides_from_db(db_session):
    db_session.add(AppSetting(key="kpi_worklog_deadline_time", value="15:30"))
    db_session.add(AppSetting(key="kpi_excluded_statuses", value='["Отменено", "Отклонено"]'))
    db_session.commit()

    s = read_kpi_settings(db_session)
    assert s.worklog_deadline_time == "15:30"
    assert "Отклонено" in s.excluded_statuses
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/services/test_kpi_settings.py -v`
Expected: FAIL, `No module named 'app.services.kpi'`

- [ ] **Step 3: Реализация**

`app/services/kpi/settings.py`:

```python
"""Общие настройки раздела KPI. Хранятся в AppSetting, читаются с дефолтами."""
import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

DEFAULT_EXCLUDED_STATUSES = ["Отменено"]


@dataclass
class KpiSettings:
    excluded_statuses: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDED_STATUSES))
    worklog_deadline_days: int = 1
    worklog_deadline_time: str = "12:00"
    empty_policy: str = "redistribute"


def read_kpi_settings(db: Session) -> KpiSettings:
    rows = {
        r.key: r.value
        for r in db.query(AppSetting).filter(AppSetting.key.like("kpi_%")).all()
    }
    s = KpiSettings()
    raw_statuses = rows.get("kpi_excluded_statuses")
    if raw_statuses:
        try:
            parsed = json.loads(raw_statuses)
            if isinstance(parsed, list):
                s.excluded_statuses = [str(x) for x in parsed]
        except json.JSONDecodeError:
            pass
    if rows.get("kpi_worklog_deadline_days"):
        try:
            s.worklog_deadline_days = int(rows["kpi_worklog_deadline_days"])
        except ValueError:
            pass
    if rows.get("kpi_worklog_deadline_time"):
        s.worklog_deadline_time = rows["kpi_worklog_deadline_time"]
    if rows.get("kpi_empty_policy") in {"redistribute", "full", "zero"}:
        s.empty_policy = rows["kpi_empty_policy"]
    return s
```

`app/services/kpi/__init__.py` — пустой файл с докстрокой `"""Раздел KPI: справочники, расчёт, снимки."""`.

- [ ] **Step 4: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/services/test_kpi_settings.py -v
git add app/services/kpi/ tests/services/test_kpi_settings.py
git commit -m "feat(kpi): общие настройки раздела"
```

---

## Фаза 3 — движок расчёта

### Task 7: Транслятор условий отбора

**Files:**
- Create: `app/services/kpi/conditions.py`
- Test: `tests/services/test_kpi_conditions.py`

- [ ] **Step 1: Тест**

```python
"""Условия отбора превращаются в запрос к задачам."""
import json
from datetime import date, datetime

from app.models.issue import Issue
from app.services.kpi.conditions import ConditionSet, build_issue_query


def _make_issue(db, project, **kw):
    defaults = dict(
        jira_issue_id=kw.pop("jid", "1"), key=kw.pop("key", "OS-1"), summary="s",
        issue_type="Задача", status="ГОТОВО", status_category="done",
        project_id=project.id,
    )
    defaults.update(kw)
    issue = Issue(**defaults)
    db.add(issue)
    return issue


def test_filters_by_project_type_resolution(db_session, sample_project):
    _make_issue(db_session, sample_project, jid="1", key="OS-1", issue_type="Баг",
                resolution="Готово", environment="PROD", reporter_account_id="acc-1",
                resolved_at=datetime(2026, 7, 10))
    _make_issue(db_session, sample_project, jid="2", key="OS-2", issue_type="Баг",
                resolution="Отменено", environment="PROD", reporter_account_id="acc-1",
                resolved_at=datetime(2026, 7, 11))
    db_session.commit()

    cs = ConditionSet.from_json(json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [
            {"attr": "issue_type", "op": "in", "value": ["Баг"]},
            {"attr": "resolution", "op": "in", "value": ["Готово"]},
            {"attr": "environment", "op": "eq", "value": "PROD"},
        ],
    }))
    q = build_issue_query(
        db_session, cs, account_id="acc-1",
        period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
        excluded_statuses=["Отменено"], teams=None,
    )
    keys = sorted(i.key for i in q.all())
    assert keys == ["OS-1"]


def test_field_filled_requires_all_fields(db_session, sample_project):
    _make_issue(db_session, sample_project, jid="3", key="OS-3", reporter_account_id="acc-1",
                resolution="Готово", resolved_at=datetime(2026, 7, 10),
                goal_text="цель", current_behavior="как сейчас", description="описание")
    _make_issue(db_session, sample_project, jid="4", key="OS-4", reporter_account_id="acc-1",
                resolution="Готово", resolved_at=datetime(2026, 7, 10),
                goal_text="цель", current_behavior=None, description="описание")
    db_session.commit()

    cs = ConditionSet.from_json(json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [{"attr": "field_filled", "op": "all",
                        "value": ["goal_text", "current_behavior", "description"]}],
    }))
    q = build_issue_query(db_session, cs, account_id="acc-1",
                          period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
                          excluded_statuses=[], teams=None)
    assert [i.key for i in q.all()] == ["OS-3"]
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/services/test_kpi_conditions.py -v`
Expected: FAIL, `No module named 'app.services.kpi.conditions'`

- [ ] **Step 3: Реализация**

`app/services/kpi/conditions.py`:

```python
"""Трансляция условий отбора KPI в запросы SQLAlchemy.

Условия хранятся в метрике как JSON. Ни одно условие не зашито в код расчёта —
здесь только словарь допустимых атрибутов и способ их сравнения.
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Query, Session, aliased

from app.models.issue import Issue
from app.models.issue_link import IssueLink
from app.models.project import Project

# Атрибут условия → колонка задачи
ATTR_COLUMNS = {
    "issue_type": Issue.issue_type,
    "subtype": Issue.subtype,
    "status": Issue.status,
    "resolution": Issue.resolution,
    "environment": Issue.environment,
    "cost_type": Issue.cost_type,
    "direction": Issue.direction,
    "category": Issue.category,
}

# Поля, заполненность которых можно проверять
FILLABLE_FIELDS = {
    "goal_text": Issue.goal_text,
    "current_behavior": Issue.current_behavior,
    "description": Issue.description,
    "goals": Issue.goals,
}

PERSON_FIELDS = {"author", "assignee", "linked_issue_author", "worklog_author"}
PERIOD_WINDOWS = {"closed_in", "created_and_closed_in"}


@dataclass
class Condition:
    attr: str
    op: str
    value: object = None


@dataclass
class ConditionSet:
    unit: str = "issues"
    person_field: str = "author"
    period_window: str = "closed_in"
    conditions: list[Condition] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: Optional[str]) -> "ConditionSet":
        if not raw:
            return cls()
        data = json.loads(raw)
        return cls(
            unit=data.get("unit", "issues"),
            person_field=data.get("person_field", "author"),
            period_window=data.get("period_window", "closed_in"),
            conditions=[
                Condition(attr=c["attr"], op=c.get("op", "in"), value=c.get("value"))
                for c in data.get("conditions", [])
            ],
        )


def _apply_condition(clauses: list, cond: Condition) -> None:
    """Одно условие → предикат. Неизвестный атрибут молча пропускается."""
    if cond.attr == "project_key":
        values = cond.value if isinstance(cond.value, list) else [cond.value]
        sub = select(Project.id).where(Project.key.in_(values))
        clauses.append(
            Issue.project_id.in_(sub) if cond.op != "not_in"
            else ~Issue.project_id.in_(sub)
        )
        return

    if cond.attr == "field_filled":
        names = cond.value if isinstance(cond.value, list) else [cond.value]
        for name in names:
            col = FILLABLE_FIELDS.get(name)
            if col is None:
                continue
            clauses.append(and_(col.isnot(None), col != ""))
        return

    if cond.attr == "resolved_on_time":
        clauses.append(
            and_(
                Issue.resolved_at.isnot(None),
                Issue.planned_end_date.isnot(None),
                Issue.resolved_at <= Issue.planned_end_date,
            )
        )
        return

    if cond.attr == "has_linked_bug":
        linked = aliased(Issue)
        sub = (
            select(IssueLink.target_issue_id)
            .join(linked, linked.id == IssueLink.source_issue_id)
            .where(linked.issue_type == "Баг")
        )
        clauses.append(Issue.id.in_(sub))
        return

    col = ATTR_COLUMNS.get(cond.attr)
    if col is None:
        return
    if cond.op == "in":
        values = cond.value if isinstance(cond.value, list) else [cond.value]
        clauses.append(col.in_(values))
    elif cond.op == "not_in":
        values = cond.value if isinstance(cond.value, list) else [cond.value]
        clauses.append(~col.in_(values))
    elif cond.op == "eq":
        clauses.append(col == cond.value)
    elif cond.op == "ne":
        clauses.append(col != cond.value)


def _person_clause(cs: ConditionSet, account_id: str):
    """Как задача связана с оцениваемым человеком."""
    if cs.person_field == "assignee":
        return Issue.assignee_account_id == account_id
    if cs.person_field == "linked_issue_author":
        linked = aliased(Issue)
        sub = (
            select(IssueLink.source_issue_id)
            .join(linked, linked.id == IssueLink.target_issue_id)
            .where(linked.reporter_account_id == account_id)
        )
        return Issue.id.in_(sub)
    return Issue.reporter_account_id == account_id


def _period_clause(cs: ConditionSet, period_start: date, period_end: date):
    start = datetime.combine(period_start, datetime.min.time())
    end = datetime.combine(period_end, datetime.max.time())
    closed = and_(Issue.resolved_at.isnot(None), Issue.resolved_at.between(start, end))
    if cs.period_window == "created_and_closed_in":
        return and_(closed, Issue.created_at.between(start, end))
    return closed


def build_issue_query(
    db: Session,
    cs: ConditionSet,
    account_id: str,
    period_start: date,
    period_end: date,
    excluded_statuses: list[str],
    teams: Optional[list[str]],
) -> Query:
    """Запрос задач, попадающих под набор условий, для одного человека и периода."""
    clauses = [_person_clause(cs, account_id), _period_clause(cs, period_start, period_end)]
    for cond in cs.conditions:
        _apply_condition(clauses, cond)
    if excluded_statuses:
        clauses.append(or_(Issue.status.is_(None), ~Issue.status.in_(excluded_statuses)))
    if teams:
        clauses.append(Issue.team.in_(teams))
    return db.query(Issue).filter(and_(*clauses))
```

Если `Issue.created_at` — это техническая дата записи в нашей базе, а не дата создания задачи в Jira, использовать поле с датой создания из Jira. Проверить `app/models/issue.py` и при необходимости взять `jira_created_at` (если такого поля нет — добавить его в Task 3 тем же способом, что `resolved_at`).

- [ ] **Step 4: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/services/test_kpi_conditions.py -v
git add app/services/kpi/conditions.py tests/services/test_kpi_conditions.py
git commit -m "feat(kpi): транслятор условий отбора"
```

---

### Task 8: Срок внесения трудозатрат по производственному календарю

**Files:**
- Create: `app/services/kpi/timeliness.py`
- Test: `tests/services/test_kpi_timeliness.py`

- [ ] **Step 1: Тест**

```python
"""Часы за пятницу можно внести до 12:00 понедельника — выходные не считаются."""
from datetime import date, datetime

from app.models.production_calendar_day import ProductionCalendarDay
from app.services.kpi.timeliness import deadline_for, is_late


def _seed_week(db):
    days = {
        date(2026, 7, 24): True,   # пятница
        date(2026, 7, 25): False,  # суббота
        date(2026, 7, 26): False,  # воскресенье
        date(2026, 7, 27): True,   # понедельник
        date(2026, 7, 28): True,
    }
    for d, workday in days.items():
        db.add(ProductionCalendarDay(
            date=d, is_workday=workday,
            kind="workday" if workday else "weekend",
            hours=8.0 if workday else 0.0, source="manual",
            synced_at=datetime(2026, 7, 1),
        ))
    db.commit()


def test_deadline_skips_weekend(db_session):
    _seed_week(db_session)
    assert deadline_for(db_session, date(2026, 7, 24), days=1, time_str="12:00") == \
        datetime(2026, 7, 27, 12, 0)


def test_late_detection(db_session):
    _seed_week(db_session)
    assert is_late(db_session, date(2026, 7, 24), datetime(2026, 7, 27, 11, 0), 1, "12:00") is False
    assert is_late(db_session, date(2026, 7, 24), datetime(2026, 7, 27, 12, 1), 1, "12:00") is True
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/services/test_kpi_timeliness.py -v`
Expected: FAIL, `No module named 'app.services.kpi.timeliness'`

- [ ] **Step 3: Реализация**

`app/services/kpi/timeliness.py`:

```python
"""Срок внесения трудозатрат: до указанного времени N-го рабочего дня после дня работы."""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.production_calendar_day import ProductionCalendarDay

MAX_LOOKAHEAD_DAYS = 30


def _is_workday(db: Session, day: date) -> bool:
    """Нет записи в календаре — считаем рабочими Пн–Пт (тот же fallback, что в ресурсах)."""
    row = db.query(ProductionCalendarDay).filter(ProductionCalendarDay.date == day).first()
    if row is None:
        return day.weekday() < 5
    return bool(row.is_workday)


def deadline_for(db: Session, work_day: date, days: int, time_str: str) -> datetime:
    """Крайний момент внесения часов за `work_day`."""
    hh, _, mm = time_str.partition(":")
    hour, minute = int(hh), int(mm or 0)
    remaining = max(1, days)
    cursor = work_day
    for _ in range(MAX_LOOKAHEAD_DAYS):
        cursor = cursor + timedelta(days=1)
        if _is_workday(db, cursor):
            remaining -= 1
            if remaining == 0:
                return datetime(cursor.year, cursor.month, cursor.day, hour, minute)
    # Календарь не дал ни одного рабочего дня — не штрафуем.
    return datetime(work_day.year, work_day.month, work_day.day, hour, minute) + timedelta(days=days)


def is_late(
    db: Session, work_day: date, created_at: Optional[datetime], days: int, time_str: str
) -> bool:
    """Запись просрочена, если внесена позже крайнего момента. Без даты внесения — не судим."""
    if created_at is None:
        return False
    return created_at > deadline_for(db, work_day, days, time_str)
```

- [ ] **Step 4: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/services/test_kpi_timeliness.py -v
git add app/services/kpi/timeliness.py tests/services/test_kpi_timeliness.py
git commit -m "feat(kpi): срок внесения трудозатрат по производственному календарю"
```

---

### Task 9: Три способа расчёта

**Files:**
- Create: `app/services/kpi/calculators.py`
- Test: `tests/services/test_kpi_calculators.py`

- [ ] **Step 1: Тест**

```python
"""Три способа расчёта дают ожидаемые числа и корректно ведут себя на пустых данных."""
from app.services.kpi.calculators import MetricResult, ratio, norm_to_fact, score_to_max


def test_ratio_plain():
    r = ratio(numerator=8, denominator=10, invert=False, cap_at_100=True)
    assert r.value == 80.0
    assert r.has_data is True


def test_ratio_inverted_for_bugs():
    r = ratio(numerator=3, denominator=15, invert=True, cap_at_100=True)
    assert r.value == 80.0


def test_ratio_zero_numerator_gives_full_when_inverted():
    r = ratio(numerator=0, denominator=15, invert=True, cap_at_100=True)
    assert r.value == 100.0


def test_ratio_no_denominator_is_no_data():
    r = ratio(numerator=0, denominator=0, invert=False, cap_at_100=True)
    assert r.has_data is False
    assert r.value is None


def test_norm_to_fact_capped():
    assert norm_to_fact(norm=80.0, facts=[75.0]).value == 100.0
    assert round(norm_to_fact(norm=70.0, facts=[100.0]).value, 1) == 70.0
    assert norm_to_fact(norm=70.0, facts=[]).has_data is False


def test_score_to_max():
    r = score_to_max(scores=[[5, 4, 3], [4, 4, 4]], score_max=5.0)
    assert round(r.value, 1) == 80.0
    assert score_to_max(scores=[], score_max=5.0).has_data is False
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/services/test_kpi_calculators.py -v`
Expected: FAIL, `No module named 'app.services.kpi.calculators'`

- [ ] **Step 3: Реализация**

`app/services/kpi/calculators.py`:

```python
"""Три способа расчёта метрики. Ничего предметного здесь нет — только арифметика."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class MetricResult:
    value: Optional[float]
    has_data: bool
    numerator: Optional[float] = None
    denominator: Optional[float] = None


def _cap(value: float, cap_at_100: bool) -> float:
    capped = min(value, 100.0) if cap_at_100 else value
    return max(capped, 0.0)


def ratio(numerator: int, denominator: int, invert: bool, cap_at_100: bool) -> MetricResult:
    """Доля одного множества в другом, в процентах."""
    if denominator <= 0:
        return MetricResult(value=None, has_data=False, numerator=numerator, denominator=denominator)
    pct = numerator / denominator * 100.0
    if invert:
        pct = 100.0 - pct
    return MetricResult(
        value=_cap(pct, cap_at_100), has_data=True,
        numerator=numerator, denominator=denominator,
    )


def norm_to_fact(norm: Optional[float], facts: list[float]) -> MetricResult:
    """Норматив к среднему факту. Потолок 100 всегда — превышение норматива не премируется."""
    usable = [f for f in facts if f is not None and f > 0]
    if not norm or not usable:
        return MetricResult(value=None, has_data=False, numerator=norm,
                            denominator=len(usable) or None)
    avg_fact = sum(usable) / len(usable)
    return MetricResult(
        value=_cap(norm / avg_fact * 100.0, True), has_data=True,
        numerator=norm, denominator=avg_fact,
    )


def score_to_max(scores: list[list[float]], score_max: float) -> MetricResult:
    """Средний балл к максимуму. Каждая задача даёт среднее своих оценок."""
    per_issue = []
    for row in scores:
        usable = [x for x in row if x is not None]
        if usable:
            per_issue.append(sum(usable) / len(usable))
    if not per_issue or not score_max:
        return MetricResult(value=None, has_data=False)
    avg = sum(per_issue) / len(per_issue)
    return MetricResult(
        value=_cap(avg / score_max * 100.0, True), has_data=True,
        numerator=avg, denominator=score_max,
    )
```

- [ ] **Step 4: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/services/test_kpi_calculators.py -v
git add app/services/kpi/calculators.py tests/services/test_kpi_calculators.py
git commit -m "feat(kpi): три способа расчёта метрики"
```

---

### Task 10: Сервис расчёта

Собирает всё: по профилю сотрудника считает каждую метрику, применяет политику пустых данных, перераспределяет веса, даёт итог.

**Files:**
- Create: `app/services/kpi/kpi_service.py`
- Test: `tests/services/test_kpi_service.py`

- [ ] **Step 1: Тест на перераспределение весов**

```python
"""Метрика без данных не обнуляет итог, а перераспределяет вес."""
from app.services.kpi.calculators import MetricResult
from app.services.kpi.kpi_service import combine


def test_weights_redistributed_when_metric_has_no_data():
    parts = [
        ("quality", MetricResult(90.0, True), 0.5),
        ("timeliness", MetricResult(70.0, True), 0.3),
        ("customer", MetricResult(None, False), 0.2),
    ]
    total = combine(parts, empty_policy="redistribute")
    # 0.5 и 0.3 нормируются до 0.625 и 0.375
    assert round(total, 2) == round(90 * 0.625 + 70 * 0.375, 2)


def test_policy_full_counts_missing_as_hundred():
    parts = [("a", MetricResult(80.0, True), 0.5), ("b", MetricResult(None, False), 0.5)]
    assert combine(parts, empty_policy="full") == 90.0


def test_policy_zero_counts_missing_as_zero():
    parts = [("a", MetricResult(80.0, True), 0.5), ("b", MetricResult(None, False), 0.5)]
    assert combine(parts, empty_policy="zero") == 40.0


def test_all_metrics_missing_gives_none():
    parts = [("a", MetricResult(None, False), 1.0)]
    assert combine(parts, empty_policy="redistribute") is None
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/services/test_kpi_service.py -v`
Expected: FAIL, `No module named 'app.services.kpi.kpi_service'`

- [ ] **Step 3: Реализация — функция сведения**

`app/services/kpi/kpi_service.py`, первая часть:

```python
"""Расчёт KPI: по сотруднику, команде и периоду."""
import json
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.issue import Issue
from app.models.kpi import KpiCycleTimeNorm, KpiMetric, KpiProfile
from app.models.worklog import Worklog
from app.services.kpi.calculators import MetricResult, norm_to_fact, ratio, score_to_max
from app.services.kpi.conditions import ConditionSet, build_issue_query
from app.services.kpi.settings import KpiSettings, read_kpi_settings
from app.services.kpi.timeliness import is_late
from app.services.team_membership import member_intervals, members_overlapping


def combine(
    parts: list[tuple[str, MetricResult, float]], empty_policy: str
) -> Optional[float]:
    """Взвешенная сумма метрик с учётом политики пустых данных."""
    if empty_policy == "redistribute":
        usable = [(r.value, w) for _, r, w in parts if r.has_data and r.value is not None]
        total_weight = sum(w for _, w in usable)
        if not usable or total_weight <= 0:
            return None
        return sum(v * w for v, w in usable) / total_weight
    fill = 100.0 if empty_policy == "full" else 0.0
    total_weight = sum(w for _, _, w in parts)
    if total_weight <= 0:
        return None
    acc = 0.0
    for _, r, w in parts:
        acc += (r.value if r.has_data and r.value is not None else fill) * w
    return acc / total_weight
```

- [ ] **Step 4: Прогнать тест на сведение**

Run: `py -3.10 -m pytest tests/services/test_kpi_service.py -v`
Expected: PASS

- [ ] **Step 5: Тест на расчёт одной метрики от начала до конца**

Дописать в `tests/services/test_kpi_service.py`:

```python
def test_quality_metric_end_to_end(db_session, sample_project):
    """Три бага на пятнадцать выпущенных задач дают 80%."""
    import json as _json
    from datetime import datetime

    from app.models.employee import Employee
    from app.models.issue import Issue
    from app.models.issue_link import IssueLink
    from app.models.kpi import KpiMetric
    from app.services.kpi.kpi_service import compute_metric

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    db_session.commit()

    released = []
    for i in range(15):
        issue = Issue(
            jira_issue_id=f"r{i}", key=f"OS-{100 + i}", summary="Задача",
            issue_type="Задача", status="ГОТОВО", status_category="done",
            resolution="Готово", resolved_at=datetime(2026, 7, 10),
            project_id=sample_project.id, reporter_account_id="acc-1", team="Платежи",
        )
        db_session.add(issue)
        released.append(issue)
    db_session.commit()

    for i in range(3):
        bug = Issue(
            jira_issue_id=f"b{i}", key=f"OS-{200 + i}", summary="Баг",
            issue_type="Баг", status="ГОТОВО", status_category="done",
            resolution="Готово", environment="PROD", resolved_at=datetime(2026, 7, 12),
            project_id=sample_project.id, team="Платежи",
        )
        db_session.add(bug)
        db_session.commit()
        db_session.add(IssueLink(source_issue_id=bug.id, target_issue_id=released[i].id,
                                 link_type="Relates"))
    db_session.commit()

    metric = KpiMetric(
        code="quality", name="Качество выпуска", calc_kind="ratio", invert=True, cap_at_100=True,
        numerator_json=_json.dumps({
            "unit": "issues", "person_field": "linked_issue_author", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Баг"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
                {"attr": "environment", "op": "eq", "value": "PROD"},
            ],
        }),
        denominator_json=_json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Задача", "Баг"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
            ],
        }),
    )
    db_session.add(metric)
    db_session.commit()

    result = compute_metric(
        db_session, metric, account_id="acc-1",
        period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
        teams=["Платежи"], settings=None,
    )
    assert result.has_data is True
    assert round(result.value, 1) == 80.0
```

- [ ] **Step 6: Реализация расчёта метрики**

Дописать в `app/services/kpi/kpi_service.py`:

```python
def compute_metric(
    db: Session,
    metric: KpiMetric,
    account_id: str,
    period_start: date,
    period_end: date,
    teams: Optional[list[str]],
    settings: Optional[KpiSettings] = None,
    norm_value: Optional[float] = None,
) -> MetricResult:
    """Посчитать одну метрику для одного человека за период."""
    st = settings or read_kpi_settings(db)
    num_cs = ConditionSet.from_json(metric.numerator_json)

    if metric.calc_kind == "ratio":
        den_cs = ConditionSet.from_json(metric.denominator_json)
        if num_cs.unit == "worklogs":
            return _ratio_over_worklogs(db, metric, num_cs, account_id,
                                        period_start, period_end, teams, st)
        num_q = build_issue_query(db, num_cs, account_id, period_start, period_end,
                                  st.excluded_statuses, teams)
        den_q = build_issue_query(db, den_cs, account_id, period_start, period_end,
                                  st.excluded_statuses, teams)
        return ratio(num_q.count(), den_q.count(), metric.invert, metric.cap_at_100)

    if metric.calc_kind == "norm_to_fact":
        q = build_issue_query(db, num_cs, account_id, period_start, period_end,
                              st.excluded_statuses, teams)
        facts = [i.cycle_time_fact for i in q.all() if i.cycle_time_fact]
        return norm_to_fact(norm_value, facts)

    if metric.calc_kind == "score_to_max":
        q = build_issue_query(db, num_cs, account_id, period_start, period_end,
                              st.excluded_statuses, teams)
        names = json.loads(metric.score_fields or '["rating_speed","rating_quality","rating_result"]')
        rows = []
        for issue in q.all():
            row = [getattr(issue, n, None) for n in names]
            if any(v is not None for v in row):
                rows.append(row)
        return score_to_max(rows, metric.score_max or 5.0)

    return MetricResult(value=None, has_data=False)


def _ratio_over_worklogs(
    db: Session, metric: KpiMetric, cs: ConditionSet, account_id: str,
    period_start: date, period_end: date, teams: Optional[list[str]], st: KpiSettings,
) -> MetricResult:
    """Своевременность внесения часов. Единица счёта — запись, а не задача."""
    emp = db.query(Employee).filter(Employee.jira_account_id == account_id).first()
    if emp is None:
        return MetricResult(value=None, has_data=False)
    q = (
        db.query(Worklog)
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(Worklog.employee_id == emp.id)
        .filter(Worklog.started_at >= period_start)
        .filter(Worklog.started_at <= period_end)
    )
    project_keys = [
        c.value for c in cs.conditions
        if c.attr == "project_key"
    ]
    if project_keys:
        from app.models.project import Project

        keys = project_keys[0] if isinstance(project_keys[0], list) else project_keys
        q = q.filter(Issue.project_id.in_(
            db.query(Project.id).filter(Project.key.in_(keys)).scalar_subquery()
        ))
    rows = q.all()
    if not rows:
        return MetricResult(value=None, has_data=False)
    late = sum(
        1 for w in rows
        if is_late(db, w.started_at.date(), w.jira_created_at,
                   st.worklog_deadline_days, st.worklog_deadline_time)
    )
    return ratio(late, len(rows), invert=True, cap_at_100=True)
```

- [ ] **Step 7: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/services/test_kpi_service.py -v
git add app/services/kpi/kpi_service.py tests/services/test_kpi_service.py
git commit -m "feat(kpi): расчёт метрик и сведение итога"
```

---

### Task 11: Отчёт по команде и период

**Files:**
- Modify: `app/services/kpi/kpi_service.py`
- Test: `tests/services/test_kpi_report.py`

- [ ] **Step 1: Тест**

```python
"""Отчёт возвращает людей команды с метриками и итогом, учитывая период участия."""
from datetime import date, datetime

from app.services.kpi.kpi_service import build_report


def test_report_lists_only_team_members(db_session, sample_project):
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи",
                   role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.commit()

    report = build_report(db_session, teams=["Платежи"], year=2026, month=7)
    assert [r["employee_name"] for r in report["rows"]] == ["Иванов И."]
    assert "metrics" in report["rows"][0]
```

Точные названия полей `EmployeeTeam` проверить в `app/models/employee_team.py` — там периодизованное участие с `joined_at` / `left_at`.

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/services/test_kpi_report.py -v`
Expected: FAIL, `cannot import name 'build_report'`

- [ ] **Step 3: Реализация**

Дописать в `app/services/kpi/kpi_service.py`:

```python
QUARTER_OF_MONTH = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 3, 8: 3, 9: 3,
                    10: 4, 11: 4, 12: 4}


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _profile_for(db: Session, employee: Employee) -> Optional[KpiProfile]:
    """Профиль по роли сотрудника; если для роли профиля нет — первый включённый."""
    if employee.role:
        p = (
            db.query(KpiProfile)
            .filter(KpiProfile.role_code == employee.role, KpiProfile.is_enabled.is_(True))
            .first()
        )
        if p:
            return p
    return db.query(KpiProfile).filter(KpiProfile.is_enabled.is_(True)).first()


def _norm_for(db: Session, team: str, year: int, month: int) -> Optional[float]:
    row = (
        db.query(KpiCycleTimeNorm)
        .filter(
            KpiCycleTimeNorm.team == team,
            KpiCycleTimeNorm.year == year,
            KpiCycleTimeNorm.quarter == QUARTER_OF_MONTH[month],
        )
        .first()
    )
    return row.norm_value if row else None


def build_report(db: Session, teams: list[str], year: int, month: int) -> dict:
    """Отчёт по людям выбранных команд за месяц."""
    st = read_kpi_settings(db)
    period_start, period_end = month_bounds(year, month)
    employees = members_overlapping(db, teams, period_start, period_end)

    rows = []
    for emp in employees:
        profile = _profile_for(db, emp)
        if profile is None:
            continue
        intervals = member_intervals(db, teams, period_start, period_end)
        emp_intervals = [iv for iv in intervals if iv.employee_id == emp.id] \
            if hasattr(intervals[0] if intervals else None, "employee_id") else None
        eff_start, eff_end = period_start, period_end
        if emp_intervals:
            eff_start = max(period_start, min(iv.start for iv in emp_intervals))
            eff_end = min(period_end, max(iv.end for iv in emp_intervals))

        parts = []
        metric_payload = []
        for link in sorted(profile.metrics, key=lambda m: m.sort_order):
            norm = _norm_for(db, emp.team or (teams[0] if teams else ""), year, month) \
                if link.metric.calc_kind == "norm_to_fact" else None
            res = compute_metric(
                db, link.metric, emp.jira_account_id, eff_start, eff_end,
                teams, settings=st, norm_value=norm,
            )
            parts.append((link.metric.code, res, link.weight))
            metric_payload.append({
                "code": link.metric.code,
                "name": link.metric.name,
                "weight": link.weight,
                "value": res.value,
                "has_data": res.has_data,
                "numerator": res.numerator,
                "denominator": res.denominator,
            })

        rows.append({
            "employee_id": emp.id,
            "employee_name": emp.display_name,
            "account_id": emp.jira_account_id,
            "team": emp.team,
            "profile_code": profile.code,
            "target_pct": profile.target_pct,
            "warn_band_pct": profile.warn_band_pct,
            "metrics": metric_payload,
            "total": combine(parts, st.empty_policy),
        })

    rows.sort(key=lambda r: (r["total"] is None, r["total"] or 0))
    return {"year": year, "month": month, "teams": teams, "rows": rows}
```

Сигнатуры `members_overlapping` и `member_intervals` уточнить в `app/services/team_membership.py` — они уже существуют, но форма возвращаемых данных другая; подогнать код под фактическую. Если `member_intervals` возвращает отрезки без привязки к сотруднику, вызвать её отдельно для каждого сотрудника.

- [ ] **Step 4: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/services/test_kpi_report.py -v
git add app/services/kpi/kpi_service.py tests/services/test_kpi_report.py
git commit -m "feat(kpi): отчёт по команде за период"
```

---

### Task 12: Шесть метрик по умолчанию

**Files:**
- Create: `app/services/kpi/seed.py`, `alembic/versions/k06a_kpi_seed_defaults.py`
- Test: `tests/services/test_kpi_seed.py`

- [ ] **Step 1: Тест**

```python
"""Первый запуск заводит шесть метрик и профиль «Аналитик» с суммой весов 1."""
from app.models.kpi import KpiMetric, KpiProfile
from app.services.kpi.seed import seed_defaults


def test_seed_creates_six_metrics_and_profile(db_session):
    seed_defaults(db_session)
    db_session.commit()

    codes = {m.code for m in db_session.query(KpiMetric).all()}
    assert codes == {"quality", "deadlines", "regulations", "cycle_time",
                     "customer_score", "worklog_timeliness"}

    profile = db_session.query(KpiProfile).filter_by(code="analyst").one()
    assert round(sum(link.weight for link in profile.metrics), 6) == 1.0


def test_seed_is_idempotent(db_session):
    seed_defaults(db_session)
    db_session.commit()
    seed_defaults(db_session)
    db_session.commit()
    assert db_session.query(KpiMetric).count() == 6
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/services/test_kpi_seed.py -v`
Expected: FAIL

- [ ] **Step 3: Реализация**

`app/services/kpi/seed.py` — функция `seed_defaults(db)`, создающая шесть метрик ровно по разделу 3 спеки и профиль `analyst` с весами 0.2 / 0.2 / 0.2 / 0.2 / 0.1 / 0.1. Каждая метрика создаётся только если `code` ещё не занят. Наборы условий — те, что описаны в спеке; для примера метрика «Соблюдение регламентов»:

```python
    _ensure(db, KpiMetric(
        code="regulations",
        name="Соблюдение регламентов",
        description="Доля задач, поставленных в разработку с заполненными обязательными полями",
        calc_kind="ratio", invert=False, cap_at_100=True, is_builtin=True, sort_order=30,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "author",
            "period_window": "created_and_closed_in",
            "conditions": [
                {"attr": "project_key", "op": "in", "value": ["OS"]},
                {"attr": "issue_type", "op": "in", "value": ["Задача"]},
                {"attr": "status", "op": "not_in", "value": ["Backlog", "Бэклог"]},
                {"attr": "field_filled", "op": "all",
                 "value": ["goal_text", "current_behavior", "description"]},
            ],
        }, ensure_ascii=False),
        denominator_json=json.dumps({
            "unit": "issues", "person_field": "author",
            "period_window": "created_and_closed_in",
            "conditions": [
                {"attr": "project_key", "op": "in", "value": ["OS"]},
                {"attr": "issue_type", "op": "in", "value": ["Задача"]},
                {"attr": "status", "op": "not_in", "value": ["Backlog", "Бэклог"]},
            ],
        }, ensure_ascii=False),
    ))
```

Остальные пять — по тому же образцу: `quality` (инверсия, числитель по `linked_issue_author`, окружение PROD), `deadlines` (тип «Эпик»/«ИТ-задача», исполнитель, `resolved_on_time` в числителе), `cycle_time` (`calc_kind="norm_to_fact"`, `fact_field="cycle_time_fact"`, подтип RFC_STANDARD/PROJECT, тип затрат Change), `customer_score` (`calc_kind="score_to_max"`, `score_fields='["rating_speed","rating_quality","rating_result"]'`, `score_max=5.0`), `worklog_timeliness` (`unit: "worklogs"`, проекты OS/PMD/AD, инверсия).

- [ ] **Step 4: Миграция, вызывающая заполнение**

`alembic/versions/k06a_kpi_seed_defaults.py`, `down_revision = "k05a_kpi_dictionaries"`:

```python
def upgrade() -> None:
    from sqlalchemy.orm import Session

    from app.services.kpi.seed import seed_defaults

    bind = op.get_bind()
    session = Session(bind=bind)
    seed_defaults(session)
    session.commit()


def downgrade() -> None:
    op.execute("DELETE FROM kpi_profile_metrics")
    op.execute("DELETE FROM kpi_profiles WHERE code = 'analyst'")
    op.execute("DELETE FROM kpi_metrics WHERE is_builtin = 1")
```

- [ ] **Step 5: Прогнать и закоммитить**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m pytest tests/services/test_kpi_seed.py -v
git add app/services/kpi/seed.py alembic/versions/k06a_kpi_seed_defaults.py tests/services/test_kpi_seed.py
git commit -m "feat(kpi): шесть метрик и профиль «Аналитик» по умолчанию"
```

---

## Фаза 4 — API

### Task 13: Отчёт, расшифровка, утверждение

**Files:**
- Create: `app/api/endpoints/kpi.py`
- Modify: `app/api/router.py`
- Test: `tests/test_kpi_endpoints.py`

Маршруты:
- `GET /kpi/report?year=&month=&teams=&direction=` — строки по людям и сводка
- `GET /kpi/teams-summary?year=&month=&direction=` — итог по каждой команде плюс дельта к прошлому месяцу
- `GET /kpi/breakdown?account_id=&metric_code=&year=&month=&teams=` — задачи числителя и знаменателя
- `POST /kpi/approve` — заморозить месяц, тело `{team, year, month}`
- `GET /kpi/approval?team=&year=&month=` — кто и когда утвердил
- `GET /kpi/trend?account_id=&year=&month=&months=6&teams=` — итог и метрики за последние N месяцев для графика в карточке
- `GET /kpi/export.xlsx?...` — выгрузка

- [ ] **Step 1: Тест**

```python
"""Эндпоинты KPI отвечают и уважают авторизацию."""


def test_report_requires_auth(client):
    assert client.get("/api/v1/kpi/report?year=2026&month=7").status_code in (401, 403)


def test_report_returns_rows(auth_client, db_session, sample_project):
    resp = auth_client.get("/api/v1/kpi/report?year=2026&month=7&teams=Платежи")
    assert resp.status_code == 200
    body = resp.json()
    assert "rows" in body and "summary" in body


def test_approve_and_read_back(auth_client):
    resp = auth_client.post("/api/v1/kpi/approve",
                            json={"team": "Платежи", "year": 2026, "month": 7})
    assert resp.status_code == 200
    got = auth_client.get("/api/v1/kpi/approval?team=Платежи&year=2026&month=7")
    assert got.json()["approved_by"]
```

Фикстуры `client` / `auth_client` взять те же, что в `tests/test_hierarchy_rules_endpoints.py`. Учесть предупреждение из `app/api/CLAUDE.md` про особенности ORM в тестах эндпоинтов.

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_kpi_endpoints.py -v`
Expected: FAIL, 404

- [ ] **Step 3: Реализация роутера**

`app/api/endpoints/kpi.py` — по образцу `app/api/endpoints/hierarchy_rules.py`: `router = APIRouter()`, pydantic-схемы ответов, зависимости `get_db` и `get_current_user`. Сводка `summary` содержит: средний итог, сколько людей ниже цели, сколько метрик без данных. Утверждение пишет `KpiApproval` с `payload_json = json.dumps(build_report(...), ensure_ascii=False)` и `approved_by = current_user.email`.

Расшифровка возвращает два списка задач: `numerator` и `denominator`, в каждом `key`, `summary`, `status`, `resolution`, `url` (собрать из настройки `jira_base_url` + `/browse/` + ключ).

Выгрузка — `ExportService`-совместимый ответ через `openpyxl` с ленивым импортом внутри функции, как принято в `app/services/export_service.py`.

- [ ] **Step 4: Регистрация в роутере**

В `app/api/router.py` добавить импорт `kpi as kpi_endpoints` в общий блок и строку:

```python
api_router.include_router(
    kpi_endpoints.router, prefix="/kpi", tags=["kpi"], dependencies=_auth_dep,
)
```

- [ ] **Step 5: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/test_kpi_endpoints.py -v
git add app/api/endpoints/kpi.py app/api/router.py tests/test_kpi_endpoints.py
git commit -m "feat(kpi): API отчёта, расшифровки и утверждения месяца"
```

---

### Task 14: API справочников

**Files:**
- Create: `app/api/endpoints/kpi_settings.py`
- Modify: `app/api/router.py`
- Test: `tests/test_kpi_settings_endpoints.py`

Маршруты (все под `require_admin`):
- `GET/POST/PUT/DELETE /kpi-settings/metrics`
- `GET/POST/PUT/DELETE /kpi-settings/profiles` — при сохранении профиля проверять, что сумма весов равна 1 с допуском 0.001, иначе HTTP 422 с человеческим текстом
- `GET/PUT /kpi-settings/norms` — нормативы Cycle Time
- `GET/PUT /kpi-settings/general` — общие правила
- `GET /kpi-settings/attributes` — словарь допустимых атрибутов условий и их значений для выпадающих списков в интерфейсе

- [ ] **Step 1: Тест**

```python
"""Профиль с суммой весов не равной единице не сохраняется."""


def test_profile_weight_sum_validated(admin_client):
    resp = admin_client.post("/api/v1/kpi-settings/profiles", json={
        "code": "test", "name": "Тест", "role_code": "analyst", "target_pct": 80,
        "metrics": [{"metric_code": "quality", "weight": 0.5}],
    })
    assert resp.status_code == 422
    assert "весов" in resp.json()["detail"]


def test_attributes_dictionary_exposed(admin_client):
    resp = admin_client.get("/api/v1/kpi-settings/attributes")
    assert resp.status_code == 200
    attrs = {a["key"] for a in resp.json()["attributes"]}
    assert "project_key" in attrs and "environment" in attrs
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_kpi_settings_endpoints.py -v`
Expected: FAIL, 404

- [ ] **Step 3: Реализация и регистрация**

Роутер по образцу `app/api/endpoints/hierarchy_rules.py`, регистрация в `app/api/router.py` с `dependencies=_admin_dep` и префиксом `/kpi-settings`.

Словарь атрибутов отдаётся из одного места — списка в `app/services/kpi/conditions.py`, чтобы интерфейс и расчёт не разъезжались. Для каждого атрибута: ключ, человеческое название, тип значения (список из справочника, свободный текст, без значения) и, где применимо, доступные значения из базы (например, различные проекты и типы задач).

- [ ] **Step 4: Прогнать и закоммитить**

```bash
py -3.10 -m pytest tests/test_kpi_settings_endpoints.py -v
git add app/api/endpoints/kpi_settings.py app/api/router.py tests/test_kpi_settings_endpoints.py
git commit -m "feat(kpi): API справочников раздела"
```

---

## Фаза 5 — интерфейс

### Task 15: Клиент API и типы

**Files:**
- Create: `frontend/src/api/kpi.ts`

- [ ] **Step 1: Реализация**

По образцу `frontend/src/api/hierarchyRules.ts`: типы `KpiMetricValue`, `KpiRow`, `KpiReport`, `KpiTeamSummary`, `KpiBreakdown`, `KpiMetricDef`, `KpiProfileDef`, функции `fetchKpiReport`, `fetchTeamsSummary`, `fetchBreakdown`, `approveMonth`, `fetchApproval`, `fetchMetrics`, `saveMetric`, `fetchProfiles`, `saveProfile`, `fetchNorms`, `saveNorms`, `fetchGeneral`, `saveGeneral`, `fetchAttributes`.

- [ ] **Step 2: Проверка сборки типов**

```bash
cd frontend && npm run build
```
Expected: сборка без ошибок

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/api/kpi.ts
git commit -m "feat(kpi): клиент API на фронте"
```

---

### Task 16: Страница «Ведомость»

Референс — макет https://claude.ai/code/artifact/b0077150-2737-402c-a779-50cb370fcaa2

**Files:**
- Create: `frontend/src/pages/KpiPage.tsx`, `frontend/src/components/kpi/KpiLedger.tsx`
- Modify: `frontend/src/pages/lazyPages.ts`, `frontend/src/routes.tsx`, `frontend/src/aurora/shell/AuroraSidebar.tsx`

- [ ] **Step 1: Страница и таблица**

`KpiPage.tsx` — фильтры (период с пролистыванием месяц/квартал/год, направление, команда), полоса итогов, `KpiLedger`. Данные через `@tanstack/react-query`, как на остальных страницах. Глобальный фильтр команды в шапке уже существует — использовать его, а не заводить свой (см. `frontend/CLAUDE.md`).

`KpiLedger.tsx` — таблица AntD: строки-команды разворачиваются в людей, колонки метрик, моноширинные числа, заливка ячейки по отклонению от цели, дельта к прошлому месяцу у команды. В шапке страницы — кнопки «Утвердить месяц» (после утверждения показывает, кто и когда) и «Выгрузить в Excel», обе бьют в соответствующие маршруты из Task 13. Классы `glass` и переменные темы — как на существующих страницах, никаких собственных цветов.

- [ ] **Step 2: Регистрация страницы**

В `frontend/src/pages/lazyPages.ts` добавить ленивый экспорт `KpiPage`. В `frontend/src/routes.tsx` — маршрут `{ path: 'kpi', element: <ProtectedRoute>{page(<KpiPage />)}</ProtectedRoute> }`. В `frontend/src/aurora/shell/AuroraSidebar.tsx` — пункт `{ key: '/kpi', icon: Gauge, label: 'KPI' }` в группу «Обзор».

- [ ] **Step 3: Скрыть раздел по умолчанию**

Раздел прячется существующим механизмом «Видимость разделов» (`ui_hidden_section_keys`). Добавить миграцию `alembic/versions/k07a_kpi_hidden_by_default.py`, которая дописывает `/kpi` в этот список, если ключа ещё нет или маршрута в нём нет. Ничего нового в интерфейс настроек добавлять не нужно — раздел появится в существующем списке видимости.

- [ ] **Step 4: Проверка**

```bash
cd frontend && npm run lint && npm run build
```
Expected: без ошибок

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/pages/KpiPage.tsx frontend/src/components/kpi/ frontend/src/pages/lazyPages.ts frontend/src/routes.tsx frontend/src/aurora/shell/AuroraSidebar.tsx alembic/versions/k07a_kpi_hidden_by_default.py
git commit -m "feat(kpi): страница «Ведомость» и маршрут раздела"
```

---

### Task 17: Карточка сотрудника и расшифровка

**Files:**
- Create: `frontend/src/components/kpi/KpiEmployeeCard.tsx`, `frontend/src/components/kpi/KpiBreakdownModal.tsx`
- Modify: `frontend/src/components/kpi/KpiLedger.tsx`

- [ ] **Step 1: Карточка**

Боковая панель: кольцо итога, тренд за шесть месяцев с линией цели, разбор по метрикам, строка «Утвердил … · дата» или «Месяц не утверждён». Тренд — за шесть месяцев подряд, каждый месяц отдельным запросом отчёта или одним запросом с диапазоном (предпочтительно добавить в API параметр `months=6` и вернуть массив).

- [ ] **Step 2: Расшифровка**

Модалка: дробь с числами наверху, ниже два блока — «Что считаем» и «С чем сравниваем», в каждом таблица задач со ссылками в Jira.

- [ ] **Step 3: Проверка и коммит**

```bash
cd frontend && npm run lint && npm run build
git add frontend/src/components/kpi/
git commit -m "feat(kpi): карточка сотрудника и расшифровка метрики"
```

---

### Task 18: Настройки раздела

Референс — макет https://claude.ai/code/artifact/58051e23-dbae-4f08-8ece-9ddb76deecaa, компоновка «Единая форма».

**Files:**
- Create: `frontend/src/components/settings/kpi/KpiSettingsTab.tsx`, `MetricEditor.tsx`, `ProfileEditor.tsx`, `CycleTimeNorms.tsx`, `GeneralRules.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Раздел в настройках**

В `SettingsPage.tsx` в группу «Справочники» добавить `{ key: 'kpi', label: 'KPI', render: () => <KpiSettingsTab /> }`.

- [ ] **Step 2: Конструктор метрики**

Форма по макету: название, пояснение, способ расчёта, два набора условий (для способа «Доля»), признак «кто считается» отдельно на каждый набор, окно периода, инверсия, потолок, единица счёта. Условия — строки «атрибут / сравнение / значение», список атрибутов и допустимых значений берётся из `GET /kpi-settings/attributes`. Справа — предпросмотр формулы.

- [ ] **Step 3: Профили, нормативы, общие правила**

Профиль: список метрик с весами, индикатор суммы весов с состоянием ошибки, целевой уровень и полоса предупреждения. Нормативы: таблица команда × квартал с копированием из предыдущего квартала. Общие правила: исключаемые статусы пилюлями, срок внесения трудозатрат двумя полями (рабочих дней и время) с живым примером, политика при отсутствии данных.

- [ ] **Step 4: Проверка и коммит**

```bash
cd frontend && npm run lint && npm run build
git add frontend/src/components/settings/kpi/ frontend/src/pages/SettingsPage.tsx
git commit -m "feat(kpi): настройки раздела в единой форме"
```

---

## Фаза 6 — приёмка

### Task 19: Приёмочные проверки из спеки

**Files:**
- Create: `tests/test_kpi_acceptance.py`

- [ ] **Step 1: Тесты по списку готовности спеки**

По одному тесту на пункт раздела 10 спеки:

```python
"""Приёмочные проверки раздела KPI (раздел 10 спеки)."""


def test_cancelled_issues_excluded_from_denominator(db_session, sample_project):
    """Задача в статусе «Отменено» не попадает в знаменатель."""


def test_employee_moved_between_teams_not_counted_twice(db_session):
    """Сотрудник, перешедший между командами в середине месяца, считается один раз."""


def test_metric_without_data_redistributes_weight(db_session):
    """Метрика без данных не обнуляет итог."""


def test_approved_month_frozen_after_weight_change(db_session):
    """Изменение весов после утверждения не меняет утверждённый результат."""


def test_control_employee_matches_manual_calculation(db_session, sample_project):
    """Контрольный расчёт: 3 бага на 15 задач, 8 из 10 в срок, 9 из 10 по регламенту,
    норматив 80 при факте 75, оценка 4 из 5, 15 просрочек из 100 → итог 74,5%."""
```

Последний тест — пример из ТЗ, ожидаемый итог 74,5 %. Он проверяет всю цепочку разом и является главным критерием приёмки.

- [ ] **Step 2: Реализовать тела тестов и добиться прохождения**

Run: `py -3.10 -m pytest tests/test_kpi_acceptance.py -v`
Expected: PASS

- [ ] **Step 3: Полный прогон**

```bash
py -3.10 -m pytest tests/ -q
ruff check app/ tests/
mypy app/
cd frontend && npm run lint && npm run build
```
Expected: без падений

- [ ] **Step 4: Коммит и pull request**

```bash
git add tests/test_kpi_acceptance.py
git commit -m "test(kpi): приёмочные проверки раздела"
git push -u origin feature/kpi
gh pr create --title "Раздел KPI аналитиков" --body "..." --draft
```

Pull request создаётся **черновиком** и не сливается: решение о выпуске в продуктив принимает заказчик.

---

## Порядок и контрольные точки

- После Фазы 1 — данные из Jira доступны, но раздела ещё нет. Проверка: перевыгрузка за один месяц заполняет резолюцию, окружение, связи и дату внесения часов.
- После Фазы 3 — расчёт работает и покрыт тестами, интерфейса нет. Проверка: контрольный расчёт из ТЗ даёт 74,5 %.
- После Фазы 5 — раздел виден при включении в «Видимости разделов».
- Фаза 6 — приёмка и черновик pull request.

## Что осталось за рамками

Личный кабинет сотрудника, сравнение между направлениями, уведомления, произвольные формулы, отдельный профиль для руководителей проектов.
