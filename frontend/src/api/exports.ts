import { api } from './client';

export const downloadScenarioXlsx = (scenarioId: string) =>
  api.download(`/exports/scenarios/${scenarioId}.xlsx`);

export const downloadScenarioPptx = (scenarioId: string) =>
  api.download(`/exports/scenarios/${scenarioId}.pptx`);
