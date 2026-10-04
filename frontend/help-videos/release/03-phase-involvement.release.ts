// Глава «Вовлечённость фазы: «Зафиксировано»»: карточка фазы ресурсного плана →
// под процентом подписано, откуда он взят (справочник команды) → «Зафиксировано»,
// свой процент, «Сохранить» → окончание фазы пересчитано → галочка снята — фаза
// снова берёт справочник. Снятие галочки в кадре и возвращает данные как было;
// afterAll страхует, если съёмка оборвалась посередине.
import { expect, type Locator, type Page, test } from '@playwright/test';
import { Director } from '../director.ts';
import { type Assignment, phaseBar, type Plan, type Scenario, TEAM } from '../rp-setup.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

/** Свой процент фазы в ролике (в справочнике команды — больше). */
const FIXED = 50;

type Phase = Assignment & { hours_allocated: number | null };
type Explain = { phase_calc: { involvement_pct: number | null; involvement_source?: string | null } | null };
type Prefs = { view_mode: string | null; hide_weekends: boolean; collapsed_initiative_ids: string[] };
type Key = Pick<Assignment, 'backlog_item_id' | 'phase' | 'part_number'>;

releaseFrame();

let planId = '';
let phaseKey: Key;
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

  // Пересчёт до кадра: в ролике от фиксации сдвигается только своя фаза и её
  // тестирование, а не весь план разом.
  await json(await request.post(`${url}/compute`));
  const { assignments } = await json<{ assignments: Phase[] }>(await request.get(`${url}/gantt`));
  baseline = snapshot(assignments);

  // Самая ранняя разработка с исполнителем и тестированием следом, процент
  // которой не зафиксирован, — её окончание заметно сдвинется.
  const devs = assignments
    .filter((a) => a.phase === 'dev' && a.part_number === 1 && a.employee_id && a.start_date && a.end_date)
    .filter((a) => (a.hours_allocated ?? 0) >= 24)
    .filter((a) => assignments.some((q) => q.phase === 'qa' && q.backlog_item_id === a.backlog_item_id))
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!));
  for (const a of devs) {
    const explain = await json<Explain>(await request.get(`${url}/assignments/${a.id}/explain`));
    const calc = explain.phase_calc;
    if (calc && calc.involvement_source === 'team' && (calc.involvement_pct ?? 0) > FIXED) {
      phaseKey = { backlog_item_id: a.backlog_item_id, phase: a.phase, part_number: a.part_number };
      break;
    }
  }
  if (!phaseKey) throw new Error('В плане нет разработки с процентом из справочника команды');
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

  // Глава сама снимает галочку в кадре; если съёмка оборвалась раньше — снимаем здесь.
  const gantt = async () => ((await (await request.get(`${url}/gantt`)).json()) as { assignments: Phase[] }).assignments;
  const phase = phaseKey && byKey(await gantt(), phaseKey);
  if (phase) {
    const explain = (await (await request.get(`${url}/assignments/${phase.id}/explain`)).json()) as Explain;
    if (explain.phase_calc?.involvement_source === 'task') {
      expect((await request.put(`${url}/assignments/${phase.id}/involvement`, {
        data: { involvement_pct: null },
      })).ok()).toBeTruthy();
    }
  }
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

/** Увести курсор под поле ввода справа, чтобы не закрывал набираемые цифры. */
async function aside(page: Page, target: Locator): Promise<void> {
  const box = await target.boundingBox();
  if (!box) return;
  await page.evaluate((at) => window.__director?.move(at.x, at.y), {
    x: box.x + box.width + 24,
    y: box.y + box.height + 14,
  });
}

test('03-phase-involvement', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const bar = phaseBar(page, phaseKey);
  await d.open(`/resource-planning?plan_id=${planId}`, chapterTitle('Вовлечённость фазы: «Зафиксировано»'));
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });
  await expect(bar).toBeVisible();
  await d.pause(1500);

  await d.click(bar, 'Нажмите на полосу фазы — откроется её карточка');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const field = (label: string) =>
    drawer
      .locator('.ant-descriptions-row')
      .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: new RegExp(`^${label}$`) }) })
      .first();
  const involvement = field('Вовлечённость');
  const source = involvement.getByText('из справочника команды');
  const fixBox = involvement.getByRole('checkbox', { name: 'Зафиксировано' });
  const input = involvement.getByRole('spinbutton');
  const end = field('Окончание');
  const endDate = end.locator('.ant-descriptions-item-content .ant-typography').first();
  await expect(source).toBeVisible();
  await expect(fixBox).not.toBeChecked();
  const endBefore = (await endDate.innerText()).trim();
  expect(endBefore).toMatch(/^\d{2}\.\d{2}\.\d{4}$/);
  await page.mouse.move(700, 120);

  await d.caption('Под процентом подписано, откуда он взят — справочник команды');
  await d.show(involvement);
  await d.pause(2200);

  await d.click(fixBox, 'Отметьте «Зафиксировано», впишите процент и сохраните');
  await expect(input).toBeEnabled();
  await d.click(input);
  await aside(page, input);
  await input.press('Control+A');
  await input.pressSequentially(String(FIXED), { delay: 120 });
  await d.pause(500);
  await d.click(involvement.getByRole('button', { name: 'Сохранить' }));
  await expect(endDate).not.toHaveText(endBefore, { timeout: 30_000 });
  await expect(input).toHaveValue(String(FIXED));
  await page.mouse.move(700, 120);

  await d.caption('Свой процент фазы главнее личной настройки и справочника');
  await d.show(involvement);
  await d.pause(1800);

  await d.caption('План пересчитан — фаза теперь заканчивается позже');
  await d.show(end);
  await d.pause(1800);

  await d.click(fixBox, 'Снимите галочку — фаза снова возьмёт справочник команды');
  await expect(source).toBeVisible({ timeout: 30_000 });
  await expect(endDate).toHaveText(endBefore, { timeout: 30_000 });
  await d.show(involvement);
  await d.pause(1800);
  await d.show(end);
  await d.pause(2600);
  await saveClip(d, '03-phase-involvement');
});
