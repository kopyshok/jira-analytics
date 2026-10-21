import { useEffect, useState } from 'react';
import { Card } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { AnalyticsReportResponse } from '../../types/api';
import { formatHours } from '../../utils/analyticsView';

interface Props {
  data: AnalyticsReportResponse | undefined;
  selected: string | 'all';
  onSelect: (t: string | 'all') => void;
  /** Вид скина: команды горизонтальным рядом-переключателем с часами, длинный ряд листается вбок. */
  compact?: boolean;
}

const rowStyle = (active: boolean): React.CSSProperties => ({
  cursor: 'pointer',
  padding: '8px 12px',
  background: active ? DARK_THEME.darkAccent : undefined,
  color: active ? DARK_THEME.textPrimary : undefined,
  borderRadius: 6,
});

/** Ряд команд скина: есть ли что листать вправо (тогда край ряда гаснет) и колесо мыши листает вбок. */
function useRowScroll() {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [more, setMore] = useState(false);
  const measure = (n: HTMLDivElement) => setMore(n.scrollLeft + n.clientWidth < n.scrollWidth - 2);
  useEffect(() => {
    if (!el) return undefined;
    // Наблюдатель срабатывает и сразу после подключения — первый замер тоже здесь.
    const ro = new ResizeObserver(() => measure(el));
    ro.observe(el);
    for (const child of Array.from(el.children)) ro.observe(child);
    return () => ro.disconnect();
  }, [el]);
  const onWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    const n = e.currentTarget;
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && n.scrollWidth > n.clientWidth) n.scrollLeft += e.deltaY;
  };
  return { setEl, more, onScroll: (e: React.UIEvent<HTMLDivElement>) => measure(e.currentTarget), onWheel };
}

export default function AnalyticsTeamList({ data, selected, onSelect, compact = false }: Props) {
  const teams = data?.teams || [];
  const { setEl: setRowEl, more: rowMore, onScroll: onRowScroll, onWheel: onRowWheel } = useRowScroll();
  if (compact) {
    // undefined — часов не показываем (у «Все команды» при выбранной команде отчёт уже только по ней).
    const tab = (key: string, label: string, hours: number | null | undefined) => (
      <button
        key={key}
        type="button"
        aria-pressed={selected === key}
        className={`anc-team${selected === key ? ' is-active' : ''}`}
        onClick={() => onSelect(key)}
      >
        <span>{label}</span>
        {hours !== undefined && (
          <span className="anc-team-hours">{hours != null && hours > 0 ? `${formatHours(hours)} ч` : '—'}</span>
        )}
      </button>
    );
    return (
      <div
        ref={setRowEl}
        className={`anc-teams${rowMore ? ' has-more' : ''}`}
        role="group"
        aria-label="Команды"
        onScroll={onRowScroll}
        onWheel={onRowWheel}
      >
        {tab('all', 'Все команды', selected === 'all' ? data?.grand_totals.fact_hours ?? null : undefined)}
        {teams.map((t) => tab(t.team || '_none_', t.team || 'Без команды', t.totals.fact_hours))}
      </div>
    );
  }
  return (
    <Card size="small" title="Команды">
      <div>
        <div onClick={() => onSelect('all')} style={rowStyle(selected === 'all')}>
          Все команды
        </div>
        {teams.map((t) => (
          <div
            key={t.team || '_none_'}
            onClick={() => onSelect(t.team || '_none_')}
            style={rowStyle(selected === t.team)}
          >
            {t.team || 'Без команды'}{' '}
            <span style={{ color: 'var(--text-muted, #7e94b8)', marginLeft: 8 }}>
              {Math.round(t.totals.fact_hours)} ч
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
