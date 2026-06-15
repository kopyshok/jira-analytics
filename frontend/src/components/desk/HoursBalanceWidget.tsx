import type { CSSProperties } from 'react';
import { Statistic } from 'antd';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtShortDate } from './format';
import { CHART_COLORS, DARK_THEME } from '../../utils/constants';
import type { HoursBalanceData } from '../../types/desk';

/** Часы с одним знаком и знаком ± для дельты. */
function fmtSigned(h: number): string {
  const r = Math.round(h * 10) / 10;
  return `${r > 0 ? '+' : ''}${r} ч`;
}

export default function HoursBalanceWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<HoursBalanceData>(token, 'hours_balance');
  const balance = data?.balance_hours ?? 0;
  const days = data?.days ?? [];

  // Накопительная дельта по дням для спарклайна.
  const series: Array<{ date: string; value: number }> = [];
  days.reduce((acc, d) => {
    const next = acc + d.delta;
    series.push({ date: d.date, value: Math.round(next * 10) / 10 });
    return next;
  }, 0);

  const positive = balance >= 0;
  const color = positive ? CHART_COLORS.green : CHART_COLORS.red;

  // Детализация под графиком: суммы переработки/недоработки и последние ненулевые дни.
  let overDays = 0;
  let overSum = 0;
  let underDays = 0;
  let underSum = 0;
  for (const d of days) {
    if (d.delta > 0) {
      overDays += 1;
      overSum += d.delta;
    } else if (d.delta < 0) {
      underDays += 1;
      underSum += d.delta;
    }
  }
  const recent = days
    .filter((d) => d.delta !== 0)
    .slice(-5)
    .reverse();

  const rowStyle: CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    fontSize: 13,
  };

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={days.length === 0}
    >
      <Statistic
        title={positive ? 'Наработано сверх нормы с начала года' : 'Недоработка с начала года'}
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
              labelFormatter={(v) => fmtShortDate(String(v))}
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

      <div
        style={{
          marginTop: 12,
          paddingTop: 12,
          borderTop: `1px solid ${DARK_THEME.border}`,
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}
      >
        <div style={rowStyle}>
          <span style={{ color: DARK_THEME.textSecondary }}>
            Дней переработки: {overDays}
          </span>
          <span style={{ color: CHART_COLORS.green, fontWeight: 600 }}>{fmtSigned(overSum)}</span>
        </div>
        <div style={rowStyle}>
          <span style={{ color: DARK_THEME.textSecondary }}>
            Дней недоработки: {underDays}
          </span>
          <span style={{ color: CHART_COLORS.red, fontWeight: 600 }}>{fmtSigned(underSum)}</span>
        </div>

        {recent.length > 0 && (
          <div style={{ marginTop: 6 }}>
            <div
              style={{
                fontSize: 11,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                color: DARK_THEME.textMuted,
                marginBottom: 4,
              }}
            >
              Последние дни
            </div>
            {recent.map((d) => (
              <div key={d.date} style={rowStyle}>
                <span style={{ color: DARK_THEME.textSecondary }}>{fmtShortDate(d.date)}</span>
                <span
                  style={{
                    color: d.delta > 0 ? CHART_COLORS.green : CHART_COLORS.red,
                    fontWeight: 600,
                  }}
                >
                  {fmtSigned(d.delta)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </WidgetShell>
  );
}
