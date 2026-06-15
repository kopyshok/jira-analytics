import { Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtRange } from './format';
import type { MyTask, MyTasksData } from '../../types/desk';

export default function MyTasksWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<MyTasksData>(token, 'my_tasks');
  const tasks = data?.tasks ?? [];

  const columns: ColumnsType<MyTask> = [
    {
      title: 'Задача',
      dataIndex: 'title',
      render: (_, r) =>
        r.jira_url ? (
          <Typography.Link href={r.jira_url} target="_blank" rel="noreferrer">
            {r.key ? `${r.key} · ` : ''}
            {r.title ?? '—'}
          </Typography.Link>
        ) : (
          <span>{r.title ?? r.key ?? '—'}</span>
        ),
    },
    { title: 'Фаза', dataIndex: 'phase', width: 110, render: (v) => v ?? '—' },
    {
      title: 'Даты',
      width: 150,
      render: (_, r) => fmtRange(r.start_date, r.end_date),
    },
    { title: 'Часы', dataIndex: 'hours', width: 80, align: 'right', render: (v) => v ?? 0 },
  ];

  return (
    <WidgetShell title={title} isLoading={isLoading} isError={isError} isEmpty={tasks.length === 0}>
      <Table
        rowKey={(r) => `${r.key ?? ''}-${r.phase ?? ''}-${r.start_date ?? ''}`}
        size="small"
        columns={columns}
        dataSource={tasks}
        pagination={false}
        scroll={{ y: 280 }}
      />
    </WidgetShell>
  );
}
