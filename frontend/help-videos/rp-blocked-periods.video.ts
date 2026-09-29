// Ролик «Как заблокировать период и следить за запасом нормированных работ»:
// «Заблокированные периоды» → даты, вид работ, роль, причина → «Добавить» →
// штриховка на диаграмме → план сам не пересчитывается → «Распределить» →
// фазы обошли дни → «Нормированные работы — запас квартала»: новая строка
// показывает, сколько часов роли ушло на период. Период удаляется в afterAll.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import type { ReserveOut, ScheduledBlock } from '../src/api/resourcePlanning.ts';
import { Director } from './director.ts';
import { TEAM, prepareQuarterPlan } from './rp-setup.ts';

const REASON = 'Корпоративное обучение';

type FullAssignment = {
  backlog_item_id: string;
  phase: string;
  part_number: number;
  start_date: string | null;
};

const key = (a: FullAssignment) => `${a.backlog_item_id}-${a.phase}-${a.part_number}`;

let createdBlockId: string | null = null;

test.afterAll(async ({ playwright }, testInfo) => {
  // Период — только для этого ролика; убираем его, чтобы не менять запас
  // и расписание для остальных роликов, снимаемых на той же копии базы.
  if (!createdBlockId) return;
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.delete(`${api}/resource-planning/scheduled-blocks/${createdBlockId}`);
  await request.dispose();
});

test('rp-blocked-periods', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const { api, rp, plan, assignments } = await prepareQuarterPlan(page);

  // Роль «Разработчик» (или первая активная роль) и вид работ с запасом,
  // которого пока никто не касался, — после блокировки в сводке появится
  // новая строка, а не изменится существующая.
  const roles: { id: string; code: string; label: string; is_active: boolean }[] = await (
    await page.request.get(`${api}/roles`)
  ).json();
  const role = roles.find((r) => r.is_active && r.code.toLowerCase() === 'dev') ?? roles.find((r) => r.is_active);
  if (!role) throw new Error('В справочнике нет ролей');

  const workTypes: { id: string; label: string; subtracts_from_pool: boolean }[] = await (
    await page.request.get(`${api}/mandatory-work-types`, { params: { is_active: 'true' } })
  ).json();
  const workType =
    workTypes.find((w) => w.subtracts_from_pool && w.label === 'Минорные изменения') ??
    workTypes.find((w) => w.subtracts_from_pool);
  if (!workType) throw new Error('В справочнике нет видов работ, расходующих запас');

  const reserveBefore = (
    await (await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)).json()
  ).reserve as ReserveOut | null;
  const usedBefore =
    reserveBefore?.roles
      .find((r) => r.role === role.code)
      ?.rows.find((row) => row.work_type_id === workType.id)?.blocked_hours ?? 0;

  // Неделя внутри плана, отступив от самого начала — там уже идёт активная работа.
  const starts = assignments.filter((a) => a.start_date).map((a) => a.start_date as string).sort();
  if (!starts.length) throw new Error('В плане нет фаз с датой начала');
  let monday = dayjs(starts[0]).add(9, 'day');
  while (monday.day() !== 1) monday = monday.add(1, 'day');
  const friday = monday.add(4, 'day');

  const before: { assignments: FullAssignment[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const beforeStart = new Map(before.assignments.map((a) => [key(a), a.start_date]));

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как заблокировать период');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(page.locator('[data-testid^="rp-bar-"]').first()).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(700);
  await d.poster();
  await d.pause(1200);

  await d.click(
    page.getByRole('button', { name: 'Заблокированные периоды' }),
    'Откройте «Заблокированные периоды»',
  );
  const modal = page.locator('.ant-modal:visible');
  await expect(modal).toBeVisible();

  const dates = modal.locator('[data-testid="rp-block-dates"]');
  const rangeInputs = dates.locator('input');
  await d.type(rangeInputs.nth(0), monday.format('DD.MM.YYYY'), 'Укажите начало и конец периода');
  await d.type(rangeInputs.nth(1), friday.format('DD.MM.YYYY'));
  await rangeInputs.nth(1).press('Enter');

  const workTypeField = modal.locator('[data-testid="rp-block-work-type"]');
  await d.click(workTypeField.locator('.ant-select'), 'Выберите вид работ — от него зависит, какой запас спишется');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: workType.label }));

  const rolesField = modal.locator('[data-testid="rp-block-roles"]');
  await d.click(rolesField.locator('.ant-select'), 'Можно ограничить период одной ролью');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: role.label }));
  await page.keyboard.press('Escape');

  const reasonInput = modal.locator('[data-testid="rp-block-reason"] input');
  await d.type(reasonInput, REASON, 'И укажите причину');

  await d.click(modal.locator('[data-testid="rp-block-submit"] button'));
  const table = modal.locator('.ant-table');
  await expect(table.getByText(REASON)).toBeVisible();
  await expect(table.getByText(role.label)).toBeVisible();
  await d.caption('Период добавлен в список блокировок');
  await d.show(table.getByText(REASON));
  await d.pause(1300);

  const blocks: ScheduledBlock[] = await (
    await page.request.get(`${rp}/scheduled-blocks`, { params: { team: TEAM } })
  ).json();
  const created = blocks.find((b) => b.reason === REASON);
  if (!created) throw new Error('Период не найден после создания');
  createdBlockId = created.id;

  await d.click(modal.locator('.ant-modal-close'), 'Закройте окно');
  await expect(page.locator('.ant-modal:visible')).toHaveCount(0);

  const zone = page.locator(`[title="${REASON}"]`).first();
  await expect(zone).toBeVisible();
  await zone.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('На диаграмме появилась заблокированная полоса');
  await d.show(zone);
  await d.pause(1200);
  await d.caption('Сам план ещё не поменялся — нужно «Распределить»');
  await d.pause(900);

  await d.click(page.locator('[data-tour="rp-distribute"]'), 'Нажмите «Распределить», чтобы пересчитать план');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });

  const after: { assignments: FullAssignment[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const changed = after.assignments.some(
    (a) => beforeStart.has(key(a)) && beforeStart.get(key(a)) !== a.start_date,
  );
  expect(changed).toBeTruthy();

  await expect(page.locator('[data-testid^="rp-bar-"]').first()).toBeVisible();
  await page.mouse.move(900, 120);
  await d.caption('Фазы обошли заблокированный период');
  await zone.scrollIntoViewIfNeeded();
  await d.show(zone);
  await d.pause(1600);

  const reserveAfter = (
    await (await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)).json()
  ).reserve as ReserveOut | null;
  const usedAfter =
    reserveAfter?.roles
      .find((r) => r.role === role.code)
      ?.rows.find((row) => row.work_type_id === workType.id)?.blocked_hours ?? 0;
  expect(usedAfter).toBeGreaterThan(usedBefore);

  const summary = page.locator('[data-testid="rp-reserve-summary"]');
  await summary.scrollIntoViewIfNeeded();
  await d.click(page.locator('[data-testid="rp-reserve-toggle"]'), '«Нормированные работы — запас квартала»: раскройте сводку');
  const row = summary.locator('tr', { hasText: workType.label });
  await expect(row).toBeVisible();
  await d.caption('Заложено на квартал / уже занято / осталось — по каждому виду работ');
  await d.show(row);
  await d.pause(2000);

  await d.caption('Запас считается по правилам сценария');
  await d.show(summary);
  await d.pause(2000);

  await d.caption('Готово', 2200);
  await d.save('rp-blocked-periods');
});
