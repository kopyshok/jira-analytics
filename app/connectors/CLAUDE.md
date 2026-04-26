# app/connectors — внешние API

httpx (async). Все pydantic-схемы ответов — в [schemas.py](schemas.py).

## JiraClient ([jira_client.py](jira_client.py))

### Issue search

`GET /rest/api/3/search/jql` — старый `GET /search` отдаёт **410 Gone**.

**Pagination cursor-based**, не offset: response содержит `nextPageToken` и `isLast`; `startAt` **игнорируется**. Передача `startAt` в loop = бесконечный re-read page 1. `JiraClient.search_issues` принимает `next_page_token`; `iter_issues` гонит loop через token + `isLast`. `JiraSearchResponseSchema.has_more` доверяет `isLast` сначала, fallback на `nextPageToken` / `total` / length.

Pydantic response schema **требует** `summary` / `issuetype` / `status` / `project` — любой call к `search_issues` должен включать их в `fields=` даже при probe existence.

### Field discovery

`get_field_configured_options(field_id)` — **primary source** distinct values select-поля — fetches `/field/{id}/context` + `/field/{ctxId}/option` (fast, complete, 46 teams vs. 22 через scan).

`get_field_distinct_values` — **fallback на JQL scan** (limited 1000 recent issues, miss teams на stale issues) если контексты недоступны.

`/sync/jira-teams` возвращает sorted union по обоим configured team fields.

### Team filter на `/sync/jira-projects`

Team filter не может быть single global JQL (`ORDER BY project` + 1000-issue cap группирует всё под первым проектом). Решение: iterate projects, probe каждый `project = "K" AND (field1 = X OR field2 = X)` через `search_issues(max_results=1)`. Cost ~200ms × N projects, но корректно.

### Rate limiting

100ms delay между requests + exponential backoff на HTTP 429. Batch size: 100 issues per request.

### Tenant

```
Cloud ID: 604dc198-0f39-4cc9-bfbf-0a7cfdddd286
Base URL: https://itgri.atlassian.net
```

## ProductionCalendarClient ([production_calendar_client.py](production_calendar_client.py))

Тянет официальный RU производственный календарь. Используется `POST /production-calendar/sync?year=N&overwrite_manual=false`.

## Credentials resolution

AppSetting (DB) → `.env` fallback. UI пишет `jira_email` / `jira_api_token` / `jira_base_url` в AppSetting через `PUT /settings/jira`; `.env` подключается только для dev/CI когда DB пуста.
