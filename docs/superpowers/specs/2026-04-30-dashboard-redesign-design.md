# Dashboard Redesign — Design Spec

**Date:** 2026-04-30
**Scope:** редизайн трёх виджетов на странице `/dashboard`
**Mockups:** `.superpowers/brainstorm/49-1777526199/content/`

## Goal

Текущий дашборд выглядит пустым. Виджеты не показывают всю доступную картину: «Проекты квартала» полупустой, «Нормированные работы» агрегирует на уровне команды без разреза по людям, «Ворклоги по категориям» не заполняет отведённое пространство (плитки сжимаются с пустыми краями).

Этот редизайн:
1. Уплотняет «Проекты квартала» — KPI, тренды, дедлайны, прогноз.
2. Превращает «Нормированные работы» в инструмент контроля по сотрудникам, разбитый по 4 ролям.
3. Чинит «Ворклоги по категориям» — равномерная сетка-теплокарта, заполняющая всю площадь.

## Widget 1 — Проекты квартала

### Layout

Полная ширина (один `<Col xs={24}>`). 4-колоночная сетка внутри карточки:

```
grid-template-columns: 220px 1fr 280px 280px; gap: 20px
```

| Колонка | Содержимое |
|---|---|
| 1 (220px) | Donut + легенда (4 строки) |
| 2 (1fr) | Список всех проектов квартала |
| 3 (280px) | KPI 2×2 |
| 4 (280px) | Активность по неделям (спарклайны) |

### Колонка 1 — Donut

SVG-донут 180×180. 4 arc-сегмента с зазором ~2°, инвариант: суммируются в 360°. Внутренняя «дырка» — тёмный круг радиуса 56 поверх (bg `#0f2340`).

Сегменты:
- Выполнены — зелёный `#67d68d`
- В работе — cyan `#00c9c8`
- Просрочены — red `#ff4d4f`
- **Не начаты** — серый `#7e94b8` (исправить — сейчас тёмно-синий, сливается с фоном)

В центре: число проектов (32px bold) + подпись «проектов» (12px muted).

Под донутом — 4 строки легенды: цветной dot + счётчик (14px bold) + подпись «Выполнены/В работе/Просрочены/Не начаты».

Блок «Прогноз к концу квартала: N (XX%)» **удаляется** — мигрирует в KPI 2×2 (тайл «Закроются в срок»).

### Колонка 2 — Список проектов

10-колоночная сетка строк:
```
12px minmax(220px,1.3fr) 70px 70px 95px 75px 85px 1fr 80px 50px
```

| Колонка | Поле |
|---|---|
| 12px | Status dot (цвет статуса) |
| title (1.3fr) | Название проекта + бейдж (тишина / +N ч / зачёркнут если done) |
| 70px | Подзадачи: текст «N/M» + мини-бар 50×5px заливкой по статусу |
| 70px | Команда: до 3 overlapping initial circles 24×24, +N badge |
| 95px | **Срок** (новое): дата + дельта дней. Цвета: зелёный (>7д), жёлтый (≤7д), красный (просрочено), серый «—» если нет |
| 75px | **Тренд** (новое): часы за последние 7д + стрелка. ↑ зелёный (растёт), ↓ жёлтый (падает), · серый (тишина) |
| 85px | **Прогноз** (новое): расчётная дата закрытия. «к 12 авг» зелёный (в квартале), «к 30 окт ⚠» красный (выходит за квартал), «—» серый, «завершён» для done |
| 1fr | Прогресс-бар 12px толщиной (был 6-8) |
| 80px right | Факт / План часы |
| 50px right | % колор по статусу |

Header строка: «Проект | Подзадачи | Команда | Срок | Тренд | Прогноз | Прогресс | Факт / План | %» (12px uppercase muted).

Бейдж «тишина 28д» — жёлтый. Бейдж «+15 ч» (overrun) — красный. Done — title strikethrough.

Click по строке — переход на `/analytics?project={key}` (как сейчас).

### Колонка 3 — KPI 2×2

Сетка `grid-template-columns: 1fr 1fr; gap: 10px`. Каждый тайл: bg `#0a1d3a`, border `#1c3358`, rounded 8px, padding ~12px, ~150×85.

| Тайл | Значение | Подпись |
|---|---|---|
| Всего фактом | `340 ч` (32px white) | «из 780 план» (13px muted) |
| Средняя загрузка | `44%` (32px cyan, цвет по статусу) | «факт / план» (13px muted) |
| Молчат >14 дней | `4` (32px yellow) | «проекта без активности» (13px muted) |
| Закроются в срок | `2` (32px green) | «(25%) прогноз по темпу» (13px muted) |

### Колонка 4 — Активность по неделям

Card-like подпанель: bg `#0a1d3a`, border `#1c3358`, padding 14px, rounded 8px.

- Header «АКТИВНОСТЬ ПО НЕДЕЛЯМ» (12px uppercase 0.06em muted)
- 6 строк: title (110px, 14px text) + SVG-спарклайн (flex:1, height 24px)
- 8 точек на спарклайн, polyline с `vector-effect: non-scaling-stroke; preserveAspectRatio: none`
- Активные: цветная сплошная линия (cyan/red/green по статусу)
- Тихие: пунктирная серая `#2a4060` (стиль `stroke-dasharray: 3 3`)

### Удалено

- Блок «Требует внимания» — удаляется целиком (не несёт ценности без плановых дат)
- Блок «Перебор по часам» — удаляется (часть данных переехала в Срок/Тренд/Прогноз и KPI)

### Backend — что нужно от API

Endpoint `GET /analytics/dashboard/projects?year&quarter&month`. Текущий contract:

```ts
{
  total, done, in_progress, overdue, not_started,
  forecast_done, forecast_pct,
  attention_list: [...],   // удаляется
  overrun_list: [...]       // удаляется
}
```

Новый contract:

```ts
{
  total, done, in_progress, overdue, not_started,
  total_fact_hours: float,         // Σ факт по проектам (для KPI)
  total_plan_hours: float,         // Σ план
  avg_load_pct: float,             // средняя загрузка факт/план
  silent_count: int,               // молчат >14 дней
  forecast_done: int,
  forecast_pct: float,
  projects: [
    {
      issue_key: str,
      title: str,
      status_category: 'done' | 'in_progress' | 'new' | 'overdue',
      plan_hours: float,
      fact_hours: float,
      delta_hours: float,
      subtasks_done: int,
      subtasks_total: int,
      assignees: [{ initials: str, color: str }],   // top-3 + остальное в total
      assignees_total: int,
      due_date: date | null,
      days_to_due: int | null,                       // negative = overdue
      trend_hours_week: float,                       // часы за последние 7 дней
      trend_dir: 'up' | 'down' | 'flat',
      forecast_close_date: date | null,
      forecast_in_quarter: bool,
      silent_days: int,                              // дни с последнего ворклога
      weekly_activity: [float, ...]                  // 8 точек для спарклайна (часы/неделя)
    }
  ]
}
```

«Срок» — берём `Issue.due_date`. Если null — показываем «—». **Заметка:** дедлайны в Jira пока не у всех проектов; виджет работает с null-значением корректно.

«Тренд» — Σ ворклогов за последние 7 дней + сравнение с предыдущей 7-дневкой для направления.

«Прогноз» — линейная экстраполяция по фактическому темпу: если `fact/plan = X` и прошло Y дней квартала, дата закрытия = `start + plan_hours / (fact_hours / Y)`.

«Activity» — 8 буханок ворклогов (по 1 неделе каждая, с конца квартала назад). Берём 6 эпиков с наибольшим `fact_hours` в квартале.

## Widget 2 — Нормированные работы

### Pivot

Текущий виджет: команда-уровень, горизонтальные bullet-bars по видам работ (Анализ/Разработка/Тестирование/Тех.долг/Орг). Полупустой при 5 видах работ на половине ширины.

Новый виджет: **per-employee, full page width**. 4 колонки — по одной на роль. Внутри каждой роли — все её сотрудники с раскрытой разбивкой по видам работ.

### Layout

Полная ширина. Карточка `<Col xs={24}>` (один ряд, не два полу-карточных). Внутри:

```
grid-template-columns: repeat(4, 1fr); gap: 16px
```

Если экран узкий (`<lg`), колонки складываются вертикально (по 2 / по 1).

### Колонка роли — структура

4 колонки, фиксированный порядок:

1. Аналитики — цвет роли cyan `#00c9c8`
2. Программисты — blue `#1890ff`
3. Консультанты — purple `#722ed1`
4. Руководитель проектов — orange `#fa8c16`

Цвета берутся из `Role.color` если есть; fallback на эту палитру по `code`.

**Header колонки** (sticky внутри карточки если scroll):
- bg `#0a1d3a`
- border-bottom `2px solid` цветом роли
- padding 12px, rounded-top 8px
- Layout:
  - Top line: `▼ icon + dot цветом роли (10×10) + Имя роли (16px bold) + N чел. (smaller muted)`
  - Bottom line (single-line summary): «Σ план N ч · Σ факт M ч · средн X%». X% colored по статусу.

**Список сотрудников** под header. Каждый сотрудник — блок:

#### Section 1 — Header строка сотрудника

`grid-template-columns: 28px 1fr auto; gap: 8px; align-items: center`
- Avatar 24×24 circle, bg = role color, white initials (e.g. «ИА»)
- Имя 14px (truncate ellipsis)
- Right end: `%` 14px bold colored (по порогам), затем «...» menu icon

#### Section 2 — Plan/fact bullet bar

Высота 14px, bg `#1c3358`, rounded 7px. Структура (как в текущем виджете):
- Filled segment: `width = (fact / plan) * 66%`, цвет статуса
- Overrun segment если `fact > plan`: `width = ((fact - plan) / plan) * 66%`, начало с 66%, bg red `#ff4d4f`
- Vertical target line на 66% (white, 2px wide, top -3 bottom -3) — целевая 100% метка
- Под баром: «факт N ч · план M ч» (12px muted)

#### Section 3 — Разбивка по видам работ

Всегда раскрыта (без collapse — пользователь хочет видеть всё сразу). Margin-left 12px (отступ).

Список строк, каждая 22px высотой:
- `grid-template-columns: 1fr auto 60px; gap: 8px; align-items: center`
- Work type label (12px, color `#a4b8d8`)
- Mini bar: 50px × 5px, bg `#1c3358`, fill = `(fact_wt / plan_wt) * 100%`, цвет = status (по тому же порогу)
- `N/M` (11px muted) right-align

Разделитель между сотрудниками: `border-bottom: 1px solid rgba(28,51,88,.5); padding-bottom: 12px`.

### Cветовые пороги

Берём 1:1 из текущего виджета:
- `warnAbove = 110%` (красный: перегруз)
- `underBelow = 70%` (зелёный: ниже = норма; жёлтый между underBelow и warnAbove; красный выше)
- Шестерёнка в правом верхнем углу карточки → модалка с InputNumber'ами на оба порога. Сохранять локально (state в компоненте), как сейчас.

Применять пороги ко **всем** % меткам: общий % сотрудника, % разбивки по виду работ, средн% в header колонки.

### Backend

Расширяем `GET /analytics/dashboard/norm-work?year&quarter&month&teams` так, чтобы возвращало per-employee детализацию:

```ts
{
  roles: [
    {
      role_code: str,
      role_label: str,
      role_color: str,
      employees_count: int,
      total_plan: float,
      total_fact: float,
      total_pct: float,
      employees: [
        {
          employee_id: str,
          name: str,                      // «Иванова А.С.»
          initials: str,                  // «ИА»
          plan_hours: float,
          fact_hours: float,
          pct: float,
          work_types: [
            {
              work_type_id: str,
              label: str,
              plan_hours: float,
              fact_hours: float,
              pct: float
            }
          ]
        }
      ]
    }
  ]
  // top-level totals остаются для card title если нужны
  total_plan: float,
  total_fact: float,
  total_pct: float
}
```

`teams` — респектится как сейчас (фильтрация сотрудников по командам).

`employees` сортировка: по убыванию `pct` (сначала перегруженные → самые загруженные сверху).

«Роли вне 4-х основных» (если в БД есть другие через `Role` registry) — тоже выводятся, добавляются как доп. колонки. Если нет — рендерим только эти 4.

### Удалённые элементы

- Текущий top-level summary в title (Σ план / Σ факт / Загрузка X%) — переезжает в каждую колонку роли (Σ по роли). Общий Σ может остаться в title карточки как дополнение.
- Top-level bullet-bars по видам работ (Анализ/Разработка/...) — удалены. Эта инфо теперь распределена по сотрудникам.

## Widget 3 — Ворклоги по категориям задач

### Fix

Текущий: flex-wrap квадратики не заполняют отведённую площадь. Решение: **fixed grid 5×2 heatmap** заполняющая контейнер целиком.

### Layout

Полу-ширина (`<Col xs={24} lg={12}>`, как сейчас). Внутри карточки:

```
grid-template-columns: 60% 40%; gap: 16px
```

Левая часть (60%) — heatmap grid. Правая (40%) — meta table (сохраняется как сейчас).

### Heatmap

```
grid-template-columns: repeat(5, 1fr); gap: 6px
grid-auto-rows: minmax(140px, 1fr)
```

5 столбцов × 2 строки = **10 ячеек** (под 10 текущих категорий). Если категорий >10 — последняя ячейка «+N остальных» с тултипом списка.

Каждая ячейка — фиксированный размер (равные), bg `${color}33`, border `1px solid ${color}66`, rounded 8px, padding 12px.

Содержимое ячейки:
- Top: label категории (12px, color `#a4b8d8`, ellipsis)
- Center: hours число (24px bold white)
- Right top corner: pill-badge с `%` (10px, bg = категория color, white text)
- Bottom small: meta `N wl · M зад · K чел.` (10px, color `#7e94b8`)
- Bottom: тонкая прогресс-полоска с заливкой по `pct` шкале интенсивности (cyan saturation gradient)

### Summary strip

Под heatmap (полная ширина левой части): Σ часов · Σ ворклогов · Σ задач · X категорий · средн.мин/wl. 12px muted.

### Meta table (right side, 40%)

Без изменений: текущая таблица 7 колонок (Категория · Часы · Ворклоги · Задачи · Сотрудники · Ср.мин · %) + строка «Итого».

## Common Concerns

### Multi-user / team filter

Виджет 1 (`/dashboard/projects`): в текущей версии endpoint **не принимает** team filter (сценарий привязан к одной команде). Сейчас глобальный team filter применяется только к виджетам 2 и 3. Оставляем эту логику — не расширяем.

Виджеты 2, 3: глобальный team filter (`useGlobalTeamFilter().queryParams`) подмешивается в query — как сейчас.

### Performance

Виджет 2 — самый тяжёлый: 14+ employees × 5 work_types = ~70 строк. Pure render OK. Backend — один endpoint, JOIN по сотрудникам/ролям/work_types/worklogs. Если N+1 — батчим.

Виджет 1 — 8-15 эпиков × spark line (8 точек). Ворклоги за квартал по эпикам и их детям — один запрос с GROUP BY по неделям.

Виджет 3 — без изменений по нагрузке.

### Reactivity

Все 3 виджета должны реагировать на смену quarter / team filter (TanStack Query hooks с теми же ключами). При sync events `entity_changed` (worklogs / scenarios / employees) — invalidate.

## Out of Scope

- Drag-and-drop / реордеринг проектов
- Drilldown в задачи внутри эпика по клику
- Экспорт виджетов в xlsx/pdf (текущий ExportButtons остаётся, формат экспорта не меняется)
- Per-employee drilldown из виджета 2 (клик на имя — открывает страницу /capacity?employee=X) — на следующей итерации
- Settings UI для цветов категорий (уже планируется отдельной задачей `project_user_color_settings_planned`)

## Implementation Notes

### Frontend

- `frontend/src/components/dashboard/ProjectsWidget.tsx` — переписать
- `frontend/src/components/dashboard/NormWorkWidget.tsx` — переписать
- `frontend/src/components/dashboard/CategoryWidget.tsx` — переписать
- `frontend/src/types/api.ts` — обновить типы под новые contracts

### Backend

- `app/services/analytics_service.py` — расширить:
  - `get_dashboard_projects()` — добавить subtasks, assignees, due_date, trend, forecast_close, weekly_activity, total_fact/plan, avg_load, silent_count
  - `get_dashboard_norm_work()` — добавить per-employee группировку по ролям
- `app/schemas/dashboard.py` — обновить response models
- `app/api/endpoints/analytics.py` — без изменений в сигнатурах

### Tests

- Pytest: новые поля в response для всех 3 endpoint'ов
- Frontend: Playwright e2e на dashboard — проверить что 4 колонки рендерятся, donut виден, heatmap-сетка 5×2

## Open Questions

Нет.
