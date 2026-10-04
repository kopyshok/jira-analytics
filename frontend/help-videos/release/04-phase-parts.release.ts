// Глава «Части фазы у разных исполнителей»: разработка заранее разбита на две
// части у одного человека (одна строка) → в кадре второй части назначен другой
// разработчик → у каждого исполнителя своя строка фазы с его частями и часами.
// Разбивка готовится в beforeAll; afterAll сливает части и снимает ручные правки —
// план возвращается к виду до главы.
import { type APIRequestContext, expect, type Page, test } from '@playwright/test';
import { Director } from '../director.ts';
import { type Assignment, phaseBar, type Plan, type Scenario, TEAM } from '../rp-setup.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

type Phase = Assignment & { hours_allocated: number | null; employee_name: string | null };
type Candidate = { employee_id: string; display_name: string; role: string | null };
type CandidateGroup = { key: string; label: string; employees: Candidate[] };
type Preview = { has_conflicts: boolean };
type Prefs = { view_mode: string | null; hide_weekends: boolean; collapsed_initiative_ids: string[] };
type Key = Pick<Assignment, 'backlog_item_id' | 'phase' | 'part_number'>;

releaseFrame();

let planId = '';
let part1Key: Key;
let part2Key: Key;
let owner = '';
let peer: Candidate | undefined;
let prefsBefore: Prefs;
/** План до главы: после неё должен быть тем же. */
let baseline = '';

const byKey = (list: Phase[], k: Key) =>
  list.find((a) => a.backlog_item_id === k.backlog_item_id && a.phase === k.phase && a.part_number === k.part_number);
/** Снимок плана для сверки «как было»: фазы, люди, часы, даты. */
const snapshot = (list: Phase[]) =>
  JSON.stringify(
    list
      .map((a) => [a.backlog_item_id, a.phase, a.part_number, a.employee_id, a.hours_allocated, a.start_date, a.end_date])
      .sort((x, y) => x.join().localeCompare(y.join())),
  );

/** Слить части фазы обратно, снять с неё ручные правки и пересчитать план. */
async function mergeBack(request: APIRequestContext, url: string, key: Key): Promise<void> {
  const gantt = async () => ((await (await request.get(`${url}/gantt`)).json()) as { assignments: Phase[] }).assignments;
  const first = byKey(await gantt(), key);
  if (first) {
    expect((await request.post(`${url}/assignments/${first.id}/merge`)).ok()).toBeTruthy();
    const merged = byKey(await gantt(), key);
    if (merged) expect((await request.delete(`${url}/assignments/${merged.id}/manual-edit`)).ok()).toBeTruthy();
  }
  expect((await request.post(`${url}/compute`)).ok()).toBeTruthy();
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const json = async <T,>(res: { ok(): boolean; url(): string; json(): Promise<T> }): Promise<T> => {
    expect(res.ok(), res.url()).toBeTruthy();
    return res.json();
  };

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  prefsBefore = await json<Prefs>(await request.get(`${rp}/preferences`));
  await json(await request.patch(`${rp}/preferences`, {
    data: { view_mode: 'tasks', hide_weekends: false, collapsed_initiative_ids: [] },
  }));

  // План последнего утверждённого сценария демо-команды.
  const scenario = (await json<Scenario[]>(
    await request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } }),
  ))
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  if (!scenario) throw new Error(`Нет утверждённых сценариев команды ${TEAM}`);
  const plans = await json<Plan[]>(await request.get(`${rp}/resource-plans`, { params: { team: TEAM } }));
  const plan = plans.find((p) => p.scenario_id === scenario.id);
  if (!plan) throw new Error(`Нет ресурсного плана сценария «${scenario.name}»`);
  planId = plan.id;
  const url = `${rp}/resource-plans/${planId}`;
  const gantt = async () => (await json<{ assignments: Phase[] }>(await request.get(`${url}/gantt`))).assignments;

  await json(await request.post(`${url}/compute`));
  const before = await gantt();
  baseline = snapshot(before);

  // Разработка с исполнителем и чётными часами: делим пополам и ищем коллегу той же
  // роли, которому вторую часть можно отдать без предупреждения о конфликте, —
  // окно «Конфликты» в главе лишнее. Не нашёлся — сливаем части и пробуем следующую.
  const devs = before
    .filter((a) => a.phase === 'dev' && a.part_number === 1 && a.employee_id && a.start_date && a.end_date)
    .filter((a) => (a.hours_allocated ?? 0) >= 24 && (a.hours_allocated ?? 0) % 2 === 0)
    .filter((a) => before.filter((x) => x.backlog_item_id === a.backlog_item_id && x.phase === 'dev').length === 1)
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!));
  for (const dev of devs) {
    const key: Key = { backlog_item_id: dev.backlog_item_id, phase: 'dev', part_number: 1 };
    const half = dev.hours_allocated! / 2;
    // Пересчёт после прошлой попытки пересоздаёт строки с новыми id — берём свежую.
    const current = byKey(await gantt(), key);
    if (!current) throw new Error('Фаза пропала из плана после пересчёта');
    await json(await request.post(`${url}/assignments/${current.id}/split`, { data: { parts: [half, half], cascade: false } }));
    await json(await request.post(`${url}/compute`));
    const part2 = byKey(await gantt(), { ...key, part_number: 2 });
    if (!part2) throw new Error('Вторая часть не найдена после разбивки');
    const groups = await json<CandidateGroup[]>(await request.get(`${url}/assignments/${part2.id}/candidates`));
    for (const c of (groups.find((g) => g.key === 'team')?.employees ?? []).filter(
      (e) => e.employee_id !== part2.employee_id && e.role?.toLowerCase() === 'dev',
    )) {
      const preview = await json<Preview>(
        await request.post(`${url}/assignments/${part2.id}/preview-employee-change`, { data: { employee_id: c.employee_id } }),
      );
      if (!preview.has_conflicts) {
        peer = c;
        break;
      }
    }
    if (peer) {
      part1Key = key;
      part2Key = { ...key, part_number: 2 };
      owner = dev.employee_name ?? '';
      break;
    }
    await mergeBack(request, url, key);
  }
  if (!peer) throw new Error('В плане нет разработки, которую можно поделить с коллегой без конфликта');
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  if (!planId) return;
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const url = `${rp}/resource-plans/${planId}`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const gantt = async () => ((await (await request.get(`${url}/gantt`)).json()) as { assignments: Phase[] }).assignments;

  // Части — обратно в одну фазу, ручные правки (разбивка, исполнитель) — снять, план — пересчитать.
  if (part1Key) await mergeBack(request, url, part1Key);
  if (prefsBefore) {
    await request.patch(`${rp}/preferences`, {
      data: {
        view_mode: prefsBefore.view_mode,
        hide_weekends: prefsBefore.hide_weekends,
        collapsed_initiative_ids: prefsBefore.collapsed_initiative_ids,
      },
    });
  }
  const after = snapshot(await gantt());
  await request.dispose();
  expect(after, 'план после главы отличается от исходного').toBe(baseline);
});

/** Строка диаграммы, в которой лежит полоса фазы. */
const rowOf = (page: Page, k: Key) => page.locator('[data-gantt-row="true"]', { has: phaseBar(page, k) });

test('04-phase-parts', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  const other = peer!.display_name;

  const part1 = phaseBar(page, part1Key);
  const part2 = phaseBar(page, part2Key);
  const row1 = rowOf(page, part1Key);
  const row2 = rowOf(page, part2Key);
  await d.open(`/resource-planning?plan_id=${planId}`, chapterTitle('Части фазы у разных исполнителей'));
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });
  await expect(part1).toBeVisible();
  await expect(part2).toBeVisible();
  await expect(row1).toHaveCount(1);
  await expect(row1).toContainText(owner);
  // Строка фазы — в середину экрана: внизу её закрыла бы подпись.
  await part1.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'nearest' }));
  await d.pause(2000);

  await d.caption('Разработка разбита на две части — пока обе у одного человека');
  await d.show(row1);
  await d.pause(2600);

  await d.click(part2, 'Откройте вторую часть фазы');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const employee = drawer
    .locator('.ant-descriptions-row')
    .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: /^Сотрудник$/ }) })
    .first();
  await d.click(employee.locator('.ant-select'), 'В поле «Сотрудник» выберите другого разработчика');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: other }));
  await expect(employee.locator('.ant-select')).toContainText(other, { timeout: 30_000 });
  await d.pause(1200);

  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();
  await expect(row2).toContainText(other, { timeout: 30_000 });
  await expect(row1).toContainText(owner);
  await expect(row1).not.toContainText(other);
  await page.mouse.move(900, 120);

  await d.caption('Теперь у каждого исполнителя своя строка фазы');
  await d.show(row1, row2);
  await d.pause(3000);

  await d.caption('В строке — части и часы этого исполнителя');
  await d.show(row2);
  await d.pause(2800);

  await d.caption('Раньше второго исполнителя на диаграмме не было видно');
  await d.show(row1, row2);
  await d.pause(3400);
  await saveClip(d, '04-phase-parts');
});
