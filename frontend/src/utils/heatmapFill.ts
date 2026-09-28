import type { EmployeeLoadDay } from '../api/resourcePlanning';

/** Цвет часов, занятых планами других команд. */
export const EXT_LOAD_COLOR = 'hsl(265 55% 62%)';
/** Цвет прочих работ: доля дня вне задач по вовлечённости (90% → 10% дня). */
export const OTHER_WORK_COLOR = 'hsl(210 16% 52%)';
/** Свободная часть дня (как заливка свободного рабочего дня). */
export const FREE_FILL = 'rgba(255,255,255,0.06)';

/**
 * Заливка клетки дня: снизу — доля других команд, над ней — этот план
 * (цветом общей загрузки, чтобы перегруз краснел), выше — прочие работы,
 * сверху — свободно. Шкала — 100% или сумма, если перегруз.
 */
export function splitLoadFill(ownBg: string, pct: number, extPct: number, otherPct = 0): string {
  if (extPct <= 0 && otherPct <= 0) return ownBg;
  const scale = Math.max(pct + extPct + otherPct, 100);
  const e = Math.round((extPct / scale) * 100);
  const o = Math.round(((pct + extPct) / scale) * 100);
  const w = Math.round(((pct + extPct + otherPct) / scale) * 100);
  return `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 ${e}%, ${ownBg} ${e}% ${o}%, ${OTHER_WORK_COLOR} ${o}% ${w}%, ${FREE_FILL} ${w}% 100%)`;
}

/** Загрузка за период, % рабочего дня в среднем по рабочим дням. */
export interface QuarterLoad {
  own: number;
  ext: number;
  other: number;
  total: number;
  free: number;
}

/**
 * Средняя загрузка человека по рабочим дням (выходные, праздники, отпуск и
 * дни вне команды не считаются): этот план, планы других команд и прочие
 * работы. Итог считается до округления частей.
 */
export function quarterLoad(days: Pick<EmployeeLoadDay, 'pct' | 'ext_pct' | 'other_pct' | 'off'>[]): QuarterLoad {
  const work = days.filter((d) => !d.off);
  if (work.length === 0) return { own: 0, ext: 0, other: 0, total: 0, free: 0 };
  const avg = (f: (d: (typeof work)[number]) => number) => work.reduce((s, d) => s + f(d), 0) / work.length;
  const own = avg((d) => d.pct);
  const ext = avg((d) => d.ext_pct ?? 0);
  const other = avg((d) => d.other_pct ?? 0);
  const total = Math.round(own + ext + other);
  return { own: Math.round(own), ext: Math.round(ext), other: Math.round(other), total, free: Math.max(0, 100 - total) };
}
