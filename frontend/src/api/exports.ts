import { api } from './client';
import type { TeamFilterParams } from './analytics';

const boolParam = (v?: boolean): string | undefined => (v === undefined ? undefined : v ? 'true' : 'false');

export const downloadAnalyticsXlsx = (start?: string, end?: string, team?: TeamFilterParams) =>
  api.download('/exports/analytics.xlsx', {
    start, end,
    teams: team?.teams,
    match_employees: boolParam(team?.match_employees),
    match_issues: boolParam(team?.match_issues),
  });

export const downloadAnalyticsPdf = (start?: string, end?: string, team?: TeamFilterParams) =>
  api.download('/exports/analytics.pdf', {
    start, end,
    teams: team?.teams,
    match_employees: boolParam(team?.match_employees),
    match_issues: boolParam(team?.match_issues),
  });

export const downloadScenarioXlsx = (scenarioId: string) =>
  api.download(`/exports/scenarios/${scenarioId}.xlsx`);

export const downloadScenarioPptx = (scenarioId: string) =>
  api.download(`/exports/scenarios/${scenarioId}.pptx`);
