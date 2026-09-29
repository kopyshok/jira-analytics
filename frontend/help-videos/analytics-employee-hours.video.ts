// Ролик «Как посмотреть, куда ушли часы сотрудника»: Аналитика → фильтр по
// сотруднику → раскрыть дерево до вида работ/категории → часы в строке →
// переключатель «Иерархия».
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const YEAR = 2026;
const QUARTER = 3;

test('analytics-employee-hours', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = String(test.info().config.metadata.backendUrl);

  // Тот же квартал и та же команда при любом запуске — иначе на «сегодня»
  // могло попасть пустое полугодие без ворклогов.
  const teamsRes = await page.request.put(`${api}/api/v1/auth/me/teams`, {
    data: { teams: [TEAM], subgroups: [] },
  });
  expect(teamsRes.ok()).toBeTruthy();
  const periodRes = await page.request.put(`${api}/api/v1/users/me/period`, {
    data: { year: YEAR, quarter: QUARTER },
  });
  expect(periodRes.ok()).toBeTruthy();

  // Список сотрудников в фильтре не ограничен командой — берём того, у кого
  // реально есть часы в этой команде и квартале, иначе фильтр даст «Нет данных».
  const reportRes = await page.request.get(
    `${api}/api/v1/analytics/report?year=${YEAR}&quarter=${QUARTER}&teams=${encodeURIComponent(TEAM)}`,
  );
  expect(reportRes.ok()).toBeTruthy();
  const report = (await reportRes.json()) as {
    teams: { roles: { employees: { name: string; totals: { fact_hours: number } }[] }[] }[];
  };
  const employeeName = report.teams
    .flatMap((t) => t.roles)
    .flatMap((r) => r.employees)
    .sort((a, b) => b.totals.fact_hours - a.totals.fact_hours)[0]?.name;
  expect(employeeName, 'В демо-команде нет сотрудника с часами за квартал').toBeTruthy();

  await d.open('/analytics', 'Как посмотреть, куда ушли часы сотрудника');
  const table = page.locator('[data-tour="analytics-table"]');
  await expect(table.locator('tbody tr.ant-table-row').first()).toBeVisible({ timeout: 20_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  // Первый Select в блоке фильтров — «Сотрудник» (поиск по имени).
  const employeeSelect = page.locator('[data-tour="analytics-filters"] .ant-select').first();
  await d.click(employeeSelect, 'Найдите сотрудника через фильтр');
  await employeeSelect.locator('input').pressSequentially(employeeName, { delay: 60 });
  const employeeOption = page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: employeeName });
  await expect(employeeOption).toBeVisible();
  await d.click(employeeOption);
  await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);

  // Дерево свёрнуто по умолчанию: раскрываем команду → роль → сотрудника → вид работ.
  await d.caption('Раскройте строку до вида работ и категории');
  await d.click(table.locator('tr.tree-row-depth-0.tree-row-has-children').first());
  await d.click(table.locator('tr.tree-row-depth-1.tree-row-has-children').first());
  await d.click(table.locator('tr.tree-row-depth-2.tree-row-has-children').first());
  await d.click(table.locator('tr.tree-row-depth-3.tree-row-has-children').first());

  const categoryRow = table.locator('tr.tree-row-depth-4').first();
  await expect(categoryRow).toBeVisible();
  await d.caption('Вот сколько часов ушло в эту категорию');
  await d.show(categoryRow);
  await d.pause(1400);

  await d.caption('Есть переключатель «Иерархия» — задачи можно смотреть деревом до родителя');
  await d.click(page.locator('[data-tour="analytics-hierarchy"] .ant-switch'));
  await d.pause(1200);

  await d.caption('Готово', 2200);
  await d.save('analytics-employee-hours');
});
