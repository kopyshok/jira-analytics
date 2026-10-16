import { describe, expect, it } from 'vitest';
import { DEFAULT_APPEARANCE, skinAppearance } from './appearanceDefaults';
import { contrastRatio, solidFill } from '../utils/readableColor';

describe('skinAppearance', () => {
  it('без обложки возвращает настройки как есть', () => {
    expect(skinAppearance(DEFAULT_APPEARANCE, null, solidFill)).toBe(DEFAULT_APPEARANCE);
  });

  it('цвета по умолчанию заменяются палитрой обложки', () => {
    const s = skinAppearance(DEFAULT_APPEARANCE, 'swiss', solidFill);
    expect(s.phase_colors).toEqual({ analyst: '#0F7C7C', dev: '#1F4FD1', qa: '#9A5B00', opo: '#7A3E9A' });
    expect(s.initiative_bracket_color).toBe('#111111');
  });

  it('свой цвет пользователя сохраняется по тону и читается под белой подписью', () => {
    const own = { ...DEFAULT_APPEARANCE, phase_colors: { ...DEFAULT_APPEARANCE.phase_colors, qa: '#ffd8a8' } };
    const s = skinAppearance(own, 'swiss', solidFill);
    expect(s.phase_colors.qa).not.toBe('#9A5B00');
    expect(contrastRatio('#FFFFFF', s.phase_colors.qa)).toBeGreaterThanOrEqual(4.5);
    // Сохранённые настройки не меняются — это только показ.
    expect(own.phase_colors.qa).toBe('#ffd8a8');
  });
});
