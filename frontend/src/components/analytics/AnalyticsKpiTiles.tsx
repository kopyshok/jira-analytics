import type React from 'react';
import type { NodeTotals } from '../../types/api';
import { useSkin } from '../../contexts/ThemeContext';
import { formatNumber } from '../../utils/format';

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
  color: 'var(--text, #e6edf7)',
  lineHeight: 1.1,
};

export default function AnalyticsKpiTiles({ totals }: Props) {
  // В скине числа — по-русски («3 412,5»), в Aurora — как прежде.
  const ru = !!useSkin();
  const pct = totals.plan_hours && totals.plan_hours > 0
    ? (totals.fact_hours / totals.plan_hours) * 100
    : null;
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 16 }} data-tour="analytics-kpi">
      <div style={TILE}>
        <div style={LABEL}>Σ Часов факт</div>
        <div style={VALUE}>{formatNumber(totals.fact_hours, 1, ru)}</div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Σ Часов план</div>
        <div style={VALUE}>
          {totals.plan_hours != null ? formatNumber(totals.plan_hours, 0, ru) : '—'}
        </div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>% Выполнения</div>
        <div style={{ ...VALUE, color: pct == null ? 'var(--text, #e6edf7)' : pct > 110 ? 'var(--an-pct-over, #ff4d4f)' : pct >= 70 ? 'var(--an-pct-mid, #faad14)' : 'var(--an-pct-low, #67d68d)' }}>
          {pct == null ? '—' : `${pct.toFixed(0)}%`}
        </div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Сотрудников</div>
        <div style={VALUE}>{totals.employee_count}</div>
      </div>
      <div style={TILE}>
        <div style={LABEL} data-foreign={totals.foreign_hours > 0 || undefined}>Чужих часов</div>
        <div style={{ ...VALUE, color: totals.foreign_hours > 0 ? 'var(--an-foreign, #ff9c4a)' : 'var(--text, #e6edf7)' }}>
          {formatNumber(totals.foreign_hours, 1, ru)}
          {totals.foreign_hours > 0 && (
            <span style={{ fontSize: 13, marginLeft: 6, color: 'var(--an-foreign, #ff9c4a)', fontWeight: 500 }}>
              ({totals.foreign_pct.toFixed(0)}%)
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
