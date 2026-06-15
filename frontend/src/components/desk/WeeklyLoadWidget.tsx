import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { monthLabel } from './format';
import { CHART_COLORS, DARK_THEME } from '../../utils/constants';
import type { WeeklyLoadData } from '../../types/desk';

export default function WeeklyLoadWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<WeeklyLoadData>(token, 'weekly_load');
  const months = data?.months ?? [];
  const rows = months.map((m) => ({
    name: monthLabel(m.month),
    Норма: m.norm_hours,
    Факт: m.fact_hours,
  }));

  return (
    <WidgetShell title={title} isLoading={isLoading} isError={isError} isEmpty={rows.length === 0}>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={DARK_THEME.border} />
          <XAxis dataKey="name" stroke={DARK_THEME.textMuted} fontSize={12} />
          <YAxis stroke={DARK_THEME.textMuted} fontSize={12} />
          <Tooltip
            contentStyle={{
              background: DARK_THEME.cardBg,
              border: `1px solid ${DARK_THEME.border}`,
              color: DARK_THEME.textPrimary,
            }}
          />
          <Legend />
          <Bar dataKey="Норма" fill={CHART_COLORS.neutral} radius={[3, 3, 0, 0]} />
          <Bar dataKey="Факт" fill={CHART_COLORS.cyan} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </WidgetShell>
  );
}
