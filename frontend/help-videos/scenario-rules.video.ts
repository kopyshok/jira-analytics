// Ролик «Как поправить нормированные работы»: черновик сценария (подготовлен
// через API) → вкладка «Правила» → поднять долю сопровождения у аналитика →
// сохранить → справа виден пересчитанный ресурс под инициативы.
import { expect, test, type Page } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

interface ScenarioListItem {
  year: number | null;
  quarter: string | null;
  team: string | null;
}

interface WorkTypeItem {
  id: string;
  label: string;
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

test('scenario-rules', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = String(test.info().config.metadata.backendUrl);
  const { year, quarter } = await nextFreeQuarter(page, api, TEAM);

  // === Подготовка черновика через API (от имени демо-пользователя) ===
  const createRes = await page.request.post(`${api}/api/v1/planning/scenarios`, {
    data: { name: `${year} Q${quarter} ${TEAM}`, year, quarter, team: TEAM },
  });
  expect(createRes.ok()).toBeTruthy();
  const scenario: { id: string } = await createRes.json();
  const scenarioId = scenario.id;

  const workTypesRes = await page.request.get(`${api}/api/v1/mandatory-work-types?is_active=true`);
  expect(workTypesRes.ok()).toBeTruthy();
  const workTypes: WorkTypeItem[] = await workTypesRes.json();
  expect(workTypes.length).toBeGreaterThan(0);
  const supportType = workTypes.find((w) => /сопровожд/i.test(w.label)) ?? workTypes[0];

  const rulesRes = await page.request.put(`${api}/api/v1/planning/scenarios/${scenarioId}/rules`, {
    data: { rules: [{ role: 'analyst', work_type_id: supportType.id, percent_of_norm: 30 }] },
  });
  expect(rulesRes.ok()).toBeTruthy();

  // Пара включённых инициатив — иначе панель ресурса пуста и правку не на чем показать.
  const allocsRes = await page.request.get(`${api}/api/v1/planning/scenarios/${scenarioId}/allocations`);
  expect(allocsRes.ok()).toBeTruthy();
  const allocs: AllocationItem[] = await allocsRes.json();
  const withHours = allocs
    .filter((a) => (a.estimate_analyst_hours ?? 0) + (a.estimate_dev_hours ?? 0) + (a.estimate_qa_hours ?? 0) > 0)
    .slice(0, 2);
  for (const a of withHours) {
    const patchRes = await page.request.patch(
      `${api}/api/v1/planning/scenarios/${scenarioId}/allocations/${a.id}`,
      { data: { included: true, lift: true } },
    );
    expect(patchRes.ok()).toBeTruthy();
  }

  // === Съёмка ===
  await d.open(`/planning?scenario=${scenarioId}`, 'Как поправить нормированные работы');
  await expect(page.getByText('Черновик')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[data-tour="planning-capacity-panel"]')).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1200);

  await d.click(page.locator('[data-tour="planning-tab-rules"]'), 'Откройте вкладку «Правила»');

  const rulesCard = page.locator('[data-tour="planning-rules-card"]');
  const row = rulesCard.locator('tbody tr.ant-table-row').first();
  await expect(row).toBeVisible();

  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  await d.caption('Справа — ресурс на инициативы до правки');
  await d.show(roleCard);
  await d.pause(1000);
  const beforeText = await roleCard.innerText();

  const percentInput = row.locator('.ant-input-number-input');
  await d.click(percentInput, 'Поднимите долю сопровождения у аналитика');
  await percentInput.press('Control+A');
  await percentInput.pressSequentially('70', { delay: 90 });
  await d.pause(400);

  await d.click(rulesCard.getByRole('button', { name: 'Сохранить' }), 'Сохраните правило');
  await expect(rulesCard.getByRole('button', { name: 'Сбросить' })).toHaveCount(0, { timeout: 10_000 });

  await d.caption('Ресурс под инициативы пересчитался');
  await d.show(roleCard);
  await d.pause(1600);
  await expect.poll(() => roleCard.innerText()).not.toBe(beforeText);

  await d.caption('Готово', 2200);
  await d.save('scenario-rules');
});
