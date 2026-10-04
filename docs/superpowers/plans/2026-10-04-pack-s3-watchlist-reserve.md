# Поток 3: список наблюдения, честные кандидаты, часы других команд в запасе — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Техкоманда видит загрузку людей других команд («Наблюдаемые» в «Загрузке по дням»), выбирает исполнителя фазы по честным свободным часам, а часы других команд в «Загрузке по дням» подписаны тем, из какого запаса основной команды они берутся.

**Architecture:** Одна функция загрузки за квартал `normed_reserve.people_loads` (запас основных команд → `place_person`) — ей пользуются люди плана (диаграмма), наблюдаемые (новый эндпоинт) и кандидаты фазы. `PersonLoad` получает свободные часы по дням, `PersonReserve` — часы других команд по видам работ и задачи → вид. Список наблюдения — таблица `resource_plan_watch`, эндпоинты GET/POST/DELETE, событие шины как у других правок плана; фронт кладёт список под ключ `['gantt', planId, 'watch']`, поэтому все существующие инвалидации диаграммы (событие «resource_planning», отсутствия, личные настройки) обновляют и его.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic (batch), pytest; React 19 + AntD 6 + TanStack Query, vitest.

Спека: `docs/superpowers/specs/2026-10-04-q4-improvements-pack-design.md`, раздел «Поток 3». Фон: `2026-09-28-normed-works-reserve-design.md`, `2026-09-30-guest-normed-works-scenario-design.md`.

**Решения по неясным местам спеки (зафиксированы здесь):**
- Наблюдаемый считается тем же путём, что человек плана: брони опорных планов всех команд, кроме команды плана, + часы **этого** плана (если план — опорный, это те же брони). Для показа слоёв часы основной команды человека переносятся в нижний «свой» слой (как у людей плана — задачи своей команды), остальные — «другие команды». Сумма дня и раскладка нормированных работ не меняются.
- «X из Y ч» в подписи — занято запаса вида роли (заблокировано + другие команды) из заложенного, как столбец «Занято» в сводке.
- Кандидаты фазы: брони опорных планов всех команд, кроме броней этой самой фазы (той же задачи и фазы в команде плана) — иначе нынешний исполнитель выглядит занятым собственной фазой. Кандидаты строки сценария не меняются.

---

### Task 1 (3.3): автопроверка примера пользователя

**Files:** Test: `tests/api/test_rp_reserve_cross_team_example.py`

- [ ] Команда «Склад»: один разработчик, I кв. 2026 (512 ч), правило «Технические задачи» 19,53125% → заложено ровно 100 ч, плюс «Орг. вопросы» 10%. Команда «Техкоманда»: утверждённый сценарий, бронь разработчика 80 ч (16 будней по 5 ч).
- [ ] Проверки по диаграмме плана «Склада»: строка запаса — заложено 100, другие команды 80, осталось 20, перерасхода нет; загрузка квартала человека (`quarter.pct`, сумма часов) та же, что без брони; предупреждения `NORMED_OVERUSE` нет.
- [ ] Бронь 130 ч (26 будней по 5 ч) → перерасход 30, осталось 0; живое предупреждение `NORMED_OVERUSE` с `metric_value` 30 и текстом «Разработчик · Технические задачи: заложено 100 ч, другие команды заняли 130 ч»; загрузка выросла ровно на 30 ч.
- [ ] Прогнать. Падает — это ошибка в коде: найти причину, исправить, отметить в отчёте. Commit.

### Task 2 (3.3): часы других команд по видам у человека — сервис и диаграмма

**Files:** Modify `app/services/normed_reserve.py`, `app/api/endpoints/resource_planning.py`; Test: `tests/services/test_normed_reserve.py`, `tests/api/test_rp_normed_reserve_gantt.py`

- [ ] Тест сервиса: `PersonReserve.other_teams == {tech: 180}`, `PersonReserve.other_items == {item.id: tech}`; с выбором вида у задачи — переезжает; `merge_person` складывает; `TeamReserve.cross_team_work_type_id == tech`.
- [ ] Реализация: в цикле броней `team_reserve` копить по человеку; `merge_person` объединяет.
- [ ] Тест диаграммы: у Пряничникова `quarter.reserve_use == [{team: "ERP", work_type_id: tech, label, hours: 180, planned_hours: 102.4, used_hours: 180, remaining_hours: 0, overuse_hours: 77.6}]`, `quarter.reserve_items == {item.id: tech}`; у Шутова — пусто. В плане «Блока» у Пряничникова то же (цифры не зависят от плана).
- [ ] Реализация: `ReserveUseOut`, поля `EmployeeQuarterLoad.reserve_use`, `reserve_items`; заполнение из запасов основных команд. Commit.

### Task 3 (3.3): подпись в подсказках и развёрнутая сводка — фронт

**Files:** Modify `frontend/src/api/resourcePlanning.ts`, `frontend/src/utils/normedReserve.ts` (+ `.test.ts`), `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx`, `NormedReserveSummary.tsx`, `frontend/src/pages/ResourcePlanningPage.tsx` (только `key` у сводки)

- [ ] Тесты `reserveUseLines(uses, workTypeIds?)`: «за счёт «Технические задачи»: 80 из 100 ч, осталось 20 ч»; перерасход — текст «130 из 100 ч» + красная часть «сверх запаса 30 ч»; фильтр по видам дня; несколько видов — строка на вид. `dayReserveTypes(row, date, assignments, bookings)` — виды задач дня из `reserve_items`. `hasOtherTeamHours(reserve)`.
- [ ] Подсказка дня: строки в конце; подсказка у процента — AntD `Tooltip` с теми же строками (красный цвет для «сверх запаса»).
- [ ] Сводка: начальное `expanded = hasOtherTeamHours(reserve)`; на странице `key={gantt.plan.id}`, чтобы при открытии другого плана правило срабатывало заново.
- [ ] `npx vitest run src/utils/normedReserve.test.ts`, eslint по изменённым. Commit.

### Task 4: одна функция загрузки за квартал

**Files:** Modify `app/services/normed_reserve.py`, `app/api/endpoints/resource_planning.py`; Test: `tests/services/test_normed_reserve.py`

- [ ] Тест: `place_person` отдаёт `free_by_day` = норма − задачи − другие команды − нормированные (заблокированный день — 0). `people_loads(db, employees, year, quarter, capacity, own, other, residue)` даёт те же `PersonLoad`, что ручная сборка `team_reserve` + `merge_person` + `place_person`; запасов — по одному на основную команду.
- [ ] Реализация `people_loads` → `(loads, reserves, labels)`; диаграмма переходит на неё (кусок «Нормированные работы — запас основных команд людей плана»). Построение строки «Загрузки по дням» выносится в `_employee_load_out(...)`, занятость и часы плана — в `_plan_occupancy(...)`. Все тесты диаграммы зелёные, число запросов не растёт. Commit.

### Task 5 (3.2): честные кандидаты фазы — бэкенд

**Files:** Modify `app/services/assignee_candidates.py`, `app/schemas/assignee_candidates.py`, `app/api/endpoints/resource_planning.py` (`list_assignment_candidates`); Test: `tests/test_api_assignment_candidates_free.py`

- [ ] Тесты: у кандидата `free_hours` = свободно в даты фазы (норма − брони всех команд − нормированные основной − заблокированные дни); `load_pct` — с нормированными (как `quarter.pct` в диаграмме); бронь самой фазы у нынешнего исполнителя не считается; внутри группы — по убыванию `free_hours`; кандидаты строки сценария — без `free_hours`, порядок по имени (как было).
- [ ] Реализация: параметры `phase_window`, `skip_booking` у `candidate_groups`; загрузка через `people_loads`. Число запросов не растёт с числом людей. Commit.

### Task 6 (3.2): подпись кандидата — фронт

**Files:** `frontend/src/api/resourcePlanning.ts`, `frontend/src/utils/rpCandidates.ts` (+ test)

- [ ] Тест: «Петров · Разработчик · ERP · свободно 34 ч в даты фазы · 87%»; без `free_hours` — как раньше. Реализация, vitest, eslint. Commit.

### Task 7 (3.1): таблица списка наблюдения

**Files:** Create `app/models/resource_plan_watch.py`, `alembic/versions/wl01_plan_watchlist.py`; Modify `app/models/__init__.py`, `app/models/CLAUDE.md`; Test: `tests/test_migration_wl01_plan_watchlist.py`

- [ ] Модель `ResourcePlanWatch`: `id`, `plan_id` FK `resource_plans.id` CASCADE, `employee_id` FK `employees.id` CASCADE, timestamps, unique (`plan_id`, `employee_id`).
- [ ] Миграция `wl01_plan_watchlist` (предок `iv01_clear_frozen_involvement`): таблица есть — пропустить.
- [ ] Тест: `alembic upgrade head` на чистой базе создаёт таблицу; на базе, где таблица уже есть (create_all), — не падает. Commit.

### Task 8 (3.1): эндпоинты списка наблюдения

**Files:** Modify `app/api/endpoints/resource_planning.py`, `app/api/CLAUDE.md`; Test: `tests/api/test_rp_plan_watch.py`

- [ ] `GET /resource-plans/{id}/watch` → `{rows, bookings}`; строка — как у людей плана + `home_team`, `free_hours`, `free_by_month` (3 месяца квартала), `tech_reserve` (строка «Технических задач» роли человека в запасе основной), `in_plan`. Сортировка — по `free_hours` убыв.
- [ ] `POST /resource-plans/{id}/watch {employee_ids}` — добавить (повтор не дублирует), `DELETE /resource-plans/{id}/watch/{employee_id}` — убрать; оба — событие `resource_planning`.
- [ ] Тесты: цифры наблюдаемого (Пряничников из плана «Блока» и из плана третьей команды) совпадают с его строкой в диаграмме ERP (`quarter`), слои: задачи ERP — свой слой, «Блок» — другие команды; `free_by_month` = сумма свободного по дням; `tech_reserve` = строка сводки ERP; удаление плана/сотрудника чистит список; число запросов не растёт с числом наблюдаемых одной команды. Commit.

### Task 9 (3.1): «Подобрать людей» и секция «Наблюдаемые» — фронт

**Files:** `frontend/src/api/resourcePlanning.ts`, `frontend/src/hooks/useResourcePlanning.ts`, `frontend/src/components/resource-planning/WatchPickerModal.tsx` (new), `EmployeeLoadHeatmap.tsx`, `GanttChart.tsx` (`exact: true` у признака перечитывания), `ResourcePlanningPage.tsx` (подключение), `frontend/src/utils/rpWatch.ts` (+ test)

- [ ] Тесты `rpWatch`: `roleTeamPicks(employees, team, role)` — все активные сотрудники роли в команде (по членству); `freeMonthLabel`.
- [ ] Окно: поиск по ФИО (множественный выбор), «вся роль в команде» (команда + роль → добавить всех), «Добавить». Секция «НАБЛЮДАЕМЫЕ» под людьми плана: те же клетки и подсказки, справа — свободно по месяцам и «Технические задачи: осталось N ч» (перерасход — красным), кнопка «убрать».
- [ ] `npm run build`, eslint, vitest. Commit.

### Task 10: сверка на копии рабочей базы

- [ ] Скрипт в scratchpad: «Команда 1С (ERP - Товарный учет)», IV кв. 2026, разработчики — запас «Технических задач» (заложено / другие команды / осталось), цифры Пряничникова за квартал; время ответа списка кандидатов и списка наблюдения. Числа — в отчёт.

### Task 11: финальная проверка

- [ ] `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py -p no:cacheprovider`; `npm run build`; eslint по изменённым файлам.
