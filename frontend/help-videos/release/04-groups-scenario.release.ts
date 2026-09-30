// Глава «Ресурс групп в сценарии»: сценарий команды с группами → «По сотрудникам»
// разбит на группы → поделённый сотрудник в двух группах с пометкой «общий N%» и
// часами по доле → переведённый внутри квартала — в обеих группах со своими днями →
// деление после утверждения видно в «Доступность изменилась».
// «Утвердить нельзя, пока есть сотрудники без группы» не показываем: в демо-данных
// у всех активных участников команды группа есть.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

/** Сотрудник, которого глава о переводе и делении делит между группами (демо-база). */
const PERSON = 'Ольховская Раиса';

type Team = { name: string; has_subgroups: boolean; subgroups: { id: string; name: string }[] };
type Employee = { id: string; display_name: string };
type ShareRecord = { valid_from: string | null; shares: { subgroup_id: string; percent: number }[] };
type Scenario = { id: string; team: string | null; year: number; quarter: string; status: string };
type Diff = { has_changes: boolean; changed_employees: { employee_name: string; subgroup_after: string | null }[] };

releaseFrame();

let scenarioId = '';

// Данные готовим до открытия окна: запись идёт с момента его создания.
test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string): Promise<T> => {
    const res = await request.get(url);
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  const registry = await getJson<Team[]>(`${api}/teams/registry`);
  const withGroups = registry.find((t) => t.has_subgroups && t.subgroups.length >= 2);
  expect(withGroups, 'нет команды с группами').toBeTruthy();
  const team = withGroups!.name;
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [team], subgroups: [] } })).ok()).toBeTruthy();

  // Самый свежий сценарий команды.
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios`);
  const scenario = scenarios
    .filter((s) => s.team === team)
    .sort((a, b) => b.year - a.year || b.quarter.localeCompare(a.quarter))[0];
  expect(scenario, `нет сценария команды ${team}`).toBeTruthy();
  scenarioId = scenario.id;
  const quarterStart = `${scenario.year}-${String((Number(scenario.quarter.slice(1)) - 1) * 3 + 1).padStart(2, '0')}-01`;

  const employees = await getJson<Employee[]>(`${api}/employees`);
  const person = employees.find((e) => e.display_name === PERSON);
  expect(person, `нет сотрудника ${PERSON}`).toBeTruthy();
  const sharesUrl = `${api}/teams/employees/${person!.id}/subgroup-shares`;

  // 1) Сотрудник — целиком в своей группе (записи с датой, в т.ч. из главы о делении, снимаем).
  let history = await getJson<ShareRecord[]>(`${sharesUrl}?team=${encodeURIComponent(team)}`);
  for (const r of history.filter((x) => x.valid_from)) {
    expect((await request.delete(sharesUrl, { params: { team, valid_from: r.valid_from! } })).ok()).toBeTruthy();
  }
  history = await getJson<ShareRecord[]>(`${sharesUrl}?team=${encodeURIComponent(team)}`);
  const base = history.find((r) => r.valid_from === null);
  expect(base?.shares.length, 'у сотрудника должна быть одна группа с начала участия').toBe(1);
  const fromId = base!.shares[0].subgroup_id;
  const toId = withGroups!.subgroups.find((g) => g.id !== fromId)!.id;

  // 2) Утверждение заново: снимок фиксирует текущее распределение по группам
  //    (в демо-базе старый снимок подписан именами групп до обезличивания).
  if (scenario.status !== 'draft') {
    expect((await request.post(`${api}/planning/scenarios/${scenarioId}/revert-to-draft`)).ok()).toBeTruthy();
  }
  const approved = await request.post(`${api}/planning/scenarios/${scenarioId}/approve`);
  expect(approved.ok(), await approved.text()).toBeTruthy();

  // 3) После утверждения — деление 60/40 с начала квартала.
  const put = await request.put(sharesUrl, {
    data: {
      team,
      valid_from: quarterStart,
      shares: [
        { subgroup_id: fromId, percent: 60 },
        { subgroup_id: toId, percent: 40 },
      ],
    },
  });
  expect(put.ok(), await put.text()).toBeTruthy();
  const diff = await getJson<Diff>(`${api}/planning/scenarios/${scenarioId}/capacity-diff`);
  expect(diff.changed_employees.map((e) => e.employee_name)).toContain(PERSON);
  await request.dispose();
});

test('04-groups-scenario', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(`/planning?scenario=${scenarioId}`, chapterTitle('Ресурс групп в сценарии'));

  const card = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'По сотрудникам' }) });
  // Строка сотрудника в панели: пометка → имя с пометками → шапка строки → строка целиком.
  const personRow = (tag: string | RegExp) =>
    card.locator('.ant-tag', { hasText: tag }).first().locator('xpath=../../..');
  const share60 = personRow('общий 60%');
  const share40 = personRow('общий 40%');
  await expect(share60).toBeVisible({ timeout: 60_000 });
  await expect(share40).toBeVisible();
  // Переведённый внутри квартала: пометки «в группе до …» и «в группе с …».
  const movedTag = card.locator('.ant-tag', { hasText: /^в группе до / }).first();
  await expect(movedTag).toBeVisible();
  // Первый span в строке — значок роли, второй — имя.
  const movedName = (await movedTag.locator('xpath=..').locator(':scope > span').nth(1).innerText()).trim();
  const movedBefore = movedTag.locator('xpath=../../..');
  const movedAfter = card
    .locator('.ant-tag', { hasText: /^в группе с / })
    .locator('xpath=..')
    .filter({ hasText: movedName })
    .first()
    .locator('xpath=../..');

  // Панель «По сотрудникам» — к верху экрана, плавно (ещё под заголовком главы).
  await card.evaluate((el) => el.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  await d.pause(900);

  await d.caption('Ресурс сценария разбит по группам');
  await d.show(card.locator('.ant-card-body > div > div').first().locator(':scope > div').first());
  await d.pause(900);

  await d.caption('Поделённый сотрудник — в каждой группе, часы по доле');
  await d.show(share40);
  await d.pause(900);
  await d.show(share60);
  await d.pause(900);

  await d.caption('Переведённый в квартале — в обеих группах, по своим дням');
  await d.show(movedBefore);
  await d.pause(900);
  await d.show(movedAfter);
  await d.pause(900);

  // Наверх — к отметке о расхождении с утверждённым сценарием. Рамку снимаем
  // заранее: она стоит на месте экрана и при прокрутке оказалась бы на чужой строке.
  await page.evaluate(() => window.__director?.ring(null));
  const drift = page.getByText(/^Доступность изменилась/);
  await drift.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await d.pause(900);
  await d.click(drift, 'Деление после утверждения — в «Доступность изменилась»');
  const driftLine = page.locator('span', { hasText: /^группа: / }).first().locator('xpath=..');
  await expect(driftLine).toBeVisible();
  await d.show(driftLine);
  await d.pause(900);

  await d.caption('Часы групп считаются по долям и датам перевода');
  await d.show(driftLine);
  await d.pause(2600);
  await saveClip(page, '04-groups-scenario');
});
