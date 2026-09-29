import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

// Регрессия: сумма ширин соседних колонок больше области прокрутки таблицы —
// колонка «Идея» без своей ширины схлопывалась в ноль, названия шли по букве в столбик.
test('backlog: колонка «Идея» не схлопывается ни в одной вкладке', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await loginAs(page);

  // Вкладку выбираем адресом: так не мешает модалка «Что нового» при первом входе.
  for (const view of ['quarterly', 'active', 'archived']) {
    await page.goto(`/backlog?year=2026&quarter=2&view=${view}`);
    const header = page.locator('.ant-tabs-tabpane-active').getByRole('columnheader', { name: 'Идея' }).first();
    await expect(header).toBeVisible();
    expect((await header.boundingBox())?.width ?? 0, view).toBeGreaterThan(200);
  }
});
