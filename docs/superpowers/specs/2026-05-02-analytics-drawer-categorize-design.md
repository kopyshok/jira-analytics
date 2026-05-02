# Drawer категоризатора в Аналитике

**Дата:** 2026-05-02
**Мокап:** [docs/superpowers/mockups/2026-05-02-analytics-drawer-categorize.html](../mockups/2026-05-02-analytics-drawer-categorize.html)

## Цель

Из иерархического отчёта Аналитики (режим «Ворклоги: drawer») юзер кликает по задаче и в открывающейся правой панели:
- видит положение задачи в иерархии Jira (предки + дети + соседи),
- ставит/меняет категорию,
- управляет флагом «Учитывать в анализе»,
- видит ворклоги.

Главный сценарий — массовая категоризация задач из группы «Без категории», но drawer работает для любой задачи.

## UX (по мокапу)

Drawer 720px справа. Шапка sticky:
- ключ задачи (cyan, monospace, ссылка в Jira) + статус-бейдж + «×»;
- название задачи под ключом.

**Блок «Контекст»:**
- крошки родителей `Корень › ... › Текущая` (последняя — выделена);
- если у родителя 5+ детей — «+N соседей» popover (1-уровневый, не дерево);
- мини-таблица «Дети текущей задачи» (макс 10 строк, остальное — link «показать все»):
  - колонки: ключ, название, статус, селектор категории, чекбокс «в анализ»;
  - inline-сохранение по изменению поля.

**Блок «Категоризация»:**
- селектор категории текущей задачи (полный список из реестра + «Без категории»);
- чекбокс «Учитывать в анализе»;
- тумблер «Применить ко всему поддереву (N задач)» — если включён, сохранение пишет категорию + флаг на всё поддерево (BFS вниз) одним батч-запросом;
- кнопки «Сохранить» (cyan primary) / «Отмена».

**Блок «Ворклоги»** — без изменений (`AnalyticsWorklogsBlock`), под категоризатором.

**Edge cases:**
- Лист (нет детей) — блок «Дети» скрыт, тумблер поддерева скрыт.
- Задача в архивной категории — чекбокс «в анализе» disabled с тултипом «снимается автоматически архивной категорией».
- Контейнер по правилам иерархии (HierarchyRule) — селектор категории disabled, баннер «Это контейнер. Категории ставятся детям».

## Backend

**Новый endpoint:** `GET /issues/{issue_id}/context`

Response (`IssueContextSchema`):
```
{
  "id": str,
  "key": str,
  "summary": str,
  "status": str,
  "status_category": str | None,
  "issue_type": str,
  "category": str | None,         // assigned_category или унаследованная
  "assigned_category": str | None,
  "include_in_analysis": bool,
  "is_container": bool,           // по HierarchyRule
  "ancestors": [                  // от корня до прямого родителя
    {"id", "key", "summary", "issue_type"}, ...
  ],
  "siblings_total": int,          // сколько детей у прямого родителя
  "children": [                   // прямые дети, до 50
    {
      "id", "key", "summary", "status", "status_category",
      "issue_type", "category", "assigned_category",
      "include_in_analysis", "subtree_count"
    }, ...
  ],
  "subtree_count": int            // сколько задач в поддереве (текущая + все потомки)
}
```

- `ancestors` — обход вверх по `parent_id` до корня (защита от циклов: max 20 шагов).
- `is_container` — через `HierarchyRulesService.classify(issue, parent)`.
- `subtree_count` — BFS вниз с чанком 500.
- `category` для каждого узла — через денормализованное `Issue.category` (уже есть, MappingService поддерживает).

**Endpoint для соседей (lazy):** `GET /issues/{parent_id}/children?limit=200`
- возвращает прямых детей `parent_id` без рекурсии. Используется для popover «+N соседей».

**Существующие endpoints (без изменений):**
- `PUT /issues/{id}/category`
- `PUT /issues/{id}/include` (с `recursive` флагом)
- `PUT /issues/batch-category`

**Реактивность:** все мутации публикуют `entity_changed` (issue), пайплайн уже инвалидирует Аналитику.

## Frontend

### Структура

- `AnalyticsTable.tsx` — заменить inline `<Drawer>` на `<AnalyticsIssueDrawer>` (новый компонент).
- `AnalyticsIssueDrawer.tsx` (новый) — 720px Drawer + три секции (Контекст / Категоризация / Ворклоги) + back-stack.
- `IssueContextBlock.tsx` (новый) — крошки + popover соседей + таблица детей.
- `IssueCategorizer.tsx` (новый) — селектор категории + чекбокс include + тумблер поддерева + Save/Cancel.
- `useIssueContext(issueId)` (новый hook) — TanStack Query.
- Расширить `useChildrenLazy(parentId)` для popover.

### Drill-down

Клик по ключу ребёнка / соседа в drawer — `pushIssue(id)`. Drawer держит стек id; кнопка «← назад» в шапке всплывает второй drawer (или возвращает к предыдущему). Закрытие drawer сбрасывает стек.

### Стили

Точно по мокапу (`docs/superpowers/mockups/2026-05-02-analytics-drawer-categorize.html`):
- цвета: `#0d1c33` фон, `#0f2340` карточки, `#00c9c8` cyan primary, `#e6edf7` текст, `#94a3b8` muted, `rgba(255,255,255,0.1)` border;
- секции — карточки с заголовками UPPERCASE muted;
- таблица детей — компактная, hover подсветка;
- кнопки/селектор/чекбокс — AntD 6 dark, без кастомного CSS где можно (отступы под мокап).

### Реактивность UI

Сохранение категории/флага → invalidate:
- `['issues','tree']` (CategoryConfigTab),
- `['analytics','report']` (текущий отчёт),
- `['issue','context', issueId]` (сам drawer и предков, чтобы при drill обновилось).

### Edge cases UI

- Архив-категория → чекбокс disabled + Tooltip.
- Container → весь категоризатор disabled, баннер сверху блока (компонент `Alert` AntD).
- Лист → блок «Дети» = `<Empty description="У задачи нет подзадач" />` мелким шрифтом, тумблер поддерева скрыт.
- Загрузка контекста — `Skeleton` в шапке + блоках.
- Ошибка контекста — `Alert` red + кнопка retry.

## Тесты

**Backend (pytest):**
- `test_issue_context_endpoint.py`:
  - happy path: ancestors + children + counts;
  - issue без родителя — ancestors = [];
  - issue без детей — children = [], subtree_count = 1;
  - container detection через HierarchyRule;
  - siblings_total корректен;
  - 404 для unknown id;
  - cycle protection (искусственный self-parent — обрывается на 20).

**Frontend (Playwright e2e):**
- `analytics-drawer-categorize.spec.ts`:
  - drawer открывается по клику на issue;
  - крошки родителей кликабельны;
  - категоризация одной задачи работает;
  - тумблер поддерева пишет всем детям;
  - архивная категория снимает чекбокс анализа;
  - drill в ребёнка открывает второй drawer и «назад» возвращается.

## Out of scope

- Редактирование иерархии (parent_id) из drawer.
- Drag-and-drop задач между категориями.
- Multi-select задач из таблицы детей с групповым действием (есть тумблер «всё поддерево» — достаточно).
- Bulk-edit нескольких задач из мини-таблицы (inline-сохранение per row покрывает кейс).
