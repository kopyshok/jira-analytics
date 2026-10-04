# Поток 5. Фактическая вовлечённость — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Показать, сколько времени аналитики и разработчики команды на деле тратят на проектные
задачи: «факт N%» рядом с заданной вовлечённостью в справочнике (последний завершённый квартал) и
отчёт «Фактическая вовлечённость» (сотрудники × месяцы квартала + итог + среднее по роли).

**Формула:** факт = часы списаний на задачах вида работ «Проекты и развитие» (`project`) ÷ все
списанные часы. «Списано от нормы» = все списанные ÷ норма (календарь минус отсутствия). Итог роли —
Σ проектных ÷ Σ всех (не среднее процентов).

**Architecture:** новый сервис только для чтения `app/services/involvement_fact.py`:
- состав — `team_membership.intervals_by_team` (команда — по участию на дату списания);
- роли — `Employee.role` ∈ {`analyst`, `dev`}, без роли и прочие роли не входят;
- списания — **один** запрос за квартал по всем людям всех команд (`Worklog` ⨝ `Issue.category`),
  задачи, исключённые из анализа, не учитываются (как в аналитике);
- вид работ — категория задачи (`Issue.category` — уже с наследованием от родителя, проставляет
  `MappingService`/`CategoryResolver`) → `Category.work_type_id`; карта «категория → вид работ»
  выносится в общий помощник `categories.get_category_work_types` и им же пользуется
  `AnalyticsService.get_dashboard_norm_work`;
- норма — `CapacityService.team_quarter_capacity(employee_ids=…, teams_filter=[team])` (пакетно,
  за дни участия в команде, минус отсутствия), по месяцам.

Эндпоинт `GET /planning/involvement-defaults/fact?teams=A,B&year=&quarter=` — без квартала берётся
последний завершённый.

**Tech Stack:** FastAPI, SQLAlchemy 2 (ORM), pytest; React 19 + AntD 6 + TanStack Query, vitest.

Спека: `docs/superpowers/specs/2026-10-04-q4-improvements-pack-design.md`, «Поток 5».

---

### Task 1: Общая карта «категория → вид работ»

**Files:** Modify `app/services/categories.py`, `app/services/analytics_service.py` (~943);
Test `tests/services/test_involvement_fact.py`.

- [ ] Тест: `get_category_work_types(db)` отдаёт только категории с видом работ.
- [ ] Помощник в `categories.py`; дашборд нормированных работ берёт карту из него.
- [ ] Прогнать `tests/test_dashboard_*`, `tests/test_membership_periods_facts.py` — зелёные.

### Task 2: Сервис фактической вовлечённости

**Files:** Create `app/services/involvement_fact.py`; Test `tests/services/test_involvement_fact.py`.

Тесты (сначала красные):
- [ ] факт = проектные ÷ все, «списано от нормы» = все ÷ норма; разбивка по месяцам и итог квартала;
- [ ] задача без категории / без вида работ — только в знаменатель; исключённая из анализа — нигде;
- [ ] итог роли = Σ проектных ÷ Σ всех (два человека 10/10 и 0/30 → 25%, не 50%);
- [ ] команда по дате списания: после перевода часы уходят в новую команду, норма — за дни участия;
- [ ] роли: тестировщик и сотрудник без роли не попадают;
- [ ] отсутствие уменьшает норму;
- [ ] нет списаний — факт пустой (не 0), «списано от нормы» 0%;
- [ ] число запросов к базе не растёт с числом людей (один проход по списаниям);
- [ ] `last_completed_quarter(date(2026,10,4)) == (2026, 3)`, январь → IV прошлого года.

- [ ] Реализация, тесты зелёные, коммит.

### Task 3: Эндпоинт

**Files:** Modify `app/api/endpoints/involvement_defaults.py`; Test `tests/api/test_involvement_fact_api.py`.

- [ ] Тест: `GET /planning/involvement-defaults/fact?teams=A&year=2026&quarter=3` — команды, роли,
  сотрудники, месяцы; без `year/quarter` — последний завершённый квартал; без `teams` — 422.
- [ ] Реализация (синхронный обработчик, только чтение), коммит.

### Task 4: Фронт — справочник и отчёт

**Files:** Modify `frontend/src/types/api.ts`, `frontend/src/components/planning/InvolvementDefaultsDrawer.tsx`;
Create `frontend/src/hooks/useInvolvementFact.ts`, `frontend/src/utils/involvementFact.ts` (+ `.test.ts`),
`frontend/src/components/planning/InvolvementFactReport.tsx`.

- [ ] vitest: формат процента (`null` → «—»), предыдущий завершённый квартал, список кварталов выбора,
  подпись подсказки.
- [ ] В строке справочника рядом с процентом — «факт N%» роли за последний завершённый квартал;
  подсказка: квартал, число людей, «списано от нормы M%», формула словами. Нет данных — «факт —».
- [ ] Кнопка «Фактическая вовлечённость» → окно: команды (из шапки; пустая шапка — все команды) и
  квартал; таблица: сотрудник, роль, факт по месяцам, итог квартала, списано от нормы; строки
  «Среднее по роли»; подсказки к заголовкам объясняют формулу.
- [ ] `npx eslint` по изменённым файлам, `npm run build`, `npx vitest run src/utils/involvementFact.test.ts`; коммит.

### Task 5: Сверка на копии рабочей базы

- [ ] Скрипт во временной папке: III кв. 2026, 2–3 команды × роли — факт рядом со значением справочника.
- [ ] Полный прогон бэкенда, сборка фронта.
