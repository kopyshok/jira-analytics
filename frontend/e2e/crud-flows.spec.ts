import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test';
import { expectNoBrowserErrors, expectVisible, trackBrowserErrors } from './helpers';

const backendPort = process.env.E2E_BACKEND_PORT ?? '8010';
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`;
const e2eYear = 2026;
const e2eQuarter = 2;

type ScopeProject = {
  id: string;
  jira_project_key: string;
};

type ScopeRoot = {
  id: string;
  jira_issue_key: string;
};

type CategoryOverride = {
  id: string;
  jira_issue_key: string;
};

type CapacityRule = {
  id: string;
  year: number;
  month: number;
  percent_of_norm: number;
};

type BacklogItem = {
  id: string;
  title: string;
  year: number | null;
  quarter: string | null;
};

type Scenario = {
  id: string;
  name: string;
};

async function apiGet<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`${apiBaseUrl}${path}`);
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<T>;
}

async function clickPrimaryInModal(page: Page) {
  await page.locator('.ant-modal').last().locator('.ant-btn-primary').click();
}

async function confirmPopconfirm(page: Page) {
  await page.locator('.ant-popconfirm').last().locator('.ant-btn-primary').click();
}

async function selectVisibleOption(page: Page, optionText: string) {
  const option = page
    .locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')
    .locator('.ant-select-item-option-content')
    .filter({ hasText: optionText })
    .first();

  await option.click();
}

async function selectFromAntd(select: Locator, page: Page, optionText: string) {
  await select.click();
  await selectVisibleOption(page, optionText);
}

test('scope, capacity, backlog, and planning CRUD flows work with seeded data', async ({
  page,
  request,
}) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/scope');
  await page.getByPlaceholder('Ключ проекта (напр. PROJ)').fill('CRUD');
  await page.getByRole('button', { name: 'Добавить' }).click();
  await expectVisible(page.getByRole('cell', { name: 'CRUD' }));

  let scopeProjects = await apiGet<ScopeProject[]>(request, '/scope/projects');
  expect(scopeProjects.some((project) => project.jira_project_key === 'CRUD')).toBeTruthy();

  await page.getByRole('tab', { name: 'Корневые элементы' }).click();
  await page.getByPlaceholder('Ключ задачи (напр. PROJ-123)').fill('E2E-100');
  await selectFromAntd(page.locator('.ant-tabs-tabpane-active .ant-select').first(), page, 'Технический долг / прочее');
  await page.getByRole('button', { name: 'Добавить' }).click();
  await expectVisible(page.getByRole('cell', { name: 'E2E-100' }));

  let scopeRoots = await apiGet<ScopeRoot[]>(request, '/scope/roots');
  expect(scopeRoots.some((root) => root.jira_issue_key === 'E2E-100')).toBeTruthy();

  await page.getByRole('tab', { name: 'Переопределения' }).click();
  await page.getByPlaceholder('Ключ задачи', { exact: true }).fill('E2E-101');
  await selectFromAntd(page.locator('.ant-tabs-tabpane-active .ant-select').first(), page, 'Сопровождение и консультация');
  await page.getByRole('button', { name: 'Добавить' }).click();
  await expectVisible(page.getByRole('cell', { name: 'E2E-101' }));

  let overrides = await apiGet<CategoryOverride[]>(request, '/scope/overrides');
  expect(overrides.some((override) => override.jira_issue_key === 'E2E-101')).toBeTruthy();

  await page.goto(`/capacity?year=${e2eYear}&quarter=${e2eQuarter}`);
  await expectVisible(page.getByRole('cell', { name: 'E2E Analyst' }));
  await page.getByRole('tab', { name: 'Правила' }).click();
  await page.getByRole('button', { name: 'Добавить правило' }).click();

  const ruleDialog = page.getByRole('dialog', { name: 'Новое правило ёмкости' });
  await ruleDialog.getByLabel('Год').fill(String(e2eYear));
  await selectFromAntd(ruleDialog.locator('.ant-select').first(), page, 'Апрель');
  await ruleDialog.getByLabel('% от нормы').fill('12');
  await clickPrimaryInModal(page);
  await expectVisible(page.getByRole('cell', { name: '12%' }));

  let rules = await apiGet<CapacityRule[]>(request, `/capacity/rules?year=${e2eYear}`);
  expect(
    rules.some((rule) => rule.month === 4 && rule.percent_of_norm === 12),
  ).toBeTruthy();

  await page.goto(`/backlog?year=${e2eYear}&quarter=${e2eQuarter}`);
  await page.getByRole('button', { name: 'Добавить' }).click();

  let backlogDialog = page.getByRole('dialog', { name: 'Новый элемент' });
  await backlogDialog.getByLabel('Название').fill('E2E backlog candidate');
  await selectFromAntd(backlogDialog.locator('.ant-select').first(), page, 'E2E — E2E Project');
  await backlogDialog.getByLabel('Оценка (часы)').fill('16');
  await backlogDialog.getByLabel('Приоритет').fill('1');
  await clickPrimaryInModal(page);
  await expectVisible(page.getByRole('cell', { name: 'E2E backlog candidate' }));

  let backlog = await apiGet<BacklogItem[]>(
    request,
    `/backlog?year=${e2eYear}&quarter=Q${e2eQuarter}`,
  );
  const createdBacklog = backlog.find((item) => item.title === 'E2E backlog candidate');
  expect(createdBacklog).toBeTruthy();

  const createdBacklogRow = page.getByRole('row').filter({ hasText: 'E2E backlog candidate' });
  await createdBacklogRow.locator('button').first().click();

  backlogDialog = page.getByRole('dialog', { name: 'Редактирование' });
  await backlogDialog.getByLabel('Название').fill('E2E backlog candidate updated');
  await clickPrimaryInModal(page);
  await expectVisible(page.getByRole('cell', { name: 'E2E backlog candidate updated' }));

  backlog = await apiGet<BacklogItem[]>(
    request,
    `/backlog?year=${e2eYear}&quarter=Q${e2eQuarter}`,
  );
  expect(backlog.some((item) => item.title === 'E2E backlog candidate updated')).toBeTruthy();

  await page.goto(`/planning?year=${e2eYear}&quarter=${e2eQuarter}`);
  await page.getByRole('button', { name: 'Сгенерировать сценарий' }).click();

  const scenarioDialog = page.getByRole('dialog', { name: 'Новый сценарий' });
  await scenarioDialog.getByLabel('Название сценария').fill('E2E generated scenario');
  await clickPrimaryInModal(page);
  await expectVisible(page.getByText('Результат: E2E generated scenario'));
  await expectVisible(page.getByRole('cell', { name: 'E2E backlog candidate updated' }));
  await expectVisible(page.getByText('Включена'));

  let scenarios = await apiGet<Scenario[]>(
    request,
    `/planning/scenarios?year=${e2eYear}&quarter=${e2eQuarter}`,
  );
  expect(scenarios.some((scenario) => scenario.name === 'E2E generated scenario')).toBeTruthy();

  const scenarioRow = page.getByRole('row').filter({ hasText: 'E2E generated scenario' }).first();
  await scenarioRow.locator('button').last().click();
  await confirmPopconfirm(page);

  scenarios = await apiGet<Scenario[]>(
    request,
    `/planning/scenarios?year=${e2eYear}&quarter=${e2eQuarter}`,
  );
  expect(scenarios.some((scenario) => scenario.name === 'E2E generated scenario')).toBeFalsy();

  await page.goto(`/backlog?year=${e2eYear}&quarter=${e2eQuarter}`);
  const updatedBacklogRow = page.getByRole('row').filter({ hasText: 'E2E backlog candidate updated' });
  await updatedBacklogRow.locator('button').last().click();
  await confirmPopconfirm(page);

  backlog = await apiGet<BacklogItem[]>(
    request,
    `/backlog?year=${e2eYear}&quarter=Q${e2eQuarter}`,
  );
  expect(backlog.some((item) => item.title === 'E2E backlog candidate updated')).toBeFalsy();

  await page.goto(`/capacity?year=${e2eYear}&quarter=${e2eQuarter}`);
  await page.getByRole('tab', { name: 'Правила' }).click();
  const ruleRow = page.getByRole('row').filter({ hasText: '12%' });
  await ruleRow.locator('button').click();
  await confirmPopconfirm(page);

  rules = await apiGet<CapacityRule[]>(request, `/capacity/rules?year=${e2eYear}`);
  expect(rules.some((rule) => rule.month === 4 && rule.percent_of_norm === 12)).toBeFalsy();

  await page.goto('/scope');
  await page.getByRole('tab', { name: 'Переопределения' }).click();
  const overrideRow = page.getByRole('row').filter({ hasText: 'E2E-101' });
  await overrideRow.locator('button').click();
  await confirmPopconfirm(page);

  await page.getByRole('tab', { name: 'Корневые элементы' }).click();
  const rootRow = page.getByRole('row').filter({ hasText: 'E2E-100' });
  await rootRow.locator('button').click();
  await confirmPopconfirm(page);

  await page.getByRole('tab', { name: 'Проекты' }).click();
  const scopeProjectRow = page.getByRole('row').filter({ hasText: 'CRUD' });
  await scopeProjectRow.locator('button').click();
  await confirmPopconfirm(page);

  scopeProjects = await apiGet<ScopeProject[]>(request, '/scope/projects');
  expect(scopeProjects.some((project) => project.jira_project_key === 'CRUD')).toBeFalsy();
  scopeRoots = await apiGet<ScopeRoot[]>(request, '/scope/roots');
  expect(scopeRoots.some((root) => root.jira_issue_key === 'E2E-100')).toBeFalsy();
  overrides = await apiGet<CategoryOverride[]>(request, '/scope/overrides');
  expect(overrides.some((override) => override.jira_issue_key === 'E2E-101')).toBeFalsy();

  await expectNoBrowserErrors(browserErrors);
});
