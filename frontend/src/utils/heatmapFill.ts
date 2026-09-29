/** Цвет часов, занятых планами других команд. */
export const EXT_LOAD_COLOR = 'hsl(265 55% 62%)';
/** Цвет нормированных работ: заблокированные периоды и запас квартала на свободное время. */
export const NORMED_WORK_COLOR = 'hsl(210 16% 52%)';
/** Свободная часть дня (как заливка свободного рабочего дня). */
export const FREE_FILL = 'rgba(255,255,255,0.06)';

/**
 * Заливка клетки дня: снизу — доля других команд, над ней — этот план
 * (цветом общей загрузки, чтобы перегруз краснел), выше — нормированные
 * работы, сверху — свободно. Шкала — 100% или сумма, если перегруз.
 */
export function splitLoadFill(ownBg: string, pct: number, extPct: number, normedPct = 0): string {
  if (extPct <= 0 && normedPct <= 0) return ownBg;
  const scale = Math.max(pct + extPct + normedPct, 100);
  const e = Math.round((extPct / scale) * 100);
  const o = Math.round(((pct + extPct) / scale) * 100);
  const w = Math.round(((pct + extPct + normedPct) / scale) * 100);
  return `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 ${e}%, ${ownBg} ${e}% ${o}%, ${NORMED_WORK_COLOR} ${o}% ${w}%, ${FREE_FILL} ${w}% 100%)`;
}
