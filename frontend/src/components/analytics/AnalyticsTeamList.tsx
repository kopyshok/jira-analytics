import { Card } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { AnalyticsReportResponse } from '../../types/api';

interface Props {
  data: AnalyticsReportResponse | undefined;
  selected: string | 'all';
  onSelect: (t: string | 'all') => void;
  /** list — колонкой слева (Aurora); tabs — строкой вкладок над таблицей (обложки). */
  variant?: 'list' | 'tabs';
  /** Номер блока перед первой вкладкой («2.2»). */
  num?: string;
}

const rowStyle = (active: boolean): React.CSSProperties => ({
  cursor: 'pointer',
  padding: '8px 12px',
  background: active ? DARK_THEME.darkAccent : undefined,
  color: active ? DARK_THEME.textPrimary : undefined,
  borderRadius: 6,
});

const fmtHours = (h: number) =>
  h.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export default function AnalyticsTeamList({ data, selected, onSelect, variant = 'list', num }: Props) {
  const teams = data?.teams || [];

  if (variant === 'tabs') {
    const total = teams.reduce((s, t) => s + t.totals.fact_hours, 0);
    return (
      <div role="tablist" aria-label="Команды" className="sw-tabs an-team-tabs">
        <button
          type="button"
          role="tab"
          aria-selected={selected === 'all'}
          className={selected === 'all' ? 'is-active' : undefined}
          onClick={() => onSelect('all')}
        >
          {num && <span className="sw-tab-num">{num}</span>}
          Все команды <span className="an-tab-hours">{fmtHours(total)} ч</span>
        </button>
        {teams.map((t) => {
          const key = t.team || '_none_';
          const active = selected === key;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active}
              className={active ? 'is-active' : undefined}
              onClick={() => onSelect(key)}
            >
              {t.team || 'Без команды'} <span className="an-tab-hours">{fmtHours(t.totals.fact_hours)} ч</span>
            </button>
          );
        })}
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
