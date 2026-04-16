import { api } from './client';

export const downloadAnalyticsXlsx = (start?: string, end?: string) =>
  api.download('/exports/analytics.xlsx', { start, end });

export const downloadAnalyticsPdf = (start?: string, end?: string) =>
  api.download('/exports/analytics.pdf', { start, end });

export const downloadScenarioXlsx = (scenarioId: string) =>
  api.download(`/exports/scenarios/${scenarioId}.xlsx`);

export const downloadScenarioPptx = (scenarioId: string) =>
  api.download(`/exports/scenarios/${scenarioId}.pptx`);
