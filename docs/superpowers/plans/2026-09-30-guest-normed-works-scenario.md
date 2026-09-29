# Нормированные работы основной команды в сценарии неосновной — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В сценарии неосновной команды у общего сотрудника «На бэклог» уменьшается на нормированные работы его основной команды (кроме «Технических задач»), а правила самой неосновной команды к нему не применяются.

**Architecture:** Новая функция `normed_reserve.guest_normed_by_day` раскладывает по дням запас основной команды гостя тем же `place_person`, что «Загрузка по дням». `ResourceBaseService.compute` и `compute_summary` вызывают её через один приватный метод и прибавляют часы к броням дня гостя; правила сценария гостю обнуляются через пустые «свои проценты». Сводка отдаёт новые поля, интерфейс показывает строку под таблицей.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, pytest; React 19 + TypeScript.

Спека: `docs/superpowers/specs/2026-09-30-guest-normed-works-scenario-design.md`.

Тесты запускать в переднем плане: `py -3.10 -m pytest <путь> -q`. Git — только в ветке `fix/manual-check-2026-09-30` рабочей копии `D:\ClaudeDev\JiraAnalysis-fixes2`.

---

## Файлы

- Modify: `app/services/normed_reserve.py` — новая функция `guest_normed_by_day`.
- Modify: `app/services/resource_base_service.py` — `_guest_normed`, гость в `compute` и `compute_summary`, поля `primary_normed_by_role`, `primary_normed_people`.
- Modify: `app/api/endpoints/planning.py` — поля ответа сводки.
- Modify: `frontend/src/types/api.ts`, `frontend/src/components/planning/ScenarioResourceSummary.tsx` — строка под таблицей.
- Modify: `docs/help/resource-planning.md` (раздел 3.10, пункт «Сценарий»), `release_notes/drafts.json`.
- Test: `tests/services/test_normed_reserve.py`, `tests/services/test_resource_base_external.py`.

---

### Task 1: `guest_normed_by_day` — нормированные работы основной команды гостя по дням

**Files:**
- Modify: `app/services/normed_reserve.py` (после `place_person`)
- Test: `tests/services/test_normed_reserve.py`

- [ ] **Step 1: Написать падающие тесты** (в конец `tests/services/test_normed_reserve.py`)

```python
def _guest_setup(db):
    """P — разработчик ERP (правила 55%, из них «Технические задачи» 10%),
    состоит и в «Блоке», где команда не основная. Броней нет."""
    types = _types(db)
    p = make_employee(db, "Пряничников", "ERP", role="dev")
    s = make_employee(db, "Шутов", "ERP", role="dev")
    join_team(db, p, "Блок")
    sc, _plan = make_plan(db, "ERP")
    _rules(db, sc, types)
    db.commit()
    return types, p, s


def test_guest_normed_excludes_cross_team_type(db_session):
    """Остаток «Технических задач» — время для других команд: в нормированные
    работы гостя он не входит (45% из 55%)."""
    types, p, _s = _guest_setup(db_session)

    by_day = nr.guest_normed_by_day(db_session, [p], [], *Q, D("2026-01-01"), D("2026-03-31"))

    assert round(sum(by_day[p.id].values()), 1) == round(0.45 * 64 * 8.0, 1)
    assert all(d.weekday() < 5 for d in by_day[p.id])


def test_guest_normed_blocked_day_is_whole_day(db_session):
    types, p, _s = _guest_setup(db_session)
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-05"), end_date=D("2026-01-07"),
                                  reason="Закрытие месяца", work_type_id=types["support_consult"].id))
    db_session.commit()

    by_day = nr.guest_normed_by_day(db_session, [p], [], *Q, D("2026-01-01"), D("2026-03-31"))

    assert [by_day[p.id][D(d)] for d in ("2026-01-05", "2026-01-06", "2026-01-07")] == [8.0, 8.0, 8.0]


def test_guest_normed_empty_without_home_reserve(db_session):
    """У основной команды нет правил — нормированных работ нет, как и раньше."""
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, p, "Блок")
    db_session.commit()

    assert nr.guest_normed_by_day(db_session, [p], [], *Q, D("2026-01-01"), D("2026-03-31")) == {}
```

- [ ] **Step 2: Убедиться, что падают**

Run: `py -3.10 -m pytest tests/services/test_normed_reserve.py -q -k guest_normed`
Expected: FAIL — `AttributeError: module 'app.services.normed_reserve' has no attribute 'guest_normed_by_day'`.

- [ ] **Step 3: Реализация** (в конец `app/services/normed_reserve.py`)

```python
def guest_normed_by_day(
    db: Session,
    guests: List[Employee],
    bookings: Iterable[cto.ExternalBooking],
    year: int,
    quarter: int,
    start: date,
    end: date,
) -> Dict[str, Dict[date, float]]:
    """{гость: {день: часы}} — нормированные работы основной команды гостя
    сценария, без вида работы в других командах («Технические задачи»):
    остаток этого вида — время, которое берут неосновные команды.

    Гость — состоит в команде сценария, но она у него не основная. Запас —
    основных команд квартала (`team_reserve`, личные проценты уже в нём),
    раскладка — `place_person`, как в «Загрузке по дням»: норма дня —
    календарь минус отсутствия; занятость — ``bookings`` (вычитаемые брони
    гостя); доля дня вне задачи — по вовлечённости броней; заблокированные
    дни — периоды основной команды и общие. Нет запаса — гостя в ответе нет.
    """
    if not guests:
        return {}
    ids = [e.id for e in guests]
    membership = tm.membership_rows(db, ids)
    homes = sorted({
        t
        for rows in membership.values()
        for t, joined, left, primary in rows
        if primary and (joined is None or joined <= end) and (left is None or left > start)
    })
    reserves = [team_reserve(db, t, year, quarter) for t in homes]
    labels = next((r.labels for r in reserves if r is not None), None)
    if labels is None:
        return {}
    cross = {
        w.id
        for w in db.execute(
            select(MandatoryWorkType).where(MandatoryWorkType.code == CROSS_TEAM_WORK_TYPE_CODE)
        ).scalars()
    }
    booked = list(bookings)
    busy = cto.daily_totals(booked)
    residue = cto.other_work_share((b.employee_id, b.involvement, b.daily_hours) for b in booked)
    hits = sb.resolve_blocked_days(db, guests, start, end, None)
    calendar = calendar_hours(db, start, end)
    absent = absent_days(db, ids, start, end)
    out: Dict[str, Dict[date, float]] = {}
    for e in guests:
        person = merge_person(reserves, e.id)
        if person is None:
            continue
        for wt in cross:
            person.share.pop(wt, None)
        cap = {d: h for d, h in calendar.items() if d not in absent.get(e.id, set())}
        load = place_person(
            cap, {}, busy.get(e.id, {}), residue.get(e.id, {}), hits.get(e.id, {}), person, labels
        )
        out[e.id] = {d: h for d, h in load.normed_by_day.items() if h > 0}
    return out
```

- [ ] **Step 4: Прогнать**

Run: `py -3.10 -m pytest tests/services/test_normed_reserve.py -q`
Expected: все зелёные.

- [ ] **Step 5: Коммит**

```bash
git add app/services/normed_reserve.py tests/services/test_normed_reserve.py
git commit -m "feat(planning): нормированные работы основной команды гостя по дням"
```

---

### Task 2: Гость в базе ресурса и сводке сценария

**Files:**
- Modify: `app/services/resource_base_service.py`
- Test: `tests/services/test_resource_base_external.py`

- [ ] **Step 1: Падающие тесты** (в конец `tests/services/test_resource_base_external.py`)

```python
def _guest_scenario(db_session, block_rule_pct=None):
    """P: основная ERP (правила 55%), вторая — «Блок». Сценарий «Блока» — P гость.
    В «Блоке» есть свой разработчик Иванов. ``block_rule_pct`` — правило «Блока»
    для разработчиков (орг. вопросы)."""
    from app.models import ScenarioRule
    from tests.services.normed_factory import _rules, _types

    types = _types(db_session)
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    make_employee(db_session, "Шутов", "ERP", role="dev")
    join_team(db_session, p, "Блок")
    ivanov = make_employee(db_session, "Иванов", "Блок", role="dev")
    erp_sc, _ = make_plan(db_session, "ERP")
    _rules(db_session, erp_sc, types)
    blk_sc, _ = make_plan(db_session, "Блок", scenario_status="draft")
    if block_rule_pct is not None:
        db_session.add(ScenarioRule(scenario_id=blk_sc.id, role="dev",
                                    work_type_id=types["organizational"].id,
                                    percent_of_norm=block_rule_pct))
    db_session.commit()
    return p, ivanov, erp_sc, blk_sc


QUARTER_NORM = 64 * 8.0  # I кв. 2026 без записей календаря


def test_guest_loses_home_normed_works_except_cross_team_type(db_session):
    p, ivanov, _erp, blk = _guest_scenario(db_session)

    s = ResourceBaseService(db_session).compute_summary(blk)

    home_normed = 0.45 * QUARTER_NORM
    assert round(s.primary_normed_by_role["dev"], 1) == round(home_normed, 1)
    assert round(s.available_by_role["dev"], 1) == round(2 * QUARTER_NORM - home_normed, 1)
    assert [x["display_name"] for x in s.primary_normed_people] == ["Пряничников"]


def test_guest_exempt_from_own_rules_of_secondary_team(db_session):
    """Правило «Блока» 20% режет только своего разработчика, не гостя."""
    p, ivanov, _erp, blk = _guest_scenario(db_session, block_rule_pct=20.0)
    svc = ResourceBaseService(db_session)

    base = {x.employee_id: x.total_hours for x in svc.compute(blk).employees}

    assert round(base[ivanov.id], 1) == round(0.8 * QUARTER_NORM, 1)
    assert round(base[p.id], 1) == round(0.55 * QUARTER_NORM, 1)


def test_guest_daily_base_matches_summary(db_session):
    p, ivanov, _erp, blk = _guest_scenario(db_session, block_rule_pct=20.0)
    svc = ResourceBaseService(db_session)

    total = sum(x.total_hours for x in svc.compute(blk).employees)
    s = svc.compute_summary(blk)

    assert round(total, 1) == round(s.available_by_role["dev"], 1)


def test_home_team_scenario_unchanged(db_session):
    p, _ivanov, erp, _blk = _guest_scenario(db_session)

    s = ResourceBaseService(db_session).compute_summary(erp)

    assert s.primary_normed_by_role == {}
    assert round(s.available_by_role["dev"], 1) == round(2 * 0.45 * QUARTER_NORM, 1)
```

И поменять ожидания в `test_summary_booking_cut_matches_daily_base`: E там — гость сценария A (основная B), поэтому правило A 50% к нему больше не применяется (решение 30.09):

```python
    emp = next(x for x in base.employees if x.employee_id == e.id)
    # E — гость A: правило A (50%) к нему не применяется; бронь B снимает 6 ч из 8.
    assert {d.date: d.hours for d in emp.days}[date(2026, 1, 5)] == 2.0
    assert s.booked_by_other_teams_by_role == {"developer": 6.0}
    assert s.available_by_role["developer"] == emp.total_hours
```

Докстринг теста: `"""Сводка режет бронь так же, как база по дням (гостю правила сценария не режут день)."""`.

- [ ] **Step 2: Убедиться, что падают**

Run: `py -3.10 -m pytest tests/services/test_resource_base_external.py -q`
Expected: FAIL — нет `primary_normed_by_role`; `test_summary_booking_cut_matches_daily_base` — 0.0 вместо 2.0.

- [ ] **Step 3: Реализация**

3a. Импорт в шапке `app/services/resource_base_service.py`:

```python
from app.services import normed_reserve as nr
```

3b. Поля `ResourceSummary` (после `ungrouped_employees`):

```python
    # Нормированные работы основной команды у гостей сценария (команда у них
    # не основная), кроме «Технических задач»: роль → часы. Вычтены из «На бэклог».
    primary_normed_by_role: dict[str, float] = field(default_factory=dict)
    # [{employee_id, display_name, hours}] — кому и сколько, для подсказки.
    primary_normed_people: list[dict] = field(default_factory=list)
```

3c. Метод класса (рядом с `_pool_share`):

```python
    def _guest_normed(
        self,
        team: str,
        employees: list[Employee],
        subtracted: list,
        year: Optional[int],
        quarter: int,
        start: date,
        end: date,
    ) -> tuple[set[str], dict[str, dict[date, float]]]:
        """Гости сценария (команда у них не основная) и нормированные работы
        их основной команды по дням — одна раскладка для базы и сводки."""
        guests = cto.guest_ids(self.db, team, start, end, [e.id for e in employees])
        if not guests or not year:
            return guests, {}
        return guests, nr.guest_normed_by_day(
            self.db,
            [e for e in employees if e.id in guests],
            [b for b in subtracted if b.employee_id in guests],
            year,
            quarter,
            start,
            end,
        )
```

3d. `compute`: брони — списком, гость без правил сценария, его нормы — к броням дня. Заменить блок `booked = cto.daily_totals(cto.subtractable(...))` на:

```python
        subtracted = cto.subtractable(
            cto.external_bookings(
                self.db,
                team=team,
                year=year,
                quarter=q,
                employee_ids=[e.id for e in employees],
                start=period_start,
                end=last_day,
            ),
            set(),
        )
        booked = cto.daily_totals(subtracted)
        # Гость (команда у него не основная): правила сценария день не режут,
        # его нормированные работы — основной команды, по дням как брони.
        guests, guest_normed = self._guest_normed(
            team, employees, subtracted, year, q, period_start, last_day
        )
```

и строку `pool_share = self._pool_share(scenario, self._personal_normed(...))` на:

```python
        personal = self._personal_normed([e.id for e in employees], year, q)
        personal.update({g: {} for g in guests})
        pool_share = self._pool_share(scenario, personal)
```

В цикле по дням:

```python
                taken = booked.get(e.id, {}).get(cur, 0.0) + guest_normed.get(e.id, {}).get(cur, 0.0)
```

3e. `compute_summary`: после `subtracted = cto.subtractable(bookings, set())` добавить вызов `_guest_normed`; после `personal_normed = ...` — `personal_normed.update({g: {} for g in guests})`; завести `primary_normed_by_emp: dict[str, float] = {}`. В цикле по сотруднику завести `normed_taken = 0.0` и `emp_gnormed = guest_normed.get(e.id, {})`; в цикле по дням заменить

```python
                        day_taken = min(emp_booked.get(cur, 0.0), norm * share)
                        taken += day_taken
```

на

```python
                        day_booked = min(emp_booked.get(cur, 0.0), norm * share)
                        day_normed = min(emp_gnormed.get(cur, 0.0), norm * share - day_booked)
                        day_taken = day_booked + day_normed
                        taken += day_booked
                        normed_taken += day_normed
```

(разрез по группам уже берёт `day_taken` — он теперь включает нормы гостя). После цикла: `primary_normed_by_emp[e.id] = round(normed_taken, 2)`.

После `lent_by_role = _by_role(lent_by_emp)`:

```python
        primary_normed_by_role = _by_role(primary_normed_by_emp)
```

В расчёте `available_by_role` вычесть и их:

```python
            available_by_role[role] = round(
                max(
                    0.0,
                    gross - mandatory_total - booked_by_role.get(role, 0.0)
                    - primary_normed_by_role.get(role, 0.0),
                ),
                2,
            )
```

В `ResourceSummary(...)`:

```python
            primary_normed_by_role=primary_normed_by_role,
            primary_normed_people=sorted(
                (
                    {"employee_id": eid, "display_name": emp_name[eid], "hours": h}
                    for eid, h in primary_normed_by_emp.items()
                    if h > 0
                ),
                key=lambda x: x["display_name"],
            ),
```

- [ ] **Step 4: Прогнать**

Run: `py -3.10 -m pytest tests/services/test_resource_base_external.py tests/services/test_personal_normed_scenario.py tests/test_resource_summary_subgroups.py tests/test_resource_base_service.py -q`
Expected: все зелёные.

- [ ] **Step 5: Коммит**

```bash
git add app/services/resource_base_service.py tests/services/test_resource_base_external.py
git commit -m "fix(planning): сценарий неосновной команды вычитает нормы основной у общего сотрудника"
```

---

### Task 3: Поля ответа и строка под таблицей сценария

**Files:**
- Modify: `app/api/endpoints/planning.py` (модель ответа сводки ~стр. 446, сборка ~стр. 2050)
- Modify: `frontend/src/types/api.ts` (~стр. 697), `frontend/src/components/planning/ScenarioResourceSummary.tsx` (~стр. 722–756)
- Test: `tests/services/test_resource_base_external.py`

- [ ] **Step 1: Падающий тест**

```python
def test_resource_summary_endpoint_returns_primary_normed(db_session):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    _p, _ivanov, _erp, blk = _guest_scenario(db_session)

    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        r = TestClient(app).get(f"/api/v1/planning/scenarios/{blk.id}/resource-summary")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200, r.text
    body = r.json()
    assert round(body["primary_normed_by_role"]["dev"], 1) == round(0.45 * QUARTER_NORM, 1)
    assert [x["display_name"] for x in body["primary_normed_people"]] == ["Пряничников"]
```

- [ ] **Step 2: Прогнать — FAIL** (`KeyError: 'primary_normed_by_role'`).

- [ ] **Step 3: API.** В модели ответа после `borrowed_by_other_teams_by_role`:

```python
    # Нормированные работы основной команды у общих сотрудников, для которых
    # команда сценария не основная (вычтены из «На бэклог»), и кому сколько.
    primary_normed_by_role: Dict[str, float] = {}
    primary_normed_people: List[Dict] = []
```

В сборке ответа после `borrowed_by_other_teams_by_role=...`:

```python
        primary_normed_by_role=summary.primary_normed_by_role,
        primary_normed_people=summary.primary_normed_people,
```

- [ ] **Step 4: Типы.** В `frontend/src/types/api.ts` после `borrowed_by_other_teams_by_role`:

```ts
  /** Нормированные работы основной команды у общих сотрудников (уже вычтены из «На бэклог»). */
  primary_normed_by_role?: Record<string, number>;
  primary_normed_people?: { employee_id: string; display_name: string; hours: number }[];
```

- [ ] **Step 5: Строка.** В `ScenarioResourceSummary.tsx` после `const borrowed = ...`:

```tsx
        const normed = byRole(summary.primary_normed_by_role);
        const normedWho = (summary.primary_normed_people ?? [])
          .map((p) => `${p.display_name} — ${Math.round(p.hours).toLocaleString('ru')} ч`)
          .join('\n');
        if (!booked && !borrowed && !normed) return null;
```

(заменив прежнее `if (!booked && !borrowed) return null;`), и после блока `{booked && (...)}`:

```tsx
            {normed && (
              <div title={normedWho}>
                Нормированные работы основной команды у общих сотрудников: {normed}. Эти часы уже
                вычтены из «На бэклог».
              </div>
            )}
```

- [ ] **Step 6: Проверки**

Run: `py -3.10 -m pytest tests/services/test_resource_base_external.py -q` → PASS.
Run (в `frontend/`): `npx tsc -b` → без ошибок; `npx eslint src/components/planning/ScenarioResourceSummary.tsx src/types/api.ts` → без замечаний.

- [ ] **Step 7: Коммит**

```bash
git add app/api/endpoints/planning.py frontend/src/types/api.ts frontend/src/components/planning/ScenarioResourceSummary.tsx tests/services/test_resource_base_external.py
git commit -m "feat(planning): строка о нормах основной команды у общих сотрудников в сценарии"
```

---

### Task 4: Справка, заметка, проверка на копии базы

**Files:**
- Modify: `docs/help/resource-planning.md` (раздел 3.10, пункт «**Сценарий:**»)
- Modify: `release_notes/drafts.json`

- [ ] **Step 1: Справка.** В конец пункта «**Сценарий:**» раздела 3.10 дописать:

```markdown
Если ваша команда у человека не основная, из «На бэклог» вычитаются ещё и нормированные работы его основной команды — те же, что в её «Загрузке по дням», кроме «Технических задач»: это время основная команда отдаёт на работу в других командах. Правила нормированных работ вашего сценария к такому человеку не применяются — его нормы задаёт основная команда. Под таблицей — строка «Нормированные работы основной команды у общих сотрудников», имена — в подсказке.
```

- [ ] **Step 2: Заметка** (`type: fix`, `section: scenarios`):
  - title: «Общий сотрудник в сценарии неосновной команды — без двойного счёта»
  - description: «В сценарии команды, которая у сотрудника не основная, из «На бэклог» теперь вычитаются нормированные работы его основной команды, кроме «Технических задач» — так же, как в «Загрузке по дням» ресурсного плана. Правила нормированных работ самого сценария к нему больше не применяются. Раньше вычитались только его задачи в основной команде, и доступных часов показывалось больше, чем есть: у разработчика ERP в «Блоке Компетенций» было 362 ч вместо примерно 132 ч.»

- [ ] **Step 3: Полный прогон** (без собранного интерфейса в `app/static`):

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py -p no:cacheprovider`
Expected: всё зелёное.

- [ ] **Step 4: Проверка на копии рабочей базы** (стенд 8121): сценарий «Блока Компетенций» Q4 `44854d40-1877-41cd-aae4-084494287bf8`, `GET /planning/scenarios/{id}/resource-summary` → у разработчиков `primary_normed_by_role` ≈ 230 ч, Пряничников в `primary_normed_people`; «На бэклог» Пряничникова в базе (`/resource`) ≈ 132 ч. Сценарий ERP ТУ `90521904-…` — без изменений (`primary_normed_by_role` пусто). Скриншот строки под таблицей.

- [ ] **Step 5: Коммит**

```bash
git add docs/help/resource-planning.md release_notes/drafts.json
git commit -m "docs(help): нормы основной команды у общих сотрудников в сценарии"
```
