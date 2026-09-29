// Глава 5 «Заблокированные периоды»: ресурсный план → «Заблокированные периоды» →
// даты, обязательный вид работ, конкретный сотрудник → «Добавить» → в списке видно,
// кому назначен период и на кого период роли теперь не действует (сотрудник главнее).
import { expect, type Locator, type Page, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from '../director.ts';
import { CHAPTERS } from './chapters.ts';
import { apiUrl, chapterTitle, hideVersion, releaseFrame, saveClip } from './common.ts';

const TEAM = 'Команда Альфа';
const REASON = 'Дежурство';

type Scenario = { id: string; team: string | null; year: number | null; quarter: string | null; status: string };
type Plan = { id: string; scenario_id: string | null; parent_plan_id: string | null };
type Block = {
  id: string;
  role_ids: string[];
  employee_ids: string[];
  start_date: string;
  end_date: string;
  reason: string;
  work_type_id: string | null;
  work_type_label: string | null;
};
type Role = { id: string; code: string };
type Member = {
  employee_id: string;
  employee_name: string | null;
  employee_role: string | null;
  member_from?: string | null;
  member_to?: string | null;
  is_borrowed?: boolean;
};

releaseFrame();

let planId = '';
let rival: Block | undefined;
let person: Member | undefined;
let start = dayjs();
let end = dayjs();

// Данные готовим до открытия окна: иначе в начале ролика — тёмные секунды.
test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string): Promise<T> => {
    const res = await request.get(url);
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  expect(
    (await request.patch(`${rp}/preferences`, {
      data: { view_mode: 'tasks', hide_weekends: false, collapsed_initiative_ids: [] },
    })).ok(),
  ).toBeTruthy();

  // Самый свежий сценарий команды. Глава 2 в общем прогоне возвращает его в черновик,
  // а ресурсный план показывает только утверждённые — утверждаем обратно.
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios?teams=${encodeURIComponent(TEAM)}`);
  const scenario = scenarios
    .filter((s) => s.team === TEAM && s.year && s.quarter)
    .sort((a, b) => b.year! - a.year! || b.quarter!.localeCompare(a.quarter!))[0];
  expect(scenario, `нет сценария команды ${TEAM}`).toBeTruthy();
  if (scenario.status !== 'approved') {
    const res = await request.post(`${api}/planning/scenarios/${scenario.id}/approve`, { data: {} });
    expect(res.ok(), `утверждение сценария: ${await res.text()}`).toBeTruthy();
  }

  const plans = await getJson<Plan[]>(`${rp}/resource-plans?team=${encodeURIComponent(TEAM)}`);
  let plan = plans.find((p) => p.scenario_id === scenario.id && !p.parent_plan_id);
  if (!plan) {
    const res = await request.post(`${rp}/resource-plans`, {
      data: { scenario_id: scenario.id, team: TEAM, quarter: scenario.quarter, year: scenario.year },
    });
    expect(res.ok()).toBeTruthy();
    plan = (await res.json()) as Plan;
  }
  planId = plan.id;

  // Период из прошлого прогона в той же копии базы — снимаем, ролик добавит заново.
  let blocks = await getJson<Block[]>(`${rp}/scheduled-blocks?team=${encodeURIComponent(TEAM)}`);
  for (const b of blocks.filter((x) => x.reason === REASON)) {
    expect((await request.delete(`${rp}/scheduled-blocks/${b.id}`)).ok()).toBeTruthy();
  }
  expect((await request.post(`${rp}/resource-plans/${planId}/compute`)).ok()).toBeTruthy();
  blocks = await getJson<Block[]>(`${rp}/scheduled-blocks?team=${encodeURIComponent(TEAM)}`);

  // Период одной роли в квартале плана и человек этой роли на весь квартал:
  // его личный период того же вида в том же месяце главнее — период роли на него
  // перестаёт действовать, и список это показывает.
  const q = Number(scenario.quarter!.replace('Q', ''));
  const qStart = dayjs(`${scenario.year}-${String((q - 1) * 3 + 1).padStart(2, '0')}-01`);
  const qEnd = qStart.add(3, 'month').subtract(1, 'day');
  const roleCode = new Map((await getJson<Role[]>(`${api}/roles`)).map((r) => [r.id, r.code.toLowerCase()]));
  const gantt = await getJson<{ employee_load?: Member[] }>(`${rp}/resource-plans/${planId}/gantt`);
  const members = (gantt.employee_load ?? [])
    .filter((m) => !m.is_borrowed && !m.member_from && !m.member_to && m.employee_name)
    .sort((a, b) => a.employee_name!.localeCompare(b.employee_name!));
  for (const b of blocks) {
    if (b.role_ids.length !== 1 || b.employee_ids.length || !b.work_type_id) continue;
    if (dayjs(b.start_date).isBefore(qStart) || dayjs(b.end_date).isAfter(qEnd)) continue;
    const who = members.find((m) => (m.employee_role ?? '').toLowerCase() === roleCode.get(b.role_ids[0]));
    if (who) {
      rival = b;
      person = who;
      break;
    }
  }
  expect(rival, 'в квартале плана нет периода роли с человеком этой роли в команде').toBeTruthy();

  // Три дня с первого понедельника после середины месяца периода роли.
  start = dayjs(rival!.start_date).date(15);
  while (start.day() !== 1) start = start.add(1, 'day');
  end = start.add(2, 'day');
  await request.dispose();
});

/** Короткий клик для второстепенных шагов: курсор и нажатие видны, без рамки и долгих пауз. */
async function tap(page: Page, target: Locator): Promise<void> {
  const box = await target.boundingBox();
  if (!box) throw new Error(`Элемент не виден на экране: ${target}`);
  await page.evaluate((at) => window.__director?.move(at.x, at.y), {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  });
  await page.waitForTimeout(650);
  await page.evaluate(() => window.__director?.press());
  await page.waitForTimeout(120);
  await target.click();
  await page.waitForTimeout(250);
}

/** Увести курсор под поле справа, чтобы не закрывал набираемый текст. */
async function aside(page: Page, target: Locator): Promise<void> {
  const box = await target.boundingBox();
  if (!box) return;
  await page.evaluate((at) => window.__director?.move(at.x, at.y), {
    x: box.x + box.width + 24,
    y: box.y + box.height + 14,
  });
}

test('05-blocked-periods', async ({ page }) => {
  const name = person!.employee_name!;
  const surname = name.split(' ')[0];
  const workType = rival!.work_type_label!;

  const d = new Director(page);
  await d.install();
  await hideVersion(page);
  await d.open(`/resource-planning?plan_id=${planId}`, chapterTitle(5, CHAPTERS[4]));
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('[data-testid^="rp-bar-"]').first()).toBeVisible({ timeout: 60_000 });
  await page.mouse.move(900, 120);
  await d.pause(900);

  await d.click(
    page.getByRole('button', { name: 'Заблокированные периоды' }),
    'В ресурсном плане откройте «Заблокированные периоды»',
  );
  const modal = page.locator('.ant-modal:visible');
  await expect(modal).toBeVisible();
  // Окно появляется с увеличением: к полям идём, когда оно встало на место.
  await d.pause(450);

  // Даты — щелчками в календаре: Enter в поле даты отправил бы форму, и под
  // пустыми полями всплыли бы красные подсказки.
  const calendar = page.locator('.ant-picker-dropdown:visible');
  const cell = (day: dayjs.Dayjs) =>
    calendar.locator(`td.ant-picker-cell-in-view[title="${day.format('YYYY-MM-DD')}"]`).first();
  await d.caption('Укажите даты периода');
  await tap(page, modal.locator('.ant-picker-range input').first());
  await expect(calendar).toBeVisible();
  for (let i = 0; i < 12 && !(await cell(start).isVisible()); i++) {
    await calendar.locator('.ant-picker-header-next-btn').first().click();
  }
  await tap(page, cell(start));
  await tap(page, cell(end));
  await expect(calendar).toHaveCount(0);

  const dropdown = page.locator('.ant-select-dropdown:visible');
  const field = (id: string) => modal.locator('.ant-select', { has: page.locator(`#${id}`) });
  await d.click(field('work_type_id'), 'Вид работ теперь обязателен: из его запаса спишется день');
  await tap(page, dropdown.locator('.ant-select-item-option', { hasText: workType }).first());
  await expect(field('work_type_id')).toContainText(workType);

  await d.caption('Период можно назначить ролям или конкретным сотрудникам');
  // Поля на разных строках формы: общая рамка захватила бы всю форму — обводим по очереди.
  await d.show(field('role_ids'));
  await d.pause(300);
  await d.show(field('employee_ids'));
  await tap(page, field('employee_ids'));
  await page.keyboard.type(surname, { delay: 100 });
  await expect(dropdown.locator('.ant-select-item-option-active', { hasText: name })).toBeVisible();
  await d.pause(300);
  await page.keyboard.press('Enter');
  await expect(field('employee_ids')).toContainText(name);

  // Щелчок по полю причины заодно закрывает список сотрудников.
  await page.evaluate(() => window.__director?.ring(null));
  const reason = modal.locator('#reason');
  await tap(page, reason);
  await expect(dropdown).toHaveCount(0);
  await aside(page, reason);
  await reason.pressSequentially(REASON, { delay: 80 });
  await d.pause(300);
  await tap(page, modal.getByRole('button', { name: 'Добавить' }));

  const added = modal.locator('.ant-table-row', { hasText: REASON });
  await expect(added).toBeVisible();
  await expect(added).toContainText(`${start.format('DD.MM')}–${end.format('DD.MM')}`);
  await expect(added).toContainText(name);
  const rivalRow = modal
    .locator('.ant-table-row')
    .filter({ hasText: `${dayjs(rival!.start_date).format('DD.MM')}–${dayjs(rival!.end_date).format('DD.MM')}` });
  const notApplied = rivalRow.locator('.ant-typography', { hasText: 'Не действует' });
  await expect(notApplied).toContainText(name);
  await page.mouse.move(900, 60);

  await d.caption('В списке видно, кому назначен период');
  await d.show(added.locator('td').nth(1));
  await d.pause(1000);

  await d.caption('Сотрудник главнее роли: видно, на кого период не действует');
  await d.show(rivalRow.locator('td').nth(1));
  await d.pause(2600);
  await saveClip(page, '05-blocked-periods');

  // Период ролика меняет раскладку плана — следующим главам общего прогона он
  // не нужен: снимаем и пересчитываем план.
  const request = page.context().request;
  const rp = `${apiUrl()}/resource-planning`;
  const blocks: Block[] = await (await request.get(`${rp}/scheduled-blocks?team=${encodeURIComponent(TEAM)}`)).json();
  for (const b of blocks.filter((x) => x.reason === REASON)) {
    expect((await request.delete(`${rp}/scheduled-blocks/${b.id}`)).ok()).toBeTruthy();
  }
  expect((await request.post(`${rp}/resource-plans/${planId}/compute`)).ok()).toBeTruthy();
});
