import { Tooltip } from 'antd';
import { roundHours } from '../../api/teamDesk';

interface Props {
  fact: number;
  est: number | null;
  /**
   * centered — засечка оценки посередине: недобор влево, перебор вправо;
   * inline — полоса и процент в одну строку (часы стоят в соседних колонках).
   */
  variant?: 'bar' | 'centered' | 'inline';
  overrunPct: number;
  width?: number;
}

// Цвета — через CSS-переменные скина; без скина — прежние.
const COLOR_OK = 'var(--desk-scale-ok, #3ebd85)';
const COLOR_OVER = 'var(--desk-scale-over, #ff6b6b)';
const COLOR_IDLE = 'var(--desk-scale-idle, #788799)';
const COLOR_UNDER = 'var(--desk-scale-under, #eeb13c)';
const TRACK = 'var(--desk-scale-track, rgba(125,145,170,0.22))';

/** Шкала «факт / оценка». Перерасход рисуется штриховым хвостом поверх полосы. */
export function HoursScale({ fact, est, variant = 'bar', overrunPct, width }: Props) {
  const factText = roundHours(fact);
  if (est == null) {
    return <span style={{ color: COLOR_IDLE }}>{factText} / — ч</span>;
  }
  const estText = roundHours(est);
  const ratio = est > 0 ? fact / est : 0;
  const over = ratio > 1 + overrunPct / 100;
  const color = over ? COLOR_OVER : fact === 0 ? COLOR_IDLE : COLOR_OK;
  const title = `Факт ${factText} ч из ${estText} ч`;

  if (variant === 'centered') {
    const left = ratio < 1 ? Math.min(1 - ratio, 1) * 50 : 0;
    const right = ratio > 1 ? Math.min(ratio - 1, 1) * 50 : 0;
    return (
      <Tooltip title={title}>
        <div style={{ width: width ?? 150 }}>
          <div style={{ position: 'relative', height: 14, background: TRACK, borderRadius: 3 }}>
            <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: COLOR_IDLE }} />
            {left > 0 && (
              <div style={{ position: 'absolute', top: 2, bottom: 2, right: '50%', width: `${left}%`, background: COLOR_UNDER, borderRadius: '2px 0 0 2px' }} />
            )}
            {right > 0 && (
              <div style={{ position: 'absolute', top: 2, bottom: 2, left: '50%', width: `${right}%`, background: color, borderRadius: '0 2px 2px 0' }} />
            )}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: COLOR_IDLE, fontVariantNumeric: 'tabular-nums' }}>
            <span>{ratio < 1 ? `−${Math.round((1 - ratio) * 100)}%` : ''}</span>
            <span>{factText}/{estText} ч</span>
            <span>{ratio > 1 ? `+${Math.round((ratio - 1) * 100)}%` : ''}</span>
          </div>
        </div>
      </Tooltip>
    );
  }

  const base = Math.min(ratio, 1) * 100;
  const tail = ratio > 1 ? Math.min(ratio - 1, 1) * 100 : 0;
  if (variant === 'inline') {
    return (
      <Tooltip title={title}>
        <div className="desk-scale-inline" style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: width ?? 110 }}>
          <div style={{ position: 'relative', flex: '0 0 70px', height: 6, borderRadius: 2, background: TRACK, overflow: 'hidden' }}>
            <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${over ? 100 : base}%`, background: color, borderRadius: 2 }} />
          </div>
          <span className="desk-scale-pct" data-over={over || undefined} style={{ fontSize: 12, color, fontVariantNumeric: 'tabular-nums' }}>
            {Math.round(ratio * 100)}%
          </span>
        </div>
      </Tooltip>
    );
  }
  return (
    <Tooltip title={title}>
      <div style={{ minWidth: width ?? 132 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
          <span>{factText} / {estText} ч</span>
          <span style={{ color }}>{Math.round(ratio * 100)}%</span>
        </div>
        <div style={{ position: 'relative', height: 5, borderRadius: 3, background: TRACK, marginTop: 4, overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${base}%`, background: color, borderRadius: 3 }} />
          {tail > 0 && (
            <div
              style={{
                position: 'absolute', top: 0, bottom: 0,
                left: `${100 - tail}%`, width: `${tail}%`,
                background: `repeating-linear-gradient(135deg, ${COLOR_OVER} 0 3px, transparent 3px 6px)`,
              }}
            />
          )}
        </div>
      </div>
    </Tooltip>
  );
}
