// Ролик «Как связать и отвязать фазы»: карточка разработки → убрать анализ из
// «Предшественников» → «Распределить» → разработка больше не ждёт анализа →
// вернуть связь через «Зависит от…» → «Распределить» → всё как было.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';
import { type Assignment, phaseBar, prepareQuarterPlan } from './rp-setup.ts';

type Linked = Assignment & { predecessor_ids?: string[] };

test('rp-predecessors', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Самая ранняя разработка с исполнителем, которая ждёт анализа своей задачи:
  // её предшественник — анализ, и начинается она только после него.
  const { rp, plan, assignments } = await prepareQuarterPlan(page);
  const phases = assignments as Linked[];
  const byId = new Map(phases.map((a) => [a.id, a]));
  const analystOf = (a: Linked) =>
    (a.predecessor_ids ?? []).map((id) => byId.get(id)).find((p) => p?.phase === 'analyst');
  const dev = phases
    .filter((a) => a.phase === 'dev' && a.part_number === 1 && a.employee_id && a.start_date)
    .filter((a) => {
      const an = analystOf(a);
      return !!an?.start_date && an.start_date < a.start_date!;
    })
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!))[0];
  if (!dev) throw new Error('В плане нет разработки, которая ждёт анализа');
  const analyst = analystOf(dev)!;

  const devStart = async () => {
    const g: { assignments: Linked[] } = await (await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)).json();
    return g.assignments.find(
      (a) => a.backlog_item_id === dev.backlog_item_id && a.phase === 'dev' && a.part_number === 1,
    )?.start_date;
  };

  const devBar = phaseBar(page, dev);
  const analystBar = phaseBar(page, analyst);
  const status = (text: string) => page.locator('.ant-tag', { hasText: new RegExp(`^${text}$`) });
  const distribute = page.locator('[data-tour="rp-distribute"]');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  const predecessors = drawer
    .locator('.ant-descriptions-row')
    .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: /^Предшественники$/ }) });

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как связать и отвязать фазы');
  await expect(status('Готово')).toBeVisible();
  await expect(devBar).toBeVisible();
  await expect(analystBar).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(devBar, 'Нажмите на полосу разработки');
  await expect(drawer).toBeVisible();
  await d.caption('«Предшественники» — чего фаза ждёт');
  await d.show(predecessors);
  await d.pause(900);

  await d.click(predecessors.locator('.ant-select-selection-item-remove'), 'Уберите анализ крестиком');
  await expect(predecessors.getByText('Зависит от…')).toBeVisible();
  await expect(status('Требуется пересчёт')).toBeVisible();

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  await d.click(distribute, 'Нажмите «Распределить» — план пересчитается');
  await expect(status('Готово')).toBeVisible({ timeout: 60_000 });
  // Без связи разработка встала раньше — ищет свободное время с начала квартала.
  expect((await devStart()) ?? '').toBeTruthy();
  expect((await devStart())! < dev.start_date!).toBeTruthy();
  await page.mouse.move(900, 120);
  await d.caption('Фаза больше не ждёт анализа');
  await d.show(analystBar, devBar);
  await d.pause(1600);

  await d.click(devBar, 'Чтобы связать снова, откройте фазу');
  await expect(drawer).toBeVisible();
  await d.click(predecessors.locator('.ant-select'), 'Выберите анализ в поле «Зависит от…»');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: /^Анализ/ }));
  await expect(predecessors.locator('.ant-select-selection-item', { hasText: /^Анализ/ })).toBeVisible();

  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);
  await d.click(distribute, 'Снова «Распределить»');
  await expect(status('Готово')).toBeVisible({ timeout: 60_000 });
  expect(await devStart()).toBe(dev.start_date);
  await page.mouse.move(900, 120);
  await d.caption('Разработка снова идёт после анализа');
  await d.show(analystBar, devBar);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('rp-predecessors');
});
