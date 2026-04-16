import { Card, Row, Col, Statistic, Spin, Empty, Table, Tag } from 'antd';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts';
import { useSyncStatus } from '../hooks/useSync';
import { useHoursByCategory, useHoursByPeriod } from '../hooks/useAnalytics';
import { CATEGORY_LABELS, CATEGORY_COLORS } from '../utils/constants';
import { formatHours, formatDate } from '../utils/format';
import type { SyncStatusResponse } from '../types/api';

const tooltipFmt = (v: unknown) => formatHours(Number(v)) + ' ч';

export default function DashboardPage() {
  const { data: syncStatus, isLoading: syncLoading } = useSyncStatus();
  const { data: categories } = useHoursByCategory();
  const { data: trend } = useHoursByPeriod('week');

  const totalHours = categories?.reduce((s, r) => s + r.total_hours, 0) ?? 0;
  const totalWorklogs = categories?.reduce((s, r) => s + r.worklog_count, 0) ?? 0;

  const pieData = categories?.map((d) => ({
    ...d,
    label: CATEGORY_LABELS[d.key] || d.label,
    fill: CATEGORY_COLORS[d.key] || '#8884d8',
  }));

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card><Statistic title="Всего часов" value={formatHours(totalHours)} suffix="ч" /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title="Ворклогов" value={totalWorklogs} /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title="Категорий" value={categories?.length ?? 0} /></Card>
        </Col>
      </Row>

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

      <Card title="Статус синхронизации">
        {syncLoading ? <Spin /> : (
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
        )}
      </Card>
    </div>
  );
}
