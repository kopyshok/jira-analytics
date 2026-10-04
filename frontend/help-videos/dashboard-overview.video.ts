// Ролик «Как провести утренний обзор команды»: Дашборд — «Проекты квартала»
// (плашки «тишина»/перерасход, прогноз, KPI-плитки, «Настройка вида»),
// «Нормированные работы» (перегруз сотрудника → Аналитика → назад),
// «Ворклоги по категориям» и «Последний ворклог сотрудника», «Баланс часов
// команды» (сортировка, карточка → календарь, подсказка дня). Подписи
// проговаривают связи: список проектов и план — из утверждённого сценария;
// отпуска уменьшают норму в балансе часов.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const YEAR = 2026;
const QUARTER = 3;

interface ProjectItem {
  issue_key: string;
  title: string;
  silent_days: number;
  team_fact_hours: number;
  plan_hours: number;
  status_category: string;
}
interface NormWorkEmployee {
  employee_id: string;
  name: string;
  pct: number;
  fact_hours: number;
  plan_hours: number;
}
interface NormWorkRole {
  employees: NormWorkEmployee[];
}

let silentProjectTitle: string | null = null;
let overrunProjectTitle: string | null = null;
let overloadedEmployeeName = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();

  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } }));
  ok(await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: QUARTER } }));

  const projRes = await request.get(`${api}/analytics/dashboard/projects`, {
    params: { year: YEAR, quarter: QUARTER, teams: TEAM },
  });
  ok(projRes);
  const projData = (await projRes.json()) as { projects: ProjectItem[] };
  silentProjectTitle = projData.projects.find((p) => p.silent_days > 14 && p.status_category !== 'done')?.title ?? null;
  overrunProjectTitle = projData.projects
    .find((p) => p.plan_hours > 0 && p.team_fact_hours > p.plan_hours)?.title ?? null;

  const normRes = await request.get(`${api}/analytics/dashboard/norm-work`, {
    params: { year: YEAR, quarter: QUARTER, teams: TEAM },
  });
  ok(normRes);
  const normData = (await normRes.json()) as { roles: NormWorkRole[] };
  const employees = normData.roles.flatMap((r) => r.employees).filter((e) => e.plan_hours > 0);
  employees.sort((a, b) => b.pct - a.pct);
  overloadedEmployeeName = employees[0]?.name ?? '';
  expect(overloadedEmployeeName, `В демо-команде ${TEAM} нет сотрудников с планом за квартал`).toBeTruthy();

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: QUARTER } });
  await request.dispose();
});

test('dashboard-overview', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/', 'Как провести утренний обзор команды');
  const projectsWidget = page.locator('[data-tour="dash-projects"]');
  await expect(projectsWidget.locator('[data-testid="dash-project-row"]').first()).toBeVisible({ timeout: 20_000 });
  await d.pause(900);
  await d.poster();
  await d.pause(500);

  await d.caption('Проекты квартала — те, что вошли в утверждённый сценарий команды');
  await d.show(projectsWidget);
  await d.pause(500);

  if (silentProjectTitle) {
    const row = projectsWidget.locator('[data-testid="dash-project-row"]', { hasText: silentProjectTitle });
    await d.caption('Плашка «тишина» — по проекту давно никто не списывал часы');
    await d.show(row);
    await d.pause(500);
  }
  if (overrunProjectTitle && overrunProjectTitle !== silentProjectTitle) {
    const row = projectsWidget.locator('[data-testid="dash-project-row"]', { hasText: overrunProjectTitle });
    await d.caption('А эта — что команда потратила больше часов, чем планировала');
    await d.show(row);
    await d.pause(500);
  }

  await d.caption('Колонка «Прогноз» — к какой дате проект закроется при текущем темпе');
  await d.show(projectsWidget.getByText('Прогноз', { exact: true }).first());
  await d.pause(300);

  const kpiTiles = projectsWidget.locator('[data-testid="dash-kpi-tile"]');
  await d.caption('Справа — пять ключевых показателей по всем проектам квартала');
  await d.show(kpiTiles.first(), kpiTiles.last());
  await d.pause(500);

  await d.caption('Правее — активность по неделям: где есть движение');
  await d.show(page.getByText('Активность по неделям'));
  await d.pause(500);

  // Нормированные работы: перегруз сотрудника → Аналитика → назад.
  const normWidget = page.locator('[data-tour="dash-normed"]');
  const employeeBlock = normWidget.locator('[data-testid="dash-norm-employee"]', { hasText: overloadedEmployeeName });
  await d.caption('Нормированные работы — план и факт по каждому сотруднику');
  await d.show(normWidget);
  await d.pause(500);
  const foreignBadge = normWidget.getByText(/чужие \d+ ч/).first();
  if (await foreignBadge.count()) {
    await d.caption('Красная метка — чужие часы: списания на задачи других команд');
    await d.show(foreignBadge);
    await d.pause(300);
  }
  const thematicIcon = normWidget.locator('.anticon-bar-chart').first();
  await d.caption('Значок рядом с видом работ открывает «Тематический отчёт»');
  await d.show(thematicIcon);
  await d.waitVoice();
  await d.click(employeeBlock, 'Щёлкните по имени — откроется Аналитика с часами этого сотрудника');
  await expect(page).toHaveURL(/\/analytics\?employee=/, { timeout: 15_000 });
  const analyticsTable = page.locator('[data-tour="analytics-table"]');
  await expect(analyticsTable).toBeVisible({ timeout: 20_000 });
  await d.caption('Аналитика сразу открылась с фильтром по этому человеку');
  await d.show(page.locator('[data-tour="analytics-filters"] .ant-select').first());
  await d.pause(500);
  await d.waitVoice();
  await d.click(page.locator('.side-item', { hasText: 'Дашборд' }));
  await expect(projectsWidget).toBeVisible({ timeout: 15_000 });
  await d.pause(800);

  // Ворклоги по категориям + последний ворклог сотрудника.
  const catWidget = page.locator('[data-tour="dash-worklogs"]');
  await catWidget.scrollIntoViewIfNeeded();
  const catTile = catWidget.locator('[data-testid="dash-cat-tile"]').first();
  await expect(catTile).toBeVisible({ timeout: 15_000 });
  await d.caption('Ворклоги по категориям — на что фактически ушли часы команды');
  await d.show(catTile);
  await d.pause(500);

  const foreignTile = catWidget.locator('[data-testid="dash-cat-tile"]', { hasText: 'Чужие задачи' }).first();
  if (await foreignTile.count()) {
    await d.caption('Отдельная плитка — чужие задачи без категории');
    await d.show(foreignTile);
    await d.pause(300);
  }

  const worklogCard = catWidget.locator('[data-testid="dash-worklog-card"]').first();
  await expect(worklogCard).toBeVisible();
  await d.caption('А внизу — когда каждый сотрудник последний раз списывал время');
  await d.show(worklogCard);
  await d.pause(500);

  // Баланс часов команды.
  const balanceWidget = page.locator('[data-tour="dash-balance"]');
  await balanceWidget.scrollIntoViewIfNeeded();
  await expect(balanceWidget.locator('[data-testid="dash-balance-card"]').first()).toBeVisible({ timeout: 15_000 });
  await d.caption('Баланс часов команды — переработки и недоработки с начала года');
  await d.show(balanceWidget);
  await d.pause(500);

  await d.caption('Итоговая строка — переработки и нетто всей команды');
  await d.show(balanceWidget.locator('[data-testid="dash-balance-summary"]'));
  await d.waitVoice();
  await d.click(page.locator('[data-testid="dash-balance-sort"] .ant-select'), 'Отсортируйте, например, по переработкам');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Больше переработали' }));

  const firstBalanceCard = balanceWidget.locator('[data-testid="dash-balance-card"]').first();
  await d.click(firstBalanceCard, 'Клик по карточке открывает детальный календарь');
  const balanceModal = page.locator('.ant-modal', { hasText: 'Баланс часов —' });
  await expect(balanceModal).toBeVisible();
  await d.pause(500);

  const dayCell = balanceModal.locator('[data-testid="balance-calendar-day"]').first();
  await dayCell.hover();
  await d.caption('Наведите на день — норма, факт и разница');
  await d.show(dayCell);
  await d.pause(300);

  await d.caption('Отпуск или больничный обнуляет норму дня');
  await d.show(balanceModal.getByText('отпуск/больничный'));
  await d.waitVoice();
  await d.click(balanceModal.locator('.ant-modal-close'));
  await expect(balanceModal).toBeHidden();
  await page.mouse.move(1100, 160);

  await d.caption('Готово', 2800);
  await d.save('dashboard-overview');
});
