import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtDate } from './format';
import type { DeadlineItem, QuarterDeadlinesData } from '../../types/desk';

export default function QuarterDeadlinesWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<QuarterDeadlinesData>(
    token,
    'quarter_deadlines',
  );
  const items = [...(data?.items ?? [])].sort((a, b) =>
    (a.due_date ?? '').localeCompare(b.due_date ?? ''),
  );

  const columns: ColumnsType<DeadlineItem> = [
    { title: 'Ключ', dataIndex: 'key', width: 110 },
    { title: 'Задача', dataIndex: 'title' },
    {
      title: 'Срок',
      dataIndex: 'due_date',
      width: 120,
      render: (v) => fmtDate(v),
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      width: 130,
      render: (v) => (v ? <Tag>{v}</Tag> : '—'),
    },
  ];

  return (
    <WidgetShell title={title} isLoading={isLoading} isError={isError} isEmpty={items.length === 0}>
      <Table
        rowKey="key"
        size="small"
        columns={columns}
        dataSource={items}
        pagination={false}
        scroll={{ y: 280 }}
      />
    </WidgetShell>
  );
}
