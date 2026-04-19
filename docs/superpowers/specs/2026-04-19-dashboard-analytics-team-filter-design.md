# Dashboard & Analytics — team filter

**Дата:** 2026-04-19
**Статус:** дизайн утверждён, готов к плану реализации

## Контекст и проблема

`DashboardPage` и `AnalyticsPage` показывают факт трудозатрат по всей организации. Из фильтров есть только даты, сотрудник и проект. PM работает с конкретной командой и хочет быстро ограничить обзор до неё.

Наивная фильтрация «по команде сотрудника» не покрывает реальные сценарии:
- Родительские задачи (эпики) могут не принадлежать целевой команде, но их подзадачи — да.
- Сотрудник может списывать часы на задачи чужих команд.

Следовательно, фильтр должен работать **в двух измерениях** — по команде сотрудника И по команде задачи — с возможностью выбрать одно из них, другое или оба одновременно (объединение).

`CapacityPage` уже имеет собственный team-фильтр, но он client-side (`matchesTeam(employeeId)`) и не покрывает агрегаты без разбивки по сотрудникам. Для аналитики нужна server-side фильтрация.

## Решение

Добавить общий team-фильтр Dashboard+Analytics со сквозным состоянием между двумя страницами, реализовать server-side в `/analytics/*` и `/exports/analytics.*`.

### Область применения

- Фильтр шарится между `/` (Dashboard) и `/analytics` (Analytics): одно состояние, один persisted state.
- Capacity не трогаем — у него свой `CapacityFilterProvider`, отдельное хранилище.
- Backlog, Planning, Sync не трогаем.

### UI

**Компонент `FactFilterBar`** рендерится в той же `Space wrap`-полосе, где уже живут `DateRangeSelect`, Select сотрудника и Select проекта (на обеих страницах). Содержит:

- Мульти-Select команд — options из `useJiraTeams()` плюс опция «Без команды» со значением `__none__` (константа, такая же идея как `NO_TEAM_VALUE` в Capacity).
- Чекбокс «Сотрудники» (default `true`).
- Чекбокс «Задачи» (default `true`).

Поведение:
- Если выбраны команды и обе галочки включены — применяется OR (объединение по обоим измерениям).
- Если выбрана только одна галочка — фильтр применяется только по этому измерению.
- Нельзя снять обе галочки: если пользователь снимает последнюю активную — UI отказывает (галочка остаётся `true`).
- Пустой список команд → фильтр выключен независимо от состояния галочек.

**Провайдер `FactFilterProvider`** оборачивает роуты `/` и `/analytics` в `main.tsx`. Предоставляет контекст:

```ts
type FactFilterCtx = {
  selectedTeams: string[];
  setSelectedTeams: (v: string[]) => void;
  matchEmployees: boolean;
  setMatchEmployees: (v: boolean) => void;
  matchIssues: boolean;
  setMatchIssues: (v: boolean) => void;
  hydrated: boolean;
  // derived query params for API calls
  queryParams: { teams?: string; match_employees?: boolean; match_issues?: boolean };
};
```

**Persistence** — три AppSetting ключа:
- `ui_fact_filter_teams` — CSV (`"Core,Mobile"` или `"__none__"` или `""`)
- `ui_fact_filter_scope_employees` — `"1"` | `"0"`
- `ui_fact_filter_scope_issues` — `"1"` | `"0"`

Дефолты при первом открытии: пустой список команд, обе галочки on.

**Использование в хуках**. Все `useHoursBy*` / `useContextSwitching` хуки читают `queryParams` из `useFactFilter()` и добавляют их в querykey и запрос. Для Dashboard и Analytics хуки вызываются одинаково.

### API

Расширить все 5 аналитических эндпоинтов тремя query-параметрами:

```python
teams: Optional[str] = Query(None)         # CSV, пусто = фильтр выключен
match_employees: bool = Query(True)
match_issues: bool = Query(True)
```

Эндпоинты:
- `GET /analytics/hours/by-employee`
- `GET /analytics/hours/by-project`
- `GET /analytics/hours/by-category`
- `GET /analytics/hours/by-period`
- `GET /analytics/context-switching`

А также экспорты, чтобы экспорт соответствовал видимому фильтру:
- `GET /exports/analytics.xlsx`
- `GET /exports/analytics.pdf`

Эти два принимают те же параметры и пробрасывают в `AnalyticsService`.

### Сервисная логика

В `AnalyticsService` добавить хелпер:

```python
def _apply_team_filter(
    self,
    query,
    teams: Optional[list[str]],
    match_employees: bool,
    match_issues: bool,
    require_issue_join: bool,  # True если query ещё не join'ит Issue
):
    ...
```

Алгоритм:

1. Если `teams` пуст или `not match_employees and not match_issues` — вернуть `query` без изменений.
2. Разделить `teams` на `named_teams` (все кроме `__none__`) и `has_none` (bool).
3. Построить две клаузы:

   **`emp_clause`** (если `match_employees`):
   - `named`: `Worklog.employee_id IN (SELECT et.employee_id FROM employee_teams et WHERE et.team IN (:named_teams))`
   - `none` (если `has_none`): `Worklog.employee_id NOT IN (SELECT et.employee_id FROM employee_teams et)`
   - Итоговая `emp_clause = named_sub OR none_sub` (или одна из них, если только одно).

   **`issue_clause`** (если `match_issues`, и join Issue должен быть в query — см. `require_issue_join`):
   - `named`:
     - `Issue.team IN (:named_teams) OR Issue.participating_teams LIKE '%"X"%' for X in named_teams`
     - LIKE экспрессии строятся через bound параметры, имя команды экранируется от `%`/`_`/`\` и подставляется в паттерн `%"<escaped>"%`. Совпадение на уровне JSON-строки безопасно: список хранится как `["Core","Mobile"]`, кавычки вокруг имени предотвращают префиксные/суффиксные ложные совпадения.
   - `none` (если `has_none`): `Issue.team IS NULL AND (Issue.participating_teams IS NULL OR Issue.participating_teams = '[]')`
   - Итоговая `issue_clause = named OR none` (или одна).

4. Если обе клаузы есть — `final = emp_clause OR issue_clause`.
   Если только одна — `final = <та одна>`.
5. `query.filter(final)`.

**Join Issue** — необходим для `issue_clause`. Для `hours_by_period` join Issue сейчас условный (только при `project_key`). Добавить безусловный join, когда `match_issues and teams`.

**Для context_switching**: там уже `join(Issue)` всегда. Добавить логику фильтра по задачам/сотрудникам через тот же хелпер.

### Экспорты

`downloadAnalyticsXlsx(start, end)` и `downloadAnalyticsPdf(start, end)` в `frontend/src/api/exports.ts` расширяются — принимают 3 параметра team-фильтра и строят URL с ними.

Компоненты Dashboard и Analytics, которые дергают экспорты, берут параметры из `useFactFilter()`.

Backend `app/api/endpoints/exports.py` принимает те же query params и пробрасывает в `AnalyticsService` при построении xlsx/pdf.

### Взаимодействие с существующими фильтрами

`employee_id` и `project_key` остаются и продолжают работать через AND с team-фильтром. То есть если выбрано: team=`Core`, employee_id=`uuid-X`, match_employees=true, match_issues=true — SQL:
```
WHERE (worklog in team-filter) AND Worklog.employee_id = uuid-X AND (Project.key = ... если задан)
```

### Что НЕ делаем

- Не переиспользуем `CapacityFilterProvider`: его `matchesTeam` client-side-only, и он сидит только на Capacity. Новый провайдер — отдельный, со своим хранилищем.
- Не добавляем team-фильтр на Backlog / Planning / Sync.
- Не объединяем fact-фильтр с Capacity-фильтром (явное решение PM).
- Не индексируем `Issue.participating_teams` отдельно: на локальной базе ~115k issues LIKE-скан приемлем; если станет узким местом — вынесем в отдельный проект нормализации.

## Тесты

**Backend** — новые кейсы в `tests/test_analytics_service.py` (фикстура с 2 сотрудниками в разных командах + 2 задачи с разными team/participating):
- `teams=X, match_employees=True, match_issues=False` — видим только ворклоги авторов из команды X.
- `teams=X, match_employees=False, match_issues=True` — видим только ворклоги на задачах команды X (включая participating).
- `teams=X, match_employees=True, match_issues=True` — объединение.
- `teams=__none__, match_employees=True` — видим только ворклоги сотрудников без команды.
- `teams=__none__, match_issues=True` — видим только ворклоги на задачах без команды.
- `teams=""` — фильтр игнорируется (эквивалент «без фильтра»).
- `match_employees=False, match_issues=False, teams=X` — фильтр игнорируется, как будто выключен.

Кейсы добавить минимум для `hours_by_employee`, `hours_by_project`, `hours_by_category`, `hours_by_period`, `context_switching` (смыслово идентичный `_apply_team_filter`, но по разным агрегатам — нужно убедиться что join Issue подключён там, где надо).

**Endpoint-тесты** в `tests/test_api_*.py` — smoke по одному вызову на каждый эндпоинт с `teams=X&match_employees=true&match_issues=true`, проверить 200 и форму ответа.

**Frontend e2e** — один happy-path в `frontend/e2e/dashboard.spec.ts`: выбрать команду в `FactFilterBar`, убедиться что KPI пересчитываются (как минимум total_hours отличается от «без фильтра»). seeded `data/e2e.db` уже имеет нужный минимум.

**Unit frontend** — по желанию, минимум: тест что нельзя снять обе галочки одновременно.

## Миграции

Не требуется — только чтение существующих полей (`employee_teams`, `Issue.team`, `Issue.participating_teams`).

## Оценка объёма

- Backend: 1 хелпер в `AnalyticsService` + прокидывание параметров в 5 эндпоинтов + 2 экспорта + ~10 тестов.
- Frontend: 1 провайдер + 1 FilterBar-компонент + изменение 2 страниц + правка 5+1 хуков + правка экспорт-API.

Порядок реализации:
1. Backend: хелпер + 5 эндпоинтов + тесты.
2. Backend: экспорты с теми же параметрами.
3. Frontend: провайдер + FilterBar.
4. Frontend: пробросить параметры в хуки и вызовы экспортов.
5. Smoke через Playwright + `py -3.10 -m pytest`.
