import { useState } from 'react';
import { Spin, Table, Empty, Switch } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import type { IssueWorklogItem } from '../../types/api';
import { useIssueWorklogs } from '../../hooks/useIssueWorklogs';

interface Props {
  issueId: string;
  periodStart: string;
  periodEnd: string;
  /** Задача открыта из строки сотрудника — можно оставить только его ворклоги. */
  employee?: { id: string; name: string };
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

export default function AnalyticsWorklogsBlock({ issueId, periodStart, periodEnd, employee }: Props) {
  const { data, isLoading } = useIssueWorklogs(issueId, periodStart, periodEnd);
  // По умолчанию — только сотрудник строки: часы в строке тоже только его.
  const [onlyEmployee, setOnlyEmployee] = useState(true);

  if (isLoading) return <Spin size="small" style={{ margin: 16 }} />;
  if (!data?.length) return <Empty description="Нет ворклогов за период" style={{ margin: 16 }} />;

  const filtered = employee && onlyEmployee ? data.filter((w) => w.employee_id === employee.id) : data;

  return (
    <div style={{ margin: '8px 0 8px 40px', maxWidth: 700 }}>
      {employee && (
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            margin: '0 0 8px',
            fontSize: 12,
            color: 'var(--text-muted, #7e94b8)',
            cursor: 'pointer',
          }}
        >
          <Switch size="small" checked={onlyEmployee} onChange={setOnlyEmployee} />
          <span>
            Только {employee.name}
            {onlyEmployee && ` · ${filtered.length} из ${data.length}`}
          </span>
        </label>
      )}
      {filtered.length === 0 ? (
        <Empty description="У сотрудника нет ворклогов по задаче за период" style={{ margin: 16 }} />
      ) : (
        <Table<IssueWorklogItem>
          dataSource={filtered}
          columns={columns}
          rowKey="worklog_id"
          pagination={false}
          size="small"
        />
      )}
    </div>
  );
}
