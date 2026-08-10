import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Empty, Progress, Spin, Tag, Typography } from 'antd';
import {
  CheckCircleFilled, CheckCircleOutlined, CloseCircleFilled, LockOutlined, WarningFilled,
} from '@ant-design/icons';
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import {
  fetchApproval, fetchTrend,
  type KpiReportRow, type KpiTeamSummaryRow,
} from '../../api/kpi';
import { formatDateOnly } from '../../utils/format';
import { kpiStatusOf, onKpiCellActivate, KPI_MONTH_ABBR_RU, type KpiStatus } from '../../utils/kpiShared';

const { Text } = Typography;

const TREND_MONTHS = 12;

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

export interface KpiEmployeeTabProps {
  row: KpiReportRow;
  year: number;
  month: number;
  /** Длина периода отчёта в месяцах — карточка подписывает тот же период. */
  months?: number;
  direction?: string;
  /** Команды, с которыми запрошен отчёт (глобальный фильтр) — тренд считается
   * тем же отбором, что и ведомость, иначе последняя точка графика может не
   * совпасть с числом в кольце (см. ревью, BLOCKER 3). */
  teams?: string;
  /** Сводка команды: средние по метрикам и норматив Cycle Time на квартал. */
  teamSummary?: KpiTeamSummaryRow;
  /** Место в команде по итогу и сколько всего оценённых людей. */
  rank?: { place: number; of: number };
  onOpenBreakdown: (metricCode: string, metricName: string) => void;
}

/**
 * Сотрудник — вкладкой внутри раздела, а не боковым окном.
 *
 * В узкое окно не помещалось то, ради чего карточку и открывают в разговоре
 * с человеком: вклад каждой метрики в итог в процентных пунктах, сравнение со
 * средним по команде и честный ответ, почему половина метрик пустая (спека
 * доработок 2026-08-03, раздел 7).
 */
export default function KpiEmployeeTab({
  row, year, month, months = 1, direction, teams, teamSummary, rank, onOpenBreakdown,
}: KpiEmployeeTabProps) {
  const t = useThemeTokens();

  const trendQuery = useQuery({
    queryKey: ['kpi', 'trend', row.account_id, year, month, teams, direction, TREND_MONTHS],
    queryFn: ({ signal }) => fetchTrend(
      { account_id: row.account_id, year, month, months: TREND_MONTHS, teams, direction },
      signal,
    ),
  });

  // Утверждается квартал целиком, поэтому и признак заморозки читается по
  // кварталу, которому принадлежит конечный месяц периода.
  const quarter = Math.floor((month - 1) / 3) + 1;
  const approvalQuery = useQuery({
    queryKey: ['kpi', 'approval', row.team, year, quarter],
    queryFn: ({ signal }) => fetchApproval(row.team as string, year, quarter, signal),
    enabled: !!row.team,
  });

  const statusColor = (s: KpiStatus) => (
    s === 'good' ? t.success : s === 'warn' ? t.amber : s === 'bad' ? t.danger : t.textMuted
  );

  const total = row.total;
  const target = row.target_pct;
  const ringStatus = kpiStatusOf(total, target, row.warn_band_pct);

  const points = trendQuery.data?.points ?? [];
  const trendData = points.map((p) => ({
    label: `${KPI_MONTH_ABBR_RU[p.month - 1]} ${String(p.year).slice(2)}`,
    total: p.total,
  }));
  // Дельта к прошлому месяцу — из того же тренда, отдельный запрос не нужен.
  // На периоде длиннее месяца её не показываем: график остаётся помесячным, а
  // итог карточки — за весь период, и вычитать одно из другого нельзя.
  const previous = points.length > 1 ? points[points.length - 2].total : null;
  const delta = months === 1 && previous != null && total != null ? total - previous : null;

  const withData = row.metrics.filter((m) => m.has_data && m.value != null);
  const usableWeight = withData.reduce((s, m) => s + m.weight, 0);
  const noDataCount = row.metrics.length - withData.length;

  const teamMetricValue = (code: string) => {
    const m = teamSummary?.metrics.find((x) => x.code === code);
    return m?.has_data ? m.value : null;
  };

  // Что мешает считать: конкретные причины пустых метрик, а не «нет данных».
  const blockers: string[] = [];
  if (row.metrics.some((m) => m.code === 'cycle_time' && !m.has_data)
      && teamSummary && teamSummary.cycle_time_norm == null) {
    blockers.push('Норматив Cycle Time на этот квартал не задан — метрика не считается ни у кого в команде.');
  }
  for (const m of row.metrics) {
    if (m.has_data) continue;
    if (teamMetricValue(m.code) == null && m.code !== 'cycle_time') {
      blockers.push(`«${m.name}» пуста у всей команды, а не только у этого сотрудника.`);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Card size="small">
        <div style={{ display: 'flex', alignItems: 'center', gap: 22, flexWrap: 'wrap' }}>
          <Progress
            type="circle"
            percent={total != null ? Math.round(total) : 0}
            size={104}
            format={() => (total != null ? `${Math.round(total)}%` : '—')}
            strokeColor={statusColor(ringStatus)}
          />
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 20, fontWeight: 600 }}>{row.employee_name}</div>
            <Text type="secondary" style={{ fontSize: 12.5 }}>
              {row.team ?? 'без команды'}
              {row.profile_name ? ` · профиль «${row.profile_name}»` : ''}
              {months > 1
                ? ` · ${KPI_MONTH_ABBR_RU[(((month - months) % 12) + 12) % 12]}–${KPI_MONTH_ABBR_RU[month - 1]} ${year}`
                : ` · ${KPI_MONTH_ABBR_RU[month - 1]} ${year}`}
            </Text>
            <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginTop: 10, fontSize: 12.5 }}>
              {months === 1 && (
                <span>
                  <Text type="secondary">К прошлому месяцу </Text>
                  {delta == null ? '—' : (
                    <b className="num" style={{ color: delta >= 0 ? t.success : t.danger }}>
                      {delta > 0 ? '+' : ''}{delta.toFixed(1)} п.п.
                    </b>
                  )}
                </span>
              )}
              {rank && (
                <span>
                  <Text type="secondary">В команде </Text>
                  <b className="num">{rank.place}-й из {rank.of}</b>
                </span>
              )}
              {teamSummary?.avg_total != null && (
                <span>
                  <Text type="secondary">Среднее команды </Text>
                  <b className="num">{Math.round(teamSummary.avg_total)}%</b>
                </span>
              )}
              <span>
                <Text type="secondary">Метрик без данных </Text>
                <b className="num">{noDataCount} из {row.metrics.length}</b>
              </span>
            </div>
          </div>
          <div
            style={{
              display: 'flex', alignItems: 'center', gap: 7, fontSize: 12,
              background: t.darkAccent, border: `1px solid ${t.border}`, borderRadius: 10,
              padding: '9px 12px', color: approvalQuery.data?.approved ? t.success : t.textMuted,
            }}
          >
            {approvalQuery.data?.approved ? <CheckCircleOutlined /> : <LockOutlined />}
            {row.team == null
              ? 'Утверждение доступно только для сотрудника с командой'
              : approvalQuery.data?.approved
                ? `Утвердил ${approvalQuery.data.approved_by} · ${formatDateOnly(approvalQuery.data.approved_at)}`
                : 'Квартал не утверждён'}
          </div>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 14 }}>
        <Card size="small" title={`Тренд за ${TREND_MONTHS} месяцев`}>
          <div style={{ width: '100%', height: 210 }}>
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
        </Card>

        <Card size="small" title={total != null ? `Из чего сложился итог ${Math.round(total)}%` : 'Из чего сложился итог'}>
          {/* Вклад метрики в итог: её значение, умноженное на долю веса среди
              метрик с данными. «67%» само по себе не говорит, сколько это
              стоило в итоге, — а разговор с сотрудником идёт именно об этом. */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {row.metrics.map((m) => {
              const share = usableWeight > 0 ? m.weight / usableWeight : 0;
              const contribution = m.has_data && m.value != null ? m.value * share : null;
              const maxContribution = share * 100;
              return (
                <div
                  key={m.code}
                  style={{ display: 'grid', gridTemplateColumns: '160px minmax(0,1fr) 62px', gap: 9, alignItems: 'center' }}
                >
                  <span style={{ fontSize: 12, color: contribution == null ? t.textMuted : undefined }}>
                    {m.name}
                  </span>
                  <span style={{ height: 11, borderRadius: 3, background: t.darkRows, position: 'relative', overflow: 'hidden' }}>
                    {contribution != null && (
                      <span
                        style={{
                          position: 'absolute', inset: 0, borderRadius: 3,
                          width: `${maxContribution > 0 ? (contribution / maxContribution) * 100 : 0}%`,
                          background: statusColor(kpiStatusOf(m.value, row.target_pct, row.warn_band_pct)),
                          opacity: 0.85,
                        }}
                      />
                    )}
                  </span>
                  <span className="num" style={{ textAlign: 'right', fontSize: 12, color: contribution == null ? t.textMuted : undefined }}>
                    {contribution == null ? 'вес роздан' : contribution.toFixed(1)}
                  </span>
                </div>
              );
            })}
          </div>
          {noDataCount > 0 && (
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 10 }}>
              {noDataCount} метрик без данных, их вес распределён между остальными.
            </Text>
          )}
        </Card>
      </div>

      <Card size="small" title="Разбор по метрикам · клик открывает расчёт">
        {row.metrics.length === 0 && <Empty description="У сотрудника нет профиля оценки" />}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 10 }}>
          {row.metrics.map((m) => {
            const status = kpiStatusOf(m.value, row.target_pct, row.warn_band_pct);
            const activate = () => onOpenBreakdown(m.code, m.name);
            const teamValue = teamMetricValue(m.code);
            return (
              <div
                key={m.code}
                role="button"
                tabIndex={0}
                onClick={activate}
                onKeyDown={onKpiCellActivate(activate)}
                style={{
                  border: `1px solid ${t.border}`, borderRadius: 11, padding: '11px 13px',
                  background: t.darkAccent, cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 600 }}>{m.name}</span>
                  <span className="num" style={{ fontWeight: 700, color: statusColor(status), display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    {m.has_data ? (
                      <>
                        <StatusIcon status={status} />
                        {Math.round(m.value ?? 0)}%
                      </>
                    ) : <Tag style={{ margin: 0 }}>нет данных</Tag>}
                  </span>
                </div>

                {m.has_data ? (
                  <>
                    <div style={{ height: 6, borderRadius: 999, background: t.darkRows, marginTop: 8, position: 'relative' }}>
                      <div
                        style={{
                          height: '100%', borderRadius: 999,
                          width: `${Math.min(100, Math.max(0, m.value ?? 0))}%`,
                          background: statusColor(status),
                        }}
                      />
                      {/* Маркер цели на полосе — из макета. */}
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
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 7, fontSize: 11.5, color: t.textMuted }}>
                      {m.numerator != null && m.denominator != null && (
                        <span className="num">{m.numerator} / {m.denominator}</span>
                      )}
                      <span>вес {Math.round(m.weight * 100)}%</span>
                      {teamValue != null && <span>в команде {Math.round(teamValue)}%</span>}
                    </div>
                  </>
                ) : (
                  <Text type="secondary" style={{ fontSize: 11.5, display: 'block', marginTop: 7 }}>
                    {emptyPolicyText(m.empty_policy ?? row.empty_policy, Math.round(m.weight * 100))}
                  </Text>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {blockers.length > 0 && (
        <Card size="small" title="Что мешает считать">
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: t.textMuted }}>
            {blockers.map((b) => <li key={b} style={{ marginBottom: 3 }}>{b}</li>)}
          </ul>
        </Card>
      )}
    </div>
  );
}
