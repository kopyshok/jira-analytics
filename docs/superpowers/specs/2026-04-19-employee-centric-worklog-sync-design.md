# Employee-centric worklog sync + team membership

**Дата:** 2026-04-19
**Контекст:** PM обнаружил, что если сотрудник залогировал время в чужой задаче (проект вне scope, тип не в БД) — эти часы никогда не попадут в анализ. Нужно заходить от сотрудника, а не только от задачи.

---

## 1. Проблема

Текущая цепочка синхронизации **issue-centric**:

```
ScopeProjects → sync_issues → sync_worklogs (по локальным Issue)
```

Последствия:
- **Потеря ворклогов вне scope.** Фокеева помогает соседней команде и логирует на их задачу (проект не в scope). Задача никогда не попадает в `Issue`, её ворклоги — тем более.
- **Back-dated ворклоги теряются в reload.** JQL `worklogDate >= since` использует `worklog.started`. Сотрудник 19.04 создал запись с `started = 10.04`, reload с `since = 15.04` его не увидит (10.04 < 15.04).
- **Reload разрушителен.** Текущая «Перезагрузить с даты» удаляет все worklog с `started >= since` и перечитывает. Это правильно для «синхронизировать удаления», но не для повседневного обновления.

`Employee.team` уже существует (String, single value), но не масштабируется на сценарий «менеджер с несколькими подкомандами» и на сотрудников, работающих на стыке.

---

## 2. Цели

1. **Сценарий A «все ворклоги задач команды»** — видим работу всех авторов (в т.ч. чужих) на задачах с `Issue.team ∈ выбранные`. Уже частично работает, дополняется back-dated upsert'ом.
2. **Сценарий B «все ворклоги сотрудников команды»** — видим работу наших людей **где угодно**, включая задачи вне scope. Требует employee-centric синк.
3. **Безопасный reload** — повседневное обновление не удаляет данные. Полная перезагрузка — отдельная кнопка с warning'ом.
4. **Поддержка мульти-команд** — сотрудник числится в нескольких командах; менеджер охватывает несколько команд одним фильтром.

---

## 3. Изменения модели данных

### 3.1 Новая таблица `employee_teams` (M:N)

```
employee_teams
  id              String(36) PK
  employee_id     String(36) FK → employees.id (ON DELETE CASCADE)
  team            String(100) — название команды (как в Jira)
  is_primary      Boolean default false — основная команда (для Capacity-группировки)
  created_at      DateTime
  UNIQUE (employee_id, team)
  INDEX (team), INDEX (employee_id)
```

**Почему M:N, а не CSV в строке:** запросы типа «все сотрудники команды X» должны использовать индекс (`WHERE team = 'X'`); CSV приводит к `LIKE '%X%'` с коллизиями.

**Почему `is_primary`:** Capacity-агрегации (план/факт часов, % загрузки) не могут дважды считать одного человека. Primary team — единственная для capacity-расчётов. Вторичные — только для фильтров в ворклогах и аналитике.

Инвариант: у сотрудника ровно 0 или 1 строка с `is_primary=true`. Enforce на сервисе (не в БД — SQLite не умеет partial unique).

### 3.2 Legacy `Employee.team`

Мигрируем данные при применении migration:
```
INSERT INTO employee_teams (employee_id, team, is_primary)
SELECT id, team, true FROM employees WHERE team IS NOT NULL;
```

Колонку `Employee.team` **оставляем** как derived view: обновляется синхронно с primary membership (через сервис). Это сохраняет совместимость с существующими запросами/аналитикой до полного рефакторинга (он не в скоупе этой задачи). В миграции пишем комментарий «derived, источник истины — employee_teams».

Альтернатива (отброшена): удалить колонку сразу и переписать все использования. Слишком широкий blast radius для одной задачи.

### 3.3 Новый флаг `Issue.out_of_scope`

```
issues.out_of_scope  Boolean default false, index
```

Задача, обнаруженная через Ведро B (worklogAuthor-sync), добавляется с `out_of_scope=true`. Значение:
- **Не** попадает в CategoryConfigTab (дерево задач) — в запросе `/issues/tree` фильтруется по `out_of_scope=false`.
- **Не** попадает в Backlog / Planning / Analytics по задачам.
- Её **ворклоги видны** в отчётах по ворклогам (Activity, Capacity breakdown) с пометкой «вне scope».
- Если потом PM вручную добавит проект задачи в scope и запустит обычный sync — `out_of_scope` сбросится в false.

---

## 4. Стратегия синхронизации

### 4.1 Два независимых прохода

```
Ведро A (issue-centric, есть сегодня):
  scope_projects → sync_issues → для каждого Issue: iter_worklogs → upsert

Ведро B (employee-centric, новое):
  Для каждого Employee с membership в employee_teams:
    JQL: worklogAuthor = "accountId" AND updated >= since
    Для каждого найденного Issue:
      если локально нет → создать Issue(out_of_scope=true), минимальные поля
      iter_worklogs → upsert, фильтр по автору = этот сотрудник
```

### 4.2 Back-dated catching — JQL `updated >= since`

Заменяем `worklogDate >= since` на `updated >= since` во всех reload/update сценариях:

| Событие | `issue.updated` двигается? | Ловит JQL `updated >=`? |
|---|---|---|
| Новый worklog (текущая дата started) | ✅ | ✅ |
| Новый worklog (back-dated started) | ✅ | ✅ |
| Правка started existing worklog'а | ✅ | ✅ |
| Удаление worklog'а | ✅ | ⚠ issue найдётся, но ворклога в ответе нет — локальный не удалится (для этого полная перезагрузка) |
| Правка статуса / коммент / прочее | ✅ | ✅ (no-op при upsert ворклогов) |

Цена — больше issue в JQL-ответе, но на каждом мы всё равно берём только ворклоги, лишняя работа минимальна.

### 4.3 Employee-centric авто-ингест задач

При обнаружении ворклога на незнакомой задаче:
1. `GET /rest/api/3/issue/{key}?fields=summary,issuetype,status,project,<team-fields>` — один запрос.
2. Если проект нет в локальной `projects` — создать Project (без scope).
3. Создать Issue с `out_of_scope=true`, минимальные поля.
4. Upsert worklog.

Батчинг: issue'и, полученные из JQL, сразу приходят с fields — второго запроса не нужно. Запрос #1 выше относится только к случаю, если JQL вернул только issue-id без полей (не наш случай, мы всегда просим fields).

### 4.4 Разделение кнопок

| Кнопка (UI) | Endpoint | JQL | Действия |
|---|---|---|---|
| **«Обновить ворклоги с даты»** (новая логика) | `POST /sync/worklogs/update/stream` (новый) | `updated >= since` + `worklogAuthor in (...) AND updated >= since` | Upsert. Без удаления. Ведро A + Ведро B (если включено). |
| **«Полная перезагрузка (удалить и перечитать)»** (существующая логика) | `POST /sync/worklogs/reload/stream` (есть) | `worklogDate >= since` | DELETE + re-insert. Под `Popconfirm` с красным предупреждением. |

Обе — SSE-прогресс (паттерн уже внедрён в прошлой задаче).

---

## 5. API

### 5.1 Новый endpoint — `POST /sync/worklogs/update/stream`

```json
Request:
{
  "since": "2026-04-15",
  "teams": ["Команда А", "Команда B"]   // опционально, включает Ведро B по primary+secondary membership
}

SSE events:
data: {"type":"progress","bucket":"A","issues_scanned":N,"worklogs_upserted":M,"current_key":"PRJ-1"}
data: {"type":"progress","bucket":"B","employee_id":"...","issues_scanned":N,"worklogs_upserted":M,"issues_out_of_scope_created":K}
data: {"type":"done","total_issues_scanned":...,"total_worklogs_upserted":...,"total_out_of_scope_created":...}
```

Реализация: `SyncService.update_worklogs_since(since, teams=None, on_progress=None)` — новый метод. Не трогает `sync_state.last_sync` (как и reload сегодня — это не курсорный sync).

### 5.2 CRUD `employee_teams`

| Method | Path | Назначение |
|---|---|---|
| `GET /employees/{id}/teams` | Список команд сотрудника | |
| `PUT /employees/{id}/teams` | body `{teams: [{team, is_primary}], primary?: string}` — заменить весь набор | |
| `POST /employees/{id}/teams` | body `{team, is_primary?}` — добавить одну | |
| `DELETE /employees/{id}/teams/{team}` | Убрать одну | |
| `PUT /employees/{id}/teams/primary` | body `{team}` — поменять primary | |

`PUT /employees/{id}/team` (текущий single-value endpoint) → оставляем как совместимую обёртку: выставляет primary, стирает остальные. Скрыть из OpenAPI тегом `deprecated=true`.

### 5.3 Bulk endpoint (для UI)

`GET /employees?with_teams=true` — включает в ответ `teams: [{team, is_primary}]`, чтобы TeamTab рендерил за один запрос.

---

## 6. UI

### 6.1 `CapacityPage → TeamTab`

**Сейчас:** один Select на строку сотрудника, значение — `Employee.team`.

**Станет:**
- Select становится **multiple** — набор команд сотрудника.
- Звёздочка рядом со значением = primary (кнопка «сделать основной» в dropdown-item).
- Визуальная группировка осталась по primary (capacity-суммы считаются как сейчас).
- При работе фильтра «выбранные команды» сотрудник виден в **каждой** выбранной команде, в которой он состоит. Суммы часов дедуплицируются по `employee_id` (один человек = одна ячейка часов, независимо от того, скольких команд вы фильтруете).

### 6.2 `SyncPage → SyncControls` (раздел «Синхронизация»)

Текущий блок ворклогов заменяется:

```
[DatePicker] [Обновить ворклоги с даты]   ← новая, безопасная
             [Включить выбранные команды (N)]  ← чекбокс рядом, активен если selectedTeams.length > 0
[ ⚠ Полная перезагрузка (удалить и перечитать) ] ← danger Popconfirm
```

Оба — прогресс-бар SSE с счётчиками (как у reload).

«Включить выбранные команды» читает `selectedTeams` из `ui_teams_categories` (уже персистится) — единый источник команд в приложении.

### 6.3 Индикация `out_of_scope`

- Analytics / Capacity breakdown: колонка / тег «Вне scope» на задачах с `out_of_scope=true`.
- Дерево задач (CategoryConfigTab): **не показывает** out_of_scope — их там бизнес-логикой не должно быть.

---

## 7. Масштабирование и production

### 7.1 Нагрузка на Jira при Ведре B

Худший случай: 50 сотрудников × JQL `worklogAuthor = X AND updated >= since`. Jira rate-limit 100 req/sec на tenant, но с курсорной пагинацией каждый sync может требовать 5-10 страниц. С уже имеющимся 100ms delay + exponential backoff на 429 — безопасно для single-user. Для мульти-пользовательского продуктива добавим **shared rate-limiter** (semaphore на уровне JiraClient factory) при переходе на multi-tenant. Сейчас он не нужен.

### 7.2 Дедупликация

Issue.jira_issue_id — unique. Два параллельных прохода (A и B) могут найти одну и ту же задачу. Upsert by id — не создаст дубль. Флаг `out_of_scope` не переписывается с `false → true` (если задача уже есть в scope, Ведро B не «выталкивает» её).

### 7.3 Миграции

Один Alembic revision:
1. `CREATE TABLE employee_teams`
2. `ALTER TABLE issues ADD COLUMN out_of_scope BOOLEAN DEFAULT FALSE NOT NULL`
3. `CREATE INDEX ix_issues_out_of_scope ON issues(out_of_scope)`
4. Data migration: перенос `employees.team` → `employee_teams(is_primary=true)`.

Downgrade: drop column, drop table. Данные M:N при downgrade теряются — допустимо для dev/early-prod.

### 7.4 Многопользовательский задел

Для продуктива (несколько PM одновременно) критично:
- Endpoint'ы `employee_teams` — idempotent PUT/DELETE, безопасны при гонке.
- SSE-sync'и уже cancel-safe.
- **НЕ в этой задаче:** изоляция по пользователям (`user_id` scope на scope_projects, category_overrides и т.п.) — это отдельная масштабная работа. Флагируем как follow-up.

---

## 8. Тесты

### Backend
- `test_employee_teams_crud.py` — CRUD endpoint'ы, primary-инвариант.
- `test_sync_service_bucket_b.py` — Ведро B:
  - `worklogAuthor`-JQL вызывается для каждого сотрудника команды
  - out_of_scope Issue создаются
  - existing Issue не перезаписывают `out_of_scope=true` на false
  - upsert не создаёт дублей при повторном прогоне
- `test_sync_service_back_dated.py` — JQL `updated >= since` ловит back-dated:
  - мок возвращает issue с `updated=2026-04-19`, `worklog.started=2026-04-10`
  - при reload с `since=2026-04-15` ворклог попадает в БД
- `test_sync_update_endpoint.py` — SSE-стрим нового endpoint'а.

### Frontend
- Existing Playwright e2e остаётся зелёным.
- Новый e2e на CapacityPage: назначение multi-team, пометка primary.

---

## 9. Follow-ups (не в скоупе этой задачи)

- Удаление deprecated `Employee.team` колонки после стабилизации.
- User-level изоляция для multi-PM продуктива.
- UI «Ворклоги вне scope» — сводный отчёт по `out_of_scope=true` задачам.
- Авто-определение primary team при массовом импорте.

---

## 10. Open questions

Ни одного — все решения выше приняты. На реализацию идём через writing-plans.
