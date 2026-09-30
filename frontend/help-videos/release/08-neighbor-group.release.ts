// Глава «Работа на соседнюю группу»: ресурсный план команды с группами →
// исполнителя фазы перевели в другую группу посреди фазы → план пересчитан,
// задача осталась за этим человеком → с даты перевода на полосе пунктирная рамка.
// Вид «Исполнители» (без пунктирных рамок инициатив, чтобы не путать) и масштаб
// «День»: тонкая рамка на неделях теряется при сжатии видео.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

type Team = { name: string; has_subgroups: boolean; subgroups: { id: string; name: string }[] };
type Scenario = { id: string; year: number | null; quarter: string | null };
type Plan = { id: string; scenario_id: string | null };
type Span = { start: string; end: string };
type Assignment = {
  id: string;
  backlog_item_id: string;
  phase: string;
  part_number: number;
  employee_id: string | null;
  employee_name: string | null;
  start_date: string | null;
  end_date: string | null;
  subgroup_id: string | null;
  other_subgroup: boolean;
  other_subgroup_ranges: Span[];
  unavailable_days: { date: string; type: string }[];
};
type Gantt = { assignments: Assignment[]; employee_subgroups: Record<string, string[]> };

releaseFrame();

let planId = '';
let target: Assignment | undefined;

const DAY = 86_400_000;
const days = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / DAY) + 1;
const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

/** Нет отпусков и блокировок внутри полосы — рамку ничто не заслоняет. */
const clean = (a: Assignment) => !a.unavailable_days.some((u) => u.type === 'absence' || u.type === 'block');

/** Полоса, где пунктир только на части дат и помещается в кадр в масштабе «День»:
 *  до перевода — хотя бы 5 дней, после — хотя бы неделя, всего не больше 40 дней. */
function partlyNeighbor(a: Assignment, quarterEnd: string): boolean {
  const r = a.other_subgroup_ranges[0];
  return (
    !!a.employee_id &&
    !!a.start_date &&
    !!a.end_date &&
    !a.other_subgroup &&
    a.other_subgroup_ranges.length === 1 &&
    days(a.start_date, r.start) > 5 &&
    days(r.start, r.end) >= 7 &&
    days(a.start_date, a.end_date) <= 40 &&
    a.end_date <= quarterEnd &&
    clean(a)
  );
}

// Данные готовим до открытия окна: запись идёт с момента его создания.
test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string, params?: Record<string, string>): Promise<T> => {
    const res = await request.get(url, { params });
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  const registry = await getJson<Team[]>(`${api}/teams/registry`);
  const withGroups = registry.find((t) => t.has_subgroups && t.subgroups.length >= 2);
  expect(withGroups, 'нет команды с группами').toBeTruthy();
  const team = withGroups!.name;
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [team], subgroups: [] } })).ok()).toBeTruthy();
  expect(
    (await request.patch(`${rp}/preferences`, {
      data: { view_mode: 'people', hide_weekends: false, collapsed_initiative_ids: [] },
    })).ok(),
  ).toBeTruthy();

  // План последнего утверждённого сценария команды (как в rp-setup.ts).
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios`, { status: 'approved', teams: team });
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  expect(scenario, `нет утверждённого сценария команды ${team}`).toBeTruthy();
  const q = Number(scenario!.quarter!.slice(1));
  const quarterEnd = new Date(Date.UTC(scenario!.year!, q * 3, 0)).toISOString().slice(0, 10);
  const plans = await getJson<Plan[]>(`${rp}/resource-plans`, { team });
  let plan = plans.find((p) => p.scenario_id === scenario!.id);
  if (!plan) {
    const created = await request.post(`${rp}/resource-plans`, {
      data: { scenario_id: scenario!.id, team, quarter: scenario!.quarter, year: scenario!.year },
    });
    expect(created.ok()).toBeTruthy();
    plan = (await created.json()) as Plan;
  }
  planId = plan.id;
  const recompute = async (): Promise<Gantt> => {
    expect((await request.post(`${rp}/resource-plans/${planId}/bulk-clear`, { data: { mode: 'all' } })).ok()).toBeTruthy();
    expect((await request.post(`${rp}/resource-plans/${planId}/compute`)).ok()).toBeTruthy();
    return getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`);
  };

  let gantt = await recompute();
  target = gantt.assignments.find((a) => partlyNeighbor(a, quarterEnd));
  if (!target) {
    // Фаза внутри квартала на 3–6 недель без отпусков, исполнитель — целиком в группе
    // задачи; разработка — в первую очередь, среди равных — самая длинная.
    const phase = gantt.assignments
      .filter(
        (a) =>
          ['analyst', 'dev'].includes(a.phase) &&
          a.employee_id &&
          a.start_date &&
          a.end_date &&
          a.end_date <= quarterEnd &&
          days(a.start_date, a.end_date) >= 21 &&
          days(a.start_date, a.end_date) <= 40 &&
          a.subgroup_id &&
          a.other_subgroup_ranges.length === 0 &&
          clean(a) &&
          (gantt.employee_subgroups[a.employee_id] ?? []).join() === a.subgroup_id,
      )
      .sort(
        (a, b) =>
          Number(b.phase === 'dev') - Number(a.phase === 'dev') ||
          days(b.start_date!, b.end_date!) - days(a.start_date!, a.end_date!),
      )[0];
    expect(phase, 'нет фазы для перевода исполнителя').toBeTruthy();
    // Перевод — с первого понедельника через 10 дней после начала фазы, в первую другую группу.
    const mid = new Date(Date.parse(phase!.start_date!) + 10 * DAY);
    while (mid.getUTCDay() !== 1) mid.setTime(mid.getTime() + DAY);
    const other = withGroups!.subgroups.find((g) => g.id !== phase!.subgroup_id)!;
    const put = await request.put(`${api}/teams/employees/${phase!.employee_id}/subgroup-shares`, {
      data: { team, valid_from: mid.toISOString().slice(0, 10), shares: [{ subgroup_id: other.id, percent: 100 }] },
    });
    expect(put.ok(), await put.text()).toBeTruthy();
    gantt = await recompute();
    target =
      gantt.assignments.find((a) => a.employee_id === phase!.employee_id && partlyNeighbor(a, quarterEnd)) ??
      gantt.assignments.find((a) => partlyNeighbor(a, quarterEnd));
  }
  expect(target, 'после перевода на плане нет полосы с пунктиром').toBeTruthy();
  await request.dispose();
});

test('08-neighbor-group', async ({ page }) => {
  const a = target!;
  const from = ddmm(a.other_subgroup_ranges[0].start);

  const d = new Director(page);
  await d.install();
  await d.open(`/resource-planning?plan_id=${planId}`, chapterTitle('Работа на соседнюю группу'));

  const bar = page.getByTestId(`rp-bar-${a.backlog_item_id}-${a.phase}-${a.part_number}`);
  const dashed = bar.getByTestId('rp-other-subgroup-range');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });
  await expect(dashed).toHaveCount(1);

  // Пока держится заголовок главы: масштаб «День» и полоса в кадре — строка по
  // центру экрана, дата перевода чуть левее середины диаграммы.
  await page.locator('.ant-segmented-item', { hasText: /^День$/ }).click();
  await expect(dashed).toBeVisible();
  await bar.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
  // Слева у диаграммы закреплена колонка с именами (~540 пикселей): начало
  // длинной полосы уходит под неё.
  const timelineLeft = await dashed.evaluate((el) => {
    let box = el.parentElement;
    while (box && !/(auto|scroll)/.test(getComputedStyle(box).overflowX)) box = box.parentElement;
    if (!box) return 0;
    const left = box.getBoundingClientRect().left + 540;
    const target = left + (box.getBoundingClientRect().right - left) * 0.42;
    box.scrollBy({ left: el.getBoundingClientRect().left - target, behavior: 'smooth' });
    return left;
  });
  await d.pause(1200);

  // Рамка вокруг полосы — только по видимой части, не поверх колонки с именами.
  const showBar = async () => {
    const b = (await bar.boundingBox())!;
    const x = Math.max(b.x, timelineLeft);
    const rect = { x, y: b.y, width: b.x + b.width - x, height: b.height };
    await page.evaluate((r) => {
      window.__director?.ring(r);
      window.__director?.move(r.x + r.width - 10, r.y + r.height + 16);
    }, rect);
    await d.pause(750);
  };

  await d.caption(`Сотрудника перевели в другую группу с ${from}`);
  await showBar();
  await d.pause(1200);

  await d.caption('С этой даты — фиолетовая пунктирная рамка');
  await d.show(dashed);
  await d.pause(1400);

  // Рамку режиссёра снимаем: тонкий пунктир виден лучше без подсветки рядом.
  await d.caption('Человек доделывает задачу прежней группы — это не конфликт');
  await page.evaluate(() => window.__director?.ring(null));
  await d.pause(1800);

  await d.caption('Работа на соседнюю группу сразу видна на плане');
  await showBar();
  await d.pause(2800);
  await saveClip(page, '08-neighbor-group');
});
