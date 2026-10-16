import type { AppearanceSettings } from '../../api/appearance';
import { DEFAULT_APPEARANCE } from '../../contexts/appearanceDefaults';

/** Цвета фаз скина: спокойные насыщенные, белые часы на полосе читаются. */
export const ZONES_PHASE_COLORS: AppearanceSettings['phase_colors'] = {
  analyst: '#0F7F8C',
  dev: '#2F5FD0',
  qa: '#B85C00',
  opo: '#7A45B8',
};

/**
 * Цвета пользователя из «Вида → Цвета» остаются его; заводские неоновые цвета
 * фаз в скине заменяются спокойными.
 */
export function zonesAppearance(a: AppearanceSettings): AppearanceSettings {
  const phase_colors = { ...a.phase_colors };
  (Object.keys(phase_colors) as (keyof typeof phase_colors)[]).forEach((k) => {
    if (phase_colors[k].toLowerCase() === DEFAULT_APPEARANCE.phase_colors[k].toLowerCase()) {
      phase_colors[k] = ZONES_PHASE_COLORS[k];
    }
  });
  return { ...a, phase_colors };
}
