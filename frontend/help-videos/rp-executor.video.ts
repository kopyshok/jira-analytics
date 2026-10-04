// Ролик «Как сменить исполнителя, дату и вовлечённость фазы»: карточка фазы →
// «Сотрудник» (группы Из Jira / Моя команда / Другие команды, загрузка %) →
// конфликт при смене → «Всё равно сохранить и пересчитать» → исполнитель
// закрепился сам. Другая фаза: новая дата «Начало», «Зафиксировать дату» /
// «Снять фиксацию», «Вовлечённость» → «Зафиксировано» → «Сохранить» — фаза удлинилась.
// Данные готовятся в beforeAll — запись идёт с момента открытия окна.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';
import { phaseBar, TEAM, type Assignment } from './rp-setup.ts';

type Scenario = { id: string; name: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null };
type Gantt = { assignments: Assignment[] };
type Candidate = { employee_id: string; display_name: string; role: string | null };
type CandidateGroup = { key: string; label: string; employees: Candidate[] };
type Preview = { has_conflicts: boolean };
type Explain = {
  phase_calc: { involvement_pct: number | null; involvement_source?: string | null } | null;
};
type Key = { item: string; phase: string; part: number };

let planId = '';
let phaseAKey: Key;
let nextEmployee: Candidate;
let phaseBKey: Key;
// Фиксация вовлечённости фазы Б до ролика: null — фаза не была зафиксирована.
let phaseBFixedBefore: number | null = null;

const keyOf = (a: Assignment): Key => ({ item: a.backlog_item_id, phase: a.phase, part: a.part_number });
const byKey = (list: Assignment[], k: Key) =>
  list.find((a) => a.backlog_item_id === k.item && a.phase === k.phase && a.part_number === k.part)!;

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

  const g = await json<Gantt>(await request.get(`${url}/gantt`));

  // Фаза А: самый ранний анализ, у которого в своей команде есть другой человек
  // той же специализации (не разработчик) — при выборе сервис предупредит о
  // конфликте, и в ролике всегда видно окно с предупреждением.
  const analyses = g.assignments
    .filter((a) => a.phase === 'analyst' && a.employee_id && a.start_date)
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!));
  let foundA: Assignment | undefined;
  for (const a of analyses) {
    const groups: CandidateGroup[] = await (
      await request.get(`${url}/assignments/${a.id}/candidates`)
    ).json();
    const team = groups.find((gr) => gr.key === 'team')?.employees ?? [];
    for (const e of team.filter((c) => c.employee_id !== a.employee_id && c.role?.toLowerCase() !== 'dev')) {
      const preview: Preview = await (
        await request.post(`${url}/assignments/${a.id}/preview-employee-change`, { data: { employee_id: e.employee_id } })
      ).json();
      if (preview.has_conflicts) {
        nextEmployee = e;
        foundA = a;
        break;
      }
    }
    if (foundA) break;
  }
  if (!foundA || !nextEmployee!) throw new Error('Нет анализа, где смена исполнителя даёт предупреждение о конфликте');
  phaseAKey = keyOf(foundA);

  // Фаза Б: самая ранняя разработка (другая задача) с исполнителем и тестированием
  // следом — для смены даты, фиксации и вовлечённости.
  const devB = g.assignments
    .filter((a) => a.phase === 'dev' && a.employee_id && a.start_date && a.end_date && a.backlog_item_id !== foundA!.backlog_item_id)
    .filter((a) => g.assignments.some((q) => q.phase === 'qa' && q.backlog_item_id === a.backlog_item_id))
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!))[0];
  if (!devB) throw new Error('Нет второй разработки с исполнителем и тестированием');
  phaseBKey = keyOf(devB);
  const explainB: Explain = await (await request.get(`${url}/assignments/${devB.id}/explain`)).json();
  phaseBFixedBefore = explainB.phase_calc?.involvement_source === 'task'
    ? explainB.phase_calc.involvement_pct
    : null;

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  // Фиксация вовлечённости фазы Б записывается в саму задачу — возвращаем как
  // было, иначе другие ролики раздела увидят изменённую фазу этой задачи.
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const url = `${rp}/resource-plans/${planId}`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const g: Gantt = await (await request.get(`${url}/gantt`)).json();
  const current = byKey(g.assignments, phaseBKey);
  if (current) {
    await request.put(`${url}/assignments/${current.id}/involvement`, {
      data: { involvement_pct: phaseBFixedBefore },
    });
  }
  await request.dispose();
});

test('rp-executor', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open(`/resource-planning?plan_id=${planId}`, 'Как сменить исполнителя, дату и вовлечённость фазы');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await d.pause(700);
  await d.poster();
  await d.pause(1200);

  // Получить актуальные строки по ключу — id мог пересоздаться при compute().
  const rpUrl = `${String(test.info().config.metadata.backendUrl)}/api/v1/resource-planning/resource-plans/${planId}`;
  const gantt = async (): Promise<Gantt> => (await (await page.request.get(`${rpUrl}/gantt`)).json()) as Gantt;
  let g = await gantt();
  const phaseA = byKey(g.assignments, phaseAKey);
  const barA = phaseBar(page, phaseA);

  await d.click(barA, 'Нажмите на полосу фазы');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const field = (label: string) =>
    drawer
      .locator('.ant-descriptions-row')
      .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: new RegExp(`^${label}$`) }) })
      .first();
  const employeeField = field('Сотрудник');

  await d.click(employeeField.locator('.ant-select'), 'В поле «Сотрудник» — список кандидатов');
  const dropdown = page.locator('.ant-select-dropdown:visible');
  await expect(dropdown.locator('.ant-select-item-group', { hasText: 'Моя команда' })).toBeVisible();
  const option = dropdown.locator('.ant-select-item-option', { hasText: nextEmployee.display_name });
  await expect(option).toBeVisible();
  await d.caption('Люди сгруппированы: из Jira, своя команда, другие команды — у каждого своя загрузка');
  await d.show(dropdown.locator('.rc-virtual-list'));
  await d.pause(1300);

  await d.click(option, 'Выберите нового исполнителя');
  const modal = page.getByRole('dialog', { name: /Конфликты/ });
  await expect(modal).toBeVisible();
  await d.caption('Сервис предупредит об отпуске или перегрузке');
  await d.show(modal.locator('.ant-modal-body'));
  await d.pause(1500);

  await d.click(modal.getByRole('button', { name: 'Всё равно сохранить и пересчитать' }), 'Нажмите «Всё равно сохранить и пересчитать»');
  await expect(modal).toBeHidden();
  const pinnedTag = drawer.locator('.ant-drawer-header .ant-tag', { hasText: 'Закреплено' });
  await expect(pinnedTag).toBeVisible();
  await expect(employeeField.locator('.ant-select')).toContainText(nextEmployee.display_name);
  await d.caption('Исполнитель закрепился сам — отдельной галочки нет');
  await d.show(pinnedTag);
  await d.pause(1300);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  // Фаза Б: новая дата, фиксация, вовлечённость.
  g = await gantt();
  const phaseB = byKey(g.assignments, phaseBKey);
  const barB = phaseBar(page, phaseB);
  await barB.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
  await d.pause(500);

  await d.click(barB, 'Другую фазу можно передвинуть вручную — без мыши, датой');
  const drawerB = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawerB).toBeVisible();
  const fieldB = (label: string) =>
    drawerB
      .locator('.ant-descriptions-row')
      .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: new RegExp(`^${label}$`) }) })
      .first();
  const startField = fieldB('Начало');
  const target = dayjs(phaseB.start_date).add(7, 'day');
  const dayCell = (d2: dayjs.Dayjs) =>
    page.locator(`.ant-picker-dropdown:visible td.ant-picker-cell-in-view[title="${d2.format('YYYY-MM-DD')}"]`);

  await d.click(startField.locator('.ant-picker'), 'В поле «Начало» — новая дата');
  const pickerDropdown = page.locator('.ant-picker-dropdown:visible');
  if (!(await dayCell(target).count())) {
    await d.click(pickerDropdown.locator('.ant-picker-header-next-btn'));
  }
  await d.click(dayCell(target));
  await expect(pickerDropdown).toHaveCount(0);

  const pinnedTagB = drawerB.locator('.ant-drawer-header .ant-tag', { hasText: 'Закреплено' });
  await expect(pinnedTagB).toBeVisible();
  await d.caption('Дата задана вручную — фаза закреплена');
  await d.show(pinnedTagB);
  await d.pause(1100);

  const unpinBtn = drawerB.getByRole('button', { name: 'Снять фиксацию даты' });
  await d.click(unpinBtn, '«Снять фиксацию даты» — планировщик подберёт день сам');
  await expect(pinnedTagB).toBeHidden();
  await d.pause(500);
  const pinBtn = drawerB.getByRole('button', { name: 'Зафиксировать дату' });
  await d.click(pinBtn, '«Зафиксировать дату» — закрепить снова без переноса');
  await expect(pinnedTagB).toBeVisible();
  await d.pause(700);

  const involvementField = fieldB('Вовлечённость');
  const input = involvementField.getByRole('spinbutton');
  const endField = fieldB('Окончание');
  const endBefore = await endField.innerText();
  const NEXT = 50;

  await d.caption('Вовлечённость — какая доля дня уходит на эту фазу');
  await d.show(involvementField);
  await d.pause(1000);

  const fixBox = involvementField.getByRole('checkbox', { name: 'Зафиксировано' });
  if (!(await fixBox.isChecked())) {
    await d.click(fixBox, 'Отметьте «Зафиксировано» — у фазы будет свой процент, справочник на неё не действует');
  }
  await expect(input).toBeEnabled();
  await d.click(input, `Впишите новое значение — например, ${NEXT}%`);
  const inputBox = (await input.boundingBox())!;
  await page.evaluate(
    ({ x, y }) => window.__director?.move(x, y),
    { x: inputBox.x + inputBox.width + 30, y: inputBox.y + inputBox.height + 16 },
  );
  await d.pause(400);
  await input.press('Control+A');
  await input.pressSequentially(String(NEXT), { delay: 110 });
  await d.pause(500);
  await d.click(involvementField.getByRole('button', { name: 'Сохранить' }), 'Нажмите «Сохранить»');

  await expect(endField).not.toHaveText(endBefore);
  await d.caption('Процент зафиксирован для этой фазы задачи — во всех планах; снять — убрать галочку');
  await d.show(endField);
  await d.pause(1600);

  await d.click(drawerB.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawerB).toBeHidden();
  await page.mouse.move(900, 120);

  await expect(barB).toBeVisible();
  await d.caption('Фаза стала длиннее — окончание пересчитано');
  await d.show(barB);
  await d.pause(1800);

  await d.caption('Готово', 2200);
  await d.save('rp-executor');
});
