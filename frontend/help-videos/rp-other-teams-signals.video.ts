// Ролик «Как понять, что план зависит от других команд»: у команды, которая берёт
// людей из другой, над диаграммой — предупреждение «Планы других команд изменились
// после расчёта», в «Конфликтах» — «Пересечение с другой командой», а блок
// «Привлечённые» показывает, чем эти люди заняты в чужих планах. «Распределить» всё
// гасит. Затем шапка переключается на команду-донора: у неё — «Наши люди в других
// командах». Состояние готовится в beforeAll: донор (Дельта) закрепляет работу
// общего сотрудника на дни, где он занят у второй команды (Дзета). В afterAll
// закрепление снимается, планы обеих команд пересчитываются, шапка — на «Команда Альфа».
import { expect, type Page, test } from '@playwright/test';
import { Director } from './director.ts';
import { TEAM as ALFA_TEAM, phaseBar } from './rp-setup.ts';

const BORROWER = 'Команда Дзета';
const DONOR = 'Команда Дельта';

type A = {
  id: string;
  backlog_item_id: string;
  phase: string;
  part_number: number;
  employee_id: string | null;
  employee_name?: string | null;
  start_date: string | null;
  end_date: string | null;
  pinned_start: boolean;
};
type Conflict = { type: string; message: string };
type Gantt = {
  assignments: A[];
  conflicts: Conflict[];
  stale_due_to_other_teams: boolean;
  external_bookings: { employee_id: string; team: string; employee_is_borrowed: boolean }[];
};
type Plan = { id: string; scenario_id: string | null; quarter: string | null; year: number | null };
type Scenario = { id: string; name: string; quarter: string | null; year: number | null };

let borrowerPlanId = '';
let donorPlanId = '';
let donorScenarioLabel = '';
let overlapMessage = '';
let sharedPhase: A;
/** Что вернуть в afterAll: закреплённая фаза донора и фаза заёмщика этого человека. */
let donorRestore: A | null = null;
let borrowerRestore: A | null = null;

/** Строки плана пересоздаются при расчёте — находим фазу заново по задаче, этапу и части. */
const sameAs = (x: A) => (y: A) =>
  y.backlog_item_id === x.backlog_item_id && y.phase === x.phase && y.part_number === x.part_number &&
  y.employee_id === x.employee_id;

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const current = async (planId: string, x: A) => {
    const g = (await (await request.get(`${rp}/resource-plans/${planId}/gantt`)).json()) as Gantt;
    return g.assignments.find(sameAs(x));
  };
  if (donorRestore && donorPlanId) {
    const now = await current(donorPlanId, donorRestore);
    if (now) await request.patch(`${rp}/resource-plans/${donorPlanId}/assignments/${now.id}`, { data: { pinned_start: false } });
    await request.post(`${rp}/resource-plans/${donorPlanId}/compute`);
  }
  if (borrowerRestore && borrowerPlanId) {
    const now = await current(borrowerPlanId, borrowerRestore);
    if (now) {
      await request.patch(`${rp}/resource-plans/${borrowerPlanId}/assignments/${now.id}`, {
        data: { start_date: borrowerRestore.start_date, pinned_start: borrowerRestore.pinned_start },
      });
    }
    await request.post(`${rp}/resource-plans/${borrowerPlanId}/compute`);
  }
  await request.put(`${api}/auth/me/teams`, { data: { teams: [ALFA_TEAM], subgroups: [] } });
  await request.dispose();
});

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const json = async <T,>(res: { ok(): boolean; json(): Promise<T> }): Promise<T> => {
    expect(res.ok()).toBeTruthy();
    return res.json();
  };
  const latestPlan = async (team: string): Promise<Plan> => {
    const plans = await json<Plan[]>(await request.get(`${rp}/resource-plans`, { params: { team } }));
    const p = plans
      .filter((x) => x.scenario_id && x.quarter && x.year)
      .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
      .at(-1);
    if (!p) throw new Error(`У команды ${team} нет плана по сценарию`);
    return p;
  };
  const gantt = async (planId: string) => json<Gantt>(await request.get(`${rp}/resource-plans/${planId}/gantt`));
  const compute = async (planId: string) =>
    expect((await request.post(`${rp}/resource-plans/${planId}/compute`)).ok()).toBeTruthy();

  expect(
    (await request.patch(`${rp}/preferences`, {
      data: { view_mode: 'tasks', hide_weekends: false, collapsed_initiative_ids: [] },
    })).ok(),
  ).toBeTruthy();

  const borrower = await latestPlan(BORROWER);
  const donor = await latestPlan(DONOR);
  borrowerPlanId = borrower.id;
  donorPlanId = donor.id;
  const scenarios = await json<Scenario[]>(
    await request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: DONOR } }),
  );
  const sc = scenarios.find((s) => s.id === donor.scenario_id);
  if (!sc) throw new Error('Не найден сценарий плана донора');
  donorScenarioLabel = `${sc.quarter} ${sc.year} — ${sc.name}`;

  // Исходная раскладка: донор, затем заёмщик подстраивается под него.
  await compute(donor.id);
  await compute(borrower.id);
  const before = await gantt(borrower.id);
  const donorBefore = await gantt(donor.id);

  // Общий сотрудник: у заёмщика привлечён из донора и у обоих есть его фазы.
  const people = new Set(before.external_bookings.filter((b) => b.team === DONOR).map((b) => b.employee_id));
  let found = false;
  for (const own of before.assignments.filter((a) => a.employee_id && people.has(a.employee_id) && a.start_date)) {
    const theirs = donorBefore.assignments
      .filter((a) => a.employee_id === own.employee_id && a.start_date && !a.pinned_start)
      .reverse();
    for (const t of theirs) {
      const cur = (await gantt(donor.id)).assignments.find(sameAs(t));
      if (!cur) continue;
      const patch = await request.patch(`${rp}/resource-plans/${donor.id}/assignments/${cur.id}`, {
        data: { start_date: own.start_date, force: true },
      });
      if (!patch.ok()) continue;
      await compute(donor.id);
      const g = await gantt(borrower.id);
      const overlap = g.conflicts.find((c) => c.type === 'CROSS_TEAM_OVERLAP');
      if (g.stale_due_to_other_teams && overlap) {
        overlapMessage = overlap.message;
        sharedPhase = own;
        donorRestore = t;
        borrowerRestore = own;
        found = true;
        break;
      }
      // Не подошло — вернуть обе стороны и пробовать дальше.
      const moved = (await gantt(donor.id)).assignments.find(sameAs(t));
      if (moved) await request.patch(`${rp}/resource-plans/${donor.id}/assignments/${moved.id}`, { data: { pinned_start: false } });
      await compute(donor.id);
      const back = (await gantt(borrower.id)).assignments.find(sameAs(own));
      if (back) {
        await request.patch(`${rp}/resource-plans/${borrower.id}/assignments/${back.id}`, {
          data: { start_date: own.start_date, pinned_start: own.pinned_start },
        });
      }
      await compute(borrower.id);
    }
    if (found) break;
  }
  if (!found) throw new Error('Не удалось подготовить пересечение двух команд на общем сотруднике');

  expect(
    (await request.put(`${api}/auth/me/teams`, { data: { teams: [BORROWER], subgroups: [] } })).ok(),
  ).toBeTruthy();
  await request.dispose();
});

/** Переключить команду в шапке на другую — видимый для зрителя переход. */
async function switchTeam(d: Director, page: Page, from: string, to: string, caption: string) {
  const teamButton = page.locator('.topbar').getByRole('button', { name: new RegExp(from) });
  await d.click(teamButton, caption);
  const popover = page.locator('.ant-popover:visible');
  await d.click(popover.getByRole('button', { name: 'Сбросить' }));
  await popover.getByPlaceholder('Поиск команды').fill(to);
  await d.click(popover.locator('[data-testid="team-filter-option"]', { hasText: to }));
  await d.click(popover.getByRole('button', { name: 'Применить' }));
  await page.mouse.move(900, 120);
}

test('rp-other-teams-signals', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const ready = page.locator('.ant-tag', { hasText: /^Готово$/ });
  const stale = page.locator('.ant-alert', { hasText: 'Планы других команд изменились после расчёта' });

  await d.open(`/resource-planning?plan_id=${borrowerPlanId}`, 'Как понять, что план зависит от других команд');
  await expect(ready).toBeVisible();
  await expect(stale).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(800);
  await d.poster();
  await d.pause(1200);

  await d.caption('Над диаграммой — предупреждение: другие команды поменяли свои планы');
  await d.show(stale);
  await d.pause(600);

  const header = page.locator('.ant-collapse-header', { hasText: 'Конфликты' });
  await d.click(header, 'А в «Конфликтах» — пересечение с другой командой');
  const panel = page.locator('.ant-collapse', { has: header });
  await d.click(panel.locator('.ant-segmented-item', { hasText: 'По типу' }));
  const overlap = panel.locator('.ant-alert', { hasText: overlapMessage }).first();
  await expect(overlap).toBeVisible();
  await overlap.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('Сотрудник занят у другой команды в те же дни');
  await d.show(overlap);
  await d.pause(600);

  await d.waitVoice();
  await d.click(header);
  await expect(overlap).toBeHidden();
  await page.mouse.move(900, 120);

  const borrowedHeader = page.getByRole('button', { name: /Привлечённые/ });
  await expect(borrowedHeader).toBeVisible();
  await borrowedHeader.scrollIntoViewIfNeeded();
  await d.caption('Блок «Привлечённые» — чем эти люди заняты в чужих планах');
  await d.show(borrowedHeader);
  await d.pause(600);
  await d.caption('Серые дни — человек занят у другой команды');
  const bar = phaseBar(page, sharedPhase);
  await d.show(bar);
  await d.pause(600);

  await d.waitVoice();
  await page.evaluate(() => window.scrollTo({ left: 0, top: 0 }));
  await d.click(
    page.locator('[data-tour="rp-distribute"]'),
    'Нажмите «Распределить» — план подстроится под другие команды',
  );
  await expect(ready).toBeVisible({ timeout: 60_000 });
  await expect(stale).toBeHidden();
  await page.mouse.move(900, 120);
  await d.caption('Предупреждение исчезло, пересечение тоже');
  await d.show(page.locator('[data-tour="rp-distribute"]'));
  await d.pause(600);

  await d.waitVoice();
  await switchTeam(d, page, BORROWER, DONOR, 'Теперь посмотрим со стороны команды, чьи люди работают в чужом плане');
  await d.click(page.locator('[data-tour="rp-scenario-select"]'), 'Выберите план этой команды');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: donorScenarioLabel }));
  await expect(ready).toBeVisible();

  // Верхний блок сворачиваем, чтобы нужный был виден целиком.
  await page.getByRole('button', { name: /Привлечённые/ }).click();
  const ownPeople = page.getByRole('button', { name: /Наши люди в других командах/ });
  await expect(ownPeople).toBeVisible();
  await ownPeople.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('«Наши люди в других командах» — где заняты наши сотрудники');
  await d.show(ownPeople);
  await d.pause(600);

  await d.caption('Готово', 2200);
  await d.save('rp-other-teams-signals');
});
