import { effectiveEstimate } from './allocationEstimates';
import { foldOpo } from './opo';
import type { AllocationResponse } from '../types/api';

/** Состояние строки сценария для колонки «Состояние» (точка + подпись). */
export type ScenarioRowState = 'no-estimates' | 'deficit' | 'in-work' | 'included' | 'none';

const ROW_STATE_LABEL: Record<ScenarioRowState, string> = {
  'no-estimates': 'нет оценок',
  deficit: 'включено при дефиците',
  'in-work': 'уже в работе',
  included: 'включено',
  none: '—',
};

/**
 * Состояние строки из класса, который считает страница (нет оценок →
 * включено при дефиците → квартальная задача уже в работе), плюс простое
 * «включено» для остальных отмеченных.
 */
export function scenarioRowState(rowStateClass: string, included: boolean): { key: ScenarioRowState; label: string } {
  let key: ScenarioRowState = included ? 'included' : 'none';
  if (rowStateClass.includes('row-state-no-estimates')) key = 'no-estimates';
  else if (rowStateClass.includes('row-state-deficit')) key = 'deficit';
  else if (rowStateClass.includes('row-state-in-work')) key = 'in-work';
  return { key, label: ROW_STATE_LABEL[key] };
}

export type RoleHoursTotals = {
  analyst: number;
  dev: number;
  qa: number;
  opo: number;
  total: number;
  /** Сколько строк отмечено. */
  included: number;
};

/**
 * Часы по ролям у набора строк (оценка с учётом переоценки). С квартала
 * отсечки ОПЭ её часы уже внутри АН и ПР. `onlyIncluded` — считать часы
 * только отмеченных строк.
 */
export function roleHoursTotals(
  items: AllocationResponse[],
  opoOff: boolean,
  onlyIncluded = false,
): RoleHoursTotals {
  let analyst = 0;
  let dev = 0;
  let qa = 0;
  let opo = 0;
  let included = 0;
  for (const a of items) {
    if (a.included) included += 1;
    if (onlyIncluded && !a.included) continue;
    const raw = effectiveEstimate(a);
    const eff = opoOff ? foldOpo(raw, a.opo_analyst_ratio) : raw;
    analyst += eff.analyst;
    dev += eff.dev;
    qa += eff.qa;
    opo += eff.opo;
  }
  return { analyst, dev, qa, opo, included, total: analyst + dev + qa + opo };
}

/**
 * Полоса «план / доступно» с запасом шкалы: доступное стоит на отметке
 * 1/headroom ширины, поэтому перегруз виден правее отметки. Без доступного
 * отметки нет: полоса пустая, а если план есть — заполнена целиком (весь план — перегруз).
 */
export function capacityBar(demand: number, capacity: number, headroom: number) {
  if (capacity <= 0) {
    return { fillPct: demand > 0 ? 100 : 0, markerPct: null as number | null, over: demand > 0, loadPct: 0 };
  }
  const scale = capacity * headroom;
  return {
    fillPct: Math.min(100, (demand / scale) * 100),
    markerPct: 100 / headroom,
    over: demand > capacity,
    loadPct: Math.round((demand / capacity) * 100),
  };
}

/** Часы для таблицы: целые — как есть, дробные — до десятых; разряды пробелом. */
export function formatHours(h: number): string {
  return (Math.round(h * 10) / 10).toLocaleString('ru');
}

const ROLE_SHORT: Record<string, string> = {
  analyst: 'АН',
  dev: 'ПР',
  qa: 'ТС',
  RP: 'РП',
  project_manager: 'РП',
  consultant: 'КС',
};

/** Короткая подпись роли для пилюль «АН 95 ч»: свои коды — по таблице, прочие — две буквы названия. */
export function roleShortLabel(code: string, label: string | null | undefined): string {
  return ROLE_SHORT[code] ?? (label || code).slice(0, 2).toUpperCase();
}

/** Инициалы для аватара: «Иванов Сергей» → «ИС», одно слово — две первые буквы. */
export function personInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '—';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}
