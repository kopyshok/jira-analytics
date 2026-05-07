/** Shared utilities for the work-type report components */

import type { Theme } from '../../types/workTypeReport';

export interface Slice {
  name: string;
  hours: number;
  pct: number;
  color: string;
}

const MAX_DONUT = 5;

/** Build pie/bar slices from themes, grouping tail into «Другое». */
export function buildSlices(themes: Theme[], totalHours: number, otherColor: string): Slice[] {
  const sorted = [...themes].sort((a, b) => b.totals.hours - a.totals.hours);
  const top = sorted.slice(0, MAX_DONUT);
  const rest = sorted.slice(MAX_DONUT);
  const slices: Slice[] = top.map((t) => ({
    name: t.name,
    hours: t.totals.hours,
    pct: t.totals.pct,
    color: t.color,
  }));
  if (rest.length > 0) {
    const otherHours = rest.reduce((s, t) => s + t.totals.hours, 0);
    const otherPct = totalHours > 0 ? (otherHours / totalHours) * 100 : 0;
    slices.push({ name: 'Другое', hours: otherHours, pct: otherPct, color: otherColor });
  }
  return slices;
}

/** Reason code → human-readable label */
export const REASON_LABELS: Record<string, string> = {
  high_hours: 'Часы выше нормы',
  many_reopens: 'Часто переоткрывалась',
  many_workers: 'Много исполнителей',
  stale: 'Долго без активности',
  // legacy codes in case snapshot was built with old detector
  hours_high: 'Часы выше нормы',
  reopen_count: 'Часто переоткрывалась',
  workers_many: 'Много исполнителей',
  stale_dormant: 'Долго без активности',
};
