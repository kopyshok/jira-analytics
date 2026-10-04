// Ролик «Как увидеть переток часов между группами»: шапка на «Команда Эта» →
// Аналитика → «Настройка отчёта»: включить уровень «Группа» → строки групп в
// дереве → строка «Переток внутри команды». В конце раскладка отчёта и шапка
// возвращены (на «Команда Альфа» без групп, стандартная раскладка).
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Эта';
const HOME_TEAM = 'Команда Альфа';
const YEAR = 2026;

interface FlowReport {
  subgroup_flow?: { out_hours: number; in_hours: number }[];
}

const DEFAULT_LAYOUT = {
  group_order: ['team', 'subgroup', 'role', 'employee', 'work_type', 'category', 'issue'],
  hidden_levels: ['subgroup'],
  active_preset: 'default',
  show_fact_bar: true,
};

let flowQuarter = 3;

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();

  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } }));
  ok(await request.put(`${api}/users/me/analytics-layout`, { data: { layout: DEFAULT_LAYOUT } }));
  // Квартал, где у команды реально есть переток между группами.
  let found = false;
  for (const quarter of [3, 2, 4, 1]) {
    const res = await request.get(`${api}/analytics/report`, { params: { year: YEAR, quarter, teams: TEAM } });
    if (!res.ok()) continue;
    const report = (await res.json()) as FlowReport;
    if (report.subgroup_flow?.some((f) => f.out_hours > 0 || f.in_hours > 0)) {
      flowQuarter = quarter;
      found = true;
      break;
    }
  }
  expect(found, `У команды ${TEAM} нет перетока между группами ни в одном квартале ${YEAR}`).toBeTruthy();
  ok(await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: flowQuarter } }));

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/users/me/analytics-layout`, { data: { layout: DEFAULT_LAYOUT } });
  await request.put(`${api}/auth/me/teams`, { data: { teams: [HOME_TEAM], subgroups: [] } });
  await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: 3 } });
  await request.dispose();
});

test('analytics-groups-flow', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/analytics', 'Как увидеть переток часов между группами');
  const table = page.locator('[data-tour="analytics-table"]');
  await expect(table.locator('tbody tr.ant-table-row').first()).toBeVisible({ timeout: 20_000 });
  await d.pause(900);
  await d.poster();
  await d.pause(1200);

  await d.caption('В шапке выбрана команда, в которой есть группы');
  await d.show(page.locator('[data-tour="header-team"]'));
  await d.waitVoice();

  await d.click(page.locator('[data-tour="header-team"] button'), 'Блок «Группы» в шапке сужает отчёт до выбранных групп');
  const subgroupBlock = page.locator('[data-testid="team-filter-subgroups"]');
  await expect(subgroupBlock).toBeVisible();
  await d.show(subgroupBlock);
  await d.waitVoice();
  await page.keyboard.press('Escape');
  await expect(subgroupBlock).toBeHidden();
  await page.mouse.move(1100, 160);

  await d.click(page.locator('[data-tour="analytics-settings"]'), 'Откройте «Настройку отчёта»');
  const settingsModal = page.locator('.ant-modal', { hasText: 'Настройка отчёта' });
  await expect(settingsModal).toBeVisible();
  const groupLevel = settingsModal.locator('div').filter({ hasText: /^Группа$/ }).last();
  await d.caption('Уровень «Группа» сейчас скрыт — включите его глазком');
  await d.show(groupLevel);
  await d.waitVoice();
  await d.click(groupLevel.locator('button.ant-btn'));
  await d.waitVoice();
  await page.keyboard.press('Escape');
  await expect(settingsModal).toBeHidden();

  const teamRow = table.locator('tr.tree-row-depth-0').first();
  await expect(teamRow).toBeVisible({ timeout: 15_000 });
  await d.click(teamRow, 'Раскройте команду — внутри появились группы');
  const groupRow = table.locator('tr.tree-row-depth-1').first();
  await expect(groupRow).toBeVisible({ timeout: 15_000 });
  await d.show(groupRow, table.locator('tr.tree-row-depth-1').last());
  await d.waitVoice();

  const flowLine = page.getByText('Переток внутри команды', { exact: true });
  await expect(flowLine).toBeVisible({ timeout: 15_000 });
  await d.caption('Строка «Переток внутри команды» — кто кому помог часами');
  await d.show(flowLine.locator('xpath=..'));
  await d.waitVoice();

  await d.caption('Минус — часы ушли соседям, плюс — пришли от соседей');
  await d.show(flowLine.locator('xpath=..'));
  await d.waitVoice();

  const ungroupedRow = table.locator('tr', { hasText: 'Без группы' }).first();
  await d.caption('Строка «Без группы» — часы сотрудников, которых ещё не распределили');
  await d.show(ungroupedRow);
  await d.waitVoice();

  await d.caption('Это обмен внутри команды, помощь извне считается отдельно');
  await d.show(page.locator('[data-tour="analytics-kpi"]'));
  await d.waitVoice();

  await d.click(page.locator('[data-tour="analytics-settings"]'), 'Прежний вид возвращается тем же глазком');
  await expect(settingsModal).toBeVisible();
  await d.click(settingsModal.locator('div').filter({ hasText: /^Группа$/ }).last().locator('button.ant-btn'));
  await d.waitVoice();
  await settingsModal.locator('.ant-modal-close').click();
  await expect(settingsModal).toBeHidden();
  await page.mouse.move(1100, 160);
  await d.pause(600);

  await d.caption('Готово', 2200);
  await d.save('analytics-groups-flow');
});
