/** Настройки панели подробностей: место и размер, сохранённые в браузере. */

export type Placement = 'bottom' | 'right';

export interface Prefs {
  placement: Placement;
  /** Доли окна: высота листа снизу и ширина панели справа. */
  bottom: number;
  right: number;
}

const STORAGE_KEY = 'detail-sheet';
const DEFAULTS: Prefs = { placement: 'bottom', bottom: 0.55, right: 0.5 };
const LIMITS: Record<Placement, [number, number]> = { bottom: [0.3, 0.9], right: [0.3, 0.8] };

export const clamp = (p: Placement, v: number) => Math.min(LIMITS[p][1], Math.max(LIMITS[p][0], v));

/** Сохранённые настройки → безопасные значения (мусор и выход за пределы — по умолчанию / к границе). */
export function parsePrefs(raw: string | null): Prefs {
  try {
    const saved = JSON.parse(raw ?? 'null') as Partial<Prefs> | null;
    if (!saved || typeof saved !== 'object') return DEFAULTS;
    return {
      placement: saved.placement === 'right' ? 'right' : 'bottom',
      bottom: clamp('bottom', Number(saved.bottom) || DEFAULTS.bottom),
      right: clamp('right', Number(saved.right) || DEFAULTS.right),
    };
  } catch {
    return DEFAULTS;
  }
}

export function loadPrefs(): Prefs {
  try {
    return parsePrefs(localStorage.getItem(STORAGE_KEY));
  } catch {
    return DEFAULTS;
  }
}

export function savePrefs(p: Prefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* приватное окно — живём без памяти */
  }
}
