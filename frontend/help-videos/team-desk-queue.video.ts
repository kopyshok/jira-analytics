// Ролик «Как оценить очередь разработчика»: Стол тимлида → «Ведомость» →
// колонка «Очередь» (подсказка со свободными часами) → «к вып.» у
// перегруженного разработчика → длинной задаче дневная норма → очередь
// пересчиталась, появилась «Резиновые задачи» → «Задач в работе одновременно»
// → спринт → «Колонки» → «Отсутствия».
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

interface DeskDeveloper {
  developer_id: string;
  display_name: string | null;
}
interface DeskIssue {
  id: string;
  key: string;
  developer_id: string | null;
  est_hours: number | null;
  fact_hours: number;
  in_queue: boolean;
  assigned_to_owner: boolean;
  daily_rate: number | null;
  is_subtask: boolean;
}
interface Workload {
  assigned_hours: number;
  overloaded: boolean;
}
interface Overview {
  developers: DeskDeveloper[];
  issues: DeskIssue[];
  workload: Record<string, Workload>;
}

let issueId = '';
let devId = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  expect((await request.put(`${api}/users/me/team-desk-filter`, {
    data: {
      teams: [TEAM], mode: 'open', show_reviewed: false, show_done_subtasks: true,
      group_by_developer: true, hidden_columns: ['days', 'scale', 'sprint', 'release'],
    },
  })).ok()).toBeTruthy();

  const overviewRes = await request.get(`${api}/team-desk/overview`, {
    params: { teams: TEAM, only_open: 'true', show_reviewed: 'false', show_done_subtasks: 'true' },
  });
  expect(overviewRes.ok()).toBeTruthy();
  const overview = (await overviewRes.json()) as Overview;

  // Перегруженный разработчик — у него очередь больше свободных часов недели.
  const overloaded = overview.developers.find((dv) => overview.workload[dv.developer_id]?.overloaded);
  expect(overloaded, 'нет перегруженного разработчика в срезе').toBeTruthy();
  devId = overloaded!.developer_id;

  // Длинная задача этого же разработчика в очереди к выполнению, без своей
  // дневной нормы — та же строка, что окажется в списке после клика «к вып.».
  // Сортировка по оценке — самая крупная задача нагляднее всего меняет очередь.
  const candidates = overview.issues
    .filter((i) => i.developer_id === devId && i.in_queue && i.assigned_to_owner
      && !i.daily_rate && !i.is_subtask && (i.est_hours ?? 0) - i.fact_hours > 10)
    .sort((a, b) => (b.est_hours ?? 0) - (a.est_hours ?? 0));
  expect(candidates.length, 'нет подходящей длинной задачи для дневной нормы').toBeGreaterThan(0);
  issueId = candidates[0].id;

  // На случай следов прошлого прогона на той же копии базы.
  await request.put(`${api}/team-desk/issues/${issueId}/daily-rate`, { data: { hours: null } });
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (issueId) {
    await request.put(`${api}/team-desk/issues/${issueId}/daily-rate`, { data: { hours: null } }).catch(() => undefined);
  }
  // Личная раскладка и колонки — не общие настройки, но следующий ролик не
  // должен унаследовать спринт-отбор и убранную колонку этого ролика.
  await request.put(`${api}/users/me/team-desk-filter`, {
    data: {
      teams: [TEAM], mode: 'open', show_reviewed: false, show_done_subtasks: true,
      group_by_developer: true, hidden_columns: [], sprints: [], releases: [],
    },
  }).catch(() => undefined);
  await request.dispose();
});

test('team-desk-queue', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open('/team-desk', 'Как оценить очередь разработчика');

  const issuesBlock = page.locator('[data-tour="desk-issues"]');
  await expect(issuesBlock).toBeVisible({ timeout: 20_000 });
  await d.pause(1100);
  await d.poster();
  await d.pause(1700);

  await d.click(page.locator('[data-tour="desk-tabs"] .ant-tabs-tab', { hasText: 'Ведомость' }), 'Переключитесь на раскладку «Ведомость»');

  const table = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Сводка по разработчикам' }) });
  await expect(table).toBeVisible();
  const devRow = table.locator(`tr[data-row-key="${devId}"]`);
  await expect(devRow).toBeVisible();

  const queueCell = devRow.locator('td', { hasText: 'к вып.' });
  await queueCell.hover();
  await d.caption('Колонка «Очередь» — сколько часов и дней висит на человеке');
  await d.show(queueCell);
  await d.pause(2600);

  // Подпись «к вып.» рендерится отдельным span внутри кликабельной строки —
  // точный узел вместо родительского div, который делят обе строки очереди.
  const assignedLine = devRow.locator('span.ant-typography', { hasText: 'к вып.' });
  await d.click(assignedLine, 'Нажмите «к вып.» у перегруженного разработчика');
  const activeFilters = page.locator('[data-tour="desk-flags"]', { hasText: 'ОТОБРАНО' });
  await expect(activeFilters).toBeVisible();
  await d.caption('«Отобрано» — видно, из каких задач сложилась очередь');
  await d.show(activeFilters);
  await d.pause(2200);

  const row = issuesBlock.locator(`tr[data-row-key="${issueId}"]`);
  await expect(row).toBeVisible();
  await d.show(row);
  await d.pause(1000);

  const parseHours = (text: string) => Number(text.match(/к вып\.\D*([\d.]+)\s*ч/)?.[1] ?? NaN);
  const hoursBefore = parseHours(await devRow.locator('td', { hasText: 'к вып.' }).innerText());

  const rateInput = row.locator('.ant-input-number-input');
  await d.type(rateInput, '2', 'Длинной задаче поставьте дневную норму');
  await page.keyboard.press('Tab');
  await d.pause(900);

  // У команды уже есть резиновые задачи — наша строка добавится ещё одной.
  const rubberCard = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Резиновые задачи' }) });
  await expect(rubberCard).toBeVisible();
  await d.caption('Задача помечена «резиновая» и попала в карточку «Резиновые задачи»');
  await d.show(rubberCard);
  await d.pause(2800);

  await table.scrollIntoViewIfNeeded();
  await expect(async () => {
    const text = await devRow.locator('td', { hasText: 'к вып.' }).innerText();
    expect(parseHours(text)).toBeLessThan(hoursBefore);
  }).toPass({ timeout: 10_000 });
  await d.caption('В ведомости очередь разработчика стала меньше');
  await d.show(devRow.locator('td', { hasText: 'к вып.' }));
  await d.pause(1400);

  const workloadCard = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Задач в работе одновременно' }) });
  await workloadCard.scrollIntoViewIfNeeded();
  await d.caption('«Задач в работе одновременно» — сколько человек держит в руках сразу');
  await d.show(workloadCard);
  await d.pause(3600);

  const filters = page.locator('[data-tour="desk-filters"]');
  await filters.scrollIntoViewIfNeeded();
  // Четвёртое поле шапки, по порядку: КОМАНДЫ, ОТДЕЛЬНЫЕ ЛЮДИ, СПРИНТ, РЕЛИЗ.
  const sprintSelect = filters.locator('.ant-select').nth(2);
  await d.click(sprintSelect, 'Можно сузить список одним спринтом');
  const sprintOption = page.locator('.ant-select-dropdown:visible .ant-select-item-option').first();
  await d.click(sprintOption);
  await page.keyboard.press('Escape');
  await page.mouse.move(700, 120);
  await d.pause(800);

  const columnsBtn = issuesBlock.getByRole('button', { name: 'Колонки' });
  await d.click(columnsBtn, '«Колонки» — что показывать в списке задач');
  const releaseItem = page.locator('.ant-dropdown-menu-item', { hasText: 'Релиз' });
  await d.click(releaseItem, 'Добавьте, например, колонку «Релиз»');
  await page.mouse.move(700, 120);
  await d.pause(700);

  await d.click(columnsBtn);
  await d.click(page.locator('.ant-dropdown-menu-item', { hasText: 'Релиз' }), 'И уберите её обратно, когда не нужна');
  await page.keyboard.press('Escape');
  await page.mouse.move(700, 120);
  await d.pause(600);

  const absences = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Отсутствия' }) });
  await absences.scrollIntoViewIfNeeded();
  await d.caption('Внизу — отсутствия команды: объясняют, почему свободных часов мало');
  await d.show(absences);
  await d.pause(2200);

  await d.caption('Готово', 4200);
  await d.pause(1200);
  await d.save('team-desk-queue');
});
