import { describe, expect, it } from 'vitest';
import { DEFAULT_APPEARANCE } from '../../contexts/appearanceDefaults';
import { planStatusTag } from '../../hooks/useResourcePlanningPage';
import { ZONES_PHASE_COLORS, zonesAppearance } from './rpAppearance';

describe('zonesAppearance', () => {
  it('заводские цвета фаз заменяются цветами скина', () => {
    expect(zonesAppearance(DEFAULT_APPEARANCE).phase_colors).toEqual(ZONES_PHASE_COLORS);
  });

  it('свои цвета пользователя остаются', () => {
    const custom = { ...DEFAULT_APPEARANCE, phase_colors: { ...DEFAULT_APPEARANCE.phase_colors, dev: '#123456' } };
    const out = zonesAppearance(custom);
    expect(out.phase_colors.dev).toBe('#123456');
    expect(out.phase_colors.analyst).toBe(ZONES_PHASE_COLORS.analyst);
  });

  it('прочие настройки вида не трогает', () => {
    const out = zonesAppearance(DEFAULT_APPEARANCE);
    expect(out.initiative_bracket_color).toBe(DEFAULT_APPEARANCE.initiative_bracket_color);
    expect(out.animation_speed_seconds).toBe(DEFAULT_APPEARANCE.animation_speed_seconds);
  });
});

describe('planStatusTag', () => {
  it.each([
    ['ready', 'Готово', 'cyan'],
    ['stale', 'Требуется пересчёт', 'orange'],
    ['computing', 'Считается…', 'blue'],
    ['draft', 'Черновик', 'default'],
  ])('%s → %s', (status, label, color) => {
    expect(planStatusTag(status)).toEqual({ label, color });
  });
});
