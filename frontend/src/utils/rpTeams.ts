import type { DefaultOptionType } from 'antd/es/select';

// Ресурсное планирование при нескольких командах в шапке.

interface ScenarioLike {
  id: string;
  name: string;
  team: string | null;
  quarter: string | null;
  year: number | null;
}

/** Команда страницы: команда плана, иначе команда сценария из адреса, иначе первая команда шапки. */
export function resolvePageTeam(
  headerTeams: string[],
  planTeam: string | null | undefined,
  scenarioTeam: string | null | undefined,
): string {
  return planTeam || scenarioTeam || headerTeams[0] || '';
}

/** Выбранный план чужой для шапки (команду убрали) — выбор надо сбросить. */
export function isOutsideHeader(headerTeams: string[], planTeam: string | null | undefined): boolean {
  return headerTeams.length > 0 && !!planTeam && !headerTeams.includes(planTeam);
}

const optionOf = (s: ScenarioLike) => ({
  label: `${s.quarter ?? '—'} ${s.year ?? ''} — ${s.name}`,
  value: s.id,
});

/** Варианты списка «Сценарий»: одна команда — плоско, несколько — группы по командам в порядке шапки. */
export function groupScenarioOptions(scenarios: ScenarioLike[], headerTeams: string[]): DefaultOptionType[] {
  if (headerTeams.length <= 1) return scenarios.map(optionOf);
  return headerTeams
    .map(t => ({ label: t, options: scenarios.filter(s => s.team === t).map(optionOf) }))
    .filter(g => g.options.length > 0);
}

interface PlanLike {
  id: string;
  scenario_id: string | null;
}

type AutoPlanDecision =
  | { action: 'none' }
  | { action: 'select'; planId: string }
  | { action: 'create'; team: string; quarter: string; year: number };

/**
 * Что делать со сценарием из адреса: ничего (списки не загружены, сценария нет
 * среди утверждённых сценариев команд шапки), выбрать готовый план или создать
 * план в команде самого сценария.
 */
export function decideAutoPlan(args: {
  scenarioId: string | null;
  plansLoaded: boolean;
  scenariosLoaded: boolean;
  plans: PlanLike[];
  scenarios: ScenarioLike[];
  currentPlanId: string | null;
}): AutoPlanDecision {
  const { scenarioId, plansLoaded, scenariosLoaded, plans, scenarios, currentPlanId } = args;
  if (!scenarioId || !plansLoaded || !scenariosLoaded) return { action: 'none' };
  const current = currentPlanId ? plans.find(p => p.id === currentPlanId) : null;
  if (current && current.scenario_id === scenarioId) return { action: 'none' };
  const existing = plans.find(p => p.scenario_id === scenarioId);
  if (existing) return { action: 'select', planId: existing.id };
  const sc = scenarios.find(s => s.id === scenarioId);
  if (!sc || !sc.team || !sc.quarter || !sc.year) return { action: 'none' };
  return { action: 'create', team: sc.team, quarter: sc.quarter, year: sc.year };
}
