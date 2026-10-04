// Ролик «Как разделить команду на группы»: «Настройки» → «Команды и группы» — признак
// «Делится на группы» → две группы → фильтр групп в шапке → «Ресурсы»: плашка «Без группы»,
// группа в карточке сотрудника → «Сценарии»: «Ресурс по группам» и секции задач.
// От имени демо-администратора. В конце деление выключено, группы и приписка убраны.
import { type APIRequestContext, expect, type PlaywrightWorkerArgs, test, type TestInfo } from '@playwright/test';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const TEAM = 'Команда Фи';
const HOME_TEAM = 'Команда Альфа';
const GROUPS = ['Группа А', 'Группа Б'];

interface TeamRegistryRow {
  name: string;
  has_subgroups: boolean;
  subgroups: { id: string; name: string }[];
}
interface ScenarioItem {
  id: string;
  name: string;
  team: string | null;
  year: number | null;
  quarter: string | null;
}

let scenario: ScenarioItem | null = null;
let touchedEmployeeId = '';
/** Остальные сотрудники, которых ролик группирует за кадром, — для уборки. */
const extraEmployeeIds: string[] = [];
/** Задачи сценария, включённые за кадром: (id строки, было ли включено). */
const touchedAllocs: { id: string; included: boolean }[] = [];

async function ctx(playwright: PlaywrightWorkerArgs['playwright'], testInfo: TestInfo) {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({ storageState: ADMIN_STATE });
  return { api, request };
}

/** Вернуть команду в исходное состояние: приписка сотрудника, группы, признак деления. */
async function cleanup(api: string, request: APIRequestContext, employeeId: string): Promise<void> {
  for (const id of extraEmployeeIds) {
    await request.delete(`${api}/teams/employees/${id}/subgroup-shares?team=${encodeURIComponent(TEAM)}`);
  }
  if (scenario) {
    for (const a of touchedAllocs) {
      await request.patch(`${api}/planning/scenarios/${scenario.id}/allocations/${a.id}`, { data: { included: a.included } });
    }
  }
  const registry = (await (await request.get(`${api}/teams/registry`)).json()) as TeamRegistryRow[];
  const row = registry.find((t) => t.name === TEAM);
  if (!row) return;
  if (employeeId) {
    await request.delete(`${api}/teams/employees/${employeeId}/subgroup-shares?team=${encodeURIComponent(TEAM)}`);
  }
  for (const g of row.subgroups) await request.delete(`${api}/teams/subgroups/${g.id}`);
  if (row.has_subgroups) {
    await request.patch(`${api}/teams/registry/${encodeURIComponent(TEAM)}`, { data: { has_subgroups: false } });
  }
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const { api, request } = await ctx(playwright, testInfo);
  await cleanup(api, request, '');
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  const list = (await (await request.get(`${api}/planning/scenarios`, { params: { teams: TEAM } })).json()) as ScenarioItem[];
  scenario = list.find((s) => s.team === TEAM && s.year === 2026 && s.quarter === 'Q4') ?? list.find((s) => s.team === TEAM) ?? null;
  expect(scenario, `нет сценария команды ${TEAM}`).toBeTruthy();
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const { api, request } = await ctx(playwright, testInfo);
  await cleanup(api, request, touchedEmployeeId);
  await request.put(`${api}/auth/me/teams`, { data: { teams: [HOME_TEAM], subgroups: [] } });
  await request.dispose();
});

test('settings-team-groups', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;

  await d.open('/settings#teams', 'Как разделить команду на группы');
  const teamRow = page.locator('tr.ant-table-row', { hasText: TEAM }).first();
  await expect(teamRow).toBeVisible({ timeout: 20_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.caption('«Настройки», экран «Команды и группы»');
  await d.show(page.locator('.ant-menu-item', { hasText: 'Команды и группы' }));
  await d.pause(1200);

  await d.click(teamRow.getByRole('switch'), 'Включите «Делится на группы» у нужной команды');
  await expect(teamRow.getByRole('switch')).toBeChecked();
  const expander = teamRow.locator('.ant-table-row-expand-icon');
  await expect(expander).toBeVisible({ timeout: 10_000 });
  await d.click(expander, 'Раскройте строку — там список групп');

  const nameInput = page.getByPlaceholder('Название группы');
  await expect(nameInput).toBeVisible();
  for (const name of GROUPS) {
    await d.type(nameInput, name, name === GROUPS[0] ? 'Впишите название группы' : 'И ещё одну группу');
    await d.click(page.getByRole('button', { name: 'Добавить' }));
    await expect(page.locator(`input[value="${name}"]`)).toBeVisible();
  }
  await page.mouse.move(1300, 120);
  await d.caption('Группы заведены — их видно в строке команды');
  await d.show(teamRow);
  await d.pause(1500);

  // Шапка: второй уровень фильтра.
  await d.waitVoice();
  const headerTeam = page.locator('[data-tour="header-team"]');
  await d.click(headerTeam.locator('button'), 'В шапке появился фильтр по группам');
  const subgroups = page.locator('[data-testid="team-filter-subgroups"]');
  await expect(subgroups).toBeVisible({ timeout: 10_000 });
  await d.show(subgroups);
  await d.pause(2200);
  await page.keyboard.press('Escape');
  await expect(subgroups).toBeHidden();
  await page.evaluate(() => window.__director?.ring(null));

  // Ресурсы: кого куда.
  await d.waitVoice();
  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Теперь распределим людей — раздел «Ресурсы»');
  const alert = page.locator('.ant-alert', { hasText: 'Без группы' });
  await expect(alert).toBeVisible({ timeout: 20_000 });
  await d.caption('Пока у людей нет группы, сервис напоминает об этом');
  await d.show(alert);
  await d.pause(1500);
  const link = alert.locator('a').first();
  const person = (await link.innerText()).trim();
  await d.click(link, 'Откройте карточку сотрудника');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible({ timeout: 10_000 });
  await d.click(drawer.getByRole('button', { name: 'Перевести в группу' }).first(), 'Нажмите «Перевести в группу»');
  const modal = page.locator('.ant-modal', { hasText: 'Перевести в группу' });
  await expect(modal).toBeVisible();
  await d.click(modal.locator('.ant-select'), 'Выберите группу');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: GROUPS[0] }));
  await d.click(modal.getByRole('button', { name: 'Сохранить' }), 'Сохраните');
  await expect(modal).toBeHidden();
  await page.mouse.move(1300, 120);

  // Запоминаем сотрудника для уборки.
  const employees = (await (await page.request.get(`${api}/employees`)).json()) as { id: string; display_name: string }[];
  touchedEmployeeId = employees.find((e) => e.display_name === person)?.id ?? '';

  await d.caption(`Сотрудник теперь в группе «${GROUPS[0]}»`);
  await d.show(drawer);
  await d.pause(1800);
  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();

  const prep = (async () => {
    // За кадром, пока идёт озвучка: остальных сотрудников раскладываем по группам, нескольким задачам сценария
    // назначаем группы — иначе в «Сценариях» нечего показать, кроме нулей.
    const registry = (await (await page.request.get(`${api}/teams/registry`)).json()) as TeamRegistryRow[];
    const groupIds = registry.find((t) => t.name === TEAM)!.subgroups.map((g) => g.id);
    const ungrouped = (await (
      await page.request.get(`${api}/teams/ungrouped`, { params: { teams: TEAM, year: '2026', quarter: '4' } })
    ).json()) as { employee_id: string }[];
    await Promise.all(ungrouped.map(async (u, i) => {
      const res = await page.request.put(`${api}/teams/employees/${u.employee_id}/subgroup-shares`, {
        data: { team: TEAM, valid_from: null, shares: [{ subgroup_id: groupIds[(i + 1) % 2], percent: 100 }] },
      });
      expect(res.ok()).toBeTruthy();
      extraEmployeeIds.push(u.employee_id);
    }));
    const allocs = (await (
      await page.request.get(`${api}/planning/scenarios/${scenario!.id}/allocations`)
    ).json()) as {
      id: string;
      issue_id: string | null;
      included: boolean;
      estimate_analyst_hours: number | null;
      estimate_dev_hours: number | null;
    }[];
    const picked = allocs
      .filter((a) => a.issue_id && (a.estimate_analyst_hours ?? 0) + (a.estimate_dev_hours ?? 0) > 0)
      .sort((a, b) => Number(b.included) - Number(a.included))
      .slice(0, 4);
    for (const [i, a] of picked.entries()) {
      touchedAllocs.push({ id: a.id, included: a.included });
      if (!a.included) {
        const inc = await page.request.patch(`${api}/planning/scenarios/${scenario!.id}/allocations/${a.id}`, {
          data: { included: true, lift: true },
        });
        expect(inc.ok()).toBeTruthy();
      }
      const grp = await page.request.put(`${api}/issues/${a.issue_id}/subgroup`, { data: { subgroup_id: groupIds[i % 2] } });
      expect(grp.ok()).toBeTruthy();
    }


  })();

  await d.caption('Остальных сотрудников раскладывают по группам так же');
  await d.pause(1500);

  // Сценарии.
  await d.waitVoice();
  await prep;
  await d.click(page.locator('.side-item', { hasText: 'Сценарии' }), 'В «Сценариях» команда тоже делится на группы');
  await d.click(page.locator('[data-tour="planning-scenario-select"]'));
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: scenario!.name }));
  const resourceGroups = page.locator('[data-tour="planning-resource-subgroups"]');
  await expect(resourceGroups).toBeVisible({ timeout: 20_000 });
  await d.caption('«Ресурс по группам» — часы на бэклог по каждой группе');
  await d.show(resourceGroups);
  await d.pause(2200);
  const section = page.locator('[data-tour="planning-subgroup-section"]').first();
  if (await section.count()) {
    await d.caption('Список задач разбит на секции по группам');
    await d.show(section);
    await d.pause(2200);
  }

  await d.caption('Готово', 2200);
  await d.save('settings-team-groups');
});
