import { expect, test, type APIRequestContext, type Locator, type Page, type TestInfo } from '@playwright/test';
import { mkdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { expectNoBrowserErrors, expectVisible, trackBrowserErrors } from './helpers';

const backendPort = process.env.E2E_BACKEND_PORT ?? '8010';
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`;
const e2eProjectId = '00000000-0000-0000-0000-000000000002';
const exportYear = 2027;
const exportQuarter = 3;

type BacklogItem = {
  id: string;
};

type PlanningResult = {
  scenario_id: string;
  allocations: Array<{
    included: boolean;
  }>;
};

async function apiPost<T>(
  request: APIRequestContext,
  pathName: string,
  data: Record<string, unknown>,
): Promise<T> {
  const response = await request.post(`${apiBaseUrl}${pathName}`, { data });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<T>;
}

async function apiDelete(request: APIRequestContext, pathName: string) {
  await request.delete(`${apiBaseUrl}${pathName}`);
}

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

test('analytics exports download non-empty files', async ({ page }, testInfo) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/analytics');
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

test('scenario exports download non-empty files', async ({ page, request }, testInfo) => {
  const browserErrors = trackBrowserErrors(page);
  let backlogId: string | undefined;
  let scenarioId: string | undefined;

  try {
    const backlogItem = await apiPost<BacklogItem>(request, '/backlog', {
      title: 'E2E export backlog candidate',
      project_id: e2eProjectId,
      quarter: `Q${exportQuarter}`,
      year: exportYear,
      estimate_hours: 8,
      priority: 1,
    });
    backlogId = backlogItem.id;

    const scenario = await apiPost<PlanningResult>(
      request,
      '/planning/scenarios/generate',
      {
        name: 'E2E export scenario',
        year: exportYear,
        quarter: exportQuarter,
        backlog_item_ids: [backlogId],
      },
    );
    scenarioId = scenario.scenario_id;
    expect(scenario.allocations.length).toBeGreaterThan(0);

    await page.goto(`/planning?year=${exportYear}&quarter=${exportQuarter}`);
    const scenarioRow = page.getByRole('row').filter({ hasText: 'E2E export scenario' }).first();
    await expectVisible(scenarioRow);

    await expectDownload(
      page,
      scenarioRow.getByRole('button', { name: 'XLSX' }),
      testInfo,
      `${scenarioId}.xlsx`,
    );
    await expectDownload(
      page,
      scenarioRow.getByRole('button', { name: 'PPTX' }),
      testInfo,
      `${scenarioId}.pptx`,
    );

    await expectNoBrowserErrors(browserErrors);
  } finally {
    if (scenarioId) {
      await apiDelete(request, `/planning/scenarios/${scenarioId}`);
    }
    if (backlogId) {
      await apiDelete(request, `/backlog/${backlogId}`);
    }
  }
});
