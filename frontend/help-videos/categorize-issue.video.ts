// Ролик «Как отнести задачу к категории»: Категории задач → очередь «К разбору» →
// категория у задачи → сохранить → задача ушла из очереди.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const CATEGORY = 'Технические задачи';

test('categorize-issue', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open('/categories', 'Как отнести задачу к категории');

  const table = page.locator('[data-tour="categories-table"]');
  // Задача без подзадач и не «контекстная» (чужой родитель без права правки).
  const issue = table.locator('tbody tr.ant-table-row:not(.tree-row-has-children):not(.tree-row-context)').first();
  await expect(issue).toBeVisible({ timeout: 60_000 });
  const issueKey = await issue.getAttribute('data-row-key');
  const stackCard = page.locator('[data-tour="categories-queues"] .category-queue-card').first();
  await expect(stackCard).toContainText('К разбору');
  const stackBefore = Number(await stackCard.locator('.category-queue-count').innerText());
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.locator('.side-item', { hasText: 'Категории задач' }), 'Откройте раздел «Категории задач»');
  await d.click(stackCard, 'Очередь «К разбору» — задачи без решения');
  await d.pause(600);

  await d.click(issue.locator('.ant-select'), 'Откройте список категорий у задачи');
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: CATEGORY }),
    'Выберите подходящую категорию',
  );

  await d.click(issue.getByTitle('Сохранить категорию'), 'Сохраните — кнопка с галочкой');
  await expect(table.locator(`tr[data-row-key="${issueKey}"]`)).toHaveCount(0);
  await expect(stackCard.locator('.category-queue-count')).toHaveText(String(stackBefore - 1));

  await d.caption('Задача ушла из очереди «К разбору»');
  await d.show(stackCard);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('categorize-issue');
});
