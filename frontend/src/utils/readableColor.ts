/**
 * Читаемые пары цветов для цветов справочников (роли, виды работ, причины
 * отсутствия, аватары): цвет в базе может быть любым — пастельным, ярким,
 * почти белым. В светлых обложках из него строится пара «светлая подложка +
 * тёмный текст того же тона» с контрастом не ниже 4.5:1 (WCAG AA).
 */

interface Rgb { r: number; g: number; b: number }

const FALLBACK: Rgb = { r: 110, g: 110, b: 110 };

function parseHex(hex: string | null | undefined): Rgb | null {
  if (!hex) return null;
  const m = hex.trim().match(/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (!m) return null;
  const s = m[1].length === 3 ? m[1].split('').map((c) => c + c).join('') : m[1];
  return { r: parseInt(s.slice(0, 2), 16), g: parseInt(s.slice(2, 4), 16), b: parseInt(s.slice(4, 6), 16) };
}

function toHex({ r, g, b }: Rgb): string {
  return '#' + [r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('').toUpperCase();
}

function rgbToHsl({ r, g, b }: Rgb): [number, number, number] {
  const rn = r / 255, gn = g / 255, bn = b / 255;
  const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0);
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  return [h * 60, s, l];
}

function hslToRgb(h: number, s: number, l: number): Rgb {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = ((h % 360) + 360) % 360 / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let rgb: [number, number, number];
  if (hp < 1) rgb = [c, x, 0];
  else if (hp < 2) rgb = [x, c, 0];
  else if (hp < 3) rgb = [0, c, x];
  else if (hp < 4) rgb = [0, x, c];
  else if (hp < 5) rgb = [x, 0, c];
  else rgb = [c, 0, x];
  const m = l - c / 2;
  return { r: (rgb[0] + m) * 255, g: (rgb[1] + m) * 255, b: (rgb[2] + m) * 255 };
}

function luminance({ r, g, b }: Rgb): number {
  const f = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

/** Контраст двух hex-цветов по WCAG (1…21). */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(parseHex(a) ?? FALLBACK);
  const lb = luminance(parseHex(b) ?? FALLBACK);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Тёмный цвет того же тона, читаемый на `against` (по умолчанию — на белом). */
export function readableInk(hex: string | null | undefined, against = '#FFFFFF', min = 4.5): string {
  const [h, s0] = rgbToHsl(parseHex(hex) ?? FALLBACK);
  // Яркие и пастельные цвета приглушаем: насыщенный тёмный текст «звенит».
  const s = Math.min(s0, 0.75);
  for (let l = 0.42; l >= 0; l -= 0.02) {
    const ink = toHex(hslToRgb(h, s, l));
    if (contrastRatio(ink, against) >= min) return ink;
  }
  return '#111111';
}

/**
 * Пара для метки/фишки с текстом: светлая подложка тона цвета, тёмный текст
 * того же тона (контраст ≥ 4.5:1) и рамка чуть темнее подложки.
 */
export function readablePair(hex: string | null | undefined): { bg: string; fg: string; border: string } {
  const [h, s0] = rgbToHsl(parseHex(hex) ?? FALLBACK);
  const s = Math.min(s0, 0.6);
  const bg = toHex(hslToRgb(h, s, 0.94));
  const border = toHex(hslToRgb(h, s, 0.80));
  return { bg, fg: readableInk(hex, bg), border };
}

/** Сплошная заливка под белый текст (аватары, плотные фишки): тот же тон, контраст ≥ 4.5:1. */
export function solidFill(hex: string | null | undefined): string {
  return readableInk(hex, '#FFFFFF');
}
