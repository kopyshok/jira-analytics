import { describe, it, expect } from 'vitest';
import { contrastRatio, parseColor, readableInk, readablePair, textOnFill } from './readableColor';

const ratio = (a: string, b: string) => contrastRatio(parseColor(a)!, parseColor(b)!);

describe('parseColor', () => {
  it('понимает короткий и полный hex и rgb()', () => {
    expect(parseColor('#fff')).toEqual({ r: 255, g: 255, b: 255 });
    expect(parseColor('#2F6FDE')).toEqual({ r: 47, g: 111, b: 222 });
    expect(parseColor('rgb(10, 20, 30)')).toEqual({ r: 10, g: 20, b: 30 });
  });
  it('мусор — null', () => {
    expect(parseColor('')).toBeNull();
    expect(parseColor('cyan')).toBeNull();
    expect(parseColor(null)).toBeNull();
  });
});

describe('readablePair', () => {
  // Пастельные цвета ролей из справочника, которые не читались на светлой подложке.
  const pastel = ['#9bd7f2', '#f48bc4', '#78a49a', '#ffffff', '#eb2f96', '#00c9c8', '#52d364', '#ffb432'];

  it.each(pastel)('%s: текст на подложке не хуже 4.5:1', (c) => {
    const p = readablePair(c);
    expect(ratio(p.fg, p.bg)).toBeGreaterThanOrEqual(4.5);
  });

  it('подложка светлая, текст того же оттенка', () => {
    const p = readablePair('#2F6FDE');
    const bg = parseColor(p.bg)!;
    expect(bg.r + bg.g + bg.b).toBeGreaterThan(600);
    const fg = parseColor(p.fg)!;
    expect(fg.b).toBeGreaterThan(fg.r); // синий остаётся синим
  });

  it('непонятный цвет — нейтральная читаемая пара', () => {
    const p = readablePair('not-a-color');
    expect(ratio(p.fg, p.bg)).toBeGreaterThanOrEqual(4.5);
  });
});

describe('readableInk', () => {
  it('тёмный цвет не трогает', () => {
    expect(readableInk('#1C1C1A')).toBe('#1C1C1A');
  });
  it('светлый затемняет до 4.5:1 к белому', () => {
    expect(ratio(readableInk('#5c82b5'), '#FFFFFF')).toBeGreaterThanOrEqual(4.5);
    expect(ratio(readableInk('#ff9c4a'), '#FFFFFF')).toBeGreaterThanOrEqual(4.5);
  });
  it('учитывает фон', () => {
    expect(ratio(readableInk('#b5502a', '#f6ddd7'), '#f6ddd7')).toBeGreaterThanOrEqual(4.5);
  });
});

describe('textOnFill', () => {
  it('на насыщенном синем — белый, на бирюзовом и оранжевом — тёмный', () => {
    expect(textOnFill('#2F6FDE')).toBe('#FFFFFF');
    expect(textOnFill('#4DBFB4')).toBe('#1C1C1A');
    expect(textOnFill('#F0A04B')).toBe('#1C1C1A');
  });
});
