# Resource Planning — фиксы и юзабилити-улучшения

**Статус:** в работе
**Дата:** 2026-05-17
**Раздел:** `/resource-planning`

## Цели

Раздел `/resource-planning` — самый сложный для понимания PM-ом: непонятно, как планировщик строит расписание, не очевидны причины конфликтов, и часть фич либо сломана, либо недостаточно выразительна. Цель — закрыть пакет багов в расчёте/визуализации, унифицировать управление назначениями и сделать боковую панель полноценным «окном диагностики» вместо короткой формы.

В скоупе **только страница `/resource-planning`** (режимы Портфель / Фазы / Ресурсы / Plane) — модель ресурсов, сценариев, бэклога не меняем.

## Контекст и текущее поведение

### Что есть сегодня

- `ResourcePlanningPage` со страничным состоянием (планы, view-mode, scale, фильтры) и тремя дочерними компонентами:
  - `GanttChart` + `GanttRows` (Портфель/Фазы/Ресурсы)
  - `PlaneGantt` (экспериментальный режим, на паузе)
  - `AssignmentSidebar` (Drawer 460px с расчётом проблем)
- `AssignEmployeePopover` навешен на каждый бар фазы — открывается тем же кликом, что и `AssignmentSidebar`.
- Backend планировщик в `app/services/resource_planning_service.py` (`ResourcePlanningService.compute_schedule`) распределяет часы по сотрудникам помесячно от `q_start` до `q_end`. Конфликты считаются в `_build_conflict_dicts` + `conflict_aggregator`.

### Найденные корни багов

| Симптом | Корень |
|---|---|
| #3 Наложение часов (PRJ-10623 + ITL-304 ОПЭ = 146%) | `_allocate_hours` зануляет `emp_days[d] = 0` даже если использована не вся ёмкость дня → теряются часы. `effective_end = cal_end` растягивает бар на дни без работы (когда Jira-поля заданы). Конфликт-агрегатор делит `hours_allocated / длина бара в днях` → даёт «вес» дням, на которых работы фактически нет |
| #7 Переключатель «только рабочие» не работает | `hideWeekends` объявлен в `GanttChart` props, но нигде в коде не применяется — чистый no-op |
| #8 Анализ ITL-299 длится до 20-х апреля при готовности часов 08.04 | То же место: `effective_end = cal_end` при `jira_cal_set=True`. Dev-фаза стартует от растянутого `phase_end`, а не от фактического конца работы |
| #9 Разделитель неделя посередине гряды выходных | Воскресный день и понедельник-праздник РФ-календаря образуют непрерывную «гряду нерабочих», а вертикальный разделитель `W8→W9` стоит на старте Пн → визуально оказывается в центре полосы |

### Что разбирали и отложили

Не делаем: mini-map, today-маркер с указателем, conflict-точки в левой колонке, inline heatmap, иконки фаз, skeleton-loader.

## Архитектурные решения

Все 9 пунктов из брейнштурма закрываются одним согласованным изменением. Без декомпозиции на под-проекты.

### 1. Назначение сотрудника — только через боковую панель

`AssignEmployeePopover` удаляется (был дубль `Select` сотрудника из `AssignmentSidebar`). Клик на бар фазы → открывается **только** боковая панель, в ней есть текущий Select сотрудника + кнопка пересчитать.

Чтобы не блокировать другие бары: Drawer становится **немодальным** (`mask=false`). Полоски Ганта остаются кликабельными — клик на другой бар обновит содержимое панели без её закрытия. Crosshair курсор сохраняется в режиме рисования связей.

### 2. Боковая панель — 6 секций детализации, ширина ×2

Drawer 460 → **920 px**. Секции (каждая collapsible, состояние свёрнутости per-user в `rp_preferences.detail_sections_collapsed[]`):

1. **Откуда дата старта** (алгоритм) — текстовое объяснение: `earliest_start = max(quarter_start, end предыдущей фазы, конец предшественника + lag)`. Цепочка событий: «Анализ закончился 08.04 → Разработка стартует 09.04».
2. **Дни × часы** (таблица) — по каждому рабочему дню фазы: дата, доступно ч, потрачено на эту фазу ч, статус (рабочий / отсутствие / праздник / занят другой задачей с указанием какой).
3. **Отсутствия в окне фазы** — список «01-03.05 — отпуск (Копышков)», «09.05 — праздник РФ», «05.05 — занят ОПЭ ITL-304 → разрыв на 1 день».
4. **Часы фазы по источникам** — Jira `duration_days` (если задана), `involvement %` (если задано), `parallel_count`, % по правилу роли, итоговая дневная ёмкость emp в этой фазе. «20ч × 50% involvement = 4ч/день, 5 рабочих дней».
5. **Длительность vs часы** — счётчики: всего часов, осталось, рабочих дней, дней «съели» отсутствия/конфликты.
6. **Влияние на критический путь** — `is_on_critical_path`, `slack_days`, какие фазы сдвинутся при задержке.

Шестерёнка ⚙ в шапке Drawer → popover с галочками: какие секции вообще показывать (отдельно от свёрнутости). Скрытые секции не рендерятся.

Существующие блоки (часы/часть/сотрудник/даты/предшественники, «Расчёт проблем» с overload-contributors, «Действия») остаются над секциями детализации — это форма редактирования, а не детализация.

### 3. Расчёт + визуал наложения часов

#### Расчёт (`resource_planning_service.py`)

**A1 — хирургический фикс `_allocate_hours`**:
- Вместо `emp_days[d] = 0.0` — `emp_days[d] -= used` (оставлять не использованные часы дня свободными).
- `effective_end` всегда = последний рабочий день фактической работы (срабатывает на всех путях, не только при `jira_cal_set=False`). Jira `duration_days` больше не растягивает бар.
- Dev-фаза `earliest_start` считается от фактического `seg_end`, а не от `effective_end = cal_end`.

**Мульти-сегмент только при физическом разрыве**:
- Когда чужая preempting-фаза (ОПЭ) попадает внутрь окна обычной фазы (analyst/dev) — `_allocate_hours` возвращает два сегмента: до preempting и после.
- Каждый сегмент пишется как отдельный `ResourcePlanAssignment` с `part_number=1,2` (по аналогии с уже существующим split-механизмом для аналитика).
- Если разрыв вызван НЕ другой задачей (отпуск, праздник) — остаётся один сегмент, пропуски рисуются штриховкой как сейчас (`UnavailabilityOverlay`).

#### Визуал (frontend)

- **b2** — мульти-сегмент рисуется как два бара с тонкой соединительной линией (1px пунктир в цвет фазы).
- **b3** — один бар с штриховкой на отсутствиях/праздниках (текущий `UnavailabilityOverlay`, сохраняем).
- В детализации (секция 3 «Отсутствия в окне фазы») подсвечивается причина разрыва: «05.05 — занят ОПЭ ITL-304 → разрыв на 1 день».

#### Конфликт-агрегатор (`conflict_aggregator.py`)

`OVERLOAD_*` события считаются per-day на основе **реальных дней использования**, а не равномерно распределённых часов по длине бара. Новое поле в `ResourcePlanAssignment`: `daily_hours_json: Optional[str]` (JSON map `{"2026-05-04": 6.67, "2026-05-06": 8.0}`) — пишется планировщиком при `_allocate_hours`, читается агрегатором.

### 4. Насыщенность инициативы — 2 ползунка

`AppearanceModal`:
- `fill_intensity_pct` 0-100 (по умолчанию 50) → `alphaTop = 0.05 + pct/100 × 0.35`
- `fill_contrast_pct` 0-100 (по умолчанию 50) → `alphaBottom = alphaTop × (1 - pct/100 × 0.5)`

Старые segmented `soft/medium/dense` удаляются. Миграция значений: `soft → (25, 50)`, `medium → (50, 50)`, `dense → (90, 50)`.

### 5. Планировщик за квартал — +1 месяц

- `deadline = q_end + relativedelta(months=1)` в `_allocate_hours` и связанных местах (`_allocate_hours`, `_advance_working_days` limits, `_compute_cpm`, `_persist_conflicts`).
- Новое поле `ResourcePlanAssignment.out_of_quarter: Boolean` (миграция). Заполняется при `_allocate_hours` если `seg_start > q_end`.
- Frontend timeline расширяется на 1 месяц после `q_end` когда есть хотя бы один `out_of_quarter` assignment в проекции. Visual: бары за `q_end` — диагональный штрих + opacity 0.6 + рамка `1px solid #ffb432`. В заголовке timeline добавляется отметка «Выход за квартал» на старте overflow-зоны.
- Конфликты на overflow-днях считаются как обычно (это валидный overload).

### 6. Подсветка сотрудника — A+B+C+D

Текущее: bg строки `rgba(0,201,200,0.06)`, pill `.18`, dimmed others `opacity:0.25`. Меняем на 4 совмещённых сигнала:

- **A.** Glow на барах сотрудника — `outline: 2px solid #00c9c8 + box-shadow: 0 0 8px rgba(0,201,200,0.7)`.
- **B.** Bg строк где он есть — `rgba(0,201,200,0.18)` (в 3× ярче).
- **C.** Бары других сотрудников — `opacity: 0.12` (было 0.25).
- **D.** Pulse на барах сотрудника — CSS animation 1.4s ease-in-out (плавная пульсация glow). Опционально (`rp_preferences.pulse_highlighted_employee`, по умолчанию `true`).

### 7. Фикс «только рабочие»

`hideWeekends` реально применяется. Реализация: новый утиль `buildWorkdayTimeline(start, end, calendar)` — возвращает timeline где `totalDays = только рабочие дни` (РФ-календарь + Пн-Пт fallback). Все `dateToLeft`/`datesToWidth` используют workday-индекс. Бар с `start_date` в выходной clamp-ится к ближайшему рабочему.

В шапке переключатель применяется в режимах `two-level`, `portfolio`, `resource-track`. В `plane` пока не меняем (на паузе).

### 8. Длина фазы — фактический конец

Закрывается фиксом в #3 (`effective_end` = последний рабочий день). Dev стартует от фактического `seg_end`. Jira-длительность больше не учитывается визуально.

Если PM позже захочет видеть «плановую vs фактическую» длительность — это отдельная итерация, не в этом спеке.

### 9. Неделя — выходные

В week- и month-режимах **не рендерим** `NonWorkingZones` (дневные полоски выходных). Праздники в `TimelineHeader` показываются как маленькая точка `•` под номером недели (если в неделе есть хотя бы 1 нерабочий день в РФ-календаре). Hover → tooltip с датой и названием.

Разделители недель: текущий dashed `0.08` → solid `rgba(160,200,240,0.20)`. Стиль `month` остаётся.

В day-режиме всё как есть.

### Дополнительные визуальные улучшения

- **ii. Прогресс факта внутри полоски** — backend подтягивает `worklog_hours_actual` для каждого assignment'а из `Worklog` (filter по `assignee_id=employee_id`, `started in [start_date, end_date]`). Frontend рисует прогресс-заливку слева внутри бара: `width = min(100%, fact/plan * 100%)`. Цвет — чуть светлее основного. Полоска перегруза (fact > plan) рисуется поверх с красной обводкой.
- **viii. Smooth zoom** — CSS transition `width 250ms ease-out` на `trackWidthPx`. При смене scale (День/Неделя/Месяц) бары и заголовок плавно растягиваются.
- **ix. Pulse на критическом пути** — CSS animation 2s ease-in-out на `box-shadow` для баров с `is_on_critical_path=true`. Toggle в Appearance (`pulse_critical_path`, по умолчанию `true`).
- **x. Collapse-all / Expand-all** — кнопка в шапке `[↕]` рядом с переключателем view-mode. Toggle всех инициатив в `rp_preferences.collapsed_initiative_ids` (полный список ID при collapse, пустой массив при expand).
- **xi. Sticky left column** — `ItemTitleCell` оборачивается в `position: sticky; left: 0; z-index: 4; background: #0a1628`. Применяется ко всем view-режимам. При горизонтальном скролле левая колонка остаётся видимой целиком (заголовок задачи + фаза + сотрудник).

## API + модели

### Миграция

```sql
-- alembic revision: add resource plan assignment out_of_quarter + daily_hours
ALTER TABLE resource_plan_assignments
    ADD COLUMN out_of_quarter BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN daily_hours_json TEXT;
```

### `ResourcePlanAssignment` (SQLAlchemy)

```python
out_of_quarter: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
daily_hours_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

`daily_hours_json` — `{"YYYY-MM-DD": float, ...}` фактически использованные часы по дням. Помесячная агрегация для conflict-aggregator + per-day breakdown в детализации.

### `ResourcePlanAssignmentOut` (Pydantic)

Добавляем `out_of_quarter: bool`, `daily_hours: dict[str, float] | None`.

### `/explain` endpoint расширение

`AssignmentExplainResponse` получает:
- `algorithm_log: list[str]` — текст «откуда дата старта» (секция 1)
- `daily_breakdown: list[DailyBreakdownItem]` — секция 2: `date, available, used, status, blocker_assignment_id?`
- `absences_in_window: list[AbsenceWindowItem]` — секция 3
- `phase_calc: PhaseCalcDetails` — секция 4: `duration_days_jira, involvement_pct, parallel_count, role_pct, daily_capacity_hours`
- `hours_summary: HoursSummary` — секция 5: `total, used, remaining, workdays, blocked_days`

Поле `is_on_critical_path` + `slack_days` уже есть — секция 6 их использует.

### `UserSetting.rp_preferences` (JSON)

Добавляются ключи:
- `detail_sections_visible: dict[str, bool]` — какие из 6 секций показывать (по умолчанию все `true`)
- `detail_sections_collapsed: dict[str, bool]` — какие свёрнуты (по умолчанию `false`)
- `fill_intensity_pct: int` 0-100 (default 50)
- `fill_contrast_pct: int` 0-100 (default 50)
- `pulse_highlighted_employee: bool` (default true)
- `pulse_critical_path: bool` (default true)
- `out_of_quarter_months: int` (default 1, range 0-3)
- `hide_weekend_stripes_week_mode: bool` (default true)

Backward-compat: миграция значений `initiative_fill_intensity` segmented → ползунки (один раз при первом чтении).

## Тестирование

### pytest (backend)

- `test_allocate_hours_preserves_unused_capacity` — `daily_capacity < avail_h` → остаток доступен для другой фазы того же сотрудника в тот же день
- `test_effective_end_no_stretch_when_jira_duration_set` — Jira `duration_days=20` + hours done за 5 дней → assignment.end_date = day 5
- `test_dev_starts_after_actual_analyst_end` — analyst Jira-длительность 20 дней, фактически 8 → dev.start_date = 9
- `test_multi_segment_on_preempting_phase` — ОПЭ вклинивается на 1 день в середину analyst → 2 assignment'а с part_number=1,2
- `test_out_of_quarter_allocation` — часы не помещаются в Q2 → последний сегмент `out_of_quarter=True`, dates за q_end
- `test_conflict_aggregator_uses_daily_hours` — 2 phase'ы overlap по дате-диапазону но не по `daily_hours_json` → no OVERLOAD

### frontend unit / integration

- `useRpPreferences` — нормализация segmented `soft/medium/dense` → ползунки
- `buildWorkdayTimeline` — без выходных и праздников
- Sidebar — клик на разные бары обновляет содержимое без закрытия (mask=false)

### E2E (Playwright)

- `resource-planning-fixes.spec.ts`:
  - Открыть план, кликнуть бар → Drawer открыт, бары других задач кликабельны
  - Toggle «Только рабочие» → шкала перестроена без вых/праздников
  - View-mode «Неделя» → нет полосок выходных, разделители видны
  - Сценарий где хватает часов → нет бара за q_end. Сценарий где не хватает → бары со штрихом за q_end

## Out of scope

- Drag arrows для создания зависимостей мышью (отдельная итерация)
- Plane view улучшения (на паузе)
- Mini-map / overview ribbon
- Today-маркер с треугольным указателем
- Conflict-точки в левой колонке
- Inline heatmap
- Иконки фаз
- Skeleton loader
- Mobile/touch
- Backend optimization (N+1 на calendar reads — отдельный backlog)

## Риски

- Мульти-сегмент меняет инвариант «1 фаза = 1 assignment». Predecessor-граф и CPM работают по `(item_id, phase, part_number)` — нужно убедиться что arrows и leveler корректно работают с part_number>1.
- `daily_hours_json` увеличит размер `resource_plan_assignments` (для 5000 assignment × ~50 дней JSON ≈ 5MB). Допустимо. Если станет проблемой — выделить в отдельную таблицу `assignment_daily_hours`.
- `hideWeekends` rebuild timeline затрагивает все view-режимы — нужно тестировать что bar positioning одинаково корректен с workday-индексом.
- 920px Drawer на узких экранах (<1400px) занимает половину Ганта. Принимаем — `mask=false` решает проблему интерактивности.

## Этапы реализации (high-level)

1. **Backend scheduler + конфликт-агрегатор** — `_allocate_hours`, `effective_end`, мульти-сегмент, `daily_hours_json`, `out_of_quarter`. Миграция.
2. **API `/explain` расширение** — algorithm_log, daily_breakdown, absences_in_window, phase_calc, hours_summary.
3. **Frontend Sidebar v2** — 6 секций, ширина 920, шестерёнка, mask=false, удалить Popover.
4. **Frontend Appearance** — 2 слайдера, миграция segmented.
5. **Frontend timeline-фиксы** — `hideWeekends` реализация, week-mode без полосок, sticky left.
6. **Frontend подсветка + пульсы + прогресс факта + zoom + collapse-all** — A+B+C+D, pulse-critical, fact-fill, smooth zoom, ↕ кнопка.
7. **Tests + e2e + lint**.

Детальный план задач — в follow-up плане после утверждения этого спека.
