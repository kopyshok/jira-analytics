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
