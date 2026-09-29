# Видео-инструкции (пилот) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Обезличенная демо-база, робот-съёмка двух роликов (Playwright + слой «режиссёра»), показ роликов в справке и в «Первых шагах».

**Architecture:** Локальный скрипт строит `data/demo.db` из локальной базы (обезличивание по отражённой схеме + проверка утечек). Отдельная конфигурация Playwright поднимает сервер на копии демо-базы и снимает сценарии; готовые `.webm` + обложки лежат в `frontend/public/help-videos/`. Фронт показывает их модальным окном по ссылкам `video:<id>` в markdown справки и по кнопке в панели.

**Tech Stack:** Python 3.10 (sqlite3 + SQLAlchemy Core reflection), pytest; Playwright (уже в devDependencies), React 19 / AntD 6.3.

Spec: `docs/superpowers/specs/2026-09-29-help-videos-design.md` — читать целиком перед любой задачей.

Рабочая копия: `D:\ClaudeDev\JiraAnalysis\.worktrees\onboarding`, ветка `feature/help-videos`. Windows, `py -3.10`. Никогда не трогать `D:\ClaudeDev\JiraAnalysis` (другая сессия), не использовать `git stash`, коммитить явными путями.

---

### Task 1: Обезличенная демо-база

**Files:**
- Create: `scripts/demo_db/__init__.py` (пустой), `scripts/demo_db/fake_data.py` (списки фамилий/имён, генератор названий задач, буквы команд), `scripts/demo_db/anonymize.py`, `scripts/demo_db/leak_check.py`, `scripts/demo_db/build_demo_db.py`
- Test: `tests/test_demo_db_anonymize.py`

Устройство:
- `anonymize.anonymize(conn: sqlite3.Connection, *, primary_team: str) -> Sensitive` — работает на сыром sqlite-соединении по отражённой схеме (`PRAGMA table_info` / `sqlite_master`), чтобы покрыть и колонки, неизвестные моделям ветки. Возвращает набор исходных чувствительных строк для проверки утечек.
- Порядок: (1) собрать словари соответствий из структурных источников (сотрудники, пользователи, поля ФИО задач, снимки сценариев, имена команд из всех мест, группы, проекты, заказчики бэклога/снимков, спринты/релизы); (2) колоночные правила — заменить целиком (названия задач, e-mail, учётки, ключи), очистить свободный текст, удалить таблицы из списка «удалить целиком»; (3) финальный проход по всем текстовым колонкам всех таблиц: замена исходных строк из словаря (длинные первыми; регэксп по ключам задач `\b(KEY)-(\d+)\b`) — так же попадают в JSON-строки (`selected_teams`, `participating_teams`, `team_set_json`, `payload_json` и т. п.).
- Не трогать справочники из спеки (категории, роли, причины отсутствий, виды нормированных работ, метрики KPI, статусы/типы/приоритеты, производственный календарь, заметки «Что нового», служебные поля: id, коды, даты, числа, `alembic_version`).
- Секреты в `app_settings`: значения ключей, содержащих `token|password|secret|api_key|apikey|credential|jira_email|confluence`, → пусто; ключ адреса Jira (найти по коду `app/services` / `app/models/CLAUDE.md`) → `https://jira.example.com`.
- `leak_check.check(conn, sensitive) -> list[str]` — находки «таблица.колонка: фрагмент»; ищет исходные строки (ФИО целиком, фамилии ≥5 символов, e-mail, команды, группы, ключи проектов как `\bKEY-\d+`, названия проектов, заказчиков, домен Jira) без учёта регистра во всех текстовых колонках + шаблоны: e-mail не на `@example.com`, `atlassian.net`.
- `build_demo_db.py --source <db> --out <db> [--primary-team "..."]`: sqlite backup-копия исходника (открыт `mode=ro`) → `anonymize` → `leak_check` (находки → печать до 50 строк, удалить выход, код 1) → демо-пользователь (`demo@example.com`, пароль `demo12345` через `app.core.security.hash_password`, роль `manager`, `selected_teams=["Команда Альфа"]`, `last_seen_release_version` = самая свежая версия из `release_notes`, `onboarding={"auto_opened": true}`) → `VACUUM` → печать сводки (сколько людей/команд/задач обезличено).
- Производительность: 115k задач — обновлять пакетно (`executemany`), в одной транзакции на таблицу.

- [ ] **Step 1: Тесты** — `tests/test_demo_db_anonymize.py` строит маленькую sqlite-базу в `tmp_path` через `Base.metadata.create_all` (движок на файл), кладёт: 2 сотрудника с ФИО и e-mail, участие в команде «Команда 1С (ERP - Товарный учет)» и «Команда Х», пользователь с `selected_teams` JSON этих команд, проект `ERPTU` c задачами `ERPTU-1`, `ERPTU-2` (summary с реальным текстом, description, assignee_display_name = ФИО сотрудника, team, participating_teams JSON), связь задач, бэклог с customer и title, сценарий с командой, комментарий, настройка с токеном и адресом `https://itgri.atlassian.net`. Проверяет после `anonymize`: одно ФИО → одно вымышленное в `employees.display_name` и `issues.assignee_display_name`; команда в `employee_teams`, `issues.team`, JSON `users.selected_teams` и `participating_teams` заменена одинаково, «Команда 1С (ERP - Товарный учет)» → «Команда Альфа»; ключи `ERPTU-1` → `PRA-1` и `projects.key` → `PRA`; summary заменён, description пуст; комментарий пуст; токен пуст; адрес Jira `https://jira.example.com`; `leak_check` → пусто. Отдельный тест: подложить исходную фамилию в `issues.summary` после анонимизации → `leak_check` находит.
- [ ] **Step 2:** запустить — падают. **Step 3:** реализовать. **Step 4:** зелёные; `ruff check scripts/demo_db tests/test_demo_db_anonymize.py`.
- [ ] **Step 5: Боевой прогон** — `py -3.10 scripts/demo_db/build_demo_db.py --source D:/ClaudeDev/JiraAnalysis/data/jira_analytics.db --out data/demo.db` (исходник только читать!). Проверка утечек должна пройти; если находит — доработать правила, не ослабляя проверку. Затем схема ветки: `DATABASE_URL=sqlite:///./data/demo.db py -3.10 -m alembic stamp --purge pq07_assignment_opo_part && ... alembic upgrade head` (локальная база уже на миграциях параллельной ветки; для ветки ставим её базу и применяем свою миграцию). Проверить выборочно глазами 20 задач, 10 сотрудников, список команд.
- [ ] **Step 6: Commit** `feat(help-videos): обезличенная демо-база для съёмки`.

### Task 2: Робот-съёмка двух роликов

**Files:**
- Create: `frontend/playwright.videos.config.ts`, `frontend/help-videos/global-setup.ts`, `frontend/help-videos/director.ts`, `frontend/help-videos/absence-add.video.ts`, `frontend/help-videos/categorize-issue.video.ts`
- Modify: `frontend/package.json` (скрипт `"videos": "playwright test -c playwright.videos.config.ts"`)
- Output (commit): `frontend/public/help-videos/absence-add.webm|.jpg`, `categorize-issue.webm|.jpg`

- Конфигурация по образцу `frontend/playwright.config.ts`: webServer — бэкенд `py -3.10 -m uvicorn app.main:app --port 8012` с `DATABASE_URL=sqlite:///./data/demo_run.db`, `DEBUG=false`, `JWT_SECRET_KEY=<32+ символа>`, `CORS_ORIGINS=http://127.0.0.1:5176`; фронт `npm run dev -- --port 5176 --strictPort` с `VITE_API_BASE_URL=http://127.0.0.1:8012/api/v1`. `reuseExistingServer: false`. `globalSetup` копирует `data/demo.db` → `data/demo_run.db` (нет демо-базы — понятная ошибка «сначала build_demo_db.py»). `use: { viewport: 1440×900, video: { mode: 'on', size: 1440×900 }, locale: 'ru-RU' }`, `workers: 1`, `retries: 0`, таймаут теста 120 с. Расписания синхронизации в копии выключить (как в живой проверке: `sync_schedule.enabled=0`) — в global-setup.
- `director.ts` — `class Director { constructor(page) ; install() ; caption(text, ms?) ; point(locator) ; click(locator, caption?) ; type(locator, text, caption?) ; pause(ms) }`. `install()` через `page.addInitScript` добавляет слой: курсор (круг 22px с тенью, `pointer-events:none`, z-index максимум), подсветка (рамка вокруг прямоугольника элемента), плашка подписи внизу по центру (шрифт 22px, тёмный фон, скруглённая). `point` — плавный переезд курсора к центру элемента (CSS transition ~600 мс) + подсветка. `click` — point → подпись → пауза ~900 мс → «нажатие» (кратко уменьшить курсор) → реальный `locator.click()` → пауза. Тексты подписей — короткие, по-русски, без технических слов.
- Сценарий начинается с входа демо-пользователем на `/login` (вход не в кадре не требуется, но первые кадры — уже нужная страница: после входа `page.goto` раздела, затем подпись-заголовок ролика «Как внести отпуск»), заканчивается видимым результатом + подписью «Готово» на 2 с. Длительность 15–40 с.
- После теста: закрыть контекст, `page.video().saveAs('public/help-videos/<id>.webm')`; обложка — `page.screenshot({ path: 'public/help-videos/<id>.jpg', type: 'jpeg', quality: 80 })` в момент заголовка.
- Селекторы — по видимым подписям и имеющимся `data-tour` / `data-testid`; не добавлять новые атрибуты в страницы без необходимости (если добавили — только атрибут).
- Проверка: `cd frontend && npm run videos` → два файла; размер каждого < 8 МБ; извлечь кадры `ffmpeg -i x.webm -vf fps=1/3 data/frames/x-%02d.png` и просмотреть — подписи читаются, курсор виден, реальных имён нет.
- [ ] Commit `feat(help-videos): робот-съёмка роликов «Внести отпуск» и «Отнести задачу к категории»` (конфиг, режиссёр, сценарии, скрипт, два ролика с обложками).

### Task 3: Показ роликов

**Files:**
- Create: `frontend/src/help-videos/videos.ts`, `frontend/src/help-videos/VideoModal.tsx`, `frontend/src/help-videos/VideoLink.tsx`
- Modify: `frontend/src/components/shared/HelpDrawer.tsx` (компонент `a`: `href` вида `video:<id>` → `VideoLink`), `docs/help/capacity.md`, `docs/help/categories.md` (раздел «Видео» со ссылками), `frontend/src/onboarding/steps.ts` (поле `videoId?: string` у шага: `absences` → `absence-add`, `categorization` → `categorize-issue`), `frontend/src/onboarding/OnboardingDrawer.tsx` (кнопка «Видео» у шага с `videoId`)

- `videos.ts`: `export const VIDEOS: Record<string, { title: string; src: string; poster: string }>` — пути от корня сайта `/help-videos/<id>.webm` (с учётом `import.meta.env.BASE_URL`).
- `VideoModal`: AntD `Modal` шириной `min(1400px, 94vw)`, без футера, `destroyOnHidden` (сверить название пропа в AntD 6.3 — без устаревших), внутри `<video src autoPlay loop muted controls playsInline style={{ width: '100%' }} poster>`. Неизвестный id — ничего не рендерить.
- `VideoLink`: карточка «▶ Название» с обложкой (ширина ~260px) — клик открывает `VideoModal`. Модалка поверх панели справки/«Первых шагов» (z-index выше Drawer — проверить).
- Проверка: `npm run lint`, `npm run build`, `npx playwright test e2e/onboarding.spec.ts`; вручную — ролик открывается из справки «Ресурсы» и из «Первых шагов».
- [ ] Commit `feat(help-videos): ролики в справке и в «Первых шагах»`.
