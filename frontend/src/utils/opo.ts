export const OPO_COLOR = '#7F77DD';
export const OPO_LABEL = 'Запуск (ОПЭ)';
export const OPO_SHORT = 'ОПЭ';

/** Отсечка ОПЭ: с этого квартала этап не планируется. Значение вида «2026Q4». */
export type OpoCutoff = string | null | undefined;

export function parseOpoCutoff(value: OpoCutoff): { year: number; quarter: number } | null {
  const m = /^(\d{4})Q([1-4])$/.exec((value ?? '').trim().toUpperCase());
  return m ? { year: Number(m[1]), quarter: Number(m[2]) } : null;
}

export function isOpoOff(
  cutoff: OpoCutoff,
  year: number | null | undefined,
  quarter: number | string | null | undefined,
): boolean {
  const c = parseOpoCutoff(cutoff);
  const q = Number(String(quarter ?? '').toUpperCase().replace('Q', ''));
  if (!c || !year || !q) return false;
  return year > c.year || (year === c.year && q >= c.quarter);
}

type OpoHours = { analyst: number; dev: number; qa: number; opo: number };

/** Влить часы ОПЭ в анализ и разработку по доле аналитика (по умолчанию поровну). */
export function foldOpo(h: OpoHours, ratio: number | null | undefined): OpoHours {
  const r = ratio ?? 0.5;
  return {
    analyst: h.analyst + h.opo * r,
    dev: h.dev + h.opo * (1 - r),
    qa: h.qa,
    opo: 0,
  };
}
