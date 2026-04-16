import { Card, Row, Col, Statistic, Spin, Empty, Table, Tag, Collapse } from 'antd';
import {
  ClockCircleOutlined,
  TeamOutlined,
  ProjectOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  BarChart, Bar,
} from 'recharts';
import { useSyncStatus } from '../hooks/useSync';
import {
  useHoursByCategory,
  useHoursByPeriod,
  useHoursByEmployee,
  useHoursByProject,
  useContextSwitching,
} from '../hooks/useAnalytics';
import { CATEGORY_LABELS, CATEGORY_COLORS } from '../utils/constants';
import { formatHours, formatDate } from '../utils/format';
import type { SyncStatusResponse } from '../types/api';

const tooltipFmt = (v: unknown) => formatHours(Number(v)) + ' ч';

export default function DashboardPage() {
  const { data: syncStatus, isLoading: syncLoading } = useSyncStatus();
  const { data: categories } = useHoursByCategory();
  const { data: trend } = useHoursByPeriod('week');
  const { data: employees } = useHoursByEmployee();
  const { data: projects } = useHoursByProject();
  const { data: switching } = useContextSwitching();

  const totalHours = categories?.reduce((s, r) => s + r.total_hours, 0) ?? 0;
  const employeeCount = employees?.length ?? 0;
  const projectCount = projects?.length ?? 0;
  const avgSwitches = switching?.length
    ? switching.reduce((s, r) => s + r.switches, 0) / switching.length
    : 0;

  const pieData = categories?.map((d) => ({
    ...d,
    label: CATEGORY_LABELS[d.key] || d.label,
    fill: CATEGORY_COLORS[d.key] || '#8884d8',
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
      {/* KPI cards */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="Всего часов"
              value={formatHours(totalHours)}
              suffix="ч"
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Сотрудников"
              value={employeeCount}
              prefix={<TeamOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Проектов"
              value={projectCount}
              prefix={<ProjectOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Ср. переключений"
              value={avgSwitches.toFixed(1)}
              prefix={<SwapOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Top-5 employees & Top-5 projects */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card title="Топ-5 сотрудников по часам">
            {top5employees?.length ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={top5employees} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="label" width={140} />
                  <Tooltip formatter={tooltipFmt} />
                  <Bar dataKey="total_hours" fill="#1890ff" name="Часы" />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty description="Нет данных" />}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="Топ-5 проектов по часам">
            {top5projects?.length ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={top5projects} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="label" width={140} />
                  <Tooltip formatter={tooltipFmt} />
                  <Bar dataKey="total_hours" fill="#52c41a" name="Часы" />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty description="Нет данных" />}
          </Card>
        </Col>
      </Row>

      {/* Category pie + weekly trend */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
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
        <Col span={12}>
          <Card title="Динамика (по неделям)">
            {trend?.length ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trend}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip formatter={tooltipFmt} />
                  <Line type="monotone" dataKey="total_hours" stroke="#1890ff" />
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
