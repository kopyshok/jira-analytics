interface Props {
  pct: number;
  max?: number;
  glow?: boolean;
  color?: string;
}

export function Track({ pct, max = 130, glow = true, color }: Props) {
  const width = `${(Math.min(pct, max) / max) * 100}%`;
  return (
    <div className="track">
      <i
        style={{
          width,
          background:
            color || 'linear-gradient(90deg, var(--accent-1), var(--accent-2))',
          boxShadow: glow ? '0 0 10px var(--accent-glow)' : 'none',
        }}
      />
    </div>
  );
}
