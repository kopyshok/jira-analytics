import { useQuery } from '@tanstack/react-query';
import { Drawer, Progress, Space, Tag, Typography, Empty, Spin } from 'antd';
import { LockOutlined, CheckCircleOutlined } from '@ant-design/icons';
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import { fetchApproval, fetchTrend, type KpiReportRow } from '../../api/kpi';
import { formatDate } from '../../utils/format';

const { Text, Title } = Typography;

const MONTH_ABBR = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

type Status = 'good' | 'warn' | 'bad' | 'none';

function statusOf(value: number | null, target: number | null, warnBand: number | null): Status {
  if (value == null || target == null) return 'none';
  if (value >= target) return 'good';
  const band = warnBand ?? 10;
  if (value >= target - band) return 'warn';
  return 'bad';
}

export interface KpiEmployeeCardProps {
  row: KpiReportRow | null;
  year: number;
  month: number;
  direction?: string;
  onClose: () => void;
  onOpenBreakdown: (metricCode: string, metricName: string) => void;
}

export default function KpiEmployeeCard({
  row, year, month, direction, onClose, onOpenBreakdown,
}: KpiEmployeeCardProps) {
  const t = useThemeTokens();

  const trendQuery = useQuery({
    queryKey: ['kpi', 'trend', row?.account_id, year, month, row?.team, direction],
    queryFn: ({ signal }) => fetchTrend(
      {
        account_id: row!.account_id, year, month, months: 6,
        teams: row?.team ?? undefined, direction,
      },
      signal,
    ),
    enabled: !!row,
  });

  const approvalQuery = useQuery({
    queryKey: ['kpi', 'approval', row?.team, year, month],
    queryFn: ({ signal }) => fetchApproval(row!.team as string, year, month, signal),
    enabled: !!row?.team,
  });

  const statusColor = (s: Status) => (
    s === 'good' ? t.success : s === 'warn' ? t.amber : s === 'bad' ? t.danger : t.textMuted
  );

  const total = row?.total ?? null;
  const target = row?.target_pct ?? null;
  const ringStatus = statusOf(total, target, row?.warn_band_pct ?? null);

  const trendData = (trendQuery.data?.points ?? []).map((p) => ({
    label: `${MONTH_ABBR[p.month - 1]} ${String(p.year).slice(2)}`,
    total: p.total,
  }));

  return (
    <Drawer
      title={row ? row.employee_name : ''}
      open={!!row}
      onClose={onClose}
      width={460}
      destroyOnHidden
    >
      {row && (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          <Text type="secondary" style={{ fontSize: 12.5 }}>
            {row.team ?? 'без команды'}
            {row.profile_code ? ` · профиль «${row.profile_code}»` : ''}
            {` · ${MONTH_ABBR[month - 1]} ${year}`}
          </Text>

          <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            <Progress
              type="circle"
              percent={total != null ? Math.round(total) : 0}
              size={88}
              format={() => (total != null ? `${Math.round(total)}` : '—')}
              strokeColor={statusColor(ringStatus)}
            />
            <div>
              <Title level={3} style={{ margin: 0, color: statusColor(ringStatus) }}>
                {total != null ? `${Math.round(total)}%` : '—'}
              </Title>
              <Text type="secondary" style={{ fontSize: 12 }}>
                коэффициент эффективности{target != null ? ` · цель ${target}%` : ''}
                {row.metrics.some((m) => !m.has_data) ? ' · есть метрика без данных' : ''}
              </Text>
            </div>
          </div>

          <div>
            <Text strong style={{ fontSize: 13 }}>Тренд за 6 месяцев</Text>
            <div style={{ width: '100%', height: 170, marginTop: 6 }}>
              {trendQuery.isLoading ? (
                <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}><Spin /></div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData}>
                    <CartesianGrid stroke={t.border} strokeDasharray="3 3" />
                    <XAxis dataKey="label" stroke={t.textMuted} tick={{ fontSize: 10.5 }} />
                    <YAxis domain={[0, 100]} stroke={t.textMuted} tick={{ fontSize: 10.5 }} width={30} />
                    <Tooltip
                      contentStyle={{ background: t.cardBg, border: `1px solid ${t.border}`, fontSize: 12 }}
                      formatter={(v) => (v == null ? 'нет данных' : `${Math.round(Number(v))}%`)}
                    />
                    {target != null && (
                      <ReferenceLine
                        y={target}
                        stroke={t.textMuted}
                        strokeDasharray="3 4"
                        label={{ value: `цель ${target}%`, position: 'insideTopRight', fontSize: 10, fill: t.textMuted }}
                      />
                    )}
                    <Line type="monotone" dataKey="total" stroke={t.cyanPrimary} strokeWidth={2} dot connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div
            style={{
              display: 'flex', alignItems: 'center', gap: 7, fontSize: 12,
              background: t.darkAccent, border: `1px solid ${t.border}`, borderRadius: 10, padding: '9px 12px',
              color: approvalQuery.data?.approved ? t.success : t.textMuted,
            }}
          >
            {approvalQuery.data?.approved ? <CheckCircleOutlined /> : <LockOutlined />}
            {row.team == null
              ? 'Утверждение доступно только для сотрудника с командой'
              : approvalQuery.data?.approved
                ? `Утвердил ${approvalQuery.data.approved_by} · ${formatDate(approvalQuery.data.approved_at)}`
                : 'Месяц не утверждён'}
          </div>

          <div>
            <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>Разбор по метрикам</Text>
            {row.metrics.length === 0 && <Empty description="У сотрудника нет профиля оценки" />}
            <Space orientation="vertical" size={4} style={{ width: '100%' }}>
              {row.metrics.map((m) => {
                const status = statusOf(m.value, row.target_pct, row.warn_band_pct);
                return (
                  <div
                    key={m.code}
                    role="button"
                    tabIndex={0}
                    onClick={() => onOpenBreakdown(m.code, m.name)}
                    style={{
                      display: 'grid', gridTemplateColumns: '1fr auto', gap: 8,
                      alignItems: 'center', padding: '8px 0', borderBottom: `1px solid ${t.border}`,
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600 }}>{m.name}</div>
                      {!m.has_data ? (
                        <Text type="secondary" style={{ fontSize: 10.5 }}>
                          Вес {(m.weight * 100).toFixed(0)}% перераспределён между остальными метриками
                        </Text>
                      ) : (
                        <div style={{ height: 6, borderRadius: 999, background: t.darkRows, marginTop: 4, position: 'relative' }}>
                          <div
                            style={{
                              height: '100%', borderRadius: 999,
                              width: `${Math.min(100, Math.max(0, m.value ?? 0))}%`,
                              background: statusColor(status),
                            }}
                          />
                        </div>
                      )}
                    </div>
                    <span className="num" style={{ fontWeight: 700, color: statusColor(status) }}>
                      {m.has_data ? `${Math.round(m.value ?? 0)}%` : <Tag style={{ margin: 0 }}>нет данных</Tag>}
                    </span>
                  </div>
                );
              })}
            </Space>
          </div>
        </Space>
      )}
    </Drawer>
  );
}
