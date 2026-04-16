import { useState } from 'react';
import { Card, Row, Col, Statistic, Spin, Empty, Table, Tag, Collapse, Space, Select, Button, App } from 'antd';
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
          <Card hoverable onClick={() => navigate('/analytics?tab=category')}>
            <Statistic
              title="Всего часов"
              value={formatHours(totalHours)}
              suffix="ч"
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/analytics?tab=employee')}>
            <Statistic
              title="Сотрудников"
              value={employeeCount}
              prefix={<TeamOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/analytics?tab=project')}>
            <Statistic
              title="Проектов"
              value={projectCount}
              prefix={<ProjectOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/analytics?tab=switching')}>
            <Statistic
              title="Ср. переключений"
              value={avgSwitches.toFixed(1)}
              prefix={<SwapOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Top-5 employees & Top-5 projects */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="Топ-5 сотрудников по часам">
            {top5employees?.length ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={top5employees} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={DARK_THEME.border} />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="label" width={140} />
                  <Tooltip formatter={tooltipFmt} />
                  <Bar dataKey="total_hours" fill={CHART_COLORS.blue} name="Часы" />
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
                  <CartesianGrid strokeDasharray="3 3" stroke={DARK_THEME.border} />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="label" width={140} />
                  <Tooltip formatter={tooltipFmt} />
                  <Bar dataKey="total_hours" fill={CHART_COLORS.green} name="Часы" />
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
                  <CartesianGrid strokeDasharray="3 3" stroke={DARK_THEME.border} />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip formatter={tooltipFmt} />
                  <Line type="monotone" dataKey="total_hours" stroke={CHART_COLORS.cyan} />
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
