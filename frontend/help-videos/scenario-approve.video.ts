// Ролик «Как утвердить сценарий и что дальше»: черновик с отмеченными задачами
// (подготовлен в beforeAll) → «Утвердить» → заставка → задачи появились в
// «Целевых задачах» на вкладке «Активные» → «Диаграмма» открывает ресурсный
// план → «Распределить» → «В черновик» возвращает сценарий обратно.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

interface ScenarioListItem {
  year: number | null;
  quarter: string | null;
  team: string | null;
}
interface AllocationItem {
  id: string;
  jira_key: string | null;
  estimate_analyst_hours: number | null;
  estimate_dev_hours: number | null;
  estimate_qa_hours: number | null;
}

let scenarioId = '';
let freeYear = 0;
let freeQuarter = 0;
let includedIds: string[] = [];
let includedJiraKeys: string[] = [];

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string, params?: Record<string, string>): Promise<T> => {
    const res = await request.get(url, params ? { params } : undefined);
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Первый квартал, для которого у команды ещё нет сценария — детерминировано
  // в любой день, не зависит от состава демо-базы.
  const list = await getJson<ScenarioListItem[]>(`${api}/planning/scenarios`, { teams: TEAM });
  const keys = list
    .filter((s) => s.team === TEAM && s.year != null && s.quarter != null)
    .map((s) => (s.year as number) * 4 + (Number((s.quarter as string).replace('Q', '')) - 1));
  const now = new Date();
  const currentKey = now.getFullYear() * 4 + Math.floor(now.getMonth() / 3);
  const nextKey = Math.max(currentKey, ...keys) + 1;
  freeYear = Math.floor(nextKey / 4);
  freeQuarter = (nextKey % 4) + 1;

  const created = await request.post(`${api}/planning/scenarios`, {
    data: { name: `${freeYear} Q${freeQuarter} ${TEAM}`, year: freeYear, quarter: freeQuarter, team: TEAM },
  });
  expect(created.ok()).toBeTruthy();
  scenarioId = (await created.json()).id;

  // Несколько задач из Jira — по ключу их легко найти потом на вкладке «Активные».
  const allocs = await getJson<AllocationItem[]>(`${api}/planning/scenarios/${scenarioId}/allocations`);
  const withJira = allocs
    .filter(
      (a) =>
        !!a.jira_key &&
        (a.estimate_analyst_hours ?? 0) + (a.estimate_dev_hours ?? 0) + (a.estimate_qa_hours ?? 0) > 0,
    )
    .slice(0, 3);
  expect(withJira.length, 'в бэклоге нет задач Jira с часами').toBeGreaterThan(0);
  for (const a of withJira) {
    const res = await request.patch(`${api}/planning/scenarios/${scenarioId}/allocations/${a.id}`, {
      data: { included: true, lift: true },
    });
    expect(res.ok()).toBeTruthy();
  }
  includedIds = withJira.map((a) => a.id);
  includedJiraKeys = withJira.map((a) => a.jira_key!);

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (scenarioId) {
    // Утверждённый лишний сценарий команды ломает ролики ресурсного планирования —
    // возвращаем в черновик (если тест упал до этого шага) и удаляем целиком.
    const res = await request.get(`${api}/planning/scenarios/${scenarioId}`);
    if (res.ok()) {
      const s: { status: string } = await res.json();
      if (s.status === 'approved') {
        await request.post(`${api}/planning/scenarios/${scenarioId}/revert-to-draft`);
      }
    }
    await request.delete(`${api}/planning/scenarios/${scenarioId}`);
  }
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.dispose();
});

test('scenario-approve', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open(`/planning?scenario=${scenarioId}`, 'Как утвердить сценарий и что дальше');
  await expect(page.getByText('Черновик')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(new RegExp(`включено ${includedIds.length} из`))).toBeVisible();
  await d.pause(1000);
  await d.poster();
  await d.pause(1700);

  const firstIncludedRow = page.locator(`[data-flip-wrapper][data-alloc-id="${includedIds[0]}"] .backlog-row`);
  await d.caption('В сценарии уже отмечены несколько задач квартала');
  await d.show(firstIncludedRow);
  await d.pause(2000);

  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  await d.caption('Ресурс под них уже посчитан');
  await d.show(roleCard);
  await d.pause(1800);

  // === Утвердить ===
  await d.click(page.locator('[data-tour="planning-approve"]'), 'Нажмите «Утвердить»');
  const celebration = page.locator('[data-testid="approve-celebration"]');
  await expect(celebration).toBeVisible({ timeout: 15_000 });
  await d.caption('Сценарий утверждён');
  await d.pause(1700);
  await expect(celebration).toBeHidden({ timeout: 5_000 });
  const statusBadge = page.locator('.ant-badge-status-text', { hasText: 'Утверждён' });
  await expect(statusBadge).toBeVisible();

  await d.caption('Статус сменился, отметки и исполнители заблокированы');
  await d.show(statusBadge, page.getByText('сценарий утверждён — отметки заблокированы'));
  await d.pause(1800);

  // === «Целевые задачи» → «Активные» ===
  await d.caption('Утверждение переносит задачи в «Активные»');
  await d.pause(900);
  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }), 'Откройте «Целевые задачи»');
  await expect(page).toHaveURL(/\/backlog/);
  const activeTab = page.getByRole('tab', { name: /Активные/ });
  await expect(activeTab).toHaveAttribute('aria-selected', 'true', { timeout: 15_000 });

  const activeRow = page.getByText(includedJiraKeys[0], { exact: true }).first();
  await expect(activeRow).toBeVisible({ timeout: 15_000 });
  await d.caption('Задачи сценария теперь здесь, на вкладке «Активные»');
  await d.show(activeRow);
  await d.pause(1800);

  if (includedJiraKeys[1]) {
    const secondRow = page.getByText(includedJiraKeys[1], { exact: true }).first();
    await d.caption('И остальные отмеченные задачи — тоже');
    await d.show(secondRow);
    await d.pause(1600);
  }

  // === Назад к сценарию → «Диаграмма» ===
  await d.caption('Вернёмся в сценарий');
  await d.waitVoice();
  await page.goBack();
  await expect(page.locator('[data-tour="planning-diagram"]')).toBeVisible({ timeout: 15_000 });
  await d.pause(900);

  await d.click(page.locator('[data-tour="planning-diagram"]'), 'Кнопка «Диаграмма» открывает ресурсный план');
  await expect(page).toHaveURL(/\/resource-planning/);
  await expect(page.locator('[data-tour="rp-gantt"]')).toBeVisible({ timeout: 20_000 });
  await d.pause(900);

  await d.caption('План создан, но фазы пока не расставлены');
  await d.show(page.locator('[data-tour="rp-distribute"]'));
  await d.pause(1400);

  await d.click(page.locator('[data-tour="rp-distribute"]'), 'Нажмите «Распределить»');
  await expect(page.getByText('Расписание рассчитано')).toBeVisible({ timeout: 30_000 });
  await d.caption('Расписание рассчитано — фазы расставлены по людям');
  await d.show(page.locator('[data-tour="rp-gantt"]'));
  await d.pause(2400);

  const firstDevPhase = page.locator('[data-gantt-row="true"]', { hasText: 'Разработка' }).first();
  await d.caption('У каждой фазы — свой исполнитель и даты');
  await d.show(firstDevPhase);
  await d.pause(2000);

  const loadPanel = page.locator('[data-tour="rp-load"]');
  await d.caption('Ниже видно, кто и насколько загружен по дням');
  await d.show(loadPanel);
  await d.pause(1800);

  // === Назад к сценарию → «В черновик» ===
  await d.waitVoice();
  await page.goBack();
  await expect(page.locator('[data-tour="planning-revert"]')).toBeVisible({ timeout: 15_000 });
  await d.pause(900);

  await d.click(page.locator('[data-tour="planning-revert"]'), 'Если нужно поправить — «В черновик» вернёт сценарий');
  await expect(page.locator('.ant-badge-status-text', { hasText: 'Черновик' })).toBeVisible({ timeout: 15_000 });
  await d.pause(1800);

  await d.caption('Готово', 2200);
  await d.save('scenario-approve');
});
