import { test, expect } from '@playwright/test';
import { loginAs } from './helpers';

test('resource planning v2 page loads with beta tag', async ({ page }) => {
  await loginAs(page);
  // After login, ensure auth state stabilised before navigating
  await page.waitForResponse(r => r.url().includes('/auth/me') || r.url().includes('/auth/login'), { timeout: 10_000 }).catch(() => {});

  await page.goto('/resource-planning-v2');
  await page.waitForLoadState('domcontentloaded');

  await expect(page.getByRole('heading', { name: 'Планирование' })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('β').first()).toBeVisible();
  await expect(page.getByText('По задачам')).toBeVisible();
  await expect(page.getByText('По сотрудникам')).toBeVisible();
});

test('sidebar shows both planning entries (legacy + beta)', async ({ page }) => {
  await loginAs(page);
  await page.waitForResponse(r => r.url().includes('/auth/me') || r.url().includes('/auth/login'), { timeout: 10_000 }).catch(() => {});

  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');

  await expect(page.getByRole('menuitem', { name: /Ресурс\. планир\./ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('menuitem', { name: /Планирование/ }).last()).toBeVisible();
});
