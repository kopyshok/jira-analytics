import type React from 'react';
import type { NodeTotals } from '../../types/api';

interface Props {
  totals: NodeTotals;
}

const TILE: React.CSSProperties = {
  background: 'var(--glass-bg, #0f2340)',
  borderRadius: 8,
  padding: '14px 18px',
  flex: '1 1 0',
  minWidth: 0,
  border: '1px solid var(--glass-border, rgba(255,255,255,0.04))',
};

const LABEL: React.CSSProperties = {
  fontSize: 11,
  letterSpacing: 0.5,
  textTransform: 'uppercase',
  color: 'var(--text-muted, #7e94b8)',
  marginBottom: 4,
};

const VALUE: React.CSSProperties = {
  fontSize: 24,
  fontWeight: 600,
  color: '#e6edf7',
  lineHeight: 1.1,
};

export default function AnalyticsKpiTiles({ totals }: Props) {
  const pct = totals.plan_hours && totals.plan_hours > 0
    ? (totals.fact_hours / totals.plan_hours) * 100
    : null;
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
      <div style={TILE}>
        <div style={LABEL}>Σ Часов факт</div>
        <div style={VALUE}>{totals.fact_hours.toFixed(1)}</div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Σ Часов план</div>
        <div style={VALUE}>
          {totals.plan_hours != null ? totals.plan_hours.toFixed(0) : '—'}
        </div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>% Выполнения</div>
        <div style={{ ...VALUE, color: pct == null ? '#e6edf7' : pct > 110 ? '#ff4d4f' : pct >= 70 ? '#faad14' : '#67d68d' }}>
          {pct == null ? '—' : `${pct.toFixed(0)}%`}
        </div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Сотрудников</div>
        <div style={VALUE}>{totals.employee_count}</div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Чужих часов</div>
        <div style={{ ...VALUE, color: totals.foreign_hours > 0 ? '#ff9c4a' : '#e6edf7' }}>
          {totals.foreign_hours.toFixed(1)}
          {totals.foreign_hours > 0 && (
            <span style={{ fontSize: 13, marginLeft: 6, color: '#ff9c4a', fontWeight: 500 }}>
              ({totals.foreign_pct.toFixed(0)}%)
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
