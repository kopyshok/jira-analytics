// Ролик «Как перенести фазу мышкой»: полосу фазы тянут вправо на неделю →
// план пересчитан, тестирование сдвинулось следом, фаза закреплена.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';
import { type Assignment, phaseBar, prepareQuarterPlan } from './rp-setup.ts';

/** Сколько дней переносим фазу. */
const SHIFT_DAYS = 7;

test('rp-phase-drag', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const { rp, plan, assignments } = await prepareQuarterPlan(page);
  // Самая ранняя разработка с исполнителем, за которой идёт тестирование той же задачи.
  const dev = assignments
    .filter((a) => a.phase === 'dev' && a.employee_id && a.start_date && a.end_date)
    .filter((a) => assignments.some((q) => q.phase === 'qa' && q.backlog_item_id === a.backlog_item_id))
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!))[0];
  if (!dev) throw new Error('В плане нет разработки с исполнителем и тестированием');
  const qaOf = (list: Assignment[]) =>
    list.find((q) => q.phase === 'qa' && q.backlog_item_id === dev.backlog_item_id);
  const qaBefore = qaOf(assignments)!;

  const devBar = phaseBar(page, dev);
  const qaBar = phaseBar(page, qaBefore);

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как перенести фазу мышкой');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(devBar).toBeVisible();
  // Диаграмма прокручена так, чтобы полосе было куда переехать и тестирование
  // за ней не ушло за правый край. Пока на экране заголовок — зритель не видит.
  await devBar.evaluate((el) => {
    let box = el.parentElement;
    while (box && getComputedStyle(box).overflowX !== 'auto') box = box.parentElement;
    const titleCell = el.closest('[data-gantt-row="true"]')?.firstElementChild;
    if (!box || !titleCell) return;
    box.scrollLeft += el.getBoundingClientRect().left - (titleCell.getBoundingClientRect().right + 120);
  });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  // Схватить ближе к правому краю: после переноса курсор уже не над прежней
  // полосой, и отпускание не откроет карточку.
  const box = (await devBar.boundingBox())!;
  const pxPerDay = box.width / (dayjs(dev.end_date).diff(dayjs(dev.start_date), 'day') + 1);
  const y = box.y + box.height / 2;
  const x0 = box.x + box.width - 14;
  const x1 = x0 + SHIFT_DAYS * pxPerDay;

  await d.caption('Наведите курсор на полосу фазы');
  await page.evaluate(({ rect, x, y }) => {
    window.__director?.ring(rect);
    window.__director?.move(x, y);
  }, { rect: box, x: x0, y });
  await d.pause(1400);

  await d.caption('Зажмите и перетащите вправо — на неделю позже');
  await d.pause(900);
  await page.evaluate(() => {
    window.__director?.ring(null);
    window.__director?.press();
  });
  await page.mouse.move(x0, y);
  await page.mouse.down();
  const steps = 16;
  for (let i = 1; i <= steps; i++) {
    const x = x0 + ((x1 - x0) * i) / steps;
    await page.mouse.move(x, y);
    await page.evaluate(({ x, y }) => window.__director?.move(x, y), { x, y });
    await d.pause(90);
  }
  await d.caption('Отпустите — сервис пересчитает план');
  await d.pause(900);
  await page.mouse.up();
  await page.evaluate(() => window.__director?.press());

  // План пересчитан: разработка начинается не раньше новой даты, тестирование сдвинулось.
  await expect.poll(async () => (await devBar.boundingBox())?.x ?? 0).toBeGreaterThan(box.x + pxPerDay * 3);
  const target = dayjs(dev.start_date).add(SHIFT_DAYS, 'day').format('YYYY-MM-DD');
  const after: { assignments: (Assignment & { pinned_start: boolean })[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const devAfter = after.assignments.find(
    (a) => a.phase === 'dev' && a.backlog_item_id === dev.backlog_item_id && a.part_number === dev.part_number,
  );
  expect((devAfter?.start_date ?? '') >= target).toBeTruthy();
  expect(devAfter?.pinned_start).toBeTruthy();
  expect((qaOf(after.assignments)?.start_date ?? '') > qaBefore.start_date!).toBeTruthy();

  // Настоящая мышь осталась над диаграммой — уводим, чтобы не подсвечивались полосы и связи.
  await page.mouse.move(900, 120);
  await d.caption('Фаза переехала, тестирование сдвинулось следом');
  await d.show(devBar, qaBar);
  await d.pause(1600);

  await d.click(devBar, 'Откройте карточку фазы');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const pinned = drawer.locator('.ant-drawer-header .ant-tag', { hasText: 'Закреплено' });
  await expect(pinned).toBeVisible();
  await d.caption('Метка «Закреплено»: дату начала задали вручную');
  await d.show(pinned);
  await d.pause(1400);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  await d.show(devBar, qaBar);
  await d.caption('Готово', 2200);
  await d.save('rp-phase-drag');
});
