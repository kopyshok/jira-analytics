import { api } from './client';

export interface QualityMetric {
  plan_id: string;
  overload_days_pct: number;
  late_count: number;
  mean_utilization_pct: number;
  computed_at: string;
}

export interface OptimizeResult {
  new_plan_id: string;
  before: QualityMetric;
  after: QualityMetric;
  solver_status: 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE';
  solve_time_ms: number;
  infeasible_items: string[];
}

export const resourcePlanningV2Api = {
  quality: (planId: string, signal?: AbortSignal) =>
    api.get<QualityMetric>(`/resource-planning-v2/${planId}/quality`, undefined, signal),
  optimize: (planId: string) =>
    api.post<OptimizeResult>(`/resource-planning-v2/${planId}/optimize`),
};
