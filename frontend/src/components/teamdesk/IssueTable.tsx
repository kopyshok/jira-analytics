import { Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  STATUS_GROUP_LABELS, roundHours, type DeskIssue, type StatusGroup,
} from '../../api/teamDesk';
import { FlagList } from './FlagChip';
import { HoursScale } from './HoursScale';

const GROUP_COLOR: Record<StatusGroup, string> = {
  dev: '#4ba3ff',
  waiting: '#eeb13c',
  todo: '#788799',
  done: '#3ebd85',
  unassigned: '#a78bfa',
};

interface Props {
  issues: DeskIssue[];
  overrunPct: number;
  jiraBaseUrl?: string;
}

/** Статус с точкой-меткой: чей сейчас мяч. */
export function StatusTag({ status, group }: { status: string; group: StatusGroup }) {
  return (
    <Tooltip title={STATUS_GROUP_LABELS[group]}>
      <Tag style={{ marginInlineEnd: 0 }}>
        <span
          style={{
            display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
            background: GROUP_COLOR[group], marginRight: 6,
          }}
        />
        {status}
      </Tag>
    </Tooltip>
  );
}

/** Ключ задачи — ссылка в Jira, если известен адрес сервиса. */
export function IssueKey({ issueKey, jiraBaseUrl }: { issueKey: string; jiraBaseUrl?: string }) {
  if (!jiraBaseUrl) return <Typography.Text strong>{issueKey}</Typography.Text>;
  return (
    <Typography.Link
      href={`${jiraBaseUrl}/browse/${issueKey}`}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
    >
      {issueKey}
    </Typography.Link>
  );
}

/** Детальная таблица задач: строки раскрываются в подзадачи. */
export function IssueTable({ issues, overrunPct, jiraBaseUrl }: Props) {
  const children = new Map<string, DeskIssue[]>();
  const roots: DeskIssue[] = [];
  const ids = new Set(issues.map((i) => i.id));
  issues.forEach((issue) => {
    if (issue.parent_id && ids.has(issue.parent_id)) {
      const list = children.get(issue.parent_id) ?? [];
      list.push(issue);
      children.set(issue.parent_id, list);
    } else {
      roots.push(issue);
    }
  });

  const columns: ColumnsType<DeskIssue> = [
    {
      title: 'Задача',
      dataIndex: 'key',
      render: (_, row) => (
        <span>
          <IssueKey issueKey={row.key} jiraBaseUrl={jiraBaseUrl} />{' '}
          {row.summary}
          {row.is_analysis && <Tag style={{ marginLeft: 6 }}>тех. анализ</Tag>}
        </span>
      ),
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      width: 190,
      sorter: (a, b) => a.status.localeCompare(b.status),
      render: (_, row) => <StatusTag status={row.status} group={row.status_group} />,
    },
    {
      title: 'Разработчик',
      dataIndex: 'developer_name',
      width: 170,
      ellipsis: true,
      sorter: (a, b) => (a.developer_name ?? '').localeCompare(b.developer_name ?? ''),
    },
    {
      title: 'Оценка',
      dataIndex: 'est_hours',
      width: 96,
      align: 'right',
      sorter: (a, b) => (a.est_hours ?? 0) - (b.est_hours ?? 0),
      render: (v: number | null) => (v == null ? '—' : roundHours(v)),
    },
    {
      title: 'Факт',
      dataIndex: 'fact_hours',
      width: 88,
      align: 'right',
      sorter: (a, b) => a.fact_hours - b.fact_hours,
      render: (v: number, row) => (
        <Tooltip
          title={
            row.fact_by_person.length
              ? row.fact_by_person.map((p) => `${p.name}: ${roundHours(p.hours)} ч`).join('\n')
              : 'Нет списаний'
          }
        >
          {roundHours(v)}
        </Tooltip>
      ),
    },
    {
      title: 'Шкала',
      width: 165,
      render: (_, row) => (
        <HoursScale fact={row.fact_hours} est={row.est_hours} overrunPct={overrunPct} />
      ),
    },
    {
      title: 'Дней',
      dataIndex: 'days_in_status',
      width: 84,
      align: 'right',
      sorter: (a, b) => a.days_in_status - b.days_in_status,
    },
    {
      title: 'Замечания',
      width: 165,
      render: (_, row) => (
        <FlagList
          issueId={row.id}
          flags={row.flags}
          signatures={row.signatures}
          reviewed={row.reviewed}
        />
      ),
    },
  ];

  return (
    <Table<DeskIssue>
      size="small"
      rowKey="id"
      dataSource={roots}
      columns={columns}
      pagination={false}
      // Название задачи забирает остаток ширины и переносится на вторую строку,
      // когда места мало — заголовки колонок при этом не ломаются.
      scroll={{ x: 1260 }}
      expandable={{
        rowExpandable: (row) => (children.get(row.id)?.length ?? 0) > 0,
        expandedRowRender: (row) => (
          <Table<DeskIssue>
            size="small"
            rowKey="id"
            showHeader={false}
            dataSource={children.get(row.id) ?? []}
            columns={columns}
            pagination={false}
          />
        ),
      }}
    />
  );
}
