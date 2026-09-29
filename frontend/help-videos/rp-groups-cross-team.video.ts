// Ролик «Как видеть группы и людей из других команд на плане»: у команды с
// делением на группы — «Вид» → «Разбить по группам», метка «Из группы «…»»,
// пунктирный контур «работа на соседнюю группу»; переключаем команду в шапке
// на обычную команду — блок «Наши люди в других командах» и полоса
// «Все работы» в виде «Исполнители». Шапка возвращается на «Команда Альфа»
// в afterAll — её ждут остальные ролики раздела, снятые на той же копии базы.
import { expect, type Page, test } from '@playwright/test';
import type { AssignmentOut } from '../src/api/resourcePlanning.ts';
import { Director } from './director.ts';
import { TEAM as ALFA_TEAM, phaseBar, prepareQuarterPlan } from './rp-setup.ts';

const ETA_TEAM = 'Команда Эта';

type Scenario = { id: string; name: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null };

let createdEtaPlanId: string | null = null;

/** Утверждённый сценарий и его (уже существующий или только что созданный) план — без сброса ручных правок. */
async function ensureTeamPlan(page: Page, api: string, rp: string, team: string) {
  const scenarios: Scenario[] = await (
    await page.request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: team } })
  ).json();
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  if (!scenario) throw new Error(`Нет утверждённых сценариев команды ${team}`);

  const plans: Plan[] = await (await page.request.get(`${rp}/resource-plans`, { params: { team } })).json();
  let plan = plans.find((p) => p.scenario_id === scenario.id);
  let created = false;
  if (!plan) {
    const res = await page.request.post(`${rp}/resource-plans`, {
      data: { scenario_id: scenario.id, team, quarter: scenario.quarter, year: scenario.year },
    });
    expect(res.ok()).toBeTruthy();
    plan = (await res.json()) as Plan;
    created = true;
  }
  expect((await page.request.post(`${rp}/resource-plans/${plan.id}/compute`)).ok()).toBeTruthy();
  return { scenario, plan, created };
}

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  // План, которого не было до ролика, за собой убираем; уже существовавший — не трогаем.
  if (createdEtaPlanId) {
    await request.delete(`${api}/resource-planning/resource-plans/${createdEtaPlanId}`);
  }
  // Шапка — на «Команда Альфа» без групп: так её ждут остальные ролики раздела.
  await request.put(`${api}/auth/me/teams`, { data: { teams: [ALFA_TEAM], subgroups: [] } });
  await request.dispose();
});

test('rp-groups-cross-team', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Данные обеих команд готовим заранее (только сетевые запросы — экран пока
  // тёмный из d.install()); открываем ролик уже на команде с группами.
  const { rp, scenario: alfaScenario } = await prepareQuarterPlan(page);
  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  const { plan: etaPlan, created } = await ensureTeamPlan(page, api, rp, ETA_TEAM);
  if (created) createdEtaPlanId = etaPlan.id;

  const etaGantt: { assignments: AssignmentOut[] } = await (
    await page.request.get(`${rp}/resource-plans/${etaPlan.id}/gantt`)
  ).json();
  // Фаза, где человек в эти дни помогает не своей группе — на ней виден
  // пунктирный фиолетовый контур.
  const crossGroupPhase = etaGantt.assignments.find((a) => a.other_subgroup);
  if (!crossGroupPhase) throw new Error(`В плане команды ${ETA_TEAM} нет работы на соседнюю группу`);

  const alfaLabel = `${alfaScenario.quarter} ${alfaScenario.year} — ${alfaScenario.name}`;

  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [ETA_TEAM], subgroups: [] } })).ok()).toBeTruthy();

  await d.open(`/resource-planning?plan_id=${etaPlan.id}`, 'Как видеть группы и людей из других команд');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  const crossBar = phaseBar(page, crossGroupPhase);
  await expect(crossBar).toBeVisible();
  await d.pause(1200);
  await d.poster();
  await d.pause(4200);

  await d.click(page.locator('[data-tour="rp-view"]'), 'В команде есть деление на группы — откройте «Вид»');
  const popover = page.locator('.ant-popover:visible');
  await d.click(popover.locator('label', { hasText: 'Разбить по группам' }), 'Включите «Разбить по группам»');
  await page.mouse.move(900, 120);

  const sectionHeader = page.getByText(/задач · \d/).first();
  await sectionHeader.scrollIntoViewIfNeeded();
  await d.caption('Задачи разложены по группам команды');
  await d.show(sectionHeader);
  await d.pause(4200);

  const foreignBadge = page.locator('[title^="Из группы"]').first();
  if (await foreignBadge.count()) {
    await foreignBadge.scrollIntoViewIfNeeded();
    await d.caption('Оранжевая метка — человек из другой группы команды');
    await d.show(foreignBadge);
    await d.pause(4200);
  }

  await crossBar.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('Пунктирный контур — работа на соседнюю группу');
  await d.show(crossBar);
  await d.pause(4600);

  // Видимый для зрителя переход: меняем команду в шапке приложения.
  const teamButton = page.locator('.topbar').getByRole('button', { name: new RegExp(ETA_TEAM) });
  await d.click(teamButton, 'Переключим команду в шапке — посмотрим на обычную команду');
  const teamPopover = page.locator('.ant-popover:visible');
  await d.click(teamPopover.getByRole('button', { name: 'Сбросить' }));
  const search = teamPopover.getByPlaceholder('Поиск команды');
  await search.fill(ALFA_TEAM);
  await d.click(teamPopover.locator('[data-testid="team-filter-option"]', { hasText: ALFA_TEAM }));
  await d.click(teamPopover.getByRole('button', { name: 'Применить' }));
  await page.mouse.move(900, 120);

  await d.click(page.locator('[data-tour="rp-scenario-select"]'), `Выберите план команды «${ALFA_TEAM}»`);
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: alfaLabel }));
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();

  const ownPeople = page.getByText('Наши люди в других командах').first();
  if (await ownPeople.count()) {
    await ownPeople.scrollIntoViewIfNeeded();
    await page.mouse.move(900, 120);
    await d.caption('«Наши люди в других командах» — чем заняты они там');
    await d.show(ownPeople);
    await d.pause(4800);
  }

  const layoutSwitch = page.locator('[data-tour="rp-layout-switch"]');
  await d.click(
    layoutSwitch.locator('.ant-segmented-item', { hasText: 'Исполнители' }),
    'В виде «Исполнители» — то же самое видно на полосе человека',
  );
  const allWork = page.getByText('Все работы').first();
  await expect(allWork).toBeVisible();
  await page.mouse.move(900, 120);
  await d.caption('«Все работы» — свой план и работа в других командах на одной полосе');
  await d.show(allWork);
  await d.pause(5000);

  await d.caption('Готово', 2600);
  await d.save('rp-groups-cross-team');
});
