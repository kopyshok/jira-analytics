import { describe, expect, it } from 'vitest';
import { contrastRatio, readableInk, readablePair, solidFill } from './readableColor';

// Цвета, на которых жаловались: пастель ролей, яркий розовый, почти белый, мусор.
const SAMPLES = ['#9bd7f2', '#f48bc4', '#78a49a', '#eb2f96', '#f5f1ea', '#ffffff', '#000000', '#ff9c4a', '#5c82b5', '#fa0', 'not-a-color', '', null, undefined];

describe('readableColor', () => {
  it('contrastRatio: чёрный на белом — 21, одинаковые — 1', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 0);
    expect(contrastRatio('#777777', '#777777')).toBeCloseTo(1, 5);
  });

  it.each(SAMPLES)('readablePair(%s): текст читается на подложке (≥ 4.5:1)', (hex) => {
    const { bg, fg, border } = readablePair(hex);
    expect(bg).toMatch(/^#[0-9A-F]{6}$/);
    expect(border).toMatch(/^#[0-9A-F]{6}$/);
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5);
    // Подложка светлая: на белом листе она — тон, а не плотная заливка.
    expect(contrastRatio(bg, '#FFFFFF')).toBeLessThan(1.25);
  });

  it.each(SAMPLES)('readableInk(%s): тёмный текст на белом (≥ 4.5:1)', (hex) => {
    expect(contrastRatio(readableInk(hex), '#FFFFFF')).toBeGreaterThanOrEqual(4.5);
  });

  it.each(SAMPLES)('solidFill(%s): белые инициалы читаются (≥ 4.5:1)', (hex) => {
    expect(contrastRatio('#FFFFFF', solidFill(hex))).toBeGreaterThanOrEqual(4.5);
  });

  it('тон сохраняется: из синего получается синий, из розового — розовый', () => {
    const blue = readablePair('#9bd7f2').fg;
    const pink = readablePair('#f48bc4').fg;
    const [rb, , bb] = [1, 3, 5].map((i) => parseInt(blue.slice(i, i + 2), 16));
    const [rp, , bp] = [1, 3, 5].map((i) => parseInt(pink.slice(i, i + 2), 16));
    expect(bb).toBeGreaterThan(rb);
    expect(rp).toBeGreaterThan(bp);
  });
});
