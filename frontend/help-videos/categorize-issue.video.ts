// Ролик «Как разобрать новые задачи»: Категории задач → плашка «N ждут разбора» →
// очередь «К разбору» → раскрыть эпик, выбрать категорию и сохранить на всё поддерево →
// второй эпик — «Подтвердить +N» → поиск по ключу → «В анализ» → «Только переехавшие» →
// «Сбросить категорию» → очередь стала меньше.
import { expect, test, type Locator, type Page } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const CATEGORY = 'Технические задачи';

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

  // Эпик без своей/унаследованной категории — на нём выбираем категорию сами.
  const epicA = epics.find((r) => !r.category) ?? epics[0];
  expect(epicA, `В «К разбору» команды ${TEAM} нет эпика с подзадачами`).toBeTruthy();
  // Второй эпик — уже с унаследованной категорией: «Подтвердить» подтвердит её как есть.
  const epicB = epics.find((r) => r.id !== epicA.id && !!r.category);
  expect(epicB, `Нужен второй эпик в «К разбору» с уже проставленной категорией`).toBeTruthy();
  // Отдельная задача без подзадач — для поиска, «В анализ» и сброса категории.
  const leaf =
    roots.find((r) => !r.has_children && !r.is_context && r.id !== epicA.id && r.id !== epicB!.id && !!r.category) ??
    roots.find((r) => !r.has_children && !r.is_context && r.id !== epicA.id && r.id !== epicB!.id);
  expect(leaf, `Нужна отдельная задача без подзадач в «К разбору»`).toBeTruthy();

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
  await d.click(rowB.locator('td').nth(2), 'У этого эпика категория уже унаследована от родителя');
  await d.pause(400);
  const confirmBtn = rowB.getByRole('button', { name: /^Подтвердить/ });
  await d.click(confirmBtn, '«Подтвердить +N» разом закрывает всю ветку');
  await expect(table.locator(`tr[data-row-key="${epicB!.id}"]`)).toHaveCount(0);

  await expect(waiting).not.toHaveText(waitingText);
  await d.caption('Плашка уже стала меньше');
  await d.show(waiting);
  await d.pause(1200);

  // Поиск по ключу — прыжок к конкретной задаче.
  const searchInput = page.getByPlaceholder('Введите ключ задачи и нажмите Enter');
  await d.type(searchInput, leaf!.key, 'Найдите задачу по её ключу');
  await searchInput.press('Enter');
  const leafRow = table.locator(`tr[data-row-key="${leaf!.id}"]`);
  await expect(leafRow).toHaveClass(/tree-row-search-hit/, { timeout: 10_000 });
  await d.caption('Сервис раскрыл путь и подсветил задачу');
  await d.show(leafRow);
  await d.pause(1200);

  // «В анализ» — вторая галочка в строке (первая — выбор для массового действия).
  const includeCb = leafRow.locator('.ant-checkbox-input').last();
  await d.click(includeCb, 'Галочка «В анализ» решает, войдут ли часы задачи в отчёты');
  await d.pause(500);
  await d.click(includeCb, 'Возвращаем как было');
  await page.mouse.move(700, 120);

  // «Только переехавшие» — только если такие задачи вообще есть у команды.
  const onlyMovedSwitch = page.locator('.category-toolbar .ant-switch');
  const hasMoved = roots.some((r) => r.parent_changed);
  if (hasMoved) {
    await d.click(onlyMovedSwitch, '«Только переехавшие» — задачи со сменившимся родителем');
    await d.pause(900);
    await d.click(onlyMovedSwitch);
  } else {
    await d.caption('«Только переехавшие» оставляет в списке задачи со сменившимся родителем');
    await d.show(onlyMovedSwitch);
    await d.pause(1000);
  }
  await page.mouse.move(700, 120);

  // Сбросить категорию у отмеченной задачи — массовое действие.
  const selectCb = leafRow.locator('.ant-checkbox-input').first();
  await d.click(selectCb, 'Отметьте задачу галочкой слева');
  await d.click(page.locator('[data-tour="categories-bulk"]'), 'Откройте массовое действие');
  const bulkModal = page.locator('.ant-modal', { hasText: 'Установить категорию для' });
  await expect(bulkModal).toBeVisible();
  await d.pause(400);
  await d.click(
    bulkModal.getByRole('button', { name: 'Сбросить категорию' }),
    'Можно и сбросить категорию отмеченным задачам',
  );
  const popconfirm = page.locator('.ant-popconfirm:visible');
  await expect(popconfirm).toBeVisible();
  await d.click(popconfirm.getByRole('button', { name: 'Сбросить' }), 'Подтвердите');
  await expect(bulkModal).toBeHidden();
  await page.mouse.move(700, 120);

  await d.caption('Итог: задач «К разбору» стало меньше');
  await d.show(waiting);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('categorize-issue');
});
