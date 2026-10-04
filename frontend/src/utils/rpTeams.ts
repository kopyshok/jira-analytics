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
