import { api } from './client';

export interface ExecutiveKpi {
  health_index: number;
  resource_utilization_pct: number;
  critical_risks_count: number;
  scenario_plan_fact_pct: number;
}

export interface ExecutiveModule {
  name: string;
  health: 'green' | 'yellow' | 'red';
  risk: string;
  load: string;
  note: string;
}

export interface ExecutiveQueue {
  name: string;
  critical: number;
  high: number;
  normal: number;
}

export interface ExecutiveTrendPoint {
  w: string;
  value: number;
}

export interface ExecutiveHoursTrend {
  w: string;
  incidents: number;
  improvements: number;
  consultations: number;
  regulatory: number;
}

export interface ExecutivePlanFact {
  role: string;
  plan: number;
  fact: number;
}

export interface ExecutiveRisk {
  title: string;
  impact: string;
  owner: string;
  action: string;
  level: 'red' | 'yellow' | 'green';
  key?: string;
}

export interface ExecutiveCapacity {
  role: string;
  utilization_pct: number;
}

export interface ExecutiveAiSummary {
  improved: string;
  risk: string;
  action: string;
  is_fallback: boolean;
}

export interface ExecutiveDashboardData {
  period: { year: number; quarter: number; start: string; end: string };
  kpi: ExecutiveKpi;
  health_trend: ExecutiveTrendPoint[];
  modules: ExecutiveModule[];
  queue: ExecutiveQueue[];
  hours_by_type_trend: ExecutiveHoursTrend[];
  plan_fact_by_role: ExecutivePlanFact[];
  top_risks: ExecutiveRisk[];
  capacity_by_role: ExecutiveCapacity[];
  ai_summary: ExecutiveAiSummary;
}

export interface ExecutiveDashboardResponse {
  year: number;
  quarter: number;
  team_set: string[];
  generated_at: string;
  model_id: string | null;
  prompt_version: string | null;
  data: ExecutiveDashboardData;
}

/** Backend returns `teams` as repeated query param. Pass them via URLSearchParams. */
function buildTeamsQuery(year: number, quarter: number, teams: string[]): string {
  const parts: string[] = [`year=${year}`, `quarter=${quarter}`];
  for (const t of teams) {
    parts.push(`teams=${encodeURIComponent(t)}`);
  }
  return parts.join('&');
}

/** GET — returns null if backend responded 404 (snapshot not built yet). */
export async function getDashboard(
  year: number,
  quarter: number,
  teams: string[],
  signal?: AbortSignal,
): Promise<ExecutiveDashboardResponse | null> {
  try {
    return await api.get<ExecutiveDashboardResponse>(
      `/executive/dashboard?${buildTeamsQuery(year, quarter, teams)}`,
      undefined,
      signal,
    );
  } catch (e) {
    const msg = (e as Error).message ?? '';
    // client throws Error(detail). Backend uses detail="Snapshot not built yet" on 404.
    if (msg.toLowerCase().includes('not built')) return null;
    throw e;
  }
}

/** POST — recompute snapshot (sync, ~3-10 sec). */
export async function buildDashboard(
  year: number,
  quarter: number,
  teams: string[],
): Promise<ExecutiveDashboardResponse> {
  return api.post<ExecutiveDashboardResponse>('/executive/dashboard/build', {
    year,
    quarter,
    teams,
  });
}
