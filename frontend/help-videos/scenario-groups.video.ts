// Ролик «Как вести сценарий команды с группами»: «Команда Эта» (группы
// «Группа 1…4»), черновик сценария квартала — секции групп в списке задач,
// «Ресурс по группам» и «Переток внутри команды», смена группы у задачи,
// плашка «Без группы» блокирует «Утвердить» → карточка сотрудника → группа.
// В конце — всё изменённое возвращено, шапка снова на «Команда Альфа».
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Эта';
const HOME_TEAM = 'Команда Альфа';

interface ScenarioItem {
  id: string;
  year: number | null;
  quarter: string | null;
  team: string | null;
  status: 'draft' | 'approved';
}

interface AllocationItem {
  id: string;
  issue_id: string | null;
  subgroup_id: string | null;
  included: boolean;
}

interface Subgroup {
  id: string;
  name: string;
  sort_order: number;
}

interface TeamRegistryRow {
  name: string;
  has_subgroups: boolean;
  subgroups: Subgroup[];
}

interface UngroupedEmployee {
  employee_id: string;
  display_name: string;
  team: string;
}

interface ShareItem {
  subgroup_id: string;
  percent: number;
}

interface ShareRecord {
  valid_from: string | null;
  shares: ShareItem[];
}

interface ResourceEmployee {
  employee_id: string;
  display_name: string;
  role: string | null;
}

let scenarioId = '';
let targetAllocId = '';
let targetIssueId = '';
let originalSubgroupId: string | null = null;
let newSubgroupId = '';
let subgroups: Subgroup[] = [];
let ungroupedId = '';
let ungroupedName = '';
let fabricated = false;
let originalShareRecord: ShareRecord | null = null;

// Данные готовим до открытия окна — запись идёт с момента создания страницы.
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

  const teamsRes = await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  expect(teamsRes.ok()).toBeTruthy();

  const registry = await getJson<TeamRegistryRow[]>(`${api}/teams/registry`);
  const teamRow = registry.find((t) => t.name === TEAM);
  expect(teamRow?.has_subgroups, `у команды ${TEAM} нет деления на группы`).toBeTruthy();
  subgroups = teamRow!.subgroups;
  expect(subgroups.length, `у команды ${TEAM} меньше двух групп`).toBeGreaterThan(1);

  const scenarios = await getJson<ScenarioItem[]>(`${api}/planning/scenarios?teams=${encodeURIComponent(TEAM)}`);
  const scenario = scenarios.find((s) => s.team === TEAM && s.year === 2026 && s.quarter === 'Q4');
  expect(scenario, `нет сценария Q4 2026 команды ${TEAM}`).toBeTruthy();
  scenarioId = scenario!.id;
  if (scenario!.status !== 'draft') {
    const res = await request.post(`${api}/planning/scenarios/${scenarioId}/revert-to-draft`);
    expect(res.ok()).toBeTruthy();
  }

  const allocs = await getJson<AllocationItem[]>(`${api}/planning/scenarios/${scenarioId}/allocations`);
  const withGroup = allocs.find((a) => a.included && a.issue_id && a.subgroup_id);
  expect(withGroup, 'нет включённой задачи со своей группой').toBeTruthy();
  targetAllocId = withGroup!.id;
  targetIssueId = withGroup!.issue_id!;
  originalSubgroupId = withGroup!.subgroup_id;
  newSubgroupId = subgroups.find((g) => g.id !== originalSubgroupId)!.id;

  // Сотрудник без группы в этом квартале — либо уже есть в демо-данных, либо
  // фабрикуем разрыв: снимаем единственную запись «с начала участия» у кого-то
  // из команды (восстановим её в afterAll).
  const ungrouped = await getJson<UngroupedEmployee[]>(
    `${api}/teams/ungrouped?teams=${encodeURIComponent(TEAM)}&year=2026&quarter=4`,
  );
  if (ungrouped.length > 0) {
    ungroupedId = ungrouped[0].employee_id;
    ungroupedName = ungrouped[0].display_name;
  } else {
    const resource = await getJson<{ employees: ResourceEmployee[] }>(
      `${api}/planning/scenarios/${scenarioId}/resource`,
    );
    for (const emp of resource.employees) {
      const history = await getJson<ShareRecord[]>(
        `${api}/teams/employees/${emp.employee_id}/subgroup-shares?team=${encodeURIComponent(TEAM)}`,
      );
      if (history.length === 1 && history[0].valid_from === null) {
        originalShareRecord = history[0];
        ungroupedId = emp.employee_id;
        ungroupedName = emp.display_name;
        break;
      }
    }
    expect(ungroupedId, 'не нашлось сотрудника для демонстрации «без группы»').toBeTruthy();
    const del = await request.delete(
      `${api}/teams/employees/${ungroupedId}/subgroup-shares?team=${encodeURIComponent(TEAM)}`,
    );
    expect(del.ok()).toBeTruthy();
    fabricated = true;
  }

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });

  if (targetIssueId) {
    await request.put(`${api}/issues/${targetIssueId}/subgroup`, {
      data: { subgroup_id: originalSubgroupId },
    });
  }
  if (ungroupedId) {
    if (fabricated && originalShareRecord) {
      await request.put(`${api}/teams/employees/${ungroupedId}/subgroup-shares`, {
        data: { team: TEAM, valid_from: originalShareRecord.valid_from, shares: originalShareRecord.shares },
      });
    } else if (!fabricated) {
      // Видео само завело запись «с начала участия» через карточку — снимаем её,
      // сотрудник снова без группы, как было изначально.
      await request.delete(
        `${api}/teams/employees/${ungroupedId}/subgroup-shares?team=${encodeURIComponent(TEAM)}`,
      );
    }
  }
  await request.put(`${api}/auth/me/teams`, { data: { teams: [HOME_TEAM], subgroups: [] } });
  await request.dispose();
});

test('scenario-groups', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(`/planning?scenario=${scenarioId}`, 'Как вести сценарий команды с группами');

  const headerTeam = page.locator('[data-tour="header-team"]');
  await expect(headerTeam).toContainText(TEAM, { timeout: 20_000 });
  const backlogCard = page.locator('.ant-card', { hasText: 'Элементы бэклога' });
  await expect(backlogCard).toBeVisible({ timeout: 20_000 });
  await d.pause(1000);
  await d.poster();
  await d.pause(1700);

  await d.caption(`Шапка — «${TEAM}»: у неё несколько групп`);
  await d.show(headerTeam);
  await d.pause(2200);

  // Таблица ресурса над вкладками сворачивается, как только страницу прокрутили вниз, —
  // показываем её, пока страница наверху, а перед повторным показом возвращаемся наверх.
  const resourceGroups = page.locator('[data-tour="planning-resource-subgroups"]');
  await expect(resourceGroups).toBeVisible({ timeout: 10_000 });
  await d.caption('«Ресурс по группам» — часы на бэклог по каждой из них');
  await d.show(resourceGroups);
  await d.pause(2400);

  const flowLine = page.locator('[data-tour="planning-subgroup-flow"]');
  if (await flowLine.count()) {
    await d.caption('«Переток внутри команды» — кто кому отдал часы, а кто получил');
    await d.show(flowLine);
    await d.pause(1900);
  }

  const sectionHeader = backlogCard.locator('[data-tour="planning-subgroup-section"]').first();
  await expect(sectionHeader).toBeVisible({ timeout: 15_000 });
  await d.caption('Список задач разбит по группам команды');
  await d.show(sectionHeader);
  await d.pause(2400);

  const row = page.locator(`[data-flip-wrapper][data-alloc-id="${targetAllocId}"]`);
  await expect(row).toBeVisible();
  await row.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await d.pause(600);
  // У команды с делением третий select строки — «Группа» (после аналитика и разработчика).
  const groupSelect = row.locator(':scope > div > div > .ant-select').nth(2);
  await d.click(groupSelect, 'Колонка «Группа» — у задачи есть своя группа');
  const dropdown = page.locator('.ant-select-dropdown:visible');
  const newGroupName = subgroups.find((g) => g.id === newSubgroupId)!.name;
  await expect(dropdown.locator('.ant-select-item-option').first()).toBeVisible({ timeout: 10_000 });
  await d.click(
    dropdown.locator('.ant-select-item-option', { hasText: newGroupName }),
    `Смените группу задачи на «${newGroupName}»`,
  );
  await expect(groupSelect).toContainText(newGroupName);
  await page.mouse.move(700, 120);
  await d.caption('Задача перешла в секцию другой группы');
  await d.pause(2500);

  const resourceGroupsAfter = page.locator('[data-tour="planning-resource-subgroups"]');
  await d.caption('Часы задачи сразу учтены в новой группе');
  await page.evaluate(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    for (const el of document.querySelectorAll<HTMLElement>('*')) {
      if (el.scrollTop > 0 && /(auto|scroll|overlay)/.test(getComputedStyle(el).overflowY)) {
        el.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }
  });
  await d.pause(1200);
  await d.show(resourceGroupsAfter);
  await d.pause(2700);

  const peopleCard = page.locator('.ant-card', { hasText: 'По сотрудникам' });
  const sharedTag = peopleCard.locator('.ant-tag', { hasText: /^(общий|в группе)/ });
  if (await sharedTag.count()) {
    await d.caption('Сотрудник может делить время между несколькими группами');
    await d.show(sharedTag.first());
    await d.pause(2000);
  }

  const alert = page.locator('.ant-alert', { hasText: 'сценарий нельзя утвердить' });
  await expect(alert).toBeVisible({ timeout: 10_000 });
  await d.caption('Пока у кого-то из команды нет группы — утвердить сценарий нельзя');
  await d.show(alert);
  await d.pause(2000);

  const approveWrap = page.locator('span', { has: page.locator('[data-tour="planning-approve"]') });
  await approveWrap.hover();
  await d.pause(500);
  const tooltip = page.locator('.ant-tooltip:visible', { hasText: 'Сначала проставьте группы' });
  await expect(tooltip).toBeVisible({ timeout: 5_000 });
  await d.caption('Кнопка «Утвердить» подскажет, кого именно поправить');
  await d.show(tooltip);
  await d.pause(2000);
  await page.mouse.move(700, 500);

  const nameLink = alert.getByText(ungroupedName, { exact: true });
  await d.click(nameLink, `Нажмите на имя «${ungroupedName}»`);
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible({ timeout: 10_000 });
  await d.caption('Откроется карточка сотрудника');
  await d.pause(1200);

  const noGroupTag = drawer.locator('.ant-tag', { hasText: 'без группы' });
  await expect(noGroupTag).toBeVisible({ timeout: 10_000 });
  await d.show(noGroupTag);
  await d.pause(1800);

  await d.click(drawer.getByRole('button', { name: 'Перевести в группу' }).first(), 'Нажмите «Перевести в группу»');
  const modal = page.locator('.ant-modal', { hasText: 'Перевести в группу' });
  await expect(modal).toBeVisible();
  await d.click(modal.locator('.ant-select'), 'Выберите группу');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: subgroups[0].name }));
  await d.click(modal.getByRole('button', { name: 'Сохранить' }));
  await expect(modal).toBeHidden();
  await page.mouse.move(700, 500);

  await d.caption('Группа заведена — сотрудник больше не мешает утверждению');
  await d.show(drawer);
  await d.pause(1800);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку сотрудника');
  await expect(drawer).toBeHidden();
  await page.mouse.move(700, 500);

  // Если в демо-данных без группы был только этот один человек — плашка
  // исчезнет и «Утвердить» станет доступна; если были и другие — плашка
  // останется, но уже с меньшим числом, и это тоже честный результат показать.
  const approveButton = page.locator('[data-tour="planning-approve"]');
  const approveEnabled = await expect(approveButton)
    .toBeEnabled({ timeout: 8_000 })
    .then(() => true)
    .catch(() => false);
  if (approveEnabled) {
    await d.caption('Группы у всех есть — «Утвердить» стала доступна');
    await d.show(approveButton);
  } else {
    await d.caption('Плашка обновилась — этот человек в списке больше не мешает');
    await d.show(alert);
  }
  await d.pause(2400);

  await d.caption('Готово', 2200);
  await d.save('scenario-groups');
});
