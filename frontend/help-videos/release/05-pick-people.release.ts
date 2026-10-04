// Глава «„Подобрать людей“ в „Загрузке по дням“»: ресурсный план утверждённого
// сценария демо-команды → «Загрузка по дням» → окно «Подобрать людей»: человек
// другой команды по фамилии и вся роль ещё одной команды → секция «Наблюдаемые»:
// загрузка по дням, свободные часы по месяцам, остаток «Технических задач».
// После съёмки список наблюдения плана снова пуст.
import { expect, type APIRequestContext, type Locator, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

const TEAM = 'Команда Альфа';
/** Низ закреплённых шапок (страница + шкала графика) в кадре 1920×1080, с запасом. */
const STICKY_BOTTOM = 305;

type Scenario = { id: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null; parent_plan_id: string | null };
type Gantt = {
  plan: { status: string };
  stale_due_to_other_teams: boolean;
  employee_load: { employee_id: string; days: { date: string }[] }[];
};
type Employee = {
  id: string;
  display_name: string;
  is_active: boolean;
  role: string | null;
  team: string | null;
  teams?: { team: string; joined_at: string | null; left_at: string | null }[];
};
type WatchRow = {
  employee_id: string;
  home_team: string | null;
  free_hours: number;
  quarter: { own_hours: number } | null;
  tech_reserve: unknown | null;
};

releaseFrame();

let planId = '';
let watchUrl = '';
/** Человек другой команды — добавляется по фамилии. */
let hero = '';
/** Вся роль команды — добавляется кнопкой «Добавить всех». */
let groupTeam = '';
let groupRoleLabel = '';
let groupSize = 0;

/** Убрать всех из списка наблюдения плана: глава оставляет его пустым. */
async function clearWatch(request: APIRequestContext): Promise<void> {
  const res = await request.get(watchUrl);
  expect(res.ok(), watchUrl).toBeTruthy();
  const { rows } = (await res.json()) as { rows: WatchRow[] };
  for (const r of rows) expect((await request.delete(`${watchUrl}/${r.employee_id}`)).ok()).toBeTruthy();
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

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  expect(
    (await request.patch(`${rp}/preferences`, { data: { view_mode: 'tasks', collapsed_initiative_ids: [] } })).ok(),
  ).toBeTruthy();

  // План последнего утверждённого сценария команды (как в rp-setup.ts).
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios`, { status: 'approved', teams: TEAM });
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  expect(scenario, `нет утверждённого сценария команды ${TEAM}`).toBeTruthy();
  const plans = await getJson<Plan[]>(`${rp}/resource-plans`, { team: TEAM });
  const plan = plans.find((p) => p.scenario_id === scenario!.id && !p.parent_plan_id);
  expect(plan, 'нет плана последнего сценария').toBeTruthy();
  planId = plan!.id;
  watchUrl = `${rp}/resource-plans/${planId}/watch`;

  // Прошлые главы могли поменять сценарий и людей — план должен быть свежим.
  let gantt = await getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`);
  if (gantt.plan.status !== 'ready' || gantt.stale_due_to_other_teams) {
    expect((await request.post(`${rp}/resource-plans/${planId}/compute`)).ok()).toBeTruthy();
    await expect
      .poll(async () => (await getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`)).plan.status, { timeout: 60_000 })
      .toBe('ready');
    gantt = await getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`);
  }
  const inPlan = new Set(gantt.employee_load.map((r) => r.employee_id));
  const days = gantt.employee_load[0].days.map((d) => d.date).sort();
  const [qStart, qEnd] = [days[0], days.at(-1)!];

  // Кого показать, смотрим самим списком наблюдения: добавляем всех кандидатов,
  // читаем их строки и сразу убираем.
  await clearWatch(request);
  const employees = (await getJson<Employee[]>(`${api}/employees`, { is_active: 'true', with_teams: 'true' })).filter(
    (e) => e.is_active && e.role && !inPlan.has(e.id),
  );
  expect((await request.post(watchUrl, { data: { employee_ids: employees.map((e) => e.id) } })).ok()).toBeTruthy();
  const { rows } = await getJson<{ rows: WatchRow[] }>(watchUrl);
  await clearWatch(request);
  const rowOf = new Map(rows.map((r) => [r.employee_id, r]));
  /** Есть что показать: остаток «Технических задач» и задачи в днях. */
  const telling = (id: string) => {
    const r = rowOf.get(id);
    return !!r?.tech_reserve && (r.quarter?.own_hours ?? 0) > 0;
  };

  // Роль команды — как её берёт окно: люди роли, состоявшие в команде хоть день квартала.
  const roleTeam = (team: string, role: string) =>
    employees.filter(
      (e) =>
        e.role === role &&
        (e.teams
          ? e.teams.some((t) => t.team === team && (!t.joined_at || t.joined_at <= qEnd) && (!t.left_at || t.left_at > qStart))
          : e.team === team),
    );
  const teams = [...new Set(rows.map((r) => r.home_team).filter((t): t is string => !!t && t !== TEAM))];
  const roles = [...new Set(employees.map((e) => e.role!))];
  const group = teams
    .flatMap((team) => roles.map((role) => ({ team, role, people: roleTeam(team, role) })))
    .filter((g) => g.people.length >= 2 && g.people.length <= 5 && g.people.every((e) => telling(e.id)))
    .sort((a, b) => b.people.length - a.people.length || a.team.localeCompare(b.team))[0];
  expect(group, 'нет роли команды, где у всех есть задачи и запас «Технических задач»').toBeTruthy();
  groupTeam = group.team;
  groupSize = group.people.length;
  const roleList = await getJson<{ code: string; label: string }[]>(`${api}/roles`);
  groupRoleLabel = roleList.find((r) => r.code === group.role)!.label;

  // Человек по фамилии — из третьей команды, самый свободный из тех, у кого есть что показать.
  const heroRow = rows
    .filter((r) => telling(r.employee_id) && r.free_hours > 0 && r.home_team && r.home_team !== groupTeam)
    .sort((a, b) => b.free_hours - a.free_hours)[0];
  expect(heroRow, 'нет человека другой команды со свободными часами').toBeTruthy();
  hero = employees.find((e) => e.id === heroRow.employee_id)!.display_name;
  await request.dispose();
});

// Список наблюдения общий для плана: следующие главы видят его пустым.
test.afterAll(async ({ playwright }, testInfo) => {
  if (!watchUrl) return;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await clearWatch(request);
  await request.dispose();
});

test('05-pick-people', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(`/resource-planning?plan_id=${planId}`, chapterTitle('«Подобрать людей» в «Загрузке по дням»'));

  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });
  const load = page.locator('[data-tour="rp-load"]');
  await expect(load).toBeVisible({ timeout: 60_000 });
  // Запас снизу страницы: таблица загрузки поднимается над подписью ролика.
  await page.addStyleTag({ content: '[data-tour="rp-load"] { padding-bottom: 120px; }' });
  const scroller = page.locator('.scroll-y', { has: load });
  /** Плавно прокрутить: верх `target` — под закреплённой шапкой, без цели — до конца страницы. */
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
  await d.pause(1000);

  // «Загрузка по дням» и кнопка в её шапке.
  const pickBtn = load.getByRole('button', { name: 'Подобрать людей' });
  await scrollTo();
  await d.click(pickBtn, '«Подобрать людей» — люди любых команд рядом с планом');

  const modal = page.locator('.ant-modal', { hasText: 'Подобрать людей' });
  await expect(modal).toBeVisible();
  const people = modal.getByRole('combobox', { name: 'Сотрудники' });
  await d.type(people, hero, 'Найдите человека другой команды по фамилии');
  const option = page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: hero });
  await d.click(option.first());
  // Список вариантов закрываем щелчком по заголовку окна — он закрывает строку ниже.
  await modal.locator('.ant-modal-title').click();
  await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);

  // Вся роль команды сразу.
  const teamSelect = modal.getByRole('combobox', { name: 'Команда' });
  await d.type(teamSelect, groupTeam.replace(/^Команда\s+/, ''), 'Или добавьте сразу всю роль команды');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: groupTeam }).first());
  await d.click(modal.getByRole('combobox', { name: 'Роль' }));
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: new RegExp(`^${groupRoleLabel}$`) }),
  );
  await d.click(modal.getByRole('button', { name: 'Добавить всех' }));
  const tags = modal.locator('.ant-select-selection-item');
  await expect(tags).toHaveCount(1 + groupSize);
  await d.show(modal.locator('.ant-select').first());
  await d.pause(900);
  await d.click(modal.getByRole('button', { name: 'Добавить', exact: true }));
  await expect(modal).toBeHidden();

  // Секция «Наблюдаемые» под людьми плана.
  const watchTitle = load.getByText('НАБЛЮДАЕМЫЕ', { exact: true });
  await expect(watchTitle).toBeVisible();
  const removeBtns = load.getByRole('button', { name: /^Убрать из наблюдаемых/ });
  await expect(removeBtns).toHaveCount(1 + groupSize);
  await page.mouse.move(1000, 110);
  await scrollTo();
  // Строки шире окна: рамка — от подписи секции до правых колонок последней строки.
  const lastRight = removeBtns.last().locator('xpath=..');
  await d.caption('Секция «Наблюдаемые» — их загрузка по дням');
  await d.show(watchTitle, lastRight);
  await d.pause(1600);

  const freeHead = load.getByText('СВОБОДНО ПО МЕСЯЦАМ, Ч', { exact: true });
  await d.caption('Справа — свободные часы по месяцам и остаток «Технических задач»');
  await d.show(freeHead.locator('xpath=..'), lastRight);
  await d.pause(2200);

  await page.mouse.move(1000, 110);
  await d.caption('Список общий для плана — его видят все, кто открывает план');
  await d.show(watchTitle, lastRight);
  await d.pause(2600);
  await saveClip(d, '05-pick-people');
});
