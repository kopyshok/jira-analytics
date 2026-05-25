# Обратная связь: баг-репорты и предложения

**Дата:** 2026-05-25
**Статус:** Design approved (без отдельного гейта user-review — PM сказал «пиши план и делай»)
**Тип:** Backend + Frontend feature

## Контекст

Готовим публикацию для команды компании. Многопользовательский режим уже включён (cookie auth + roles). Текущий механизм — `frontend/src/components/BugReportButton.tsx` + `frontend/src/utils/errorStore.ts`: плавающая кнопка копирует в буфер обмена markdown с последними 30 API-ошибками. Ограничения:

- Хранение только в памяти браузера — закрыл вкладку, потерял.
- Только API-ошибки. Нет описания «что юзер делал», нет консольных ошибок, нет приложений.
- Нет сервера → нет агрегации, нет модерации, нет очереди для Claude Code.
- Нет канала «предложить улучшение» — идеи теряются.

## Цель

1. **Баги** — собираются на сервере, админ выгружает разом все непрочитанные одним markdown-файлом, отдаёт в Claude Code на разбор.
2. **Идеи** — отдельный поток, видимый всем юзерам. Никаких голосований/комментов. Источник «мозгового штурма» для PM.

## Решения (зафиксированы при брейнсторме)

- **Два потока, одна таблица** (`kind` ∈ {`bug`, `idea`}). 80% полей общие; разные поля nullable.
- **Авто-сбор контекста для багов (уровень B):** URL, время, юзер, браузер/ОС, последние ~20 ошибок консоли, последние ~5 ошибочных HTTP-ответов, активная команда/период/тема. Скриншот — только опциональный аплоад файла.
- **Точка входа:** плавающая кнопка в углу (всегда видна) **И** пункт «Обратная связь» в шапке/меню (для возврата к своим обращениям + переход в админку).
- **Выгрузка багов:** чекбоксы + «Выгрузить выбранные» + быстрая «Выгрузить и пометить прочитанными — всё новое». Формат — единый markdown с разделителями `---`.
- **Идеи:** лента видимая всем юзерам, фильтр «мои / все», без лайков/комментов. Админ выгружает так же одним md.

## Архитектура

### Backend

#### Модель `FeedbackItem` (`app/models/feedback.py`)

Одна таблица `feedback_items`:

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | UUID String(36) PK | |
| `kind` | Enum(bug, idea) NOT NULL | дискриминатор |
| `author_id` | String(36) FK users.id NOT NULL | кто отправил |
| `title` | String(255) NOT NULL | короткий заголовок |
| `body` | Text NOT NULL | основное описание / суть идеи |
| `page_url` | String(2048) nullable | URL страницы в момент отправки |
| `read_at` | DateTime nullable | NULL = непрочитан, NOT NULL = прочитан админом |
| `read_by` | String(36) FK users.id nullable | кто отметил прочитанным |
| `created_at`, `updated_at` | TimestampMixin | стандарт |
| **Только bug:** | | |
| `steps_to_reproduce` | Text nullable | |
| `expected` | Text nullable | |
| `actual` | Text nullable | |
| `context_json` | Text nullable | JSON: browser/os/screen + console_errors[] + network_errors[] + active_team + active_period + theme |
| `attachments_json` | Text nullable | JSON: [{filename, mime, size, path}] |

Индексы:
- `(kind, read_at, created_at DESC)` — основной для админ-листа
- `(author_id, created_at DESC)` — для «мои обращения»

Без отдельных статусов «in-progress/done» — единственное состояние «прочитан / непрочитан». Дальнейший lifecycle обрабатывает Claude Code, тут хранилище.

Alembic-миграция в batch-режиме (SQLite).

#### Аплоад файлов

Один эндпоинт `POST /feedback/attachments` принимает multipart, сохраняет в `data/feedback_attachments/<uuid>.<ext>`, возвращает `{filename, mime, size, path}`. Лимит 5 МБ × 5 файлов на отправку. MIME whitelist: `image/*`, `application/pdf`, `text/plain`, `application/json`. Привязка к `FeedbackItem` через `attachments_json` (массив записей возвращённых от upload-endpoint). Это упрощает форму — аплоад идёт сразу, в момент отправки баг-репорта аплоадить уже не надо.

`GET /feedback/attachments/{id}` отдаёт файл (только автору + админам).

#### Сервис `FeedbackService` (`app/services/feedback_service.py`)

- `create_bug(author, payload) -> FeedbackItem`
- `create_idea(author, payload) -> FeedbackItem`
- `list_for_admin(kind, filter: unread|all|read, limit, offset) -> list[FeedbackItem]`
- `list_for_user(author_id, kind, scope: mine|all)` — для идей scope=all возвращает все, для багов scope=mine только свои.
- `mark_read(ids: list[str], reader_id: str) -> int`
- `mark_unread(ids: list[str]) -> int`
- `export_markdown(kind, ids: list[str] | None, only_unread: bool, mark_after: bool) -> str` — генерирует один md-файл; если `mark_after=True` атомарно отмечает выгруженные прочитанными.

#### Endpoints (`app/api/endpoints/feedback.py`)

Все требуют аутентификацию. Префикс `/feedback`.

| Метод | Путь | Кто | Назначение |
|-------|------|-----|-----------|
| POST | `/feedback/bugs` | любой авторизованный | создать баг |
| POST | `/feedback/ideas` | любой авторизованный | создать идею |
| POST | `/feedback/attachments` | любой авторизованный | upload файла |
| GET | `/feedback/attachments/{id}` | автор или admin | скачать файл |
| GET | `/feedback/my` | любой авторизованный | мои обращения (оба типа) |
| GET | `/feedback/ideas?scope=all` | любой авторизованный | публичная лента идей |
| GET | `/feedback/admin/bugs?filter=unread\|all` | **admin** | админ-список багов |
| GET | `/feedback/admin/ideas?filter=unread\|all` | **admin** | админ-список идей |
| POST | `/feedback/admin/mark-read` | **admin** | `{ids: [...]}` |
| POST | `/feedback/admin/mark-unread` | **admin** | `{ids: [...]}` |
| POST | `/feedback/admin/export` | **admin** | `{kind, ids?: [...], only_unread: bool, mark_after: bool}` → `text/markdown` download |

`admin` = `current_user.role == UserRole.admin`. Существующая зависимость `require_admin` (есть в `admin_users.py`).

### Frontend

#### Замена существующего `BugReportButton`

Существующий компонент перерабатывается, **errorStore сохраняется** — расширяется до ring-buffer консольных ошибок + сетевых ошибок (уже есть API errors → добавить console errors через `window.addEventListener('error')` + `console.error` wrap).

Плавашка теперь открывает **не модалку с clipboard**, а полноразмерный drawer с формой «Сообщить об ошибке» + переключатель типа «Баг / Идея». При создании отправляет в API.

#### Точки входа

1. **FloatButton** — остаётся в `App.tsx`, открывает drawer с формой.
2. **Пункт меню «Обратная связь»** в шапке — открывает страницу `/feedback`.
3. **Админ-вкладка** в `/settings` → `feedback` (admin-only).

#### Страница `/feedback` (для всех юзеров)

Две вкладки в URL:
- **`my`** — мои баги + мои идеи (стек, по дате)
- **`ideas`** — лента всех идей (для просмотра чужих перед отправкой своей)

Кнопка «Создать» открывает тот же drawer что и плавашка.

#### Страница `/settings` → вкладка «Обратная связь» (admin-only)

Две подвкладки:
- **Баги**
- **Идеи**

Каждая — таблица:
- Чекбокс
- Заголовок + автор + дата
- Статус (точка непрочитан / галка прочитан)
- Превью body
- Кнопка «открыть» → drawer с полным содержимым + контекстом + аплоадами

Фильтр сверху: «Только новые» / «Все».

Кнопки в шапке таблицы:
- «Выгрузить выбранные» — md только по checked, без отметки прочитанными.
- «Выгрузить новые и отметить прочитанными» — все непрочитанные одним md, атомарно `mark_after=True`.
- «Отметить прочитанными» — checked → read без выгрузки.
- «Снять отметку» — обратно.

#### Drawer формы отправки

Сверху переключатель «Баг / Идея» (`Radio.Group`).

**Для бага:**
- Заголовок (required)
- Что случилось / описание (required, textarea)
- Шаги воспроизведения (optional, textarea, hint «по шагам что нажимали»)
- Ожидание (optional)
- Факт (optional)
- Приложения (Upload, до 5 файлов 5 МБ)
- Дисклеймер «Автоматически прикрепится: URL страницы, браузер, активная команда/период, последние ошибки из консоли и сети»
- Кнопка «Отправить» → POST, успех → toast + закрыть drawer

**Для идеи:**
- Заголовок (required)
- Описание (required, textarea, hint «что улучшить, зачем, кому полезно»)
- Кнопка «Отправить»

#### Расширение errorStore

`errorStore.ts` сейчас хранит только API-ошибки. Добавить:

- Ring-buffer консольных ошибок (`window.onerror`, `window.onunhandledrejection`, override `console.error`): max 20 записей `{ts, message, stack?, source?}`.
- Существующий API errors ring уже есть, расширить — фильтровать только статусы ≥400 (не сетевые AbortError — уже фильтруется).
- Новая функция `buildContext(): FeedbackContext` собирает: `{userAgent, language, screen: {w, h}, url, timezone, activeTeam, activePeriod, theme, consoleErrors: [...], networkErrors: [...]}` — теги активной команды/периода берёт из URL params + AppSetting cache.
- Существующая функция `buildBugReport()` для clipboard-варианта **удаляется** (новый поток — отправка на сервер).
- Старая модалка copy-to-clipboard **удаляется** полностью.

Бейдж непрочитанных у плавашки оставляем смысловой: счётчик внутренних ошибок (стек консоли + сети ≥ 1) → подсказка юзеру «есть проблемы, кликни и пришли».

### Permissions

| Действие | Manager / Super-manager | Admin |
|---------|------------------------|-------|
| Создать баг | ✓ | ✓ |
| Создать идею | ✓ | ✓ |
| Посмотреть свои | ✓ | ✓ |
| Посмотреть чужие идеи | ✓ | ✓ |
| Посмотреть чужие баги | ✗ | ✓ |
| Отметить прочитанным | ✗ | ✓ |
| Выгрузка | ✗ | ✓ |

### Формат экспорта (markdown)

```markdown
# Баги — выгрузка 2026-05-25 (N штук)

---

## #1 — <Заголовок бага>

**Автор:** Иван Иванов (ivan@…)  |  **Создан:** 2026-05-25 14:32  |  **URL:** /resource-planning?q=2026Q2

### Что случилось
<body>

### Шаги воспроизведения
<steps>

### Ожидание
<expected>

### Факт
<actual>

### Контекст
- Браузер: Chrome 130 / Windows 11
- Экран: 1920×1080
- Активная команда: ITGRI Frontend
- Период: 2026Q2
- Тема: dark-blue

### Консольные ошибки (3)
1. `TypeError: Cannot read property 'foo' of undefined` at App.tsx:42
2. …

### Сетевые ошибки (1)
1. `POST /api/v1/planning/scenarios 500 → "Internal Server Error"`

### Приложения (2)
- `screenshot.png` → /api/v1/feedback/attachments/abc123
- `extra.json` → /api/v1/feedback/attachments/def456

---

## #2 — …
```

Для идей формат проще: автор/дата/URL + body, без блоков контекста.

## Что НЕ делаем (out of scope)

- Лайки, комменты, треды на идеях — отвергнуто PM.
- Notifications/email юзеру когда баг отметили прочитанным — пока не нужно, юзеры зайдут на `/feedback` сами.
- Линковка багов с PR / Jira — Claude Code решает что делать с выгруженным md.
- Статус workflow (in-progress / done / wont-fix) — только бинарный read/unread.
- Скриншот через `html2canvas` — нестабильно на Gantt, юзер прицепит файл руками.
- Скриншот через `getDisplayMedia` — Edge requires HTTPS, лишний UX-степ.

## Тестирование

Backend:
- Модель: migration up/down.
- Сервис: создание, list filters, mark_read/unread, export_markdown с/без mark_after.
- Endpoints: permissions (manager не видит чужих багов), upload validation (MIME, size, count), download attachment.

Frontend:
- Drawer форма submit обоих типов.
- errorStore: console error capture, ring-buffer eviction.
- Admin таблица: чекбоксы, фильтр, выгрузка-и-пометить (атомарно), bulk mark read.

E2E (Playwright):
- Логин обычным юзером → отправить баг → проверить пришёл в админ-список.
- Логин админом → выгрузить → проверить md содержит ожидаемые поля + пометил прочитанным.

## Миграция существующего

- `BugReportButton.tsx` переписывается полностью (новая логика drawer).
- `errorStore.ts` расширяется (console + network buffers), функция `buildBugReport()` удаляется.
- Никаких данных в существующем clipboard-варианте не хранится → миграция данных не нужна.
