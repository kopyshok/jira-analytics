// Ролик «Как утвердить сценарий»: черновик с включёнными инициативами
// (подготовлен через API) → «Утвердить» → статус меняется на «Утверждён».
import { expect, test, type Page } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

interface ScenarioListItem {
  year: number | null;
  quarter: string | null;
  team: string | null;
}

interface AllocationItem {
  id: string;
  estimate_analyst_hours: number | null;
  estimate_dev_hours: number | null;
  estimate_qa_hours: number | null;
}

/** Первый квартал, для которого у команды ещё нет сценария (не раньше текущего) —
 *  подготовка данных детерминирована в любой день. */
async function nextFreeQuarter(page: Page, api: string, team: string): Promise<{ year: number; quarter: number }> {
  const res = await page.request.get(`${api}/api/v1/planning/scenarios?teams=${encodeURIComponent(team)}`);
  expect(res.ok()).toBeTruthy();
  const list: ScenarioListItem[] = await res.json();
  const keys = list
    .filter((s) => s.team === team && s.year != null && s.quarter != null)
    .map((s) => (s.year as number) * 4 + (Number((s.quarter as string).replace('Q', '')) - 1));
  const now = new Date();
  const currentKey = now.getFullYear() * 4 + Math.floor(now.getMonth() / 3);
  const nextKey = Math.max(currentKey, ...keys) + 1;
  return { year: Math.floor(nextKey / 4), quarter: (nextKey % 4) + 1 };
}

test('scenario-approve', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = String(test.info().config.metadata.backendUrl);
  const { year, quarter } = await nextFreeQuarter(page, api, TEAM);

  // === Подготовка черновика через API: пара включённых инициатив ===
  const createRes = await page.request.post(`${api}/api/v1/planning/scenarios`, {
    data: { name: `${year} Q${quarter} ${TEAM}`, year, quarter, team: TEAM },
  });
  expect(createRes.ok()).toBeTruthy();
  const scenario: { id: string } = await createRes.json();
  const scenarioId = scenario.id;

  const allocsRes = await page.request.get(`${api}/api/v1/planning/scenarios/${scenarioId}/allocations`);
  expect(allocsRes.ok()).toBeTruthy();
  const allocs: AllocationItem[] = await allocsRes.json();
  const withHours = allocs
    .filter((a) => (a.estimate_analyst_hours ?? 0) + (a.estimate_dev_hours ?? 0) + (a.estimate_qa_hours ?? 0) > 0)
    .slice(0, 2);
  expect(withHours.length).toBeGreaterThan(0);
  for (const a of withHours) {
    const patchRes = await page.request.patch(
      `${api}/api/v1/planning/scenarios/${scenarioId}/allocations/${a.id}`,
      { data: { included: true, lift: true } },
    );
    expect(patchRes.ok()).toBeTruthy();
  }

  // === Съёмка ===
  await d.open(`/planning?scenario=${scenarioId}`, 'Как утвердить сценарий');
  await expect(page.getByText('Черновик')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(new RegExp(`включено ${withHours.length} из`))).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1200);

  const firstIncludedRow = page.locator(
    `[data-flip-wrapper][data-alloc-id="${withHours[0].id}"] .backlog-row`,
  );
  await d.caption('В сценарии уже отмечены инициативы квартала');
  await d.show(firstIncludedRow);
  await d.pause(1400);

  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  await d.caption('Ресурс под план уже посчитан');
  await d.show(roleCard);
  await d.pause(1400);

  const statusBadge = page.locator('.ant-badge-status-text', { hasText: 'Утверждён' });
  await d.click(page.locator('[data-tour="planning-approve"]'), 'Нажмите «Утвердить»');
  await expect(statusBadge).toBeVisible({ timeout: 15_000 });

  await d.caption('Статус сменился на «Утверждён»');
  await d.show(statusBadge);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('scenario-approve');
});
