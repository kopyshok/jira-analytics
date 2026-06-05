# Виджет «Баланс часов команды» — спецификация

**Дата:** 2026-06-05
**Раздел:** `/dashboard`
**Идея:** видеть накопительные переработки и автоотгулы по сотрудникам команды с начала календарного года, с возможностью раскрыть детальный календарь по сотруднику.

---

## 1. Цель

PM хочет одной картинкой видеть «у кого долг по часам, у кого перебор» по своей команде накопительно за текущий год. Деталь — календарь сотрудника по дням, чтобы понять когда были переработки и когда автоматически зафиксированы отгулы (нехватка ворклогов).

## 2. Out of scope

- Действий над балансом нет (просмотр).
- Не редактируем absences/worklogs.
- Не показываем задачи внутри дня (детали — в Jira).
- Не отправляем уведомления.
- Экспорт — не в этом релизе.
- История прошлых лет — не в этом релизе.

## 3. Источники данных

- `ProductionCalendarService.hours_in_range_map(start, end)` — норма дня (РФ календарь с переносами).
- `Absence` + `AbsenceReason` — официальные отсутствия. Reason с `code='day_off'` (label «Отгул») **игнорируется** при вычете нормы.
- `Worklog.time_spent_hours` — факт по дню × сотруднику (агрегация по `date_started`).
- `Employee` + `EmployeeTeam` (M:N) — состав команды.
- Глобальный фильтр команды (`selected_teams` в user prefs) — определяет какие сотрудники в виджете.

## 4. Доменная логика

**Эффективная норма дня:**
```
norm_eff(day, emp) = max(0, calendar_hours(day) − absence_hours(day, emp, excl. day_off))
```

**Дельта дня:**
```
delta(day, emp) = fact(day, emp) − norm_eff(day, emp)
```

Исключения:
- Если `norm_eff(day) = 0` и `fact(day) = 0` → день не входит в дельту (выходной, праздник или полное отсутствие).
- Если `norm_eff(day) = 0` и `fact(day) > 0` → переработка `+fact` (работа в выходной/праздник/отпуск).

**Классификация дня** (для модалки):
- `norm` — `|delta|` ≤ 10% от `norm_eff` (день закрыт примерно по норме).
- `overtime` — `delta > 0` и больше порога.
- `skip` — `delta < 0` и меньше порога (автоотгул).
- `absence` — день полностью покрыт официальным absence (кроме `day_off`).
- `holiday` — `calendar_hours = 0` (выходной/праздник) и `fact = 0`.

**Баланс сотрудника за период:** `sum(delta(day))` по всем дням периода.

**Спарклайн:** массив накопительного итога `delta` фиксированной длины — по всем дням периода где `calendar_hours(day) > 0` (рабочие дни производственного календаря). В дни отпуска/больничного `delta = 0` (линия идёт ровно). Это обеспечивает одинаковую длину спарклайнов между сотрудниками для визуального сравнения.

**Fallback:** если admin удалит `AbsenceReason` с `code='day_off'` — все absences будут уменьшать норму, автоотгулы детектиться не будут. Поведение безопасное, в спарклайне просто исчезнут серые дни. Логировать на старте сервиса warning, если код отсутствует.

## 5. Backend

### Эндпоинты

#### `GET /api/v1/dashboard/hours-balance`
Сводка по команде.

Query:
- `from` (date, опционально) — дефолт `date(current_year, 1, 1)`.
- `to` (date, опционально) — дефолт `date.today()`.
- `teams` (csv UUID, опционально) — дефолт = `selected_teams` текущего user.

Response:
```json
{
  "period": {"from": "2026-01-01", "to": "2026-06-05", "working_days": 105},
  "team_summary": {
    "employees_count": 8,
    "overtime_hours": 78.0,
    "skip_hours": -24.0,
    "net_balance": 54.0
  },
  "employees": [
    {
      "id": "uuid",
      "full_name": "Иванов И.",
      "role_label": "Аналитик",
      "avatar_url": "...",
      "balance_hours": 28.0,
      "overtime_days": 4,
      "overtime_hours": 30.0,
      "skip_days": 1,
      "skip_hours": -2.0,
      "sparkline": [0, 2, 5, 5, 3, ...]
    }
  ]
}
```

#### `GET /api/v1/dashboard/hours-balance/{employee_id}`
Drill-in по сотруднику.

Query: `from`, `to` (те же дефолты).

Response:
```json
{
  "employee": {"id", "full_name", "role_label", "team_label", "avatar_url"},
  "kpi": {"balance_hours", "overtime_days", "overtime_hours", "skip_days", "skip_hours"},
  "monthly": [
    {"year": 2026, "month": 1, "label": "Янв", "balance": 4.0, "overtime_days": 1, "skip_days": 0},
    ...
  ],
  "days": [
    {
      "date": "2026-05-06",
      "norm": 8.0,
      "fact": 11.0,
      "delta": 3.0,
      "kind": "overtime"
    },
    {
      "date": "2026-05-08",
      "norm": 8.0,
      "fact": 6.0,
      "delta": -2.0,
      "kind": "skip"
    },
    {
      "date": "2026-05-18",
      "norm": 0.0,
      "fact": 0.0,
      "delta": 0.0,
      "kind": "absence",
      "absence_label": "Отпуск"
    }
  ]
}
```

### Сервис

`app/services/hours_balance_service.py` — новый.

```
class HoursBalanceService:
    def compute_team(team_ids, from_, to_) -> TeamBalanceResult
    def compute_employee(employee_id, from_, to_) -> EmployeeDetailResult
```

Bulk-загрузка:
1. `production_calendar.hours_in_range_map(from_, to_)` — один раз, общий.
2. Один запрос worklog: `SELECT employee_id, date(date_started), SUM(time_spent_hours) FROM worklogs WHERE employee_id IN (...) AND date_started BETWEEN ... GROUP BY ...`.
3. Один запрос absence: `SELECT a.*, r.code FROM absences a JOIN absence_reasons r ON ... WHERE end_date >= from AND start_date <= to AND employee_id IN (...)`.
4. В памяти разворачиваем absence в карту day×emp → absence_hours (с учётом исключения `day_off`).
5. Итерация по дням × сотрудникам → формируем delta, классификация, накопительный итог.

Reuse: производственный календарь общий. Capacity-логику не трогаем (там месячная агрегация).

### Производительность

Цель: 10 сотрудников × 105 рабочих дней <300мс. SQLite + индексы (`worklogs.date_started`, `absences.employee_id`).

### Безопасность

Требует login. Команда — из `selected_teams` пользователя. Чужие команды через query `teams=` — только если есть права (любой залогиненный — да; админ-only не требуется по аналогии с другими виджетами).

## 6. Frontend

### Файлы
- `frontend/src/components/dashboard/HoursBalanceWidget.tsx` — виджет.
- `frontend/src/components/dashboard/HoursBalanceModal.tsx` — модалка.
- `frontend/src/hooks/useHoursBalance.ts` — TanStack Query хуки.
- `frontend/src/types/api.ts` — добавить типы ответа.
- `frontend/src/pages/DashboardPage.tsx` — вставить 4-й виджет.

### Виджет

Карточка `bg #0f2340`, padding 20, rounded 12.

**Header:** title «Баланс часов команды» + subtitle «С 01.01.2026 · N рабочих дней · норма с учётом отпусков». Справа — sort dropdown с опциями:
- «По отклонению» (default) — сортировка по `abs(balance_hours)` по убыванию: самые выделяющиеся первыми (хоть переработка, хоть отгул).
- «Больше переработали» — `balance_hours` по убыванию.
- «Больше недоработали» — `balance_hours` по возрастанию.
- «По имени» — алфавит.
- «По роли» — группировка по роли + имя.

**Team summary strip** — горизонтальная плашка `#143258`: `Команда: N чел · переработки +Xч · автоотгулы −Yч · нетто Zч` (цвета по знаку).

**Cards grid:** CSS grid `repeat(auto-fit, minmax(300px, 1fr))`. На каждого сотрудника:
- Аватар 40px (gradient из инициалов) + Имя + Роль.
- Большой бейдж баланса (28px, цвет по знаку: красный `#ff4d4f`, оранжевый `#faad14` если отрицательный, серый `#8aa0c0` если ≈0).
- SVG-спарклайн 180×40 (polyline, stroke 2px, fill 15% alpha).
- Две плашки: «🔥 Переработок: 4 дн · +18ч» (red), «🌙 Отгулов: 2 дн · −6ч» (purple-gray).
- Hover: cyan border + scale(1.015) + cursor pointer.

**Footer note** мелким курсивом: «Отпуск, больничный и другие официальные отсутствия не считаются переработкой/отгулом».

### Модалка

AntD `Modal`, width 920, footer кастомный, scroll внутри. Закрытие — крест/Esc.

**Header:** «Баланс часов — {Имя}», subtitle «{Роль} · команда {Team} · с 01.01.2026».

**KPI row** — 3 плитки в ряд (`#143258`):
1. «Баланс +28ч» (32px цвет по знаку) + подпись «за N рабочих дней».
2. «Переработки 4 дн / +24ч».
3. «Автоотгулы 2 дн / −6ч».

**Monthly summary strip** — 6 блоков (Янв, Фев, Мар, Апр, Май, Июн), каждый 130px:
- Месяц uppercase
- Баланс месяца со знаком (цвет)
- Мини «X / Y» — переработок / отгулов дней

**Calendar grid** — 6 mini calendars (3×2):
- Заголовок месяца + балл-пилюля справа.
- 7 колонок (Пн Вт Ср Чт Пт Сб Вс).
- Ячейка 24×24px:
  - выходной — `#162a4a` бледный
  - праздник — `#162a4a` + точка-маркер
  - норма — `#1d3d22` зелёный + бордер
  - переработка — `#3d1b1d` красный + цифра `+N`
  - автоотгул — `#2a2f42` со штриховкой + цифра `−N`
  - absence — `#3b3155` фиолетовый + «О»
- Hover-tooltip: «Норма Xч / Факт Yч / ±Zч».

**Legend row** под календарём (12px).

**Footer:** буква-пояснение «Детали задач — в Jira» + кнопка «Закрыть».

### Хуки

```ts
useHoursBalance({ from?, to?, teams? }) — list endpoint
useHoursBalanceDetail(employeeId, { from?, to? }) — drill-in
```

Оба `staleTime: 60s`, `retry: 1`. Inval на `entity_changed` событиях типа `worklog`/`absence`.

## 7. Edge cases

- Сотрудник вышел в команду 1 марта — балланс считается с 1 января (упрощение, иначе сложная история membership).
- Сотрудник в отпуске весь январь — `absence_hours` покроет январь, баланс не уйдёт в минус.
- Worklog на дату вне period.to — игнорируется.
- Производственный календарь не заполнен в DB — ProductionCalendarService уже даёт fallback 8ч/день mon-fri (проверить).
- Удалён `AbsenceReason.code='day_off'` — все absences уменьшают норму, автоотгулов не будет; warning в логи.
- `selected_teams` пуст — виджет показывает empty state «Выберите команду в фильтре».
- Команда без активных сотрудников — empty state «В команде нет активных сотрудников».

## 8. Тесты

### Backend (pytest)

`tests/services/test_hours_balance_service.py`:
- `test_norm_with_vacation_zero_delta` — отпуск 5 дней покрывает 5 раб дней, delta=0.
- `test_day_off_reason_ignored_in_norm` — absence с reason `day_off` не уменьшает норму.
- `test_overtime_on_weekend_counted` — fact=4ч в субботу → +4ч.
- `test_classification_thresholds` — ±10% разделяет norm / overtime / skip.
- `test_cumulative_sparkline_monotonic_on_pure_overtime` — для сотрудника со всегда +1ч баланс растёт.
- `test_missing_day_off_code_logs_warning` — fallback срабатывает.

`tests/api/test_dashboard_hours_balance.py`:
- `test_returns_200_on_empty_team` — нет активных сотрудников → 200 [].
- `test_default_period_starts_jan_1` — без query начинается с 1 января.
- `test_drill_in_employee_not_found` — несуществующий id → 404.
- `test_team_filter_applies` — фильтр по teams= возвращает только нужных.

### Frontend

`vitest`:
- хук `useHoursBalance` корректно парсит ответ.
- `HoursBalanceWidget` рендерит N карточек, sortable.

`Playwright e2e`:
- Navigate `/`, find «Баланс часов», click first card, modal opens, Esc closes.

## 9. Файлы

**Создаются:**
- `app/services/hours_balance_service.py`
- `app/api/endpoints/dashboard_hours_balance.py`
- `tests/services/test_hours_balance_service.py`
- `tests/api/test_dashboard_hours_balance.py`
- `frontend/src/components/dashboard/HoursBalanceWidget.tsx`
- `frontend/src/components/dashboard/HoursBalanceModal.tsx`
- `frontend/src/hooks/useHoursBalance.ts`

**Меняются:**
- `app/api/__init__.py` — register router
- `frontend/src/types/api.ts` — добавить типы
- `frontend/src/pages/DashboardPage.tsx` — вставить виджет 4-м

**Миграции:** не требуются (read-only фича).

## 10. Релиз

- `scripts/release_note.py add feat "Виджет «Баланс часов команды» на дашборде"`.
- Документация: коротко в `docs/changelogs/` после релиза (auto).
- E2E smoke на `/dashboard`.
