# Фиксация вовлечённости в фазе — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Процент вовлечённости фазы — только из сервиса: фиксация в фазе → личная настройка → справочник → 100%; вовлечённость из Jira не загружается.

**Architecture:** «Своё значение задачи» (`BacklogItem.involvement_*`) становится фиксацией и поднимается выше личной настройки. Синхронизация перестаёт читать поля Jira; колонки `Issue.involvement_*` удаляются; миграция iv01 (не выпущена) переписывается — снимает все проценты задач и удаляет колонки. UI: галочка «Зафиксировано» в карточке фазы, блок вовлечённости из «Параметров планирования» и строки из настроек полей Jira убираются.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic (batch для SQLite), pytest; React 19 + AntD 6.

Спека: `docs/superpowers/specs/2026-09-30-phase-involvement-fix-design.md`.

---

### Task 1: Фиксация главнее личной настройки

**Files:**
- Modify: `app/services/involvement_default_service.py` (`effective_for_phase`)
- Modify: `app/api/endpoints/resource_planning.py` (`_effective_involvement`, ~4002)
- Test: `tests/services/test_rp_personal_involvement.py`

- [ ] **Step 1: тесты.** В `_erp_plan` добавить параметр `task: Optional[float] = 0.7` (`item.involvement_dev = task`). Заменить `test_personal_involvement_wins_over_task_and_team` двумя:

```python
def test_fixed_task_wins_over_personal(db_session):
    """Зафиксированные в фазе 70% главнее личных 100% и справочника 90%."""
    _, row = _erp_plan(db_session, personal=1.0)
    assert [round(h, 2) for h in _daily(row)] == [5.6, 5.6, 4.8]


def test_personal_wins_over_team(db_session):
    """Без фиксации личные 100% главнее справочника 90%."""
    _, row = _erp_plan(db_session, personal=1.0, task=None)
    assert _daily(row) == [8.0, 8.0]
```

В `test_phase_explanation_source_is_employee`, `test_phase_explanation_reads_involvement_once`, `test_plan_quarter_without_q_prefix_takes_personal` — `task=None`. Добавить:

```python
def test_phase_explanation_source_is_task_when_fixed(client, db_session):
    plan, row = _erp_plan(db_session, personal=1.0)
    calc = _explain(client, plan.id, row.id)["phase_calc"]
    assert (calc["involvement_source"], calc["involvement_pct"]) == ("task", 70)
```

- [ ] **Step 2:** `py -3.10 -m pytest tests/services/test_rp_personal_involvement.py -q` → новые падают.
- [ ] **Step 3: код.**

```python
def effective_for_phase(item, phase, defaults, personal=None):
    """Вовлечённость фазы: зафиксированная у задачи, иначе личная вовлечённость
    исполнителя на квартал (``personal``), иначе значение справочника."""
    field = PHASE_FIELD.get(phase)
    if not field:
        return None
    own = getattr(item, field, None)
    if own is not None:
        return own
    if personal is not None:
        return personal
    return defaults.get(phase)
```

`_effective_involvement`: после `inv is None` → `if getattr(bi, PHASE_FIELD[a.phase]) is not None: return inv, "task"`; затем `if personal is not None: return inv, "employee"`; иначе `"team"`. Докстринг — новый порядок.
- [ ] **Step 4:** тесты зелёные.

### Task 2: Снятие фиксации через API

**Files:** `app/api/endpoints/resource_planning.py` (`InvolvementUpdate`, `set_assignment_involvement`); Test: `tests/test_api_assignment_involvement.py`

- [ ] **Step 1: тест.**

```python
def test_put_null_involvement_unfixes(client, db_session, ready_plan):
    from app.models import BacklogItem
    a = _analyst_assignment(db_session, ready_plan["plan_id"])
    url = (f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}"
           f"/assignments/{a.id}/involvement")
    assert client.put(url, json={"involvement_pct": 70}).status_code == 200
    a = _analyst_assignment(db_session, ready_plan["plan_id"])
    url = (f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}"
           f"/assignments/{a.id}/involvement")
    r = client.put(url, json={"involvement_pct": None})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.get(BacklogItem, ready_plan["item_id"]).involvement_analyst is None
```

- [ ] **Step 2:** падает (422).
- [ ] **Step 3: код.** `involvement_pct: Optional[int] = Field(ge=0, le=100)`; `setattr(bi, field, None if data.involvement_pct is None else data.involvement_pct / 100.0)`. Докстринги: «зафиксировать / снять фиксацию».
- [ ] **Step 4:** зелёные.

### Task 3: Вовлечённость из Jira больше не загружается

**Files:** `app/services/sync_service.py` (ключи 368-371, строки 1013-1016, докстринг 717); `app/services/backlog_service.py` (~510); `app/models/issue.py` (143-146); `app/api/endpoints/backlog.py` (89-92, 224-227, 508-511); Tests: `tests/test_backlog_service.py`, `tests/test_plan_edit_backlog_sync.py`

- [ ] **Step 1: тесты.** `tests/test_backlog_service.py`: убрать involvement из `_make_issue` вызовов и проверок; добавить

```python
def test_sync_keeps_fixed_involvement(db_session, proj):
    """Синхронизация не трогает зафиксированную вовлечённость задачи."""
    issue = _make_issue(db_session, proj, "BS-4")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    item.involvement_dev = 0.5
    db_session.commit()
    item2 = svc.sync_from_issue(issue)
    db_session.commit()
    assert item2.involvement_dev == pytest.approx(0.5)
```

`tests/test_plan_edit_backlog_sync.py::test_inline_estimate_with_other_fields_keeps_them`: `involvement_dev` → `duration_dev_days` (seed `duration_dev_days=5`, запрос `duration_dev_days: 8`, проверка `== 8`).
- [ ] **Step 2: код.** Удалить 4 ключа и 4 строки `data["involvement_*"]` в синхронизации; из цикла в `backlog_service` — 4 поля involvement (комментарий: «Длительности из Jira»); из `Issue` — 4 колонки (комментарий «Durations — synced»); из `backlog.py` — `involvement_*` в схеме правки и `involvement_*_jira` в ответе.
- [ ] **Step 3:** `grep -rn "issue.involvement\|involvement_.*_jira\|jira_involvement" app/` — пусто; тесты файлов зелёные.

### Task 4: Миграция iv01 — снять все проценты задач, удалить колонки

**Files:** Modify: `alembic/versions/iv01_clear_frozen_involvement.py`; Test: `tests/test_migration_iv01_clear_frozen_involvement.py` (переписать)

- [ ] **Step 1: тест** — настоящая цепочка на пустой SQLite: `alembic upgrade ob01_onboarding`, вставка задачи Jira и строки бэклога с процентами (sqlite3), `alembic upgrade iv01_clear_frozen_involvement`, проверка: проценты строки бэклога `NULL`, в `issues` нет колонок `involvement_*`.
- [ ] **Step 2: код.**

```python
def upgrade() -> None:
    items = sa.table("backlog_items", *(sa.column(f) for f in FIELDS))
    op.get_bind().execute(items.update().values({f: None for f in FIELDS}))
    if not context.is_offline_mode():
        cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("issues")}
    else:
        cols = set(FIELDS)
    to_drop = [f for f in FIELDS if f in cols]
    if to_drop:
        with op.batch_alter_table("issues") as batch_op:
            for f in to_drop:
                batch_op.drop_column(f)


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        for f in FIELDS:
            batch_op.add_column(sa.Column(f, sa.Float(), nullable=True))
```

`FIELDS = ("involvement_analyst", "involvement_dev", "involvement_qa", "involvement_launch")`. Докстринг — зачем.
- [ ] **Step 3:** тест + `tests/test_migrations_fresh_db.py` зелёные.

### Task 5: Интерфейс

**Files:** `frontend/src/api/resourcePlanning.ts` (`setAssignmentInvolvement`), `frontend/src/components/resource-planning/AssignmentSidebar.tsx` (`InvolvementEditor`), `frontend/src/components/resource-planning/sidebar/PhaseCalcSection.tsx`, `frontend/src/components/backlog/BacklogPlanningParamsModal.tsx`, `frontend/src/types/api.ts`, `frontend/src/components/JiraFieldsCard.tsx`, `frontend/help-videos/rp-executor.video.ts`, `frontend/help-videos/backlog-planning-params.video.ts`

- [ ] `setAssignmentInvolvement(planId, assignmentId, involvementPct: number | null)`.
- [ ] `InvolvementEditor`: `fixed = involvement_source === 'task'`. Строка: `InputNumber` (disabled, пока не зафиксировано), `Checkbox «Зафиксировано»`, `Button «Сохранить»` (виден при галочке). Галочка вкл. → локально, поле открывается с текущим значением; «Сохранить» → PUT pct. Галочка выкл. на зафиксированной → сразу PUT null. Подпись источника под полем, если не зафиксировано: «из справочника команды» / «личная настройка сотрудника» / «не задана — 100%». Ветку «личная настройка — поле серое» удалить.
- [ ] `PhaseCalcSection`: для `task` — пометка «зафиксировано».
- [ ] Модальное окно бэклога: убрать вовлечённость из состояния, строки фазы и сохранения; убрать `involvement_*_jira` из типов.
- [ ] `JiraFieldsCard`: убрать 4 строки вовлечённости; заголовок панели «Длительности».
- [ ] Ролики: rp-executor — перед вводом кликнуть «Зафиксировано», в конце вернуть исходное (null, если фаза не была зафиксирована); backlog-planning-params — убрать правку вовлечённости в окне, вместо финала с «Распределить» — подпись, что вовлечённость фиксируется в карточке фазы ресурсного плана.
- [ ] `npm run lint`, `npm run build` — без новых ошибок.

### Task 6: Справка и заметка

- [ ] `docs/help/resource-planning.md`: порядок источников (фиксация → личная → справочник), карточка фазы (галочка), расшифровка (пометка «зафиксировано»), строки 382/409.
- [ ] `docs/help/planning.md`: абзац справочника (фиксация в фазе вместо «из Jira или боковой панели»).
- [ ] `docs/help/backlog.md`: вовлечённость в окне и «из Jira» убрать, порядок источников.
- [ ] `docs/help/settings.md`: строки полей Jira — только длительности.
- [ ] `scripts/release_note.py add --type improvement --section resources ...`.

### Task 7: Проверка и выпуск в main

- [ ] `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py` — зелёные.
- [ ] Postgres: контейнер на 15432, `TEST_DATABASE_URL=... pytest` — зелёные.
- [ ] `ruff check app/ tests/`, `mypy app/` — не хуже, чем до.
- [ ] Коммиты по задачам, `git push origin HEAD:main` (проверить ветку).
