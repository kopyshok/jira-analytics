import type { AnalyticsReportResponse } from '../../types/api';

interface Props {
  data: AnalyticsReportResponse;
  selectedTeam: string | 'all';
  worklogMode: 'inline' | 'drawer';
  periodStart: string;
  periodEnd: string;
}

export default function AnalyticsTable({ data, selectedTeam }: Props) {
  const teams =
    selectedTeam === 'all'
      ? data.teams
      : data.teams.filter((t) => (t.team || '_none_') === selectedTeam);
  return (
    <div>
      {teams.map((t) => (
        <div key={t.team || '_none_'} style={{ marginBottom: 24 }}>
          <h3>{t.team || 'Без команды'}</h3>
          <div style={{ color: '#7e94b8' }}>
            {Math.round(t.totals.fact_hours)} ч / {t.totals.issue_count} задач
          </div>
        </div>
      ))}
    </div>
  );
}
