# Поток 4. Мультикомандные RFA: кто уже взял в работу — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Шаги — чекбоксы (`- [ ]`).

**Goal:** у мультикомандной RFA и её эпиков видно, какие команды уже взяли работу: плашка «в работе у K из N»
на «Целевых задачах» и в строках сценария, над сценарием — предупреждение «⚠ N задач уже взяли соседи, у вас не
включены» и переключатель «Показать только их».

**Architecture:** одна служба только для чтения `app/services/multi_team_progress.py` считает по набору RFA статус
каждой команды-участницы (взят / не взят / нет эпика + сценарии) тремя запросами на любой объём. Эндпоинты списка
бэклога и списка раскладок сценария дописывают результат в строки (`multi_team_progress`). Фронт: компонент-плашка
`MultiTeamProgressTag`, чистые хелперы `utils/multiTeamProgress.ts` (цвет, «соседи взяли»), баннер
`NeighborsTakenBanner` над таблицей сценария. Схема БД не меняется (данные производные).

**Tech Stack:** FastAPI, SQLAlchemy 2, pytest; React 19 + AntD 6, vitest.

Спека: `docs/superpowers/specs/2026-10-04-q4-improvements-pack-design.md`, раздел «Поток 4».

## Правила расчёта (зафиксировано)

- Мультикомандная RFA — `issue_is_multi_team` (участников > 1 или единственный ≠ команде RFA).
- Участники: `participating_teams` (в порядке Jira) + команда самой RFA + команды, у которых под RFA есть эпик, хотя
  в списке их нет (иначе работа команды, заведшей эпик без отметки в Jira, пропадает из плашки — так в рабочей базе у
  RFA-5011).
- «Эпик команды» — любой не отменённый (`CANCEL_STATUSES`) прямой потомок RFA с этой командой, кроме листовых задач по
  правилам иерархии (`is_planning_leaf`: задачи и подзадачи OS/PMD); контейнеры любого типа (ИТ-задача) — эпики.
- `взят` — хотя бы один эпик команды включён (`included_flag`) в утверждённый сценарий своей команды текущего или
  будущего квартала; черновики, прошлые кварталы и сценарии другой команды не считаются.
- `выполнен` (решение пользователя 04.10) — иначе, если хотя бы один эпик команды закрыт в Jira (категория статуса
  «done», не отменён); подпись — квартал последнего утверждённого сценария своей команды с этим эпиком, если был.
- `не взят` — эпик есть, но ни то, ни другое. `нет эпика` — эпиков нет.
- K — число команд со статусом `взят` или `выполнен`, N — число участников. «Соседи взяли» — у другой команды
  `взят` или `выполнен`; предупреждение над сценарием — только в черновике.
- Строка — RFA сама (если мультикомандная) либо эпик мультикомандной RFA (родитель). Своя команда строки — `Issue.team`.
- Архив «Целевых задач» плашку не получает (там закрытые и отменённые).

---

### Task 1: Служба расчёта

**Files:** Create `app/services/multi_team_progress.py`; Modify `app/services/backlog_service.py`
(`teams_make_multi_team` — признак по полям, `issue_is_multi_team` зовёт его); Test
`tests/services/test_multi_team_progress.py`.

- [ ] Тесты (сначала красные): 3 команды, взяла 1 → K=1, N=3, статусы taken/not_taken/no_epic, у взятой — имя и
  квартал сценария; участник без эпика → no_epic; утверждённый сценарий прошлого квартала не считается, текущего и
  будущего — считается; черновик не считается; `included_flag=False` не считается; команда RFA — участник; эпик
  команды вне списка участников — участник; отменённый эпик не считается; немультикомандная RFA — нет в ответе;
  число запросов не растёт с числом RFA (≤ 3 + чанки).
- [ ] Реализация: `multi_team_progress(db, rfa_issue_ids, today=None) -> dict[str, RfaProgress]`,
  `row_progress(progress_by_rfa, issue_id, parent_id, team) -> RowProgress | None`.
- [ ] `py -3.10 -m pytest tests/services/test_multi_team_progress.py -q` зелёный → commit.

### Task 2: Строки «Целевых задач»

**Files:** Create `app/schemas/multi_team_progress.py` (`MultiTeamProgressOut`); Modify `app/api/endpoints/backlog.py`
(поле у `BacklogItemResponse` и `BacklogChildSchema`, расчёт в `list_backlog_items` одним вызовом); Test
`tests/test_backlog_multi_team_progress.py`.

- [ ] Тесты: у RFA и у её эпика (дочерняя строка и строка-корень с родителем вне списка) — одинаковые K/N и свой
  статус; у обычной задачи — `null`; архив — `null`; число запросов списка не растёт с числом мультикомандных RFA.
- [ ] Реализация → тесты зелёные → commit.

### Task 3: Строки сценария

**Files:** Modify `app/api/endpoints/planning.py` (поле `AllocationResponse.multi_team_progress`, расчёт в
`list_scenario_allocations`); Test `tests/test_api_planning_multi_team_progress.py`.

- [ ] Тесты: строка эпика мультикомандной RFA в черновике команды Б, команда А взяла → K=1, своя команда
  `not_taken`; запросы не растут с числом строк.
- [ ] Реализация → зелёные → commit.

### Task 4: Фронт — плашка

**Files:** Create `frontend/src/utils/multiTeamProgress.ts` (+ `.test.ts`),
`frontend/src/components/shared/MultiTeamProgressTag.tsx`; Modify `frontend/src/types/api.ts`,
`frontend/src/pages/BacklogPage.tsx` (тег в строке, перенос поля в `adaptChildren`),
`frontend/src/components/planning/BacklogAllocRow.tsx` (одна вставка рядом с «переоценка»).

- [ ] vitest: тон плашки (K=0 серый; 0<K<N — яркий у не взявших, нейтральный у взявших; K=N зелёный),
  «соседи взяли» (`neighborsTaken`), подписи статусов.
- [ ] Компонент: AntD `Tag` + `Tooltip` со списком команд; цвета — токены темы `--warn`/`--good`/`--text-muted`.

### Task 5: Фронт — предупреждение над сценарием

**Files:** Create `frontend/src/components/planning/NeighborsTakenBanner.tsx`; Modify
`frontend/src/pages/PlanningPage.tsx` (счёт строк, переключатель, фильтр секций — минимальные точки касания:
соседний поток правит заголовки таблицы).

- [ ] Строки «соседи взяли, у вас не включено»: `!included && neighborsTaken(progress)`.
- [ ] Предупреждение показывается при N>0; переключатель «Показать только их» оставляет только эти строки.

### Task 6: Сверка и финальный прогон

- [ ] Копия рабочей базы в `data/` (не коммитить): вывести несколько реальных мультикомандных RFA со статусами на
  IV кв. 2026.
- [ ] `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py -p no:cacheprovider`; `npm run build`;
  `npx eslint <изменённые>`; `npx vitest run <тесты>`.
