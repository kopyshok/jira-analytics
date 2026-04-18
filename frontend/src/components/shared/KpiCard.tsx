import type { ReactNode } from 'react';
import { Card } from 'antd';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  eyebrow: string;
  value: string | number;
  suffix?: string;
  icon?: ReactNode;
  /** Sparkline data — at least 2 points to draw a line. */
  series?: number[];
  /** Trend direction colours the delta pill: positive=cyan, negative=amber, neutral=muted. */
  delta?: { value: string; direction: 'up' | 'down' | 'flat' } | null;
  onClick?: () => void;
  accent?: string;
}

/**
 * Dashboard KPI tile: eyebrow label, monospace numeric headline,
 * right-side mini SVG sparkline, and an optional delta pill.
 */
export default function KpiCard({
  eyebrow,
  value,
  suffix,
  icon,
  series,
  delta,
  onClick,
  accent = DARK_THEME.cyanPrimary,
}: Props) {
  return (
    <Card
      className="kpi-card"
      hoverable={!!onClick}
      onClick={onClick}
      styles={{ body: { padding: 18 } }}
      style={{ position: 'relative', overflow: 'hidden' }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background: `linear-gradient(135deg, ${accent}10 0%, transparent 60%)`,
        }}
      />
      <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 11,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              color: DARK_THEME.textMuted,
              fontWeight: 600,
              marginBottom: 10,
            }}
          >
            {icon && <span style={{ color: accent }}>{icon}</span>}
            <span>{eyebrow}</span>
          </div>
          <div
            style={{
              fontFamily: "'JetBrains Mono', ui-monospace, monospace",
              fontSize: 32,
              fontWeight: 500,
              letterSpacing: '-0.03em',
              color: DARK_THEME.textPrimary,
              fontVariantNumeric: 'tabular-nums',
              lineHeight: 1,
            }}
          >
            {value}
            {suffix && (
              <span style={{ fontSize: 14, color: DARK_THEME.textMuted, marginLeft: 6, fontWeight: 400 }}>
                {suffix}
              </span>
            )}
          </div>
          {delta && (
            <div style={{ marginTop: 10 }}>
              <DeltaPill {...delta} />
            </div>
          )}
        </div>
        {series && series.length >= 2 && (
          <Sparkline data={series} color={accent} width={88} height={44} />
        )}
      </div>
    </Card>
  );
}

function DeltaPill({ value, direction }: { value: string; direction: 'up' | 'down' | 'flat' }) {
  const color =
    direction === 'up' ? DARK_THEME.cyanPrimary :
    direction === 'down' ? DARK_THEME.amber :
    DARK_THEME.textMuted;
  const arrow = direction === 'up' ? '↗' : direction === 'down' ? '↘' : '→';
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 999,
        fontSize: 11,
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        fontVariantNumeric: 'tabular-nums',
        color,
        border: `1px solid ${color}40`,
        background: `${color}10`,
        fontWeight: 500,
      }}
    >
      <span>{arrow}</span>
      <span>{value}</span>
    </span>
  );
}

function Sparkline({ data, color, width, height }: { data: number[]; color: string; width: number; height: number }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  const points = data
    .map((v, i) => `${(i * stepX).toFixed(1)},${(height - ((v - min) / range) * height).toFixed(1)}`)
    .join(' ');
  const areaPoints = `0,${height} ${points} ${width},${height}`;
  const gid = `sp-${color.replace('#', '')}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ flexShrink: 0 }}>
      <defs>
        <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.5" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#${gid})`} />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
