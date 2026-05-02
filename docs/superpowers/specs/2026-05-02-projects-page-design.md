# Projects Page — Design Spec

**Дата:** 2026-05-02
**Статус:** утверждён, готов к плану

## Цель

Страница анализа отдельного проекта для PM. Проект = parent issue с категорией `quarterly_tasks` или `archive_target`. PM открывает один проект и за 10 секунд понимает: что делали, кто работал, сколько потратили, какой результат, как оценил заказчик.

Два режима просмотра:
- **Анализ** (Compact) — повседневная плотная сетка для PM-работы
- **Презентация** (Story) — крупная вертикальная вёрстка для встреч с заказчиком

Плюс экспорт презентации в PDF (через браузерный print API).

## Скоуп

В скоуп:
- Новый раздел `/projects` (master-detail: список + детальная панель)
- AI-генерация саммари по проекту через LLM (Gemini 2.0 Flash старт + мульти-провайдерный адаптер)
- Оценка заказчика из 3 custom fields Jira (синхронизируется в Issue model)
- Период проекта по min/max worklog (плюс задел под планируемые даты Jira)
- Drill-in из Dashboard / Analytics / Backlog
- Глобальный team filter (как везде)
- Экспорт презентации в PDF (клиентский, через `window.print()`)

Вне скоупа:
- Серверный PDF-рендер (playwright headless)
- Ручной ввод оценок (только из Jira)
- AI-оценка качества/скорости (только из Jira)
- Сравнение проектов между собой

## URL и навигация

- Новый пункт сайдбара «Проекты» (иконка folder), между Dashboard и Analytics
- `/projects` — пустой right-pane («Выберите проект слева»)
- `/projects/:key` — выбранный проект справа, его строка подсвечена в списке
- `?view=presentation` — query-param активирует режим Презентация
- Drill-in: ProjectsWidget на Dashboard, Analytics строка-проект, Backlog → переход на `/projects/:key`

## Layout master-detail

### Левая панель — список проектов (~360px, ресайзится)

**Скоуп списка**: parent issues с категорией `quarterly_tasks` ∪ `archive_target`, отфильтровано глобальным team filter (хоть один участник из выбранных команд).

**Sticky-шапка списка** содержит:
- Поиск по названию/ключу (debounce 300мс)
- Фильтр статус: chips «Все / Активные / Готовые / Просроченные»
- Фильтр категория: toggle «Все / Квартальные / Архив»
- Сортировка dropdown: «По периоду (новые сверху)» (default) / «По часам» / «По имени»

**Карточка проекта** (~80px высота):
- Цветная вертикальная полоска по статусу слева
- Строка 1: ключ эпика серым + название (truncate, 1 строка)
- Строка 2: 4 мелких метки в линию — Период / Часы / Задач / Участников
- Строка 3: статус-pill слева + 3 мини-звезды-оценки справа

Hover: tinted bg. Selected: cyan border + tinted bg.

**Производительность**: virtual scroll (react-virtual или ant-design Virtual List), не подгружать все ~50-200 проектов сразу.

### Правая панель — режим Анализ (Compact, default)

**Sticky-шапка панели**:
- Слева: название проекта крупно, ниже — ключ эпика (link на Jira) + период + статус-pill
- Справа: tab-pair `[Анализ | Презентация]` (cyan underline на активном), кнопка «Обновить AI», кнопка «Скачать PDF», меню «...» (Открыть в Jira / Перегенерировать всё)
- Под шапкой — мелкая строка «AI-резюме обновлено DD.MM.YYYY HH:MM»

**Body** — 2-колоночная сетка:

Левая колонка:
1. Card «Цели проекта» (AI, 3 нумерованных пункта с цветными маркерами)
2. Card «Структура трудозатрат» (donut-chart с центральным значением «N ч» крупно + sub-label «N нед» + список категорий с часами и %)
3. Card «Участники» (компактный список с bar-индикаторами часов и процентов)

Правая колонка:
1. Card «Основной результат» (AI flow-диаграмма из 3-5 блоков + checklist)
2. Card «Статус проекта» (AI text + 4 KPI плитки 2×2: Задач / Часов / Участников / Недель)
3. Card «Ключевые блоки» (топ-3 категории с прогресс-барами)
4. Card «Оценка заказчика» (3 строки звёзд + AI-сводка нагрузки)
5. Card «Топ-3 задачи по часам»

**Интерактив**:
- Клик на участника → drill в Analytics с фильтром «employee=X, project=Y»
- Клик на категорию (donut/Ключевые блоки) → drill в Analytics с фильтром «category=X, project=Y»
- Клик на топ-задачу → drill в Analytics с раскрытым деревом до задачи
- Звёзды — read-only (приходят из Jira)
- AI-карточки — read-only с иконкой «AI» в углу

**Empty states**:
- Нет worklogs → donut/участники/топ-задачи пустые с placeholder «Нет данных за период»
- AI ещё не сгенерирован → skeleton + «Резюме генерируется, обновите через минуту»
- Нет оценок → секция оценок скрыта

### Правая панель — режим Презентация (Story)

**Toggle** в шапке `[Анализ | Презентация]`. Состояние сохраняется в URL `?view=presentation`. По умолчанию `analysis`.

**Layout**:
- Левая панель списка скрывается или становится узкой 60px иконками
- Контент в одну колонку, центрированный, max-width ~960px
- Крупная типографика (h2 28-32px), много воздуха

**Секции**:
1. **Hero** — название (display large), эпик-ключ + период мелко, статус-pill, 3 крупные KPI плитки (Часы / Задач / Участников)
2. **Что мы делали** — AI-цели (нумерованный список с цветными маркерами) + описание эпика
3. **Какой результат** — AI flow-диаграмма на всю ширину + статус-текст
4. **Кто работал** — таблица участников с длинными bar-индикаторами, топ-2 акцентом
5. **На что ушло время** — donut крупный слева, легенда справа; ниже «Топ-3 задачи»
6. **Как оценили** — 3 крупных карточки оценок с большими звёздами (32px) + AI-сводка нагрузки

**Интерактив**: drill-клики отключены (это режим презентации). Только скролл.

**Анимация переключения**: fade 200мс.

## PDF Export

**Подход**: клиентский рендер через `window.print()` + CSS `@media print` поверх Story-вёрстки. Без бэкенда.

**Поток**:
- Кнопка «Скачать PDF» в шапке правой панели
- При клике: программно переключается в режим Презентация (если ещё не в нём) → ждёт repaint → вызывает `window.print()`
- Юзер в системном диалоге выбирает «Сохранить как PDF»

**CSS `@media print`**:
- Скрыть application chrome (sidebar, header, toggle-кнопки, кнопки экспорта)
- Page size: A4 portrait
- `page-break-inside: avoid` на каждую секцию
- `-webkit-print-color-adjust: exact` для сохранения цветного фона
- Шрифты embed через Google Fonts subset

**Известные ограничения**:
- Качество зависит от браузера (Chrome/Edge — OK, Firefox — хуже с цветами)
- Юзер видит print dialog (не one-click)

Серверный playwright-рендер — задел на будущее, если возникнет претензия к качеству.

## Период проекта

**Формула**: min/max `started_at` среди worklogs эпика и его дочерних задач.

**Задел**: 2 nullable колонки на Issue — `planned_start_date` и `planned_end_date`, под будущий инструмент планирования. Когда заполнятся (через будущий sync custom field из Jira), на странице рисуем «план» серым над «фактом». Сейчас не рисуем.

## Оценка заказчика

3 custom field в Jira (целочисленные 1-5):
- Качество
- Скорость
- Результат

**Конфигурация**: 3 новых AppSetting key (по аналогии с существующими `jira_*_field_id`):
- `jira_rating_quality_field_id`
- `jira_rating_speed_field_id`
- `jira_rating_result_field_id`

Поля редактируются на `/settings → fields` (добавить 3 input).

**Хранение**: 3 новые колонки на Issue (`rating_quality`, `rating_speed`, `rating_result`, nullable Integer 1-5).

**Sync**: `sync_service` тянет эти 3 поля при инкрементальной/полной синхронизации (как остальные plan/involvement/duration поля).

**UI**: рендер 5 SVG звёзд (заполненные cyan, пустые серые) для каждой из 3 оценок. Если все 3 пустые — карточка оценок не рендерится.

## AI-генерация

### Архитектура

**LLM-адаптер**: `app/services/llm_service.py` с интерфейсом `LLMProvider`:
```python
class LLMProvider(Protocol):
    async def summarize_project(self, epic_data: dict) -> ProjectSummary: ...
```

Реализации (старт):
- `GeminiProvider` — через Google AI Studio API, модель `gemini-2.0-flash`
- Заглушки-протоколы для будущего: `DeepSeekProvider`, `AnthropicProvider`, `OpenAIProvider`

Factory `get_llm_provider(db) -> LLMProvider`:
- Читает `AppSetting.llm_provider` (default `"gemini"`)
- Читает `AppSetting.llm_<provider>_api_key`
- Возвращает инстанс или поднимает `ConfigurationError` если ключа нет

### Структура `ProjectSummary` (Pydantic)

```python
class FlowBlock(BaseModel):
    label: str
    status: Literal["source", "flow", "done"]

class ChecklistItem(BaseModel):
    label: str
    done: bool

class ProjectSummary(BaseModel):
    goals: list[str]                       # 3 пункта
    result_flow_blocks: list[FlowBlock]    # 3-5 блоков
    result_checklist: list[ChecklistItem]  # 3-5 пунктов
    status_text: str                       # 1-2 предложения
    workload_summary: str                  # 1 предложение
```

### Кэш в БД

Новая таблица `project_ai_summary`:
- `id` UUID PK
- `issue_id` FK на `issues.id` (UNIQUE)
- `goals_json` Text (JSON-сериализованный список)
- `result_flow_json` Text
- `result_checklist_json` Text
- `status_text` Text
- `workload_summary` Text
- `generated_at` DateTime
- `model_used` String (например `"gemini-2.0-flash"`)
- `input_tokens` Integer
- `output_tokens` Integer

Миграция Alembic: создание таблицы.

### Источники для промпта

- Эпик: `summary`, `description`, `goals` (custom field), `status`
- Дочерние задачи: список «ключ → summary → status» (только включённые в анализ)
- Worklogs aggregated:
  - Часы по категориям (top-N)
  - Часы по сотрудникам (top-N)
  - Топ-5 задач по часам
- Period: min/max worklog
- Status proxy: доля закрытых дочерних задач

### Промпт

System prompt на русском, описывает роль («аналитик проектов»), формат вывода (JSON), требования (3 цели, краткий статус, etc.).

User prompt — структурированный текст с данными выше.

Ответ: structured JSON через Gemini `responseSchema`. Если не сработает — текстовый парсинг fallback.

Промпт версионируется в коде (constant `PROMPT_VERSION`), при апдейте — все кэши помечаются устаревшими (background regen).

### Расписание

**APScheduler cron** (использует существующий APScheduler из sync consolidation):
- Job `regenerate_project_summaries` ежедневно `03:00`
- Проходит все parent issues с категорией `quarterly_tasks` ∪ `archive_target`
- Регенерит если: нет записи в `project_ai_summary` ИЛИ `worklogs.updated_at > project_ai_summary.generated_at` (по любому worklog'у эпика/детей) ИЛИ изменился `PROMPT_VERSION`
- Иначе skip

**Manual refresh**:
- Endpoint `POST /projects/{key}/regenerate-summary` — синхронный (blocking, 5-15с), возвращает свежий `ProjectSummary`
- Кнопка «Обновить AI» в шапке правой панели вызывает endpoint
- SSE event `project_summary_generated` → frontend инвалидирует кэш TanStack Query

### Конфигурация в `/settings`

Новый таб «AI» в `/settings`:
- Select провайдера (gemini / deepseek / anthropic / openai) — на старте только gemini активен
- Input API key (masked) для каждого провайдера
- Test-кнопка «Проверить подключение» (вызывает provider с минимальным prompt'ом)
- Кнопка «Перегенерировать все саммари» (запускает background job с прогрессом через SSE)

### Cost-оценка

~6K input + 1K output на проект × 100 проектов = 700K токенов/день. Gemini Flash free tier (15 RPM, ~1M токенов/день) покрывает.

При апгрейде на платный (DeepSeek-V3): ~$0.20-0.30/день.

## API

Новые endpoints:

```
GET  /projects                                    Список проектов с метриками
GET  /projects/{key}                              Детали одного проекта
GET  /projects/{key}/summary                      AI-саммари (из кэша)
POST /projects/{key}/regenerate-summary           Регенерация AI-саммари (sync)
POST /llm/test                                    Test connection (settings)
POST /llm/regenerate-all                          Background regen всех проектов
```

`GET /projects/{key}` payload:
- meta: key, summary, description, status, period (start/end)
- ratings: quality/speed/result (1-5 или null)
- aggregates: total_hours, weeks, child_count, employee_count, status_breakdown
- categories: список с hours и %
- employees: список с hours и %
- top_issues: топ-5 по часам
- ai_summary: ссылка на отдельный endpoint (lazy load или join)

## Фронтенд

### Структура файлов

```
frontend/src/pages/
  ProjectsPage.tsx                              Master-detail контейнер

frontend/src/components/projects/
  ProjectsList.tsx                              Левая панель + virtual scroll
  ProjectListCard.tsx                           Карточка проекта в списке
  ProjectListFilters.tsx                        Поиск/фильтры/сортировка
  ProjectDetailPanel.tsx                        Правая панель (мост между режимами)
  ProjectAnalysisView.tsx                       Compact mode (default)
  ProjectPresentationView.tsx                   Story mode
  ProjectHeader.tsx                             Sticky-шапка панели + toggle
  cards/
    ProjectGoalsCard.tsx                        AI-цели
    ProjectResultCard.tsx                       AI-результат + flow
    ProjectStatusCard.tsx                       AI-status + KPI 2×2
    ProjectCategoriesCard.tsx                   Donut + список категорий
    ProjectEmployeesCard.tsx                    Bar-list участников
    ProjectKeyBlocksCard.tsx                    Топ-3 категории прогресс-барами
    ProjectRatingsCard.tsx                      3 строки звёзд + workload summary
    ProjectTopIssuesCard.tsx                    Топ-3 задачи
  presentation/
    ProjectHero.tsx                             Hero для Story-режима
    ProjectStorySection.tsx                     Обёртка секции
  shared/
    StarRating.tsx                              5-звёздочный SVG-рендер
    FlowDiagram.tsx                             Reusable flow-диаграмма
    DonutChart.tsx                              Reusable donut с центром

frontend/src/api/
  projects.ts                                   /projects/* API клиент

frontend/src/hooks/
  useProjects.ts                                List + detail TanStack hooks
  useProjectSummary.ts                          AI-summary + regenerate
```

### Print CSS

Отдельный файл `frontend/src/styles/print.css`, импортируется в `ProjectPresentationView`. Содержит `@media print` правила.

### Routing

`react-router` lazy: `/projects`, `/projects/:key` — обе на `ProjectsPage`. Query-param `?view=presentation` парсится внутри.

### Sidebar

Добавить пункт «Проекты» в `MainLayout.tsx` навигации (между Dashboard и Analytics).

## Drill-in из других страниц

- **Dashboard ProjectsWidget**: клик по строке проекта → `navigate('/projects/' + key)`
- **Analytics**: клик по строке-проекту в дереве → `navigate('/projects/' + key)` с возвратной кнопкой
- **Backlog**: клик по проекту в карточке → `/projects/:key`

## Тестирование

**Backend**:
- Unit: `LLMProvider` mock + `summarize_project` + кэш hit/miss
- Unit: period derivation (worklog min/max + edge cases)
- Integration: `/projects` list + `/projects/{key}` detail + ratings sync
- Integration: APScheduler job triggers regeneration only when worklogs changed

**Frontend**:
- Component: `ProjectsList` virtual scroll + filters
- Component: `ProjectAnalysisView` рендер всех карточек с моком данных
- Component: режим toggle Анализ ↔ Презентация
- E2E (Playwright): открыть `/projects` → выбрать проект → проверить рендер обоих режимов → клик «Скачать PDF» (проверить что print preview открылся)

## План внедрения (фазы)

1. **Фаза 1 — Backend данные**: миграции (3 rating-колонки, `project_ai_summary` таблица, AppSetting keys), API `/projects` list + detail, sync 3 ratings полей
2. **Фаза 2 — LLM-инфраструктура**: `llm_service.py` + `GeminiProvider`, AppSetting для ключа, endpoint `POST /llm/test`, settings tab «AI»
3. **Фаза 3 — AI-генерация**: промпт + `summarize_project`, кэш-логика, endpoint `POST /projects/{key}/regenerate-summary`, APScheduler ночной job, SSE event
4. **Фаза 4 — Фронтенд каркас**: routing, sidebar, master-detail, `ProjectsList` + virtual scroll + фильтры
5. **Фаза 5 — Compact view**: все карточки правой панели + drill-in из карточек
6. **Фаза 6 — Presentation view + PDF**: Story-вёрстка, toggle, `@media print` CSS, кнопка PDF
7. **Фаза 7 — Drill-in из существующих страниц**: ProjectsWidget, Analytics, Backlog
8. **Фаза 8 — Тесты + полировка**: unit/integration/E2E, fix UX-нюансов

## Риски и допущения

- **Gemini free tier rate limit**: 15 RPM. Если регенерим 100 проектов разом — упрёмся. Решение: APScheduler job делает по одному с throttle 5с между вызовами.
- **Качество русского у Gemini Flash**: гипотеза «достаточно хорошее». Если нет — PROMPT_VERSION + переход на DeepSeek-V3 (платный, $0.27/M).
- **Структурированный JSON**: Gemini поддерживает `responseSchema` (JSON Schema). Fallback — текстовый парсинг с regex.
- **Multi-user concurrency**: APScheduler job — один воркер, не race condition. Manual refresh — может конкурировать с cron job, решаем через advisory lock на `issue_id`.
- **PDF качество**: клиентский print может выдавать разное в Chrome vs Firefox. Принимаем компромисс на MVP, серверный рендер — если будет реальная проблема.
