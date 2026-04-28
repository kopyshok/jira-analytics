# Глобальная реструктуризация — хэндофф для новой сессии

## Контекст

Начата глобальная реструктуризация по 4 направлениям. Обсуждалось 2026-04-27.

---

## Дорожная карта (порядок выполнения)

| # | Тема | Статус | Артефакты |
|---|---|---|---|
| **4** | Единый хаб синхронизации + pipeline + scheduler + событийная инвалидация | **✅ ЗАВЕРШЕНО** (498 тестов зелёные, миграция 035, build ОК, 2026-04-27) | spec: `2026-04-27-sync-consolidation-design.md`, plan: `2026-04-27-sync-consolidation.md` |
| **1** | Кросс-секционная реактивность (ручные правки → авто-update везде) | **✅ ЗАВЕРШЕНО** (511 тестов зелёные, build ОК, 2026-04-27) | spec: `2026-04-27-cross-sectional-reactivity-design.md`, plan: `2026-04-27-cross-sectional-reactivity.md` |
| **3** | Пересмотр зависимостей показателей (смена исполнителя в Бэклоге → обновление Сценариев и наоборот) | **✅ ЗАВЕРШЕНО** (входит в п.1: entity_changed из planning/backlog/issues endpoints + pipeline, 2026-04-27) | — |
| **2** | Публикация + мульти-тенант (другие пользователи со своими командами и настройками) | 🔶 Вариант А ЗАВЕРШЁН (532 теста зелёные, build ОК, 2026-04-28). Вариант Б (серверный middleware) — следующий этап | spec: `2026-04-27-auth-multiuser-design.md`, plan: `2026-04-27-auth-multiuser.md` |

---

## Что делать в новой сессии

### ~~Шаг 1~~ ✅ ВЫПОЛНЕНО — план п.4 (sync consolidation)

498 тестов зелёные, миграция 035 применена, frontend build успешен.
Phase 6 (удаление deprecated + `/sync-old`) — отдельный PR через 1 неделю.

### ~~Шаг 2~~ ✅ ВЫПОЛНЕНО — п.1 + п.3 (реактивность)

511 тестов зелёные, build успешен. Последний коммит: `e948774`.

Что реализовано:
- Frontend: тип `entity_changed` расширен до `{ entity?: string; entities?: string[] }`; `invalidateForEntity()` дополнена кейсами `backlog`, `planning`, `capacity`, `analytics`
- Backend: 11 мутирующих endpoints публикуют `entity_changed` после `db.commit()` (planning: 6, backlog: 4, issues: 1)
- Pipeline: `PipelineOrchestrator` собирает затронутые entity от успешных стадий → публикует `entity_changed` после `pipeline_done`
- Тесты: 11 endpoint-тестов + 2 pipeline-теста; `testclient_db_session` (StaticPool) добавлен в conftest

Phase 6 (удаление legacy карточки «Синхронизация задач (legacy)» + deprecated `/sync-old`) — отдельный PR ~2026-05-04.

Глобальный фильтр команды — отдельная задача (зафиксирована в memory).

### ~~Шаг 3~~ 🔶 ЧАСТИЧНО ВЫПОЛНЕНО — п.2 Вариант А (auth + multi-user)

532 тестов зелёные, build успешен. Последний коммит: `a38838f`.

Что реализовано (Вариант А — фронтенд-защита):
- User model + migration 036_users (admin/super_manager/manager)
- bcrypt + JWT: `app/core/security.py`, `python-jose`, `passlib[bcrypt]==1.7.4` + `bcrypt==4.0.1`
- Endpoints: `POST /auth/login`, `GET /auth/me`, `/admin/users/` CRUD
- `scripts/create_admin.py` — seed первого admin
- Frontend: AuthProvider + useAuth, LoginPage, route protection (AuthLayout + ProtectedRoute)
- Header: display_name + logout button
- Settings → вкладка «Пользователи» (только для admin)
- Auto team-filter: при логине manager редирект `/?teams={default_team}`

Известные gaps (Вариант Б):
- Нет `Depends(get_current_user)` на обычных endpoints — всё открыто
- Нет refresh tokens (access token 8ч)
- `download()` в client.ts без auth header
- `UserUpdate.default_team` нельзя сбросить в null

### Шаг 4 (следующий) — Вариант Б: серверный middleware

Добавить `Depends(get_current_user)` на все endpoints + `Depends(require_admin)` на admin-endpoints.
Refresh tokens опционально. Rate limiting на `/auth/login`.

---

## Ключевые файлы

| Артефакт | Путь |
|---|---|
| Спек синхронизации | `docs/superpowers/specs/2026-04-27-sync-consolidation-design.md` |
| План синхронизации | `docs/superpowers/plans/2026-04-27-sync-consolidation.md` |
| Спек реактивности | `docs/superpowers/specs/2026-04-27-cross-sectional-reactivity-design.md` |
| План реактивности | `docs/superpowers/plans/2026-04-27-cross-sectional-reactivity.md` |
| Спек auth | `docs/superpowers/specs/2026-04-27-auth-multiuser-design.md` |
| План auth | `docs/superpowers/plans/2026-04-27-auth-multiuser.md` |
| Этот хэндофф | `docs/superpowers/RESTRUCTURE_HANDOFF.md` |

---

## Критичные особенности проекта для исполнителя плана

| Особенность | Действие |
|---|---|
| Windows + uvicorn `--reload` не подхватывает изменения бэка | После каждой правки бэка: kill PID :8000 + перезапуск |
| AntD 6: нотификации используют `title`, не `message` | `message` deprecated в AntD 6.3 |
| Имена полей моделей: `Issue.issue_type`, `Category.label/is_system` | Не `name/is_builtin` |
| Последняя миграция: `036_users.py` | Новая миграция = `037_*.py` |
| pytest: запускать через `py -3.10 -m pytest` (не `pytest`) | Дефолтный Python 3.14 без зависимостей |
| Commit + push в origin/main после каждой завершённой фазы | Без лишних вопросов |
| Brainstorm-сессии: Opus формулирует, Sonnet через Agent рисует HTML-mockup | |

---

## Текущее состояние репозитория (2026-04-27)

- Ветка: `main`
- Последний коммит: `a38838f` — `fix(auth): store token before getMe() call in LoginPage`
- БД: SQLite `data/dev.db`, последняя миграция `036_users`
- Тестов: 532 зелёных
- CI: pre-existing red на main (SyncPage lint, hierarchy_rules test DB errors, test_sync_service mock drift, 3 e2e flakies) — не трогать, не наша работа
- Целевой режим: **многопользовательский** — все архитектурные решения принимать с учётом нескольких одновременных пользователей
