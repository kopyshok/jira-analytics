import { test, expect } from '@playwright/test';
import { loginAs } from './helpers';

test('resource planning v3 page loads with gamma tag', async ({ page }) => {
  await loginAs(page);
  await page.waitForResponse(r => r.url().includes('/auth/me') || r.url().includes('/auth/login'), { timeout: 10_000 }).catch(() => {});

  await page.goto('/resource-planning-v3');
  await page.waitForLoadState('domcontentloaded');

  await expect(page.getByRole('heading', { name: 'Планирование' })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('γ').first()).toBeVisible();
  await expect(page.getByText('День')).toBeVisible();
  await expect(page.getByText('Неделя')).toBeVisible();
  await expect(page.getByText('Месяц')).toBeVisible();
});

test('sidebar shows three planning entries (legacy + beta + gamma)', async ({ page }) => {
  await loginAs(page);
  await page.waitForResponse(r => r.url().includes('/auth/me') || r.url().includes('/auth/login'), { timeout: 10_000 }).catch(() => {});

  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');

  await expect(page.getByRole('menuitem', { name: /Ресурс\. планир\./ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('menuitem', { name: /Планирование.*β/ })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: /Планирование.*γ/ })).toBeVisible();
});
