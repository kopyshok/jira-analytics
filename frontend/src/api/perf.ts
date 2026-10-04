import { api } from './client';

export type PerfPeriod = '1h' | '24h' | '7d' | '30d';
export type PerfVerdict = 'other_load' | 'database' | 'our_code' | 'waiting';

export interface PerfSeriesPoint {
  t: string;
  requests: number;
  p95_ms: number | null;
  max_ms: number | null;
  slow: number;
  host_cpu: number | null;
  host_cpu_max: number | null;
  process_cpu: number | null;
  verdict: PerfVerdict | null;
  verdict_label: string | null;
}

export interface PerfBottleneck {
  method: string;
  route: string;
  section: string;
  calls: number;
  total_ms: number;
  avg_ms: number;
  p95_ms: number;
  max_ms: number;
  errors_5xx: number;
  db_avg_count: number;
  db_share: number;
}

export interface PerfSlowRequest {
  id: string;
  at: string;
  method: string;
  route: string;
  section: string;
  path: string;
  query: string;
  status_code: number;
  duration_ms: number;
  db_count: number;
  db_ms: number;
  cpu_ms: number;
  user: string | null;
  top_queries: { ms: number; sql: string }[];
  host_cpu: number | null;
  process_cpu: number | null;
  process_cpu_core: number | null;
  host_memory: number | null;
  process_memory_mb: number | null;
  threads: number | null;
  db_pool_in_use: number | null;
  db_pool_size: number | null;
  requests_in_flight: number | null;
  verdict: PerfVerdict;
  verdict_label: string;
  /** Цифра, которая решила вывод: «сервер загружен на 95%, наш сервис — 10%». */
  verdict_reason: string;
}

export interface PerfLoad {
  snapshots: number;
  host_cpu_avg: number;
  host_cpu_max: number;
  process_cpu_avg: number;
  process_cpu_max: number;
  host_memory_max: number;
  process_memory_mb_max: number;
  threads_max: number;
  db_pool_in_use_max: number | null;
  db_pool_size: number | null;
  requests_in_flight_max: number;
  busy_snapshots: number;
  busy_by_others_snapshots: number;
}

export interface PerfOverview {
  period: PerfPeriod;
  period_label: string;
  start: string;
  end: string;
  bucket_minutes: number;
  slow_ms: number;
  totals: {
    requests: number;
    slow: number;
    errors_5xx: number;
    avg_ms: number;
    p95_ms: number;
    max_ms: number;
  };
  verdicts: Partial<Record<PerfVerdict, number>>;
  verdict_labels: Record<PerfVerdict, string>;
  series: PerfSeriesPoint[];
  bottlenecks: PerfBottleneck[];
  slow: PerfSlowRequest[];
  load: PerfLoad | null;
}

/** Сдвиг местного времени от UTC в минутах — время в выгрузках по поясу браузера. */
const tzOffset = () => String(-new Date().getTimezoneOffset());

export const perfApi = {
  overview: (period: PerfPeriod) =>
    api.get<PerfOverview>('/admin/perf/overview', { period }),
  downloadReport: (period: PerfPeriod) =>
    api.download('/admin/perf/report.md', { period, tz_offset_min: tzOffset() },
      `Быстродействие_отчёт_${period}.md`),
  downloadXlsx: (period: PerfPeriod) =>
    api.download('/admin/perf/export.xlsx', { period, tz_offset_min: tzOffset() },
      `Быстродействие_${period}.xlsx`),
};
