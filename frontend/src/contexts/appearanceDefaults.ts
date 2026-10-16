import type { AppearanceSettings } from '../api/appearance';

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  phase_colors: {
    analyst: '#00c9c8',
    dev: '#2a7fbf',
    qa: '#e8864a',
    opo: '#52d364',
  },
  initiative_bracket_color: '#b8c9e0',
  initiative_fill_intensity: 'medium',
  animation_speed_seconds: 4,
  hours_balance_lag_days: 2,
  scenario_lift_included: true,
};

/** «Швейцарская»: цвета фаз из макетов — плотные, под белую подпись внутри полосы. */
const SWISS_PHASE_COLORS: AppearanceSettings['phase_colors'] = {
  analyst: '#0F7C7C',
  dev: '#1F4FD1',
  qa: '#9A5B00',
  opo: '#7A3E9A',
};

/**
 * Внешний вид диаграммы под обложку: цвета по умолчанию заменяются палитрой
 * обложки, свои цвета пользователя сохраняются, но затемняются до читаемой
 * белой подписи. Сохранённые настройки не меняются — это только показ.
 */
export function skinAppearance(
  s: AppearanceSettings,
  skin: string | null,
  readable: (hex: string) => string,
): AppearanceSettings {
  if (!skin) return s;
  const phase_colors = { ...s.phase_colors };
  for (const key of Object.keys(phase_colors) as Array<keyof AppearanceSettings['phase_colors']>) {
    const own = phase_colors[key];
    phase_colors[key] = own.toLowerCase() === DEFAULT_APPEARANCE.phase_colors[key].toLowerCase()
      ? SWISS_PHASE_COLORS[key]
      : readable(own);
  }
  const bracket = s.initiative_bracket_color.toLowerCase() === DEFAULT_APPEARANCE.initiative_bracket_color.toLowerCase()
    ? '#111111'
    : s.initiative_bracket_color;
  return { ...s, phase_colors, initiative_bracket_color: bracket };
}
