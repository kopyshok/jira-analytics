import type { TimelineRow } from '../../../types/projects';

/** Цвет полосы фазы на таймлайне проекта (обложка задаёт свои через переменные). */
export const PHASE_COLOR: Record<string, string> = {
  analyst: 'var(--wt-analyst, #00c9c8)',
  cons: 'var(--wt-analyst, #00c9c8)',
  dev: 'var(--wt-dev, #378ADD)',
  qa: 'var(--wt-qa, #EF9F27)',
  opo: 'var(--wt-opo, #7F77DD)',
};

/** Порядок фаз в легенде — по ходу работ. */
const PHASE_ORDER = ['analyst', 'cons', 'dev', 'qa', 'opo'];

export interface LegendPhase {
  code: string;
  label: string;
  color: string;
}

/**
 * Фазы для легенды — только те, полосы которых есть на шкале. Например, ОПЭ,
 * выключенная с квартала, в легенду не попадает. Подпись — как у полосы.
 */
export function legendPhases(rows: TimelineRow[], fallbackColor = '#00c9c8'): LegendPhase[] {
  const labels = new Map<string, string>();
  for (const r of rows) {
    for (const b of r.bars) {
      if (!labels.has(b.phase)) labels.set(b.phase, b.label);
    }
  }
  const rank = (code: string) => {
    const i = PHASE_ORDER.indexOf(code);
    return i === -1 ? PHASE_ORDER.length : i;
  };
  return [...labels.keys()]
    .sort((a, b) => rank(a) - rank(b))
    .map((code) => ({ code, label: labels.get(code)!, color: PHASE_COLOR[code] ?? fallbackColor }));
}
