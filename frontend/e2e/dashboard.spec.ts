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

test('dashboard loads three widgets', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/');
  // Все три виджета по заголовкам карточек
  await expectVisible(page.getByText('Проекты квартала', { exact: true }));
  await expectVisible(page.getByText('Нормированные работы', { exact: true }));
  await expectVisible(page.getByText('Ворклоги по категориям задач', { exact: true }));

  await expectNoBrowserErrors(browserErrors);
});

test('dashboard quarter picker is visible', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/');
  // QuarterPicker рендерит кнопки кварталов Q1-Q4
  await expectVisible(page.getByRole('button', { name: 'Q1' }));
  await expectVisible(page.getByRole('button', { name: 'Q2' }));
  await expectVisible(page.getByRole('button', { name: 'Q3' }));
  await expectVisible(page.getByRole('button', { name: 'Q4' }));

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
