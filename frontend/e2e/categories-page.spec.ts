import { expect, test } from '@playwright/test';
import { E2E_EMAIL, E2E_PASSWORD, expectNoBrowserErrors, trackBrowserErrors } from './helpers';

test('task categories page exposes the triage workflow', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[type=email]', E2E_EMAIL);
  await page.fill('input[type=password]', E2E_PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL((url) => url.pathname !== '/login');

  const browserErrors = trackBrowserErrors(page);
  await page.goto('/categories');

  await expect(page.getByRole('heading', { name: 'Разбор задач' })).toBeVisible();
  await expect(page.getByText('Выберите задачи, назначьте категорию и сохраните черновик.')).toBeVisible();
  await expect(page.getByRole('button', { name: /К разбору/ }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: /Активные/ }).first()).toBeVisible();
  await expect(page.getByRole('tab', { name: /К разбору/ })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Категория' })).toBeVisible();
  await expect(page.getByText('Все задачи разобраны')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Перейти к активным' })).toBeVisible();

  await expectNoBrowserErrors(browserErrors);
});
