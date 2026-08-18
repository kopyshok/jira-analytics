# План: очередь, отборы, «резиновые» задачи

Спека: [2026-08-18-team-desk-queue-and-rubber-design.md](../specs/2026-08-18-team-desk-queue-and-rubber-design.md)

## Шаг 1. Хранение дневной нормы (backend)

- Модель `TeamDeskDailyRate` (`team_desk_daily_rates`): `issue_id` уникален,
  `hours`, кто и когда правил. Каскад по задаче.
- Миграция `td05a_team_desk_daily_rate`, предок — `k16a_kpi_metric_empty_policy`.
- Порог `rubber_days = 5` в настройках раздела.
- Проверка: `pytest tests/test_team_desk_config.py tests/test_migrations_fresh_db.py`

## Шаг 2. Срез задач отдаёт исполнителя, норму и признак очереди

- `query.py`: в строку задачи добавить исполнителя, дневную норму, `in_queue`,
  `assigned_to_owner`.
- Проверка: `pytest tests/test_team_desk_query.py`

## Шаг 3. Очередь: две строки + резина

- `workload.py`: считает обе строки (`queue_*` и `assigned_*`), резиновая задача
  даёт `min(остаток, норма × rubber_days)`.
- Проверка: `pytest tests/test_team_desk_workload.py` (новые случаи из спеки)

## Шаг 4. Ручка правки нормы

- `PUT /team-desk/issues/{id}/daily-rate` — число или пусто (снять).
- Проверка: `pytest tests/test_team_desk_endpoint.py`

## Шаг 5. Плитка разработчика

- Две строки очереди, обе кликабельны; значки замечаний кликабельны.

## Шаг 6. Страница: отборы вниз, видимость отбора, отбор по очереди

- Полосы «Требует внимания» и «Задачи по статусам» — к таблице задач.
- Строка «Отобрано: … / Сбросить».
- Состояние отбора по очереди: `all | assigned | null`.

## Шаг 7. Таблица задач: колонка «DevForDay» + отбор по очереди

## Шаг 8. Карточка «Резиновые задачи»

## Шаг 9. Настройка «дней в очередь» в панели порогов

## Шаг 10. Справка раздела + заметка к релизу

- Проверка: `py -3.10 -m pytest tests/ -k "desk"`, `npm run lint`, `npm run build`
