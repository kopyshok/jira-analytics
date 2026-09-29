// Ролик «Как перенести фазу вручную»: полоса фазы → карточка справа → новая
// дата начала → план пересчитан, фаза и тестирование за ней сдвинулись.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

type Scenario = { id: string; name: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null };
type Assignment = {
  backlog_item_id: string;
  phase: string;
  part_number: number;
  employee_id: string | null;
  start_date: string | null;
};

test('resource-plan-phase', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Подготовка до первого кадра: план последнего утверждённого сценария команды
  // без ручных правок и заново рассчитан — исходная картина одна и та же.
  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  const prefs = await page.request.patch(`${rp}/preferences`, {
    data: { view_mode: 'tasks', hide_weekends: false, collapsed_initiative_ids: [] },
  });
  expect(prefs.ok()).toBeTruthy();
  const scenarios: Scenario[] = await (
    await page.request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } })
  ).json();
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  if (!scenario) throw new Error(`Нет утверждённых сценариев команды ${TEAM}`);
  const plans: Plan[] = await (await page.request.get(`${rp}/resource-plans`, { params: { team: TEAM } })).json();
  let plan = plans.find((p) => p.scenario_id === scenario.id);
  if (!plan) {
    const created = await page.request.post(`${rp}/resource-plans`, {
      data: { scenario_id: scenario.id, team: TEAM, quarter: scenario.quarter, year: scenario.year },
    });
    expect(created.ok()).toBeTruthy();
    plan = (await created.json()) as Plan;
  }
  expect((await page.request.post(`${rp}/resource-plans/${plan.id}/bulk-clear`, { data: { mode: 'all' } })).ok()).toBeTruthy();
  expect((await page.request.post(`${rp}/resource-plans/${plan.id}/compute`)).ok()).toBeTruthy();

  // Самая ранняя разработка с исполнителем, за которой идёт тестирование той же задачи.
  const { assignments }: { assignments: Assignment[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const dev = assignments
    .filter((a) => a.phase === 'dev' && a.employee_id && a.start_date)
    .filter((a) => assignments.some((q) => q.phase === 'qa' && q.backlog_item_id === a.backlog_item_id))
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!))[0];
  if (!dev) throw new Error('В плане нет разработки с исполнителем и тестированием');
  const qaStart = (list: Assignment[]) =>
    list.find((q) => q.phase === 'qa' && q.backlog_item_id === dev.backlog_item_id)?.start_date ?? '';
  const qaStartBefore = qaStart(assignments);
  // Новое начало — на неделю позже, в рабочий день.
  let target = dayjs(dev.start_date).add(7, 'day');
  while (target.day() === 0 || target.day() === 6) target = target.add(1, 'day');

  const devBar = page.getByTestId(`rp-bar-${dev.backlog_item_id}-dev-${dev.part_number}`);
  const qaBar = page.locator(`[data-testid^="rp-bar-${dev.backlog_item_id}-qa-"]`).first();

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как перенести фазу вручную');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(devBar).toBeVisible();
  await expect(qaBar).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.caption('Откройте план квартала в «Ресурсном планировании»');
  await d.show(page.locator('[data-tour="rp-scenario-select"]'));
  await d.pause(800);

  await d.click(devBar, 'Нажмите на полосу фазы');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const row = (label: string) =>
    drawer
      .locator('.ant-descriptions-row')
      .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: new RegExp(`^${label}$`) }) });
  await d.caption('Справа откроется карточка фазы');
  await d.show(row('Сотрудник'), row('Окончание'));
  await d.pause(1000);

  await d.click(drawer.locator('.ant-picker'), 'Выберите новую дату начала');
  const dropdown = page.locator('.ant-picker-dropdown:visible');
  if (!target.isSame(dayjs(dev.start_date), 'month')) {
    await d.click(dropdown.locator('.ant-picker-header-next-btn'));
  }
  await d.click(dropdown.locator(`td.ant-picker-cell-in-view[title="${target.format('YYYY-MM-DD')}"]`));
  await expect(dropdown).toHaveCount(0);

  const pinned = drawer.locator('.ant-drawer-header .ant-tag', { hasText: 'Закреплено' });
  await expect(pinned).toBeVisible();
  await expect(drawer.locator('.ant-picker input')).toHaveValue(target.format('YYYY-MM-DD'));
  // План пересчитан: разработка начинается не раньше новой даты, тестирование сдвинулось.
  const after: { assignments: Assignment[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const devAfter = after.assignments.find(
    (a) => a.phase === 'dev' && a.backlog_item_id === dev.backlog_item_id && a.part_number === dev.part_number,
  );
  expect((devAfter?.start_date ?? '') >= target.format('YYYY-MM-DD')).toBeTruthy();
  expect(qaStart(after.assignments) > qaStartBefore).toBeTruthy();
  await d.caption('Окончание сервис пересчитал сам');
  await d.show(row('Начало'), row('Окончание'));
  await d.pause(1200);
  await d.caption('Метка «Закреплено» — дата задана вручную');
  await d.show(pinned);
  await d.pause(1000);

  // Тестирование после сдвига может уйти за правый край диаграммы: докручиваем
  // её, пока карточка закрывает полосы, — зритель прокрутки не видит.
  await qaBar.evaluate((el) => el.scrollIntoView({ block: 'nearest', inline: 'nearest' }));

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  // Настоящая мышь осталась над диаграммой — уводим, чтобы не подсвечивались полосы и связи.
  await page.mouse.move(900, 120);

  await expect(devBar).toBeVisible();
  await expect(qaBar).toBeVisible();
  await d.caption('Фаза переехала, тестирование сдвинулось следом');
  await d.show(devBar, qaBar);
  await d.pause(2000);

  await d.caption('Готово', 2200);
  await d.save('resource-plan-phase');
});
