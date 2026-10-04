// Ролик «Как разобрать новые задачи»: Категории задач → плашка «N ждут разбора» →
// очередь «К разбору» → раскрыть эпик, выбрать категорию и сохранить на всё поддерево →
// второй эпик — «Подтвердить» с числом → поиск по ключу → «В анализ» → «Только переехавшие» →
// «Сбросить категорию» → очередь стала меньше.
import { expect, test, type Locator, type Page } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const CATEGORY = 'Технические задачи';
const CATEGORY_CODE = 'tehnicheskie_zadachi';

/** Задачи, которым ролик ставит категорию, — после съёмки категорию снимаем. */
const touchedIds: string[] = [];

test.afterAll(async ({ playwright }, testInfo) => {
  if (touchedIds.length === 0) return;
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/issues/batch-category`, {
    data: { issue_ids: touchedIds, category_code: null, verify: false, overwrite: true },
  });
  await request.dispose();
});

/**
 * Открыть выпадающий список категорий и выбрать нужную. Список рендерится
 * виртуально (AntD Select) и открывается со скроллом к уже стоящему значению —
 * нужная опция может быть не отрисована вовсе, пока к ней не прокрутить.
 */
async function pickCategory(d: Director, page: Page, trigger: Locator, label: string, caption?: string): Promise<void> {
  await d.click(trigger, caption);
  const dropdown = page.locator('.ant-select-dropdown:visible');
  await expect(dropdown).toBeVisible();
  const option = dropdown.locator('.ant-select-item-option', { hasText: label });
  await dropdown.hover();
  for (let i = 0; i < 20 && (await option.count()) === 0; i++) {
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(80);
  }
  await expect(option.first()).toBeVisible({ timeout: 5_000 });
  await d.click(option.first());
}

interface IssueRoot {
  id: string;
  key: string;
  summary: string;
  category: string | null;
  status: string;
  descendant_match_count: number;
  is_context: boolean;
  has_children: boolean;
  parent_changed?: boolean;
}

test('categorize-issue', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = String(test.info().config.metadata.backendUrl);

  // Тот же фильтр в шапке, что видит зритель на экране.
  expect((await page.request.put(`${api}/api/v1/auth/me/teams`, {
    data: { teams: [TEAM], subgroups: [] },
  })).ok()).toBeTruthy();

  const rootsRes = await page.request.get(`${api}/api/v1/issues/tree/roots`, {
    params: { teams: TEAM, tab: 'stack' },
  });
  expect(rootsRes.ok()).toBeTruthy();
  const roots = (await rootsRes.json()) as IssueRoot[];
  const epics = roots.filter((r) => r.has_children && !r.is_context);

  // Первый эпик — с небольшим числом неразобранных задач внутри: сохранение на всё поддерево
  // закрывает его целиком. Эпик без категории предпочтительнее, если он есть.
  const epicA =
    epics.find((r) => !r.category) ??
    epics.find((r) => r.descendant_match_count >= 1 && r.descendant_match_count <= 5) ??
    epics[0];
  expect(epicA, `В «К разбору» команды ${TEAM} нет эпика с подзадачами`).toBeTruthy();
  // Второй эпик — без неразобранных задач внутри; категорию ему «предложили» заранее (без
  // подтверждения), как это бывает при переезде задачи: остаётся нажать «Подтвердить».
  const epicB = epics.find((r) => r.id !== epicA.id && r.descendant_match_count === 0);
  expect(epicB, `Нужен второй эпик в «К разбору» без неразобранных задач внутри`).toBeTruthy();
  expect((await page.request.put(`${api}/api/v1/issues/batch-category`, {
    data: { issue_ids: [epicB!.id], category_code: CATEGORY_CODE, verify: false, overwrite: true },
  })).ok()).toBeTruthy();
  touchedIds.push(epicA.id, epicB!.id);
  // Отдельная задача без подзадач — для поиска, «В анализ» и сброса категории.
  const leaf =
    roots.find((r) => !r.has_children && !r.is_context && r.id !== epicA.id && r.id !== epicB!.id && !!r.category) ??
    roots.find((r) => !r.has_children && !r.is_context && r.id !== epicA.id && r.id !== epicB!.id);
  expect(leaf, `Нужна отдельная задача без подзадач в «К разбору»`).toBeTruthy();
  touchedIds.push(leaf!.id);

  await d.open('/categories', 'Как разобрать новые задачи');
  const waiting = page.locator('[data-tour="categories-waiting"]');
  await expect(waiting).toBeVisible({ timeout: 20_000 });
  const table = page.locator('[data-tour="categories-table"]');
  await expect(table.locator(`tr[data-row-key="${epicA.id}"]`)).toBeVisible({ timeout: 20_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const waitingText = await waiting.innerText();

  const stackCard = page.locator('[data-tour="categories-queues"] .category-queue-card', { hasText: 'К разбору' });
  await d.caption('Плашка показывает, сколько задач ждут разбора');
  await d.show(waiting);
  await d.pause(900);
  await d.click(stackCard, 'Очередь «К разбору» — задачи без решения');


  // Раскрыть эпик — клик по названию (строка целиком кликабельна).
  const rowA = table.locator(`tr[data-row-key="${epicA.id}"]`);
  await d.click(rowA.locator('td').nth(2), 'Раскройте эпик — видно его задачи');
  await d.pause(400);

  await pickCategory(d, page, rowA.locator('.ant-select'), CATEGORY, 'Выберите категорию для эпика');
  await d.click(rowA.getByTitle('Сохранить категорию'), 'Сохраните — кнопка с галочкой');
  await d.click(
    page.locator('.ant-popover:visible .ant-btn', { hasText: 'И всё поддерево' }),
    'Категория проставится всему поддереву разом',
  );
  await expect(table.locator(`tr[data-row-key="${epicA.id}"]`)).toHaveCount(0);
  await page.mouse.move(700, 120);

  // Второй эпик — категория уже унаследована, просто подтверждаем ветку.
  const rowB = table.locator(`tr[data-row-key="${epicB!.id}"]`);
  await d.click(rowB.locator('td').nth(2), 'У этого эпика категория уже выбрана — остаётся подтвердить');
  await d.pause(400);
  const confirmBtn = rowB.getByRole('button', { name: /^Подтвердить/ });
  await d.click(confirmBtn, '«Подтвердить» закрывает всю ветку разом');
  await expect(table.locator(`tr[data-row-key="${epicB!.id}"]`)).toHaveCount(0);

  await expect(waiting).not.toHaveText(waitingText);
  await d.show(waiting);
  await d.pause(900);

  // Панель над таблицей: всё дерево раскрывается кнопкой, лишнее прячется по статусу.
  const expandAllBtn = page.getByRole('button', { name: 'Развернуть всё' });
  await d.click(expandAllBtn, '«Развернуть всё» раскрывает всё дерево');
  await d.pause(1500);
  await d.click(page.getByRole('button', { name: 'Свернуть всё' }));
  await d.pause(500);

  const usedStatuses = new Set([epicA.status, epicB!.status, leaf!.status]);
  const hideStatus = roots.map((r) => r.status).find((st) => st && !usedStatuses.has(st));
  if (hideStatus) {
    const statusSelect = page.locator('.category-toolbar .ant-select').first();
    await d.click(statusSelect, 'В «Скрытых статусах» спрячьте ненужный статус');
    await page.keyboard.type(hideStatus.slice(0, 6), { delay: 80 });
    const statusOption = page.locator('.ant-select-dropdown:visible .ant-select-item-option').first();
    await expect(statusOption).toBeVisible({ timeout: 5_000 });
    await d.click(statusOption);
    await page.keyboard.press('Escape');
    await d.pause(800);
    await d.waitVoice();
    await d.click(statusSelect.locator('.ant-select-selection-item-remove').first());
  }
  await page.mouse.move(700, 120);

  // Поиск по ключу — прыжок к конкретной задаче.
  const searchInput = page.getByPlaceholder('Введите ключ задачи и нажмите Enter');
  await d.type(searchInput, leaf!.key, 'Найдите задачу по ключу — сервис раскроет путь и подсветит её');
  await searchInput.press('Enter');
  const leafRow = table.locator(`tr[data-row-key="${leaf!.id}"]`);
  await expect(leafRow).toHaveClass(/tree-row-search-hit/, { timeout: 10_000 });
  await d.show(leafRow);
  await d.pause(700);

  // «В анализ» — вторая галочка в строке (первая — выбор для массового действия).
  const includeCb = leafRow.locator('.ant-checkbox-input').last();
  await d.click(includeCb, 'Галочка «В анализ» решает, войдут ли часы задачи в отчёты');
  await d.pause(500);
  await d.click(includeCb);
  await page.mouse.move(700, 120);

  // «Только переехавшие» — только если такие задачи вообще есть у команды.
  const onlyMovedSwitch = page.locator('.category-toolbar .ant-switch');
  const hasMoved = roots.some((r) => r.parent_changed);
  if (hasMoved) {
    await d.click(onlyMovedSwitch, '«Только переехавшие» — задачи со сменившимся родителем');
    await d.pause(900);
    await d.click(onlyMovedSwitch);
  }
  await page.mouse.move(700, 120);

  // Массовое окно: сначала сбросить категорию отмеченной задаче, затем назначить для пустых.
  const selectCb = leafRow.locator('.ant-checkbox-input').first();
  await d.click(selectCb, 'Отметьте задачу галочкой слева');
  await d.click(page.locator('[data-tour="categories-bulk"]'), 'Откройте массовое действие');
  const bulkModal = page.locator('.ant-modal', { hasText: 'Установить категорию для' });
  await expect(bulkModal).toBeVisible();
  await d.pause(400);
  await d.click(
    bulkModal.getByRole('button', { name: 'Сбросить категорию' }),
    'Категорию отмеченным задачам можно сбросить',
  );
  const popconfirm = page.locator('.ant-popconfirm:visible');
  await expect(popconfirm).toBeVisible();
  await d.click(popconfirm.getByRole('button', { name: 'Сбросить' }));
  await expect(bulkModal).toBeHidden();
  await page.mouse.move(700, 120);

  await expect(leafRow).toBeVisible({ timeout: 10_000 });
  const selectCb2 = leafRow.locator('.ant-checkbox-input').first();
  if (!(await selectCb2.isChecked())) await d.click(selectCb2, 'Отметьте её снова');
  await d.click(page.locator('[data-tour="categories-bulk"]'));
  await expect(bulkModal).toBeVisible();
  await pickCategory(d, page, bulkModal.locator('.ant-select'), CATEGORY, 'Выберите категорию');
  await d.click(
    bulkModal.getByRole('button', { name: 'Назначить для пустых' }),
    'Для пустых — задачи с уже выбранной категорией не трогаются',
  );
  await expect(bulkModal).toBeHidden();
  await page.mouse.move(700, 120);

  await d.caption('Итог: задач «К разбору» стало меньше');
  await d.show(waiting);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('categorize-issue');
});
