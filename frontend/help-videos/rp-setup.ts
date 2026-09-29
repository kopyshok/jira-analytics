// Общая подготовка роликов «Ресурсного планирования» до первого кадра:
// команда в шапке — демо-команда, план последнего утверждённого сценария без
// ручных правок и заново рассчитан. Исходная картина одна и та же в любой день.
import { expect, type Page, test } from '@playwright/test';

export const TEAM = 'Команда Альфа';

export type Scenario = { id: string; name: string; quarter: string | null; year: number | null };
export type Plan = { id: string; scenario_id: string | null };
export type Assignment = {
  id: string;
  backlog_item_id: string;
  phase: string;
  part_number: number;
  employee_id: string | null;
  start_date: string | null;
  end_date: string | null;
};

export type PreparedPlan = {
  /** Адрес API бэкенда съёмки, например `http://127.0.0.1:8012/api/v1`. */
  api: string;
  /** `${api}/resource-planning`. */
  rp: string;
  scenario: Scenario;
  plan: Plan;
  assignments: Assignment[];
};

/**
 * Подготовить план квартала: вид «Задачи», все инициативы развёрнуты, ручные правки
 * сняты, план пересчитан. Возвращает план и его назначения (фазы) после расчёта.
 */
export async function prepareQuarterPlan(page: Page): Promise<PreparedPlan> {
  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  const prefs = await page.request.patch(`${rp}/preferences`, {
    data: { view_mode: 'tasks', hide_weekends: false, collapsed_initiative_ids: [] },
  });
  expect(prefs.ok()).toBeTruthy();

  const scenarios: Scenario[] = await (
    await page.request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } })
  ).json();
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  if (!scenario) throw new Error(`Нет утверждённых сценариев команды ${TEAM}`);

  const plans: Plan[] = await (await page.request.get(`${rp}/resource-plans`, { params: { team: TEAM } })).json();
  let plan = plans.find((p) => p.scenario_id === scenario.id);
  if (!plan) {
    const created = await page.request.post(`${rp}/resource-plans`, {
      data: { scenario_id: scenario.id, team: TEAM, quarter: scenario.quarter, year: scenario.year },
    });
    expect(created.ok()).toBeTruthy();
    plan = (await created.json()) as Plan;
  }
  expect((await page.request.post(`${rp}/resource-plans/${plan.id}/bulk-clear`, { data: { mode: 'all' } })).ok()).toBeTruthy();
  expect((await page.request.post(`${rp}/resource-plans/${plan.id}/compute`)).ok()).toBeTruthy();

  const { assignments }: { assignments: Assignment[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  return { api, rp, scenario, plan, assignments };
}

/** Полоса фазы на диаграмме (атрибут в GanttRows.tsx). */
export function phaseBar(page: Page, a: Pick<Assignment, 'backlog_item_id' | 'phase' | 'part_number'>) {
  return page.getByTestId(`rp-bar-${a.backlog_item_id}-${a.phase}-${a.part_number}`);
}
