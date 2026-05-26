import { Card } from 'antd';
import type { AnalyticsReportResponse } from '../../types/api';

interface Props {
  data: AnalyticsReportResponse | undefined;
  selected: string | 'all';
  onSelect: (t: string | 'all') => void;
}

const rowStyle = (active: boolean): React.CSSProperties => ({
  cursor: 'pointer',
  padding: '8px 12px',
  background: active ? '#1c3358' : undefined,
});

export default function AnalyticsTeamList({ data, selected, onSelect }: Props) {
  const teams = data?.teams || [];
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
            <span style={{ color: '#7e94b8', marginLeft: 8 }}>
              {Math.round(t.totals.fact_hours)} ч
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
