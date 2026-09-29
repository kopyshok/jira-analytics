// Ролик «Как разбить фазу на части»: полоса разработки → карточка → «Разбить на
// части» → часы каждой части → на диаграмме две части, тестирование разделилось так же.
import { expect, type Locator, test } from '@playwright/test';
import { Director } from './director.ts';
import { type Assignment, phaseBar, prepareQuarterPlan } from './rp-setup.ts';

type Phase = Assignment & { hours_allocated: number | null };

test('rp-split', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Самая ранняя разработка с исполнителем и целыми часами, за которой идёт
  // тестирование той же задачи: на ней видно и деление, и «пропорционально».
  const { rp, plan, assignments } = await prepareQuarterPlan(page);
  const phases = assignments as Phase[];
  const dev = phases
    .filter((a) => a.phase === 'dev' && a.part_number === 1 && a.employee_id && a.start_date)
    .filter((a) => Number.isInteger(a.hours_allocated) && (a.hours_allocated ?? 0) >= 16)
    .filter((a) => phases.some((q) => q.phase === 'qa' && q.backlog_item_id === a.backlog_item_id))
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!))[0];
  if (!dev) throw new Error('В плане нет разработки с часами и тестированием');
  const total = dev.hours_allocated!;
  const first = Math.round(total * 0.6);
  const second = total - first;

  const part1 = phaseBar(page, dev);
  const part2 = phaseBar(page, { ...dev, part_number: 2 });
  const qaBars = page.locator(`[data-testid^="rp-bar-${dev.backlog_item_id}-qa-"]`);
  const status = (text: string) => page.locator('.ant-tag', { hasText: new RegExp(`^${text}$`) });

  /** Выделить число в поле и набрать новое с видимой скоростью. */
  const retype = async (field: Locator, value: number, caption?: string) => {
    await d.click(field, caption);
    await field.press('ControlOrMeta+A');
    await field.pressSequentially(String(value), { delay: 90 });
    await d.pause(500);
  };

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как разбить фазу на части');
  await expect(status('Готово')).toBeVisible();
  await expect(part1).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(part1, 'Нажмите на полосу фазы');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  await d.click(drawer.getByRole('button', { name: 'Разбить на части' }), 'В карточке нажмите «Разбить на части»');

  const modal = page.getByRole('dialog', { name: 'Разбить фазу на части' });
  await expect(modal).toBeVisible();
  const hours = modal.getByRole('spinbutton');
  await expect(hours).toHaveCount(2);
  await retype(hours.nth(0), first, 'Укажите часы каждой части');
  await retype(hours.nth(1), second);
  const sum = modal.getByText(/^Сумма:/);
  await expect(sum).toHaveText(`Сумма: ${total} ч (требуется ${total} ч)`);
  await d.caption('Вместе части дают все часы фазы');
  await d.show(sum);
  await d.pause(600);

  const cascade = modal.getByRole('checkbox');
  await expect(cascade).toBeChecked();
  await d.caption('Галочка — тестирование разделится так же');
  await d.show(modal.getByText('Разбить и последующие фазы пропорционально'));
  await d.pause(600);

  await d.click(modal.getByRole('button', { name: 'Разбить', exact: true }), 'Нажмите «Разбить»');
  await expect(modal).toBeHidden();

  // Карточка осталась открытой — теперь в ней первая часть и кнопка слияния.
  const merge = drawer.getByRole('button', { name: 'Слить части в одну' });
  await expect(merge).toBeVisible();
  const after: { assignments: Phase[] } = await (await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)).json();
  const hoursOf = (phase: string) =>
    after.assignments
      .filter((a) => a.backlog_item_id === dev.backlog_item_id && a.phase === phase)
      .sort((a, b) => a.part_number - b.part_number)
      .map((a) => a.hours_allocated);
  expect(hoursOf('dev')).toEqual([first, second]);
  expect(hoursOf('qa')).toHaveLength(2);
  await d.caption('Передумали — «Слить части в одну» вернёт фазу целиком');
  await d.show(merge);
  await d.pause(1400);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  // Настоящая мышь осталась над страницей — уводим, чтобы не подсвечивались полосы.
  await page.mouse.move(900, 120);

  await expect(part1).toBeVisible();
  await expect(part2).toBeVisible();
  await expect(qaBars).toHaveCount(2);
  // Части идут встык — обводим по одной, иначе на шкале недель их не различить.
  await d.caption(`Фаза разделилась: первая часть — ${first} ч`);
  await d.show(part1);
  await d.pause(1200);
  await d.caption(`Вторая часть — ${second} ч, она идёт следом`);
  await d.show(part2);
  await d.pause(1200);
  await d.caption('Тестирование разделилось в той же пропорции');
  await d.show(qaBars.first(), qaBars.last());
  await d.pause(1400);

  await d.caption('Готово', 2200);
  await d.save('rp-split');
});
