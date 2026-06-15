import { Tooltip, Typography } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { DARK_THEME, CHART_COLORS, MONTH_NAMES } from '../../utils/constants';
import type { CalendarDay, ProductionCalendarData } from '../../types/desk';

const WEEKDAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

/** Цвет ячейки дня по типу. */
function dayColor(kind: string): { bg: string; fg: string } {
  switch (kind) {
    case 'holiday':
      return { bg: 'rgba(226,75,74,0.22)', fg: CHART_COLORS.red };
    case 'preholiday':
      return { bg: 'rgba(239,159,39,0.20)', fg: CHART_COLORS.orange };
    case 'weekend':
      return { bg: 'rgba(255,255,255,0.04)', fg: DARK_THEME.textDim };
    default: // workday / workday_moved
      return { bg: 'rgba(255,255,255,0.08)', fg: DARK_THEME.textPrimary };
  }
}

const KIND_LABEL: Record<string, string> = {
  workday: 'Рабочий день',
  workday_moved: 'Перенесённый рабочий',
  weekend: 'Выходной',
  holiday: 'Праздник',
  preholiday: 'Предпраздничный',
};

/** Понедельник-первый индекс дня недели (0=Пн … 6=Вс). */
function mondayIndex(iso: string): number {
  return (new Date(iso).getDay() + 6) % 7;
}

function MonthGrid({ month, year, days }: { month: number; year: number; days: CalendarDay[] }) {
  if (days.length === 0) return null;
  const leadBlanks = mondayIndex(days[0].date);
  return (
    <div>
      <div style={{
        fontSize: 12, fontWeight: 600, color: DARK_THEME.textSecondary,
        textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6,
      }}>
        {MONTH_NAMES[month]} {year}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 3 }}>
        {WEEKDAY_LABELS.map((w) => (
          <div key={w} style={{ fontSize: 10, textAlign: 'center', color: DARK_THEME.textMuted }}>
            {w}
          </div>
        ))}
        {Array.from({ length: leadBlanks }).map((_, i) => (
          <div key={`blank-${i}`} />
        ))}
        {days.map((d) => {
          const c = dayColor(d.kind);
          const day = Number(d.date.slice(8, 10));
          return (
            <Tooltip
              key={d.date}
              title={`${KIND_LABEL[d.kind] ?? d.kind}${d.hours ? ` · ${d.hours} ч` : ''}`}
              mouseEnterDelay={0.3}
            >
              <div style={{
                aspectRatio: '1 / 1',
                minHeight: 22,
                background: c.bg,
                color: c.fg,
                borderRadius: 4,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11,
              }}>
                {day}
              </div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

const LEGEND: Array<{ kind: string; label: string }> = [
  { kind: 'workday', label: 'Рабочий' },
  { kind: 'weekend', label: 'Выходной' },
  { kind: 'preholiday', label: 'Предпраздничный' },
  { kind: 'holiday', label: 'Праздник' },
];

export default function ProductionCalendarWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<ProductionCalendarData>(
    token,
    'production_calendar',
  );
  const days = data?.days ?? [];

  // Группируем дни по месяцам.
  const byMonth = new Map<number, CalendarDay[]>();
  for (const d of days) {
    const m = Number(d.date.slice(5, 7));
    const arr = byMonth.get(m) ?? [];
    arr.push(d);
    byMonth.set(m, arr);
  }
  const monthEntries = [...byMonth.entries()].sort((a, b) => a[0] - b[0]);
  const year = days.length > 0 ? Number(days[0].date.slice(0, 4)) : new Date().getFullYear();

  return (
    <WidgetShell title={title} isLoading={isLoading} isError={isError} isEmpty={days.length === 0}>
      <div style={{ marginBottom: 12, fontSize: 13, color: DARK_THEME.textSecondary }}>
        <div>
          Рабочих дней в квартале:{' '}
          <Typography.Text strong style={{ color: CHART_COLORS.cyan }}>
            {data?.quarter_workdays ?? 0}
          </Typography.Text>
          {' · '}в этом месяце:{' '}
          <Typography.Text strong style={{ color: CHART_COLORS.cyan }}>
            {data?.month_workdays ?? 0}
          </Typography.Text>
        </div>
        <div style={{ marginTop: 4 }}>
          Рабочих часов в квартале:{' '}
          <Typography.Text strong style={{ color: CHART_COLORS.cyan }}>
            {data?.quarter_work_hours ?? 0} ч
          </Typography.Text>
          {' · '}в этом месяце:{' '}
          <Typography.Text strong style={{ color: CHART_COLORS.cyan }}>
            {data?.month_work_hours ?? 0} ч
          </Typography.Text>
        </div>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16,
      }}>
        {monthEntries.map(([m, mDays]) => (
          <MonthGrid key={m} month={m} year={year} days={mDays} />
        ))}
      </div>

      <div style={{
        marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 14,
        fontSize: 11, color: DARK_THEME.textSecondary,
      }}>
        {LEGEND.map((l) => {
          const c = dayColor(l.kind);
          return (
            <span key={l.kind} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                display: 'inline-block', width: 12, height: 12, borderRadius: 3, background: c.bg,
                border: `1px solid ${c.fg}`,
              }} />
              {l.label}
            </span>
          );
        })}
      </div>
    </WidgetShell>
  );
}
