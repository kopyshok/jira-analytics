import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import type { CategoryBreakdownData, WorkTypeSlice } from '../../types/desk';

/** Класс по нагрузке: >110 перегруз, 70–110 норма, <70 недогруз. */
function loadClass(wt: WorkTypeSlice): { chip: string; fill: string } {
  const overZeroPlan = wt.plan_hours === 0 && wt.fact_hours > 0;
  if (overZeroPlan || wt.pct > 110) return { chip: 'desk-chip-over', fill: 'var(--red)' };
  if (wt.pct >= 70) return { chip: 'desk-chip-ok', fill: 'var(--green)' };
  return { chip: 'desk-chip-low', fill: 'var(--accent-dim)' };
}

function BulletRow({ wt }: { wt: WorkTypeSlice }) {
  const overZeroPlan = wt.plan_hours === 0 && wt.fact_hours > 0;
  const { chip, fill } = loadClass(wt);
  // Шкала: максимум = max(план, факт), чтобы перегруз был виден за планом.
  const scaleMax = Math.max(wt.plan_hours, wt.fact_hours, 1);
  const fillW = Math.min(100, (wt.fact_hours / scaleMax) * 100);
  const tickLeft = overZeroPlan ? 100 : Math.min(100, (wt.plan_hours / scaleMax) * 100);

  return (
    <div className="desk-bullet-item">
      <div className="desk-bullet-header">
        <span className="desk-bullet-label">{wt.label}</span>
        <span className="desk-bullet-nums">
          {Math.round(wt.fact_hours)} ч / {Math.round(wt.plan_hours)} ч
          <span className={`desk-pct-chip ${chip}`}>{Math.round(wt.pct)}%</span>
        </span>
      </div>
      <div className="desk-bullet-track">
        <div className="desk-bullet-fill" style={{ width: `${fillW}%`, background: fill }} />
        <div className="desk-bullet-tick" style={{ left: `${tickLeft}%` }} />
      </div>
    </div>
  );
}

export default function CategoryBreakdownWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<CategoryBreakdownData>(token, 'category_breakdown');
  const workTypes = data?.work_types ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={workTypes.length === 0}
    >
      <div className="desk-bullet-list">
        {workTypes.map((wt) => (
          <BulletRow key={wt.label} wt={wt} />
        ))}
      </div>
    </WidgetShell>
  );
}
