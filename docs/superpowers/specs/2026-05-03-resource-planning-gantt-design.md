# Resource Planning Gantt — Design Spec

## Контекст

Новый раздел «Ресурсное планирование» — инструмент для квартального планирования загрузки команды на базе утверждённых инициатив. Надстраивается поверх существующего `PlanningScenario` / `BacklogItem`, не заменяет их.

**Ключевые принципы:**
- На момент утверждения квартала задачи Jira ещё не созданы — планирование строится на оценках трудозатрат по ролям
- Один аналитик + один программист закрепляются за каждой инициативой
- Фазы выполняются строго последовательно: Анализ → Разработка → Тестирование → ОПЭ
- Аналитик работает конвейером: сдал часть анализа программисту → перешёл на следующую инициативу
- Частичная сдача (декомпозиция) автоматически при заблокированных периодах или нехватке ёмкости

---

## 1. Архитектура

### 1.1 Место в системе

```
PlanningScenario (approved)
        ↓  кнопка «Открыть диаграмму»
ResourcePlan  ←→  ResourcePlanningPage (/resource-planning)
        ↓
Scheduling Engine → ResourcePlanAssignment (даты фаз)
        ↓
Gantt UI (3 вида × 3 режима фаз)
```

Новая страница `/resource-planning` доступна из бокового меню. Кнопка перехода из утверждённого сценария создаёт `ResourcePlan`, связанный со сценарием.

### 1.2 Поэтапная сборка

| Этап | Содержание | Срок |
|---|---|---|
| **Phase 1 — MVP** | Фазовый планировщик: ScheduledBlock, ResourcePlan, движок расписания, вид A (Portfolio) + вид B (Two-level), стрелки внутри инициативы | ~6 нед |
| **Phase 2 — Jira tasks** | Вид C (ресурсный трек), межинициативные стрелки, задачи Jira внутри фаз, CPM по реальным задачам | ~+6 нед |
| **Phase 3 — Full CPM** | RCPSP-разравнивание, конфликт-детектор, what-if сценарии, вероятностный CPM | ~+8 нед |

---

## 2. Data Model

### 2.1 Новые таблицы

#### `resource_plans`
```
id              String(36) PK
scenario_id     String(36) FK → planning_scenarios (nullable — план без сценария)
team            String(100)
quarter         String(10)   e.g. "Q2"
year            Integer
status          String(16)   draft | computing | ready | stale
computed_at     DateTime
created_at / updated_at
```

#### `resource_plan_assignments`
```
id              String(36) PK
plan_id         String(36) FK → resource_plans
backlog_item_id String(36) FK → backlog_items
phase           String(16)   analyst | dev | qa | opo
employee_id     String(36) FK → employees (nullable — роль без конкретного человека)
part_number     Integer      1..N — для частичной сдачи (split)
hours_allocated Float
start_date      Date
end_date        Date
is_on_critical_path Boolean  default False
slack_days      Float        nullable
created_at / updated_at
```

#### `scheduled_blocks`
```
id              String(36) PK
team            String(100) nullable  — если null, применяется ко всем командам
role_id         String(36) FK → roles (nullable — если null, применяется ко всем ролям)
employee_id     String(36) FK → employees (nullable — если null, применяется к роли/команде)
start_date      Date
end_date        Date
reason          String(255)
created_at / updated_at
```

#### `plan_item_dependencies` (Phase 2+)
```
id              String(36) PK
plan_id         String(36) FK → resource_plans
from_item_id    String(36) FK → backlog_items
to_item_id      String(36) FK → backlog_items
dep_type        String(4)    FS | SS | FF | SF
lag_days        Integer      default 0
source          String(16)   manual | inferred
```

### 2.2 Использование существующих таблиц

| Существующая | Роль в Gantt |
|---|---|
| `BacklogItem` | Инициатива = узел Gantt верхнего уровня. `estimate_analyst_hours`, `estimate_dev_hours`, `estimate_qa_hours`, `estimate_opo_hours` → длительность фаз |
| `PlanningScenario` | Список утверждённых инициатив. `approved` статус = вход для создания `ResourcePlan` |
| `ScenarioAllocation` | Какие `BacklogItem` включены в сценарий |
| `Employee` + `Role` | Ресурсный пул |
| `Absence` | Вычитается из доступности при расчёте расписания |
| `ProductionCalendarDay` | Рабочие/нерабочие дни, часы |
| `ResourceBaseService` | Уже считает посуточную доступность — переиспользуется |

---

## 3. Движок расписания

### 3.1 Алгоритм (Phase 1 — фазовый)

```
Входы:
  - список инициатив из сценария (с оценками по ролям и приоритетами)
  - пул сотрудников команды с ролями
  - производственный календарь
  - отсутствия
  - заблокированные периоды (ScheduledBlock)

Шаги:
1. Построить посуточный календарь доступности для каждого сотрудника:
   available_hours[employee][date] = calendar_hours − absence_hours − block_hours

2. Отсортировать инициативы по приоритету (BacklogItem.priority)

3. Назначить аналитика на каждую инициати��у:
   - Greedy: выбрать аналитика с наименьшей суммарной нагрузкой на квартал
   - PM может переопределить вручную

4. Назначить программиста на каждую инициати��у (аналогично)

5. Построить расписание фаз — для каждой инициативы:
   a. Фаза "Анализ": 
      - Найти ближайшее окно у назначенного аналитика
      - Проверить: есть ли blocked period внутри окна → split если нужно
      - Записать: start_date, end_date, part_number (1 или 2)
   b. Фаза "Разработка":
      - ES = max(end_date последней части анализа, ближайшее окно программиста)
      - Разложить hours на рабочие дни программиста от ES
   c. Фаза "Тестирование": ES = end_date Разработки
   d. Фаза "ОПЭ": ES = end_date Тестирования
   e. Если конец ОПЭ > end_of_quarter → пометить: "не вошло в квартал"

6. Детектировать конфликты:
   - Перегрузка ресурса (>100% в день)
   - Инициативы не умещающиеся в квартал

7. Сохранить ResourcePlanAssignment записи
```

### 3.2 Конвейерная логика (pipeline)

Аналитик назначается на следующую инициативу сразу после завершения анализа предыдущей (или первой части при split). Программист стартует как только есть хоть один batch от аналитика.

```
Timeline:   W1    W2    W3    W4    W5    W6    W7
Аналитик:  [ИН-01 анализ p1][блок][ИН-01 p2][ИН-02 анализ]
Программист:          [ИН-01 разработка          ][ИН-02 разр.]
```

### 3.3 Декомпозиция (split)

Триггер: `available_hours_before_next_block < remaining_analysis_hours`

Результат: создаются две `ResourcePlanAssignment` записи с `part_number=1` и `part_number=2`.
Программист получает задачи после `part_number=1`.

### 3.4 CPM (Phase 3)

После появления реальных Jira-задач:
- AON DAG по зависимостям `blocks/is_blocked_by` из Jira
- Forward pass: `ES_i = max(predecessor_finish + lag, project_start)`
- Backward pass: `LF_i = min(successor_start − lag, project_end)`
- `Total Slack = LS − ES`; критический путь = задачи с `slack ≤ 0`
- Инкрементальный пересчёт по closure при изменении задачи

---

## 4. API

### 4.1 Новые эндпоинты `/resource-planning`

```
POST   /resource-plans                    создать план (из сценария или пустой)
GET    /resource-plans                    список планов (team filter)
GET    /resource-plans/{id}               план + статус
DELETE /resource-plans/{id}

POST   /resource-plans/{id}/compute       запустить движок расписания (SSE прогресс)
GET    /resource-plans/{id}/gantt         проекция для Gantt UI (все assignments + arrows)
GET    /resource-plans/{id}/conflicts     список конфликтов

GET    /resource-plans/{id}/assignments
PATCH  /resource-plans/{id}/assignments/{aid}   ручное переопределение дат/исполнителя

GET    /scheduled-blocks                  список блокировок (team, role, employee фильтры)
POST   /scheduled-blocks                  ��оздать
PATCH  /scheduled-blocks/{id}
DELETE /scheduled-blocks/{id}
```

### 4.2 Изменения в существующих эндпоинтах

`GET /planning/scenarios/{id}` → добавить поле `resource_plan_id` (nullable) в ответ.
`POST /planning/scenarios/{id}/approve` → создавать `ResourcePlan` в статусе `draft` автоматически.

---

## 5. Frontend

### 5.1 Структура страницы

```
ResourcePlanningPage (/resource-planning)
  ├── PlanSelector        — выбор плана (dropdown по team/quarter)
  ├── PlanToolbar         — Пересчитать / Экспорт / Настройки
  ├── ViewSwitcher        — Portfolio | Two-level | Resource track
  │                          + Phase display: Single bar | Sub-rows
  ├── GanttChart          — основной компонент
  │    ├── TimelineHeader  — месяцы + недели
  │    ├── GanttRows       — виртуализированный список строк
  │    ├── BlockedZones    — серые overlay-зоны ScheduledBlock
  │    ├── TodayMarker     — вертикальная линия
  │    └── DependencyArrows — SVG overlay
  └── ConflictPanel       — список конфликтов (collapsible)
```

### 5.2 Режимы просмотра

**View A — Portfolio (инициативы)**
- 1 строка на инициативу
- Бар = весь срок инициативы (от start_date первой фазы до end_date последней)
- Цветные сегменты внутри бара по фазам
- Под Gantt: heatmap загрузки по ролям × недели

**View B — Two-level (инициативы + фазы)**
- Строка-заголовок инициативы (сворачивается)
- 4 дочерних строки: Анализ / Разработка / Тест / ОПЭ
- Каждая строка показывает бар фазы с именем исполнителя
- Split-фазы: два бара одного цвета с пунктирной связью между ними

**View C — Resource track (по сотрудникам)** *(Phase 2)*
- Группировка по сотруднику
- Все фазы сотрудника — цветные бары, окрашенные по инициативе
- Заблокированные периоды видны как серые зоны

### 5.3 Gantt компонент

Реализация — кастомная, без внешней Gantt-библиотеки:
- Список строк: `rc-virtual-list` (уже в AntD) для виртуализации 1000+ строк
- Бары: `div` с `position: absolute` + CSS `left/width` вычисляются из дат
- Стрелки: SVG overlay поверх timeline, рисуются после layout (bezier curves)
- Заблокированные зоны: `div` с полупрозрачным серым фоном, z-index под барами

### 5.4 Стрелки зависимостей

**Intra-initiative (внутри инициативы):**
- Анализ END → Разработка START (FS, cyan)
- Разработка END → Тест START (FS, orange)
- Тест END → ОПЭ START (FS, green)

**Inter-initiative relay (между инициативами, Phase 2):**
- Аналитик: конец анализа ИН-01 → начало анализа ИН-02 (тонкая пунктирная линия цвета роли)
- Стрелки скрываемы по toggle

Стиль: bezier кривые с маркером-стрелкой, цвет = цвет фазы источника, thickness 1.5px.

### 5.5 Заблокированные периоды

Серая полупрозрачная вертикальная полоса на timeline с подписью «Закрытие месяца» (ротация 90°). Управляются в отдельном разделе «Настройки → Заблокированные период��» внутри ResourcePlanningPage (не в общих настройках).

### 5.6 Интеграция с PlanningPage

На `PlanningPage` в карточке утверждённого сценария: кнопка «Открыть диаграмму» → `navigate('/resource-planning?plan_id=...')`. Если `ResourcePlan` ещё не создан → создаётся автоматически при переходе.

---

## 6. Конфликты и предупреждения

| Тип | Описание | Severity |
|---|---|---|
| `OVERLOAD` | Сотрудник назначен на >100% в рабочий день | critical |
| `QUARTER_OVERFLOW` | Инициатива не вмещается в квартал | critical |
| `NO_ANALYST` | Нет доступного аналитика для инициативы | critical |
| `NO_DEV` | Нет доступного программиста | critical |
| `LATE_START` | Фаза стартует позже целевой даты | warning |
| `SPLIT_REQUIRED` | Частичная сдача потребовалась для вписывания в квартал | info |

ConflictPanel: список конфликтов с кликом → подсветка конкретных строк на Gantt.

---

## 7. Миграции

- `migration_040_scheduled_blocks.py`
- `migration_041_resource_plans.py`
- `migration_042_resource_plan_assignments.py`
- `migration_043_plan_item_dependencies.py` *(Phase 2)*

---

## 8. Edge Cases

1. Инициатива без оценок → помечается `NO_ESTIMATE`, пропускается движком
2. Команда без аналитика → конфликт `NO_ANALYST` на все её инициативы
3. Все аналитики в отпуске одновременно → `OVERLOAD` или `QUARTER_OVERFLOW`
4. Split на 3+ части (несколько блоков внутри фазы) → поддерживается через `part_number`
5. ОПЭ без даты конца (open-ended) → фиксированная длительность = `estimate_opo_hours / 6h`
6. Два плана для одного сценария → запрещено, один сценарий → один активный план
7. Concurrent edit плана → optimistic lock через `updated_at`

---

## 9. Нереализованные в этом спеке (будущие этапы)

- EVM (Earned Value)
- Вероятностный CPM / Monte-Carlo
- What-if сценарии для «что если нанять человека»
- Экспорт в MS Project XML
- Webhook-driven replanning (пересчёт при изменении задач в Jira)
