import { useState } from 'react';
import { Card, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  FLAG_LABELS, FLAG_ORDER, roundHours,
  type DeskDeveloper, type DeskIssue, type FlagCode,
} from '../../api/teamDesk';
import { FlagList } from './FlagChip';
import { HoursScale } from './HoursScale';
import { StatusTag } from './IssueTable';

const ICON: Record<FlagCode, string> = {
  over: '↑', under: '↓', decomp: '⊞', childgap: '⊟',
  noest: '∅', nospent: '◔', stale: '⏳',
};
const COLOR: Record<FlagCode, string> = {
  over: 'red', under: 'gold', decomp: 'orange', childgap: 'volcano',
  noest: 'default', nospent: 'default', stale: 'purple',
};

interface Row extends Partial<DeskIssue> {
  rowKey: string;
  isGroup?: boolean;
  groupName?: string;
  groupCount?: number;
  groupInDev?: number;
  children?: Row[];
}

interface Props {
  developers: DeskDeveloper[];
  issues: DeskIssue[];
  flagCounts: Partial<Record<FlagCode, number>>;
  overrunPct: number;
}

/** Раскладка «Проблемы вперёд»: фильтры-признаки + один список по людям. */
export function GroupedIssueTable({ developers, issues, flagCounts, overrunPct }: Props) {
  const [filter, setFilter] = useState<FlagCode | null>(null);

  const childrenOf = new Map<string, DeskIssue[]>();
  const ids = new Set(issues.map((i) => i.id));
  issues.forEach((issue) => {
    if (issue.parent_id && ids.has(issue.parent_id)) {
      const list = childrenOf.get(issue.parent_id) ?? [];
      list.push(issue);
      childrenOf.set(issue.parent_id, list);
    }
  });

  const matches = (issue: DeskIssue): boolean =>
    !filter ||
    issue.flags.includes(filter) ||
    (childrenOf.get(issue.id) ?? []).some((c) => c.flags.includes(filter));

  const toRow = (issue: DeskIssue): Row => {
    const kids = (childrenOf.get(issue.id) ?? []).map(toRow);
    return { ...issue, rowKey: issue.id, children: kids.length ? kids : undefined };
  };

  const data: Row[] = [];
  developers.forEach((dev) => {
    const own = issues.filter(
      (i) => i.developer_id === dev.developer_id && !(i.parent_id && ids.has(i.parent_id)),
    ).filter(matches);
    if (!own.length) return;
    data.push({
      rowKey: `group-${dev.developer_id}`,
      isGroup: true,
      groupName: dev.display_name ?? 'Без имени',
      groupCount: own.length,
      groupInDev: dev.in_dev,
      est_hours: dev.est_hours,
      fact_hours: dev.fact_hours,
      children: own.map(toRow),
    });
  });

  const shown = data.reduce((n, g) => n + (g.children?.length ?? 0), 0);

  const columns: ColumnsType<Row> = [
    {
      title: 'Задача',
      ellipsis: true,
      render: (_, row) =>
        row.isGroup ? (
          <Typography.Text strong>
            {row.groupName}{' '}
            <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
              · {row.groupCount} задач · {row.groupInDev} у него
            </Typography.Text>
          </Typography.Text>
        ) : (
          <span>
            <Typography.Text strong>{row.key}</Typography.Text> {row.summary}
            {row.is_analysis && <Tag style={{ marginLeft: 6 }}>тех. анализ</Tag>}
          </span>
        ),
    },
    {
      title: 'Статус',
      width: 170,
      render: (_, row) =>
        row.isGroup ? null : <StatusTag status={row.status!} group={row.status_group!} />,
    },
    { title: 'Оценка', width: 76, align: 'right',
      render: (_, row) => (row.est_hours == null ? '—' : roundHours(row.est_hours)) },
    { title: 'Факт', width: 68, align: 'right',
      render: (_, row) => roundHours(row.fact_hours ?? 0) },
    {
      title: 'Недобор / перебор',
      width: 165,
      render: (_, row) => (
        <HoursScale
          fact={row.fact_hours ?? 0}
          est={row.est_hours ?? null}
          variant="centered"
          overrunPct={overrunPct}
        />
      ),
    },
    { title: 'Дней', width: 64, align: 'right',
      render: (_, row) => (row.isGroup ? null : row.days_in_status) },
    {
      title: 'Замечания',
      width: 140,
      render: (_, row) =>
        row.isGroup ? null : (
          <FlagList
            issueId={row.id!}
            flags={row.flags ?? []}
            signatures={row.signatures ?? {}}
            reviewed={row.reviewed ?? []}
          />
        ),
    },
  ];

  return (
    <Space orientation="vertical" size={14} style={{ width: '100%' }}>
      <Card size="small" title="Что требует внимания">
        <Space wrap size={6}>
          {FLAG_ORDER.filter((f) => flagCounts[f]).map((flag) => (
            <Tag
              key={flag}
              color={filter === flag ? 'blue' : COLOR[flag]}
              style={{ cursor: 'pointer' }}
              onClick={() => setFilter(filter === flag ? null : flag)}
            >
              {ICON[flag]} {FLAG_LABELS[flag]} · {flagCounts[flag]}
            </Tag>
          ))}
          {FLAG_ORDER.every((f) => !flagCounts[f]) && (
            <Typography.Text type="secondary">Замечаний нет</Typography.Text>
          )}
        </Space>
      </Card>

      <Card
        size="small"
        title="Задачи по разработчикам"
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {filter ? `отфильтровано: ${FLAG_LABELS[filter]} · ${shown} задач` : `${shown} задач`}
          </Typography.Text>
        }
      >
        <Table<Row>
          size="small"
          rowKey="rowKey"
          dataSource={data}
          columns={columns}
          pagination={false}
          scroll={{ x: 900 }}
          expandable={{ defaultExpandAllRows: true }}
        />
      </Card>
    </Space>
  );
}
