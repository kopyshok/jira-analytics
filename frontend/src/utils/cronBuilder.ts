export type ScheduleType =
  | 'every_minutes'
  | 'every_hours'
  | 'daily'
  | 'weekdays'
  | 'weekends'
  | 'specific_days'
  | 'weekly'
  | 'cron';

export interface ScheduleForm {
  type: ScheduleType;
  minutes?: number;
  hours?: number;
  time?: string;
  days?: number[];
  day?: number;
  cron?: string;
}

const MINUTE_DIVISORS = [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30];
const HOUR_DIVISORS = [1, 2, 3, 4, 6, 8, 12];

export const MINUTE_OPTIONS = MINUTE_DIVISORS;
export const HOUR_OPTIONS = HOUR_DIVISORS;

const DAY_LABELS_RU = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
// UI индекс (0=пн..6=вс) → cron индекс (0=вс,1=пн..6=сб)
const UI_TO_CRON_DAY = [1, 2, 3, 4, 5, 6, 0];
const CRON_TO_UI_DAY: Record<number, number> = {
  0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5,
};

export const DAY_OPTIONS = DAY_LABELS_RU.map((label, value) => ({ value, label }));

function parseTime(time: string): [number, number] {
  const [h, m] = time.split(':').map(Number);
  return [h, m];
}

export function buildCron(form: ScheduleForm): string {
  switch (form.type) {
    case 'every_minutes': {
      const n = form.minutes ?? 5;
      return `*/${n} * * * *`;
    }
    case 'every_hours': {
      const n = form.hours ?? 1;
      return `0 */${n} * * *`;
    }
    case 'daily': {
      const [h, m] = parseTime(form.time ?? '06:00');
      return `${m} ${h} * * *`;
    }
    case 'weekdays': {
      const [h, m] = parseTime(form.time ?? '09:00');
      return `${m} ${h} * * 1-5`;
    }
    case 'weekends': {
      const [h, m] = parseTime(form.time ?? '10:00');
      return `${m} ${h} * * 0,6`;
    }
    case 'specific_days': {
      const [h, m] = parseTime(form.time ?? '09:00');
      const cronDays = (form.days ?? [])
        .map((uiDay) => UI_TO_CRON_DAY[uiDay])
        .sort((a, b) => a - b)
        .join(',');
      return `${m} ${h} * * ${cronDays}`;
    }
    case 'weekly': {
      const [h, m] = parseTime(form.time ?? '09:00');
      const uiDay = form.day ?? 0;
      return `${m} ${h} * * ${UI_TO_CRON_DAY[uiDay]}`;
    }
    case 'cron':
      return form.cron ?? '';
    default:
      return '';
  }
}

function parseDow(dow: string): number[] | null {
  if (dow === '*') return [0, 1, 2, 3, 4, 5, 6];
  if (dow.includes('-')) {
    const [a, b] = dow.split('-').map(Number);
    if (Number.isFinite(a) && Number.isFinite(b) && a <= b && a >= 0 && b <= 6) {
      const out: number[] = [];
      for (let i = a; i <= b; i += 1) out.push(i);
      return out;
    }
    return null;
  }
  if (dow.includes(',')) {
    const nums = dow.split(',').map(Number);
    if (nums.every((n) => Number.isFinite(n) && n >= 0 && n <= 6)) return nums;
    return null;
  }
  const n = Number(dow);
  if (Number.isFinite(n) && n >= 0 && n <= 6) return [n];
  return null;
}

export function parseCron(cron: string): ScheduleForm {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return { type: 'cron', cron };
  const [minute, hour, dom, month, dow] = parts;

  // */N * * * *
  if (month === '*' && dom === '*' && dow === '*' && hour === '*') {
    const m = /^\*\/(\d+)$/.exec(minute);
    if (m) {
      const n = Number(m[1]);
      if (MINUTE_DIVISORS.includes(n)) return { type: 'every_minutes', minutes: n };
    }
  }

  // 0 */N * * *
  if (month === '*' && dom === '*' && dow === '*' && minute === '0') {
    const m = /^\*\/(\d+)$/.exec(hour);
    if (m) {
      const n = Number(m[1]);
      if (HOUR_DIVISORS.includes(n)) return { type: 'every_hours', hours: n };
    }
  }

  // M H * * dow
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && month === '*' && dom === '*') {
    const h = Number(hour);
    const m = Number(minute);
    const time = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;

    if (dow === '*') return { type: 'daily', time };

    const days = parseDow(dow);
    if (days === null) return { type: 'cron', cron };

    const eq = (a: number[], b: number[]) =>
      a.length === b.length && a.every((x, i) => x === b[i]);

    const sorted = [...days].sort((a, b) => a - b);
    if (eq(sorted, [1, 2, 3, 4, 5])) return { type: 'weekdays', time };
    if (eq(sorted, [0, 6])) return { type: 'weekends', time };
    if (sorted.length === 1) {
      const uiDay = CRON_TO_UI_DAY[sorted[0]];
      return { type: 'weekly', day: uiDay, time };
    }
    const uiDays = sorted.map((d) => CRON_TO_UI_DAY[d]).sort((a, b) => a - b);
    return { type: 'specific_days', days: uiDays, time };
  }

  return { type: 'cron', cron };
}
