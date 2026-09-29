// Ролик «Как заблокировать период»: «Заблокированные периоды» → диапазон дат
// → причина → «Добавить» → на графике появляется зона → «Распределить»
// разводит фазы вокруг неё.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';
import { prepareQuarterPlan } from './rp-setup.ts';

const REASON = 'Корпоративное обучение';

type FullAssignment = {
  backlog_item_id: string;
  phase: string;
  part_number: number;
  start_date: string | null;
};

const key = (a: FullAssignment) => `${a.backlog_item_id}-${a.phase}-${a.part_number}`;

test('rp-blocked-periods', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const { rp, plan, assignments } = await prepareQuarterPlan(page);

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

  const rangeInputs = modal.locator('.ant-picker-range input');
  await d.type(rangeInputs.nth(0), monday.format('DD.MM.YYYY'), 'Укажите начало периода');
  await d.type(rangeInputs.nth(1), friday.format('DD.MM.YYYY'), 'И его конец');
  await rangeInputs.nth(1).press('Enter');

  const reasonInput = modal.locator('input[placeholder="Причина"]');
  await d.type(reasonInput, REASON, 'Укажите причину — роль оставим общей, для всей команды');

  await d.click(modal.getByRole('button', { name: 'Добавить' }));
  const table = modal.locator('.ant-table');
  await expect(table.getByText(REASON)).toBeVisible();
  await expect(table.getByText(monday.format('YYYY-MM-DD'))).toBeVisible();
  await d.caption('Период добавлен в список блокировок');
  await d.show(table.getByText(REASON));
  await d.pause(1200);

  await d.click(modal.locator('.ant-modal-close'), 'Закройте окно');
  await expect(page.locator('.ant-modal:visible')).toHaveCount(0);

  const zone = page.locator(`[title="${REASON}"]`).first();
  await expect(zone).toBeVisible();
  await zone.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('На графике появилась заблокированная полоса');
  await d.show(zone);
  await d.pause(1400);

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
  await d.pause(1800);

  await d.caption('Готово', 2200);
  await d.save('rp-blocked-periods');
});
