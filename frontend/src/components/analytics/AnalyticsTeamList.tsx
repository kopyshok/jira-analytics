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

export default function AnalyticsTeamList({ data, selected, onSelect, compact = false }: Props) {
  const teams = data?.teams || [];
  if (compact) {
    const tab = (key: string, label: string, hours: number | null) => (
      <button
        key={key}
        type="button"
        aria-pressed={selected === key}
        className={`anc-team${selected === key ? ' is-active' : ''}`}
        onClick={() => onSelect(key)}
      >
        <span>{label}</span>
        <span className="anc-team-hours">{hours != null && hours > 0 ? `${formatHours(hours)} ч` : '—'}</span>
      </button>
    );
    return (
      <div className="anc-teams" role="group" aria-label="Команды">
        {tab('all', 'Все команды', data?.grand_totals.fact_hours ?? null)}
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
