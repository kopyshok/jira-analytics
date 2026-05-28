# Инструкция сисадмину — миграция SQLite → PostgreSQL

**Дата снимка:** 2026-05-28
**Файл бэкапа:** `jira_analytics_cutover.db` (SQLite, ~478 МБ)
**Целостность:** `pragma integrity_check = ok`

## Содержимое снимка (для сверки после миграции)

| Таблица | Строк |
|---|---:|
| users | 4 |
| projects | 7 |
| employees | 651 |
| planning_scenarios | 2 |
| backlog_items | 57 |
| issues | 121 335 |
| worklogs | 84 648 |
| category_mappings | 240 532 |

## Что делает миграция

Скрипт `scripts/migrate_to_postgres.py` копирует все таблицы из SQLite-снимка в PostgreSQL в порядке FK-зависимостей. UUID-ключи сохраняются (нельзя re-syncать issues из Jira — это сломает FK сценариев/беклога/комментариев).

**Не копируется** (регенерируется на новом сервере):
- `sync_state`
- `sync_run`
- `confluence_page_cache`
- `executive_dashboard_snapshots`

Ориентировочный объём: ~450k строк. Время прогона: 5-15 минут на локальном Postgres.

## Предусловия на сервере

1. **Код приложения** в `origin/main`, HEAD = `76ba58a` или новее.
2. **PostgreSQL** запущен, БД создана, пустая (никаких ручных вставок).
3. **venv** backend активирован, зависимости установлены:
   ```bash
   pip install -r requirements.txt
   pip show psycopg2-binary   # должно показать версию; если нет — pip install psycopg2-binary
   ```
4. **Переменная окружения** `DATABASE_URL` указывает на Postgres, например:
   ```
   export DATABASE_URL="postgresql://app:PASS@localhost:5432/jira_analytics_prod"
   ```
5. **Файл бэкапа** положить в директорию приложения, например `/opt/jira-analytics/data/cutover.db` (путь использовать в команде ниже).

## Шаги (все из директории приложения, venv активирован)

### 1. Накатить схему на пустой Postgres

```bash
alembic upgrade head
```

Должно закончиться без ошибок. Проверка:

```bash
psql "$DATABASE_URL" -c "select count(*) from alembic_version;"
# ожидается: 1
```

### 2. Dry-run миграции

```bash
python scripts/migrate_to_postgres.py \
    --source /opt/jira-analytics/data/cutover.db \
    --target "$DATABASE_URL" \
    --dry-run
```

**Ожидаемый вывод:** ~50 таблиц, total порядка 450 000 строк. Если хоть одна ключевая таблица (`users`, `issues`, `worklogs`, `projects`, `employees`) показывает 0 — остановиться и связаться с разработчиком.

### 3. Реальный прогон

```bash
python scripts/migrate_to_postgres.py \
    --source /opt/jira-analytics/data/cutover.db \
    --target "$DATABASE_URL" \
    --force
```

`--force` сделает TRUNCATE целевых таблиц перед копией (для пустой БД — no-op).

**Успешный финал:**

```
Summary:
  Table                                              Source     Copied
  ...
  TOTAL                                              NNNNNN     NNNNNN
```

Source == Copied для каждой таблицы. Любая строка с `MISMATCH` или `FAIL` — стоп, прислать полный вывод разработчику.

### 4. Сверка после копии

```bash
psql "$DATABASE_URL" <<SQL
select 'users' as t, count(*) from users
union all select 'issues', count(*) from issues
union all select 'worklogs', count(*) from worklogs
union all select 'projects', count(*) from projects
union all select 'employees', count(*) from employees
union all select 'planning_scenarios', count(*) from planning_scenarios
union all select 'backlog_items', count(*) from backlog_items
union all select 'category_mappings', count(*) from category_mappings;
SQL
```

Сверить с таблицей в начале документа (могут отличаться на единицы — это норма, если на момент снимка были pending транзакции).

### 5. Запуск backend

```bash
# systemd / supervisor / что используется на сервере
systemctl start jira-analytics-backend   # пример
```

Проверка готовности:

```bash
curl -fsS http://localhost:8000/health/ready
# ожидается: HTTP 200 в течение 60-90 сек после старта
```

### 6. Удалить снимок

```bash
rm /opt/jira-analytics/data/cutover.db
```

## Возможные сбои

| Симптом | Причина | Решение |
|---|---|---|
| `Target schema at revision None, expected HEAD '...'` | Не накатили миграции | Шаг 1: `alembic upgrade head` |
| `Target tables not empty (without --force)` | Postgres БД не пустая | Либо чистая БД, либо `--force` (truncate) |
| `MISMATCH` на одной таблице | FK или unique constraint | Запустить `--only <table>` для retry; прислать вывод разработчику |
| `psycopg2.OperationalError: too many parameters` | Превышен лимит Postgres (65535 параметров) | Уменьшить `--batch-size` (default 1000), например `--batch-size 500` |
| Падение в середине | Сеть / OOM | Скрипт идемпотентен с `--force` — перезапустить с начала |

## Откат

Локальный SQLite-снимок не модифицируется. Для отката:

1. Остановить backend.
2. Очистить Postgres: `DROP DATABASE jira_analytics_prod; CREATE DATABASE jira_analytics_prod;` (или `TRUNCATE` всех таблиц).
3. Разработчик возобновляет работу на локальной SQLite.

## Контакт

После прогона прислать разработчику:
- Полный вывод dry-run и real run (особенно секцию `Summary`).
- Вывод сверки из шага 4.
- Логи backend после старта (`/health/ready` ответ + первые ~20 строк).

## Связанные документы

- Полный runbook: `docs/superpowers/specs/2026-05-16-data-migration-runbook.md`
- Скрипт: `scripts/migrate_to_postgres.py`
- Спецификация деплоя: `docs/superpowers/specs/2026-05-16-server-deployment-design.md`
