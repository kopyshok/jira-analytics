export interface GanttTimeline {
  startDate: Date;
  endDate: Date;
  totalDays: number;
}

export function buildTimeline(startDate: Date, endDate: Date): GanttTimeline {
  const totalDays = Math.ceil((endDate.getTime() - startDate.getTime()) / 86_400_000) + 1;
  return { startDate, endDate, totalDays };
}

export function dateToLeft(dateStr: string, tl: GanttTimeline): number {
  const d = new Date(dateStr + 'T00:00:00');
  const offsetDays = (d.getTime() - tl.startDate.getTime()) / 86_400_000;
  return Math.max(0, (offsetDays / tl.totalDays) * 100);
}

export function datesToWidth(startStr: string, endStr: string, tl: GanttTimeline): number {
  const s = new Date(startStr + 'T00:00:00');
  const e = new Date(endStr + 'T00:00:00');
  const days = (e.getTime() - s.getTime()) / 86_400_000 + 1;
  return Math.max(0.5, (days / tl.totalDays) * 100);
}

export function quarterBounds(quarter: string, year: number): { start: Date; end: Date } {
  const q = parseInt(quarter.replace('Q', ''));
  const months: Record<number, [number, number]> = {
    1: [0, 2], 2: [3, 5], 3: [6, 8], 4: [9, 11],
  };
  const [startM, endM] = months[q] ?? [0, 2];
  const start = new Date(year, startM, 1);
  const end = new Date(year, endM + 1, 0);
  return { start, end };
}

export function getWeekLabels(tl: GanttTimeline): Array<{ label: string; leftPct: number; widthPct: number }> {
  const weeks: Array<{ label: string; leftPct: number; widthPct: number }> = [];
  const d = new Date(tl.startDate);
  const dow = d.getDay();
  if (dow !== 1) d.setDate(d.getDate() - ((dow + 6) % 7));

  let weekNum = 1;
  while (d <= tl.endDate) {
    const weekStart = new Date(d);
    const weekEnd = new Date(d);
    weekEnd.setDate(weekEnd.getDate() + 6);
    const clampedStart = weekStart < tl.startDate ? tl.startDate : weekStart;
    const clampedEnd = weekEnd > tl.endDate ? tl.endDate : weekEnd;
    const left = dateToLeft(clampedStart.toISOString().slice(0, 10), tl);
    const width = datesToWidth(clampedStart.toISOString().slice(0, 10), clampedEnd.toISOString().slice(0, 10), tl);
    weeks.push({ label: `W${weekNum}`, leftPct: left, widthPct: width });
    d.setDate(d.getDate() + 7);
    weekNum++;
  }
  return weeks;
}

const RU_MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

export type TimelineScale = 'day' | 'week' | 'month';

export function getDayLabels(tl: GanttTimeline): Array<{ label: string; leftPct: number; widthPct: number }> {
  const days: Array<{ label: string; leftPct: number; widthPct: number }> = [];
  const d = new Date(tl.startDate);
  while (d <= tl.endDate) {
    const dayEnd = new Date(d);
    const iso = d.toISOString().slice(0, 10);
    const isoEnd = dayEnd.toISOString().slice(0, 10);
    const left = dateToLeft(iso, tl);
    const width = datesToWidth(iso, isoEnd, tl);
    days.push({ label: String(d.getDate()), leftPct: left, widthPct: width });
    d.setDate(d.getDate() + 1);
  }
  return days;
}

export function getMonthLabels(tl: GanttTimeline): Array<{ label: string; leftPct: number; widthPct: number }> {
  const months: Array<{ label: string; leftPct: number; widthPct: number }> = [];
  let cursor = new Date(tl.startDate.getFullYear(), tl.startDate.getMonth(), 1);
  while (cursor <= tl.endDate) {
    const monthStart = cursor < tl.startDate ? tl.startDate : cursor;
    const next = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
    const monthEndExclusive = next > tl.endDate ? tl.endDate : new Date(next.getTime() - 86_400_000);
    const left = dateToLeft(monthStart.toISOString().slice(0, 10), tl);
    const width = datesToWidth(
      monthStart.toISOString().slice(0, 10),
      monthEndExclusive.toISOString().slice(0, 10),
      tl,
    );
    months.push({ label: RU_MONTHS[cursor.getMonth()], leftPct: left, widthPct: width });
    cursor = next;
  }
  return months;
}

export const PX_PER_DAY: Record<TimelineScale, number> = {
  day: 36,
  week: 14,
  month: 5,
};

export const PHASE_COLORS: Record<string, string> = {
  analyst: '#00c9c8',
  dev: '#2a7fbf',
  qa: '#e8864a',
  opo: '#52d364',
};

export const PHASE_LABELS: Record<string, string> = {
  analyst: 'Анализ',
  dev: 'Разработка',
  qa: 'Тестирование',
  opo: 'ОПЭ',
};

// Palette for coloring initiatives in Resource Track view (cycles when > 8 items)
export const ITEM_PALETTE = [
  '#2a7fbf',
  '#e8864a',
  '#52d364',
  '#d4567a',
  '#a36bdb',
  '#c8a82a',
  '#4ab8d4',
  '#d48b4a',
];

export function getItemColor(itemIndex: number): string {
  return ITEM_PALETTE[itemIndex % ITEM_PALETTE.length];
}
