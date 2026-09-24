# Планирование Q4 — Часть 5. Привлечённые: доработки после проверки. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Домашняя команда получает приоритет над привлекающей; ручная дата задаёт только начало фазы, а часы раскладываются по свободным окнам; появляются вид «Исполнители», фильтр по людям и блок «Наши люди в других командах»; исполнитель строки сценария выбирается из всех команд, не затирается обновлением из Jira и встаёт в ресурсном плане на фазу своей роли.

**Architecture:** В `cross_team_occupancy` каждая бронь получает признаки `is_borrowing` (команда брони взяла человека не из своего состава) и `changed_at`; общая функция `subtractable` реализует правило «сначала домашняя команда» и используется расчётом плана, расшифровкой фазы, базой сценария и признаком устаревания. Закреплённые по дате фазы раскладываются тем же `_allocate_hours_with_breakdown`, что и остальные; PATCH даты начала пересчитывает план. Диаграмма отдаёт брони всех людей плана с признаками и днями пересечения, фронт строит из них вырезы на полосах, блоки, вид «Исполнители» и подсказки подвала. Для сценария — общая функция подбора кандидатов (`assignee_candidates`), новый эндпоинт и признак ручного выбора исполнителя в `BacklogItem`.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic (batch mode), pytest; React 19 + TypeScript 6 + AntD 6, TanStack Query, vitest.

**Спека:** `docs/superpowers/specs/2026-09-23-planning-q4-design.md`, «Часть 5» (5.1–5.5) поверх «Части 4» (уже реализована: `app/services/cross_team_occupancy.py`, `app/services/jira_developer.py`, блок «Привлечённые», кандидаты фазы). Номера строк ниже — ориентиры на коммит `0f9f11a6`; искать по приведённым фрагментам.

---

## Решения и расхождения со спекой

1. **Бронь-привлечение** (`is_borrowing`) определяется по составу команды брони в квартале **её** опорного плана: для хвостов прошлого квартала — прошлый квартал. Периоды участия берутся одним запросом (`tm.membership_rows`) на вызов `external_bookings`.
2. **Что вычитается (5.1)** — одна функция `cto.subtractable(bookings, borrowed)`: привлечённому в план — все брони; своему — только брони команд, где он тоже состоит. Применяется в `compute_schedule`, `explain_assignment`, признаке устаревания. `ResourceBaseService` работает только со своими → берёт брони без `is_borrowing`, брони-привлечения считает отдельно (новое поле сводки).
3. **Подвал и подсказки** показывают все брони человека (включая привлечения): это «видно, куда забирают людей». Доля `ext_pct` в подвале не меняется.
4. **Устаревание** считается при чтении диаграммы: `changed_at` брони = позднейшее из `computed_at` её опорного плана и `updated_at` строки; план устарел, если хоть одна **вычитаемая** бронь изменилась позже `plan.computed_at`. Бронь, которая исчезла (другая команда освободила человека), признак не поднимает — спека говорит только об изменённых бронях. План, ни разу не считавшийся, не устаревает.
5. **Дни пересечения** (`overlap_days`) считаются на сервере тем же `cto.overlap_days`, что и живой конфликт техкоманды, — красная отметка стоит ровно там, где техкоманда получит «Пересечение с другой командой». Поле заполняется для всех броней; фронт рисует его в блоке «Наши люди в других командах».
6. **Закреплённая дата (5.2).** Строки `pinned_start` раскладываются до основного прохода общим `_allocate_hours_with_breakdown` с тем же дневным потолком, что и остальные фазы (`8 ч × вовлечённость × параллельность`, но не больше дня календаря). Раньше закреплённые брали `6 ч × вовлечённость` — при вовлечённости < 100% полоса станет короче (обновляются ожидания `test_compute_schedule_extends_pinned.py`). Порядок: приоритет задачи, фаза, часть. Старт полосы переезжает на первый свободный день (существующая зачистка дат по раскладке). Тестирование без сотрудника с ручной датой раскладывается по календарю прежним `_extend_window_for_hours` (раньше это делал только PATCH).
7. **Не хватило свободных дней** закреплённой фазе — конфликт «Часы не размещены» с причиной «не поместилось в свободные дни исполнителя» (раньше закреплённые фазы не проверялись вовсе). Фазы, закреплённые только разбивкой, как и раньше не проверяются.
8. **Выбывший сотрудник:** дни вне команды не свободны, поэтому закреплённая фаза больше не уходит за дату выбытия — вместо `OUT_OF_TEAM` теперь «Часы не размещены» (тест `test_rp_out_of_team_conflict.py` переписывается).
9. **PATCH даты:** `end_date` из тела игнорируется всегда — конец фазы считает планировщик (поле в схеме оставлено, чтобы старые клиенты не получали 422). Смена начала = `pinned_start` + полный пересчёт плана, как при смене исполнителя. Фронт больше не шлёт конец: ручки растягивания убраны, «Окончание» в панели фазы — только просмотр.
10. **Настройки вида:** `view_mode` = `"tasks" | "people"` (`null` = задачи). `PATCH /preferences` теперь меняет только присланные поля — раньше сбрасывал остальные к значениям по умолчанию (переключатель вида сбрасывал бы «Только рабочие» и цвета).
11. **Фильтр по людям** живёт до смены плана, не сохраняется. Клик по фишке исполнителя теперь добавляет/убирает человека из фильтра (раньше — подсветка одного); подсветка и пульсация остаются, когда в фильтре ровно один человек. Подвал фильтром не режется — в нём выбирают людей. Блоки «Привлечённые» / «Наши люди в других командах» — только в виде «Задачи»: в «Исполнителях» те же брони лежат на полосе «все работы».
12. **Вырезы на полосах** считаются на фронте из `external_bookings` и `daily_hours` фазы (нового поля в назначениях нет): рабочие дни внутри полосы без часов этой фазы, когда у человека есть бронь другой команды. Фаза без посуточной раскладки вырезов не получает.
13. **Исполнитель сценария из чужой команды** применяется в ресурсном плане, только если выбран в сценарии вручную (`assignee_manual`). Исполнитель, подтянутый из Jira, — только свой (решение Части 4: исполнитель инициативы в Jira часто заказчик). Выбор человека, который и так стоит исполнителем в Jira, — не ручной: строка снова следует за Jira. Очистка поля — ручной выбор «никого», держится до смены исполнителя в Jira.
14. **Фаза исполнителя сценария** — дословно спека: разработчик → «Разработка»; аналитик/РП/консультант → «Анализ»; иначе «Анализ», а без часов анализа — «Разработка». Это меняет прежнее «аналитик = исполнитель независимо от роли» (тест переписывается). Закреп вручную важнее; «Разработчик» из Jira — после исполнителя сценария; нехватка времени исполнителя не заменяет — остаток даёт «Часы не размещены».
15. **Подпись исполнителя в строке сценария** при ручном выборе — выбранный человек (раньше всегда имя из Jira). Список «Целевые задачи» не меняется: там данные Jira.
16. **«Из Jira» в кандидатах сценария** — исполнитель задачи в Jira (по учётной записи), а не текущий выбор. В кандидатах фазы ресурсного плана «Из Jira» для не-разработки остаётся исполнителем строки сценария, как было: задача B4 только выносит общий код.
17. **Сводка ресурса сценария:** новое поле `borrowed_by_other_teams_by_role` — по ролям, как соседнее «Занято в планах других команд»; «На бэклог» не уменьшает; за день берётся не больше остатка после обязательных работ (как у вычитаемых броней).

---

## Контракты API (бэкенд ↔ фронт)

Все поля — JSON, даты — строки `"YYYY-MM-DD"`, часы — `float`.

**1. `GET /api/v1/resource-planning/resource-plans/{plan_id}/gantt`** (группа A → группа C)

```jsonc
{
  // ...прежние поля без изменений...
  "external_bookings": [            // ТЕПЕРЬ: брони всех людей подвала (свои + привлечённые)
    {
      "assignment_id": "uuid",
      "employee_id": "uuid",
      "employee_name": "Шутов",       // string | null
      "team": "ERP ТУ",               // команда опорного плана брони
      "issue_key": "OS-91393",        // string | null
      "title": "Название задачи",
      "phase": "dev",                 // analyst | dev | qa | opo
      "start": "2026-10-05",
      "end": "2026-10-20",
      "daily_hours": {"2026-10-05": 6.0},
      "provisional": false,
      "employee_is_borrowed": true,   // НОВОЕ: человек привлечён в ЭТОТ план
      "is_borrowing": false,          // НОВОЕ: бронь-привлечение (команда брони взяла человека не из своего состава)
      "overlap_days": ["2026-10-06"]  // НОВОЕ: дни брони, где этот план тоже занял человека и вместе больше дня
    }
  ],
  "stale_due_to_other_teams": false,  // НОВОЕ: вычитаемые брони изменились после plan.computed_at
  "stale_teams": []                   // НОВОЕ: такие команды, по алфавиту
}
```

Фронт: блок «Привлечённые» = `employee_is_borrowed == true`; блок «Наши люди в других командах» = `employee_is_borrowed == false && is_borrowing == true`.

**2. `PATCH /api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}`** (A → C)

Тело для перетаскивания — только `{"start_date": "2026-10-05"}`. Присланный `end_date` игнорируется всегда. Сервер ставит `pinned_start`, пересчитывает план, отвечает прежним `AssignmentOut` с новыми `start_date` / `end_date` / `daily_hours` (начало может сдвинуться на первый свободный день).

**3. `PATCH /api/v1/resource-planning/preferences`** (A → C)

Тело частичное, например `{"view_mode": "people"}`; меняются только присланные поля. `view_mode`: `"tasks" | "people" | null`.

**4. `GET /api/v1/planning/scenarios/{scenario_id}/resource-summary`** (A → D)

Новое поле: `"borrowed_by_other_teams_by_role": {"developer": 120.0}` — часы людей команды в опорных планах команд, взявших их к себе; из «На бэклог» не вычтены. `booked_by_other_teams_by_role` теперь только по командам, где человек тоже состоит.

**5. `GET /api/v1/planning/scenarios/{scenario_id}/assignee-candidates?backlog_item_id={id}`** (B → D) — НОВЫЙ

```jsonc
[
  {
    "key": "jira",                    // "jira" | "team" | "other"; пустые группы не приходят
    "label": "Из Jira",               // «Из Jira» | «Моя команда» | «Другие команды»
    "employees": [
      {
        "employee_id": "uuid",
        "display_name": "Шутов",
        "role": "developer",          // string | null
        "team": "ERP ТУ",             // основная команда сотрудника, string | null
        "load_pct": 42.5,             // загрузка за квартал по опорным планам всех команд
        "member_from": null,          // границы участия в команде сценария внутри квартала
        "member_to": "2026-11-10"
      }
    ]
  }
]
```

Та же схема, что у `GET …/assignments/{id}/candidates` (фронт-тип `AssignmentCandidateGroup`). 404 — нет сценария или задачи в нём; 400 — у сценария не задан год/квартал. «Из Jira» — сотрудник, стоящий исполнителем задачи в Jira.

**6. `PATCH /api/v1/planning/scenarios/{scenario_id}/allocations/{alloc_id}/assignee`** (B → D)

Тело без изменений: `{"assignee_employee_id": "uuid" | null}`. Ответ `AllocationResponse`: при ручном выборе `assignee_display_name` / `assignee_role` — выбранного человека.

---

## Группы, владение файлами, порядок

| Группа | Что | Владеет файлами | Зависит от |
|---|---|---|---|
| **A** бэкенд плана | 5.1, 5.2, 5.4 (сервер), настройки вида | `app/services/cross_team_occupancy.py`, `app/services/resource_planning_service.py`, `app/services/resource_base_service.py`, `app/api/endpoints/resource_planning.py`, в `app/api/endpoints/planning.py` — только `ResourceSummaryOut` и его заполнение; тесты: `tests/services/xteam_factory.py`, `tests/services/test_cross_team_occupancy.py`, `tests/services/test_rp_borrowed_staff.py`, `tests/services/test_rp_home_first.py` (нов.), `tests/services/test_resource_base_external.py`, `tests/services/test_rp_pinned_relayout.py` (нов.), `tests/services/test_compute_schedule_extends_pinned.py`, `tests/services/test_rp_out_of_team_conflict.py`, `tests/test_rp_pinned_start_ux.py`, `tests/api/test_resource_planning_patch_extends_end.py`, `tests/api/test_rp_drag_relayout.py` (нов.), `tests/api/test_rp_cross_team_gantt.py`, `tests/test_api_user_rp_preferences.py` | — |
| **B** бэкенд исполнителя сценария | 5.5 | `app/services/assignee_candidates.py` (нов.), `app/models/backlog_item.py`, `alembic/versions/pq05_backlog_assignee_manual.py` (нов.), `app/services/backlog_service.py`, `app/api/endpoints/backlog.py`, в `app/api/endpoints/planning.py` — `_to_allocation_resp`, `patch_allocation_assignee`, новый эндпоинт; тесты `tests/services/test_assignee_candidates.py`, `tests/api/test_scenario_assignee.py`, `tests/services/test_backlog_assignee_manual.py`, `tests/test_migration_pq05_backlog_assignee_manual.py` (все нов.). **B4** дополнительно правит `resource_planning_service.py`, `resource_planning.py`, `tests/test_resource_planning_assignment_logic.py`, создаёт `tests/services/test_rp_scenario_executor.py` | B1–B3 — ни от чего; **B4 — после всей группы A** и после B1, B3 |
| **C** фронт плана | 5.2–5.4 на экране, 5.3 | `frontend/src/api/resourcePlanning.ts`, `frontend/src/utils/externalBookings.ts` (+test), `frontend/src/utils/rpBusy.ts` (нов., +test), `frontend/src/utils/rpPeople.ts` (нов., +test), `frontend/src/components/resource-planning/{GanttRows,GanttChart,ExternalBookingsRows,EmployeeLoadHeatmap,AssignmentSidebar}.tsx`, `frontend/src/pages/ResourcePlanningPage.tsx` | контракты 1–3 (для живой проверки — группа A) |
| **D** фронт сценария | 5.5 и подпись 5.1 на экране | `frontend/src/api/planning.ts`, `frontend/src/hooks/usePlanning.ts`, `frontend/src/components/planning/BacklogAllocRow.tsx`, `frontend/src/pages/PlanningPage.tsx`, `frontend/src/types/api.ts`, `frontend/src/components/planning/ScenarioResourceSummary.tsx` | контракты 4–6 (живая проверка — A3, B2, B3) |
| **F** финал | справка, заметки, проверка | `docs/help/resource-planning.md`, `docs/help/planning.md`, `app/services/CLAUDE.md`, `release_notes/drafts.json` (через CLI) | всё выше |

Параллельно можно вести четыре дорожки: **A** ‖ **B1→B2, B3** ‖ **C** ‖ **D**; затем **B4**; затем **F**. `app/api/endpoints/planning.py` правят A (блок `ResourceSummaryOut`, ~стр. 405–428, и строка `booked_by_other_teams_by_role=` в `scenario_resource_summary`, ~стр. 1808) и B (`_to_allocation_resp` ~456–515, `patch_allocation_assignee` ~1673–1729, новый эндпоинт после него) — куски не пересекаются; при работе в разных рабочих копиях слияние без конфликтов. Внутри каждой группы задачи идут строго по порядку.

---

## Общие правила

- Бэкенд-тесты: `py -3.10 -m pytest <путь> -v`; весь прогон — `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py` (LLM-тесты виснут без сети).
- Фронт: `cd frontend && npx vitest run src/<файл>` для одного файла, весь набор — `cd frontend && npx vitest run src` (никогда не голый `npx vitest`); сборка `cd frontend && npm run build` (там `tsc -b`, тестовые файлы тоже проверяются типами); линтер — только по изменённым файлам: `cd frontend && npx eslint <файлы>` (общий `npm run lint` красный до этой работы).
- Питон-линтер: `ruff check <изменённые файлы>`.
- Миграции самодостаточные (не импортируют код приложения), batch mode, совместимы с PostgreSQL (булево значение по умолчанию — `sa.false()`).
- Коммиты: сообщение на русском в формате conventional, в конце строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Всегда `git add <явные пути>` и `git commit -F - <<'EOF' … EOF`. Не использовать `git commit -- пути` (берёт рабочую копию целиком) и `git commit -m @'…'@` (роняет «@» в заголовок).
- После правок кода — `graphify update .` (в финальной задаче).

---

## Группа A — бэкенд ресурсного плана

### Task A1: Признаки брони — привлечение и время изменения

**Files:**
- Modify: `app/services/cross_team_occupancy.py` (`ReferencePlan`, `reference_plans`, `ExternalBooking`, `external_bookings`; новые `_member_of`, `subtractable`, `stale_teams`)
- Modify: `tests/services/xteam_factory.py` (новая фабрика `join_team`)
- Test: `tests/services/test_cross_team_occupancy.py`

- [ ] **Step 1: Фабрика «ещё одна команда сотрудника»**

В `tests/services/xteam_factory.py` добавить после `make_employee`:

```python
def join_team(
    db,
    employee: Employee,
    team: str,
    joined_at: Optional[date] = None,
    left_at: Optional[date] = None,
) -> EmployeeTeam:
    """Ещё одна (не основная) команда сотрудника — общий сотрудник."""
    et = EmployeeTeam(
        employee_id=employee.id,
        team=team,
        is_primary=False,
        joined_at=joined_at,
        left_at=left_at,
    )
    db.add(et)
    db.flush()
    return et
```

(`date`, `Optional`, `EmployeeTeam` в файле уже импортированы.)

- [ ] **Step 2: Падающие тесты**

В `tests/services/test_cross_team_occupancy.py` заменить строку импорта фабрик на
`from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan`
и дописать в конец файла:

```python
def _ext(employee_id, team="B", is_borrowing=False, changed_at=None):
    """Бронь без базы — для чистых функций."""
    return cto.ExternalBooking(
        assignment_id=f"a-{employee_id}-{team}-{is_borrowing}",
        employee_id=employee_id,
        team=team,
        issue_key=None,
        title="x",
        phase="dev",
        start=D("2026-01-05"),
        end=D("2026-01-05"),
        daily_hours={D("2026-01-05"): 6.0},
        provisional=False,
        is_borrowing=is_borrowing,
        changed_at=changed_at,
    )


def _booking_of(db_session, employee, team="B", year=2026, quarter="Q1", day="2026-01-05"):
    """Опорный план команды ``team`` с одной бронью на сотрудника."""
    sc, plan = make_plan(db_session, team, year=year, quarter=quarter)
    row = book(db_session, plan, add_item(db_session, sc, f"Работа {team}", dev=6), employee, {day: 6.0})
    return plan, row


def _bookings_for_a(db_session, employee, end="2026-03-31"):
    return cto.external_bookings(
        db_session, team="A", year=2026, quarter=1, employee_ids=[employee.id],
        start=D("2026-01-01"), end=D(end),
    )


def test_booking_of_team_without_the_employee_is_borrowing(db_session):
    """Команда B взяла к себе E из A — для A это бронь-привлечение."""
    e = make_employee(db_session, "Шутов", "A")
    _booking_of(db_session, e)
    db_session.commit()

    [b] = _bookings_for_a(db_session, e)

    assert b.is_borrowing is True


def test_booking_of_shared_member_is_not_borrowing(db_session):
    """E состоит и в A, и в B — бронь B на E не привлечение."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    _booking_of(db_session, e)
    db_session.commit()

    [b] = _bookings_for_a(db_session, e)

    assert b.is_borrowing is False


def test_tail_booking_checks_membership_in_its_own_quarter(db_session):
    """Хвост плана B прошлого квартала: тогда E в B состоял — не привлечение,
    хотя в этом квартале он в B уже не состоит."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B", left_at=D("2026-01-01"))
    _booking_of(db_session, e, year=2025, quarter="Q4")
    db_session.commit()

    [b] = _bookings_for_a(db_session, e, end="2026-04-30")

    assert b.is_borrowing is False


def test_subtractable_keeps_borrowing_bookings_only_for_borrowed():
    own_lent = _ext("own", is_borrowing=True)
    own_shared = _ext("own", team="C")
    ext_lent = _ext("ext", is_borrowing=True)

    assert cto.subtractable([own_lent, own_shared, ext_lent], {"ext"}) == [own_shared, ext_lent]


def test_booking_changed_at_is_latest_of_plan_compute_and_row_edit(db_session):
    e = make_employee(db_session, "Шутов", "A")
    plan, row = _booking_of(db_session, e)
    plan.computed_at = datetime(2026, 1, 2)
    row.updated_at = datetime(2026, 1, 3)
    db_session.commit()

    [b] = _bookings_for_a(db_session, e)
    assert b.changed_at == datetime(2026, 1, 3)

    row.updated_at = datetime(2026, 1, 1)
    db_session.commit()

    [b] = _bookings_for_a(db_session, e)
    assert b.changed_at == datetime(2026, 1, 2)


def test_stale_teams_lists_teams_changed_after_compute():
    bookings = [
        _ext("e", team="B", changed_at=datetime(2026, 1, 5)),
        _ext("e", team="C", changed_at=datetime(2026, 1, 1)),
        _ext("e", team="D", changed_at=None),
    ]

    assert cto.stale_teams(bookings, datetime(2026, 1, 3)) == ["B"]
    assert cto.stale_teams(bookings, None) == []
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/services/test_cross_team_occupancy.py -v`
Expected: новые тесты FAIL (`TypeError: ... unexpected keyword argument 'is_borrowing'` / `AttributeError: ... 'is_borrowing'`), прежние PASS.

- [ ] **Step 4: Реализация в `app/services/cross_team_occupancy.py`**

4.1. `ReferencePlan` — время расчёта плана:

```python
@dataclass(frozen=True)
class ReferencePlan:
    """Опорный план команды на квартал."""

    plan_id: str
    team: str
    provisional: bool
    # Когда план последний раз считался — для признака устаревания чужих планов.
    computed_at: Optional[datetime] = None
```

4.2. В `reference_plans` обе строки создания опорного плана:

```python
            out[team] = ReferencePlan(best.id, team, False, best.computed_at)
```

```python
        out[team] = ReferencePlan(best.id, team, True, best.computed_at)
```

4.3. `ExternalBooking` — два новых поля в конце:

```python
@dataclass
class ExternalBooking:
    """Фаза сотрудника в опорном плане другой команды."""

    assignment_id: str
    employee_id: str
    team: str
    issue_key: Optional[str]
    title: str
    phase: str
    start: date
    end: date
    daily_hours: Dict[date, float]
    provisional: bool
    # Бронь-привлечение: в команде брони человек не состоял ни дня квартала
    # её плана — команда взяла его к себе.
    is_borrowing: bool = False
    # Когда бронь последний раз менялась: пересчёт опорного плана или правка строки.
    changed_at: Optional[datetime] = None
```

4.4. Перед `def _in_plan_scenario` добавить:

```python
def _member_of(
    periods: Iterable[tuple[str, Optional[date], Optional[date], bool]],
    team: str,
    start: date,
    end: date,
) -> bool:
    """Состоял ли сотрудник в ``team`` хоть день отрезка.

    ``periods`` — его периоды участия из ``tm.membership_rows``:
    ``(команда, joined_at, left_at, основная)``, ``left_at`` — первый день вне команды.
    """
    return any(
        t == team
        and (joined is None or joined <= end)
        and (left is None or left > start)
        for t, joined, left, _primary in periods
    )
```

4.5. В docstring `external_bookings` заменить последний абзац

```
    Четыре запроса на любой объём: опорные планы двух кварталов, задачи
    планов квартала и назначения.
```

на

```
    У каждой брони — ``is_borrowing`` (человек не состоял в команде брони ни
    дня квартала её плана: команда его привлекла) и ``changed_at`` (когда
    бронь последний раз менялась: пересчёт опорного плана или правка строки).
    Пять запросов на любой объём: опорные планы двух кварталов, задачи
    планов квартала, назначения и периоды участия их людей.
```

4.6. В `external_bookings` заменить

```python
    out: List[ExternalBooking] = []
    for a in rows:
        if not a.employee_id or a.start_date is None or a.end_date is None:
            continue
        ref = by_plan[a.plan_id]
        if a.plan_id in prev_ids and (ref.team, a.backlog_item_id) in carried:
            continue
        daily = {d: h for d, h in _assignment_daily(a).items() if start <= d <= end}
        if not daily:
            continue
        bi = a.backlog_item
```

на

```python
    # Состав команды брони сверяется с кварталом её опорного плана: хвост
    # прошлого квартала — с прошлым кварталом.
    membership = tm.membership_rows(
        db, list({a.employee_id for a in rows if a.employee_id})
    )
    cur_bounds = quarter_bounds(year, quarter)
    prev_bounds = quarter_bounds(prev_year, prev_quarter)
    out: List[ExternalBooking] = []
    for a in rows:
        if not a.employee_id or a.start_date is None or a.end_date is None:
            continue
        ref = by_plan[a.plan_id]
        if a.plan_id in prev_ids and (ref.team, a.backlog_item_id) in carried:
            continue
        daily = {d: h for d, h in _assignment_daily(a).items() if start <= d <= end}
        if not daily:
            continue
        lo, hi = prev_bounds if a.plan_id in prev_ids else cur_bounds
        bi = a.backlog_item
```

и в том же цикле

```python
                daily_hours=daily,
                provisional=ref.provisional,
            )
        )
```

на

```python
                daily_hours=daily,
                provisional=ref.provisional,
                is_borrowing=not _member_of(
                    membership.get(a.employee_id, ()), ref.team, lo, hi
                ),
                changed_at=max(
                    (t for t in (ref.computed_at, a.updated_at) if t is not None),
                    default=None,
                ),
            )
        )
```

4.7. После `daily_totals` добавить:

```python
def subtractable(
    bookings: Iterable[ExternalBooking], borrowed: set
) -> List[ExternalBooking]:
    """Брони, которые вычитаются из доступности плана: сначала домашняя команда.

    Привлечённому в план (``borrowed``) — все брони других команд. Своему
    сотруднику — только брони команд, где он тоже состоит (общий сотрудник).
    Бронь-привлечение своего (команда взяла его к себе, не имея в составе)
    доступность не уменьшает — подстраивается привлекающая команда.
    """
    return [b for b in bookings if b.employee_id in borrowed or not b.is_borrowing]


def stale_teams(
    bookings: Iterable[ExternalBooking], computed_at: Optional[datetime]
) -> List[str]:
    """Команды, чьи брони изменились после расчёта плана, по алфавиту.

    План ни разу не считался — сравнивать не с чем, список пуст.
    """
    if computed_at is None:
        return []
    return sorted(
        {b.team for b in bookings if b.changed_at is not None and b.changed_at > computed_at}
    )
```

- [ ] **Step 5: Тесты проходят, соседние не сломаны**

Run: `py -3.10 -m pytest tests/services/test_cross_team_occupancy.py tests/services/test_rp_borrowed_staff.py tests/services/test_resource_base_external.py tests/api/test_rp_cross_team_gantt.py -v`
Expected: всё PASS (признаки пока нигде не используются).

- [ ] **Step 6: Commit**

```bash
git add app/services/cross_team_occupancy.py tests/services/xteam_factory.py tests/services/test_cross_team_occupancy.py
git commit -F - <<'EOF'
feat(resource-planning): бронь знает, привлечение ли это и когда менялась

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task A2: Расчёт плана — сначала домашняя команда

**Files:**
- Modify: `app/services/resource_planning_service.py:617-634` (`compute_schedule`, вычитание броней)
- Modify: `tests/services/test_rp_borrowed_staff.py` (пять тестов)
- Create: `tests/services/test_rp_home_first.py`

- [ ] **Step 1: Новые тесты правила**

```python
# tests/services/test_rp_home_first.py
"""Правило «сначала домашняя команда»: чьи брони обходит расчёт плана."""

import json

from sqlalchemy import select

from app.models import ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import (
    add_item, book, join_team, make_employee, make_issue, make_plan,
)


def _dev_days(db, plan_id):
    rows = db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).scalars().all()
    return {k for r in rows for k, v in json.loads(r.daily_hours_json or "{}").items() if v > 0}


def test_home_plan_avoids_booking_of_shared_member(db_session):
    """E состоит и в A, и в B: план A обходит часы E в плане B."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=12), e,
         {"2026-01-01": 6.0, "2026-01-02": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    add_item(db_session, sc_a, "Работа A", dev=12)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    assert _dev_days(db_session, plan_a.id) == {"2026-01-05", "2026-01-06"}


def test_borrower_avoids_every_other_team(db_session, sample_project):
    """Привлечённый в план B обходит брони всех команд: и домашней A,
    и команды C, которая тоже его привлекла."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    make_employee(db_session, "Свой B", "B")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=6), e,
         {"2026-01-01": 6.0})
    sc_c, plan_c = make_plan(db_session, "C")
    book(db_session, plan_c, add_item(db_session, sc_c, "Работа C", dev=6), e,
         {"2026-01-02": 6.0})
    issue = make_issue(db_session, sample_project, "OS-10", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _dev_days(db_session, plan_b.id) == {"2026-01-05", "2026-01-06"}
```

- [ ] **Step 2: Поправить существующие тесты под правило**

В `tests/services/test_rp_borrowed_staff.py`:

2.1. Импорт фабрик:
`from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_issue, make_plan`

2.2. Тест `test_home_plan_avoids_borrower_bookings` заменить целиком:

```python
def test_home_plan_does_not_yield_to_borrower_bookings(db_session):
    """Сначала домашняя команда: B взяла E из A к себе — план A её бронь
    не обходит, подстраивается B."""
    e = make_employee(db_session, "Пряничников", "A")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=12)
    book(db_session, plan_b, item_b, e, {"2026-01-01": 6.0, "2026-01-02": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    add_item(db_session, sc_a, "Работа A", dev=12)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    rows = _dev_rows(db_session, plan_a.id)
    assert {r.employee_id for r in rows} == {e.id}
    assert _days(rows) == {"2026-01-01", "2026-01-02"}
```

2.3. В тестах, которым нужна именно вычитаемая бронь, сделать человека общим сотрудником:

- `test_phase_without_capacity_is_reported_not_dropped`: строку
  `    _booked_all_window(db_session, "C", own)` заменить на

  ```python
      join_team(db_session, own, "C")  # общий сотрудник: бронь C вычитается
      _booked_all_window(db_session, "C", own)
  ```

- `test_phase_pushed_by_predecessor_past_free_days_is_reported`: строки
  ```python
      # Весь апрель (месяц запаса) второй разработчик занят командой C.
      sc_c, plan_c = make_plan(db_session, "C")
  ```
  заменить на
  ```python
      # Весь апрель (месяц запаса) второй разработчик занят командой C,
      # где он тоже состоит.
      join_team(db_session, d2, "C")
      sc_c, plan_c = make_plan(db_session, "C")
  ```

- `test_leveler_does_not_delay_onto_other_team_bookings`: строки
  ```python
      e = make_employee(db_session, "Пряничников", "A")
      # План B держит E во вторник 06.01.
  ```
  заменить на
  ```python
      e = make_employee(db_session, "Пряничников", "A")
      join_team(db_session, e, "B")  # общий сотрудник: бронь B вычитается
      # План B держит E во вторник 06.01.
  ```

- `test_plan_avoids_previous_quarter_spill_of_other_team`: строки
  ```python
      e = make_employee(db_session, "Пряничников", "A")
      sc_b, plan_b = make_plan(db_session, "B", year=2025, quarter="Q4")
  ```
  заменить на
  ```python
      e = make_employee(db_session, "Пряничников", "A")
      join_team(db_session, e, "B")  # общий сотрудник: хвост B вычитается
      sc_b, plan_b = make_plan(db_session, "B", year=2025, quarter="Q4")
  ```

- [ ] **Step 3: Убедиться, что падает только перевёрнутый тест**

Run: `py -3.10 -m pytest tests/services/test_rp_borrowed_staff.py tests/services/test_rp_home_first.py -v`
Expected: FAIL только `test_home_plan_does_not_yield_to_borrower_bookings` (`{'2026-01-05', '2026-01-06'} != {'2026-01-01', '2026-01-02'}`), остальные PASS.

- [ ] **Step 4: Реализация**

В `compute_schedule` заменить

```python
        # Часы, забронированные на этих людей опорными планами других команд,
        # раскладка не трогает — в обе стороны (домашняя ↔ привлекающая).
        external = cto.daily_totals(
            cto.external_bookings(
                self.db,
                team=plan.team,
                year=plan.year,
                quarter=cto.quarter_num(plan.quarter),
                employee_ids=[e.id for e in employees],
                start=q_start,
                end=q_end_extended,
            )
        )
        avail = cto.subtract_occupancy(raw_avail, external)
```

на

```python
        # Часы, забронированные на этих людей опорными планами других команд,
        # раскладка не трогает. Сначала домашняя команда: своему сотруднику
        # вычитаются только брони команд, где он тоже состоит, — команда,
        # взявшая его к себе, подстраивается сама. Привлечённому — все брони.
        external = cto.daily_totals(
            cto.subtractable(
                cto.external_bookings(
                    self.db,
                    team=plan.team,
                    year=plan.year,
                    quarter=cto.quarter_num(plan.quarter),
                    employee_ids=[e.id for e in employees],
                    start=q_start,
                    end=q_end_extended,
                ),
                borrowed,
            )
        )
        avail = cto.subtract_occupancy(raw_avail, external)
```

- [ ] **Step 5: Тесты проходят**

Run: `py -3.10 -m pytest tests/services/test_rp_borrowed_staff.py tests/services/test_rp_home_first.py tests/services/test_cross_team_occupancy.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_borrowed_staff.py tests/services/test_rp_home_first.py
git commit -F - <<'EOF'
feat(resource-planning): расчёт плана — сначала домашняя команда

Бронь команды, взявшей сотрудника к себе, его доступность в домашнем
плане не уменьшает: подстраивается привлекающая команда.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task A3: База сценария — брони-привлечения справочно

**Files:**
- Modify: `app/services/resource_base_service.py` (`ResourceSummary`, `compute`, `compute_summary`)
- Modify: `app/api/endpoints/planning.py` (`ResourceSummaryOut`, `scenario_resource_summary`)
- Test: `tests/services/test_resource_base_external.py`

- [ ] **Step 1: Тесты**

В `tests/services/test_resource_base_external.py`:

1.1. Импорт: `from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan`.

1.2. В `_setup` сделать E общим сотрудником (эти тесты — про вычитаемые брони):

```python
def _setup(db_session):
    """E состоит в A и в B (общий сотрудник); B бронирует его на 05.01."""
    e = make_employee(db_session, "Пряничников", "A")
    join_team(db_session, e, "B")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=6)
    book(db_session, plan_b, item_b, e, {"2026-01-05": 6.0})
    sc_a, _ = make_plan(db_session, "A", scenario_status="draft")
    db_session.commit()
    return e, sc_a
```

1.3. У E теперь два периода участия: в `test_summary_ignores_bookings_outside_membership` заменить `filter_by(employee_id=e.id)` на `filter_by(employee_id=e.id, team="A")`, в `test_subgroup_capacity_loses_only_booked_member_hours` — `filter_by(employee_id=emp.id)` на `filter_by(employee_id=emp.id, team="A")`.

1.4. Дописать в конец файла:

```python
def _setup_borrowed(db_session):
    """E — сотрудник A; команда B взяла его к себе (в B он не состоит)."""
    e = make_employee(db_session, "Шутов", "A")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=6), e,
         {"2026-01-05": 6.0})
    sc_a, _ = make_plan(db_session, "A", scenario_status="draft")
    db_session.commit()
    return e, sc_a


def test_daily_base_keeps_hours_borrowed_by_other_team(db_session):
    e, sc_a = _setup_borrowed(db_session)

    base = ResourceBaseService(db_session).compute(sc_a)

    emp = next(x for x in base.employees if x.employee_id == e.id)
    assert {d.date: d.hours for d in emp.days}[date(2026, 1, 5)] == 8.0


def test_summary_shows_borrowed_hours_without_subtracting(db_session):
    _e, sc_a = _setup_borrowed(db_session)

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    assert s.booked_by_other_teams_by_role == {}
    assert s.borrowed_by_other_teams_by_role == {"developer": 6.0}
    assert s.available_by_role["developer"] == s.gross_by_role["developer"]


def test_resource_summary_endpoint_returns_borrowed_hours(db_session):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    _e, sc_a = _setup_borrowed(db_session)

    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        r = TestClient(app).get(f"/api/v1/planning/scenarios/{sc_a.id}/resource-summary")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200, r.text
    assert r.json()["borrowed_by_other_teams_by_role"] == {"developer": 6.0}
    assert r.json()["booked_by_other_teams_by_role"] == {}
```

- [ ] **Step 2: Убедиться, что новые тесты падают**

Run: `py -3.10 -m pytest tests/services/test_resource_base_external.py -v`
Expected: FAIL три новых теста (база 2.0 вместо 8.0; `AttributeError: ... 'borrowed_by_other_teams_by_role'`; `KeyError`), прежние PASS.

- [ ] **Step 3: Реализация в `app/services/resource_base_service.py`**

3.1. В `ResourceSummary` заменить поле броней на пару полей:

```python
    # Часы сотрудников команды, забронированные опорными планами других
    # команд квартала, где они тоже состоят (только дни, учтённые в брутто):
    # роль → часы. Вычтены из «На бэклог».
    booked_by_other_teams_by_role: dict[str, float] = field(default_factory=dict)
    # Часы сотрудников команды в опорных планах команд, которые взяли их к
    # себе (там они не состоят): роль → часы. Не вычтены — справочно.
    borrowed_by_other_teams_by_role: dict[str, float] = field(default_factory=dict)
```

3.2. В `compute` заменить

```python
        # Часы, забронированные на этих людей опорными планами других команд.
        booked = cto.daily_totals(
            cto.external_bookings(
                self.db,
                team=team,
                year=year,
                quarter=q,
                employee_ids=[e.id for e in employees],
                start=period_start,
                end=last_day,
            )
        )
```

на

```python
        # Часы, забронированные на этих людей опорными планами других команд,
        # где они тоже состоят. Брони команд, взявших человека к себе, базу
        # не уменьшают: сначала домашняя команда, подстраивается привлекающая.
        booked = cto.daily_totals(
            b
            for b in cto.external_bookings(
                self.db,
                team=team,
                year=year,
                quarter=q,
                employee_ids=[e.id for e in employees],
                start=period_start,
                end=last_day,
            )
            if not b.is_borrowing
        )
```

3.3. В `compute_summary` заменить

```python
        # --- брони других команд: учитываются только дни, вошедшие в брутто ---
        booked = cto.daily_totals(
            cto.external_bookings(
                self.db,
                team=team,
                year=year,
                quarter=q,
                employee_ids=[e.id for e in employees],
                start=period_start,
                end=last_day,
            )
        )
        booked_by_emp: dict[str, float] = {}
        pool_share = self._pool_share(scenario)
```

на

```python
        # --- брони других команд: учитываются только дни, вошедшие в брутто ---
        # Вычитаются брони команд, где человек тоже состоит; брони команд,
        # взявших его к себе, — только справочно.
        bookings = cto.external_bookings(
            self.db,
            team=team,
            year=year,
            quarter=q,
            employee_ids=[e.id for e in employees],
            start=period_start,
            end=last_day,
        )
        booked = cto.daily_totals(b for b in bookings if not b.is_borrowing)
        lent = cto.daily_totals(b for b in bookings if b.is_borrowing)
        booked_by_emp: dict[str, float] = {}
        lent_by_emp: dict[str, float] = {}
        pool_share = self._pool_share(scenario)
```

3.4. В цикле по сотрудникам того же метода заменить

```python
            total = 0.0
            taken = 0.0
            emp_booked = booked.get(e.id, {})
```

на

```python
            total = 0.0
            taken = 0.0
            lent_hours = 0.0
            emp_booked = booked.get(e.id, {})
            emp_lent = lent.get(e.id, {})
```

затем

```python
                        total += norm
                        taken += min(emp_booked.get(cur, 0.0), norm * share)
```

на

```python
                        total += norm
                        taken += min(emp_booked.get(cur, 0.0), norm * share)
                        lent_hours += min(emp_lent.get(cur, 0.0), norm * share)
```

и

```python
            booked_by_emp[e.id] = round(taken, 2)
```

на

```python
            booked_by_emp[e.id] = round(taken, 2)
            lent_by_emp[e.id] = round(lent_hours, 2)
```

3.5. Заменить блок

```python
        # --- брони других команд по ролям ---
        # Внешний QA замещает штатных тестировщиков — их брони не в счёт.
        booked_by_role: dict[str, float] = {}
        for emp_id, h in booked_by_emp.items():
            role = emp_role[emp_id]
            if not role or h <= 0:
                continue
            if role == "qa" and scenario.external_qa_hours is not None:
                continue
            booked_by_role[role] = round(booked_by_role.get(role, 0.0) + h, 2)
```

на

```python
        # --- брони других команд по ролям ---
        def _by_role(hours_by_emp: dict[str, float]) -> dict[str, float]:
            # Внешний QA замещает штатных тестировщиков — их брони не в счёт.
            per_role: dict[str, float] = {}
            for emp_id, h in hours_by_emp.items():
                role = emp_role[emp_id]
                if not role or h <= 0:
                    continue
                if role == "qa" and scenario.external_qa_hours is not None:
                    continue
                per_role[role] = round(per_role.get(role, 0.0) + h, 2)
            return per_role

        booked_by_role = _by_role(booked_by_emp)
        lent_by_role = _by_role(lent_by_emp)
```

3.6. В `return ResourceSummary(...)` после `booked_by_other_teams_by_role=booked_by_role,` добавить
`            borrowed_by_other_teams_by_role=lent_by_role,`

- [ ] **Step 4: Поле в ответе `app/api/endpoints/planning.py`**

В `ResourceSummaryOut` после `booked_by_other_teams_by_role: Dict[str, float] = {}` добавить:

```python
    # Часы команды в планах команд, взявших её людей к себе (не вычтены).
    borrowed_by_other_teams_by_role: Dict[str, float] = {}
```

В `scenario_resource_summary` после `booked_by_other_teams_by_role=summary.booked_by_other_teams_by_role,` добавить
`        borrowed_by_other_teams_by_role=summary.borrowed_by_other_teams_by_role,`

- [ ] **Step 5: Тесты проходят**

Run: `py -3.10 -m pytest tests/services/test_resource_base_external.py -v`, затем соседние: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py -k "resource_base or resource_summary or scenario_resource"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_base_service.py app/api/endpoints/planning.py tests/services/test_resource_base_external.py
git commit -F - <<'EOF'
feat(planning): база сценария не уменьшается на привлечения другими командами

Часы людей команды в планах команд, взявших их к себе, видны справочно
отдельным полем сводки.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task A4: Расшифровка фазы по тому же правилу

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (`explain_assignment`, ~стр. 3494–3507)
- Test: `tests/api/test_rp_cross_team_gantt.py`

- [ ] **Step 1: Падающий тест**

Дописать в `tests/api/test_rp_cross_team_gantt.py`:

```python
def test_explain_home_employee_ignores_borrowing_booking(client, two_teams):
    """Свой сотрудник: бронь команды, взявшей его к себе, «Доступно» в домашнем
    плане не уменьшает — ровно так его видел планировщик."""
    t = two_teams
    r = client.get(f"{BASE}/{t['plan_a']}/assignments/{t['a_row']}/explain")
    assert r.status_code == 200, r.text
    days = {d["date"]: d for d in r.json()["daily_breakdown"]}

    assert days["2026-01-01"]["available_hours"] == 6.0
    assert days["2026-01-01"]["status"] == "work"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `py -3.10 -m pytest "tests/api/test_rp_cross_team_gantt.py::test_explain_home_employee_ignores_borrowing_booking" -v`
Expected: FAIL (`0.0 != 6.0`).

- [ ] **Step 3: Реализация**

В `explain_assignment` заменить

```python
        # «Доступно» — за вычетом броней других команд: ровно то, что видел
        # планировщик при раскладке.
        other_bookings = cto.external_bookings(
            db,
            team=plan.team,
            year=plan.year,
            quarter=cto.quarter_num(plan.quarter),
            employee_ids=[a.employee_id],
            start=horizon_start,
            end=horizon_end,
        )
```

на

```python
        # «Доступно» — за вычетом броней других команд по правилу «сначала
        # домашняя команда»: ровно то, что видел планировщик при раскладке.
        other_bookings = cto.subtractable(
            cto.external_bookings(
                db,
                team=plan.team,
                year=plan.year,
                quarter=cto.quarter_num(plan.quarter),
                employee_ids=[a.employee_id],
                start=horizon_start,
                end=horizon_end,
            ),
            borrowed_here,
        )
```

- [ ] **Step 4: Тесты проходят**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py -v`
Expected: PASS (расшифровки привлечённого не меняются: ему вычитаются все брони).

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/api/test_rp_cross_team_gantt.py
git commit -F - <<'EOF'
fix(resource-planning): расшифровка фазы считает занятость по правилу домашней команды

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task A5: Закреплённая дата — часы по свободным окнам общим раскладчиком

**Files:**
- Modify: `app/services/resource_planning_service.py` (`compute_schedule`: блок закреплённых строк ~694–763, создание `unlaid` ~1073–1074, вызов `_unplaced_conflict_dicts` ~1352–1356; сам `_unplaced_conflict_dicts` ~3172–3267)
- Create: `tests/services/test_rp_pinned_relayout.py`
- Modify: `tests/services/test_compute_schedule_extends_pinned.py`, `tests/services/test_rp_out_of_team_conflict.py`

- [ ] **Step 1: Новые тесты**

```python
# tests/services/test_rp_pinned_relayout.py
"""Закреплённая дата начала: часы раскладываются с неё по свободным окнам."""

import json
from datetime import date, timedelta

from sqlalchemy import select

from app.models import (
    Absence, AbsenceReason, PlanConflict, ProductionCalendarDay, ResourcePlanAssignment,
)
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

D = date.fromisoformat


def _row(db, row_id) -> ResourcePlanAssignment:
    row = db.get(ResourcePlanAssignment, row_id)
    db.refresh(row)
    return row


def _daily(db, row_id) -> dict:
    row = _row(db, row_id)
    return json.loads(row.daily_hours_json) if row.daily_hours_json else {}


def _weekdays(start: str, end: str, hours: float = 6.0) -> dict:
    out, d = {}, D(start)
    while d <= D(end):
        if d.weekday() < 5:
            out[d.isoformat()] = hours
        d += timedelta(days=1)
    return out


def test_pinned_phase_skips_other_team_work(db_session):
    """Шутов состоит в A и B; B занимает его 06.01 — фаза плана A,
    закреплённая с 05.01, этот день обходит."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=6), e,
         {"2026-01-06": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    item = add_item(db_session, sc_a, "Работа A", dev=12)
    row = book(db_session, plan_a, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
               pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    assert _daily(db_session, row.id) == {"2026-01-05": 6.0, "2026-01-07": 6.0}
    fresh = _row(db_session, row.id)
    assert (fresh.start_date, fresh.end_date) == (D("2026-01-05"), D("2026-01-07"))
    assert fresh.pinned_start is True


def test_pinned_phase_of_borrowed_starts_at_first_free_day(db_session):
    """Привлечённый занят домашней командой 05–06.01: закреплённая
    на 05.01 фаза поверх не встаёт и начинается 07.01."""
    e = make_employee(db_session, "Пряничников", "A")
    make_employee(db_session, "Свой B", "B")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=12), e,
         {"2026-01-05": 6.0, "2026-01-06": 6.0})
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12)
    row = book(db_session, plan_b, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
               pinned_start=True, pinned_employee=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _daily(db_session, row.id) == {"2026-01-07": 6.0, "2026-01-08": 6.0}
    assert _row(db_session, row.id).start_date == D("2026-01-07")


def test_pinned_phase_skips_holiday_and_absence(db_session):
    e = make_employee(db_session, "Свой", "T")
    db_session.add(ProductionCalendarDay(
        date=D("2026-01-06"), hours=0.0, is_workday=False, kind="holiday", source="manual",
    ))
    reason = AbsenceReason(code="vacation-pin", label="Отпуск", is_planned=True, is_active=True)
    db_session.add(reason)
    db_session.flush()
    db_session.add(Absence(
        employee_id=e.id, start_date=D("2026-01-07"), end_date=D("2026-01-07"),
        reason_id=reason.id,
    ))
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Работа T", dev=12)
    row = book(db_session, plan, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
               pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _daily(db_session, row.id) == {"2026-01-05": 6.0, "2026-01-08": 6.0}


def test_pinned_phases_of_one_person_take_turns(db_session):
    """Две закреплённые на 05.01 фазы одного человека: старшая задача
    получает 05.01, младшая — следующий свободный день."""
    e = make_employee(db_session, "Свой", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    first = add_item(db_session, sc, "Первая", dev=6, priority=2)
    second = add_item(db_session, sc, "Вторая", dev=6, priority=1)
    r1 = book(db_session, plan, first, e, {"2026-01-05": 6.0}, pinned_start=True)
    r2 = book(db_session, plan, second, e, {"2026-01-05": 6.0}, pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _daily(db_session, r1.id) == {"2026-01-05": 6.0}
    assert _daily(db_session, r2.id) == {"2026-01-06": 6.0}


def test_pinned_testing_phase_follows_its_date(db_session):
    """Тестирование без сотрудника с ручной датой раскладывается по календарю с неё."""
    make_employee(db_session, "Свой", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Работа T")
    item.estimate_qa_hours = 12.0
    qa = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="qa", employee_id=None,
        part_number=1, hours_allocated=12.0,
        start_date=D("2026-01-12"), end_date=D("2026-01-12"), pinned_start=True,
        daily_hours_json=json.dumps({"2026-01-05": 12.0}),
    )
    db_session.add(qa)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _daily(db_session, qa.id) == {"2026-01-12": 6.0, "2026-01-13": 6.0}


def test_pinned_phase_without_free_days_is_reported(db_session):
    """Человек до конца окна занят в команде C, где он тоже состоит, —
    часы закреплённой фазы не размещены, и это видно конфликтом."""
    e = make_employee(db_session, "Свой", "T")
    join_team(db_session, e, "C")
    sc_c, plan_c = make_plan(db_session, "C")
    book(db_session, plan_c, add_item(db_session, sc_c, "Работа C", dev=1), e,
         _weekdays("2026-01-01", "2026-04-30"))
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Работа T", dev=12)
    row = book(db_session, plan, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
               pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _daily(db_session, row.id) == {}
    [c] = db_session.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan.id, PlanConflict.type == "UNPLACED_HOURS"
        )
    ).scalars().all()
    assert c.backlog_item_id == item.id
    assert c.employee_id == e.id
    assert c.metric_value == 12.0
    assert c.message == (
        "Работа T · Разработка 0 из 12 ч — не поместилось в свободные дни исполнителя"
    )
```

- [ ] **Step 2: Поправить ожидания существующих тестов**

2.1. `tests/services/test_compute_schedule_extends_pinned.py` — закреплённая фаза теперь берёт тот же дневной потолок, что и остальные (`min(6, 8 × вовлечённость)`).

Docstring модуля заменить на:

```python
"""Тесты автоматического расширения окна для pinned_start фаз при recompute.

Если после фиксации даты у фазы (`pinned_start=True`) меняются
`hours_allocated`, `involvement` или производственный календарь, то
сохранённый `end_date` может перестать вмещать запланированные часы.
`compute_schedule` раскладывает часы закреплённой фазы заново общим
раскладчиком с закреплённой даты: старт остаётся, конец выводится из
раскладки. Дневной потолок — как у всех фаз: 8 ч × вовлечённость, но не
больше дня календаря (6 ч).
"""
```

В `test_compute_schedule_extends_pinned_start_window` в docstring строки

```
    при involvement=1.0 (cap 6h/день). Затем involvement понижается до 0.6
    (cap 3.6h/день). На 30h теперь нужно ceil(30 / 3.6) = 9 рабочих дней.
    От Mon 20.04.2026: 20,21,22,23,24 (5), 27,28,29,30 (9) — конец Thu 30.04.2026.
```

заменить на

```
    при involvement=1.0 (cap 6h/день). Затем involvement понижается до 0.6
    (cap min(6, 8 × 0.6) = 4.8h/день). На 30h нужно 30 / 4.8 = 6.25 → 7 рабочих
    дней. От Mon 20.04.2026: 20,21,22,23,24 (5), 27,28 (7) — конец Tue 28.04.2026.
```

а проверки

```python
    assert a2.end_date == date(2026, 4, 30), (
        f"end_date должен расшириться до Thu 30.04.2026; получили {a2.end_date}"
    )
```

```python
    # Старая 5-дневная раскладка должна быть заменена на 9-дневную.
    assert len(daily) == 9
    assert "2026-04-30" in daily
```

заменить на

```python
    assert a2.end_date == date(2026, 4, 28), (
        f"end_date должен расшириться до Tue 28.04.2026; получили {a2.end_date}"
    )
```

```python
    # Старая 5-дневная раскладка заменена на 7-дневную.
    assert len(daily) == 7
    assert "2026-04-28" in daily
```

В `test_compute_schedule_non_pinned_unaffected` проверку

```python
    assert pinned_after.end_date == date(2026, 4, 30), (
        f"Pinned end_date должен расшириться до 30.04.2026; "
        f"получили {pinned_after.end_date}"
    )
```

заменить на

```python
    assert pinned_after.end_date == date(2026, 4, 28), (
        f"Pinned end_date должен расшириться до 28.04.2026; "
        f"получили {pinned_after.end_date}"
    )
```

2.2. `tests/services/test_rp_out_of_team_conflict.py` — тест `test_assignment_after_departure_creates_conflict` заменить целиком:

```python
def test_pinned_phase_does_not_run_past_departure(db_session, sample_plan):
    """Закреплённая фаза выбывшего не уходит за дату выбытия: дни вне команды
    не свободны. Недоразложенные часы видны конфликтом «Часы не размещены»."""
    plan, analyst = sample_plan
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    a = (
        db_session.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "analyst",
                ResourcePlanAssignment.employee_id == analyst.id,
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    assert a is not None
    a.pinned_start = True
    db_session.commit()

    # Сотрудник выбывает на второй день своей же фазы.
    membership = (
        db_session.execute(
            select(EmployeeTeam).where(
                EmployeeTeam.employee_id == analyst.id,
                EmployeeTeam.team == plan.team,
            )
        )
        .scalars()
        .one()
    )
    membership.left_at = a.start_date + timedelta(days=1)
    db_session.commit()

    svc.compute_schedule(plan.id)

    db_session.refresh(a)
    assert a.end_date == a.start_date
    conflicts = (
        db_session.execute(select(PlanConflict).where(PlanConflict.plan_id == plan.id))
        .scalars()
        .all()
    )
    assert [c for c in conflicts if c.type == "OUT_OF_TEAM"] == []
    [unplaced] = [c for c in conflicts if c.type == "UNPLACED_HOURS"]
    assert unplaced.employee_id == analyst.id
    assert "Анализ 6 из 40 ч — не поместилось в свободные дни исполнителя" in unplaced.message
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/services/test_rp_pinned_relayout.py tests/services/test_compute_schedule_extends_pinned.py tests/services/test_rp_out_of_team_conflict.py -v`
Expected: FAIL — `test_pinned_phase_skips_other_team_work`, `test_pinned_phase_of_borrowed_starts_at_first_free_day`, `test_pinned_testing_phase_follows_its_date`, `test_pinned_phase_without_free_days_is_reported`, обе правки `extends_pinned`, `test_pinned_phase_does_not_run_past_departure`. Могут пройти и сейчас: `test_pinned_phase_skips_holiday_and_absence` (календарь и отпуск старый путь тоже обходил) и `test_pinned_phases_of_one_person_take_turns` (перегрузку мог развести выравниватель) — после реализации они обязаны проходить без выравнивателя.

- [ ] **Step 4: Реализация в `compute_schedule`**

4.1. Заменить весь блок от строки
`        # Преварительно вычесть часы pinned-сегментов из remaining чтобы не`
до конца цикла `for a in pinned_existing:` включительно (последние строки блока —
`                        d_lock += timedelta(days=1)`; следом идёт
`        new_assignments: List[ResourcePlanAssignment] = list(pinned_existing)`) на:

```python
        # Закреплённая дата — только начало. Часы такой фазы раскладывает тот
        # же раскладчик, что и остальные фазы, с этой даты по свободным окнам:
        # календарь, отсутствия, блокировки, дни вне команды, брони других
        # команд (сначала домашняя команда) и уже разложенные закреплённые
        # фазы этого плана. Поверх чужой работы фаза не встаёт — полоса
        # начнётся с первого свободного дня. Старшие по приоритету задачи
        # занимают дни первыми. pinned_split — только структурный маркер: его
        # часы разложит отдельный проход после сдвига по связям.
        # ``unlaid`` — строки, которым не нашлось ни одного дня: их часы не
        # размещены, это увидит конфликт «Часы не размещены».
        unlaid: set = set()
        item_rank = {it.id: i for i, it in enumerate(items)}
        pinned_start_rows = sorted(
            (x for x in pinned_existing if x.pinned_start),
            key=lambda x: (
                item_rank.get(x.backlog_item_id, len(item_rank)),
                PHASE_ORDER.index(x.phase) if x.phase in PHASE_ORDER else len(PHASE_ORDER),
                x.part_number,
                x.id,
            ),
        )
        for a in pinned_start_rows:
            if not a.start_date or not a.hours_allocated or a.hours_allocated <= 0:
                continue
            bi = self.db.get(BacklogItem, a.backlog_item_id)
            inv = self._involvement_for_phase(bi, a.phase) if bi else None
            if a.employee_id is None:
                # Тестирование — без сотрудника: часы по рабочим дням календаря.
                new_end, daily_json = self._extend_window_for_hours(
                    start_date=a.start_date,
                    hours=float(a.hours_allocated),
                    involvement=inv or 1.0,
                    q_end=q_end_extended,
                )
                a.end_date = new_end
                a.daily_hours_json = daily_json if daily_json != "{}" else None
                a.out_of_quarter = new_end > q_end
                continue
            if a.employee_id not in remaining:
                continue
            day_cap = self._daily_role_capacity(
                avail_hours=8.0,
                involvement=inv,
                parallel_count=_resolve_parallel_count_legacy(bi, a.phase) if bi else 1,
            )
            _, daily = self._allocate_hours_with_breakdown(
                a.employee_id,
                float(a.hours_allocated),
                a.start_date,
                q_end_extended,
                remaining,
                daily_capacity=day_cap,
                preempt_locked=preempt_locked,
                original_capacity=original_avail,
            )
            if daily:
                a.end_date = max(daily)
                a.daily_hours_json = json.dumps(
                    {d.isoformat(): h for d, h in sorted(daily.items())}
                )
            else:
                a.end_date = a.start_date
                a.daily_hours_json = None
                unlaid.add(a.id)
            # Окно — до q_end_extended (буфер spillover), флаг out_of_quarter —
            # относительно строгого q_end.
            a.out_of_quarter = a.end_date > q_end
            # Закреплённые preempting-фазы тоже разрывают чужие фазы.
            if a.phase in PREEMPTING_PHASES:
                locked_set = preempt_locked.setdefault(a.employee_id, set())
                d_lock = a.start_date
                while d_lock <= a.end_date:
                    locked_set.add(d_lock)
                    d_lock += timedelta(days=1)
```

4.2. Ниже, перед первым вызовом `_shift_to_obey_predecessors`, удалить две строки (множество уже создано выше):

```python
        # Строки, которым сдвиг по предшественникам не нашёл ни дня.
        unlaid: set = set()
```

4.3. Вызов проверки неразмещённых часов заменить:

```python
        detected += self._unplaced_conflict_dicts(
            items, new_assignments, alloc_by_item, pinned_phase_keys,
            assignments_by_role, unstaffed, {d["type"] for d in detected},
            unlaid,
            pinned_start={(x.backlog_item_id, x.phase) for x in pinned_start_rows},
        )
```

- [ ] **Step 5: Реализация в `_unplaced_conflict_dicts`**

5.1. В сигнатуре после `unlaid: set,` добавить `pinned_start: Optional[set] = None,`.

5.2. В docstring предложение

```
        Фазы, закреплённые пользователем по датам или разбивке (``skip``),
        не проверяются: их объём он задал сам.
```

заменить на

```
        Фазы, закреплённые пользователем разбивкой (``skip``), не
        проверяются: их объём он задал сам. Фаза с закреплённой датой начала
        (``pinned_start``) сверяется с часами своих же строк: с этой даты их
        не хватило — «не поместилось в свободные дни исполнителя».
```

5.3. Заменить

```python
        placed: Dict[Tuple[str, str], float] = defaultdict(float)
        first_row: Dict[Tuple[str, str], ResourcePlanAssignment] = {}
        for a in assignments:
            key = (a.backlog_item_id, a.phase)
            placed[key] += _placed_hours(a, unlaid)
            first_row.setdefault(key, a)
```

на

```python
        pinned_start = pinned_start or set()
        placed: Dict[Tuple[str, str], float] = defaultdict(float)
        # Закреплённая по дате фаза должна разложить часы своих же строк.
        pinned_need: Dict[Tuple[str, str], float] = defaultdict(float)
        first_row: Dict[Tuple[str, str], ResourcePlanAssignment] = {}
        for a in assignments:
            key = (a.backlog_item_id, a.phase)
            placed[key] += _placed_hours(a, unlaid)
            if key in pinned_start:
                pinned_need[key] += float(a.hours_allocated or 0.0)
            first_row.setdefault(key, a)
```

5.4. Заменить

```python
            for phase in PHASE_ORDER:
                key = (item.id, phase)
                if key in skip:
                    continue
                need = self._phase_hours(item, phase, alloc_by_item)
                got = placed.get(key, 0.0)
                roles = unstaffed.get(key, {})
                gap_roles = {r for r in roles if gap_of[r] in team_gaps}
                need -= sum(roles[r] for r in gap_roles)
                if need <= 0 or got + 0.01 >= need:
                    continue
                reason = (
                    "нет исполнителя"
                    if set(roles) - gap_roles
                    else "не поместилось в квартал и месяц запаса"
                )
```

на

```python
            for phase in PHASE_ORDER:
                key = (item.id, phase)
                roles: Dict[str, float] = {}
                gap_roles: set = set()
                if key in pinned_start:
                    need = pinned_need[key]
                elif key in skip:
                    continue
                else:
                    need = self._phase_hours(item, phase, alloc_by_item)
                    roles = unstaffed.get(key, {})
                    gap_roles = {r for r in roles if gap_of[r] in team_gaps}
                    need -= sum(roles[r] for r in gap_roles)
                got = placed.get(key, 0.0)
                if need <= 0 or got + 0.01 >= need:
                    continue
                if key in pinned_start:
                    reason = "не поместилось в свободные дни исполнителя"
                elif set(roles) - gap_roles:
                    reason = "нет исполнителя"
                else:
                    reason = "не поместилось в квартал и месяц запаса"
```

- [ ] **Step 6: Тесты проходят, расчёт в целом не сломан**

Run: `py -3.10 -m pytest tests/services/test_rp_pinned_relayout.py tests/services/test_compute_schedule_extends_pinned.py tests/services/test_rp_out_of_team_conflict.py tests/services/test_rp_pinned_edits.py tests/services/test_rp_borrowed_staff.py tests/services/test_rp_opo_shift_after_split.py tests/services/test_resource_planning_window_extend.py -v`
Expected: PASS.

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py -k "rp_ or resource_plan or rcpsp"`
Expected: PASS. Если упал тест, где закреплённая фаза раньше сидела поверх занятого дня, — проверить, что новое поведение совпадает с решениями 6–8, и поправить ожидание с комментарием, а не код.

- [ ] **Step 7: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_pinned_relayout.py tests/services/test_compute_schedule_extends_pinned.py tests/services/test_rp_out_of_team_conflict.py
git commit -F - <<'EOF'
feat(resource-planning): закреплённая дата раскладывает часы по свободным окнам

Фаза с ручной датой начала раскладывается общим раскладчиком: мимо
отпусков, праздников, дней вне команды, работы в других командах и
уже закреплённых фаз этого плана. Не хватило дней — конфликт
«Часы не размещены».

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task A6: Перетаскивание задаёт только начало и пересчитывает план

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (`AssignmentPatch` ~567–582, `patch_assignment` ~1932–2054)
- Modify: `tests/api/test_resource_planning_patch_extends_end.py`, `tests/test_rp_pinned_start_ux.py`
- Create: `tests/api/test_rp_drag_relayout.py`

- [ ] **Step 1: Тесты**

1.1. В `tests/api/test_resource_planning_patch_extends_end.py` docstring модуля заменить на:

```python
"""PATCH start_date: конец фазы и часы по дням считает планировщик.

Перетаскивание задаёт только дату начала. Сервер ставит закрепление даты,
пересчитывает план целиком, а часы фазы раскладывает с новой даты по
свободным дням исполнителя. Присланный клиентом конец не используется.
"""
```

Тест `test_patch_with_explicit_end_date_does_not_auto_extend` заменить целиком двумя тестами:

```python
def test_patch_ignores_client_end_date(client, db_session, dev_plan):
    """Присланный конец не используется: часы раскладываются с новой даты начала."""
    resp = client.patch(
        f"/api/v1/resource-planning/resource-plans/{dev_plan['plan_id']}/assignments/{dev_plan['assignment_id']}",
        json={"start_date": "2026-04-20", "end_date": "2026-04-22"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["start_date"] == "2026-04-20"
    assert body["end_date"] == "2026-04-28"
    assert abs(sum(body["daily_hours"].values()) - 40.0) < 0.01


def test_patch_start_date_recomputes_plan(client, db_session, dev_plan):
    """После перетаскивания план пересчитан — как при смене исполнителя."""
    from app.models import ResourcePlan

    before = db_session.get(ResourcePlan, dev_plan["plan_id"]).computed_at

    resp = client.patch(
        f"/api/v1/resource-planning/resource-plans/{dev_plan['plan_id']}/assignments/{dev_plan['assignment_id']}",
        json={"start_date": "2026-04-20"},
    )

    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    plan = db_session.get(ResourcePlan, dev_plan["plan_id"])
    assert plan.status == "ready"
    assert plan.computed_at > before
```

1.2. В `tests/test_rp_pinned_start_ux.py` фикстура `assignment` использовала план без сценария — пересчёт убрал бы из него строку. Импорт моделей заменить на
`from app.models import BacklogItem, Employee, PlanningScenario, ResourcePlan, ResourcePlanAssignment, ScenarioAllocation`,
а в фикстуре `assignment` заменить

```python
    item = BacklogItem(
        title="pin-ux-item",
        estimate_analyst_hours=8.0,
        assignee_employee_id=e.id,
    )
    db.add(item)
    db.flush()

    plan = ResourcePlan(team="PIN_UX", quarter="Q2", year=2026, status="draft")
    db.add(plan)
    db.flush()
```

на

```python
    item = BacklogItem(
        title="pin-ux-item",
        estimate_analyst_hours=8.0,
        assignee_employee_id=e.id,
    )
    db.add(item)
    db.flush()

    # Перетаскивание пересчитывает план — задача должна быть в его сценарии.
    scenario = PlanningScenario(
        name="pin-ux-scenario", quarter="Q2", year=2026, status="draft", team="PIN_UX",
    )
    db.add(scenario)
    db.flush()
    db.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True,
    ))

    plan = ResourcePlan(
        team="PIN_UX", quarter="Q2", year=2026, status="draft", scenario_id=scenario.id,
    )
    db.add(plan)
    db.flush()
```

1.3. Новый файл:

```python
# tests/api/test_rp_drag_relayout.py
"""Перетаскивание фазы: часы раскладываются с новой даты по свободным окнам."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

BASE = "/api/v1/resource-planning/resource-plans"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_drag_onto_other_team_work_lands_on_free_days(client, db_session):
    """Шутов состоит в A и B; B занимает его 05–06.01. Фазу плана A тянут
    на 05.01 — часы ложатся на 07–08.01: поверх чужой работы нельзя."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=12), e,
         {"2026-01-05": 6.0, "2026-01-06": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    item = add_item(db_session, sc_a, "Работа A", dev=12)
    row = book(db_session, plan_a, item, e, {"2026-01-12": 6.0, "2026-01-13": 6.0})
    db_session.commit()

    r = client.patch(
        f"{BASE}/{plan_a.id}/assignments/{row.id}",
        json={"start_date": "2026-01-05", "end_date": "2026-01-06"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["daily_hours"] == {"2026-01-07": 6.0, "2026-01-08": 6.0}
    assert (body["start_date"], body["end_date"]) == ("2026-01-07", "2026-01-08")
    assert body["pinned_start"] is True
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/api/test_resource_planning_patch_extends_end.py tests/api/test_rp_drag_relayout.py tests/test_rp_pinned_start_ux.py -v`
Expected: FAIL `test_patch_ignores_client_end_date` (конец 22.04), `test_patch_start_date_recomputes_plan` (статус `stale`), `test_drag_onto_other_team_work_lands_on_free_days` (часы на 05–06.01); остальные PASS.

- [ ] **Step 3: Реализация**

3.1. В `AssignmentPatch` строку `    end_date: Optional[date] = None` заменить на:

```python
    # Игнорируется: конец фазы и часы по дням считает планировщик. Поле
    # оставлено, чтобы старые клиенты не получали 422.
    end_date: Optional[date] = None
```

3.2. В `patch_assignment` заменить весь блок от строки
`        new_start = patch.get("start_date", a.start_date)`
до проверки включительно

```python
        if new_start and new_end and new_end < new_start:
            raise HTTPException(422, "end_date must be >= start_date")
```

(в него входит ветка `_extend_window_for_hours`) на:

```python
        # Конец фазы и часы по дням считает планировщик: перетаскивание задаёт
        # только начало, присланный конец не используется.
        patch.pop("end_date", None)
        start_changed = "start_date" in patch
```

3.3. Строку `        elif "start_date" in patch:` заменить на `        elif start_changed:`.

3.4. Заменить

```python
        # Любая смена сотрудника — полный пересчёт плана. pinned_employee=True
        # гарантирует, что выбор сохранится; остальные фазы этого сотрудника
        # пройдут через leveler и сдвинутся, чтобы разрулить перегрузки, обойти
        # отпуска и не упасть на выходные/праздники нового исполнителя.
        if "employee_id" in patch and plan:
```

на

```python
        # Смена сотрудника или даты начала — полный пересчёт плана.
        # pinned_employee / pinned_start сохраняют выбор; часы закреплённой
        # фазы раскладываются с её даты по свободным дням, остальные фазы
        # сдвигаются, чтобы разрулить перегрузки, обойти отпуска и не упасть
        # на выходные/праздники исполнителя.
        if ("employee_id" in patch or start_changed) and plan:
```

- [ ] **Step 4: Тесты проходят**

Run: `py -3.10 -m pytest tests/api/test_resource_planning_patch_extends_end.py tests/api/test_rp_drag_relayout.py tests/test_rp_pinned_start_ux.py tests/test_api_assignment_patch.py tests/test_api_assignment_split.py tests/test_api_entity_changed_resource_planning.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/api/test_resource_planning_patch_extends_end.py tests/test_rp_pinned_start_ux.py tests/api/test_rp_drag_relayout.py
git commit -F - <<'EOF'
feat(resource-planning): перетаскивание фазы задаёт только начало и пересчитывает план

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task A7: Диаграмма — брони всех людей плана, пересечения, устаревание

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (`ExternalBookingOut` ~534–549, `GanttProjection` ~552–564, `get_gantt` ~1294–1484)
- Test: `tests/api/test_rp_cross_team_gantt.py`

- [ ] **Step 1: Тесты**

В `tests/api/test_rp_cross_team_gantt.py`:

1.1. В `test_borrower_plan_shows_overlap_bookings_and_borrowed_row` после
`    assert body["external_bookings"][0]["employee_name"] == "Пряничников"` добавить:

```python
    assert body["external_bookings"][0]["employee_is_borrowed"] is True
    assert body["external_bookings"][0]["is_borrowing"] is False
    assert body["external_bookings"][0]["overlap_days"] == ["2026-01-01", "2026-01-02"]
```

1.2. В `test_home_plan_shows_other_team_share_without_conflict` строку
`    assert body["external_bookings"] == []` заменить на:

```python
    # Домашней команде видно, куда забрали её человека.
    [b] = body["external_bookings"]
    assert (b["employee_id"], b["team"]) == (t["e"], "B")
    assert b["employee_is_borrowed"] is False
    assert b["is_borrowing"] is True
    # В эти дни и домашний план занял человека — техкоманда получит конфликт.
    assert b["overlap_days"] == ["2026-01-01", "2026-01-02"]
```

1.3. В `test_no_live_conflict_when_borrower_fits_next_to_booking` после
`    assert [c for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"] == []` добавить:

```python
    assert body["external_bookings"][0]["overlap_days"] == []
```

1.4. Дописать в конец файла:

```python
def test_borrower_plan_is_stale_after_home_plan_changed(client, db_session, two_teams):
    """План B считался раньше, чем поменялась бронь домашней команды A."""
    from datetime import datetime

    from app.models import ResourcePlan

    t = two_teams
    db_session.get(ResourcePlan, t["plan_b"]).computed_at = datetime(2026, 1, 1)
    db_session.commit()

    body = _gantt(client, t["plan_b"])

    assert body["stale_due_to_other_teams"] is True
    assert body["stale_teams"] == ["A"]


def test_plan_computed_after_changes_is_not_stale(client, db_session, two_teams):
    from datetime import datetime, timedelta

    from app.models import ResourcePlan

    t = two_teams
    db_session.get(ResourcePlan, t["plan_b"]).computed_at = datetime.utcnow() + timedelta(days=1)
    db_session.commit()

    body = _gantt(client, t["plan_b"])

    assert body["stale_due_to_other_teams"] is False
    assert body["stale_teams"] == []


def test_borrowing_booking_does_not_make_home_plan_stale(client, db_session, two_teams):
    """Бронь техкоманды, взявшей человека к себе, домашний план не занимает —
    и устаревания в нём не даёт."""
    from datetime import datetime

    from app.models import ResourcePlan

    t = two_teams
    db_session.get(ResourcePlan, t["plan_a"]).computed_at = datetime(2026, 1, 1)
    db_session.commit()

    body = _gantt(client, t["plan_a"])

    assert body["stale_due_to_other_teams"] is False
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py -v`
Expected: FAIL (`KeyError: 'employee_is_borrowed'`, `KeyError: 'stale_due_to_other_teams'`, пустой список броней у домашнего плана).

- [ ] **Step 3: Реализация**

3.1. `ExternalBookingOut` заменить целиком:

```python
class ExternalBookingOut(BaseModel):
    """Фаза сотрудника плана в опорном плане другой команды."""

    assignment_id: str
    employee_id: str
    employee_name: Optional[str] = None
    team: str
    issue_key: Optional[str] = None
    title: str
    phase: str
    start: date
    end: date
    # {"YYYY-MM-DD": часы} внутри окна диаграммы (квартал + месяц запаса).
    daily_hours: Dict[str, float] = {}
    # Опорный план — черновик сценария (утверждённого у команды нет).
    provisional: bool = False
    # Человек привлечён в ЭТОТ план (в его команде не состоял ни дня квартала).
    employee_is_borrowed: bool = False
    # Бронь-привлечение: команда брони взяла человека не из своего состава.
    is_borrowing: bool = False
    # Дни брони, где этот план тоже занял человека и вместе выходит больше
    # его дня: там техкоманда получает «Пересечение с другой командой».
    overlap_days: List[date] = []
```

3.2. В `GanttProjection` после поля `external_bookings` заменить его комментарий и добавить поля:

```python
    # Брони людей плана (свои и привлечённые) в опорных планах других команд.
    external_bookings: List[ExternalBookingOut] = []
    # Брони, вычитаемые из доступности плана, изменились после его расчёта:
    # «Планы других команд изменились — нажмите «Распределить»».
    stale_due_to_other_teams: bool = False
    stale_teams: List[str] = []
```

3.3. В `get_gantt` после `    employee_load: list[EmployeeLoadOut] = []` добавить `    changed_teams: list[str] = []`.

3.4. В `get_gantt` заменить

```python
            names = {e.id: e.display_name for e in plan_employees}
            external_out = [
                ExternalBookingOut(
                    assignment_id=b.assignment_id,
                    employee_id=b.employee_id,
                    employee_name=names.get(b.employee_id),
                    team=b.team,
                    issue_key=b.issue_key,
                    title=b.title,
                    phase=b.phase,
                    start=b.start,
                    end=b.end,
                    daily_hours={d.isoformat(): h for d, h in b.daily_hours.items()},
                    provisional=b.provisional,
                )
                for b in bookings
                if b.employee_id in borrowed
            ]
```

на

```python
            names = {e.id: e.display_name for e in plan_employees}
            # Дни, где этот план и брони других команд вместе больше дня
            # человека, — тем же расчётом, что и живой конфликт техкоманды.
            overlap_by_emp = {
                eid: set(cto.overlap_days(used.get(eid, {}), days, avail.get(eid, {})))
                for eid, days in ext_daily.items()
            }
            external_out = [
                ExternalBookingOut(
                    assignment_id=b.assignment_id,
                    employee_id=b.employee_id,
                    employee_name=names.get(b.employee_id),
                    team=b.team,
                    issue_key=b.issue_key,
                    title=b.title,
                    phase=b.phase,
                    start=b.start,
                    end=b.end,
                    daily_hours={d.isoformat(): h for d, h in b.daily_hours.items()},
                    provisional=b.provisional,
                    employee_is_borrowed=b.employee_id in borrowed,
                    is_borrowing=b.is_borrowing,
                    overlap_days=sorted(
                        d
                        for d in overlap_by_emp.get(b.employee_id, ())
                        if b.daily_hours.get(d, 0.0) > 0
                    ),
                )
                for b in bookings
            ]
            # План устарел, если вычитаемые из его доступности брони
            # поменялись после расчёта. Считается при чтении, не хранится.
            changed_teams = cto.stale_teams(
                cto.subtractable(bookings, borrowed), plan.computed_at
            )
```

3.5. В `return GanttProjection(...)` после `external_bookings=external_out,` добавить:

```python
        stale_due_to_other_teams=bool(changed_teams),
        stale_teams=changed_teams,
```

- [ ] **Step 4: Тесты проходят**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py tests/api/test_resource_planning_gantt_employee_load.py tests/api/test_resource_planning_gantt_reset_counts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/api/test_rp_cross_team_gantt.py
git commit -F - <<'EOF'
feat(resource-planning): диаграмма показывает брони всех людей плана и устаревание

Для своих сотрудников видно, куда их забрали другие команды и где это
пересекается с планом; признак «планы других команд изменились после
расчёта» считается при чтении.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task A8: Настройки вида меняют только присланные поля

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (`patch_user_rp_preferences` ~691–715)
- Test: `tests/test_api_user_rp_preferences.py`

- [ ] **Step 1: Падающий тест**

Дописать в `tests/test_api_user_rp_preferences.py`:

```python
def test_patch_changes_only_sent_fields(db_session, client_factory):
    """Переключатель «Задачи / Исполнители» шлёт одно поле — остальные
    настройки не сбрасываются к значениям по умолчанию."""
    user = _make_user(db_session, "u3@example.com")
    client = client_factory(user)
    client.patch(
        "/api/v1/resource-planning/preferences",
        json={"hide_weekends": True, "fill_intensity_pct": 80},
    )

    r = client.patch("/api/v1/resource-planning/preferences", json={"view_mode": "people"})

    assert r.status_code == 200, r.text
    body = client.get("/api/v1/resource-planning/preferences").json()
    assert body["view_mode"] == "people"
    assert body["hide_weekends"] is True
    assert body["fill_intensity_pct"] == 80
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `py -3.10 -m pytest tests/test_api_user_rp_preferences.py -v`
Expected: FAIL (`hide_weekends` стал `False`).

- [ ] **Step 3: Реализация**

В `patch_user_rp_preferences` заменить блок присваиваний

```python
    p.hide_weekends = payload.hide_weekends
    p.collapsed_initiative_ids = list(payload.collapsed_initiative_ids or [])
    p.view_mode = payload.view_mode
    p.show_relay = payload.show_relay
    p.detail_sections_visible = dict(payload.detail_sections_visible or {})
    p.detail_sections_collapsed = dict(payload.detail_sections_collapsed or {})
    p.fill_intensity_pct = max(0, min(100, payload.fill_intensity_pct))
    p.fill_contrast_pct = max(0, min(100, payload.fill_contrast_pct))
    p.pulse_highlighted_employee = payload.pulse_highlighted_employee
    p.pulse_critical_path = payload.pulse_critical_path
    p.out_of_quarter_months = max(0, min(3, payload.out_of_quarter_months))
    p.hide_weekend_stripes_week_mode = payload.hide_weekend_stripes_week_mode
```

на

```python
    # Меняем только присланные поля: переключатели шлют по одному полю,
    # остальное не должно сбрасываться к значениям по умолчанию.
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key in ("fill_intensity_pct", "fill_contrast_pct"):
            value = max(0, min(100, value))
        elif key == "out_of_quarter_months":
            value = max(0, min(3, value))
        elif key == "collapsed_initiative_ids":
            value = list(value or [])
        elif key in ("detail_sections_visible", "detail_sections_collapsed"):
            value = dict(value or {})
        setattr(p, key, value)
```

- [ ] **Step 4: Тесты проходят**

Run: `py -3.10 -m pytest tests/test_api_user_rp_preferences.py tests/test_user_rp_preferences_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit и прогон группы**

```bash
git add app/api/endpoints/resource_planning.py tests/test_api_user_rp_preferences.py
git commit -F - <<'EOF'
fix(resource-planning): настройки вида меняют только присланные поля

Раньше сворачивание задачи или смена вида сбрасывали остальные
настройки страницы к значениям по умолчанию.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py`
Expected: PASS весь бэкенд. `ruff check app/services/cross_team_occupancy.py app/services/resource_planning_service.py app/services/resource_base_service.py app/api/endpoints/resource_planning.py app/api/endpoints/planning.py` — без новых замечаний.

---

## Группа B — бэкенд исполнителя сценария

### Task B1: Общая функция подбора кандидатов

**Files:**
- Create: `app/services/assignee_candidates.py`
- Test: `tests/services/test_assignee_candidates.py`

- [ ] **Step 1: Падающие тесты**

```python
# tests/services/test_assignee_candidates.py
"""Кандидаты в исполнители: общая функция для фазы плана и строки сценария."""

from datetime import date

from app.models.employee_team import EmployeeTeam
from app.services.assignee_candidates import candidate_groups, jira_assignee_id
from tests.services.xteam_factory import add_item, book, make_employee, make_issue, make_plan

D = date.fromisoformat
Q1 = dict(start=D("2026-01-01"), end=D("2026-03-31"), year=2026, quarter=1)


def test_three_groups_with_quarter_load(db_session):
    e = make_employee(db_session, "Пряничников", "A")
    own = make_employee(db_session, "Свой B", "B")
    other = make_employee(db_session, "Посторонний", "C")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=12), e,
         {"2026-01-05": 6.0, "2026-01-06": 6.0})
    db_session.commit()

    groups = candidate_groups(db_session, team="B", jira_employee_id=e.id, **Q1)

    by_key = {g.key: g for g in groups}
    assert [g.key for g in groups] == ["jira", "team", "other"]
    assert by_key["jira"].label == "Из Jira"
    assert [c.employee_id for c in by_key["jira"].employees] == [e.id]
    assert [c.employee_id for c in by_key["team"].employees] == [own.id]
    assert [c.employee_id for c in by_key["other"].employees] == [other.id]
    assert by_key["jira"].employees[0].team == "A"
    assert 0 < by_key["jira"].employees[0].load_pct < 10  # 12 ч из 384
    assert by_key["team"].employees[0].load_pct == 0.0


def test_people_outside_teams_and_empty_groups_skipped(db_session):
    own = make_employee(db_session, "Свой B", "B")
    make_employee(db_session, "Automation for Jira", None, member=False)
    gone = make_employee(db_session, "Ушедший", "C", member=False)
    db_session.add(EmployeeTeam(employee_id=gone.id, team="C", is_primary=True,
                                left_at=D("2025-12-01")))
    db_session.commit()

    groups = candidate_groups(db_session, team="B", jira_employee_id=gone.id, **Q1)

    assert [(g.key, [c.employee_id for c in g.employees]) for g in groups] == [
        ("team", [own.id])
    ]


def test_member_borders_inside_quarter(db_session):
    leaving = make_employee(db_session, "Выбывает", "B", member=False)
    db_session.add(EmployeeTeam(employee_id=leaving.id, team="B", is_primary=True,
                                left_at=D("2026-02-11")))
    db_session.commit()

    [team] = candidate_groups(db_session, team="B", jira_employee_id=None, **Q1)

    assert team.employees[0].member_from is None
    assert team.employees[0].member_to == D("2026-02-10")


def test_jira_assignee_found_by_account(db_session, sample_project):
    e = make_employee(db_session, "Из Jira", "A", jira_account_id="acc-j")
    issue = make_issue(db_session, sample_project, "RFA-7")
    issue.assignee_account_id = "acc-j"
    db_session.commit()

    assert jira_assignee_id(db_session, issue) == e.id
    issue.assignee_account_id = None
    assert jira_assignee_id(db_session, issue) is None
    assert jira_assignee_id(db_session, None) is None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/services/test_assignee_candidates.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.assignee_candidates'`).

- [ ] **Step 3: Реализация**

```python
# app/services/assignee_candidates.py
"""Кандидаты в исполнители — общая функция для фазы плана и строки сценария.

Кандидат — активный сотрудник, состоявший хоть в какой-то команде хотя бы
день квартала (боты и люди вне команд не попадают). Группы: «Из Jira» (кого
показать, решает вызывающий), «Моя команда» (состав команды за квартал),
«Другие команды». У каждого — загрузка за квартал по опорным планам всех
команд. Пустые группы не возвращаются. Чистое чтение.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Employee, EmployeeTeam, Issue
from app.services import cross_team_occupancy as cto
from app.services import team_membership as tm


@dataclass
class Candidate:
    """Кандидат в исполнители."""

    employee_id: str
    display_name: str
    role: Optional[str]
    team: Optional[str]
    # Загрузка за квартал по всем опорным планам команд, %.
    load_pct: float
    # Границы участия в команде внутри квартала; None — край покрыт.
    member_from: Optional[date]
    member_to: Optional[date]


@dataclass
class CandidateGroup:
    """Группа кандидатов: key — "jira" | "team" | "other"."""

    key: str
    label: str
    employees: List[Candidate]


def candidate_groups(
    db: Session,
    *,
    team: Optional[str],
    start: date,
    end: date,
    year: Optional[int],
    quarter: Optional[int],
    jira_employee_id: Optional[str],
) -> List[CandidateGroup]:
    """Все, кто в квартале ``start`` — ``end`` состоит в какой-либо команде, группами.

    ``team`` — команда группы «Моя команда»; ``jira_employee_id`` — кого
    показать в группе «Из Jira» (если он среди кандидатов). Загрузка
    считается, только если известны год и квартал.
    """
    employees = list(
        db.execute(
            select(Employee).where(
                Employee.is_active == True,  # noqa: E712
                exists().where(
                    EmployeeTeam.employee_id == Employee.id,
                    *tm.overlaps_clause(start, end),
                ),
            )
        )
        .scalars()
        .all()
    )
    by_id = {e.id: e for e in employees}
    member_iv = tm.member_intervals(db, [team], start, end) if team else {}
    jira_ids = [jira_employee_id] if jira_employee_id in by_id else []
    load = cto.quarter_load_pct(db, year, quarter, employees) if year and quarter else {}

    def _out(e: Employee) -> Candidate:
        iv = member_iv.get(e.id) or []
        # Отрезки могут вкладываться — конец участия = самый поздний конец.
        iv_end = max((hi for _, hi in iv), default=None)
        return Candidate(
            employee_id=e.id,
            display_name=e.display_name,
            role=e.role,
            team=e.team,
            load_pct=load.get(e.id, 0.0),
            member_from=iv[0][0] if iv and iv[0][0] > start else None,
            member_to=iv_end if iv_end is not None and iv_end < end else None,
        )

    rest = sorted(
        (e for e in employees if e.id not in jira_ids),
        key=lambda e: (e.display_name or "").lower(),
    )
    groups = [
        CandidateGroup("jira", "Из Jira", [_out(by_id[i]) for i in jira_ids]),
        CandidateGroup("team", "Моя команда", [_out(e) for e in rest if e.id in member_iv]),
        CandidateGroup(
            "other", "Другие команды", [_out(e) for e in rest if e.id not in member_iv]
        ),
    ]
    return [g for g in groups if g.employees]


def jira_assignee_id(db: Session, issue: Optional[Issue]) -> Optional[str]:
    """Сотрудник, стоящий исполнителем задачи в Jira (по учётной записи)."""
    account = issue.assignee_account_id if issue is not None else None
    if not account:
        return None
    return (
        db.execute(select(Employee.id).where(Employee.jira_account_id == account))
        .scalars()
        .first()
    )
```

- [ ] **Step 4: Тесты проходят**

Run: `py -3.10 -m pytest tests/services/test_assignee_candidates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/assignee_candidates.py tests/services/test_assignee_candidates.py
git commit -F - <<'EOF'
feat(planning): общая функция подбора кандидатов в исполнители

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task B2: Эндпоинт кандидатов строки сценария

**Files:**
- Modify: `app/api/endpoints/planning.py` (импорты; новый эндпоинт после `patch_allocation_assignee`)
- Test: `tests/api/test_scenario_assignee.py`

- [ ] **Step 1: Падающие тесты**

```python
# tests/api/test_scenario_assignee.py
"""Исполнитель строки сценария: кандидаты из всех команд; ручной выбор
держится, пока в Jira не сменят исполнителя."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, ScenarioAllocation
from app.models.project import Project
from tests.services.xteam_factory import add_item, make_employee, make_issue, make_plan

PLANNING = "/api/v1/planning/scenarios"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def row(db_session):
    """Строка черновика команды B; в Jira исполнитель задачи — «Из Jira» (команда A)."""
    project = Project(jira_project_id="p-rfa", key="RFA", name="RFA")
    db_session.add(project)
    db_session.flush()
    jira_person = make_employee(db_session, "Из Jira", "A", jira_account_id="acc-jira")
    own = make_employee(db_session, "Свой B", "B")
    chosen = make_employee(db_session, "Выбранный", "C", jira_account_id="acc-chosen")
    issue = make_issue(db_session, project, "RFA-1")
    issue.issue_type = "RFA"
    issue.assigned_category = "initiatives_rfa"
    issue.category = "initiatives_rfa"
    issue.assignee_account_id = "acc-jira"
    issue.assignee_display_name = "Из Jira"
    sc, _plan = make_plan(db_session, "B", scenario_status="draft")
    item = add_item(db_session, sc, "RFA-1", issue=issue, assignee=jira_person)
    alloc = (
        db_session.query(ScenarioAllocation)
        .filter_by(scenario_id=sc.id, backlog_item_id=item.id)
        .one()
    )
    db_session.commit()
    return SimpleNamespace(
        sc=sc, item=item, alloc=alloc, issue=issue,
        jira=jira_person, own=own, chosen=chosen,
    )


def test_scenario_candidates_from_all_teams(client, row):
    r = client.get(
        f"{PLANNING}/{row.sc.id}/assignee-candidates",
        params={"backlog_item_id": row.item.id},
    )

    assert r.status_code == 200, r.text
    groups = {g["key"]: g for g in r.json()}
    assert [c["employee_id"] for c in groups["jira"]["employees"]] == [row.jira.id]
    assert groups["jira"]["employees"][0]["team"] == "A"
    assert [c["employee_id"] for c in groups["team"]["employees"]] == [row.own.id]
    assert [c["employee_id"] for c in groups["other"]["employees"]] == [row.chosen.id]


def test_scenario_candidates_unknown_item_is_404(client, row):
    r = client.get(
        f"{PLANNING}/{row.sc.id}/assignee-candidates", params={"backlog_item_id": "nope"}
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/api/test_scenario_assignee.py -v`
Expected: FAIL (404 на несуществующий маршрут у первого теста; второй может пройти).

- [ ] **Step 3: Реализация в `app/api/endpoints/planning.py`**

3.1. Импорты: после `import calendar` добавить `from dataclasses import asdict`; к импортам приложения добавить

```python
from app.api.endpoints.resource_planning import CandidateGroupOut
from app.services.assignee_candidates import candidate_groups, jira_assignee_id
from app.services.cross_team_occupancy import quarter_num
```

3.2. После функции `patch_allocation_assignee` (перед `# === Scenario resource base ===`) добавить:

```python
@router.get(
    "/scenarios/{scenario_id}/assignee-candidates",
    response_model=List[CandidateGroupOut],
)
def scenario_assignee_candidates(
    scenario_id: str,
    backlog_item_id: str = Query(..., description="Задача бэклога — строка сценария"),
    db: Session = Depends(get_db),
):
    """Кандидаты в исполнители строки сценария.

    Все, кто в квартале сценария состоит в какой-либо команде, группами
    «Из Jira» (исполнитель задачи в Jira) / «Моя команда» / «Другие команды»,
    у каждого — загрузка за квартал по опорным планам команд. Пустые группы
    не возвращаются.
    """
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    in_scenario = (
        db.query(ScenarioAllocation.id)
        .filter(
            ScenarioAllocation.scenario_id == scenario_id,
            ScenarioAllocation.backlog_item_id == backlog_item_id,
        )
        .first()
    )
    if not in_scenario:
        raise HTTPException(status_code=404, detail="Allocation not found")
    quarter = quarter_num(scenario.quarter)
    if not scenario.year or not quarter:
        raise HTTPException(status_code=400, detail="Год/квартал у сценария не заданы")
    start, end = quarter_bounds(scenario.year, quarter)
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.id == backlog_item_id)
        .first()
    )
    groups = candidate_groups(
        db,
        team=scenario.team,
        start=start,
        end=end,
        year=scenario.year,
        quarter=quarter,
        jira_employee_id=jira_assignee_id(db, item.issue if item else None),
    )
    return [asdict(g) for g in groups]
```

- [ ] **Step 4: Тесты проходят**

Run: `py -3.10 -m pytest tests/api/test_scenario_assignee.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/planning.py tests/api/test_scenario_assignee.py
git commit -F - <<'EOF'
feat(planning): кандидаты в исполнители строки сценария из всех команд

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task B3: Ручной исполнитель не затирается обновлением из Jira

**Files:**
- Create: `alembic/versions/pq05_backlog_assignee_manual.py`, `tests/test_migration_pq05_backlog_assignee_manual.py`, `tests/services/test_backlog_assignee_manual.py`
- Modify: `app/models/backlog_item.py`, `app/services/backlog_service.py`, `app/api/endpoints/backlog.py` (`_perform_refresh.on_issue` ~1004–1011), `app/api/endpoints/planning.py` (`_to_allocation_resp` ~456–515, `patch_allocation_assignee` ~1673–1729)
- Test: `tests/api/test_scenario_assignee.py` (дописать)

- [ ] **Step 1: Проверить голову миграций**

Run: `alembic heads`
Expected: `pq03_issue_plan_sources (head)`. Если голова другая — подставить её в `down_revision` и в тест миграции ниже.

- [ ] **Step 2: Падающие тесты**

2.1. Миграция:

```python
# tests/test_migration_pq05_backlog_assignee_manual.py
"""pq05: признак ручного исполнителя строки — вверх, вниз, снова вверх; Postgres."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
COLUMNS = {"assignee_manual", "assignee_jira_account_at_choice"}


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _columns(db_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns("backlog_items")}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(tmp_path):
    db_path = tmp_path / "pq05.db"
    url = f"sqlite:///{db_path.as_posix()}"
    _alembic(url, "upgrade", "head")
    assert COLUMNS <= _columns(db_path)
    _alembic(url, "downgrade", "pq03_issue_plan_sources")
    assert not (COLUMNS & _columns(db_path))
    _alembic(url, "upgrade", "head")
    assert COLUMNS <= _columns(db_path)


def test_postgres_boolean_default_is_false():
    """На Postgres значение по умолчанию — false, а не 0 (прод падал на v1.9.0).
    SQL берём в офлайн-режиме — сервер Postgres не нужен."""
    sql = _alembic(
        "postgresql://offline:offline@localhost:1/offline",
        "upgrade", "pq03_issue_plan_sources:pq05_backlog_assignee_manual", "--sql",
    )
    assert "ADD COLUMN assignee_manual BOOLEAN DEFAULT false NOT NULL" in sql
    assert "ADD COLUMN assignee_jira_account_at_choice VARCHAR(128)" in sql
```

2.2. Правило обновления из Jira:

```python
# tests/services/test_backlog_assignee_manual.py
"""Исполнитель строки из Jira — если его не выбрали в сценарии вручную."""

from types import SimpleNamespace

from app.models import BacklogItem
from app.services.backlog_service import apply_jira_assignee

EMPS = {"acc-1": SimpleNamespace(id="e1"), "acc-2": SimpleNamespace(id="e2")}


def _item(**kw) -> BacklogItem:
    return BacklogItem(title="x", **kw)


def test_not_manual_follows_jira():
    item = _item(assignee_employee_id=None, assignee_manual=False)

    apply_jira_assignee(item, "acc-1", EMPS)

    assert item.assignee_employee_id == "e1"


def test_unknown_or_empty_jira_assignee_clears():
    item = _item(assignee_employee_id="e1", assignee_manual=False)
    apply_jira_assignee(item, "acc-x", EMPS)
    assert item.assignee_employee_id is None

    item.assignee_employee_id = "e1"
    apply_jira_assignee(item, None, EMPS)
    assert item.assignee_employee_id is None


def test_manual_choice_kept_while_jira_unchanged():
    item = _item(assignee_employee_id="e9", assignee_manual=True,
                 assignee_jira_account_at_choice="acc-1")

    apply_jira_assignee(item, "acc-1", EMPS)

    assert item.assignee_employee_id == "e9"
    assert item.assignee_manual is True


def test_manual_clear_kept_while_jira_unchanged():
    item = _item(assignee_employee_id=None, assignee_manual=True,
                 assignee_jira_account_at_choice="acc-1")

    apply_jira_assignee(item, "acc-1", EMPS)

    assert item.assignee_employee_id is None


def test_manual_choice_dropped_when_jira_assignee_changes():
    item = _item(assignee_employee_id="e9", assignee_manual=True,
                 assignee_jira_account_at_choice="acc-1")

    apply_jira_assignee(item, "acc-2", EMPS)

    assert item.assignee_employee_id == "e2"
    assert item.assignee_manual is False
    assert item.assignee_jira_account_at_choice is None
```

2.3. Дописать в `tests/api/test_scenario_assignee.py`:

```python
def _choose(client, row, employee_id):
    return client.patch(
        f"{PLANNING}/{row.sc.id}/allocations/{row.alloc.id}/assignee",
        json={"assignee_employee_id": employee_id},
    )


def test_manual_choice_from_other_team_is_remembered(client, db_session, row):
    r = _choose(client, row, row.chosen.id)

    assert r.status_code == 200, r.text
    assert r.json()["assignee_employee_id"] == row.chosen.id
    assert r.json()["assignee_display_name"] == "Выбранный"
    db_session.expire_all()
    item = db_session.get(BacklogItem, row.item.id)
    assert item.assignee_manual is True
    assert item.assignee_jira_account_at_choice == "acc-jira"


def test_choosing_jira_assignee_follows_jira_again(client, db_session, row):
    _choose(client, row, row.chosen.id)

    r = _choose(client, row, row.jira.id)

    assert r.status_code == 200, r.text
    db_session.expire_all()
    item = db_session.get(BacklogItem, row.item.id)
    assert item.assignee_manual is False
    assert item.assignee_jira_account_at_choice is None


def test_manual_choice_survives_refresh_until_jira_changes(client, db_session, row, monkeypatch):
    from app.api.endpoints import backlog as backlog_ep

    jira = {"account": "acc-jira"}

    class _FakeJira:
        @classmethod
        def from_db(cls, db):
            return cls()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    async def fake_refresh(self, keys, extra_field_ids=None, on_issue=None, on_progress=None):
        issues = db_session.query(Issue).filter(Issue.key.in_(keys)).all()
        for issue in issues:
            fields = SimpleNamespace(
                assignee=SimpleNamespace(accountId=jira["account"]), _extra={},
            )
            on_issue(SimpleNamespace(fields=fields), issue)
        return len(issues), len(issues)

    monkeypatch.setattr(backlog_ep, "JiraClient", _FakeJira)
    monkeypatch.setattr(backlog_ep, "_discover_field_id", AsyncMock(return_value=None))
    monkeypatch.setattr(backlog_ep.SyncService, "refresh_issues_by_keys", fake_refresh)
    _choose(client, row, row.chosen.id)

    assert client.post("/api/v1/backlog/refresh-from-jira").status_code == 200
    db_session.expire_all()
    assert db_session.get(BacklogItem, row.item.id).assignee_employee_id == row.chosen.id

    # В Jira сменили исполнителя — ручной выбор больше не действует.
    newcomer = make_employee(db_session, "Новый в Jira", "B", jira_account_id="acc-new")
    db_session.commit()
    jira["account"] = "acc-new"
    assert client.post("/api/v1/backlog/refresh-from-jira").status_code == 200
    db_session.expire_all()
    item = db_session.get(BacklogItem, row.item.id)
    assert item.assignee_employee_id == newcomer.id
    assert item.assignee_manual is False
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_migration_pq05_backlog_assignee_manual.py tests/services/test_backlog_assignee_manual.py tests/api/test_scenario_assignee.py -v`
Expected: FAIL (нет ревизии `pq05…`; `ImportError: cannot import name 'apply_jira_assignee'`; `TypeError: 'assignee_manual' is an invalid keyword argument`).

- [ ] **Step 4: Модель и миграция**

4.1. `app/models/backlog_item.py`: импорт `from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, false, true`; после поля `assignee_employee_id` добавить:

```python
    # Исполнитель выбран в сценарии вручную: обновление из Jira его не
    # затирает, пока в Jira не сменят исполнителя. Кто стоял исполнителем
    # в Jira в момент выбора — ``assignee_jira_account_at_choice``
    # (учётная запись Jira; None — в Jira исполнителя не было).
    assignee_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(),
    )
    assignee_jira_account_at_choice: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
```

4.2. Миграция:

```python
# alembic/versions/pq05_backlog_assignee_manual.py
"""backlog_items: исполнитель, выбранный в сценарии вручную

Revision ID: pq05_backlog_assignee_manual
Revises: pq03_issue_plan_sources
Create Date: 2026-09-24

Самодостаточна: не импортирует код приложения.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "pq05_backlog_assignee_manual"
down_revision: Union[str, None] = "pq03_issue_plan_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.add_column(
            sa.Column("assignee_manual", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("assignee_jira_account_at_choice", sa.String(length=128), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_column("assignee_jira_account_at_choice")
        batch.drop_column("assignee_manual")
```

- [ ] **Step 5: Правило обновления из Jira**

5.1. `app/services/backlog_service.py`: импорт типов `from typing import Any, Mapping, Optional, cast`; в импорт моделей добавить `Employee`; после `has_included_ancestor` добавить:

```python
def apply_jira_assignee(
    item: BacklogItem,
    account_id: Optional[str],
    emp_by_account: Mapping[str, Employee],
) -> None:
    """Исполнитель строки бэклога из Jira — если его не выбрали в сценарии вручную.

    Ручной выбор держится, пока в Jira стоит тот же исполнитель, что и в
    момент выбора. Сменили исполнителя в Jira — выбор сбрасывается, строка
    снова следует за Jira.
    """
    account_id = account_id or None
    if item.assignee_manual:
        if account_id == (item.assignee_jira_account_at_choice or None):
            return
        item.assignee_manual = False
        item.assignee_jira_account_at_choice = None
    emp = emp_by_account.get(account_id) if account_id else None
    item.assignee_employee_id = emp.id if emp else None
```

5.2. `app/api/endpoints/backlog.py`: в импорт из `app.services.backlog_service` добавить `apply_jira_assignee`; в `on_issue` заменить

```python
                # Исполнитель
                assignee = getattr(jira_issue.fields, "assignee", None)
                account_id = getattr(assignee, "accountId", None) if assignee else None
                if account_id:
                    emp = emp_by_account.get(account_id)
                    item.assignee_employee_id = emp.id if emp else None
                else:
                    item.assignee_employee_id = None
```

на

```python
                # Исполнитель — если его не выбрали в сценарии вручную.
                assignee = getattr(jira_issue.fields, "assignee", None)
                apply_jira_assignee(
                    item,
                    getattr(assignee, "accountId", None) if assignee else None,
                    emp_by_account,
                )
```

- [ ] **Step 6: Выбор в сценарии и подпись строки (`app/api/endpoints/planning.py`)**

6.1. В `_to_allocation_resp` заменить

```python
    jira_assignee_name = item.issue.assignee_display_name if item.issue else None
    resolved_role = (
        item.assignee.role if item.assignee
        else (
            employee_role_by_name.get(jira_assignee_name)
            if employee_role_by_name and jira_assignee_name
            else None
        )
    )
```

на

```python
    jira_assignee_name = item.issue.assignee_display_name if item.issue else None
    if item.assignee_manual:
        # Выбран в сценарии вручную — показываем выбранного, а не Jira.
        assignee_name = item.assignee.display_name if item.assignee else None
        resolved_role = item.assignee.role if item.assignee else None
    else:
        assignee_name = jira_assignee_name or (
            item.assignee.display_name if item.assignee else None
        )
        resolved_role = (
            item.assignee.role if item.assignee
            else (
                employee_role_by_name.get(jira_assignee_name)
                if employee_role_by_name and jira_assignee_name
                else None
            )
        )
```

и в конструкторе ответа

```python
        assignee_display_name=(
            jira_assignee_name if jira_assignee_name
            else (item.assignee.display_name if item.assignee else None)
        ),
```

на `        assignee_display_name=assignee_name,`

6.2. В `patch_allocation_assignee` docstring заменить на
`"""Сменить исполнителя строки сценария; ручной выбор держится до смены исполнителя в Jira."""`,
а блок

```python
    if data.assignee_employee_id is not None:
        emp = db.query(Employee).filter(Employee.id == data.assignee_employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        backlog_item.assignee_employee_id = data.assignee_employee_id
    else:
        backlog_item.assignee_employee_id = None
```

на

```python
    issue = backlog_item.issue
    jira_account = (issue.assignee_account_id or None) if issue is not None else None
    if data.assignee_employee_id is not None:
        emp = db.query(Employee).filter(Employee.id == data.assignee_employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        backlog_item.assignee_employee_id = data.assignee_employee_id
        chosen_account = emp.jira_account_id or None
    else:
        backlog_item.assignee_employee_id = None
        chosen_account = None
    # Выбрали того, кто и так исполнитель в Jira, — строка снова следует за
    # Jira. Иначе выбор ручной: обновление из Jira его не затрёт, пока там
    # не сменят исполнителя, — запоминаем, кто стоит в Jira сейчас.
    backlog_item.assignee_manual = chosen_account != jira_account
    backlog_item.assignee_jira_account_at_choice = (
        jira_account if backlog_item.assignee_manual else None
    )
```

- [ ] **Step 7: Тесты проходят**

Run: `py -3.10 -m pytest tests/test_migration_pq05_backlog_assignee_manual.py tests/services/test_backlog_assignee_manual.py tests/api/test_scenario_assignee.py tests/test_api_backlog_link.py tests/test_migrations_fresh_db.py -v`
Expected: PASS (`test_upgrade_head_on_empty_postgres` — SKIPPED без `TEST_DATABASE_URL`).

- [ ] **Step 8: Commit**

```bash
git add alembic/versions/pq05_backlog_assignee_manual.py app/models/backlog_item.py app/services/backlog_service.py app/api/endpoints/backlog.py app/api/endpoints/planning.py tests/test_migration_pq05_backlog_assignee_manual.py tests/services/test_backlog_assignee_manual.py tests/api/test_scenario_assignee.py
git commit -F - <<'EOF'
feat(planning): исполнитель, выбранный в сценарии, не затирается обновлением из Jira

Выбор держится, пока в Jira не сменят исполнителя задачи; в строке
сценария показывается выбранный человек.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task B4: Ресурсный план — исполнитель сценария на фазе своей роли (после группы A)

> Начинать, только когда группа A влита: задача правит те же `resource_planning_service.py` и `resource_planning.py`.

**Files:**
- Modify: `app/services/resource_planning_service.py` (`compute_schedule` ~580–589, `_load_borrowed`, `_assign_employees`; новый `_scenario_executor`)
- Modify: `app/api/endpoints/resource_planning.py` (`list_assignment_candidates` ~1685–1789, импорты)
- Modify: `tests/test_resource_planning_assignment_logic.py`
- Create: `tests/services/test_rp_scenario_executor.py`

- [ ] **Step 1: Тесты**

1.1. В `tests/test_resource_planning_assignment_logic.py` тест `test_analyst_assigned_regardless_of_role` заменить целиком:

```python
def test_developer_executor_goes_to_development(db_session):
    """Исполнитель сценария с ролью разработчика встаёт на разработку, а не на анализ."""
    dev = _make_emp(db_session, "Разраб", "developer")
    item = _make_item(
        db_session,
        estimate_analyst_hours=10.0,
        estimate_dev_hours=10.0,
        assignee_employee_id=dev.id,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [dev])
    assert result["dev"][item.id] == dev.id
    assert result["analyst"][item.id] is None
```

1.2. Новый файл:

```python
# tests/services/test_rp_scenario_executor.py
"""Исполнитель строки сценария встаёт на фазу своей роли, в том числе из чужой команды."""

from datetime import date, timedelta

from sqlalchemy import select

from app.models import BacklogItem, PlanConflict, ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, make_employee, make_plan


def _item(db, dev=10.0, analyst=0.0, assignee=None, manual=False):
    it = BacklogItem(
        title="x", priority=1, estimate_dev_hours=dev, estimate_analyst_hours=analyst,
        estimate_qa_hours=0.0, estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
        assignee_manual=manual,
    )
    db.add(it)
    db.flush()
    return it


def _weekdays(start: str, end: str, hours: float = 6.0) -> dict:
    out, d = {}, date.fromisoformat(start)
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out[d.isoformat()] = hours
        d += timedelta(days=1)
    return out


def _rows(db, plan_id, phase):
    return db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            ResourcePlanAssignment.phase == phase,
        )
    ).scalars().all()


def _conflicts(db, plan_id, type_):
    return db.execute(
        select(PlanConflict).where(PlanConflict.plan_id == plan_id, PlanConflict.type == type_)
    ).scalars().all()


def test_analyst_role_executor_takes_analysis(db_session):
    an = make_employee(db_session, "Аналитик", "B", role="analyst")
    consultant = make_employee(db_session, "Консультант", "B", role="консультант")
    item = _item(db_session, dev=0, analyst=8, assignee=consultant)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [an, consultant])

    assert res["analyst"][item.id] == consultant.id


def test_executor_without_role_depends_on_analysis_hours(db_session):
    """Роли нет: на анализ, а если у задачи нет часов анализа — на разработку."""
    x = make_employee(db_session, "Без роли", "B", role=None)
    dev = make_employee(db_session, "Разработчик", "B")
    with_analysis = _item(db_session, dev=10, analyst=8, assignee=x)
    no_analysis = _item(db_session, dev=10, analyst=0, assignee=x)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [with_analysis, no_analysis], [x, dev]
    )

    assert res["analyst"][with_analysis.id] == x.id
    assert res["dev"][with_analysis.id] == dev.id
    assert res["dev"][no_analysis.id] == x.id


def test_executor_beats_jira_developer(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _item(db_session, assignee=own)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], jira_dev={item.id: ext.id}, borrowed={ext.id}
    )

    assert res["dev"][item.id] == own.id


def test_manual_executor_from_other_team_is_used(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _item(db_session, assignee=ext, manual=True)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], borrowed={ext.id}
    )

    assert res["dev"][item.id] == ext.id


def test_manual_executor_from_other_team_is_borrowed_in_plan(db_session):
    make_employee(db_session, "Свой B", "B")
    ext = make_employee(db_session, "Шутов", "A")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12, assignee=ext)
    item.assignee_manual = True
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    rows = _rows(db_session, plan_b.id, "dev")
    assert {r.employee_id for r in rows} == {ext.id}
    assert sum(r.hours_allocated or 0 for r in rows) == 12
    assert _conflicts(db_session, plan_b.id, "OUT_OF_TEAM") == []


def test_busy_manual_executor_is_kept_and_reported(db_session):
    """Явный выбор не заменяется при нехватке времени: часы не размещены."""
    make_employee(db_session, "Свой B", "B")
    ext = make_employee(db_session, "Шутов", "A")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=1), ext,
         _weekdays("2026-01-01", "2026-04-30"))
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12, assignee=ext)
    item.assignee_manual = True
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _rows(db_session, plan_b.id, "dev") == []
    [c] = _conflicts(db_session, plan_b.id, "UNPLACED_HOURS")
    assert c.backlog_item_id == item.id
    assert c.employee_id == ext.id
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_resource_planning_assignment_logic.py tests/services/test_rp_scenario_executor.py -v`
Expected: FAIL `test_developer_executor_goes_to_development`, `test_executor_without_role_depends_on_analysis_hours`, `test_executor_beats_jira_developer`, `test_manual_executor_from_other_team_is_used`, `test_manual_executor_from_other_team_is_borrowed_in_plan`, `test_busy_manual_executor_is_kept_and_reported`; `test_analyst_role_executor_takes_analysis` может пройти.

- [ ] **Step 3: Привлечённые из ручного выбора в `compute_schedule`**

Заменить

```python
        # Привлечённые: закреплены вручную или стоят «Разработчиком» в Jira,
        # но в команде плана не состояли ни дня квартала.
        jira_dev = jira_developers_for_items(self.db, items, q_start, q_end)
        team_ids = {e.id for e in team_employees}
        borrowed_rows = self._load_borrowed(
            (set(pinned_map.values()) | set(jira_dev.values())) - team_ids
        )
```

на

```python
        # Привлечённые: закреплены вручную, стоят «Разработчиком» в Jira или
        # выбраны исполнителем строки в сценарии вручную, но в команде плана
        # не состояли ни дня квартала.
        jira_dev = jira_developers_for_items(self.db, items, q_start, q_end)
        manual_executors = {
            it.assignee_employee_id
            for it in items
            if it.assignee_manual and it.assignee_employee_id
        }
        team_ids = {e.id for e in team_employees}
        borrowed_rows = self._load_borrowed(
            (set(pinned_map.values()) | set(jira_dev.values()) | manual_executors)
            - team_ids
        )
```

и в docstring `_load_borrowed` строку `        Источники — ручное закрепление фазы и «Разработчик» из Jira.` заменить на
`        Источники — ручное закрепление фазы, «Разработчик» из Jira и исполнитель, выбранный в сценарии вручную.`

- [ ] **Step 4: `_assign_employees` и `_scenario_executor`**

Функцию `_assign_employees` заменить целиком и сразу после неё добавить `_scenario_executor`:

```python
    def _assign_employees(
        self,
        items: List[BacklogItem],
        employees: List[Employee],
        pinned: Optional[Dict[Tuple[str, str, int], str]] = None,
        alloc_by_item: Optional[Dict[str, ScenarioAllocation]] = None,
        emp_group: Optional[Dict[str, str]] = None,
        item_group: Optional[Dict[str, str]] = None,
        capacity: Optional[Dict[str, float]] = None,
        jira_dev: Optional[Dict[str, str]] = None,
        borrowed: Optional[set] = None,
    ) -> Dict[str, Dict[str, Optional[str]]]:
        """{phase: {item_id: employee_id|None}} с учётом ролей и закреплений.

        Исполнитель фазы, по убыванию приоритета: закреп вручную (``pinned``:
        {(item_id, phase, part_number): employee_id}) → исполнитель строки
        сценария на фазе своей роли (см. `_scenario_executor`) → для разработки
        «Разработчик» из Jira (``jira_dev``, из любой команды), если его ёмкости
        квартала (``capacity`` — уже за вычетом броней других команд) хватает
        на часы разработки → жадный подбор внутри команды: анализ — из пула
        ANALYST_ROLES, разработка — из DEV_ROLES (fallback — вся команда).
        В команде с группами сначала перебираются свои по группе; сосед из
        другой группы берётся, только когда своих уже не хватает по ёмкости
        квартала (см. `_pick_in_group`). Закреп и исполнителя сценария
        нехватка времени не отменяет: неразмещённые часы дают конфликт.
        - qa:  всегда None (часы-only, дату назначаем без сотрудника).
        - opo: не возвращается — реально создаётся как 2 строки через
               `_opo_split` в compute_schedule.

        ``borrowed`` — привлечённые из других команд: в жадные пулы не
        попадают; в план — закрепом, как «Разработчик» из Jira или как
        исполнитель, выбранный в сценарии вручную.
        """
        pinned = pinned or {}
        alloc_by_item = alloc_by_item or {}
        emp_group = emp_group or {}
        item_group = item_group or {}
        capacity = capacity or {}
        jira_dev = jira_dev or {}
        borrowed = borrowed or set()
        # Жадный подбор и подстановка по имени — только из своей команды.
        team_emps = [e for e in employees if e.id not in borrowed]
        all_by_id: Dict[str, Employee] = {e.id: e for e in employees}
        by_id: Dict[str, Employee] = {e.id: e for e in team_emps}
        # Резолв по display_name для fallback (если bk.assignee_employee_id NULL,
        # но в связанной Issue есть assignee_display_name — пробуем найти сотрудника).
        by_name: Dict[str, str] = {}
        for e in team_emps:
            if e.display_name:
                # При коллизии имён берём первого; production-correct fix —
                # заполнять BacklogItem.assignee_employee_id при refresh-from-jira.
                by_name.setdefault(e.display_name.strip().lower(), e.id)

        dev_ids = [e.id for e in team_emps if (e.role or "").lower() in DEV_ROLES]
        if not dev_ids:
            dev_ids = [e.id for e in team_emps]

        analyst_ids = [e.id for e in team_emps if (e.role or "").lower() in ANALYST_ROLES]

        load: Dict[str, float] = defaultdict(float)
        result: Dict[str, Dict[str, Optional[str]]] = {p: {} for p in PHASE_ORDER}

        for item in items:
            an_hours = self._phase_hours(item, "analyst", alloc_by_item)
            dev_hours = self._phase_hours(item, "dev", alloc_by_item)
            executor_id, executor_phase = self._scenario_executor(
                item, all_by_id, by_id, by_name, an_hours
            )

            # ── analyst ────────────────────────────────────────────────
            analyst_id: Optional[str] = pinned.get((item.id, "analyst", 1))
            if not analyst_id and executor_phase == "analyst":
                analyst_id = executor_id
            # Исполнителя анализа нет — наименее загруженный из пула
            # аналитиков команды, чтобы фаза «Анализ» всё равно появилась.
            if not analyst_id and analyst_ids:
                analyst_id = self._pick_in_group(
                    analyst_ids, item_group.get(item.id), load, an_hours,
                    emp_group, capacity,
                )
            if analyst_id:
                load[analyst_id] += an_hours
            result["analyst"][item.id] = analyst_id

            # ── dev ────────────────────────────────────────────────────
            dev_id: Optional[str] = pinned.get((item.id, "dev", 1))
            if not dev_id and executor_phase == "dev":
                dev_id = executor_id
            jira_id = jira_dev.get(item.id)
            # Занятый «Разработчик» из Jira не получает работу, которую некуда
            # положить: без этой проверки фаза без единого свободного дня
            # пропадала из плана молча.
            if (
                not dev_id
                and jira_id
                and load[jira_id] + dev_hours <= capacity.get(jira_id, float("inf"))
            ):
                dev_id = jira_id
            if not dev_id and dev_ids:
                dev_id = self._pick_in_group(
                    dev_ids, item_group.get(item.id), load, dev_hours,
                    emp_group, capacity,
                )
            if dev_id:
                load[dev_id] += dev_hours
            result["dev"][item.id] = dev_id

            # ── qa: без сотрудника ─────────────────────────────────────
            result["qa"][item.id] = None

            # OPO здесь не пишем — реальные 2 строки (analyst+dev) создаются
            # через _opo_split в compute_schedule.

        return result

    def _scenario_executor(
        self,
        item: BacklogItem,
        all_by_id: Dict[str, Employee],
        team_by_id: Dict[str, Employee],
        by_name: Dict[str, str],
        an_hours: float,
    ) -> Tuple[Optional[str], Optional[str]]:
        """(исполнитель строки сценария, фаза, на которую он встаёт) или (None, None).

        Выбранный в сценарии вручную — из любой команды (станет привлечённым).
        Подтянутый из Jira — только свой: исполнитель инициативы из чужой
        команды часто заказчик. Своего исполнителя нет — ищем своего по имени
        исполнителя задачи в Jira. Фаза — по роли: разработчик → разработка;
        аналитик, РП, консультант → анализ; роли нет или иная → анализ, а
        если у задачи нет часов анализа — разработка.
        """
        eid = item.assignee_employee_id
        if item.assignee_manual:
            emp = all_by_id.get(eid) if eid else None
        else:
            emp = team_by_id.get(eid) if eid else None
            issue = item.issue
            if emp is None and issue is not None and issue.assignee_display_name:
                name_id = by_name.get(issue.assignee_display_name.strip().lower())
                emp = team_by_id.get(name_id) if name_id else None
        if emp is None:
            return None, None
        role = (emp.role or "").lower()
        if role in DEV_ROLES:
            return emp.id, "dev"
        if role in ANALYST_ROLES or an_hours > 0:
            return emp.id, "analyst"
        return emp.id, "dev"
```

- [ ] **Step 5: Кандидаты фазы — через общую функцию (`app/api/endpoints/resource_planning.py`)**

5.1. Импорты: `from sqlalchemy import exists, select` → `from sqlalchemy import select`; добавить `from dataclasses import asdict` и `from app.services.assignee_candidates import candidate_groups`.

5.2. Тело `list_assignment_candidates` заменить (сигнатура и декоратор те же):

```python
    """Все, кто в квартале плана состоит в какой-либо команде, тремя группами:
    «Из Jira», «Моя команда», «Другие команды» (общая с выбором исполнителя
    строки сценария функция ``assignee_candidates.candidate_groups``).

    «Из Jira»: для разработки — поле «Разработчик», для остальных фаз —
    исполнитель строки сценария. «Моя команда» — состав команды плана за
    квартал. У каждого — загрузка за квартал плана по всем опорным планам
    команд. Пустые группы не возвращаются.
    """
    from app.services.jira_developer import jira_developers_for_items

    a = db.execute(
        select(ResourcePlanAssignment)
        .options(joinedload(ResourcePlanAssignment.backlog_item))
        .where(
            ResourcePlanAssignment.id == assignment_id,
            ResourcePlanAssignment.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Assignment not found")
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    try:
        q_start, q_end = ResourcePlanningService(db)._quarter_bounds(plan)
    except ValueError as e:
        raise HTTPException(422, str(e))

    jira_id: Optional[str] = None
    item = a.backlog_item
    if item is not None:
        if a.phase == "dev":
            jira_id = jira_developers_for_items(db, [item], q_start, q_end).get(item.id)
        else:
            jira_id = item.assignee_employee_id
    groups = candidate_groups(
        db,
        team=plan.team,
        start=q_start,
        end=q_end,
        year=plan.year,
        quarter=cto.quarter_num(plan.quarter),
        jira_employee_id=jira_id,
    )
    return [asdict(g) for g in groups]
```

- [ ] **Step 6: Тесты проходят**

Run: `py -3.10 -m pytest tests/test_resource_planning_assignment_logic.py tests/services/test_rp_scenario_executor.py tests/services/test_rp_borrowed_staff.py tests/api/test_rp_cross_team_gantt.py -v`
Expected: PASS.

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py`
Expected: PASS. Если упал тест, где исполнитель сценария с ролью разработчика ожидался на анализе, — поправить ожидание по решению 14.

- [ ] **Step 7: Commit**

```bash
git add app/services/resource_planning_service.py app/api/endpoints/resource_planning.py tests/test_resource_planning_assignment_logic.py tests/services/test_rp_scenario_executor.py
git commit -F - <<'EOF'
feat(resource-planning): исполнитель сценария встаёт на фазу своей роли

Разработчик — на разработку, аналитик — на анализ; выбранный в сценарии
вручную берётся из любой команды и становится привлечённым. Кандидаты
фазы подбираются общей с сценарием функцией.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Группа C — фронт ресурсного плана

### Task C1: Типы ответа и расчёты для экрана (вырезы, подсказка дня, люди, фильтр)

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts` (`ExternalBookingOut`, `GanttProjection`, `RpPreferences`)
- Modify: `frontend/src/utils/externalBookings.ts`, `frontend/src/utils/externalBookings.test.ts`
- Create: `frontend/src/utils/rpBusy.ts`, `frontend/src/utils/rpBusy.test.ts`, `frontend/src/utils/rpPeople.ts`, `frontend/src/utils/rpPeople.test.ts`

- [ ] **Step 1: Типы по контракту 1 и 3**

В `frontend/src/api/resourcePlanning.ts`:

1.1. В `ExternalBookingOut` после `provisional: boolean;` добавить:

```ts
  /** Человек привлечён в ЭТОТ план (в его команде не состоял ни дня квартала). */
  employee_is_borrowed: boolean;
  /** Бронь-привлечение: команда брони взяла человека не из своего состава. */
  is_borrowing: boolean;
  /** Дни брони, где этот план тоже занял человека и вместе выходит больше его дня. */
  overlap_days: string[];
```

и комментарий над интерфейсом заменить на `/** Фаза человека из этого плана в опорном плане другой команды. */`.

1.2. В `GanttProjection` заменить

```ts
  /** Брони привлечённых в опорных планах других команд — блок «Привлечённые». */
  external_bookings?: ExternalBookingOut[];
```

на

```ts
  /** Брони людей плана (свои и привлечённые) в опорных планах других команд. */
  external_bookings?: ExternalBookingOut[];
  /** Брони, вычитаемые из доступности плана, изменились после его расчёта. */
  stale_due_to_other_teams?: boolean;
  /** Команды, чьи планы изменились после расчёта. */
  stale_teams?: string[];
```

1.3. В `RpPreferences` над `view_mode: string | null;` добавить комментарий
`  /** Вид страницы: 'tasks' — по задачам (по умолчанию), 'people' — по исполнителям. */`.

- [ ] **Step 2: Падающие тесты**

2.1. `frontend/src/utils/externalBookings.test.ts`: импорт заменить на

```ts
import {
  bookingRuns, externalBookingLabel, groupExternalBookings, ownPeopleBookingLabel,
  phaseCountLabel, workdayChecker,
} from './externalBookings';
```

в фабрике `b` после `provisional: false,` добавить

```ts
  employee_is_borrowed: true,
  is_borrowing: false,
  overlap_days: [],
```

и дописать в конец:

```ts
describe('ownPeopleBookingLabel', () => {
  it('имя · ключ · фаза', () => {
    expect(ownPeopleBookingLabel(b({}))).toBe('Пряничников · OS-91393 · Разработка');
  });
});

describe('workdayChecker', () => {
  it('производственный календарь важнее дня недели', () => {
    const isWorkday = workdayChecker([
      { date: '2026-01-05', is_workday: false },
      { date: '2026-01-10', is_workday: true },
    ]);
    expect(isWorkday('2026-01-05')).toBe(false); // праздник в понедельник
    expect(isWorkday('2026-01-10')).toBe(true); // рабочая суббота
    expect(isWorkday('2026-01-06')).toBe(true);
    expect(isWorkday('2026-01-11')).toBe(false);
  });
});
```

2.2. Новый `frontend/src/utils/rpBusy.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { busyGaps, dayTooltipLines } from './rpBusy';
import { workdayChecker } from './externalBookings';
import type { AssignmentOut, ExternalBookingOut } from '../api/resourcePlanning';

const weekdays = workdayChecker([]);

const a = (over: Partial<AssignmentOut> = {}): AssignmentOut => ({
  id: 'a1',
  backlog_item_id: 'i1',
  backlog_item_key: 'OS-1',
  backlog_item_title: 'Задача',
  phase: 'dev',
  employee_id: 'e1',
  employee_name: 'Шутов',
  employee_role: 'developer',
  part_number: 1,
  hours_allocated: 12,
  start_date: '2026-01-05',
  end_date: '2026-01-09',
  is_on_critical_path: false,
  slack_days: null,
  is_pinned: false,
  out_of_quarter: false,
  daily_hours: { '2026-01-05': 6, '2026-01-08': 6 },
  worklog_hours_actual: 0,
  ...over,
});

const b = (over: Partial<ExternalBookingOut> = {}): ExternalBookingOut => ({
  assignment_id: 'x1',
  employee_id: 'e1',
  employee_name: 'Шутов',
  team: 'ERP ТУ',
  issue_key: 'OS-7',
  title: 'Чужая',
  phase: 'dev',
  start: '2026-01-06',
  end: '2026-01-07',
  daily_hours: { '2026-01-06': 6, '2026-01-07': 6 },
  provisional: false,
  employee_is_borrowed: true,
  is_borrowing: false,
  overlap_days: [],
  ...over,
});

describe('busyGaps', () => {
  it('рабочий день внутри полосы без часов фазы, занятый другой командой, — вырез', () => {
    expect(busyGaps(a(), [b()], weekdays)).toEqual([
      { date: '2026-01-06', label: 'занят в плане ERP ТУ · OS-7 Разработка' },
      { date: '2026-01-07', label: 'занят в плане ERP ТУ · OS-7 Разработка' },
    ]);
  });
  it('день с часами фазы и день без брони — не вырезы', () => {
    expect(busyGaps(a(), [b({ daily_hours: { '2026-01-05': 2 } })], weekdays)).toEqual([]);
  });
  it('выходные и брони другого человека не в счёт', () => {
    const friToMon = a({
      start_date: '2026-01-09', end_date: '2026-01-12',
      daily_hours: { '2026-01-09': 6, '2026-01-12': 6 },
    });
    expect(busyGaps(friToMon, [b({ daily_hours: { '2026-01-10': 6, '2026-01-11': 6 } })], weekdays)).toEqual([]);
    expect(busyGaps(a(), [b({ employee_id: 'e2' })], weekdays)).toEqual([]);
  });
  it('фаза без посуточной раскладки — без вырезов', () => {
    expect(busyGaps(a({ daily_hours: null }), [b()], weekdays)).toEqual([]);
  });
  it('несколько броней в один день — по строке на каждую', () => {
    const second = b({
      assignment_id: 'x2', team: 'СФО', issue_key: 'OS-9', phase: 'analyst',
      daily_hours: { '2026-01-06': 2 },
    });
    expect(busyGaps(a(), [b(), second], weekdays)[0].label).toBe(
      'занят в плане ERP ТУ · OS-7 Разработка\nзанят в плане СФО · OS-9 Анализ',
    );
  });
});

describe('dayTooltipLines', () => {
  it('этот план и каждая другая команда — отдельной строкой', () => {
    const own = [
      a({ daily_hours: { '2026-01-06': 4 } }),
      a({ id: 'a2', backlog_item_key: 'OS-2', phase: 'analyst', daily_hours: { '2026-01-06': 1.5 } }),
      a({ id: 'a3', employee_id: 'e2', daily_hours: { '2026-01-06': 6 } }),
    ];
    const ext = [
      b({ team: 'СФО', daily_hours: { '2026-01-06': 2 } }),
      b({
        assignment_id: 'x2', team: 'Бухгалтерия', issue_key: null, title: 'Отчёт',
        phase: 'analyst', daily_hours: { '2026-01-06': 1 },
      }),
    ];
    expect(dayTooltipLines('e1', '2026-01-06', own, ext)).toEqual([
      'этот план 5,5 ч: OS-1 Разработка; OS-2 Анализ',
      'Бухгалтерия 1 ч: Отчёт Анализ',
      'СФО 2 ч: OS-7 Разработка',
    ]);
  });
  it('в этот день ничего — пустой список', () => {
    expect(dayTooltipLines('e1', '2026-01-10', [a()], [b()])).toEqual([]);
  });
});
```

2.3. Новый `frontend/src/utils/rpPeople.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { filterByPeople, peopleSections, personLaneRuns } from './rpPeople';
import { workdayChecker } from './externalBookings';
import type { AssignmentOut, EmployeeLoadOut, ExternalBookingOut } from '../api/resourcePlanning';

const weekdays = workdayChecker([]);

const a = (over: Partial<AssignmentOut> = {}): AssignmentOut => ({
  id: 'a1',
  backlog_item_id: 'i1',
  backlog_item_key: 'OS-1',
  backlog_item_title: 'Задача',
  phase: 'dev',
  employee_id: 'e1',
  employee_name: 'Шутов',
  employee_role: 'developer',
  part_number: 1,
  hours_allocated: 12,
  start_date: '2026-01-05',
  end_date: '2026-01-08',
  is_on_critical_path: false,
  slack_days: null,
  is_pinned: false,
  out_of_quarter: false,
  daily_hours: { '2026-01-05': 6, '2026-01-08': 6 },
  worklog_hours_actual: 0,
  ...over,
});

const b = (over: Partial<ExternalBookingOut> = {}): ExternalBookingOut => ({
  assignment_id: 'x1',
  employee_id: 'e1',
  employee_name: 'Шутов',
  team: 'ERP ТУ',
  issue_key: 'OS-7',
  title: 'Чужая',
  phase: 'dev',
  start: '2026-01-06',
  end: '2026-01-07',
  daily_hours: { '2026-01-06': 6, '2026-01-07': 6 },
  provisional: false,
  employee_is_borrowed: false,
  is_borrowing: true,
  overlap_days: [],
  ...over,
});

const load = (over: Partial<EmployeeLoadOut> = {}): EmployeeLoadOut => ({
  employee_id: 'e1',
  employee_name: 'Шутов',
  employee_role: 'developer',
  days: [
    { date: '2026-01-05', pct: 100 },
    { date: '2026-01-06', pct: 50 },
    { date: '2026-01-10', pct: 0, off: 'weekend' },
  ],
  ...over,
});

describe('peopleSections', () => {
  it('свои по имени, затем привлечённые, в конце «Без исполнителя»', () => {
    const sections = peopleSections(
      [
        a({ id: 'q', employee_id: null, employee_name: null, phase: 'qa' }),
        a({ id: 'x', employee_id: 'e3', employee_name: 'Андреев' }),
        a({ id: 'y', employee_id: 'e2', employee_name: 'Яковлев' }),
        a({ id: 'z' }),
      ],
      [],
      [
        load({ employee_id: 'e3', employee_name: 'Андреев', is_borrowed: true, borrowed_from: 'ERP ТУ' }),
        load({ employee_id: 'e2', employee_name: 'Яковлев' }),
        load(),
      ],
      'СФО',
    );
    expect(sections.map((s) => s.name)).toEqual(['Шутов', 'Яковлев', 'Андреев', 'Без исполнителя']);
    expect(sections.map((s) => s.teamNote)).toEqual(['СФО', 'СФО', 'из ERP ТУ', '']);
    expect(sections[2].isBorrowed).toBe(true);
  });
  it('части одной фазы — одна строка; строки по дате начала', () => {
    const [s] = peopleSections(
      [
        a({ id: 'p2', part_number: 2, start_date: '2026-01-20', hours_allocated: 4 }),
        a({ id: 'an', backlog_item_id: 'i2', backlog_item_key: 'OS-2', phase: 'analyst', start_date: '2026-01-02' }),
        a({ id: 'p1', start_date: '2026-01-05', hours_allocated: 8 }),
      ],
      [],
      [load()],
      'СФО',
    );
    expect(s.rows.map((r) => r.key)).toEqual(['i2-analyst', 'i1-dev']);
    expect(s.rows[1].assignments.map((x) => x.id)).toEqual(['p1', 'p2']);
    expect(s.rows[1].hours).toBe(12);
  });
  it('загрузка — средняя по рабочим дням; брони — только свои', () => {
    const [s] = peopleSections([a()], [b(), b({ assignment_id: 'x2', employee_id: 'e2' })], [load()], 'СФО');
    expect(s.loadPct).toBe(75);
    expect(s.bookings.map((x) => x.assignment_id)).toEqual(['x1']);
  });
});

describe('personLaneRuns', () => {
  it('фазы этого плана и брони других команд — по дате', () => {
    const [s] = peopleSections([a()], [b()], [load()], 'СФО');
    expect(personLaneRuns(s, '2026-01-01', '2026-03-31', weekdays)).toEqual([
      { kind: 'phase', phase: 'dev', start: '2026-01-05', end: '2026-01-05', hours: 6, label: 'OS-1 · Разработка' },
      { kind: 'booking', start: '2026-01-06', end: '2026-01-07', hours: 12, label: 'OS-7 · Разработка — ERP ТУ' },
      { kind: 'phase', phase: 'dev', start: '2026-01-08', end: '2026-01-08', hours: 6, label: 'OS-1 · Разработка' },
    ]);
  });
});

describe('filterByPeople', () => {
  it('пустой выбор — все строки; иначе только выбранные люди, без строк без человека', () => {
    const rows = [a(), a({ id: 'a2', employee_id: 'e2' }), a({ id: 'q', employee_id: null })];
    expect(filterByPeople(rows, [])).toBe(rows);
    expect(filterByPeople(rows, ['e2']).map((r) => r.id)).toEqual(['a2']);
  });
});
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `cd frontend && npx vitest run src/utils/externalBookings.test.ts src/utils/rpBusy.test.ts src/utils/rpPeople.test.ts`
Expected: FAIL (`ownPeopleBookingLabel is not a function`, `Failed to resolve import "./rpBusy"`, `"./rpPeople"`).

- [ ] **Step 4: Реализация**

4.1. `frontend/src/utils/externalBookings.ts`: объявление `function nextIso(iso: string): string {` заменить на `export function nextIso(iso: string): string {`; после `const isWeekday = …;` добавить:

```ts
/** Рабочий ли день: производственный календарь, иначе Пн–Пт. */
export function workdayChecker(
  calendar: ReadonlyArray<{ date: string; is_workday: boolean }>,
): (iso: string) => boolean {
  const known = new Map(calendar.map((c) => [c.date, c.is_workday] as const));
  return (iso) => known.get(iso) ?? isWeekday(iso);
}
```

после `externalBookingLabel` добавить:

```ts
/** «Шутов · OS-91393 · Разработка» — строка блока «Наши люди в других командах». */
export function ownPeopleBookingLabel(b: ExternalBookingOut): string {
  return [b.employee_name ?? '', b.issue_key ?? b.title, PHASE_LABELS[b.phase] ?? b.phase]
    .filter(Boolean)
    .join(' · ');
}

/** Серая штриховка чужой работы — только просмотр. */
export const OTHER_TEAM_HATCH =
  'repeating-linear-gradient(45deg, rgba(160,170,190,0.55) 0 4px, rgba(160,170,190,0.18) 4px 8px)';
```

4.2. `frontend/src/utils/rpBusy.ts`:

```ts
import type { AssignmentOut, ExternalBookingOut } from '../api/resourcePlanning';
import { nextIso } from './externalBookings';
import { PHASE_LABELS } from './gantt';

/** Вырез в полосе фазы: рабочий день без её часов, когда человек занят в другой команде. */
export interface BusyGap {
  date: string;
  /** «занят в плане ERP ТУ · OS-7 Разработка», по строке на бронь. */
  label: string;
}

const phaseName = (phase: string) => PHASE_LABELS[phase] ?? phase;
const bookingName = (b: ExternalBookingOut) => `${b.issue_key ?? b.title} ${phaseName(b.phase)}`;
const fmtHours = (h: number) => (Math.round(h * 10) / 10).toLocaleString('ru');

/**
 * Рабочие дни внутри полосы, где у фазы нет часов, а человек занят в плане
 * другой команды. Фаза без посуточной раскладки вырезов не получает.
 */
export function busyGaps(
  a: AssignmentOut,
  bookings: ExternalBookingOut[],
  isWorkday: (iso: string) => boolean,
): BusyGap[] {
  const { employee_id: employeeId, start_date: start, end_date: end, daily_hours: daily } = a;
  if (!employeeId || !start || !end || !daily) return [];
  const mine = bookings.filter((b) => b.employee_id === employeeId);
  if (mine.length === 0) return [];
  const out: BusyGap[] = [];
  for (let d = start; d <= end; d = nextIso(d)) {
    if (!isWorkday(d) || (daily[d] ?? 0) > 0) continue;
    const busy = mine.filter((b) => (b.daily_hours[d] ?? 0) > 0);
    if (busy.length === 0) continue;
    out.push({
      date: d,
      label: busy.map((b) => `занят в плане ${b.team} · ${bookingName(b)}`).join('\n'),
    });
  }
  return out;
}

/**
 * Строки подсказки дня в подвале: «этот план N ч: KEY Фаза; …» и по строке
 * на каждую другую команду «<команда> N ч: KEY Фаза; …». Пусто — дня нет.
 */
export function dayTooltipLines(
  employeeId: string,
  date: string,
  assignments: AssignmentOut[],
  bookings: ExternalBookingOut[],
): string[] {
  const lines: string[] = [];
  const own = assignments.filter(
    (a) => a.employee_id === employeeId && (a.daily_hours?.[date] ?? 0) > 0,
  );
  if (own.length > 0) {
    const total = own.reduce((s, a) => s + (a.daily_hours?.[date] ?? 0), 0);
    const names = own.map((a) => `${a.backlog_item_key ?? a.backlog_item_title} ${phaseName(a.phase)}`);
    lines.push(`этот план ${fmtHours(total)} ч: ${names.join('; ')}`);
  }
  const byTeam = new Map<string, ExternalBookingOut[]>();
  for (const b of bookings) {
    if (b.employee_id !== employeeId || (b.daily_hours[date] ?? 0) <= 0) continue;
    byTeam.set(b.team, [...(byTeam.get(b.team) ?? []), b]);
  }
  for (const team of [...byTeam.keys()].sort((x, y) => x.localeCompare(y, 'ru'))) {
    const list = byTeam.get(team) ?? [];
    const total = list.reduce((s, b) => s + (b.daily_hours[date] ?? 0), 0);
    lines.push(`${team} ${fmtHours(total)} ч: ${list.map(bookingName).join('; ')}`);
  }
  return lines;
}
```

4.3. `frontend/src/utils/rpPeople.ts`:

```ts
import type { AssignmentOut, EmployeeLoadOut, ExternalBookingOut } from '../api/resourcePlanning';
import { bookingRuns, type BookingRun } from './externalBookings';
import { PHASE_LABELS } from './gantt';

/** Строка фазы в секции человека: все части одной фазы одной задачи. */
export interface PersonRow {
  key: string;
  itemId: string;
  itemKey: string | null;
  itemTitle: string;
  phase: AssignmentOut['phase'];
  hours: number;
  assignments: AssignmentOut[];
}

/** Секция вида «Исполнители». employeeId = null — фазы без человека. */
export interface PersonSection {
  employeeId: string | null;
  name: string;
  role: string | null;
  /** Подпись: команда плана или «из <команда>» у привлечённого. */
  teamNote: string;
  isBorrowed: boolean;
  /** Средняя загрузка в этом плане по рабочим дням квартала, %; null — нет строки подвала. */
  loadPct: number | null;
  rows: PersonRow[];
  bookings: ExternalBookingOut[];
}

/** Отрезок полосы «все работы»: фаза этого плана или бронь другой команды. */
export type LaneRun = BookingRun & { label: string } & (
  | { kind: 'phase'; phase: AssignmentOut['phase'] }
  | { kind: 'booking' }
);

/** Средняя загрузка по рабочим дням — как бейдж подвала. */
function avgLoad(row: EmployeeLoadOut): number {
  const work = row.days.filter((d) => !d.off);
  return work.length ? Math.round(work.reduce((s, d) => s + d.pct, 0) / work.length) : 0;
}

/**
 * Секции вида «Исполнители»: каждый, у кого есть фазы в плане. Сначала свои
 * (по имени), затем привлечённые, в конце — «Без исполнителя».
 */
export function peopleSections(
  assignments: AssignmentOut[],
  bookings: ExternalBookingOut[],
  loadRows: EmployeeLoadOut[],
  planTeam: string | null,
): PersonSection[] {
  const loadBy = new Map(loadRows.map((r) => [r.employee_id, r] as const));
  const byPerson = new Map<string | null, AssignmentOut[]>();
  for (const a of assignments) {
    byPerson.set(a.employee_id, [...(byPerson.get(a.employee_id) ?? []), a]);
  }
  const sections: PersonSection[] = [];
  for (const [employeeId, list] of byPerson) {
    const rowsByKey = new Map<string, PersonRow>();
    for (const a of list) {
      const key = `${a.backlog_item_id}-${a.phase}`;
      const row = rowsByKey.get(key) ?? {
        key,
        itemId: a.backlog_item_id,
        itemKey: a.backlog_item_key,
        itemTitle: a.backlog_item_title,
        phase: a.phase,
        hours: 0,
        assignments: [],
      };
      row.hours += a.hours_allocated ?? 0;
      row.assignments.push(a);
      rowsByKey.set(key, row);
    }
    const firstStart = (r: PersonRow) =>
      r.assignments.map((x) => x.start_date ?? '9999-12-31').sort()[0];
    const rows = [...rowsByKey.values()].sort(
      (x, y) => firstStart(x).localeCompare(firstStart(y)) || x.key.localeCompare(y.key),
    );
    for (const r of rows) r.assignments.sort((x, y) => x.part_number - y.part_number);
    const load = employeeId ? loadBy.get(employeeId) : undefined;
    const isBorrowed = !!load?.is_borrowed;
    sections.push({
      employeeId,
      name: employeeId ? (load?.employee_name ?? list[0].employee_name ?? '—') : 'Без исполнителя',
      role: load?.employee_role ?? list[0].employee_role ?? null,
      teamNote: !employeeId ? '' : isBorrowed ? `из ${load?.borrowed_from ?? 'другой команды'}` : (planTeam ?? ''),
      isBorrowed,
      loadPct: load ? avgLoad(load) : null,
      rows,
      bookings: employeeId ? bookings.filter((b) => b.employee_id === employeeId) : [],
    });
  }
  const rank = (s: PersonSection) => (s.employeeId === null ? 2 : s.isBorrowed ? 1 : 0);
  return sections.sort((x, y) => rank(x) - rank(y) || x.name.localeCompare(y.name, 'ru'));
}

/**
 * Полоса «все работы» человека: фазы этого плана (по дням с часами) и брони
 * других команд. Свободные дни остаются пустыми.
 */
export function personLaneRuns(
  section: PersonSection,
  from: string,
  to: string,
  isWorkday: (iso: string) => boolean,
): LaneRun[] {
  const out: LaneRun[] = [];
  for (const row of section.rows) {
    const label = `${row.itemKey ?? row.itemTitle} · ${PHASE_LABELS[row.phase] ?? row.phase}`;
    for (const a of row.assignments) {
      if (a.daily_hours) {
        for (const r of bookingRuns(a.daily_hours, from, to, isWorkday)) {
          out.push({ kind: 'phase', phase: a.phase, ...r, label });
        }
      } else if (a.start_date && a.end_date) {
        out.push({
          kind: 'phase', phase: a.phase, start: a.start_date, end: a.end_date,
          hours: a.hours_allocated ?? 0, label,
        });
      }
    }
  }
  for (const b of section.bookings) {
    const label = `${b.issue_key ?? b.title} · ${PHASE_LABELS[b.phase] ?? b.phase} — ${b.team}`;
    for (const r of bookingRuns(b.daily_hours, from, to, isWorkday)) {
      out.push({ kind: 'booking', ...r, label });
    }
  }
  return out.sort((x, y) => x.start.localeCompare(y.start) || x.kind.localeCompare(y.kind));
}

/** Только строки выбранных людей; пустой выбор — все строки как есть. */
export function filterByPeople<T extends { employee_id: string | null }>(
  rows: T[],
  people: readonly string[],
): T[] {
  if (people.length === 0) return rows;
  const wanted = new Set(people);
  return rows.filter((r) => r.employee_id !== null && wanted.has(r.employee_id));
}
```

- [ ] **Step 5: Тесты проходят, сборка цела**

Run: `cd frontend && npx vitest run src/utils/externalBookings.test.ts src/utils/rpBusy.test.ts src/utils/rpPeople.test.ts`
Expected: PASS.

Run: `cd frontend && npm run build`
Expected: сборка без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/utils/externalBookings.ts frontend/src/utils/externalBookings.test.ts frontend/src/utils/rpBusy.ts frontend/src/utils/rpBusy.test.ts frontend/src/utils/rpPeople.ts frontend/src/utils/rpPeople.test.ts
git commit -F - <<'EOF'
feat(rp-ui): расчёты для вырезов, подсказки дня и вида «Исполнители»

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task C2: Полоса фазы — вырезы занятости и перетаскивание только начала

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (`Props`, `PhaseBarProps`, `PhaseBar`, новый `BusyOverlay`, вызов `PhaseBar` в `TwoLevelRows`)
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx`
- Modify: `frontend/src/components/resource-planning/AssignmentSidebar.tsx` (поле «Окончание»)
- Modify: `frontend/src/api/resourcePlanning.ts` (`AssignmentPatch`)

- [ ] **Step 1: Контракт PATCH — конец не шлём**

В `frontend/src/api/resourcePlanning.ts` из `AssignmentPatch` удалить строку `  end_date?: string;`.

- [ ] **Step 2: `GanttRows.tsx` — перетаскивание и вырезы**

2.1. Импорты: строку
`import { dateToLeft, datesToWidth, PHASE_COLORS, PHASE_LABELS, getItemColor } from '../../utils/gantt';`
заменить на

```ts
import { dateToLeft, datesToWidth, fmtLocalIso, PHASE_COLORS, PHASE_LABELS, getItemColor } from '../../utils/gantt';
import type { BusyGap } from '../../utils/rpBusy';
```

2.2. В `interface Props` после `quarterEndDate?: string;` добавить:

```ts
  /** Вырезы полос: {id фазы: рабочие дни без её часов, когда человек занят в другой команде}. */
  busyByAssignment?: Map<string, BusyGap[]>;
```

2.3. В `interface PhaseBarProps` удалить строку `  showResize: boolean;`, а после `  quarterEndDate?: string;` добавить:

```ts
  /** Рабочие дни внутри полосы без часов фазы, когда человек занят в другой команде. */
  busyDays?: BusyGap[];
```

2.4. Строку сигнатуры

```ts
function PhaseBar({ assignment, planId, timeline, refKey, extraRefKeys, rowRefs, color, showResize, hasConflict, dimmed, onClick, unavailableDays, highlightedEmployeeId, pulseEmp, pulseCp, quarterEndDate }: PhaseBarProps) {
```

заменить на

```ts
function PhaseBar({ assignment, planId, timeline, refKey, extraRefKeys, rowRefs, color, hasConflict, dimmed, onClick, unavailableDays, highlightedEmployeeId, pulseEmp, pulseCp, quarterEndDate, busyDays }: PhaseBarProps) {
```

2.5. Блок от `  const [drag, setDrag] = useState<null | {` до `  useMemoizedDragListeners(drag, onMouseMove, onMouseUp);` включительно заменить на:

```tsx
  const [drag, setDrag] = useState<null | {
    startClientX: number;
    origStart: string;
    origEnd: string;
    rowWidthPx: number;
  }>(null);
  const [previewLeft, setPreviewLeft] = useState<number | null>(null);
  const [previewWidth, setPreviewWidth] = useState<number | null>(null);

  const beginDrag = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!assignment.start_date || !assignment.end_date) return;
    const row = (e.currentTarget as HTMLElement).closest('[data-gantt-row="true"]') as HTMLElement | null;
    if (!row) return;
    const trackEl = row.querySelector('[data-gantt-track="true"]') as HTMLElement | null;
    const trackWidth = trackEl ? trackEl.getBoundingClientRect().width : row.getBoundingClientRect().width;
    setDrag({
      startClientX: e.clientX,
      origStart: assignment.start_date,
      origEnd: assignment.end_date,
      rowWidthPx: trackWidth,
    });
  };

  // Полоса сдвигается целиком. На сервер уходит только новое начало: конец и
  // часы по дням планировщик разложит сам по свободным дням исполнителя.
  const shiftDates = (dxDays: number) => {
    const sd = new Date(drag!.origStart + 'T00:00:00');
    const ed = new Date(drag!.origEnd + 'T00:00:00');
    sd.setDate(sd.getDate() + dxDays);
    ed.setDate(ed.getDate() + dxDays);
    return { newStart: fmtLocalIso(sd), newEnd: fmtLocalIso(ed) };
  };

  const onMouseMove = (e: MouseEvent) => {
    if (!drag) return;
    const dxPx = e.clientX - drag.startClientX;
    const pxPerDay = drag.rowWidthPx / timeline.totalDays;
    const dxDays = Math.round(dxPx / pxPerDay);
    if (dxDays === 0) return;
    const { newStart, newEnd } = shiftDates(dxDays);
    setPreviewLeft(dateToLeft(newStart, timeline));
    setPreviewWidth(datesToWidth(newStart, newEnd, timeline));
  };

  const onMouseUp = (e: MouseEvent) => {
    if (!drag) return;
    const dxPx = e.clientX - drag.startClientX;
    const pxPerDay = drag.rowWidthPx / timeline.totalDays;
    const dxDays = Math.round(dxPx / pxPerDay);
    if (dxDays !== 0) {
      patch.mutate({
        planId,
        assignmentId: assignment.id,
        data: { start_date: shiftDates(dxDays).newStart },
      });
    }
    setDrag(null);
    setPreviewLeft(null);
    setPreviewWidth(null);
  };

  useMemoizedDragListeners(drag, onMouseMove, onMouseUp);
```

2.6. В разметке полосы `      onMouseDown={(e) => beginDrag(e, 'move')}` заменить на `      onMouseDown={beginDrag}`.

2.7. Сразу после блока `{unavailableDays && unavailableDays.length > 0 && ( <UnavailabilityOverlay … /> )}` (перед закрывающим `</div>` полосы) добавить:

```tsx
      {busyDays && busyDays.length > 0 && (
        <BusyOverlay
          barStart={assignment.start_date}
          barEnd={assignment.end_date}
          days={busyDays}
          timeline={timeline}
        />
      )}
```

2.8. В `return` компонента удалить весь блок `{showResize && ( <> …две ручки растягивания… </> )}` — остаются `{bar}` и предпросмотр.

2.9. После функции `OutOfQuarterOverlay` добавить:

```tsx
// Вырез в полосе: рабочий день без часов фазы, когда человек занят в другой команде.
const BUSY_CUTOUT =
  'repeating-linear-gradient(45deg, rgba(160,170,190,0.55) 0 4px, rgba(10,22,40,0.92) 4px 8px)';

function BusyOverlay({ barStart, barEnd, days, timeline }: {
  barStart: string;
  barEnd: string;
  days: BusyGap[];
  timeline: GanttTimeline;
}) {
  // Координаты — по шкале (работает и в режиме «Только рабочие»), в процентах от полосы.
  const barLeft = dateToLeft(barStart, timeline);
  const barWidth = datesToWidth(barStart, barEnd, timeline);
  if (barWidth <= 0) return null;
  return (
    <>
      {days.map((d) => (
        <div
          key={d.date}
          title={d.label}
          style={{
            position: 'absolute',
            left: `${((dateToLeft(d.date, timeline) - barLeft) / barWidth) * 100}%`,
            width: `${(datesToWidth(d.date, d.date, timeline) / barWidth) * 100}%`,
            top: 0,
            bottom: 0,
            background: BUSY_CUTOUT,
            zIndex: 3,
          }}
        />
      ))}
    </>
  );
}
```

2.10. В `TwoLevelRows`: в деструктуризацию параметров добавить `busyByAssignment`; в вызове `<PhaseBar …>` удалить строку `showResize={a.phase !== 'qa'}`, а после `quarterEndDate={quarterEndDate}` добавить `busyDays={busyByAssignment?.get(a.id)}`.

- [ ] **Step 3: `GanttChart.tsx` — расчёт вырезов**

3.1. Импорты — добавить:

```ts
import { workdayChecker } from '../../utils/externalBookings';
import { busyGaps, type BusyGap } from '../../utils/rpBusy';
```

3.2. После `const NO_CALENDAR: ProductionCalendarDayResponse[] = [];` добавить:

```ts
// Та же пустая ссылка для броней: иначе вырезы пересчитывались бы на каждом рендере.
const NO_BOOKINGS: ExternalBookingOut[] = [];
```

3.3. После `  const { prefs } = useRpPreferences();` добавить:

```ts
  const isWorkday = useMemo(() => workdayChecker(calendar), [calendar]);
  const bookings = externalBookings ?? NO_BOOKINGS;
  // Вырезы на полосах: рабочие дни без часов фазы, когда человек занят в
  // плане другой команды.
  const busyByAssignment = useMemo(() => {
    const out = new Map<string, BusyGap[]>();
    for (const a of assignments) {
      const gaps = busyGaps(a, bookings, isWorkday);
      if (gaps.length > 0) out.set(a.id, gaps);
    }
    return out;
  }, [assignments, bookings, isWorkday]);
```

3.4. В `<GanttRows …>` добавить проп `busyByAssignment={busyByAssignment}`.

- [ ] **Step 4: Панель фазы — «Окончание» только для просмотра**

В `AssignmentSidebar.tsx` заменить

```tsx
        <Descriptions.Item label="Окончание">
          <DatePicker
            value={assignment.end_date ? dayjs(assignment.end_date) : null}
            disabled={saving}
            allowClear={false}
            onChange={(d) => d && updateField({ end_date: d.format('YYYY-MM-DD') })}
          />
        </Descriptions.Item>
```

на

```tsx
        <Descriptions.Item label="Окончание">
          {/* Конец считает планировщик по свободным дням исполнителя от даты начала. */}
          <Typography.Text title="Считается по свободным дням исполнителя от даты начала">
            {assignment.end_date ? dayjs(assignment.end_date).format('DD.MM.YYYY') : '—'}
          </Typography.Text>
        </Descriptions.Item>
```

- [ ] **Step 5: Сборка, тесты, линтер**

Run: `cd frontend && npm run build`
Expected: без ошибок (в том числе нет обращений к удалённому `end_date` и `showResize`).

Run: `cd frontend && npx vitest run src`
Expected: PASS.

Run: `cd frontend && npx eslint src/components/resource-planning/GanttRows.tsx src/components/resource-planning/GanttChart.tsx src/components/resource-planning/AssignmentSidebar.tsx src/api/resourcePlanning.ts`
Expected: без новых замечаний.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/components/resource-planning/GanttRows.tsx frontend/src/components/resource-planning/GanttChart.tsx frontend/src/components/resource-planning/AssignmentSidebar.tsx
git commit -F - <<'EOF'
feat(rp-ui): вырезы занятости в другой команде и перетаскивание только начала

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task C3: Блоки «Привлечённые» и «Наши люди в других командах»

**Files:**
- Modify: `frontend/src/components/resource-planning/ExternalBookingsRows.tsx` (переписывается целиком)
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx`, `frontend/src/components/resource-planning/GanttRows.tsx` (тип раскладки)

- [ ] **Step 1: Тип раскладки**

В `GanttRows.tsx` после `export type ViewMode = 'portfolio' | 'two-level' | 'resource-track' | 'plane';` добавить:

```ts
/** Раскладка строк основного вида: по задачам или по исполнителям. */
export type RpLayout = 'tasks' | 'people';
```

- [ ] **Step 2: `ExternalBookingsRows.tsx` — общий блок броней с заголовком и отметками пересечений**

Содержимое файла заменить целиком:

```tsx
import { useMemo, useState } from 'react';
import type { ExternalBookingOut } from '../../api/resourcePlanning';
import type { ProductionCalendarDayResponse } from '../../types/api';
import type { GanttTimeline, WorkdayTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth, fmtLocalIso } from '../../utils/gantt';
import {
  OTHER_TEAM_HATCH,
  bookingRuns,
  externalBookingLabel,
  groupExternalBookings,
  phaseCountLabel,
  workdayChecker,
} from '../../utils/externalBookings';

const ROW_H = 28;
const BAR_H = 16;
// Левая колонка перекрывает метку «сегодня» (z=20) при горизонтальном скролле —
// как у строк задач.
const STICKY_Z = 25;
const OVERLAP_HINT = 'пересекается с вашим планом — техкоманда получит конфликт';

interface Props {
  bookings: ExternalBookingOut[];
  timeline: GanttTimeline | WorkdayTimeline;
  calendar: ProductionCalendarDayResponse[];
  leftColWidth: number;
  trackWidthPx: number;
  /** Заголовок блока. */
  title: string;
  /** Подпись строки; по умолчанию «KEY · Фаза · Имя». */
  labelOf?: (b: ExternalBookingOut) => string;
  /** Красная отметка в днях, где этот план тоже занял человека. */
  showOverlap?: boolean;
}

const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

/**
 * Брони людей плана в опорных планах других команд: блоки «Привлечённые»
 * и «Наши люди в других командах». Только просмотр. Полосы — дни с часами,
 * так что паузы внутри чужой фазы видны как свободные окна.
 */
export default function ExternalBookingsRows({
  bookings,
  timeline,
  calendar,
  leftColWidth,
  trackWidthPx,
  title,
  labelOf = externalBookingLabel,
  showOverlap = false,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const rows = useMemo(() => {
    const from = fmtLocalIso(timeline.startDate);
    const to = fmtLocalIso(timeline.endDate);
    const isWorkday = workdayChecker(calendar);
    return groupExternalBookings(bookings)
      .flatMap((g) => g.rows)
      .map((b) => ({ b, runs: bookingRuns(b.daily_hours, from, to, isWorkday) }))
      .filter((r) => r.runs.length > 0);
  }, [bookings, timeline, calendar]);

  if (rows.length === 0) return null;

  return (
    <div style={{ borderBottom: '2px solid #066770' }}>
      {/* Шапка сворачивает блок — как секции групп команды. */}
      <button
        type="button"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((v) => !v)}
        style={{
          position: 'sticky',
          left: 0,
          zIndex: STICKY_Z,
          width: leftColWidth,
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          padding: '6px 14px',
          background: '#0a1628',
          border: 0,
          borderBottom: '1px solid #1e3a5f',
          cursor: 'pointer',
          userSelect: 'none',
          textAlign: 'left',
          font: 'inherit',
        }}
      >
        <span aria-hidden="true" style={{ fontSize: 11, color: 'var(--text-muted, #7a9ab8)' }}>
          {collapsed ? '▶' : '▼'}
        </span>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary, #e6f0f7)' }}>
          {title}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-hint, #7a9ab8)' }}>
          {phaseCountLabel(rows.length)} в планах других команд · только просмотр
        </span>
      </button>
      {!collapsed && rows.map(({ b, runs }) => {
        const label = labelOf(b);
        const meta = b.provisional ? `${b.team} · предварительно` : b.team;
        return (
          <div
            key={b.assignment_id}
            style={{ display: 'flex', height: ROW_H, borderBottom: '1px solid #0e2540' }}
          >
            <div
              title={`${label} — ${meta}`}
              style={{
                width: leftColWidth,
                boxSizing: 'border-box',
                flexShrink: 0,
                position: 'sticky',
                left: 0,
                zIndex: STICKY_Z,
                background: '#0a1628',
                borderRight: '1px solid #1e3a5f',
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 1fr) 160px',
                columnGap: 8,
                alignItems: 'center',
                padding: '0 12px',
                fontSize: 12,
                whiteSpace: 'nowrap',
              }}
            >
              <span style={{ color: '#9ab3cc', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {label}
              </span>
              {/* «предварительно» — отдельной строкой: длинное название команды его не съест. */}
              <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, fontSize: 11, lineHeight: 1.15 }}>
                <span style={{ color: '#7a9ab8', overflow: 'hidden', textOverflow: 'ellipsis' }}>{b.team}</span>
                {b.provisional && <span style={{ fontSize: 10, color: '#e0a84a' }}>предварительно</span>}
              </span>
            </div>
            <div style={{ position: 'relative', width: trackWidthPx, flex: '0 0 auto' }}>
              {runs.map((r) => (
                <div
                  key={r.start}
                  title={`${label} — ${meta}: ${ddmm(r.start)}–${ddmm(r.end)}, ${Math.round(r.hours)} ч. Только просмотр`}
                  style={{
                    position: 'absolute',
                    left: `${dateToLeft(r.start, timeline)}%`,
                    width: `${datesToWidth(r.start, r.end, timeline)}%`,
                    top: (ROW_H - BAR_H) / 2,
                    height: BAR_H,
                    boxSizing: 'border-box',
                    borderRadius: 3,
                    background: OTHER_TEAM_HATCH,
                    border: '1px solid rgba(160,170,190,0.5)',
                    zIndex: 2,
                  }}
                />
              ))}
              {showOverlap && b.overlap_days.map((d) => (
                <div
                  key={`overlap-${d}`}
                  title={`${ddmm(d)}: ${OVERLAP_HINT}`}
                  style={{
                    position: 'absolute',
                    left: `${dateToLeft(d, timeline)}%`,
                    width: `${datesToWidth(d, d, timeline)}%`,
                    top: (ROW_H - BAR_H) / 2 - 2,
                    height: BAR_H + 4,
                    boxSizing: 'border-box',
                    border: '2px solid #ef4444',
                    borderRadius: 3,
                    zIndex: 3,
                  }}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: `GanttChart.tsx` — два блока, только в виде «Задачи»**

3.1. Импорт `import type { ViewMode } from './GanttRows';` заменить на `import type { RpLayout, ViewMode } from './GanttRows';`; импорт из `../../utils/externalBookings` сделать `import { ownPeopleBookingLabel, workdayChecker } from '../../utils/externalBookings';`.

3.2. В `interface Props` заменить

```ts
  /** Брони привлечённых в опорных планах других команд — блок «Привлечённые». */
  externalBookings?: ExternalBookingOut[];
```

на

```ts
  /** Брони людей плана в опорных планах других команд (свои и привлечённые). */
  externalBookings?: ExternalBookingOut[];
  /** «Задачи» — строки по задачам, «Исполнители» — секции по людям. */
  layout?: RpLayout;
```

и в деструктуризацию параметров добавить `layout = 'tasks',`.

3.3. После расчёта `busyByAssignment` добавить:

```ts
  // «Привлечённые» — наши привлечённые в чужих планах; «Наши люди в других
  // командах» — свои, которых другие команды взяли к себе.
  const borrowedBookings = useMemo(() => bookings.filter((b) => b.employee_is_borrowed), [bookings]);
  const ownPeopleBookings = useMemo(
    () => bookings.filter((b) => !b.employee_is_borrowed && b.is_borrowing),
    [bookings],
  );
```

3.4. Блок

```tsx
          {externalBookings && externalBookings.length > 0 && (
            <ExternalBookingsRows
              bookings={externalBookings}
              timeline={timeline}
              calendar={calendar}
              leftColWidth={LEFT_COL}
              trackWidthPx={trackWidthPx}
            />
          )}
```

заменить на

```tsx
          {/* В виде «Исполнители» те же брони лежат на полосе «все работы». */}
          {layout === 'tasks' && (
            <ExternalBookingsRows
              title="Привлечённые"
              bookings={borrowedBookings}
              timeline={timeline}
              calendar={calendar}
              leftColWidth={LEFT_COL}
              trackWidthPx={trackWidthPx}
            />
          )}
          {layout === 'tasks' && (
            <ExternalBookingsRows
              title="Наши люди в других командах"
              bookings={ownPeopleBookings}
              labelOf={ownPeopleBookingLabel}
              showOverlap
              timeline={timeline}
              calendar={calendar}
              leftColWidth={LEFT_COL}
              trackWidthPx={trackWidthPx}
            />
          )}
```

- [ ] **Step 4: Сборка и тесты**

Run: `cd frontend && npm run build && npx vitest run src`
Expected: PASS.

Run: `cd frontend && npx eslint src/components/resource-planning/ExternalBookingsRows.tsx src/components/resource-planning/GanttChart.tsx src/components/resource-planning/GanttRows.tsx`
Expected: без новых замечаний.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/resource-planning/ExternalBookingsRows.tsx frontend/src/components/resource-planning/GanttChart.tsx frontend/src/components/resource-planning/GanttRows.tsx
git commit -F - <<'EOF'
feat(rp-ui): блок «Наши люди в других командах» с отметками пересечений

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task C4: Подвал — многострочная подсказка дня и щелчок по имени

**Files:**
- Modify: `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx`

- [ ] **Step 1: Пропсы и подсказка**

1.1. Импорт `import type { EmployeeLoadOut } from '../../api/resourcePlanning';` заменить на

```ts
import type { AssignmentOut, EmployeeLoadOut, ExternalBookingOut } from '../../api/resourcePlanning';
import { dayTooltipLines } from '../../utils/rpBusy';
```

1.2. В `interface Props` после `subgroupOrder?: string[];` добавить:

```ts
  /** Фазы плана — подсказка дня: часы и задачи этого плана. */
  assignments?: AssignmentOut[];
  /** Брони людей плана в других командах — строки подсказки по командам. */
  bookings?: ExternalBookingOut[];
  /** Люди в фильтре «Исполнители» — их имена выделены. */
  selectedIds?: string[];
  /** Щелчок по имени — добавить человека в фильтр или убрать. */
  onEmployeeClick?: (employeeId: string) => void;
```

1.3. Перед `function isoDate` добавить:

```ts
// Стабильные пустые значения по умолчанию.
const NO_ASSIGNMENTS: AssignmentOut[] = [];
const NO_BOOKINGS: ExternalBookingOut[] = [];
const NO_IDS: string[] = [];
```

1.4. Сигнатуру компонента заменить на:

```tsx
export default function EmployeeLoadHeatmap({
  rows,
  subgroupByEmployee,
  subgroupOrder = [],
  assignments = NO_ASSIGNMENTS,
  bookings = NO_BOOKINGS,
  selectedIds = NO_IDS,
  onEmployeeClick,
}: Props) {
  const [tip, setTip] = useState<{ x: number; y: number; lines: string[] } | null>(null);
```

(строку `const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);` удалить).

1.5. Функцию `showTip` заменить на:

```tsx
  const showTip = (e: React.MouseEvent, row: EmployeeLoadOut, date: string, off: Off) => {
    const dt = isoDate(date);
    const head = `${RU_WD[dt.getDay()]}, ${dt.getDate()} ${RU_MONTHS_SHORT[dt.getMonth()]}`;
    let body: string[];
    if (off === 'out_of_team') body = [outOfTeamText(row, date)];
    else if (off === 'absence') body = ['отпуск / отсутствие'];
    else if (off === 'holiday') body = ['праздник'];
    else {
      // По строке на этот план и на каждую другую команду: часы и задачи дня.
      const lines = dayTooltipLines(row.employee_id, date, assignments, bookings);
      body = lines.length > 0 ? lines : ['нет загрузки'];
    }
    setTip({ x: e.clientX, y: e.clientY, lines: [head, ...body] });
  };
```

1.6. Вызов `onMouseEnter={(e) => showTip(e, row, cell.date, off, pct, ext)}` заменить на `onMouseEnter={(e) => showTip(e, row, cell.date, off)}`.

1.7. Вывод подсказки `{tip.text}` заменить на:

```tsx
          {tip.lines.map((line, i) => (
            <div key={i} style={i === 0 ? { fontWeight: 600 } : undefined}>{line}</div>
          ))}
```

1.8. Подзаголовок `Только рабочие дни. Наведите на день, чтобы увидеть дату и загрузку.` заменить на
`Только рабочие дни. Наведите на день — часы по задачам этого плана и других команд; щелчок по имени — фильтр по человеку.`

- [ ] **Step 2: Имя — переключатель фильтра**

Спан с именем

```tsx
                    <span
                      style={{
                        fontSize: 12,
                        color: '#fff',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {row.employee_name ?? row.employee_id}
                    </span>
```

заменить на

```tsx
                    <span
                      onClick={onEmployeeClick ? () => onEmployeeClick(row.employee_id) : undefined}
                      title={
                        onEmployeeClick
                          ? 'Щёлкните, чтобы добавить человека в фильтр «Исполнители» или убрать'
                          : undefined
                      }
                      style={{
                        fontSize: 12,
                        color: selectedIds.includes(row.employee_id) ? '#00c9c8' : '#fff',
                        fontWeight: selectedIds.includes(row.employee_id) ? 700 : undefined,
                        cursor: onEmployeeClick ? 'pointer' : undefined,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {row.employee_name ?? row.employee_id}
                    </span>
```

- [ ] **Step 3: Сборка и линтер**

Run: `cd frontend && npm run build && npx eslint src/components/resource-planning/EmployeeLoadHeatmap.tsx`
Expected: без ошибок и новых замечаний (новые пропсы пока не передаются — это C5).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx
git commit -F - <<'EOF'
feat(rp-ui): подсказка дня в подвале по задачам плана и других команд

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task C5: Вид «Исполнители», фильтр по людям, предупреждение об устаревании

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (пропсы, новый `PeopleRows`, щелчок по фишке)
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx` (проброс)
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx`

- [ ] **Step 1: `GanttRows.tsx` — вид «Исполнители»**

1.1. Импорты: `import type { AssignmentOut } from '../../api/resourcePlanning';` заменить на
`import type { AssignmentOut, EmployeeLoadOut, ExternalBookingOut } from '../../api/resourcePlanning';`
и добавить

```ts
import { OTHER_TEAM_HATCH, workdayChecker } from '../../utils/externalBookings';
import { peopleSections, personLaneRuns } from '../../utils/rpPeople';
```

1.2. В `interface Props` после `busyByAssignment?: …;` добавить:

```ts
  /** «Задачи» (по умолчанию) или «Исполнители». */
  layout?: RpLayout;
  /** Брони людей плана в других командах — полоса «все работы» в виде «Исполнители». */
  externalBookings?: ExternalBookingOut[];
  /** Строки подвала: команда, привлечённость и загрузка человека. */
  employeeLoad?: EmployeeLoadOut[];
  /** Команда плана — подпись своих в виде «Исполнители». */
  planTeam?: string | null;
  /** Рабочий ли день (производственный календарь). */
  isWorkday?: (iso: string) => boolean;
```

1.3. После `const STICKY_INIT_Z = 26;` добавить `const WEEKDAYS = workdayChecker([]);`.

1.4. В `TwoLevelRows` щелчок по фишке исполнителя

```tsx
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onEmployeeRowClick && empId) {
                        onEmployeeRowClick(isHighlighted ? null : empId);
                      }
                    }}
```

заменить на

```tsx
                    onClick={(e) => {
                      e.stopPropagation();
                      // Щелчок добавляет человека в фильтр «Исполнители» или убирает.
                      if (onEmployeeRowClick && empId) onEmployeeRowClick(empId);
                    }}
```

1.5. Перед `function ResourceTrackRows` добавить:

```tsx
/** Вид «Исполнители»: секция на человека — полоса «все работы» и его фазы этого плана. */
function PeopleRows({
  assignments, timeline, leftColWidth, trackWidthPx, rowRefs, planId, employees,
  conflictAssignmentIds, onAssignmentClick, highlightedEmployeeId, onEmployeeRowClick,
  quarterEndDate, externalBookings, employeeLoad, planTeam, busyByAssignment, isWorkday,
}: SubProps) {
  const appearance = useAppearanceSettings();
  const { prefs: rpPrefs } = useRpPreferences();
  const conflictSet = useMemo(() => new Set(conflictAssignmentIds ?? []), [conflictAssignmentIds]);
  const sections = useMemo(
    () => peopleSections(assignments, externalBookings ?? [], employeeLoad ?? [], planTeam ?? null),
    [assignments, externalBookings, employeeLoad, planTeam],
  );
  const from = fmtLocalIso(timeline.startDate);
  const to = fmtLocalIso(timeline.endDate);
  const workday = isWorkday ?? WEEKDAYS;

  return (
    <>
      {sections.map((s, si) => {
        const lane = personLaneRuns(s, from, to, workday);
        const clickable = !!s.employeeId && !!onEmployeeRowClick;
        return (
          <div key={s.employeeId ?? '__none__'} style={{ borderTop: si > 0 ? INIT_DIVIDER : 'none' }}>
            {/* Заголовок секции: имя, команда, загрузка; щелчок — фильтр по человеку. */}
            <div style={{ display: 'flex', minHeight: ROW_HEIGHT, background: INIT_HEADER_BG, borderBottom: '1px solid #1e3a5f' }}>
              <div
                onClick={() => { if (s.employeeId) onEmployeeRowClick?.(s.employeeId); }}
                title={clickable ? 'Щёлкните, чтобы добавить человека в фильтр «Исполнители» или убрать' : undefined}
                style={{
                  width: leftColWidth,
                  flexShrink: 0,
                  boxSizing: 'border-box',
                  position: 'sticky',
                  left: 0,
                  zIndex: STICKY_INIT_Z,
                  background: INIT_HEADER_BG_OPAQUE,
                  borderRight: '1px solid #1e3a5f',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 12px',
                  cursor: clickable ? 'pointer' : 'default',
                }}
              >
                {s.employeeId && <EmployeeAvatar name={s.name} role={s.role} size={20} />}
                <span style={{ fontSize: 13, fontWeight: 700, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.name}
                </span>
                {s.teamNote && (
                  <span style={{ fontSize: 11, whiteSpace: 'nowrap', color: s.isBorrowed ? '#b39ddb' : 'var(--text-muted, #8ab0d8)' }}>
                    {s.teamNote}
                  </span>
                )}
                {s.loadPct !== null && (
                  <span
                    title="Средняя загрузка в этом плане по рабочим дням квартала"
                    style={{ marginLeft: 'auto', flexShrink: 0, fontSize: 11, color: 'var(--text-muted, #8ab0d8)' }}
                  >
                    {s.loadPct}%
                  </span>
                )}
              </div>
              <div style={trackStyle(trackWidthPx)} />
            </div>
            {/* Полоса «все работы»: фазы этого плана цветом фазы, чужие брони — штриховкой. */}
            {s.employeeId && (
              <div style={{ display: 'flex', height: ROW_HEIGHT - 8, borderBottom: '1px solid #0e2540' }}>
                <ItemTitleCell title="Все работы" jiraKey={null} leftColWidth={leftColWidth} fontWeight={400} />
                <div style={trackStyle(trackWidthPx)}>
                  {lane.map((r) => (
                    <div
                      key={`${r.kind}-${r.start}-${r.label}`}
                      title={r.label}
                      style={{
                        position: 'absolute',
                        left: `${dateToLeft(r.start, timeline)}%`,
                        width: `${datesToWidth(r.start, r.end, timeline)}%`,
                        top: '50%',
                        transform: 'translateY(-50%)',
                        height: 12,
                        boxSizing: 'border-box',
                        borderRadius: 3,
                        background: r.kind === 'booking'
                          ? OTHER_TEAM_HATCH
                          : (appearance.phase_colors[r.phase] ?? PHASE_COLORS[r.phase]),
                        border: r.kind === 'booking' ? '1px solid rgba(160,170,190,0.5)' : 'none',
                        zIndex: r.kind === 'booking' ? 3 : 2,
                      }}
                    />
                  ))}
                </div>
              </div>
            )}
            {/* Фазы человека в этом плане — те же полосы, что в «Задачах», с перетаскиванием. */}
            {s.rows.map((row) => {
              const color = appearance.phase_colors[row.phase] ?? PHASE_COLORS[row.phase];
              return (
                <div
                  key={row.key}
                  data-gantt-row="true"
                  style={{ display: 'flex', height: ROW_HEIGHT - 4, borderBottom: '1px solid #0e2540' }}
                >
                  <ItemTitleCell
                    title={row.itemTitle}
                    jiraKey={row.itemKey}
                    leftColWidth={leftColWidth}
                    fontWeight={400}
                    dotColor={color}
                    assignee={PHASE_LABELS[row.phase]}
                    hours={row.hours > 0 ? `${Math.round(row.hours)} ч` : ''}
                  />
                  <div data-gantt-track="true" style={trackStyle(trackWidthPx)}>
                    {row.assignments.filter((a) => a.start_date && a.end_date).map((a) => (
                      <PhaseBar
                        key={a.id}
                        assignment={a}
                        planId={planId}
                        timeline={timeline}
                        refKey={`${a.backlog_item_id}-${a.phase}-${a.part_number}`}
                        rowRefs={rowRefs}
                        color={color}
                        employees={employees}
                        hasConflict={conflictSet.has(a.id)}
                        onClick={onAssignmentClick ? () => onAssignmentClick(a.id) : undefined}
                        unavailableDays={a.unavailable_days}
                        highlightedEmployeeId={highlightedEmployeeId}
                        pulseEmp={rpPrefs.pulse_highlighted_employee}
                        pulseCp={rpPrefs.pulse_critical_path}
                        quarterEndDate={quarterEndDate}
                        busyDays={busyByAssignment?.get(a.id)}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}
```

1.6. В `export default function GanttRows` перед `return <TwoLevelRows {...props} />;` добавить
`  if (props.layout === 'people') return <PeopleRows {...props} />;`

- [ ] **Step 2: `GanttChart.tsx` — проброс**

2.1. Импорт типов: `import type { AssignmentOut, DependencyOut, ExternalBookingOut, ScheduledBlock } from '../../api/resourcePlanning';` заменить на
`import type { AssignmentOut, DependencyOut, EmployeeLoadOut, ExternalBookingOut, ScheduledBlock } from '../../api/resourcePlanning';`.

2.2. В `interface Props` после `layout?: RpLayout;` добавить:

```ts
  /** Строки подвала — команда, привлечённость и загрузка людей для вида «Исполнители». */
  employeeLoad?: EmployeeLoadOut[];
  /** Команда плана — подпись своих в виде «Исполнители». */
  planTeam?: string | null;
```

и в деструктуризацию — `employeeLoad,` и `planTeam,`.

2.3. В `<GanttRows …>` добавить пропсы:

```tsx
            layout={layout}
            externalBookings={bookings}
            employeeLoad={employeeLoad}
            planTeam={planTeam}
            isWorkday={isWorkday}
```

- [ ] **Step 3: Страница `ResourcePlanningPage.tsx`**

3.1. Импорты: `import { App, Button, Empty, … Tag } from 'antd';` → добавить `Alert` первым: `import { Alert, App, Button, Empty, Input, Modal, Select, Segmented, Space, Spin, Switch, Tag } from 'antd';`; `import type { ViewMode } from '../components/resource-planning/GanttRows';` → `import type { RpLayout, ViewMode } from '../components/resource-planning/GanttRows';`; после `import { sortAssignmentsByScenarioAssignee } from '../utils/sortAssignments';` добавить `import { filterByPeople } from '../utils/rpPeople';`; перед `function ResourcePlanningPageInner()` добавить `const NO_PEOPLE: string[] = [];`.

3.2. Строку

```tsx
  const [highlightedEmployeeId, setHighlightedEmployeeId] = useState<string | null>(null);
```

заменить на

```tsx
  // Фильтр «Исполнители» — на план: при смене плана сбрасывается сам.
  const [peopleFilterState, setPeopleFilterState] = useState<{ planId: string | null; ids: string[] }>(
    { planId: null, ids: [] },
  );
```

3.3. После `  const { prefs, patch: patchPrefs } = useRpPreferences();` добавить:

```tsx
  const layout: RpLayout = prefs.view_mode === 'people' ? 'people' : 'tasks';
  const peopleFilter = useMemo(
    () => (peopleFilterState.planId === planId ? peopleFilterState.ids : NO_PEOPLE),
    [peopleFilterState, planId],
  );
  const setPeopleFilter = (ids: string[]) => setPeopleFilterState({ planId, ids });
  // Щелчок по человеку (фишка фазы, имя в подвале, заголовок секции)
  // добавляет его в фильтр или убирает.
  const togglePerson = (id: string | null) => {
    if (!id) return;
    setPeopleFilter(peopleFilter.includes(id) ? peopleFilter.filter(x => x !== id) : [...peopleFilter, id]);
  };
  // Подсветка и пульсация — когда в фильтре ровно один человек.
  const highlightedEmployeeId = peopleFilter.length === 1 ? peopleFilter[0] : null;
```

3.4. После мемо `displayedAssignments` добавить:

```tsx
  // Фильтр по людям: только их фазы и их брони в других командах.
  const shownAssignments = useMemo(
    () => filterByPeople(displayedAssignments, peopleFilter),
    [displayedAssignments, peopleFilter],
  );
  const shownBookings = useMemo(
    () => filterByPeople(gantt?.external_bookings ?? [], peopleFilter),
    [gantt, peopleFilter],
  );
  const peopleOptions = useMemo(
    () => (gantt?.employee_load ?? []).map(r => ({
      value: r.employee_id,
      label: r.is_borrowed
        ? `${r.employee_name ?? '—'} · из ${r.borrowed_from ?? 'другой команды'}`
        : (r.employee_name ?? '—'),
    })),
    [gantt],
  );
```

3.5. В панели `<Space size={4} style={{ marginLeft: 'auto' }}>` первыми элементами вставить:

```tsx
          {viewMode === 'two-level' && gantt && (
            <Segmented
              size="small"
              value={layout}
              onChange={v => patchPrefs({ view_mode: v as RpLayout })}
              options={[
                { label: 'Задачи', value: 'tasks' },
                { label: 'Исполнители', value: 'people' },
              ]}
            />
          )}
          {viewMode === 'two-level' && gantt && (
            <Select
              mode="multiple"
              size="small"
              allowClear
              prefix="Исполнители:"
              placeholder="все"
              value={peopleFilter}
              onChange={setPeopleFilter}
              options={peopleOptions}
              maxTagCount="responsive"
              showSearch={{ optionFilterProp: 'label' }}
              style={{ minWidth: 220, maxWidth: 360 }}
            />
          )}
```

3.6. В виде «Исполнители» не нужны кнопки про задачи:
- `{viewMode === 'two-level' && (` перед кнопкой с `type={depDrawMode ? 'primary' : 'default'}` → `{viewMode === 'two-level' && layout === 'tasks' && (`;
- `{viewMode === 'two-level' && subgroupOrder.length > 0 && (` → `{viewMode === 'two-level' && layout === 'tasks' && subgroupOrder.length > 0 && (`;
- у кнопки «Свернуть все» условие `{viewMode === 'two-level' && gantt && (` (то, за которым идёт `<Button size="small" onClick={() => { const allIds = …`) → `{viewMode === 'two-level' && layout === 'tasks' && gantt && (`.

3.7. Перед `{gantt && viewMode !== 'plane' && ( <ConflictPanel` добавить:

```tsx
      {gantt?.stale_due_to_other_teams && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 8 }}
          title={`Планы других команд изменились после расчёта${
            gantt.stale_teams?.length ? ` (${gantt.stale_teams.join(', ')})` : ''
          } — нажмите «Распределить»`}
          action={
            <Button size="small" loading={compute.isPending} onClick={handleCompute}>
              Распределить
            </Button>
          }
        />
      )}
```

3.8. В `<GanttChart …>`: `assignments={displayedAssignments}` → `assignments={shownAssignments}`; `externalBookings={gantt.external_bookings}` → `externalBookings={shownBookings}`; `onEmployeeRowClick={setHighlightedEmployeeId}` → `onEmployeeRowClick={togglePerson}`; добавить пропсы `layout={layout}`, `employeeLoad={gantt.employee_load}`, `planTeam={gantt.plan.team}`.

3.9. В `<EmployeeLoadHeatmap …>` добавить пропсы:

```tsx
          assignments={gantt.assignments}
          bookings={gantt.external_bookings ?? []}
          selectedIds={peopleFilter}
          onEmployeeClick={togglePerson}
```

- [ ] **Step 4: Сборка, тесты, линтер**

Run: `cd frontend && npm run build && npx vitest run src`
Expected: PASS.

Run: `cd frontend && npx eslint src/pages/ResourcePlanningPage.tsx src/components/resource-planning/GanttRows.tsx src/components/resource-planning/GanttChart.tsx`
Expected: без новых замечаний.

- [ ] **Step 5: Проверка вживую (нужна группа A)**

Запустить бэкенд `uvicorn app.main:app --reload --port 8000` (на Windows при зависании перезапуска — завершить процесс на порту 8000 и запустить снова) и фронт `cd frontend && npm run dev`; открыть «Ресурсное планирование», план Q4 2026 команды СФО:
- переключатель «Задачи / Исполнители» переживает перезагрузку страницы, «Только рабочие» при этом не сбрасывается;
- у Шутова/Пряничникова в «Исполнителях» полоса «все работы» показывает брони ERP ТУ штриховкой с подсказкой «KEY · Фаза — команда»;
- на полосах фаз привлечённых — вырезы с подсказкой «занят в плане … ·»;
- фильтр «Исполнители» и щелчки по фишке, имени в подвале, заголовку секции добавляют/убирают человека, «×» сбрасывает;
- в плане ERP ТУ блок «Наши люди в других командах» со строками «Имя · KEY · Фаза», красные отметки там, где ERP ТУ тоже занял человека;
- перетаскивание полосы на занятый день ставит её на первый свободный день;
- после «Распределить» в плане ERP ТУ план СФО показывает предупреждение «Планы других команд изменились…».

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/resource-planning/GanttRows.tsx frontend/src/components/resource-planning/GanttChart.tsx frontend/src/pages/ResourcePlanningPage.tsx
git commit -F - <<'EOF'
feat(rp-ui): вид «Исполнители», фильтр по людям и предупреждение об изменённых планах

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Группа D — фронт сценария

### Task D1: Выбор исполнителя строки сценария из всех команд

**Files:**
- Modify: `frontend/src/api/planning.ts`, `frontend/src/hooks/usePlanning.ts`
- Modify: `frontend/src/components/planning/BacklogAllocRow.tsx`
- Modify: `frontend/src/pages/PlanningPage.tsx` (~425–431 и проп строки ~973)

- [ ] **Step 1: Запрос кандидатов (контракт 5)**

В `frontend/src/api/planning.ts` после импорта типов добавить `import type { AssignmentCandidateGroup } from './resourcePlanning';`, а после `patchAllocationAssignee`:

```ts
/** Кандидаты в исполнители строки сценария: «Из Jira» / «Моя команда» / «Другие команды». */
export const getScenarioAssigneeCandidates = (scenarioId: string, backlogItemId: string) =>
  api.get<AssignmentCandidateGroup[]>(
    `/planning/scenarios/${scenarioId}/assignee-candidates`,
    { backlog_item_id: backlogItemId },
  );
```

В `frontend/src/hooks/usePlanning.ts` в список импортов из `'../api/planning'` добавить `getScenarioAssigneeCandidates,`, добавить `import type { AssignmentCandidateGroup } from '../api/resourcePlanning';`, а после `usePatchAllocationAssignee`:

```ts
/** Кандидаты в исполнители строки сценария — грузятся, когда список открыли. */
export function useScenarioAssigneeCandidates(
  scenarioId: string,
  backlogItemId: string,
  enabled: boolean,
) {
  return useQuery<AssignmentCandidateGroup[]>({
    queryKey: ['planning', 'assignee-candidates', scenarioId, backlogItemId],
    queryFn: () => getScenarioAssigneeCandidates(scenarioId, backlogItemId),
    enabled: enabled && !!scenarioId && !!backlogItemId,
    staleTime: 30_000,
  });
}
```

- [ ] **Step 2: Список в строке сценария**

В `frontend/src/components/planning/BacklogAllocRow.tsx`:

2.1. Импорты: `import { memo, useCallback, type CSSProperties } from 'react';` → `import { memo, useCallback, useMemo, useState, type CSSProperties } from 'react';`; добавить

```ts
import { useScenarioAssigneeCandidates } from '../../hooks/usePlanning';
import { candidateOptions } from '../../utils/rpCandidates';
```

2.2. Из `BacklogAllocRowProps` удалить строку `  assigneeOptions: { label: string; value: string }[];`, из деструктуризации параметров — `assigneeOptions,`.

2.3. После `const setRowRef = useCallback(…);` добавить:

```tsx
  // Кандидаты — все, кто в квартале сценария состоит в какой-либо команде.
  // Грузятся, только когда список открыли: строк в сценарии много.
  const [assigneeOpen, setAssigneeOpen] = useState(false);
  const candidates = useScenarioAssigneeCandidates(scenarioId, a.backlog_item_id, assigneeOpen);
  const roleLabels = useMemo(
    () => new Map(roles.map((r) => [r.code, r.label] as const)),
    [roles],
  );
  const assigneeOptions = useMemo(
    () =>
      candidates.data?.length
        ? candidateOptions(candidates.data, roleLabels)
        : a.assignee_employee_id
          ? [{ value: a.assignee_employee_id, label: a.assignee_display_name ?? '—' }]
          : [],
    [candidates.data, roleLabels, a.assignee_employee_id, a.assignee_display_name],
  );
```

2.4. Заменить `<Select …>` исполнителя

```tsx
          <Select
            size="small"
            value={a.assignee_employee_id ?? undefined}
            placeholder={a.assignee_display_name ?? '—'}
            allowClear
            disabled={!isDraft}
            style={{ width: '100%', fontSize: 12 }}
            options={assigneeOptions}
            onChange={(value: string | undefined) => onAssigneeChange(a.id, value ?? null)}
          />
```

на

```tsx
          <Select
            size="small"
            value={a.assignee_employee_id ?? undefined}
            placeholder={a.assignee_display_name ?? '—'}
            allowClear
            disabled={!isDraft}
            style={{ width: '100%', fontSize: 12 }}
            popupMatchSelectWidth={false}
            showSearch={{ optionFilterProp: 'label' }}
            loading={candidates.isFetching}
            options={assigneeOptions}
            onOpenChange={(open) => {
              if (open) setAssigneeOpen(true);
            }}
            // В закрытом поле — только имя; роль, команда и загрузка — в списке.
            labelRender={({ label }) => a.assignee_display_name ?? label}
            onChange={(value: string | undefined) => onAssigneeChange(a.id, value ?? null)}
          />
```

- [ ] **Step 3: Страница сценария**

В `frontend/src/pages/PlanningPage.tsx` удалить мемо

```tsx
  const assigneeOptions = useMemo(
    () => (resourceBase?.employees ?? []).map((emp) => ({
      label: emp.display_name,
      value: emp.employee_id,
    })),
    [resourceBase?.employees],
  );
```

и в `<BacklogAllocRow …>` проп `assigneeOptions={assigneeOptions}`.

- [ ] **Step 4: Сборка, тесты, линтер**

Run: `cd frontend && npm run build && npx vitest run src`
Expected: PASS.

Run: `cd frontend && npx eslint src/components/planning/BacklogAllocRow.tsx src/pages/PlanningPage.tsx src/api/planning.ts src/hooks/usePlanning.ts`
Expected: без новых замечаний.

- [ ] **Step 5: Проверка вживую (нужны B2, B3)**

Сценарий СФО Q4 2026 в черновике: открыть список исполнителя в строке — группы «Из Jira», «Моя команда», «Другие команды», у каждого роль, команда и процент; поиск по фамилии и по названию команды работает; выбрать Шутова из ERP ТУ — в закрытом поле его имя; «Обновить с Jira» в «Целевых задачах» выбор не сбрасывает.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/planning.ts frontend/src/hooks/usePlanning.ts frontend/src/components/planning/BacklogAllocRow.tsx frontend/src/pages/PlanningPage.tsx
git commit -F - <<'EOF'
feat(planning-ui): исполнитель строки сценария — из всех команд с группами и загрузкой

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task D2: Подпись «Привлечены другими командами (не вычтено)»

**Files:**
- Modify: `frontend/src/types/api.ts` (`ResourceSummaryOut`)
- Modify: `frontend/src/components/planning/ScenarioResourceSummary.tsx` (~719–746)

- [ ] **Step 1: Тип (контракт 4)**

В `ResourceSummaryOut` после `booked_by_other_teams_by_role?: Record<string, number>;` добавить:

```ts
  /** Часы людей команды в планах команд, взявших их к себе (не вычтены из «На бэклог»). */
  borrowed_by_other_teams_by_role?: Record<string, number>;
```

- [ ] **Step 2: Подпись под таблицей**

В `ScenarioResourceSummary.tsx` блок

```tsx
      {(() => {
        // Часы, которые сотрудники команды уже отдали планам других команд
        // этого квартала: сервер вычел их из «На бэклог».
        const rank = (role: string) => {
          const i = summary.roles.indexOf(role);
          return i < 0 ? summary.roles.length : i;
        };
        const booked = Object.entries(summary.booked_by_other_teams_by_role ?? {})
          .filter(([, h]) => h >= 0.5)
          .sort(([a], [b]) => rank(a) - rank(b));
        if (booked.length === 0) return null;
        return (
          <div
            style={{
              borderTop: `1px solid ${DARK_THEME.border}`,
              padding: '8px 14px',
              fontSize: 12,
              color: DARK_THEME.textMuted,
            }}
          >
            Занято в планах других команд этого квартала:{' '}
            {booked
              .map(([role, h]) => `${getRoleLabel(roles, role)} ${Math.round(h).toLocaleString('ru')} ч`)
              .join(', ')}
            . Эти часы уже вычтены из «На бэклог».
          </div>
        );
      })()}
```

заменить на

```tsx
      {(() => {
        // Работа людей команды в планах других команд этого квартала. Где
        // человек тоже состоит — сервер вычел её из «На бэклог»; команды,
        // взявшие его к себе, подстраиваются сами — их часы только справочно.
        const rank = (role: string) => {
          const i = summary.roles.indexOf(role);
          return i < 0 ? summary.roles.length : i;
        };
        const byRole = (hours?: Record<string, number>) =>
          Object.entries(hours ?? {})
            .filter(([, h]) => h >= 0.5)
            .sort(([a], [b]) => rank(a) - rank(b))
            .map(([role, h]) => `${getRoleLabel(roles, role)} ${Math.round(h).toLocaleString('ru')} ч`)
            .join(', ');
        const booked = byRole(summary.booked_by_other_teams_by_role);
        const borrowed = byRole(summary.borrowed_by_other_teams_by_role);
        if (!booked && !borrowed) return null;
        return (
          <div
            style={{
              borderTop: `1px solid ${DARK_THEME.border}`,
              padding: '8px 14px',
              fontSize: 12,
              color: DARK_THEME.textMuted,
            }}
          >
            {booked && (
              <div>
                Занято в планах других команд этого квартала: {booked}. Эти часы уже вычтены из «На бэклог».
              </div>
            )}
            {borrowed && <div>Привлечены другими командами: {borrowed} (не вычтено).</div>}
          </div>
        );
      })()}
```

- [ ] **Step 3: Сборка и линтер**

Run: `cd frontend && npm run build && npx eslint src/components/planning/ScenarioResourceSummary.tsx src/types/api.ts`
Expected: без ошибок и новых замечаний.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -F - <<'EOF'
feat(planning-ui): сводка ресурса показывает часы, забранные командами-привлекателями

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Финал

### Task F1: Справка и заметки для разработчиков

**Files:**
- Modify: `docs/help/resource-planning.md` (3.4, 3.5, 3.9, 3.10, сценарии Д и Е)
- Modify: `docs/help/planning.md` (3.4, 3.8)
- Modify: `app/services/CLAUDE.md` (раздел `cross_team_occupancy`)

- [ ] **Step 1: `docs/help/resource-planning.md`**

1.1. Раздел `### 3.4. Закрепление окна и автопродление` заменить целиком (до `### 3.5.`) на:

```markdown
### 3.4. Ручная дата начала

Полосу фазы можно перетащить мышью или задать ей дату начала в боковой панели. Задаётся **только начало**: конец и часы по дням планировщик считает сам — с этой даты по свободным дням исполнителя. Выходные, праздники, отпуска, заблокированные периоды, дни вне команды, работа человека в планах других команд и уже закреплённые фазы этого плана при этом пропускаются. Поставить фазу поверх чужой работы нельзя: полоса начнётся с первого свободного дня. После перетаскивания план пересчитывается целиком — как при смене исполнителя.

Полоса с ручной датой обведена тонкой бирюзовой рамкой, в боковой панели — метка «Закреплено». Поле «Окончание» в панели только показывает, где фаза закончится. Если с выбранной даты до конца квартала с месяцем запаса свободных дней не хватило, план покажет конфликт «Часы не размещены» с пояснением «не поместилось в свободные дни исполнителя».

Без ручной даты планировщик подбирает окно сам — по загрузке и связям.
```

1.2. В разделе 3.5 пункт `- **Прямо с полосы Gantt** — клик по аватарке → Popover …` заменить на:

```markdown
- **Щелчок по фишке исполнителя** на строке фазы исполнителя не меняет — он добавляет человека в фильтр «Исполнители» или убирает (см. 3.9).
```

а абзац, начинающийся с `Аналитик по умолчанию подтягивается из поля «исполнитель» инициативы в Jira`, заменить на:

```markdown
Кого планировщик ставит на фазу, по порядку: исполнитель, закреплённый на этой фазе вручную → исполнитель строки сценария на фазе своей роли (разработчик — на разработку; аналитик, РП, консультант — на анализ; без роли или с другой ролью — на анализ, а если у задачи нет часов анализа — на разработку) → для разработки — «Разработчик» из поля задачи в Jira → подбор среди своей команды. Исполнитель строки сценария из другой команды ставится, только если его выбрали в сценарии вручную, — тогда он становится привлечённым; исполнитель, подтянутый из Jira, берётся только из своей команды. «Разработчик» из Jira подходит из любой команды, если у него разработческая роль (или роль не указана) и в квартале плана он состоит хотя бы в одной команде; если у самой задачи поле пустое или человек не подходит, берётся тот, кто чаще всего стоит «Разработчиком» в её незакрытых подзадачах; если у него не хватает свободных часов на разработку — разработчика подбирает планировщик среди своей команды. Выбранного вручную (на фазе или в сценарии) планировщик не заменяет, даже если у человека не хватает времени: остаток часов виден конфликтом «Часы не размещены». Тестирование — без сотрудника.
```

1.3. Раздел `### 3.9. Виды отображения (включая «Ресурсы»)` заменить целиком (до `### 3.10.`) на:

```markdown
### 3.9. Виды «Задачи» и «Исполнители», фильтр по людям

Переключатель **«Задачи / Исполнители»** — в панели над диаграммой; выбор запоминается для вашей учётной записи.

- **Задачи** — основной вид: задача → её фазы, задачи можно сворачивать. Здесь доступны связи, эстафета, группы команды и блоки «Привлечённые» и «Наши люди в других командах» (см. 3.10).
- **Исполнители** — секция на каждого, у кого есть фазы в этом плане: свои, привлечённые и отдельно «Без исполнителя» (например, тестирование). В заголовке — имя, команда (у привлечённого — «из <команда>») и средняя загрузка в этом плане. Под ним полоса **«все работы»**: фазы этого плана цветом фазы, работа в планах других команд — серой штриховкой (в подсказке — задача, фаза и команда), свободные дни пустые. Ниже — фазы человека в этом плане; их можно перетаскивать, как в «Задачах».

**Фильтр «Исполнители»** оставляет на диаграмме только фазы выбранных людей и их работу в других командах — в обоих видах. Добавить или убрать человека можно в самом фильтре или щелчком по нему: по фишке исполнителя на строке фазы, по имени в подвале «Загрузка по дням», по заголовку секции в виде «Исполнители». Крестик в фильтре возвращает всех. Когда в фильтре один человек, его полосы подсвечиваются.
```

1.4. В разделе 3.10:
- пункт `- **Как он попадает в план:** …` заменить на `- **Как он попадает в план:** вручную через поле «исполнитель» фазы, как исполнитель строки сценария, выбранный там вручную (см. справку «Планирование сценариев»), или сам — если он стоит «Разработчиком» задачи в Jira.`
- пункт `- **Когда он свободен:** …` заменить на:

```markdown
- **Когда он свободен — сначала домашняя команда.** Для каждой команды на квартал берётся её опорный план — основной план утверждённого сценария, а если утверждённого нет, план самого свежего черновика (он помечается «предварительно»). Привлечённый в ваш план обходит всю свою работу в опорных планах других команд, включая «хвосты» планов прошлого квартала. Ваш собственный сотрудник обходит только работу в командах, где он тоже состоит; работу в команде, которая взяла его к себе, домашний план не обходит — подстраивается привлекающая команда. Если эта работа всё же пересеклась с домашним планом, команда, которая привлекла сотрудника, увидит конфликт «Пересечение с другой командой» (см. 3.7).
- **Вырезы на полосе.** Рабочие дни внутри полосы, когда у фазы нет часов, потому что человек занят в другой команде, показаны вырезом со штриховкой; подсказка — «занят в плане <команда> · <задача> <фаза>».
```

- после пункта `- **Блок «Привлечённые»** …` добавить:

```markdown
- **Блок «Наши люди в других командах»** — над задачами, для ваших сотрудников, которых другие команды взяли к себе: строки «Имя · задача · фаза», команда и дни работы там. Только просмотр, сворачивается щелчком по шапке. Красная рамка на дне — ваш план в этот день тоже занял человека и вместе выходит больше его рабочего дня: команда, которая его привлекла, получит конфликт «Пересечение с другой командой».
- **«Планы других команд изменились после расчёта».** Если после последнего «Распределить» другие команды поменяли планы, которые влияют на свободные дни ваших людей, над диаграммой появится предупреждение с кнопкой «Распределить».
```

- в конец пункта `- **Подвал «Загрузка по дням»:** …` дописать: ` Подсказка дня перечисляет по строкам, сколько часов и на каких задачах человек занят в этом плане и в каждой другой команде.`
- пункт `- **Сценарий:** …` заменить на `- **Сценарий:** в блоке ресурса сценария часы «На бэклог» уменьшаются на работу сотрудников команды в планах команд, где они тоже состоят; под таблицей — подпись, сколько вычтено. Часы, которые забрали команды, взявшие ваших людей к себе, не вычитаются — они показаны отдельной подписью «Привлечены другими командами … (не вычтено)».`

1.5. `### Сценарий Д: закрепить окно работ под дедлайн` заменить целиком (до `### Сценарий Е`) на:

```markdown
### Сценарий Д: поставить фазу на нужную дату

1. Перетащить полосу фазы на нужный день — или открыть фазу и задать дату начала в боковой панели.
2. План пересчитается: часы лягут с этой даты по свободным дням исполнителя, полоса начнётся с первого свободного дня.
3. При следующих пересчётах фаза остаётся на своей дате; снять ручную дату — кнопкой сброса ручных правок.
4. Если свободных дней с этой даты не хватило — появится конфликт «Часы не размещены».
```

1.6. `### Сценарий Е: посмотреть, чем занят конкретный сотрудник` заменить целиком (до `---`) на:

```markdown
### Сценарий Е: посмотреть, чем занят конкретный сотрудник

1. Переключить вид на «Исполнители» — у человека своя секция: полоса «все работы» (этот план и другие команды) и его фазы.
2. Чтобы оставить на диаграмме только его, выбрать человека в фильтре «Исполнители» или щёлкнуть по его имени в подвале.
3. Кликнуть по любой полосе — справа откроется панель с деталями.
```

- [ ] **Step 2: `docs/help/planning.md`**

2.1. В таблице раздела 3.4 строку

```markdown
| Исполнитель | Кто ведёт инициативу. Выбирается из списка сотрудников команды. |
```

заменить на

```markdown
| Исполнитель | Кто ведёт инициативу. В списке — все, кто в квартале сценария состоит в какой-либо команде, тремя группами: «Из Jira» (исполнитель задачи в Jira), «Моя команда», «Другие команды»; поиск по имени, роли и команде, рядом — загрузка за квартал по планам всех команд. Выбор вручную не затирается обновлением из Jira, пока в Jira не сменят исполнителя. В ресурсном плане исполнитель встаёт на фазу своей роли — разработчик на разработку, аналитик на анализ; из другой команды — как привлечённый. |
```

2.2. В разделе 3.8 после пункта `- **По сотрудникам** — …` добавить:

```markdown
- **Подписи под таблицей ресурса** — «Занято в планах других команд этого квартала» (работа ваших людей в командах, где они тоже состоят; вычтена из «На бэклог») и «Привлечены другими командами … (не вычтено)» (часы, которые забрали команды, взявшие ваших людей к себе; из «На бэклог» не вычитаются — подстраиваются они).
```

- [ ] **Step 3: `app/services/CLAUDE.md`**

В абзаце под `## cross_team_occupancy` фразу

```
`external_bookings(team=...)` — брони в опорных планах всех команд, кроме `team` (`team=None` — всех): квартала и прошлого квартала (его хвосты заходят в этот на месяц запаса), по окну `start`–`end`; три запроса на любой объём; фаза без посуточной раскладки размазывается по будням. `subtract_occupancy` вычитается из доступности в `compute_schedule`:
```

заменить на

```
`external_bookings(team=...)` — брони в опорных планах всех команд, кроме `team` (`team=None` — всех): квартала и прошлого квартала (его хвосты заходят в этот на месяц запаса), по окну `start`–`end`; пять запросов на любой объём; фаза без посуточной раскладки размазывается по будням. У брони `is_borrowing` (команда брони взяла человека не из своего состава — по кварталу её плана) и `changed_at`. `subtractable(bookings, borrowed)` — правило «сначала домашняя команда»: привлечённому вычитаются все брони, своему — только команд, где он тоже состоит; им пользуются расчёт плана, расшифровка фазы и признак устаревания диаграммы (`stale_teams`). Закреплённая дата начала раскладывается общим `_allocate_hours_with_breakdown` по этой же доступности. `subtract_occupancy` вычитается из доступности в `compute_schedule`:
```

и в конце того же абзаца дописать:

```
`ResourceBaseService` вычитает только брони без `is_borrowing`, остальные показывает справочно (`borrowed_by_other_teams_by_role`). Кандидаты в исполнители фазы и строки сценария — общая [assignee_candidates.py](assignee_candidates.py); исполнитель строки сценария встаёт на фазу своей роли (`_scenario_executor`), из чужой команды — только выбранный вручную (`BacklogItem.assignee_manual`, обновление из Jira его не затирает до смены исполнителя в Jira — `backlog_service.apply_jira_assignee`).
```

- [ ] **Step 4: Commit**

```bash
git add docs/help/resource-planning.md docs/help/planning.md app/services/CLAUDE.md
git commit -F - <<'EOF'
docs(help): домашняя команда, ручная дата, вид «Исполнители», исполнитель сценария

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task F2: Заметки «Что нового»

**Files:**
- Modify: `release_notes/drafts.json` (через CLI)

- [ ] **Step 1: Добавить заметки** (порядок: новое → улучшения)

```bash
py -3.10 scripts/release_note.py add --type new --section resources --title "Вид «Исполнители» и фильтр по людям" --description "В ресурсном плане появился переключатель «Задачи / Исполнители». В виде «Исполнители» у каждого человека своя секция: полоса «все работы» показывает его фазы в этом плане и занятость в других командах, ниже — его фазы, их можно перетаскивать. Фильтр «Исполнители» оставляет на диаграмме только выбранных людей — выбрать можно в списке или щелчком по человеку на строке фазы, в подвале или в заголовке секции."
py -3.10 scripts/release_note.py add --type new --section resources --title "Видно, куда другие команды забирают ваших людей" --description "Над задачами появился блок «Наши люди в других командах»: чем ваши сотрудники заняты в планах команд, которые взяли их к себе. Дни, где ваш план тоже занял человека и вместе выходит больше его рабочего дня, отмечены красным. Подсказка дня в подвале «Загрузка по дням» перечисляет по строкам, сколько часов и на каких задачах человек занят в этом плане и в каждой другой команде."
py -3.10 scripts/release_note.py add --type new --section scenarios --title "Исполнитель в сценарии — из любой команды" --description "В строке сценария исполнителя можно выбрать из всех, кто в квартале состоит в какой-либо команде: группы «Из Jira», «Моя команда» и «Другие команды», с поиском, ролью и загрузкой за квартал. Выбор не затирается обновлением из Jira, пока там не сменят исполнителя. В ресурсном плане исполнитель встаёт на фазу своей роли — разработчик на разработку, аналитик на анализ — даже если он из другой команды."
py -3.10 scripts/release_note.py add --type improvement --section resources --title "Сначала домашняя команда" --description "Расчёт плана больше не уступает команде, которая взяла вашего сотрудника к себе: подстраивается она. Работа в командах, где человек тоже состоит, по-прежнему обходится. Если после расчёта планы других команд изменились, над диаграммой появится предупреждение с кнопкой «Распределить»."
py -3.10 scripts/release_note.py add --type improvement --section resources --title "Перетаскивание фазы раскладывает часы по свободным дням" --description "Перетаскивание задаёт только дату начала: часы раскладываются с неё по свободным дням исполнителя — мимо отпусков, праздников и работы в других командах, — а план сразу пересчитывается. Дни внутри полосы, когда человек занят в другой команде, показаны вырезом со штриховкой и подсказкой, чем он там занят."
py -3.10 scripts/release_note.py add --type improvement --section scenarios --title "Сводка ресурса показывает, сколько часов забрали другие команды" --description "Под таблицей ресурса сценария появилась подпись «Привлечены другими командами»: сколько часов ваших людей забронировали команды, взявшие их к себе. Из «На бэклог» эти часы не вычитаются."
```

Expected: каждая команда сообщает о добавлении записи в `release_notes/drafts.json`.

- [ ] **Step 2: Commit**

```bash
git add release_notes/drafts.json
git commit -F - <<'EOF'
docs(release-notes): заметки о доработках привлечения сотрудников

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task F3: Полная проверка

- [ ] **Step 1: Бэкенд целиком**

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py`
Expected: PASS (Postgres-тесты — SKIPPED без `TEST_DATABASE_URL`).

Run: `ruff check app/ tests/`
Expected: без новых замечаний относительно `main`.

Run: `mypy app/`
Expected: без новых ошибок относительно `main`.

- [ ] **Step 2: Миграции**

Run: `py -3.10 -m pytest tests/test_migrations_fresh_db.py tests/test_migration_pq05_backlog_assignee_manual.py -v`
Expected: PASS. Перед выпуском — тот же прогон на Postgres (`TEST_DATABASE_URL=postgresql://…`): SQLite не ловит типы значений по умолчанию.

- [ ] **Step 3: Фронт целиком**

Run: `cd frontend && npx vitest run src`
Expected: PASS.

Run: `cd frontend && npm run build`
Expected: сборка без ошибок.

Run: `cd frontend && npx eslint src/utils/rpBusy.ts src/utils/rpPeople.ts src/utils/externalBookings.ts src/components/resource-planning src/pages/ResourcePlanningPage.tsx src/pages/PlanningPage.tsx src/components/planning/BacklogAllocRow.tsx src/components/planning/ScenarioResourceSummary.tsx src/api src/hooks/usePlanning.ts src/types/api.ts`
Expected: без новых замечаний (сравнить с `main`, общий линтер фронта красный до этой работы).

- [ ] **Step 4: Граф кода и отправка**

Run: `graphify update .`
Expected: граф обновлён.

Run: `git push origin feature/planning-q4`
Expected: ветка отправлена.

---

## Самопроверка: покрытие спеки

| Требование спеки (Часть 5) | Задача |
|---|---|
| 5.1 бронь-привлечение, определение | A1 (`is_borrowing`, `_member_of`) |
| 5.1 свой сотрудник обходит только брони общих команд; привлечённый — все | A1 (`subtractable`), A2 (расчёт), A4 (расшифровка) |
| 5.1 база сценария: брони-привлечения не вычитаются, подпись «Привлечён другими командами: N ч (не вычтено)» | A3 (сервер), D2 (подпись) |
| 5.1 `CROSS_TEAM_OVERLAP` только у привлекающей; в домашнем — справочная отметка в блоке «Наши люди…» | не меняется (живой конфликт — только для привлечённых); A7 `overlap_days`, C3 отметки |
| 5.1 устаревание при чтении по `computed_at`/`updated_at`, не хранится | A1 (`changed_at`, `stale_teams`), A7 (поля ответа), C5 (предупреждение) |
| 5.2 вырезы со штриховкой и подсказкой «занят в плане <команда> · <KEY> <фаза>» | C1 (`busyGaps`), C2 (`BusyOverlay`) |
| 5.2 ручная дата = только начало, общий раскладчик по свободным окнам, поверх нельзя | A5 |
| 5.2 конец от клиента игнорируется, пересборка часов, пересчёт плана | A6 (сервер), C2 (фронт шлёт только начало) |
| 5.3 переключатель «Задачи / Исполнители», сохраняется в настройках | A8 (частичный PATCH), C5 |
| 5.3 секции людей, «Без исполнителя», заголовок, полоса «все работы», фазы с перетаскиванием | C1 (`peopleSections`, `personLaneRuns`), C5 (`PeopleRows`) |
| 5.3 фильтр по людям: список, щелчки (фишка, подвал, заголовок), оба вида, «×» | C1 (`filterByPeople`), C4 (подвал), C5 |
| 5.4 `external_bookings` для всех людей подвала с `employee_is_borrowed`, `is_borrowing` | A7 |
| 5.4 блок «Наши люди в других командах», красные отметки, сворачивается | A7 (`overlap_days`), C3 |
| 5.4 многострочная подсказка дня в подвале | C1 (`dayTooltipLines`), C4 |
| 5.4 брони на полосе «все работы» | C1, C5 |
| 5.5 кандидаты сценария из всех команд, группы, поиск, роль, команда, загрузка; общая функция | B1, B2, B4 (фаза плана), D1 |
| 5.5 ручной выбор не затирается обновлением из Jira до смены исполнителя там | B3 |
| 5.5 исполнитель сценария на фазе своей роли, из любой команды; приоритеты; нехватка времени → «Часы не размещены» | B4 |
| Тесты pytest: 5.1, база, устаревание, перетаскивание, кандидаты, ручной исполнитель, исполнитель по роли | A1–A7, B1–B4 |
| Тесты vitest: вырезы, группировка «Исполнители», фильтр, строки подсказки | C1 |
