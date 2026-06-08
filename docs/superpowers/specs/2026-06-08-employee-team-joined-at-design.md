# Дата вступления сотрудника в команду — спецификация

**Дата:** 2026-06-08
**Контекст:** Виджет «Баланс часов команды» считает баланс с 01.01 текущего года. Если сотрудник пришёл в команду позже (например, 21.01), до этой даты он автоматически получает «отгулы» каждый день — это неверно.

---

## 1. Цель

Учитывать фактическую дату вступления сотрудника в каждую конкретную команду. Баланс часов считать с этой даты (не раньше).

## 2. Out of scope

- История переходов между командами (только текущая дата, без журнала).
- Дата увольнения / окончания в команде (только начало).
- Влияние на capacity-расчёт квартального плана (это отдельная тема).
- Кадровые поля Employee: ФИО, должность и т.д. — без изменений.

## 3. Доменная модель

Поле **на membership** (не на сотрудника): `EmployeeTeam.joined_at: date | null`.

Причины per-membership:
- Если сотрудник числится в двух командах с разными датами входа — мы их различаем.
- При смене команды старая запись сохраняет старую дату, новая получает новую.

## 4. Эффективная дата старта для виджета

Алгоритм `team_start(employee, teams_filter, period_from)`:

1. **Явная дата:** взять минимум `joined_at` среди тех membership сотрудника, чья команда входит в `teams_filter` (если фильтр пуст — среди всех membership).
2. Если есть → вернуть `max(period_from, найденная дата)`.
3. **Fallback β:** найти `MIN(Worklog.started_at)` сотрудника по задачам где `Issue.team ∈ teams_filter` (или по всем задачам если фильтр пуст). Если есть → `max(period_from, дата)`.
4. Иначе → `period_from` (как было).

## 5. Применение в виджете баланса

В `compute_team` и `compute_employee`:
- Для каждого сотрудника считаем `eff_start` через `team_start`.
- В цикле по дням периода: если `day < eff_start` → пропускаем как пустой день (kind `holiday` в drill-in, нулевая точка в спарклайне).
- KPI «Переработки/Автоотгулы» отражают только дни с `day ≥ eff_start`.

## 6. UI — «карточка ресурса»

На странице `/capacity` Team-tab:
- Клик по строке сотрудника → открывается **Drawer справа** (AntD `Drawer`, width 480).
- Содержание:
  - Шапка: аватар, ФИО, роль, основная команда.
  - Секция «Членство в командах» — карточки по командам сотрудника:
    - Название команды + бейдж «основная» если `is_primary`.
    - DatePicker «В команде с» (RU локаль, формат DD.MM.YYYY).
    - Кнопка «×» рядом с DatePicker — очистить дату.
  - Подсказка под секцией: «Если дата не указана — используется первый ворклог по задачам команды».

Сохранение DatePicker → PATCH membership → invalidate teams + dashboard queries.

## 7. Backend API

Новый эндпоинт:
```
PATCH /api/v1/employees/{employee_id}/teams/{team}/joined-at
body: {"joined_at": "YYYY-MM-DD"} | {"joined_at": null}
```

Возвращает обновлённый membership. Authentication: обычный auth (как остальные `/employees/{id}/teams/*`).

Существующий `GET /employees/{id}/teams` расширяется полем `joined_at` в ответе.

## 8. Миграция

Alembic batch:
```python
op.add_column('employee_teams', sa.Column('joined_at', sa.Date, nullable=True))
```

Никакого backfill — все существующие записи остаются `null`, виджет применит fallback β.

## 9. Edge cases

- **Сотрудник без worklogs + без joined_at:** виджет покажет его с `period_from`. Как сейчас.
- **Multi-team фильтр:** берётся минимум по выбранным. Самая ранняя команда определяет старт.
- **Изменение даты на будущее:** разрешено, но виджет покажет пустые дни — это ожидаемо.
- **Сотрудник переименовал команду:** не наша забота, membership-запись с другим `team` value уже отдельный объект.

## 10. Тесты

Backend:
- `team_start` — explicit date победит fallback.
- `team_start` — fallback на первый ворклог Issue.team.
- `team_start` — без всего → period_from.
- PATCH endpoint возвращает 200 на валидной дате.
- PATCH endpoint возвращает 200 на null (очистка).
- PATCH endpoint 404 на несуществующем employee/team.
- Виджет: сотрудник с `joined_at=2026-01-21`, баланс Январь не учитывает дни до 21.01.

Frontend:
- Drawer открывается по клику.
- DatePicker сохраняет дату.
- Кнопка «×» очищает.

## 11. Файлы

**Создаются:**
- `alembic/versions/045_*.py` миграция.
- `app/api/endpoints/employee_teams_joined_at.py` (или добавление в `employees.py`).
- `frontend/src/components/capacity/EmployeeDrawer.tsx`.

**Меняются:**
- `app/models/employee_team.py` — поле.
- `app/services/employee_team_service.py` — set_joined_at + GET включает поле.
- `app/services/hours_balance_service.py` — учёт `team_start`.
- `app/api/endpoints/employees.py` — расширение существующих ответов.
- `tests/services/test_hours_balance_service.py` — новые тесты.
- `tests/api/test_dashboard_hours_balance.py` — тест effective_start.
- `frontend/src/pages/CapacityPage.tsx` — `onClick` на строку → открытие Drawer.

## 12. Релиз

- `release_note.py add` (feat: «Дата вступления сотрудника в команду»).
- Без миграции данных, миграция схемы — да.
