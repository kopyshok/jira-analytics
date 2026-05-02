import type React from 'react';
import { useState } from 'react';
import { Table, Tag, Drawer } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import type {
  AnalyticsReportResponse,
  AnalyticsTeamNode,
  NodeTotals,
  AnalyticsIssueNode,
  AnalyticsCategoryNode,
  AnalyticsWorkTypeNode,
  AnalyticsEmployeeNode,
  AnalyticsRoleNode,
} from '../../types/api';
import { useAnalyticsColumns } from '../../hooks/useAnalyticsColumns';
import { statusTagColor } from '../../utils/status';
import AnalyticsWorklogsBlock from './AnalyticsWorklogsBlock';

type RowKind = 'team' | 'role' | 'emp' | 'wt' | 'cat' | 'issue' | 'worklog-block';

interface TreeNode {
  key: string;
  kind: RowKind;
  depth: number;
  label: React.ReactNode;
  totals: NodeTotals;
  children?: TreeNode[];
  /** Issue UUID — set only for issue rows */
  issueId?: string;
  /** Issue Jira key (e.g. PROJ-123) — set only for issue rows */
  issueKey?: string;
}

const EMPTY_TOTALS: NodeTotals = {
  fact_hours: 0,
  plan_hours: null,
  pct_plan: null,
  pct_total: 0,
  worklog_count: 0,
  issue_count: 0,
  employee_count: 0,
  avg_worklog_minutes: 0,
};

function initialsOf(name: string): string {
  const parts = (name || '').split(/\s+/).filter(Boolean);
  if (!parts.length) return '??';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function indent(depth: number, content: React.ReactNode): React.ReactNode {
  return (
    <div style={{ paddingLeft: depth * 14, lineHeight: 1.35 }}>{content}</div>
  );
}

function pctColor(pct: number | null | undefined): string | undefined {
  if (pct == null) return undefined;
  if (pct > 110) return '#ff4d4f';
  if (pct >= 70) return '#faad14';
  return '#67d68d';
}

function stripKeyPrefix(summary: string, key: string): string {
  // Некоторые Jira-summary включают ключ в начало («OS-79306 Обмен Розница...»).
  // Срезаем чтобы не дублировалось со ссылкой-ключом слева.
  const trimmed = summary.trim();
  if (trimmed.startsWith(key)) {
    return trimmed.slice(key.length).replace(/^[\s:.\-—]+/, '');
  }
  return trimmed;
}

function buildIssueNode(
  i: AnalyticsIssueNode,
  prefix: string,
  depth: number,
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
): TreeNode {
  const cleanSummary = stripKeyPrefix(i.summary, i.key);
  const node: TreeNode = {
    key: `${prefix}/i:${i.id}`,
    kind: 'issue',
    depth,
    issueId: i.id,
    issueKey: i.key,
    label: indent(
      depth,
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 6,
          minWidth: 0,
        }}
      >
        <a
          href={`https://itgri.atlassian.net/browse/${i.key}`}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          style={{
            color: '#22d3ee',
            textDecoration: 'underline',
            fontWeight: 600,
            flexShrink: 0,
            whiteSpace: 'nowrap',
          }}
        >
          {i.key}
        </a>
        <Tag
          color={statusTagColor(i.status, i.status_category)}
          style={{ marginInlineEnd: 0, flexShrink: 0 }}
        >
          {i.status}
        </Tag>
        <span
          style={{
            color: '#e6edf7',
            whiteSpace: 'normal',
            wordBreak: 'break-word',
            minWidth: 0,
            flex: '1 1 auto',
          }}
        >
          {cleanSummary}
        </span>
      </div>,
    ),
    totals: i.totals,
  };

  // В inline-режиме ворклоги задачи показываются как один child-row через
  // tree-expansion, чтобы не конфликтовать с tree-mode на родительских уровнях.
  if (worklogMode === 'inline') {
    node.children = [
      {
        key: `${node.key}/wl`,
        kind: 'worklog-block',
        depth: depth + 1,
        label: (
          <div style={{ paddingLeft: (depth + 1) * 14 }}>
            <AnalyticsWorklogsBlock
              issueId={i.id}
              periodStart={periodStart}
              periodEnd={periodEnd}
            />
          </div>
        ),
        totals: EMPTY_TOTALS,
      },
    ];
  }

  return node;
}

function buildCategoryNode(
  c: AnalyticsCategoryNode,
  prefix: string,
  depth: number,
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
): TreeNode {
  return {
    key: `${prefix}/c:${c.category_code || '_none'}`,
    kind: 'cat',
    depth,
    label: indent(
      depth,
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            display: 'inline-block',
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: c.color,
            flexShrink: 0,
          }}
        />
        <span>{c.label}</span>
      </span>,
    ),
    totals: c.totals,
    children: c.issues.map((i) =>
      buildIssueNode(
        i,
        `${prefix}/c:${c.category_code || '_none'}`,
        depth + 1,
        worklogMode,
        periodStart,
        periodEnd,
      ),
    ),
  };
}

function buildWorkTypeNode(
  w: AnalyticsWorkTypeNode,
  prefix: string,
  depth: number,
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
): TreeNode {
  return {
    key: `${prefix}/w:${w.work_type_id}`,
    kind: 'wt',
    depth,
    label: indent(
      depth,
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: '#7e94b8',
            flexShrink: 0,
          }}
        />
        <span style={{ fontWeight: 500 }}>{w.label}</span>
      </span>,
    ),
    totals: w.totals,
    children: w.categories.map((c) =>
      buildCategoryNode(
        c,
        `${prefix}/w:${w.work_type_id}`,
        depth + 1,
        worklogMode,
        periodStart,
        periodEnd,
      ),
    ),
  };
}

function buildEmployeeNode(
  e: AnalyticsEmployeeNode,
  prefix: string,
  depth: number,
  roleColor: string,
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
): TreeNode {
  const initials = e.initials || initialsOf(e.name);
  return {
    key: `${prefix}/e:${e.employee_id}`,
    kind: 'emp',
    depth,
    label: indent(
      depth,
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 22,
            height: 22,
            borderRadius: '50%',
            background: roleColor,
            color: '#fff',
            fontSize: 10,
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          {initials}
        </span>
        <span style={{ color: '#e6edf7' }}>{e.name}</span>
      </span>,
    ),
    totals: e.totals,
    children: e.work_types.map((w) =>
      buildWorkTypeNode(
        w,
        `${prefix}/e:${e.employee_id}`,
        depth + 1,
        worklogMode,
        periodStart,
        periodEnd,
      ),
    ),
  };
}

function buildRoleNode(
  r: AnalyticsRoleNode,
  prefix: string,
  depth: number,
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
): TreeNode {
  return {
    key: `${prefix}/r:${r.role_code}`,
    kind: 'role',
    depth,
    label: indent(
      depth,
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            display: 'inline-block',
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: r.role_color,
            flexShrink: 0,
          }}
        />
        <span style={{ color: r.role_color, fontWeight: 600 }}>
          {r.role_label}
        </span>
      </span>,
    ),
    totals: r.totals,
    children: r.employees.map((e) =>
      buildEmployeeNode(
        e,
        `${prefix}/r:${r.role_code}`,
        depth + 1,
        r.role_color,
        worklogMode,
        periodStart,
        periodEnd,
      ),
    ),
  };
}

function buildTeamNode(
  t: AnalyticsTeamNode,
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
): TreeNode {
  const prefix = `team:${t.team || '_none'}`;
  return {
    key: prefix,
    kind: 'team',
    depth: 0,
    label: indent(0, <b>{t.team || 'Без команды'}</b>),
    totals: t.totals,
    children: t.roles.map((r) =>
      buildRoleNode(r, prefix, 1, worklogMode, periodStart, periodEnd),
    ),
  };
}

interface Props {
  data: AnalyticsReportResponse;
  selectedTeam: string | 'all';
  worklogMode: 'inline' | 'drawer';
  periodStart: string;
  periodEnd: string;
}

export default function AnalyticsTable({
  data,
  selectedTeam,
  worklogMode,
  periodStart,
  periodEnd,
}: Props) {
  const { visible } = useAnalyticsColumns();
  const visibleSet = new Set(visible);
  const [drawerIssue, setDrawerIssue] = useState<{ id: string; key: string } | null>(null);

  const teams =
    selectedTeam === 'all'
      ? data.teams
      : data.teams.filter((t) => (t.team || '_none_') === selectedTeam);

  const tableData: TreeNode[] = teams.map((t) =>
    buildTeamNode(t, worklogMode, periodStart, periodEnd),
  );

  const isBlock = (r: TreeNode) => r.kind === 'worklog-block';

  const allColumns: ColumnsType<TreeNode> = [
    {
      title: 'Группа / Задача',
      dataIndex: 'label',
      key: 'label',
      width: 600,
      ellipsis: false,
    },
    {
      title: 'Часы факт',
      key: 'fact_hours',
      render: (_, r) =>
        isBlock(r) ? null : (
          <span style={{ color: pctColor(r.totals.pct_plan), fontWeight: 600 }}>
            {r.totals.fact_hours.toFixed(1)}
          </span>
        ),
      width: 100,
      align: 'right',
    },
    {
      title: 'Часы план',
      key: 'plan_hours',
      render: (_, r) =>
        isBlock(r) ? null : r.totals.plan_hours != null ? Math.round(r.totals.plan_hours) : '—',
      width: 100,
      align: 'right',
    },
    {
      title: '% план',
      key: 'pct_plan',
      render: (_, r) =>
        isBlock(r)
          ? null
          : r.totals.pct_plan != null
            ? (
                <span style={{ color: pctColor(r.totals.pct_plan), fontWeight: 600 }}>
                  {r.totals.pct_plan.toFixed(0)}%
                </span>
              )
            : '—',
      width: 90,
      align: 'right',
    },
    {
      title: '% от итога',
      key: 'pct_total',
      render: (_, r) => (isBlock(r) ? null : `${r.totals.pct_total.toFixed(1)}%`),
      width: 100,
      align: 'right',
    },
    {
      title: 'Ворклогов',
      key: 'worklog_count',
      render: (_, r) => (isBlock(r) ? null : r.totals.worklog_count),
      width: 100,
      align: 'right',
    },
    {
      title: 'Задач',
      key: 'issue_count',
      render: (_, r) => (isBlock(r) ? null : r.totals.issue_count),
      width: 80,
      align: 'right',
    },
    {
      title: 'Сотр.',
      key: 'employee_count',
      render: (_, r) => (isBlock(r) ? null : r.totals.employee_count),
      width: 80,
      align: 'right',
    },
    {
      title: 'Ср.мин',
      key: 'avg_min',
      render: (_, r) => (isBlock(r) ? null : r.totals.avg_worklog_minutes.toFixed(0)),
      width: 90,
      align: 'right',
    },
  ];

  // Mandatory columns always shown: label, fact_hours.
  const MANDATORY_KEYS = new Set(['label', 'fact_hours']);
  const columns = allColumns.filter(
    (col) =>
      MANDATORY_KEYS.has(col.key as string) || visibleSet.has(col.key as string),
  );

  return (
    <>
      <Table<TreeNode>
        dataSource={tableData}
        columns={columns}
        rowKey="key"
        pagination={false}
        size="small"
        scroll={{ x: 'max-content' }}
        rowClassName={(record) => {
          const cls = [`tree-row-depth-${record.depth}`];
          if (record.children && record.children.length > 0)
            cls.push('tree-row-has-children');
          return cls.join(' ');
        }}
        expandable={{
          defaultExpandAllRows: false,
          rowExpandable: (record) => (record.children?.length ?? 0) > 0,
        }}
        onRow={(record) =>
          worklogMode === 'drawer' && record.kind === 'issue' && record.issueId
            ? {
                onClick: () =>
                  setDrawerIssue({ id: record.issueId!, key: record.issueKey! }),
                style: { cursor: 'pointer' },
              }
            : {}
        }
      />
      <Drawer
        title={drawerIssue?.key}
        open={!!drawerIssue}
        onClose={() => setDrawerIssue(null)}
        width={600}
        destroyOnClose
      >
        {drawerIssue && (
          <AnalyticsWorklogsBlock
            issueId={drawerIssue.id}
            periodStart={periodStart}
            periodEnd={periodEnd}
          />
        )}
      </Drawer>
    </>
  );
}
