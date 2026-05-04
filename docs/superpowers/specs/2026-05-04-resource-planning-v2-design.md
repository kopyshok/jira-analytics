# Resource Planning v2 — Design

**Дата:** 2026-05-04
**Статус:** approved (verbal), proceeding to plan
**Контекст memory:** `project_resource_planning_redesign_planned`, `project_gantt_phase3_shipped`, `project_resource_planning_fixes_shipped`

## Цель

Создать параллельный раздел «Планирование β» в боковом меню, использующий:
- готовую UI-библиотеку Gantt вместо самописного `GanttRows.tsx` (418 строк) и `DependencyArrows.tsx`,
- промышленный constraint-solver вместо самописного CPM/RCPSP-leveler.

Старый раздел `/resource-planning` остаётся нетронутым. Пользователь сравнивает оба раздела в течение ~1 месяца, выбирает победителя. Проигравший удаляется.

## Принципы редизайна

1. **Параллельность, не замена.** Оба раздела работают на одних и тех же данных, видны одновременно в меню.
2. **Защита данных.** Кнопка «Оптимизировать» в новом разделе всегда создаёт **копию плана** (форк) с пометкой `label='auto-PyJobShop'`. Оригинал не переписывается.
3. **Аддитивность.** Новый код — отдельная папка фронта + один новый эндпоинт бэка + один новый сервис. Удаление = `rm -rf` папки + drop одного эндпоинта + меню. Никаких миграций БД (схема общая).
4. **Метрика выбора победителя.** Тонкий блок «Качество расписания» в шапке обоих разделов: % перегруженных дней, число просрочек, среднее использование ёмкости. Видно одинаково.

## Решения по UX (зафиксированы)

| Вопрос | Решение |
|---|---|
| Один или несколько разделов | Два — старый «Ресурсное планирование» + новый «Планирование β» |
| Общие или раздельные планы | Общие, кнопка «Оптимизировать» создаёт защитный форк |
| Режимы графика в новом | Два: «По задачам» (с раскрываемыми фазами) + «По сотрудникам» |
| Сравнение версий | Отдельная страница `/resource-planning/compare` (уже существует) |
| Что меняет «Оптимизировать» | Исполнители + сроки внутри квартала. Не добавляет/убирает задачи из плана |
| Железные правила солвера | Все 6: роль, календарь сотрудника, заблокированные зоны, зависимости, ёмкость, приоритет проекта |
| Маркировка нового раздела | Бета-метка «β» рядом с пунктом меню |
| Куда переходит «Перейти к графику» из утверждённого сценария | В старый раздел (новый — только через клик в меню) |
| Критерий выбора победителя | Метрика качества видна в обоих разделах + субъективный фидбек |
| Что с проигравшим | Под флагом ещё месяц, потом полное удаление |

## Архитектурное решение — Approach B

**Общий бэк, новая страница спереди + один новый эндпоинт + один новый сервис.**

Бэкенд остаётся один. Добавляется:
- новый сервис `app/services/pyjobshop_solver_service.py` — обёртка над PyJobShop, читает существующие модели (`BacklogItem`, `Employee`, `ScenarioRule`, `ResourceBase`, `ProductionCalendarDay`, `Absence`, `BlockedZone`), возвращает `dict[backlog_item_id, {assignee_id, start_date, end_date}]`,
- новый эндпоинт `POST /api/v1/resource-plans/{plan_id}/optimize` — вызывает solver, создаёт форк плана со статусом `ready` и `label='auto-PyJobShop'`, возвращает новый `plan_id`,
- новый сервис `app/services/plan_quality_service.py` — считает метрику качества для любого плана (`overload_days_pct`, `late_count`, `mean_utilization_pct`); возвращает компактный dict; используется обоими разделами,
- новый эндпоинт `GET /api/v1/resource-plans/{plan_id}/quality` — возвращает метрику для конкретного плана.

Фронт получает:
- новую страницу `frontend/src/pages/ResourcePlanningV2Page.tsx` (роут `/resource-planning-v2`),
- новую папку компонентов `frontend/src/components/resource-planning-v2/` (на SVAR Gantt),
- общий компонент `frontend/src/components/resource-planning/PlanQualityBadge.tsx` (mounted в обеих страницах),
- пункт меню «Планирование β» в `Sider`.

Старая страница `/resource-planning` и её компоненты не трогаются вообще.

### Поток оптимизации

```
[Пользователь] → /resource-planning-v2?plan_id=X
   ↓
[UI «Оптимизировать»] → POST /resource-plans/X/optimize
   ↓
[PlanQualityService] измеряет качество X (для сравнения)
[PyJobShopSolverService] строит модель из BacklogItem + Employee + правил
   ↓
[ResourcePlanForker] создаёт копию X с label='auto-PyJobShop'
[Применяет результат solver] (assignee + start + end на каждый assignment)
   ↓
[PlanQualityService] измеряет качество новой копии
   ↓
return { new_plan_id, before: {...}, after: {...} }
   ↓
[UI] переключается на новый plan_id, показывает diff в шапке
```

## Стек выбранных библиотек

### Frontend — SVAR Gantt
- Пакет: `wx-react-gantt` (React-обёртка над Svelte-ядром).
- Лицензия: MIT.
- Что даёт: виртуализация (10k+ задач), drag-resize, нативные FS/SS/FF/SF зависимости.
- Что не даёт (и не нужно): критический путь, MS Project import — это уже есть в нашем CPM на бэке.
- Bundle: ~150-250 KB. Допустимо.
- Стилизация под dark theme `#0d1c33` через CSS-переменные SVAR (`--wx-gantt-...`).

### Backend — PyJobShop
- Пакет: `pyjobshop`.
- Лицензия: MIT.
- Под капотом: OR-Tools CP-SAT.
- Модель RCPSP: `Job` = BacklogItem, `Task` = одна phase (`analyst`/`dev`/`qa`/`opo`) этой инициативы (= одна строка `ResourcePlanAssignment`), `Resource` = Employee (renewable, capacity = available_hours per day).
- Constraints:
  - hard: skill match (роль = phase), employee calendar (отсутствия + production calendar), blocked zones, dependencies (precedence), capacity per day, project priority (как ordering первичной задачи через weight в objective), **respect `is_pinned=True`** (если строка закреплена вручную — не переназначаем employee_id),
  - soft: minimize total tardiness + minimize peak utilization (fairness).

## File Structure

**Backend (новые файлы):**
- `app/services/pyjobshop_solver_service.py` — solver wrapper.
- `app/services/plan_quality_service.py` — метрика качества.
- `app/api/endpoints/resource_planning_v2.py` — два новых эндпоинта (`POST /optimize`, `GET /quality`).
- `app/schemas/resource_planning_v2.py` — `OptimizeResponse`, `QualityMetric`.
- `tests/test_pyjobshop_solver_service.py` — unit-тесты solver на синтетических данных.
- `tests/test_plan_quality_service.py` — unit-тесты метрики.
- `tests/test_resource_planning_v2_endpoints.py` — integration тесты эндпоинтов.

**Backend (модификации):**
- `app/main.py` — подключить роутер `resource_planning_v2`.
- `requirements.txt` / `pyproject.toml` — добавить `pyjobshop>=0.0.8`.

**Frontend (новые файлы):**
- `frontend/src/pages/ResourcePlanningV2Page.tsx`.
- `frontend/src/components/resource-planning-v2/SvarGanttChart.tsx` — обёртка над `wx-react-gantt`, два режима (task / employee), маппинг наших данных → SVAR-формат.
- `frontend/src/components/resource-planning-v2/OptimizeButton.tsx` — кнопка + модалка прогресса + переключение на новый план.
- `frontend/src/components/resource-planning/PlanQualityBadge.tsx` — общий компонент, mounted в обеих страницах.
- `frontend/src/api/resourcePlanningV2.ts` — клиент для двух новых эндпоинтов.
- `frontend/src/hooks/useResourcePlanningV2.ts` — TanStack-хуки для оптимизации и метрики.
- `frontend/src/lazyPages.tsx` — добавить lazy import.
- `frontend/src/router.tsx` — добавить роут.
- `frontend/src/components/layout/Sider.tsx` или эквивалент — пункт «Планирование β» с тегом.

**Frontend (модификации):**
- `frontend/src/pages/ResourcePlanningPage.tsx` — добавить `<PlanQualityBadge plan_id={planId} />` в шапку (только это, остальное не трогаем).
- `frontend/package.json` — добавить `wx-react-gantt`.

## Data flow и контракт солвера

Солвер ничего не пишет в БД сам. Его обязанность — вернуть структуру:

```python
SolverResult = {
    "assignments": [
        {
            "backlog_item_id": str,
            "assignee_employee_id": str | None,  # None для пула (qa)
            "start_date": date,
            "end_date": date,
            "phase_breakdown": [  # один phase = один assignment row в текущей модели
                {"phase": "analyst" | "dev" | "qa" | "opo", "hours": float, "employee_id": str | None, "start_date": date, "end_date": date}
            ],
        },
        ...
    ],
    "infeasible_items": [str],  # backlog_item_id что не влезли (overflow → не назначены)
    "solver_status": "OPTIMAL" | "FEASIBLE" | "INFEASIBLE",
    "solve_time_ms": int,
}
```

Применение к плану: переиспользуем существующий fork-механизм (`POST /resource-plans/{id}/fork` → копия со всеми `ResourcePlanAssignment`), затем эндпоинт `optimize` перезаписывает `start_date`/`end_date`/`employee_id` каждой записи согласно SolverResult. `is_pinned` сохраняется из исходного плана. Закреплённые строки (где `is_pinned=True` в исходнике) солвер получает как фиксированные ассайны и не трогает.

## Метрика качества

```python
QualityMetric = {
    "plan_id": str,
    "overload_days_pct": float,    # % дней где сумма часов сотрудника > 110% его ёмкости
    "late_count": int,             # число задач с end_date > scenario.target_end_date
    "mean_utilization_pct": float, # средний % использования ёмкости команды
    "computed_at": datetime,
}
```

Считается из существующих таблиц (`ResourcePlanAssignment`, `Employee`, `ProductionCalendarDay`, `Absence`). Кэшируется в памяти процесса на 60 сек (один план редко открывают чаще).

## Поведение и состояния

**Шапка нового раздела:**
1. Выпадашка плана (как в старом).
2. Бейдж «Качество: 12% перегрузок · 3 просрочки · 78% утилизации» (PlanQualityBadge).
3. Кнопка **«Оптимизировать»** — primary, disabled когда план уже `auto-PyJobShop` (запрет цепочки оптимизаций без пересоздания базы).
4. Кнопка «Сделать копию» (как в старом).
5. Переключатель режима «По задачам / По сотрудникам».
6. Тег «β» рядом с заголовком.

**Поток «Оптимизировать»:**
1. Клик → модалка «Запускаю солвер... может занять до 30 сек».
2. Backend синхронно: измеряет старый план, запускает PyJobShop (timeout 30 сек), создаёт форк, применяет результат, измеряет новый.
3. Возвращает `{ new_plan_id, before: QualityMetric, after: QualityMetric }`.
4. Фронт показывает диалог «Готово. Качество улучшилось на X% / ухудшилось / не изменилось. Открыть новый план?» с кнопками «Открыть» и «Отмена».
5. «Открыть» → переключается на `new_plan_id` (URL `?plan_id=new`).

**Если солвер вернул INFEASIBLE:**
- Форк не создаётся.
- Сообщение «Невозможно построить расписание под текущие правила. Слишком жёсткие ограничения или не хватает ёмкости.» + список первых 5 проблемных задач.

## Тестирование

**Backend:**
- `test_pyjobshop_solver_service.py` — синтетические сценарии: 2 сотрудника / 5 задач, проверка соблюдения каждого hard rule по очереди, проверка возврата INFEASIBLE при перегрузке.
- `test_plan_quality_service.py` — вручную составленные планы, проверка формул метрики (1 перегруженный день из 10 = 10%, и т.д.).
- `test_resource_planning_v2_endpoints.py` — integration: создать план, optimize → новый план, проверить что данные форка соответствуют.

**Frontend:**
- Smoke-тест роута `/resource-planning-v2` через Playwright (`e2e/resource-planning-v2.spec.ts`).
- Manual visual check на dark theme.

**Не тестируем:**
- Производительность solver на >100 задачах в этой итерации (пометить как known limitation, померить и решить позже).
- Cross-browser SVAR (доверяем библиотеке).

## Известные ограничения и риски

- **SVAR React wrapper** — Svelte под капотом. Хитрая интеграция с React 19 lifecycle. Риск: SSR/hydration warnings. Митигация: только client-side рендер (`'use client'` не нужен в Vite, но проверить динамическую загрузку).
- **PyJobShop solver time** — на 100 задачах × 20 сотрудниках может уходить >30 сек. Митигация: timeout с graceful fallback на «частичное решение» (FEASIBLE). Если стабильно >30s — переносим в фоновый воркер (вне scope этой итерации).
- **Метрика кэширования** — invalidate на `entity_changed: ResourcePlan`. Мелочь, но про неё легко забыть.
- **Бета-юзеры** — поскольку оба раздела видны всем, нужен короткий tooltip на бете «Экспериментальная версия. Старая остаётся доступной».

## Критерий приёмки v2

После 1 месяца параллельной работы пользователь решает:
- если новый раздел оставляет — переименовать «β» в дефолтный, перенаправить старый роут на новый, удалить старую папку через ещё неделю,
- если старый раздел оставляет — удалить новую папку (один коммит-revert), снести пакет PyJobShop из dependencies, снести wx-react-gantt из package.json.

## Out of scope

- Замена `/scenario-comparator` (используем как есть).
- Изменение схемы `BacklogItem` / `Employee` / `ResourcePlan` / `ResourcePlanAssignment`.
- Поддержка >100 задач в одной оптимизации.
- Персонализация какой раздел показывать какому юзеру (всем сразу).
- A/B-телеметрия (выбор делается субъективно + по метрике, не по аналитике).
