# app/connectors — внешние API

httpx (async). Все pydantic-схемы ответов — в [schemas.py](schemas.py).

## JiraClient ([jira_client.py](jira_client.py)) — Jira Data Center

Jira DC 11.3.7, REST API **v2** (`API_PREFIX = "/rest/api/2"`), вход `Authorization: Bearer <персональный токен>`. Облако не поддерживается (переезд — `docs/superpowers/specs/2026-10-14-jira-dc-migration-design.md`).

### Пользователи

У пользователя DC нет `accountId`. `key` (`JIRAUSER12223`, не меняется при переименовании) → `JiraUserSchema.jira_account_id` → `Employee.jira_account_id`. `name` (логин, `Lebedev_A_A`) → `JiraUserSchema.name` → `Employee.jira_username`, синк обновляет его при каждой встрече. Почта не идентификатор (в DC другая, чем была в облаке). JQL `worklogAuthor` принимает логин, не `key`. Поиск — `GET /user/search?username=` (логин, имя, почта; только активные).

### JQL-помощники ([jql.py](jql.py))

Любое значение, попадающее в JQL, — через `jql_quote` (экранирует сначала `\`, затем `"`). Ссылка на кастомное поле — `jql_field_ref(id)` (`customfield_11092` → `cf[11092]`); номер поля — `custom_field_number(id)`. Строить JQL конкатенацией сырых значений нельзя.

### Поиск задач

`GET /search` со смещением: `startAt` / `maxResults` / `total`; `iter_issues` листает до `total`. **Если в JQL нет сортировки, клиент добавляет `ORDER BY key ASC`**: при смещении сортировка по изменяемому полю (`updated`) теряет задачи, изменённые во время обхода.

**Строгий режим по умолчанию** (`lenient=False`): плохой JQL → `JiraClientError` с текстом `errorMessages` от Jira. Мягкий режим (`lenient=True`, `validateQuery=warn`, предупреждения пишутся в лог) — только там, где часть ключей может не существовать: обновление по списку ключей (`key in (...)`) и корзина B синка. Остальные запросы строгие, иначе ошибка в запросе молча даёт пустую выдачу.

Pydantic-схема ответа **требует** `summary` / `issuetype` / `status` / `project` — любой `search_issues` должен их запрашивать. Сверка ключей без схемы — `iter_issue_keys(jql)` (`fields=key`, страницы по 1000).

`expand=changelog` кладёт историю в `JiraIssueSchema.changelog`; в задаче остаются **только элементы смены статуса** (остальное отбрасывается при разборе). Сколько записей истории DC отдаёт в поиске, не проверено — синк дочитывает неполную (`total` > записей) через `get_issue_changelog(key)` (`GET /issue/{key}?expand=changelog`). Разбор — [changelog.py](changelog.py): даты с часовым поясом (aware). Пустой результат полной выборки истории не затирает уже сохранённые `status_changed_at` и дни паузы. Очередь задач в синке для путей с историей ограничена (`maxsize` 500).

### Чем DC отличается от облака

- `statuscategorychangedate` нет → `Issue.status_changed_at` = последняя смена **категории** статуса по истории (категории — `GET /status`, `statusCategory.key`), иначе дата создания.
- Описание и комментарии — wiki-строка, не ADF (схемы пропускают строку как есть).
- Иерархия: подзадача → `fields.parent`; задача → эпик — «Ссылка на эпик» (`gh-epic-link`); эпик → инициатива — «Parent Link» (`jpo-custom-field-parent`). Значения — строка-ключ. id полей синк находит по типу и хранит в AppSetting `jira_epic_link_field_id` / `jira_parent_link_field_id` (как `jira_sprint_field_id`).
- Спринт — список строк `com.atlassian.greenhopper.service.sprint.Sprint@…[id=…,name=…,state=ACTIVE,…]`, разбирает `sync_service._extract_sprints`.
- Время ворклогов и комментариев хранится как **фиксированное московское «настенное» время (UTC+3)** — константа в `jira_client.py`, как было в облаке; перевод в `sync_service._drop_tz`. Границы жёсткой перезагрузки считаются по Москве; «голый» (без пояса) `since` трактуется как московское. Остальные времена (`created` и т. п.) приходят в UTC (`+0000`).
- Проекты — `GET /project` (массив целиком).

### Ворклоги

`iter_worklogs_updated_since(since_ms)`: `GET /worklog/updated` (`lastPage` / `until`) → `POST /worklog/list` пачками по 1000, потоком. `since_ms=0` — все ворклоги Jira. Удалённые — `iter_deleted_worklog_ids`. Оба итератора id (`/worklog/updated`, `/worklog/deleted`) используют общий `_iter_since_ids`: если страница не последняя, а `until` отсутствует или не двигается, итератор **падает с ошибкой**, а не зацикливается или молча обрывается.

### Опции полей

`get_field_configured_options(field_id)` → `GET /customFields/{n}/options` (включённые значения). Листается по `page`, запрос с `useAllContexts=true`; есть предел числа страниц — при его достижении, ошибке или не кастомном поле возвращается `[]`. Тогда `get_field_distinct_values` сканирует задачи JQL `cf[N] is not EMPTY` (до 1000 свежих). Поле в JQL — `jql_field_ref(id)`.

### Доступность поля на карточке

`get_editable_field_ids(issue_key)` → `GET /issue/{key}/editmeta`, множество id
полей карточки. Нужен, чтобы отличить живое значение кастомного поля от
оставшегося после переноса задачи в другой проект: Jira такие значения хранит и
отдаёт в `fields`, хотя поля на экранах нового проекта нет. Ответ зависит от
проекта, типа задачи и прав — см. `app/services/stale_field_cleanup.py`.

### Team filter на `/sync/jira-projects`

Team filter не может быть single global JQL (`ORDER BY project` + 1000-issue cap группирует всё под первым проектом). Решение: iterate projects, probe каждый `project = "K" AND (cf[N] = X OR cf[M] = X)` через `search_issues(max_results=1)`. Cost ~200ms × N projects, но корректно.

### Rate limiting и повторы

Пауза только на повторе (экспонента от 100 мс) + отдельная ветка 429 (`Retry-After`; нечисловое значение → задержка по умолчанию). Ответы 4xx, кроме 429, **не повторяются** — сразу ошибка. Лимитов на сервере нет (ответ админа 2026-10-14).

### Сервер

```
Base URL: https://jira.example.ru   (только из внутренней сети)
Версия:   11.3.7, REST API v2
```

## ConfluenceClient ([confluence_client.py](confluence_client.py)) — Confluence Data Center

Свой сервер: AppSetting `confluence_base_url` + `confluence_api_token`, вход Bearer. Пути без `/wiki`: `/rest/api/content/{id}?expand=body.storage`, `/rest/api/user/current`, поиск по названию `/rest/api/content?spaceKey=&title=`. `resolve_page_id(url)`: прямой id (`viewpage.action?pageId=` / `/pages/N`), короткая `/x/…` (переадресация), `/display/<пространство>/<название>` (поиск). Ссылки в описаниях задач ищет `confluence_service.extract_confluence_urls` по адресу из настроек (хост сравнивается без учёта регистра, после хоста — граница пути); описание — wiki-разметка, `|` и `]` завершают адрес.

Редиректы клиент **сам не выполняет** (токен не уходит на чужой адрес); короткие ссылки разбираются вручную. Недоступный или не настроенный Confluence не роняет синк — раздел деградирует (пусто), ошибки пользователю — по-русски, без технических деталей.

## ProductionCalendarClient ([production_calendar_client.py](production_calendar_client.py))

Тянет официальный RU производственный календарь. Используется `POST /production-calendar/sync?year=N&overwrite_manual=false`.

## Credentials resolution

AppSetting (DB) → `.env` fallback. UI пишет `jira_base_url` / `jira_api_token` через `PUT /settings/jira` и `confluence_base_url` / `confluence_api_token` через `PUT /settings/confluence`; `.env` (`JIRA_BASE_URL`, `JIRA_API_TOKEN`) — только для dev/CI, когда база пуста. Проверка Jira с пустым токеном → 400. `GET /ui-config/jira-base-url` отдаёт адрес без хвостового `/`. Старая строка `jira_email` в базе ни на что не влияет.

## Блокировка синка

Пока AppSetting `jira_migration_state = pending`, любой пишущий синк отказывает (`SyncBlockedError` → HTTP 409, проверка в конструкторе `SyncService` и в начале пишущих эндпоинтов). **Закрыта по умолчанию:** разрешено, только если строки нет или в ней ровно `done`; любое другое значение блокирует. Сам клиент не ограничен: чтения для переезда и настроек работают. См. `app/services/jira_migration/state.py`.
