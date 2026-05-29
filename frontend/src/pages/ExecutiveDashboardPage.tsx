import { useMemo, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Spin,
  Typography,
} from 'antd';
import {
  AlertOutlined,
  HeartOutlined,
  QuestionCircleOutlined,
  RocketOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import HelpDrawer from '../components/shared/HelpDrawer';
import executiveHelp from '../../../docs/help/executive.md?raw';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  buildDashboard,
  getDashboard,
  type ExecutiveDashboardResponse,
} from '../api/executive';
import KpiCard from '../components/executive/KpiCard';
import AISummary from '../components/executive/AISummary';
import ModuleHealth from '../components/executive/ModuleHealth';
import RiskList from '../components/executive/RiskList';
import { AiGate } from '../components/shared/AiGate';
import { useAiEnabled } from '../hooks/useAiEnabled';
import { useGlobalPeriod } from '../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { CHART_COLORS, DARK_THEME, FONTS } from '../utils/constants';

const PAGE_TITLE = 'Executive dashboard сопровождения 1С';

function dashboardKey(year: number, quarter: number, teams: string[]) {
  return ['executive-dashboard', year, quarter, [...teams].sort().join(',')] as const;
}

function formatGenerated(iso: string | undefined | null): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function kpiStatusFromHealth(value: number): 'good' | 'warn' | 'bad' {
  if (value >= 80) return 'good';
  if (value >= 60) return 'warn';
  return 'bad';
}

function kpiStatusFromUtil(value: number): 'good' | 'warn' | 'bad' {
  if (value > 100) return 'bad';
  if (value >= 70) return 'good';
  return 'warn';
}

function kpiStatusFromRiskCount(count: number): 'good' | 'warn' | 'bad' {
  if (count === 0) return 'good';
  if (count <= 3) return 'warn';
  return 'bad';
}

function kpiStatusFromPlanFact(pct: number): 'good' | 'warn' | 'bad' {
  if (pct >= 90) return 'good';
  if (pct >= 70) return 'warn';
  return 'bad';
}

const SectionLabel = ({ children }: { children: string }) => (
  <Typography.Text
    style={{
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      color: DARK_THEME.textHint,
      display: 'block',
      marginBottom: 8,
    }}
  >
    {children}
  </Typography.Text>
);

const ChartCard = ({
  title,
  children,
  height = 240,
}: {
  title: string;
  children: React.ReactNode;
  height?: number;
}) => (
  <Card
    style={{
      background: DARK_THEME.cardBg,
      border: `1px solid ${DARK_THEME.border}`,
      borderRadius: 8,
      height: '100%',
    }}
    styles={{ body: { padding: '14px 16px' } }}
  >
    <SectionLabel>{title}</SectionLabel>
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  </Card>
);

const TOOLTIP_STYLE = {
  background: DARK_THEME.darkAccent,
  border: `1px solid ${DARK_THEME.border}`,
  borderRadius: 6,
  fontSize: 12,
  color: DARK_THEME.textPrimary,
};

export default function ExecutiveDashboardPage() {
  const { message } = App.useApp();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();
  const qc = useQueryClient();
  const [helpOpen, setHelpOpen] = useState(false);

  const teamsKey = useMemo(() => [...selectedTeams].sort(), [selectedTeams]);

  const reportQuery = useQuery({
    queryKey: dashboardKey(period.year, period.quarter, teamsKey),
    queryFn: ({ signal }) => getDashboard(period.year, period.quarter, teamsKey, signal),
    staleTime: 60_000,
  });

  const buildMutation = useMutation({
    mutationFn: () => buildDashboard(period.year, period.quarter, teamsKey),
    onSuccess: (data: ExecutiveDashboardResponse) => {
      qc.setQueryData(dashboardKey(period.year, period.quarter, teamsKey), data);
      qc.invalidateQueries({ queryKey: ['executive-dashboard'] });
      message.success('Дашборд обновлён');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось построить: ${err?.message ?? 'Ошибка'}`);
    },
  });

  const report = reportQuery.data ?? null;
  const data = report?.data ?? null;
  const { enabled: aiEnabled } = useAiEnabled();

  const isInitialLoading = reportQuery.isLoading && !report;
  const isBuilding = buildMutation.isPending;

  const headerRight = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      {report ? (
        <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
          AI-сводка обновлена {formatGenerated(report.generated_at)}
        </Typography.Text>
      ) : null}
      <Button
        type="text"
        icon={<QuestionCircleOutlined />}
        onClick={() => setHelpOpen(true)}
        title="Справка по разделу"
      >
        Справка
      </Button>
      <AiGate>
        <Button
          type="primary"
          loading={isBuilding}
          onClick={() => buildMutation.mutate()}
        >
          {report ? 'Пересчитать' : 'Построить'}
        </Button>
      </AiGate>
    </div>
  );

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span
            style={{
              fontSize: 11,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              color: DARK_THEME.cyanPrimary,
              fontWeight: 600,
            }}
          >
            ОБЗОР
          </span>
          <Typography.Title
            level={1}
            style={{
              margin: 0,
              fontSize: 22,
              fontFamily: FONTS.display,
              fontWeight: 600,
              color: DARK_THEME.textPrimary,
              lineHeight: 1.2,
            }}
          >
            {PAGE_TITLE}
          </Typography.Title>
        </div>
        {headerRight}
      </div>

      <HelpDrawer
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title="Дашборд руководителя"
        content={executiveHelp}
        imageBase="/help-assets/"
      />

      {reportQuery.isError ? (
        <Alert
          type="error"
          showIcon
          message="Не удалось загрузить дашборд"
          description={(reportQuery.error as Error).message}
          style={{ marginBottom: 16 }}
        />
      ) : null}

      {isInitialLoading ? (
        <div style={{ display: 'grid', placeItems: 'center', minHeight: 300 }}>
          <Spin size="large" />
        </div>
      ) : !data ? (
        <Card
          style={{
            background: DARK_THEME.cardBg,
            border: `1px solid ${DARK_THEME.border}`,
            borderRadius: 8,
          }}
          styles={{ body: { padding: '32px 16px' } }}
        >
          <Empty
            description={
              <span style={{ color: DARK_THEME.textMuted }}>
                Нажмите «Построить» для генерации сводки за {period.year}Q{period.quarter}
              </span>
            }
          >
            <AiGate>
              <Button
                type="primary"
                loading={isBuilding}
                onClick={() => buildMutation.mutate()}
              >
                Построить
              </Button>
            </AiGate>
          </Empty>
        </Card>
      ) : (
        <>
          {/* KPI row */}
          <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={12} md={6}>
              <KpiCard
                icon={<HeartOutlined />}
                title="Индекс здоровья"
                value={`${data.kpi.health_index}/100`}
                status={kpiStatusFromHealth(data.kpi.health_index)}
                detail="Сводный показатель по критичности, возрасту, плану и нагрузке"
              />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <KpiCard
                icon={<ThunderboltOutlined />}
                title="Загрузка ресурса"
                value={`${data.kpi.resource_utilization_pct}%`}
                status={kpiStatusFromUtil(data.kpi.resource_utilization_pct)}
                detail="Средняя по ролям за квартал"
              />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <KpiCard
                icon={<AlertOutlined />}
                title="Критичные риски"
                value={String(data.kpi.critical_risks_count)}
                status={kpiStatusFromRiskCount(data.kpi.critical_risks_count)}
                detail="Открытые задачи Critical / Highest / Blocker"
              />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <KpiCard
                icon={<RocketOutlined />}
                title="Выполнение сценария"
                value={`${data.kpi.scenario_plan_fact_pct}%`}
                status={kpiStatusFromPlanFact(data.kpi.scenario_plan_fact_pct)}
                detail="Факт / план по утверждённому сценарию"
              />
            </Col>
          </Row>

          {/* AI summary */}
          {!aiEnabled && (
            <Alert
              type="info"
              showIcon
              message="ИИ выключен администратором — AI-сводка не обновляется"
              description="Показаны последние сгенерированные данные. Чтобы пересчитать, попросите администратора включить ИИ."
              style={{ marginBottom: 12 }}
            />
          )}
          <AISummary
            improved={data.ai_summary.improved}
            risk={data.ai_summary.risk}
            action={data.ai_summary.action}
            isFallback={data.ai_summary.is_fallback}
          />

          {/* Health trend */}
          <Card
            style={{
              background: DARK_THEME.cardBg,
              border: `1px solid ${DARK_THEME.border}`,
              borderRadius: 8,
              marginBottom: 16,
            }}
            styles={{ body: { padding: '14px 16px' } }}
          >
            <SectionLabel>Тренд здоровья (8 недель)</SectionLabel>
            <div style={{ width: '100%', height: 180 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.health_trend}>
                  <defs>
                    <linearGradient id="healthGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={DARK_THEME.cyanPrimary} stopOpacity={0.5} />
                      <stop offset="100%" stopColor={DARK_THEME.cyanPrimary} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={DARK_THEME.border} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="w"
                    stroke={DARK_THEME.textMuted}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis hide domain={[0, 100]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: DARK_THEME.border }} />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke={DARK_THEME.cyanPrimary}
                    strokeWidth={2}
                    fill="url(#healthGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Modules + Queue */}
          <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={12}>
              <ModuleHealth modules={data.modules} />
            </Col>
            <Col xs={24} lg={12}>
              <ChartCard title="Очередь по типам">
                <BarChart data={data.queue} layout="vertical">
                  <CartesianGrid stroke={DARK_THEME.border} strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" stroke={DARK_THEME.textMuted} tick={{ fontSize: 11 }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    stroke={DARK_THEME.textMuted}
                    tick={{ fontSize: 12 }}
                    width={110}
                  />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Legend wrapperStyle={{ fontSize: 11, color: DARK_THEME.textMuted }} />
                  <Bar dataKey="critical" name="Критичные" stackId="q" fill={CHART_COLORS.red} />
                  <Bar dataKey="high" name="Высокие" stackId="q" fill={CHART_COLORS.orange} />
                  <Bar dataKey="normal" name="Обычные" stackId="q" fill={CHART_COLORS.blue} />
                </BarChart>
              </ChartCard>
            </Col>
          </Row>

          {/* Plan/Fact + hours by type trend */}
          <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={12}>
              <ChartCard title="План / факт по ролям">
                <BarChart data={data.plan_fact_by_role}>
                  <CartesianGrid stroke={DARK_THEME.border} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="role"
                    stroke={DARK_THEME.textMuted}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis stroke={DARK_THEME.textMuted} tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Legend wrapperStyle={{ fontSize: 11, color: DARK_THEME.textMuted }} />
                  <Bar dataKey="plan" name="План" fill={CHART_COLORS.cyanSecondary} />
                  <Bar dataKey="fact" name="Факт" fill={CHART_COLORS.cyan} />
                </BarChart>
              </ChartCard>
            </Col>
            <Col xs={24} lg={12}>
              <ChartCard title="Часы по типам (8 недель)">
                <AreaChart data={data.hours_by_type_trend}>
                  <CartesianGrid stroke={DARK_THEME.border} strokeDasharray="3 3" />
                  <XAxis dataKey="w" stroke={DARK_THEME.textMuted} tick={{ fontSize: 11 }} />
                  <YAxis stroke={DARK_THEME.textMuted} tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: DARK_THEME.border }} />
                  <Legend wrapperStyle={{ fontSize: 11, color: DARK_THEME.textMuted }} />
                  <Area
                    type="monotone"
                    dataKey="incidents"
                    name="Инциденты"
                    stackId="hrs"
                    stroke={CHART_COLORS.red}
                    fill={CHART_COLORS.red}
                    fillOpacity={0.5}
                  />
                  <Area
                    type="monotone"
                    dataKey="improvements"
                    name="Доработки"
                    stackId="hrs"
                    stroke={CHART_COLORS.green}
                    fill={CHART_COLORS.green}
                    fillOpacity={0.5}
                  />
                  <Area
                    type="monotone"
                    dataKey="consultations"
                    name="Консультации"
                    stackId="hrs"
                    stroke={CHART_COLORS.blue}
                    fill={CHART_COLORS.blue}
                    fillOpacity={0.5}
                  />
                  <Area
                    type="monotone"
                    dataKey="regulatory"
                    name="Регламент"
                    stackId="hrs"
                    stroke={CHART_COLORS.purple}
                    fill={CHART_COLORS.purple}
                    fillOpacity={0.5}
                  />
                </AreaChart>
              </ChartCard>
            </Col>
          </Row>

          {/* Risks + capacity */}
          <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={16}>
              <RiskList risks={data.top_risks} />
            </Col>
            <Col xs={24} lg={8}>
              <Card
                style={{
                  background: DARK_THEME.cardBg,
                  border: `1px solid ${DARK_THEME.border}`,
                  borderRadius: 8,
                  height: '100%',
                }}
                styles={{ body: { padding: '14px 16px' } }}
              >
                <SectionLabel>Загрузка по ролям</SectionLabel>
                {data.capacity_by_role.length === 0 ? (
                  <Typography.Text style={{ color: DARK_THEME.textMuted, fontSize: 13 }}>
                    Нет данных
                  </Typography.Text>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {data.capacity_by_role.map((c) => {
                      const pct = c.utilization_pct;
                      const overload = pct > 100;
                      const colorPct = Math.min(100, Math.max(0, pct));
                      const fill = overload
                        ? DARK_THEME.danger
                        : pct >= 90
                          ? DARK_THEME.yellow
                          : DARK_THEME.cyanPrimary;
                      return (
                        <div key={c.role}>
                          <div
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              fontSize: 12,
                              color: DARK_THEME.textPrimary,
                              marginBottom: 4,
                            }}
                          >
                            <span>{c.role}</span>
                            <span style={{ color: fill, fontWeight: 600 }}>{pct}%</span>
                          </div>
                          <div
                            style={{
                              position: 'relative',
                              height: 8,
                              background: DARK_THEME.darkRows,
                              borderRadius: 4,
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                position: 'absolute',
                                inset: 0,
                                transform: `scaleX(${colorPct / 100})`,
                                transformOrigin: 'left',
                                background: fill,
                                transition: 'transform 200ms ease',
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Card>
            </Col>
          </Row>
        </>
      )}
    </div>
  );
}
