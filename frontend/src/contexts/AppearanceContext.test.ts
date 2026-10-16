import { describe, it, expect } from 'vitest';
import { DEFAULT_APPEARANCE, skinAppearance } from './AppearanceContext';
import { PULT_PHASE_COLORS } from '../skins/pult/palette';

describe('skinAppearance', () => {
  it('без обложки — тот же объект', () => {
    expect(skinAppearance(DEFAULT_APPEARANCE, null)).toBe(DEFAULT_APPEARANCE);
  });

  it('обложка заменяет цвета фаз по умолчанию своей палитрой', () => {
    const out = skinAppearance(DEFAULT_APPEARANCE, 'pult');
    expect(out.phase_colors).toEqual(PULT_PHASE_COLORS);
    expect(out.animation_speed_seconds).toBe(DEFAULT_APPEARANCE.animation_speed_seconds);
  });

  it('свои цвета пользователя не трогает', () => {
    const own = { ...DEFAULT_APPEARANCE, phase_colors: { ...DEFAULT_APPEARANCE.phase_colors, dev: '#123456' } };
    const out = skinAppearance(own, 'pult');
    expect(out.phase_colors.dev).toBe('#123456');
    expect(out.phase_colors.qa).toBe(PULT_PHASE_COLORS.qa);
  });
});
