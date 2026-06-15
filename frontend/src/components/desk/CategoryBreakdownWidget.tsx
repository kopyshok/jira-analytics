import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { CHART_COLORS, DARK_THEME } from '../../utils/constants';
import type { CategoryBreakdownData } from '../../types/desk';

const PALETTE = [
  CHART_COLORS.cyan,
  CHART_COLORS.blue,
  CHART_COLORS.green,
  CHART_COLORS.orange,
  CHART_COLORS.purple,
  CHART_COLORS.yellow,
  CHART_COLORS.red,
  CHART_COLORS.neutral,
];

export default function CategoryBreakdownWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<CategoryBreakdownData>(
    token,
    'category_breakdown',
  );
  const cats = data?.categories ?? [];
  const rows = cats.map((c) => ({ name: c.label, hours: c.hours }));
  const height = Math.max(160, rows.length * 32 + 40);

  return (
    <WidgetShell title={title} isLoading={isLoading} isError={isError} isEmpty={rows.length === 0}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart layout="vertical" data={rows} margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={DARK_THEME.border} horizontal={false} />
          <XAxis type="number" stroke={DARK_THEME.textMuted} fontSize={12} />
          <YAxis
            type="category"
            dataKey="name"
            width={140}
            stroke={DARK_THEME.textMuted}
            fontSize={11}
          />
          <Tooltip
            formatter={(v) => [`${v} ч`, 'Часы']}
            contentStyle={{
              background: DARK_THEME.cardBg,
              border: `1px solid ${DARK_THEME.border}`,
              color: DARK_THEME.textPrimary,
            }}
          />
          <Bar dataKey="hours" radius={[0, 3, 3, 0]}>
            {rows.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </WidgetShell>
  );
}
