import { DEFAULT_APPEARANCE } from '../../contexts/appearanceDefaults';
import { PHASE_COLORS } from '../../utils/gantt';

/** Цвет фазы для полос. Цвет по умолчанию отдаётся CSS-переменной (скин
 *  подставляет свою палитру), свой цвет из окна «Цвета» — как есть.
 *  Общий для полос диаграммы и легенды под ней. */
export function phaseFill(phase: string, color: string | undefined): string {
  const def = DEFAULT_APPEARANCE.phase_colors[phase as keyof typeof DEFAULT_APPEARANCE.phase_colors] ?? PHASE_COLORS[phase];
  const c = color ?? def;
  if (def && c.toLowerCase() === def.toLowerCase()) return `var(--rp-phase-${phase}, ${def})`;
  return c;
}
