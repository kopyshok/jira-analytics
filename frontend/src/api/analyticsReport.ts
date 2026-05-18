import { api } from './client';
import type { AnalyticsReportResponse, IssueWorklogItem } from '../types/api';

export interface AnalyticsReportParams {
  year: number;
  quarter: number;
  month?: number;
  start_date?: string;
  end_date?: string;
  teams?: string;
  employee_id?: string;
  task_query?: string;
  work_type_codes?: string;
  category_codes?: string;
}

export function fetchAnalyticsReport(p: AnalyticsReportParams, signal?: AbortSignal) {
  const params: Record<string, string | undefined> = {
    year: String(p.year),
    quarter: String(p.quarter),
    month: p.month !== undefined ? String(p.month) : undefined,
    start_date: p.start_date,
    end_date: p.end_date,
    teams: p.teams,
    employee_id: p.employee_id,
    task_query: p.task_query,
    work_type_codes: p.work_type_codes,
    category_codes: p.category_codes,
  };
  return api.get<AnalyticsReportResponse>('/analytics/report', params, signal);
}

export function fetchIssueWorklogs(issueId: string, start: string, end: string, signal?: AbortSignal) {
  return api.get<IssueWorklogItem[]>(
    `/analytics/report/issue/${issueId}/worklogs`, { start, end }, signal,
  );
}

export type AnalyticsLevel = 'team' | 'role' | 'employee' | 'work_type' | 'category' | 'issue';

export interface AnalyticsLayout {
  group_order?: AnalyticsLevel[];
  hidden_levels?: AnalyticsLevel[];
  active_preset?: string;
  saved_presets?: { name: string; group_order: AnalyticsLevel[]; hidden_levels: AnalyticsLevel[] }[];
}

export async function fetchAnalyticsLayout(): Promise<AnalyticsLayout> {
  const res = await api.get<{ layout: AnalyticsLayout }>('/users/me/analytics-layout');
  return res.layout ?? {};
}

export async function saveAnalyticsLayout(layout: AnalyticsLayout): Promise<void> {
  await api.put('/users/me/analytics-layout', { layout });
}
