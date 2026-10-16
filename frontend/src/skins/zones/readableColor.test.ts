import { describe, expect, it } from 'vitest';
import { contrastRatio, readablePair } from './readableColor';

function hue(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const d = max - min;
  if (d === 0) return -1;
  let h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  h *= 60;
  return h;
}

describe('contrastRatio', () => {
  it('чёрный на белом — 21, одинаковые — 1', () => {
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 0);
    expect(contrastRatio('#2546A6', '#2546A6')).toBeCloseTo(1, 5);
  });

  it('неразборчивый цвет — 1', () => {
    expect(contrastRatio('red', '#FFFFFF')).toBe(1);
  });
});

describe('readablePair', () => {
  // Цвета, на которых метки были нечитаемыми: пастельные роли, неоновые
  // аватары, белый и бежевый фон, насыщенный розовый.
  const colors = ['#9bd7f2', '#f48bc4', '#78a49a', '#eb2f96', '#ff9c4a', '#00c9c8',
    '#52d364', '#5470ff', '#ffffff', '#f5f1ea', '#000000', '#b5502a', '#888'];

  it.each(colors)('%s — текст к подложке и к белому не ниже 4.5', (c) => {
    const p = readablePair(c);
    expect(contrastRatio(p.fg, p.bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(p.fg, '#FFFFFF')).toBeGreaterThanOrEqual(4.5);
  });

  it.each(colors)('%s — подложка светлая', (c) => {
    expect(contrastRatio(readablePair(c).bg, '#FFFFFF')).toBeLessThan(1.25);
  });

  it('оттенок сохраняется', () => {
    for (const c of ['#9bd7f2', '#f48bc4', '#eb2f96', '#ff9c4a']) {
      const h0 = hue(c.length === 4 ? c : c);
      const p = readablePair(c);
      expect(Math.abs(hue(p.fg) - h0)).toBeLessThan(8);
      expect(Math.abs(hue(p.bg) - h0)).toBeLessThan(8);
    }
  });

  it('почти серый и пустой — нейтральная пара', () => {
    for (const c of ['#f5f1ea', '#ffffff', null, undefined, '', 'не цвет']) {
      const p = readablePair(c);
      expect(hue(p.fg)).toBe(-1);
      expect(hue(p.bg)).toBe(-1);
    }
  });
});
