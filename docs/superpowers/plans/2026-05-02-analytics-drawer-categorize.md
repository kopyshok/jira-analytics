# План: Drawer категоризатора в Аналитике

**Spec:** [docs/superpowers/specs/2026-05-02-analytics-drawer-categorize-design.md](../specs/2026-05-02-analytics-drawer-categorize-design.md)
**Мокап:** [docs/superpowers/mockups/2026-05-02-analytics-drawer-categorize.html](../mockups/2026-05-02-analytics-drawer-categorize.html)

## Этапы

### Этап 1. Backend: контекст задачи + lazy children

1. **Schema** `app/schemas/issue_context.py` — `IssueContextSchema`, `IssueContextNode`, `IssueContextChild` (per spec).
2. **Endpoint** `GET /issues/{issue_id}/context` в `app/api/endpoints/issues.py`:
   - 404 если нет;
   - ancestors: walk up `parent_id` max 20 шагов, защита от циклов через set;
   - children: прямые дети + per-child `subtree_count` (BFS из child_id, чанк 500);
   - `siblings_total`: count детей `parent_id`;
   - `subtree_count` (root): BFS вниз;
   - `is_container`: `HierarchyRulesService.classify(issue, parent)`;
   - `category` для каждого узла — `Issue.category` (денорм, уже учитывает наследование).
3. **Endpoint** `GET /issues/{parent_id}/children?limit=200` (если нет — добавить):
   - прямые дети без рекурсии, нужные для popover;
   - sort by status_category (active first), then key.
4. **Тесты** `tests/test_issue_context_endpoint.py`:
   - happy path,
   - root без родителя,
   - лист без детей,
   - container detection,
   - siblings_total,
   - 404,
   - cycle protection.

**Verify:** `py -3.10 -m pytest tests/test_issue_context_endpoint.py -v`

### Этап 2. Frontend: hooks + types

1. `frontend/src/types/api.ts` — добавить `IssueContextResponse`, `IssueContextChild` типы.
2. `frontend/src/api/issues.ts` — `getIssueContext(issueId)`, `getIssueChildren(parentId, limit?)`.
3. `frontend/src/hooks/useIssueContext.ts` — TanStack Query, staleTime 30s.
4. `frontend/src/hooks/useIssueChildren.ts` — для popover, enabled по флагу.

**Verify:** `cd frontend && npx tsc --noEmit`

### Этап 3. Frontend: компоненты drawer

1. `frontend/src/components/analytics/IssueContextBlock.tsx`:
   - крошки родителей (cyan ссылки в Jira + клик внутри drawer = drill);
   - popover «+N соседей» (AntD `Popover` + список из `useIssueChildren`);
   - мини-таблица детей с inline селектором категории и чекбоксом включения;
   - empty state «У задачи нет подзадач».
2. `frontend/src/components/analytics/IssueCategorizer.tsx`:
   - селектор категории (Select из `useCategories`);
   - чекбокс «Учитывать в анализе»;
   - тумблер «Применить ко всему поддереву (N)» — N из `subtree_count - 1`;
   - кнопки Save/Cancel;
   - Save: если тумблер выкл — `setIssueCategory + setIssueInclude`; если вкл — собрать все ID поддерева через `useIssueContext` + lazy walk и `batchSetCategory` + per-id `setIssueInclude` (последовательно или одним новым endpoint — пока reused существующих);
   - архив-кейс: чекбокс disabled + Tooltip;
   - container-кейс: всё disabled + Alert баннер сверху.
3. `frontend/src/components/analytics/AnalyticsIssueDrawer.tsx`:
   - 720px Drawer;
   - back-stack `useState<string[]>`;
   - шапка: ключ + ссылка Jira + status tag + (если стек>1) «← назад»;
   - название задачи под ключом;
   - три карточки: Контекст / Категоризатор / Ворклоги (`AnalyticsWorklogsBlock`);
   - стили строго по мокапу (цвета + UPPERCASE muted заголовки секций).
4. `frontend/src/components/analytics/AnalyticsTable.tsx` — заменить inline `<Drawer>` на `<AnalyticsIssueDrawer>`.

**Verify:** `cd frontend && npx tsc --noEmit && npx eslint src/components/analytics/`

### Этап 4. Стилизация по мокапу

1. CSS-классы для секций: `.drawer-section`, `.drawer-section-title`, `.drawer-card`, `.drawer-breadcrumb`.
2. Цвета жёстко по мокапу (palette в `frontend/src/utils/constants.ts` уже есть — переиспользовать DARK_THEME).
3. Hover-эффекты на крошках, активной задаче (`background: #0a1830`).
4. Таблица детей — `size="small"` + кастомные paddings под мокап.
5. Селектор категории — bullet-цвет рядом с label через `optionRender`.

**Verify:** open-in-browser → визуально совпадает с мокапом (проверить «contextual sections», bullets, breadcrumbs, кнопки).

### Этап 5. Реактивность

1. Все мутации в `IssueCategorizer` invalidate:
   - `['issues','tree']`,
   - `['analytics','report']`,
   - `['issue','context', issueId]`,
   - `['issue','context', ...ancestors]` (для drill при возврате).
2. Бэк публикует `entity_changed{kind:'issue', id}` — проверить что pipeline уже подцеплен; если нет — добавить `event_bus.publish` после commit в `set_category` / `set_include`.

**Verify:** в браузере — изменить категорию, увидеть обновление иерархического отчёта без F5.

### Этап 6. E2E

1. `frontend/e2e/analytics-drawer-categorize.spec.ts`:
   - открыть Аналитику в drawer-mode;
   - кликнуть на задачу из «Без категории»;
   - проверить наличие крошек, селектора, чекбокса;
   - изменить категорию + сохранить;
   - перепроверить что задача ушла из «Без категории».
2. Проверить edge cases — лист, контейнер, архив (если есть в seed-данных).

**Verify:** `.\scripts\e2e-local.ps1`

### Этап 7. Финал

1. Полный тест-ран: `py -3.10 -m pytest tests/ -q` + frontend lint + tsc.
2. Commit одним батчем (или по этапам, если объём большой):
   ```
   feat(analytics): drawer категоризатора с иерархией задачи

   - GET /issues/{id}/context — предки, дети, subtree_count, is_container.
   - Drawer 720px: контекст в иерархии, селектор категории + флаг анализа,
     тумблер «применить к поддереву», ворклоги.
   - Drill-down в детей через back-stack.
   - Edge cases: лист, контейнер, архивная категория.
   ```
3. `git push origin main`.

## Критерии приёмки

- Клик по задаче в drawer-режиме открывает панель 720px справа.
- Крошки родителей кликабельны (drill в drawer + ссылка в Jira).
- Селектор категории + чекбокс анализа работают, отчёт перестраивается без F5.
- Тумблер «всё поддерево» помечает категорию всем потомкам одной операцией.
- Edge cases отрабатывают: лист (нет блока детей), контейнер (категоризатор disabled с баннером), архив (чекбокс disabled).
- Визуально совпадает с мокапом 2026-05-02.
- Все pytest зелёные кроме pre-existing flakes (CI red on main).
- Frontend tsc + eslint чистые.
