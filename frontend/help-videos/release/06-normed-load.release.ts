// Глава 6 «Нормированные работы в «Загрузке по дням»»: план квартала → новые
// предупреждения (перерасход, «Квартал не вмещается») → свёрнутая в строку сводка
// запаса → развёрнутая таблица с полосками «занято из заложенного» → процент
// загрузки у имени с подсказкой → дни с нормированными работами.
import { expect, type Locator, type Page, test } from '@playwright/test';
import { Director } from '../director.ts';
import { CHAPTERS } from './chapters.ts';
import { chapterTitle, hideVersion, releaseFrame, saveClip } from './common.ts';

const TEAM = 'Команда Альфа';
/** Низ закреплённых шапок (страница + шкала графика) в кадре 1920×1080, с запасом. */
const STICKY_BOTTOM = 305;

type Scenario = { id: string; team: string | null; year: number; quarter: string };
type Plan = { id: string; scenario_id: string | null; parent_plan_id: string | null };
type LoadDay = { date: string; off: string | null; pct: number; normed_pct: number; blocked: string | null };
type LoadRow = {
  employee_id: string;
  employee_name: string | null;
  days: LoadDay[];
  quarter: { pct: number; unplaced_hours: number; normed_hours: number } | null;
};
type Reserve = { roles: { rows: { blocked_hours: number; other_teams_hours: number }[] }[] };
type Gantt = {
  plan: { status: string };
  stale_due_to_other_teams: boolean;
  conflicts: { type: string }[];
  employee_load: LoadRow[];
  reserve: Reserve | null;
};

releaseFrame();

let planId = '';
let personName = '';
/** У героя часть нормированных работ не вмещается — подсказка у процента это покажет. */
let hasUnplaced = false;
/** В плане есть предупреждение «Квартал не вмещается». */
let hasUnplacedWarning = false;
/** Номер клетки дня в строке человека (ось — рабочие дни квартала, как в самой таблице). */
let dayIndex = -1;

// Данные готовим до открытия окна: запись идёт с момента его создания.
test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string): Promise<T> => {
    const res = await request.get(url);
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  // Вид «Задачи», инициативы развёрнуты — как в остальных главах про план.
  expect(
    (await request.patch(`${rp}/preferences`, { data: { view_mode: 'tasks', collapsed_initiative_ids: [] } })).ok(),
  ).toBeTruthy();

  // Самый свежий сценарий команды (глава 2 возвращает его в черновик — статус не важен) и его план.
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios`);
  const scenario = scenarios
    .filter((s) => s.team === TEAM && s.year && s.quarter)
    .sort((a, b) => b.year - a.year || b.quarter.localeCompare(a.quarter))[0];
  expect(scenario, `нет сценария команды ${TEAM}`).toBeTruthy();
  const plans = await getJson<Plan[]>(`${rp}/resource-plans?team=${encodeURIComponent(TEAM)}`);
  const plan = plans.find((p) => p.scenario_id === scenario.id && !p.parent_plan_id);
  expect(plan, 'нет плана последнего сценария').toBeTruthy();
  planId = plan!.id;

  // Прошлые главы могли поменять сценарий и людей — план должен быть свежим.
  let gantt = await getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`);
  if (gantt.plan.status !== 'ready' || gantt.stale_due_to_other_teams) {
    expect((await request.post(`${rp}/resource-plans/${planId}/compute`)).ok()).toBeTruthy();
    await expect
      .poll(async () => (await getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`)).plan.status, { timeout: 60_000 })
      .toBe('ready');
    gantt = await getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`);
  }

  // Сводке есть что показать: запас что-то расходует (в демо-базе — периоды и другие команды).
  const used = (gantt.reserve?.roles ?? []).some((r) => r.rows.some((x) => x.blocked_hours + x.other_teams_hours > 0.05));
  expect(used, 'запас нормированных работ ничего не расходует').toBeTruthy();
  expect(gantt.conflicts.some((c) => c.type === 'NORMED_OVERUSE'), 'нет предупреждения о перерасходе').toBeTruthy();
  hasUnplacedWarning = gantt.conflicts.some((c) => c.type === 'NORMED_UNPLACED');

  // Герой — у кого что-то не вмещается, иначе самый загруженный с нормированными работами.
  const rows = gantt.employee_load.filter((r) => r.quarter && r.quarter.normed_hours > 0);
  const byUnplaced = [...rows].sort((a, b) => b.quarter!.unplaced_hours - a.quarter!.unplaced_hours);
  const byPct = [...rows].sort((a, b) => b.quarter!.pct - a.quarter!.pct);
  const person = byUnplaced[0]?.quarter!.unplaced_hours > 0.5 ? byUnplaced[0] : byPct[0];
  expect(person, 'ни у кого нет нормированных работ').toBeTruthy();
  personName = person.employee_name ?? '';
  hasUnplaced = person.quarter!.unplaced_hours > 0.5;

  // День для подсказки: заблокированный, иначе день с задачами плана и нормированными работами.
  const day =
    person.days.find((d) => !d.off && d.blocked) ?? person.days.find((d) => !d.off && d.pct > 0 && d.normed_pct > 0);
  expect(day, 'нет дня с нормированными работами').toBeTruthy();
  // Ось дней — как в таблице: все даты строк без выходных (признак выходного — по первой строке).
  const weekend = new Set(gantt.employee_load[0].days.filter((d) => d.off === 'weekend').map((d) => d.date));
  const axis = [...new Set(gantt.employee_load.flatMap((r) => r.days.map((d) => d.date)))]
    .filter((d) => !weekend.has(d))
    .sort();
  dayIndex = axis.indexOf(day!.date);
  expect(dayIndex).toBeGreaterThanOrEqual(0);
  await request.dispose();
});

/**
 * Подсказка у процента — системная (атрибут title), в запись браузера она не попадает.
 * Рисуем её копию с тем же текстом рядом с курсором, как её увидит пользователь.
 */
async function showNativeTip(page: Page, target: Locator, text: string): Promise<void> {
  const box = await target.boundingBox();
  if (!box) throw new Error('Процент не виден на экране');
  await page.evaluate(
    ({ x, y, above, text }) => {
      const tip = document.createElement('div');
      tip.id = '__native_tip';
      tip.textContent = text;
      Object.assign(tip.style, {
        position: 'fixed', left: `${x}px`, top: `${y}px`, zIndex: '2147483646', pointerEvents: 'none',
        whiteSpace: 'pre', background: '#f7f7f7', color: '#1b1b1b', border: '1px solid #9a9a9a',
        borderRadius: '4px', padding: '6px 10px', font: '14px/1.5 "Segoe UI", system-ui, sans-serif',
        boxShadow: '0 6px 18px rgba(0, 0, 0, 0.45)',
      });
      document.body.appendChild(tip);
      // Внизу экрана — подпись ролика: подсказка тогда раскрывается вверх.
      if (y + tip.offsetHeight > window.innerHeight - 130) tip.style.top = `${above - tip.offsetHeight}px`;
    },
    { x: box.x + box.width + 16, y: box.y + box.height + 6, above: box.y - 6, text },
  );
}

test('06-normed-load', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await hideVersion(page);
  await d.open(`/resource-planning?plan_id=${planId}`, chapterTitle(6, CHAPTERS[5]));

  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });
  const load = page.locator('[data-tour="rp-load"]');
  await expect(load).toBeVisible({ timeout: 60_000 });
  // Запас снизу страницы: таблица загрузки поднимается над подписью ролика.
  await page.addStyleTag({ content: '[data-tour="rp-load"] { padding-bottom: 120px; }' });
  const scroller = page.locator('.scroll-y', { has: load });
  /**
   * Плавно прокрутить: верх `target` — сразу под закреплённой шапкой страницы и графика,
   * без цели — до конца страницы. Уже на месте — без паузы.
   */
  const scrollTo = async (target?: Locator) => {
    await page.evaluate(() => window.__director?.ring(null));
    const handle = target ? await target.elementHandle() : null;
    const moved = await scroller.evaluate(
      (el, { t, below }) => {
        const max = el.scrollHeight - el.clientHeight;
        const want = t ? el.scrollTop + t.getBoundingClientRect().top - below : max;
        const top = Math.max(0, Math.min(max, want));
        if (Math.abs(top - el.scrollTop) < 2) return false;
        el.scrollTo({ top, behavior: 'smooth' });
        return true;
      },
      { t: handle, below: STICKY_BOTTOM },
    );
    if (moved) await d.pause(1100);
  };
  await page.mouse.move(1000, 110);
  await d.pause(1200);

  // Новые предупреждения плана — по типу.
  const conflicts = page.locator('.ant-collapse', { has: page.locator('.ant-collapse-header', { hasText: 'Конфликты' }) });
  await d.click(
    conflicts.locator('.ant-collapse-header'),
    hasUnplacedWarning
      ? 'Новые предупреждения: перерасход и «Квартал не вмещается»'
      : 'Новое предупреждение — перерасход нормированных работ',
  );
  await d.click(conflicts.locator('.ant-segmented-item', { hasText: 'По типу' }));
  const normedAlerts = conflicts.locator('.ant-alert', { hasText: /нормированных работ|заложено/ });
  await expect(normedAlerts.first()).toBeVisible();
  await page.mouse.move(1000, 110);
  const unplacedGroup = conflicts.getByText('Квартал не вмещается');
  await d.show(hasUnplacedWarning ? unplacedGroup.first() : normedAlerts.first(), normedAlerts.last());
  await d.pause(1300);

  // Сводка запаса над «Загрузкой по дням» — свёрнута в одну строку.
  const summaryBtn = page.locator('button[aria-expanded]', { hasText: 'Нормированные работы — запас квартала' });
  await d.caption('Сводка запаса — одна строка с числом перерасходов');
  await scrollTo();
  await expect(summaryBtn).toBeVisible();
  await d.show(summaryBtn);
  await d.pause(900);

  await d.click(summaryBtn, 'Разверните сводку');
  await expect(summaryBtn).toHaveAttribute('aria-expanded', 'true');
  await page.mouse.move(1000, 110);
  // Таблица целиком под шапкой; если с «Загрузкой по дням» влезает — страница просто до конца.
  const summary = summaryBtn.locator('xpath=..');
  await scrollTo(summary);
  const table = summary.locator('table');
  await expect(table).toBeVisible();
  await d.caption('Одна таблица — только то, что расходует запас');
  await d.show(table);
  await d.pause(1000);

  const usedCells = table.locator('tbody tr > td:nth-child(3)');
  await d.caption('Полоска — занято из заложенного, красная — перерасход');
  await d.show(usedCells.first(), usedCells.last());
  await d.pause(1300);

  // Процент у имени — загрузка за квартал; подсказка — разбивка и что не вмещается.
  const name = load.locator('span[role="button"]', { hasText: personName }).first();
  const label = name.locator('xpath=../../..');
  const pctBadge = label.locator('span', { hasText: /^\d+%$/ });
  await d.caption('Процент у имени — вся загрузка человека за квартал');
  await scrollTo();
  await expect(pctBadge).toBeVisible();
  await d.show(pctBadge);
  await d.pause(700);
  await pctBadge.hover();
  const tipText = await pctBadge.getAttribute('title');
  expect(tipText).toBeTruthy();
  await showNativeTip(page, pctBadge, tipText!);
  await d.caption(hasUnplaced ? 'В подсказке — разбивка по работам и что не вмещается' : 'В подсказке — разбивка по видам работ');
  await d.pause(2400);
  await page.evaluate(() => document.getElementById('__native_tip')?.remove());

  // День с нормированными работами — своя подсказка приложения.
  const cell = name
    .locator('xpath=../../../..')
    .locator(':scope > div:not(:first-child) > div')
    .nth(dayIndex);
  await d.caption('Серым в днях — нормированные работы');
  await d.show(cell);
  await cell.hover();
  await d.pause(2100);

  await page.mouse.move(1000, 110);
  await d.caption('Видно, сколько времени уходит на нормированные работы');
  await d.show(load.locator(':scope > div'));
  await d.pause(2600);
  await saveClip(page, '06-normed-load');
});
