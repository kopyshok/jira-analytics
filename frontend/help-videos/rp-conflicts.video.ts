// Ролик «Как разобрать конфликты плана»: панель конфликтов над диаграммой →
// группировка по сотрудникам → конфликт открывает карточку фазы с причиной →
// фаза обведена на диаграмме красным → конфликт отмечен «Принят».
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import type { AssignmentOut, GanttProjection } from '../src/api/resourcePlanning.ts';
import { sortAssignmentsByScenarioAssignee } from '../src/utils/sortAssignments.ts';
import { Director } from './director.ts';
import { phaseBar, prepareQuarterPlan } from './rp-setup.ts';

/** Ближайший рабочий день (суббота и воскресенье пропускаются) вперёд или назад. */
function workday(d: dayjs.Dayjs, step: 1 | -1 = 1): dayjs.Dayjs {
  let x = d;
  while (x.day() === 0 || x.day() === 6) x = x.add(step, 'day');
  return x;
}

test('rp-conflicts', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Подготовка до первого кадра. Пересчитанный план конфликтов не содержит —
  // создаём два ручными датами: предупреждение (разработка начата до конца
  // анализа) и критический (разработка закреплена в последние дни запаса
  // после квартала, часы не помещаются). Оба — у разных сотрудников.
  const { rp, plan } = await prepareQuarterPlan(page);
  const url = `${rp}/resource-plans/${plan.id}`;
  const gantt = async () => (await (await page.request.get(`${url}/gantt`)).json()) as GanttProjection;
  const pinStart = async (a: AssignmentOut, day: dayjs.Dayjs) => {
    const res = await page.request.patch(`${url}/assignments/${a.id}`, {
      data: { start_date: day.format('YYYY-MM-DD') },
    });
    expect(res.ok()).toBeTruthy();
  };
  const phaseOf = (list: AssignmentOut[], itemId: string, phase: AssignmentOut['phase']) =>
    list.find((a) => a.backlog_item_id === itemId && a.phase === phase && a.part_number === 1);
  // Порядок задач — как на диаграмме: первая задача видна без прокрутки.
  const itemsInOrder = (list: AssignmentOut[]) =>
    [...new Set(sortAssignmentsByScenarioAssignee(list).map((a) => a.backlog_item_id))];

  let g = await gantt();
  const warnItem = itemsInOrder(g.assignments).find((id) => {
    const an = phaseOf(g.assignments, id, 'analyst');
    const dev = phaseOf(g.assignments, id, 'dev');
    return an?.start_date && an.end_date && dev?.employee_id && dev.start_date;
  });
  if (!warnItem) throw new Error('В плане нет задачи с анализом и разработкой');
  const analyst = phaseOf(g.assignments, warnItem, 'analyst')!;
  const warnDev = phaseOf(g.assignments, warnItem, 'dev')!;
  let early = workday(dayjs(analyst.start_date).add(7, 'day'));
  if (!early.isBefore(dayjs(analyst.end_date))) early = dayjs(analyst.start_date);
  await pinStart(warnDev, early);

  g = await gantt();
  const others = itemsInOrder(g.assignments).filter((id) => id !== warnItem);
  const devOf = (id: string) => phaseOf(g.assignments, id, 'dev');
  const otherPerson = (id: string) => !!devOf(id)?.employee_id && devOf(id)?.employee_id !== warnDev.employee_id;
  // Без тестирования следом — сообщение короче: не поместилась только разработка.
  const critItem =
    others.find((id) => otherPerson(id) && !phaseOf(g.assignments, id, 'qa')) ?? others.find(otherPerson);
  if (!critItem) throw new Error('В плане нет второй разработки у другого сотрудника');
  const quarterEnd = dayjs(`${g.plan.year}-01-01`)
    .add(Number(String(g.plan.quarter).slice(1)) * 3, 'month')
    .subtract(1, 'day');
  await pinStart(devOf(critItem)!, workday(quarterEnd.add(1, 'month').subtract(3, 'day'), -1));

  g = await gantt();
  const warn = g.conflicts.find((c) => c.type === 'PREDECESSOR_VIOLATED' && c.backlog_item_id === warnItem);
  const crit = g.conflicts.find((c) => c.type === 'UNPLACED_HOURS' && c.backlog_item_id === critItem);
  expect(warn?.status).toBe('open');
  expect(crit?.status).toBe('open');
  expect(g.conflicts.filter((c) => c.severity !== 'info')).toHaveLength(2);

  const header = page.locator('.ant-collapse-header', { hasText: 'Конфликты' });
  const panel = page.locator('.ant-collapse', { has: header });
  const warnAlert = page.locator('.ant-alert', { hasText: 'до завершения предшественника' }).first();
  const bar = phaseBar(page, warnDev);
  // Рамка режиссёра — вокруг всей задачи: красная обводка фазы внутри остаётся видна.
  const itemFirst = phaseBar(page, analyst);
  const itemLast = phaseBar(page, phaseOf(g.assignments, warnItem, 'qa') ?? warnDev);

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как разобрать конфликты плана');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(header).toContainText('1 критических');
  await expect(header).toContainText('1 предупреждений');
  await expect(bar).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.caption('Счётчик конфликтов плана — над диаграммой');
  await d.show(header);
  await d.pause(900);

  await d.click(header, 'Нажмите, чтобы открыть список');
  await expect(warnAlert).toBeVisible();

  await d.click(page.locator('.ant-segmented-item', { hasText: 'По сотрудникам' }), 'Сгруппируйте, например, по сотрудникам');
  // Два сотрудника — две группы по одному конфликту.
  await expect(panel.locator('.ant-tag', { hasText: /^1$/ })).toHaveCount(2);
  await d.show(panel);
  await d.pause(1200);

  await d.click(warnAlert.getByText(/до завершения предшественника/), 'Нажмите на конфликт');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  const reason = drawer.locator('.ant-alert', { hasText: 'до завершения предшественника' });
  await expect(reason).toBeVisible();
  await d.caption('Откроется карточка фазы — причина в разделе «Расчёт проблем»');
  await d.show(drawer.locator('.ant-divider', { hasText: 'Расчёт проблем' }), reason);
  await d.pause(2200);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  // Полоса под открытым списком — у нижнего края, за подписью ролика: плавно
  // поднимаем её к середине экрана.
  await page.evaluate(() => window.__director?.ring(null));
  await d.caption('На диаграмме такая фаза обведена красным');
  await bar.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' }));
  await d.pause(900);
  await d.show(itemFirst, itemLast);
  await d.pause(2000);

  await page.evaluate(() => window.__director?.ring(null));
  await header.evaluate((el) => {
    let box = el.parentElement;
    while (box && !/(auto|scroll)/.test(getComputedStyle(box).overflowY)) box = box.parentElement;
    box?.scrollTo({ top: 0, behavior: 'smooth' });
  });
  await d.pause(900);

  const status = warnAlert.locator('.ant-tag');
  await expect(status).toHaveText('Открыт');
  await d.click(warnAlert.locator('a:has(.anticon-more)'), 'Конфликт допустим? Откройте меню справа');
  await d.click(page.locator('.ant-dropdown:visible .ant-dropdown-menu-item', { hasText: 'Принят' }), 'Выберите «Принят»');
  await expect(status).toHaveText('Принят');
  await d.caption('Конфликт отмечен: вы знаете о нём и оставляете как есть');
  await d.show(status);
  await d.pause(2200);

  await d.caption('Готово', 2200);
  await d.save('rp-conflicts');
});
