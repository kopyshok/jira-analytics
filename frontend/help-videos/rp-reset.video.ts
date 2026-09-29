// Ролик «Как сбросить ручные правки»: в плане перенесена фаза и заменён
// исполнитель → «Сбросить» → число правок каждого вида → «Сбросить всё к
// первоначальному виду» → план пересчитан, фаза и исполнитель вернулись.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import type { AssignmentOut, GanttProjection } from '../src/api/resourcePlanning.ts';
import { sortAssignmentsByScenarioAssignee } from '../src/utils/sortAssignments.ts';
import { Director } from './director.ts';
import { phaseBar, prepareQuarterPlan } from './rp-setup.ts';

test('rp-reset', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Подготовка до первого кадра: план без правок, затем две ручные правки в двух
  // верхних задачах диаграммы — разработка первой перенесена на неделю позже,
  // у разработки второй заменён исполнитель на коллегу той же роли.
  const { rp, plan } = await prepareQuarterPlan(page);
  const url = `${rp}/resource-plans/${plan.id}`;
  const gantt = async () => (await (await page.request.get(`${url}/gantt`)).json()) as GanttProjection;
  const patch = async (a: AssignmentOut, data: object) =>
    expect((await page.request.patch(`${url}/assignments/${a.id}`, { data })).ok()).toBeTruthy();
  const devOf = (list: AssignmentOut[], itemId: string) =>
    list.find((a) => a.backlog_item_id === itemId && a.phase === 'dev' && a.part_number === 1);

  let g = await gantt();
  // Задачи в порядке диаграммы, у которых разработка с исполнителем и датами.
  const items = [...new Set(sortAssignmentsByScenarioAssignee(g.assignments).map((a) => a.backlog_item_id))].filter(
    (id) => devOf(g.assignments, id)?.employee_id && devOf(g.assignments, id)?.start_date,
  );
  if (items.length < 2) throw new Error('В плане меньше двух задач с разработкой');
  const [movedItem, swappedItem] = items;
  const moved = devOf(g.assignments, movedItem)!;
  const swapped = devOf(g.assignments, swappedItem)!;
  const load = g.employee_load ?? [];
  const role = load.find((r) => r.employee_id === swapped.employee_id)?.employee_role;
  const peer = load.find((r) => r.employee_id !== swapped.employee_id && r.employee_role === role && !r.is_borrowed);
  if (!peer) throw new Error('Нет второго сотрудника той же роли для замены исполнителя');
  const originalStart = moved.start_date!;
  const originalName = swapped.employee_name!;

  let target = dayjs(originalStart).add(7, 'day');
  while (target.day() === 0 || target.day() === 6) target = target.add(1, 'day');
  await patch(moved, { start_date: target.format('YYYY-MM-DD') });
  g = await gantt();
  await patch(devOf(g.assignments, swappedItem)!, { employee_id: peer.employee_id, force: true });

  g = await gantt();
  expect(g.reset_counts).toEqual({ pinned_dates: 1, pinned_employees: 1, edited_predecessors: 0 });
  expect(devOf(g.assignments, movedItem)!.start_date! > originalStart).toBeTruthy();
  expect(devOf(g.assignments, swappedItem)!.employee_id).toBe(peer.employee_id);

  const movedBar = phaseBar(page, moved);
  // Строка разработки второй задачи: слева — имя исполнителя.
  const swappedRow = phaseBar(page, swapped).locator('xpath=ancestor::*[@data-gantt-row="true"][1]');
  const resetButton = page.locator('[data-testid="rp-reset-trigger"]');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как сбросить ручные правки');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(movedBar).toBeVisible();
  await expect(swappedRow.getByText(peer.employee_name ?? '', { exact: true })).toBeVisible();
  await d.pause(1200);
  await d.poster();
  await d.pause(4000);

  await d.caption('Эту фазу перенесли вручную');
  await d.show(movedBar);
  await d.pause(3800);
  await d.caption('А здесь вручную сменили исполнителя');
  await d.show(swappedRow.getByText(peer.employee_name ?? '', { exact: true }));
  await d.pause(3800);

  await d.click(movedBar, 'У каждой фазы такая правка видна и в её карточке');
  await expect(drawer).toBeVisible();
  const cardReset = drawer.getByRole('button', { name: 'Снять фиксацию даты' });
  await expect(cardReset).toBeVisible();
  await d.caption('«Снять фиксацию даты» снимет правку только здесь');
  await d.show(cardReset);
  await d.pause(4000);
  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  await d.click(resetButton, 'А для всего плана сразу — нажмите «Сбросить»');
  const menu = page.locator('.ant-dropdown:visible .ant-dropdown-menu');
  await expect(menu.locator('[data-testid="rp-reset-item-dates"]')).toContainText('Сбросить закреплённые даты (1)');
  await expect(menu.locator('[data-testid="rp-reset-item-employees"]')).toContainText('Сбросить закреплённых исполнителей (1)');
  await d.caption('В скобках — сколько правок каждого вида');
  await d.show(menu);
  await d.pause(4200);
  await d.caption('Связи между задачами (оранжевые стрелки) сброс не трогает');
  await d.show(menu.locator('[data-testid="rp-reset-item-predecessors"]'));
  await d.pause(4200);

  await d.click(
    menu.locator('[data-testid="rp-reset-item-all"]'),
    'Можно сбросить всё сразу',
  );
  const confirm = page.locator('.ant-modal-confirm');
  await expect(confirm).toBeVisible();
  await d.click(confirm.getByRole('button', { name: 'Сбросить' }), 'Подтвердите сброс');
  await expect(confirm).toBeHidden();
  // Число в сообщении — все строки плана, которые затронул сброс, а не только правки.
  await expect(page.getByText(/^Фаз сброшено: \d+$/)).toBeVisible({ timeout: 60_000 });
  await page.mouse.move(900, 120);

  g = await gantt();
  expect(g.reset_counts).toEqual({ pinned_dates: 0, pinned_employees: 0, edited_predecessors: 0 });
  expect(devOf(g.assignments, movedItem)!.start_date).toBe(originalStart);
  expect(devOf(g.assignments, swappedItem)!.employee_name).toBe(originalName);
  await expect(swappedRow.getByText(originalName, { exact: true })).toBeVisible();

  await d.caption('План пересчитан: фаза вернулась на своё место');
  await d.show(movedBar);
  await d.pause(4200);
  await d.caption('И исполнитель — прежний');
  await d.show(swappedRow.getByText(originalName, { exact: true }));
  await d.pause(4200);

  await d.caption('Готово', 2600);
  await d.save('rp-reset');
});
