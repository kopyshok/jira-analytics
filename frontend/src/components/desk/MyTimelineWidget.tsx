import { Tooltip, Typography } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtShortRange } from './format';
import { statusTagColor } from '../../utils/status';
import { CHART_COLORS, DARK_THEME, MONTH_NAMES } from '../../utils/constants';
import type { MyTimelineData, TimelineBar } from '../../types/desk';

const BAR_PALETTE = [
  CHART_COLORS.cyan,
  CHART_COLORS.blue,
  CHART_COLORS.green,
  CHART_COLORS.orange,
  CHART_COLORS.purple,
];

function toTime(iso: string): number {
  return new Date(iso.slice(0, 10)).getTime();
}

/** Границы месяцев внутри [start, end] — для вертикальных разделителей. */
function monthTicks(startIso: string, endIso: string): Array<{ left: number; label: string }> {
  const start = new Date(startIso.slice(0, 10));
  const end = new Date(endIso.slice(0, 10));
  const span = end.getTime() - start.getTime();
  if (span <= 0) return [];
  const ticks: Array<{ left: number; label: string }> = [];
  let y = start.getFullYear();
  let m = start.getMonth(); // 0-based
  // Первый день каждого месяца начиная со следующего после start.
  let cur = new Date(y, m + 1, 1);
  while (cur.getTime() < end.getTime()) {
    const left = ((cur.getTime() - start.getTime()) / span) * 100;
    ticks.push({ left, label: MONTH_NAMES[cur.getMonth() + 1] ?? '' });
    m = cur.getMonth();
    y = cur.getFullYear();
    cur = new Date(y, m + 1, 1);
  }
  return ticks;
}

function BarRow({ bar, quarterStart, quarterEnd, color }: {
  bar: TimelineBar; quarterStart: string; quarterEnd: string; color: string;
}) {
  const qStart = toTime(quarterStart);
  const qEnd = toTime(quarterEnd);
  const span = qEnd - qStart || 1;
  const bStart = Math.max(toTime(bar.start_date), qStart);
  const bEnd = Math.min(toTime(bar.end_date), qEnd);
  const left = ((bStart - qStart) / span) * 100;
  const width = Math.max(1, ((bEnd - bStart) / span) * 100);

  const label = bar.key ? `${bar.key} · ${bar.title ?? ''}` : (bar.title ?? '—');
  const jiraUrl = bar.key ? `https://example.atlassian.net/browse/${bar.key}` : null;
  const tip = (
    <span>
      {label}
      <br />
      {fmtShortRange(bar.start_date, bar.end_date)}
      {bar.status ? ` · ${bar.status}` : ''}
    </span>
  );

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 8, alignItems: 'center', padding: '3px 0' }}>
      <div style={{
        fontSize: 12, color: DARK_THEME.textPrimary,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {jiraUrl ? (
          <Typography.Link href={jiraUrl} target="_blank" rel="noreferrer">
            {label}
          </Typography.Link>
        ) : label}
      </div>
      <div style={{ position: 'relative', height: 16, background: DARK_THEME.darkRows, borderRadius: 4 }}>
        <Tooltip title={tip} mouseEnterDelay={0.2}>
          <div style={{
            position: 'absolute', top: 0, height: '100%',
            left: `${left}%`, width: `${width}%`,
            background: color, borderRadius: 4,
            border: `1px solid ${statusTagColor(bar.status, null) === 'success' ? CHART_COLORS.green : 'transparent'}`,
          }} />
        </Tooltip>
      </div>
    </div>
  );
}

export default function MyTimelineWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<MyTimelineData>(token, 'my_timeline');
  const bars = data?.bars ?? [];
  const qStart = data?.quarter_start ?? '';
  const qEnd = data?.quarter_end ?? '';
  const ticks = qStart && qEnd ? monthTicks(qStart, qEnd) : [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={bars.length === 0}
      emptyText="Нет проектов с датами"
    >
      <div style={{ position: 'relative' }}>
        {/* Шкала месяцев */}
        <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 8, marginBottom: 6 }}>
          <div />
          <div style={{ position: 'relative', height: 16, color: DARK_THEME.textMuted, fontSize: 10 }}>
            {ticks.map((t, i) => (
              <span key={i} style={{ position: 'absolute', left: `${t.left}%`, transform: 'translateX(-50%)' }}>
                {t.label}
              </span>
            ))}
          </div>
        </div>
        {bars.map((bar, i) => (
          <BarRow
            key={`${bar.key ?? ''}-${bar.start_date}-${i}`}
            bar={bar}
            quarterStart={qStart}
            quarterEnd={qEnd}
            color={BAR_PALETTE[i % BAR_PALETTE.length]}
          />
        ))}
      </div>
    </WidgetShell>
  );
}
