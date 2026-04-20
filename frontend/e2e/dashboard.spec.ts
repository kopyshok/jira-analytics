import { expect, test, type Page, type TestInfo, type Locator } from '@playwright/test';
import { mkdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { expectNoBrowserErrors, expectVisible, trackBrowserErrors } from './helpers';

async function expectDownload(
  page: Page,
  button: Locator,
  testInfo: TestInfo,
  expectedFilename: string,
) {
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    button.click(),
  ]);

  expect(download.suggestedFilename()).toBe(expectedFilename);
  expect(await download.failure()).toBeNull();

  const filePath = testInfo.outputPath('downloads', expectedFilename);
  await mkdir(path.dirname(filePath), { recursive: true });
  await download.saveAs(filePath);

  const fileStats = await stat(filePath);
  expect(fileStats.size).toBeGreaterThan(0);
}

test('dashboard loads KPI cards, charts, and sync status', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/');
  await expectVisible(page.getByText('Всего часов', { exact: true }));
  await expectVisible(page.getByText('Сотрудников', { exact: true }));
  await expectVisible(page.getByText('Проектов', { exact: true }));
  await expectVisible(page.getByText('Ср. переключений', { exact: true }));

  // Sync status collapse is present
  await expectVisible(page.getByText('Статус синхронизации'));

  await expectNoBrowserErrors(browserErrors);
});

test('dashboard filters work', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/');
  await expectVisible(page.getByText('Всего часов'));

  // Employee filter dropdown
  const employeeSelect = page.getByText('Все сотрудники');
  await expect(employeeSelect).toBeVisible();

  // Project filter dropdown
  const projectSelect = page.getByText('Все проекты');
  await expect(projectSelect).toBeVisible();

  await expectNoBrowserErrors(browserErrors);
});

test('dashboard KPI cards navigate to analytics tabs', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/');

  // Click "Сотрудников" KPI card -> analytics employee tab
  await page.locator('.ant-statistic-title', { hasText: 'Сотрудников' }).click();
  await expect(page).toHaveURL(/\/analytics\?tab=employee/);
  await expectVisible(page.getByRole('tab', { name: 'По сотрудникам' }));

  // Go back and click "Проектов" KPI card
  await page.goto('/');
  await page.locator('.ant-statistic-title', { hasText: 'Проектов' }).click();
  await expect(page).toHaveURL(/\/analytics\?tab=project/);
  await expectVisible(page.getByRole('tab', { name: 'По проектам' }));

  await expectNoBrowserErrors(browserErrors);
});

test('dashboard export buttons download files', async ({ page }, testInfo) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/');
  await expectVisible(page.getByRole('button', { name: 'XLSX' }));
  await expectVisible(page.getByRole('button', { name: 'PDF' }));

  await expectDownload(
    page,
    page.getByRole('button', { name: 'XLSX' }),
    testInfo,
    'analytics.xlsx',
  );
  await expectDownload(
    page,
    page.getByRole('button', { name: 'PDF' }),
    testInfo,
    'analytics.pdf',
  );

  await expectNoBrowserErrors(browserErrors);
});

test('analytics tab selection via URL param works', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/analytics?tab=switching');
  await expectVisible(page.getByRole('tab', { name: 'Переключения контекста' }));

  // Verify the switching tab is active
  const activeTab = page.locator('.ant-tabs-tab-active');
  await expect(activeTab).toContainText('Переключения контекста');

  await expectNoBrowserErrors(browserErrors);
});

test('team filter narrows dashboard KPIs', async ({ page }) => {
  await page.goto('/');
  await expectVisible(page.getByText('Всего часов', { exact: true }));

  // Open the team select (FactFilterBar). AntD 6 renders the placeholder as
  // span.ant-select-placeholder inside the select wrapper. Without Jira
  // credentials the only available option is «Без команды» (value __none__).
  const teamSelect = page
    .locator('.ant-select', { has: page.locator('.ant-select-placeholder', { hasText: 'Команда' }) })
    .first();
  await teamSelect.click();

  // Arm the response wait BEFORE clicking the option so the request is
  // observed as soon as TanStack Query reacts to the state change.
  const responsePromise = page.waitForResponse((r) =>
    r.url().includes('/analytics/hours/by-category')
    && r.url().includes('teams=__none__')
  );

  await page
    .locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')
    .locator('.ant-select-item-option-content', { hasText: 'Без команды' })
    .first()
    .click();
  await page.keyboard.press('Escape');

  await responsePromise;
});
