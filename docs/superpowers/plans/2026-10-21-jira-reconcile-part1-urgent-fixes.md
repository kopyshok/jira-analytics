# Сверка с Jira — часть 1: срочная правка при обновлении версии

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** после обновления версии KPI, стол тимлида, план QA, автоархив, пауза Cycle Time, сводка для руководителя и тематический отчёт снова работают со значениями новой Jira DC — без ручной работы.

**Architecture:** миграция данных `jr01` правит сохранённые настройки (условия KPI, исключённые статусы KPI, конфиг стола тимлида, поле плановых часов QA) только там, где найдено старое значение; логика — чистые функции в самой миграции (миграция не импортирует код приложения). Код: умолчания и сид подставляют новые значения; автоархив и пауза понимают новые статусы; «выполнено» определяется по категории статуса.

**Tech Stack:** Python 3.10, SQLAlchemy 2.0 Core в миграции Alembic, pytest (`py -3.10 -m pytest`).

Спека: `docs/superpowers/specs/2026-10-21-jira-reconcile-design.md`, раздел «Часть 1».

Рабочая папка: `D:\ClaudeDev\JiraAnalysis\.worktrees\jira-reconcile` (ветка `feature/jira-reconcile`). Все команды — из неё. Тесты: `py -3.10 -m pytest <путь> -q -p no:cacheprovider`. Полный прогон — без `tests/api/test_llm.py` (висит без сети).

## Файлы

| Файл | Что |
|---|---|
| `app/models/issue.py` | свойство `Issue.is_done` |
| `app/services/executive_dashboard_service.py` | 7 проверок `status.lower() == "done"` → `is_done` |
| `app/services/work_type_report_service.py` | 1 проверка → `is_done` |
| `app/services/sync_service.py` | `PAUSED_STATUSES` + `Hold`; автоархив через `is_cancel_like` |
| `app/services/kpi/settings.py` | умолчание исключённых статусов + `Won't Do` |
| `app/services/team_desk/config.py` | умолчания групп/очереди/скрытых + новые статусы |
| `app/services/kpi/seed.py` | резолюция `Готово`, исключение бэклога + `IDEA BACKLOG`, `APPROVED IDEA BACKLOG` |
| `alembic/versions/jr01_jira_dc_value_fixes.py` | миграция данных |
| `tests/test_migration_jr01_jira_dc_value_fixes.py` | тесты миграции |
| `tests/test_issue_is_done.py`, правки существующих тестов | см. задачи |
| `release_notes/drafts.json` | заметка «Что нового» (только дописать) |

---

### Task 1: «Выполнено» по категории статуса

**Files:**
- Modify: `app/models/issue.py` (рядом со свойствами `planned_*`, ~строка 122)
- Modify: `app/services/executive_dashboard_service.py:173,185,232,247,288,450,493`
- Modify: `app/services/work_type_report_service.py:551`
- Test: `tests/test_issue_is_done.py`

- [ ] **Step 1: Write the failing test**

```python
"""«Выполнено» — по категории статуса Jira: имена статусов у нас русские и меняются."""
from app.models.issue import Issue


def test_done_by_status_category():
    assert Issue(status="ГОТОВО", status_category="done").is_done is True
    assert Issue(status="Won't Do", status_category="done").is_done is True


def test_done_by_legacy_status_name():
    # Старые данные и тесты без категории: статус с именем Done.
    assert Issue(status="Done", status_category=None).is_done is True


def test_not_done():
    assert Issue(status="В РАБОТЕ", status_category="indeterminate").is_done is False
    assert Issue(status=None, status_category=None).is_done is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_issue_is_done.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: 'Issue' object has no attribute 'is_done'`

- [ ] **Step 3: Add the property** in `app/models/issue.py` right after the `planned_opo_hours` property:

```python
    @property
    def is_done(self) -> bool:
        """Задача выполнена: категория статуса Jira «done».

        Имя статуса не годится — у нас «ГОТОВО», «Готово», «Won't Do», и Jira
        переименовывает их. Имя «Done» оставлено для данных без категории.
        """
        return self.status_category == "done" or (self.status or "").lower() == "done"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.10 -m pytest tests/test_issue_is_done.py -q -p no:cacheprovider`
Expected: 3 passed

- [ ] **Step 5: Use it in the executive dashboard.** In `app/services/executive_dashboard_service.py` replace every
`(i.status or "").lower() != "done"` with `not i.is_done` and every `(i.status or "").lower() == "done"` with `i.is_done` (lines 173, 185, 232, 247, 288, 450, 493). Check each `i` there is an `Issue` ORM object (they come from `select(Issue)`, lines 138 and 222; `theme_issues` at 473 — open the code and confirm; if any of them is a row of columns, select `Issue.status_category` too and keep a local equivalent check). Verify nothing is left:

Run: `grep -n "lower() [!=]= \"done\"" app/services/executive_dashboard_service.py app/services/work_type_report_service.py`
Expected: только строка 551 в work_type_report_service.py (её — следующий шаг).

- [ ] **Step 6: Use it in the work type report.** `app/services/work_type_report_service.py:551`:

```python
                "is_done": issue.is_done,
```
(`issue` там из `_select_scope_issues` → `select(Issue)`, строка 499 — это ORM-объекты.)

- [ ] **Step 7: Run related tests**

Run: `py -3.10 -m pytest tests/test_issue_is_done.py tests/test_executive_dashboard_service.py tests/test_executive_endpoint.py tests/test_work_type_report_service.py tests/test_work_type_report_endpoints.py -q -p no:cacheprovider`
Expected: all passed

- [ ] **Step 8: Commit**

```bash
git add app/models/issue.py app/services/executive_dashboard_service.py app/services/work_type_report_service.py tests/test_issue_is_done.py
git commit -m "fix(executive): выполненные задачи — по категории статуса, а не по имени Done"
```

---

### Task 2: Автоархив и пауза понимают новые статусы

**Files:**
- Modify: `app/services/sync_service.py:320` (`PAUSED_STATUSES`), `:1312-1319` (автоархив в `_upsert_issue`)
- Test: `tests/test_paused_days.py` (дописать), `tests/test_sync_auto_archive.py` (новый)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_paused_days.py`:

```python
def test_hold_is_a_pause_too():
    """После переезда на Jira DC появился статус Hold — та же пауза, что «Приостановлено»."""
    changes = [
        ("2026-01-01T10:00:00.000+0300", "Hold"),
        ("2026-01-11T10:00:00.000+0300", "В РАБОТЕ"),
    ]
    assert paused_days_from_changes(changes) == 10.0
```

Create `tests/test_sync_auto_archive.py`:

```python
"""Автоархив синка: отменённая задача без ручной категории уходит в архив."""
from app.models.issue import Issue
from app.services.sync_service import _auto_archive_cancelled


def test_wont_do_goes_to_archive():
    issue = Issue(status="Won't Do", assigned_category=None, include_in_analysis=True)
    _auto_archive_cancelled(issue)
    assert (issue.category, issue.assigned_category, issue.include_in_analysis) == ("archive", "archive", False)
    assert issue.category_verified is True


def test_old_cancel_status_still_archived():
    issue = Issue(status="Отменено", assigned_category=None, include_in_analysis=True)
    _auto_archive_cancelled(issue)
    assert issue.category == "archive"


def test_manual_category_kept():
    issue = Issue(status="Won't Do", assigned_category="archive_target", category="archive_target")
    _auto_archive_cancelled(issue)
    assert issue.category == "archive_target"


def test_open_issue_untouched():
    issue = Issue(status="В РАБОТЕ", assigned_category=None, category="active")
    _auto_archive_cancelled(issue)
    assert issue.category == "active"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/test_paused_days.py tests/test_sync_auto_archive.py -q -p no:cacheprovider`
Expected: `test_hold_is_a_pause_too` FAIL (0.0 != 10.0); `test_sync_auto_archive.py` — ImportError `_auto_archive_cancelled`.

- [ ] **Step 3: Implement.** In `app/services/sync_service.py`:

`PAUSED_STATUSES` (строка 320) и комментарий над ним:

```python
# Статусы «задача на паузе»: время в них не считается сроком выполнения и
# вычитается из факта Cycle Time. «Hold» появился после переезда на Jira DC.
# ponytail: список зашит в код — справочник заводить незачем, пока пауз две.
PAUSED_STATUSES = ("Приостановлено", "Hold")
```

Добавить импорт `is_cancel_like` к существующему `from app.services.backlog_service import switch_off_if_became_service_epic`:

```python
from app.services.backlog_service import is_cancel_like, switch_off_if_became_service_epic
```

Модульная функция (рядом с `paused_days_from_changes`):

```python
def _auto_archive_cancelled(issue: Issue) -> None:
    """Отменённая задача без явной категории сразу уходит в архив — PM не
    разбирает её вручную. Категорию, назначенную PM, не трогаем. Статусы
    отмены — общий список бэклога (там и «Won't Do» новой Jira)."""
    if is_cancel_like(issue) and issue.assigned_category is None:
        issue.assigned_category = "archive"
        issue.category = "archive"
        issue.include_in_analysis = False
        issue.category_verified = True
```

В `_upsert_issue` заменить блок (строки ~1312-1319, начинается с комментария «# Авто-архив: задачи в статусе «Отменено»…» и `if issue.status == "Отменено" and issue.assigned_category is None:`) на:

```python
        _auto_archive_cancelled(issue)
```

Если импорт `is_cancel_like` из `backlog_service` даёт циклический импорт — проверить: `py -3.10 -c "import app.services.sync_service"`. `backlog_service` уже импортируется в sync_service, цикла быть не должно.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_paused_days.py tests/test_sync_auto_archive.py -q -p no:cacheprovider`
Expected: all passed

- [ ] **Step 5: Run sync-related tests**

Run: `py -3.10 -m pytest tests -q -p no:cacheprovider -k "sync or paused or archive"`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add app/services/sync_service.py tests/test_paused_days.py tests/test_sync_auto_archive.py
git commit -m "fix(sync): автоархив понимает Won't Do, Hold — пауза Cycle Time"
```

---

### Task 3: Умолчания и сид — значения новой Jira

**Files:**
- Modify: `app/services/kpi/settings.py:9`
- Modify: `app/services/team_desk/config.py:22-56`
- Modify: `app/services/kpi/seed.py:24-26,142,153`
- Modify tests: `tests/services/test_kpi_settings.py:8`, `tests/test_kpi_settings_endpoints.py:359`, `tests/services/test_kpi_seed.py:49-61`, `tests/test_team_desk_config.py:16`

- [ ] **Step 1: Update tests to the new expectations (they fail now)**

`tests/services/test_kpi_settings.py` строка 8:
```python
    assert s.excluded_statuses == ["Отменено", "Won't Do"]
```
`tests/test_kpi_settings_endpoints.py` строка 359:
```python
        assert body["excluded_statuses"] == ["Отменено", "Won't Do"]
```
`tests/test_team_desk_config.py` строка 16:
```python
    assert cfg.queue_statuses == ["К выполнению", "Сделать", "В РАБОТЕ", "Ожидает помещения"]
```
и дописать в этот файл:
```python
def test_defaults_know_jira_dc_statuses():
    """После переезда на Jira DC: Won't Do — завершена, Сделать — к выполнению,
    IDEA BACKLOG — бэклог (скрыт), Hold — пауза."""
    from app.services.team_desk.config import DEFAULT_HIDDEN_STATUSES, DEFAULT_STATUS_GROUPS

    assert "Won't Do" in DEFAULT_STATUS_GROUPS["done"]
    for status in ("Сделать", "IDEA BACKLOG", "APPROVED IDEA BACKLOG", "Hold"):
        assert status in DEFAULT_STATUS_GROUPS["todo"]
    assert {"IDEA BACKLOG", "APPROVED IDEA BACKLOG"} <= set(DEFAULT_HIDDEN_STATUSES)
```
`tests/services/test_kpi_seed.py` — заменить тест `test_seed_uses_actual_done_resolution_value` (строки ~49-61):
```python
def test_seed_uses_actual_done_resolution_value(db_session):
    """Резолюция «выполнено» в Jira DC называется «Готово» (в облаке была Done)."""
    seed_defaults(db_session)
    db_session.commit()

    for metric in db_session.query(KpiMetric).all():
        for cond_json in (metric.numerator_json, metric.denominator_json):
            if not cond_json:
                continue
            values = _resolution_values(cond_json)
            assert "Done" not in values
            if values:
                assert values == {"Готово"}


def test_seed_backlog_exclusion_knows_jira_dc_statuses(db_session):
    seed_defaults(db_session)
    db_session.commit()
    import json

    found = False
    for metric in db_session.query(KpiMetric).all():
        for cond_json in (metric.numerator_json, metric.denominator_json):
            for c in (json.loads(cond_json).get("conditions") if cond_json else []) or []:
                if c.get("attr") == "status" and c.get("op") == "not_in":
                    found = True
                    assert {"Backlog", "Бэклог", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"} <= set(c["value"])
    assert found
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/services/test_kpi_settings.py tests/test_kpi_settings_endpoints.py tests/services/test_kpi_seed.py tests/test_team_desk_config.py -q -p no:cacheprovider`
Expected: the changed/new tests FAIL

- [ ] **Step 3: Implement**

`app/services/kpi/settings.py:9`:
```python
# «Won't Do» — отмена в Jira DC (в облаке был статус «Отменено»).
DEFAULT_EXCLUDED_STATUSES = ["Отменено", "Won't Do"]
```

`app/services/team_desk/config.py` — умолчания:
```python
    "todo": [
        "Backlog", "IDEA BACKLOG", "APPROVED IDEA BACKLOG",
        "К выполнению", "Сделать", "Приостановлено", "Hold",
    ],
    "done": ["ГОТОВО", "Готово", "Отменено", "Won't Do"],
}

DEFAULT_QUEUE_STATUSES = ["К выполнению", "Сделать", "В РАБОТЕ", "Ожидает помещения"]
```
и
```python
DEFAULT_HIDDEN_STATUSES = ["Backlog", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
```
Над `DEFAULT_STATUS_GROUPS` дописать в комментарий строку: «Jira DC переименовала часть статусов (Отменено → Won't Do, К выполнению → Сделать, Backlog → IDEA BACKLOG, Приостановлено → Hold) — перечислены оба имени.»

`app/services/kpi/seed.py:24-26`:
```python
# «Готово» из ТЗ — так резолюция и называется в Jira DC (в облаке была Done).
RESOLUTION_DONE = "Готово"
```
строки 142 и 153 (`{"attr": "status", "op": "not_in", "value": ["Backlog", "Бэклог"]}`) — обе:
```python
                {"attr": "status", "op": "not_in",
                 "value": ["Backlog", "Бэклог", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/services/test_kpi_settings.py tests/test_kpi_settings_endpoints.py tests/services/test_kpi_seed.py tests/test_team_desk_config.py -q -p no:cacheprovider`
Expected: all passed

- [ ] **Step 5: Run KPI and team desk tests (catch other expectations of old defaults)**

Run: `py -3.10 -m pytest tests -q -p no:cacheprovider -k "kpi or team_desk or desk"`
Expected: all passed. Если падает тест, который явно ждёт старое значение умолчания (`["Отменено"]`, `"Done"` из сида, старую очередь) — обновить ожидание на новое; если падает по другой причине — остановиться и сообщить.

- [ ] **Step 6: Commit**

```bash
git add app/services/kpi/settings.py app/services/team_desk/config.py app/services/kpi/seed.py tests/services/test_kpi_settings.py tests/test_kpi_settings_endpoints.py tests/services/test_kpi_seed.py tests/test_team_desk_config.py
git commit -m "fix(kpi,desk): умолчания и сид — статусы и резолюция Jira DC"
```

---

### Task 4: Миграция данных jr01

**Files:**
- Create: `alembic/versions/jr01_jira_dc_value_fixes.py`
- Test: `tests/test_migration_jr01_jira_dc_value_fixes.py`

- [ ] **Step 1: Check the head**

Run: `py -3.10 -m alembic heads`
Expected: `em01_employee_account_aliases (head)`. Если голова другая — `down_revision` ниже поставить на неё.

- [ ] **Step 2: Write the failing test** `tests/test_migration_jr01_jira_dc_value_fixes.py`:

```python
"""Миграция jr01: настройки после переезда на Jira DC — новые имена статусов, резолюции, поля QA."""
import importlib.util
import json
from pathlib import Path

from app.models.app_setting import AppSetting
from app.models.kpi import KpiMetric


def _module():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "jr01_jira_dc_value_fixes.py"
    spec = importlib.util.spec_from_file_location("migration_jr01", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _spec(*conditions):
    return {"unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": list(conditions)}


def test_metric_spec_done_and_backlog():
    m = _module()
    spec = _spec(
        {"attr": "resolution", "op": "in", "value": ["Done"]},
        {"attr": "status", "op": "not_in", "value": ["Backlog", "Бэклог"]},
        {"attr": "issue_type", "op": "in", "value": ["Done"]},
    )
    assert m.fix_metric_spec(spec) is True
    assert spec["conditions"][0]["value"] == ["Готово"]
    assert spec["conditions"][1]["value"] == ["Backlog", "Бэклог", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    assert spec["conditions"][2]["value"] == ["Done"]  # не резолюция — не трогаем
    assert m.fix_metric_spec(spec) is False  # повторно — без изменений


def test_metric_spec_eq_and_dedupe():
    m = _module()
    spec = _spec({"attr": "resolution", "op": "eq", "value": "Done"},
                 {"attr": "resolution", "op": "in", "value": ["Done", "Готово"]})
    assert m.fix_metric_spec(spec) is True
    assert spec["conditions"][0]["value"] == "Готово"
    assert spec["conditions"][1]["value"] == ["Готово"]


def test_status_list_additions_only_next_to_source():
    m = _module()
    assert m.fix_status_list(["ГОТОВО", "Отменено"]) == ["ГОТОВО", "Отменено", "Won't Do"]
    assert m.fix_status_list(["К выполнению", "В РАБОТЕ"]) == ["К выполнению", "В РАБОТЕ", "Сделать"]
    assert m.fix_status_list(["Backlog"]) == ["Backlog", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    assert m.fix_status_list(["Приостановлено"]) == ["Приостановлено", "Hold"]
    assert m.fix_status_list(["В РАБОТЕ"]) == ["В РАБОТЕ"]
    assert m.fix_status_list(["Отменено", "Won't Do"]) == ["Отменено", "Won't Do"]


def test_qa_setting():
    m = _module()
    raw = json.dumps([
        {"field_id": "customfield_11140", "kind": "alt", "name": "Тестирование (ч)"},
        {"field_id": "customfield_10845", "kind": "alt", "name": "QA spent (ч)"},
    ], ensure_ascii=False)
    fixed = json.loads(m.fix_qa_setting(raw))
    assert fixed[1] == {"field_id": "customfield_11042", "kind": "alt", "name": "Оценка QA (ч)"}
    assert fixed[0]["field_id"] == "customfield_11140"
    assert m.fix_qa_setting("customfield_10845") == "customfield_11042"
    assert m.fix_qa_setting("customfield_11140") == "customfield_11140"
    assert m.fix_qa_setting("") == ""


def test_upgrade_on_database(db_session):
    m = _module()
    metric = KpiMetric(
        code="quality", name="Качество", calc_kind="ratio", invert=False, cap_at_100=True,
        is_builtin=True,
        numerator_json=json.dumps(_spec({"attr": "resolution", "op": "in", "value": ["Done"]})),
        denominator_json=json.dumps(_spec({"attr": "status", "op": "not_in", "value": ["Backlog"]})),
    )
    db_session.add_all([
        metric,
        AppSetting(key="kpi_excluded_statuses", value=json.dumps(["Отменено"], ensure_ascii=False)),
        AppSetting(key="team_desk_config", value=json.dumps({
            "status_groups": {"todo": ["Backlog", "К выполнению"], "done": ["ГОТОВО", "Отменено"]},
            "queue_statuses": ["К выполнению", "В РАБОТЕ"],
            "hidden_statuses": ["Backlog"],
            "thresholds": {"wip_limit": 3},
        }, ensure_ascii=False)),
        AppSetting(key="jira_planned_qa_hours_field_id", value=json.dumps(
            [{"field_id": "customfield_10845", "kind": "alt", "name": "QA spent (ч)"}],
            ensure_ascii=False)),
    ])
    db_session.commit()

    for _ in range(2):  # второй прогон ничего не меняет
        m._upgrade(db_session.connection())
        db_session.commit()

    db_session.expire_all()
    got = db_session.get(KpiMetric, metric.id)
    assert json.loads(got.numerator_json)["conditions"][0]["value"] == ["Готово"]
    assert json.loads(got.denominator_json)["conditions"][0]["value"] == [
        "Backlog", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    settings = {s.key: s.value for s in db_session.query(AppSetting)}
    assert json.loads(settings["kpi_excluded_statuses"]) == ["Отменено", "Won't Do"]
    desk = json.loads(settings["team_desk_config"])
    # Добавки идут в порядке источников: Отменено, К выполнению, Backlog, Приостановлено.
    assert desk["status_groups"]["todo"] == [
        "Backlog", "К выполнению", "Сделать", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    assert desk["status_groups"]["done"] == ["ГОТОВО", "Отменено", "Won't Do"]
    assert desk["queue_statuses"] == ["К выполнению", "В РАБОТЕ", "Сделать"]
    assert desk["hidden_statuses"] == ["Backlog", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    assert desk["thresholds"] == {"wip_limit": 3}
    assert json.loads(settings["jira_planned_qa_hours_field_id"])[0]["field_id"] == "customfield_11042"


def test_upgrade_on_empty_database(db_session):
    """Новая установка: настроек нет — миграция ничего не создаёт и не падает."""
    m = _module()
    m._upgrade(db_session.connection())
    db_session.commit()
    assert db_session.query(AppSetting).count() == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_migration_jr01_jira_dc_value_fixes.py -q -p no:cacheprovider`
Expected: FAIL — файла миграции нет.

- [ ] **Step 4: Write the migration** `alembic/versions/jr01_jira_dc_value_fixes.py`:

```python
"""jira_dc_value_fixes

Revision ID: jr01_jira_dc_value_fixes
Revises: em01_employee_account_aliases
Create Date: 2026-10-21

После переезда на Jira DC сменились значения, на которые ссылаются сохранённые
настройки: резолюция Done → «Готово»; статусы Отменено → Won't Do, К выполнению →
Сделать, Backlog → IDEA BACKLOG (+ APPROVED IDEA BACKLOG), Приостановлено → Hold;
вторым полем плановых часов QA при переезде выбрано «QA spent (ч)» — факт, а не
оценка. Правится только там, где найдено старое значение; повторный запуск ничего
не меняет. Самодостаточна: код приложения не импортирует.

Откат ничего не возвращает: старых значений в новой Jira нет, возвращать их в
настройки — снова сломать KPI и стол тимлида.
"""
import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "jr01_jira_dc_value_fixes"
down_revision: Union[str, None] = "em01_employee_account_aliases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RESOLUTION_RENAMES = {"Done": "Готово"}
BACKLOG_STATUSES = {"Backlog", "Бэклог"}
BACKLOG_ADDITIONS = ["IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
# Рядом со старым статусом (ключ) добавляются новые (значение).
DESK_ADDITIONS = {
    "Отменено": ["Won't Do"],
    "К выполнению": ["Сделать"],
    "Backlog": ["IDEA BACKLOG", "APPROVED IDEA BACKLOG"],
    "Приостановлено": ["Hold"],
}
DESK_LISTS = ("queue_statuses", "wip_statuses", "hidden_statuses")
EXCLUDED_ADDITIONS = {"Отменено": ["Won't Do"]}
QA_SPENT_FIELD = "customfield_10845"
QA_ESTIMATE_FIELD = "customfield_11042"
QA_ESTIMATE_NAME = "Оценка QA (ч)"

_settings = sa.table("app_settings", sa.column("key", sa.String), sa.column("value", sa.Text))
_metrics = sa.table(
    "kpi_metrics",
    sa.column("id", sa.String),
    sa.column("numerator_json", sa.Text),
    sa.column("denominator_json", sa.Text),
)


def _dedupe(values: list) -> list:
    out: list = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _with_additions(values: list, additions: dict[str, list[str]]) -> list:
    out = list(values)
    for source, extra in additions.items():
        if source in out:
            out.extend(v for v in extra if v not in out)
    return out


def fix_status_list(values: list) -> list:
    return _with_additions(values, DESK_ADDITIONS)


def fix_metric_spec(spec: dict) -> bool:
    """Условия метрики KPI: Done → Готово, к исключению бэклога — новые бэклоги."""
    changed = False
    for cond in spec.get("conditions") or []:
        if not isinstance(cond, dict):
            continue
        attr, value = cond.get("attr"), cond.get("value")
        if attr == "resolution":
            if isinstance(value, list):
                new = _dedupe([RESOLUTION_RENAMES.get(v, v) for v in value])
            else:
                new = RESOLUTION_RENAMES.get(value, value)
            if new != value:
                cond["value"] = new
                changed = True
        elif (
            attr == "status" and cond.get("op") == "not_in"
            and isinstance(value, list) and BACKLOG_STATUSES & set(value)
        ):
            new = value + [s for s in BACKLOG_ADDITIONS if s not in value]
            if new != value:
                cond["value"] = new
                changed = True
    return changed


def fix_desk_config(cfg: dict) -> bool:
    changed = False
    groups = cfg.get("status_groups")
    if isinstance(groups, dict):
        for name, values in groups.items():
            if isinstance(values, list):
                new = fix_status_list(values)
                if new != values:
                    groups[name] = new
                    changed = True
    for key in DESK_LISTS:
        values = cfg.get(key)
        if isinstance(values, list):
            new = fix_status_list(values)
            if new != values:
                cfg[key] = new
                changed = True
    return changed


def fix_qa_setting(raw: str) -> str:
    """Поле плановых часов QA: «QA spent (ч)» → «Оценка QA (ч)» (список полей или одно поле)."""
    if not raw:
        return raw
    if raw.strip() == QA_SPENT_FIELD:
        return QA_ESTIMATE_FIELD
    try:
        items = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(items, list):
        return raw
    changed = False
    for item in items:
        if isinstance(item, dict) and item.get("field_id") == QA_SPENT_FIELD:
            item["field_id"] = QA_ESTIMATE_FIELD
            item["name"] = QA_ESTIMATE_NAME
            changed = True
    return json.dumps(items, ensure_ascii=False) if changed else raw


def _load_json(raw: Any) -> Any:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _upgrade(conn: Any) -> None:
    for row in conn.execute(sa.select(_metrics)).mappings().all():
        updates = {}
        for col in ("numerator_json", "denominator_json"):
            spec = _load_json(row[col])
            if isinstance(spec, dict) and fix_metric_spec(spec):
                updates[col] = json.dumps(spec, ensure_ascii=False)
        if updates:
            conn.execute(_metrics.update().where(_metrics.c.id == row["id"]).values(**updates))

    settings = {key: value for key, value in conn.execute(sa.select(_settings.c.key, _settings.c.value))}

    def save(key: str, value: str) -> None:
        conn.execute(_settings.update().where(_settings.c.key == key).values(value=value))

    excluded = _load_json(settings.get("kpi_excluded_statuses"))
    if isinstance(excluded, list):
        new = _with_additions(excluded, EXCLUDED_ADDITIONS)
        if new != excluded:
            save("kpi_excluded_statuses", json.dumps(new, ensure_ascii=False))

    desk = _load_json(settings.get("team_desk_config"))
    if isinstance(desk, dict) and fix_desk_config(desk):
        save("team_desk_config", json.dumps(desk, ensure_ascii=False))

    qa_raw = settings.get("jira_planned_qa_hours_field_id")
    if qa_raw:
        new_qa = fix_qa_setting(qa_raw)
        if new_qa != qa_raw:
            save("jira_planned_qa_hours_field_id", new_qa)


def upgrade() -> None:
    _upgrade(op.get_bind())


def downgrade() -> None:
    pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_migration_jr01_jira_dc_value_fixes.py -q -p no:cacheprovider`
Expected: 6 passed

- [ ] **Step 6: Run the migration chain tests**

Run: `py -3.10 -m pytest tests -q -p no:cacheprovider -k "migration or alembic or upgrade"`
Expected: all passed; `py -3.10 -m alembic heads` → `jr01_jira_dc_value_fixes (head)`.

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/jr01_jira_dc_value_fixes.py tests/test_migration_jr01_jira_dc_value_fixes.py
git commit -m "fix(migration): настройки KPI, стола и поля QA — значения Jira DC"
```

---

### Task 5: Заметка, прогон на копии прода, полный прогон (контроллер)

**Files:**
- Modify: `release_notes/drafts.json` (только дописать в конец `notes`, сохранить переводы строк файла)

- [ ] **Step 1: Release note** — дописать две заметки:

```json
{"type": "fix", "section": "kpi", "title": "KPI снова находит закрытые задачи после переезда на новую Jira",
 "description": "В новой Jira резолюция «Done» называется «Готово», отмена — «Won't Do», бэклог — «IDEA BACKLOG». Метрики качества, Cycle Time, сроков и оценки заказчика не находили ни одной задачи, а отменённые задачи попадали в расчёт. Настройки KPI исправлены автоматически; KPI за прошлые кварталы пересчитаются по новым значениям.", "sort_order": 0},
{"type": "fix", "section": "team-desk", "title": "Стол тимлида знает статусы новой Jira; план тестирования — по оценке",
 "description": "«Сделать» попадает в очередь как «К выполнению», «Won't Do» — в завершённые, «IDEA BACKLOG» скрыт как бэклог, «Hold» — пауза. Отменённые задачи снова уходят в архив сами. Плановые часы тестирования берутся из «Оценка QA (ч)», а не из потраченных часов: после обновления администратору нужно один раз перезагрузить задачи (Синхронизация → Дополнительно → Задачи). Сводка для руководителя и тематический отчёт снова видят выполненные задачи.", "sort_order": 0}
```

- [ ] **Step 2: Прогон на копии выгрузки прода** — копия `data/prod-20261021/prod.db` → `data/jira_analytics.db` в рабочей папке (с выключенными расписаниями и удалёнными ключами Jira, как в сессии 21.10), `alembic upgrade head`; до и после — условия KPI, `kpi_excluded_statuses`, `team_desk_config`, поле QA; KPI за Q3 и Q4 2026 по командам до/после (через сервис KPI) — разницу показать владельцу.

- [ ] **Step 3: Полный прогон**

Run: `py -3.10 -m pytest tests/ -q -p no:cacheprovider --ignore=tests/api/test_llm.py`
Expected: all passed

- [ ] **Step 4: Commit + push** (проверить ветку и что впереди `origin/main` только свои коммиты; слить в main — `git push origin HEAD:main` после `git rebase origin/main`).
