import { useState } from 'react';
import { Tabs, Table, Space, Spin, Empty, Select, Segmented, Alert, Button } from 'antd';
import type { Dayjs } from 'dayjs';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Legend } from 'recharts';
import DateRangeSelect from '../components/shared/DateRangeSelect';
import ExportButtons from '../components/shared/ExportButtons';
import { useHoursByEmployee, useHoursByProject, useHoursByCategory, useHoursByPeriod, useContextSwitching, useEmployeesForFilter, useProjectsForFilter } from '../hooks/useAnalytics';
import { downloadAnalyticsXlsx, downloadAnalyticsPdf } from '../api/exports';
import { CATEGORY_LABELS, CATEGORY_COLORS } from '../utils/constants';
import { formatHours } from '../utils/format';
import type { AggregateRowResponse, ContextSwitchRowResponse } from '../types/api';

const tooltipFmt = (v: unknown) => formatHours(Number(v)) + ' ч';

export default function AnalyticsPage() {
  const [dates, setDates] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [employeeId, setEmployeeId] = useState<string | undefined>();
  const [projectKey, setProjectKey] = useState<string | undefined>();
  const [period, setPeriod] = useState<'day' | 'week' | 'month'>('week');

  const start = dates?.[0]?.format('YYYY-MM-DD');
  const end = dates?.[1]?.format('YYYY-MM-DD');

  const { data: employees } = useEmployeesForFilter();
  const { data: projects } = useProjectsForFilter();

  const hasFilters = !!employeeId || !!projectKey || !!dates;

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Space wrap>
        <DateRangeSelect value={dates} onChange={setDates} />
        <Select
          allowClear
          placeholder="Все сотрудники"
          style={{ minWidth: 180 }}
          value={employeeId}
          onChange={setEmployeeId}
          options={employees?.map(e => ({ value: e.id, label: e.display_name }))}
          showSearch
          optionFilterProp="label"
        />
        <Select
          allowClear
          placeholder="Все проекты"
          style={{ minWidth: 160 }}
          value={projectKey}
          onChange={setProjectKey}
          options={projects?.map(p => ({ value: p.key, label: p.name }))}
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
      </Space>
      <Tabs items={[
        { key: 'employee', label: 'По сотрудникам', children: <EmployeeTab start={start} end={end} employeeId={employeeId} projectKey={projectKey} /> },
        { key: 'project', label: 'По проектам', children: <ProjectTab start={start} end={end} employeeId={employeeId} projectKey={projectKey} /> },
        { key: 'category', label: 'По категориям', children: <CategoryTab start={start} end={end} employeeId={employeeId} projectKey={projectKey} /> },
        { key: 'period', label: 'По периодам', children: <PeriodTab start={start} end={end} period={period} onPeriodChange={setPeriod} employeeId={employeeId} projectKey={projectKey} /> },
        { key: 'switching', label: 'Переключения контекста', children: <SwitchingTab start={start} end={end} employeeId={employeeId} projectKey={projectKey} /> },
      ]} />
    </Space>
  );
}

function HoursBarChart({ data, loading }: { data?: AggregateRowResponse[]; loading: boolean }) {
  if (loading) return <Spin />;
  if (!data?.length) return <Empty description="Нет данных" />;
  return (
    <ResponsiveContainer width="100%" height={400}>
      <BarChart data={data} margin={{ left: 20, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="label" angle={-45} textAnchor="end" interval={0} height={80} />
        <YAxis />
        <Tooltip formatter={tooltipFmt} />
        <Bar dataKey="total_hours" fill="#1890ff" name="Часы" />
      </BarChart>
    </ResponsiveContainer>
  );
}

function EmployeeTab({ start, end, employeeId, projectKey }: { start?: string; end?: string; employeeId?: string; projectKey?: string }) {
  const { data, isLoading, isError, error } = useHoursByEmployee(start, end, employeeId, projectKey);
  return (
    <>
      {isError && <Alert type="error" message="Ошибка загрузки" description={(error as Error)?.message} showIcon style={{ marginBottom: 16 }} />}
      <HoursBarChart data={data} loading={isLoading} />
      <Table<AggregateRowResponse>
        dataSource={data}
        rowKey="key"
        size="small"
        pagination={false}
        columns={[
          { title: 'Сотрудник', dataIndex: 'label' },
          { title: 'Часы', dataIndex: 'total_hours', render: formatHours, sorter: (a, b) => a.total_hours - b.total_hours },
          { title: 'Ворклогов', dataIndex: 'worklog_count', sorter: (a, b) => a.worklog_count - b.worklog_count },
        ]}
      />
    </>
  );
}

function ProjectTab({ start, end, employeeId, projectKey }: { start?: string; end?: string; employeeId?: string; projectKey?: string }) {
  const { data, isLoading, isError, error } = useHoursByProject(start, end, employeeId, projectKey);
  return (
    <>
      {isError && <Alert type="error" message="Ошибка загрузки" description={(error as Error)?.message} showIcon style={{ marginBottom: 16 }} />}
      <HoursBarChart data={data} loading={isLoading} />
      <Table<AggregateRowResponse>
        dataSource={data}
        rowKey="key"
        size="small"
        pagination={false}
        columns={[
          { title: 'Проект', dataIndex: 'label' },
          { title: 'Часы', dataIndex: 'total_hours', render: formatHours, sorter: (a, b) => a.total_hours - b.total_hours },
          { title: 'Ворклогов', dataIndex: 'worklog_count', sorter: (a, b) => a.worklog_count - b.worklog_count },
        ]}
      />
    </>
  );
}

function CategoryTab({ start, end, employeeId, projectKey }: { start?: string; end?: string; employeeId?: string; projectKey?: string }) {
  const { data, isLoading, isError, error } = useHoursByCategory(start, end, employeeId, projectKey);
  if (isLoading) return <Spin />;
  if (isError) return <Alert type="error" message="Ошибка загрузки" description={(error as Error)?.message} showIcon />;
  if (!data?.length) return <Empty description="Нет данных" />;

  const chartData = data.map((d) => ({
    ...d,
    label: CATEGORY_LABELS[d.key] || d.label,
    fill: CATEGORY_COLORS[d.key] || '#8884d8',
  }));

  return (
    <>
      <ResponsiveContainer width="100%" height={400}>
        <PieChart>
          <Pie data={chartData} dataKey="total_hours" nameKey="label" cx="50%" cy="50%" outerRadius={150} label={({ name, percent }: { name?: string; percent?: number }) => `${name ?? ''} (${((percent ?? 0) * 100).toFixed(0)}%)`}>
            {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
          </Pie>
          <Tooltip formatter={tooltipFmt} />
        </PieChart>
      </ResponsiveContainer>
      <Table<AggregateRowResponse>
        dataSource={data}
        rowKey="key"
        size="small"
        pagination={false}
        columns={[
          { title: 'Категория', dataIndex: 'key', render: (v: string) => CATEGORY_LABELS[v] || v },
          { title: 'Часы', dataIndex: 'total_hours', render: formatHours, sorter: (a, b) => a.total_hours - b.total_hours },
          { title: 'Ворклогов', dataIndex: 'worklog_count', sorter: (a, b) => a.worklog_count - b.worklog_count },
        ]}
      />
    </>
  );
}

function PeriodTab({ start, end, period, onPeriodChange, employeeId, projectKey }: { start?: string; end?: string; period: 'day' | 'week' | 'month'; onPeriodChange: (v: 'day' | 'week' | 'month') => void; employeeId?: string; projectKey?: string }) {
  const { data, isLoading, isError, error } = useHoursByPeriod(period, start, end, employeeId, projectKey);
  if (isLoading) return <Spin />;
  if (isError) return <Alert type="error" message="Ошибка загрузки" description={(error as Error)?.message} showIcon />;
  if (!data?.length) return (
    <>
      <Segmented options={[{ label: 'День', value: 'day' }, { label: 'Неделя', value: 'week' }, { label: 'Месяц', value: 'month' }]} value={period} onChange={v => onPeriodChange(v as 'day' | 'week' | 'month')} style={{ marginBottom: 16 }} />
      <Empty description="Нет данных" />
    </>
  );
  return (
    <>
      <Segmented options={[{ label: 'День', value: 'day' }, { label: 'Неделя', value: 'week' }, { label: 'Месяц', value: 'month' }]} value={period} onChange={v => onPeriodChange(v as 'day' | 'week' | 'month')} style={{ marginBottom: 16 }} />
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" />
          <YAxis />
          <Tooltip formatter={tooltipFmt} />
          <Legend />
          <Line type="monotone" dataKey="total_hours" stroke="#1890ff" name="Часы" />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

function SwitchingTab({ start, end, employeeId, projectKey }: { start?: string; end?: string; employeeId?: string; projectKey?: string }) {
  const { data, isLoading, isError, error } = useContextSwitching(start, end, employeeId, projectKey);
  return (
    <>
      {isError && <Alert type="error" message="Ошибка загрузки" description={(error as Error)?.message} showIcon style={{ marginBottom: 16 }} />}
      <Table<ContextSwitchRowResponse>
        dataSource={data}
        rowKey="employee_id"
        loading={isLoading}
        size="small"
        pagination={false}
        columns={[
          { title: 'Сотрудник', dataIndex: 'employee_name' },
          { title: 'Ворклогов', dataIndex: 'total_worklogs', sorter: (a, b) => a.total_worklogs - b.total_worklogs },
          { title: 'Проектов', dataIndex: 'distinct_projects', sorter: (a, b) => a.distinct_projects - b.distinct_projects },
          { title: 'Категорий', dataIndex: 'distinct_categories', sorter: (a, b) => a.distinct_categories - b.distinct_categories },
          { title: 'Переключений', dataIndex: 'switches', sorter: (a, b) => a.switches - b.switches },
        ]}
      />
    </>
  );
}
