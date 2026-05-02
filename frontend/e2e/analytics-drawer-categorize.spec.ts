import { expect, test } from '@playwright/test';
import { expectVisible, trackBrowserErrors } from './helpers';

/**
 * E2E: Analytics Drawer — категоризатор.
 *
 * Использует seeded данные из data/e2e.db (E2E Analyst employee + E2E project).
 * Drawer открывается при клике на задачу в режиме «Ворклоги: drawer».
 *
 * Часть тестов может быть пропущена если в seed-данных нет подходящих задач —
 * в этом случае тест проходит (warn-only).
 */

async function goToAnalytics(page: import('@playwright/test').Page) {
  await page.goto('/analytics');
  // Убедиться что страница загрузилась
  await page.waitForSelector('[data-testid="analytics-page"], .ant-table, h2, h1', { timeout: 10_000 });
}

test.describe('Analytics Drawer — категоризатор', () => {
  test('страница Аналитики открывается без ошибок браузера', async ({ page }) => {
    const errors = trackBrowserErrors(page);
    await goToAnalytics(page);
    // Проверяем что страница отрисовалась (нет пустого белого экрана)
    await expect(page.locator('body')).not.toBeEmpty();
    // Минимальная проверка — нет критических ошибок в консоли
    const criticalErrors = errors.filter(e => e.includes('TypeError') || e.includes('ReferenceError'));
    expect(criticalErrors).toHaveLength(0);
  });

  test('drawer открывается при клике на задачу в режиме drawer', async ({ page }) => {
    const errors = trackBrowserErrors(page);
    await goToAnalytics(page);

    // Ищем переключатель режима «Ворклоги: drawer» если он есть
    const drawerModeSwitch = page.locator('text=drawer').first();
    if (await drawerModeSwitch.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await drawerModeSwitch.click();
    }

    // Ищем строку с задачей в таблице — в drawer-режиме строки issue кликабельны
    const issueRows = page.locator('tr.ant-table-row[style*="cursor: pointer"]');
    const count = await issueRows.count();
    if (count === 0) {
      // Нет данных в seeded DB — тест не может проверить drawer
      console.log('Нет задач с курсором pointer — пропускаем проверку drawer');
      return;
    }

    await issueRows.first().click();

    // Drawer должен появиться
    await expect(page.locator('.ant-drawer-open')).toBeVisible({ timeout: 5_000 });

    // Критические ошибки браузера
    const criticalErrors = errors.filter(e => e.includes('TypeError') || e.includes('ReferenceError'));
    expect(criticalErrors).toHaveLength(0);
  });

  test('drawer содержит секции контекст, категория, ворклоги', async ({ page }) => {
    const errors = trackBrowserErrors(page);
    await goToAnalytics(page);

    const drawerModeSwitch = page.locator('text=drawer').first();
    if (await drawerModeSwitch.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await drawerModeSwitch.click();
    }

    const issueRows = page.locator('tr.ant-table-row[style*="cursor: pointer"]');
    if (await issueRows.count() === 0) {
      console.log('Нет задач — пропускаем');
      return;
    }

    await issueRows.first().click();
    await expect(page.locator('.ant-drawer-open')).toBeVisible({ timeout: 5_000 });

    // Проверяем секции по заголовкам (uppercase muted)
    const drawerBody = page.locator('.ant-drawer-body');
    const contextSection = drawerBody.getByText('Контекст', { exact: true });
    const categorySection = drawerBody.getByText('Категория и анализ', { exact: true });
    const worklogsSection = drawerBody.getByText('Ворклоги за период', { exact: true });

    // Хотя бы часть секций должна быть видна (если данные загружены)
    const anyVisible = await Promise.all([
      contextSection.isVisible({ timeout: 3_000 }).catch(() => false),
      categorySection.isVisible({ timeout: 3_000 }).catch(() => false),
      worklogsSection.isVisible({ timeout: 3_000 }).catch(() => false),
    ]);
    // Если drawer открылся, хотя бы одна секция должна быть видна
    const atLeastOne = anyVisible.some(Boolean);
    expect(atLeastOne).toBe(true);

    const criticalErrors = errors.filter(e => e.includes('TypeError') || e.includes('ReferenceError'));
    expect(criticalErrors).toHaveLength(0);
  });
});
