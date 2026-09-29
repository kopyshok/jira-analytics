# Личная вовлечённость и личные нормированные работы — план

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Личная настройка сотрудника «с квартала»: вовлечённость (главнее задачи и справочника) и свои проценты нормированных работ — в раскладке, брони других команд, «Загрузке по дням», запасе нормированных работ и базе сценария.

**Architecture:** Модели + чтение `app/services/personal_settings.py` + CRUD API; затем параллельно — учёт вовлечённости (планировщик, брони, диаграмма, расшифровка), учёт процентов (запас, база сценария), интерфейс (панель в Сценариях), справка.

**Спека:** [../specs/2026-09-29-personal-involvement-design.md](../specs/2026-09-29-personal-involvement-design.md).

## Общие правила

- Рабочая копия: `D:\ClaudeDev\JiraAnalysis-personal` (ветка `feature/personal-involvement`). Не трогать `D:\ClaudeDev\JiraAnalysis` — там работают другие сессии.
- Python: `py -3.10`. Тесты: `py -3.10 -m pytest <пути> -q -p no:cacheprovider`; полный прогон `--ignore=tests/api/test_llm.py`.
- Фронт: `cd frontend && npx tsc -b && npx eslint <файлы> && npx vitest run src`.
- Не коммитить: коммитит координатор после ревью фазы.
- Перед исследованием кода — `graphify query "<вопрос>"` (граф в основной копии: `D:\ClaudeDev\JiraAnalysis\graphify-out`; может быть устаревшим).
- Роли сотрудников — коды реестра (`dev`, `analyst`, `RP`, `consultant`, `qa`); фазы вовлечённости — `analyst`, `dev`, `qa`, `opo`.
- Фабрики тестов: `tests/services/xteam_factory.py`, `tests/services/normed_factory.py`.

## Фазы

- **Фаза 0:** задача 1.
- **Фаза 1 (параллельно):** задачи 2, 3, 4, 5.
- Ревью, полный прогон, коммит, push, заметки «Что нового».

### Task 1: Модели, миграция, сервис чтения, API

**Files:** create `alembic/versions/pi01_personal_settings.py`, `app/models/employee_personal_setting.py`, `app/services/personal_settings.py`, `app/api/endpoints/personal_settings.py`; modify `app/models/__init__.py`, `app/api/router.py`, `app/api/endpoints/mandatory_work_types.py` (409 при удалении вида, используемого в личных процентах); tests `tests/test_migration_pi01_personal_settings.py`, `tests/services/test_personal_settings.py`, `tests/api/test_personal_settings_api.py`.

- [ ] Миграция (revises текущий head — узнать `py -3.10 -m alembic heads`), идемпотентная: пропускать уже существующие таблицы (`sa.inspect(bind).has_table`, офлайн-режим — без проверки). Таблицы по спеке 4.1. Тест: upgrade/downgrade/upgrade на временной SQLite (образец — `tests/test_migration_nw01_normed_reserve.py`), плюс «таблица уже создана create_all → upgrade проходит».
- [ ] Модели `EmployeePersonalSetting` (relationship `normed` → `EmployeePersonalNormed`, cascade delete-orphan) и `EmployeePersonalNormed`.
- [ ] Сервис:

```python
@dataclass(frozen=True)
class PersonalSetting:
    """Личная настройка сотрудника на квартал. involvement=None — как обычно;
    normed=None — по правилам роли, {} — нормированных работ нет."""
    involvement: Optional[float]
    normed: Optional[Dict[str, float]]

def personal_for(db, employee_ids, year, quarter) -> Dict[str, PersonalSetting]:
    """Последняя запись сотрудника с (год, квартал) ≤ заданного. Константа запросов."""
```

Запись без вовлечённости и с «по правилам роли» тоже возвращается (involvement=None, normed=None) — она перекрывает более раннюю. Тесты: выбор последней записи ≤ квартала; более поздняя запись «по правилам роли» отменяет раннюю; «свои» пустые → `{}`; запросов ≤ 3 на 10 сотрудников.
- [ ] API `/planning/personal-settings` (роутер как у `involvement_defaults`): GET `?team=` → `[{id, employee_id, employee_name, employee_role, effective_year, effective_quarter, involvement, normed_custom, normed: [{work_type_id, label, percent_of_norm}]}]` для сотрудников, состоявших в команде (`team_membership`), сортировка по имени, затем по кварталу; POST/PUT/DELETE; валидация по спеке 4.3 (сообщения по-русски); после записи — событие `entity_changed` с `planning` и `resource_planning` (как делают соседние эндпоинты — найти способ получить шину). Тесты API на CRUD и валидацию (422 на сумму > 100, на вид «Прочие/Чужие», 409 на дубль).
- [ ] `mandatory_work_types` delete → 409, если вид есть в личных процентах (тот же текст/стиль, что для периодов); тест.

### Task 2: Вовлечённость сотрудника везде

**Files:** modify `app/services/involvement_default_service.py`, `app/services/resource_planning_service.py`, `app/services/cross_team_occupancy.py`, `app/api/endpoints/resource_planning.py`; tests `tests/services/test_rp_personal_involvement.py` (+ правка существующих, если меняется сигнатура).

- [ ] `effective_for_phase(item, phase, defaults, personal: Optional[float] = None)` — `personal` первым.
- [ ] Планировщик: вовлечённость фазы с исполнителем берёт личную настройку исполнителя на квартал плана (`personal_for` один раз на расчёт, по всем людям плана). Все места, где вызывается `_involvement_for_phase` для фазы с сотрудником (основной цикл, части разбитых фаз, ОПЭ-части, пост-проходы), — с учётом исполнителя. Тестирование без исполнителя — как было.
- [ ] `cross_team_occupancy.external_bookings`: `involvement` брони — с личной настройкой сотрудника брони на квартал опорного плана брони. `base_other_share`: если у сотрудника личная вовлечённость — доля `1 − личная` вместо справочника.
- [ ] `resource_planning.py`: остаток дня в «Загрузке по дням» (`own_phases`) — с личной; `_effective_involvement` и расшифровка фазы: `involvement_source` = `"employee"` при личной (схема `PhaseCalcDetails.involvement_source`: добавить значение в комментарий/тип).
- [ ] Тесты: (1) разработчик с личной 100% при задаче 70% и справочнике 90% → фаза берёт 8 ч/день; (2) без личной — как раньше; (3) бронь в плане другой команды у человека с личной 100% → вовлечённость брони 1.0, остаток дня 0; (4) `base_other_share` с личной 100% → 0; (5) расшифровка фазы: источник `employee`.

### Task 3: Личные проценты в запасе и сценарии

**Files:** modify `app/services/normed_reserve.py`, `app/services/resource_base_service.py`; tests `tests/services/test_normed_reserve.py`, `tests/services/test_personal_normed_scenario.py`.

- [ ] `team_reserve`: заложено человека по виду = норма × (личный % если `normed` задан, иначе % роли). Виды, которых нет у роли, но есть в личных, — тоже строки роли. Остаток вида — людям роли пропорционально их заложенному по этому виду (сумма заложенного 0 → никому).
- [ ] `ResourceBaseService`: доля проектных часов человека `1 − Σ личных %` (только виды, уменьшающие запас), иначе как было (`_pool_share(role)`); в `compute_summary` часы видов работ по ролям — сумма по людям (личные проценты у кого есть), `pct_by_role` — как было (правило роли); разрез по группам — из тех же часов по людям; брони — как было.
- [ ] Тесты: пример спеки 5 (два разработчика, у одного «свои» 0%): запас «Технических задач» = 10% нормы второго; остатки видов у первого 0; `На бэклог` первого = вся норма; `compute()` посуточно — 8 ч/день у первого; без личных — все прежние тесты зелёные.

### Task 4: Интерфейс

**Files:** modify `frontend/src/components/planning/InvolvementDefaultsDrawer.tsx`, `frontend/src/hooks/useInvolvementDefaults.ts` (или новый `usePersonalSettings.ts`), `frontend/src/types/api.ts`, `frontend/src/api/resourcePlanning.ts` (`involvement_source` += `'employee'`), `frontend/src/components/resource-planning/sidebar/PhaseCalcSection.tsx`; new helper + vitest test in `frontend/src/utils/`.

- [ ] Заголовок панели «Вовлечённость и нормированные работы». Существующий раздел — «По ролям команды».
- [ ] Раздел «Сотрудники»: таблица (Сотрудник, С квартала «Q4 2026», Вовлечённость «100%» или «—», Нормированные работы: «по правилам роли» / «нет» / «Сопровождение 5% · Орг. вопросы 10%»), кнопки «изменить»/«удалить», «Добавить».
- [ ] Модальная форма: сотрудник (состав команды сценария — найти, откуда страница Сценариев берёт состав; не выдумывать новый запрос, если есть), год, квартал, вовлечённость в % (необязательно), переключатель «по правилам роли / свои», при «свои» — список видов работ (уменьшающих запас, активных) с процентами; при переключении на «свои» подставить проценты правил роли сотрудника из текущего сценария (если страница их уже загружает — взять оттуда), показывать сумму и предупреждать при > 100%.
- [ ] `PhaseCalcSection`: подпись источника «сотрудник» (рядом с существующими «задача»/«справочник команды»).
- [ ] Помощник форматирования «Нормированные работы» + vitest тест.
- [ ] Тексты — простым русским языком, без технических слов.

### Task 5: Справка и заметки

**Files:** `docs/help/planning.md` (панель вовлечённости — раздел «Сотрудники»), `docs/help/resource-planning.md` (вовлечённость: порядок «сотрудник → задача → справочник»; нормированные работы: личные проценты), `release_notes/drafts.json` (заметка `new`: «Личная вовлечённость и нормированные работы сотрудника»; порядок new → improvement → fix), `app/services/CLAUDE.md` (абзац о `personal_settings.py`, правки абзацев вовлечённости и `normed_reserve`).
