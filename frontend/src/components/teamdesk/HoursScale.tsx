import { Tooltip } from 'antd';

interface Props {
  fact: number;
  est: number | null;
  /** centered — засечка оценки посередине: недобор влево, перебор вправо */
  variant?: 'bar' | 'centered';
  overrunPct: number;
  width?: number;
}

const COLOR_OK = '#3ebd85';
const COLOR_OVER = '#ff6b6b';
const COLOR_IDLE = '#788799';
const COLOR_UNDER = '#eeb13c';
const TRACK = 'rgba(125,145,170,0.22)';

/** Шкала «факт / оценка». Перерасход рисуется штриховым хвостом поверх полосы. */
export function HoursScale({ fact, est, variant = 'bar', overrunPct, width }: Props) {
  if (est == null) {
    return <span style={{ color: COLOR_IDLE }}>{fact} / — ч</span>;
  }
  const ratio = est > 0 ? fact / est : 0;
  const over = ratio > 1 + overrunPct / 100;
  const color = over ? COLOR_OVER : fact === 0 ? COLOR_IDLE : COLOR_OK;
  const title = `Факт ${fact} ч из ${est} ч`;

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
            <span>{fact}/{est} ч</span>
            <span>{ratio > 1 ? `+${Math.round((ratio - 1) * 100)}%` : ''}</span>
          </div>
        </div>
      </Tooltip>
    );
  }

  const base = Math.min(ratio, 1) * 100;
  const tail = ratio > 1 ? Math.min(ratio - 1, 1) * 100 : 0;
  return (
    <Tooltip title={title}>
      <div style={{ minWidth: width ?? 132 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
          <span>{fact} / {est} ч</span>
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
