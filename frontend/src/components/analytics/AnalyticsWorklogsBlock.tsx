import { Spin, Table, Empty } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import type { IssueWorklogItem } from '../../types/api';
import { useIssueWorklogs } from '../../hooks/useIssueWorklogs';
import { formatHours, formatIsoDate } from '../../utils/analyticsView';
import { deskShortName } from '../../utils/teamDeskView';

interface Props {
  issueId: string;
  periodStart: string;
  periodEnd: string;
  /** Вид скина: плотная таблица «Когда / Кто / Часы / Комментарий» с итогом, даты по-русски. */
  compact?: boolean;
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

export default function AnalyticsWorklogsBlock({ issueId, periodStart, periodEnd, compact = false }: Props) {
  const { data, isLoading } = useIssueWorklogs(issueId, periodStart, periodEnd);

  if (isLoading) return <Spin size="small" style={{ margin: 16 }} />;
  if (compact && !data?.length) return <div className="anc-wl-empty">Нет ворклогов за период</div>;
  if (!data?.length) return <Empty description="Нет ворклогов за период" style={{ margin: 16 }} />;

  if (compact) {
    const total = data.reduce((sum, w) => sum + w.hours, 0);
    return (
      <div className="anc-wl">
        <table className="anc-wl-table">
          <thead>
            <tr>
              <th className="is-when">Когда</th>
              <th className="is-who">Кто</th>
              <th className="is-num">Часы</th>
              <th>Комментарий</th>
            </tr>
          </thead>
          <tbody>
            {data.map((w) => (
              <tr key={w.worklog_id}>
                <td className="is-when">{formatIsoDate(w.started_at)}</td>
                <td className="is-who" title={w.employee_name}>{deskShortName(w.employee_name)}</td>
                <td className="is-num">{formatHours(w.hours)}</td>
                <td>{w.comment || '—'}</td>
              </tr>
            ))}
            <tr className="is-total">
              <td colSpan={2}>Итого</td>
              <td className="is-num">{formatHours(total)}</td>
              <td className="anc-wl-unit">ч</td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

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
