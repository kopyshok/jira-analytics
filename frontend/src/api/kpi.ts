import { api } from './client';

// === Отчёт «Ведомость» ===

export interface KpiMetricValue {
  code: string;
  name: string;
  weight: number;
  value: number | null;
  has_data: boolean;
  numerator: number | null;
  denominator: number | null;
}

export interface KpiReportRow {
  employee_id: string;
  employee_name: string;
  account_id: string;
  team: string | null;
  profile_code: string | null;
  /** Человекочитаемое название профиля оценки — показывать вместо
   * технического кода (латиницей), см. ревью, мелочи. */
  profile_name: string | null;
  target_pct: number | null;
  warn_band_pct: number | null;
  metrics: KpiMetricValue[];
  total: number | null;
  /** Применённая политика при отсутствии данных метрики — сервер сам решает,
   * какая из трёх настроена (админ видит общие правила, остальные роли —
   * нет), поэтому фронт не может считать её всегда «перераспределить». */
  empty_policy: 'redistribute' | 'full' | 'zero';
}

export interface KpiNoDataMetric {
  code: string;
  name: string;
  count: number;
}

export interface KpiReportSummary {
  avg_total: number | null;
  below_target_count: number;
  no_data_metrics_count: number;
  /** Разбор пустых клеток по метрикам — «25 без данных» само по себе ни о чём не говорит. */
  no_data_by_metric: KpiNoDataMetric[];
}

export interface KpiTeamApproval {
  approved: boolean;
  approved_by: string | null;
  approved_at: string | null;
}

export interface KpiReport {
  year: number;
  month: number;
  teams: string[];
  rows: KpiReportRow[];
  summary: KpiReportSummary;
  approvals: Record<string, KpiTeamApproval>;
  /** Сколько человек команды не оценивается: их роль не привязана ни к одному профилю. */
  skipped_no_profile: number;
}

export interface KpiTeamSummaryMetric {
  code: string;
  name: string;
  value: number | null;
  has_data: boolean;
}

export interface KpiTeamSummaryRow {
  team: string | null;
  member_count: number;
  avg_total: number | null;
  below_target_count: number;
  no_data_metrics_count: number;
  delta: number | null;
  target_pct: number | null;
  warn_band_pct: number | null;
  metrics: KpiTeamSummaryMetric[];
  /** Норматив Cycle Time на квартал; без него метрика пуста у всей команды. */
  cycle_time_norm: number | null;
}

export interface KpiTeamsSummary {
  year: number;
  month: number;
  rows: KpiTeamSummaryRow[];
}

export interface KpiReportFilters {
  year: number;
  month: number;
  teams?: string;
  direction?: string;
}

export const fetchKpiReport = (
  { year, month, teams, direction }: KpiReportFilters,
  signal?: AbortSignal,
) =>
  api.get<KpiReport>(
    '/kpi/report',
    { year: String(year), month: String(month), teams, direction },
    signal,
  );

export const fetchDirections = () => api.get<string[]>('/kpi/directions');

export const fetchTeamsSummary = (
  year: number,
  month: number,
  teams?: string,
  direction?: string,
  signal?: AbortSignal,
) =>
  api.get<KpiTeamsSummary>(
    '/kpi/teams-summary',
    { year: String(year), month: String(month), teams, direction },
    signal,
  );

// === Расшифровка метрики ===

export interface KpiIssueBrief {
  key: string;
  summary: string | null;
  status: string | null;
  resolution: string | null;
  url: string | null;
  /** Только для «норматив к факту» */
  fact?: number | null;
  /** Только для «средний балл к максимуму» */
  score?: number | null;
}

export interface KpiWorklogBrief {
  id: string;
  key: string | null;
  summary: string | null;
  started_at: string | null;
  jira_created_at: string | null;
  hours: number;
  late: boolean;
  url: string | null;
}

export type KpiBreakdownItem = KpiIssueBrief | KpiWorklogBrief;

export function isWorklogItem(item: KpiBreakdownItem): item is KpiWorklogBrief {
  return 'hours' in item;
}

/** Шаг воронки отбора: подпись условия, сколько осталось и сколько отсеяно. */
export interface KpiFunnelStep {
  label: string;
  remaining: number;
  dropped: number | null;
}

export interface KpiBreakdown {
  metric_code: string;
  metric_name: string;
  numerator: KpiBreakdownItem[];
  denominator: KpiBreakdownItem[];
  numerator_count: number;
  denominator_count: number;
  numerator_funnel: KpiFunnelStep[];
  denominator_funnel: KpiFunnelStep[];
}

export interface KpiBreakdownFilters {
  account_id: string;
  metric_code: string;
  year: number;
  month: number;
  teams?: string;
  direction?: string;
}

export const fetchBreakdown = (
  { account_id, metric_code, year, month, teams, direction }: KpiBreakdownFilters,
  signal?: AbortSignal,
) =>
  api.get<KpiBreakdown>(
    '/kpi/breakdown',
    {
      account_id, metric_code, year: String(year), month: String(month), teams, direction,
    },
    signal,
  );

// === Тренд сотрудника ===

export type KpiTrendPoint = KpiReportRow & { year: number; month: number; approved: boolean };

export interface KpiTrend {
  account_id: string;
  points: KpiTrendPoint[];
}

export interface KpiTrendFilters {
  account_id: string;
  year: number;
  month: number;
  months?: number;
  teams?: string;
  direction?: string;
}

export const fetchTrend = (
  { account_id, year, month, months, teams, direction }: KpiTrendFilters,
  signal?: AbortSignal,
) =>
  api.get<KpiTrend>(
    '/kpi/trend',
    {
      account_id, year: String(year), month: String(month),
      months: months ? String(months) : undefined, teams, direction,
    },
    signal,
  );

// === Утверждение месяца ===

export interface KpiApproval {
  team: string;
  year: number;
  month: number;
  approved: boolean;
  approved_by: string | null;
  approved_at: string | null;
}

export const approveMonth = (body: { team: string; year: number; month: number }) =>
  api.post<KpiApproval>('/kpi/approve', body);

export const fetchApproval = (team: string, year: number, month: number, signal?: AbortSignal) =>
  api.get<KpiApproval>(
    '/kpi/approval',
    { team, year: String(year), month: String(month) },
    signal,
  );

// === Выгрузка ===

export const downloadKpiExport = (
  { year, month, teams, direction }: KpiReportFilters,
  filename: string,
) =>
  api.download(
    '/kpi/export.xlsx',
    { year: String(year), month: String(month), teams, direction },
    filename,
  );

// === Справочники (настройки, admin-only) ===

export interface KpiCondition {
  attr: string;
  op: string;
  value: unknown;
}

export interface KpiConditionSet {
  unit: string;
  person_field: string;
  period_window: string;
  conditions: KpiCondition[];
}

export interface KpiMetricPayload {
  code: string;
  name: string;
  description?: string | null;
  calc_kind: string;
  numerator: KpiConditionSet;
  denominator?: KpiConditionSet | null;
  fact_field?: string | null;
  score_fields?: string[] | null;
  score_max?: number | null;
  invert: boolean;
  cap_at_100: boolean;
  sort_order: number;
}

export interface KpiMetricDef extends KpiMetricPayload {
  id: string;
  is_builtin: boolean;
}

export const fetchMetrics = () => api.get<KpiMetricDef[]>('/kpi-settings/metrics');

export const createMetric = (body: KpiMetricPayload) =>
  api.post<KpiMetricDef>('/kpi-settings/metrics', body);

export const updateMetric = (id: string, body: KpiMetricPayload) =>
  api.put<KpiMetricDef>(`/kpi-settings/metrics/${id}`, body);

export const deleteMetric = (id: string) =>
  api.del<{ status: string }>(`/kpi-settings/metrics/${id}`);

export interface KpiProfileMetricPayload {
  metric_code: string;
  weight: number;
  sort_order: number;
}

export interface KpiProfileMetricDef {
  metric_code: string;
  metric_name: string;
  weight: number;
  sort_order: number;
}

export interface KpiProfilePayload {
  code: string;
  name: string;
  /** Роли, которые оценивает профиль. Одна роль — не более чем в одном профиле. */
  role_codes: string[];
  target_pct: number;
  warn_band_pct: number;
  is_enabled: boolean;
  metrics: KpiProfileMetricPayload[];
}

export interface KpiProfileDef {
  id: string;
  code: string;
  name: string;
  role_codes: string[];
  target_pct: number;
  warn_band_pct: number;
  is_enabled: boolean;
  metrics: KpiProfileMetricDef[];
}

export interface KpiCoverageRow {
  role_code: string | null;
  role_label: string;
  employee_count: number;
  profile_code: string | null;
  profile_name: string | null;
}

export interface KpiCoverage {
  rows: KpiCoverageRow[];
  evaluated_count: number;
  total_count: number;
}

export const fetchCoverage = () =>
  api.get<KpiCoverage>('/kpi-settings/profiles/coverage');

export const fetchProfiles = () => api.get<KpiProfileDef[]>('/kpi-settings/profiles');

export const createProfile = (body: KpiProfilePayload) =>
  api.post<KpiProfileDef>('/kpi-settings/profiles', body);

export const updateProfile = (id: string, body: KpiProfilePayload) =>
  api.put<KpiProfileDef>(`/kpi-settings/profiles/${id}`, body);

export const deleteProfile = (id: string) =>
  api.del<{ status: string }>(`/kpi-settings/profiles/${id}`);

export interface KpiNormDef {
  id: string;
  team: string;
  year: number;
  quarter: number;
  norm_value: number;
}

export interface KpiNormPayload {
  team: string;
  year: number;
  quarter: number;
  /** ``null`` очищает норматив (удаляет строку на сервере) — см. ревью, ВАЖНО 10. */
  norm_value: number | null;
}

export const fetchNorms = (year?: number, quarter?: number) =>
  api.get<KpiNormDef[]>('/kpi-settings/norms', {
    year: year ? String(year) : undefined,
    quarter: quarter ? String(quarter) : undefined,
  });

export const saveNorms = (items: KpiNormPayload[]) =>
  api.put<KpiNormDef[]>('/kpi-settings/norms', items);

export type KpiDeadlineMode = 'hours_from_start' | 'calendar';

export interface KpiGeneralSettings {
  excluded_statuses: string[];
  /** «Часов от времени работы» (по ТЗ) или «рабочие дни и время отсечки». */
  worklog_deadline_mode: KpiDeadlineMode;
  worklog_deadline_hours: number;
  worklog_deadline_days: number;
  worklog_deadline_time: string;
  empty_policy: string;
}

export interface KpiDeadlineCompareRow {
  employee_name: string;
  worklog_count: number;
  hours_from_start: number | null;
  calendar: number | null;
}

export const fetchDeadlineCompare = (team: string, year: number, month: number) =>
  api.get<{ rows: KpiDeadlineCompareRow[] }>('/kpi-settings/worklog-deadline/compare', {
    team, year: String(year), month: String(month),
  });

export const fetchGeneral = () => api.get<KpiGeneralSettings>('/kpi-settings/general');

export const saveGeneral = (body: KpiGeneralSettings) =>
  api.put<KpiGeneralSettings>('/kpi-settings/general', body);

export interface KpiAttribute {
  key: string;
  label: string;
  value_type: 'list' | 'none' | string;
  choices?: string[];
}

export interface KpiFactField {
  key: string;
  label: string;
}

export interface KpiAttributesResponse {
  attributes: KpiAttribute[];
  person_fields: string[];
  period_windows: string[];
  fact_fields: KpiFactField[];
}

export const fetchAttributes = () => api.get<KpiAttributesResponse>('/kpi-settings/attributes');

// === Предпросмотр метрики (конструктор) ===

export interface KpiPreviewRow {
  employee_id: string;
  employee_name: string;
  account_id: string;
  numerator: number | null;
  denominator: number | null;
  value: number | null;
  has_data: boolean;
}

export interface KpiPreviewItems {
  numerator: KpiIssueBrief[];
  denominator: KpiIssueBrief[];
  numerator_count: number;
  denominator_count: number;
}

export interface KpiPreviewResult {
  metric_name: string;
  calc_kind: string;
  team: string;
  year: number;
  month: number;
  team_value: number | null;
  people_with_data: number;
  people_total: number;
  numerator_funnel: KpiFunnelStep[];
  denominator_funnel: KpiFunnelStep[];
  rows: KpiPreviewRow[];
  items: KpiPreviewItems;
}

export interface KpiPreviewRequest {
  metric: KpiMetricPayload;
  team: string;
  year: number;
  month: number;
  account_id?: string | null;
  direction?: string | null;
}

export const previewMetric = (body: KpiPreviewRequest) =>
  api.post<KpiPreviewResult>('/kpi-settings/metrics/preview', body);

export interface KpiExplainStep {
  label: string;
  passed: boolean;
}

export interface KpiExplainResult {
  found: boolean;
  issue_key: string;
  summary?: string | null;
  passed: boolean;
  failed_step: string | null;
  steps: KpiExplainStep[];
}

export const explainIssue = (body: KpiPreviewRequest & { issue_key: string; side: string }) =>
  api.post<KpiExplainResult>('/kpi-settings/metrics/explain-issue', body);
