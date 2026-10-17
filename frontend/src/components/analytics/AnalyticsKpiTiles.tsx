import type React from 'react';
import { TriangleAlert } from 'lucide-react';
import type { NodeTotals } from '../../types/api';
import { formatHours, formatInt, formatPct, planTone } from '../../utils/analyticsView';

interface Props {
  totals: NodeTotals;
  /** Вид скина: одна карточка с пятью ячейками, числа по-русски, «чужие» — подкрашенной ячейкой. */
  compact?: boolean;
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

// Цвет «чужих часов»: оранжевый Aurora на светлых поверхностях не читается,
// скин задаёт свой через переменную.
const FOREIGN = 'var(--an-foreign-text, #ff9c4a)';

export default function AnalyticsKpiTiles({ totals, compact = false }: Props) {
  const pct = totals.plan_hours && totals.plan_hours > 0
    ? (totals.fact_hours / totals.plan_hours) * 100
    : null;
  if (compact) return <KpiStrip totals={totals} pct={pct} />;
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 16 }} data-tour="analytics-kpi">
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
        <div style={{ ...VALUE, color: pct == null ? 'var(--text, #e6edf7)' : pct > 110 ? '#ff4d4f' : pct >= 70 ? '#faad14' : '#67d68d' }}>
          {pct == null ? '—' : `${pct.toFixed(0)}%`}
        </div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Сотрудников</div>
        <div style={VALUE}>{totals.employee_count}</div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Чужих часов</div>
        <div style={{ ...VALUE, color: totals.foreign_hours > 0 ? FOREIGN : 'var(--text, #e6edf7)' }}>
          {totals.foreign_hours.toFixed(1)}
          {totals.foreign_hours > 0 && (
            <span style={{ fontSize: 13, marginLeft: 6, color: FOREIGN, fontWeight: 500 }}>
              ({totals.foreign_pct.toFixed(0)}%)
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Сводка одной карточкой: факт крупно, остальное тише; у «% выполнения» —
 * тонкая полоса, «чужие часы» — подкрашенная ячейка с предупреждением.
 */
function KpiStrip({ totals, pct }: { totals: NodeTotals; pct: number | null }) {
  const foreign = totals.foreign_hours > 0;
  return (
    <section className="wr-card anc-kpi" aria-label="Сводка" data-tour="analytics-kpi">
      <div className="anc-kpi-cell is-main">
        <div className="anc-kpi-label">Σ Часов факт</div>
        <div className="anc-kpi-value">{formatHours(totals.fact_hours)}</div>
      </div>
      <div className="anc-kpi-cell">
        <div className="anc-kpi-label">Σ Часов план</div>
        <div className="anc-kpi-value">
          {totals.plan_hours != null ? formatInt(totals.plan_hours) : '—'}
        </div>
      </div>
      <div className="anc-kpi-cell">
        <div className="anc-kpi-label">% Выполнения</div>
        <div className="anc-kpi-value">{pct == null ? '—' : formatPct(pct)}</div>
        {pct != null && (
          <div className="anc-kpi-bar" aria-hidden>
            <span className={`is-${planTone(pct)}`} style={{ width: `${Math.min(100, pct)}%` }} />
          </div>
        )}
      </div>
      <div className="anc-kpi-cell">
        <div className="anc-kpi-label">Сотрудников</div>
        <div className="anc-kpi-value">{formatInt(totals.employee_count)}</div>
      </div>
      <div className={`anc-kpi-cell is-foreign${foreign ? ' is-on' : ''}`}>
        <div className="anc-kpi-label">
          {foreign && <TriangleAlert size={14} aria-hidden />}
          Чужих часов
        </div>
        <div className="anc-kpi-foreign">
          <span className="anc-kpi-value">{formatHours(totals.foreign_hours)}</span>
          {foreign && <span className="anc-kpi-share">({formatPct(totals.foreign_pct)})</span>}
        </div>
      </div>
    </section>
  );
}
