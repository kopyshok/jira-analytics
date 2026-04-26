# Review Fixes 2026-04-26

## Обнаружено

- Generic-настройки позволяют читать и писать Jira credentials в обход отдельной Jira-ручки.
- Копирование правил квартала вызывает отсутствующий метод сервиса.
- Frontend API client пытается разобрать пустой успешный ответ как JSON.
- Подключение к БД всегда использует SQLite-only параметры.
- Точечное и командное обновление задач не запрашивают due date.

## Изменено

- Добавлены регрессионные тесты для настроек, параметров подключения к БД, копирования правил и sync due date.
- Generic settings теперь ограничены безопасными UI/runtime/Jira-field ключами.
- Добавлено копирование правил квартала в сервис ресурсов.
- SQLite-only параметры подключения вынесены за проверку типа БД.
- Targeted refresh и team sync теперь запрашивают due date.
- Frontend API client теперь не пытается JSON-разбирать успешные пустые ответы.
- Обновлена тестовая заглушка sync под текущий контракт.
- Убраны два frontend lint-блокера, которые мешали проверке плана.

## Проверки

- Red: targeted backend tests падали на текущих дефектах.
- Pass: targeted backend tests after backend fix (`10 passed`).
- Pass: `py -3.10 -m pytest tests/ -q` (`422 passed`).
- Pass: `py -3.10 -m ruff check app/api/endpoints/settings.py app/services/capacity_service.py app/database.py app/services/sync_service.py tests/test_database.py tests/test_settings_endpoints.py tests/test_sync_service.py`.
- Pass: `npm run lint`.
- Pass: `npm run build`.
- Pass: `alembic heads` (`e97b35c021a7 (head)`).
- Fail: `py -3.10 -m ruff check app tests` — 48 repo-wide findings outside this fix set / old touched-test import debt.
- Fail: `py -3.10 -m mypy app` — 85 existing type errors; the new `app/database.py` error was removed.

## Осталось

- По пяти review findings кодовые исправления внесены.
- Отдельно, не в рамках этого плана: разобрать repo-wide `ruff` и `mypy` долг.

## Примечания для следующей сессии

- До этой задачи в рабочем дереве уже были изменения в `.gitignore` и `frontend/src/components/planning/PlanningCapacityPanel.tsx`; их не трогать без отдельного запроса.
- Дополнительно тронуты `frontend/src/components/Layout/SyncIndicator.tsx` и `frontend/src/pages/SyncPage.tsx`, чтобы выполнить запрошенный frontend lint/build без изменения пользовательского сценария.
