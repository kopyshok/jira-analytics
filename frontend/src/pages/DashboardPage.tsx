import { useState } from 'react';
import { Card, Row, Col, Spin, Empty, Table, Tag, Collapse, Space, Select, Button, App } from 'antd';
import {
  ClockCircleOutlined,
  TeamOutlined,
  ProjectOutlined,
  SwapOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import { useNavigate } from 'react-router';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  BarChart, Bar,
} from 'recharts';
import DateRangeSelect from '../components/shared/DateRangeSelect';
import ExportButtons from '../components/shared/ExportButtons';
import PageHeader from '../components/shared/PageHeader';
import KpiCard from '../components/shared/KpiCard';
import { useSyncStatus, useSyncMutation } from '../hooks/useSync';
import {
  useHoursByCategory,
  useHoursByPeriod,
  useHoursByEmployee,
  useHoursByProject,
  useContextSwitching,
  useEmployeesForFilter,
  useProjectsForFilter,
} from '../hooks/useAnalytics';
import { downloadAnalyticsXlsx, downloadAnalyticsPdf } from '../api/exports';
import { CHART_COLORS, DARK_THEME } from '../utils/constants';
import { useCategories } from '../hooks/useCategories';
import { formatHours, formatDate } from '../utils/format';
import type { SyncStatusResponse } from '../types/api';

const tooltipFmt = (v: unknown) => formatHours(Number(v)) + ' ч';

export default function DashboardPage() {
  const { notification } = App.useApp();
  const navigate = useNavigate();
  const [dates, setDates] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const { labels: catLabels, colors: catColors } = useCategories();
  const [employeeId, setEmployeeId] = useState<string | undefined>();
  const [projectKey, setProjectKey] = useState<string | undefined>();

  const start = dates?.[0]?.format('YYYY-MM-DD');
  const end = dates?.[1]?.format('YYYY-MM-DD');

  const { data: filterEmployees } = useEmployeesForFilter();
  const { data: filterProjects } = useProjectsForFilter();
  const hasFilters = !!employeeId || !!projectKey || !!dates;

  const { data: syncStatus, isLoading: syncLoading } = useSyncStatus();
  const syncFull = useSyncMutation('full');
  const { data: categories } = useHoursByCategory(start, end, employeeId, projectKey);
  const { data: trend } = useHoursByPeriod('week', start, end, employeeId, projectKey);
  const { data: employees } = useHoursByEmployee(start, end, employeeId, projectKey);
  const { data: projects } = useHoursByProject(start, end, employeeId, projectKey);
  const { data: switching } = useContextSwitching(start, end, employeeId, projectKey);

  const totalHours = categories?.reduce((s, r) => s + r.total_hours, 0) ?? 0;
  const employeeCount = employees?.length ?? 0;
  const projectCount = projects?.length ?? 0;
  const avgSwitches = switching?.length
    ? switching.reduce((s, r) => s + r.switches, 0) / switching.length
    : 0;

  const trendSeries = trend?.map(t => t.total_hours) ?? [];
  const hoursDelta = (() => {
    if (trendSeries.length < 4) return null;
    const half = Math.floor(trendSeries.length / 2);
    const first = trendSeries.slice(0, half).reduce((a, b) => a + b, 0);
    const last = trendSeries.slice(half).reduce((a, b) => a + b, 0);
    if (first === 0) return null;
    const pct = ((last - first) / first) * 100;
    const dir = Math.abs(pct) < 1 ? 'flat' : pct > 0 ? 'up' : 'down';
    return { value: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`, direction: dir as 'up' | 'down' | 'flat' };
  })();

  const pieData = categories?.map((d) => ({
    ...d,
    label: catLabels[d.key] || d.label,
    fill: catColors[d.key] || '#8884d8',
  }));

  const top5employees = employees
    ?.slice()
    .sort((a, b) => b.total_hours - a.total_hours)
    .slice(0, 5);

  const top5projects = projects
    ?.slice()
    .sort((a, b) => b.total_hours - a.total_hours)
    .slice(0, 5);

  return (
    <div>
      <PageHeader
        eyebrow="Обзор"
        title="Дашборд"
        subtitle={
          totalHours > 0
            ? `${formatHours(totalHours)} ч · ${employeeCount} сотрудников · ${projectCount} проектов`
            : 'Нет данных за выбранный период'
        }
      />
      {/* Filters */}
      <Space wrap style={{ marginBottom: 24 }}>
        <DateRangeSelect value={dates} onChange={setDates} />
        <Select
          allowClear
          placeholder="Все сотрудники"
          style={{ minWidth: 180 }}
          value={employeeId}
          onChange={setEmployeeId}
          options={filterEmployees?.map(e => ({ value: e.id, label: e.display_name }))}
          showSearch
          optionFilterProp="label"
        />
        <Select
          allowClear
          placeholder="Все проекты"
          style={{ minWidth: 160 }}
          value={projectKey}
          onChange={setProjectKey}
          options={filterProjects?.map(p => ({ value: p.key, label: p.name }))}
          showSearch
          optionFilterProp="label"
        />
        {hasFilters && (
          <Button onClick={() => { setEmployeeId(undefined); setProjectKey(undefined); setDates(null); }}>
            Сбросить
          </Button>
        )}
        <ExportButtons
          onXlsx={() => downloadAnalyticsXlsx(start, end)}
          onPdf={() => downloadAnalyticsPdf(start, end)}
        />
        <Button
          icon={<SyncOutlined spin={syncFull.isPending} />}
          loading={syncFull.isPending}
          onClick={() => syncFull.mutate(undefined, {
            onSuccess: (res) => notification.success({ title: 'Синхронизация завершена', description: res.message }),
            onError: (e) => notification.error({ title: 'Ошибка синхронизации', description: e.message }),
          })}
        >
          Синхронизация
        </Button>
      </Space>

      {/* KPI cards — clickable, navigate to analytics tab */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            eyebrow="Всего часов"
            value={formatHours(totalHours)}
            suffix="ч"
            icon={<ClockCircleOutlined />}
            series={trendSeries.length >= 2 ? trendSeries : undefined}
            delta={hoursDelta}
            onClick={() => navigate('/analytics?tab=category')}
            accent={DARK_THEME.cyanPrimary}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            eyebrow="Сотрудников"
            value={employeeCount}
            icon={<TeamOutlined />}
            onClick={() => navigate('/analytics?tab=employee')}
            accent={CHART_COLORS.cyanSecondary}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            eyebrow="Проектов"
            value={projectCount}
            icon={<ProjectOutlined />}
            onClick={() => navigate('/analytics?tab=project')}
            accent={CHART_COLORS.green}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            eyebrow="Ср. переключений"
            value={avgSwitches.toFixed(1)}
            icon={<SwapOutlined />}
            onClick={() => navigate('/analytics?tab=switching')}
            accent={CHART_COLORS.purple}
          />
        </Col>
      </Row>

      {/* Top-5 employees & Top-5 projects */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="Топ-5 сотрудников по часам">
            {top5employees?.length ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={top5employees} layout="vertical" margin={{ left: 20 }}>
                  <defs>
                    <linearGradient id="grad-employees" x1="0" x2="1" y1="0" y2="0">
                      <stop offset="0%" stopColor={CHART_COLORS.blue} stopOpacity={0.25} />
                      <stop offset="100%" stopColor={CHART_COLORS.blue} stopOpacity={0.95} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid horizontal={false} stroke={DARK_THEME.border} />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="label" width={140} />
                  <Tooltip formatter={tooltipFmt} cursor={{ fill: 'rgba(0,201,200,0.06)' }} />
                  <Bar dataKey="total_hours" fill="url(#grad-employees)" name="Часы" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty description="Нет данных" />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Топ-5 проектов по часам">
            {top5projects?.length ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={top5projects} layout="vertical" margin={{ left: 20 }}>
                  <defs>
                    <linearGradient id="grad-projects" x1="0" x2="1" y1="0" y2="0">
                      <stop offset="0%" stopColor={CHART_COLORS.green} stopOpacity={0.25} />
                      <stop offset="100%" stopColor={CHART_COLORS.green} stopOpacity={0.95} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid horizontal={false} stroke={DARK_THEME.border} />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="label" width={140} />
                  <Tooltip formatter={tooltipFmt} cursor={{ fill: 'rgba(0,201,200,0.06)' }} />
                  <Bar dataKey="total_hours" fill="url(#grad-projects)" name="Часы" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty description="Нет данных" />}
          </Card>
        </Col>
      </Row>

      {/* Category pie + weekly trend */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="Распределение по категориям">
            {pieData?.length ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={pieData} dataKey="total_hours" nameKey="label" cx="50%" cy="50%" outerRadius={110}>
                    {pieData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                  </Pie>
                  <Tooltip formatter={tooltipFmt} />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty description="Нет данных" />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Динамика (по неделям)">
            {trend?.length ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trend}>
                  <defs>
                    <linearGradient id="grad-trend" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor={CHART_COLORS.cyan} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={CHART_COLORS.cyan} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke={DARK_THEME.border} />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip formatter={tooltipFmt} cursor={{ stroke: DARK_THEME.cyanPrimary, strokeDasharray: '3 3' }} />
                  <Line
                    type="monotone"
                    dataKey="total_hours"
                    stroke={CHART_COLORS.cyan}
                    strokeWidth={2}
                    dot={{ fill: CHART_COLORS.cyan, r: 3 }}
                    activeDot={{ r: 5, fill: DARK_THEME.textPrimary, stroke: CHART_COLORS.cyan, strokeWidth: 2 }}
                    fill="url(#grad-trend)"
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : <Empty description="Нет данных" />}
          </Card>
        </Col>
      </Row>

      {/* Sync status — collapsible */}
      <Collapse
        items={[{
          key: 'sync',
          label: 'Статус синхронизации',
          children: syncLoading ? <Spin /> : (
            <Table<SyncStatusResponse>
              dataSource={syncStatus}
              rowKey="entity"
              pagination={false}
              size="small"
              scroll={{ x: true }}
              columns={[
                { title: 'Сущность', dataIndex: 'entity' },
                { title: 'Последняя синхронизация', dataIndex: 'last_sync', render: (v: string | null) => formatDate(v) },
                { title: 'Статус', dataIndex: 'last_error', render: (v: string | null) => v ? <Tag color="red">Ошибка</Tag> : <Tag color="green">OK</Tag> },
              ]}
            />
          ),
        }]}
      />
    </div>
  );
}
