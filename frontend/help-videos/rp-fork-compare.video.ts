// Ролик «Как сделать копию плана и сравнить»: «Сделать копию плана» → название
// копии → в копии перенесена фаза → «Сравнить с базовым» → итоги двух планов
// и список сдвинутых фаз.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import type { AssignmentOut, GanttProjection } from '../src/api/resourcePlanning.ts';
import { sortAssignmentsByScenarioAssignee } from '../src/utils/sortAssignments.ts';
import { Director } from './director.ts';
import { phaseBar, prepareQuarterPlan } from './rp-setup.ts';

const LABEL = 'Вариант Б';

test('rp-fork-compare', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Подготовка до первого кадра: план без ручных правок. В копии переносим
  // разработку первой задачи диаграммы на неделю позже.
  const { rp, plan } = await prepareQuarterPlan(page);
  const g = (await (await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)).json()) as GanttProjection;
  const dev = sortAssignmentsByScenarioAssignee(g.assignments).find(
    (a) => a.phase === 'dev' && a.employee_id && a.start_date,
  );
  if (!dev) throw new Error('В плане нет разработки с исполнителем');
  let target = dayjs(dev.start_date).add(7, 'day');
  while (target.day() === 0 || target.day() === 6) target = target.add(1, 'day');

  const devBar = phaseBar(page, dev);
  const nextBar = page.locator(`[data-testid^="rp-bar-${dev.backlog_item_id}-qa-"]`).first();

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как сделать копию плана и сравнить');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(devBar).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.getByRole('button', { name: 'Сделать копию плана' }), 'Нажмите «Сделать копию плана»');
  const modal = page.locator('.ant-modal', { hasText: 'Сделать копию плана' });
  await expect(modal).toBeVisible();
  await d.type(modal.locator('input'), LABEL, 'Назовите копию');
  await d.click(modal.getByRole('button', { name: 'Создать' }));
  await expect(modal).toBeHidden();

  const tag = page.locator('.ant-tag', { hasText: new RegExp(`^${LABEL}$`) });
  await expect(tag).toBeVisible();
  const forkId = new URL(page.url()).searchParams.get('plan_id');
  expect(forkId).toBeTruthy();
  expect(forkId).not.toBe(plan.id);
  await expect(devBar).toBeVisible();
  await page.mouse.move(900, 120);
  await d.caption('Вы в копии — её название рядом со статусом');
  await d.show(tag);
  await d.pause(1200);

  await d.click(devBar, 'Поменяйте что-нибудь, например начало фазы');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  await d.click(drawer.locator('.ant-picker'), 'Выберите новую дату');
  const dropdown = page.locator('.ant-picker-dropdown:visible');
  if (!target.isSame(dayjs(dev.start_date), 'month')) {
    await d.click(dropdown.locator('.ant-picker-header-next-btn'));
  }
  await d.click(dropdown.locator(`td.ant-picker-cell-in-view[title="${target.format('YYYY-MM-DD')}"]`));
  await expect(dropdown).toHaveCount(0);
  await expect(drawer.locator('.ant-drawer-header .ant-tag', { hasText: 'Закреплено' })).toBeVisible();

  // Изменилась только копия: в ней фаза сдвинута, в базовом плане — на месте.
  const diff = await (await page.request.get(`${rp}/resource-plans/${forkId}/diff/${plan.id}`)).json();
  const shift = (diff.assignment_shifts as Array<Pick<AssignmentOut, 'backlog_item_id' | 'phase'> & { kind: string }>)
    .find((s) => s.backlog_item_id === dev.backlog_item_id && s.phase === 'dev');
  expect(shift?.kind).toBe('shifted');

  await nextBar.evaluate((el) => el.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);
  await d.caption('Фаза сдвинулась только в копии');
  await d.show(devBar, nextBar);
  await d.pause(1500);

  await d.click(page.getByRole('button', { name: 'Сравнить с базовым' }), 'Нажмите «Сравнить с базовым»');
  await expect(page).toHaveURL(/\/resource-planning\/compare/);
  const stats = page.locator('.ant-statistic');
  await expect(stats).toHaveCount(4);
  const table = page.locator('.ant-card', { hasText: 'Изменения назначений' });
  await expect(table.locator('.ant-table-row').first()).toBeVisible();
  await page.mouse.move(900, 120);

  await d.caption('Сверху — итоги базового плана и копии');
  await d.show(stats.first(), stats.last());
  await d.pause(1800);
  await d.caption('Ниже — какие фазы сдвинулись и на сколько дней');
  await d.show(table);
  await d.pause(2200);

  await d.caption('Готово', 2200);
  await d.save('rp-fork-compare');
});
