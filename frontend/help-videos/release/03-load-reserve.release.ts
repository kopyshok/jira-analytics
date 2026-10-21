// Глава «Загрузка по дням и нормированные работы»: ресурсный план утверждённого
// сценария демо-команды в «Пульте» на широком экране → колонка сотрудников (имена,
// роли и проценты столбиком) → плашка нормированных работ во всю оставшуюся ширину:
// итог строкой и разбивка по видам работ, «сверх» красным → «Подробнее» — таблица по
// ролям в панели → щелчок по фазе — назначение в той же панели.
// Кадр шире обычного (2400×1350, в ролике уменьшен до 1920×1080): плашка нормированных
// работ раскрывает разбивку, только когда ей хватает места.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, saveClip } from './common.ts';

const TEAM = 'Команда Альфа';
const WIDE = { width: 2400, height: 1350 };

type Scenario = { id: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null; parent_plan_id: string | null };
type Gantt = { plan: { status: string }; stale_due_to_other_teams: boolean };

test.use({ viewport: WIDE, video: { mode: 'on', size: { width: 1920, height: 1080 } } });

let planId = '';

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
  expect((await request.put(`${api}/users/me/theme`, { data: { theme: 'pult-light' } })).ok()).toBeTruthy();
  expect(
    (await request.patch(`${rp}/preferences`, { data: { view_mode: 'tasks', collapsed_initiative_ids: [] } })).ok(),
  ).toBeTruthy();

  // План последнего утверждённого сценария команды.
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

  const gantt = await getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`);
  if (gantt.plan.status !== 'ready' || gantt.stale_due_to_other_teams) {
    expect((await request.post(`${rp}/resource-plans/${planId}/compute`)).ok()).toBeTruthy();
    await expect
      .poll(async () => (await getJson<Gantt>(`${rp}/resource-plans/${planId}/gantt`)).plan.status, { timeout: 60_000 })
      .toBe('ready');
  }
  await request.dispose();
});

test('03-load-reserve', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await page.addInitScript(() => localStorage.setItem('app_theme', 'pult-light'));
  await d.open(`/resource-planning?plan_id=${planId}`, chapterTitle('Загрузка по дням и нормированные работы'));

  const heat = page.locator('.rp-heat-module');
  await expect(heat.locator('[data-testid="rp-load-pct"]').first()).toBeVisible({ timeout: 60_000 });
  const types = page.locator('.rp-rs-types');
  await expect(types).toBeVisible();
  await page.mouse.move(1300, 600);
  await d.pause(2000);

  await d.caption('Внизу экрана — загрузка сотрудников по дням');
  await d.show(heat);
  await d.pause(2500);

  await d.caption('Имена целиком, роли и проценты загрузки — ровными столбцами');
  await d.show(heat.locator('.rp-heat-scroll'));
  await d.pause(3000);
  await d.waitVoice();

  const reserve = page.locator('.rp-reserve-sum');
  await d.caption('Загрузка — по ширине квартала, остальное место — нормированным работам');
  await d.show(reserve);
  await d.pause(3000);

  await d.caption('Итог одной строкой и разбивка по видам работ: занято, заложено, осталось');
  await d.show(types);
  await d.pause(3500);

  const over = page.locator('.rp-rs-t-over').filter({ hasText: 'сверх' }).first();
  if (await over.count()) {
    await d.caption('Где запас превышен — красным');
    await d.show(over);
    await d.pause(2500);
  }
  await d.waitVoice();

  await d.click(reserve.getByRole('button', { name: 'Подробнее' }), '«Подробнее» — полная таблица по ролям в панели');
  const sheet = page.locator('.detail-sheet');
  await expect(sheet).toBeVisible();
  await page.mouse.move(1300, 300);
  await d.pause(3500);
  await d.waitVoice();
  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  await d.pause(800);

  // Фаза своего плана (полосы «Наших людей в других командах» — только для просмотра).
  const bar = page.locator('.rp-bar[title^="Анализ"]').first();
  await d.click(bar, 'Щелчок по фазе на диаграмме — назначение в той же панели');
  await expect(page.locator('.rp-assign-sheet')).toBeVisible();
  await page.mouse.move(1300, 250);
  await d.pause(4000);
  await d.waitVoice();
  await page.keyboard.press('Escape');
  await d.pause(1500);
  await saveClip(d, '03-load-reserve');
});
