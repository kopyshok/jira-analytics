// Ролик «Как подобрать людей под план и увидеть, кто свободен»: «Загрузка по дням» →
// «Подобрать людей» → поиск по фамилии (у людей плана пометка «уже в плане») →
// сотрудник другой команды → «Вся роль в команде» + «Добавить всех» → «Добавить» →
// секция «Наблюдаемые»: свободные часы по месяцам, самые свободные сверху →
// подсказка у процента загрузки (слой «Другие команды» — за счёт запаса основной
// команды) → «Убрать из наблюдаемых». Данные готовятся в beforeAll; список
// наблюдения плана очищается и до, и после ролика.
import { type APIRequestContext, expect, test } from '@playwright/test';
import { Director } from './director.ts';
import { TEAM } from './rp-setup.ts';

type Scenario = { id: string; name: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null };

/** Сотрудник другой команды, которого находим поиском по фамилии. */
const PICK_NAME = 'Комарова Елена';
/** Команда и роль для «Вся роль в команде». */
const ROLE_TEAM = 'Команда Лямбда';
const ROLE_LABEL = 'Программист';

let planId = '';
let planPersonName = '';

async function clearWatch(request: APIRequestContext, rp: string, id: string) {
  const watch: { rows: { employee_id: string }[] } = await (await request.get(`${rp}/resource-plans/${id}/watch`)).json();
  for (const r of watch.rows) await request.delete(`${rp}/resource-plans/${id}/watch/${r.employee_id}`);
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();

  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } }));
  ok(await request.patch(`${rp}/preferences`, {
    data: { view_mode: 'tasks', hide_weekends: false, collapsed_initiative_ids: [] },
  }));

  const scenarios: Scenario[] = await (
    await request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } })
  ).json();
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  if (!scenario) throw new Error(`Нет утверждённых сценариев команды ${TEAM}`);

  const plans: Plan[] = await (await request.get(`${rp}/resource-plans`, { params: { team: TEAM } })).json();
  let plan = plans.find((p) => p.scenario_id === scenario.id);
  if (!plan) {
    const created = await request.post(`${rp}/resource-plans`, {
      data: { scenario_id: scenario.id, team: TEAM, quarter: scenario.quarter, year: scenario.year },
    });
    ok(created);
    plan = (await created.json()) as Plan;
  }
  planId = plan.id;
  ok(await request.post(`${rp}/resource-plans/${planId}/bulk-clear`, { data: { mode: 'all' } }));
  ok(await request.post(`${rp}/resource-plans/${planId}/compute`));
  await clearWatch(request, rp, planId);

  const gantt: { employee_load: { employee_name: string }[] } = await (
    await request.get(`${rp}/resource-plans/${planId}/gantt`)
  ).json();
  planPersonName = gantt.employee_load[0].employee_name;

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const rp = `${String(testInfo.config.metadata.backendUrl)}/api/v1/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await clearWatch(request, rp, planId);
  await request.dispose();
});

test('rp-watch-people', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open(`/resource-planning?plan_id=${planId}`, 'Как подобрать людей под план и увидеть, кто свободен');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  const load = page.locator('[data-tour="rp-load"]');
  await expect(load).toBeVisible();
  await d.pause(600);
  await d.poster();
  await d.pause(900);

  await load.evaluate((el) => {
    (el as HTMLElement).style.marginBottom = '160px';
  });
  await d.caption('Внизу плана — загрузка сотрудников по дням');
  await load.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  await d.pause(700);
  await d.show(load);
  await d.pause(500);

  await d.click(page.locator('[data-tour="rp-pick-people"]'), 'Кого ещё рассмотреть для плана? Нажмите «Подобрать людей»');
  const modal = page.locator('.ant-modal', { hasText: 'Подобрать людей' });
  await expect(modal).toBeVisible();
  await page.mouse.move(900, 120);

  const search = modal.getByRole('combobox', { name: 'Сотрудники' });
  const options = page.locator('.ant-select-dropdown:visible .ant-select-item-option');
  await d.type(search, planPersonName.split(' ')[0], 'Найдите сотрудника по фамилии');
  const inPlan = options.filter({ hasText: 'уже в плане' }).first();
  await expect(inPlan).toBeVisible();
  await d.caption('У людей плана пометка «уже в плане» — выбрать их нельзя');
  await d.show(inPlan);
  await d.pause(1200);

  await search.press('Control+A');
  await search.press('Backspace');
  await d.type(search, PICK_NAME, 'А сотрудника другой команды — выберите в списке');
  await d.click(options.filter({ hasText: PICK_NAME }).first());
  await modal.locator('.ant-modal-title').click();
  await page.mouse.move(900, 120);

  const teamSelect = modal.getByRole('combobox', { name: 'Команда' });
  await d.caption('Или возьмите сразу всю роль команды');
  await d.show(modal.getByText('Вся роль в команде:'));
  await d.type(teamSelect, ROLE_TEAM.replace('Команда ', ''));
  await d.click(options.filter({ hasText: ROLE_TEAM }).first());
  await d.click(modal.getByRole('combobox', { name: 'Роль' }));
  await d.click(options.filter({ hasText: new RegExp(`^${ROLE_LABEL}$`) }).first());
  await d.click(modal.getByRole('button', { name: 'Добавить всех' }), 'Кнопка «Добавить всех» выберет всех программистов команды');
  await d.pause(500);

  await d.click(modal.getByRole('button', { name: 'Добавить', exact: true }), 'Нажмите «Добавить»');
  await expect(modal).toBeHidden();
  const header = page.locator('[data-tour="rp-watch-header"]');
  await expect(header).toBeVisible();
  await page.mouse.move(900, 120);

  await header.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  await d.pause(700);
  await d.caption('Выбранные появились отдельной секцией «Наблюдаемые»');
  await d.show(header);
  await d.pause(900);

  const free = page.locator('[data-testid="rp-watch-free"]');
  await d.caption('Справа — свободные часы по месяцам. Самые свободные стоят сверху');
  await d.show(free.first(), free.last());
  await d.pause(1500);

  // Процент у выбранного поиском сотрудника: у него есть часы других команд.
  const pct = page.locator(
    `xpath=//*[contains(normalize-space(text()), "${PICK_NAME}")]/ancestor::div[.//*[@data-testid="rp-watch-pct"]][1]//*[@data-testid="rp-watch-pct"]`,
  ).first();
  await expect(pct).toBeVisible();
  await d.caption('Наведите на процент — видно, из чего сложилась загрузка');
  await d.point(pct);
  await pct.hover();
  await d.pause(1800);
  await d.caption('Часы других команд идут за счёт запаса основной команды');
  await d.pause(2200);
  await page.mouse.move(900, 120);

  const remove = page.getByRole('button', { name: /^Убрать из наблюдаемых/ }).first();
  await d.click(remove, 'Ненужного человека можно убрать крестиком');
  await page.mouse.move(900, 120);
  await d.pause(900);
  await d.show(free.first(), free.last());
  await d.pause(900);

  await d.caption('Готово', 2200);
  await d.save('rp-watch-people');
});
