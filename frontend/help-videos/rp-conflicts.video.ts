// Ролик «Как разобрать перегрузки в плане»: панель «Конфликты» → группировка
// «По сотрудникам» / «По типу» → щелчок по критическому конфликту открывает
// фазу → перетаскивание полосы на свободные дни убирает конфликт → второй
// конфликт (предупреждение) отмечен «Принят», затем «Замучен» → «Показать
// погашенные» возвращает его на экран. Оба конфликта готовятся в beforeAll —
// запись идёт с момента открытия окна.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';
import { phaseBar, TEAM, type Assignment } from './rp-setup.ts';

type Scenario = { id: string; name: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null };
type Conflict = {
  id: string;
  type: string;
  severity: 'critical' | 'warning' | 'info';
  status: string;
  message: string;
  employee_id: string | null;
  backlog_item_id: string | null;
  assignment_id: string | null;
};
type Gantt = { assignments: Assignment[]; conflicts: Conflict[] };

let planId = '';
let criticalAssignment: Assignment;
let criticalMessage = '';
let warnMessage = '';
/** Ранняя дата, куда фазу вернут перетаскиванием — там точно есть свободное окно. */
let earlySlot = '';

/** Ближайший рабочий день (суббота и воскресенье пропускаются) вперёд. */
function workday(d: dayjs.Dayjs): dayjs.Dayjs {
  let x = d;
  while (x.day() === 0 || x.day() === 6) x = x.add(1, 'day');
  return x;
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();
  const json = async <T,>(res: { ok(): boolean; json(): Promise<T> }): Promise<T> => {
    ok(res);
    return res.json();
  };

  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } }));
  ok(await request.patch(`${rp}/preferences`, {
    data: { view_mode: 'tasks', hide_weekends: false, collapsed_initiative_ids: [] },
  }));

  const scenarios = await json<Scenario[]>(
    await request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } }),
  );
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  if (!scenario) throw new Error(`Нет утверждённых сценариев команды ${TEAM}`);

  const plans = await json<Plan[]>(await request.get(`${rp}/resource-plans`, { params: { team: TEAM } }));
  let plan = plans.find((p) => p.scenario_id === scenario.id);
  if (!plan) {
    plan = await json<Plan>(
      await request.post(`${rp}/resource-plans`, {
        data: { scenario_id: scenario.id, team: TEAM, quarter: scenario.quarter, year: scenario.year },
      }),
    );
  }
  planId = plan.id;
  const url = `${rp}/resource-plans/${planId}`;
  ok(await request.post(`${url}/bulk-clear`, { data: { mode: 'all' } }));
  ok(await request.post(`${url}/compute`));

  const pin = async (assignmentId: string, day: dayjs.Dayjs) =>
    ok(await request.patch(`${url}/assignments/${assignmentId}`, { data: { start_date: day.format('YYYY-MM-DD') } }));
  const byKey = (list: Assignment[], k: { item: string; phase: string; part: number }) =>
    list.find((a) => a.backlog_item_id === k.item && a.phase === k.phase && a.part_number === k.part);

  const quarterNum = Number(String(scenario.quarter).slice(1));
  const quarterStart = dayjs(`${scenario.year}-01-01`).add((quarterNum - 1) * 3, 'month');
  const quarterEnd = dayjs(`${scenario.year}-01-01`).add(quarterNum * 3, 'month').subtract(1, 'day');
  earlySlot = workday(quarterStart.add(3, 'day')).format('YYYY-MM-DD');
  // Край запаса на выход за квартал (+1 месяц): дальше сдвигать некуда — часы
  // не помещаются, и конфликт не «рассосётся» сам при пересчёте.
  const latePin = workday(quarterEnd.add(3, 'week'));

  // Критический конфликт: фазу с исполнителем уводим к самому краю квартала.
  let g = await json<Gantt>(await request.get(`${url}/gantt`));
  const critCandidate = g.assignments.find((a) => a.employee_id && a.start_date && a.phase !== 'qa');
  if (!critCandidate) throw new Error('В плане нет фазы с исполнителем для критического конфликта');
  const critKey = { item: critCandidate.backlog_item_id, phase: critCandidate.phase, part: critCandidate.part_number };
  await pin(critCandidate.id, latePin);

  // Предупреждение: другой сотрудник, разработка запущена раньше конца анализа той же задачи.
  g = await json<Gantt>(await request.get(`${url}/gantt`));
  const warnCandidate = g.assignments.find((a) => {
    if (a.phase !== 'analyst' || !a.employee_id || a.backlog_item_id === critCandidate.backlog_item_id) return false;
    const dev = g.assignments.find((d) => d.backlog_item_id === a.backlog_item_id && d.phase === 'dev' && d.employee_id);
    return !!dev && !!a.start_date && !!a.end_date && !!dev.start_date;
  });
  if (!warnCandidate) throw new Error('Нет пары анализ/разработка для второго конфликта');
  const dev = g.assignments.find((d) => d.backlog_item_id === warnCandidate.backlog_item_id && d.phase === 'dev')!;
  let early = workday(dayjs(warnCandidate.start_date).add(3, 'day'));
  if (!early.isBefore(dayjs(warnCandidate.end_date))) early = dayjs(warnCandidate.start_date!);
  await pin(dev.id, early);

  // Итоговые конфликты для UI-локаторов.
  g = await json<Gantt>(await request.get(`${url}/gantt`));
  criticalAssignment = byKey(g.assignments, critKey)!;
  const criticalConflict = g.conflicts.find(
    (c) => c.severity === 'critical' && c.backlog_item_id === critCandidate.backlog_item_id,
  );
  const warnConflict = g.conflicts.find(
    (c) => c.type === 'PREDECESSOR_VIOLATED' && c.backlog_item_id === warnCandidate.backlog_item_id,
  );
  if (!criticalConflict) throw new Error('Критический конфликт не создался');
  if (!warnConflict) throw new Error('Предупреждение о предшественнике не создалось');
  criticalMessage = criticalConflict.message;
  warnMessage = warnConflict.message;

  await request.dispose();
});

test('rp-conflicts', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open(`/resource-planning?plan_id=${planId}`, 'Как разобрать перегрузки в плане');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  const header = page.locator('.ant-collapse-header', { hasText: 'Конфликты' });
  await expect(header).toBeVisible();
  await d.pause(600);
  await d.poster();
  await d.pause(900);

  await d.click(header, 'Панель «Конфликты» — над диаграммой');
  const panel = page.locator('.ant-collapse', { has: header });
  const criticalAlert = panel.locator('.ant-alert', { hasText: criticalMessage }).first();
  const warnAlert = panel.locator('.ant-alert', { hasText: warnMessage }).first();
  await expect(criticalAlert).toBeVisible();
  await expect(warnAlert).toBeVisible();

  await d.click(page.locator('.ant-segmented-item', { hasText: 'По сотрудникам' }), 'Можно сгруппировать по сотрудникам…');
  await d.pause(1300);
  await d.click(page.locator('.ant-segmented-item', { hasText: 'По типу' }), '…или по типу проблемы');
  await d.pause(1300);
  await d.click(page.locator('.ant-segmented-item', { hasText: 'По задачам' }));

  await d.click(criticalAlert.getByText(criticalMessage, { exact: false }), 'Щелчок по конфликту откроет фазу');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  await page.mouse.move(900, 120);
  await d.caption('Часы фазы не поместились в план — исполнитель перегружен по срокам');
  await d.show(drawer.getByText('Расчёт проблем'));
  await d.pause(3000);
  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  // Перетащить полосу далеко влево, на свободное окно в начале квартала.
  const bar = phaseBar(page, criticalAssignment);
  await expect(bar).toBeVisible();
  await bar.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
  // scrollIntoView сдвигает вбок и всю страницу (она чуть шире окна) — боковое меню
  // уезжает из кадра. Возвращаем страницу на место до замера полосы.
  await page.evaluate(() => {
    if (window.scrollX) window.scrollTo({ left: 0, top: window.scrollY });
  });
  await d.pause(700);
  const box = (await bar.boundingBox())!;
  const y = box.y + box.height / 2;
  const x0 = box.x + box.width - 10;
  // Масштаб недели: расстояние от текущего (край квартала) до раннего слота
  // в неделях, переведённое в пиксели ширины одной недели на полосе.
  const daysSpan = Math.max(1, dayjs(criticalAssignment.start_date).diff(dayjs(earlySlot), 'day'));
  const totalDays = Math.max(1, dayjs(criticalAssignment.end_date).diff(dayjs(criticalAssignment.start_date), 'day') + 1);
  const pxPerDay = box.width / totalDays;
  const x1 = Math.max(60, x0 - daysSpan * pxPerDay);

  await d.caption('Перетащите полосу дальше — на свободные дни в начале квартала');
  await page.evaluate(({ rect, x, y }) => {
    window.__director?.ring(rect);
    window.__director?.move(x, y);
  }, { rect: box, x: x0, y });
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
    await d.pause(60);
  }
  await page.mouse.up();
  await page.evaluate(() => window.__director?.press());
  await page.mouse.move(900, 120);

  await expect(criticalAlert).toHaveCount(0, { timeout: 15_000 });
  await d.caption('Конфликт ушёл — часы поместились в план');
  await d.show(header);
  await d.pause(2600);

  // Второй конфликт: «Принят», затем «Замучен» и «Показать погашенные».
  await d.click(warnAlert.locator('a:has(.anticon-more)'), 'Конфликт допустим? Откройте меню статуса справа');
  await d.click(page.locator('.ant-dropdown:visible .ant-dropdown-menu-item', { hasText: 'Принят' }), 'Выберите «Принят»');
  await expect(warnAlert.locator('.ant-tag')).toHaveText('Принят');
  await d.caption('Конфликт остаётся на виду, но вы уже приняли решение');
  await d.show(warnAlert.locator('.ant-tag'));
  await d.pause(1000);

  await d.click(warnAlert.locator('a:has(.anticon-more)'), 'А если он совсем не важен — «Замучен»');
  await d.click(page.locator('.ant-dropdown:visible .ant-dropdown-menu-item', { hasText: 'Замучен' }));
  await expect(warnAlert).toBeHidden();
  await page.mouse.move(900, 120);

  const hiddenLink = panel.getByText(/Показать \d+ погашенных/);
  await d.click(hiddenLink, '«Показать погашенные» вернёт скрытые конфликты на экран');
  await expect(warnAlert).toBeVisible();
  await expect(warnAlert.locator('.ant-tag')).toHaveText('Замучен');
  await d.show(warnAlert.locator('.ant-tag'));
  await d.pause(3000);

  // Загрузка по дням — итог: где ещё остался перегруз.
  const load = page.locator('[data-tour="rp-load"]');
  await load.evaluate((el) => {
    (el as HTMLElement).style.marginBottom = '160px';
  });
  await d.caption('Внизу — загрузка по дням: где ещё остался перегруз, видно сразу');
  await load.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  await d.pause(800);
  await d.show(load);
  await d.pause(2600);

  await d.caption('Готово', 2200);
  await d.save('rp-conflicts');
});
