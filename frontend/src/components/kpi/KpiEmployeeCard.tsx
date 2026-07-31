import { useQuery } from '@tanstack/react-query';
import { Drawer, Progress, Space, Tag, Typography, Empty, Spin, Alert, Button } from 'antd';
import { LockOutlined, CheckCircleOutlined, CheckCircleFilled, WarningFilled, CloseCircleFilled } from '@ant-design/icons';
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import { fetchApproval, fetchTrend, type KpiReportRow } from '../../api/kpi';
import { formatDateOnly } from '../../utils/format';
import { kpiStatusOf, onKpiCellActivate, KPI_MONTH_ABBR_RU, type KpiStatus } from '../../utils/kpiShared';

const { Text, Title } = Typography;

/** Текст про метрику без данных — по применённой политике, а не всегда
 * «перераспределён» (политика настраивается в общих правилах, доступных
 * только администратору — фронт не может считать её всегда одной и той же,
 * см. ревью, ВАЖНО 9). */
function emptyPolicyText(policy: string, weightPct: number): string {
  if (policy === 'full') return 'Нет данных — метрика считается выполненной на 100%';
  if (policy === 'zero') return 'Нет данных — метрика считается невыполненной, 0%';
  return `Вес ${weightPct}% перераспределён между остальными метриками`;
}

/** Значок статуса — цвет не единственный сигнал (см. ревью, мелочи). */
function StatusIcon({ status }: { status: KpiStatus }) {
  if (status === 'good') return <CheckCircleFilled style={{ fontSize: 11 }} />;
  if (status === 'warn') return <WarningFilled style={{ fontSize: 11 }} />;
  if (status === 'bad') return <CloseCircleFilled style={{ fontSize: 11 }} />;
  return null;
}

export interface KpiEmployeeCardProps {
  row: KpiReportRow | null;
  year: number;
  month: number;
  direction?: string;
  /** Команды, с которыми запрошен отчёт (глобальный фильтр) — тренд считается
   * тем же отбором, что и ведомость, иначе последняя точка графика может не
   * совпасть с числом в кольце (см. ревью, BLOCKER 3). */
  teams?: string;
  onClose: () => void;
  onOpenBreakdown: (metricCode: string, metricName: string) => void;
}

export default function KpiEmployeeCard({
  row, year, month, direction, teams, onClose, onOpenBreakdown,
}: KpiEmployeeCardProps) {
  const t = useThemeTokens();

  const trendQuery = useQuery({
    queryKey: ['kpi', 'trend', row?.account_id, year, month, teams, direction],
    queryFn: ({ signal }) => fetchTrend(
      {
        account_id: row!.account_id, year, month, months: 6,
        teams, direction,
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

  const statusColor = (s: KpiStatus) => (
    s === 'good' ? t.success : s === 'warn' ? t.amber : s === 'bad' ? t.danger : t.textMuted
  );

  const total = row?.total ?? null;
  const target = row?.target_pct ?? null;
  const ringStatus = kpiStatusOf(total, target, row?.warn_band_pct ?? null);

  const trendData = (trendQuery.data?.points ?? []).map((p) => ({
    label: `${KPI_MONTH_ABBR_RU[p.month - 1]} ${String(p.year).slice(2)}`,
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
            {row.profile_name ? ` · профиль «${row.profile_name}»` : ''}
            {` · ${KPI_MONTH_ABBR_RU[month - 1]} ${year}`}
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
              ) : trendQuery.isError ? (
                <Alert
                  type="error"
                  showIcon
                  title="Не удалось загрузить тренд"
                  description={(trendQuery.error as Error).message}
                  action={<Button size="small" onClick={() => trendQuery.refetch()}>Повторить</Button>}
                />
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
                ? `Утвердил ${approvalQuery.data.approved_by} · ${formatDateOnly(approvalQuery.data.approved_at)}`
                : 'Месяц не утверждён'}
          </div>

          <div>
            <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>Разбор по метрикам</Text>
            {row.metrics.length === 0 && <Empty description="У сотрудника нет профиля оценки" />}
            <Space orientation="vertical" size={4} style={{ width: '100%' }}>
              {row.metrics.map((m) => {
                const status = kpiStatusOf(m.value, row.target_pct, row.warn_band_pct);
                const activate = () => onOpenBreakdown(m.code, m.name);
                return (
                  <div
                    key={m.code}
                    role="button"
                    tabIndex={0}
                    onClick={activate}
                    onKeyDown={onKpiCellActivate(activate)}
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
                          {emptyPolicyText(row.empty_policy, Math.round(m.weight * 100))}
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
                          {/* Маркер цели на полосе — из макета, раньше не был перенесён. */}
                          {row.target_pct != null && (
                            <div
                              title={`цель ${row.target_pct}%`}
                              style={{
                                position: 'absolute', top: -2, bottom: -2,
                                left: `${Math.min(100, Math.max(0, row.target_pct))}%`,
                                width: 2, background: t.textMuted, borderRadius: 1,
                              }}
                            />
                          )}
                        </div>
                      )}
                    </div>
                    <span className="num" style={{ fontWeight: 700, color: statusColor(status), display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      {m.has_data ? (
                        <>
                          <StatusIcon status={status} />
                          {Math.round(m.value ?? 0)}%
                        </>
                      ) : <Tag style={{ margin: 0 }}>нет данных</Tag>}
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
