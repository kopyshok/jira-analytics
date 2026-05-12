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
};
