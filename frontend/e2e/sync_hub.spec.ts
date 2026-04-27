import { expect, test } from '@playwright/test';
import { expectNoBrowserErrors, trackBrowserErrors } from './helpers';

test('shows main tabs and start button', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/sync');

  // Вкладки хаба
  await expect(page.getByRole('tab', { name: 'Синхронизация' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Расписание' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Дополнительно' })).toBeVisible();

  // Кнопка запуска pipeline
  await expect(page.getByRole('button', { name: 'Запустить' })).toBeVisible();

  await expectNoBrowserErrors(browserErrors);
});

test('schedule tab shows seeded rules', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/sync');
  await page.getByRole('tab', { name: 'Расписание' }).click();

  // Три дефолтных расписания из миграции 035
  await expect(page.getByText('daily_incremental')).toBeVisible();
  await expect(page.getByText('worklogs_workhours')).toBeVisible();
  await expect(page.getByText('weekly_full')).toBeVisible();

  await expectNoBrowserErrors(browserErrors);
});

test('toggling schedule enabled persists after reload', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/sync');
  await page.getByRole('tab', { name: 'Расписание' }).click();

  // Найти строку daily_incremental и получить её переключатель
  const row = page.locator('tr', { hasText: 'daily_incremental' });
  await expect(row).toBeVisible();
  const toggle = row.locator('.ant-switch').first();

  // Читаем текущее состояние
  const wasChecked = await toggle.evaluate(
    (el) => el.classList.contains('ant-switch-checked'),
  );

  // Переключаем
  await toggle.click();
  await page.waitForTimeout(500);

  // Перезагрузка
  await page.reload();
  await page.getByRole('tab', { name: 'Расписание' }).click();

  const rowAfter = page.locator('tr', { hasText: 'daily_incremental' });
  await expect(rowAfter).toBeVisible();
  const toggleAfter = rowAfter.locator('.ant-switch').first();

  const isCheckedAfter = await toggleAfter.evaluate(
    (el) => el.classList.contains('ant-switch-checked'),
  );

  // Состояние должно было измениться
  expect(isCheckedAfter).toBe(!wasChecked);

  // Возвращаем обратно (чтобы не ломать другие тесты)
  await toggleAfter.click();
  await page.waitForTimeout(300);

  await expectNoBrowserErrors(browserErrors);
});
