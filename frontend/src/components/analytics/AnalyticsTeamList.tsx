import { Card, List } from 'antd';
import type { AnalyticsReportResponse } from '../../types/api';

interface Props {
  data: AnalyticsReportResponse | undefined;
  selected: string | 'all';
  onSelect: (t: string | 'all') => void;
}

export default function AnalyticsTeamList({ data, selected, onSelect }: Props) {
  const teams = data?.teams || [];
  return (
    <Card size="small" title="Команды">
      <List size="small">
        <List.Item
          onClick={() => onSelect('all')}
          style={{ cursor: 'pointer', background: selected === 'all' ? '#1c3358' : undefined }}
        >
          Все команды
        </List.Item>
        {teams.map((t) => (
          <List.Item
            key={t.team || '_none_'}
            onClick={() => onSelect(t.team || '_none_')}
            style={{ cursor: 'pointer', background: selected === t.team ? '#1c3358' : undefined }}
          >
            {t.team || 'Без команды'}{' '}
            <span style={{ color: '#7e94b8', marginLeft: 8 }}>
              {Math.round(t.totals.fact_hours)} ч
            </span>
          </List.Item>
        ))}
      </List>
    </Card>
  );
}
