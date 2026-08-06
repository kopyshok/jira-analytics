import { useState } from 'react';
import { Card, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  roundHours, type DeskDeveloper, type DeskIssue, type FlagCode,
} from '../../api/teamDesk';
import { FlagList } from './FlagChip';
import { HoursScale } from './HoursScale';
import { IssueKey, StatusTag } from './IssueCells';

interface Row extends Partial<DeskIssue> {
  rowKey: string;
  isGroup?: boolean;
  groupName?: string;
  groupCount?: number;
  groupInDev?: number;
  /** Имя, если подзадачу делает не владелец группы. */
  otherDeveloper?: string | null;
  children?: Row[];
}

interface Props {
  title: string;
  developers: DeskDeveloper[];
  issues: DeskIssue[];
  overrunPct: number;
  jiraBaseUrl?: string;
  /** bar — «факт / оценка» полосой, centered — недобор влево, перебор вправо. */
  scale?: 'bar' | 'centered';
  /** Оставить только задачи с этим признаком (и их родителей). */
  flagFilter?: FlagCode | null;
  /** Оставить только одного разработчика — клик по карточке или строке сводки. */
  onlyDeveloper?: string | null;
  /** Пояснение слева от счётчика задач в шапке карточки. */
  hint?: string;
}

/**
 * Список задач, сгруппированный по разработчикам. Одна и та же таблица во всех
 * трёх раскладках: колонки «Разработчик» нет — имя стоит в строке группы.
 */
export function GroupedIssues({
  title, developers, issues, overrunPct, jiraBaseUrl,
  scale = 'bar', flagFilter = null, onlyDeveloper = null, hint = '',
}: Props) {
  // Люди развёрнуты по умолчанию, задачи — свёрнуты; здесь только отклонения
  // от этого правила, чтобы не пересобирать состояние на каждой загрузке.
  const [toggled, setToggled] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setToggled((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });

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
    !flagFilter ||
    issue.flags.includes(flagFilter) ||
    (childrenOf.get(issue.id) ?? []).some((c) => c.flags.includes(flagFilter));

  const data: Row[] = [];
  developers
    .filter((dev) => !onlyDeveloper || dev.developer_id === onlyDeveloper)
    .forEach((dev) => {
      const toRow = (issue: DeskIssue): Row => {
        const kids = (childrenOf.get(issue.id) ?? []).map(toRow);
        return {
          ...issue,
          rowKey: issue.id,
          otherDeveloper:
            issue.developer_id && issue.developer_id !== dev.developer_id
              ? issue.developer_name
              : null,
          children: kids.length ? kids : undefined,
        };
      };
      const own = issues
        .filter(
          (i) => i.developer_id === dev.developer_id && !(i.parent_id && ids.has(i.parent_id)),
        )
        .filter(matches);
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

  const expandableKeys: string[] = [];
  const collect = (rows: Row[]) =>
    rows.forEach((row) => {
      if (row.children?.length) {
        expandableKeys.push(row.rowKey);
        collect(row.children);
      }
    });
  collect(data);
  const expandedRowKeys = expandableKeys.filter(
    (key) => key.startsWith('group-') !== toggled.has(key),
  );

  const columns: ColumnsType<Row> = [
    {
      title: 'Задача',
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
            <IssueKey issueKey={row.key!} jiraBaseUrl={jiraBaseUrl} /> {row.summary}
            {row.is_analysis && <Tag style={{ marginLeft: 6 }}>тех. анализ</Tag>}
            {row.otherDeveloper && (
              <Typography.Text type="secondary"> · {row.otherDeveloper}</Typography.Text>
            )}
          </span>
        ),
    },
    {
      title: 'Статус',
      width: 190,
      render: (_, row) =>
        row.isGroup ? null : <StatusTag status={row.status!} group={row.status_group!} />,
    },
    { title: 'Оценка', width: 96, align: 'right',
      render: (_, row) => (row.est_hours == null ? '—' : roundHours(row.est_hours)) },
    { title: 'Факт', width: 88, align: 'right',
      render: (_, row) => roundHours(row.fact_hours ?? 0) },
    {
      title: scale === 'centered' ? 'Недобор / перебор' : 'Шкала',
      width: 190,
      render: (_, row) => (
        <HoursScale
          fact={row.fact_hours ?? 0}
          est={row.est_hours ?? null}
          variant={scale}
          overrunPct={overrunPct}
        />
      ),
    },
    { title: 'Дней', width: 84, align: 'right',
      render: (_, row) => (row.isGroup ? null : row.days_in_status) },
    {
      title: 'Замечания',
      width: 165,
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
    <Card
      size="small"
      title={title}
      extra={
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {hint ? `${hint} · ` : ''}{shown} задач
        </Typography.Text>
      }
    >
      <Table<Row>
        size="small"
        rowKey="rowKey"
        dataSource={data}
        columns={columns}
        pagination={false}
        scroll={{ x: 1180 }}
        expandable={{
          expandedRowKeys,
          onExpand: (_, row) => toggle(row.rowKey),
        }}
        onRow={(row) =>
          row.isGroup
            ? { onClick: () => toggle(row.rowKey), style: { cursor: 'pointer' } }
            : {}
        }
      />
    </Card>
  );
}
