# Виджет «Баланс часов команды» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дашборд-виджет накопительного баланса часов (переработки/автоотгулы) по сотрудникам команды с 1 января текущего года + drill-in модалка с календарём по дням.

**Architecture:** Тонкий REST: `GET /api/v1/dashboard/hours-balance` (сводка по команде) + `GET /api/v1/dashboard/hours-balance/{employee_id}` (детализация). Сервис `HoursBalanceService` делает bulk-загрузку worklogs/absences + использует `ProductionCalendarService`. На фронте — карточный виджет + AntD Modal с 6 мини-календарями.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 на бэке. React 19 + TS + AntD 6 + TanStack Query на фронте. Тесты — pytest + Playwright.

**Spec:** [docs/superpowers/specs/2026-06-05-hours-balance-widget-design.md](../specs/2026-06-05-hours-balance-widget-design.md)

---

## File Structure

**Создаются:**
- `app/schemas/hours_balance.py` — Pydantic response models
- `app/services/hours_balance_service.py` — domain logic
- `tests/services/test_hours_balance_service.py` — unit tests
- `tests/api/test_dashboard_hours_balance.py` — integration tests
- `frontend/src/hooks/useHoursBalance.ts` — TanStack Query hooks
- `frontend/src/components/dashboard/HoursBalanceWidget.tsx` — widget component
- `frontend/src/components/dashboard/HoursBalanceModal.tsx` — modal component
- `e2e/hours-balance.spec.ts` — Playwright e2e

**Меняются:**
- `app/api/endpoints/analytics.py` — два эндпоинта добавляются (паттерн dashboard/*)
- `frontend/src/types/api.ts` — добавить типы ответа
- `frontend/src/pages/DashboardPage.tsx` — вставить 4-й виджет

**Не трогаем:** capacity_service.py, production_calendar_service.py (переиспользуем как есть).

---

## Task 1: Pydantic schemas

**Files:**
- Create: `app/schemas/hours_balance.py`

- [ ] **Step 1: Создать файл схем**

Содержимое `app/schemas/hours_balance.py`:

```python
"""Pydantic схемы виджета баланса часов."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


DayKind = Literal["norm", "overtime", "skip", "absence", "holiday"]


class PeriodInfo(BaseModel):
    from_: date
    to: date
    working_days: int

    model_config = ConfigDict(populate_by_name=True)

    def model_dump(self, **kwargs):  # alias from_ → from in output
        d = super().model_dump(**kwargs)
        if "from_" in d:
            d["from"] = d.pop("from_")
        return d


class TeamSummary(BaseModel):
    employees_count: int
    overtime_hours: float
    skip_hours: float
    net_balance: float


class EmployeeBalance(BaseModel):
    id: str
    full_name: str
    role_label: str | None = None
    avatar_url: str | None = None
    initials: str
    balance_hours: float
    overtime_days: int
    overtime_hours: float
    skip_days: int
    skip_hours: float
    sparkline: list[float]


class HoursBalanceResponse(BaseModel):
    period: PeriodInfo
    team_summary: TeamSummary
    employees: list[EmployeeBalance]


class MonthlySummary(BaseModel):
    year: int
    month: int
    label: str
    balance: float
    overtime_days: int
    skip_days: int


class DailyEntry(BaseModel):
    day: date
    norm: float
    fact: float
    delta: float
    kind: DayKind
    absence_label: str | None = None


class EmployeeInfo(BaseModel):
    id: str
    full_name: str
    role_label: str | None = None
    team_label: str | None = None
    avatar_url: str | None = None
    initials: str


class EmployeeKpi(BaseModel):
    balance_hours: float
    overtime_days: int
    overtime_hours: float
    skip_days: int
    skip_hours: float


class EmployeeBalanceDetail(BaseModel):
    employee: EmployeeInfo
    period: PeriodInfo
    kpi: EmployeeKpi
    monthly: list[MonthlySummary]
    days: list[DailyEntry]
```

- [ ] **Step 2: Проверить импорт схемы (smoke)**

Run: `py -3.10 -c "from app.schemas.hours_balance import HoursBalanceResponse; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/hours_balance.py
git commit -m "feat(hours-balance): pydantic schemas

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Сервис — каркас + норма с учётом absence

**Files:**
- Create: `app/services/hours_balance_service.py`
- Create: `tests/services/test_hours_balance_service.py`

- [ ] **Step 1: Создать каркас сервиса**

Содержимое `app/services/hours_balance_service.py`:

```python
"""Сервис расчёта баланса часов: переработки и автоотгулы.

Норма дня = производственный календарь − официальные отсутствия (кроме «Отгула»).
Дельта дня = факт − эффективная норма. Накопительный баланс по периоду.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.worklog import Worklog
from app.services.production_calendar_service import ProductionCalendarService

logger = logging.getLogger(__name__)

DAY_OFF_CODE = "day_off"
CLASS_THRESHOLD_PCT = 0.10  # ±10% от нормы — считается «норма»

MONTH_LABELS_RU = [
    "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
]


@dataclass
class DayCalc:
    day: date
    norm: float
    fact: float
    delta: float
    kind: str  # norm | overtime | skip | absence | holiday
    absence_label: Optional[str] = None


class HoursBalanceService:
    def __init__(
        self,
        db: Session,
        production_calendar: Optional[ProductionCalendarService] = None,
    ) -> None:
        self.db = db
        self.production_calendar = production_calendar or ProductionCalendarService(db)
        self._warn_if_day_off_missing()

    def _warn_if_day_off_missing(self) -> None:
        exists = (
            self.db.query(AbsenceReason)
            .filter(AbsenceReason.code == DAY_OFF_CODE)
            .first()
        )
        if exists is None:
            logger.warning(
                "AbsenceReason code='%s' not found — автоотгулы детектиться не будут.",
                DAY_OFF_CODE,
            )

    def _absence_map(
        self,
        employee_ids: list[str],
        from_: date,
        to_: date,
    ) -> dict[tuple[str, date], str]:
        """Карта (employee_id, day) -> reason_label для absences кроме day_off."""
        if not employee_ids:
            return {}
        rows = (
            self.db.query(Absence, AbsenceReason)
            .join(AbsenceReason, Absence.reason_id == AbsenceReason.id)
            .filter(
                Absence.employee_id.in_(employee_ids),
                Absence.end_date >= from_,
                Absence.start_date <= to_,
                AbsenceReason.code != DAY_OFF_CODE,
            )
            .all()
        )
        result: dict[tuple[str, date], str] = {}
        for absence, reason in rows:
            cur = max(absence.start_date, from_)
            end = min(absence.end_date, to_)
            while cur <= end:
                result[(absence.employee_id, cur)] = reason.label
                cur += timedelta(days=1)
        return result

    def _worklog_map(
        self,
        employee_ids: list[str],
        from_: date,
        to_: date,
    ) -> dict[tuple[str, date], float]:
        """Карта (employee_id, day) -> sum(time_spent_hours)."""
        if not employee_ids:
            return {}
        from app.models.worklog import Worklog as W
        day_col = func.date(W.date_started).label("day")
        rows = (
            self.db.query(
                W.employee_id,
                day_col,
                func.sum(W.time_spent_hours).label("hours"),
            )
            .filter(
                W.employee_id.in_(employee_ids),
                W.date_started >= from_,
                W.date_started < to_ + timedelta(days=1),
            )
            .group_by(W.employee_id, day_col)
            .all()
        )
        result: dict[tuple[str, date], float] = {}
        for emp_id, day_val, hours in rows:
            # SQLite func.date returns string; coerce
            if isinstance(day_val, str):
                day_val = date.fromisoformat(day_val)
            result[(emp_id, day_val)] = float(hours or 0)
        return result
```

- [ ] **Step 2: Создать тестовую инфру**

Содержимое `tests/services/test_hours_balance_service.py`:

```python
"""Тесты HoursBalanceService."""

from datetime import date, datetime, timedelta

import pytest

from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.models.employee import Employee
from app.models.worklog import Worklog
from app.services.hours_balance_service import HoursBalanceService


@pytest.fixture
def emp(db_session):
    e = Employee(
        id="emp-1",
        full_name="Тестов Т.",
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    return e


@pytest.fixture
def vacation_reason(db_session):
    r = AbsenceReason(
        id="r-vacation",
        code="vacation",
        label="Отпуск",
        is_planned=True,
        is_active=True,
    )
    db_session.add(r)
    db_session.commit()
    return r


@pytest.fixture
def day_off_reason(db_session):
    r = AbsenceReason(
        id="r-day-off",
        code="day_off",
        label="Отгул",
        is_planned=False,
        is_active=True,
    )
    db_session.add(r)
    db_session.commit()
    return r
```

- [ ] **Step 3: Запустить smoke — модуль импортится, фикстуры читаются**

Run: `py -3.10 -m pytest tests/services/test_hours_balance_service.py --collect-only`
Expected: 0 tests collected, no errors.

- [ ] **Step 4: Commit**

```bash
git add app/services/hours_balance_service.py tests/services/test_hours_balance_service.py
git commit -m "feat(hours-balance): service skeleton + test fixtures

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Сервис — основная функция compute_team

**Files:**
- Modify: `app/services/hours_balance_service.py`
- Modify: `tests/services/test_hours_balance_service.py`

- [ ] **Step 1: Написать тест — баланс = 0 при отсутствии данных**

Добавить в `tests/services/test_hours_balance_service.py`:

```python
def test_empty_employees_returns_empty(db_session):
    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[],
        from_=date(2026, 1, 1),
        to_=date(2026, 1, 31),
    )
    assert result.employees == []
    assert result.team_summary.employees_count == 0
    assert result.team_summary.net_balance == 0


def test_employee_full_norm_balance_zero(db_session, emp):
    """Сотрудник отработал ровно норму каждый рабочий день → баланс 0."""
    # Январь 2026: рабочие дни (без 1-8 праздников) = 9..31 минус выходные
    for day_num in range(9, 32):
        d = date(2026, 1, day_num)
        if d.weekday() >= 5:
            continue
        wl = Worklog(
            id=f"wl-{day_num}",
            jira_worklog_id=f"j-{day_num}",
            issue_id=None,
            employee_id=emp.id,
            time_spent_hours=8.0,
            date_started=datetime(2026, 1, day_num, 10, 0),
        )
        db_session.add(wl)
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 1),
        to_=date(2026, 1, 31),
    )
    assert len(result.employees) == 1
    bal = result.employees[0]
    assert bal.balance_hours == pytest.approx(0, abs=1)
    assert bal.overtime_days == 0
    assert bal.skip_days == 0
```

- [ ] **Step 2: Запустить — должны упасть на missing compute_team**

Run: `py -3.10 -m pytest tests/services/test_hours_balance_service.py::test_empty_employees_returns_empty -v`
Expected: FAIL — AttributeError `'HoursBalanceService' has no attribute 'compute_team'`.

- [ ] **Step 3: Реализовать compute_team**

Дописать в `app/services/hours_balance_service.py` (перед классом или внутри):

```python
@dataclass
class EmployeeBalanceResult:
    id: str
    full_name: str
    role_label: Optional[str]
    avatar_url: Optional[str]
    initials: str
    balance_hours: float
    overtime_days: int
    overtime_hours: float
    skip_days: int
    skip_hours: float
    sparkline: list[float]


@dataclass
class TeamBalanceResult:
    period_from: date
    period_to: date
    working_days: int
    team_summary_overtime_hours: float
    team_summary_skip_hours: float
    team_summary_net_balance: float
    employees: list[EmployeeBalanceResult]
```

И метод (в классе `HoursBalanceService`):

```python
    def compute_team(
        self,
        employee_ids: list[str],
        from_: date,
        to_: date,
    ) -> TeamBalanceResult:
        if not employee_ids:
            return TeamBalanceResult(
                period_from=from_,
                period_to=to_,
                working_days=0,
                team_summary_overtime_hours=0.0,
                team_summary_skip_hours=0.0,
                team_summary_net_balance=0.0,
                employees=[],
            )

        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(employee_ids))
            .all()
        )
        if not employees:
            return TeamBalanceResult(
                period_from=from_,
                period_to=to_,
                working_days=0,
                team_summary_overtime_hours=0.0,
                team_summary_skip_hours=0.0,
                team_summary_net_balance=0.0,
                employees=[],
            )

        cal_hours = self.production_calendar.hours_in_range_map(from_, to_)
        absences = self._absence_map(employee_ids, from_, to_)
        worklogs = self._worklog_map(employee_ids, from_, to_)

        working_days = 0
        days_iter: list[date] = []
        cur = from_
        while cur <= to_:
            ch = cal_hours.get(cur)
            is_workday = ch is not None and ch > 0 if ch is not None else (cur.weekday() < 5)
            if is_workday:
                working_days += 1
                days_iter.append(cur)
            cur += timedelta(days=1)

        emp_results: list[EmployeeBalanceResult] = []
        team_overtime = 0.0
        team_skip = 0.0
        for e in employees:
            balance = 0.0
            overtime_days = 0
            overtime_hours = 0.0
            skip_days = 0
            skip_hours = 0.0
            sparkline: list[float] = []
            for d in days_iter:
                cal = cal_hours.get(d)
                base_norm = cal if cal is not None else (8.0 if d.weekday() < 5 else 0.0)
                absence_label = absences.get((e.id, d))
                # absence label means full-day absence: norm_eff = 0
                norm_eff = 0.0 if absence_label else max(0.0, base_norm)
                fact = worklogs.get((e.id, d), 0.0)
                if norm_eff == 0 and fact == 0:
                    sparkline.append(balance)
                    continue
                delta = fact - norm_eff
                balance += delta
                if delta > 0 and (norm_eff == 0 or delta > norm_eff * CLASS_THRESHOLD_PCT):
                    overtime_days += 1
                    overtime_hours += delta
                elif delta < 0 and abs(delta) > norm_eff * CLASS_THRESHOLD_PCT:
                    skip_days += 1
                    skip_hours += delta  # negative
                sparkline.append(balance)
            initials = "".join(p[0] for p in e.full_name.split()[:2]).upper() or "?"
            emp_results.append(EmployeeBalanceResult(
                id=e.id,
                full_name=e.full_name,
                role_label=getattr(getattr(e, "role", None), "label", None),
                avatar_url=getattr(e, "avatar_url", None),
                initials=initials,
                balance_hours=round(balance, 1),
                overtime_days=overtime_days,
                overtime_hours=round(overtime_hours, 1),
                skip_days=skip_days,
                skip_hours=round(skip_hours, 1),
                sparkline=[round(v, 1) for v in sparkline],
            ))
            team_overtime += overtime_hours
            team_skip += skip_hours

        return TeamBalanceResult(
            period_from=from_,
            period_to=to_,
            working_days=working_days,
            team_summary_overtime_hours=round(team_overtime, 1),
            team_summary_skip_hours=round(team_skip, 1),
            team_summary_net_balance=round(team_overtime + team_skip, 1),
            employees=emp_results,
        )
```

- [ ] **Step 4: Запустить тесты — оба зелёные**

Run: `py -3.10 -m pytest tests/services/test_hours_balance_service.py -v`
Expected: PASS оба.

- [ ] **Step 5: Commit**

```bash
git add app/services/hours_balance_service.py tests/services/test_hours_balance_service.py
git commit -m "feat(hours-balance): compute_team основная функция

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Сервис — пограничные случаи

**Files:**
- Modify: `tests/services/test_hours_balance_service.py`
- Modify: `app/services/hours_balance_service.py` (если потребуется доработка)

- [ ] **Step 1: Тест — отпуск не считается отгулом**

Добавить:

```python
def test_vacation_not_counted_as_skip(db_session, emp, vacation_reason):
    """Сотрудник в отпуске 12-16 января → ни отгулов, ни переработок."""
    db_session.add(Absence(
        id="a-1",
        employee_id=emp.id,
        start_date=date(2026, 1, 12),
        end_date=date(2026, 1, 16),
        reason_id=vacation_reason.id,
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 12),
        to_=date(2026, 1, 16),
    )
    bal = result.employees[0]
    assert bal.skip_days == 0
    assert bal.overtime_days == 0
    assert bal.balance_hours == 0
```

- [ ] **Step 2: Тест — day_off reason игнорируется**

```python
def test_day_off_reason_does_not_zero_norm(db_session, emp, day_off_reason):
    """Если у сотрудника absence с reason day_off, норма НЕ обнуляется.

    Тогда отсутствие worklog → детектится как автоотгул.
    """
    db_session.add(Absence(
        id="a-d",
        employee_id=emp.id,
        start_date=date(2026, 1, 13),
        end_date=date(2026, 1, 13),
        reason_id=day_off_reason.id,
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 13),
        to_=date(2026, 1, 13),
    )
    bal = result.employees[0]
    # 13 янв 2026 — вторник, норма 8ч, факт 0 → -8ч скип
    assert bal.skip_days == 1
    assert bal.skip_hours == pytest.approx(-8.0)
```

- [ ] **Step 3: Тест — переработка в выходной**

```python
def test_weekend_work_counted_as_overtime(db_session, emp):
    """Работа в субботу (норма 0) → +часы переработки."""
    db_session.add(Worklog(
        id="wl-sat",
        jira_worklog_id="j-sat",
        issue_id=None,
        employee_id=emp.id,
        time_spent_hours=4.0,
        date_started=datetime(2026, 1, 17, 12, 0),  # суббота
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 17),
        to_=date(2026, 1, 17),
    )
    bal = result.employees[0]
    assert bal.overtime_days == 1
    assert bal.overtime_hours == pytest.approx(4.0)
    assert bal.balance_hours == pytest.approx(4.0)
```

- [ ] **Step 4: Тест — порог классификации ±10%**

```python
def test_small_deviation_within_threshold_is_norm(db_session, emp):
    """Норма 8ч, факт 7.5ч → недодельта 0.5ч (6.25% < 10%) → не скип."""
    db_session.add(Worklog(
        id="wl-1",
        jira_worklog_id="j-1",
        issue_id=None,
        employee_id=emp.id,
        time_spent_hours=7.5,
        date_started=datetime(2026, 1, 13, 10, 0),
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 13),
        to_=date(2026, 1, 13),
    )
    bal = result.employees[0]
    assert bal.skip_days == 0
    assert bal.overtime_days == 0
    # balance считается всё равно (это для KPI)
    assert bal.balance_hours == pytest.approx(-0.5)
```

- [ ] **Step 5: Тест — спарклайн нарастающим итогом**

```python
def test_sparkline_is_cumulative(db_session, emp):
    """Каждый рабочий день +1ч → спарклайн монотонно растёт."""
    for day_num in range(12, 17):
        d = date(2026, 1, day_num)
        if d.weekday() >= 5:
            continue
        db_session.add(Worklog(
            id=f"wl-{day_num}",
            jira_worklog_id=f"j-{day_num}",
            issue_id=None,
            employee_id=emp.id,
            time_spent_hours=9.0,  # +1ч сверх нормы
            date_started=datetime(2026, 1, day_num, 10, 0),
        ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 12),
        to_=date(2026, 1, 16),
    )
    sp = result.employees[0].sparkline
    # 12-16 янв 2026 = пн-пт = 5 рабочих дней
    assert len(sp) == 5
    for i in range(1, len(sp)):
        assert sp[i] >= sp[i - 1]  # монотонность
    assert sp[-1] == pytest.approx(5.0)
```

- [ ] **Step 6: Запустить все**

Run: `py -3.10 -m pytest tests/services/test_hours_balance_service.py -v`
Expected: все PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/services/test_hours_balance_service.py app/services/hours_balance_service.py
git commit -m "test(hours-balance): edge cases — vacation/day_off/weekend/threshold

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Сервис — compute_employee (drill-in)

**Files:**
- Modify: `app/services/hours_balance_service.py`
- Modify: `tests/services/test_hours_balance_service.py`

- [ ] **Step 1: Тест — компонент возвращает days и monthly**

```python
def test_compute_employee_returns_days_and_monthly(db_session, emp):
    """Drill-in возвращает посуточный массив + месячные сводки."""
    db_session.add(Worklog(
        id="wl-1",
        jira_worklog_id="j-1",
        issue_id=None,
        employee_id=emp.id,
        time_spent_hours=11.0,
        date_started=datetime(2026, 1, 13, 10, 0),  # вт +3ч
    ))
    db_session.add(Worklog(
        id="wl-2",
        jira_worklog_id="j-2",
        issue_id=None,
        employee_id=emp.id,
        time_spent_hours=5.0,
        date_started=datetime(2026, 2, 3, 10, 0),  # вт -3ч
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    detail = svc.compute_employee(
        employee_id=emp.id,
        from_=date(2026, 1, 1),
        to_=date(2026, 2, 28),
    )
    assert detail.employee_id == emp.id
    assert detail.balance_hours == pytest.approx(0.0, abs=0.1)  # +3 -3
    assert detail.overtime_days == 1
    assert detail.skip_days == 1
    assert len(detail.monthly) == 2
    jan = next(m for m in detail.monthly if m.month == 1)
    assert jan.balance == pytest.approx(3.0)
    assert jan.overtime_days == 1
    feb = next(m for m in detail.monthly if m.month == 2)
    assert feb.balance == pytest.approx(-3.0)
    assert feb.skip_days == 1
    # days: рабочие дни + дни с absence/holiday
    overtime_day = next(d for d in detail.days if d.day == date(2026, 1, 13))
    assert overtime_day.kind == "overtime"
    assert overtime_day.delta == pytest.approx(3.0)
```

- [ ] **Step 2: Реализовать compute_employee**

Добавить в `HoursBalanceService`:

```python
    def compute_employee(
        self,
        employee_id: str,
        from_: date,
        to_: date,
    ) -> "EmployeeDetailResult":
        e = self.db.get(Employee, employee_id)
        if e is None:
            raise ValueError(f"Employee {employee_id} not found")

        cal_hours = self.production_calendar.hours_in_range_map(from_, to_)
        absences = self._absence_map([employee_id], from_, to_)
        worklogs = self._worklog_map([employee_id], from_, to_)

        days: list[DayCalc] = []
        balance = 0.0
        overtime_days = 0
        overtime_hours = 0.0
        skip_days = 0
        skip_hours = 0.0
        monthly_acc: dict[tuple[int, int], dict] = defaultdict(
            lambda: {"balance": 0.0, "overtime_days": 0, "skip_days": 0}
        )

        cur = from_
        while cur <= to_:
            cal = cal_hours.get(cur)
            base_norm = cal if cal is not None else (8.0 if cur.weekday() < 5 else 0.0)
            absence_label = absences.get((employee_id, cur))
            fact = worklogs.get((employee_id, cur), 0.0)

            if absence_label:
                kind = "absence"
                days.append(DayCalc(cur, 0.0, fact, 0.0, kind, absence_label))
                cur += timedelta(days=1)
                continue
            if base_norm == 0:
                if fact > 0:
                    # work on holiday/weekend counts as overtime
                    delta = fact
                    balance += delta
                    overtime_days += 1
                    overtime_hours += delta
                    monthly_acc[(cur.year, cur.month)]["balance"] += delta
                    monthly_acc[(cur.year, cur.month)]["overtime_days"] += 1
                    days.append(DayCalc(cur, 0.0, fact, delta, "overtime"))
                else:
                    days.append(DayCalc(cur, 0.0, 0.0, 0.0, "holiday"))
                cur += timedelta(days=1)
                continue

            delta = fact - base_norm
            balance += delta
            month_key = (cur.year, cur.month)
            monthly_acc[month_key]["balance"] += delta
            if delta > base_norm * CLASS_THRESHOLD_PCT:
                kind = "overtime"
                overtime_days += 1
                overtime_hours += delta
                monthly_acc[month_key]["overtime_days"] += 1
            elif -delta > base_norm * CLASS_THRESHOLD_PCT:
                kind = "skip"
                skip_days += 1
                skip_hours += delta
                monthly_acc[month_key]["skip_days"] += 1
            else:
                kind = "norm"
            days.append(DayCalc(cur, base_norm, fact, delta, kind))
            cur += timedelta(days=1)

        monthly = []
        for (y, m), acc in sorted(monthly_acc.items()):
            monthly.append(MonthlySummaryResult(
                year=y,
                month=m,
                label=MONTH_LABELS_RU[m - 1],
                balance=round(acc["balance"], 1),
                overtime_days=acc["overtime_days"],
                skip_days=acc["skip_days"],
            ))

        initials = "".join(p[0] for p in e.full_name.split()[:2]).upper() or "?"
        return EmployeeDetailResult(
            employee_id=e.id,
            full_name=e.full_name,
            role_label=getattr(getattr(e, "role", None), "label", None),
            team_label=getattr(e, "team", None),
            initials=initials,
            avatar_url=getattr(e, "avatar_url", None),
            period_from=from_,
            period_to=to_,
            balance_hours=round(balance, 1),
            overtime_days=overtime_days,
            overtime_hours=round(overtime_hours, 1),
            skip_days=skip_days,
            skip_hours=round(skip_hours, 1),
            monthly=monthly,
            days=days,
        )
```

И добавить dataclass-результаты выше:

```python
@dataclass
class MonthlySummaryResult:
    year: int
    month: int
    label: str
    balance: float
    overtime_days: int
    skip_days: int


@dataclass
class EmployeeDetailResult:
    employee_id: str
    full_name: str
    role_label: Optional[str]
    team_label: Optional[str]
    initials: str
    avatar_url: Optional[str]
    period_from: date
    period_to: date
    balance_hours: float
    overtime_days: int
    overtime_hours: float
    skip_days: int
    skip_hours: float
    monthly: list[MonthlySummaryResult]
    days: list[DayCalc]
```

- [ ] **Step 3: Запустить**

Run: `py -3.10 -m pytest tests/services/test_hours_balance_service.py -v`
Expected: все PASS, новый тоже зелёный.

- [ ] **Step 4: Commit**

```bash
git add app/services/hours_balance_service.py tests/services/test_hours_balance_service.py
git commit -m "feat(hours-balance): compute_employee для drill-in

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: API эндпоинт сводки + интеграционный тест

**Files:**
- Modify: `app/api/endpoints/analytics.py`
- Create: `tests/api/test_dashboard_hours_balance.py`

- [ ] **Step 1: Написать failing integration test**

Содержимое `tests/api/test_dashboard_hours_balance.py`:

```python
"""Integration: /api/v1/dashboard/hours-balance."""

from datetime import date, datetime

from fastapi.testclient import TestClient


def test_hours_balance_returns_200_on_empty(client: TestClient, auth_headers):
    """Empty teams + no employees → 200 с пустым массивом."""
    resp = client.get(
        "/api/v1/dashboard/hours-balance",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "period" in data
    assert "team_summary" in data
    assert isinstance(data["employees"], list)


def test_hours_balance_default_period_from_jan_1(client: TestClient, auth_headers):
    """Без query period начинается с 1 января текущего года."""
    resp = client.get(
        "/api/v1/dashboard/hours-balance",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    today = date.today()
    assert data["period"]["from"] == f"{today.year}-01-01"
    assert data["period"]["to"] == today.isoformat()
```

- [ ] **Step 2: Запустить — должен упасть на 404 endpoint not found**

Run: `py -3.10 -m pytest tests/api/test_dashboard_hours_balance.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Добавить эндпоинт**

В `app/api/endpoints/analytics.py` после блока dashboard добавить (импорты в шапке файла — `from app.services.hours_balance_service import HoursBalanceService`, `from app.schemas.hours_balance import HoursBalanceResponse, EmployeeBalanceDetail, PeriodInfo, TeamSummary, EmployeeBalance, EmployeeInfo, EmployeeKpi, MonthlySummary, DailyEntry`, `from app.models.employee import Employee`, `from app.models.employee_team import EmployeeTeam`):

```python
@router.get("/dashboard/hours-balance", response_model=HoursBalanceResponse)
def dashboard_hours_balance(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = Query(None),
    teams: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Виджет баланса часов: накопительные переработки/автоотгулы по команде."""
    today = date.today()
    from_ = from_ or date(today.year, 1, 1)
    to = to or today
    if from_ > to:
        raise HTTPException(status_code=422, detail="from must be <= to")

    team_ids = parse_teams_csv(teams)
    q = db.query(Employee).filter(Employee.is_active == True)  # noqa: E712
    if team_ids:
        q = q.join(EmployeeTeam, Employee.id == EmployeeTeam.employee_id).filter(
            EmployeeTeam.team.in_(team_ids)
        ).distinct()
    employees = q.all()
    employee_ids = [e.id for e in employees]

    svc = HoursBalanceService(db)
    res = svc.compute_team(employee_ids=employee_ids, from_=from_, to_=to)

    return HoursBalanceResponse(
        period=PeriodInfo(
            from_=res.period_from,
            to=res.period_to,
            working_days=res.working_days,
        ),
        team_summary=TeamSummary(
            employees_count=len(res.employees),
            overtime_hours=res.team_summary_overtime_hours,
            skip_hours=res.team_summary_skip_hours,
            net_balance=res.team_summary_net_balance,
        ),
        employees=[
            EmployeeBalance(
                id=b.id,
                full_name=b.full_name,
                role_label=b.role_label,
                avatar_url=b.avatar_url,
                initials=b.initials,
                balance_hours=b.balance_hours,
                overtime_days=b.overtime_days,
                overtime_hours=b.overtime_hours,
                skip_days=b.skip_days,
                skip_hours=b.skip_hours,
                sparkline=b.sparkline,
            )
            for b in res.employees
        ],
    )
```

- [ ] **Step 4: Запустить тесты**

Run: `py -3.10 -m pytest tests/api/test_dashboard_hours_balance.py -v`
Expected: PASS оба.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/analytics.py tests/api/test_dashboard_hours_balance.py
git commit -m "feat(hours-balance): эндпоинт сводки /dashboard/hours-balance

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: API drill-in эндпоинт + интеграционные тесты

**Files:**
- Modify: `app/api/endpoints/analytics.py`
- Modify: `tests/api/test_dashboard_hours_balance.py`

- [ ] **Step 1: Тест 404 на несуществующий id**

```python
def test_drill_in_404_on_missing_employee(client: TestClient, auth_headers):
    resp = client.get(
        "/api/v1/dashboard/hours-balance/no-such-id",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_drill_in_returns_kpi_monthly_days(
    client: TestClient,
    auth_headers,
    db_session,
):
    """Создаём сотрудника + 1 ворклог → проверяем shape ответа."""
    from app.models.employee import Employee
    from app.models.worklog import Worklog
    db_session.add(Employee(id="emp-drill", full_name="Дрилл Д.", is_active=True))
    db_session.add(Worklog(
        id="wl-d",
        jira_worklog_id="j-d",
        issue_id=None,
        employee_id="emp-drill",
        time_spent_hours=10.0,
        date_started=datetime(2026, 2, 3, 10, 0),
    ))
    db_session.commit()

    resp = client.get(
        "/api/v1/dashboard/hours-balance/emp-drill",
        params={"from": "2026-01-01", "to": "2026-02-28"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["employee"]["id"] == "emp-drill"
    assert data["employee"]["full_name"] == "Дрилл Д."
    assert "kpi" in data
    assert isinstance(data["monthly"], list)
    assert isinstance(data["days"], list)
    feb = next(m for m in data["monthly"] if m["month"] == 2)
    assert feb["overtime_days"] >= 1
```

- [ ] **Step 2: Запустить — должны упасть на 404 эндпоинт not registered**

Run: `py -3.10 -m pytest tests/api/test_dashboard_hours_balance.py -v`
Expected: первый тест возможно даст 404 от Starlette (что и ожидается), но второй точно упадёт.

- [ ] **Step 3: Реализовать эндпоинт**

В `app/api/endpoints/analytics.py`:

```python
@router.get(
    "/dashboard/hours-balance/{employee_id}",
    response_model=EmployeeBalanceDetail,
)
def dashboard_hours_balance_detail(
    employee_id: str,
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Drill-in: посуточная развёртка по одному сотруднику + помесячная сводка."""
    today = date.today()
    from_ = from_ or date(today.year, 1, 1)
    to = to or today
    if from_ > to:
        raise HTTPException(status_code=422, detail="from must be <= to")

    svc = HoursBalanceService(db)
    try:
        detail = svc.compute_employee(
            employee_id=employee_id, from_=from_, to_=to,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return EmployeeBalanceDetail(
        employee=EmployeeInfo(
            id=detail.employee_id,
            full_name=detail.full_name,
            role_label=detail.role_label,
            team_label=detail.team_label,
            avatar_url=detail.avatar_url,
            initials=detail.initials,
        ),
        period=PeriodInfo(
            from_=detail.period_from,
            to=detail.period_to,
            working_days=sum(1 for d in detail.days if d.kind != "holiday"),
        ),
        kpi=EmployeeKpi(
            balance_hours=detail.balance_hours,
            overtime_days=detail.overtime_days,
            overtime_hours=detail.overtime_hours,
            skip_days=detail.skip_days,
            skip_hours=detail.skip_hours,
        ),
        monthly=[
            MonthlySummary(
                year=m.year,
                month=m.month,
                label=m.label,
                balance=m.balance,
                overtime_days=m.overtime_days,
                skip_days=m.skip_days,
            )
            for m in detail.monthly
        ],
        days=[
            DailyEntry(
                day=d.day,
                norm=d.norm,
                fact=d.fact,
                delta=round(d.delta, 1),
                kind=d.kind,  # type: ignore
                absence_label=d.absence_label,
            )
            for d in detail.days
        ],
    )
```

- [ ] **Step 4: Прогнать**

Run: `py -3.10 -m pytest tests/api/test_dashboard_hours_balance.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Прогнать весь suite — не сломали ничего**

Run: `py -3.10 -m pytest tests/ -x`
Expected: All PASS (учитывая известный test_sync_service флаки из memory — игнор если он там и был).

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/analytics.py tests/api/test_dashboard_hours_balance.py
git commit -m "feat(hours-balance): drill-in /dashboard/hours-balance/{employee_id}

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Frontend — типы и хук

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/hooks/useHoursBalance.ts`

- [ ] **Step 1: Добавить типы в api.ts**

В конец `frontend/src/types/api.ts`:

```ts
// === Dashboard Hours Balance ===

export type DayKind = 'norm' | 'overtime' | 'skip' | 'absence' | 'holiday';

export interface HoursBalancePeriod {
  from: string;
  to: string;
  working_days: number;
}

export interface HoursBalanceTeamSummary {
  employees_count: number;
  overtime_hours: number;
  skip_hours: number;
  net_balance: number;
}

export interface HoursBalanceEmployee {
  id: string;
  full_name: string;
  role_label: string | null;
  avatar_url: string | null;
  initials: string;
  balance_hours: number;
  overtime_days: number;
  overtime_hours: number;
  skip_days: number;
  skip_hours: number;
  sparkline: number[];
}

export interface HoursBalanceResponse {
  period: HoursBalancePeriod;
  team_summary: HoursBalanceTeamSummary;
  employees: HoursBalanceEmployee[];
}

export interface HoursBalanceMonthlySummary {
  year: number;
  month: number;
  label: string;
  balance: number;
  overtime_days: number;
  skip_days: number;
}

export interface HoursBalanceDailyEntry {
  day: string;
  norm: number;
  fact: number;
  delta: number;
  kind: DayKind;
  absence_label: string | null;
}

export interface HoursBalanceEmployeeInfo {
  id: string;
  full_name: string;
  role_label: string | null;
  team_label: string | null;
  avatar_url: string | null;
  initials: string;
}

export interface HoursBalanceEmployeeKpi {
  balance_hours: number;
  overtime_days: number;
  overtime_hours: number;
  skip_days: number;
  skip_hours: number;
}

export interface HoursBalanceDetailResponse {
  employee: HoursBalanceEmployeeInfo;
  period: HoursBalancePeriod;
  kpi: HoursBalanceEmployeeKpi;
  monthly: HoursBalanceMonthlySummary[];
  days: HoursBalanceDailyEntry[];
}
```

- [ ] **Step 2: Создать хук**

Содержимое `frontend/src/hooks/useHoursBalance.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';
import type {
  HoursBalanceResponse,
  HoursBalanceDetailResponse,
} from '../types/api';

export function useHoursBalance() {
  const { selectedTeams } = useGlobalTeamFilter();
  return useQuery<HoursBalanceResponse>({
    queryKey: ['dashboard', 'hours-balance', selectedTeams],
    queryFn: ({ signal }) =>
      api.get<HoursBalanceResponse>(
        '/dashboard/hours-balance',
        selectedTeams.length > 0 ? { teams: selectedTeams.join(',') } : {},
        signal,
      ),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useHoursBalanceDetail(
  employeeId: string | null,
) {
  return useQuery<HoursBalanceDetailResponse>({
    queryKey: ['dashboard', 'hours-balance', 'detail', employeeId],
    queryFn: ({ signal }) =>
      api.get<HoursBalanceDetailResponse>(
        `/dashboard/hours-balance/${employeeId}`,
        {},
        signal,
      ),
    enabled: employeeId !== null,
    staleTime: 60_000,
    retry: 1,
  });
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/hooks/useHoursBalance.ts
git commit -m "feat(hours-balance): frontend types + TanStack Query hooks

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Frontend — виджет на дашборде

**Files:**
- Create: `frontend/src/components/dashboard/HoursBalanceWidget.tsx`

- [ ] **Step 1: Создать компонент**

Содержимое `frontend/src/components/dashboard/HoursBalanceWidget.tsx`:

```tsx
import { useState, useMemo } from 'react';
import { Card, Spin, Empty, Select } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import { useHoursBalance } from '../../hooks/useHoursBalance';
import type { HoursBalanceEmployee } from '../../types/api';
import HoursBalanceModal from './HoursBalanceModal';

type SortKey =
  | 'abs_desc'
  | 'balance_desc'
  | 'balance_asc'
  | 'name'
  | 'role';

function balanceColor(b: number): string {
  if (b > 1) return '#ff4d4f'; // переработка — красный
  if (b < -1) return '#faad14'; // недоработка — оранжевый
  return '#8aa0c0';
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data.length) return null;
  const w = 180;
  const h = 40;
  const min = Math.min(...data, 0);
  const max = Math.max(...data, 0);
  const span = Math.max(max - min, 1);
  const stepX = data.length > 1 ? w / (data.length - 1) : 0;
  const points = data
    .map((v, i) => `${i * stepX},${h - ((v - min) / span) * h}`)
    .join(' ');
  const zeroY = h - ((0 - min) / span) * h;
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <line
        x1={0}
        y1={zeroY}
        x2={w}
        y2={zeroY}
        stroke={DARK_THEME.textMuted}
        strokeDasharray="2 3"
        strokeOpacity={0.4}
      />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={2}
      />
    </svg>
  );
}

function EmployeeCard({
  emp,
  onClick,
}: {
  emp: HoursBalanceEmployee;
  onClick: () => void;
}) {
  const color = balanceColor(emp.balance_hours);
  const sign = emp.balance_hours > 0 ? '+' : '';
  return (
    <div
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
      style={{
        background: '#143258',
        border: '1px solid #1d3a66',
        borderRadius: 10,
        padding: 16,
        cursor: 'pointer',
        transition: 'transform .12s, border-color .12s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = DARK_THEME.cyanPrimary;
        e.currentTarget.style.transform = 'scale(1.015)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#1d3a66';
        e.currentTarget.style.transform = 'scale(1)';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div style={{
          width: 40, height: 40, borderRadius: '50%',
          background: 'linear-gradient(135deg, #00c9c8, #4a6cf7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: 14,
        }}>{emp.initials}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            color: DARK_THEME.textPrimary, fontSize: 15, fontWeight: 600,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{emp.full_name}</div>
          <div style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>
            {emp.role_label ?? '—'}
          </div>
        </div>
        <div style={{ fontSize: 28, fontWeight: 700, color }}>
          {sign}{Math.round(emp.balance_hours)}ч
        </div>
      </div>
      <Sparkline data={emp.sparkline} color={color} />
      <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 4,
          background: 'rgba(255,77,79,.12)', color: '#ff7875',
        }}>
          🔥 Переработок: {emp.overtime_days} дн · +{Math.round(emp.overtime_hours)}ч
        </span>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 4,
          background: 'rgba(110,122,153,.18)', color: '#a4b8d8',
        }}>
          🌙 Отгулов: {emp.skip_days} дн · {Math.round(emp.skip_hours)}ч
        </span>
      </div>
      <div style={{
        fontSize: 11, color: DARK_THEME.textMuted,
        fontStyle: 'italic', marginTop: 6,
      }}>Клик — детальный календарь</div>
    </div>
  );
}

export default function HoursBalanceWidget() {
  const { data, isLoading } = useHoursBalance();
  const [sortKey, setSortKey] = useState<SortKey>('abs_desc');
  const [openId, setOpenId] = useState<string | null>(null);

  const sorted = useMemo(() => {
    if (!data) return [];
    const arr = [...data.employees];
    switch (sortKey) {
      case 'abs_desc':
        arr.sort((a, b) => Math.abs(b.balance_hours) - Math.abs(a.balance_hours));
        break;
      case 'balance_desc':
        arr.sort((a, b) => b.balance_hours - a.balance_hours);
        break;
      case 'balance_asc':
        arr.sort((a, b) => a.balance_hours - b.balance_hours);
        break;
      case 'name':
        arr.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
        break;
      case 'role':
        arr.sort((a, b) => {
          const r = (a.role_label ?? '').localeCompare(b.role_label ?? '', 'ru');
          return r !== 0 ? r : a.full_name.localeCompare(b.full_name, 'ru');
        });
        break;
    }
    return arr;
  }, [data, sortKey]);

  if (isLoading) {
    return (
      <Card style={{ background: '#0f2340', border: '1px solid #1d3a66' }}>
        <Spin />
      </Card>
    );
  }
  if (!data || data.employees.length === 0) {
    return (
      <Card
        title={<span style={{ color: DARK_THEME.textPrimary }}>Баланс часов команды</span>}
        style={{ background: '#0f2340', border: '1px solid #1d3a66' }}
      >
        <Empty description="Нет активных сотрудников в выбранных командах" />
      </Card>
    );
  }

  const t = data.team_summary;
  return (
    <Card
      title={
        <div>
          <div style={{ color: DARK_THEME.textPrimary, fontSize: 16 }}>
            Баланс часов команды
          </div>
          <div style={{ color: DARK_THEME.textMuted, fontSize: 12, fontWeight: 400, marginTop: 2 }}>
            С {data.period.from.split('-').reverse().join('.')} · {data.period.working_days} рабочих дней · норма с учётом отпусков
          </div>
        </div>
      }
      extra={
        <Select
          value={sortKey}
          onChange={(v) => setSortKey(v as SortKey)}
          size="small"
          style={{ width: 220 }}
          options={[
            { value: 'abs_desc', label: 'По отклонению' },
            { value: 'balance_desc', label: 'Больше переработали' },
            { value: 'balance_asc', label: 'Больше недоработали' },
            { value: 'name', label: 'По имени' },
            { value: 'role', label: 'По роли' },
          ]}
        />
      }
      style={{ background: '#0f2340', border: '1px solid #1d3a66' }}
    >
      <div style={{
        background: '#143258', borderRadius: 6, padding: '8px 12px',
        marginBottom: 16, fontSize: 13, color: DARK_THEME.textMuted,
      }}>
        Команда: {t.employees_count} чел ·
        переработки <span style={{ color: '#ff7875' }}>+{Math.round(t.overtime_hours)}ч</span> ·
        автоотгулы <span style={{ color: '#a4b8d8' }}>{Math.round(t.skip_hours)}ч</span> ·
        нетто <span style={{ color: balanceColor(t.net_balance), fontWeight: 600 }}>
          {t.net_balance > 0 ? '+' : ''}{Math.round(t.net_balance)}ч
        </span>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: 12,
      }}>
        {sorted.map((emp) => (
          <EmployeeCard
            key={emp.id}
            emp={emp}
            onClick={() => setOpenId(emp.id)}
          />
        ))}
      </div>
      <div style={{
        marginTop: 12, textAlign: 'center', fontSize: 11,
        color: DARK_THEME.textMuted, fontStyle: 'italic',
      }}>
        Отпуск, больничный и другие официальные отсутствия не считаются переработкой/отгулом.
      </div>
      <HoursBalanceModal
        employeeId={openId}
        onClose={() => setOpenId(null)}
      />
    </Card>
  );
}
```

- [ ] **Step 2: Type-check (модалка ещё не создана — будет ошибка импорта)**

Run: `cd frontend && npx tsc --noEmit`
Expected: ошибка «Cannot find module './HoursBalanceModal'» — это ожидаемо, фиксим в task 10.

- [ ] **Step 3: Commit (без модалки — следующая задача)**

Не коммитим, продолжим в task 10. Виджет и модалка — одна логическая единица.

---

## Task 10: Frontend — модалка drill-in

**Files:**
- Create: `frontend/src/components/dashboard/HoursBalanceModal.tsx`

- [ ] **Step 1: Создать компонент**

Содержимое `frontend/src/components/dashboard/HoursBalanceModal.tsx`:

```tsx
import { Modal, Spin, Tooltip } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import { useHoursBalanceDetail } from '../../hooks/useHoursBalance';
import type { HoursBalanceDailyEntry } from '../../types/api';

interface Props {
  employeeId: string | null;
  onClose: () => void;
}

const WEEKDAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function balanceColor(b: number): string {
  if (b > 1) return '#ff4d4f';
  if (b < -1) return '#faad14';
  return '#8aa0c0';
}

function dayBg(kind: string): { bg: string; border: string; tone: string } {
  switch (kind) {
    case 'overtime':
      return { bg: '#3d1b1d', border: '#ff4d4f', tone: '#ff7875' };
    case 'skip':
      return { bg: '#2a2f42', border: '#6e7a99', tone: '#a4b8d8' };
    case 'norm':
      return { bg: '#1d3d22', border: '#52c41a', tone: '#52c41a' };
    case 'absence':
      return { bg: '#3b3155', border: '#6e5fb0', tone: '#b39ddb' };
    case 'holiday':
    default:
      return { bg: '#162a4a', border: 'transparent', tone: DARK_THEME.textMuted };
  }
}

function MonthCalendar({
  year,
  month,
  days,
}: {
  year: number;
  month: number;
  days: HoursBalanceDailyEntry[];
}) {
  const monthDays = days.filter((d) => {
    const dt = new Date(d.day);
    return dt.getFullYear() === year && dt.getMonth() + 1 === month;
  });
  const firstDay = new Date(year, month - 1, 1);
  const lastDay = new Date(year, month, 0);
  const startWeekday = (firstDay.getDay() + 6) % 7; // 0=Пн
  const cells: (HoursBalanceDailyEntry | null)[] = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= lastDay.getDate(); d++) {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push(monthDays.find((x) => x.day === dateStr) ?? {
      day: dateStr, norm: 0, fact: 0, delta: 0, kind: 'holiday', absence_label: null,
    });
  }
  const balance = monthDays.reduce((s, x) => s + x.delta, 0);
  const MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

  return (
    <div style={{ background: '#0d1c33', padding: 12, borderRadius: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ color: DARK_THEME.textPrimary, fontSize: 13, fontWeight: 600 }}>
          {MONTH_NAMES[month - 1]}
        </div>
        <div style={{
          fontSize: 11, padding: '2px 6px', borderRadius: 4,
          color: balanceColor(balance), background: 'rgba(255,255,255,.05)',
        }}>
          {balance > 0 ? '+' : ''}{Math.round(balance)}ч
        </div>
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
        gap: 2, fontSize: 9, color: DARK_THEME.textMuted, marginBottom: 4,
      }}>
        {WEEKDAY_LABELS.map((w) => (
          <div key={w} style={{ textAlign: 'center' }}>{w}</div>
        ))}
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
        gap: 2,
      }}>
        {cells.map((c, i) => {
          if (!c) return <div key={i} style={{ height: 24 }} />;
          const { bg, border, tone } = dayBg(c.kind);
          const tip = c.kind === 'absence'
            ? c.absence_label ?? 'Отсутствие'
            : `Норма ${c.norm}ч / Факт ${c.fact}ч / ${c.delta > 0 ? '+' : ''}${c.delta}ч`;
          return (
            <Tooltip key={i} title={tip}>
              <div style={{
                height: 24, background: bg,
                border: `1px solid ${border}`, borderRadius: 3,
                fontSize: 9, color: tone,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                position: 'relative',
              }}>
                {new Date(c.day).getDate()}
                {c.kind === 'overtime' && (
                  <span style={{
                    position: 'absolute', bottom: 1, right: 2,
                    fontSize: 7, color: '#fff', fontWeight: 700,
                  }}>+{Math.round(c.delta)}</span>
                )}
                {c.kind === 'skip' && (
                  <span style={{
                    position: 'absolute', bottom: 1, right: 2,
                    fontSize: 7, color: '#fff', fontWeight: 700,
                  }}>{Math.round(c.delta)}</span>
                )}
              </div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

export default function HoursBalanceModal({ employeeId, onClose }: Props) {
  const { data, isLoading } = useHoursBalanceDetail(employeeId);

  return (
    <Modal
      open={employeeId !== null}
      onCancel={onClose}
      width={920}
      footer={null}
      styles={{ body: { background: '#0f2340', padding: 24 } }}
      title={
        data ? (
          <div>
            <div style={{ color: DARK_THEME.textPrimary }}>
              Баланс часов — {data.employee.full_name}
            </div>
            <div style={{ color: DARK_THEME.textMuted, fontSize: 12, fontWeight: 400 }}>
              {data.employee.role_label ?? '—'}
              {data.employee.team_label ? ` · команда ${data.employee.team_label}` : ''}
              {` · с ${data.period.from.split('-').reverse().join('.')}`}
            </div>
          </div>
        ) : 'Загрузка...'
      }
    >
      {isLoading || !data ? (
        <Spin />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* KPI tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            <KpiTile
              label="Баланс"
              value={`${data.kpi.balance_hours > 0 ? '+' : ''}${Math.round(data.kpi.balance_hours)}ч`}
              caption={`за ${data.period.working_days} рабочих дней`}
              color={balanceColor(data.kpi.balance_hours)}
            />
            <KpiTile
              label="Переработки"
              value={`${data.kpi.overtime_days} дн / +${Math.round(data.kpi.overtime_hours)}ч`}
              caption=""
              color="#ff4d4f"
            />
            <KpiTile
              label="Автоотгулы"
              value={`${data.kpi.skip_days} дн / ${Math.round(data.kpi.skip_hours)}ч`}
              caption=""
              color="#a4b8d8"
            />
          </div>
          {/* Monthly strip */}
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto' }}>
            {data.monthly.map((m) => (
              <div key={`${m.year}-${m.month}`} style={{
                flex: '0 0 130px', background: '#0d1c33', padding: 10, borderRadius: 6,
              }}>
                <div style={{
                  fontSize: 10, textTransform: 'uppercase',
                  color: DARK_THEME.textMuted, marginBottom: 4,
                }}>{m.label}</div>
                <div style={{
                  fontSize: 18, fontWeight: 700, color: balanceColor(m.balance),
                }}>
                  {m.balance > 0 ? '+' : ''}{Math.round(m.balance)}ч
                </div>
                <div style={{ fontSize: 10, color: DARK_THEME.textMuted, marginTop: 2 }}>
                  {m.overtime_days} / {m.skip_days}
                </div>
              </div>
            ))}
          </div>
          {/* Calendar grid */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12,
          }}>
            {data.monthly.map((m) => (
              <MonthCalendar
                key={`${m.year}-${m.month}`}
                year={m.year}
                month={m.month}
                days={data.days}
              />
            ))}
          </div>
          {/* Legend */}
          <div style={{
            display: 'flex', gap: 16, fontSize: 11, color: DARK_THEME.textMuted,
            flexWrap: 'wrap',
          }}>
            <span>🟩 норма</span>
            <span>🟥 переработка</span>
            <span>🟪 автоотгул</span>
            <span>🟦 отпуск/больничный</span>
            <span>⬜ выходной/праздник</span>
          </div>
          <div style={{ fontSize: 11, color: DARK_THEME.textMuted, fontStyle: 'italic' }}>
            Детали задач — в Jira.
          </div>
        </div>
      )}
    </Modal>
  );
}

function KpiTile({
  label, value, caption, color,
}: {
  label: string; value: string; caption: string; color: string;
}) {
  return (
    <div style={{
      background: '#143258', border: '1px solid #1d3a66', borderRadius: 10, padding: 16,
    }}>
      <div style={{ fontSize: 12, color: DARK_THEME.textMuted, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
      {caption && (
        <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginTop: 4 }}>
          {caption}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint -- --max-warnings=0`
Expected: clean.

- [ ] **Step 4: Commit виджета и модалки одним коммитом**

```bash
git add frontend/src/components/dashboard/HoursBalanceWidget.tsx frontend/src/components/dashboard/HoursBalanceModal.tsx
git commit -m "feat(hours-balance): виджет + модалка drill-in

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Frontend — встроить виджет в DashboardPage

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Прочитать текущую структуру**

Run: `cat frontend/src/pages/DashboardPage.tsx | head -80`

Найти где монтируются текущие виджеты (ProjectsWidget, NormWorkWidget, CategoryWidget). Виджеты разнесены в AntD Col по сетке.

- [ ] **Step 2: Добавить импорт и вставить 4-й виджет**

Добавить импорт сверху:
```tsx
import HoursBalanceWidget from '../components/dashboard/HoursBalanceWidget';
```

В JSX добавить новый `<Col span={24}>` блок ПОСЛЕ существующего ряда виджетов (HoursBalance — полноширинный, идёт последним):
```tsx
<Col span={24}>
  <HoursBalanceWidget />
</Col>
```

- [ ] **Step 3: Type-check + lint**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run lint -- --max-warnings=0
```
Expected: clean.

- [ ] **Step 4: Запустить dev сервера, открыть в браузере**

Run (background): `cd frontend && npm run dev` (port 5173)
Run (background): backend `py -3.10 -m uvicorn app.main:app --reload --port 8000`

Открыть http://localhost:5173/ — увидеть новый виджет в самом низу дашборда. Кликнуть карточку — открыть модалку. Esc — закрыть. Sort — попереключать опции, проверить порядок.

Manual checklist:
- [ ] виджет видим
- [ ] карточки в сетке адаптируются под ширину
- [ ] клик открывает модалку
- [ ] сортировка работает
- [ ] empty state «Нет активных сотрудников» если команда пустая
- [ ] hover на карточке подсвечивает cyan

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "feat(hours-balance): виджет на дашборде (4-й блок)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: E2E Playwright

**Files:**
- Create: `e2e/hours-balance.spec.ts`

- [ ] **Step 1: Создать spec**

Содержимое `e2e/hours-balance.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

test.describe('Виджет «Баланс часов команды»', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // login если нужен — см. e2e/utils
  });

  test('виджет рендерится на дашборде', async ({ page }) => {
    await expect(page.getByText('Баланс часов команды')).toBeVisible({ timeout: 10000 });
  });

  test('клик по карточке открывает модалку, Esc закрывает', async ({ page }) => {
    await expect(page.getByText('Баланс часов команды')).toBeVisible({ timeout: 10000 });
    // найти первую карточку с инициалами и кликнуть
    const firstCard = page.locator('[role="button"]', { hasText: /^[А-Я]{1,2}$/ }).first();
    if ((await firstCard.count()) === 0) {
      test.skip(); // нет данных в e2e seed
    }
    await firstCard.click();
    await expect(page.getByText(/Баланс часов —/)).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByText(/Баланс часов —/)).not.toBeVisible();
  });
});
```

- [ ] **Step 2: Запустить e2e**

Run: `cd frontend && npm run e2e -- --grep "Баланс часов"`
Expected: PASS или test.skip если нет seed данных.

- [ ] **Step 3: Commit**

```bash
git add e2e/hours-balance.spec.ts
git commit -m "test(hours-balance): e2e playwright spec

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Release note + push

**Files:**
- Modify: `data/release_notes.json` (через скрипт)

- [ ] **Step 1: Добавить release note**

Run:
```bash
py -3.10 scripts/release_note.py add feat "Виджет «Баланс часов команды» на дашборде — переработки и автоотгулы накопительно с начала года, drill-in календарь"
```
Expected: запись добавилась.

- [ ] **Step 2: Push всех коммитов в origin/main**

Run:
```bash
git push origin main
```

- [ ] **Step 3: Финальная верификация**

- pytest зелёный (минус известный pre-existing): `py -3.10 -m pytest tests/`
- e2e зелёный или skipped
- виджет работает в браузере
- линт зелёный
- release note виден на /settings → Release Notes

---

## Notes for the executor

- **Production calendar:** на dev DB заполнен на 2026 миграцией 042+ (memory: `project_postgres_migration_phase1_2_shipped`). Если нет — фоллбэк 8ч/будни сработает.
- **AntD Modal:** AntD 6 использует `styles={{ body: {...} }}` (см. memory `feedback_antd6_notification_title`). Modal title-структура поддерживает ReactNode.
- **Worklog.date_started:** datetime поле, `func.date()` в SQLite вернёт ISO-строку — coerced в `_worklog_map` в код.
- **Pydantic 2:** `from_` alias → `from` в JSON — сделан через `model_dump` override + `populate_by_name=True`.
- **EmployeeTeam.team:** строка (legacy поле), есть в M:N модели; фильтр `team.in_(team_ids)` где team_ids — строки команд.
- **AbsenceReason код `day_off`:** seeded миграцией 021. Если отсутствует — warning + автоотгулы не детектятся (документировано).
- **TanStack Query inval:** виджет не подписывается на SSE events (worklogs меняются редко, 60с stale достаточно).
- **Tests fixture `db_session` + `auth_headers`:** должны быть в conftest. Если нет — добавить базу из других test_api модулей.
