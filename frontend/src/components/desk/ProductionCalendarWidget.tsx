import { Tooltip } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { MONTH_NAMES } from '../../utils/constants';
import type { CalendarDay, ProductionCalendarData } from '../../types/desk';

const WEEKDAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const KIND_LABEL: Record<string, string> = {
  workday: 'Рабочий день',
  workday_moved: 'Перенесённый рабочий',
  weekend: 'Выходной',
  holiday: 'Праздник',
  preholiday: 'Предпраздничный',
};

/** CSS-класс ячейки дня по типу. */
function dayClass(kind: string): string {
  switch (kind) {
    case 'holiday': return 'holiday';
    case 'preholiday': return 'preholiday';
    case 'weekend': return 'weekend';
    default: return '';
  }
}

/** Понедельник-первый индекс дня недели (0=Пн … 6=Вс). */
function mondayIndex(iso: string): number {
  return (new Date(iso.slice(0, 10)).getDay() + 6) % 7;
}

function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function MonthGrid({ month, year, days, today }: {
  month: number; year: number; days: CalendarDay[]; today: string;
}) {
  if (days.length === 0) return null;
  const leadBlanks = mondayIndex(days[0].date);
  return (
    <div className="desk-cal-month">
      <div className="desk-cal-month-title">{MONTH_NAMES[month]}</div>
      <div className="desk-cal-grid">
        {WEEKDAY_LABELS.map((w) => (
          <div key={w} className="desk-cal-dow">{w}</div>
        ))}
        {Array.from({ length: leadBlanks }).map((_, i) => (
          <div key={`blank-${i}`} />
        ))}
        {days.map((d) => {
          const iso = d.date.slice(0, 10);
          const dayNum = Number(iso.slice(8, 10));
          const isToday = iso === today;
          const isPast = iso < today;
          const cls = ['desk-cal-day', dayClass(d.kind)];
          if (isToday) cls.push('today');
          else if (isPast) cls.push('past');
          return (
            <Tooltip
              key={iso}
              title={`${dayNum} ${(MONTH_NAMES[month] ?? '').toLowerCase()} ${year} · ${KIND_LABEL[d.kind] ?? d.kind}`}
              mouseEnterDelay={0.3}
            >
              <div className={cls.join(' ')}>{dayNum}</div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

export default function ProductionCalendarWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<ProductionCalendarData>(token, 'production_calendar');
  const days = data?.days ?? [];
  const today = todayIso();

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
      <div className="desk-cal-months">
        {monthEntries.map(([m, mDays]) => (
          <MonthGrid key={m} month={m} year={year} days={mDays} today={today} />
        ))}
      </div>

      <div className="desk-cal-legend">
        <span className="desk-cal-legend-item"><span className="desk-cal-legend-swatch desk-sw-today" />Сегодня</span>
        <span className="desk-cal-legend-item"><span className="desk-cal-legend-swatch desk-sw-holiday" />Праздник</span>
        <span className="desk-cal-legend-item"><span className="desk-cal-legend-swatch desk-sw-preholiday" />Предпраздничный</span>
        <span className="desk-cal-legend-item"><span className="desk-cal-legend-swatch desk-sw-weekend" />Выходной</span>
      </div>

      <div className="desk-cal-footer">
        <strong>Рабочих дней в квартале: {data?.quarter_workdays ?? 0}</strong>
        {' · '}в этом месяце: {data?.month_workdays ?? 0}<br />
        <strong>Рабочих часов в квартале: {data?.quarter_work_hours ?? 0} ч</strong>
        {' · '}в этом месяце: {data?.month_work_hours ?? 0} ч
      </div>
    </WidgetShell>
  );
}
