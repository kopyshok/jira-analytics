# Рабочий стол тимлида — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Новый раздел `/team-desk` — контроль задач в разрезе разработчиков: три раскладки одного набора данных, семь признаков-проблем с отметкой «просмотрено», очередь работы и отсутствия.

**Architecture:** Данные приходят двумя новыми полями Jira (`Разработчик`, `DEV est (ч)`) через существующий механизм сопоставления полей. Расчёт вынесен в пакет `app/services/team_desk/`: `config.py` (настройки из AppSetting), `flags.py` (чистые функции признаков), `query.py` (срез задач + факт из worklog), `workload.py` (очередь работы), `marks.py` (отметки «просмотрено» и их сгорание). Один эндпоинт-агрегат `/team-desk/overview` отдаёт всё, что нужно любой из трёх раскладок; раскладки различаются только рендером на фронте.

**Tech Stack:** Python 3.10 (`py -3.10`), FastAPI, SQLAlchemy 2.0, Alembic (batch mode), pytest. Frontend — React 19 + TypeScript + AntD 6 + TanStack Query.

**Спецификация:** [docs/superpowers/specs/2026-08-05-team-lead-desk-design.md](../specs/2026-08-05-team-lead-desk-design.md)
**Макет:** https://claude.ai/code/artifact/4b60ca0f-6900-4b58-bcdd-a2e740ec54d4

---

## Структура файлов

**Создаются (backend):**
- `alembic/versions/td01a_team_desk_issue_fields.py` — поля разработчика и оценки в `issues`
- `alembic/versions/td02a_team_desk_marks.py` — таблица отметок «просмотрено»
- `app/models/team_desk_mark.py` — модель `TeamDeskMark`
- `app/services/team_desk/__init__.py`
- `app/services/team_desk/config.py` — чтение/запись настроек раздела из `AppSetting`
- `app/services/team_desk/flags.py` — вычисление семи признаков + подпись причины
- `app/services/team_desk/query.py` — выборка задач среза + факт из worklog + сводка
- `app/services/team_desk/workload.py` — очередь работы в часах и днях
- `app/services/team_desk/marks.py` — CRUD отметок + фильтрация сгоревших
- `app/schemas/team_desk.py` — pydantic-схемы ответа
- `app/api/endpoints/team_desk.py` — роутер `/team-desk`
- `tests/test_team_desk_flags.py`, `tests/test_team_desk_marks.py`, `tests/test_team_desk_query.py`, `tests/test_team_desk_workload.py`, `tests/test_team_desk_endpoint.py`

**Создаются (frontend):**
- `frontend/src/api/teamDesk.ts` — типы + вызовы
- `frontend/src/hooks/useTeamDesk.ts` — хуки TanStack Query
- `frontend/src/pages/TeamDeskPage.tsx` — страница, шапка, табы раскладок
- `frontend/src/components/teamdesk/DeskFilters.tsx` — команды, люди, период, шестерёнка
- `frontend/src/components/teamdesk/ThresholdsPanel.tsx` — пороги
- `frontend/src/components/teamdesk/FlagChip.tsx` — значок признака + меню «Просмотрено»
- `frontend/src/components/teamdesk/HoursScale.tsx` — шкала факт/оценка (обычная и центрированная)
- `frontend/src/components/teamdesk/DeveloperCards.tsx` — раскладка A
- `frontend/src/components/teamdesk/DeveloperTable.tsx` — раскладка B
- `frontend/src/components/teamdesk/GroupedIssueTable.tsx` — раскладка C
- `frontend/src/components/teamdesk/IssueTable.tsx` — детальная таблица для A и B
- `frontend/src/components/teamdesk/WorkloadBars.tsx` — очередь работы
- `frontend/src/components/teamdesk/AbsenceStrip.tsx` — лента отсутствий
- `frontend/src/components/settings/TeamDeskSettingsTab.tsx` — группы статусов и пороги в настройках

**Изменяются:**
- `app/models/issue.py` — три новых поля
- `app/models/__init__.py` — экспорт `TeamDeskMark`
- `app/services/sync_service.py` — сопоставление двух новых полей
- `app/api/router.py` — подключение роутера
- `frontend/src/pages/lazyPages.tsx`, `frontend/src/routes.tsx` — маршрут
- `frontend/src/components/Layout/AppLayout.tsx` — пункт меню
- `frontend/src/components/JiraFieldsCard.tsx` — два новых поля в сопоставлении
- `frontend/src/pages/SettingsPage.tsx` — секция настроек раздела
- `app/api/CLAUDE.md`, `frontend/CLAUDE.md`, `app/services/CLAUDE.md`, `app/models/CLAUDE.md` — документация

---

### Task 1: Поля разработчика и оценки в задаче

**Files:**
- Modify: `app/models/issue.py`
- Create: `alembic/versions/td01a_team_desk_issue_fields.py`
- Test: `tests/test_team_desk_query.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_team_desk_query.py`:

```python
"""Срез рабочего стола тимлида."""
from app.models import Issue, Project


def test_issue_has_developer_and_dev_estimate(db_session):
    project = Project(jira_project_id="1", key="OS", name="OS")
    db_session.add(project)
    db_session.flush()
    issue = Issue(
        jira_issue_id="10001",
        key="OS-1",
        summary="Тестовая задача",
        issue_type="Задача",
        status="В РАБОТЕ",
        project_id=project.id,
        developer_account_id="acc-1",
        developer_display_name="Шутов Сергей",
        dev_est_hours=16.0,
    )
    db_session.add(issue)
    db_session.commit()

    loaded = db_session.query(Issue).filter_by(key="OS-1").one()
    assert loaded.developer_display_name == "Шутов Сергей"
    assert loaded.dev_est_hours == 16.0
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_team_desk_query.py -v`
Expected: FAIL, `TypeError: 'developer_account_id' is an invalid keyword argument for Issue`

- [ ] **Step 3: Добавить поля в модель**

В `app/models/issue.py` после блока `assignee_account_id` / `reporter_display_name` (около строки 161) добавить:

```python
    # Рабочий стол тимлида: кастомное поле Jira «Разработчик» (тип user) и
    # «DEV est (ч)» — оценка разработки конкретной задачи. Не путать с
    # planned_dev_hours — та приходит с вкладки плановых трудозатрат RFA/эпика.
    developer_account_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    developer_display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dev_est_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
```

- [ ] **Step 4: Написать миграцию**

Создать `alembic/versions/td01a_team_desk_issue_fields.py`:

```python
"""team desk: developer + dev est fields on issues

Revision ID: td01a_team_desk_issue_fields
Revises: k15a_kpi_issue_paused_days
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "td01a_team_desk_issue_fields"
down_revision: Union[str, None] = "k15a_kpi_issue_paused_days"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("developer_account_id", sa.String(128), nullable=True))
        batch.add_column(sa.Column("developer_display_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("dev_est_hours", sa.Float(), nullable=True))
    op.create_index("ix_issues_developer_account_id", "issues", ["developer_account_id"])


def downgrade() -> None:
    op.drop_index("ix_issues_developer_account_id", table_name="issues")
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("dev_est_hours")
        batch.drop_column("developer_display_name")
        batch.drop_column("developer_account_id")
```

- [ ] **Step 5: Применить миграцию и прогнать тест**

Run: `alembic upgrade head && py -3.10 -m pytest tests/test_team_desk_query.py -v`
Expected: миграция без ошибок, тест PASS

- [ ] **Step 6: Коммит**

```bash
git add app/models/issue.py alembic/versions/td01a_team_desk_issue_fields.py tests/test_team_desk_query.py
git commit -m "feat(team-desk): поля разработчика и оценки разработки в задаче"
```

---

### Task 2: Синхронизация двух новых полей из Jira

**Files:**
- Modify: `app/services/sync_service.py:310-323` (списки ключей настроек), `~826-845` (сборка данных задачи)
- Test: `tests/test_team_desk_sync_fields.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_team_desk_sync_fields.py`:

```python
"""Извлечение полей «Разработчик» и «DEV est (ч)» из Jira."""
from app.services.sync_service import _extract_user_field, _to_float


def test_extract_user_field_reads_display_name_and_account_id():
    extra = {
        "customfield_14052": {
            "accountId": "627b98a119b129006829829d",
            "displayName": "Пряничников Алексей",
        }
    }
    assert _extract_user_field(extra, "customfield_14052") == (
        "627b98a119b129006829829d",
        "Пряничников Алексей",
    )


def test_extract_user_field_handles_empty():
    assert _extract_user_field({}, "customfield_14052") == (None, None)
    assert _extract_user_field({"customfield_14052": None}, "customfield_14052") == (None, None)
    assert _extract_user_field({"customfield_14052": {}}, None) == (None, None)


def test_dev_est_parses_number():
    assert _to_float(16.0) == 16.0
    assert _to_float("8,5") == 8.5
    assert _to_float(None) is None
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_team_desk_sync_fields.py -v`
Expected: FAIL, `ImportError: cannot import name '_extract_user_field'`

- [ ] **Step 3: Добавить хелпер и ключи настроек**

В `app/services/sync_service.py` рядом с `_normalize_level` (около строки 372) добавить:

```python
def _extract_user_field(extra: dict, field_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Достаёт (accountId, displayName) из кастомного поля Jira типа user.

    Пустое поле, отсутствующий id или чужая форма значения → (None, None).
    """
    if not field_id:
        return None, None
    raw = (extra or {}).get(field_id)
    if not isinstance(raw, dict):
        return None, None
    account_id = raw.get("accountId")
    display_name = raw.get("displayName")
    return (account_id or None), (display_name or None)
```

В список `_KPI_FIELD_SETTING_KEYS` (строка 310) добавить два ключа — механизм чтения настроек и добавления в `fields=` уже общий:

```python
_KPI_FIELD_SETTING_KEYS = [
    "jira_environment_field_id",
    "jira_subtype_field_id",
    "jira_cost_type_field_id",
    "jira_cycle_time_field_id",
    "jira_direction_field_id",
    # Рабочий стол тимлида
    "jira_developer_field_id",
    "jira_dev_est_field_id",
]
```

- [ ] **Step 4: Записать значения в задачу**

В `app/services/sync_service.py` в блоке сборки `data` рядом со строкой `data["environment"] = ...` (около 843) добавить:

```python
        dev_account_id, dev_display_name = _extract_user_field(
            extra, planned_ids.get("jira_developer_field_id")
        )
        data["developer_account_id"] = dev_account_id
        data["developer_display_name"] = dev_display_name
        data["dev_est_hours"] = _to_float(extra.get(planned_ids.get("jira_dev_est_field_id")))
```

- [ ] **Step 5: Прогнать тесты**

Run: `py -3.10 -m pytest tests/test_team_desk_sync_fields.py -v`
Expected: PASS (3 теста)

- [ ] **Step 6: Коммит**

```bash
git add app/services/sync_service.py tests/test_team_desk_sync_fields.py
git commit -m "feat(team-desk): синк полей «Разработчик» и «DEV est (ч)»"
```

---

### Task 3: Настройки раздела — группы статусов и пороги

**Files:**
- Create: `app/services/team_desk/__init__.py`, `app/services/team_desk/config.py`
- Test: `tests/test_team_desk_config.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_team_desk_config.py`:

```python
"""Настройки рабочего стола тимлида."""
from app.services.team_desk.config import (
    DEFAULT_STATUS_GROUPS,
    DEFAULT_THRESHOLDS,
    group_of_status,
    load_config,
    save_config,
)


def test_defaults_when_nothing_saved(db_session):
    cfg = load_config(db_session)
    assert cfg.thresholds["decomposition_hours"] == 16
    assert cfg.thresholds["overrun_pct"] == 30
    assert cfg.thresholds["stale_days"] == 5
    assert "В РАБОТЕ" in cfg.status_groups["dev"]
    assert "ФИЧА-РЕВЬЮ" in cfg.status_groups["other"]
    assert cfg.queue_statuses == ["К выполнению", "В РАБОТЕ", "Ожидает помещения"]
    assert cfg.subtask_types == ["Подзадача"]
    assert cfg.assignee_types == ["Research"]


def test_save_and_reload(db_session):
    cfg = load_config(db_session)
    cfg.thresholds["decomposition_hours"] = 24
    cfg.status_groups["dev"].append("НОВЫЙ СТАТУС")
    save_config(db_session, cfg)

    reloaded = load_config(db_session)
    assert reloaded.thresholds["decomposition_hours"] == 24
    assert "НОВЫЙ СТАТУС" in reloaded.status_groups["dev"]


def test_unknown_status_falls_into_other_bucket(db_session):
    cfg = load_config(db_session)
    assert group_of_status(cfg, "В РАБОТЕ") == "dev"
    assert group_of_status(cfg, "Тестирование") == "waiting"
    assert group_of_status(cfg, "Backlog") == "todo"
    assert group_of_status(cfg, "ГОТОВО") == "done"
    assert group_of_status(cfg, "Совершенно новый статус") == "unassigned"
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_team_desk_config.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.services.team_desk'`

- [ ] **Step 3: Написать модуль настроек**

Создать `app/services/team_desk/__init__.py` (пустой файл) и `app/services/team_desk/config.py`:

```python
"""Настройки раздела «Рабочий стол тимлида».

Всё, что может измениться в Jira или в голове тимлида, — настройка в AppSetting,
а не константа в коде: статусная модель меняется, пороги подбираются на живых
данных.
"""
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting

SETTING_KEY = "team_desk_config"

# Группы статусов. dev — мяч у разработчика, waiting — ждёт другого человека,
# todo — ещё не в работе, done — закрыта.
DEFAULT_STATUS_GROUPS: dict[str, list[str]] = {
    "dev": ["В РАБОТЕ", "КОД-РЕВЬЮ", "Ожидает помещения"],
    "waiting": ["ФИЧА-РЕВЬЮ", "Ожидает тестирования", "Тестирование",
                "У инициатора", "У инициаторa", "Ожидает обновления",
                "Ожидает oбновления"],
    "todo": ["Backlog", "К выполнению"],
    "done": ["ГОТОВО", "Готово", "Отменено"],
}
# В Jira у части статусов латинская «a»/«o» в русском слове — значения выше
# перечислены в обеих написаниях намеренно.

DEFAULT_QUEUE_STATUSES = ["К выполнению", "В РАБОТЕ", "Ожидает помещения"]

DEFAULT_THRESHOLDS: dict[str, float] = {
    "decomposition_hours": 16,   # оценка, с которой обязательна декомпозиция
    "overrun_pct": 30,           # перерасход от, %
    "underrun_pct": 50,          # недорасход от, %
    "stale_days": 5,             # зависла, дней в одном статусе
    "child_gap_pct": 25,         # оценки подзадач ниже родителя на, %
    "wip_limit": 3,              # лимит задач в работе одновременно
}

DEFAULT_SUBTASK_TYPES = ["Подзадача"]
DEFAULT_ASSIGNEE_TYPES = ["Research"]


@dataclass
class DeskConfig:
    status_groups: dict[str, list[str]] = field(default_factory=dict)
    queue_statuses: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    subtask_types: list[str] = field(default_factory=list)
    assignee_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_groups": self.status_groups,
            "queue_statuses": self.queue_statuses,
            "thresholds": self.thresholds,
            "subtask_types": self.subtask_types,
            "assignee_types": self.assignee_types,
        }


def _defaults() -> DeskConfig:
    return DeskConfig(
        status_groups={k: list(v) for k, v in DEFAULT_STATUS_GROUPS.items()},
        queue_statuses=list(DEFAULT_QUEUE_STATUSES),
        thresholds=dict(DEFAULT_THRESHOLDS),
        subtask_types=list(DEFAULT_SUBTASK_TYPES),
        assignee_types=list(DEFAULT_ASSIGNEE_TYPES),
    )


def load_config(db: Session) -> DeskConfig:
    """Настройки раздела; отсутствующие ключи добираются значениями по умолчанию."""
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    cfg = _defaults()
    if not row or not row.value:
        return cfg
    try:
        stored = json.loads(row.value)
    except (TypeError, ValueError):
        return cfg
    if isinstance(stored.get("status_groups"), dict):
        for group, statuses in stored["status_groups"].items():
            if isinstance(statuses, list):
                cfg.status_groups[group] = [str(s) for s in statuses]
    for key, target in (
        ("queue_statuses", "queue_statuses"),
        ("subtask_types", "subtask_types"),
        ("assignee_types", "assignee_types"),
    ):
        if isinstance(stored.get(key), list):
            setattr(cfg, target, [str(s) for s in stored[key]])
    if isinstance(stored.get("thresholds"), dict):
        for key, value in stored["thresholds"].items():
            if key in cfg.thresholds:
                try:
                    cfg.thresholds[key] = float(value)
                except (TypeError, ValueError):
                    pass
    return cfg


def save_config(db: Session, cfg: DeskConfig) -> None:
    """Пишет настройки одной записью. Коммитит сам — как остальные сервисы."""
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    payload = json.dumps(cfg.to_dict(), ensure_ascii=False)
    if row:
        row.value = payload
    else:
        db.add(AppSetting(key=SETTING_KEY, value=payload))
    db.commit()


def group_of_status(cfg: DeskConfig, status: str | None) -> str:
    """dev | waiting | todo | done | unassigned.

    Статус, не отнесённый ни к одной группе, не ломает расчёты — он попадает
    в 'unassigned' и подсвечивается в настройках как нераспределённый.
    """
    for group, statuses in cfg.status_groups.items():
        if status in statuses:
            return group
    return "unassigned"
```

- [ ] **Step 4: Прогнать тесты**

Run: `py -3.10 -m pytest tests/test_team_desk_config.py -v`
Expected: PASS (3 теста)

- [ ] **Step 5: Коммит**

```bash
git add app/services/team_desk/ tests/test_team_desk_config.py
git commit -m "feat(team-desk): настройки раздела — группы статусов, пороги, типы"
```

---

### Task 4: Признаки-проблемы

**Files:**
- Create: `app/services/team_desk/flags.py`
- Test: `tests/test_team_desk_flags.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_team_desk_flags.py`:

```python
"""Семь признаков рабочего стола тимлида."""
from dataclasses import dataclass
from typing import Optional

from app.services.team_desk.config import _defaults
from app.services.team_desk.flags import IssueFacts, compute_flags, flag_signature


def facts(**kw) -> IssueFacts:
    base = dict(
        key="OS-1", status="В РАБОТЕ", group="dev", est=None, fact=0.0,
        days_in_status=0, child_est_sum=None, has_children=False,
        is_subtask=False, is_analysis=False,
    )
    base.update(kw)
    return IssueFacts(**base)


CFG = _defaults()


def test_overrun_when_fact_exceeds_estimate_by_threshold():
    assert "over" in compute_flags(facts(est=6, fact=9), CFG)
    assert "over" not in compute_flags(facts(est=6, fact=7), CFG)


def test_underrun_only_for_closed_issues():
    assert "under" in compute_flags(facts(est=8, fact=0.5, status="Отменено", group="done"), CFG)
    assert "under" not in compute_flags(facts(est=8, fact=0.5), CFG)


def test_no_decomposition_above_threshold():
    assert "decomp" in compute_flags(facts(est=24, has_children=False), CFG)
    assert "decomp" not in compute_flags(facts(est=16, has_children=False), CFG)
    assert "decomp" not in compute_flags(facts(est=24, has_children=True, child_est_sum=24), CFG)


def test_child_gap_when_children_underestimated():
    assert "childgap" in compute_flags(
        facts(est=42, has_children=True, child_est_sum=0), CFG)
    assert "childgap" not in compute_flags(
        facts(est=40, has_children=True, child_est_sum=40), CFG)


def test_missing_estimate_and_missing_worklog():
    assert compute_flags(facts(est=None), CFG) == ["noest"]
    assert "nospent" in compute_flags(facts(est=5, fact=0.0), CFG)
    assert "nospent" not in compute_flags(facts(est=5, fact=1.0), CFG)


def test_stale_only_for_open_issues():
    assert "stale" in compute_flags(facts(est=5, fact=1, days_in_status=6), CFG)
    assert "stale" not in compute_flags(
        facts(est=5, fact=5, days_in_status=99, status="ГОТОВО", group="done"), CFG)


def test_analysis_issue_skips_estimate_flags():
    got = compute_flags(facts(est=None, is_analysis=True, days_in_status=9), CFG)
    assert got == ["stale"]


def test_subtask_never_gets_decomposition_flags():
    got = compute_flags(facts(est=40, is_subtask=True, has_children=False), CFG)
    assert "decomp" not in got and "childgap" not in got


def test_signature_changes_with_cause():
    a = facts(est=6, fact=9, status="В РАБОТЕ", days_in_status=3)
    b = facts(est=6, fact=12, status="В РАБОТЕ", days_in_status=3)
    assert flag_signature("over", a) != flag_signature("over", b)
    assert flag_signature("stale", a) == flag_signature("stale", b)
    c = facts(est=6, fact=9, status="КОД-РЕВЬЮ", days_in_status=1)
    assert flag_signature("stale", a) != flag_signature("stale", c)
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_team_desk_flags.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.services.team_desk.flags'`

- [ ] **Step 3: Написать модуль признаков**

Создать `app/services/team_desk/flags.py`:

```python
"""Признаки-проблемы задачи. Чистые функции: ORM сюда не заходит."""
from dataclasses import dataclass
from typing import Optional

from app.services.team_desk.config import DeskConfig

# Порядок важен: в интерфейсе значки идут в этом порядке.
FLAG_ORDER = ["over", "under", "decomp", "childgap", "noest", "nospent", "stale"]

FLAG_LABELS = {
    "over": "Перерасход",
    "under": "Недорасход",
    "decomp": "Без декомпозиции",
    "childgap": "Подзадачи недооценены",
    "noest": "Нет оценки",
    "nospent": "Нет списаний",
    "stale": "Зависла",
}


@dataclass
class IssueFacts:
    """Всё, что нужно для признаков одной задачи. Собирается в query.py."""
    key: str
    status: Optional[str]
    group: str                      # dev | waiting | todo | done | unassigned
    est: Optional[float]            # DEV est (ч)
    fact: float                     # часы из списаний
    days_in_status: int
    child_est_sum: Optional[float]  # сумма оценок подзадач
    has_children: bool
    is_subtask: bool
    is_analysis: bool               # задача технического анализа (Research)


def compute_flags(f: IssueFacts, cfg: DeskConfig) -> list[str]:
    """Список кодов признаков задачи в порядке FLAG_ORDER."""
    t = cfg.thresholds
    closed = f.group == "done"
    found: set[str] = set()

    if f.est is None:
        # У технического анализа оценки разработки нет по определению —
        # признак «нет оценки» на нём был бы шумом.
        if not f.is_analysis:
            found.add("noest")
    else:
        if f.fact > f.est * (1 + t["overrun_pct"] / 100):
            found.add("over")
        if closed and f.fact < f.est * (t["underrun_pct"] / 100):
            found.add("under")
        if not closed and f.fact == 0:
            found.add("nospent")
        if not f.is_subtask and not f.is_analysis:
            if f.est > t["decomposition_hours"] and not f.has_children:
                found.add("decomp")
            if f.has_children and (f.child_est_sum or 0) < f.est * (1 - t["child_gap_pct"] / 100):
                found.add("childgap")

    if not closed and f.days_in_status >= t["stale_days"]:
        found.add("stale")

    return [code for code in FLAG_ORDER if code in found]


def flag_signature(flag: str, f: IssueFacts) -> str:
    """Подпись причины, по которой признак загорелся.

    Отметка «просмотрено» сгорает, когда подпись перестаёт совпадать: задача
    сменила статус, вырос факт, поменялась оценка. Иначе отметка навсегда
    прятала бы реальную проблему.
    """
    est = "-" if f.est is None else f"{f.est:g}"
    fact = f"{round(f.fact, 1):g}"
    if flag == "stale":
        return f"{f.status}"
    if flag in ("over", "under"):
        return f"{est}:{fact}"
    if flag == "decomp":
        return est
    if flag == "childgap":
        child = "-" if f.child_est_sum is None else f"{f.child_est_sum:g}"
        return f"{est}:{child}"
    # noest / nospent гаснут сами, как только появляется оценка или часы.
    return ""
```

- [ ] **Step 4: Прогнать тесты**

Run: `py -3.10 -m pytest tests/test_team_desk_flags.py -v`
Expected: PASS (9 тестов)

- [ ] **Step 5: Коммит**

```bash
git add app/services/team_desk/flags.py tests/test_team_desk_flags.py
git commit -m "feat(team-desk): семь признаков задачи и подпись причины"
```

---

### Task 5: Отметка «просмотрено»

**Files:**
- Create: `app/models/team_desk_mark.py`, `alembic/versions/td02a_team_desk_marks.py`, `app/services/team_desk/marks.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_team_desk_marks.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_team_desk_marks.py`:

```python
"""Отметка «просмотрено» и её сгорание."""
import pytest

from app.services.team_desk.marks import mark_reviewed, unmark, active_marks


@pytest.fixture()
def issue(db_session):
    from app.models import Issue, Project
    project = Project(jira_project_id="1", key="OS", name="OS")
    db_session.add(project)
    db_session.flush()
    row = Issue(jira_issue_id="1", key="OS-1", summary="Задача",
                issue_type="Задача", status="В РАБОТЕ", project_id=project.id)
    db_session.add(row)
    db_session.commit()
    return row


def test_mark_stores_author_and_signature(db_session, issue, user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment="ждём заказчика", user_id=user.id)
    marks = active_marks(db_session, [issue.id], {("stale", issue.id): "В РАБОТЕ"})
    assert (issue.id, "stale") in marks
    assert marks[(issue.id, "stale")].comment == "ждём заказчика"
    assert marks[(issue.id, "stale")].created_by_user_id == user.id


def test_mark_burns_when_signature_changes(db_session, issue, user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment=None, user_id=user.id)
    # задача уехала в другой статус — отсчёт дней начался заново
    marks = active_marks(db_session, [issue.id], {("stale", issue.id): "КОД-РЕВЬЮ"})
    assert marks == {}


def test_mark_is_per_flag(db_session, issue, user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment=None, user_id=user.id)
    current = {("stale", issue.id): "В РАБОТЕ", ("over", issue.id): "6:9"}
    marks = active_marks(db_session, [issue.id], current)
    assert (issue.id, "stale") in marks
    assert (issue.id, "over") not in marks


def test_second_mark_replaces_first(db_session, issue, user):
    mark_reviewed(db_session, issue.id, "over", signature="6:9", comment="a", user_id=user.id)
    mark_reviewed(db_session, issue.id, "over", signature="6:12", comment="b", user_id=user.id)
    marks = active_marks(db_session, [issue.id], {("over", issue.id): "6:12"})
    assert marks[(issue.id, "over")].comment == "b"
    from app.models import TeamDeskMark
    assert db_session.query(TeamDeskMark).count() == 1


def test_unmark_removes(db_session, issue, user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment=None, user_id=user.id)
    unmark(db_session, issue.id, "stale")
    assert active_marks(db_session, [issue.id], {("stale", issue.id): "В РАБОТЕ"}) == {}
```

Фикстура `user` берётся из `tests/conftest.py` — если её нет, добавить туда:

```python
@pytest.fixture()
def user(db_session):
    from app.models import User
    row = User(email="lead@example.com", full_name="Тимлид",
               password_hash="x", is_admin=False)
    db_session.add(row)
    db_session.commit()
    return row
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_team_desk_marks.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.services.team_desk.marks'`

- [ ] **Step 3: Модель и миграция**

Создать `app/models/team_desk_mark.py`:

```python
"""Отметка «просмотрено» на признаке задачи (рабочий стол тимлида)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class TeamDeskMark(Base, TimestampMixin):
    """Тимлид посмотрел признак и решил, что это не проблема.

    Отметка живёт, пока не изменилась причина: `signature` — снимок причины на
    момент отметки (статус для «зависла», оценка и факт для «перерасхода»).
    Не совпала с текущей — отметка сгорела, признак снова проблемный.
    """

    __tablename__ = "team_desk_marks"
    __table_args__ = (UniqueConstraint("issue_id", "flag", name="uq_team_desk_mark"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flag: Mapped[str] = mapped_column(String(32), nullable=False)
    signature: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    marked_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
```

В `app/models/__init__.py` добавить импорт и запись в `__all__` рядом с остальными моделями:

```python
from app.models.team_desk_mark import TeamDeskMark
```

Создать `alembic/versions/td02a_team_desk_marks.py`:

```python
"""team desk: reviewed marks

Revision ID: td02a_team_desk_marks
Revises: td01a_team_desk_issue_fields
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "td02a_team_desk_marks"
down_revision: Union[str, None] = "td01a_team_desk_issue_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_desk_marks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("issue_id", sa.String(36), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flag", sa.String(32), nullable=False),
        sa.Column("signature", sa.String(160), nullable=False, server_default=""),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("marked_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("issue_id", "flag", name="uq_team_desk_mark"),
    )
    op.create_index("ix_team_desk_marks_issue_id", "team_desk_marks", ["issue_id"])


def downgrade() -> None:
    op.drop_index("ix_team_desk_marks_issue_id", table_name="team_desk_marks")
    op.drop_table("team_desk_marks")
```

- [ ] **Step 4: Написать сервис отметок**

Создать `app/services/team_desk/marks.py`:

```python
"""Отметки «просмотрено»: постановка, снятие, отсев сгоревших."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import TeamDeskMark


def mark_reviewed(
    db: Session,
    issue_id: str,
    flag: str,
    signature: str,
    comment: Optional[str],
    user_id: Optional[str],
) -> TeamDeskMark:
    """Отметить один признак одной задачи. Повторная отметка обновляет запись."""
    row = (
        db.query(TeamDeskMark)
        .filter(TeamDeskMark.issue_id == issue_id, TeamDeskMark.flag == flag)
        .first()
    )
    if row is None:
        row = TeamDeskMark(issue_id=issue_id, flag=flag)
        db.add(row)
    row.signature = signature or ""
    row.comment = comment
    row.created_by_user_id = user_id
    row.marked_at = datetime.utcnow()
    db.commit()
    return row


def unmark(db: Session, issue_id: str, flag: str) -> None:
    """Снять отметку — признак снова считается проблемным."""
    db.query(TeamDeskMark).filter(
        TeamDeskMark.issue_id == issue_id, TeamDeskMark.flag == flag
    ).delete(synchronize_session=False)
    db.commit()


def active_marks(
    db: Session,
    issue_ids: list[str],
    current_signatures: dict[tuple[str, str], str],
) -> dict[tuple[str, str], TeamDeskMark]:
    """Живые отметки: подпись совпала с текущей причиной.

    current_signatures — {(flag, issue_id): подпись сейчас}. Отметка, чья
    подпись не совпала, считается сгоревшей и удаляется из базы: держать
    мёртвые записи незачем, а тимлид увидит признак заново.
    """
    if not issue_ids:
        return {}
    rows = db.query(TeamDeskMark).filter(TeamDeskMark.issue_id.in_(issue_ids)).all()
    alive: dict[tuple[str, str], TeamDeskMark] = {}
    burned: list[str] = []
    for row in rows:
        current = current_signatures.get((row.flag, row.issue_id))
        if current is None or current != row.signature:
            burned.append(row.id)
            continue
        alive[(row.issue_id, row.flag)] = row
    if burned:
        db.query(TeamDeskMark).filter(TeamDeskMark.id.in_(burned)).delete(
            synchronize_session=False
        )
        db.commit()
    return alive
```

- [ ] **Step 5: Применить миграцию и прогнать тесты**

Run: `alembic upgrade head && py -3.10 -m pytest tests/test_team_desk_marks.py -v`
Expected: PASS (5 тестов)

- [ ] **Step 6: Коммит**

```bash
git add app/models/team_desk_mark.py app/models/__init__.py alembic/versions/td02a_team_desk_marks.py app/services/team_desk/marks.py tests/test_team_desk_marks.py tests/conftest.py
git commit -m "feat(team-desk): отметка «просмотрено» со сгоранием по причине"
```

---

### Task 6: Срез задач и сводка по разработчикам

**Files:**
- Create: `app/services/team_desk/query.py`
- Test: `tests/test_team_desk_query.py` (дополнить)

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_team_desk_query.py`:

```python
from datetime import datetime, timedelta

from app.services.team_desk.query import build_overview


def _issue(db_session, project, key, **kw):
    from app.models import Issue
    row = Issue(
        jira_issue_id=key, key=key, summary=kw.pop("summary", key),
        issue_type=kw.pop("issue_type", "Задача"),
        status=kw.pop("status", "В РАБОТЕ"),
        project_id=project.id, **kw,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_overview_groups_issues_by_developer(db_session):
    from app.models import Employee, Project, Worklog
    project = Project(jira_project_id="1", key="OS", name="OS")
    db_session.add(project)
    db_session.flush()
    emp = Employee(jira_account_id="acc-1", display_name="Шутов Сергей", email="s@x.ru")
    db_session.add(emp)
    db_session.flush()

    issue = _issue(db_session, project, "OS-1", developer_account_id="acc-1",
                   developer_display_name="Шутов Сергей", dev_est_hours=6.0,
                   status_changed_at=datetime.utcnow() - timedelta(days=9))
    db_session.add(Worklog(jira_worklog_id="w1", issue_id=issue.id, employee_id=emp.id,
                           hours=9.0, started_at=datetime.utcnow()))
    db_session.commit()

    result = build_overview(db_session, teams=[], developer_ids=["acc-1"], only_open=True)
    assert len(result["developers"]) == 1
    dev = result["developers"][0]
    assert dev["display_name"] == "Шутов Сергей"
    assert dev["total_issues"] == 1
    assert dev["fact_hours"] == 9.0
    assert dev["est_hours"] == 6.0
    row = result["issues"][0]
    assert row["key"] == "OS-1"
    assert "over" in row["flags"]
    assert "stale" in row["flags"]


def test_subtask_counts_for_its_own_developer(db_session):
    from app.models import Project
    project = Project(jira_project_id="1", key="OS", name="OS")
    db_session.add(project)
    db_session.flush()
    parent = _issue(db_session, project, "OS-10", developer_account_id="acc-1",
                    developer_display_name="Шутов Сергей", dev_est_hours=40.0)
    _issue(db_session, project, "OS-11", issue_type="Подзадача", parent_id=parent.id,
           developer_account_id="acc-2", developer_display_name="Пак Илья",
           dev_est_hours=8.0)
    db_session.commit()

    result = build_overview(db_session, teams=[], developer_ids=["acc-1", "acc-2"],
                            only_open=True)
    names = {d["display_name"]: d for d in result["developers"]}
    assert names["Пак Илья"]["total_issues"] == 1


def test_research_issue_taken_by_assignee(db_session):
    from app.models import Project
    project = Project(jira_project_id="1", key="OS", name="OS")
    db_session.add(project)
    db_session.flush()
    _issue(db_session, project, "OS-20", issue_type="Research",
           assignee_account_id="acc-1", assignee_display_name="Шутов Сергей")
    db_session.commit()

    result = build_overview(db_session, teams=[], developer_ids=["acc-1"], only_open=True)
    row = result["issues"][0]
    assert row["is_analysis"] is True
    assert "noest" not in row["flags"]
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_team_desk_query.py -v`
Expected: FAIL, `ImportError: cannot import name 'build_overview'`

- [ ] **Step 3: Написать модуль среза**

Создать `app/services/team_desk/query.py`:

```python
"""Срез задач рабочего стола тимлида: выборка, факт, признаки, сводка."""
import statistics
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import Issue, Worklog
from app.services.team_desk.config import DeskConfig, group_of_status, load_config
from app.services.team_desk.flags import IssueFacts, compute_flags, flag_signature
from app.services.team_desk.marks import active_marks


def _days_in_status(issue: Issue, today: datetime) -> int:
    if not issue.status_changed_at:
        return 0
    return max(0, (today - issue.status_changed_at).days)


def _fact_by_issue(db: Session, issue_ids: list[str]) -> dict[str, float]:
    """Часы списаний по задачам. Факт — сумма по всем, кто списывал."""
    if not issue_ids:
        return {}
    rows = (
        db.query(Worklog.issue_id, func.sum(Worklog.hours))
        .filter(Worklog.issue_id.in_(issue_ids))
        .group_by(Worklog.issue_id)
        .all()
    )
    return {issue_id: float(total or 0) for issue_id, total in rows}


def _fact_by_issue_and_person(db: Session, issue_ids: list[str]) -> dict[str, list[dict]]:
    """Разбивка факта по людям — показывается при раскрытии строки."""
    if not issue_ids:
        return {}
    from app.models import Employee
    rows = (
        db.query(Worklog.issue_id, Employee.display_name, func.sum(Worklog.hours))
        .join(Employee, Employee.id == Worklog.employee_id)
        .filter(Worklog.issue_id.in_(issue_ids))
        .group_by(Worklog.issue_id, Employee.display_name)
        .all()
    )
    out: dict[str, list[dict]] = {}
    for issue_id, name, total in rows:
        out.setdefault(issue_id, []).append({"name": name, "hours": float(total or 0)})
    return out


def _select_issues(
    db: Session, cfg: DeskConfig, developer_ids: list[str], only_open: bool
) -> list[Issue]:
    """Задачи, где человек стоит разработчиком, плюс технический анализ по исполнителю."""
    conditions = [Issue.developer_account_id.in_(developer_ids)]
    if cfg.assignee_types:
        conditions.append(
            Issue.issue_type.in_(cfg.assignee_types)
            & Issue.assignee_account_id.in_(developer_ids)
        )
    query = db.query(Issue).filter(or_(*conditions))
    if only_open:
        closed = cfg.status_groups.get("done", [])
        if closed:
            query = query.filter(~Issue.status.in_(closed))
    return query.all()


def build_overview(
    db: Session,
    teams: list[str],
    developer_ids: list[str],
    only_open: bool = True,
    show_reviewed: bool = False,
    today: Optional[datetime] = None,
) -> dict:
    """Всё, что нужно любой из трёх раскладок: задачи, сводка, отметки.

    teams используется вызывающим кодом для сбора developer_ids (состав команды
    на дату) — сюда приходит уже готовый список людей.
    """
    cfg = load_config(db)
    today = today or datetime.utcnow()
    if not developer_ids:
        return {"developers": [], "issues": [], "flag_counts": {}}

    issues = _select_issues(db, cfg, developer_ids, only_open)
    ids = [i.id for i in issues]
    fact_map = _fact_by_issue(db, ids)
    person_map = _fact_by_issue_and_person(db, ids)

    # Оценки подзадач для признака «подзадачи недооценены».
    child_est: dict[str, float] = {}
    child_count: dict[str, int] = {}
    if ids:
        rows = (
            db.query(Issue.parent_id, func.sum(Issue.dev_est_hours), func.count(Issue.id))
            .filter(Issue.parent_id.in_(ids))
            .group_by(Issue.parent_id)
            .all()
        )
        for parent_id, est_sum, count in rows:
            child_est[parent_id] = float(est_sum or 0)
            child_count[parent_id] = int(count or 0)

    rows: list[dict] = []
    signatures: dict[tuple[str, str], str] = {}
    for issue in issues:
        group = group_of_status(cfg, issue.status)
        is_analysis = issue.issue_type in cfg.assignee_types
        facts = IssueFacts(
            key=issue.key,
            status=issue.status,
            group=group,
            est=issue.dev_est_hours,
            fact=fact_map.get(issue.id, 0.0),
            days_in_status=_days_in_status(issue, today),
            child_est_sum=child_est.get(issue.id),
            has_children=child_count.get(issue.id, 0) > 0,
            is_subtask=issue.issue_type in cfg.subtask_types,
            is_analysis=is_analysis,
        )
        flags = compute_flags(facts, cfg)
        for flag in flags:
            signatures[(flag, issue.id)] = flag_signature(flag, facts)
        owner = (
            issue.assignee_account_id if is_analysis and not issue.developer_account_id
            else issue.developer_account_id
        )
        owner_name = (
            issue.assignee_display_name if is_analysis and not issue.developer_display_name
            else issue.developer_display_name
        )
        rows.append({
            "id": issue.id,
            "key": issue.key,
            "summary": issue.summary,
            "issue_type": issue.issue_type,
            "status": issue.status,
            "status_group": group,
            "developer_id": owner,
            "developer_name": owner_name,
            "parent_id": issue.parent_id,
            "est_hours": issue.dev_est_hours,
            "fact_hours": facts.fact,
            "fact_by_person": person_map.get(issue.id, []),
            "days_in_status": facts.days_in_status,
            "is_analysis": is_analysis,
            "is_subtask": facts.is_subtask,
            "flags": flags,
        })

    marks = active_marks(db, ids, signatures)
    for row in rows:
        reviewed = []
        for flag in list(row["flags"]):
            mark = marks.get((row["id"], flag))
            if not mark:
                continue
            reviewed.append({
                "flag": flag,
                "comment": mark.comment,
                "marked_at": mark.marked_at.isoformat(),
            })
            if not show_reviewed:
                row["flags"].remove(flag)
        row["reviewed"] = reviewed

    developers = _summarize(rows, developer_ids)
    flag_counts: dict[str, int] = {}
    for row in rows:
        for flag in row["flags"]:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    return {"developers": developers, "issues": rows, "flag_counts": flag_counts}


def _summarize(rows: list[dict], developer_ids: list[str]) -> list[dict]:
    """Сводка на человека: счётчики по группам статусов, часы, точность, признаки."""
    by_dev: dict[str, list[dict]] = {dev_id: [] for dev_id in developer_ids}
    for row in rows:
        by_dev.setdefault(row["developer_id"], []).append(row)

    result = []
    for dev_id, items in by_dev.items():
        if not items:
            continue
        ratios = [
            r["fact_hours"] / r["est_hours"]
            for r in items
            if r["est_hours"] and r["fact_hours"] > 0
        ]
        flag_counts: dict[str, int] = {}
        for row in items:
            for flag in row["flags"]:
                flag_counts[flag] = flag_counts.get(flag, 0) + 1
        result.append({
            "developer_id": dev_id,
            "display_name": items[0]["developer_name"],
            "total_issues": len(items),
            "in_dev": sum(1 for r in items if r["status_group"] == "dev"),
            "waiting": sum(1 for r in items if r["status_group"] == "waiting"),
            "todo": sum(1 for r in items if r["status_group"] == "todo"),
            "est_hours": sum(r["est_hours"] or 0 for r in items),
            "fact_hours": sum(r["fact_hours"] for r in items),
            "accuracy": round(statistics.median(ratios), 2) if ratios else None,
            "flag_counts": flag_counts,
        })
    result.sort(key=lambda d: d["display_name"] or "")
    return result
```

- [ ] **Step 4: Прогнать тесты**

Run: `py -3.10 -m pytest tests/test_team_desk_query.py -v`
Expected: PASS (4 теста)

- [ ] **Step 5: Коммит**

```bash
git add app/services/team_desk/query.py tests/test_team_desk_query.py
git commit -m "feat(team-desk): срез задач по разработчикам и сводка"
```

---

### Task 7: Очередь работы

**Files:**
- Create: `app/services/team_desk/workload.py`
- Test: `tests/test_team_desk_workload.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_team_desk_workload.py`:

```python
"""Очередь работы разработчика в часах и рабочих днях."""
from datetime import date

from app.services.team_desk.workload import queue_for_developers


def test_queue_counts_only_queue_statuses(db_session):
    rows = [
        {"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": 8.0},
        {"developer_id": "acc-1", "status": "К выполнению", "est_hours": 4.0},
        {"developer_id": "acc-1", "status": "Ожидает тестирования", "est_hours": 40.0},
        {"developer_id": "acc-1", "status": "ГОТОВО", "est_hours": 16.0},
    ]
    result = queue_for_developers(db_session, rows, employee_by_account={},
                                  start=date(2026, 8, 5), days=7)
    assert result["acc-1"]["queue_hours"] == 12.0


def test_issues_without_estimate_counted_separately(db_session):
    rows = [
        {"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": None},
        {"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": 6.0},
    ]
    result = queue_for_developers(db_session, rows, employee_by_account={},
                                  start=date(2026, 8, 5), days=7)
    assert result["acc-1"]["queue_hours"] == 6.0
    assert result["acc-1"]["without_estimate"] == 1


def test_available_hours_drop_during_absence(db_session):
    from app.models import Absence, AbsenceReason, Employee
    reason = AbsenceReason(code="vacation", name="Отпуск", is_planned=True, color="#3b82f6")
    emp = Employee(jira_account_id="acc-1", display_name="Шутов Сергей", email="s@x.ru")
    db_session.add_all([reason, emp])
    db_session.flush()
    db_session.add(Absence(employee_id=emp.id, reason_id=reason.id,
                           start_date=date(2026, 8, 5), end_date=date(2026, 8, 11)))
    db_session.commit()

    rows = [{"developer_id": "acc-1", "status": "В РАБОТЕ", "est_hours": 8.0}]
    result = queue_for_developers(db_session, rows, employee_by_account={"acc-1": emp.id},
                                  start=date(2026, 8, 5), days=7)
    assert result["acc-1"]["available_hours"] == 0
    assert result["acc-1"]["queue_days"] is None
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_team_desk_workload.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.services.team_desk.workload'`

- [ ] **Step 3: Написать модуль очереди**

Создать `app/services/team_desk/workload.py`:

```python
"""Очередь работы: сколько часов висит на человеке и на сколько дней это тянет."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Absence, ProductionCalendarDay
from app.services.team_desk.config import load_config


def _calendar_hours(db: Session, start: date, end: date) -> dict[date, float]:
    """Нормо-часы по дням. Нет записи в календаре — будни по 8, выходные 0."""
    rows = (
        db.query(ProductionCalendarDay)
        .filter(ProductionCalendarDay.day >= start, ProductionCalendarDay.day <= end)
        .all()
    )
    known = {row.day: float(row.hours or 0) for row in rows}
    out: dict[date, float] = {}
    cursor = start
    while cursor <= end:
        out[cursor] = known.get(cursor, 8.0 if cursor.weekday() < 5 else 0.0)
        cursor += timedelta(days=1)
    return out


def _absent_days(db: Session, employee_ids: list[str], start: date, end: date) -> dict[str, set]:
    if not employee_ids:
        return {}
    rows = (
        db.query(Absence)
        .filter(
            Absence.employee_id.in_(employee_ids),
            Absence.start_date <= end,
            Absence.end_date >= start,
        )
        .all()
    )
    out: dict[str, set] = {}
    for row in rows:
        cursor = max(row.start_date, start)
        last = min(row.end_date, end)
        while cursor <= last:
            out.setdefault(row.employee_id, set()).add(cursor)
            cursor += timedelta(days=1)
    return out


def queue_for_developers(
    db: Session,
    issue_rows: list[dict],
    employee_by_account: dict[str, str],
    start: date,
    days: int = 7,
) -> dict[str, dict]:
    """Очередь работы на окно `days` дней вперёд.

    queue_hours — сумма оценок незакрытых задач в статусах очереди.
    available_hours — нормо-часы окна минус дни отсутствий.
    queue_days — во сколько рабочих дней укладывается очередь; None, если
    свободных часов в окне нет (человек в отпуске).
    """
    cfg = load_config(db)
    end = start + timedelta(days=days - 1)
    calendar = _calendar_hours(db, start, end)
    employee_ids = [e for e in employee_by_account.values() if e]
    absences = _absent_days(db, employee_ids, start, end)

    per_dev: dict[str, dict] = {}
    for row in issue_rows:
        dev_id = row.get("developer_id")
        if not dev_id or row.get("status") not in cfg.queue_statuses:
            continue
        bucket = per_dev.setdefault(dev_id, {"queue_hours": 0.0, "without_estimate": 0})
        est = row.get("est_hours")
        if est is None:
            bucket["without_estimate"] += 1
        else:
            bucket["queue_hours"] += float(est)

    daily_norm = 8.0
    for dev_id, bucket in per_dev.items():
        employee_id = employee_by_account.get(dev_id)
        away = absences.get(employee_id, set()) if employee_id else set()
        available = sum(h for day, h in calendar.items() if day not in away)
        bucket["available_hours"] = available
        bucket["queue_days"] = (
            round(bucket["queue_hours"] / daily_norm, 1) if available > 0 else None
        )
        bucket["overloaded"] = available > 0 and bucket["queue_hours"] > available
    return per_dev
```

- [ ] **Step 4: Прогнать тесты**

Run: `py -3.10 -m pytest tests/test_team_desk_workload.py -v`
Expected: PASS (3 теста)

- [ ] **Step 5: Коммит**

```bash
git add app/services/team_desk/workload.py tests/test_team_desk_workload.py
git commit -m "feat(team-desk): очередь работы с учётом отсутствий"
```

---

### Task 8: Эндпоинты раздела

**Files:**
- Create: `app/schemas/team_desk.py`, `app/api/endpoints/team_desk.py`
- Modify: `app/api/router.py`
- Test: `tests/test_team_desk_endpoint.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_team_desk_endpoint.py`:

```python
"""Эндпоинты рабочего стола тимлида."""


def test_overview_returns_empty_without_filters(client, auth_headers):
    resp = client.get("/api/v1/team-desk/overview", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["developers"] == []
    assert body["issues"] == []


def test_settings_roundtrip(client, auth_headers):
    resp = client.get("/api/v1/team-desk/settings", headers=auth_headers)
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["thresholds"]["decomposition_hours"] == 16

    cfg["thresholds"]["decomposition_hours"] = 24
    resp = client.put("/api/v1/team-desk/settings", json=cfg, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["thresholds"]["decomposition_hours"] == 24


def test_mark_and_unmark(client, auth_headers, db_session):
    from app.models import Issue, Project
    project = Project(jira_project_id="1", key="OS", name="OS")
    db_session.add(project)
    db_session.flush()
    issue = Issue(jira_issue_id="1", key="OS-1", summary="Задача", issue_type="Задача",
                  status="В РАБОТЕ", project_id=project.id)
    db_session.add(issue)
    db_session.commit()

    resp = client.post(
        f"/api/v1/team-desk/issues/{issue.id}/mark",
        json={"flag": "stale", "signature": "В РАБОТЕ", "comment": "ждём заказчика"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = client.delete(
        f"/api/v1/team-desk/issues/{issue.id}/mark?flag=stale", headers=auth_headers
    )
    assert resp.status_code == 200


def test_mark_rejects_unknown_flag(client, auth_headers, db_session):
    from app.models import Issue, Project
    project = Project(jira_project_id="2", key="OS2", name="OS2")
    db_session.add(project)
    db_session.flush()
    issue = Issue(jira_issue_id="2", key="OS-2", summary="Задача", issue_type="Задача",
                  status="В РАБОТЕ", project_id=project.id)
    db_session.add(issue)
    db_session.commit()

    resp = client.post(
        f"/api/v1/team-desk/issues/{issue.id}/mark",
        json={"flag": "выдуманный", "signature": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_team_desk_endpoint.py -v`
Expected: FAIL, 404 на всех маршрутах

- [ ] **Step 3: Схемы ответа**

Создать `app/schemas/team_desk.py`:

```python
"""Схемы раздела «Рабочий стол тимлида»."""
from typing import Optional

from pydantic import BaseModel, Field


class DeskSettings(BaseModel):
    status_groups: dict[str, list[str]]
    queue_statuses: list[str]
    thresholds: dict[str, float]
    subtask_types: list[str]
    assignee_types: list[str]


class MarkRequest(BaseModel):
    flag: str = Field(..., description="Код признака")
    signature: str = Field("", description="Снимок причины на момент отметки")
    comment: Optional[str] = None
```

- [ ] **Step 4: Роутер**

Создать `app/api/endpoints/team_desk.py`:

```python
"""Рабочий стол тимлида: срез задач, настройки, отметки «просмотрено»."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import Employee, User
from app.schemas.team_desk import DeskSettings, MarkRequest
from app.services.team_desk.config import DeskConfig, load_config, save_config
from app.services.team_desk.flags import FLAG_LABELS, FLAG_ORDER
from app.services.team_desk.marks import mark_reviewed, unmark
from app.services.team_desk.query import build_overview
from app.services.team_desk.workload import queue_for_developers
from app.services.team_membership import members_on

router = APIRouter()


def _split(raw: Optional[str]) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Пороги, группы статусов и типы задач раздела."""
    return load_config(db).to_dict()


@router.put("/settings")
def put_settings(
    payload: DeskSettings,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Сохранить настройки раздела целиком."""
    cfg = DeskConfig(
        status_groups=payload.status_groups,
        queue_statuses=payload.queue_statuses,
        thresholds=payload.thresholds,
        subtask_types=payload.subtask_types,
        assignee_types=payload.assignee_types,
    )
    save_config(db, cfg)
    return load_config(db).to_dict()


@router.get("/flags")
def get_flag_dictionary(_: User = Depends(get_current_user)):
    """Справочник признаков — подписи для интерфейса."""
    return [{"code": code, "label": FLAG_LABELS[code]} for code in FLAG_ORDER]


@router.get("/overview")
def get_overview(
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    developers: Optional[str] = Query(None, description="Учётные записи через запятую"),
    only_open: bool = Query(True),
    show_reviewed: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Задачи, сводка по разработчикам, очередь работы и признаки."""
    team_list = _split(teams)
    account_ids = set(_split(developers))

    employees: list[Employee] = []
    if team_list:
        employees = members_on(db, team_list, date.today())
        account_ids.update(e.jira_account_id for e in employees if e.jira_account_id)
    if account_ids and not employees:
        employees = (
            db.query(Employee).filter(Employee.jira_account_id.in_(account_ids)).all()
        )

    employee_by_account = {
        e.jira_account_id: e.id for e in employees if e.jira_account_id
    }
    result = build_overview(
        db,
        teams=team_list,
        developer_ids=sorted(account_ids),
        only_open=only_open,
        show_reviewed=show_reviewed,
    )
    result["workload"] = queue_for_developers(
        db,
        [
            {"developer_id": r["developer_id"], "status": r["status"],
             "est_hours": r["est_hours"]}
            for r in result["issues"]
        ],
        employee_by_account=employee_by_account,
        start=date.today(),
        days=7,
    )
    result["employee_ids"] = employee_by_account
    return result


@router.post("/issues/{issue_id}/mark")
def post_mark(
    issue_id: str,
    payload: MarkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отметить признак просмотренным."""
    if payload.flag not in FLAG_ORDER:
        raise HTTPException(status_code=422, detail="Неизвестный признак")
    row = mark_reviewed(
        db, issue_id, payload.flag, payload.signature, payload.comment, user.id
    )
    return {"issue_id": issue_id, "flag": row.flag,
            "marked_at": row.marked_at.isoformat()}


@router.delete("/issues/{issue_id}/mark")
def delete_mark(
    issue_id: str,
    flag: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Снять отметку — признак снова считается проблемным."""
    unmark(db, issue_id, flag)
    return {"issue_id": issue_id, "flag": flag}
```

- [ ] **Step 5: Подключить роутер**

В `app/api/router.py` рядом с остальными authenticated-роутерами добавить:

```python
from app.api.endpoints import team_desk

api_router.include_router(
    team_desk.router,
    prefix="/team-desk",
    tags=["team-desk"],
    dependencies=[Depends(get_current_user)],
)
```

- [ ] **Step 6: Прогнать тесты**

Run: `py -3.10 -m pytest tests/test_team_desk_endpoint.py -v`
Expected: PASS (4 теста)

- [ ] **Step 7: Прогнать весь backend**

Run: `py -3.10 -m pytest tests/ -q`
Expected: без новых падений

- [ ] **Step 8: Коммит**

```bash
git add app/schemas/team_desk.py app/api/endpoints/team_desk.py app/api/router.py tests/test_team_desk_endpoint.py
git commit -m "feat(team-desk): эндпоинты среза, настроек и отметок"
```

---

### Task 9: Клиент API и хуки на фронте

**Files:**
- Create: `frontend/src/api/teamDesk.ts`, `frontend/src/hooks/useTeamDesk.ts`

- [ ] **Step 1: Написать клиент**

Создать `frontend/src/api/teamDesk.ts`:

```ts
import { api } from './client'

export type FlagCode = 'over' | 'under' | 'decomp' | 'childgap' | 'noest' | 'nospent' | 'stale'

export interface ReviewedMark {
  flag: FlagCode
  comment: string | null
  marked_at: string
}

export interface DeskIssue {
  id: string
  key: string
  summary: string
  issue_type: string
  status: string
  status_group: 'dev' | 'waiting' | 'todo' | 'done' | 'unassigned'
  developer_id: string | null
  developer_name: string | null
  parent_id: string | null
  est_hours: number | null
  fact_hours: number
  fact_by_person: { name: string; hours: number }[]
  days_in_status: number
  is_analysis: boolean
  is_subtask: boolean
  flags: FlagCode[]
  reviewed: ReviewedMark[]
}

export interface DeskDeveloper {
  developer_id: string
  display_name: string | null
  total_issues: number
  in_dev: number
  waiting: number
  todo: number
  est_hours: number
  fact_hours: number
  accuracy: number | null
  flag_counts: Partial<Record<FlagCode, number>>
}

export interface DeskWorkload {
  queue_hours: number
  without_estimate: number
  available_hours: number
  queue_days: number | null
  overloaded: boolean
}

export interface DeskOverview {
  developers: DeskDeveloper[]
  issues: DeskIssue[]
  flag_counts: Partial<Record<FlagCode, number>>
  workload: Record<string, DeskWorkload>
}

export interface DeskSettings {
  status_groups: Record<string, string[]>
  queue_statuses: string[]
  thresholds: Record<string, number>
  subtask_types: string[]
  assignee_types: string[]
}

export const teamDeskApi = {
  overview: (params: {
    teams?: string
    developers?: string
    only_open?: boolean
    show_reviewed?: boolean
  }) => api.get<DeskOverview>('/team-desk/overview', params),

  settings: () => api.get<DeskSettings>('/team-desk/settings'),
  saveSettings: (payload: DeskSettings) => api.put<DeskSettings>('/team-desk/settings', payload),

  mark: (issueId: string, payload: { flag: FlagCode; signature: string; comment?: string }) =>
    api.post(`/team-desk/issues/${issueId}/mark`, payload),

  unmark: (issueId: string, flag: FlagCode) =>
    api.delete(`/team-desk/issues/${issueId}/mark?flag=${flag}`),
}

export const FLAG_LABELS: Record<FlagCode, string> = {
  over: 'Перерасход',
  under: 'Недорасход',
  decomp: 'Без декомпозиции',
  childgap: 'Подзадачи недооценены',
  noest: 'Нет оценки',
  nospent: 'Нет списаний',
  stale: 'Зависла',
}
```

- [ ] **Step 2: Написать хуки**

Создать `frontend/src/hooks/useTeamDesk.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { teamDeskApi, type DeskSettings, type FlagCode } from '../api/teamDesk'

export function useDeskOverview(params: {
  teams: string[]
  developers: string[]
  onlyOpen: boolean
  showReviewed: boolean
}) {
  return useQuery({
    queryKey: ['team-desk', 'overview', params],
    queryFn: () =>
      teamDeskApi.overview({
        teams: params.teams.join(',') || undefined,
        developers: params.developers.join(',') || undefined,
        only_open: params.onlyOpen,
        show_reviewed: params.showReviewed,
      }),
    enabled: params.teams.length > 0 || params.developers.length > 0,
  })
}

export function useDeskSettings() {
  return useQuery({ queryKey: ['team-desk', 'settings'], queryFn: teamDeskApi.settings })
}

export function useSaveDeskSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: DeskSettings) => teamDeskApi.saveSettings(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-desk'] }),
  })
}

export function useMarkFlag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { issueId: string; flag: FlagCode; signature: string; comment?: string }) =>
      teamDeskApi.mark(vars.issueId, {
        flag: vars.flag,
        signature: vars.signature,
        comment: vars.comment,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-desk', 'overview'] }),
  })
}

export function useUnmarkFlag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { issueId: string; flag: FlagCode }) =>
      teamDeskApi.unmark(vars.issueId, vars.flag),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-desk', 'overview'] }),
  })
}
```

- [ ] **Step 3: Проверить сборку**

Run: `cd frontend && npm run lint`
Expected: без ошибок в новых файлах

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/api/teamDesk.ts frontend/src/hooks/useTeamDesk.ts
git commit -m "feat(team-desk): клиент API и хуки раздела"
```

---

### Task 10: Общие элементы интерфейса — шкала и значок признака

**Files:**
- Create: `frontend/src/components/teamdesk/HoursScale.tsx`, `frontend/src/components/teamdesk/FlagChip.tsx`

- [ ] **Step 1: Шкала факт/оценка**

Создать `frontend/src/components/teamdesk/HoursScale.tsx`:

```tsx
import { Tooltip } from 'antd'

interface Props {
  fact: number
  est: number | null
  /** centered — засечка оценки посередине, недобор влево, перебор вправо (раскладка C) */
  variant?: 'bar' | 'centered'
  overrunPct: number
}

export function HoursScale({ fact, est, variant = 'bar', overrunPct }: Props) {
  if (est == null) {
    return <span style={{ color: '#7b8a9c' }}>{fact} / — ч</span>
  }
  const ratio = est > 0 ? fact / est : 0
  const over = ratio > 1 + overrunPct / 100
  const color = over ? '#ff6b6b' : fact === 0 ? '#788799' : '#3ebd85'

  if (variant === 'centered') {
    const left = ratio < 1 ? Math.min(1 - ratio, 1) * 50 : 0
    const right = ratio > 1 ? Math.min(ratio - 1, 1) * 50 : 0
    return (
      <Tooltip title={`Факт ${fact} ч из ${est} ч`}>
        <div style={{ width: 150 }}>
          <div style={{ position: 'relative', height: 14, background: '#1e2a39', borderRadius: 3 }}>
            <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: '#66788d' }} />
            {left > 0 && (
              <div style={{ position: 'absolute', top: 2, bottom: 2, right: '50%', width: `${left}%`, background: '#eeb13c', borderRadius: '2px 0 0 2px' }} />
            )}
            {right > 0 && (
              <div style={{ position: 'absolute', top: 2, bottom: 2, left: '50%', width: `${right}%`, background: color, borderRadius: '0 2px 2px 0' }} />
            )}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#8395aa' }}>
            <span>{ratio < 1 ? `−${Math.round((1 - ratio) * 100)}%` : ''}</span>
            <span>{fact}/{est} ч</span>
            <span>{ratio > 1 ? `+${Math.round((ratio - 1) * 100)}%` : ''}</span>
          </div>
        </div>
      </Tooltip>
    )
  }

  const base = Math.min(ratio, 1) * 100
  const tail = ratio > 1 ? Math.min(ratio - 1, 1) * 100 : 0
  return (
    <Tooltip title={`Факт ${fact} ч из ${est} ч`}>
      <div style={{ minWidth: 132 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontVariantNumeric: 'tabular-nums' }}>
          <span>{fact} / {est} ч</span>
          <span style={{ color }}>{Math.round(ratio * 100)}%</span>
        </div>
        <div style={{ position: 'relative', height: 5, borderRadius: 3, background: '#1e2a39', marginTop: 4, overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${base}%`, background: color, borderRadius: 3 }} />
          {tail > 0 && (
            <div style={{ position: 'absolute', top: 0, bottom: 0, left: `${100 - tail}%`, width: `${tail}%`, background: 'repeating-linear-gradient(135deg,#ff6b6b 0 3px,transparent 3px 6px)' }} />
          )}
        </div>
      </div>
    </Tooltip>
  )
}
```

- [ ] **Step 2: Значок признака с действием «Просмотрено»**

Создать `frontend/src/components/teamdesk/FlagChip.tsx`:

```tsx
import { useState } from 'react'
import { Dropdown, Input, Modal, Tag, Tooltip } from 'antd'
import { FLAG_LABELS, type FlagCode, type ReviewedMark } from '../../api/teamDesk'
import { useMarkFlag, useUnmarkFlag } from '../../hooks/useTeamDesk'

const ICON: Record<FlagCode, string> = {
  over: '↑', under: '↓', decomp: '⊞', childgap: '⊟',
  noest: '∅', nospent: '◔', stale: '⏳',
}
const COLOR: Record<FlagCode, string> = {
  over: 'red', under: 'gold', decomp: 'orange', childgap: 'orange',
  noest: 'default', nospent: 'default', stale: 'purple',
}

interface Props {
  issueId: string
  flag: FlagCode
  signature: string
  reviewed?: ReviewedMark
  count?: number
}

export function FlagChip({ issueId, flag, signature, reviewed, count }: Props) {
  const [open, setOpen] = useState(false)
  const [comment, setComment] = useState('')
  const mark = useMarkFlag()
  const unmark = useUnmarkFlag()

  const label = FLAG_LABELS[flag]
  const title = reviewed
    ? `${label} · просмотрено ${new Date(reviewed.marked_at).toLocaleDateString('ru')}${reviewed.comment ? ` · ${reviewed.comment}` : ''}`
    : label

  const items = reviewed
    ? [{ key: 'unmark', label: 'Вернуть в проблемные' }]
    : [{ key: 'mark', label: 'Просмотрено' }]

  return (
    <>
      <Dropdown
        menu={{
          items,
          onClick: ({ key }) => {
            if (key === 'unmark') unmark.mutate({ issueId, flag })
            else setOpen(true)
          },
        }}
        trigger={['click']}
      >
        <Tooltip title={title}>
          <Tag color={reviewed ? 'default' : COLOR[flag]} style={{ cursor: 'pointer', opacity: reviewed ? 0.5 : 1 }}>
            {ICON[flag]}{count != null ? ` ${count}` : ''}
          </Tag>
        </Tooltip>
      </Dropdown>
      <Modal
        title={`Просмотрено: ${label}`}
        open={open}
        okText="Отметить"
        cancelText="Отмена"
        onCancel={() => setOpen(false)}
        onOk={() => {
          mark.mutate({ issueId, flag, signature, comment: comment || undefined })
          setComment('')
          setOpen(false)
        }}
      >
        <p style={{ color: '#8395aa' }}>
          Признак перестанет считаться проблемой. Если причина изменится — задача сменит
          статус, вырастет факт или поменяется оценка — признак вернётся.
        </p>
        <Input.TextArea
          rows={2}
          placeholder="Комментарий (необязательно)"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </Modal>
    </>
  )
}
```

- [ ] **Step 3: Проверить сборку**

Run: `cd frontend && npm run lint && npm run build`
Expected: сборка проходит

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/components/teamdesk/
git commit -m "feat(team-desk): шкала часов и значок признака с отметкой"
```

---

### Task 11: Страница, шапка и три раскладки

**Files:**
- Create: `frontend/src/pages/TeamDeskPage.tsx`, `frontend/src/components/teamdesk/DeskFilters.tsx`, `ThresholdsPanel.tsx`, `IssueTable.tsx`, `DeveloperCards.tsx`, `DeveloperTable.tsx`, `GroupedIssueTable.tsx`, `WorkloadBars.tsx`, `AbsenceStrip.tsx`
- Modify: `frontend/src/pages/lazyPages.tsx`, `frontend/src/routes.tsx`, `frontend/src/components/Layout/AppLayout.tsx`

- [ ] **Step 1: Каркас страницы**

Создать `frontend/src/pages/TeamDeskPage.tsx`:

```tsx
import { useState } from 'react'
import { Card, Segmented, Space, Spin, Tabs, Typography } from 'antd'
import { useDeskOverview, useDeskSettings } from '../hooks/useTeamDesk'
import { DeskFilters } from '../components/teamdesk/DeskFilters'
import { ThresholdsPanel } from '../components/teamdesk/ThresholdsPanel'
import { DeveloperCards } from '../components/teamdesk/DeveloperCards'
import { DeveloperTable } from '../components/teamdesk/DeveloperTable'
import { GroupedIssueTable } from '../components/teamdesk/GroupedIssueTable'
import { IssueTable } from '../components/teamdesk/IssueTable'
import { WorkloadBars } from '../components/teamdesk/WorkloadBars'
import { AbsenceStrip } from '../components/teamdesk/AbsenceStrip'

export default function TeamDeskPage() {
  const [teams, setTeams] = useState<string[]>([])
  const [developers, setDevelopers] = useState<string[]>([])
  const [onlyOpen, setOnlyOpen] = useState(true)
  const [showReviewed, setShowReviewed] = useState(false)
  const [showThresholds, setShowThresholds] = useState(false)
  const [layout, setLayout] = useState<'cards' | 'table' | 'grouped'>('cards')
  const [selectedDev, setSelectedDev] = useState<string | null>(null)

  const settings = useDeskSettings()
  const overview = useDeskOverview({ teams, developers, onlyOpen, showReviewed })
  const data = overview.data

  const visibleIssues = selectedDev
    ? (data?.issues ?? []).filter((i) => i.developer_id === selectedDev)
    : (data?.issues ?? [])

  return (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ margin: 0 }}>Рабочий стол тимлида</Typography.Title>
        <Typography.Text type="secondary">
          Контроль задач в разрезе разработчиков: где стоит, кто не укладывается в оценку,
          что не разбито на подзадачи.
        </Typography.Text>
      </div>

      <DeskFilters
        teams={teams} onTeamsChange={setTeams}
        developers={developers} onDevelopersChange={setDevelopers}
        onlyOpen={onlyOpen} onOnlyOpenChange={setOnlyOpen}
        showReviewed={showReviewed} onShowReviewedChange={setShowReviewed}
        onToggleThresholds={() => setShowThresholds((v) => !v)}
      />

      {showThresholds && settings.data && <ThresholdsPanel settings={settings.data} />}

      <Tabs
        activeKey={layout}
        onChange={(key) => setLayout(key as typeof layout)}
        items={[
          { key: 'cards', label: 'Светофор' },
          { key: 'table', label: 'Ведомость' },
          { key: 'grouped', label: 'Проблемы вперёд' },
        ]}
      />

      {overview.isLoading && <Spin />}
      {data && layout === 'cards' && (
        <>
          <DeveloperCards
            developers={data.developers}
            workload={data.workload}
            selected={selectedDev}
            onSelect={setSelectedDev}
          />
          <Card size="small" title="Задачи">
            <IssueTable issues={visibleIssues} overrunPct={settings.data?.thresholds.overrun_pct ?? 30} />
          </Card>
          <Card size="small" title="Задач в работе одновременно">
            <WorkloadBars developers={data.developers} workload={data.workload}
              limit={settings.data?.thresholds.wip_limit ?? 3} />
          </Card>
        </>
      )}
      {data && layout === 'table' && (
        <>
          <DeveloperTable
            developers={data.developers}
            workload={data.workload}
            selected={selectedDev}
            onSelect={setSelectedDev}
          />
          <Card size="small" title="Задачи">
            <IssueTable issues={visibleIssues} overrunPct={settings.data?.thresholds.overrun_pct ?? 30} />
          </Card>
          <Card size="small" title="Задач в работе одновременно">
            <WorkloadBars developers={data.developers} workload={data.workload}
              limit={settings.data?.thresholds.wip_limit ?? 3} />
          </Card>
        </>
      )}
      {data && layout === 'grouped' && (
        <GroupedIssueTable
          developers={data.developers}
          issues={data.issues}
          flagCounts={data.flag_counts}
          overrunPct={settings.data?.thresholds.overrun_pct ?? 30}
        />
      )}

      <Card size="small" title="Отсутствия">
        <AbsenceStrip developerIds={data ? Object.values(data.workload).length : 0} />
      </Card>
    </Space>
  )
}
```

- [ ] **Step 2: Подключить маршрут и меню**

В `frontend/src/pages/lazyPages.tsx` добавить:

```tsx
export const TeamDeskPage = lazy(() => import('./TeamDeskPage'))
```

В `frontend/src/routes.tsx` в списке защищённых маршрутов добавить рядом с `/kpi`:

```tsx
{ path: 'team-desk', element: page(<TeamDeskPage />) },
```

В `frontend/src/components/Layout/AppLayout.tsx` в пункты меню рядом с «KPI» добавить:

```tsx
{ key: '/team-desk', icon: <TeamOutlined />, label: 'Стол тимлида' },
```

- [ ] **Step 3: Написать остальные компоненты раскладок**

`DeskFilters.tsx` — мультиселект команд (данные из `/teams`), мультиселект людей (данные из `/employees`), переключатель «Открытые сейчас / Весь период», переключатель «Показывать просмотренные», кнопка-шестерёнка.

`ThresholdsPanel.tsx` — шесть `InputNumber` по ключам `decomposition_hours`, `overrun_pct`, `underrun_pct`, `stale_days`, `child_gap_pct`, `wip_limit`; кнопка «Сохранить» вызывает `useSaveDeskSettings`.

`IssueTable.tsx` — AntD `Table` с `expandable` по подзадачам (`parent_id`), колонки: ключ (ссылка в Jira), название, статус (`Tag` с точкой цвета по `status_group`), разработчик, оценка, факт, `HoursScale`, дней в статусе, признаки (`FlagChip` на каждый код из `flags` и из `reviewed`).

`DeveloperCards.tsx` — сетка карточек: инициалы, имя, число задач, разбивка «у него / ждут не его / не начаты», `HoursScale`, точность, значки признаков; выбранная карточка подсвечена.

`DeveloperTable.tsx` — те же данные `Table`, строка «Итого» через `summary`.

`GroupedIssueTable.tsx` — лента `FlagChip`-фильтров сверху, ниже `Table` с группировкой по разработчику (строки-группы раскрываются), `HoursScale variant="centered"`.

`WorkloadBars.tsx` — по каждому человеку полоса `queue_hours / available_hours`, пунктир на лимите, подпись «≈ N дней» и «ещё N задач без оценки».

`AbsenceStrip.tsx` — переиспользует существующий `AbsenceHeatmap` из `components/capacity/`, ограниченный выбранными людьми.

Выбранная раскладка запоминается: `localStorage.setItem('team-desk-layout', layout)` при смене, чтение при монтировании страницы. Тимлид пробует все три и остаётся на удобной — переключать её каждый вход он не должен.

- [ ] **Step 4: Проверить сборку и открыть страницу**

Run: `cd frontend && npm run lint && npm run build`
Затем: `uvicorn app.main:app --reload --port 8000` и `npm run dev`, открыть `http://localhost:5173/team-desk`
Expected: страница открывается, при выборе команды таблица наполняется

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/pages/TeamDeskPage.tsx frontend/src/pages/lazyPages.tsx frontend/src/routes.tsx frontend/src/components/teamdesk/ frontend/src/components/Layout/AppLayout.tsx
git commit -m "feat(team-desk): страница раздела с тремя раскладками"
```

---

### Task 12: Сопоставление полей и настройки в администрировании

**Files:**
- Modify: `frontend/src/components/JiraFieldsCard.tsx`, `frontend/src/pages/SettingsPage.tsx`
- Create: `frontend/src/components/settings/TeamDeskSettingsTab.tsx`

- [ ] **Step 1: Два новых поля в сопоставлении**

В `frontend/src/components/JiraFieldsCard.tsx` в список сопоставляемых полей добавить:

```tsx
{ key: 'jira_developer_field_id', label: 'Разработчик', hint: 'Кастомное поле-пользователь' },
{ key: 'jira_dev_est_field_id', label: 'Оценка разработки, ч', hint: 'DEV est (ч)' },
```

- [ ] **Step 2: Секция настроек раздела**

Создать `frontend/src/components/settings/TeamDeskSettingsTab.tsx` — редактор групп статусов: четыре списка (`dev`, `waiting`, `todo`, `done`) с перетаскиванием статусов между ними, отдельный блок «Статусы очереди работы», списки типов подзадач и типов задач по исполнителю, блок порогов. Источник статусов — уникальные значения `status` из `/issues/tree` либо ручной ввод. Статусы, не попавшие ни в одну группу, показываются сверху с пометкой «не распределены».

В `frontend/src/pages/SettingsPage.tsx` в группу «Справочники» добавить пункт:

```tsx
{ key: 'team-desk', label: 'Стол тимлида', render: () => <TeamDeskSettingsTab /> },
```

- [ ] **Step 3: Проверить сборку**

Run: `cd frontend && npm run lint && npm run build`
Expected: сборка проходит

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/components/JiraFieldsCard.tsx frontend/src/components/settings/TeamDeskSettingsTab.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat(team-desk): сопоставление полей и настройки раздела"
```

---

### Task 13: Перезаливка задач и проверка на живых данных

**Files:** нет изменений кода

- [ ] **Step 1: Указать поля в настройках**

Открыть `/settings` → «Подключение» → «Поля Jira», выбрать:
- «Разработчик» → `customfield_14052`
- «Оценка разработки, ч» → `customfield_12952`

- [ ] **Step 2: Перезалить задачи**

На `/sync` запустить обычную синхронизацию задач.
Expected: в базе у задач проекта OS заполнены разработчик и оценка

- [ ] **Step 3: Проверить раздел**

Открыть `/team-desk`, выбрать команды «Команда 1С (ERP - Товарный учет)» и «Команда 1С (ERP - УУ)».
Expected: в сводке видны Шутов, Кирилов, Поляков, Болдонов, Пряничников, Золотонос; у части задач горят признаки.

- [ ] **Step 4: Проверить отметку**

Нажать на значок «Зависла» у любой задачи → «Просмотрено» → признак гаснет, счётчик уменьшается. Включить «Показывать просмотренные» → признак виден приглушённым с комментарием.

- [ ] **Step 5: Обновить документацию**

Дописать раздел в `app/api/CLAUDE.md` (роутер `/team-desk`), `frontend/CLAUDE.md` (страница `/team-desk`), `app/services/CLAUDE.md` (пакет `team_desk`), `app/models/CLAUDE.md` (таблица `team_desk_marks` и новые поля задачи).

- [ ] **Step 6: Прогнать всё и закоммитить**

```bash
py -3.10 -m pytest tests/ -q
ruff check app/ tests/
cd frontend && npm run lint && npm run build && cd ..
git add app/api/CLAUDE.md frontend/CLAUDE.md app/services/CLAUDE.md app/models/CLAUDE.md
git commit -m "docs(team-desk): документация раздела"
```

---

## Заметки для исполнителя

- **Windows:** pytest только через `py -3.10 -m pytest`; после правок бэкенда убить процесс на порту 8000 и перезапустить uvicorn — `--reload` на Windows подвисает.
- **Миграции:** SQLite требует `batch_alter_table` для любого ALTER.
- **Тесты чистят за собой:** сервисы коммитят сами, поэтому в тестах чистить таблицы через фикстуры `conftest.py` (см. `tests/CLAUDE.md`).
- **Состав команды** запрашивать только через `app/services/team_membership.py` — прямые запросы к участию тянут выбывших задним числом.
- **После правок кода** прогнать `graphify .` для обновления графа знаний (полная пересборка, не инкрементальная).
