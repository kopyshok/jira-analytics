import type React from 'react';
import { Table, Tag } from 'antd';
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

interface TreeNode {
  key: string;
  label: React.ReactNode;
  totals: NodeTotals;
  children?: TreeNode[];
}

function buildCategoryNode(
  c: AnalyticsCategoryNode,
  prefix: string,
): TreeNode {
  return {
    key: `${prefix}/c:${c.category_code || '_none'}`,
    label: (
      <span style={{ marginLeft: 32 }}>
        <span
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: 2,
            background: c.color,
            marginRight: 6,
          }}
        />
        {c.label}
      </span>
    ),
    totals: c.totals,
    children: c.issues.map((i: AnalyticsIssueNode) => ({
      key: `${prefix}/c:${c.category_code || '_none'}/i:${i.id}`,
      label: (
        <span style={{ marginLeft: 40 }}>
          <a
            href={`https://example.atlassian.net/browse/${i.key}`}
            target="_blank"
            rel="noreferrer"
          >
            {i.key}
          </a>
          <Tag style={{ marginLeft: 6 }}>{i.status}</Tag>
          {' '}
          {i.summary}
        </span>
      ),
      totals: i.totals,
    })),
  };
}

function buildWorkTypeNode(
  w: AnalyticsWorkTypeNode,
  prefix: string,
): TreeNode {
  return {
    key: `${prefix}/w:${w.work_type_id}`,
    label: <span style={{ marginLeft: 24 }}>{w.label}</span>,
    totals: w.totals,
    children: w.categories.map((c) =>
      buildCategoryNode(c, `${prefix}/w:${w.work_type_id}`),
    ),
  };
}

function buildEmployeeNode(
  e: AnalyticsEmployeeNode,
  prefix: string,
): TreeNode {
  return {
    key: `${prefix}/e:${e.employee_id}`,
    label: <span style={{ marginLeft: 16 }}>{e.name}</span>,
    totals: e.totals,
    children: e.work_types.map((w) =>
      buildWorkTypeNode(w, `${prefix}/e:${e.employee_id}`),
    ),
  };
}

function buildRoleNode(r: AnalyticsRoleNode, prefix: string): TreeNode {
  return {
    key: `${prefix}/r:${r.role_code}`,
    label: (
      <span style={{ color: r.role_color, marginLeft: 8 }}>
        {r.role_label}
      </span>
    ),
    totals: r.totals,
    children: r.employees.map((e) =>
      buildEmployeeNode(e, `${prefix}/r:${r.role_code}`),
    ),
  };
}

function buildAntTreeNode(t: AnalyticsTeamNode): TreeNode {
  const prefix = `team:${t.team || '_none'}`;
  return {
    key: prefix,
    label: <b>{t.team || 'Без команды'}</b>,
    totals: t.totals,
    children: t.roles.map((r) => buildRoleNode(r, prefix)),
  };
}

interface Props {
  data: AnalyticsReportResponse;
  selectedTeam: string | 'all';
  worklogMode: 'inline' | 'drawer';
  periodStart: string;
  periodEnd: string;
}

export default function AnalyticsTable({ data, selectedTeam }: Props) {
  const teams =
    selectedTeam === 'all'
      ? data.teams
      : data.teams.filter(
          (t) => (t.team || '_none_') === selectedTeam,
        );

  const tableData: TreeNode[] = teams.map((t) => buildAntTreeNode(t));

  const columns: ColumnsType<TreeNode> = [
    {
      title: 'Группа / Задача',
      dataIndex: 'label',
      key: 'label',
      width: 400,
    },
    {
      title: 'Часы факт',
      key: 'fact_hours',
      render: (_, r) => r.totals.fact_hours.toFixed(1),
      width: 100,
      align: 'right',
    },
    {
      title: 'Часы план',
      key: 'plan_hours',
      render: (_, r) =>
        r.totals.plan_hours != null
          ? Math.round(r.totals.plan_hours)
          : '—',
      width: 100,
      align: 'right',
    },
    {
      title: '% план',
      key: 'pct_plan',
      render: (_, r) =>
        r.totals.pct_plan != null
          ? `${r.totals.pct_plan.toFixed(0)}%`
          : '—',
      width: 80,
      align: 'right',
    },
    {
      title: '% от итога',
      key: 'pct_total',
      render: (_, r) => `${r.totals.pct_total.toFixed(1)}%`,
      width: 90,
      align: 'right',
    },
    {
      title: 'Ворклогов',
      key: 'worklog_count',
      render: (_, r) => r.totals.worklog_count,
      width: 90,
      align: 'right',
    },
    {
      title: 'Задач',
      key: 'issue_count',
      render: (_, r) => r.totals.issue_count,
      width: 70,
      align: 'right',
    },
    {
      title: 'Сотр.',
      key: 'employee_count',
      render: (_, r) => r.totals.employee_count,
      width: 70,
      align: 'right',
    },
    {
      title: 'Ср.мин',
      key: 'avg_min',
      render: (_, r) => r.totals.avg_worklog_minutes.toFixed(0),
      width: 80,
      align: 'right',
    },
  ];

  return (
    <Table<TreeNode>
      dataSource={tableData}
      columns={columns}
      rowKey="key"
      pagination={false}
      size="small"
      expandable={{
        defaultExpandAllRows: false,
      }}
    />
  );
}
