interface Props {
  uid: string;
  points: number[];
  height?: number;
}

export function NeonLine({ uid, points, height = 120 }: Props) {
  if (points.length < 2) return null;
  const w = 460;
  const h = height;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const pad = 14;
  const xs = points.map((_, i) => pad + (i * (w - pad * 2)) / (points.length - 1));
  const ys = points.map(
    (p) => h - pad - ((p - min) / (max - min || 1)) * (h - pad * 2),
  );
  const line = xs
    .map((x, i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${ys[i].toFixed(1)}`)
    .join(' ');
  const area = `${line} L${xs[xs.length - 1].toFixed(1)} ${h} L${xs[0].toFixed(1)} ${h} Z`;
  const gid = `nl-${uid}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
      <defs>
        <linearGradient id={`${gid}-s`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="var(--accent-1)" />
          <stop offset="1" stopColor="var(--accent-2)" />
        </linearGradient>
        <linearGradient id={`${gid}-a`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--accent-1)" stopOpacity="0.30" />
          <stop offset="1" stopColor="var(--accent-1)" stopOpacity="0" />
        </linearGradient>
        <filter id={`${gid}-g`} x="-20%" y="-50%" width="140%" height="200%">
          <feGaussianBlur stdDeviation="4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path d={area} fill={`url(#${gid}-a)`} />
      <path
        d={line}
        fill="none"
        stroke={`url(#${gid}-s)`}
        strokeWidth="2.5"
        strokeLinecap="round"
        filter={`url(#${gid}-g)`}
      />
      <circle
        cx={xs[xs.length - 1]}
        cy={ys[ys.length - 1]}
        r="4"
        fill="var(--accent-2)"
        filter={`url(#${gid}-g)`}
      />
    </svg>
  );
}
