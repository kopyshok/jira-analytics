// Ролик «Как завести идею и оценить её по ролям»: Целевые задачи → вкладка «Бэклог» →
// «Идея вручную» → название и оценки часов по ролям → сохранить → строка в списке.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TITLE = 'Личный кабинет поставщика';

test('backlog-idea-add', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Боковая ссылка «Целевые задачи» ведёт на голый /backlog (без ?view=) — открываем
  // так и переключаемся на «Бэклог» кликом по вкладке, а не query-параметром в URL,
  // иначе редундантный клик по разделу в кадре сбросил бы вкладку обратно.
  await d.open('/backlog', 'Как завести идею и оценить её по ролям');
  const pane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }), 'Откройте раздел «Целевые задачи»');
  await d.click(
    page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: 'Бэклог' }),
    'Перейдите на вкладку «Бэклог»',
  );
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible();

  await d.click(page.locator('[data-tour="backlog-manual-idea"]'), 'Нажмите «Идея вручную»');
  const modal = page.locator('.ant-modal', { hasText: 'Новая идея' });
  await expect(modal).toBeVisible();

  const field = (label: string) => modal.locator('.ant-form-item', { hasText: label }).last();
  await d.type(field('Название').locator('input'), TITLE, 'Введите название идеи');
  await d.type(field('АН ч').locator('input'), '40', 'Оцените часы аналитика');
  await d.type(field('ПР ч').locator('input'), '120', 'Часы разработки');
  await d.type(field('ТС ч').locator('input'), '24', 'И часы тестирования');

  await d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните');
  await expect(modal).toBeHidden();

  const row = pane.locator('tbody tr', { hasText: TITLE });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await d.caption('Идея появилась в списке');
  await d.show(row);
  await d.pause(1400);

  await d.caption('Готово', 2200);
  await d.save('backlog-idea-add');
});
