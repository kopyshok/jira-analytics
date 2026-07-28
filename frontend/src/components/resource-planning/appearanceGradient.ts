// Формула градиента: alphaTop = 0.05 + intensity/100 × 0.35,
// alphaBottom = alphaTop × (1 − contrast/100 × 0.5).
// При intensity=0,contrast=0 — практически прозрачно. При intensity=100,contrast=100 —
// верх ярко (0.40), низ — почти невидимо (0.10).
export function computeFillGradientAlphas(intensityPct: number, contrastPct: number): { alphaTop: number; alphaBottom: number } {
  const i = Math.max(0, Math.min(100, intensityPct)) / 100;
  const c = Math.max(0, Math.min(100, contrastPct)) / 100;
  const alphaTop = 0.05 + i * 0.35;
  const alphaBottom = alphaTop * (1 - c * 0.5);
  return { alphaTop, alphaBottom };
}
