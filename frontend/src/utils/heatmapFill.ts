/** Цвет часов, занятых планами других команд. */
export const EXT_LOAD_COLOR = 'hsl(265 55% 62%)';
/** Свободная часть дня (как заливка свободного рабочего дня). */
export const FREE_FILL = 'rgba(255,255,255,0.06)';

/**
 * Заливка клетки дня: снизу — доля других команд, над ней — этот план
 * (цветом общей загрузки, чтобы перегруз краснел), сверху — свободно.
 * Шкала — 100% или сумма, если перегруз.
 */
export function splitLoadFill(ownBg: string, pct: number, extPct: number): string {
  if (extPct <= 0) return ownBg;
  const scale = Math.max(pct + extPct, 100);
  const e = Math.round((extPct / scale) * 100);
  const o = Math.round(((pct + extPct) / scale) * 100);
  return `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 ${e}%, ${ownBg} ${e}% ${o}%, ${FREE_FILL} ${o}% 100%)`;
}
