import { Spin, Table, Empty } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import type { IssueWorklogItem } from '../../types/api';
import { useIssueWorklogs } from '../../hooks/useIssueWorklogs';

interface Props {
  issueId: string;
  periodStart: string;
  periodEnd: string;
}

const columns: ColumnsType<IssueWorklogItem> = [
  {
    title: 'Когда',
    dataIndex: 'started_at',
    key: 'started_at',
    width: 110,
    render: (v: string) => v?.slice(0, 10) ?? '—',
  },
  {
    title: 'Кто',
    dataIndex: 'employee_name',
    key: 'employee_name',
    width: 160,
  },
  {
    title: 'Часы',
    dataIndex: 'hours',
    key: 'hours',
    width: 70,
    align: 'right',
    render: (v: number) => v.toFixed(1),
  },
  {
    title: 'Комментарий',
    dataIndex: 'comment',
    key: 'comment',
    render: (v: string | null) => v || '—',
  },
];

export default function AnalyticsWorklogsBlock({ issueId, periodStart, periodEnd }: Props) {
  const { data, isLoading } = useIssueWorklogs(issueId, periodStart, periodEnd);

  if (isLoading) return <Spin size="small" style={{ margin: 16 }} />;
  if (!data?.length) return <Empty description="Нет ворклогов за период" style={{ margin: 16 }} />;

  return (
    <Table<IssueWorklogItem>
      dataSource={data}
      columns={columns}
      rowKey="worklog_id"
      pagination={false}
      size="small"
      style={{ margin: '8px 0 8px 40px', maxWidth: 700 }}
    />
  );
}
