interface Props {
  pct: number;
  sub?: string;
  uid?: string;
  size?: number;
  stroke?: number;
  color?: string;
}

export function GlowRing({ pct, sub, uid = 'r', size = 132, stroke = 11, color }: Props) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(pct, 100) / 100);
  const gid = `ring-${uid}`.replace(/[^a-z0-9]/gi, '');
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={color || 'var(--accent-1)'} />
            <stop offset="1" stopColor={color || 'var(--accent-2)'} />
          </linearGradient>
          <filter id={`${gid}-g`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--track-bg)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#${gid})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={off}
          filter={`url(#${gid}-g)`}
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div className="num" style={{ fontSize: size * 0.23, fontWeight: 700 }}>
          {pct}
          <span style={{ fontSize: size * 0.12 }}>%</span>
        </div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}
