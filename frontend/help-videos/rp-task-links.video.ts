// Ролик «Как связать задачи между собой»: «Вид» → «Рисовать связи» → первая
// задача → вторая задача → оранжевая линия связи → щелчок по линии и
// подтверждение → связь удалена.
import { expect, type Locator, test } from '@playwright/test';
import { Director } from './director.ts';
import { type Assignment, prepareQuarterPlan } from './rp-setup.ts';

type Keyed = Assignment & { backlog_item_key: string | null };
type Dependency = { id: string; from_item_id: string; to_item_id: string; dep_type: string };
type Point = { x: number; y: number };

// Придержан: в кадре ошибки раздела (см. справку «Ресурсное планирование»); снять после исправления.
test.skip('rp-task-links', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // План без ручных правок; связи между задачами пересчёт не снимает — убираем их отдельно.
  const { rp, plan, assignments } = await prepareQuarterPlan(page);
  const deps = `${rp}/resource-plans/${plan.id}/dependencies`;
  for (const dep of (await (await page.request.get(deps)).json()) as Dependency[]) {
    expect((await page.request.delete(`${deps}/${dep.id}`)).ok()).toBeTruthy();
  }
  const itemByKey = new Map((assignments as Keyed[]).map((a) => [a.backlog_item_key, a.backlog_item_id]));

  const gantt = page.locator('[data-tour="rp-gantt"]');
  // Строка задачи — родитель ячейки с кнопкой «Свернуть <ключ>»; первые две сверху.
  const toggles = page.getByRole('button', { name: /^Свернуть / });
  const taskRow = (i: number) => toggles.nth(i).locator('xpath=../..');
  const link = gantt.locator('svg path[stroke="#ff7a45"]');

  /** Видимая часть строки задачи: от левого края до правого края диаграммы. */
  const rowRect = async (row: Locator) => {
    const box = (await row.boundingBox())!;
    const chart = (await gantt.boundingBox())!;
    return { x: box.x, y: box.y, width: chart.x + chart.width - box.x, height: box.height };
  };
  /** Точка на шкале строки — правее колонки с названием, где нет ссылки в Jira. */
  const trackPoint = async (row: Locator): Promise<Point> => {
    const title = (await row.locator('xpath=./div[1]').boundingBox())!;
    const box = (await row.boundingBox())!;
    return { x: title.x + title.width + 180, y: box.y + box.height / 2 };
  };
  /** Подвести нарисованный курсор к точке, обвести область и щёлкнуть настоящей мышью. */
  const clickAt = async (at: Point, rect: { x: number; y: number; width: number; height: number }, caption?: string) => {
    if (caption) await d.caption(caption);
    await page.evaluate(
      ({ at: p, rect: r }) => {
        window.__director?.ring(r);
        window.__director?.move(p.x, p.y);
      },
      { at, rect },
    );
    await d.pause(1450);
    await page.evaluate(() => window.__director?.press());
    await d.pause(160);
    await page.mouse.click(at.x, at.y);
    await page.evaluate(() => window.__director?.ring(null));
    await d.pause(650);
  };
  /** Длинный горизонтальный участок линии связи, обрезанный видимой частью шкалы. */
  const linkSegment = async () => {
    const title = (await taskRow(0).locator('xpath=./div[1]').boundingBox())!;
    const chart = (await gantt.boundingBox())!;
    const y = await link.evaluate((el) => {
      const path = el as SVGPathElement;
      const svg = path.ownerSVGElement!.getBoundingClientRect();
      const runs = new Map<number, { min: number; max: number }>();
      for (let l = 0; l <= path.getTotalLength(); l += 2) {
        const p = path.getPointAtLength(l);
        const key = Math.round(p.y * 10) / 10;
        const run = runs.get(key) ?? { min: p.x, max: p.x };
        runs.set(key, { min: Math.min(run.min, p.x), max: Math.max(run.max, p.x) });
      }
      const [longest] = [...runs.entries()].sort((a, b) => b[1].max - b[1].min - (a[1].max - a[1].min));
      return svg.top + longest[0];
    });
    const left = title.x + title.width;
    const right = chart.x + chart.width;
    return { at: { x: (left + right) / 2, y }, rect: { x: left, y: y - 12, width: right - left, height: 24 } };
  };

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как связать задачи между собой');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(toggles.nth(1)).toBeVisible();
  const keys = await Promise.all([0, 1].map(async (i) => (await toggles.nth(i).getAttribute('aria-label'))!.slice(9)));
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const view = page.locator('[data-tour="rp-view"]');
  await d.click(view, 'Откройте «Вид»');
  await d.click(page.getByRole('button', { name: 'Рисовать связи' }), 'Нажмите «Рисовать связи»');
  // Окно «Вид» закрываем щелчком мимо — по заголовку страницы.
  await page.mouse.click(700, 118);
  const hint = gantt.getByText('Режим связей: кликните по инициативе-источнику');
  await expect(hint).toBeVisible();

  const from = taskRow(0);
  const to = taskRow(1);
  await clickAt(await trackPoint(from), await rowRect(from), 'Нажмите на задачу, от которой идёт связь');
  await expect(gantt.getByText(/^Кликните по второй инициативе/)).toBeVisible();
  await clickAt(await trackPoint(to), await rowRect(to), 'Затем — на задачу, которая идёт после неё');
  await expect(page.getByText('Связь создана')).toBeVisible();
  await expect(link).toHaveCount(1);
  const created: Dependency[] = await (await page.request.get(deps)).json();
  expect(created).toHaveLength(1);
  expect(created[0]).toMatchObject({ from_item_id: itemByKey.get(keys[0]), to_item_id: itemByKey.get(keys[1]), dep_type: 'FS' });
  await page.mouse.move(700, 118);

  // Стрелки рисуются через кадр после перечитывания плана.
  await d.pause(300);
  const segment = await linkSegment();
  await d.caption('Оранжевая линия — связь между задачами');
  await page.evaluate((r) => window.__director?.ring(r), segment.rect);
  await d.pause(2000);
  await page.evaluate(() => window.__director?.ring(null));

  // Подтверждение — окно браузера, в запись оно не попадает: подпись говорит о нём заранее.
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toBe('Удалить связь FS?');
    await d.pause(900);
    await dialog.accept();
  });
  await clickAt(segment.at, segment.rect, 'Чтобы удалить, нажмите на линию и подтвердите');
  await expect(page.getByText('Связь удалена')).toBeVisible();
  await expect(link).toHaveCount(0);
  expect(await (await page.request.get(deps)).json()).toHaveLength(0);
  await page.mouse.move(700, 118);
  await d.caption('Связь удалена — линии больше нет');
  await page.evaluate((r) => window.__director?.ring(r), segment.rect);
  await d.pause(2000);
  await page.evaluate(() => window.__director?.ring(null));

  await d.caption('Готово', 2200);
  await d.save('rp-task-links');
});
