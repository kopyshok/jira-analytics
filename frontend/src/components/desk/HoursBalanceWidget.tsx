import { Statistic } from 'antd';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtDate } from './format';
import { CHART_COLORS, DARK_THEME } from '../../utils/constants';
import type { HoursBalanceData } from '../../types/desk';

export default function HoursBalanceWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<HoursBalanceData>(token, 'hours_balance');
  const balance = data?.balance_hours ?? 0;
  const days = data?.days ?? [];

  // Накопительная дельта по дням для спарклайна.
  let acc = 0;
  const series = days.map((d) => {
    acc += d.delta;
    return { date: d.date, value: Math.round(acc * 10) / 10 };
  });

  const positive = balance >= 0;
  const color = positive ? CHART_COLORS.green : CHART_COLORS.red;

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={days.length === 0}
    >
      <Statistic
        title="Баланс часов с начала года"
        value={balance}
        precision={1}
        suffix="ч"
        valueStyle={{ color }}
      />
      {series.length > 0 && (
        <ResponsiveContainer width="100%" height={120}>
          <LineChart data={series} margin={{ top: 12, right: 8, left: 8, bottom: 0 }}>
            <XAxis dataKey="date" hide />
            <Tooltip
              labelFormatter={(v) => fmtDate(String(v))}
              formatter={(v) => [`${v} ч`, 'Накоплено']}
              contentStyle={{
                background: DARK_THEME.cardBg,
                border: `1px solid ${DARK_THEME.border}`,
                color: DARK_THEME.textPrimary,
              }}
            />
            <Line type="monotone" dataKey="value" stroke={color} dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </WidgetShell>
  );
}
