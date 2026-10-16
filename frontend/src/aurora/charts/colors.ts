export const CHART_COLORS_AURORA = {
  blue: '#38bdf8',
  violet: '#a78bfa',
  green: '#34d399',
  yellow: '#fbbf24',
  red: '#fb7185',
  cyan: '#22d3ee',
  pink: '#e879f9',
  amber: '#fcd34d',
  teal: '#2dd4bf',
  neutral: '#7f90b0',
} as const;

export const CHART_PALETTE_AURORA = [
  CHART_COLORS_AURORA.blue,
  CHART_COLORS_AURORA.violet,
  CHART_COLORS_AURORA.green,
  CHART_COLORS_AURORA.yellow,
  CHART_COLORS_AURORA.red,
  CHART_COLORS_AURORA.cyan,
  CHART_COLORS_AURORA.pink,
  CHART_COLORS_AURORA.amber,
  CHART_COLORS_AURORA.teal,
  CHART_COLORS_AURORA.neutral,
];

/* «Швейцарская»: плотные цвета статусов и фаз из макетов; акцент — перерасход.
 * Те же ключи, что у Aurora, — потребители берут цвета по имени. */
export const CHART_COLORS_SWISS: Record<keyof typeof CHART_COLORS_AURORA, string> = {
  blue: '#1F4FD1',
  violet: '#7A3E9A',
  green: '#1E7A3E',
  yellow: '#9A6400',
  red: '#D9391A',
  cyan: '#0E7C86',
  pink: '#B0306A',
  amber: '#C75B00',
  teal: '#0F7C7C',
  neutral: '#6E6E6E',
};

export const CHART_PALETTE_SWISS = [
  '#111111',
  CHART_COLORS_SWISS.blue,
  CHART_COLORS_SWISS.amber,
  CHART_COLORS_SWISS.cyan,
  CHART_COLORS_SWISS.violet,
  CHART_COLORS_SWISS.green,
  CHART_COLORS_SWISS.red,
  CHART_COLORS_SWISS.yellow,
  CHART_COLORS_SWISS.pink,
  CHART_COLORS_SWISS.neutral,
];
