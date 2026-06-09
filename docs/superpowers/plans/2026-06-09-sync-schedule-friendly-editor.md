# Sync Schedule Friendly Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить cron-инпут в редакторе расписаний `/sync` на типизированный билдер (минуты/часы/ежедневно/будни/выходные/дни недели/еженедельно + cron fallback), добавить edit существующих, показать описание + 3 ближайших запуска.

**Architecture:** Frontend строит cron из формы (`cronBuilder.ts`), backend получает уже готовый cron + отдаёт computed `description` через `humanize_cron`. Новый endpoint `POST /sync/schedule/preview` возвращает описание + 3 ближайших запуска. Один `ScheduleEditorModal` обслуживает create + edit.

**Tech Stack:** Python 3.10 / FastAPI / APScheduler / pytest; React 19 / TS 6 / AntD 6 / TanStack Query.

---

## File Structure

**Backend:**
- `app/services/scheduler.py` — добавить `humanize_cron(cron: str) -> str` и `next_runs(cron: str, count: int) -> list[datetime]`.
- `app/schemas/sync_pipeline.py` — добавить computed `description` в `SyncScheduleOut`, новые схемы `SchedulePreviewRequest` / `SchedulePreviewResponse`.
- `app/api/endpoints/sync.py` — новый endpoint `POST /sync/schedule/preview`.
- `tests/test_sync_schedule_preview.py` — новые тесты на preview + humanize.
- `tests/test_sync_schedule_crud.py` (если существует) или соответствующий — проверить `description` в ответе.

**Frontend:**
- `frontend/src/api/syncSchedule.ts` — добавить `description` в `SyncScheduleOut`, новые типы preview, функция `previewSchedule`.
- `frontend/src/utils/cronBuilder.ts` (новый) — `parseCron` / `buildCron` / типы `ScheduleType` и `ScheduleForm`.
- `frontend/src/components/sync/ScheduleEditorModal.tsx` (новый) — modal билдера для create + edit.
- `frontend/src/components/sync/SyncSchedule.tsx` — таблица: колонка «Расписание» с описанием+tooltip, клик строки → edit, удалить inline create-modal.

---

## Task 1: Backend — `humanize_cron` + `next_runs` helpers

**Files:**
- Modify: `app/services/scheduler.py`
- Test: `tests/test_sync_schedule_preview.py`

- [ ] **Step 1: Прочитать существующий `scheduler.py`**

Read: `app/services/scheduler.py`
Goal: понять как используется `is_valid_cron`, какие импорты уже есть. APScheduler уже зависимость.

- [ ] **Step 2: Написать failing-тесты для `humanize_cron`**

Create: `tests/test_sync_schedule_preview.py`

```python
"""Тесты humanize_cron + next_runs + preview endpoint."""
import pytest
from datetime import datetime, timezone
from app.services.scheduler import SchedulerService


class TestHumanizeCron:
    def test_every_5_minutes(self):
        assert SchedulerService.humanize_cron("*/5 * * * *") == "Каждые 5 минут"

    def test_every_minute(self):
        assert SchedulerService.humanize_cron("*/1 * * * *") == "Каждую минуту"

    def test_every_2_hours(self):
        assert SchedulerService.humanize_cron("0 */2 * * *") == "Каждые 2 часа"

    def test_every_hour(self):
        assert SchedulerService.humanize_cron("0 */1 * * *") == "Каждый час"

    def test_daily(self):
        assert SchedulerService.humanize_cron("0 6 * * *") == "Каждый день в 06:00"

    def test_weekdays(self):
        assert SchedulerService.humanize_cron("30 9 * * 1-5") == "По будням (пн-пт) в 09:30"

    def test_weekdays_list_form(self):
        assert SchedulerService.humanize_cron("30 9 * * 1,2,3,4,5") == "По будням (пн-пт) в 09:30"

    def test_weekends(self):
        assert SchedulerService.humanize_cron("0 10 * * 0,6") == "По выходным (сб-вс) в 10:00"

    def test_specific_days(self):
        # пн + чт = 1,4
        assert SchedulerService.humanize_cron("0 18 * * 1,4") == "По дням: пн, чт в 18:00"

    def test_weekly_single_day(self):
        assert SchedulerService.humanize_cron("0 12 * * 3") == "Каждую среду в 12:00"

    def test_unparseable_fallback(self):
        # Случайный валидный cron не из шаблона
        result = SchedulerService.humanize_cron("15,45 8-17 * * *")
        assert result.startswith("По cron-выражению:")
```

- [ ] **Step 3: Запустить тесты — должны падать**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py::TestHumanizeCron -v`
Expected: FAIL с `AttributeError: type object 'SchedulerService' has no attribute 'humanize_cron'`.

- [ ] **Step 4: Реализовать `humanize_cron` в `app/services/scheduler.py`**

Modify: `app/services/scheduler.py`

В классе `SchedulerService` добавить статический метод:

```python
    @staticmethod
    def humanize_cron(cron_expr: str) -> str:
        """Преобразовать cron-выражение в человекочитаемое описание на русском.

        Поддерживает шаблоны: */N (минуты/часы), M H * * *, M H * * 1-5/0,6,
        M H * * D1,D2,..., M H * * D. Для не распознанных шаблонов возвращает
        ``По cron-выражению: <expr>``.
        """
        import re

        DAY_NAMES = {0: "вс", 1: "пн", 2: "вт", 3: "ср", 4: "чт", 5: "пт", 6: "сб"}
        DAY_NOMINATIVE = {
            0: "воскресенье", 1: "понедельник", 2: "вторник", 3: "среду",
            4: "четверг", 5: "пятницу", 6: "субботу",
        }

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return f"По cron-выражению: {cron_expr}"
        minute, hour, dom, month, dow = parts

        # Каждые N минут
        if month == "*" and dom == "*" and dow == "*" and hour == "*":
            m = re.fullmatch(r"\*/(\d+)", minute)
            if m:
                n = int(m.group(1))
                if n == 1:
                    return "Каждую минуту"
                return f"Каждые {n} минут"

        # Каждые N часов
        if month == "*" and dom == "*" and dow == "*" and minute == "0":
            m = re.fullmatch(r"\*/(\d+)", hour)
            if m:
                n = int(m.group(1))
                if n == 1:
                    return "Каждый час"
                return f"Каждые {n} часа" if 2 <= n <= 4 else f"Каждые {n} часов"

        # Точное время M H
        if minute.isdigit() and hour.isdigit() and month == "*" and dom == "*":
            time_str = f"{int(hour):02d}:{int(minute):02d}"
            if dow == "*":
                return f"Каждый день в {time_str}"

            days = _parse_dow(dow)
            if days is None:
                return f"По cron-выражению: {cron_expr}"

            if days == {1, 2, 3, 4, 5}:
                return f"По будням (пн-пт) в {time_str}"
            if days == {0, 6}:
                return f"По выходным (сб-вс) в {time_str}"
            if len(days) == 1:
                d = next(iter(days))
                return f"Каждую {DAY_NOMINATIVE[d]} в {time_str}"

            names = ", ".join(DAY_NAMES[d] for d in sorted(days))
            return f"По дням: {names} в {time_str}"

        return f"По cron-выражению: {cron_expr}"
```

И вспомогательная функция в том же файле (модульного уровня):

```python
def _parse_dow(dow: str) -> set[int] | None:
    """Распарсить day-of-week часть cron в множество 0-6.

    Поддерживает: ``*``, ``1-5``, ``0,6``, ``1,2,3``. Возвращает None если
    формат не распознан.
    """
    if dow == "*":
        return set(range(7))
    if "-" in dow:
        m = dow.split("-")
        if len(m) == 2 and m[0].isdigit() and m[1].isdigit():
            start, end = int(m[0]), int(m[1])
            if 0 <= start <= 6 and 0 <= end <= 6 and start <= end:
                return set(range(start, end + 1))
        return None
    if "," in dow:
        try:
            days = {int(x) for x in dow.split(",")}
            if all(0 <= d <= 6 for d in days):
                return days
        except ValueError:
            return None
        return None
    if dow.isdigit():
        d = int(dow)
        if 0 <= d <= 6:
            return {d}
    return None
```

- [ ] **Step 5: Запустить тесты `humanize_cron` — должны пройти**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py::TestHumanizeCron -v`
Expected: PASS (11 tests).

- [ ] **Step 6: Написать failing-тесты для `next_runs`**

Append to `tests/test_sync_schedule_preview.py`:

```python
class TestNextRuns:
    def test_daily_returns_3(self):
        runs = SchedulerService.next_runs("0 6 * * *", count=3)
        assert len(runs) == 3
        # Каждый следующий через сутки
        for i in range(1, 3):
            delta = runs[i] - runs[i - 1]
            assert delta.total_seconds() == 86400

    def test_every_5_minutes(self):
        runs = SchedulerService.next_runs("*/5 * * * *", count=3)
        assert len(runs) == 3
        for i in range(1, 3):
            delta = runs[i] - runs[i - 1]
            assert delta.total_seconds() == 300

    def test_returns_aware_datetimes(self):
        runs = SchedulerService.next_runs("0 6 * * *", count=1)
        assert runs[0].tzinfo is not None

    def test_invalid_cron_returns_empty(self):
        assert SchedulerService.next_runs("not a cron", count=3) == []
```

- [ ] **Step 7: Запустить тесты — должны падать**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py::TestNextRuns -v`
Expected: FAIL с `AttributeError: ... has no attribute 'next_runs'`.

- [ ] **Step 8: Реализовать `next_runs`**

Modify: `app/services/scheduler.py` (в классе `SchedulerService`)

```python
    @staticmethod
    def next_runs(cron_expr: str, count: int = 3) -> list[datetime]:
        """Получить ``count`` ближайших времён запуска для cron-выражения.

        Возвращает пустой список если cron невалиден. Datetime'ы tz-aware
        в локальной таймзоне сервера (для отображения пользователю).
        """
        from datetime import datetime, timezone

        if not SchedulerService.is_valid_cron(cron_expr):
            return []
        try:
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger.from_crontab(cron_expr)
            results: list[datetime] = []
            now = datetime.now(timezone.utc).astimezone()
            previous = now
            for _ in range(count):
                next_fire = trigger.get_next_fire_time(None, previous)
                if next_fire is None:
                    break
                results.append(next_fire)
                # сместить курсор чтобы получить следующий — добавить микросекунду
                from datetime import timedelta
                previous = next_fire + timedelta(microseconds=1)
            return results
        except Exception:
            return []
```

Убедиться что `datetime` импортирован вверху файла (если ещё нет — добавить `from datetime import datetime`).

- [ ] **Step 9: Запустить тесты `next_runs`**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py::TestNextRuns -v`
Expected: PASS (4 tests).

- [ ] **Step 10: Коммит**

```bash
git add app/services/scheduler.py tests/test_sync_schedule_preview.py
git commit -m "feat(scheduler): humanize_cron + next_runs хелперы"
```

---

## Task 2: Backend — `description` в `SyncScheduleOut`

**Files:**
- Modify: `app/schemas/sync_pipeline.py`
- Test: `tests/test_sync_schedule_preview.py`

- [ ] **Step 1: Прочитать существующую схему**

Read: `app/schemas/sync_pipeline.py`
Найти класс `SyncScheduleOut`.

- [ ] **Step 2: Написать failing-тест**

Append to `tests/test_sync_schedule_preview.py`:

```python
class TestScheduleOutDescription:
    def test_description_computed_from_cron(self):
        from app.schemas.sync_pipeline import SyncScheduleOut
        from datetime import datetime

        data = {
            "id": "abc-123",
            "name": "Утренний синк",
            "cron_expr": "0 6 * * *",
            "mode": "normal",
            "team": None,
            "enabled": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        out = SyncScheduleOut.model_validate(data)
        assert out.description == "Каждый день в 06:00"
```

- [ ] **Step 3: Запустить — fail**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py::TestScheduleOutDescription -v`
Expected: FAIL с `AttributeError` или `ValidationError` об отсутствующем поле.

- [ ] **Step 4: Добавить computed-поле**

Modify: `app/schemas/sync_pipeline.py`

В классе `SyncScheduleOut` добавить computed field:

```python
    from pydantic import computed_field

    @computed_field  # type: ignore[misc]
    @property
    def description(self) -> str:
        """Человекочитаемое описание расписания (например, "Каждый день в 06:00")."""
        from app.services.scheduler import SchedulerService
        return SchedulerService.humanize_cron(self.cron_expr)
```

Если `computed_field` ещё не импортирован в файле — добавить в существующий импорт из `pydantic`. Если структура файла требует разместить импорт `computed_field` глобально — сделать это.

- [ ] **Step 5: Тест должен пройти**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py::TestScheduleOutDescription -v`
Expected: PASS.

- [ ] **Step 6: Прогнать существующие тесты CRUD расписаний (regression)**

Run: `py -3.10 -m pytest tests/ -k "schedule" -v`
Expected: все PASS. Если есть тесты, явно проверяющие отсутствие лишних полей — обновить их (добавить `description` в expected).

- [ ] **Step 7: Коммит**

```bash
git add app/schemas/sync_pipeline.py tests/test_sync_schedule_preview.py
git commit -m "feat(sync): computed description в SyncScheduleOut"
```

---

## Task 3: Backend — endpoint `POST /sync/schedule/preview`

**Files:**
- Modify: `app/schemas/sync_pipeline.py` (новые request/response схемы)
- Modify: `app/api/endpoints/sync.py`
- Test: `tests/test_sync_schedule_preview.py`

- [ ] **Step 1: Добавить failing-тесты endpoint**

Append to `tests/test_sync_schedule_preview.py`:

```python
class TestPreviewEndpoint:
    def test_valid_cron_returns_description_and_next_runs(self, client):
        resp = client.post("/api/v1/sync/schedule/preview", json={"cron_expr": "0 6 * * *"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["description"] == "Каждый день в 06:00"
        assert len(body["next_runs"]) == 3
        assert body["error"] is None

    def test_invalid_cron_returns_valid_false(self, client):
        resp = client.post("/api/v1/sync/schedule/preview", json={"cron_expr": "not a cron"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["next_runs"] == []
        assert body["error"]

    def test_every_5_minutes(self, client):
        resp = client.post("/api/v1/sync/schedule/preview", json={"cron_expr": "*/5 * * * *"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["description"] == "Каждые 5 минут"
```

Если в `tests/conftest.py` нет фикстуры `client` — посмотреть как используются другие тесты sync (`tests/test_sync_*.py`) и взять оттуда. Скорее всего фикстура называется `client` или `api_client`.

- [ ] **Step 2: Запустить — fail**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py::TestPreviewEndpoint -v`
Expected: FAIL с 404 (endpoint не существует) или fixture error.

- [ ] **Step 3: Если fixture отсутствует — найти существующую**

Run: `Grep pattern="def client" path="tests/" -n -A 3 --include="conftest*"`
Если нет `client` — использовать ту, что в других sync-тестах. Подправить тест если нужно.

- [ ] **Step 4: Добавить request/response схемы**

Modify: `app/schemas/sync_pipeline.py`

Добавить:

```python
class SchedulePreviewRequest(BaseModel):
    """Запрос на preview расписания: cron → описание + ближайшие запуски."""
    cron_expr: str


class SchedulePreviewResponse(BaseModel):
    """Ответ preview: valid + описание + 3 ближайших запуска."""
    valid: bool
    description: Optional[str] = None
    next_runs: list[str] = []
    error: Optional[str] = None
```

(Импорт `Optional` уже есть в файле; если нет — добавить.)

- [ ] **Step 5: Реализовать endpoint**

Modify: `app/api/endpoints/sync.py`

В импорт `from app.schemas.sync_pipeline import ...` добавить `SchedulePreviewRequest, SchedulePreviewResponse`.

После `delete_schedule` (или в любом месте между `update_schedule` и `run_schedule_now` — порядок не важен, но удобно сгруппировать) добавить:

```python
@router.post("/schedule/preview", response_model=SchedulePreviewResponse)
def preview_schedule(body: SchedulePreviewRequest) -> SchedulePreviewResponse:
    """Preview расписания: описание + 3 ближайших запуска.

    Используется фронтом при редактировании, чтобы показать пользователю,
    как cron-выражение интерпретируется и когда сработает следующий раз.
    """
    from app.services.scheduler import SchedulerService

    if not SchedulerService.is_valid_cron(body.cron_expr):
        return SchedulePreviewResponse(
            valid=False,
            description=None,
            next_runs=[],
            error="Невалидное cron-выражение",
        )
    description = SchedulerService.humanize_cron(body.cron_expr)
    runs = SchedulerService.next_runs(body.cron_expr, count=3)
    return SchedulePreviewResponse(
        valid=True,
        description=description,
        next_runs=[r.isoformat() for r in runs],
        error=None,
    )
```

- [ ] **Step 6: Тесты endpoint должны пройти**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py::TestPreviewEndpoint -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Прогнать все тесты файла + regression**

Run: `py -3.10 -m pytest tests/test_sync_schedule_preview.py -v && py -3.10 -m pytest tests/ -k "schedule or sync" -v --tb=short`
Expected: PASS. Если уже существующие sync-тесты сломались — починить.

- [ ] **Step 8: Коммит**

```bash
git add app/schemas/sync_pipeline.py app/api/endpoints/sync.py tests/test_sync_schedule_preview.py
git commit -m "feat(sync): POST /sync/schedule/preview — описание + 3 запуска"
```

---

## Task 4: Frontend — типы + API клиент

**Files:**
- Modify: `frontend/src/api/syncSchedule.ts`

- [ ] **Step 1: Прочитать существующий клиент**

Read: `frontend/src/api/syncSchedule.ts`
Цель: понять стиль (как объявлены `SyncScheduleOut`, `getSchedules` и т.п.).

- [ ] **Step 2: Добавить `description` в `SyncScheduleOut`**

Modify: `frontend/src/api/syncSchedule.ts`

В интерфейсе `SyncScheduleOut` добавить поле:

```ts
  description: string;
```

- [ ] **Step 3: Добавить preview API**

В тот же файл (в конец):

```ts
export interface SchedulePreviewRequest {
  cron_expr: string;
}

export interface SchedulePreviewResponse {
  valid: boolean;
  description: string | null;
  next_runs: string[];
  error: string | null;
}

export async function previewSchedule(
  cron_expr: string,
): Promise<SchedulePreviewResponse> {
  return api.post('/sync/schedule/preview', { cron_expr });
}
```

(Если `api.post` принимает другой shape — посмотреть как вызываются `createSchedule` / `updateSchedule` в этом файле и повторить паттерн.)

- [ ] **Step 4: Запустить TypeScript check**

Run: `cd frontend && npm run lint`
Expected: новых ошибок нет.

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/api/syncSchedule.ts
git commit -m "feat(sync-fe): description + preview API клиент"
```

---

## Task 5: Frontend — `cronBuilder.ts`

**Files:**
- Create: `frontend/src/utils/cronBuilder.ts`

- [ ] **Step 1: Создать файл с типами и `buildCron`**

Create: `frontend/src/utils/cronBuilder.ts`

```ts
export type ScheduleType =
  | 'every_minutes'
  | 'every_hours'
  | 'daily'
  | 'weekdays'
  | 'weekends'
  | 'specific_days'
  | 'weekly'
  | 'cron';

export interface ScheduleForm {
  type: ScheduleType;
  minutes?: number;
  hours?: number;
  time?: string;
  days?: number[];
  day?: number;
  cron?: string;
}

const MINUTE_DIVISORS = [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30];
const HOUR_DIVISORS = [1, 2, 3, 4, 6, 8, 12];

export const MINUTE_OPTIONS = MINUTE_DIVISORS;
export const HOUR_OPTIONS = HOUR_DIVISORS;

const DAY_LABELS_RU = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
// Маппинг UI-индекса (0=пн..6=вс) → cron-индекс (0=вс,1=пн..6=сб)
const UI_TO_CRON_DAY = [1, 2, 3, 4, 5, 6, 0];
const CRON_TO_UI_DAY: Record<number, number> = {
  0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5,
};

export const DAY_OPTIONS = DAY_LABELS_RU.map((label, value) => ({ value, label }));

function parseTime(time: string): [number, number] {
  const [h, m] = time.split(':').map(Number);
  return [h, m];
}

export function buildCron(form: ScheduleForm): string {
  switch (form.type) {
    case 'every_minutes': {
      const n = form.minutes ?? 5;
      return `*/${n} * * * *`;
    }
    case 'every_hours': {
      const n = form.hours ?? 1;
      return `0 */${n} * * *`;
    }
    case 'daily': {
      const [h, m] = parseTime(form.time ?? '06:00');
      return `${m} ${h} * * *`;
    }
    case 'weekdays': {
      const [h, m] = parseTime(form.time ?? '09:00');
      return `${m} ${h} * * 1-5`;
    }
    case 'weekends': {
      const [h, m] = parseTime(form.time ?? '10:00');
      return `${m} ${h} * * 0,6`;
    }
    case 'specific_days': {
      const [h, m] = parseTime(form.time ?? '09:00');
      const cronDays = (form.days ?? [])
        .map((uiDay) => UI_TO_CRON_DAY[uiDay])
        .sort((a, b) => a - b)
        .join(',');
      return `${m} ${h} * * ${cronDays}`;
    }
    case 'weekly': {
      const [h, m] = parseTime(form.time ?? '09:00');
      const uiDay = form.day ?? 0;
      return `${m} ${h} * * ${UI_TO_CRON_DAY[uiDay]}`;
    }
    case 'cron':
      return form.cron ?? '';
  }
}

export function parseCron(cron: string): ScheduleForm {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return { type: 'cron', cron };
  const [minute, hour, dom, month, dow] = parts;

  // every_minutes: */N * * * *
  if (month === '*' && dom === '*' && dow === '*' && hour === '*') {
    const m = /^\*\/(\d+)$/.exec(minute);
    if (m) {
      const n = Number(m[1]);
      if (MINUTE_DIVISORS.includes(n)) return { type: 'every_minutes', minutes: n };
    }
  }

  // every_hours: 0 */N * * *
  if (month === '*' && dom === '*' && dow === '*' && minute === '0') {
    const m = /^\*\/(\d+)$/.exec(hour);
    if (m) {
      const n = Number(m[1]);
      if (HOUR_DIVISORS.includes(n)) return { type: 'every_hours', hours: n };
    }
  }

  // M H * * (*|days)
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && month === '*' && dom === '*') {
    const h = Number(hour);
    const m = Number(minute);
    const time = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;

    if (dow === '*') return { type: 'daily', time };

    const days = parseDow(dow);
    if (days === null) return { type: 'cron', cron };

    const eq = (a: number[], b: number[]) =>
      a.length === b.length && a.every((x, i) => x === b[i]);

    const sorted = [...days].sort((a, b) => a - b);
    if (eq(sorted, [1, 2, 3, 4, 5])) return { type: 'weekdays', time };
    if (eq(sorted, [0, 6])) return { type: 'weekends', time };
    if (sorted.length === 1) {
      const uiDay = CRON_TO_UI_DAY[sorted[0]];
      return { type: 'weekly', day: uiDay, time };
    }
    const uiDays = sorted.map((d) => CRON_TO_UI_DAY[d]).sort((a, b) => a - b);
    return { type: 'specific_days', days: uiDays, time };
  }

  return { type: 'cron', cron };
}

function parseDow(dow: string): number[] | null {
  if (dow === '*') return [0, 1, 2, 3, 4, 5, 6];
  if (dow.includes('-')) {
    const [a, b] = dow.split('-').map(Number);
    if (Number.isFinite(a) && Number.isFinite(b) && a <= b && a >= 0 && b <= 6) {
      const out: number[] = [];
      for (let i = a; i <= b; i += 1) out.push(i);
      return out;
    }
    return null;
  }
  if (dow.includes(',')) {
    const nums = dow.split(',').map(Number);
    if (nums.every((n) => Number.isFinite(n) && n >= 0 && n <= 6)) return nums;
    return null;
  }
  const n = Number(dow);
  if (Number.isFinite(n) && n >= 0 && n <= 6) return [n];
  return null;
}
```

- [ ] **Step 2: Lint**

Run: `cd frontend && npm run lint -- src/utils/cronBuilder.ts`
Expected: no errors. Если линт ругается на `Number()` vs `parseInt` — исправить по стилю проекта.

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/utils/cronBuilder.ts
git commit -m "feat(sync-fe): cronBuilder — parseCron + buildCron"
```

---

## Task 6: Frontend — `ScheduleEditorModal`

**Files:**
- Create: `frontend/src/components/sync/ScheduleEditorModal.tsx`

- [ ] **Step 1: Создать modal**

Create: `frontend/src/components/sync/ScheduleEditorModal.tsx`

```tsx
import { useEffect, useMemo, useState } from 'react';
import {
  Alert, Checkbox, Form, Input, InputNumber, Modal, Select, Switch, TimePicker, Typography,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useMutation } from '@tanstack/react-query';
import {
  createSchedule, updateSchedule, previewSchedule,
  type SchedulePreviewResponse, type SyncScheduleOut, type SyncScheduleCreate,
} from '../../api/syncSchedule';
import type { PipelineMode } from '../../api/syncRuns';
import {
  type ScheduleType, type ScheduleForm,
  parseCron, buildCron, MINUTE_OPTIONS, HOUR_OPTIONS, DAY_OPTIONS,
} from '../../utils/cronBuilder';

const MODE_LABELS: Record<PipelineMode, string> = {
  quick: 'Быстрый',
  normal: 'Обычный',
  full: 'Полный',
  team: 'По команде',
};

const TYPE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: 'every_minutes', label: 'Каждые N минут' },
  { value: 'every_hours', label: 'Каждые N часов' },
  { value: 'daily', label: 'Каждый день в...' },
  { value: 'weekdays', label: 'Будни (пн-пт) в...' },
  { value: 'weekends', label: 'Выходные (сб-вс) в...' },
  { value: 'specific_days', label: 'По дням недели в...' },
  { value: 'weekly', label: 'Еженедельно в...' },
  { value: 'cron', label: 'Произвольно (cron)' },
];

interface FormValues {
  name: string;
  type: ScheduleType;
  minutes?: number;
  hours?: number;
  time?: Dayjs;
  days?: number[];
  day?: number;
  cron?: string;
  mode: PipelineMode;
  team?: string;
  enabled: boolean;
}

function valuesToScheduleForm(v: FormValues): ScheduleForm {
  return {
    type: v.type,
    minutes: v.minutes,
    hours: v.hours,
    time: v.time ? v.time.format('HH:mm') : undefined,
    days: v.days,
    day: v.day,
    cron: v.cron,
  };
}

function scheduleFormToValues(f: ScheduleForm, base: Partial<FormValues>): FormValues {
  return {
    name: base.name ?? '',
    type: f.type,
    minutes: f.minutes ?? 5,
    hours: f.hours ?? 2,
    time: f.time ? dayjs(f.time, 'HH:mm') : dayjs('06:00', 'HH:mm'),
    days: f.days ?? [0, 3], // пн+чт по умолчанию
    day: f.day ?? 0,
    cron: f.cron ?? '0 6 * * *',
    mode: (base.mode as PipelineMode) ?? 'normal',
    team: base.team,
    enabled: base.enabled ?? true,
  };
}

interface Props {
  open: boolean;
  schedule: SyncScheduleOut | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function ScheduleEditorModal({ open, schedule, onClose, onSaved }: Props) {
  const isEdit = schedule !== null;
  const [form] = Form.useForm<FormValues>();
  const [preview, setPreview] = useState<SchedulePreviewResponse | null>(null);
  const [values, setValues] = useState<FormValues | null>(null);

  // Инициализация при открытии
  useEffect(() => {
    if (!open) return;
    const initialForm: ScheduleForm = schedule
      ? parseCron(schedule.cron_expr)
      : { type: 'daily', time: '06:00' };
    const initialValues = scheduleFormToValues(initialForm, {
      name: schedule?.name ?? '',
      mode: schedule?.mode as PipelineMode | undefined,
      team: schedule?.team ?? undefined,
      enabled: schedule?.enabled ?? true,
    });
    form.setFieldsValue(initialValues);
    setValues(initialValues);
  }, [open, schedule, form]);

  // Debounced preview
  useEffect(() => {
    if (!values) return;
    const cron = buildCron(valuesToScheduleForm(values));
    if (!cron) return;
    const t = setTimeout(() => {
      previewSchedule(cron).then(setPreview).catch(() => setPreview(null));
    }, 300);
    return () => clearTimeout(t);
  }, [values]);

  const createMut = useMutation({
    mutationFn: (body: SyncScheduleCreate) => createSchedule(body),
    onSuccess: () => { onSaved(); onClose(); },
  });
  const updateMut = useMutation({
    mutationFn: (body: SyncScheduleCreate) =>
      updateSchedule(schedule!.id, body),
    onSuccess: () => { onSaved(); onClose(); },
  });

  const handleOk = async () => {
    const v = await form.validateFields();
    const cron = buildCron(valuesToScheduleForm(v));
    const body: SyncScheduleCreate = {
      name: v.name,
      cron_expr: cron,
      mode: v.mode,
      team: v.mode === 'team' ? v.team ?? null : null,
      enabled: v.enabled,
    };
    if (isEdit) updateMut.mutate(body);
    else createMut.mutate(body);
  };

  const type = values?.type ?? 'daily';
  const mode = values?.mode ?? 'normal';

  const previewBlock = useMemo(() => {
    if (!preview) return null;
    if (!preview.valid) {
      return <Alert type="error" message={preview.error ?? 'Невалидное расписание'} showIcon />;
    }
    const runs = preview.next_runs.map((iso) => dayjs(iso).format('DD.MM.YYYY HH:mm')).join(', ');
    return (
      <Alert
        type="info"
        showIcon
        message={preview.description}
        description={`Следующие запуски: ${runs}`}
      />
    );
  }, [preview]);

  return (
    <Modal
      title={isEdit ? 'Редактирование расписания' : 'Новое расписание'}
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={createMut.isPending || updateMut.isPending}
      okText="Сохранить"
      cancelText="Отмена"
      width={560}
    >
      <Form<FormValues>
        form={form}
        layout="vertical"
        onValuesChange={(_, all) => setValues(all)}
      >
        <Form.Item name="name" label="Название" rules={[{ required: true }]}>
          <Input placeholder="Например, утренний полный синк" />
        </Form.Item>

        <Form.Item name="type" label="Тип расписания" rules={[{ required: true }]}>
          <Select options={TYPE_OPTIONS} />
        </Form.Item>

        {type === 'every_minutes' && (
          <Form.Item
            name="minutes"
            label="Каждые ... минут"
            rules={[{ required: true }]}
            extra="Доступны делители 60: 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30"
          >
            <Select
              options={MINUTE_OPTIONS.map((n) => ({ value: n, label: `${n} мин` }))}
              style={{ width: 200 }}
            />
          </Form.Item>
        )}

        {type === 'every_hours' && (
          <Form.Item
            name="hours"
            label="Каждые ... часов"
            rules={[{ required: true }]}
            extra="Доступны делители 24: 1, 2, 3, 4, 6, 8, 12"
          >
            <Select
              options={HOUR_OPTIONS.map((n) => ({ value: n, label: `${n} ч` }))}
              style={{ width: 200 }}
            />
          </Form.Item>
        )}

        {(type === 'daily' || type === 'weekdays' || type === 'weekends'
          || type === 'specific_days' || type === 'weekly') && (
          <Form.Item name="time" label="Время" rules={[{ required: true }]}>
            <TimePicker format="HH:mm" minuteStep={5} style={{ width: 160 }} />
          </Form.Item>
        )}

        {type === 'specific_days' && (
          <Form.Item
            name="days"
            label="Дни недели"
            rules={[
              { required: true, message: 'Выберите хотя бы один день' },
              {
                validator: (_, v) =>
                  v && v.length > 0 ? Promise.resolve() : Promise.reject(new Error('Выберите хотя бы один день')),
              },
            ]}
          >
            <Checkbox.Group options={DAY_OPTIONS} />
          </Form.Item>
        )}

        {type === 'weekly' && (
          <Form.Item name="day" label="День недели" rules={[{ required: true }]}>
            <Select options={DAY_OPTIONS} style={{ width: 200 }} />
          </Form.Item>
        )}

        {type === 'cron' && (
          <Form.Item
            name="cron"
            label="Cron-выражение"
            rules={[{ required: true }]}
            extra="Стандартный формат: минута час день месяц день_недели"
          >
            <Input placeholder="0 6 * * *" />
          </Form.Item>
        )}

        <Form.Item name="mode" label="Режим запуска" rules={[{ required: true }]}>
          <Select
            options={(Object.entries(MODE_LABELS) as [PipelineMode, string][]).map(
              ([value, label]) => ({ value, label }),
            )}
          />
        </Form.Item>

        {mode === 'team' && (
          <Form.Item name="team" label="Команда" rules={[{ required: true }]}>
            <Input placeholder="Название команды" />
          </Form.Item>
        )}

        <Form.Item name="enabled" label="Включено" valuePropName="checked">
          <Switch />
        </Form.Item>

        {previewBlock && <div style={{ marginTop: 8 }}>{previewBlock}</div>}

        {values && (
          <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 8 }}>
            Cron: <code>{buildCron(valuesToScheduleForm(values))}</code>
          </Typography.Text>
        )}
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 2: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors в новом файле.

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/sync/ScheduleEditorModal.tsx
git commit -m "feat(sync-fe): ScheduleEditorModal — билдер + edit + превью"
```

---

## Task 7: Frontend — переписать `SyncSchedule`

**Files:**
- Modify: `frontend/src/components/sync/SyncSchedule.tsx`

- [ ] **Step 1: Переписать компонент**

Write полностью (заменить содержимое файла):

```tsx
import { useState } from 'react';
import {
  Button, Card, Popconfirm, Space, Switch, Table, Tag, Tooltip, App,
} from 'antd';
import { PlusOutlined, DeleteOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getSchedules, updateSchedule, deleteSchedule, runScheduleNow,
  type SyncScheduleOut,
} from '../../api/syncSchedule';
import type { PipelineMode } from '../../api/syncRuns';
import ScheduleEditorModal from './ScheduleEditorModal';

const MODE_LABELS: Record<PipelineMode, string> = {
  quick: 'Быстрый',
  normal: 'Обычный',
  full: 'Полный',
  team: 'По команде',
};

export default function SyncSchedule() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const { data: schedules = [], isLoading } = useQuery({
    queryKey: ['sync', 'schedule'],
    queryFn: getSchedules,
  });

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<SyncScheduleOut | null>(null);

  const openCreate = () => { setEditing(null); setEditorOpen(true); };
  const openEdit = (row: SyncScheduleOut) => { setEditing(row); setEditorOpen(true); };
  const closeEditor = () => setEditorOpen(false);
  const onSaved = () => {
    qc.invalidateQueries({ queryKey: ['sync', 'schedule'] });
    notification.success({ title: editing ? 'Расписание обновлено' : 'Расписание создано' });
  };

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateSchedule(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'schedule'] }),
    onError: (e) =>
      notification.error({ title: 'Ошибка', description: (e as Error).message }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSchedule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'schedule'] }),
    onError: (e) =>
      notification.error({ title: 'Ошибка удаления', description: (e as Error).message }),
  });

  const runNowMut = useMutation({
    mutationFn: (id: string) => runScheduleNow(id),
    onSuccess: () => {
      notification.success({ title: 'Запущено' });
      qc.invalidateQueries({ queryKey: ['sync', 'runs'] });
    },
    onError: (e) =>
      notification.error({ title: 'Ошибка запуска', description: (e as Error).message }),
  });

  const stop = (e: React.MouseEvent | React.SyntheticEvent) => e.stopPropagation();

  const columns = [
    {
      title: 'Название',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Расписание',
      dataIndex: 'description',
      key: 'description',
      render: (desc: string, r: SyncScheduleOut) => (
        <Tooltip title={r.cron_expr}>
          <span>{desc}</span>
        </Tooltip>
      ),
    },
    {
      title: 'Режим',
      dataIndex: 'mode',
      key: 'mode',
      render: (v: PipelineMode) => <Tag>{MODE_LABELS[v] ?? v}</Tag>,
    },
    {
      title: 'Команда',
      dataIndex: 'team',
      key: 'team',
      render: (v: string | null) => v ?? <span style={{ color: '#888' }}>—</span>,
    },
    {
      title: 'Вкл',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (v: boolean, r: SyncScheduleOut) => (
        <span onClick={stop}>
          <Switch
            checked={v}
            size="small"
            loading={toggleMut.isPending}
            onChange={(checked) => toggleMut.mutate({ id: r.id, enabled: checked })}
          />
        </span>
      ),
    },
    {
      title: '',
      key: 'actions',
      render: (_: unknown, r: SyncScheduleOut) => (
        <Space size={4} onClick={stop}>
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            loading={runNowMut.isPending}
            onClick={() => runNowMut.mutate(r.id)}
          >
            Запустить
          </Button>
          <Popconfirm
            title="Удалить расписание?"
            okText="Да"
            cancelText="Нет"
            onConfirm={() => deleteMut.mutate(r.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="Расписание автозапуска"
      size="small"
      extra={
        <Button size="small" icon={<PlusOutlined />} onClick={openCreate}>
          Добавить
        </Button>
      }
    >
      <Table<SyncScheduleOut>
        dataSource={schedules}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        onRow={(row) => ({
          onClick: () => openEdit(row),
          style: { cursor: 'pointer' },
        })}
      />

      <ScheduleEditorModal
        open={editorOpen}
        schedule={editing}
        onClose={closeEditor}
        onSaved={onSaved}
      />
    </Card>
  );
}
```

- [ ] **Step 2: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: всё PASS. Если есть unused imports / types — поправить.

- [ ] **Step 3: Ручной браузер-смок**

Backend running: `py -3.10 -m uvicorn app.main:app --reload --port 8000`
Frontend running: `cd frontend && npm run dev`

Открыть `/sync` → вкладка «Расписание». Проверить вручную:
1. Кнопка «Добавить» → modal. Создать каждый из 8 типов (минуты, часы, ежедневно, будни, выходные, дни недели, еженедельно, cron). Проверить: alert с описанием + 3 запуска появляется. Сохранение работает.
2. В таблице — описание + tooltip cron при hover.
3. Клик по строке → modal с предзаполненными полями (тип распознан). Изменить → Сохранить → таблица обновилась.
4. Switch Вкл/Выкл, Запустить, Удалить — не открывают modal (stopPropagation).
5. Невалидный cron в режиме «Произвольно» → preview показывает ошибку.

Если что-то не работает — fix inline и re-test.

- [ ] **Step 4: Запустить backend regression**

Run: `py -3.10 -m pytest tests/ -k "sync or schedule" --tb=short`
Expected: всё PASS.

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/components/sync/SyncSchedule.tsx
git commit -m "feat(sync-fe): таблица — описание+tooltip, клик-edit, общий editor modal"
```

---

## Task 8: Release note + финальный smoke

**Files:**
- Run: `scripts/release_note.py`

- [ ] **Step 1: Добавить release note**

Run:
```bash
py -3.10 scripts/release_note.py add --category improvement --title "Удобный редактор расписаний синхронизации" --body "Cron-выражение в /sync → Расписание заменено на типизированный билдер (минуты, часы, ежедневно, будни, выходные, дни недели, еженедельно). Существующие расписания можно редактировать по клику. В таблице теперь видно описание расписания и 3 ближайших запуска."
```

(Если флаги отличаются — посмотреть `release_note.py --help` и адаптировать.)

- [ ] **Step 2: Финальный полный прогон тестов**

Run: `py -3.10 -m pytest tests/ -x --tb=short`
Expected: всё PASS.

- [ ] **Step 3: Финальный lint + build фронта**

Run: `cd frontend && npm run lint && npm run build`
Expected: всё PASS.

- [ ] **Step 4: Коммит + push**

```bash
git status
git add -A
git commit -m "chore: release note для удобного редактора расписаний"
git push origin redesign/aurora
```

---

## Self-Review Notes

**Spec coverage:**
- 8 типов расписания → Task 5 (cronBuilder) + Task 6 (UI) + Task 1 (backend humanize)
- Edit существующих → Task 6 (Modal принимает `schedule`) + Task 7 (клик строки)
- Превью 3 запусков → Task 1 (next_runs) + Task 3 (endpoint) + Task 6 (UI)
- Описание в таблице → Task 2 (computed field) + Task 7 (колонка с Tooltip)
- Cron fallback → Task 5 (`type='cron'`) + Task 6 (Input)

**Type consistency:** `ScheduleType`, `ScheduleForm`, `SchedulePreviewResponse`, `SyncScheduleOut.description` — определены в Task 4-5, используются в Task 6-7 с теми же сигнатурами.

**Гранулярность:** каждый шаг 2-5 мин: read/write test/run/implement/run/commit. Backend задачи TDD-стиль с failing-first.
