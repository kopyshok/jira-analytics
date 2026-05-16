# tests — pytest backend

Windows: `py -3.10 -m pytest tests/ -v` (pytest не установлен под дефолтным Python 3.14).

## Структура

- Сервисные тесты: `test_<service>.py`
- Schema/reference: `test_schemas.py`, `test_*_reference.py`
- Endpoint-ориентированные: `test_api_*.py` / `test_*_endpoints.py`
- Config / models: `test_config.py`, `test_database.py`
- Shared sample data: `tests/fixtures/`

## Fixtures ([conftest.py](conftest.py))

- `engine` — session-scoped in-memory SQLite
- `db_session` — function-scoped

**ПРАВИЛО:** после каждого теста явно удаляются rows из всех таблиц (`table.delete()` в reverse order), потому что сервисы типа `MappingService`, `PlanningService`, `BacklogService` коммитят internally — plain `rollback()` не отменит committed data.

**Если добавляешь сервис с internal commit — НЕ ослабляй cleanup.** Иначе предыдущий тест оставит хвосты, следующий упадёт по уникальным constraint или непредсказуемому состоянию.

## Endpoint-тесты с TestClient

`:memory:` SQLite + TestClient async endpoints выявляет ORM caveat: после `db.commit()` сессия expire-ит атрибуты; обращение триггерит reload на potentially thread-rotated connection. В endpoints **снимать снимок полей в локали до commit** — иначе получишь `DetachedInstanceError` (см. `app/api/endpoints/issue_config.py` `set_issue_category`).

## Команды

```bash
# Полный прогон
py -3.10 -m pytest tests/ -v

# Один тест
py -3.10 -m pytest tests/test_capacity_service.py::TestMonthlyCapacity::test_vacation_inside_month -v
```

## Прогон против Postgres локально

CI гоняет тесты дважды: SQLite (быстро) и Postgres 16 (проверка совместимости). Локально по умолчанию SQLite. Чтобы воспроизвести Postgres-фейл с CI:

```powershell
# Windows
.\scripts\run_tests_postgres.ps1            # весь suite
.\scripts\run_tests_postgres.ps1 -k capacity # только нужные
```

```bash
# Linux / WSL
./scripts/run_tests_postgres.sh
./scripts/run_tests_postgres.sh -k capacity
```

Скрипт поднимает `postgres:16-alpine` через `docker-compose.test.yml` (порт `55432`, tmpfs), экспортирует `TEST_DATABASE_URL`, гоняет pytest, останавливает контейнер.

Один тест вручную:

```powershell
docker compose -f docker-compose.test.yml up -d
$env:TEST_DATABASE_URL = "postgresql://test:test@localhost:55432/jira_analytics_test"
py -3.10 -m pytest tests/test_capacity_service.py -v
Remove-Item Env:TEST_DATABASE_URL
docker compose -f docker-compose.test.yml down
```

**Conftest behaviour:** `_resolve_test_database_url()` читает env; `engine` fixture применяет `StaticPool` + `check_same_thread` только для SQLite, для Postgres использует дефолтный пул и `drop_all` перед `create_all` (чистый schema на каждом запуске).
