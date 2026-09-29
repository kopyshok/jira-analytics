// Ролик «Как изменить вовлечённость на фазе»: полоса фазы → карточка → новая
// вовлечённость → «Сохранить» → окончание пересчитано, полоса стала длиннее.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';
import { type Assignment, phaseBar, prepareQuarterPlan } from './rp-setup.ts';

type Explain = { phase_calc: { involvement_pct: number | null } | null };

test('rp-involvement', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const { rp, plan, assignments } = await prepareQuarterPlan(page);
  const explain = async (a: Assignment): Promise<Explain> =>
    (await page.request.get(`${rp}/resource-plans/${plan.id}/assignments/${a.id}/explain`)).json();
  // Самая ранняя разработка с исполнителем и заданной вовлечённостью, за которой
  // идёт тестирование той же задачи.
  let dev: Assignment | undefined;
  let before = 0;
  const devs = assignments
    .filter((a) => a.phase === 'dev' && a.employee_id && a.start_date && a.end_date)
    .filter((a) => assignments.some((q) => q.phase === 'qa' && q.backlog_item_id === a.backlog_item_id))
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!));
  for (const a of devs) {
    const pct = (await explain(a)).phase_calc?.involvement_pct;
    if (pct && pct > 55) {
      dev = a;
      before = pct;
      break;
    }
  }
  if (!dev) throw new Error('В плане нет разработки с вовлечённостью выше 55% и тестированием');
  // Половина дня вместо почти полного: фаза заметно удлиняется.
  const NEXT = 50;
  const qaOf = (list: Assignment[]) =>
    list.find((q) => q.phase === 'qa' && q.backlog_item_id === dev.backlog_item_id);
  const qaBefore = qaOf(assignments)!;

  const devBar = phaseBar(page, dev);
  const qaBar = phaseBar(page, qaBefore);

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как изменить вовлечённость на фазе');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(devBar).toBeVisible();
  // Диаграмма прокручена так, чтобы удлинённая фаза и тестирование за ней не ушли
  // за правый край. Пока на экране заголовок — зритель не видит.
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

  const widthBefore = (await devBar.boundingBox())!.width;
  await d.click(devBar, 'Нажмите на полосу фазы');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const field = (label: string) =>
    drawer
      .locator('.ant-descriptions-row')
      .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: new RegExp(`^${label}$`) }) })
      // Ниже, в разделе расчёта, есть строка с тем же названием — нужна верхняя.
      .first();
  const involvement = field('Вовлечённость');
  const input = involvement.getByRole('spinbutton');
  const end = field('Окончание');
  await expect(input).toHaveValue(String(before));
  const endBefore = dayjs(dev.end_date).format('DD.MM.YYYY');
  await expect(end).toContainText(endBefore);

  await d.caption('Вовлечённость — какая доля рабочего дня уходит на фазу');
  await d.show(involvement);
  await d.pause(1200);
  await d.caption(`Сейчас фаза заканчивается ${endBefore}`);
  await d.show(end);
  await d.pause(1000);

  await d.click(input, `Впишите новое значение — например, ${NEXT}%`);
  // Курсор — под поле, чтобы не закрывал набираемые цифры.
  const inputBox = (await input.boundingBox())!;
  await page.evaluate(
    ({ x, y }) => window.__director?.move(x, y),
    { x: inputBox.x + inputBox.width + 30, y: inputBox.y + inputBox.height + 16 },
  );
  await d.pause(400);
  await input.press('Control+A');
  await input.pressSequentially(String(NEXT), { delay: 120 });
  await d.pause(500);
  await d.click(involvement.getByRole('button', { name: 'Сохранить' }), 'Нажмите «Сохранить»');

  // План пересчитан: вовлечённость записана, фаза заканчивается позже.
  await expect(end).not.toContainText(endBefore);
  await expect(input).toHaveValue(String(NEXT));
  const after: { assignments: Assignment[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const devAfter = after.assignments.find(
    (a) => a.phase === 'dev' && a.backlog_item_id === dev.backlog_item_id && a.part_number === dev.part_number,
  )!;
  expect(devAfter.end_date! > dev.end_date!).toBeTruthy();
  expect((await explain(devAfter)).phase_calc?.involvement_pct).toBe(NEXT);
  expect((qaOf(after.assignments)?.start_date ?? '') > qaBefore.start_date!).toBeTruthy();

  await d.caption(`Окончание пересчитано: теперь ${dayjs(devAfter.end_date).format('DD.MM.YYYY')}`);
  await d.show(end);
  await d.pause(1200);
  await d.caption('Значение сохранится в самой задаче — и в других планах тоже');
  await d.show(involvement);
  await d.pause(1400);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  // Настоящая мышь осталась над диаграммой — уводим, чтобы не подсвечивались полосы и связи.
  await page.mouse.move(900, 120);

  await expect.poll(async () => (await devBar.boundingBox())?.width ?? 0).toBeGreaterThan(widthBefore);
  await expect(qaBar).toBeVisible();
  await d.caption('Фаза стала длиннее, тестирование сдвинулось следом');
  await d.show(devBar, qaBar);
  await d.pause(2000);

  await d.caption('Готово', 2200);
  await d.save('rp-involvement');

  // Вовлечённость записана в саму задачу, и снятие ручных правок её не вернёт:
  // возвращаем прежнее значение, чтобы следующие ролики прогона шли на исходной картине.
  const now: { assignments: Assignment[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const current = now.assignments.find(
    (a) => a.phase === 'dev' && a.backlog_item_id === dev.backlog_item_id && a.part_number === dev.part_number,
  )!;
  const restored = await page.request.put(`${rp}/resource-plans/${plan.id}/assignments/${current.id}/involvement`, {
    data: { involvement_pct: before },
  });
  expect(restored.ok()).toBeTruthy();
});
