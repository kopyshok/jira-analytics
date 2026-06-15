import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { CHART_COLORS, DARK_THEME } from '../../utils/constants';
import type { CategoryBreakdownData, WorkTypeSlice } from '../../types/desk';

/** Цвет по проценту: >110 перегруз (красный), 70–110 норма, <70 недогруз (приглушённый). */
function barColor(wt: WorkTypeSlice): string {
  const overflowZeroPlan = wt.plan_hours === 0 && wt.fact_hours > 0;
  if (overflowZeroPlan || wt.pct > 110) return CHART_COLORS.red;
  if (wt.pct >= 70) return CHART_COLORS.green;
  return DARK_THEME.textMuted;
}

function WorkTypeRow({ wt }: { wt: WorkTypeSlice }) {
  const overflowZeroPlan = wt.plan_hours === 0 && wt.fact_hours > 0;
  const color = barColor(wt);
  const fillW = wt.plan_hours > 0
    ? Math.min(100, (wt.fact_hours / wt.plan_hours) * 100)
    : (overflowZeroPlan ? 100 : 0);
  return (
    <div style={{ padding: '4px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 3 }}>
        <span style={{
          fontSize: 12, color: DARK_THEME.textPrimary,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {wt.label}
        </span>
        <span style={{ fontSize: 12, color: DARK_THEME.textMuted, whiteSpace: 'nowrap' }}>
          {Math.round(wt.fact_hours)}ч / {Math.round(wt.plan_hours)}ч
        </span>
      </div>
      <div style={{ height: 8, background: DARK_THEME.darkRows, borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${fillW}%`, background: color, borderRadius: 4 }} />
      </div>
    </div>
  );
}

export default function CategoryBreakdownWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<CategoryBreakdownData>(
    token,
    'category_breakdown',
  );
  const workTypes = data?.work_types ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={workTypes.length === 0}
    >
      <div>
        {workTypes.map((wt) => (
          <WorkTypeRow key={wt.label} wt={wt} />
        ))}
      </div>
    </WidgetShell>
  );
}
