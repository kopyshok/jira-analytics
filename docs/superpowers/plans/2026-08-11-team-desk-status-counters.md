# План: счётчики статусов в разрезе разработчиков

Спека: [2026-08-11-team-desk-status-counters-design.md](../specs/2026-08-11-team-desk-status-counters-design.md)

## 1. Сервер: разбивка по статусам в сводке

- `app/services/team_desk/query.py::_summarize` — добавить `status_counts` в
  строку разработчика: словарь «статус → число», считается по тем же
  самостоятельным задачам, что и `total_issues`.
- Верхнеуровневых полей не добавлять: список статусов среза интерфейс собирает
  из уже приходящих задач.

Проверка: `tests/test_team_desk_query.py` — новый тест «разбивка по статусам
сходится с общим числом задач и не считает подзадачи».

## 2. Сервер: выбор статусов в профиле

- `app/api/endpoints/users.py::TeamDeskFilterPayload` — поле `status_counters:
  list[str] = []`. Хранилище — тот же свободный JSON, миграция не нужна.

Проверка: `tests/test_user_settings.py` — сохранение и чтение выбора.

## 3. Фронт: типы и порядок статусов

- `frontend/src/api/teamDesk.ts`:
  - `DeskDeveloper.status_counts: Record<string, number>`
  - `DeskFilterPrefs.status_counters: string[]`
  - `orderedStatuses(statusGroups, seen)` — статусы в порядке групп
    (dev → waiting → todo → done → нераспределённые), только те, что переданы
  - `statusGroupOf(statusGroups, status)` — группа статуса
- `frontend/src/components/teamdesk/IssueCells.tsx` — экспортировать цвета
  групп, чтобы значок статуса и тег статуса в списке задач красились одинаково.

## 4. Фронт: значок-счётчик

- Новый `frontend/src/components/teamdesk/StatusCounters.tsx` — строка значков:
  точка группы + название + число, подсказка при наведении, клик выбирает
  разработчика и статус.

## 5. Фронт: три раскладки

- `DeveloperCards.tsx` — строка значков между очередью и замечаниями.
- `GroupedIssues.tsx` — строка значков в строке разработчика; фильтр по статусу
  рядом с фильтром по замечанию (родитель остаётся, если подходит подзадача).
- `DeveloperTable.tsx` — колонка на каждый выбранный статус после «Замечаний»,
  сортировка, итог в нижней строке, клик по числу фильтрует.

## 6. Фронт: настройка в шапке

- `DeskFilters.tsx` — поле «Счётчики статусов» (множественный выбор, пусто =
  все статусы среза).
- `TeamDeskPage.tsx` — состояние фильтра по статусу, сборка списка статусов
  среза, передача выбранных статусов во все три раскладки, подсказка о
  действующих фильтрах.

Проверка: `npm run lint` + `npm run build`.

## 7. Документация

- `docs/help/team-desk.md` — раздел про счётчики статусов: что считается, как
  настроить, как фильтровать.
- `app/services/CLAUDE.md`, `frontend/CLAUDE.md`, `app/api/CLAUDE.md` — по одной
  строке про новое поле сводки и настройку в шапке.
- `release_notes/drafts.json` — заметка к релизу.

Проверка: `py -3.10 -m pytest tests/test_team_desk_query.py tests/test_user_settings.py -q`
