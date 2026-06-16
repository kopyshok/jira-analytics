import { Area, AreaChart, ResponsiveContainer, Tooltip } from 'recharts';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtDayWithWeekday, fmtShortDate, fmtSignedHours } from './format';
import type { HoursBalanceData } from '../../types/desk';

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
  const lineColor = positive ? 'var(--green)' : 'var(--red)';

  let overDays = 0;
  let overSum = 0;
  let underDays = 0;
  let underSum = 0;
  for (const d of days) {
    if (d.delta > 0) { overDays += 1; overSum += d.delta; }
    else if (d.delta < 0) { underDays += 1; underSum += d.delta; }
  }
  const recent = days.filter((d) => d.delta !== 0).slice(-5).reverse();

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={days.length === 0}
    >
      <div className={`desk-overwork-big ${positive ? 'positive' : 'negative'}`}>
        {fmtSignedHours(balance)}
      </div>
      <div className="desk-overwork-desc">
        {positive ? 'наработано сверх нормы с 1 января' : 'недоработка с 1 января'}
      </div>

      {series.length > 0 && (
        <div className="desk-spark-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="deskSparkGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={lineColor} stopOpacity={0.24} />
                  <stop offset="100%" stopColor={lineColor} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <Tooltip
                labelFormatter={(v) => fmtShortDate(String(v))}
                formatter={(v) => [`${v} ч`, 'Накоплено']}
                contentStyle={{
                  background: 'var(--surface)',
                  border: '1px solid var(--hair)',
                  borderRadius: 8,
                  color: 'var(--ink)',
                  fontSize: 12,
                }}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={lineColor}
                strokeWidth={2}
                fill="url(#deskSparkGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="desk-detail">
        <div className="desk-detail-row">
          <span className="label">Дней переработки</span>
          <span className="desk-val-green">{overDays} дн. ({fmtSignedHours(overSum)})</span>
        </div>
        <div className="desk-detail-row">
          <span className="label">Дней недоработки</span>
          <span className="desk-val-red">{underDays} дн. ({fmtSignedHours(underSum)})</span>
        </div>
      </div>

      {recent.length > 0 && (
        <div>
          <div className="desk-rd-title">Последние дни</div>
          {recent.map((d) => (
            <div key={d.date} className="desk-rd-item">
              <span className="desk-rd-date">{fmtDayWithWeekday(d.date)}</span>
              <span className={d.delta > 0 ? 'desk-rd-plus' : 'desk-rd-minus'}>
                {fmtSignedHours(d.delta)}
              </span>
            </div>
          ))}
        </div>
      )}
    </WidgetShell>
  );
}
